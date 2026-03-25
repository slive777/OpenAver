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


# ===========================================================================
# P1-2: Logger tests — verify all 7 except blocks emit the correct log level
# ===========================================================================

# ---------------------------------------------------------------------------
# Logger test 1: open_file — custom player Popen raises OSError → logger.warning
# ---------------------------------------------------------------------------
def test_open_file_custom_player_popen_oserror_logs_warning(api_module, api_instance, monkeypatch):
    """custom player の Popen が OSError → logger.warning を呼ぶ（fallback は継続）"""
    monkeypatch.setattr(sys, 'platform', 'win32')

    # ファイルが存在するように見せる
    monkeypatch.setattr(api_module.os.path, 'exists', lambda p: True)

    # _get_player_path が有効なプレイヤーを返す
    monkeypatch.setattr(api_instance, '_get_player_path', lambda: 'C:\\Players\\vlc.exe')

    # Popen は失敗、startfile は成功
    monkeypatch.setattr(api_module.subprocess, 'Popen', MagicMock(side_effect=OSError("spawn failed")))
    monkeypatch.setattr(api_module.os, 'startfile', MagicMock(), raising=False)

    mock_logger = MagicMock()
    monkeypatch.setattr(api_module, 'logger', mock_logger)

    result = api_instance.open_file('C:\\video.mp4')

    mock_logger.warning.assert_called_once()
    warning_msg = mock_logger.warning.call_args[0][0]
    assert 'custom player failed' in warning_msg
    assert 'falling back to OS default' in warning_msg
    # fallback should continue — startfile called and result is True
    api_module.os.startfile.assert_called_once()
    assert result is True


# ---------------------------------------------------------------------------
# Logger test 2: open_file — OS default startfile raises OSError → logger.error
# ---------------------------------------------------------------------------
def test_open_file_os_default_oserror_logs_error(api_module, api_instance, monkeypatch):
    """OS デフォルト開き (startfile) が OSError → logger.error を呼び False を返す"""
    monkeypatch.setattr(sys, 'platform', 'win32')

    monkeypatch.setattr(api_module.os.path, 'exists', lambda p: True)
    monkeypatch.setattr(api_instance, '_get_player_path', lambda: '')

    monkeypatch.setattr(api_module.os, 'startfile', MagicMock(side_effect=OSError("no assoc")), raising=False)

    mock_logger = MagicMock()
    monkeypatch.setattr(api_module, 'logger', mock_logger)

    result = api_instance.open_file('C:\\video.mp4')

    mock_logger.error.assert_called_once()
    error_msg = mock_logger.error.call_args[0][0]
    assert 'open_file failed' in error_msg
    assert result is False


# ---------------------------------------------------------------------------
# Logger test 3: open_url — os.startfile raises OSError → logger.error
# ---------------------------------------------------------------------------
def test_open_url_startfile_oserror_logs_error(api_module, api_instance, monkeypatch):
    """open_url で os.startfile が OSError → logger.error を呼び False を返す"""
    monkeypatch.setattr(sys, 'platform', 'win32')

    monkeypatch.setattr(api_module.os, 'startfile', MagicMock(side_effect=OSError("No association")), raising=False)

    mock_logger = MagicMock()
    monkeypatch.setattr(api_module, 'logger', mock_logger)

    result = api_instance.open_url("https://valid.com")

    mock_logger.error.assert_called_once()
    error_msg = mock_logger.error.call_args[0][0]
    assert 'open_url failed' in error_msg
    assert 'https://valid.com' in error_msg
    assert result is False


# ---------------------------------------------------------------------------
# Logger test 4: open_folder — subprocess.Popen raises OSError → logger.error
# ---------------------------------------------------------------------------
def test_open_folder_popen_oserror_logs_error(api_module, api_instance, monkeypatch):
    """open_folder で Popen が OSError → logger.error を呼び False を返す"""
    monkeypatch.setattr(sys, 'platform', 'win32')

    monkeypatch.setattr(api_module.os.path, 'exists', lambda p: True)
    monkeypatch.setattr(api_module.os.path, 'isfile', lambda p: False)
    monkeypatch.setattr(api_module.subprocess, 'Popen', MagicMock(side_effect=OSError("explorer missing")))

    mock_logger = MagicMock()
    monkeypatch.setattr(api_module, 'logger', mock_logger)

    result = api_instance.open_folder('C:\\some\\folder')

    mock_logger.error.assert_called_once()
    error_msg = mock_logger.error.call_args[0][0]
    assert 'open_folder failed' in error_msg
    assert result is False


# ---------------------------------------------------------------------------
# Logger test 5: _get_video_extensions — json.load raises JSONDecodeError → logger.warning
# ---------------------------------------------------------------------------
def test_get_video_extensions_json_error_logs_warning(api_module, api_instance, monkeypatch, tmp_path):
    """_get_video_extensions の JSON parse 失敗 → logger.warning + DEFAULT_VIDEO_EXTENSIONS を返す"""
    import json as _json

    # 壊れた config.json を tmp_path に作る
    bad_config = tmp_path / 'config.json'
    bad_config.write_text('{invalid json', encoding='utf-8')

    original_open = open

    def patched_open(path, *args, **kwargs):
        if 'config.json' in str(path):
            raise _json.JSONDecodeError("bad json", "", 0)
        return original_open(path, *args, **kwargs)

    # Path.exists を True に、open は JSONDecodeError
    class FakePath:
        def __init__(self, *a):
            pass
        def __truediv__(self, other):
            return self
        def exists(self):
            return True
        def __str__(self):
            return 'fake/config.json'

    monkeypatch.setattr(api_module, 'Path', FakePath)
    import builtins
    monkeypatch.setattr(builtins, 'open', patched_open)

    mock_logger = MagicMock()
    monkeypatch.setattr(api_module, 'logger', mock_logger)

    result = api_instance._get_video_extensions()

    mock_logger.warning.assert_called_once()
    warning_msg = mock_logger.warning.call_args[0][0]
    assert '_get_video_extensions' in warning_msg
    assert 'DEFAULT_VIDEO_EXTENSIONS' in warning_msg
    assert result == set(api_module.DEFAULT_VIDEO_EXTENSIONS)


# ---------------------------------------------------------------------------
# Logger test 6: _get_player_path — json.load raises JSONDecodeError → logger.warning
# ---------------------------------------------------------------------------
def test_get_player_path_json_error_logs_warning(api_module, api_instance, monkeypatch):
    """_get_player_path の JSON parse 失敗 → logger.warning + '' を返す"""
    import json as _json
    import builtins

    class FakePath:
        def __init__(self, *a):
            pass
        def __truediv__(self, other):
            return self
        def exists(self):
            return True

    original_open = builtins.open

    def patched_open(path, *args, **kwargs):
        if 'config.json' in str(path):
            raise _json.JSONDecodeError("bad json", "", 0)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(api_module, 'Path', FakePath)
    monkeypatch.setattr(builtins, 'open', patched_open)

    mock_logger = MagicMock()
    monkeypatch.setattr(api_module, 'logger', mock_logger)

    result = api_instance._get_player_path()

    mock_logger.warning.assert_called_once()
    warning_msg = mock_logger.warning.call_args[0][0]
    assert '_get_player_path' in warning_msg
    assert 'OS default player' in warning_msg
    assert result == ''


# ---------------------------------------------------------------------------
# Logger test 7: _load_config_extensions — json.load raises JSONDecodeError → logger.warning
# ---------------------------------------------------------------------------
def test_load_config_extensions_json_error_logs_warning(api_module, monkeypatch):
    """_load_config_extensions の JSON parse 失敗 → logger.warning + DEFAULT_VIDEO_EXTENSIONS を返す"""
    import json as _json
    import builtins

    class FakePath:
        def __init__(self, *a):
            pass
        def __truediv__(self, other):
            return self
        def exists(self):
            return True

    original_open = builtins.open

    def patched_open(path, *args, **kwargs):
        if 'config.json' in str(path):
            raise _json.JSONDecodeError("bad json", "", 0)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(api_module, 'Path', FakePath)
    monkeypatch.setattr(builtins, 'open', patched_open)

    mock_logger = MagicMock()
    monkeypatch.setattr(api_module, 'logger', mock_logger)

    result = api_module._load_config_extensions()

    mock_logger.warning.assert_called_once()
    warning_msg = mock_logger.warning.call_args[0][0]
    assert '_load_config_extensions' in warning_msg
    assert 'DEFAULT_VIDEO_EXTENSIONS' in warning_msg
    assert result == set(api_module.DEFAULT_VIDEO_EXTENSIONS)
