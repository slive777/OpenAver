"""
JavHelper Windows 單機版啟動器
整合 FastAPI 後端 + PyWebView 前端於同一進程
"""
import os
import sys
import time
import threading
import socket
import urllib.request
import urllib.error

# 確保專案根目錄在 sys.path 中
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

# 確保 windows 目錄也在 sys.path 中（for pywebview_api import）
WINDOWS_DIR = os.path.dirname(os.path.abspath(__file__))
if WINDOWS_DIR not in sys.path:
    sys.path.insert(0, WINDOWS_DIR)

import webview
from pywebview_api import api, bind_events

# 配置
HOST = "127.0.0.1"
PORT = 8000
STARTUP_TIMEOUT = 30  # 最多等待 30 秒


def find_free_port(start_port=8000, max_attempts=100):
    """尋找可用端口"""
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind((HOST, port))
                return port
        except OSError:
            continue
    raise RuntimeError(f"無法找到可用端口 ({start_port}-{start_port + max_attempts})")


def wait_for_server(port, timeout=STARTUP_TIMEOUT):
    """等待伺服器啟動"""
    url = f"http://{HOST}:{port}/api/health"
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ConnectionRefusedError):
            pass
        time.sleep(0.2)

    return False


def run_server(port):
    """在背景執行 uvicorn 伺服器"""
    import uvicorn
    from web.app import app

    config = uvicorn.Config(
        app,
        host=HOST,
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    server.run()


# ============ 主程序 ============

def main():
    print("[JavHelper] 正在啟動...")

    # 1. 尋找可用端口
    port = find_free_port(PORT)
    print(f"[JavHelper] 使用端口: {port}")

    # 2. 在背景 thread 啟動 FastAPI
    server_thread = threading.Thread(target=run_server, args=(port,), daemon=True)
    server_thread.start()
    print("[JavHelper] 正在啟動伺服器...")

    # 3. 等待伺服器就緒
    if not wait_for_server(port):
        print("[JavHelper] 錯誤：伺服器啟動逾時")
        sys.exit(1)
    print("[JavHelper] 伺服器已就緒")

    # 4. 隱藏控制台視窗（Windows 限定）
    try:
        import ctypes
        ctypes.windll.user32.ShowWindow(
            ctypes.windll.kernel32.GetConsoleWindow(), 0
        )
    except Exception:
        pass  # 非 Windows 或無控制台時忽略

    # 5. 啟動 PyWebView 窗口
    webview.settings['OPEN_DEVTOOLS_IN_DEBUG'] = False

    window = webview.create_window(
        'JavHelper',
        f'http://{HOST}:{port}',
        js_api=api,
        width=1200,
        height=800
    )

    # 6. 開始 GUI 事件循環（阻塞直到窗口關閉）
    # 使用 EdgeChromium 後端（Windows 10/11 內建，不需要 .NET）
    # debug=True 可開啟 F12 開發者工具
    webview.start(bind_events, window, debug=True, gui='edgechromium')


if __name__ == '__main__':
    main()
