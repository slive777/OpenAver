"""
TASK-58a-A5: canonicalize DB merge + cache invalidate unit tests (TDD-lite)

Tests:
  1. DB alias 生效（happy path）
  2. DB read 失敗 → fallback hardcoded-only，不 raise
  3. 空 DB → 與 hardcoded-only 等價
  4. cache invalidate 計次（區分 cache hit vs miss）
  5. DB 覆蓋 hardcoded（DB 優先）
"""

import pytest
from unittest.mock import patch, MagicMock
from core.similar.canonicalize import canonicalize, _invalidate_cache
from core.database import TagAliasRecord


@pytest.fixture(autouse=True)
def isolate_cache():
    """每 test 前後清 cache，避免 cross-test 污染"""
    _invalidate_cache()
    yield
    _invalidate_cache()


# ---------------------------------------------------------------------------
# Case 1: DB alias 生效（happy path）
# ---------------------------------------------------------------------------

def test_db_alias_applied(caplog):
    """DB 回傳 alias record → canonicalize 應套用 DB 定義"""
    mock_record = TagAliasRecord(primary_name="メイド", aliases=["女僕"])
    mock_repo = MagicMock()
    mock_repo.get_all.return_value = [mock_record]

    with patch("core.database.TagAliasRepository", return_value=mock_repo), \
         patch("core.database.TagBlacklistRepository", return_value=MagicMock(**{"get_all.return_value": []})):
        result = canonicalize(["女僕"])

    assert result == ["メイド"]


# ---------------------------------------------------------------------------
# Case 2: DB read 失敗 → fallback hardcoded-only，不 raise
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Case 3: 空 DB → 與 hardcoded-only 等價（regression protection）
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Case 4: cache invalidate 計次（區分 cache hit vs miss）
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Case 5: DB 覆蓋 hardcoded（DB 優先）
# ---------------------------------------------------------------------------

