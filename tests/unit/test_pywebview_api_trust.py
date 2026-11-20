"""windows/pywebview_api.py 信任閘測試（168a-T3b）。

只驅動假 window 事件並斷言結果；不推演事件先後。
oracle：(a) 載入序列、(i) before_load 立即撤銷、(ii) 遲到驗證不套用、origin 比對表、None==None、例外路徑。
"""
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

import core.config as core_config

TRUSTED = "http://127.0.0.1:8000"
OTHER = "http://127.0.0.1:8001"

METHODS = ["open_file", "open_folder", "open_url", "select_files",
           "select_folder", "select_folder_path", "on_drop"]
REFUSALS = {
    "open_file": {"ok": False, "reason": "untrusted", "local_path": None, "server_path": None},
    "open_folder": {"ok": False, "reason": "untrusted", "local_path": None, "server_path": None},
    "open_url": False,
    "select_files": [],
    "select_folder": None,
    "select_folder_path": None,
    "on_drop": None,
}


class _FakeEvent:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, fn):
        self.handlers.append(fn)
        return self

    def fire(self):
        for fn in list(self.handlers):
            fn()


class _FakeEvents:
    def __init__(self):
        self.before_load = _FakeEvent()
        self.loaded = _FakeEvent()


@pytest.fixture
def api_module(monkeypatch, tmp_path):
    mock_webview = MagicMock()
    mock_webview.OPEN_DIALOG = 10
    mock_webview.FOLDER_DIALOG = 20
    monkeypatch.setitem(sys.modules, "webview", mock_webview)
    monkeypatch.setitem(sys.modules, "webview.dom", MagicMock())
    monkeypatch.setenv("OPENAVER_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(core_config, "CONFIG_PATH", tmp_path / "config.json")
    spec = importlib.util.spec_from_file_location(
        "pywebview_api_trust_test",
        Path(__file__).parent.parent.parent / "windows" / "pywebview_api.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    yield module
    module.set_window(None)


@pytest.fixture
def fx(api_module, monkeypatch, tmp_path):
    """副作用口全換成 Mock；window 是假的（events 只含 before_load／loaded）"""
    monkeypatch.setattr(sys, "platform", "win32")
    effects = {"Popen": Mock(), "run": Mock(), "startfile": Mock()}
    monkeypatch.setattr(api_module.subprocess, "Popen", effects["Popen"])
    monkeypatch.setattr(api_module.subprocess, "run", effects["run"])
    monkeypatch.setattr(api_module.os, "startfile", effects["startfile"], raising=False)
    video = tmp_path / "x.mp4"
    video.write_bytes(b"v")
    window = MagicMock()
    window.events = _FakeEvents()
    window.create_file_dialog.side_effect = lambda kind, **kw: [str(video)] if kind == 10 else [str(tmp_path)]
    window.evaluate_js.return_value = TRUSTED
    window.get_current_url.return_value = TRUSTED + "/"
    window.dom.document.events.drop = _FakeEvent()
    effects["create_file_dialog"] = window.create_file_dialog
    ns = type("FX", (), dict(m=api_module, window=window, effects=effects, video=video))
    api = api_module.Api()
    api._set_trusted_origin(TRUSTED)
    _wire(ns, api)
    return ns


def _wire(fx, api):
    """把 api 設為模組級實例並（重新）綁事件"""
    fx.api = api
    fx.m.api = api
    fx.window.events = _FakeEvents()
    fx.m.bind_events(fx.window)


def _call(fx, method):
    if method == "open_file":
        return fx.api.open_file(str(fx.video))
    if method == "open_folder":
        return fx.api.open_folder(str(fx.video))
    if method == "open_url":
        return fx.api.open_url("https://example.com")
    if method == "on_drop":
        return fx.m.on_drop({"dataTransfer": {"files": [{"pywebviewFullPath": str(fx.video)}]}})
    return getattr(fx.api, method)()


def _call_ok(fx, method):
    return _call(fx, method) != REFUSALS[method]


def _all_effects_called(fx):
    e = fx.effects
    return any(e[k].called for k in ("Popen", "run", "startfile", "create_file_dialog")) \
        or fx.window.evaluate_js.called


def _reset(fx):
    for k in ("Popen", "run", "startfile"):
        fx.effects[k].reset_mock()
    fx.window.create_file_dialog.reset_mock()
    fx.window.evaluate_js.reset_mock()


def _load(fx, origin):
    fx.window.evaluate_js.return_value = origin
    fx.window.get_current_url.return_value = origin + "/p?q=1" if isinstance(origin, str) else origin
    fx.window.events.before_load.fire()
    fx.window.events.loaded.fire()


def _assert_all_inert(fx):
    for method in METHODS:
        _reset(fx)
        assert _call(fx, method) == REFUSALS[method], method
        assert not _all_effects_called(fx), method


def _assert_all_live(fx):
    for method in METHODS:
        _reset(fx)
        assert method == "on_drop" or _call_ok(fx, method), method
        if method == "on_drop":
            _call(fx, method)
        assert _all_effects_called(fx), method


def test_default_state_is_fail_closed(api_module, fx):
    _wire(fx, api_module.Api())
    _assert_all_inert(fx)


def test_load_sequence_trusts_only_trusted_segments(fx):
    _load(fx, TRUSTED)
    _assert_all_live(fx)
    _load(fx, OTHER)
    _assert_all_inert(fx)
    _load(fx, TRUSTED)
    _assert_all_live(fx)


def test_before_load_revokes_trust_before_any_verification(fx):
    _load(fx, TRUSTED)
    _assert_all_live(fx)
    fx.window.events.before_load.fire()
    _assert_all_inert(fx)


def test_stale_verification_never_trusts_later_navigation(fx):
    def late_verdict(_js):
        fx.window.events.before_load.fire()
        return TRUSTED

    fx.window.evaluate_js.side_effect = late_verdict
    fx.window.events.before_load.fire()
    fx.window.events.loaded.fire()
    assert fx.api._trusted is False
    assert fx.window.dom.document.events.drop.handlers == []
    fx.window.evaluate_js.side_effect = None
    fx.window.evaluate_js.return_value = TRUSTED
    _assert_all_inert(fx)


def test_drop_bound_only_on_trusted_page(fx):
    _load(fx, OTHER)
    assert fx.window.dom.document.events.drop.handlers == []
    _load(fx, TRUSTED)
    assert len(fx.window.dom.document.events.drop.handlers) == 1


@pytest.mark.parametrize("origin", [
    "http://127.0.0.1:8000.evil.com",
])
def test_origin_comparison_is_exact(fx, origin):
    _load(fx, origin)
    assert fx.api._trusted is False
    _assert_all_inert(fx)
    # 信任值是頁面 origin 的字串前綴（埠 800 vs 8000）也不能放行
    fx.api._set_trusted_origin("http://127.0.0.1:800")
    _load(fx, "http://127.0.0.1:8000")
    assert fx.api._trusted is False


def test_trailing_slash_on_configured_origin_is_normalised(fx):
    fx.api._set_trusted_origin(TRUSTED + "/")
    _load(fx, TRUSTED)
    assert fx.api._trusted is True


WHITELIST = {"open_file", "open_folder", "open_url",
             "select_files", "select_folder", "select_folder_path",
             "connect_get_state", "connect_probe", "connect_login", "connect_sources",
             "connect_test_row", "connect_save_path_map", "connect_apply_restart",
             "connect_switch_local_restart", "connect_show_offline", "copy_text",
             "offline_get_state", "offline_retry", "offline_save_url", "offline_login",
             "offline_switch_local_restart",
             "local_settings_get", "local_settings_save", "update_check", "update_context",
             "update_run", "cf_retry",
             "startup_get_state", "startup_open_log_folder", "startup_quit"}


def test_exposed_bridge_surface_is_exactly_the_whitelist(api_module):
    import inspect
    funcs = api_module.exposed_functions()
    assert {f.__name__ for f in funcs} == WHITELIST
    assert len(funcs) == len(WHITELIST)
    assert all(inspect.isfunction(f) and f.__module__ == api_module.__name__ for f in funcs)
    assert all("self" not in inspect.getfullargspec(f).args for f in funcs)


def _resolve(functions, name):
    """照 webview/util.py js_bridge_call（:330）：window._functions 精確查表，否則對 js_api(None) 逐層 getattr（:268-274）"""
    def get_nested_attribute(obj, attr_str):
        for attr in attr_str.split("."):
            obj = getattr(obj, attr, None)
            if obj is None:
                return None
        return obj
    return functions.get(name) or get_nested_attribute(None, name)


def test_dispatch_cannot_reach_api_internals(fx):
    functions = {f.__name__: f for f in fx.m.exposed_functions()}
    for name in ("open_file.__func__.__globals__", "_set_trusted_origin", "api._trusted", "_trusted"):
        assert _resolve(functions, name) is None, name
    # None 自己的方法（如 __setattr__）可被 getattr 到，但綁在 None 上，碰不到 Api
    hit = _resolve(functions, "__setattr__")
    assert hit is None or hit.__self__ is None
    with pytest.raises(Exception):
        hit("_trusted", True)
    assert fx.api._trusted is False


@pytest.mark.parametrize("js,native,trusted", [
    (TRUSTED, OTHER + "/", False),            # eval 被偽造：JS 說信任、原生說別處
])
def test_both_origin_sources_must_match_trusted(fx, js, native, trusted):
    fx.window.evaluate_js.return_value = js
    fx.window.get_current_url.return_value = native
    fx.window.events.before_load.fire()
    fx.window.events.loaded.fire()
    assert fx.api._trusted is trusted


# ---------------------------------------------------------------------------
# 168b-T4a：頁面種類 scope（_page_kind／_SCOPE）、離線頁判定、導航失敗分支、離線狀態容器
# ---------------------------------------------------------------------------
import core.client_settings as client_settings  # noqa: E402
import core.self_update as self_update  # noqa: E402

OFFLINE_ORIGIN = "http://127.0.0.1:55555"
OFFLINE_URL = OFFLINE_ORIGIN + "/offline.html"
SERVER_LAN = "http://192.168.1.50:8765"


def _load_raw(fx, js, native):
    """JS 與原生 URL 各給原字串（_load 只能表達同 origin）"""
    fx.window.evaluate_js.return_value = js
    fx.window.get_current_url.return_value = native
    fx.window.events.before_load.fire()
    fx.window.events.loaded.fire()


def _load_offline(fx, origin=OFFLINE_ORIGIN):
    _load_raw(fx, origin, origin + "/offline.html")


STARTUP_ORIGIN = OFFLINE_ORIGIN
STARTUP_URL = OFFLINE_ORIGIN + "/startup.html"
STARTUP_METHODS = ["startup_get_state", "startup_open_log_folder", "startup_quit"]


def _load_startup(fx, origin=OFFLINE_ORIGIN):
    _load_raw(fx, origin, origin + "/startup.html")


def _write_client(tmp_path, url=SERVER_LAN):
    client_settings.save_client_settings({
        "version": 1, "server": {"url": url, "token": ""}, "path_map": [],
        "player": "", "video_extensions": None, "close_action": "ask", "tray_locale": None})


def test_unregistered_method_is_denied(fx):
    _load(fx, TRUSTED)
    assert fx.api._page_kind == "server"
    assert fx.api._denied("not_in_scope_table") is True


def test_offline_page_reload_stays_offline_other_port_does_not(fx):
    fx.api._expect_offline()
    _load_offline(fx)
    _load_offline(fx)  # 同頁重整（無旗標）
    assert fx.api._page_kind == "offline"
    _load_offline(fx, "http://127.0.0.1:55556")
    assert fx.api._page_kind is None


@pytest.mark.parametrize("js,native,expected", [
    ("http://127.0.0.1:5", "http://127.0.0.1:5/offline.html", True),
    ("http://evil.example:5", "http://evil.example:5/offline.html", False),
    ("http://127.0.0.1:5", "http://127.0.0.1:5/offline.html.evil", False),
    ("http://127.0.0.1:5", "http://127.0.0.1:6/offline.html", False),
])
def test_is_offline_landing_table(api_module, js, native, expected):
    assert api_module._is_offline_landing(js, native) is expected


def _nav_failure_fx(fx, tmp_path, mode_client=True, native=None):
    if mode_client:
        _write_client(tmp_path)
    fx.api._set_trusted_origin(SERVER_LAN)
    seen = []
    fx.window.load_url.side_effect = lambda url: seen.append(fx.api._offline_expected)
    _load_raw(fx, "chrome-error://chromewebdata", native or SERVER_LAN + "/")
    return seen


def test_nav_failure_in_client_mode_shows_offline_once(fx, tmp_path):
    seen = _nav_failure_fx(fx, tmp_path)
    fx.window.load_url.assert_called_once_with(fx.m.OFFLINE_PAGE)
    assert seen == [True]
    assert fx.api._offline_state["failed_url"] == SERVER_LAN
    assert fx.api._page_kind is None


def test_nav_failure_warning_has_host_only_and_not_refusal_text(fx, tmp_path):
    fx.m.logger = MagicMock()
    _nav_failure_fx(fx, tmp_path)
    lines = [c[0][0] for c in fx.m.logger.warning.call_args_list]
    assert not any("refused reason=untrusted origin=" in line for line in lines)
    assert any("192.168.1.50:8765" in line for line in lines)
    assert not any("oa_token" in line or "http://192" in line for line in lines)


def test_nav_failure_in_local_mode_does_not_show_offline(fx, tmp_path):
    _nav_failure_fx(fx, tmp_path, mode_client=False)
    fx.window.load_url.assert_not_called()


# ---------------------------------------------------------------------------
# 168b-T4b／168e-T13：28 個方法 × 3 種頁面的 scope 矩陣（期望表為字面值，不由 _SCOPE 衍生）
# ---------------------------------------------------------------------------
SCOPE_LITERAL = {
    "select_files": "server", "select_folder": "server", "select_folder_path": "server",
    "open_file": "server", "open_folder": "server", "open_url": "server", "on_drop": "server",
    "connect_get_state": "server", "connect_probe": "server", "connect_login": "server",
    "connect_sources": "server", "connect_test_row": "server", "connect_save_path_map": "server",
    "connect_apply_restart": "server", "connect_switch_local_restart": "server",
    "connect_show_offline": "server", "copy_text": "server",
    "offline_get_state": "offline", "offline_retry": "offline", "offline_save_url": "offline",
    "offline_login": "offline", "offline_switch_local_restart": "offline",
    "local_settings_get": "server", "local_settings_save": "server", "update_check": "server",
    "update_context": "server", "update_run": "server", "cf_retry": "server",
    "startup_get_state": "startup", "startup_open_log_folder": "startup",
    "startup_quit": "startup",
}
NEW_ARGS = {
    "connect_get_state": (), "connect_probe": (SERVER_LAN,), "connect_login": (SERVER_LAN, "1234"),
    "connect_sources": (SERVER_LAN,), "connect_test_row": ("/a", "D:/a", "/a/x.mp4"),
    "connect_save_path_map": ([],), "connect_apply_restart": (SERVER_LAN, []),
    "connect_switch_local_restart": (), "connect_show_offline": (), "copy_text": ("x",),
    "offline_get_state": (), "offline_retry": (), "offline_save_url": (SERVER_LAN,),
    "offline_login": ("1234",), "offline_switch_local_restart": (),
    "local_settings_get": (), "local_settings_save": ({},), "update_check": (),
    "update_context": (), "update_run": (), "cf_retry": (),
    "startup_get_state": (), "startup_open_log_folder": (), "startup_quit": (),
}
OFFLINE_METHODS = sorted(m for m, k in SCOPE_LITERAL.items() if k == "offline")
STARTUP_LITERAL_METHODS = sorted(m for m, k in SCOPE_LITERAL.items() if k == "startup")
UNTRUSTED_REPLY = {"ok": False, "reason": "untrusted"}


@pytest.fixture
def mx(fx, tmp_path, monkeypatch):
    """matrix fixture：client 模式、所有新方法的副作用口換成 Mock"""
    import core.client_connect as client_connect
    _write_client(tmp_path)
    fx.mocks = {
        "probe": Mock(return_value={"ok": True, "reason": None, "version": "0.17.7", "kind": "nas",
                                    "auth_required": False, "authed": True,
                                    "compat": client_connect.Compat("ok", "")}),
        "login": Mock(return_value={"ok": True, "reason": None, "token": "t"}),
        "fetch_sources": Mock(return_value={"ok": True, "reason": None, "sources": []}),
        "preflight": Mock(return_value=client_connect.Preflight("ok", None, {})),
    }
    for name, mock in fx.mocks.items():
        monkeypatch.setattr(client_connect, name, mock)
    for name in ("apply_connection", "clear_connection", "save_path_map", "touch_last_ok"):
        fx.mocks[name] = Mock()
        monkeypatch.setattr(client_settings, name, fx.mocks[name])
    fx.mocks["copy_text"] = Mock(return_value=True)
    monkeypatch.setattr(fx.m.clipboard, "copy_text", fx.mocks["copy_text"])
    fx.mocks["stat"] = Mock()
    monkeypatch.setattr(fx.m, "_stat_path", fx.mocks["stat"])
    fx.mocks["restart"] = Mock()
    fx.m.set_restart_handler(fx.mocks["restart"])
    fx.mocks["cf_retry"] = Mock(return_value={"ok": True, "cf": {"state": "ready"}})
    fx.m.set_cf_retry_handler(fx.mocks["cf_retry"])
    fx.mocks["check_latest"] = Mock(return_value={"ok": True, "has_update": False, "current_version": "0.0.0"})
    monkeypatch.setattr(self_update, "check_latest", fx.mocks["check_latest"])
    fx.mocks["launch_installer"] = Mock()
    monkeypatch.setattr(self_update, "launch_installer", fx.mocks["launch_installer"])
    fx.mocks["update_local_settings"] = Mock(return_value={"ok": True, "changed": []})
    monkeypatch.setattr(client_settings, "update_local_settings", fx.mocks["update_local_settings"])
    fx.mocks["startup_state"] = Mock(return_value={"ok": True})
    fx.m.set_startup_state_provider(fx.mocks["startup_state"])
    fx.mocks["startup_log_opener"] = Mock()
    fx.m.set_startup_log_opener(fx.mocks["startup_log_opener"])
    fx.mocks["startup_quit"] = Mock()
    fx.m.set_startup_quit_handler(fx.mocks["startup_quit"])
    return fx


def _land(fx, kind):
    if kind == "server":
        _load(fx, TRUSTED)
    elif kind == "offline":
        fx.api._expect_offline()
        _load_offline(fx)
    elif kind == "startup":
        fx.window.real_url = STARTUP_URL
        fx.api._expect_startup()
        _load_startup(fx)
    else:
        _load(fx, OTHER)
    assert fx.api._page_kind == (None if kind == "none" else kind)
    _reset(fx)
    for mock in fx.mocks.values():
        mock.reset_mock()
    fx.window.load_url.reset_mock()
    fx.window.set_title.reset_mock()


def _matrix_call(fx, method):
    if method in NEW_ARGS:
        return getattr(fx.m, method)(*NEW_ARGS[method])
    return _call(fx, method)


def _refusal(method):
    return UNTRUSTED_REPLY if method in NEW_ARGS else REFUSALS[method]


def _assert_zero_effects(fx):
    assert not _all_effects_called(fx)
    for mock in fx.mocks.values():
        mock.assert_not_called()
    fx.window.load_url.assert_not_called()
    fx.window.set_title.assert_not_called()


def test_scope_matrix_literal_covers_exactly_the_scope_table(api_module):
    assert len(SCOPE_LITERAL) == 31
    assert set(SCOPE_LITERAL) == set(api_module._SCOPE)
    assert {m: api_module._SCOPE[m] for m in SCOPE_LITERAL} == SCOPE_LITERAL


@pytest.mark.parametrize("method", ["offline_get_state", "open_file",
                                    "startup_get_state", "startup_open_log_folder", "startup_quit"])
def test_scope_matrix_method_passes_on_its_own_page_kind(mx, method):
    _land(mx, SCOPE_LITERAL[method])
    result = _matrix_call(mx, method)
    if method in NEW_ARGS:
        assert result != UNTRUSTED_REPLY, method
    else:
        # 既有七項：回傳不是拒絕形狀（open_*：client 模式下會是 uncovered 另一種拒絕），或副作用口真的被碰到
        assert result != REFUSALS[method] or _all_effects_called(mx), method


@pytest.mark.parametrize("method, kind", [
    ("cf_retry", "none"),
    ("connect_apply_restart", "none"),
    ("connect_get_state", "none"),
    ("connect_login", "none"),
    ("connect_probe", "none"),
    ("connect_save_path_map", "none"),
    ("connect_show_offline", "none"),
    ("connect_sources", "none"),
    ("connect_switch_local_restart", "none"),
    ("connect_test_row", "none"),
    ("copy_text", "none"),
    ("local_settings_get", "none"),
    ("local_settings_save", "none"),
    ("offline_get_state", "none"),
    ("offline_login", "none"),
    ("offline_retry", "none"),
    ("offline_save_url", "none"),
    ("offline_switch_local_restart", "none"),
    ("on_drop", "none"),
    ("open_file", "none"),
    ("open_file", "offline"),
    ("open_folder", "none"),
    ("open_url", "none"),
    ("select_files", "none"),
    ("select_folder", "none"),
    ("select_folder_path", "none"),
    ("update_check", "none"),
    ("update_context", "none"),
    ("update_run", "none"),
    ("startup_get_state", "none"),
    ("startup_get_state", "server"),
    ("startup_get_state", "offline"),
    ("startup_open_log_folder", "none"),
    ("startup_open_log_folder", "server"),
    ("startup_open_log_folder", "offline"),
    ("startup_quit", "none"),
    ("startup_quit", "server"),
    ("startup_quit", "offline"),
] + [(method, "startup") for method in SCOPE_LITERAL if SCOPE_LITERAL[method] != "startup"])
def test_scope_matrix_denied_on_other_page_kinds(mx, method, kind):
    if SCOPE_LITERAL[method] == kind:
        pytest.skip("own page kind")
    _land(mx, kind)
    assert _matrix_call(mx, method) == _refusal(method), (method, kind)
    _assert_zero_effects(mx)


@pytest.mark.parametrize("method", OFFLINE_METHODS)
def test_scope_matrix_offline_methods_denied_on_server_page(mx, method):
    _land(mx, "server")
    assert _matrix_call(mx, method) == UNTRUSTED_REPLY
    _assert_zero_effects(mx)


# ---------------------------------------------------------------------------
# 168b-T9a：就緒訊號（F1/F2）與 WebView2 導航失敗簽名 "null"（F3）
# ---------------------------------------------------------------------------
def _ready_calls(fx):
    return [c[0][0] for c in fx.window.evaluate_js.call_args_list if "oabridgeready" in c[0][0]]


def test_loaded_signals_bridge_ready_with_kind_only_after_page_kind_is_set(fx, tmp_path):
    _write_client(tmp_path)
    fx.api._set_trusted_origin(SERVER_LAN)
    kinds_at_signal = []

    def spy(js):
        if "oabridgeready" in js:
            kinds_at_signal.append(fx.api._page_kind)
        return SERVER_LAN

    fx.window.evaluate_js.side_effect = spy
    fx.window.get_current_url.return_value = SERVER_LAN + "/p?oa_token=TKN-SENTINEL-9"
    fx.window.events.before_load.fire()
    fx.window.events.loaded.fire()
    sent = _ready_calls(fx)
    assert len(sent) == 1
    assert kinds_at_signal == ["server"]
    assert "__oaBridgeKind" in sent[0] and '"server"' in sent[0]
    for secret in ("192.168", "TKN-SENTINEL-9", "oa_token", "http"):
        assert secret not in sent[0]


def test_nav_failure_with_webview2_null_origin_on_server_url_shows_offline(fx, tmp_path):
    _write_client(tmp_path)
    fx.api._set_trusted_origin(SERVER_LAN)
    _load_raw(fx, "null", SERVER_LAN + "/settings")
    fx.window.load_url.assert_called_once_with(fx.m.OFFLINE_PAGE)


def test_null_origin_on_about_blank_is_not_a_nav_failure(fx, tmp_path):
    _write_client(tmp_path)
    fx.api._set_trusted_origin(SERVER_LAN)
    _load_raw(fx, "null", "about:blank")
    fx.window.load_url.assert_not_called()


# ---------------------------------------------------------------------------
# 168c-T2：導航空窗複查（原生 origin）與載入完成鉤子
# ---------------------------------------------------------------------------
EVIL_URL = "http://evil.example/"
_KIND_ORIGIN = {"server": TRUSTED, "offline": OFFLINE_ORIGIN}


def _set_native(fx, how, kind):
    """_land 之後才改原生 URL：同／異／None／拋例外"""
    getter = fx.window.get_current_url
    getter.side_effect = None
    if how == "same":
        getter.return_value = _KIND_ORIGIN[kind] + "/next"
    elif how == "other":
        getter.return_value = EVIL_URL
    elif how == "none":
        getter.return_value = None
    else:
        getter.side_effect = RuntimeError("no url")


@pytest.mark.parametrize("how", ["other", "raises"])
@pytest.mark.parametrize("method", ["open_file"])
def test_native_origin_recheck_refuses_with_zero_effects(mx, method, how):
    kind = SCOPE_LITERAL[method]
    _land(mx, kind)
    _set_native(mx, how, kind)
    mx.m.logger = MagicMock()
    assert _matrix_call(mx, method) == _refusal(method), (method, how)
    _assert_zero_effects(mx)
    lines = [c[0][0] for c in mx.m.logger.warning.call_args_list
             if "refused reason=navigating origin=" in c[0][0]]
    assert len(lines) == 1 and method in lines[0]
    assert not any("reason=untrusted" in c[0][0] for c in mx.m.logger.warning.call_args_list)


def test_loaded_hook_runs_for_server_and_offline_pages(fx):
    hook = Mock()
    fx.m.set_loaded_hook(hook)
    try:
        _load(fx, TRUSTED)
        hook.assert_called_once_with("server", fx.window, fx.api._nav_gen)
        hook.reset_mock()
        fx.api._expect_offline()
        _load_offline(fx)
        hook.assert_called_once_with("offline", fx.window, fx.api._nav_gen)
        hook.reset_mock()
        _load(fx, OTHER)  # 不受信任頁
        hook.assert_not_called()

        def late(js):
            if js == "location.origin":
                fx.window.events.before_load.fire()
            return TRUSTED

        fx.window.evaluate_js.side_effect = late  # 遲到的 loaded
        fx.window.events.before_load.fire()
        fx.window.events.loaded.fire()
        hook.assert_not_called()
        fx.window.evaluate_js.side_effect = None
        fx.m.set_loaded_hook(None)  # 未註冊
        _load(fx, TRUSTED)
        hook.assert_not_called()
    finally:
        fx.m.set_loaded_hook(None)


def test_page_loaded_subscriber_gets_every_kind_old_hook_unchanged(fx):
    old, subscriber = Mock(), Mock()
    fx.m.set_loaded_hook(old)
    try:
        fx.m.set_page_loaded_subscriber(subscriber)
        fx.window.real_url = STARTUP_URL
        fx.api._expect_startup()
        _load_startup(fx)
        subscriber.assert_called_once_with("startup", fx.window, fx.api._nav_gen)
        old.assert_not_called()
        subscriber.reset_mock()
        _load(fx, TRUSTED)
        old.assert_called_once_with("server", fx.window, fx.api._nav_gen)
        subscriber.assert_called_once_with("server", fx.window, fx.api._nav_gen)
        old.reset_mock()
        subscriber.reset_mock()
        fx.api._expect_offline()
        _load_offline(fx)
        old.assert_called_once_with("offline", fx.window, fx.api._nav_gen)
        subscriber.assert_called_once_with("offline", fx.window, fx.api._nav_gen)
        old.reset_mock()
        subscriber.reset_mock()
        _load(fx, OTHER)
        old.assert_not_called()
        subscriber.assert_not_called()
        old.side_effect = RuntimeError("old")
        _load(fx, TRUSTED)
        subscriber.assert_called_once_with("server", fx.window, fx.api._nav_gen)
        old.side_effect = None
        old.reset_mock()
        subscriber.side_effect = RuntimeError("new")
        _load(fx, TRUSTED)
        old.assert_called_once_with("server", fx.window, fx.api._nav_gen)
        subscriber.side_effect = None
        subscriber.reset_mock()
        fx.m.set_loaded_hook(None)
        _load(fx, TRUSTED)
        subscriber.assert_called_once_with("server", fx.window, fx.api._nav_gen)
        subscriber.reset_mock()
        fx.m.set_page_loaded_subscriber(None)
        _load(fx, TRUSTED)
        subscriber.assert_not_called()
    finally:
        fx.m.set_loaded_hook(None)
        fx.m.set_page_loaded_subscriber(None)


# ---------------------------------------------------------------------------
# 203-T6：第三種頁面種類 startup（偽造、綁定本次 real_url、延遲退出、兩頁不互借）
# ---------------------------------------------------------------------------
_NON_STARTUP_LANDINGS = [
    # 原生主機不是 loopback（JS 與原生 origin 一致）
    (STARTUP_ORIGIN, "http://10.0.0.5:55555/startup.html", STARTUP_URL),
    # 路徑只是以 /startup.html 結尾，不是它
    (STARTUP_ORIGIN, OFFLINE_ORIGIN + "/startup.html.evil", STARTUP_URL),
    # JS 與原生 origin 不一致：原生恰為 real_url，只有 JS 回別的 port
    ("http://127.0.0.1:1/", STARTUP_URL, STARTUP_URL),
    # real_url 非字串 → fail-closed（None == None 不算相符）
    (STARTUP_ORIGIN, STARTUP_URL, None),
    # 等的是啟動頁、實際載到離線頁：旗標已消耗，也不憑空變 offline
    (OFFLINE_ORIGIN, OFFLINE_URL, STARTUP_URL),
]


@pytest.mark.parametrize("js,native,real", _NON_STARTUP_LANDINGS)
def test_forged_startup_page_is_not_classified(fx, js, native, real):
    fx.window.real_url = real
    fx.api._expect_startup()
    _load_raw(fx, js, native)
    assert fx.api._page_kind is None
    assert fx.api._startup_expected is False  # 旗標已消耗
    assert fx.api._denied("startup_quit") is True


@pytest.mark.parametrize("case", ["other_port", "native_path_moved", "offline_native_path_moved"])
def test_startup_landing_is_bound_to_this_runs_server(mx, case):
    if case == "other_port":
        # real_url 綁的是 55555；同機另一埠也有 /startup.html
        mx.window.real_url = STARTUP_URL
        mx.api._expect_startup()
        other = "http://127.0.0.1:55556"
        _load_raw(mx, other, other + "/startup.html")
        assert mx.api._page_kind is None
        _reset(mx)
        for mock in mx.mocks.values():
            mock.reset_mock()
        assert mx.m.startup_quit() == UNTRUSTED_REPLY
        _assert_zero_effects(mx)
        return
    if case == "offline_native_path_moved":
        # 離線頁分類後原生 origin 不變、路徑換掉：舊分類仍在但 offline scope 全拒
        _land(mx, "offline")
        mx.window.get_current_url.return_value = OFFLINE_ORIGIN + "/next"
        for method in OFFLINE_METHODS:
            assert _matrix_call(mx, method) == UNTRUSTED_REPLY, method
        _assert_zero_effects(mx)
        return
    # 分類成 startup 後原生 origin 不變、路徑換掉：舊分類仍在但小頁 scope 全拒
    _land(mx, "startup")
    mx.window.get_current_url.return_value = OFFLINE_ORIGIN + "/next"
    assert mx.m.startup_get_state() == UNTRUSTED_REPLY
    assert mx.m.offline_get_state() == UNTRUSTED_REPLY
    _assert_zero_effects(mx)


@pytest.mark.parametrize("with_handler", [False, True])
def test_startup_quit_returns_before_closing_windows(mx, monkeypatch, with_handler):
    started = []

    class _FakeThread:
        def __init__(self, target=None, daemon=None, **kwargs):
            self.target = target
            self.daemon = daemon
            self.started = False
            started.append(self)

        def start(self):
            self.started = True

    monkeypatch.setattr(mx.m, "threading", SimpleNamespace(
        Thread=_FakeThread, Lock=mx.m.threading.Lock, Event=mx.m.threading.Event))
    monkeypatch.setattr(mx.m, "STARTUP_QUIT_DELAY", 0)
    _land(mx, "startup")
    handler = Mock()
    mx.m.set_startup_quit_handler(handler if with_handler else None)
    windows = [MagicMock(), MagicMock()]
    mx.m.webview.windows = windows
    assert mx.m.startup_quit() == {"ok": True, "reason": None}
    assert len(started) == 1 and started[0].daemon is True and started[0].started
    for window in windows:
        window.destroy.assert_not_called()
    started[0].target()
    if with_handler:
        handler.assert_called_once_with()
        for window in windows:
            window.destroy.assert_not_called()
    else:
        handler.assert_not_called()
        for window in windows:
            window.destroy.assert_called_once()


def test_startup_then_offline_pages_do_not_borrow_each_other(mx):
    _land(mx, "startup")
    for method in OFFLINE_METHODS:
        assert _matrix_call(mx, method) == UNTRUSTED_REPLY, method
    _assert_zero_effects(mx)
    mx.api._expect_offline()
    mx.window.events.before_load.fire()
    assert mx.api._page_kind is None
    mx.window.evaluate_js.return_value = OFFLINE_ORIGIN
    mx.window.get_current_url.return_value = OFFLINE_URL
    mx.window.events.loaded.fire()
    assert mx.api._page_kind == "offline"
    _reset(mx)
    for mock in mx.mocks.values():
        mock.reset_mock()
    for method in STARTUP_METHODS:
        assert _matrix_call(mx, method) == UNTRUSTED_REPLY, method
    _assert_zero_effects(mx)


def test_startup_loaded_does_not_consume_pending_offline(fx):
    fx.window.real_url = STARTUP_URL
    fx.api._expect_startup()
    fx.api._expect_offline()
    _load_startup(fx)
    assert fx.api._page_kind == "startup"
    _load_offline(fx)
    assert fx.api._page_kind == "offline"
    assert fx.api._denied("offline_get_state") is False


def test_trusted_server_loaded_consumes_pending_offline(fx):
    fx.api._set_trusted_origin(TRUSTED)
    fx.api._expect_offline()
    _load(fx, TRUSTED)
    assert fx.api._page_kind == "server"
    assert fx.api._offline_expected is False



