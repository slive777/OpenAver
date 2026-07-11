from unittest.mock import MagicMock
from pathlib import Path

import pytest

from windows.tray import (
    CLOSE_ASK,
    CLOSE_CANCEL,
    CLOSE_EXIT,
    CLOSE_TRAY,
    CMD_CLOSE_ASK,
    CMD_CLOSE_EXIT,
    CMD_CLOSE_TRAY,
    CMD_CONFIRM,
    CMD_OPEN,
    CMD_QUIT,
    IDCANCEL,
    NIF_SHOWTIP,
    TRAY_OPEN_EVENTS,
    CloseDecision,
    DesktopLifecycle,
    _OpenEventDebouncer,
    _map_dialog_result,
    load_desktop_texts,
)


@pytest.fixture
def desktop():
    window = MagicMock()
    jl_window = MagicMock()
    tray = MagicMock()
    saved = []
    # close_action store: injected dict-backed read/write (feature/82 T4)
    close_action_store = {"value": CLOSE_ASK}
    close_action_writes = []  # record each write for assertions

    def _read_ca():
        return close_action_store["value"]

    def _write_ca(action):
        close_action_store["value"] = action
        close_action_writes.append(action)

    state = {
        "width": 1200,
        "height": 800,
        "x": None,
        "y": None,
        "maximized": False,
    }
    lifecycle = DesktopLifecycle(
        window, jl_window, state,
        lambda value: saved.append(dict(value)),
        read_close_action=_read_ca,
        write_close_action=_write_ca,
    )
    lifecycle.attach_tray(tray)
    tray.start.return_value = True
    lifecycle.start_tray()
    return lifecycle, window, jl_window, tray, saved, close_action_store, close_action_writes


def test_prompt_tray_remember_hides_and_cancels_close(desktop):
    lifecycle, window, jl_window, tray, saved, ca_store, ca_writes = desktop
    lifecycle.prompt = lambda: CloseDecision(CLOSE_TRAY, remember=True)

    assert lifecycle.on_window_closing() is False
    window.hide.assert_called_once_with()
    jl_window.destroy.assert_not_called()
    tray.stop.assert_not_called()
    assert lifecycle.get_close_action() == CLOSE_TRAY
    # close_action now written via injected write_close_action (not geometry saved[])
    assert ca_store["value"] == CLOSE_TRAY
    assert ca_writes[-1] == CLOSE_TRAY


def test_prompt_cancel_keeps_window_open(desktop):
    lifecycle, window, jl_window, tray, saved, ca_store, ca_writes = desktop
    lifecycle.prompt = lambda: CloseDecision(CLOSE_CANCEL, remember=True)

    assert lifecycle.on_window_closing() is False
    window.hide.assert_not_called()
    jl_window.destroy.assert_not_called()
    assert lifecycle.get_close_action() == CLOSE_ASK
    assert ca_writes == []


def test_remembered_tray_skips_prompt(desktop):
    lifecycle, window, _jl_window, _tray, _saved, ca_store, _ca_writes = desktop
    # inject tray action directly into the store (injected path)
    ca_store["value"] = CLOSE_TRAY
    lifecycle.prompt = MagicMock(side_effect=AssertionError("prompt must not run"))

    assert lifecycle.on_window_closing() is False
    window.hide.assert_called_once_with()
    lifecycle.prompt.assert_not_called()


def test_remembered_exit_stops_tray_and_allows_close(desktop):
    lifecycle, _window, jl_window, tray, saved, ca_store, _ca_writes = desktop
    # inject exit action directly into the store (injected path)
    ca_store["value"] = CLOSE_EXIT

    assert lifecycle.on_window_closing() is None
    assert lifecycle.quitting is True
    tray.stop.assert_called_once_with()
    jl_window.destroy.assert_called_once_with()
    assert saved  # geometry state is still saved on quit


def test_tray_commands_open_change_preference_and_quit(desktop):
    lifecycle, window, jl_window, tray, saved, ca_store, ca_writes = desktop

    lifecycle.handle_tray_command(CMD_OPEN)
    window.show.assert_called_once_with()

    lifecycle.handle_tray_command(CMD_CLOSE_TRAY)
    assert lifecycle.get_close_action() == CLOSE_TRAY
    lifecycle.handle_tray_command(CMD_CLOSE_EXIT)
    assert lifecycle.get_close_action() == CLOSE_EXIT
    lifecycle.handle_tray_command(CMD_CLOSE_ASK)
    assert lifecycle.get_close_action() == CLOSE_ASK
    # close_action writes go to injected store, not geometry saved[]
    assert ca_writes[:3] == [CLOSE_TRAY, CLOSE_EXIT, CLOSE_ASK]

    lifecycle.handle_tray_command(CMD_QUIT)
    assert lifecycle.quitting is True
    tray.stop.assert_called_once_with()
    jl_window.destroy.assert_called_once_with()
    window.destroy.assert_called_once_with()


def test_quit_cleanup_is_idempotent(desktop):
    lifecycle, _window, jl_window, tray, _saved, _ca_store, _ca_writes = desktop
    lifecycle.handle_tray_command(CMD_QUIT)
    lifecycle.shutdown_after_loop()
    assert tray.stop.call_count == 1
    assert jl_window.destroy.call_count == 1


def test_dialog_result_mapping():
    assert _map_dialog_result(CMD_CONFIRM, CMD_CLOSE_TRAY, True) == CloseDecision(CLOSE_TRAY, True)
    assert _map_dialog_result(CMD_CONFIRM, CMD_CLOSE_EXIT, False) == CloseDecision(CLOSE_EXIT, False)
    assert _map_dialog_result(IDCANCEL, CMD_CLOSE_TRAY, True) == CloseDecision(CLOSE_CANCEL, False)
    assert _map_dialog_result(CMD_CONFIRM, 9999, True) == CloseDecision(CLOSE_CANCEL, False)


@pytest.mark.parametrize("locale", ["zh-TW", "zh-CN", "ja", "en"])
def test_desktop_texts_are_complete_for_every_supported_locale(monkeypatch, locale):
    monkeypatch.setattr("windows.tray.load_config", lambda: {"general": {"locale": locale}})

    texts = load_desktop_texts()

    assert texts.locale == locale
    for name, value in vars(texts).items():
        if name != "locale":
            assert value
            assert not value.startswith("[desktop.")


def test_desktop_texts_follow_runtime_locale_change(monkeypatch):
    current = {"locale": "zh-TW"}
    monkeypatch.setattr(
        "windows.tray.load_config",
        lambda: {"general": {"locale": current["locale"]}},
    )

    assert load_desktop_texts().minimize_to_tray == "最小化到系統匣"
    current["locale"] = "zh-CN"
    assert load_desktop_texts().minimize_to_tray == "最小化到系统托盘"


def test_open_event_debouncer_collapses_single_double_click_burst():
    now = [10.0]
    debouncer = _OpenEventDebouncer(interval=0.5, clock=lambda: now[0])

    assert debouncer.accept() is True
    now[0] += 0.1
    assert debouncer.accept() is False
    now[0] += 0.5
    assert debouncer.accept() is True


def test_tray_contract_supports_hover_single_and_double_click():
    assert NIF_SHOWTIP == 0x0080
    assert {0x0202, 0x0203, 0x0400}.issubset(TRAY_OPEN_EVENTS)


def test_unavailable_tray_remembered_downgrades_to_prompt_exit(desktop):
    """Remembered CLOSE_TRAY with tray unavailable must downgrade to prompt; exit path works."""
    lifecycle, window, _jl_window, _tray, _saved, ca_store, _ca_writes = desktop
    ca_store["value"] = CLOSE_TRAY
    _tray.start.return_value = False
    lifecycle.start_tray()
    lifecycle.prompt = lambda: CloseDecision(CLOSE_EXIT)

    result = lifecycle.on_window_closing()
    assert result is None
    assert lifecycle.quitting is True
    window.hide.assert_not_called()


def test_unavailable_tray_remembered_downgrades_to_prompt_cancel(desktop):
    """Remembered CLOSE_TRAY with tray unavailable must downgrade to prompt; cancel keeps window open."""
    lifecycle, window, _jl_window, _tray, _saved, ca_store, _ca_writes = desktop
    ca_store["value"] = CLOSE_TRAY
    _tray.start.return_value = False
    lifecycle.start_tray()
    lifecycle.prompt = lambda: CloseDecision(CLOSE_CANCEL)

    result = lifecycle.on_window_closing()
    assert result is False
    window.hide.assert_not_called()


def test_unavailable_tray_picked_in_prompt_notifies_and_cancels(desktop, monkeypatch):
    """User insisting on CLOSE_TRAY in prompt while tray is unavailable → notice shown, window not hidden."""
    lifecycle, window, _jl_window, _tray, _saved, ca_store, _ca_writes = desktop
    ca_store["value"] = CLOSE_TRAY
    _tray.start.return_value = False
    lifecycle.start_tray()
    lifecycle.prompt = lambda: CloseDecision(CLOSE_TRAY)
    unavailable = MagicMock()
    monkeypatch.setattr("windows.tray.show_tray_unavailable", unavailable)

    result = lifecycle.on_window_closing()
    assert result is False
    unavailable.assert_called_once_with(window)
    window.hide.assert_not_called()


def test_native_tray_has_taskbar_created_recovery():
    """AST guard: tray.py must call RegisterWindowMessageW with 'TaskbarCreated'.

    # [lint-guard: pytest-justified] 守 Python 源碼語意（AST 掃 win32 RegisterWindowMessageW 呼叫）——
    # 非前端靜態字串守衛，永久留 pytest（CD-96a-8c / CD-96-2）。
    """
    import ast as _ast

    source = (Path(__file__).parents[2] / "windows" / "tray.py").read_text(encoding="utf-8")
    tree = _ast.parse(source)

    def _func_name(node):
        if isinstance(node, _ast.Name):
            return node.id
        if isinstance(node, _ast.Attribute):
            return node.attr
        return None

    found = any(
        isinstance(node, _ast.Call)
        and _func_name(node.func) == "RegisterWindowMessageW"
        and node.args
        and isinstance(node.args[0], _ast.Constant)
        and node.args[0].value == "TaskbarCreated"
        for node in _ast.walk(tree)
    )
    assert found, "tray.py must call RegisterWindowMessageW('TaskbarCreated') for explorer-restart recovery"


# ---------------------------------------------------------------------------
# feature/82 T4: injected read/write close_action store tests
# ---------------------------------------------------------------------------

def test_injected_read_write_store_roundtrip():
    """set_close_action writes via injected write_close_action; get_close_action reads via injected read_close_action."""
    store = {"value": CLOSE_ASK}
    window = MagicMock()
    jl_window = MagicMock()
    saved = []

    lifecycle = DesktopLifecycle(
        window, jl_window, {"width": 1200, "height": 800, "x": None, "y": None, "maximized": False},
        lambda v: saved.append(dict(v)),
        read_close_action=lambda: store["value"],
        write_close_action=lambda a: store.__setitem__("value", a),
    )

    assert lifecycle.get_close_action() == CLOSE_ASK
    lifecycle.set_close_action(CLOSE_TRAY)
    assert store["value"] == CLOSE_TRAY
    assert lifecycle.get_close_action() == CLOSE_TRAY
    # geometry state saved[] not touched by set_close_action with injected write
    assert saved == []


def test_injected_read_invalid_value_coerced_to_ask():
    """get_close_action coerces invalid stored value to CLOSE_ASK."""
    store = {"value": "destroy-everything"}
    window = MagicMock()

    lifecycle = DesktopLifecycle(
        window, MagicMock(), {"width": 1200, "height": 800, "x": None, "y": None, "maximized": False},
        lambda v: None,
        read_close_action=lambda: store["value"],
        write_close_action=lambda a: None,
    )

    assert lifecycle.get_close_action() == CLOSE_ASK


def test_standalone_registers_tray_on_win32():
    """AST guard: NativeTrayIcon(...) must appear inside an 'if sys.platform == win32' body."""
    import ast as _ast

    source = (Path(__file__).parents[2] / "windows" / "standalone.py").read_text(encoding="utf-8")
    tree = _ast.parse(source)

    def _is_win32_check(test_node):
        """Return True if test_node is `sys.platform == 'win32'`."""
        if not isinstance(test_node, _ast.Compare):
            return False
        left = test_node.left
        if not (isinstance(left, _ast.Attribute) and left.attr == "platform"):
            return False
        if not (isinstance(left.value, _ast.Name) and left.value.id == "sys"):
            return False
        if len(test_node.ops) != 1 or not isinstance(test_node.ops[0], _ast.Eq):
            return False
        if len(test_node.comparators) != 1:
            return False
        comp = test_node.comparators[0]
        return isinstance(comp, _ast.Constant) and comp.value == "win32"

    def _func_name(node):
        if isinstance(node, _ast.Name):
            return node.id
        if isinstance(node, _ast.Attribute):
            return node.attr
        return None

    found = False
    for node in _ast.walk(tree):
        if isinstance(node, _ast.If) and _is_win32_check(node.test):
            # Walk the body of this if-node for a NativeTrayIcon(...) call
            for child in _ast.walk(node):
                if (
                    isinstance(child, _ast.Call)
                    and _func_name(child.func) == "NativeTrayIcon"
                ):
                    found = True
                    break
        if found:
            break

    assert found, "standalone.py must instantiate NativeTrayIcon(...) inside 'if sys.platform == win32'"


# ---------------------------------------------------------------------------
# T2 regression tests: on_quit_cleanup DI
# ---------------------------------------------------------------------------

def _make_lifecycle_with_cleanup(cleanup_cb):
    """Build a DesktopLifecycle with a mock tray + cleanup callback."""
    window = MagicMock()
    jl_window = MagicMock()
    tray = MagicMock()
    state = {"close_action": CLOSE_ASK}
    lc = DesktopLifecycle(
        window, jl_window, state,
        lambda value: None,
        on_quit_cleanup=cleanup_cb,
    )
    lc.attach_tray(tray)
    tray.start.return_value = True
    lc.start_tray()
    return lc, window, jl_window, tray


def test_begin_quit_invokes_quit_cleanup():
    """on_quit_cleanup must be called exactly once when _begin_quit() runs."""
    cleanup = MagicMock()
    lc, _, _, _ = _make_lifecycle_with_cleanup(cleanup)
    lc._begin_quit()
    cleanup.assert_called_once_with()


def test_begin_quit_cleanup_idempotent():
    """Calling _begin_quit() twice must invoke the cleanup only once."""
    cleanup = MagicMock()
    lc, _, _, _ = _make_lifecycle_with_cleanup(cleanup)
    lc._begin_quit()
    lc._begin_quit()
    cleanup.assert_called_once_with()


def test_close_exit_path_runs_cleanup():
    """close_action=='exit' via on_window_closing() must trigger cleanup."""
    cleanup = MagicMock()
    lc, _, _, _ = _make_lifecycle_with_cleanup(cleanup)
    lc.state["close_action"] = CLOSE_EXIT
    lc.on_window_closing()
    cleanup.assert_called_once_with()


def test_tray_quit_runs_cleanup():
    """CMD_QUIT via handle_tray_command() must trigger cleanup (tray-Quit path)."""
    cleanup = MagicMock()
    lc, _, _, _ = _make_lifecycle_with_cleanup(cleanup)
    lc.handle_tray_command(CMD_QUIT)
    cleanup.assert_called_once_with()


def test_cleanup_exception_does_not_block_quit():
    """If on_quit_cleanup raises, quitting must still be True and exception must not propagate."""
    def bad_cleanup():
        raise RuntimeError("cleanup boom")

    lc, _, _, _ = _make_lifecycle_with_cleanup(bad_cleanup)
    lc._begin_quit()  # must not raise
    assert lc.quitting is True


def test_minimize_path_does_not_run_cleanup():
    """close_action=='tray' (minimize) must NOT invoke the cleanup callback."""
    cleanup = MagicMock()
    lc, _, _, _ = _make_lifecycle_with_cleanup(cleanup)
    lc.tray_available = True  # simulate tray running
    lc.state["close_action"] = CLOSE_TRAY
    lc.on_window_closing()
    cleanup.assert_not_called()


# ---------------------------------------------------------------------------
# P1 regression: set_close_action / on_window_closing best-effort persistence
# ---------------------------------------------------------------------------

def test_set_close_action_swallows_write_failure():
    """set_close_action must NOT raise when write_close_action raises (best-effort);
    the new action must also be readable via get_close_action (session-local fallback)."""
    def _raising_write(action):
        raise RuntimeError("disk full")

    window = MagicMock()
    lc = DesktopLifecycle(
        window, MagicMock(),
        {"width": 1200, "height": 800, "x": None, "y": None, "maximized": False},
        lambda v: None,
        read_close_action=lambda: CLOSE_ASK,
        write_close_action=_raising_write,
    )
    # Must not raise even though write_close_action raises
    lc.set_close_action(CLOSE_TRAY)
    # Session-local override must be readable so the preference change is not lost
    assert lc.get_close_action() == CLOSE_TRAY


def test_set_close_action_invalid_still_raises_value_error():
    """set_close_action with a bogus action must still raise ValueError (programming-error guard)."""
    window = MagicMock()
    lc = DesktopLifecycle(
        window, MagicMock(),
        {"width": 1200, "height": 800, "x": None, "y": None, "maximized": False},
        lambda v: None,
        write_close_action=lambda a: None,
    )
    with pytest.raises(ValueError):
        lc.set_close_action("destroy-everything")


def test_on_window_closing_remember_best_effort_with_raising_write():
    """on_window_closing() must NOT raise when remember=True and write_close_action raises;
    returns False (hides window), AND the session-local value survives for this session."""
    def _raising_write(action):
        raise RuntimeError("sync-software lock")

    window = MagicMock()
    lc = DesktopLifecycle(
        window, MagicMock(),
        {"width": 1200, "height": 800, "x": None, "y": None, "maximized": False},
        lambda v: None,
        read_close_action=lambda: CLOSE_ASK,
        write_close_action=_raising_write,
    )
    lc.prompt = lambda: CloseDecision(CLOSE_TRAY, remember=True)
    lc.tray_available = True

    result = lc.on_window_closing()
    # Must not raise; window is hidden (returns False) and write failure is swallowed
    assert result is False
    window.hide.assert_called_once_with()
    # Session-local fallback: preference change must survive for the rest of this session
    assert lc.get_close_action() == CLOSE_TRAY


def test_session_override_cleared_on_successful_write():
    """After a failed write the session override is set; after a successful write it is cleared
    and config becomes authoritative again (self-healing: no sticky shadow)."""
    store = {"value": CLOSE_ASK}
    should_fail = [True]  # togglable; first writes raise, then succeed

    def _togglable_write(action):
        if should_fail[0]:
            raise IOError("transient failure")
        store["value"] = action

    window = MagicMock()
    lc = DesktopLifecycle(
        window, MagicMock(),
        {"width": 1200, "height": 800, "x": None, "y": None, "maximized": False},
        lambda v: None,
        read_close_action=lambda: store["value"],
        write_close_action=_togglable_write,
    )

    # Phase 1: write fails → session-local override active, store unchanged
    lc.set_close_action(CLOSE_EXIT)
    assert lc.get_close_action() == CLOSE_EXIT  # override visible
    assert store["value"] == CLOSE_ASK  # store unchanged (write failed)

    # Phase 2: write succeeds → override cleared, config authoritative
    should_fail[0] = False
    lc.set_close_action(CLOSE_TRAY)
    assert store["value"] == CLOSE_TRAY  # write went through
    assert lc.get_close_action() == CLOSE_TRAY  # reads from config (no override)
    assert "close_action" not in lc.state  # override was popped


def test_successful_write_does_not_shadow_external_config_change():
    """A successful set_close_action must pop any session-local override so that a later
    external Settings change (PUT /api/config) is visible via get_close_action (no shadow)."""
    store = {"value": CLOSE_ASK}

    window = MagicMock()
    lc = DesktopLifecycle(
        window, MagicMock(),
        {"width": 1200, "height": 800, "x": None, "y": None, "maximized": False},
        lambda v: None,
        read_close_action=lambda: store["value"],
        write_close_action=lambda a: store.__setitem__("value", a),
    )

    # Successful write: set to CLOSE_TRAY
    lc.set_close_action(CLOSE_TRAY)
    assert store["value"] == CLOSE_TRAY
    assert "close_action" not in lc.state  # override was popped — config is authoritative

    # External Settings change (e.g. PUT /api/config while app runs)
    store["value"] = CLOSE_EXIT

    # get_close_action must see the external change (NOT a stale self.state value)
    assert lc.get_close_action() == CLOSE_EXIT
