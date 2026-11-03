"""Integration tests for POST /api/ai/tags/test (TASK-188c-T6)."""

from __future__ import annotations

import core.config as core_config
import pytest
from fastapi.testclient import TestClient

from core.ai_services.tagging_vocab import load_builtin
from core.cloud_translate import build_error
from core.config import load_config, save_config
from core.secret_fields import mask_secret
from tests.unit._custom_source_fake import finalize_root  # noqa: PLC2701
from web.app import app

STORED_KEY = "sk-ant-stored-key-aaaa"
NEW_KEY = "sk-ant-new-key-zzzz"


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setenv("OPENAVER_DATA_DIR", str(root))
    save_config(load_config())
    finalize_root(root)
    return root


def _seed_claude_tags(*, api_key: str = STORED_KEY, provider: str = "claude", model: str = "claude-haiku-4"):
    cfg = load_config()
    tags = cfg.setdefault("ai_services", {}).setdefault("tags", {})
    tags["provider"] = provider
    tags["model"] = model
    # enabled stays at default false — test must work with switch off
    cfg.setdefault("translate", {}).setdefault("claude", {})["api_key"] = api_key
    save_config(cfg)


@pytest.mark.parametrize(
    "case",
    ["masked", "plaintext"],
    ids=["masked_uses_stored", "plaintext_uses_new"],
)
def test_masked_api_key_resolves_to_stored_key(monkeypatch, case):
    """使用者沒改金鑰就按測試 → 用已存金鑰；送新明文 → 用新明文。"""
    _seed_claude_tags()
    calls: list = []

    async def fake(conn, system, user_text, poster_uri):
        calls.append({"conn": conn, "poster_uri": poster_uri})
        raise build_error("X", "auth_failed", 401, "", "")

    monkeypatch.setattr("core.ai_services.tagging.vision_chat", fake)

    if case == "masked":
        # 用已存 provider／model，只送遮罩金鑰（最貼近 UI）
        body = {"api_key": mask_secret(STORED_KEY)}
        expected_key = STORED_KEY
    else:
        body = {
            "provider": "claude",
            "model": "claude-haiku-4",
            "api_key": NEW_KEY,
        }
        expected_key = NEW_KEY

    with TestClient(app) as c:
        resp = c.post("/api/ai/tags/test", json=body)
    assert resp.status_code == 200
    assert len(calls) == 1
    assert calls[0]["conn"].api_key == expected_key
    assert STORED_KEY not in resp.text


@pytest.mark.parametrize(
    "case",
    [
        "unreachable",
        "model_unsupported",
        "bad_response",
        "refused",
        "no_tags",
        "ok",
        "not_configured",
    ],
)
def test_outcomes_name_what_the_user_should_fix(monkeypatch, case):
    """三種結果各對到正確 outcome——說錯原因，使用者去修錯地方。"""
    calls: list = []

    async def fake(conn, system, user_text, poster_uri):
        calls.append({"conn": conn, "poster_uri": poster_uri, "system": system})
        if case == "unreachable":
            # auth_failed → unreachable（連不上，去查金鑰／網路）
            raise build_error("X", "auth_failed", 401, "", "")
        if case == "model_unsupported":
            # 400 http_error → unusable/model_unsupported（換看得懂圖的模型）
            raise build_error("X", "http_error", 400, "", "")
        if case == "bad_response":
            # 含 { 但不是合法 JSON 物件 → unusable/bad_response
            return "{not-a-json-object"
        if case == "refused":
            # 不含 { 的非空文字 → unusable/refused
            return "I cannot help with that request."
        if case == "no_tags":
            # 空 tags 陣列 → unusable/no_tags（樣本圖 0 字）
            return '{"tags":[]}'
        if case == "ok":
            # 命中詞表 model_name → ok，tags 為顯示名
            item = load_builtin()[0]
            return (
                '{"tags":[{"tag":"'
                + item.model_name
                + '","confidence":"high"}]}'
            )
        raise AssertionError(f"vision_fn should not be called for case={case}")

    monkeypatch.setattr("core.ai_services.tagging.vision_chat", fake)

    if case == "not_configured":
        # 已存 provider 空 → not_configured（根本沒打模型）
        with TestClient(app) as c:
            resp = c.post("/api/ai/tags/test")
        assert resp.status_code == 200
        assert resp.json() == {
            "ok": False,
            "outcome": "not_configured",
            "detail": "provider",
        }
        assert len(calls) == 0
        return

    _seed_claude_tags()

    with TestClient(app) as c:
        sample = c.get("/api/ai/sample/tags").json()["inputs"][0]
        resp = c.post("/api/ai/tags/test", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert len(calls) == 1

    if case == "unreachable":
        assert body == {"ok": False, "outcome": "unreachable", "detail": "auth_failed"}
    elif case == "model_unsupported":
        assert body == {
            "ok": False,
            "outcome": "unusable",
            "detail": "model_unsupported",
        }
    elif case == "bad_response":
        assert body == {"ok": False, "outcome": "unusable", "detail": "bad_response"}
    elif case == "refused":
        assert body == {"ok": False, "outcome": "unusable", "detail": "refused"}
    elif case == "no_tags":
        assert body == {"ok": False, "outcome": "unusable", "detail": "no_tags"}
    elif case == "ok":
        item = load_builtin()[0]
        assert item.name != item.model_name  # 顯示名與 model_name 可區分
        assert body == {"ok": True, "outcome": "ok", "tags": [item.name]}
        assert calls[0]["poster_uri"] == sample


def test_test_button_has_no_side_effects(monkeypatch):
    """按測試不改設定、不標任何片；覆寫不漏進共用狀態。"""
    _seed_claude_tags()
    before = core_config.CONFIG_PATH.read_bytes()

    apply_calls = {"n": 0}
    tag_calls = {"n": 0}
    vision_calls: list = []

    def fake_apply(*a, **k):
        apply_calls["n"] += 1
        raise AssertionError("apply_user_tags must not be called")

    async def fake_tag(*a, **k):
        tag_calls["n"] += 1
        raise AssertionError("tag_video must not be called")

    async def fake_vision(conn, system, user_text, poster_uri):
        vision_calls.append(conn.api_key)
        raise build_error("X", "auth_failed", 401, "", "")

    monkeypatch.setattr("core.ai_services.tagging.apply_user_tags", fake_apply)
    monkeypatch.setattr("web.routers.ai_tags.tag_video", fake_tag)
    monkeypatch.setattr("core.ai_services.tagging.vision_chat", fake_vision)

    with TestClient(app) as c:
        # 帶覆寫（新明文）打一次
        resp1 = c.post(
            "/api/ai/tags/test",
            json={"api_key": NEW_KEY},
        )
        assert resp1.status_code == 200
        assert vision_calls == [NEW_KEY]

        # config 位元組不變；寫入路徑未被呼叫
        assert core_config.CONFIG_PATH.read_bytes() == before
        assert apply_calls["n"] == 0
        assert tag_calls["n"] == 0

        # 隨後不帶覆寫仍用已存金鑰
        resp2 = c.post("/api/ai/tags/test", json={})
        assert resp2.status_code == 200
        assert vision_calls == [NEW_KEY, STORED_KEY]
        assert core_config.CONFIG_PATH.read_bytes() == before
        assert apply_calls["n"] == 0
        assert tag_calls["n"] == 0
