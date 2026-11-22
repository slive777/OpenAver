from unittest.mock import MagicMock, patch

import pytest

from core.database import Video
from core.similar.ranker import SimilarRanker, extract_prefix


@pytest.fixture(autouse=True)
def _isolate_canonicalize_cache():
    """`SimilarRanker` 走 `canonicalize()` → `_load_merged_map()`，module-level
    單例未命中時會連真實 DB 讀 `TagAliasRepository`。

    本檔在 127b-T4 之前**看起來是乾淨的**——因為別的檔先把 `_merged_alias_map`
    暖好了。T4 把那些檔一一隔離之後，這裡就露了出來（sonnet review 的 Finding 1
    逐字點名過本檔會是下一個）。**「report 模式沒報你」不等於「你有隔離」。**

    形狀比照 `test_ranker_cache.py` / `test_similar_api.py` / `test_similar_perf.py`：
    前後各清一次，整個測試體在 mock 保護內。
    """
    from core.similar.canonicalize import _invalidate_cache

    mock_alias_repo = MagicMock()
    mock_alias_repo.get_all.return_value = []
    _invalidate_cache()
    with patch("core.database.TagAliasRepository", return_value=mock_alias_repo), \
         patch("core.database.TagBlacklistRepository", return_value=MagicMock(**{"get_all.return_value": []})):
        yield
    _invalidate_cache()


def _v(
    *,
    id: int | None = None,
    tags: list[str] | None = None,
    actresses: list[str] | None = None,
    series: str | None = None,
    maker: str = "",
    duration: int | None = None,
    release_date: str = "",
    number: str | None = None,
) -> Video:
    return Video(
        id=id,
        number=number,
        tags=tags or [],
        actresses=actresses or [],
        series=series,
        maker=maker,
        duration=duration,
        release_date=release_date,
    )


# ------------------------------------------------------------------
# extract_prefix — CD-57a-5 6 case
# ------------------------------------------------------------------

@pytest.mark.parametrize("number,expected", [
    ("FC2-PPV-12345", "FC2-PPV"),
])
def test_extract_prefix_cases(number, expected):
    assert extract_prefix(number) == expected


# ------------------------------------------------------------------
# Tier 1 happy path：≥2 共同 useful tag → MMR
# ------------------------------------------------------------------


# ------------------------------------------------------------------
# Tier 2 補位：所有 corpus 與 target 只有 ≥1 共同 useful tag
# ------------------------------------------------------------------


# ------------------------------------------------------------------
# Tier 3 prefix 補位：target 0 useful tag → Tier 1/2 跳過
# ------------------------------------------------------------------


# ------------------------------------------------------------------
# Tier 4 兜底：target prefix=None + 0 useful tag → Tier 4 random
# ------------------------------------------------------------------


# ------------------------------------------------------------------
# 嚴格 1 → 2 → 3 → 4 順序
# ------------------------------------------------------------------

def test_strict_tier_order_1_2_3_4():
    # Tier 1 候選 3 部、Tier 2 候選 4 部、Tier 3 候選 5 部，target prefix=ABC
    padding = [_v(id=5000 + i, tags=[f"pad_{i}"]) for i in range(30)]
    target = _v(id=1, number="ABC-001", tags=["rareA", "rareB", "rareC"])
    tier1 = [
        _v(id=100 + i, number=f"OTH-{i:03d}", tags=["rareA", "rareB", f"unique{i}"])
        for i in range(3)
    ]
    tier2 = [
        _v(id=200 + i, number=f"OTHER-{i:03d}", tags=["rareA", f"u2_{i}"])
        for i in range(4)
    ]
    tier3 = [
        _v(id=300 + i, number=f"ABC-{i + 100:03d}", tags=[f"u3_{i}"])
        for i in range(5)
    ]
    r = SimilarRanker(padding + [target] + tier1 + tier2 + tier3)
    out = r.rank(target, top_k=12)

    # 前 3 部必須來自 tier1 ids
    tier1_ids = {100, 101, 102}
    tier2_ids = {200, 201, 202, 203}
    tier3_ids = {300, 301, 302, 303, 304}
    assert {c.id for c in out[:3]} == tier1_ids
    # 接下來 4 部必須是 tier2
    assert {c.id for c in out[3:7]} == tier2_ids
    # 接下來 5 部必須是 tier3
    assert {c.id for c in out[7:12]} == tier3_ids


# ------------------------------------------------------------------
# MMR diversity：corpus 含 5 部同片商連續 → top-12 不全是同片商前 5
# ------------------------------------------------------------------


# ------------------------------------------------------------------
# corpus 同女優連 3 部 → 結果多樣化
# ------------------------------------------------------------------


# ------------------------------------------------------------------
# P1-B regression：hot-only overlap（IDF=0） → 不走 Tier 1/2
# ------------------------------------------------------------------

def test_regression_p1b_hot_only_overlap_falls_to_tier3_or_4():
    # corpus 30 部都含「common」tag（df/N=30/30=1.0 > 0.25 → IDF=0 hot）
    # 各自 unique rare tag → IDF > 0
    corpus = [
        _v(id=100 + i, number=f"ABC-{i:03d}", tags=["common", f"unique_{i}"])
        for i in range(30)
    ]
    # target 只有 hot tag「common」
    target = _v(id=1, number="ABC-999", tags=["common"])
    r = SimilarRanker(corpus + [target])
    # target_useful 應為空（common IDF=0）
    target_useful = r._useful_set(target)
    assert target_useful == set()
    out = r.rank(target, top_k=12)
    assert len(out) == 12
    # 因 useful=∅，Tier 1/2 都跳過 → Tier 3 prefix=ABC 補滿
    assert all(c.number and c.number.startswith("ABC") for c in out)


# ------------------------------------------------------------------
# P1-A regression：MMR 符號減號（寫成 + 此 test 必 fail）
# ------------------------------------------------------------------

def test_regression_p1a_mmr_minus_sign_diversity():
    padding = [_v(id=8000 + i, tags=[f"pad_{i}"]) for i in range(60)]
    target = _v(id=1, tags=["rareA", "rareB"], actresses=["actor_t"], maker="MK_TARGET")
    # 5 部同女優同片商高 rel → 互相 sim=1.0
    cluster = [
        _v(id=200 + i, tags=["rareA", "rareB", f"c_{i}"], actresses=["Actress_X"], maker="Maker_Y")
        for i in range(5)
    ]
    # 7 部 diverse
    diverse = [
        _v(id=210 + i, tags=["rareA", "rareB", f"d_{i}"], actresses=[f"a_{i}"], maker=f"MK_{i}")
        for i in range(7)
    ]
    r = SimilarRanker(padding + [target] + cluster + diverse)
    out = r.rank(target, top_k=12)
    # 12 部全進（5 + 7）；關鍵是「順序」不同
    assert len(out) == 12
    # 寫成 + 會把 5 部 Actress_X 全排前 → top-5 都是 Actress_X
    # 寫成 - 會穿插 → top-5 中 Actress_X 應 < 5
    top5_actress_x = sum(1 for c in out[:5] if c.actresses == ["Actress_X"])
    assert top5_actress_x < 5
    # top-5 中 Maker_Y 也應 < 5
    top5_maker_y = sum(1 for c in out[:5] if c.maker == "Maker_Y")
    assert top5_maker_y < 5
    # 整體 top-12 不同女優數應分散
    distinct_actresses = {tuple(c.actresses) for c in out}
    assert len(distinct_actresses) >= 6


# ------------------------------------------------------------------
# P2-A regression：target 不同物件實例同 number 必排除（id=None 兩邊都走 num fallback）
# ------------------------------------------------------------------

def test_regression_p2a_same_number_different_object_excluded():
    # 加 padding 避免 hot 化
    padding = [_v(id=9000 + i, tags=[f"pad_{i}"]) for i in range(30)]
    # corpus video A: id=None, number="ABP-001"
    a = _v(id=None, number="ABP-001", tags=["巨乳"])
    # 加幾部其他可被選的 corpus
    others = [_v(id=500 + i, tags=[f"o_{i}"]) for i in range(5)]
    # target B: 不同 Python object，但 id=None + number="ABP-001" 相同
    b = _v(id=None, number="ABP-001", tags=["巨乳"])
    r = SimilarRanker(padding + [a] + others)
    # 確認 stable_key 撞
    assert SimilarRanker._stable_key(a) == ('num', 'ABP-001')
    assert SimilarRanker._stable_key(b) == ('num', 'ABP-001')
    assert SimilarRanker._stable_key(a) == SimilarRanker._stable_key(b)
    # 確認 a 與 b 是不同 object
    assert a is not b
    out = r.rank(b, top_k=12)
    # a 不應出現於結果
    assert a not in out
    # 但 number 相同的 a 也透過 stable_key 被排除
    assert all(c.number != "ABP-001" or c is not a for c in out)


# ------------------------------------------------------------------
# rank() 邊界穩定性 4-in-1
# ------------------------------------------------------------------


# ------------------------------------------------------------------
# _stable_key 三段 fallback 直接 unit test
# ------------------------------------------------------------------


# ------------------------------------------------------------------
# 永遠 ≤ top_k
# ------------------------------------------------------------------


# ------------------------------------------------------------------
# Tier 3 prefix 不命中 → fall to Tier 4
# ------------------------------------------------------------------

    # 全部走 Tier 4 random（包含 padding 與 others）


# ------------------------------------------------------------------
# Tier 2 公式：maker bonus + actress penalty
# ------------------------------------------------------------------


# ------------------------------------------------------------------
# Tier 1 contract regression
# ------------------------------------------------------------------

