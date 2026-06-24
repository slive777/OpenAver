"""
tests/integration/test_installer_api.py — install-context / trigger-update 端點 403 gate
"""
from fastapi.testclient import TestClient
from web.app import app


def test_install_context_non_desktop_returns_403(monkeypatch):
    """dev/uvicorn 裸跑（無 OPENAVER_STANDALONE）→ 403。"""
    monkeypatch.delenv("OPENAVER_STANDALONE", raising=False)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/install-context")
    assert resp.status_code == 403


def test_trigger_update_non_desktop_returns_403(monkeypatch):
    """dev/uvicorn 裸跑（無 OPENAVER_STANDALONE）→ 403。"""
    monkeypatch.delenv("OPENAVER_STANDALONE", raising=False)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post("/api/trigger-update")
    assert resp.status_code == 403
