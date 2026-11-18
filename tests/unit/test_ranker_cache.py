"""
tests/unit/test_ranker_cache.py
SimilarRankerCache singleton — 全 mock，不碰真 DB
"""
from unittest.mock import MagicMock, patch

import pytest


# ──────────────────────────────────────────────────────────
# Fixture：每個 test 前後 reset class state，避免互相污染
# ──────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def reset_cache():
    """每個 test 前後都 reset SimilarRankerCache state，避免 test 間互相污染。

    SimilarRanker.__init__ 內部會呼叫 canonicalize()，其 _load_merged_map()
    在 module-level cache 為 None 時會 lazy-import core.database.TagAliasRepository
    連真實 DB（見 tests/unit/test_similar_canonicalize.py 的 isolate_canonicalize_cache
    同一手法）。這裡比照該既有慣例：mock 掉 TagAliasRepository 並前後清 cache，
    避免本檔案第一支呼叫 .get() 的測試連到 output/openaver.db。
    """
    from core.similar.ranker_cache import SimilarRankerCache
    from core.similar.canonicalize import _invalidate_cache

    SimilarRankerCache._instance = None
    _invalidate_cache()
    mock_alias_repo = MagicMock()
    mock_alias_repo.get_all.return_value = []
    with patch("core.database.TagAliasRepository", return_value=mock_alias_repo):
        yield
    SimilarRankerCache._instance = None
    _invalidate_cache()


# ──────────────────────────────────────────────────────────
# T1：首次 get() 建立 SimilarRanker instance
# ──────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────
# T2：兩次 get() 回傳同一物件（identity）
# ──────────────────────────────────────────────────────────
def test_get_returns_same_instance():
    from core.similar.ranker_cache import SimilarRankerCache

    mock_video = MagicMock()
    with patch("core.similar.ranker_cache.VideoRepository") as mock_repo_cls:
        mock_repo_cls.return_value.get_all.return_value = [mock_video]
        a = SimilarRankerCache.get()
        b = SimilarRankerCache.get()

    assert a is b


# ──────────────────────────────────────────────────────────
# T3：invalidate() 後 get() 回傳新 instance
# ──────────────────────────────────────────────────────────
def test_invalidate_clears_cache():
    from core.similar.ranker_cache import SimilarRankerCache

    mock_video = MagicMock()
    with patch("core.similar.ranker_cache.VideoRepository") as mock_repo_cls:
        mock_repo_cls.return_value.get_all.return_value = [mock_video]
        a = SimilarRankerCache.get()
        SimilarRankerCache.invalidate()
        b = SimilarRankerCache.get()

    assert a is not b


# ──────────────────────────────────────────────────────────
# T4：從未 get() 直接 invalidate() — no-op，不拋例外
# ──────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────
# T5：多執行緒同時 get() — SimilarRanker 只 build 一次
# ──────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────
# T6：同 thread 內 get → invalidate → get，驗不死鎖（RLock）
# ──────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────
# T7：import 時不觸發 DB（lazy）
# ──────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────
# T8：空 corpus get() 正常不拋例外
# ──────────────────────────────────────────────────────────
def test_get_empty_corpus():
    from core.similar.ranker_cache import SimilarRankerCache
    from core.similar.ranker import SimilarRanker

    with patch("core.similar.ranker_cache.VideoRepository") as mock_repo_cls:
        mock_repo_cls.return_value.get_all.return_value = []
        result = SimilarRankerCache.get()

    assert result is not None
    assert isinstance(result, SimilarRanker)


# ──────────────────────────────────────────────────────────
# T9：改 user_rating 不影響相似排名（TASK-201-T2 A12）
# ──────────────────────────────────────────────────────────
def test_changing_only_user_rating_preserves_rank_order():
    """同語料只差 user_rating → rank() 的 number 序列逐位相同且排名非空。"""
    from core.database import Video
    from core.similar.ranker_cache import SimilarRankerCache

    def _corpus(rating: int):
        target = Video(
            number="TGT-001", tags=["rareA", "rareB", "t_only"],
            maker="MakerT", user_rating=rating,
        )
        cands = [
            Video(
                number=f"CAND-{i:03d}", tags=["rareA", "rareB", f"u{i}"],
                maker=f"Maker{i}",
            )
            for i in range(12)
        ]
        pads = [
            Video(number=f"PAD-{i:03d}", tags=[f"pad{i}"])
            for i in range(60)
        ]
        return [target, *cands, *pads]

    videos = _corpus(0)
    with patch("core.similar.ranker_cache.VideoRepository") as mock_repo_cls:
        mock_repo_cls.return_value.get_all.return_value = videos
        first = SimilarRankerCache.get()
        out_before = first.rank(videos[0])
        assert len(out_before) > 0

    for v in videos:
        v.user_rating = 3
    with patch("core.similar.ranker_cache.VideoRepository") as mock_repo_cls:
        mock_repo_cls.return_value.get_all.return_value = videos
        SimilarRankerCache.invalidate()
        second = SimilarRankerCache.get()
        out_after = second.rank(videos[0])

    assert len(out_after) > 0
    assert [v.number for v in out_after] == [v.number for v in out_before]
