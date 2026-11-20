"""Desktop GUI profile lifecycle across platforms."""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "windows"))
import standalone  # noqa: E402


@pytest.fixture(autouse=True)
def data_root(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAVER_DATA_DIR", str(tmp_path))


class Event:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def fire(self):
        for handler in self.handlers:
            handler()


@pytest.fixture
def gui(monkeypatch, tmp_path):
    logger = MagicMock()
    monkeypatch.setattr(standalone, "get_logger", lambda *args: logger)
    window = SimpleNamespace(events=SimpleNamespace(loaded=Event()))
    calls = []
    startup = MagicMock()
    def start(func, win, **kw):
        calls.append((func, win, kw, (tmp_path / "webview2" / ".started").exists()))
        func(win)
    monkeypatch.setattr(standalone.webview, "start", start)
    class EdgeChrome:
        def clear_user_data(self):
            self.original_called = True
    process = MagicMock()
    edge = SimpleNamespace(EdgeChrome=EdgeChrome, _state={"private_mode": True},
                           Convert=SimpleNamespace(ToInt32=lambda value: value),
                           Process=SimpleNamespace(GetProcessById=lambda pid: process))
    monkeypatch.setitem(sys.modules, "webview.platforms.edgechromium", edge)
    return SimpleNamespace(logger=logger, window=window, calls=calls, startup=startup,
                           edge=edge, process=process)


@pytest.mark.parametrize("platform,dispose_fails", [("win32", False), ("win32", True), ("darwin", False)])
def test_windows_gui_keeps_webview2_profile_and_mac_is_untouched(monkeypatch, tmp_path, gui, platform, dispose_fails):
    monkeypatch.setattr(standalone.sys, "platform", platform)
    if platform == "win32":
        profile = tmp_path / "webview2"
        profile.mkdir()
        (profile / "keep.bin").write_text("keep")
    standalone._start_gui(gui.startup, gui.window)
    func, win, kw, marker_at_start = gui.calls[0]
    gui.startup.assert_called_once_with(gui.window)
    if platform == "darwin":
        assert kw == {"icon": standalone.app_icon.icon_path(standalone.APP_DIR)}
        assert not (tmp_path / "webview2").exists()
    else:
        assert kw["gui"] == "edgechromium"
        assert kw["private_mode"] is True
        assert kw["storage_path"] == str(profile)
        assert marker_at_start
        instance = gui.edge.EdgeChrome()
        instance.webview = MagicMock()
        instance.webview.CoreWebView2.BrowserProcessId = 42
        if dispose_fails:
            instance.webview.Dispose.side_effect = RuntimeError("dispose failed")
        instance.clear_user_data()
        assert not hasattr(instance, "original_called")
        instance.webview.Dispose.assert_called_once()
        if dispose_fails:
            gui.logger.warning.assert_called_once()
            gui.process.WaitForExit.assert_not_called()
        else:
            gui.process.WaitForExit.assert_called_once_with(3000)
        gui.window.events.loaded.fire()
        assert not (profile / ".started").exists()
        assert (profile / "keep.bin").exists()


@pytest.mark.parametrize("case", ["stale", "file", "invalid"])
def test_stale_started_marker_wipes_profile_and_unusable_dir_falls_back(monkeypatch, tmp_path, gui, case):
    monkeypatch.setattr(standalone.sys, "platform", "win32")
    profile = tmp_path / "webview2"
    original = gui.edge.EdgeChrome.clear_user_data
    if case in ("stale", "invalid"):
        profile.mkdir()
        (profile / ".started").write_text("" if case == "invalid" else "1")
        (profile / "junk.bin").write_text("junk")
    else:
        profile.write_text("file")
    standalone._start_gui(gui.startup, gui.window)
    func, _, kw, marker_at_start = gui.calls[0]
    if case in ("stale", "invalid"):
        assert not (profile / "junk.bin").exists()
        assert profile.is_dir() and marker_at_start
        assert kw["storage_path"] == str(profile)
        if case == "invalid":
            assert (profile / ".started").read_text() == "2"
        gui.logger.info.assert_called()
    else:
        assert kw["storage_path"] is None and kw["private_mode"] is True
        assert gui.edge.EdgeChrome.clear_user_data is original
        assert func is gui.startup
        gui.logger.warning.assert_called()


def test_missing_edge_class_logs_and_gui_still_starts(monkeypatch, gui):
    monkeypatch.setattr(standalone.sys, "platform", "win32")
    monkeypatch.delitem(sys.modules, "webview.platforms.edgechromium", raising=False)
    standalone._start_gui(gui.startup, gui.window)
    gui.startup.assert_called_once_with(gui.window)
    gui.logger.warning.assert_called()


@pytest.mark.parametrize("case", ["unloaded", "loaded"])
def test_two_unloaded_launches_fall_back_to_temp_folder_for_good(monkeypatch, tmp_path, gui, case):
    monkeypatch.setattr(standalone.sys, "platform", "win32")
    profile = tmp_path / "webview2"
    marker = profile / ".started"
    fallback = tmp_path / "webview2.fallback"
    for attempt in range(1, 6 if case == "unloaded" else 4):
        window = SimpleNamespace(events=SimpleNamespace(loaded=Event()))
        gui.calls.clear()
        standalone._start_gui(gui.startup, window)
        func, _, kw, _ = gui.calls[-1]
        if case == "loaded" or attempt <= 3:
            assert kw["storage_path"] == str(profile)
            assert marker.read_text() == str(attempt if case == "unloaded" else max(1, attempt - 1))
            assert not fallback.exists()
            if attempt > 1 and (case == "unloaded" or attempt > 2):
                gui.logger.info.assert_called()
        else:
            assert kw["storage_path"] is None
            assert func is gui.startup
            assert not profile.exists()
            assert fallback.exists()
            assert not window.events.loaded.handlers
            gui.logger.warning.assert_called()
        if case == "loaded" and attempt == 1:
            window.events.loaded.fire()
