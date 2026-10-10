"""TASK-165-T6: capabilities 揭露四個自訂來源工具＋三個既有工具 source 描述補 custom:<id> 句。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import core.access_auth as access_auth


@pytest.fixture(autouse=True)
def auth_db(tmp_path, monkeypatch):
    """GET /api/capabilities 冷啟動會呼叫 load_snapshot()，未 mock 前連上 output/openaver.db。"""
    db_path = tmp_path / "access.db"
    monkeypatch.setattr("core.access_auth.get_db_path", lambda: db_path)
    access_auth.ensure_schema()
    access_auth.reset_state_for_tests()
    yield db_path
    access_auth.reset_state_for_tests()


@pytest.fixture
def client():
    from web.app import app
    return TestClient(app)


def _tool(data: dict, name: str) -> dict:
    return next(t for t in data["tools"] if t["name"] == name)


def _collect_enums(node, out):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "enum" and isinstance(v, list):
                out.append(v)
            _collect_enums(v, out)
    elif isinstance(node, list):
        for v in node:
            _collect_enums(v, out)
    return out


@pytest.mark.parametrize(
    "name,method,path,side_effect,confirm",
    [
        ("custom_source_upload", "POST", "/api/custom-sources", True, True),
        ("custom_source_verify", "POST", "/api/custom-sources/{id}/verify", True, True),
        ("custom_sources_list", "GET", "/api/custom-sources", False, False),
        ("custom_source_remove", "DELETE", "/api/custom-sources/{id}", True, True),
    ],
)
def test_custom_source_tool_flags(client, name, method, path, side_effect, confirm):
    t = _tool(client.get("/api/capabilities").json(), name)
    assert t["method"] == method
    assert t["path"] == path
    assert t["side_effect"] is side_effect
    if confirm:
        assert t["confirmation_required"] is True
    else:
        assert t.get("confirmation_required") is not True
    assert t["example"].startswith("curl ")


def test_upload_description_has_four_things(client):
    t = _tool(client.get("/api/capabilities").json(), "custom_source_upload")
    d = t["description"]
    assert "https://github.com/slive777/OpenAver/blob/main/docs/custom-sources.md" in d
    assert "自己撰寫" in d
    assert "驗收通過即自動啟用" in d
    assert "重新整理" in d
    assert "AI 沒有啟用端點" in d
    for w in ("請求", "合法", "未驗證"):
        assert w in d
    assert "Content-Type: text/plain" in t["example"]
    assert "--data-binary" in t["example"]


def test_custom_sources_paths_exactly_four_and_no_enable_applicable(client):
    tools = client.get("/api/capabilities").json()["tools"]
    cs = sorted((t["method"], t["path"]) for t in tools if "custom-sources" in t["path"])
    assert cs == sorted([
        ("POST", "/api/custom-sources"),
        ("POST", "/api/custom-sources/{id}/verify"),
        ("GET", "/api/custom-sources"),
        ("DELETE", "/api/custom-sources/{id}"),
    ])
    assert all("/enabled" not in t["path"] and "/applicable" not in t["path"] for t in tools)
    assert all("enabled" not in t["name"] and "applicable" not in t["name"] for t in tools)


def test_no_custom_in_any_enum(client):
    tools = client.get("/api/capabilities").json()["tools"]
    enums = _collect_enums(tools, [])
    assert enums
    assert not [e for e in enums for v in e if isinstance(v, str) and v.startswith("custom:")]


@pytest.mark.parametrize("name", ["search", "enrich_single", "video_rescrape_with_source"])
def test_source_description_mentions_custom_id(client, name):
    desc = _tool(client.get("/api/capabilities").json(), name)["input_schema"]["properties"]["source"]["description"]
    assert "custom:<id>" in desc
    assert "驗收" in desc
    assert "已啟用" in desc
