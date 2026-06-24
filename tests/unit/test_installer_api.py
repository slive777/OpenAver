"""
tests/unit/test_installer_api.py — _is_mac_desktop() 真值表、/api/install-context、
/api/trigger-update、capabilities 守衛（全 mock，不需真 desktop 環境）
"""
import json
import pytest
from pathlib import Path
from unittest import mock
from fastapi.testclient import TestClient

import web.app as _web_app


@pytest.fixture
def client():
    return TestClient(_web_app.app, raise_server_exceptions=False)


# ─────────────────────────────────────────────────────────
# 1. _is_mac_desktop() 真值表
# ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("standalone_val,platform_val,expected", [
    ("1",  "darwin", True),   # 桌面 macOS → True
    ("1",  "win32",  False),  # standalone 但非 darwin → False
    ("1",  "linux",  False),  # standalone 但非 darwin → False
    ("0",  "darwin", False),  # darwin 但非 standalone → False
    (None, "darwin", False),  # env 未設 + darwin → False
])
def test_is_mac_desktop_truth_table(standalone_val, platform_val, expected, monkeypatch):
    """五象限：OPENAVER_STANDALONE × sys.platform"""
    monkeypatch.delenv("OPENAVER_STANDALONE", raising=False)
    if standalone_val is not None:
        monkeypatch.setenv("OPENAVER_STANDALONE", standalone_val)
    monkeypatch.setattr(_web_app.sys, "platform", platform_val)

    assert _web_app._is_mac_desktop() is expected, (
        f"standalone_val={standalone_val!r}, platform={platform_val!r} → expected {expected}"
    )


# ─────────────────────────────────────────────────────────
# 2. GET /api/install-context
# ─────────────────────────────────────────────────────────

def test_install_context_non_desktop_returns_403(client, monkeypatch):
    monkeypatch.setattr("web.app._is_windows_desktop", lambda: False)
    monkeypatch.setattr("web.app._is_mac_desktop", lambda: False)
    resp = client.get("/api/install-context")
    assert resp.status_code == 403


def test_install_context_windows_default_path(client, monkeypatch):
    """Windows desktop：sys.executable 在 ~/OpenAver/python/pythonw.exe → is_default_path=True"""
    monkeypatch.setattr("web.app._is_windows_desktop", lambda: True)
    monkeypatch.setattr("web.app._is_mac_desktop", lambda: False)

    home = Path.home()
    fake_exe = home / "OpenAver" / "python" / "pythonw.exe"
    monkeypatch.setattr(_web_app.sys, "platform", "win32")
    monkeypatch.setattr(_web_app.sys, "executable", str(fake_exe))

    resp = client.get("/api/install-context")
    assert resp.status_code == 200
    assert resp.json() == {"is_default_path": True}


def test_install_context_windows_non_default_path(client, monkeypatch):
    """Windows desktop：sys.executable 在非預設路徑 → is_default_path=False"""
    monkeypatch.setattr("web.app._is_windows_desktop", lambda: True)
    monkeypatch.setattr("web.app._is_mac_desktop", lambda: False)

    fake_exe = "/custom/path/python/pythonw.exe"
    monkeypatch.setattr(_web_app.sys, "platform", "win32")
    monkeypatch.setattr(_web_app.sys, "executable", fake_exe)

    resp = client.get("/api/install-context")
    assert resp.status_code == 200
    assert resp.json() == {"is_default_path": False}


def test_install_context_macos_default_path(client, monkeypatch):
    """macOS desktop：sys.executable 在 ~/OpenAver/python/bin/python3 → is_default_path=True"""
    monkeypatch.setattr("web.app._is_windows_desktop", lambda: False)
    monkeypatch.setattr("web.app._is_mac_desktop", lambda: True)

    home = Path.home()
    fake_exe = home / "OpenAver" / "python" / "bin" / "python3"
    monkeypatch.setattr(_web_app.sys, "platform", "darwin")
    monkeypatch.setattr(_web_app.sys, "executable", str(fake_exe))

    resp = client.get("/api/install-context")
    assert resp.status_code == 200
    assert resp.json() == {"is_default_path": True}


def test_install_context_path_exception_fallback(client, monkeypatch):
    """路徑計算異常 → fallback is_default_path=True（保守）"""
    monkeypatch.setattr("web.app._is_windows_desktop", lambda: True)
    monkeypatch.setattr("web.app._is_mac_desktop", lambda: False)
    monkeypatch.setattr(_web_app.sys, "platform", "win32")

    # Path("") 會導致 Path.parent.parent 算出 "." / "." 而非 OSError，
    # 所以改 patch Path 本身拋出例外
    original_path = _web_app.Path

    def raise_path(*args, **kwargs):
        if args and args[0] == _web_app.sys.executable:
            raise OSError("simulated path error")
        return original_path(*args, **kwargs)

    monkeypatch.setattr("web.app.Path", raise_path)
    monkeypatch.setattr(_web_app.sys, "executable", "/some/exe")

    resp = client.get("/api/install-context")
    assert resp.status_code == 200
    assert resp.json() == {"is_default_path": True}


# ─────────────────────────────────────────────────────────
# 3. POST /api/trigger-update
# ─────────────────────────────────────────────────────────

def test_trigger_update_non_desktop_returns_403(client, monkeypatch):
    monkeypatch.setattr("web.app._is_windows_desktop", lambda: False)
    monkeypatch.setattr("web.app._is_mac_desktop", lambda: False)
    resp = client.post("/api/trigger-update")
    assert resp.status_code == 403


def test_trigger_update_windows_calls_powershell(client, monkeypatch):
    """Windows → subprocess.Popen 以 powershell.exe + CREATE_NEW_CONSOLE 呼叫"""
    monkeypatch.setattr("web.app._is_windows_desktop", lambda: True)
    monkeypatch.setattr("web.app._is_mac_desktop", lambda: False)
    monkeypatch.setattr(_web_app.sys, "platform", "win32")

    # CREATE_NEW_CONSOLE (0x10) 在 Linux 上不存在，以 mock.patch.object(create=True) 跨平台 patch
    CREATE_NEW_CONSOLE = 0x00000010
    with mock.patch.object(_web_app.subprocess, "CREATE_NEW_CONSOLE", CREATE_NEW_CONSOLE, create=True), \
         mock.patch("web.app.subprocess.Popen") as mock_popen:
        resp = client.post("/api/trigger-update")

    assert resp.status_code == 200
    assert resp.json() == {"success": True}
    mock_popen.assert_called_once()
    call_args, call_kwargs = mock_popen.call_args
    cmd = call_args[0]
    assert cmd[0] == "powershell.exe"
    assert call_kwargs.get("creationflags") == CREATE_NEW_CONSOLE


def test_trigger_update_macos_calls_osascript(client, monkeypatch):
    """macOS → subprocess.Popen 以 osascript 呼叫"""
    monkeypatch.setattr("web.app._is_windows_desktop", lambda: False)
    monkeypatch.setattr("web.app._is_mac_desktop", lambda: True)
    monkeypatch.setattr(_web_app.sys, "platform", "darwin")

    with mock.patch("web.app.subprocess.Popen") as mock_popen:
        resp = client.post("/api/trigger-update")

    assert resp.status_code == 200
    assert resp.json() == {"success": True}
    mock_popen.assert_called_once()
    call_args, _ = mock_popen.call_args
    cmd = call_args[0]
    assert cmd[0] == "osascript"


def test_trigger_update_subprocess_oserror_returns_500(client, monkeypatch):
    """subprocess.Popen 拋 OSError → HTTP 500"""
    monkeypatch.setattr("web.app._is_windows_desktop", lambda: True)
    monkeypatch.setattr("web.app._is_mac_desktop", lambda: False)
    monkeypatch.setattr(_web_app.sys, "platform", "win32")

    with mock.patch("web.app.subprocess.Popen", side_effect=OSError("not found")):
        resp = client.post("/api/trigger-update")

    assert resp.status_code == 500


# ─────────────────────────────────────────────────────────
# 4. capabilities 守衛：trigger-update 不在 blob
# ─────────────────────────────────────────────────────────

def test_trigger_update_not_in_capabilities(client):
    """capabilities JSON blob 不得含 trigger-update（不揭露給 AI agent）"""
    blob = json.dumps(client.get("/api/capabilities").json(), ensure_ascii=False).lower()
    assert "trigger-update" not in blob, "capabilities 不得揭露 trigger-update"
    assert "/api/trigger-update" not in blob, "capabilities 不得揭露 /api/trigger-update"
