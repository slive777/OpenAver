"""黑名單 API 整合測試（TASK-205b-T2）：列出／新增／刪除＋封面標章字保護。"""

import pytest
from fastapi.testclient import TestClient

from core.database import init_db


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "tag_blacklist.db"
    init_db(path)
    monkeypatch.setattr("core.database.connection.get_db_path", lambda: path)
    return path


@pytest.fixture
def client(db_path):
    from web.app import app

    return TestClient(app)


def test_add_list_delete_roundtrip(client, db_path):
    from core.tag_display import COMMON_BLACKLIST_SUGGESTIONS

    r = client.post("/api/tag-blacklist", json={"name": "AC/DC"})
    assert r.status_code == 200
    assert r.json()["success"] is True
    assert [i["name"] for i in r.json()["items"]] == ["AC/DC"]

    r = client.get("/api/tag-blacklist")
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert [i["name"] for i in data["items"]] == ["AC/DC"]
    assert data["suggestions"] == list(COMMON_BLACKLIST_SUGGESTIONS)
    assert data["hidden"] == sorted(data["hidden"])
    assert "ac/dc" in data["hidden"]

    r = client.post("/api/tag-blacklist", json={"name": "AC/DC"})
    assert r.status_code == 409
    assert r.json()["code"] == "duplicate"
    assert len(client.get("/api/tag-blacklist").json()["items"]) == 1

    r = client.delete("/api/tag-blacklist/AC/DC")
    assert r.status_code == 200
    assert r.json()["success"] is True

    r = client.delete("/api/tag-blacklist/AC/DC")
    assert r.status_code == 200
    assert client.get("/api/tag-blacklist").json()["items"] == []


@pytest.mark.parametrize("word", ["中字", " 字幕 ", "ai", "VR"])
def test_direct_protected_word_rejected(client, db_path, word):
    r = client.post("/api/tag-blacklist", json={"name": word})
    assert r.status_code == 400
    assert r.json()["code"] == "cover_badge"
    assert client.get("/api/tag-blacklist").json()["items"] == []


@pytest.mark.parametrize("order", ["blacklist_first", "alias_first"])
def test_blacklist_and_alias_group_never_hide_badge_words(client, db_path, order):
    from core.cover_attributes import protected_tag_words

    alias_body = {"primary_name": "中文字幕", "aliases": ["ハイビジョン"]}
    closure = set(protected_tag_words()) | {"中文字幕", "ハイビジョン"}

    if order == "blacklist_first":
        r = client.post("/api/tag-blacklist", json={"name": "ハイビジョン"})
        assert r.status_code == 200
        r = client.post("/api/tag-aliases", json=alias_body)
        assert r.status_code == 200
        data = client.get("/api/tag-blacklist").json()
        assert [i["name"] for i in data["items"]] == ["ハイビジョン"]
        assert set(data["hidden"]) & closure == set()
    else:
        r = client.post("/api/tag-aliases", json=alias_body)
        assert r.status_code == 200
        r = client.post("/api/tag-blacklist", json={"name": "ハイビジョン"})
        assert r.status_code == 400
        assert r.json()["code"] == "cover_badge"
        data = client.get("/api/tag-blacklist").json()
        assert data["items"] == []
        assert set(data["hidden"]) & closure == set()


@pytest.mark.parametrize("name,code,status", [
    ("", "empty", 400),
    ("a,b", "invalid", 400),
    ("x" * 41, "invalid", 400),
    ("y" * 40, None, 200),
])
def test_invalid_name_rejected(client, db_path, name, code, status):
    r = client.post("/api/tag-blacklist", json={"name": name})
    assert r.status_code == status
    if code is None:
        assert r.json()["success"] is True
    else:
        assert r.json()["code"] == code
        assert client.get("/api/tag-blacklist").json()["items"] == []
