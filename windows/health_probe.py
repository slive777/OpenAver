"""
OpenAver Windows 伺服器生命週期與探活模組

提供 uvicorn 伺服器啟動 (run_server) 與本機 loopback 探活 (wait_for_server)。
脫離 pywebview 依賴，可在無 GUI / Linux 環境下進行獨立測試。
"""
import http.client
import time
import urllib.error
import urllib.request
from pathlib import Path

from core.logger import get_logger

logger = get_logger(__name__)

# 配置
CLIENT_HOST = "127.0.0.1"  # 桌面 App 自連：find_free_port、health 探活、WebView URL（loopback only）
STARTUP_TIMEOUT = 30  # 最多等待 30 秒

PROBE_OK = "ok"
PROBE_TIMEOUT = "timeout"
PROBE_THREAD_DIED = "thread_died"
PROBE_CANCELLED = "cancelled"


def wait_for_server(port, server_thread, timeout=STARTUP_TIMEOUT, cancelled=None) -> str:
    """等待伺服器啟動；回傳 PROBE_OK / PROBE_TIMEOUT / PROBE_THREAD_DIED。"""
    url = f"http://{CLIENT_HOST}:{port}/api/health"
    start_time = time.monotonic()
    _opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    last_exc = None

    while True:
        if cancelled is not None and cancelled():
            return PROBE_CANCELLED
        # 先查 thread 存活，再查逾時（死掉 × 已逾時 → thread_died）
        if not server_thread.is_alive():
            if last_exc is not None:
                logger.warning(
                    "伺服器 thread 已中止，最後一次探活失敗：%s: %s",
                    type(last_exc).__name__,
                    last_exc,
                )
            else:
                logger.warning("伺服器 thread 已中止")
            return PROBE_THREAD_DIED

        if time.monotonic() - start_time >= timeout:
            if last_exc is not None:
                logger.warning("探活未成功，最後一次失敗：%s: %s", type(last_exc).__name__, last_exc)
            return PROBE_TIMEOUT

        try:
            with _opener.open(url, timeout=1) as response:
                if response.status == 200:
                    return PROBE_OK
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, http.client.HTTPException) as exc:
            last_exc = exc
        time.sleep(0.2)


def _debug_log_hint() -> str:
    """使用者要去哪裡找 debug.log。

    路徑必須與 core/logger.py 的預設一致 —— 目錄在 core/logger.py:34-35
    （`log_dir = Path.home() / "OpenAver" / "logs"`）、檔名在 core/logger.py:39
    （`log_file = log_dir / "debug.log"`）。那邊改了這邊要跟著改。

    這裡不依賴 core.logger 的私有狀態，因為日誌系統可能尚未初始化。

    ⚠️ 這是一組「靠兩處常數相等才成立」的機制。守住它的是
    tests/unit/test_health_probe_lifecycle.py::test_debug_log_hint_matches_core_logger_default
    —— 那支測試直接掃 core/logger.py 的原始碼。**改這裡或改那裡都會讓它轉紅，這是刻意的。**
    """
    try:
        return str(Path.home() / "OpenAver" / "logs" / "debug.log")
    except RuntimeError:
        return "OpenAver 的 logs 資料夾"


def run_server(port, debug_mode=False):
    """在背景執行 uvicorn 伺服器"""
    try:
        import uvicorn
        from web.app import app

        # Debug 模式顯示完整 HTTP 請求 log
        if debug_mode:
            log_level = "debug"
            access_log = True
        else:
            log_level = "warning"
            access_log = False

        config = uvicorn.Config(
            app,
            host=CLIENT_HOST,
            port=port,
            log_level=log_level,
            access_log=access_log,
        )
        server = uvicorn.Server(config)
        server.run()
    except Exception:
        logger.exception("伺服器 thread 發生未預期例外")
