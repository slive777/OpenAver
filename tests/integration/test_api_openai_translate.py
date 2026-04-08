"""
OpenAI Compatible API router integration tests.

Covers /api/openai/models and /api/openai/test endpoints.
Uses TestClient + mock httpx.AsyncClient (no real HTTP connections).
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, MagicMock
import httpx

from web.app import app

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

    def test_models_empty_base_url(self):
        """Empty base_url → success=False, fixed error key."""
        response = client.post("/api/openai/models", json={
            "base_url": "",
            "api_key": ""
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "missing_base_url"

    def test_models_http_error(self):
        """HTTP 403 from upstream → success=False, error key is 'forbidden'."""
        resp = _make_http_response(403)
        mock_cm = _make_mock_client(get_response=resp)

        with patch("web.routers.openai_translate.httpx.AsyncClient", return_value=mock_cm):
            response = client.post("/api/openai/models", json={
                "base_url": "http://localhost:8080",
                "api_key": "bad-key"
            })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "forbidden"

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

    def test_models_not_found(self):
        """HTTP 404 → success=False, error='not_found'."""
        resp = _make_http_response(404)
        mock_cm = _make_mock_client(get_response=resp)

        with patch("web.routers.openai_translate.httpx.AsyncClient", return_value=mock_cm):
            response = client.post("/api/openai/models", json={
                "base_url": "http://localhost:8080",
                "api_key": ""
            })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "not_found"

    def test_models_rate_limited(self):
        """HTTP 429 → success=False, error='rate_limited'."""
        resp = _make_http_response(429)
        mock_cm = _make_mock_client(get_response=resp)

        with patch("web.routers.openai_translate.httpx.AsyncClient", return_value=mock_cm):
            response = client.post("/api/openai/models", json={
                "base_url": "http://localhost:8080",
                "api_key": "test-key"
            })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "rate_limited"

    def test_models_timeout(self):
        """Timeout → success=False, error is a fixed string (no exception text)."""
        mock_cm = _make_mock_client(raise_on_get=httpx.TimeoutException("timed out"))

        with patch("web.routers.openai_translate.httpx.AsyncClient", return_value=mock_cm):
            response = client.post("/api/openai/models", json={
                "base_url": "http://localhost:8080",
                "api_key": ""
            })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        # error must be a fixed key matching locale
        assert data["error"] == "connection_timeout"

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

    def test_translate_forbidden(self):
        """HTTP 403 → success=False, error='forbidden'."""
        resp = _make_http_response(403)
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
        assert data["error"] == "forbidden"

    def test_translate_not_found(self):
        """HTTP 404 → success=False, error='not_found'."""
        resp = _make_http_response(404)
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
        assert data["success"] is False
        assert data["error"] == "not_found"

    def test_translate_rate_limited(self):
        """HTTP 429 → success=False, error='rate_limited'."""
        resp = _make_http_response(429)
        mock_cm = _make_mock_client(post_response=resp)

        with patch("web.routers.openai_translate.httpx.AsyncClient", return_value=mock_cm), \
             patch("web.routers.openai_translate.load_config", return_value={"general": {"locale": "zh-TW"}}):
            response = client.post("/api/openai/test", json={
                "base_url": "http://localhost:8080",
                "api_key": "test-key",
                "model": "my-model"
            })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "rate_limited"

    def test_translate_server_error(self):
        """HTTP 500 → success=False, error='http_error' (generic fallback)."""
        resp = _make_http_response(500)
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
        assert data["success"] is False
        assert data["error"] == "http_error"

    def test_translate_api_error_response(self):
        """Upstream returns error field with XSS payload → fixed error string, no raw message."""
        api_resp = {"error": {"message": "Model not found <script>alert(1)</script>"}}
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
        assert data["success"] is False
        # Negative assertions: must NOT leak the upstream error message
        assert "script" not in data["error"]
        assert "alert" not in data["error"]
        assert "Model not found" not in data["error"]
        assert data["error"]  # non-empty fixed string

    def test_translate_unknown_format(self):
        """Response with no 'choices' and no 'error' → success=False, fixed error string."""
        api_resp = {"unexpected": "format"}
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
        assert data["success"] is False
        assert data["error"]  # non-empty fixed string

    def test_translate_ja_locale(self):
        """ja locale short-circuits without any HTTP call → success=True, translation='ja_skip'."""
        mock_cm = _make_mock_client()  # no side-effects configured

        with patch("web.routers.openai_translate.httpx.AsyncClient", return_value=mock_cm) as mock_client_cls, \
             patch("web.routers.openai_translate.load_config", return_value={"general": {"locale": "ja"}}):
            response = client.post("/api/openai/test", json={
                "base_url": "http://localhost:8080",
                "api_key": "",
                "model": "my-model"
            })
            # httpx.AsyncClient should never be instantiated
            mock_client_cls.assert_not_called()

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["translation"] == "ja_skip"

    def test_translate_empty_base_url(self):
        """Empty base_url → success=False, fixed error key."""
        response = client.post("/api/openai/test", json={
            "base_url": "",
            "api_key": "",
            "model": "my-model"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "missing_base_url"

    def test_translate_empty_model(self):
        """Empty model → success=False, fixed error key."""
        response = client.post("/api/openai/test", json={
            "base_url": "http://localhost:8080",
            "api_key": "",
            "model": ""
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "missing_model"

    def test_translate_general_exception(self):
        """Generic exception → success=False, error does NOT leak exception details."""
        mock_cm = _make_mock_client(raise_on_post=Exception("Internal error details"))

        with patch("web.routers.openai_translate.httpx.AsyncClient", return_value=mock_cm), \
             patch("web.routers.openai_translate.load_config", return_value={"general": {"locale": "zh-TW"}}):
            response = client.post("/api/openai/test", json={
                "base_url": "http://localhost:8080",
                "api_key": "",
                "model": "my-model"
            })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        # Negative assertion: must NOT contain raw exception text
        assert "Internal error details" not in data["error"]
        assert data["error"]  # non-empty fixed string
