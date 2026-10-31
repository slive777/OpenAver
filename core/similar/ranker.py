from __future__ import annotations

import math
import random
import re
from collections import defaultdict
from typing import TYPE_CHECKING

from core.similar.canonicalize import canonicalize
from core.similar.cast_bucket import cast_bucket
from core.similar.idf import build_idf, idf_jaccard, IDF_HOT_THRESHOLD  # noqa: F401

if TYPE_CHECKING:
    from core.database import Video
    from array import array as ArrayType

# CD-186-14：RRF 融合權重（只此一處）
RRF_K = 60
RRF_RULE_WEIGHT = 1.0
RRF_VECTOR_WEIGHT = 1.0


# CD-57a-5：番號 prefix 提取，支援多段 prefix（FC2-PPV 等）
_PREFIX_RE = re.compile(
    r'^([A-Za-z][A-Za-z0-9]*(?:-[A-Za-z][A-Za-z0-9]*)*)(?=-?\d)',
    re.IGNORECASE,
)


def extract_prefix(number: str | None) -> str | None:
    if not number:
        return None
    m = _PREFIX_RE.match(number)
    return m.group(1).upper() if m else None


# spec-57 §2.4 helper：release_date 解析失敗 → 0.0；公式 exp(-0.5*(diff/sigma)^2)
def gaussian_year_proximity(cand: Video, target: Video, sigma: float = 4) -> float:
    cy = _extract_year(cand.release_date)
    ty = _extract_year(target.release_date)
    if cy is None or ty is None:
        return 0.0
    diff = cy - ty
    return math.exp(-0.5 * (diff / sigma) ** 2)


# spec-57 §2.4 三桶（≤20 / 20-60 / 60+）；任一邊 None/0（無資訊）→ False
def same_duration_bucket(cand: Video, target: Video) -> bool:
    cd = cand.duration
    td = target.duration
    if not cd or not td:
        return False
    return _bucket(cd) == _bucket(td)


def _extract_year(release_date: str | None) -> int | None:
    if not release_date:
        return None
    m = re.match(r"^(\d{4})", release_date)
    return int(m.group(1)) if m else None


def _bucket(minutes: int) -> int:
    if minutes <= 20:
        return 0
    if minutes <= 60:
        return 1
    return 2


class SimilarRanker:
    def __init__(self, corpus: list[Video]) -> None:
        self._corpus: list[Video] = corpus
        # CD-57a-3：建構期預先 canonicalize，rank() / _retrieve() 不重做
        self._canon_tags: list[list[str]] = [canonicalize(v.tags) for v in corpus]
        # CD-57a-9：IDF 只看 v.tags（_canon_tags），不含 user_tags
        self._idf_table: dict[str, float] = build_idf(self._canon_tags)
        self._inverted_index: dict[str, list[int]] = {}
        for i, tags in enumerate(self._canon_tags):
            # set() 去 per-video 重複；canonicalize 已去重，這裡是 belt-and-suspenders
            for t in set(tags):
                # 嚴格 > 0：hot tag (IDF=0) 與 OOV 都不入索引
                if self._idf_table.get(t, 0.0) > 0:
                    self._inverted_index.setdefault(t, []).append(i)

    def _retrieve(
        self,
        target_tags: list[str],
        exclude: Video | None = None,
        top_n: int = 100,
    ) -> list[Video]:
        useful = [t for t in target_tags if self._idf_table.get(t, 0.0) > 0]
        if not useful:
            return []
        scores: dict[int, float] = defaultdict(float)
        for t in useful:
            idf = self._idf_table[t]
            for i in self._inverted_index.get(t, []):
                scores[i] += idf
        # 用 object identity 排除 target 自身（id=None / number 重複場景皆穩）
        if exclude is not None:
            filtered = [(i, s) for i, s in scores.items() if self._corpus[i] is not exclude]
        else:
            filtered = list(scores.items())
        filtered.sort(key=lambda kv: kv[1], reverse=True)
        return [self._corpus[i] for i, _ in filtered[:top_n]]

    # spec-57 §2.4：base + series/maker/year/duration/cast bonus + actress penalty（同系列例外）；不 clamp
    def _score(self, target: Video, cand: Video) -> float:
        target_canon = set(canonicalize(target.tags))
        cand_canon = set(canonicalize(cand.tags))
        rel = idf_jaccard(target_canon, cand_canon, self._idf_table)

        if cand.series and cand.series == target.series:
            rel += 0.30
        if cand.maker and cand.maker == target.maker:
            rel += 0.20
        rel += 0.15 * gaussian_year_proximity(cand, target, sigma=4)
        if same_duration_bucket(cand, target):
            rel += 0.10

        tgt_b = cast_bucket(target.actresses)
        cnd_b = cast_bucket(cand.actresses)
        if tgt_b == cnd_b and tgt_b in ("duo", "multi"):
            rel += 0.20

        if set(target.actresses) & set(cand.actresses):
            if cand.series and cand.series == target.series:
                rel -= 0.15
            else:
                rel -= 0.50

        return rel

    # CD-57a-6：id → number → object id 三段 fallback
    @staticmethod
    def _stable_key(video) -> tuple:
        if getattr(video, 'id', None) is not None:
            return ('id', video.id)
        if getattr(video, 'number', None):
            return ('num', video.number)
        return ('mem', id(video))

    # Q-T6-1 方案 B：實時計算（per-call 微小成本）
    def _useful_set(self, video) -> set[str]:
        return {t for t in canonicalize(video.tags) if self._idf_table.get(t, 0.0) > 0}

    # CD-57a-4：MMR similarity = actress jaccard * 0.7 + maker match * 0.3
    def _sim(self, a: Video, b: Video) -> float:
        sa, sb = set(a.actresses or []), set(b.actresses or [])
        actress_jac = len(sa & sb) / len(sa | sb) if (sa or sb) else 0.0
        maker_match = 1.0 if (a.maker and a.maker == b.maker) else 0.0
        return actress_jac * 0.7 + maker_match * 0.3

    # CD-57a-4：mmr = λ·rel − (1−λ)·max_sim；減號絕對不可變加號
    # CD-186-14：選填 rel（給定時取代 _score；鍵＝id(c)）
    def _mmr_rerank(
        self,
        target: Video,
        candidates: list[Video],
        top_k: int = 12,
        rel: dict[int, float] | None = None,
    ) -> list[Video]:
        if not candidates or top_k <= 0:
            return []
        lambda_ = 0.7
        rel_cache = rel if rel is not None else {id(c): self._score(target, c) for c in candidates}
        remaining = list(candidates)
        selected: list[Video] = []
        while remaining and len(selected) < top_k:
            best = None
            best_score = float('-inf')
            for c in remaining:
                rel_v = rel_cache[id(c)]
                max_sim = max((self._sim(c, s) for s in selected), default=0.0)
                mmr = lambda_ * rel_v - (1 - lambda_) * max_sim
                if mmr > best_score:
                    best_score = mmr
                    best = c
            selected.append(best)
            remaining.remove(best)
        return selected

    # spec-57 §2.4 Tier 2：0.3·shared + 0.5·same_maker + 0.4·same_series（raw count + truthy guard + actress penalty）
    def _fallback_tier2(
        self,
        target: Video,
        target_canon: list[str],
        target_useful: set[str],
        exclude_keys: set[tuple],
        fill_n: int,
    ) -> list[Video]:
        if fill_n <= 0:
            return []
        scored: list[tuple[Video, float]] = []
        for c in self._corpus:
            if c is target or self._stable_key(c) in exclude_keys:
                continue
            cand_useful = self._useful_set(c)
            shared = len(target_useful & cand_useful)
            if shared < 1:
                continue
            score = 0.3 * shared
            if c.maker and c.maker == target.maker:
                score += 0.5
            if c.series and c.series == target.series:
                score += 0.4
            if set(target.actresses or []) & set(c.actresses or []):
                if c.series and c.series == target.series:
                    score -= 0.15
                else:
                    score -= 0.50
            scored.append((c, score))
        scored.sort(key=lambda kv: kv[1], reverse=True)
        return [c for c, _ in scored[:fill_n]]

    # CD-57a-5 + CD-57a-7 + CD-57a-11：同 prefix random，不 seed；prefix=None 直接回 []
    def _fallback_tier3(self, target: Video, exclude_keys: set[tuple], fill_n: int) -> list[Video]:
        if fill_n <= 0:
            return []
        target_prefix = extract_prefix(getattr(target, 'number', None))
        if target_prefix is None:
            return []
        pool = [
            c for c in self._corpus
            if c is not target
            and self._stable_key(c) not in exclude_keys
            and extract_prefix(getattr(c, 'number', None)) == target_prefix
        ]
        if not pool:
            return []
        return random.sample(pool, min(fill_n, len(pool)))

    # CD-57a-11：全庫 random 兜底，不 seed
    def _fallback_tier4(self, target: Video, exclude_keys: set[tuple], fill_n: int) -> list[Video]:
        if fill_n <= 0:
            return []
        pool = [
            c for c in self._corpus
            if c is not target and self._stable_key(c) not in exclude_keys
        ]
        if not pool:
            return []
        return random.sample(pool, min(fill_n, len(pool)))

    def _rule_path_for_fusion(self, target: Video) -> list[Video]:
        """融合規則路：_retrieve 前 100，剔 target，依 _score 降冪；不套 Tier1 ≥2 門檻。"""
        retrieved = self._retrieve(canonicalize(target.tags), exclude=target, top_n=100)
        target_key = self._stable_key(target)
        rule = [c for c in retrieved if self._stable_key(c) != target_key]
        rule.sort(key=lambda c: self._score(target, c), reverse=True)
        return rule

    def _vector_path_for_fusion(
        self,
        target: Video,
        vectors: dict[int, ArrayType],
    ) -> list[Video]:
        """融合向量路：全量點積降冪後剔同女優非同系列，取前 30。"""
        q = vectors[target.id]
        scored: list[tuple[Video, float]] = []
        for c in self._corpus:
            if c.id is None or c.id == target.id or c.id not in vectors:
                continue
            scored.append((c, math.sumprod(q, vectors[c.id])))
        scored.sort(key=lambda kv: kv[1], reverse=True)
        vec: list[Video] = []
        for c, _ in scored:
            shares = set(target.actresses) & set(c.actresses)
            same_series = c.series and c.series == target.series
            if not (shares and not same_series):
                vec.append(c)
                if len(vec) >= 30:
                    break
        return vec

    def _rrf_rel(
        self,
        rule: list[Video],
        vec: list[Video],
    ) -> tuple[list[Video], dict[int, float]]:
        """RRF 合成候選列（規則路在前）與正規化 rel（鍵＝id(c)）。"""
        rr = {id(c): r for r, c in enumerate(rule)}
        vr = {id(c): r for r, c in enumerate(vec)}
        pool: dict[int, Video] = {}
        ordered: list[Video] = []
        for c in rule + vec:
            i = id(c)
            if i in pool:
                continue
            pool[i] = c
            ordered.append(c)
        score = {
            i: (
                (RRF_RULE_WEIGHT / (RRF_K + rr[i]) if i in rr else 0.0)
                + (RRF_VECTOR_WEIGHT / (RRF_K + vr[i]) if i in vr else 0.0)
            )
            for i in pool
        }
        mx = max(score.values()) if score else 1.0
        if mx <= 0:
            mx = 1.0
        rel = {i: score[i] / mx for i in score}
        ordered.sort(key=lambda c: rel[id(c)], reverse=True)
        return ordered, rel

    def _fill_fallbacks(
        self,
        target: Video,
        top_k: int,
        result: list[Video],
        selected_keys: set[tuple],
    ) -> list[Video]:
        """Tier2／3／4 補位（融合與今天路徑共用）。"""
        if len(result) >= top_k:
            return result
        target_canon = canonicalize(target.tags)
        target_useful = {t for t in target_canon if self._idf_table.get(t, 0.0) > 0}

        if len(result) < top_k:
            for c in self._fallback_tier2(target, target_canon, target_useful, selected_keys, top_k - len(result)):
                k = self._stable_key(c)
                if k in selected_keys:
                    continue
                selected_keys.add(k)
                result.append(c)
                if len(result) >= top_k:
                    return result

        if len(result) < top_k:
            for c in self._fallback_tier3(target, selected_keys, top_k - len(result)):
                k = self._stable_key(c)
                if k in selected_keys:
                    continue
                selected_keys.add(k)
                result.append(c)
                if len(result) >= top_k:
                    return result

        if len(result) < top_k:
            for c in self._fallback_tier4(target, selected_keys, top_k - len(result)):
                k = self._stable_key(c)
                if k in selected_keys:
                    continue
                selected_keys.add(k)
                result.append(c)
                if len(result) >= top_k:
                    return result

        return result

    def _rank_fused(
        self,
        target: Video,
        top_k: int,
        vectors: dict[int, ArrayType],
    ) -> list[Video]:
        """CD-186-14：規則路 ∪ 向量路 → RRF → MMR(rel) → Tier2／3／4。"""
        rule = self._rule_path_for_fusion(target)
        vec = self._vector_path_for_fusion(target, vectors)
        ordered, rel = self._rrf_rel(rule, vec)
        selected_keys: set[tuple] = {self._stable_key(target)}
        result: list[Video] = []
        for c in self._mmr_rerank(target, ordered, top_k=top_k, rel=rel):
            k = self._stable_key(c)
            if k in selected_keys:
                continue
            selected_keys.add(k)
            result.append(c)
            if len(result) >= top_k:
                return result
        return self._fill_fallbacks(target, top_k, result, selected_keys)

    # spec-57 §2.4：Stage 1 retrieve → Stage 2 score → Stage 3 MMR → Tier 2/3/4 fallback
    # CD-186-14：vectors 閘——None 或不含 target.id → 今天路徑一行不變
    def rank(
        self,
        target: Video,
        top_k: int = 12,
        vectors: dict[int, ArrayType] | None = None,
    ) -> list[Video]:
        if not self._corpus or top_k <= 0:
            return []

        if vectors is None or target.id not in vectors:
            target_canon = canonicalize(target.tags)
            target_useful = {t for t in target_canon if self._idf_table.get(t, 0.0) > 0}

            selected_keys: set[tuple] = {self._stable_key(target)}
            result: list[Video] = []

            retrieved = self._retrieve(target_canon, exclude=target, top_n=100)
            # Codex P1 fix：DB 場景 target 可能是 corpus 內 row 的另一個 Python object
            # （`_retrieve` 的 `is` 排不掉），用 stable_key 兜底防 Tier 1 slot 被 target 副本占用
            target_key = self._stable_key(target)
            tier1_pool = [
                c for c in retrieved
                if self._stable_key(c) != target_key
                and len(target_useful & self._useful_set(c)) >= 2
            ]
            for c in self._mmr_rerank(target, tier1_pool, top_k=top_k):
                k = self._stable_key(c)
                if k in selected_keys:
                    continue
                selected_keys.add(k)
                result.append(c)
                if len(result) >= top_k:
                    return result

            return self._fill_fallbacks(target, top_k, result, selected_keys)

        return self._rank_fused(target, top_k, vectors)
