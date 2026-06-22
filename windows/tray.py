"""Windows close-to-tray lifecycle and native Shell_NotifyIcon integration."""

from __future__ import annotations

import ctypes
import os
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core.config import load_config
from core.i18n import FALLBACK_LOCALE, SUPPORTED_LOCALES, t
from core.logger import get_logger

logger = get_logger(__name__)

CLOSE_ASK = "ask"
CLOSE_TRAY = "tray"
CLOSE_EXIT = "exit"
CLOSE_CANCEL = "cancel"
CLOSE_ACTIONS = {CLOSE_ASK, CLOSE_TRAY, CLOSE_EXIT}

CMD_OPEN = 1001
CMD_CLOSE_ASK = 1002
CMD_CLOSE_TRAY = 1003
CMD_CLOSE_EXIT = 1004
CMD_QUIT = 1005

IDCANCEL = 2
CMD_CONFIRM = 1006
CMD_CANCEL = 1007

NIF_MESSAGE = 0x0001
NIF_ICON = 0x0002
NIF_TIP = 0x0004
NIF_SHOWTIP = 0x0080

TRAY_OPEN_EVENTS = {0x0202, 0x0203, 0x0400}  # WM_LBUTTONUP, WM_LBUTTONDBLCLK, NIN_SELECT


@dataclass(frozen=True)
class CloseDecision:
    action: str
    remember: bool = False


@dataclass(frozen=True)
class DesktopTexts:
    """Localized native-desktop strings loaded from the app's current locale."""

    locale: str
    open_app: str
    close_behavior: str
    ask_on_close: str
    minimize_to_tray: str
    exit_program: str
    quit_app: str
    dialog_instruction: str
    dialog_content: str
    dialog_minimize: str
    dialog_exit: str
    confirm: str
    cancel: str
    do_not_show_again: str
    fallback_message: str
    tray_unavailable: str


def load_desktop_texts() -> DesktopTexts:
    """Read the current locale once and return all strings for one native UI interaction."""
    try:
        locale = load_config().get("general", {}).get("locale", FALLBACK_LOCALE)
    except Exception:
        logger.warning("failed to read desktop locale; using fallback", exc_info=True)
        locale = FALLBACK_LOCALE
    if locale not in SUPPORTED_LOCALES:
        locale = FALLBACK_LOCALE

    def text(key: str) -> str:
        return t(f"desktop.{key}", locale=locale)

    return DesktopTexts(
        locale=locale,
        open_app=text("tray.open_app"),
        close_behavior=text("tray.close_behavior"),
        ask_on_close=text("tray.ask_on_close"),
        minimize_to_tray=text("tray.minimize_to_tray"),
        exit_program=text("tray.exit_program"),
        quit_app=text("tray.quit_app"),
        dialog_instruction=text("close_dialog.instruction"),
        dialog_content=text("close_dialog.content"),
        dialog_minimize=text("close_dialog.minimize"),
        dialog_exit=text("close_dialog.exit"),
        confirm=text("close_dialog.confirm"),
        cancel=text("close_dialog.cancel"),
        do_not_show_again=text("close_dialog.do_not_show_again"),
        fallback_message=text("close_dialog.fallback_message"),
        tray_unavailable=text("tray.unavailable"),
    )


class _OpenEventDebouncer:
    """Collapse the single/double-click event burst into one restore command."""

    def __init__(self, interval: float = 0.5, clock: Callable[[], float] = time.monotonic) -> None:
        self.interval = interval
        self.clock = clock
        self._last_open = float("-inf")

    def accept(self) -> bool:
        now = self.clock()
        if now - self._last_open < self.interval:
            return False
        self._last_open = now
        return True


class DesktopLifecycle:
    """Coordinates the main window, hidden CF window, tray, and close policy."""

    def __init__(
        self,
        window,
        jl_window,
        state: dict,
        save_state: Callable[[dict], None],
        prompt: Callable[[], CloseDecision] | None = None,
        on_quit_cleanup: Callable[[], None] | None = None,
    ) -> None:
        self.window = window
        self.jl_window = jl_window
        self.state = state
        self.save_state = save_state
        self.prompt = prompt or (lambda: show_close_dialog(self.window))
        self.on_quit_cleanup = on_quit_cleanup
        self.tray = None
        self.tray_available = False
        self.quitting = False

    def replace_state(self, state: dict) -> None:
        """Use the live state returned by window_state.attach()."""
        self.state = state

    def attach_tray(self, tray) -> None:
        self.tray = tray

    def start_tray(self) -> None:
        if self.tray is not None:
            self.tray_available = bool(self.tray.start())

    def get_close_action(self) -> str:
        action = self.state.get("close_action", CLOSE_ASK)
        return action if action in CLOSE_ACTIONS else CLOSE_ASK

    def set_close_action(self, action: str) -> None:
        if action not in CLOSE_ACTIONS:
            raise ValueError("invalid close action")
        self.state["close_action"] = action
        self.save_state(self.state)

    def on_window_closing(self):
        """Return False to cancel PyWebView close, or None to allow exit."""
        if self.quitting:
            return None

        action = self.get_close_action()
        if action == CLOSE_ASK:
            try:
                decision = self.prompt()
            except Exception:
                logger.exception("close dialog failed")
                decision = CloseDecision(CLOSE_CANCEL)
            action = decision.action
            if decision.remember and action in {CLOSE_TRAY, CLOSE_EXIT}:
                self.set_close_action(action)

        if action == CLOSE_TRAY:
            if not self.tray_available:
                logger.error("close-to-tray requested while tray icon is unavailable")
                show_tray_unavailable(self.window)
                return False
            self.save_state(self.state)
            try:
                self.window.hide()
            except Exception:
                logger.exception("failed to hide main window")
                return False
            return False
        if action == CLOSE_EXIT:
            self._begin_quit()
            return None
        return False

    def handle_tray_command(self, command: int) -> None:
        if command == CMD_OPEN:
            try:
                self.window.show()
            except Exception:
                logger.exception("failed to show main window")
            return
        if command == CMD_CLOSE_ASK:
            self.set_close_action(CLOSE_ASK)
            return
        if command == CMD_CLOSE_TRAY:
            self.set_close_action(CLOSE_TRAY)
            return
        if command == CMD_CLOSE_EXIT:
            self.set_close_action(CLOSE_EXIT)
            return
        if command == CMD_QUIT:
            self._begin_quit()
            try:
                self.window.destroy()
            except Exception:
                logger.exception("failed to destroy main window from tray")

    def _begin_quit(self) -> None:
        if self.quitting:
            return
        self.quitting = True
        self.save_state(self.state)
        if self.tray is not None:
            try:
                self.tray.stop()
            except Exception:
                logger.exception("failed to stop tray icon")
        if self.jl_window is not None:
            try:
                self.jl_window.destroy()
            except Exception:
                logger.warning("failed to destroy JL window on app close", exc_info=True)
        if self.on_quit_cleanup is not None:
            try:
                self.on_quit_cleanup()
            except Exception:
                logger.exception("quit cleanup callback failed")

    def shutdown_after_loop(self) -> None:
        """Backstop for forced native-window closure."""
        self._begin_quit()


def _map_dialog_result(button_id: int, radio_id: int, remember: bool) -> CloseDecision:
    if button_id != CMD_CONFIRM:
        return CloseDecision(CLOSE_CANCEL)
    mapping = {CMD_CLOSE_TRAY: CLOSE_TRAY, CMD_CLOSE_EXIT: CLOSE_EXIT}
    action = mapping.get(radio_id, CLOSE_CANCEL)
    return CloseDecision(action, remember and action in {CLOSE_TRAY, CLOSE_EXIT})


def show_close_dialog(window=None) -> CloseDecision:
    """Show a Windows 11 task dialog with a remember-choice checkbox."""
    if sys.platform != "win32":
        return CloseDecision(CLOSE_EXIT)
    texts = load_desktop_texts()
    owner = _resolve_owner_hwnd(window)
    try:
        return _show_task_dialog(texts, owner)
    except Exception:
        logger.warning("TaskDialog unavailable; falling back to MessageBox", exc_info=True)
        return _show_message_box(texts, owner)


def _resolve_owner_hwnd(window=None):
    """Best-effort owner HWND lookup without depending on a pywebview backend detail."""
    if sys.platform != "win32":
        return None
    for candidate in (
        getattr(window, "native", None),
        getattr(getattr(window, "native", None), "Handle", None),
    ):
        try:
            value = int(candidate)
            if value:
                return value
        except (TypeError, ValueError):
            pass
    try:
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        user32.GetActiveWindow.restype = wintypes.HWND
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        hwnd = user32.GetActiveWindow() or user32.GetForegroundWindow()
        if not hwnd:
            return None
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        return hwnd if process_id.value == os.getpid() else None
    except Exception:
        return None


@contextmanager
def _common_controls_v6():
    """Activate Common Controls v6 so TaskDialogIndirect is actually available.

    The embeddable Python executable has no application manifest of its own.
    Without this activation context TaskDialogIndirect returns E_INVALIDARG and
    the desktop silently falls back to a legacy MessageBox.
    """
    from ctypes import wintypes

    class ActCtx(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.ULONG),
            ("dwFlags", wintypes.DWORD),
            ("lpSource", wintypes.LPCWSTR),
            ("wProcessorArchitecture", wintypes.WORD),
            ("wLangId", wintypes.WORD),
            ("lpAssemblyDirectory", wintypes.LPCWSTR),
            ("lpResourceName", wintypes.LPCWSTR),
            ("lpApplicationName", wintypes.LPCWSTR),
            ("hModule", wintypes.HMODULE),
        ]

    manifest = Path(__file__).with_name("common-controls.manifest")
    if not manifest.is_file():
        raise FileNotFoundError(manifest)

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateActCtxW.argtypes = [ctypes.POINTER(ActCtx)]
    kernel32.CreateActCtxW.restype = wintypes.HANDLE
    kernel32.ActivateActCtx.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_size_t)]
    kernel32.ActivateActCtx.restype = wintypes.BOOL
    kernel32.DeactivateActCtx.argtypes = [wintypes.DWORD, ctypes.c_size_t]
    kernel32.DeactivateActCtx.restype = wintypes.BOOL
    kernel32.ReleaseActCtx.argtypes = [wintypes.HANDLE]

    config = ActCtx()
    config.cbSize = ctypes.sizeof(ActCtx)
    config.lpSource = str(manifest)
    handle = kernel32.CreateActCtxW(ctypes.byref(config))
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError()

    cookie = ctypes.c_size_t()
    if not kernel32.ActivateActCtx(handle, ctypes.byref(cookie)):
        kernel32.ReleaseActCtx(handle)
        raise ctypes.WinError()
    try:
        yield
    finally:
        kernel32.DeactivateActCtx(0, cookie.value)
        kernel32.ReleaseActCtx(handle)


def _show_task_dialog(texts: DesktopTexts, owner=None) -> CloseDecision:
    from ctypes import wintypes

    class TaskDialogButton(ctypes.Structure):
        _pack_ = 1
        _fields_ = [("nButtonID", ctypes.c_int), ("pszButtonText", wintypes.LPCWSTR)]

    callback_type = ctypes.WINFUNCTYPE(
        ctypes.c_long, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM, ctypes.c_ssize_t,
    )

    class TaskDialogConfig(ctypes.Structure):
        _pack_ = 1
        _fields_ = [
            ("cbSize", wintypes.UINT),
            ("hwndParent", wintypes.HWND),
            ("hInstance", wintypes.HINSTANCE),
            ("dwFlags", wintypes.DWORD),
            ("dwCommonButtons", wintypes.DWORD),
            ("pszWindowTitle", wintypes.LPCWSTR),
            ("mainIcon", ctypes.c_void_p),
            ("pszMainInstruction", wintypes.LPCWSTR),
            ("pszContent", wintypes.LPCWSTR),
            ("cButtons", wintypes.UINT),
            ("pButtons", ctypes.POINTER(TaskDialogButton)),
            ("nDefaultButton", ctypes.c_int),
            ("cRadioButtons", wintypes.UINT),
            ("pRadioButtons", ctypes.POINTER(TaskDialogButton)),
            ("nDefaultRadioButton", ctypes.c_int),
            ("pszVerificationText", wintypes.LPCWSTR),
            ("pszExpandedInformation", wintypes.LPCWSTR),
            ("pszExpandedControlText", wintypes.LPCWSTR),
            ("pszCollapsedControlText", wintypes.LPCWSTR),
            ("footerIcon", ctypes.c_void_p),
            ("pszFooter", wintypes.LPCWSTR),
            ("pfCallback", callback_type),
            ("lpCallbackData", ctypes.c_ssize_t),
            ("cxWidth", wintypes.UINT),
        ]

    buttons = (TaskDialogButton * 2)(
        TaskDialogButton(CMD_CONFIRM, texts.confirm),
        TaskDialogButton(CMD_CANCEL, texts.cancel),
    )
    radio_buttons = (TaskDialogButton * 2)(
        TaskDialogButton(CMD_CLOSE_TRAY, texts.dialog_minimize),
        TaskDialogButton(CMD_CLOSE_EXIT, texts.dialog_exit),
    )
    config = TaskDialogConfig()
    config.cbSize = ctypes.sizeof(TaskDialogConfig)
    config.hwndParent = owner
    config.dwFlags = 0x0008 | (0x1000 if owner else 0)  # ALLOW_CANCELLATION | POSITION_RELATIVE
    config.dwCommonButtons = 0
    config.pszWindowTitle = "OpenAver"
    config.pszMainInstruction = texts.dialog_instruction
    config.pszContent = texts.dialog_content
    config.cButtons = len(buttons)
    config.pButtons = buttons
    config.nDefaultButton = CMD_CONFIRM
    config.cRadioButtons = len(radio_buttons)
    config.pRadioButtons = radio_buttons
    config.nDefaultRadioButton = CMD_CLOSE_TRAY
    config.pszVerificationText = texts.do_not_show_again

    selected = ctypes.c_int(CMD_CANCEL)
    radio = ctypes.c_int(CMD_CLOSE_TRAY)
    verified = wintypes.BOOL(False)
    task_dialog = ctypes.windll.comctl32.TaskDialogIndirect
    task_dialog.argtypes = [
        ctypes.POINTER(TaskDialogConfig),
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(wintypes.BOOL),
    ]
    task_dialog.restype = ctypes.c_long
    with _common_controls_v6():
        result = task_dialog(
            ctypes.byref(config), ctypes.byref(selected), ctypes.byref(radio), ctypes.byref(verified),
        )
    if result != 0:
        raise OSError(result, "TaskDialogIndirect failed")
    return _map_dialog_result(selected.value, radio.value, bool(verified.value))


def _show_message_box(texts: DesktopTexts, owner=None) -> CloseDecision:
    # Yes=exit, No=tray, Cancel=cancel. The fallback cannot persist a choice.
    result = ctypes.windll.user32.MessageBoxW(
        owner,
        texts.fallback_message,
        "OpenAver",
        0x00000003 | 0x00000020 | 0x00000100,  # YESNOCANCEL | ICONQUESTION | DEFBUTTON2
    )
    return {
        6: CloseDecision(CLOSE_EXIT),
        7: CloseDecision(CLOSE_TRAY),
    }.get(result, CloseDecision(CLOSE_CANCEL))


def show_tray_unavailable(window=None) -> None:
    if sys.platform != "win32":
        return
    try:
        texts = load_desktop_texts()
        ctypes.windll.user32.MessageBoxW(
            _resolve_owner_hwnd(window),
            texts.tray_unavailable,
            "OpenAver",
            0x00000000 | 0x00000030,
        )
    except Exception:
        logger.warning("failed to show tray unavailable dialog", exc_info=True)


class NativeTrayIcon:
    """Small native Windows tray host running a dedicated message loop."""

    def __init__(
        self,
        source_icon: Path,
        command_handler: Callable[[int], None],
        get_close_action: Callable[[], str],
    ) -> None:
        self.source_icon = source_icon
        self.command_handler = command_handler
        self.get_close_action = get_close_action
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._hwnd = None
        self._wnd_proc = None
        self.available = False

    def start(self) -> bool:
        if sys.platform != "win32" or (self._thread is not None and self._thread.is_alive()):
            return self.available
        self._thread = threading.Thread(target=self._run, name="OpenAverTray", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=5):
            logger.warning("tray icon startup timed out")
            return False
        return self.available

    def stop(self) -> None:
        if sys.platform != "win32" or not self._hwnd:
            return
        try:
            ctypes.windll.user32.PostMessageW(self._hwnd, 0x0010, 0, 0)  # WM_CLOSE
        except Exception:
            logger.warning("failed to post tray shutdown message", exc_info=True)

    def _prepare_icon(self) -> Path | None:
        try:
            from PIL import Image

            destination = Path.home() / "OpenAver" / "tray.ico"
            destination.parent.mkdir(parents=True, exist_ok=True)
            with Image.open(self.source_icon) as image:
                image.convert("RGBA").save(
                    destination,
                    format="ICO",
                    sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (48, 48), (64, 64)],
                )
            return destination
        except Exception:
            logger.warning("failed to prepare tray icon; using Windows default", exc_info=True)
            return None

    def _run(self) -> None:
        try:
            self._run_windows()
        except Exception:
            logger.exception("tray icon message loop failed")
            self._ready.set()

    def _run_windows(self) -> None:
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        shell32 = ctypes.windll.shell32
        kernel32 = ctypes.windll.kernel32
        user32.DefWindowProcW.argtypes = [
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
        ]
        user32.DefWindowProcW.restype = ctypes.c_ssize_t
        user32.PostMessageW.argtypes = [
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
        ]
        user32.PostMessageW.restype = wintypes.BOOL
        user32.CreatePopupMenu.restype = wintypes.HMENU
        user32.AppendMenuW.argtypes = [
            wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR,
        ]
        user32.AppendMenuW.restype = wintypes.BOOL
        user32.TrackPopupMenu.argtypes = [
            wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HWND, ctypes.c_void_p,
        ]
        user32.TrackPopupMenu.restype = wintypes.UINT
        user32.DestroyMenu.argtypes = [wintypes.HMENU]
        user32.DestroyMenu.restype = wintypes.BOOL
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.SetForegroundWindow.restype = wintypes.BOOL
        user32.SetMenuDefaultItem.argtypes = [wintypes.HMENU, wintypes.UINT, wintypes.UINT]
        user32.SetMenuDefaultItem.restype = wintypes.BOOL
        user32.DestroyWindow.argtypes = [wintypes.HWND]
        user32.DestroyWindow.restype = wintypes.BOOL
        user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        user32.GetCursorPos.restype = wintypes.BOOL
        user32.RegisterClassExW.argtypes = [ctypes.c_void_p]
        user32.RegisterClassExW.restype = wintypes.ATOM
        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD, wintypes.ATOM, wintypes.LPCWSTR, wintypes.DWORD,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p,
        ]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.LoadImageW.argtypes = [
            wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
            ctypes.c_int, ctypes.c_int, wintypes.UINT,
        ]
        user32.LoadImageW.restype = wintypes.HANDLE
        user32.LoadIconW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
        user32.LoadIconW.restype = wintypes.HICON
        user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
        user32.LoadCursorW.restype = wintypes.HANDLE
        user32.GetMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT,
        ]
        user32.GetMessageW.restype = wintypes.BOOL
        user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.TranslateMessage.restype = wintypes.BOOL
        user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user32.DispatchMessageW.restype = ctypes.c_ssize_t
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
        shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.c_void_p]
        shell32.Shell_NotifyIconW.restype = wintypes.BOOL
        wm_tray = 0x0400 + 11  # WM_USER + 11
        wm_taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")

        class Guid(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        class NotifyIconData(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT),
                ("uFlags", wintypes.UINT), ("uCallbackMessage", wintypes.UINT),
                ("hIcon", wintypes.HICON), ("szTip", wintypes.WCHAR * 128),
                ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD),
                ("szInfo", wintypes.WCHAR * 256), ("uVersion", wintypes.UINT),
                ("szInfoTitle", wintypes.WCHAR * 64), ("dwInfoFlags", wintypes.DWORD),
                ("guidItem", Guid), ("hBalloonIcon", wintypes.HICON),
            ]

        wnd_proc_type = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
        )

        class WndClassEx(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.UINT), ("style", wintypes.UINT),
                ("lpfnWndProc", wnd_proc_type),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HANDLE),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR),
                ("hIconSm", wintypes.HICON),
            ]

        notify_data = NotifyIconData()
        loaded_icon = None
        open_debouncer = _OpenEventDebouncer()

        def add_icon() -> bool:
            notify_data.cbSize = ctypes.sizeof(NotifyIconData)
            notify_data.hWnd = self._hwnd
            notify_data.uID = 1
            # NIF_SHOWTIP is required for the standard hover tooltip after opting
            # into NOTIFYICON_VERSION_4 via NIM_SETVERSION.
            notify_data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_SHOWTIP
            notify_data.uCallbackMessage = wm_tray
            notify_data.hIcon = loaded_icon
            notify_data.szTip = "OpenAver"
            added = bool(shell32.Shell_NotifyIconW(0x00000000, ctypes.byref(notify_data)))  # NIM_ADD
            notify_data.uVersion = 4
            if added:
                shell32.Shell_NotifyIconW(0x00000004, ctypes.byref(notify_data))  # NIM_SETVERSION
            else:
                logger.warning(
                    "Shell_NotifyIconW failed to register tray icon (hwnd=%r icon=%r cbSize=%s)",
                    self._hwnd,
                    loaded_icon,
                    notify_data.cbSize,
                )
            return added

        def dispatch(command: int) -> None:
            try:
                self.command_handler(command)
            except Exception:
                logger.exception("tray command failed: %s", command)

        def show_menu() -> None:
            texts = load_desktop_texts()
            menu = user32.CreatePopupMenu()
            submenu = user32.CreatePopupMenu()
            user32.AppendMenuW(menu, 0x0000, CMD_OPEN, texts.open_app)
            user32.SetMenuDefaultItem(menu, CMD_OPEN, 0)
            user32.AppendMenuW(menu, 0x0800, 0, None)
            try:
                action = self.get_close_action()
            except Exception:
                logger.exception("failed to read tray close preference")
                action = CLOSE_ASK
            for command, value, label in (
                (CMD_CLOSE_ASK, CLOSE_ASK, texts.ask_on_close),
                (CMD_CLOSE_TRAY, CLOSE_TRAY, texts.minimize_to_tray),
                (CMD_CLOSE_EXIT, CLOSE_EXIT, texts.exit_program),
            ):
                flags = 0x0000 | (0x0008 if action == value else 0)
                user32.AppendMenuW(submenu, flags, command, label)
            user32.AppendMenuW(menu, 0x0010, submenu, texts.close_behavior)
            user32.AppendMenuW(menu, 0x0800, 0, None)
            user32.AppendMenuW(menu, 0x0000, CMD_QUIT, texts.quit_app)
            point = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(point))
            user32.SetForegroundWindow(self._hwnd)
            command = user32.TrackPopupMenu(menu, 0x0100 | 0x0002, point.x, point.y, 0, self._hwnd, None)
            user32.DestroyMenu(menu)
            if command:
                dispatch(int(command))

        @wnd_proc_type
        def wnd_proc(hwnd, message, w_param, l_param):
            if message == wm_taskbar_created:
                self.available = add_icon()
                return 0
            if message == wm_tray:
                event = int(l_param) & 0xFFFF
                if event in TRAY_OPEN_EVENTS:
                    if open_debouncer.accept():
                        dispatch(CMD_OPEN)
                elif event in {0x0205, 0x007B}:  # WM_RBUTTONUP, WM_CONTEXTMENU
                    show_menu()
                return 0
            if message == 0x0010:  # WM_CLOSE
                user32.DestroyWindow(hwnd)
                return 0
            if message == 0x0002:  # WM_DESTROY
                shell32.Shell_NotifyIconW(0x00000002, ctypes.byref(notify_data))  # NIM_DELETE
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hwnd, message, w_param, l_param)

        self._wnd_proc = wnd_proc
        instance = kernel32.GetModuleHandleW(None)
        class_name = f"OpenAverTrayWindow_{id(self)}"
        wnd_class = WndClassEx()
        wnd_class.cbSize = ctypes.sizeof(WndClassEx)
        wnd_class.lpfnWndProc = wnd_proc
        wnd_class.hInstance = instance
        wnd_class.lpszClassName = class_name
        wnd_class.hbrBackground = 6  # COLOR_WINDOW + 1
        atom = user32.RegisterClassExW(ctypes.byref(wnd_class))
        if not atom:
            raise ctypes.WinError()
        self._hwnd = user32.CreateWindowExW(
            0, atom, "OpenAver Tray", 0x80000000, 0, 0, 0, 0,
            None, None, instance, None,
        )
        if not self._hwnd:
            raise ctypes.WinError()
        try:
            change_filter = user32.ChangeWindowMessageFilterEx
            change_filter(self._hwnd, wm_taskbar_created, 1, None)
        except AttributeError:
            pass

        icon_path = self._prepare_icon()
        if icon_path is not None:
            loaded_icon = user32.LoadImageW(
                None, str(icon_path), 1, 0, 0, 0x0010 | 0x0040,
            )
        if not loaded_icon:
            loaded_icon = user32.LoadIconW(None, ctypes.c_void_p(32512))
        self.available = add_icon()
        self._ready.set()

        message = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))
        self._hwnd = None
        self.available = False
