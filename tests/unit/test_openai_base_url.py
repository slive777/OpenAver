"""TASK-206b-T1: OpenAI Base URL normalization vectors + sink parity.

Test 1 reads the shared vectors file (produced by the implementation);
test 2 drives the send sites against a local stub HTTP server
(no httpx mock, no real network beyond 127.0.0.1).
"""

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from core.ai_services.tagging import resolve_vision_conn
from core.ai_services.vision_chat import vision_chat
from core.openai_client import (
    chat_completions_url,
    models_url,
    normalize_openai_base_url,
    request_vision,
)
from core.translate_service import create_translate_service
from web.app import app

_VECTORS = json.loads(
    (Path(__file__).resolve().parents[1] / "data" / "openai_base_url_vectors.json").read_text(
        encoding="utf-8"
    )
)["vectors"]

FAKE_KEY = "sk-test-fake-not-real"
FAKE_MODEL = "m"
DATA_URI = "data:image/jpeg;base64,AA=="

client = TestClient(app)


@pytest.mark.parametrize("v", _VECTORS, ids=[f"case-{i}" for i in range(len(_VECTORS))])
def test_openai_base_url_vectors(v):
    raw = v["input"]
    assert normalize_openai_base_url(raw) == v["normalized"]
    assert chat_completions_url(raw) == v["chat_completions_url"]
    assert models_url(raw) == v["models_url"]
    expected_preview = (
        "" if normalize_openai_base_url(raw) == "" else chat_completions_url(raw)
    )
    assert v["preview"] == expected_preview
    assert normalize_openai_base_url(normalize_openai_base_url(raw)) == normalize_openai_base_url(raw)


class _StubHandler(BaseHTTPRequestHandler):
    def _reply(self, body):
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.server.received.append(("GET", self.path))
        self._reply({"data": [{"id": FAKE_MODEL}]})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        self.server.received.append(("POST", self.path))
        self._reply(
            {"choices": [{"message": {"content": "x"}, "finish_reason": "stop"}]}
        )

    def log_message(self, *args):
        pass


@pytest.fixture()
def fake_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
    server.received = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def _cfg(base_url):
    return {
        "ai_services": {"tags": {"provider": "openai", "model": FAKE_MODEL}},
        "translate": {
            "claude": {"api_key": "", "model": "Y"},
            "gemini": {"api_key": "", "model": "Y"},
            "openai": {
                "api_key": FAKE_KEY,
                "base_url": base_url,
                "model": FAKE_MODEL,
            },
            "openai_official": {"api_key": "", "model": "Y"},
            "ollama": {"url": "", "model": "Y"},
        },
    }


@pytest.mark.parametrize(
    "suffix", ["/v1", "/v1/", "/v1/chat/completions"], ids=["v1", "v1_slash", "v1_full_endpoint"]
)
def test_all_four_sinks_send_identical_path(fake_server, monkeypatch, suffix):
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
    base = f"http://127.0.0.1:{fake_server.server_port}{suffix}"

    fake_server.received.clear()
    with patch("web.routers.openai_translate.load_config", return_value={}):
        r = client.post(
            "/api/openai/models", json={"base_url": base, "api_key": FAKE_KEY}
        )
    assert r.status_code == 200
    assert r.json()["success"] is True
    assert fake_server.received == [("GET", "/v1/models")]

    fake_server.received.clear()
    with patch("web.routers.openai_translate.load_config", return_value={}):
        r = client.post(
            "/api/openai/test",
            json={"base_url": base, "api_key": FAKE_KEY, "model": FAKE_MODEL},
        )
    assert r.status_code == 200
    assert r.json()["success"] is True
    assert fake_server.received == [("POST", "/v1/chat/completions")]

    fake_server.received.clear()
    svc = create_translate_service(
        {
            "provider": "openai",
            "openai": {"base_url": base, "api_key": FAKE_KEY, "model": FAKE_MODEL},
        }
    )
    out = asyncio.run(svc.translate_or_raise("title"))
    assert out == "x"
    assert fake_server.received == [("POST", "/v1/chat/completions")]

    fake_server.received.clear()
    out = asyncio.run(
        vision_chat(resolve_vision_conn(_cfg(base)), "s", "u", DATA_URI)
    )
    assert out == "x"
    assert fake_server.received == [("POST", "/v1/chat/completions")]

    fake_server.received.clear()
    out = asyncio.run(
        request_vision(base, FAKE_KEY, FAKE_MODEL, "s", "u", DATA_URI, timeout=5)
    )
    assert out == "x"
    assert fake_server.received == [("POST", "/v1/chat/completions")]
