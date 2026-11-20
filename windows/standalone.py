"""
OpenAver Windows 單機版啟動器
整合 FastAPI 後端 + PyWebView 前端於同一進程
"""
import contextlib
import os
import shutil
import subprocess
import sys
import threading
import time
import socket
import logging
import traceback
import types
from pathlib import Path

# 確保專案根目錄在 sys.path 中
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

# 確保 windows 目錄也在 sys.path 中（for pywebview_api import）
WINDOWS_DIR = os.path.dirname(os.path.abspath(__file__))
if WINDOWS_DIR not in sys.path:
    sys.path.insert(0, WINDOWS_DIR)

from core import startup_trace   # 啟動計時基準：須早於所有重 import
from core.data_layout import bootstrap_data_layout
from core.data_root import get_data_root
from core.logger import setup_logging, get_logger
import webview
from pywebview_api import api, bind_events
import pywebview_api
from tray import CMD_QUIT, DesktopLifecycle, NativeTrayIcon
from core import client_settings
from core.proxy_policy import current_settings
from windows import app_icon, cf_boot, cf_shell, cf_windows, health_probe, restart, shell_boot, shell_sync, startup_boot, update_notice
from windows.health_probe import (
    CLIENT_HOST,
    PROBE_CANCELLED,
    PROBE_OK,
    PROBE_TIMEOUT,
    run_server,
    wait_for_server,
)

startup_trace.mark("modules_loaded")

# 配置
PORT = 49152  # 使用動態/私有端口範圍 (49152-65535)，避免權限問題
STARTUP_PAGE = os.path.join(WINDOWS_DIR, "offline", "startup.html")
STARTUP_PAGE_READY_TIMEOUT = 10
STARTUP_EXIT_BACKSTOP_S = 3.0
STARTUP_PAGE_WAIT_S = 3.0
STARTUP_PAGE_POLL_S = 0.01
WEBVIEW2_PROFILE_DIR = "webview2"
WEBVIEW2_STARTED_MARKER = ".started"


# ============ WebView2 檢查 ============
# 判準忠實移植 pywebview 6.2.1 winforms.py `_is_chromium()`（含只比 major、
# `pv=''` 中止走訪兩條「看起來像 bug」的語意）。兩處具名豁免：
# 豁免 1（CD-120b-2）：.NET Release 讀不到時，pywebview 因 finally:
# winreg.CloseKey(net_key) 對未賦值名稱取值而拋 NameError 穿出；
# read_dotnet_release() 契約是回 None，決策邏輯把 None 轉成 False。
# 理由：那台機器上 pywebview 必定啟動失敗，使用者可見結論相同（起不來），
# 差別只在我們給看得懂的提示、它給未攔截例外。
# 豁免 2（WEBVIEW2_RUNTIME_PATH 短路不移植）：_is_chromium() 開頭
# if settings['WEBVIEW2_RUNTIME_PATH']: return True 不搬。
# 理由：全庫 core/web/windows/build.py/build_macos.py 沒有該 setting 的賦值，
# 恆為 falsy，等價性不受影響。前提由 test_standalone_webview2 賦值掃描鎖住。

WEBVIEW2_RUNTIME_GUID = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
WEBVIEW2_BETA_GUID = '{2CD8A007-E189-409D-A2C8-9AF4EF3C72AA}'
WEBVIEW2_DEV_GUID = '{0D50BFEC-CD6A-4F9A-964C-C7416E3ACB10}'
WEBVIEW2_CANARY_GUID = '{65C35B14-6C1D-4122-AC46-7148CC9D6497}'
WEBVIEW2_MIN_BUILD = '86.0.622.0'
DOTNET_RELEASE_MIN = 394802
WEBVIEW2_REGISTRY_HIVES = ('HKEY_CURRENT_USER', 'HKEY_LOCAL_MACHINE')


def webview2_registry_subpath(hive_name: str, guid: str, machine_name: str) -> str:
    """算出 EdgeUpdate Clients 的 registry 子路徑（與 pywebview edge_build 逐字相同）。"""
    if machine_name == 'x86' or hive_name == 'HKEY_CURRENT_USER':
        path = rf'Microsoft\EdgeUpdate\Clients\{guid}'
    else:
        path = rf'WOW6432Node\Microsoft\EdgeUpdate\Clients\{guid}'
    return rf'SOFTWARE\{path}'


def read_webview2_pv(hive_name: str, guid: str) -> str:
    """讀某 hive／GUID 的 EdgeUpdate `pv`。讀不到回 '0'；空字串原樣回傳。"""
    try:
        import winreg
        from platform import machine

        subpath = webview2_registry_subpath(hive_name, guid, machine())
        with winreg.OpenKey(getattr(winreg, hive_name), subpath) as windows_key:
            build, _ = winreg.QueryValueEx(windows_key, 'pv')
            return str(build)
    except Exception:  # noqa: BLE001,S110 — registry miss is the contract ('0'); do not map '' to '0'
        pass
    return '0'


def read_dotnet_release() -> int | None:
    """讀 HKLM .NET 4 Full `Release`。讀不到回 None（豁免 1／CD-120b-2，不拋 NameError）。"""
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full'
        ) as net_key:
            version, _ = winreg.QueryValueEx(net_key, 'Release')
        # pywebview 用原值比 version < 394802；非 int（含 bool）會 TypeError → False。
        # 不得 int() 轉型，否則 REG_SZ "394802" 會比它寬。
        if type(version) is not int:
            return None
        return version
    except Exception:  # noqa: BLE001 — missing .NET key is a documented None, not NameError
        return None


def _is_new_version(current_version: str, new_version: str) -> bool:
    # 逐字保留 pywebview 只比 major 的形狀（index 0 無條件 return）。
    # 門檻從 WEBVIEW2_MIN_BUILD 推導，不得寫死字面 86。
    new_range = new_version.split('.')
    cur_range = current_version.split('.')
    for index, _ in enumerate(new_range):
        if len(cur_range) > index:
            return int(new_range[index]) >= int(cur_range[index])
    return False


def check_webview2_installed():
    """檢查 WebView2 Runtime 是否已安裝（pywebview `_is_chromium()` 忠實移植）。"""
    if sys.platform != 'win32':
        return False
    try:
        release = read_dotnet_release()
        if release is None or release < DOTNET_RELEASE_MIN:
            try:
                get_logger('standalone').debug(
                    "WebView2 偵測：.NET Release 不足或讀不到 release=%r", release
                )
            except Exception:  # noqa: S110 — logger may not be initialized; must not abort detection
                pass
            return False
        cells = []
        for guid in (
            WEBVIEW2_RUNTIME_GUID,
            WEBVIEW2_BETA_GUID,
            WEBVIEW2_DEV_GUID,
            WEBVIEW2_CANARY_GUID,
        ):
            for hive_name in WEBVIEW2_REGISTRY_HIVES:
                build = read_webview2_pv(hive_name, guid)
                cells.append((hive_name, guid, build))
                if _is_new_version(WEBVIEW2_MIN_BUILD, build):
                    return True
    except Exception:  # noqa: BLE001 — empty pv ValueError aborts the walk (pywebview semantics)
        try:
            get_logger('standalone').debug("WebView2 偵測走訪中止", exc_info=True)
        except Exception:  # noqa: S110 — logger may not be initialized; must not abort detection
            pass
        return False
    try:
        get_logger('standalone').debug(
            "WebView2 偵測：四 GUID × 兩 hive 全部沒命中 cells=%s", cells
        )
    except Exception:  # noqa: S110 — logger may not be initialized; must not abort detection
        pass
    return False


# ============ 原生訊息視窗（Windows MessageBoxW）============
WEBVIEW2_DOWNLOAD_URL = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
MB_OK = 0x00000000
MB_YESNO = 0x00000004
MB_ICONERROR = 0x00000010
MB_ICONWARNING = 0x00000030
MB_SETFOREGROUND = 0x00010000
MB_TOPMOST = 0x00040000
IDYES = 6
IDNO = 7


def _win_message_box(text: str, caption: str, *, yes_no: bool) -> bool:
    """Windows 原生訊息視窗（MessageBoxW）。ctypes 延遲 import（函式內），
    因為 ctypes.windll 在 Linux 上不存在，module-level 取用會炸。
    """
    import ctypes

    if yes_no:
        flags = MB_YESNO | MB_ICONWARNING | MB_SETFOREGROUND | MB_TOPMOST
    else:
        flags = MB_OK | MB_ICONERROR | MB_SETFOREGROUND | MB_TOPMOST

    result = ctypes.windll.user32.MessageBoxW(0, text, caption, flags)
    if result == 0:
        code = ctypes.GetLastError()
        raise RuntimeError(f"MessageBoxW failed (GetLastError={code})")
    if yes_no:
        return result == IDYES
    return True


def copy_to_clipboard(text: str) -> bool:
    """Write Unicode text to the Windows clipboard. Failures return False."""
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32

        kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalUnlock.restype = ctypes.c_int
        kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
        kernel32.GlobalFree.restype = ctypes.c_void_p
        user32.OpenClipboard.argtypes = [ctypes.c_void_p]
        user32.OpenClipboard.restype = ctypes.c_int
        user32.EmptyClipboard.argtypes = []
        user32.EmptyClipboard.restype = ctypes.c_int
        user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
        user32.SetClipboardData.restype = ctypes.c_void_p
        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = ctypes.c_int

        payload = text.encode('utf-16-le') + b'\x00\x00'
        size = len(payload)
        gmem_moveable = 0x0002
        cf_unicodetext = 13

        h = kernel32.GlobalAlloc(gmem_moveable, size)
        if not h:
            return False

        p = kernel32.GlobalLock(h)
        if not p:
            kernel32.GlobalFree(h)
            return False

        ctypes.memmove(p, payload, size)
        kernel32.GlobalUnlock(h)

        if not user32.OpenClipboard(0):
            kernel32.GlobalFree(h)
            return False

        try:
            user32.EmptyClipboard()
            owned = user32.SetClipboardData(cf_unicodetext, h)
            if not owned:
                kernel32.GlobalFree(h)
                return False
            return True
        finally:
            user32.CloseClipboard()
    except Exception as e:  # noqa: BLE001 — clipboard failure must not abort the prompt
        try:
            get_logger('standalone').debug("clipboard copy failed: %s", e)
        except Exception:  # noqa: S110 — logger may not be initialized; silent fallback is intentional
            pass
        return False


def show_webview2_prompt():
    """顯示 WebView2 安裝提示。回傳值只表達使用者選擇（True=去下載/False=不要）。
    顯示本身失敗時改為拋例外（CD-120b-7），呼叫端 _ensure_webview2_runtime() 負責接住。
    """
    if sys.platform == 'win32':
        message = (
            "OpenAver 需要 Microsoft Edge WebView2 Runtime 才能運行。\n\n"
            "這是 Windows 10/11 的標準元件，但您的系統尚未安裝。\n\n"
            "下載網址：" + WEBVIEW2_DOWNLOAD_URL + "\n\n"
            "是否前往下載頁面？（約 2MB，安裝需 1 分鐘）"
        )
        # 第一段：顯示 + 取得選擇——失敗就讓例外往外穿，不吞
        result = _win_message_box(message, "需要 WebView2 Runtime", yes_no=True)
        if result:
            # 第二段：開瀏覽器——獨立 try，這裡的失敗不得改變 result 或被誤判成「沒問成」
            opened = False
            try:
                import webbrowser
                opened = webbrowser.open(WEBVIEW2_DOWNLOAD_URL)
                if opened:
                    try:
                        get_logger('standalone').info(
                            "已請系統開啟下載頁：%s", WEBVIEW2_DOWNLOAD_URL
                        )
                    except Exception:  # noqa: S110 — logger may not be initialized; silent fallback is intentional
                        pass
            except Exception as e:
                try:
                    get_logger('standalone').warning(f"[OpenAver] 開啟瀏覽器失敗：{e}")
                except Exception:  # noqa: S110 — logger may not be initialized; silent fallback is intentional
                    pass
            if not opened:
                # 回 False（沒有預設瀏覽器）與拋例外是兩種不同的失敗形式，兩種都要留痕：
                # 沒有這一行時，「按了是卻沒反應」的回報在 debug.log 裡完全是空白。
                try:
                    get_logger('standalone').warning(
                        "[OpenAver] 瀏覽器未開啟，改以視窗顯示下載網址"
                    )
                except Exception:  # noqa: S110 — logger may not be initialized; silent fallback is intentional
                    pass
                clipboard_copied = copy_to_clipboard(WEBVIEW2_DOWNLOAD_URL)
                if clipboard_copied:
                    message2 = (
                        "瀏覽器沒能開啟。\n"
                        "網址已複製到剪貼簿。\n"
                        "\n"
                        + WEBVIEW2_DOWNLOAD_URL
                    )
                else:
                    message2 = (
                        "瀏覽器沒能開啟。\n"
                        "無法寫入剪貼簿，請按 Ctrl+C 複製此視窗文字。\n"
                        "\n"
                        + WEBVIEW2_DOWNLOAD_URL
                    )
                _win_message_box(message2, "需要 WebView2 Runtime", yes_no=False)
        return result

    # 非 Windows：逐字不動（tkinter 現行實作）
    try:
        import tkinter as tk
        from tkinter import messagebox
        import webbrowser

        root = tk.Tk()
        root.withdraw()

        message = (
            "OpenAver 需要 Microsoft Edge WebView2 Runtime 才能運行。\n\n"
            "這是 Windows 10/11 的標準元件，但您的系統尚未安裝。\n\n"
            "是否前往下載頁面？（約 2MB，安裝需 1 分鐘）"
        )

        result = messagebox.askyesno("需要 WebView2 Runtime", message)

        if result:
            webbrowser.open("https://go.microsoft.com/fwlink/p/?LinkId=2124703")

        root.destroy()
        return result
    except Exception as e:
        # 使用 ASCII-safe 格式避免 Windows console 編碼問題
        try:
            err_logger = get_logger('standalone')
            err_logger.warning(f"[OpenAver] 無法顯示 WebView2 提示視窗：{e}")
        except Exception:  # noqa: S110 — logger may not be initialized; silent fallback is intentional
            pass
        return False


# ============ 錯誤處理 ============

def show_error(title, message, details=None, logger=None):
    """顯示錯誤訊息視窗"""
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()

        full_message = message
        if details:
            full_message += f"\n\n錯誤詳情：\n{details[:500]}"  # 限制詳情長度

        messagebox.showerror(title, full_message)
        root.destroy()
    except Exception:
        # tkinter 不可用時，只輸出到 console/log
        if logger:
            logger.error(f"{title}: {message}")
            if details:
                logger.error(f"詳情: {details}")
        else:
            try:
                err_logger = get_logger('standalone')
                err_logger.error(f"{title}: {message}")
                if details:
                    err_logger.error(f"Details: {details}")
            except Exception:  # noqa: S110 — logger not yet initialized; silent fallback is intentional
                pass  # logger 未初始化時靜默失敗


# ============ 核心功能 ============

def find_free_port(start_port=49152, logger=None, max_attempts=100):
    """尋找可用端口（改進版，使用動態端口範圍避免權限問題）"""
    last_error = None
    tested_ports = []

    for port in range(start_port, start_port + max_attempts):
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # 設置 SO_REUSEADDR 選項（允許快速重用端口）
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # 設置超時避免卡住
            sock.settimeout(1)
            sock.bind((CLIENT_HOST, port))
            sock.close()

            # 記錄成功找到的端口
            if logger:
                logger.info(f"找到可用端口: {port}")

            return port
        except OSError as e:
            last_error = e
            tested_ports.append(port)
            # 記錄詳細的失敗信息（僅前 5 次和最後 5 次，避免日誌過多）
            if len(tested_ports) <= 5 or len(tested_ports) >= max_attempts - 5:
                if logger:
                    logger.debug(f"端口 {port} 不可用: {e}")
            continue
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:  # noqa: S110 — cleanup after port probe; socket close failure is harmless
                    pass

    # 提供更詳細的錯誤信息和解決方案
    error_msg = f"無法找到可用端口 ({start_port}-{start_port + max_attempts - 1})"
    if last_error:
        error_code = getattr(last_error, 'winerror', None) or getattr(last_error, 'errno', None)
        error_msg += f"\n最後錯誤: {last_error}"

        # 針對 Windows Error 10013 提供具體建議
        if error_code == 10013:
            error_msg += "\n\n[解決方案]"
            error_msg += "\n1. 暫時關閉防火牆或安全軟件（如 360、McAfee）"
            error_msg += "\n2. 右鍵點擊 OpenAver.bat，選擇「以系統管理員身分執行」"
            error_msg += "\n3. 檢查 Windows Defender 防火牆設定"
            error_msg += "\n4. 重新啟動電腦後再試"

        error_msg += f"\n已測試 {len(tested_ports)} 個端口"

    if logger:
        logger.error(error_msg)

    raise RuntimeError(error_msg)


def _bootstrap_data_layout_or_exit(logger) -> None:
    """資料根定版；失敗 → 顯示錯誤視窗 → sys.exit(1)。

    從 main() 抽出以維持 function-size ≤ 200；必須在 port／server thread／視窗之前呼叫。

    win32 上這裡是 `show_error()` 唯一的 Windows 原生 modal 例外（Codex/CodeRabbit
    review，153b）：D1（0.14.0／120d-T1）把 `show_error()` 本身的 Windows 平台分派
    撤回，原因是開機自動啟動的機器啟動失敗時，沒人會按的 modal 會卡住行程、
    且**當時**那個行程還佔著 port。這裡不適用同一個理由——本函式呼叫點在
    `find_free_port()` 之前（見 main()），失敗時從未綁定 port；而且資料根壞掉
    是**每次啟動都會重現**的持續性失敗，不像 port 衝突通常一次性、換個 port 或
    重試就過。不跳窗的話使用者永遠不知道 App 為什麼打不開，直接違反
    spec-153 §7／AC-7 的承諾。真實 Windows 打包版（embeddable Python）沒有
    Tcl/Tk，`show_error()` 的 tkinter 分支在那裡必炸、靜默退化成只寫 log——
    `pythonw.exe` 沒有主控台，log 沒人看得到。因此 win32 先試原生
    `_win_message_box()`（僅靠 ctypes，打包版一定有），失敗才退回 `show_error()`
    當保底。`show_error()` 本身與其他 5 個呼叫點刻意不動，反向守衛
    `test_show_error_non_windows_skips_win_message_box` 必須維持綠。
    """
    try:
        bootstrap_data_layout()
    except Exception:
        logger.error("資料根定版失敗", exc_info=True)
        title = "OpenAver 啟動失敗"
        message = "OpenAver 啟動失敗：資料位置尚未就緒或已損毀，暫時無法開啟主畫面。詳細原因已寫入 debug.log。"
        shown = False
        if sys.platform == "win32":
            try:
                _win_message_box(message, title, yes_no=False)
                shown = True
            except Exception:
                logger.warning("原生訊息視窗顯示失敗，改用 show_error 保底", exc_info=True)
        if not shown:
            show_error(title, message, None, logger)
        sys.exit(1)


def _ensure_webview2_runtime(logger) -> None:
    """Windows-only: verify WebView2 Runtime is installed; prompt + exit(0) if not.

    TASK-118a-T1: extracted out of main() (was inline step "0.") purely to keep
    main()'s cyclomatic complexity under the ruff C901 threshold now that a
    second CF-transport window's setup + closing-handler branches live there —
    this block is otherwise unrelated to T1 and unchanged behaviourally.
    """
    if sys.platform != 'win32':
        return
    if check_webview2_installed():
        return
    logger.info("WebView2 Runtime 未安裝")
    try:
        accepted = show_webview2_prompt()
    except Exception as e:
        logger.warning("[OpenAver] 提示視窗無法顯示：%s", e)
        sys.exit(0)
    if not accepted:
        logger.info("用戶取消安裝，程式結束")
        sys.exit(0)
    else:
        logger.info("請安裝 WebView2 後重新啟動")
        sys.exit(0)


def _maybe_autostart_lan_listener(lan_listener, logger) -> None:
    from core.config import load_config
    if load_config().get("general", {}).get("server_mode", False):
        try:
            _lp = lan_listener.start()
            logger.info("server_mode persisted true → LAN listener on :%s", _lp)
        except Exception as e:                     # noqa: BLE001 — auto-start best-effort
            logger.warning("auto-start LAN listener failed: %s", e)
            try:
                from web.routers.notifications import emit_notification
                # 不傳 str(e)：Python 例外細節不可暴露給前端（安全規則）。
                # 細節已由上方 logger.warning 寫入 server-side log。
                emit_notification("error", "settings.server_info.autostart_failed")
            except Exception:  # noqa: BLE001,S110 — emit_notification failure is harmless; best-effort only
                pass


def _setup_windows_lifecycle(window, jl_win, javten_win, saved, lan_listener) -> DesktopLifecycle | None:
    if sys.platform == 'win32':
        import window_state

        lifecycle = DesktopLifecycle(
            window,
            {'javlibrary': jl_win, 'fc-javten': javten_win},
            saved,
            window_state.save_state,
            on_quit_cleanup=lan_listener.shutdown if lan_listener is not None else None,
            read_close_action=client_settings.close_action,
            write_close_action=client_settings.set_close_action,
        )
        tray_icon = NativeTrayIcon(
            Path(APP_DIR) / "web" / "static" / "openaver.png",
            lifecycle.handle_tray_command,
            lifecycle.get_close_action,
        )
        lifecycle.attach_tray(tray_icon)
        return lifecycle
    return None


# ============ 主程序 ============

def _create_main_window(boot, saved, background_color=None):
    """建立主視窗並公開橋接方法。"""
    if boot.kind == "startup":
        api._expect_startup()
    create_kwargs = dict(js_api=None, width=saved['width'], height=saved['height'])
    if background_color is not None:
        create_kwargs['background_color'] = background_color
    if saved['x'] is not None and saved['y'] is not None:
        create_kwargs['x'] = saved['x']
        create_kwargs['y'] = saved['y']
    window = webview.create_window(boot.title, boot.url, **create_kwargs)
    window.expose(*pywebview_api.exposed_functions())
    return window


def _attach_window_state(w, saved, lifecycle, logger):
    import window_state
    bind_events(w)
    live = window_state.attach(w, saved)
    if lifecycle is not None:
        lifecycle.replace_state(live)
        lifecycle.start_tray()
    if saved['maximized']:
        try:
            w.maximize()
        except Exception as e:
            logger.warning(f"window maximize failed: {e}")
            # Codex P2: maximize 失敗時清 live state，否則 on_resized/on_moved
            # 永遠 early-return，下次啟動仍寫回 maximized=true 形成 sticky failure
            live["maximized"] = False


def _make_quit_app(window, lifecycle):
    """重啟用的退出動作：有托盤走托盤的結束路徑（不手設 quitting，否則收尾會被略過）。"""
    if lifecycle is not None:
        return lambda: lifecycle.handle_tray_command(CMD_QUIT)
    return _destroy_all_windows


def _destroy_all_windows():
    """沒有 lifecycle 時的退出：主視窗與 CF 隱藏視窗都要關，否則 GUI 迴圈不返回。"""
    for w in list(webview.windows):
        with contextlib.suppress(Exception):
            w.destroy()


def _native_notice(message, logger):
    if sys.platform == "win32":
        _win_message_box(message, "OpenAver", yes_no=False)
    elif sys.platform == "darwin":
        subprocess.run(["osascript", "-e", "on run argv", "-e",
            'display dialog (item 1 of argv) with title "OpenAver" buttons {"OK"} default button "OK" with icon stop',
            "-e", "end run", message], check=False)
    else:
        logger.error("啟動失敗：%s", message)


def _log_boot_exceptions(fn):
    def guarded(boot_state, quit_startup, logger, *args, **kwargs):
        try:
            return fn(boot_state, quit_startup, logger, *args, **kwargs)
        except Exception:
            logger.exception("啟動失敗處理失敗")
    return guarded


@_log_boot_exceptions
def _notify_if_page_silent(boot_state, quit_startup, logger, timeout=STARTUP_PAGE_READY_TIMEOUT,
                           clock=time.monotonic, sleep=time.sleep):
    deadline = clock() + timeout
    while not (boot_state.error_polled or boot_state.quitting):
        if clock() >= deadline:
            try:
                _native_notice(boot_state.native_message(), logger)
            finally:
                quit_startup()
            return
        sleep(0.1)


@_log_boot_exceptions
def _fail_boot(boot_state, quit_startup, logger, kind, detail=""):
    if not boot_state.set_error(kind, detail):
        return
    _notify_if_page_silent(boot_state, quit_startup, logger)


def _open_log_folder(log_path):
    path = Path(log_path)
    if not path.is_absolute():
        raise ValueError("invalid log path")
    folder = str(path.parent)
    if sys.platform == "win32":
        os.startfile(folder)
    else:
        subprocess.run(["open" if sys.platform == "darwin" else "xdg-open", folder], check=True)


def _arm_exit_backstop(delay=STARTUP_EXIT_BACKSTOP_S, exit_fn=None):
    def force_exit():
        time.sleep(delay)
        get_logger("standalone").warning("啟動期間強制結束")
        (exit_fn or os._exit)(0)
    thread = threading.Thread(target=force_exit, daemon=True)
    thread.start()
    return thread


def _make_startup_quit(window, lifecycle):
    quit_app = _make_quit_app(window, lifecycle)
    def quit_startup():
        _arm_exit_backstop()
        quit_app()
    return quit_startup


def _close_during_startup(boot_state, lifecycle):
    if not boot_state.request_quit():
        return False
    try:
        if lifecycle is not None:
            lifecycle.quit_now()
    finally:
        _arm_exit_backstop()
    return True


def _register_bridge_seams(window, lifecycle):
    """註冊 bridge 的兩個注入接縫（重啟、小頁文案）；兩種模式都要呼叫。"""
    quit_app = _make_quit_app(window, lifecycle)
    pywebview_api.set_restart_handler(lambda: restart.request_restart(quit_app))
    pywebview_api.set_offline_text_provider(shell_boot.offline_texts)
    shell_sync.install(pywebview_api)


def _restart_failed_notice(message):
    """重啟 spawn 失敗的告知；本身不得拋。"""
    with contextlib.suppress(Exception):
        if sys.platform == 'win32':
            try:
                _win_message_box(message, "OpenAver", yes_no=False)
                return
            except Exception:                                        # noqa: BLE001
                get_logger("standalone").debug("restart notice msgbox failed")
        show_error("OpenAver", message, None, None)


def _shutdown_and_maybe_restart(lifecycle):
    """GUI 迴圈返回後的收尾；spawn 一定在 shutdown_after_loop 之後。"""
    if lifecycle is not None:
        lifecycle.shutdown_after_loop()
    restart.spawn_if_requested(notify_error=_restart_failed_notice)


def _prepare_webview2_profile(logger):
    try:
        profile = get_data_root() / WEBVIEW2_PROFILE_DIR
        marker = profile / WEBVIEW2_STARTED_MARKER
        if marker.exists():
            shutil.rmtree(profile)
            logger.info("WebView2 profile 上次未載入完成，已清除重建")
        profile.mkdir(parents=True, exist_ok=True)
        marker.write_text("1", encoding="utf-8")
    except OSError as exc:
        logger.warning("WebView2 profile 不可用，退回暫存資料夾 (%s)", type(exc).__name__)
        return None
    return profile


def _dispose_keep_profile(self):
    try:
        edge = sys.modules["webview.platforms.edgechromium"]
        if not edge._state["private_mode"]:
            return
        pid = edge.Convert.ToInt32(self.webview.CoreWebView2.BrowserProcessId)
        proc = edge.Process.GetProcessById(pid)
        self.webview.Dispose()
        proc.WaitForExit(3000)
    except Exception:
        get_logger("standalone").warning("無法釋放 WebView2 瀏覽器程序", exc_info=True)


def _keep_webview2_profile_on_close(logger):
    try:
        edge = sys.modules["webview.platforms.edgechromium"]
        if not callable(getattr(edge.EdgeChrome, "clear_user_data", None)):
            raise AttributeError("clear_user_data")
        edge.EdgeChrome.clear_user_data = _dispose_keep_profile
    except (KeyError, AttributeError) as exc:
        logger.warning("無法保留 WebView2 profile，關閉時將照舊清除 (%s)", type(exc).__name__)


def _start_gui_windows(startup, window):
    logger = get_logger("standalone")
    profile = _prepare_webview2_profile(logger)
    callback = startup
    if profile is not None:
        def on_loaded():
            with contextlib.suppress(OSError):
                (profile / WEBVIEW2_STARTED_MARKER).unlink(missing_ok=True)
        try:
            window.events.loaded += on_loaded
        except Exception:
            logger.warning("無法訂閱 WebView2 載入事件", exc_info=True)
        def callback(*args):
            _keep_webview2_profile_on_close(logger)
            startup(*args)
    webview.start(callback, window, gui='edgechromium', private_mode=True,
                  storage_path=None if profile is None else str(profile), icon=app_icon.icon_path(APP_DIR))


def _start_gui(startup, window):
    if sys.platform == 'darwin':
        webview.start(startup, window, icon=app_icon.icon_path(APP_DIR))  # macOS 使用預設 (Cocoa/WebKit)
    elif sys.platform == 'win32':
        _start_gui_windows(startup, window)
    else:
        webview.start(startup, window, gui='edgechromium', icon=app_icon.icon_path(APP_DIR))  # Windows


def _make_cf_agent(cf_set, origin, token, server_remote, supported):
    """建 CF 殼 agent 並把它的唯讀狀態交給連線頁（bridge 只讀、不動視窗）。"""
    agent = cf_shell.CfShellAgent(origin=origin, token=token, windows=cf_set,
                                  server_remote=server_remote, supported=supported)
    pywebview_api.set_cf_status_provider(agent.public_status)
    pywebview_api.set_cf_retry_handler(cf_boot.agent_retry_handler(agent))   # 本機版的「重試」＝重讀，不補建
    return agent


def _make_page_loaded_subscriber(boot_state):
    def on_loaded(kind, window, gen):
        if gen != pywebview_api.api._nav_gen:
            return
        if kind == "startup":
            startup_trace.mark("startup_screen_shown")
        elif kind in ("server", "offline"):
            boot_state.mark_ready()
            startup_trace.mark("first_page_loaded")
    return on_loaded


def _arm_page_marks(boot_state):
    pywebview_api.set_page_loaded_subscriber(_make_page_loaded_subscriber(boot_state))


def _start_boot_worker(worker, *args):
    thread = threading.Thread(target=worker, args=args, name="oa-boot-worker", daemon=True)
    thread.start()
    return thread


def _shutdown_lan_listener_if_loaded():
    module = sys.modules.get("web.lan_listener")
    if module is not None:
        module.lan_listener.shutdown()


def _wait_startup_page_shown(boot_state, logger):
    deadline = time.monotonic() + STARTUP_PAGE_WAIT_S
    while api._page_kind != "startup":
        if boot_state.quitting or boot_state.phase != "starting":
            return
        if time.monotonic() >= deadline:
            logger.warning("等待啟動畫面超過 %.1f 秒，直接導向首頁", STARTUP_PAGE_WAIT_S)
            return
        time.sleep(STARTUP_PAGE_POLL_S)


def _local_boot_worker(window, boot_state, logger, debug_mode, cf_set, cf_supported, cf_agent_box, quit_startup):
    try:
        try:
            port = find_free_port(PORT, logger)
        except RuntimeError as exc:
            _fail_boot(boot_state, quit_startup, logger, "no_port", str(exc))
            return
        logger.info("使用端口: %s", port)
        server_thread = threading.Thread(target=run_server, args=(port, debug_mode), daemon=True)
        server_thread.start()
        startup_trace.mark("server_thread_started")
        result = wait_for_server(port, server_thread, cancelled=lambda: boot_state.quitting)
        if result != PROBE_OK:
            if result == PROBE_CANCELLED:
                return
            logger.error("伺服器啟動失敗 result=%s", result)
            _fail_boot(boot_state, quit_startup, logger, "timeout" if result == PROBE_TIMEOUT else "died")
            return
        startup_trace.mark("server_ready")
        from web.app import app as _app
        from web.lan_listener import lan_listener
        lan_listener.wire(_app, local_port=port)
        _maybe_autostart_lan_listener(lan_listener, logger)
        local_origin = f'http://{CLIENT_HOST}:{port}'
        cf_agent = _make_cf_agent(cf_set, local_origin, None, False, cf_supported)
        cf_agent_box["agent"] = cf_agent
        cf_agent.announce()
        cf_agent.start()
        boot = shell_boot.resolve_boot(local_origin, client_settings.shell_kind())
        api._set_trusted_origin(client_settings.server_origin(local_origin))
        _wait_startup_page_shown(boot_state, logger)
        if not boot_state.claim_navigation():
            return
        window.load_url(boot.url)
    except Exception:
        logger.exception("本機啟動失敗")
        _fail_boot(boot_state, quit_startup, logger, "died")


def _run_client_mode(logger):
    """連線模式：只開殼，不起任何本機服務。"""
    import window_state
    saved = window_state.load_state()
    theme = client_settings.shell_theme()
    log_path = health_probe._debug_log_hint()
    boot_state = startup_boot.BootState(client_settings.tray_locale(), theme, log_path)
    local_origin = f'http://{CLIENT_HOST}:{PORT}'
    boot = shell_boot.BootTarget("startup", STARTUP_PAGE, "OpenAver", None)
    window = _create_main_window(boot, saved, startup_boot.background_color(theme, startup_boot.system_prefers_dark()))
    startup_trace.mark("main_window_created")
    lifecycle = _setup_windows_lifecycle(window, None, None, saved, None)
    _register_bridge_seams(window, lifecycle)
    quit_startup = _make_startup_quit(window, lifecycle)
    pywebview_api.set_startup_state_provider(boot_state.get_state)
    pywebview_api.set_startup_log_opener(lambda: _open_log_folder(log_path))
    pywebview_api.set_startup_quit_handler(quit_startup)
    cf_box = {"cf": None}
    cf_quitting = {"v": False}
    is_quitting = lambda: lifecycle.quitting if lifecycle is not None else cf_quitting["v"]

    def _on_main_closing():
        starting = _close_during_startup(boot_state, lifecycle)
        if lifecycle is not None:
            if starting:
                return None
            return lifecycle.on_window_closing()
        cf_quitting["v"] = True
        if cf_box["cf"] is not None:
            cf_box["cf"].destroy_all()
        return None

    window.events.closing += _on_main_closing

    def boot_worker():
        try:
            boot = shell_boot.resolve_boot(local_origin, client_settings.shell_kind())
            startup_trace.mark("client_preflight_done")
            cf = cf_boot.CfShellController(logger, boot.kind, local_origin)
            cf_box["cf"] = cf
            pywebview_api.set_cf_status_provider(cf.status)
            pywebview_api.set_cf_retry_handler(cf.retry)
            cf.bind(lifecycle, is_quitting)
            cf.initial()
            if cf.agent is not None:
                startup_trace.mark("cf_windows_created")
            cf.announce_initial()
            cf.start()
            if boot.kind == "offline":
                api._set_offline_state(boot.offline.reason, boot.offline.failed_url)
            else:
                window.set_title(boot.title)
                api._set_trusted_origin(client_settings.server_origin(local_origin))
            _wait_startup_page_shown(boot_state, logger)
            if not boot_state.claim_navigation():
                return
            if boot.kind == "offline":
                api._expect_offline()
            window.load_url(boot.url)
        except Exception:
            logger.exception("client 啟動失敗")
            _fail_boot(boot_state, quit_startup, logger, "died")

    def startup(w):
        _arm_page_marks(boot_state)
        _attach_window_state(w, saved, lifecycle, logger)
        update_notice.start_background_check()
        _start_boot_worker(boot_worker)

    try:
        _start_gui(startup, window)
    finally:
        if cf_box["cf"] is not None:
            cf_box["cf"].stop()
        _shutdown_and_maybe_restart(lifecycle)
        _arm_exit_backstop()


def main():
    # 檢查 DEBUG 環境變數
    debug_mode = os.environ.get('OPENAVER_DEBUG', '0') == '1'
    console_level = logging.DEBUG if debug_mode else logging.INFO
    setup_logging(console_level=console_level)
    logger = get_logger('standalone')
    startup_trace.flush()
    restart.wait_for_parent_exit()
    shell_boot.install_webview_token_filter()
    app_icon.set_windows_app_id()   # 須早於任何視窗（含 WebView2 提示框與 CF 隱藏視窗）

    logger.info("正在啟動...")

    # 0. 檢查 WebView2（僅 Windows）
    _ensure_webview2_runtime(logger)

    # 1. 標記為 Windows 桌面 App（feature/82 T4：_is_windows_desktop() 讀此環境變數）
    # 必須在任何 web.app import 之前設定，確保 get_common_context 能正確判斷。
    os.environ["OPENAVER_STANDALONE"] = "1"

    # 1b. 資料根定版（必須在 port／server thread／視窗之前；失敗即中止啟動）
    _bootstrap_data_layout_or_exit(logger)
    startup_trace.mark("data_root_ready")
    if client_settings.mode() == "client":
        _run_client_mode(logger)
        return

    theme = client_settings.shell_theme()
    log_path = health_probe._debug_log_hint()
    boot_state = startup_boot.BootState(client_settings.tray_locale(), theme, log_path)
    logger.info("啟動視窗...")
    webview.settings['OPEN_DEVTOOLS_IN_DEBUG'] = False

    import window_state
    saved = window_state.load_state()
    boot = shell_boot.BootTarget("startup", STARTUP_PAGE, "OpenAver", None)
    window = _create_main_window(boot, saved, startup_boot.background_color(theme))
    startup_trace.mark("main_window_created")

    cf_supported = cf_windows.cf_shell_supported()
    cf_set = cf_windows.build_cf_windows(logger, current_settings()) if cf_supported else cf_windows.CfWindowSet()
    startup_trace.mark("cf_windows_created")
    jl_win, javten_win = cf_set.jl_win, cf_set.javten_win
    cf_agent_box = {"agent": None}

    # CD-70c-2 Layer 1: closing a hidden CF window hides it instead of destroying it
    # (cf_windows.attach_close_guards); app-quit lets it close so we don't trap the shutdown sequence.
    _app_state = {"quitting": False}
    lifecycle = _setup_windows_lifecycle(window, jl_win, javten_win, saved,
                                         types.SimpleNamespace(shutdown=_shutdown_lan_listener_if_loaded))
    _register_bridge_seams(window, lifecycle)
    quit_startup = _make_startup_quit(window, lifecycle)
    pywebview_api.set_startup_state_provider(boot_state.get_state)
    pywebview_api.set_startup_log_opener(lambda: _open_log_folder(log_path))
    pywebview_api.set_startup_quit_handler(quit_startup)

    def _on_main_closing():
        starting = _close_during_startup(boot_state, lifecycle)
        if lifecycle is not None:
            if starting:
                return None
            result = lifecycle.on_window_closing()
            _app_state["quitting"] = lifecycle.quitting
            return result
        # Non-Windows launchers keep the original close-to-exit behaviour.
        # CD-118a-4b: both transport windows must be destroyed here, not just jl_win —
        # a window left un-destroyed keeps pywebview's instance count above 0 forever.
        _app_state["quitting"] = True
        if jl_win is not None:
            try:
                jl_win.destroy()
            except Exception:
                logger.warning("failed to destroy JL window on app close")
        if javten_win is not None:
            try:
                javten_win.destroy()
            except Exception:
                logger.warning("failed to destroy javten window on app close")
        _shutdown_lan_listener_if_loaded()

    window.events.closing += _on_main_closing
    cf_windows.attach_close_guards(
        cf_set, lambda: lifecycle.quitting if lifecycle is not None else _app_state["quitting"])

    def startup(w):
        _arm_page_marks(boot_state)
        _attach_window_state(w, saved, lifecycle, logger)
        _start_boot_worker(_local_boot_worker, w, boot_state, logger, debug_mode,
                           cf_set, cf_supported, cf_agent_box, quit_startup)

    # 5. 開始 GUI 事件循環（阻塞直到窗口關閉）
    # 根據平台選擇 GUI 後端
    try:
        _start_gui(startup, window)
    finally:
        try:
            if cf_agent_box["agent"] is not None:
                cf_agent_box["agent"].stop()
        finally:
            _shutdown_and_maybe_restart(lifecycle)
            _arm_exit_backstop()


if __name__ == '__main__':
    try:
        main()
    except ImportError as e:
        show_error(
            "啟動失敗 - 缺少依賴",
            "缺少必要的 Python 套件。\n\n請確認是否使用打包版執行，或檢查虛擬環境。",
            str(e)
        )
        sys.exit(1)
    except PermissionError as e:
        show_error(
            "啟動失敗 - 權限不足",
            "無法存取必要的檔案或目錄。\n\n請以一般使用者權限執行（不要用管理員）。",
            str(e)
        )
        sys.exit(1)
    except Exception as e:
        error_details = traceback.format_exc()
        # 嘗試取得 logger 寫入錯誤（可能尚未初始化）
        try:
            err_logger = get_logger('standalone')
            err_logger.error(f"未預期的錯誤：{e}\n{error_details}")
        except Exception:  # noqa: S110 — logger may not be initialized at startup crash; silent fallback is intentional
            pass
        show_error(
            "啟動失敗 - 未知錯誤",
            "OpenAver 啟動時發生錯誤。\n\n請將錯誤詳情回報到 GitHub Issues。",
            error_details
        )
        sys.exit(1)
