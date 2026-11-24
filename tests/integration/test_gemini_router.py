"""
Gemini API router integration tests — model pagination.

Covers POST /api/gemini/test endpoint.
Uses TestClient + mock httpx.AsyncClient (no real HTTP connections).
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, MagicMock
import httpx

from web.app import app

client = TestClient(app)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_client(get_response=None, raise_on_get=None):
    """Build a mock httpx.AsyncClient context-manager with configurable responses."""
    mock_client = AsyncMock()

    if raise_on_get is not None:
        mock_client.get = AsyncMock(side_effect=raise_on_get)
    elif get_response is not None:
        mock_client.get = AsyncMock(return_value=get_response)

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


class TestGeminiErrors:

    def test_invalid_api_key_400(self):
        """BC5: API Key 無效 (HTTP 400) → success=False + error 非空。"""
        resp = _make_http_response(400)
        mock_cm = _make_mock_client(get_response=resp)

        with patch("web.routers.gemini.httpx.AsyncClient", return_value=mock_cm):
            response = client.post("/api/gemini/test", json={"api_key": "bad-key"})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error"]  # 非空即可，不鎖定具體文案




class _PageHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlsplit(self.path)
        query = parse_qs(parsed.query)
        self.server.received.append((parsed.path, query, self.headers.get("x-goog-api-key")))
        token = query.get("pageToken", [""])[0]
        mode = self.server.mode
        status = 500 if mode == "failure" and token else 200
        body = {"models": [{"name": "models/gemini-2.0-flash"}]}
        if mode == "follow":
            if token:
                body = {"models": [{"name": "models/gemini-2.5-flash-lite"}]}
            else:
                body["nextPageToken"] = "page-two"
        elif mode == "repeat_token":
            body["nextPageToken"] = "repeat-page"
        elif mode == "endless_tokens":
            body["nextPageToken"] = str(int(token or "0") + 1)
        elif mode == "failure" and not token:
            body["nextPageToken"] = "page-two"
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


@pytest.fixture
def stub_server(monkeypatch):
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    server = ThreadingHTTPServer(("127.0.0.1", 0), _PageHandler)
    server.received = []
    monkeypatch.setattr("core.gemini_client.GEMINI_BASE_URL", f"http://127.0.0.1:{server.server_port}")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_gemini_models_follow_next_page_token(stub_server):
    stub_server.mode = "follow"
    response = client.post("/api/gemini/test", json={"api_key": "fake-gemini-key-123456"})
    assert response.json()["success"] is True
    assert "gemini-2.5-flash-lite" in [model["name"] for model in response.json()["models"]]
    assert stub_server.received == [
        ("/models", {"pageSize": ["1000"]}, "fake-gemini-key-123456"),
        ("/models", {"pageSize": ["1000"], "pageToken": ["page-two"]}, "fake-gemini-key-123456"),
    ]


@pytest.mark.parametrize("mode,expected", [("repeat_token", 2), ("endless_tokens", 10)], ids=["repeat_token", "endless_tokens"])
def test_gemini_models_pagination_terminates(stub_server, mode, expected):
    stub_server.mode = mode
    response = client.post("/api/gemini/test", json={"api_key": "fake-gemini-key-123456"})
    assert response.json()["success"] is True
    assert response.json()["models"]
    assert len(stub_server.received) == expected


def test_gemini_models_page_failure_gives_no_partial_list(stub_server):
    stub_server.mode = "failure"
    response = client.post("/api/gemini/test", json={"api_key": "fake-gemini-key-123456"})
    assert len(stub_server.received) == 2
    assert response.json()["success"] is False
    assert response.json()["models"] == []
    assert response.json()["count"] == 0
