"""Local startup sequencing and page-load ownership."""
import sys
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.parse import urlsplit

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "windows"))
import standalone  # noqa: E402
from core import client_settings  # noqa: E402
from windows import startup_boot  # noqa: E402


@pytest.fixture
def boot_env(monkeypatch):
    events = []
    agent = MagicMock()
    agent.announce.side_effect = lambda: events.append("announce") or True
    agent.start.side_effect = lambda: events.append("agent_start")
    listener = MagicMock()
    listener.wire.side_effect = lambda *a, **k: events.append("wire")
    monkeypatch.setitem(sys.modules, "web.app", SimpleNamespace(app=object()))
    monkeypatch.setitem(sys.modules, "web.lan_listener", SimpleNamespace(lan_listener=listener))
    monkeypatch.setattr(standalone, "find_free_port", lambda *a: 49152)
    monkeypatch.setattr(standalone, "run_server", lambda *a: None)
    monkeypatch.setattr(standalone, "wait_for_server", lambda *a, **k: standalone.PROBE_OK)
    monkeypatch.setattr(standalone, "_notify_if_page_silent", MagicMock(), raising=False)
    monkeypatch.setattr(standalone, "_maybe_autostart_lan_listener", lambda *a: events.append("lan"))
    monkeypatch.setattr(standalone, "_make_cf_agent", lambda *a: agent)
    monkeypatch.setattr(standalone.api, "_set_trusted_origin", lambda origin: events.append(("trusted", origin)))
    monkeypatch.setattr(client_settings, "shell_kind", lambda: "standalone")
    window = MagicMock()
    window.load_url.side_effect = lambda url: events.append(("load_url", url))
    state = startup_boot.BootState("zh_TW", "light", "")
    return SimpleNamespace(events=events, agent=agent, window=window, state=state,
                           logger=MagicMock(), box={"agent": None}, quit=MagicMock())


def _args(e):
    return (e.window, e.state, e.logger, False, object(), True, e.box, e.quit)


@pytest.mark.parametrize("case,expected", [("timeout", ("timeout", "")), ("died", ("died", "")),
    ("no_port", ("no_port", "msg")), ("unexpected", ("died", "")), ("cancelled", None)])
def test_boot_failures_become_error_state_never_dialog_or_navigation(monkeypatch, boot_env, case, expected):
    e = boot_env
    monkeypatch.setattr(standalone, "show_error", MagicMock(side_effect=AssertionError("dialog")))
    monkeypatch.setattr(standalone, "_win_message_box", MagicMock(side_effect=AssertionError("dialog")))
    monkeypatch.setattr(standalone, "wait_for_server", MagicMock(return_value={"timeout": "timeout", "died": "thread_died", "cancelled": "cancelled"}.get(case, "ok")))
    if case == "no_port":
        monkeypatch.setattr(standalone, "find_free_port", MagicMock(side_effect=RuntimeError("msg")))
    if case == "unexpected":
        monkeypatch.setattr(standalone, "_make_cf_agent", MagicMock(side_effect=ValueError("bad")))
    standalone._local_boot_worker(*_args(e))
    assert e.state.error == expected
    if expected:
        assert isinstance(e.state.error[1], str)
    e.window.load_url.assert_not_called()
    standalone.show_error.assert_not_called()
    standalone._win_message_box.assert_not_called()
    assert standalone._notify_if_page_silent.call_count == (0 if case == "cancelled" else 1)


@pytest.mark.parametrize("case", ["win32", "darwin", "polled", "quitting"])
def test_silent_page_falls_back_to_native_notice_then_quits(monkeypatch, case):
    state = startup_boot.BootState("zh_TW", "light", "/tmp/debug.log")
    state.set_error("died")
    if case == "polled": state.get_state()
    if case == "quitting": state.request_quit()
    monkeypatch.setattr(standalone.sys, "platform", "darwin" if case == "darwin" else "win32")
    msgbox, run, quit_mock = MagicMock(), MagicMock(), MagicMock()
    monkeypatch.setattr(standalone, "_win_message_box", msgbox)
    monkeypatch.setattr(standalone, "subprocess", subprocess, raising=False)
    monkeypatch.setattr(subprocess, "run", run)
    t = [0.0]
    standalone._notify_if_page_silent(state, quit_mock, MagicMock(), timeout=10,
        clock=lambda: t[0], sleep=lambda s: t.__setitem__(0, t[0] + s))
    if case == "win32":
        msgbox.assert_called_once()
        assert startup_boot.startup_texts("zh_TW")["message_died"] in msgbox.call_args.args[0]
        assert "/tmp/debug.log" in msgbox.call_args.args[0]
        run.assert_not_called()
    elif case == "darwin":
        run.assert_called_once()
        argv = run.call_args.args[0]
        assert argv[0] == "osascript" and "/tmp/debug.log" in argv[-1]
        assert startup_boot.startup_texts("zh_TW")["message_died"] in argv[-1]
        assert all(argv[-1] not in argv[i+1] for i, arg in enumerate(argv[:-1]) if arg == "-e")
        msgbox.assert_not_called()
    else:
        msgbox.assert_not_called(); run.assert_not_called()
    assert quit_mock.call_count == (1 if case in ("win32", "darwin") else 0)


@pytest.mark.parametrize("announced", [True, False])
def test_worker_navigates_home_only_after_probe_and_announce(monkeypatch, boot_env, announced):
    e = boot_env
    probe_entered, probe_release = threading.Event(), threading.Event()
    announce_entered, announce_release = threading.Event(), threading.Event()

    def probe(*args, **kwargs):
        probe_entered.set()
        assert probe_release.wait(3)
        e.events.append("probe")
        return standalone.PROBE_OK

    def announce():
        announce_entered.set()
        assert announce_release.wait(3)
        e.events.append("announce")
        return announced

    monkeypatch.setattr(standalone, "wait_for_server", probe)
    e.agent.announce.side_effect = announce
    thread = standalone._start_boot_worker(standalone._local_boot_worker, *_args(e))
    try:
        assert probe_entered.wait(3)
        e.window.load_url.assert_not_called()
        probe_release.set()
        assert announce_entered.wait(3)
        e.window.load_url.assert_not_called()
    finally:
        probe_release.set()
        announce_release.set()
        thread.join(3)
    assert not thread.is_alive()
    expected = client_settings.shell_entry_url("http://127.0.0.1:49152", "standalone")
    e.window.load_url.assert_called_once_with(expected)
    trusted = ("trusted", client_settings.server_origin("http://127.0.0.1:49152"))
    assert e.events.index("probe") < e.events.index("wire") < e.events.index("lan")
    assert e.events.index("lan") < e.events.index("announce") < e.events.index(trusted)
    assert e.events.index(trusted) < e.events.index(("load_url", expected))
    assert urlsplit(expected).netloc == urlsplit(trusted[1]).netloc


@pytest.mark.parametrize("case", ["timeout", "died", "port", "quit"])
def test_worker_never_navigates_when_backend_not_ready_or_user_quit(monkeypatch, boot_env, case):
    e = boot_env
    probe = MagicMock(return_value={"timeout": standalone.health_probe.PROBE_TIMEOUT,
                                   "died": standalone.health_probe.PROBE_THREAD_DIED}.get(case, standalone.PROBE_OK))
    monkeypatch.setattr(standalone, "wait_for_server", probe)
    if case == "port":
        monkeypatch.setattr(standalone, "find_free_port", MagicMock(side_effect=RuntimeError("no port")))
    if case == "quit":
        assert e.state.request_quit()
    standalone._local_boot_worker(*_args(e))
    e.window.load_url.assert_not_called()


@pytest.mark.parametrize("kind,gen,keys,phase", [
    ("startup", 2, {"startup_screen_shown"}, "starting"),
    ("startup", 1, set(), "starting"),
    ("server", 2, {"first_page_loaded"}, "ready"),
    ("offline", 2, {"first_page_loaded"}, "ready"),
    ("server", 1, set(), "starting"),
])
def test_page_loaded_marks_follow_kind_and_generation(monkeypatch, kind, gen, keys, phase):
    marks = []
    state = startup_boot.BootState("zh_TW", "light", "")
    monkeypatch.setattr(standalone.pywebview_api.api, "_nav_gen", 2)
    monkeypatch.setattr(standalone.startup_trace, "mark", marks.append)
    standalone._make_page_loaded_subscriber(state)(kind, object(), gen)
    assert set(marks) == keys
    assert state.phase == phase


def _main_env(monkeypatch, tmp_path):
    events = []
    for slot in ("_page_loaded_subscriber", "_loaded_hook", "_restart_handler",
                 "_offline_text_provider", "_startup_state_provider", "_startup_log_opener", "_startup_quit_handler"):
        monkeypatch.setattr(standalone.pywebview_api, slot, None)
    monkeypatch.setenv("OPENAVER_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(standalone, "setup_logging", lambda **k: None)
    monkeypatch.setattr(standalone, "get_logger", lambda *a: MagicMock())
    monkeypatch.setattr(standalone, "bootstrap_data_layout", lambda: None)
    monkeypatch.setattr(standalone, "_ensure_webview2_runtime", lambda *a: None)
    monkeypatch.setattr(standalone.restart, "wait_for_parent_exit", lambda: None)
    monkeypatch.setattr(standalone.restart, "spawn_if_requested", lambda **k: None)
    monkeypatch.setattr(standalone.shell_boot, "install_webview_token_filter", lambda: None)
    monkeypatch.setattr(client_settings, "mode", lambda: "local")
    monkeypatch.setattr(standalone, "current_settings", lambda: None)
    monkeypatch.setattr(standalone.cf_windows, "cf_shell_supported", lambda: True)
    monkeypatch.setattr(standalone.cf_windows, "build_cf_windows", lambda *a: events.append("build") or standalone.cf_windows.CfWindowSet())
    monkeypatch.setattr(standalone.cf_windows, "attach_close_guards", lambda *a: None)
    monkeypatch.setattr(standalone, "_setup_windows_lifecycle", lambda *a: None)
    monkeypatch.setattr(standalone, "_attach_window_state", lambda *a: None)
    monkeypatch.setattr(standalone, "_arm_exit_backstop", MagicMock(), raising=False)
    monkeypatch.setitem(sys.modules, "window_state", SimpleNamespace(load_state=lambda: {"width": 800, "height": 600, "x": None, "y": None, "maximized": False}))
    window = MagicMock()
    monkeypatch.setattr(standalone.webview, "create_window", lambda title, url, **kw: events.append(("create", url, kw)) or window)
    monkeypatch.setattr(standalone.api, "_expect_startup", lambda: events.append("expect"))
    monkeypatch.setattr(standalone.api, "_set_trusted_origin", lambda origin: events.append(("trusted", origin)))
    monkeypatch.setattr(standalone.pywebview_api, "_startup_state_provider", None)
    return events, window


class _Collector:
    def __init__(self): self.handlers = []
    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self


def _closing_env(monkeypatch, tmp_path):
    _, window = _main_env(monkeypatch, tmp_path)
    window.events.closing = _Collector()
    states = []
    base = standalone.startup_boot.BootState
    class State(base):
        def __init__(self, *args):
            super().__init__(*args)
            states.append(self)
    monkeypatch.setattr(standalone.startup_boot, "BootState", State)
    lifecycle = standalone.DesktopLifecycle(window, {}, {}, lambda *a: None, read_close_action=lambda: "tray")
    lifecycle.prompt = MagicMock(side_effect=AssertionError("prompt"))
    tray = MagicMock(); tray.start.return_value = True
    lifecycle.attach_tray(tray); lifecycle.start_tray()
    return window, states, lifecycle


@pytest.mark.parametrize("platform,phase", [("win32", "starting"), ("win32", "error"), ("darwin", "starting")])
def test_x_during_startup_quits_even_when_close_action_is_tray(monkeypatch, tmp_path, platform, phase):
    window, states, lifecycle = _closing_env(monkeypatch, tmp_path)
    jl, javten = MagicMock(), MagicMock()
    monkeypatch.setattr(standalone, "_setup_windows_lifecycle", lambda *a: lifecycle if platform == "win32" else None)
    monkeypatch.setattr(standalone.cf_windows, "build_cf_windows", lambda *a: standalone.cf_windows.CfWindowSet(jl_win=jl, javten_win=javten))
    def gui(startup, win):
        if phase == "error": states[0].set_error("died")
        assert window.events.closing.handlers[0]() is None
        window.hide.assert_not_called(); lifecycle.prompt.assert_not_called()
        if platform == "win32": assert lifecycle.quitting
        else:
            jl.destroy.assert_called_once(); javten.destroy.assert_called_once()
        standalone._arm_exit_backstop.assert_called()
    monkeypatch.setattr(standalone, "_start_gui", gui)
    standalone.main()


@pytest.mark.parametrize("ready_first", [True, False])
def test_ready_and_close_race_has_exactly_one_winner(monkeypatch, tmp_path, ready_first):
    window, states, lifecycle = _closing_env(monkeypatch, tmp_path)
    monkeypatch.setattr(standalone, "_setup_windows_lifecycle", lambda *a: lifecycle)
    def gui(startup, win):
        state = states[0]
        if ready_first: assert state.mark_ready()
        window.events.closing.handlers[0]()
        if ready_first:
            window.hide.assert_called_once(); assert not lifecycle.quitting
        else:
            assert not state.mark_ready()
            monkeypatch.setattr(standalone.pywebview_api.api, "_nav_gen", 4)
            standalone._make_page_loaded_subscriber(state)("server", object(), 4)
            assert state.phase == "starting" and lifecycle.quitting
    monkeypatch.setattr(standalone, "_start_gui", gui)
    standalone.main()


@pytest.mark.parametrize("platform", ["win32", "darwin"])
def test_error_screen_buttons_are_wired_open_log_folder_and_quit(monkeypatch, tmp_path, platform):
    arm_backstop = standalone._arm_exit_backstop
    _, window = _main_env(monkeypatch, tmp_path)
    lifecycle = MagicMock() if platform == "win32" else None
    monkeypatch.setattr(standalone, "_setup_windows_lifecycle", lambda *a: lifecycle)
    monkeypatch.setattr(standalone.sys, "platform", platform)
    path = tmp_path / "OpenAver" / "logs" / "debug.log"
    monkeypatch.setattr(standalone.health_probe, "_debug_log_hint", lambda: str(path))
    start, run = MagicMock(), MagicMock()
    monkeypatch.setattr(standalone.os, "startfile", start, raising=False)
    monkeypatch.setattr(standalone, "subprocess", subprocess, raising=False)
    monkeypatch.setattr(subprocess, "run", run)
    w1, w2 = MagicMock(), MagicMock()
    monkeypatch.setattr(standalone.webview, "windows", [w1, w2])
    def gui(startup, win):
        opener = standalone.pywebview_api._startup_log_opener
        quit_handler = standalone.pywebview_api._startup_quit_handler
        opener()
        if platform == "win32": start.assert_called_once_with(str(path.parent))
        else: run.assert_called_once_with(["open", str(path.parent)], check=True)
        quit_handler()
        standalone._arm_exit_backstop.assert_called()
        if lifecycle: lifecycle.handle_tray_command.assert_called_once_with(standalone.CMD_QUIT)
        else: w1.destroy.assert_called_once(); w2.destroy.assert_called_once()
    monkeypatch.setattr(standalone, "_start_gui", gui)
    standalone.main()
    start.reset_mock(); run.reset_mock()
    monkeypatch.setattr(standalone.health_probe, "_debug_log_hint", lambda: "OpenAver 的 logs 資料夾")
    def bad_path_gui(startup, win):
        with pytest.raises(ValueError):
            standalone.pywebview_api._startup_log_opener()
        start.assert_not_called(); run.assert_not_called()
    monkeypatch.setattr(standalone, "_start_gui", bad_path_gui)
    standalone.main()
    exit_fn = MagicMock()
    thread = arm_backstop(delay=0, exit_fn=exit_fn)
    thread.join(2)
    exit_fn.assert_called_once_with(0)


def test_gui_callback_returns_at_once_and_worker_is_daemon(monkeypatch, tmp_path):
    _main_env(monkeypatch, tmp_path)
    entered, release = threading.Event(), threading.Event()
    def worker(*args):
        entered.set()
        assert release.wait(3)
    monkeypatch.setattr(standalone, "_local_boot_worker", worker, raising=False)
    def gui(startup, win):
        startup(win)
        assert entered.wait(3)
        threads = [t for t in threading.enumerate() if t.name == "oa-boot-worker"]
        assert len(threads) == 1 and threads[0].daemon
        release.set()
        threads[0].join(3)
        assert not threads[0].is_alive()
    monkeypatch.setattr(standalone, "_start_gui", gui)
    try:
        standalone.main()
    finally:
        release.set()
        for thread in threading.enumerate():
            if thread.name == "oa-boot-worker":
                thread.join(3)


def test_main_opens_startup_window_before_backend_and_cf_windows_before_gui(monkeypatch, tmp_path):
    events, window = _main_env(monkeypatch, tmp_path)
    monkeypatch.setattr(standalone, "_start_boot_worker", lambda *a: events.append("worker"), raising=False)
    monkeypatch.setattr(standalone, "find_free_port", lambda *a: events.append("port"))
    monkeypatch.setattr(standalone, "run_server", lambda *a: events.append("server"))
    def gui(startup, win):
        events.append("gui")
        assert standalone.pywebview_api._startup_state_provider is not None
        startup(win)
    monkeypatch.setattr(standalone, "_start_gui", gui)
    standalone.main()
    create = next(e for e in events if isinstance(e, tuple) and e[0] == "create")
    assert create[1] == standalone.STARTUP_PAGE
    assert create[2]["js_api"] is None
    assert create[2]["background_color"] == startup_boot.background_color(client_settings.shell_theme())
    assert events.index("expect") < events.index(create) < events.index("build") < events.index("gui")
    assert not any(isinstance(e, tuple) and e[0] == "trusted" for e in events[:events.index("gui")])
    assert not {"port", "server", "announce"} & set(e for e in events if isinstance(e, str))


def test_local_gui_return_arms_exit_backstop_after_cleanup(monkeypatch, tmp_path):
    events, _ = _main_env(monkeypatch, tmp_path)
    monkeypatch.setattr(standalone, "_start_gui", lambda *a: events.append("gui_return"))
    monkeypatch.setattr(standalone, "_shutdown_and_maybe_restart", lambda *a: events.append("cleanup"))
    arm = MagicMock(side_effect=lambda: events.append("arm"))
    monkeypatch.setattr(standalone, "_arm_exit_backstop", arm)
    standalone.main()
    arm.assert_called_once_with()
    assert events.index("gui_return") < events.index("cleanup") < events.index("arm")


def test_main_window_urls_share_pywebview_local_server_root(monkeypatch, tmp_path):
    import webview.http as webview_http

    build = standalone.cf_windows.build_cf_windows
    events, _ = _main_env(monkeypatch, tmp_path)
    monkeypatch.setattr(standalone.cf_windows, "build_cf_windows", build)
    monkeypatch.setattr(standalone.cf_windows, "window_titles", lambda: ("JL", "javten"))
    monkeypatch.setattr(standalone, "_start_gui", lambda *a: None)
    monkeypatch.setattr(webview_http, "_get_random_port", lambda: 12345)
    monkeypatch.setattr(webview_http, "threading", SimpleNamespace(
        Thread=lambda **kw: SimpleNamespace(start=lambda: None)))
    for proxy in (None, object()):
        events.clear()
        monkeypatch.setattr(standalone.cf_windows, "_prepare_cf_window_proxy",
                            lambda *a, proxy=proxy: (proxy, None, True))
        standalone.main()
        creates = [e for e in events if isinstance(e, tuple) and e[0] == "create"]
        assert len(creates) == 3
        assert all(e[2].get("hidden") is True for e in creates[1:])
        urls = [e[1] for e in creates]
        address, common_path, server = webview_http.BottleServer.start_server(urls, None)
        assert address == server.address
        assert Path(common_path) == Path(standalone.STARTUP_PAGE).parent
        assert Path(server.root_path) == Path(standalone.pywebview_api.OFFLINE_PAGE).parent
