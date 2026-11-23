"""
OpenAI Compatible API router integration tests.

Covers /api/openai/models and /api/openai/test endpoints.
Uses TestClient + mock httpx.AsyncClient (no real HTTP connections).
"""
import asyncio
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, MagicMock
import httpx

import core.config as core_config
from core import secret_store
from core.config import load_config, save_config
from core.secret_fields import mask_secret
from core.translate_service import create_translate_service
from web.app import app

pytestmark = pytest.mark.usefixtures("isolate_secret_store")

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_client(get_response=None, post_response=None, raise_on_get=None, raise_on_post=None):
    """Build a mock httpx.AsyncClient context-manager with configurable responses."""
    mock_client = AsyncMock()

    if raise_on_get is not None:
        mock_client.get = AsyncMock(side_effect=raise_on_get)
    elif get_response is not None:
        mock_client.get = AsyncMock(return_value=get_response)

    if raise_on_post is not None:
        mock_client.post = AsyncMock(side_effect=raise_on_post)
    elif post_response is not None:
        mock_client.post = AsyncMock(return_value=post_response)

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=mock_client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _make_http_response(status_code: int, json_body: dict | None = None):
    """Build a minimal mock httpx.Response."""
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = status_code
    if json_body is not None:
        mock_resp.json = MagicMock(return_value=json_body)
    # Simulate raise_for_status for 4xx/5xx
    if status_code >= 400:
        request = MagicMock()
        mock_resp.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError(
                message=f"HTTP {status_code}",
                request=request,
                response=mock_resp,
            )
        )
    else:
        mock_resp.raise_for_status = MagicMock(return_value=None)
    return mock_resp


# ===========================================================================
# /api/openai/models
# ===========================================================================

class TestOpenAIModels:

    def test_models_success(self):
        """GET /models returns sorted model id list."""
        resp = _make_http_response(200, {"data": [{"id": "model-b"}, {"id": "model-a"}]})
        mock_cm = _make_mock_client(get_response=resp)

        with patch("web.routers.openai_translate.httpx.AsyncClient", return_value=mock_cm):
            response = client.post("/api/openai/models", json={
                "base_url": "http://localhost:8080",
                "api_key": "test-key"
            })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["models"] == ["model-a", "model-b"]


    def test_models_auth_failed(self):
        """HTTP 401 → success=False, error='auth_failed'."""
        resp = _make_http_response(401)
        mock_cm = _make_mock_client(get_response=resp)

        with patch("web.routers.openai_translate.httpx.AsyncClient", return_value=mock_cm):
            response = client.post("/api/openai/models", json={
                "base_url": "http://localhost:8080",
                "api_key": "bad-key"
            })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "auth_failed"


    def test_models_connection_error(self):
        """Generic exception (DNS failure etc.) → success=False, error is fixed string."""
        mock_cm = _make_mock_client(raise_on_get=Exception("DNS resolution failed"))

        with patch("web.routers.openai_translate.httpx.AsyncClient", return_value=mock_cm):
            response = client.post("/api/openai/models", json={
                "base_url": "http://nonexistent.invalid",
                "api_key": ""
            })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        # Negative assertion: must NOT contain raw exception text
        assert "DNS resolution failed" not in data["error"]
        assert data["error"]  # non-empty


# ===========================================================================
# /api/openai/test
# ===========================================================================

class TestOpenAITranslate:

    def test_translate_success(self):
        """Valid chat completions response → success=True, non-empty translation."""
        api_resp = {
            "choices": [
                {"message": {"content": "新人女演員出道"}}
            ]
        }
        resp = _make_http_response(200, api_resp)
        mock_cm = _make_mock_client(post_response=resp)

        with patch("web.routers.openai_translate.httpx.AsyncClient", return_value=mock_cm), \
             patch("web.routers.openai_translate.load_config", return_value={"general": {"locale": "zh-TW"}}):
            response = client.post("/api/openai/test", json={
                "base_url": "http://localhost:8080",
                "api_key": "",
                "model": "my-model"
            })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["translation"]  # non-empty

    def test_translate_http_error(self):
        """HTTP 401 → success=False, error='auth_failed'."""
        resp = _make_http_response(401)
        mock_cm = _make_mock_client(post_response=resp)

        with patch("web.routers.openai_translate.httpx.AsyncClient", return_value=mock_cm), \
             patch("web.routers.openai_translate.load_config", return_value={"general": {"locale": "zh-TW"}}):
            response = client.post("/api/openai/test", json={
                "base_url": "http://localhost:8080",
                "api_key": "bad",
                "model": "my-model"
            })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "auth_failed"


GID_A = "oc0123abcd"
GID_B = "oc00ff00ff"
GID_NEW = "oc0a0b0c0d"
KEY_DEFAULT = "fake-key-default-0001abcd"
KEY_CUSTOM = "fake-key-custom-0002abcd"
KEY_TEMP = "fake-key-temp-0003abcd"


class _RecordHandler(BaseHTTPRequestHandler):
    def _reply(self, body):
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.server.received.append(
            ("GET", self.path, self.headers.get("Authorization"))
        )
        self._reply({"data": [{"id": "m"}]})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        self.server.received.append(
            ("POST", self.path, self.headers.get("Authorization"))
        )
        self._reply(
            {"choices": [{"message": {"content": '{"tags":[]}'}, "finish_reason": "stop"}]}
        )

    def log_message(self, *args):
        pass


@pytest.fixture()
def stub_server(monkeypatch):
    for var in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RecordHandler)
    server.received = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def _seed_two_groups(default_url, custom_url,
                      default_key=KEY_DEFAULT, custom_key=KEY_CUSTOM):
    cfg = load_config()
    cfg["translate"]["provider"] = "openai"
    cfg["translate"]["openai"] = {
        "base_url": default_url,
        "api_key": default_key,
        "model": "m-default",
        "use_custom_model": False,
    }
    cfg["translate"]["openai_custom"] = {
        GID_A: {
            "name": "custom-a",
            "base_url": custom_url,
            "model": "m-custom",
            "use_custom_model": False,
            "api_key": custom_key,
        }
    }
    save_config(cfg)


def _snapshot_state():
    return (
        hashlib.sha256(core_config.CONFIG_PATH.read_bytes()).hexdigest(),
        dict(secret_store.snapshot()),
        load_config(),
    )


def _hits(server):
    return [r for r in server.received if r[1] == "/v1/chat/completions"]


@pytest.mark.parametrize(
    "case",
    ["translate_default_tags_custom", "translate_custom_tags_default"],
    ids=["translate_default_tags_custom", "translate_custom_tags_default"],
    )
def test_two_groups_hit_their_own_servers(case, stub_server):
    srv_b = stub_server
    srv_a_server = ThreadingHTTPServer(("127.0.0.1", 0), _RecordHandler)
    srv_a_server.received = []
    thread = threading.Thread(target=srv_a_server.serve_forever, daemon=True)
    thread.start()
    try:
        url_a = f"http://127.0.0.1:{srv_a_server.server_port}/v1"
        url_b = f"http://127.0.0.1:{srv_b.server_port}/v1"
        _seed_two_groups(url_a, url_b)
        srv_a_server.received.clear()
        srv_b.received.clear()

        if case == "translate_default_tags_custom":
            svc = create_translate_service(load_config()["translate"], "zh-TW")
            out = asyncio.run(svc.translate_or_raise("title"))
            assert out == '{"tags":[]}'
            with TestClient(app) as c:
                resp = c.post(
                    "/api/ai/tags/test",
                    json={"provider": f"openai:{GID_A}", "model": "m-tags"},
                )
            assert resp.status_code == 200
        else:
            cfg = load_config()
            cfg["translate"]["provider"] = f"openai:{GID_A}"
            save_config(cfg)
            svc = create_translate_service(load_config()["translate"], "zh-TW")
            out = asyncio.run(svc.translate_or_raise("title"))
            assert out == '{"tags":[]}'
            with TestClient(app) as c:
                resp = c.post(
                    "/api/ai/tags/test",
                    json={"provider": "openai", "model": "m-tags"},
                )
            assert resp.status_code == 200

        default_hits = _hits(srv_a_server)
        custom_hits = _hits(srv_b)
        exp_default = [f"Bearer {KEY_DEFAULT}"]
        exp_custom = [f"Bearer {KEY_CUSTOM}"]
        assert len(default_hits) == 1
        assert len(custom_hits) == 1
        if case == "translate_default_tags_custom":
            assert [r[2] for r in default_hits] == exp_default
            assert [r[2] for r in custom_hits] == exp_custom
        else:
            assert [r[2] for r in custom_hits] == exp_custom
            assert [r[2] for r in default_hits] == exp_default
        for _, _, auth in srv_a_server.received:
            assert auth != f"Bearer {KEY_CUSTOM}"
        for _, _, auth in srv_b.received:
            assert auth != f"Bearer {KEY_DEFAULT}"
    finally:
        srv_a_server.shutdown()
        thread.join()
        srv_a_server.server_close()


@pytest.mark.parametrize(
    "case",
    ["models", "test", "tags_test"],
    ids=["models", "test", "tags_test"],
    )
def test_group_endpoints_use_that_groups_stored_key(case, stub_server):
    url = f"http://127.0.0.1:{stub_server.server_port}/v1"
    _seed_two_groups("http://127.0.0.1:9/v1", url)
    stub_server.received.clear()
    masked = mask_secret(KEY_CUSTOM)
    assert masked != KEY_CUSTOM
    assert masked != ""

    if case == "models":
        with TestClient(app) as c:
            resp = c.post(
                "/api/openai/models",
                json={"base_url": url, "api_key": masked, "group_id": GID_A},
            )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
    elif case == "test":
        with TestClient(app) as c:
            resp = c.post(
                "/api/openai/test",
                json={
                    "base_url": url,
                    "api_key": masked,
                    "model": "m-custom",
                    "group_id": GID_A,
                },
            )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
    else:
        with TestClient(app) as c:
            resp = c.post(
                "/api/ai/tags/test",
                json={
                    "provider": f"openai:{GID_A}",
                    "model": "m-tags",
                    "api_key": masked,
                    "base_url": url,
                },
            )
        assert resp.status_code == 200

    posts = [r for r in stub_server.received if r[0] == "POST"]
    gets = [r for r in stub_server.received if r[0] == "GET"]
    touched = posts if case != "models" else gets
    assert len(touched) == 1
    assert touched[0][2] == f"Bearer {KEY_CUSTOM}"
    for _, _, auth in stub_server.received:
        assert auth != f"Bearer {KEY_DEFAULT}"


@pytest.mark.parametrize(
    "case",
    [
        "unsaved_models_no_auth",
        "saved_default_cleared",
        "saved_custom_cleared",
        "tags_custom_cleared",
        "empty_base_url_models",
        "empty_base_url_test",
        "tags_unsaved_no_base_url",
    ],
    ids=[
        "unsaved_models_no_auth",
        "saved_default_cleared",
        "saved_custom_cleared",
        "tags_custom_cleared",
        "empty_base_url_models",
        "empty_base_url_test",
        "tags_unsaved_no_base_url",
    ],
    )
def test_unsaved_or_cleared_group_never_borrows_a_key(case, stub_server):
    url_default = f"http://127.0.0.1:{stub_server.server_port}/v1"
    _seed_two_groups(url_default, f"http://127.0.0.1:9/v1")
    stub_server.received.clear()

    if case == "unsaved_models_no_auth":
        with TestClient(app) as c:
            resp = c.post(
                "/api/openai/models",
                json={
                    "base_url": url_default,
                    "api_key": "",
                    "group_id": GID_NEW,
                },
            )
        assert resp.json()["success"] is True
        gets = [r for r in stub_server.received if r[0] == "GET"]
        assert len(gets) == 1
        assert gets[0][2] is None
        assert len(stub_server.received) == 1
    elif case == "saved_default_cleared":
        with TestClient(app) as c:
            resp = c.post(
                "/api/openai/models",
                json={"base_url": url_default, "api_key": ""},
            )
        assert resp.json()["success"] is True
        gets = [r for r in stub_server.received if r[0] == "GET"]
        assert len(gets) == 1
        assert gets[0][2] is None
    elif case == "saved_custom_cleared":
        url_custom = f"http://127.0.0.1:{stub_server.server_port}/v1"
        _seed_two_groups(f"http://127.0.0.1:9/v1", url_custom)
        stub_server.received.clear()
        with TestClient(app) as c:
            resp = c.post(
                "/api/openai/models",
                json={"base_url": url_custom, "api_key": "", "group_id": GID_A},
            )
        assert resp.json()["success"] is True
        gets = [r for r in stub_server.received if r[0] == "GET"]
        assert len(gets) == 1
        assert gets[0][2] is None
    elif case == "tags_custom_cleared":
        with TestClient(app) as c:
            resp = c.post(
                "/api/ai/tags/test",
                json={
                    "provider": f"openai:{GID_A}",
                    "model": "m-tags",
                    "api_key": "",
                    "base_url": url_default,
                },
            )
        assert resp.status_code == 200
        posts = [r for r in stub_server.received if r[0] == "POST"]
        assert len(posts) == 1
        assert posts[0][2] is None
    elif case == "empty_base_url_models":
        with TestClient(app) as c:
            resp = c.post(
                "/api/openai/models",
                json={"base_url": "", "api_key": "", "group_id": GID_NEW},
            )
        assert resp.json() == {"success": False, "models": [], "error": "missing_base_url"}
        assert stub_server.received == []
    elif case == "empty_base_url_test":
        with TestClient(app) as c:
            resp = c.post(
                "/api/openai/test",
                json={
                    "base_url": "",
                    "api_key": "",
                    "model": "m",
                    "group_id": GID_NEW,
                },
            )
        assert resp.json()["success"] is False
        assert resp.json()["error"] == "missing_base_url"
        assert stub_server.received == []
    elif case == "tags_unsaved_no_base_url":
        with TestClient(app) as c:
            resp = c.post(
                "/api/ai/tags/test",
                json={"provider": f"openai:{GID_NEW}", "model": "m-tags"},
            )
        assert resp.status_code == 200
        assert resp.json()["outcome"] == "not_configured"
        assert stub_server.received == []


@pytest.mark.parametrize(
    "case",
    ["models_only_url", "test_url_model_temp_key", "tags_unsaved_full_body"],
    ids=["models_only_url", "test_url_model_temp_key", "tags_unsaved_full_body"],
    )
def test_keyless_group_can_be_tested_without_saving(case, stub_server):
    url = f"http://127.0.0.1:{stub_server.server_port}/v1"
    cfg = load_config()
    cfg["translate"]["openai_custom"] = {}
    save_config(cfg)
    before = _snapshot_state()
    stub_server.received.clear()

    if case == "models_only_url":
        with TestClient(app) as c:
            resp = c.post(
                "/api/openai/models",
                json={"base_url": url, "api_key": "", "group_id": GID_NEW},
            )
        assert resp.json()["success"] is True
        gets = [r for r in stub_server.received if r[0] == "GET"]
        assert len(gets) == 1
        assert gets[0][2] is None
    elif case == "test_url_model_temp_key":
        with TestClient(app) as c:
            resp = c.post(
                "/api/openai/test",
                json={
                    "base_url": url,
                    "api_key": KEY_TEMP,
                    "model": "m",
                    "group_id": GID_NEW,
                },
            )
        assert resp.json()["success"] is True
        posts = [r for r in stub_server.received if r[0] == "POST"]
        assert len(posts) == 1
        assert posts[0][2] == f"Bearer {KEY_TEMP}"
    else:
        with TestClient(app) as c:
            resp = c.post(
                "/api/ai/tags/test",
                json={
                    "provider": f"openai:{GID_NEW}",
                    "model": "m-tags",
                    "api_key": KEY_TEMP,
                    "base_url": url,
                },
            )
        assert resp.status_code == 200
        posts = [r for r in stub_server.received if r[0] == "POST"]
        assert len(posts) == 1
        assert posts[0][2] == f"Bearer {KEY_TEMP}"

    after = _snapshot_state()
    assert after[0] == before[0]
    assert after[1] == before[1]
    assert after[2] == before[2]


@pytest.mark.parametrize(
    "case",
    [
        "resolve_ok",
        "resolve_no_key_ok",
        "resolve_missing_group",
        "resolve_empty_base_url",
        "factory_missing_group",
        "group_id_invalid_models",
        "group_id_invalid_test",
    ],
    ids=[
        "resolve_ok",
        "resolve_no_key_ok",
        "resolve_missing_group",
        "resolve_empty_base_url",
        "factory_missing_group",
        "group_id_invalid_models",
        "group_id_invalid_test",
    ],
    )
def test_custom_group_provider_and_group_id_rows(case, stub_server, monkeypatch):
    from core.ai_services.tagging import TaggingFailure, resolve_vision_conn

    url = f"http://127.0.0.1:{stub_server.server_port}/v1/"

    if case == "resolve_ok":
        _seed_two_groups(f"http://127.0.0.1:9/v1", url)
        cfg = load_config()
        tags = cfg.setdefault("ai_services", {}).setdefault("tags", {})
        tags["provider"] = f"openai:{GID_A}"
        tags["model"] = "m-tags"
        conn = resolve_vision_conn(cfg)
        assert conn.provider == "openai"
        assert conn.model == "m-tags"
        assert conn.base_url == url.rstrip("/")
        assert conn.api_key == KEY_CUSTOM
    elif case == "resolve_no_key_ok":
        _seed_two_groups(f"http://127.0.0.1:9/v1", url, custom_key="")
        cfg = load_config()
        tags = cfg.setdefault("ai_services", {}).setdefault("tags", {})
        tags["provider"] = f"openai:{GID_A}"
        tags["model"] = "m-tags"
        conn = resolve_vision_conn(cfg)
        assert conn.provider == "openai"
        assert conn.api_key == ""
    elif case == "resolve_missing_group":
        _seed_two_groups(url, f"http://127.0.0.1:9/v1")
        cfg = load_config()
        tags = cfg.setdefault("ai_services", {}).setdefault("tags", {})
        tags["provider"] = f"openai:{GID_NEW}"
        tags["model"] = "m-tags"
        with pytest.raises(TaggingFailure) as ei:
            resolve_vision_conn(cfg)
        assert ei.value.reason == "not_configured"
        assert ei.value.detail == "provider"
    elif case == "resolve_empty_base_url":
        _seed_two_groups(url, f"http://127.0.0.1:9/v1", custom_key="")
        cfg = load_config()
        cfg["translate"]["openai_custom"][GID_A]["base_url"] = ""
        save_config(cfg)
        tags = cfg.setdefault("ai_services", {}).setdefault("tags", {})
        cfg2 = load_config()
        cfg2.setdefault("ai_services", {}).setdefault("tags", {})["provider"] = f"openai:{GID_A}"
        cfg2["ai_services"]["tags"]["model"] = "m-tags"
        with pytest.raises(TaggingFailure) as ei:
            resolve_vision_conn(cfg2)
        assert ei.value.reason == "not_configured"
        assert ei.value.detail == "base_url"
    elif case == "factory_missing_group":
        _seed_two_groups(url, f"http://127.0.0.1:9/v1")
        cfg = load_config()
        cfg["translate"]["provider"] = f"openai:{GID_NEW}"
        with pytest.raises(ValueError):
            create_translate_service(cfg["translate"], "zh-TW")
    else:
        def _boom(*a, **k):
            raise AssertionError("load_config must not be called")

        monkeypatch.setattr("web.routers.openai_translate.load_config", _boom)
        stub_server.received.clear()
        bad = "oc01234567\n" if case == "group_id_invalid_models" else "../x"
        with TestClient(app) as c:
            if case == "group_id_invalid_models":
                resp = c.post(
                    "/api/openai/models",
                    json={"base_url": url, "api_key": "", "group_id": bad},
                )
            else:
                resp = c.post(
                    "/api/openai/test",
                    json={"base_url": url, "api_key": "", "model": "m", "group_id": bad},
                )
        assert resp.status_code == 200
        assert resp.json()["success"] is False
        assert resp.json()["error"] == "invalid_group_id"
        assert stub_server.received == []



