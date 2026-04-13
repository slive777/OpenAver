"""
test_alias_api.py — 女優別名 API 整合測試

端點：
    GET    /api/actress-aliases                   列出所有別名組
    GET    /api/actress-aliases/{name}            查單一別名組（primary 或 alias 查）
    POST   /api/actress-aliases/search-online     線上搜尋建議別名
    POST   /api/actress-aliases                   新增別名組
    DELETE /api/actress-aliases/{name}            刪除別名組
    POST   /api/actress-aliases/{name}/alias      為 group 新增 alias
    DELETE /api/actress-aliases/{name}/alias/{a} 移除單一 alias

策略：TestClient + mock AliasRepository（monkeypatch）。不使用真實 DB。
"""

from collections import namedtuple
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers — 建立測試用 AliasRecord-like object
# ---------------------------------------------------------------------------

def _make_record(primary_name, aliases=None, source="manual",
                 created_at=None, updated_at=None):
    """建立符合 AliasRecord 介面的 MagicMock"""
    record = MagicMock()
    record.primary_name = primary_name
    record.aliases = aliases or []
    record.source = source
    record.applied_count = 0
    record.created_at = created_at or datetime(2026, 4, 13)
    record.updated_at = updated_at
    return record


ProfileResult = namedtuple("ProfileResult", ["data", "timed_out"])


# ---------------------------------------------------------------------------
# Fixture: client with mocked AliasRepository
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_repo():
    """回傳一個 MagicMock AliasRepository"""
    return MagicMock()


@pytest.fixture
def client(mock_repo, monkeypatch):
    """
    TestClient — monkeypatch AliasRepository constructor 回傳 mock_repo。
    """
    monkeypatch.setattr(
        "web.routers.actress_alias.AliasRepository",
        lambda *args, **kwargs: mock_repo,
    )
    monkeypatch.setattr(
        "web.routers.actress_alias.init_db",
        lambda *args, **kwargs: None,
    )
    from web.app import app
    return TestClient(app)


# ===========================================================================
# GET /api/actress-aliases — 列出所有別名組
# ===========================================================================

class TestListAliases:
    """GET /api/actress-aliases"""

    def test_empty_list(self, client, mock_repo):
        """空表 → {success: true, groups: [], total: 0}"""
        mock_repo.get_all.return_value = []
        resp = client.get("/api/actress-aliases")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["groups"] == []
        assert data["total"] == 0

    def test_returns_all_records(self, client, mock_repo):
        """兩筆資料 → total=2，每筆含 primary_name / aliases / source"""
        records = [
            _make_record("橋本ありな", ["新ありな"]),
            _make_record("三上悠亜", ["鬼頭桃菜"]),
        ]
        mock_repo.get_all.return_value = records
        resp = client.get("/api/actress-aliases")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["groups"]) == 2
        names = [g["primary_name"] for g in data["groups"]]
        assert "橋本ありな" in names
        assert "三上悠亜" in names


# ===========================================================================
# GET /api/actress-aliases/{name} — 查單一別名組
# ===========================================================================

class TestGetOneAlias:
    """GET /api/actress-aliases/{name}"""

    def test_primary_hit(self, client, mock_repo):
        """name = primary_name → 直接回傳"""
        record = _make_record("橋本ありな", ["新ありな"])
        mock_repo.get_by_primary.return_value = record
        resp = client.get("/api/actress-aliases/橋本ありな")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["group"]["primary_name"] == "橋本ありな"
        assert "新ありな" in data["group"]["aliases"]

    def test_alias_hit(self, client, mock_repo):
        """name = alias → get_by_primary miss → find_by_alias hit"""
        record = _make_record("橋本ありな", ["新ありな"])
        mock_repo.get_by_primary.return_value = None
        mock_repo.find_by_alias.return_value = record
        resp = client.get("/api/actress-aliases/新ありな")
        assert resp.status_code == 200
        data = resp.json()
        assert data["group"]["primary_name"] == "橋本ありな"

    def test_not_found(self, client, mock_repo):
        """primary 和 alias 都查無 → 404"""
        mock_repo.get_by_primary.return_value = None
        mock_repo.find_by_alias.return_value = None
        resp = client.get("/api/actress-aliases/不存在的名字")
        assert resp.status_code == 404
        assert resp.json()["error"] == "not_found"

    def test_created_at_serialized(self, client, mock_repo):
        """created_at datetime → isoformat string"""
        record = _make_record("橋本ありな", [], created_at=datetime(2026, 4, 13, 0, 0, 0))
        mock_repo.get_by_primary.return_value = record
        resp = client.get("/api/actress-aliases/橋本ありな")
        assert resp.status_code == 200
        group = resp.json()["group"]
        assert group["created_at"] == "2026-04-13T00:00:00"

    def test_updated_at_none(self, client, mock_repo):
        """updated_at=None → response 也是 null"""
        record = _make_record("橋本ありな", [], updated_at=None)
        mock_repo.get_by_primary.return_value = record
        resp = client.get("/api/actress-aliases/橋本ありな")
        assert resp.json()["group"]["updated_at"] is None


# ===========================================================================
# POST /api/actress-aliases/search-online — 線上搜尋建議別名
# NOTE: 靜態路徑，必須在 /{name} 之前定義
# ===========================================================================

class TestSearchOnline:
    """POST /api/actress-aliases/search-online"""

    def test_name_empty_returns_422(self, client, mock_repo):
        """name 空字串 → 422"""
        resp = client.post("/api/actress-aliases/search-online", json={"name": ""})
        assert resp.status_code == 422

    def test_timeout_returns_504(self, client, mock_repo, monkeypatch):
        """orchestrator timeout → 504"""
        monkeypatch.setattr(
            "web.routers.actress_alias.get_actress_profile",
            lambda *a, **kw: ProfileResult(data=None, timed_out=True),
        )
        resp = client.post("/api/actress-aliases/search-online", json={"name": "橋本ありな"})
        assert resp.status_code == 504
        assert resp.json()["error"] == "timeout"

    def test_not_found_returns_empty_suggestions(self, client, mock_repo, monkeypatch):
        """orchestrator data=None, timed_out=False → 200 + 空 suggested_aliases"""
        monkeypatch.setattr(
            "web.routers.actress_alias.get_actress_profile",
            lambda *a, **kw: ProfileResult(data=None, timed_out=False),
        )
        resp = client.post("/api/actress-aliases/search-online", json={"name": "不存在的人"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["suggested_aliases"] == []
        assert "message" in data

    def test_success_with_str_aliases(self, client, mock_repo, monkeypatch):
        """orchestrator 回傳 str list aliases → suggested_aliases 是 str list"""
        profile_data = {
            "name": "橋本ありな",
            "text": {
                "aliases": ["新ありな", "アリス"]
            }
        }
        monkeypatch.setattr(
            "web.routers.actress_alias.get_actress_profile",
            lambda *a, **kw: ProfileResult(data=profile_data, timed_out=False),
        )
        resp = client.post("/api/actress-aliases/search-online", json={"name": "橋本ありな"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "新ありな" in data["suggested_aliases"]
        assert "アリス" in data["suggested_aliases"]

    def test_success_with_dict_aliases_flattened(self, client, mock_repo, monkeypatch):
        """minnano 格式 dict list aliases → _flatten_aliases 轉為 str list"""
        profile_data = {
            "name": "橋本ありな",
            "text": {
                "aliases": [
                    {"ja": "新ありな", "hiragana": "ありな", "romaji": "Arina Hashimoto"},
                ]
            }
        }
        monkeypatch.setattr(
            "web.routers.actress_alias.get_actress_profile",
            lambda *a, **kw: ProfileResult(data=profile_data, timed_out=False),
        )
        resp = client.post("/api/actress-aliases/search-online", json={"name": "橋本ありな"})
        assert resp.status_code == 200
        data = resp.json()
        assert "新ありな" in data["suggested_aliases"]

    def test_success_with_empty_aliases(self, client, mock_repo, monkeypatch):
        """orchestrator 有 data 但 aliases 為空 → suggested_aliases=[]"""
        profile_data = {
            "name": "橋本ありな",
            "text": {}  # no aliases key
        }
        monkeypatch.setattr(
            "web.routers.actress_alias.get_actress_profile",
            lambda *a, **kw: ProfileResult(data=profile_data, timed_out=False),
        )
        resp = client.post("/api/actress-aliases/search-online", json={"name": "橋本ありな"})
        assert resp.status_code == 200
        assert resp.json()["suggested_aliases"] == []


# ===========================================================================
# POST /api/actress-aliases — 新增別名組
# ===========================================================================

class TestCreateAliasGroup:
    """POST /api/actress-aliases"""

    def test_success_with_aliases(self, client, mock_repo):
        """成功建立 group → 200 + {success: true, group: {...}}"""
        record = _make_record("橋本ありな", ["新ありな"])
        mock_repo.add.return_value = record
        resp = client.post("/api/actress-aliases", json={
            "primary_name": "橋本ありな",
            "aliases": ["新ありな"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["group"]["primary_name"] == "橋本ありな"

    def test_success_without_aliases(self, client, mock_repo):
        """aliases 省略 → 等同空 list，建立只有 primary 的空 group"""
        record = _make_record("橋本ありな", [])
        mock_repo.add.return_value = record
        resp = client.post("/api/actress-aliases", json={"primary_name": "橋本ありな"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_empty_primary_name_returns_422(self, client, mock_repo):
        """primary_name 空字串 → 422"""
        resp = client.post("/api/actress-aliases", json={"primary_name": ""})
        assert resp.status_code == 422

    def test_primary_conflict_returns_400(self, client, mock_repo):
        """primary_name 已存在為其他 group 的 primary → repo.add raises ValueError → 400"""
        mock_repo.add.side_effect = ValueError("primary_name '橋本ありな' 已被使用")
        resp = client.post("/api/actress-aliases", json={"primary_name": "橋本ありな"})
        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False
        assert "error" in data

    def test_alias_conflict_returns_400(self, client, mock_repo):
        """aliases 中某名字已是其他 group 的 alias → ValueError → 400"""
        mock_repo.add.side_effect = ValueError("alias '新ありな' 已被使用")
        resp = client.post("/api/actress-aliases", json={
            "primary_name": "橋本ありな",
            "aliases": ["新ありな"],
        })
        assert resp.status_code == 400
        assert resp.json()["success"] is False


# ===========================================================================
# DELETE /api/actress-aliases/{name} — 刪除別名組
# ===========================================================================

class TestDeleteAliasGroup:
    """DELETE /api/actress-aliases/{name}"""

    def test_delete_by_primary(self, client, mock_repo):
        """name = primary → repo.delete 回 True → 200"""
        mock_repo.delete.return_value = True
        resp = client.delete("/api/actress-aliases/橋本ありな")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_delete_by_alias(self, client, mock_repo):
        """name = alias → repo.delete 內部 resolve → True → 200"""
        mock_repo.delete.return_value = True
        resp = client.delete("/api/actress-aliases/新ありな")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_delete_not_found(self, client, mock_repo):
        """不存在 → repo.delete 回 False → 404"""
        mock_repo.delete.return_value = False
        resp = client.delete("/api/actress-aliases/不存在")
        assert resp.status_code == 404
        assert "error" in resp.json()


# ===========================================================================
# POST /api/actress-aliases/{name}/alias — 為 group 新增 alias
# ===========================================================================

class TestAddAlias:
    """POST /api/actress-aliases/{name}/alias"""

    def test_success(self, client, mock_repo):
        """成功新增 → 200 + {success: true, group: {...}}"""
        record = _make_record("橋本ありな", ["新ありな"])
        mock_repo.get_by_primary.return_value = record
        mock_repo.add_alias.return_value = (True, None)
        # re-read record after add
        mock_repo.get_by_primary.side_effect = [
            record,   # 第一次：確認 group 存在
            _make_record("橋本ありな", ["新ありな", "アリス"]),  # 第二次：re-read
        ]
        resp = client.post("/api/actress-aliases/橋本ありな/alias", json={"alias": "アリス"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "group" in data

    def test_alias_empty_returns_422(self, client, mock_repo):
        """alias 空字串 → 422"""
        resp = client.post("/api/actress-aliases/橋本ありな/alias", json={"alias": ""})
        assert resp.status_code == 422

    def test_group_not_found_returns_404(self, client, mock_repo):
        """{name} group 不存在 → 404（先查 primary 再 add_alias）"""
        mock_repo.get_by_primary.return_value = None
        resp = client.post("/api/actress-aliases/不存在的人/alias", json={"alias": "アリス"})
        assert resp.status_code == 404

    def test_alias_conflict_returns_400(self, client, mock_repo):
        """alias 已屬其他 group → add_alias 回 (False, msg) → 400"""
        record = _make_record("橋本ありな", [])
        mock_repo.get_by_primary.return_value = record
        mock_repo.add_alias.return_value = (False, "alias 'アリス' 已屬於其他 group")
        resp = client.post("/api/actress-aliases/橋本ありな/alias", json={"alias": "アリス"})
        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False
        assert "error" in data


# ===========================================================================
# DELETE /api/actress-aliases/{name}/alias/{alias} — 移除單一 alias
# ===========================================================================

class TestRemoveAlias:
    """DELETE /api/actress-aliases/{name}/alias/{alias}"""

    def test_success(self, client, mock_repo):
        """成功移除 → 200 + {success: true}"""
        record = _make_record("橋本ありな", ["新ありな"])
        mock_repo.get_by_primary.return_value = record
        mock_repo.remove_alias.return_value = True
        resp = client.delete("/api/actress-aliases/橋本ありな/alias/新ありな")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_group_not_found_returns_404(self, client, mock_repo):
        """{name} primary 不存在 → 404"""
        mock_repo.get_by_primary.return_value = None
        resp = client.delete("/api/actress-aliases/不存在/alias/新ありな")
        assert resp.status_code == 404

    def test_alias_not_found_returns_404(self, client, mock_repo):
        """alias 不在 group → remove_alias 回 False → 404 error=alias_not_found"""
        record = _make_record("橋本ありな", [])
        mock_repo.get_by_primary.return_value = record
        mock_repo.remove_alias.return_value = False
        resp = client.delete("/api/actress-aliases/橋本ありな/alias/不存在的alias")
        assert resp.status_code == 404
        assert resp.json()["error"] == "alias_not_found"
