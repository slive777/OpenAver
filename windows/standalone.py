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

import webview
from webview.dom import DOMEventHandler

# 配置
HOST = "127.0.0.1"
PORT = 8000
STARTUP_TIMEOUT = 30  # 最多等待 30 秒

# 支援的影片副檔名
VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mkv', '.wmv', '.rmvb', '.flv', '.mov', '.m4v', '.ts'}


def is_video_file(filename):
    """檢查是否為影片檔案"""
    ext = os.path.splitext(filename)[1].lower()
    return ext in VIDEO_EXTENSIONS


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


# ============ PyWebView API ============

class Api:
    """供前端 JS 調用的 Python API"""

    def select_files(self):
        """開啟檔案選擇對話框，選取影片檔案"""
        global window
        file_types = ('影片檔案 (*.mp4;*.avi;*.mkv;*.wmv;*.rmvb;*.flv;*.mov;*.m4v;*.ts)',
                      '所有檔案 (*.*)')
        result = window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=True,
            file_types=file_types
        )
        if result:
            return list(result)
        return []

    def select_folder(self):
        """開啟資料夾選擇對話框，展開內部影片檔案"""
        global window
        result = window.create_file_dialog(webview.FOLDER_DIALOG)
        if result and len(result) > 0:
            folder_path = result[0]
            files = []
            for f in os.listdir(folder_path):
                file_path = os.path.join(folder_path, f)
                if os.path.isfile(file_path) and is_video_file(f):
                    files.append(file_path)
            return files
        return []

    def select_folder_path(self):
        """開啟資料夾選擇對話框，返回資料夾路徑"""
        global window
        result = window.create_file_dialog(webview.FOLDER_DIALOG)
        if result and len(result) > 0:
            return result[0]
        return None

    def open_file(self, path):
        """用系統預設程式開啟檔案"""
        if os.path.exists(path):
            os.startfile(path)
            return True
        return False


api = Api()
window = None


def on_drop(e):
    """處理拖放事件，取得完整路徑並傳給前端"""
    global window
    import json

    files = e.get('dataTransfer', {}).get('files', [])
    if not files:
        return

    expanded_paths = []  # 影片檔案路徑
    folder_paths = []    # 資料夾路徑

    for file_info in files:
        win_path = file_info.get('pywebviewFullPath', '')
        if not win_path:
            continue

        if os.path.isdir(win_path):
            # 記錄資料夾路徑（給 avlist 用）
            folder_paths.append(win_path)
            # 資料夾：展開第一層影片檔案（給 search 用）
            for f in os.listdir(win_path):
                file_win_path = os.path.join(win_path, f)
                if os.path.isfile(file_win_path) and is_video_file(f):
                    expanded_paths.append(file_win_path)
        else:
            expanded_paths.append(win_path)

    # 傳送影片檔案路徑（search 頁面用）
    if expanded_paths:
        paths_json = json.dumps(expanded_paths)
        window.evaluate_js(f'if(typeof handlePyWebViewDrop === "function") handlePyWebViewDrop({paths_json})')

    # 傳送資料夾路徑（avlist 頁面用）
    if folder_paths:
        folders_json = json.dumps(folder_paths)
        window.evaluate_js(f'if(typeof handleFolderDrop === "function") handleFolderDrop({folders_json})')


def bind(w):
    """綁定 DOM 事件"""
    global window
    window = w

    def on_loaded():
        window.dom.document.events.drop += DOMEventHandler(on_drop, True, True)

    window.events.loaded += on_loaded


# ============ 主程序 ============

def main():
    global window

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
    webview.start(bind, window, debug=False, gui='edgechromium')


if __name__ == '__main__':
    main()
