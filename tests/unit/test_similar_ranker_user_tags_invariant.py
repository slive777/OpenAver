"""188a：user tag 與刮削標籤同權重。

被鎖行為現已正確；本檔以行為測試鎖住，不以原始碼字面守衛。
fixture 刻意讓 df 比例落在 hot 門檻之下，rank(top_k=12) 在 Tier 1 填滿——
不得用 random.seed() 掩蓋 fallback 非決定性。
"""

import pytest
from unittest.mock import MagicMock, patch
from core.database import Video
from core.similar.ranker import SimilarRanker
from tests.unit.test_similar_fusion import _build_base_corpus, _fill_vectors, _unit

@pytest.fixture(autouse=True)
def _isolate_canonicalize_cache():
    """`SimilarRanker` 走 `canonicalize()` → `_load_merged_map()`，module-level
    單例未命中時會連真實 DB 讀 `TagAliasRepository`。

    本檔在 127b-T4 之前看起來乾淨，是因為別的檔先把 `_merged_alias_map` 暖好了。
    T4 逐一隔離之後才露出來——**「report 模式沒報你」不等於「你有隔離」**。
    sonnet review 的 Finding 1 已逐字點名本族還有哪些檔沒隔離，這裡一次補齊。

    形狀比照 `test_ranker_cache.py` / `test_similar_api.py` / `test_similar_perf.py`。
    """
    from core.similar.canonicalize import _invalidate_cache

    _mock_alias_repo = MagicMock()
    _mock_alias_repo.get_all.return_value = []
    _invalidate_cache()
    with patch("core.database.TagAliasRepository", return_value=_mock_alias_repo):
        yield
    _invalidate_cache()

_TIER1_CANARY_MSG = (
    "Tier 1 已不再填滿 → 排序斷言不再具決定性 → "
    "請重新設計 fixture 的 df 比例，不要用 random seed 掩蓋"
)

_SHARED_TAGS = ["痴女", "中出"]
_N_CORE = 13  # target + 12 候選
_N_PAD = 47
_TOP_K = 12


def _build_corpus(with_user_tags: bool) -> list[Video]:
    """N=60：前 13 部共享兩個 tag（13/60=21.7% ≤ 0.25），後 47 部壓 df。"""
    videos: list[Video] = []
    for i in range(_N_CORE):
        user_tags = ["中字", f"手動{i}"] if with_user_tags else []
        videos.append(
            Video(
                number=f"CORE-{i:03d}",
                tags=_SHARED_TAGS + [f"獨有{i}"],
                user_tags=user_tags,
            )
        )
    for i in range(_N_PAD):
        user_tags = ["中字", f"手動P{i}"] if with_user_tags else []
        videos.append(
            Video(
                number=f"PAD-{i:03d}",
                tags=[f"雜訊{i}"],
                user_tags=user_tags,
            )
        )
    return videos


def test_user_tags_lower_score_but_preserve_rank_order():
    """同 fixture：序列仍相同，但 dirty._score 逐項嚴格低於 clean（IDF 分母含獨有 user tag）。"""
    clean_corpus = _build_corpus(False)
    dirty_corpus = _build_corpus(True)
    clean = SimilarRanker(clean_corpus)
    dirty = SimilarRanker(dirty_corpus)
    clean_target = clean_corpus[0]
    dirty_target = dirty_corpus[0]

    clean_out = clean.rank(clean_target, top_k=_TOP_K)
    dirty_out = dirty.rank(dirty_target, top_k=_TOP_K)

    assert [v.number for v in clean_out] == [v.number for v in dirty_out]
    for c_cand, d_cand in zip(clean_out, dirty_out, strict=True):
        assert dirty._score(dirty_target, d_cand) < clean._score(clean_target, c_cand)


def test_golden_rule_path_matches_pre_188a():
    """規則路排序與分數基線。

    使用者流程：沒有任何 user tag 時，升級後星空前 12 名換了。
    字面值取自 05866a69（188a 之前）；若日後刻意改排序，改這裡必須同時改 CHANGELOG。
    """
    corpus = _build_corpus(False)
    ranker = SimilarRanker(corpus)
    target = corpus[0]
    out = ranker.rank(target, top_k=12)

    assert [v.number for v in out] == [
        "CORE-001",
        "CORE-002",
        "CORE-003",
        "CORE-004",
        "CORE-005",
        "CORE-006",
        "CORE-007",
        "CORE-008",
        "CORE-009",
        "CORE-010",
        "CORE-011",
        "CORE-012",
    ]
    assert [repr(ranker._score(target, v)) for v in out] == ["0.3587779996848771"] * 12


def test_golden_fusion_path_matches_pre_188a():
    """融合路排序基線。

    使用者流程：沒有任何 user tag 時，升級後星空前 12 名換了。
    字面值取自 05866a69（188a 之前）；若日後刻意改排序，改這裡必須同時改 CHANGELOG。
    """
    corpus, target, dim = _build_base_corpus()
    ranker = SimilarRanker(corpus)
    vectors = _fill_vectors(corpus, {1: _unit(dim, 0), 200: _unit(dim, 1)}, dim)
    out = ranker.rank(target, vectors=vectors)

    assert [v.id for v in out] == [105, 100, 5014, 101, 5030, 102, 103, 5000, 104, 5001, 5002, 106]


def test_user_tag_lifts_one_scraped_tag_candidate_into_tier1():
    """① 兩部片共 1 刮削＋1 user tag → 進 Tier1 前幾名；清空後被同片商 decoy 擠出。"""
    target = Video(
        number="TGT-001",
        tags=["rareA", "rareT"],
        user_tags=["校服"],
        maker="MakerT",
    )
    strong = [
        Video(
            number=f"STR-{i:03d}",
            tags=["rareA", "rareT", f"s{i}"],
            maker=f"MS{i}",
        )
        for i in range(2)
    ]
    x = Video(
        number="X-001",
        tags=["rareA", "x_only"],
        user_tags=["校服"],
        maker="MX",
    )
    decoys = [
        Video(
            number=f"DEC-{i:03d}",
            tags=["rareA", f"d{i}"],
            maker="MakerT",
        )
        for i in range(6)
    ]
    pads = [
        Video(number=f"PAD-{i:03d}", tags=[f"pad{i}"])
        for i in range(40)
    ]
    corpus = [target, *strong, x, *decoys, *pads]
    ranker = SimilarRanker(corpus)
    out = ranker.rank(target, top_k=3)
    assert [v.number for v in out] == ["X-001", "STR-000", "STR-001"]
    score_with = ranker._score(target, x)

    target.user_tags = []
    x.user_tags = []
    ranker2 = SimilarRanker(corpus)
    out2 = ranker2.rank(target, top_k=3)
    assert [v.number for v in out2] == ["STR-000", "STR-001", "DEC-000"]
    assert "X-001" not in [v.number for v in out2]
    score_without = ranker2._score(target, x)
    assert score_with > score_without


def test_user_tag_reaches_fusion_rule_path():
    """② 刮削零交集、只共 user tag → 開圖片相似也進榜；清空後不在榜且分數為 0。"""
    dim = 16
    target = Video(id=1, number="T-001", tags=["tA", "tB"], user_tags=["校服"])
    x = Video(id=200, number="X-001", tags=["xq"], user_tags=["校服"])
    pads = [
        Video(id=5000 + i, number=f"PAD-{i:03d}", tags=[f"pad{i}"])
        for i in range(60)
    ]
    corpus = [target, x, *pads]
    vectors = {1: _unit(dim, 0), 200: _unit(dim, 5)}
    for p in pads:
        vectors[p.id] = _unit(dim, 0)
    ranker = SimilarRanker(corpus)
    out = ranker.rank(target, vectors=vectors)
    assert x in out
    score_with = ranker._score(target, x)

    target.user_tags = []
    x.user_tags = []
    ranker2 = SimilarRanker(corpus)
    out2 = ranker2.rank(target, vectors=vectors)
    assert x not in out2
    assert ranker2._score(target, x) == 0.0
    assert score_with > 0.0


def test_user_tag_fills_tier2_when_nothing_else_shared():
    """③ 小片庫只共 1 個 user tag → Tier2 補入為唯一結果。"""
    target = Video(number="TGT-001", tags=["tA"], user_tags=["校服"])
    x = Video(number="X-001", tags=["xq"], user_tags=["校服"])
    pads = [
        Video(number=f"PAD-{i:03d}", tags=[f"pad{i}"])
        for i in range(40)
    ]
    corpus = [target, x, *pads]
    ranker = SimilarRanker(corpus)
    out = ranker.rank(target, top_k=1)
    assert [v.number for v in out] == ["X-001"]


def test_hot_user_tag_is_ignored_cold_one_counts():
    """④ 貼超過 1/4 片庫的 user tag 無效；貼在 ≤25% 時影響排序。"""
    def _build(n_h_pads: int) -> tuple[list[Video], Video]:
        target = Video(number="CRE-000", tags=["c1", "c2"], user_tags=["H"])
        cores = [
            Video(
                number=f"CRE-{i:03d}",
                tags=["c1", "c2", f"u{i}"],
                user_tags=["H"] if i >= 11 else [],
            )
            for i in range(1, 15)
        ]
        pads = []
        for i in range(65):
            ut = ["H"] if i < n_h_pads else []
            pads.append(Video(number=f"PAD-{i:03d}", tags=[f"pad{i}"], user_tags=ut))
        corpus = [target, *cores, *pads]
        return corpus, target

    # hot：H 在 T + 最後 4 core + 18 pad = 23/80 = 28.75%
    hot_corpus, hot_t = _build(18)
    hot_r = SimilarRanker(hot_corpus)
    hot_out = hot_r.rank(hot_t, top_k=4)
    hot_nums = [v.number for v in hot_out]
    hot_scores = [hot_r._score(hot_t, v) for v in hot_out]

    for v in hot_corpus:
        v.user_tags = []
    hot_r2 = SimilarRanker(hot_corpus)
    hot_out2 = hot_r2.rank(hot_t, top_k=4)
    assert [v.number for v in hot_out2] == hot_nums == [
        "CRE-001", "CRE-002", "CRE-003", "CRE-004",
    ]
    for a, b in zip(hot_scores, [hot_r2._score(hot_t, v) for v in hot_out2], strict=True):
        assert a == pytest.approx(b)

    # cold：H 在 T + 最後 4 core + 8 pad = 13/80 = 16.25%
    cold_corpus, cold_t = _build(8)
    cold_r = SimilarRanker(cold_corpus)
    cold_with = [v.number for v in cold_r.rank(cold_t, top_k=4)]
    for v in cold_corpus:
        v.user_tags = []
    cold_r2 = SimilarRanker(cold_corpus)
    cold_without = [v.number for v in cold_r2.rank(cold_t, top_k=4)]
    assert cold_with == ["CRE-011", "CRE-012", "CRE-013", "CRE-014"]
    assert cold_without == ["CRE-001", "CRE-002", "CRE-003", "CRE-004"]
    assert cold_with != cold_without


@pytest.mark.parametrize(
    "tags,user_tags,expected",
    [
        (["中出し"], ["中出"], ["中出し"]),
        (["痴女"], ["中文字幕"], ["痴女"]),
    ],
    ids=["alias", "stopword"],
)
def test_user_tag_uses_alias_and_stopword_rules(tags, user_tags, expected):
    """⑤ user tag 走別名合併與停用詞過濾，與刮削標籤同規則。"""
    from core.similar.canonicalize import canonical_video_tags

    video = Video(number="V-001", tags=tags, user_tags=user_tags)
    assert canonical_video_tags(video) == expected


def test_non_string_tag_elements_are_skipped_ranker_still_works():
    """user_tags／tags 含 dict／None／int 時星空仍建得起來；字串標籤仍有效。"""
    target = Video(
        number="TGT-001",
        tags=["tA", {"bad": True}, None, 7],
        user_tags=[{"x": 1}, None, 42, "校服"],
    )
    x = Video(number="X-001", tags=["xq"], user_tags=["校服"])
    pads = [
        Video(number=f"PAD-{i:03d}", tags=[f"pad{i}"])
        for i in range(40)
    ]
    corpus = [target, x, *pads]
    ranker = SimilarRanker(corpus)
    out = ranker.rank(target, top_k=1)
    assert [v.number for v in out] == ["X-001"]
