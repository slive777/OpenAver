"""
tests/unit/test_pywebview_api.py
TDD-lite: windows/pywebview_api.py の Api.open_url() 邊界條件測試

pywebview は Windows 専用。すべてのシステムコールをモックして実行する。
"""
import pytest
import sys
import os
from unittest.mock import MagicMock, patch
from pathlib import Path
import importlib
import importlib.util


@pytest.fixture
def api_module(monkeypatch):
    """
    pywebview_api モジュールをロードする。
    webview モジュールをモックして import エラーを回避する。
    """
    mock_webview = MagicMock()
    mock_webview.OPEN_DIALOG = 10
    mock_webview.FOLDER_DIALOG = 20
    monkeypatch.setitem(sys.modules, 'webview', mock_webview)
    monkeypatch.setitem(sys.modules, 'webview.dom', MagicMock())

    spec = importlib.util.spec_from_file_location(
        "pywebview_api_test",
        Path(__file__).parent.parent.parent / "windows" / "pywebview_api.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def api_instance(api_module):
    return api_module.Api()


# ---------------------------------------------------------------------------
# Case 1: valid https URL → True
# ---------------------------------------------------------------------------
def test_open_url_https_success(api_module, api_instance, monkeypatch):
    """https:// URL を win32 で開いた場合 True を返す"""
    monkeypatch.setattr(sys, 'platform', 'win32')

    mock_startfile = MagicMock()
    monkeypatch.setattr(api_module.os, 'startfile', mock_startfile, raising=False)

    result = api_instance.open_url("https://www.dmm.co.jp/mono/dvd/-/detail/=/cid=abc123/")
    assert result is True
    mock_startfile.assert_called_once_with("https://www.dmm.co.jp/mono/dvd/-/detail/=/cid=abc123/")


# ---------------------------------------------------------------------------
# Case 2: valid http URL → True
# ---------------------------------------------------------------------------
def test_open_url_http_success(api_module, api_instance, monkeypatch):
    """http:// URL も合法として True を返す"""
    monkeypatch.setattr(sys, 'platform', 'win32')

    mock_startfile = MagicMock()
    monkeypatch.setattr(api_module.os, 'startfile', mock_startfile, raising=False)

    result = api_instance.open_url("http://example.com")
    assert result is True
    mock_startfile.assert_called_once_with("http://example.com")


# ---------------------------------------------------------------------------
# Case 3: empty string → False
# ---------------------------------------------------------------------------
def test_open_url_empty_string(api_module, api_instance, monkeypatch):
    """空文字列の場合 False を返す（システム API を呼ばない）"""
    monkeypatch.setattr(sys, 'platform', 'win32')

    mock_startfile = MagicMock()
    monkeypatch.setattr(api_module.os, 'startfile', mock_startfile, raising=False)

    result = api_instance.open_url("")
    assert result is False
    mock_startfile.assert_not_called()


# ---------------------------------------------------------------------------
# Case 4: javascript: scheme → False
# ---------------------------------------------------------------------------
def test_open_url_javascript_scheme(api_module, api_instance, monkeypatch):
    """javascript: スキームは拒否して False を返す"""
    monkeypatch.setattr(sys, 'platform', 'win32')

    mock_startfile = MagicMock()
    monkeypatch.setattr(api_module.os, 'startfile', mock_startfile, raising=False)

    result = api_instance.open_url("javascript:alert(1)")
    assert result is False
    mock_startfile.assert_not_called()


# ---------------------------------------------------------------------------
# Case 5: file:// scheme → False
# ---------------------------------------------------------------------------
def test_open_url_file_scheme(api_module, api_instance, monkeypatch):
    """file:// スキームは拒否して False を返す"""
    monkeypatch.setattr(sys, 'platform', 'win32')

    mock_startfile = MagicMock()
    monkeypatch.setattr(api_module.os, 'startfile', mock_startfile, raising=False)

    result = api_instance.open_url("file:///C:/evil.exe")
    assert result is False
    mock_startfile.assert_not_called()


# ---------------------------------------------------------------------------
# Case 6: valid URL + os.startfile raises OSError → False
# ---------------------------------------------------------------------------
def test_open_url_startfile_raises_oserror(api_module, api_instance, monkeypatch):
    """os.startfile が OSError を投げた場合 False を返す（例外を伝播させない）"""
    monkeypatch.setattr(sys, 'platform', 'win32')

    mock_startfile = MagicMock(side_effect=OSError("No association"))
    monkeypatch.setattr(api_module.os, 'startfile', mock_startfile, raising=False)

    result = api_instance.open_url("https://valid.com")
    assert result is False


# ---------------------------------------------------------------------------
# Case 7: None → False
# ---------------------------------------------------------------------------
def test_open_url_none(api_module, api_instance, monkeypatch):
    """None を渡した場合 False を返す（防御的処理）"""
    monkeypatch.setattr(sys, 'platform', 'win32')

    mock_startfile = MagicMock()
    monkeypatch.setattr(api_module.os, 'startfile', mock_startfile, raising=False)

    result = api_instance.open_url(None)
    assert result is False
    mock_startfile.assert_not_called()


# ---------------------------------------------------------------------------
# Case 8: macOS subprocess returns non-zero → False
# ---------------------------------------------------------------------------
def test_open_url_macos_nonzero_returncode(api_module, api_instance, monkeypatch):
    """macOS で open コマンドが非ゼロ終了した場合 False を返す"""
    monkeypatch.setattr(sys, 'platform', 'darwin')

    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_run = MagicMock(return_value=mock_result)
    monkeypatch.setattr(api_module.subprocess, 'run', mock_run)

    result = api_instance.open_url("https://example.com")
    assert result is False
    mock_run.assert_called_once_with(['open', 'https://example.com'])


# ---------------------------------------------------------------------------
# Case 9: Linux subprocess returns zero → True
# ---------------------------------------------------------------------------
def test_open_url_linux_success(api_module, api_instance, monkeypatch):
    """Linux で xdg-open が正常終了した場合 True を返す"""
    monkeypatch.setattr(sys, 'platform', 'linux')

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_run = MagicMock(return_value=mock_result)
    monkeypatch.setattr(api_module.subprocess, 'run', mock_run)

    result = api_instance.open_url("https://example.com")
    assert result is True
    mock_run.assert_called_once_with(['xdg-open', 'https://example.com'])
