# [lint-guard: pytest-justified]  啟動流程呼叫序列（client 分岔／重啟順序／接縫註冊）＋ launcher AST 順序
"""TASK-168b-T5b: standalone／launcher 把 shell_boot 與 restart 接進啟動流程。

以記錄呼叫序列的假件驗證順序與零呼叫；不比行號、不碰真網路、不 patch 全域 os.path.exists。
"""
import ast
import sys
import threading
import types
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

from core import client_connect, client_settings
from core.client_connect import Preflight
from core.proxy_policy import ProxySettings

REPO_ROOT = Path(__file__).resolve().parents[2]
WINDOWS_DIR = REPO_ROOT / "windows"
if str(WINDOWS_DIR) not in sys.path:
    sys.path.insert(0, str(WINDOWS_DIR))

import standalone  # noqa: E402
from tray import CMD_QUIT  # noqa: E402
from windows.cf_windows import CfWindowSet  # noqa: E402

SERVER = "http://192.168.1.180:8000"
TOKEN = "TKN-SENTINEL-T5B"
REAL_START_BOOT_WORKER = standalone._start_boot_worker


class _FakeEvent:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, fn):
        self.handlers.append(fn)
        return self

    def fire(self):
        for fn in list(self.handlers):
            fn()


class _FakeWindow:
    def __init__(self, events):
        self._ev = events
        self.events = types.SimpleNamespace(closing=_FakeEvent(), loaded=_FakeEvent())
        self.exposed = None
        self.maximize_error = None

    def expose(self, *fns):
        self.exposed = fns

    def destroy(self):
        self._ev.append("window.destroy")

    def maximize(self):
        self._ev.append("maximize")
        if self.maximize_error:
            raise self.maximize_error

    def load_url(self, url):
        self._ev.append(("load_url", url))

    def set_title(self, title):
        self._ev.append(("set_title", title))

    def hide(self):
        self._ev.append("hide")


class _FakeLifecycle:
    def __init__(self, events):
        self._ev = events
        self.on_window_closing = lambda *a: None
        self.quitting = False

    def handle_tray_command(self, cmd):
        self._ev.append(("handle_tray_command", cmd))

    def shutdown_after_loop(self):
        self._ev.append("shutdown_after_loop")

    def replace_state(self, live):
        self._ev.append(("replace_state", live))

    def start_tray(self):
        self._ev.append("start_tray")

    def register_cf_windows(self, mapping):
        self._ev.append(("register_cf_windows", sorted(mapping)))

    def quit_now(self):
        self.quitting = True


class _ClosableWindow:
    """destroy() 會依序呼叫已掛的 closing handler；任何一個回 False 就取消關閉（pywebview 語意）。"""

    def __init__(self, name, events, windows):
        self.name, self._ev, self._windows = name, events, windows
        self.events = types.SimpleNamespace(closing=_FakeEvent(), loaded=_FakeEvent())
        self.hidden = False

    def hide(self):
        self.hidden = True
        self._ev.append(f"{self.name}.hide")

    def expose(self, *fns):
        pass

    def load_url(self, url):
        self._ev.append(("load_url", url))

    def set_title(self, title):
        self._ev.append(("set_title", title))

    def destroy(self):
        for fn in list(self.events.closing.handlers):
            if fn() is False:
                self._ev.append(f"{self.name}.close_cancelled")
                return
        self._ev.append(f"{self.name}.destroy")
        if self in self._windows:
            self._windows.remove(self)


class _FakeAgent:
    """CfShellAgent 假件：只記呼叫；start 不開執行緒。"""

    def __init__(self, bag, events, origin, token, windows, **kw):
        self.origin, self.token, self.windows, self.kw = origin, token, windows, kw
        self._ev = events
        bag.agents.append(self)

    def announce(self):
        self._ev.append("cf.announce")
        return True

    def start(self):
        self._ev.append("cf.start")

    def stop(self):
        self._ev.append("cf.stop")

    def refresh_now(self):
        self._ev.append("cf.refresh_now")
        return True

    def public_status(self):
        return {"state": "ready", "reason": None, "proxy_note": None, "sites": ["javlibrary"]}


SAVED = {"width": 1000, "height": 700, "x": None, "y": None, "maximized": False}


@pytest.fixture
def env(monkeypatch, tmp_path):
    """共用假件：事件序列 events、窗口、lifecycle、api 接縫旗標；結束後還原全域狀態。"""
    monkeypatch.setenv("OPENAVER_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(standalone.api, "_page_kind", "startup")
    events = []
    win = _FakeWindow(events)
    lifecycle = _FakeLifecycle(events)
    e = types.SimpleNamespace(events=events, win=win, lifecycle=lifecycle, create_calls=[],
                              marks=[], logger=MagicMock())

    monkeypatch.setattr(standalone.pywebview_api, "_restart_handler", None)
    monkeypatch.setattr(standalone.pywebview_api, "_offline_text_provider", None)
    monkeypatch.setattr(standalone.pywebview_api, "_loaded_hook", None)
    monkeypatch.setattr(standalone.pywebview_api, "_page_loaded_subscriber", None, raising=False)
    monkeypatch.setattr(standalone.pywebview_api, "_cf_retry_handler", None)
    for name in ("_startup_state_provider", "_startup_log_opener", "_startup_quit_handler"):
        monkeypatch.setattr(standalone.pywebview_api, name, None)
    monkeypatch.setattr(standalone.startup_boot, "system_prefers_dark", lambda: False, raising=False)
    monkeypatch.setattr(standalone, "_start_boot_worker", lambda worker, *a: worker(*a))
    monkeypatch.setattr(standalone, "_arm_exit_backstop", MagicMock())
    monkeypatch.setattr(standalone, "_notify_if_page_silent", MagicMock())
    monkeypatch.setattr(standalone, "show_error", Mock(side_effect=AssertionError("native notice")))
    monkeypatch.setattr(standalone, "_win_message_box", Mock(side_effect=AssertionError("native notice")))
    e.start_check = Mock(side_effect=lambda: events.append("start_check"))
    monkeypatch.setattr(standalone.update_notice, "start_background_check", e.start_check)
    monkeypatch.setattr(standalone.restart, "_state", {"requested": False, "spawned": False})

    monkeypatch.setattr(standalone.api, "_set_trusted_origin",
                        lambda o: events.append(("trusted", o)))
    monkeypatch.setattr(standalone.api, "_set_offline_state",
                        lambda r, u: events.append(("offline_state", r, u)))
    monkeypatch.setattr(standalone.api, "_expect_offline",
                        lambda: events.append("expect_offline"))

    def fake_create_window(title, url, **kw):
        e.create_calls.append((title, url, kw))
        events.append(("create_window", url))
        return win

    monkeypatch.setattr(standalone.webview, "create_window", fake_create_window)
    monkeypatch.setattr(standalone, "_setup_windows_lifecycle", lambda *a: lifecycle)
    monkeypatch.setattr(standalone.startup_trace, "mark",
                        lambda k, *a, **kw: (e.marks.append(k), events.append(f"mark:{k}")))

    # CF 殼接線假件（168d-T4）：全部可記錄呼叫；agent.start 不開執行緒
    cf = types.SimpleNamespace(fetch_calls=[], build_calls=[], agents=[], build_result=None,
                               fetch_result=None)
    e.cf = cf

    def fake_fetch(url, token):
        cf.fetch_calls.append((url, token))
        events.append("cf.fetch")
        return cf.fetch_result or {"ok": True, "reason": None, "settings": ProxySettings(url="", scope="dmm")}

    def fake_build(logger, settings, local_direct=False):
        cf.build_calls.append((settings, local_direct))
        events.append("cf.build")
        return cf.build_result if cf.build_result is not None else CfWindowSet(local_direct=local_direct)

    monkeypatch.setattr(client_connect, "fetch_proxy_settings", fake_fetch)
    monkeypatch.setattr(standalone.cf_windows, "build_cf_windows", fake_build)
    monkeypatch.setattr(standalone.cf_windows, "cf_shell_supported", lambda: True)
    monkeypatch.setattr(standalone.cf_shell, "CfShellAgent",
                        lambda origin, token, windows, **kw: _FakeAgent(cf, events, origin, token, windows, **kw))
    monkeypatch.setattr(standalone.pywebview_api, "_cf_status_provider", None)

    fake_ws = types.SimpleNamespace(
        load_state=lambda: dict(SAVED),
        attach=lambda w, saved: {"maximized": bool(saved["maximized"])},
    )
    monkeypatch.setitem(sys.modules, "window_state", fake_ws)
    monkeypatch.setattr(standalone, "bind_events", lambda w: events.append("bind_events"))

    spawn = Mock(side_effect=lambda **kw: events.append("spawn") or False)
    monkeypatch.setattr(standalone.restart, "spawn_if_requested", spawn)
    e.spawn = spawn

    boom = Mock(side_effect=AssertionError("client mode must not start local server"))
    for name in ("find_free_port", "run_server", "_maybe_autostart_lan_listener"):
        monkeypatch.setattr(standalone, name, boom)
    real_start = threading.Thread.start

    def guarded_start(self):   # 只放行重啟的延遲退出執行緒；其餘仍禁
        if self.name in (standalone.restart.QUIT_THREAD_NAME, "oa-boot-worker", "oa-client-prefetch"):
            return real_start(self)
        return boom()

    monkeypatch.setattr(standalone.threading.Thread, "start", guarded_start)
    monkeypatch.setattr(standalone.restart, "QUIT_DELAY", 0)
    monkeypatch.setattr(standalone.webview, "windows", [win], raising=False)
    e.boom = boom
    return e


def _join_quit():
    """等重啟的延遲退出執行緒做完（它已在 request_restart 返回前啟動）。"""
    for th in threading.enumerate():
        if th.name == standalone.restart.QUIT_THREAD_NAME:
            th.join(5)


def _client_json():
    client_settings.save_client_settings({"version": 1, "server": {"url": SERVER, "token": TOKEN}})


def _fake_start(env, in_loop=None):
    def start(startup, window, **kw):
        env.events.append("gui_loop_enter")
        startup(window)
        if in_loop:
            in_loop()
        env.events.append("gui_loop_exit")
    return start


def _ok_preflight(monkeypatch):
    monkeypatch.setattr(client_connect, "preflight", lambda url, token: Preflight("ok", None, {}))


@pytest.mark.parametrize("offline", [False, True])
def test_client_prefetch_starts_before_gui_loop_and_worker_reuses_its_result(monkeypatch, env, offline):
    _client_json()
    monkeypatch.setattr(client_connect, "preflight", lambda *a: Preflight(
        "offline" if offline else "ok", "unreachable" if offline else None, {}))
    entered = threading.Event()
    resolves, fetches = [], []
    real_resolve = standalone.shell_boot.resolve_boot
    real_fetch = standalone.cf_windows.fetch_client_cf

    def resolve(*args):
        resolves.append(threading.current_thread().name)
        entered.set()
        return real_resolve(*args)

    def fetch(*args):
        fetches.append(threading.current_thread().name)
        return real_fetch(*args)

    def start(startup, window, **kw):
        assert entered.wait(2)
        startup(window)

    monkeypatch.setattr(standalone.shell_boot, "resolve_boot", resolve)
    monkeypatch.setattr(standalone.cf_windows, "fetch_client_cf", fetch)
    monkeypatch.setattr(standalone.webview, "start", start)
    standalone._run_client_mode(env.logger)
    assert resolves == ["oa-client-prefetch"]
    assert fetches == ([] if offline else ["oa-client-prefetch"])
    loads = [e for e in env.events if isinstance(e, tuple) and e[0] == "load_url"]
    assert len(loads) == 1
    if offline:
        assert loads[0][1] == standalone.shell_boot.OFFLINE_PAGE


@pytest.mark.parametrize("case", ["raises", "stalls"])
def test_client_worker_falls_back_to_live_preflight_when_prefetch_fails_or_stalls(monkeypatch, env, case):
    _client_json()
    _ok_preflight(monkeypatch)
    gate = threading.Event()
    calls = []
    real_resolve = standalone.shell_boot.resolve_boot

    def resolve(*args):
        calls.append(threading.current_thread().name)
        if len(calls) == 1:
            if case == "raises":
                raise RuntimeError("prefetch failed")
            gate.wait(3)
        return real_resolve(*args)

    monkeypatch.setattr(standalone.shell_boot, "resolve_boot", resolve)
    if case == "stalls":
        monkeypatch.setattr(standalone, "CLIENT_PREFETCH_WAIT_S", 0.05)
    monkeypatch.setattr(standalone.webview, "start", _fake_start(env))
    try:
        standalone._run_client_mode(env.logger)
        assert len(calls) == 2
        local_origin = f"http://{standalone.CLIENT_HOST}:{standalone.PORT}"
        url = client_settings.shell_entry_url(local_origin, client_settings.shell_kind(), token=TOKEN)
        loads = [e for e in env.events if isinstance(e, tuple) and e[0] == "load_url"]
        assert loads == [("load_url", url)]
        assert env.events.index(("trusted", SERVER)) < env.events.index(loads[0])
        assert len(env.cf.fetch_calls) == 1
        assert standalone.pywebview_api._startup_state_provider.__self__.error is None
        assert env.logger.exception.call_count == 0
    finally:
        gate.set()
        for thread in threading.enumerate():
            if thread.name == "oa-client-prefetch":
                thread.join(3)
                if thread.is_alive():
                    pytest.fail("prefetch thread did not finish")


def test_client_worker_holds_navigation_until_startup_page_is_up(monkeypatch, env):
    _client_json()
    _ok_preflight(monkeypatch)
    monkeypatch.setattr(standalone.api, "_page_kind", "pending")
    monkeypatch.setattr(standalone, "_start_boot_worker", REAL_START_BOOT_WORKER)
    def in_loop():
        worker = next(t for t in threading.enumerate() if t.name == "oa-boot-worker")
        try:
            worker.join(0.2)
            assert not any(isinstance(e, tuple) and e[0] == "load_url" for e in env.events)
        finally:
            monkeypatch.setattr(standalone.api, "_page_kind", "startup")
            worker.join(3)
        assert not worker.is_alive()
        assert sum(isinstance(e, tuple) and e[0] == "load_url" for e in env.events) == 1
    monkeypatch.setattr(standalone.webview, "start", _fake_start(env, in_loop))
    standalone._run_client_mode(env.logger)


def test_client_gui_return_arms_exit_backstop_after_cleanup(monkeypatch, env):
    _client_json()
    _ok_preflight(monkeypatch)
    arm = MagicMock(side_effect=lambda: env.events.append("arm"))
    monkeypatch.setattr(standalone, "_arm_exit_backstop", arm)
    monkeypatch.setattr(standalone.webview, "start", _fake_start(env))
    standalone._run_client_mode(env.logger)
    arm.assert_called_once_with()
    assert env.events.index("gui_loop_exit") < env.events.index("cf.stop") < env.events.index("spawn") < env.events.index("arm")


def test_client_window_opens_before_preflight_and_gui_callback_returns(monkeypatch, env):
    _client_json()
    entered, release, done = threading.Event(), threading.Event(), threading.Event()
    threads = []

    def resolve(*args):
        env.events.append("resolve_entered")
        entered.set()
        release.wait(3)
        done.set()
        return standalone.shell_boot.BootTarget("client", SERVER, "OpenAver", None)

    def start_worker(worker):
        threads.append(REAL_START_BOOT_WORKER(worker))

    monkeypatch.setattr(standalone.shell_boot, "resolve_boot", resolve)
    monkeypatch.setattr(standalone, "_start_boot_worker", start_worker)

    def in_loop():
        try:
            assert entered.wait(3)
            assert not done.is_set()
            assert not any(isinstance(e, tuple) and e[0] == "load_url" for e in env.events)
            assert threads[0].daemon is True
        finally:
            release.set()
            for thread in threads:
                thread.join(3)

    monkeypatch.setattr(standalone.webview, "start", _fake_start(env, in_loop))
    standalone._run_client_mode(env.logger)
    assert env.events.index(("create_window", standalone.STARTUP_PAGE)) < env.events.index("resolve_entered")
    assert len([e for e in env.events if isinstance(e, tuple) and e[0] == "load_url"]) == 1


@pytest.mark.parametrize("offline", [False, True])
def test_client_trust_and_offline_state_set_before_navigation(monkeypatch, env, offline):
    _client_json()
    monkeypatch.setattr(client_connect, "preflight", lambda *a: Preflight(
        "offline" if offline else "ok", "unreachable" if offline else None, {}))
    monkeypatch.setattr(standalone.webview, "start", _fake_start(env))
    standalone._run_client_mode(env.logger)
    if offline:
        state = ("offline_state", "unreachable", SERVER)
        assert TOKEN not in str(state)
        assert env.events.index(state) < env.events.index("expect_offline") < env.events.index(
            ("load_url", standalone.shell_boot.OFFLINE_PAGE))
        assert not any(isinstance(e, tuple) and e[0] == "trusted" for e in env.events)
        env.boom.assert_not_called()
    else:
        local_origin = f"http://{standalone.CLIENT_HOST}:{standalone.PORT}"
        url = client_settings.shell_entry_url(local_origin, client_settings.shell_kind(), token=TOKEN)
        assert env.events.index(("trusted", SERVER)) < env.events.index(("load_url", url))
        assert ("set_title", "OpenAver — 192.168.1.180") in env.events


@pytest.mark.parametrize("case", ["normal", "before_controller", "during_build"])
def test_client_cf_windows_registered_and_destroyed_when_quit_interleaves(monkeypatch, env, case):
    _client_json()
    _ok_preflight(monkeypatch)
    main, jl, javten, wins = _closable_cf(env, monkeypatch)
    lifecycle = standalone.DesktopLifecycle(main, {}, {}, lambda *a: None, read_close_action=lambda: "tray")
    monkeypatch.setattr(standalone, "_setup_windows_lifecycle", lambda *a: None if case == "during_build" else lifecycle)
    if case == "before_controller":
        monkeypatch.setattr(standalone, "_start_boot_worker", lambda worker, *a: (main.events.closing.handlers[0](), worker(*a)))
    if case == "during_build":
        original = standalone.cf_windows.build_cf_windows
        def build(*a, **kw):
            result = original(*a, **kw)
            main.events.closing.handlers[0]()
            return result
        monkeypatch.setattr(standalone.cf_windows, "build_cf_windows", build)

    def in_loop():
        if case == "normal":
            assert set(lifecycle.cf_windows.values()) == {jl, javten}
            jl.destroy()
            assert jl.hidden and jl in wins
        else:
            assert jl not in wins and javten not in wins
            assert not lifecycle.cf_windows
            assert not any(isinstance(e, tuple) and e[0] == "load_url" for e in env.events)
            assert standalone.pywebview_api._startup_state_provider.__self__.error is None
    monkeypatch.setattr(standalone.webview, "start", _fake_start(env, in_loop))
    standalone._run_client_mode(env.logger)


@pytest.mark.parametrize("case", ["starting", "ready", "darwin"])
def test_client_x_during_startup_quits_but_after_home_follows_close_action(monkeypatch, env, case):
    _client_json()
    _ok_preflight(monkeypatch)
    lifecycle = standalone.DesktopLifecycle(env.win, {}, {}, lambda *a: None, read_close_action=lambda: "tray")
    tray = MagicMock()
    tray.start.return_value = True
    lifecycle.attach_tray(tray)
    lifecycle.start_tray()
    lifecycle.prompt = MagicMock(side_effect=AssertionError("prompt"))
    env.win.hide = MagicMock()
    monkeypatch.setattr(standalone, "_setup_windows_lifecycle", lambda *a: None if case == "darwin" else lifecycle)
    def in_loop():
        if case == "ready":
            monkeypatch.setattr(standalone.pywebview_api.api, "_nav_gen", 4)
            standalone.pywebview_api._page_loaded_subscriber("server", object(), 4)
        env.win.events.closing.handlers[0]()
        if case == "ready":
            env.win.hide.assert_called_once()
            assert not lifecycle.quitting
        else:
            env.win.hide.assert_not_called()
            standalone._arm_exit_backstop.assert_called()
            if case == "starting":
                assert lifecycle.quitting
        lifecycle.prompt.assert_not_called()
    monkeypatch.setattr(standalone.webview, "start", _fake_start(env, in_loop))
    standalone._run_client_mode(env.logger)


@pytest.mark.parametrize("dark", [False, True])
def test_client_window_background_follows_os_dark_mode(monkeypatch, env, dark):
    _client_json()
    _ok_preflight(monkeypatch)
    monkeypatch.setattr(standalone.startup_boot, "system_prefers_dark", lambda: dark)
    monkeypatch.setattr(standalone.webview, "start", _fake_start(env))
    standalone._run_client_mode(env.logger)
    assert env.create_calls[0][1] == standalone.STARTUP_PAGE
    assert env.create_calls[0][2]["background_color"] == standalone.startup_boot.THEME_BACKGROUNDS[
        "dim" if dark else "light"]


# ---------- client 模式流程 ----------

def test_client_mode_ok_starts_no_local_server(monkeypatch, env):
    _client_json()
    _ok_preflight(monkeypatch)
    monkeypatch.setattr(standalone.webview, "start", _fake_start(env))
    standalone._run_client_mode(env.logger)

    env.boom.assert_not_called()
    assert len(env.create_calls) == 1
    title, url, kw = env.create_calls[0]
    assert title == "OpenAver"
    assert url == standalone.STARTUP_PAGE
    assert kw["js_api"] is None
    messages = [str(c) for c in env.logger.info.call_args_list]
    assert not any("啟動伺服器" in m or "等待伺服器就緒" in m for m in messages)
    assert ("trusted", SERVER) in env.events
    assert env.events.index(("create_window", url)) < env.events.index(("trusted", SERVER))
    assert "expect_offline" not in env.events


# ---------- 168d：CF 殼接線（client） ----------

def _cf_state():
    return standalone.pywebview_api.api._cf_status()


def test_client_mode_wires_cf_once_with_same_origin_and_token(monkeypatch, env):
    _client_json()
    _ok_preflight(monkeypatch)
    monkeypatch.setattr(standalone.webview, "start", _fake_start(env))
    standalone._run_client_mode(env.logger)

    assert env.cf.fetch_calls == [(SERVER, TOKEN)]
    assert len(env.cf.build_calls) == 1 and len(env.cf.agents) == 1
    (agent,) = env.cf.agents
    assert ("trusted", agent.origin) in env.events          # 與 _set_trusted_origin 同一個值（CD-9）
    assert agent.origin == SERVER and agent.token == TOKEN
    assert agent.kw["server_remote"] is True and agent.kw["supported"] is True
    seq = [x for x in env.events if x in ("gui_loop_enter", "cf.build", "mark:cf_windows_created", "cf.announce",
                                           "cf.start", "gui_loop_exit", "cf.stop",
                                           "shutdown_after_loop", "spawn")]
    assert seq == ["gui_loop_enter", "cf.build", "mark:cf_windows_created", "cf.announce",
                   "cf.start", "gui_loop_exit", "cf.stop", "shutdown_after_loop", "spawn"]
    controller = standalone.pywebview_api._cf_status_provider.__self__      # 168e-T13：provider 改由控制器轉接
    assert standalone.pywebview_api._cf_status_provider == controller.status
    assert controller.agent is agent
    assert standalone.pywebview_api._cf_retry_handler == controller.retry


@pytest.mark.parametrize("server,proxy,expected_url,expected_direct", [
    (SERVER, "http://127.0.0.1:7890", "", True),            # 遠端伺服器＋loopback 代理 → 這台連不到 → 直連
])
def test_client_mode_remote_server_loopback_proxy_goes_direct(monkeypatch, env, server, proxy,
                                                              expected_url, expected_direct):
    client_settings.save_client_settings({"version": 1, "server": {"url": server, "token": TOKEN}})
    _ok_preflight(monkeypatch)
    env.cf.fetch_result = {"ok": True, "reason": None, "settings": ProxySettings(url=proxy, scope="all")}
    monkeypatch.setattr(standalone.webview, "start", _fake_start(env))
    standalone._run_client_mode(env.logger)
    (settings, local_direct), = env.cf.build_calls
    assert settings.url == expected_url and settings.scope == "all"
    assert local_direct is expected_direct


@pytest.mark.parametrize("fetch_reason,expected", [
    ("unauthorized", "unauthorized"), ("unreachable", "unreachable"),
])
def test_client_mode_cf_settings_failure_builds_no_windows(monkeypatch, env, fetch_reason, expected):
    _client_json()
    _ok_preflight(monkeypatch)
    env.cf.fetch_result = {"ok": False, "reason": fetch_reason, "settings": None}
    monkeypatch.setattr(standalone.webview, "start", _fake_start(env))
    standalone._run_client_mode(env.logger)
    assert env.cf.build_calls == [] and env.cf.agents == []
    assert _cf_state() == {"state": "not_ready", "reason": expected, "proxy_note": None, "sites": []}
    assert "gui_loop_enter" in env.events and "mark:cf_windows_created" not in env.events   # 主視窗照常


def _closable_cf(env, monkeypatch):
    """主視窗＋兩個 CF 視窗都是會跑 closing handler 的假視窗；回 (main, jl, javten)。"""
    wins = []
    main = _ClosableWindow("main", env.events, wins)
    jl = _ClosableWindow("jl", env.events, wins)
    javten = _ClosableWindow("javten", env.events, wins)
    wins.extend([main, jl, javten])
    monkeypatch.setattr(standalone.webview, "windows", wins, raising=False)
    monkeypatch.setattr(standalone.webview, "create_window", lambda title, url, **kw: main)
    env.cf.build_result = CfWindowSet(jl_win=jl, javten_win=javten)
    return main, jl, javten, wins


def test_client_mode_without_lifecycle_main_closing_destroys_cf_windows(monkeypatch, env):
    _client_json()
    _ok_preflight(monkeypatch)
    monkeypatch.setattr(standalone, "_setup_windows_lifecycle", lambda *a: None)
    main, jl, javten, wins = _closable_cf(env, monkeypatch)

    def in_loop():
        jl.destroy()                                         # 使用者按 X：隱藏而不關
        assert jl in wins and jl.hidden
        main.destroy()                                       # 關主視窗：CF 視窗放行，GUI 迴圈才會結束

    monkeypatch.setattr(standalone.webview, "start", _fake_start(env, in_loop=in_loop))
    standalone._run_client_mode(env.logger)
    print("WINDOWS_AFTER_CLOSE:", wins)  # noqa: T201
    assert wins == []
    assert "jl.destroy" in env.events and "javten.destroy" in env.events


def test_client_mode_with_lifecycle_cf_guards_follow_lifecycle_quitting(monkeypatch, env):
    _client_json()
    _ok_preflight(monkeypatch)
    main, jl, javten, wins = _closable_cf(env, monkeypatch)

    def in_loop():
        javten.destroy()
        assert javten in wins                                # quitting 為假 → 攔下
        env.lifecycle.quitting = True
        javten.destroy()
        assert javten not in wins                            # quitting 為真 → 放行

    monkeypatch.setattr(standalone.webview, "start", _fake_start(env, in_loop=in_loop))
    standalone._run_client_mode(env.logger)


# ---------- 重啟 ----------


def test_restart_sequence_in_client_mode(monkeypatch, env):
    _client_json()
    _ok_preflight(monkeypatch)

    def trigger():
        assert standalone.pywebview_api._request_restart() is True
        assert "spawn" not in env.events      # 迴圈返回前零 spawn
        _join_quit()

    monkeypatch.setattr(standalone.webview, "start", _fake_start(env, in_loop=trigger))
    standalone._run_client_mode(env.logger)
    seq = [x for x in env.events if x in ("gui_loop_enter", "gui_loop_exit", "shutdown_after_loop", "spawn")
           or (isinstance(x, tuple) and x[0] == "handle_tray_command")]
    print("EVENTS:", seq)  # noqa: T201  事件序列供 -s 目視
    assert seq == ["gui_loop_enter", ("handle_tray_command", CMD_QUIT), "gui_loop_exit",
                   "shutdown_after_loop", "spawn"]
    assert env.spawn.call_count == 1
    assert standalone.restart._state["requested"] is True


def test_restart_failed_notice_win32_uses_message_box(monkeypatch):
    box, err = Mock(), Mock()
    monkeypatch.setattr(standalone.sys, "platform", "win32")
    monkeypatch.setattr(standalone, "_win_message_box", box)
    monkeypatch.setattr(standalone, "show_error", err)
    standalone._restart_failed_notice("msg")
    box.assert_called_once_with("msg", "OpenAver", yes_no=False)
    err.assert_not_called()


# ---------- 接縫註冊 ----------


# ---------- main() 分岔與順序 ----------

def _patch_main_prelude(monkeypatch, events):
    monkeypatch.setattr(standalone, "setup_logging", lambda **k: None)
    monkeypatch.setattr(standalone, "get_logger", lambda name: MagicMock())
    monkeypatch.setattr(standalone, "bootstrap_data_layout", lambda: MagicMock(status="already_complete"))
    monkeypatch.setattr(standalone.restart, "wait_for_parent_exit",
                        lambda *a, **k: events.append("wait_for_parent_exit"))
    monkeypatch.setattr(standalone.shell_boot, "install_webview_token_filter",
                        lambda: events.append("install_filter"))

    def ensure(logger):
        events.append("ensure_webview2")
        raise SystemExit(0)

    monkeypatch.setattr(standalone, "_ensure_webview2_runtime", ensure)


def test_main_waits_for_restart_parent_before_startup(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAVER_DATA_DIR", str(tmp_path))
    events = []
    _patch_main_prelude(monkeypatch, events)
    with pytest.raises(SystemExit):
        standalone.main()
    assert "wait_for_parent_exit" in events and "ensure_webview2" in events
    assert events.index("wait_for_parent_exit") < events.index("ensure_webview2")


def test_token_filter_installed_before_resolve_boot(monkeypatch, tmp_path):
    monkeypatch.setattr(standalone.pywebview_api, "_startup_log_opener", None)
    monkeypatch.setattr(standalone.pywebview_api, "_startup_quit_handler", None)
    monkeypatch.setenv("OPENAVER_DATA_DIR", str(tmp_path))
    events = []
    _patch_main_prelude(monkeypatch, events)
    monkeypatch.setattr(standalone, "_ensure_webview2_runtime", lambda logger: None)
    monkeypatch.setattr(standalone, "_bootstrap_data_layout_or_exit", lambda logger: None)
    monkeypatch.setattr(standalone, "_run_client_mode", lambda logger: events.append("client_mode"))
    monkeypatch.setattr(client_settings, "mode", lambda: "client")

    def resolve(*a, **k):
        events.append("resolve_boot")
        raise SystemExit(0)

    monkeypatch.setattr(standalone.shell_boot, "resolve_boot", resolve)
    standalone.main()
    assert "install_filter" in events
    assert events.index("install_filter") < events.index("client_mode")

    # 本機路徑：resolve_boot 之前 filter 已裝
    events.clear()
    monkeypatch.setattr(client_settings, "mode", lambda: "local")
    monkeypatch.setattr(standalone, "find_free_port", lambda *a, **k: 49152)
    monkeypatch.setattr(standalone, "_start_boot_worker", lambda worker, *a: worker(*a))
    monkeypatch.setattr(standalone, "_start_gui", lambda startup, window: startup(window))
    monkeypatch.setattr(standalone, "wait_for_server", lambda *a, **k: standalone.PROBE_OK)
    monkeypatch.setattr(standalone, "run_server", lambda *a: None)
    monkeypatch.setitem(sys.modules, "web.app", types.SimpleNamespace(app=object()))
    ll = types.SimpleNamespace(lan_listener=MagicMock())
    monkeypatch.setitem(sys.modules, "web.lan_listener", ll)
    monkeypatch.setattr(standalone, "_maybe_autostart_lan_listener", lambda *a: None)
    monkeypatch.setitem(sys.modules, "window_state", types.SimpleNamespace(load_state=lambda: dict(SAVED)))
    monkeypatch.setattr(standalone.webview, "create_window", lambda *a, **k: MagicMock())
    monkeypatch.setattr(standalone.cf_windows, "cf_shell_supported", lambda: False)
    monkeypatch.setattr(standalone, "_setup_windows_lifecycle", lambda *a: None)
    monkeypatch.setattr(standalone, "_attach_window_state", lambda *a: None)
    monkeypatch.setattr(standalone, "_make_cf_agent", lambda *a: MagicMock())
    with pytest.raises(SystemExit):
        standalone.main()
    assert "resolve_boot" in events
    assert events.index("install_filter") < events.index("resolve_boot")


# ---------- lifecycle / window state ----------


# ---------- launcher AST ----------

def _launcher_tree():
    path = WINDOWS_DIR / "launcher.py"
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _chain(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _calls(tree, dotted):
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call) and _chain(n.func) == dotted]


# ---------- 168d：dev launcher 的 CF 接線與關閉路徑 ----------

def _launcher(monkeypatch):
    import importlib
    launcher = importlib.import_module("launcher")
    monkeypatch.setitem(launcher._cf_quitting, "v", False)
    return launcher


def _launcher_closable(launcher, monkeypatch, events):
    wins = []
    main = _ClosableWindow("main", events, wins)
    jl = _ClosableWindow("jl", events, wins)
    javten = _ClosableWindow("javten", events, wins)
    wins.extend([main, jl, javten])
    monkeypatch.setattr(launcher.webview, "windows", wins, raising=False)
    cf_set = CfWindowSet(jl_win=jl, javten_win=javten)
    controller = launcher.cf_boot.CfShellController(MagicMock(), "client", "http://localhost:8000")
    controller._cf_set = cf_set
    controller.bind(None, lambda: launcher._cf_quitting["v"])
    controller.attach_guards()
    return main, jl, javten, wins, controller


