from unittest.mock import MagicMock, patch

import pytest

from core.database import Video
from core.similar.ranker import (
    SimilarRanker,
)

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
    with patch("core.database.TagAliasRepository", return_value=_mock_alias_repo), \
         patch("core.database.TagBlacklistRepository", return_value=MagicMock(**{"get_all.return_value": []})):
        yield
    _invalidate_cache()

def _v(
    *,
    tags: list[str] | None = None,
    actresses: list[str] | None = None,
    series: str | None = None,
    maker: str = "",
    duration: int | None = None,
    release_date: str = "",
    number: str | None = None,
) -> Video:
    return Video(
        number=number,
        tags=tags or [],
        actresses=actresses or [],
        series=series,
        maker=maker,
        duration=duration,
        release_date=release_date,
    )


def _padded_ranker(extra: list[Video], pad: int = 30) -> SimilarRanker:
    # padding 讓 rare tag IDF > 0 且 jaccard 可計算
    padding = [_v(tags=[f"pad_{i}"]) for i in range(pad)]
    return SimilarRanker(padding + extra)


# --- helper: gaussian_year_proximity ---


# --- helper: same_duration_bucket ---


# --- _score: base / series / maker ---


# --- _score: cast bucket ---


# --- _score: actress penalty ---

def test_score_actress_overlap_diff_series_minus_half():
    target = _v(tags=["rareA"], actresses=["alice"], series="S1")
    cand = _v(tags=["rareA"], actresses=["alice"], series="S2")
    r = _padded_ranker([target, cand])
    # 對照：無 overlap 同 cand
    cand_no_overlap = _v(tags=["rareA"], actresses=["bob"], series="S2")
    rb = _padded_ranker([target, cand_no_overlap])
    assert r._score(target, cand) == pytest.approx(rb._score(target, cand_no_overlap) - 0.50, abs=1e-6)


# --- _score: not clamped ---


# --- _score: full integration sanity ---

def test_score_full_signals_combined():
    target = _v(
        tags=["rareA"],
        actresses=["alice"],
        series="SUPER",
        maker="MK1",
        duration=30,
        release_date="2020",
    )
    cand = _v(
        tags=["rareA"],
        actresses=["bob"],
        series="SUPER",
        maker="MK1",
        duration=50,
        release_date="2020",
    )
    r = _padded_ranker([target, cand])
    bare = _v(tags=["rareA"], actresses=["bob"])
    rb = _padded_ranker([_v(tags=["rareA"], actresses=["alice"]), bare])
    base = rb._score(_v(tags=["rareA"], actresses=["alice"]), bare)
    # 預期： base + series(0.30) + maker(0.20) + year(0.15*1.0) + duration(0.10) ；solo-solo 不加；無 overlap 不扣
    assert r._score(target, cand) == pytest.approx(base + 0.30 + 0.20 + 0.15 + 0.10, abs=1e-6)
