"""
test_favorite_sync.py — T3: Favorite 同步

測試 POST /api/actresses/favorite 成功後自動呼叫
AliasRepository.sync_from_favorite()。

策略：TestClient + monkeypatch mock 所有外部依賴。
"""
from collections import namedtuple
from datetime import datetime
from unittest.mock import MagicMock, call

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# 共用 stub helpers
# ---------------------------------------------------------------------------

ProfileResult = namedtuple("ProfileResult", ["data", "timed_out"])


def _make_profile(name="橋本ありな", aliases=None):
    """建立假 scraper profile"""
    return {
        "name": name,
        "name_en": "Arina Hashimoto",
        "photo_url": None,
        "photo_source": None,
        "primary_text_source": "minnano",
        "text": {
            "birth": "1998-08-19",
            "aliases": aliases or [],
        },
    }


def _make_actress_mock(name="橋本ありな", aliases=None):
    """建立假 Actress-like MagicMock（DB re-read 後的值）"""
    actress = MagicMock()
    actress.name = name
    actress.name_en = "Arina Hashimoto"
    actress.birth = "1998-08-19"
    actress.height = None
    actress.cup = None
    actress.bust = None
    actress.waist = None
    actress.hip = None
    actress.hometown = None
    actress.hobby = None
    actress.aliases = aliases if aliases is not None else []
    actress.agency = None
    actress.debut_work = None
    actress.tags = []
    actress.nickname = None
    actress.blog_url = None
    actress.official_url = None
    actress.photo_source = None
    actress.primary_text_source = "minnano"
    actress.created_at = datetime(2026, 4, 13)
    return actress


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_alias_repo():
    """Mock AliasRepository instance"""
    repo = MagicMock()
    repo.sync_from_favorite.return_value = {"primary_name": "橋本ありな", "skipped_aliases": []}
    return repo


@pytest.fixture
def mock_actress_repo():
    """Mock ActressRepository instance"""
    repo = MagicMock()
    repo.exists.return_value = False
    actress = _make_actress_mock()
    repo.get_by_name.return_value = actress
    repo.count_videos_for_actress.return_value = 0
    repo.count_videos_for_actress_names.return_value = 0
    return repo


@pytest.fixture
def client(mock_alias_repo, mock_actress_repo, monkeypatch):
    """
    TestClient — monkeypatch 所有 actress router 外部依賴：
    - init_db (no-op)
    - ActressRepository → mock_actress_repo
    - AliasRepository → mock_alias_repo
    - get_cached_profile → None（觸發 scraper）
    - get_actress_profile → dummy profile
    - download_actress_photo → False
    - get_local_photo_path → None
    """
    monkeypatch.setattr("web.routers.actress.init_db", lambda *a, **kw: None)
    monkeypatch.setattr(
        "web.routers.actress.ActressRepository",
        lambda *a, **kw: mock_actress_repo,
    )
    monkeypatch.setattr(
        "web.routers.actress.AliasRepository",
        lambda *a, **kw: mock_alias_repo,
    )
    monkeypatch.setattr(
        "web.routers.actress.get_cached_profile",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        "web.routers.actress.get_actress_profile",
        lambda *a, **kw: ProfileResult(data=_make_profile(), timed_out=False),
    )
    monkeypatch.setattr(
        "web.routers.actress.download_actress_photo",
        lambda *a, **kw: False,
    )
    monkeypatch.setattr(
        "web.routers.actress.get_local_photo_path",
        lambda *a, **kw: None,
    )
    # suppress load_prefix_mapping side effects
    monkeypatch.setattr(
        "web.routers.actress.load_prefix_mapping",
        lambda *a, **kw: {},
    )
    from web.app import app
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. Happy path — sync called with correct args, response has skipped_aliases
# ---------------------------------------------------------------------------

class TestFavoriteSyncHappyPath:
    """正常收藏後 sync 被呼叫，response 含 skipped_aliases"""

    def test_sync_called_with_name_and_aliases(self, client, mock_alias_repo, mock_actress_repo):
        """favorite 成功 → sync_from_favorite(name, aliases) 被呼叫一次"""
        # actress.aliases 包含兩個 alias
        actress = _make_actress_mock(aliases=["新ありな", "アリス"])
        mock_actress_repo.get_by_name.return_value = actress

        resp = client.post("/api/actresses/favorite", json={"name": "橋本ありな"})
        assert resp.status_code == 200

        mock_alias_repo.sync_from_favorite.assert_called_once_with(
            "橋本ありな", ["新ありな", "アリス"]
        )

    def test_response_contains_skipped_aliases_empty(self, client, mock_alias_repo):
        """sync 無跳過 → response 含 skipped_aliases: []"""
        mock_alias_repo.sync_from_favorite.return_value = {
            "primary_name": "橋本ありな",
            "skipped_aliases": [],
        }
        resp = client.post("/api/actresses/favorite", json={"name": "橋本ありな"})
        assert resp.status_code == 200
        data = resp.json()
        assert "skipped_aliases" in data
        assert data["skipped_aliases"] == []

    def test_response_success_true(self, client):
        """favorite 成功 → response success: true"""
        resp = client.post("/api/actresses/favorite", json={"name": "橋本ありな"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True


# ---------------------------------------------------------------------------
# 2. Empty aliases — sync still called with []
# ---------------------------------------------------------------------------

class TestFavoriteSyncEmptyAliases:
    """aliases 為空時，sync 仍被呼叫（empty list）"""

    def test_sync_called_with_empty_list(self, client, mock_alias_repo, mock_actress_repo):
        """actress.aliases == [] → sync_from_favorite(name, []) 被呼叫"""
        actress = _make_actress_mock(aliases=[])
        mock_actress_repo.get_by_name.return_value = actress

        resp = client.post("/api/actresses/favorite", json={"name": "橋本ありな"})
        assert resp.status_code == 200

        mock_alias_repo.sync_from_favorite.assert_called_once_with("橋本ありな", [])

    def test_sync_called_when_aliases_is_none(self, client, mock_alias_repo, mock_actress_repo):
        """actress.aliases is None → sync_from_favorite(name, []) — guarded by 'or []'"""
        actress = _make_actress_mock(aliases=None)
        mock_actress_repo.get_by_name.return_value = actress

        resp = client.post("/api/actresses/favorite", json={"name": "橋本ありな"})
        assert resp.status_code == 200

        # aliases=None → the handler does `actress.aliases or []` → []
        mock_alias_repo.sync_from_favorite.assert_called_once_with("橋本ありな", [])


# ---------------------------------------------------------------------------
# 3. Sync returns skipped_aliases → response includes them
# ---------------------------------------------------------------------------

class TestFavoriteSyncSkippedAliases:
    """sync 回傳有衝突的 alias → response skipped_aliases 列出"""

    def test_skipped_aliases_passed_to_response(self, client, mock_alias_repo):
        """sync 回傳 skipped=['アリス'] → response skipped_aliases=['アリス']"""
        mock_alias_repo.sync_from_favorite.return_value = {
            "primary_name": "橋本ありな",
            "skipped_aliases": ["アリス"],
        }
        resp = client.post("/api/actresses/favorite", json={"name": "橋本ありな"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["skipped_aliases"] == ["アリス"]

    def test_http_200_even_with_skipped(self, client, mock_alias_repo):
        """skipped_aliases 不空 → HTTP 仍 200（非錯誤）"""
        mock_alias_repo.sync_from_favorite.return_value = {
            "primary_name": "橋本ありな",
            "skipped_aliases": ["アリス", "新ありな"],
        }
        resp = client.post("/api/actresses/favorite", json={"name": "橋本ありな"})
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 4. Sync raises exception → favorite still succeeds (200), logged warning
# ---------------------------------------------------------------------------

class TestFavoriteSyncException:
    """sync 拋例外 → favorite 仍回 200，skipped_aliases=[]"""

    def test_sync_exception_does_not_block_favorite(self, client, mock_alias_repo):
        """sync_from_favorite 拋 RuntimeError → response 200, success True"""
        mock_alias_repo.sync_from_favorite.side_effect = RuntimeError("DB locked")
        resp = client.post("/api/actresses/favorite", json={"name": "橋本ありな"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_sync_exception_skipped_aliases_is_empty(self, client, mock_alias_repo):
        """sync 拋例外 → response skipped_aliases=[] (fallback)"""
        mock_alias_repo.sync_from_favorite.side_effect = Exception("DB error")
        resp = client.post("/api/actresses/favorite", json={"name": "橋本ありな"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["skipped_aliases"] == []


