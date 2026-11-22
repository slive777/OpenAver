"""
tests/integration/test_ranker_cache_invalidation.py
Integration tests for SimilarRankerCache.invalidate() choke-point hooks（57b-T4）

Verifies that each DB write mutation triggers cache invalidation so the next
SimilarRankerCache.get() returns a freshly-built instance (identity check).
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from core.database import init_db, Video, VideoRepository
from core.path_utils import to_file_uri
from core.similar.ranker_cache import SimilarRankerCache


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_video(idx: int, number: str | None = None) -> Video:
    """Build a minimal Video for upsert; path must be unique."""
    return Video(
        path=to_file_uri(f"/fake/cache_test_{idx:04d}.mp4"),
        number=number or f"CACHE-{idx:04d}",
        title=f"Cache Test Video {idx:04d}",
        maker="MakerX",
        series=None,
        actresses=[],
        tags=["高畫質", "單體作品", f"tag{idx}"],
        release_date="2024-01-01",
        duration=90,
        cover_path="",
        mtime=float(idx),
    )


def _make_corrupted_video(idx: int) -> Video:
    """Build a Video with corrupted number (digit_prefix rule) for fix_numbers_apply tests."""
    return Video(
        path=to_file_uri(f"/fake/fix_num_{idx:04d}.mp4"),
        number=f"7IPZ-{idx:03d}",
        title=f"Fix Num Video {idx:04d}",
        maker="MakerY",
        series=None,
        actresses=[],
        tags=["高畫質"],
        release_date="2024-01-01",
        duration=60,
        cover_path="",
        mtime=float(idx),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_cache():
    """Ensure cache is clean before and after each test.

    SimilarRanker.__init__ internally calls canonicalize(), whose
    _load_merged_map() lazy-loads core.database.TagAliasRepository and, on a
    cold module-level cache, connects to the real output/openaver.db (見
    tests/unit/test_similar_canonicalize.py 的 isolate_canonicalize_cache 同一
    手法；tests/unit/test_ranker_cache.py 的 reset_cache 已套用過同一修法）。
    """
    from core.similar.canonicalize import _invalidate_cache

    SimilarRankerCache._instance = None
    _invalidate_cache()
    mock_alias_repo = MagicMock()
    mock_alias_repo.get_all.return_value = []
    with patch("core.database.TagAliasRepository", return_value=mock_alias_repo), \
         patch("core.database.TagBlacklistRepository", return_value=MagicMock(**{"get_all.return_value": []})):
        yield
    SimilarRankerCache._instance = None
    _invalidate_cache()


@pytest.fixture
def repo_and_cache(tmp_path, monkeypatch):
    """建立測試 DB + 初始化 warm cache。"""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    repo = VideoRepository(db_path)

    # Seed at least one video so the ranker corpus is non-trivial
    seed = _make_video(0)
    repo.upsert(seed)

    # Patch SimilarRankerCache to build corpus from our test DB
    monkeypatch.setattr(
        "core.similar.ranker_cache.VideoRepository",
        lambda: VideoRepository(db_path),
    )

    # Warm the cache (reset_cache fixture already set _instance = None)
    first = SimilarRankerCache.get()
    assert first is not None

    yield repo, first, db_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestInvalidateAfterUpsert:
    """T4-1: upsert() invalidates cache."""

    def test_invalidate_after_upsert(self, repo_and_cache):
        repo, first, db_path = repo_and_cache

        new_video = _make_video(1)
        repo.upsert(new_video)

        second = SimilarRankerCache.get()
        assert second is not first, "upsert() must invalidate cache so get() rebuilds"


