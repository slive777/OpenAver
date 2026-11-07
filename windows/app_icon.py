"""殼程式的應用程式圖示（Windows 工作列／Alt+Tab、macOS Dock）。

沒傳 icon 時，pywebview 在 Windows 會改用 `pythonw.exe` 的圖示、在 macOS 顯示 Python 火箭。
圖檔由 `web/static/favicon.svg` 一次產好提交（`openaver.ico` 多尺寸、`openaver.icns`），
執行期不轉檔；檔案不在就回 None，pywebview 退回原本的預設圖示，不影響啟動。
"""
import sys
from pathlib import Path

from core.logger import get_logger

logger = get_logger("app_icon")

# Windows 工作列依 AppUserModelID 分組並決定按鈕圖示；不設就會跟其他 Python 程式歸成同一組、顯示 Python 圖示
APP_USER_MODEL_ID = "OpenAver.App"


def icon_path(app_dir) -> str | None:
    """依平台回傳 `webview.start(icon=...)` 要的圖檔路徑（Windows .ico、macOS .icns）。"""
    name = "openaver.icns" if sys.platform == "darwin" else "openaver.ico"
    path = Path(app_dir) / "web" / "static" / name
    if path.is_file():
        return str(path)
    logger.warning("app icon not found: %s", path)
    return None


def set_windows_app_id() -> None:
    """Windows only：必須在建任何視窗之前呼叫；失敗只記 log，不影響啟動。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        logger.warning("failed to set AppUserModelID", exc_info=True)
