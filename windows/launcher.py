"""
JavHelper Windows Launcher
使用 PyWebView 連接 WSL 後端服務
"""
import os
import webview
from webview.dom import DOMEventHandler

# 支援的影片副檔名
VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mkv', '.wmv', '.rmvb', '.flv', '.mov', '.m4v', '.ts'}


def is_video_file(filename):
    """檢查是否為影片檔案"""
    ext = os.path.splitext(filename)[1].lower()
    return ext in VIDEO_EXTENSIONS


class Api:
    """供前端 JS 調用的 Python API"""

    def convert_path(self, win_path):
        """
        將 Windows 路徑轉換為 WSL 路徑

        支援格式：
        1. C:\\Users\\peace\\... → /mnt/c/Users/peace/...
        2. \\\\wsl.localhost\\Ubuntu-24.04\\home\\... → /home/...
        """
        if not win_path:
            return win_path

        # 格式1: WSL 網路路徑 (\\wsl.localhost\distro\path 或 \\wsl$\distro\path)
        if win_path.startswith('\\\\wsl.localhost\\') or win_path.startswith('\\\\wsl$\\'):
            # 移除 \\wsl.localhost\ 或 \\wsl$\
            path = win_path.replace('\\\\wsl.localhost\\', '').replace('\\\\wsl$\\', '')
            # 移除發行版名稱 (第一個 \ 之前的部分，如 Ubuntu-24.04)
            parts = path.split('\\', 1)
            if len(parts) > 1:
                wsl_path = '/' + parts[1].replace('\\', '/')
                return wsl_path
            return '/'

        # 格式2: Windows 本地路徑 (C:\Users\...)
        if len(win_path) >= 2 and win_path[1] == ':':
            drive = win_path[0].lower()
            rest = win_path[2:].replace('\\', '/')
            return f'/mnt/{drive}{rest}'

        return win_path


# 全域變數
api = Api()
window = None


def on_drop(e):
    """處理拖放事件，取得完整路徑並傳給前端（支援多檔案和資料夾）"""
    global window
    import json

    print("[DEBUG] on_drop 被觸發")

    files = e.get('dataTransfer', {}).get('files', [])
    if not files:
        print("[DEBUG] 沒有檔案")
        return

    # 收集所有項目（用 Windows 路徑判斷檔案/資料夾）
    expanded_paths = []
    for file_info in files:
        win_path = file_info.get('pywebviewFullPath', '')
        if not win_path:
            continue

        if os.path.isdir(win_path):
            # 資料夾：展開第一層影片檔案
            print(f"[DEBUG] 展開資料夾: {win_path}")
            for f in os.listdir(win_path):
                file_win_path = os.path.join(win_path, f)
                if os.path.isfile(file_win_path) and is_video_file(f):
                    wsl_path = api.convert_path(file_win_path)
                    expanded_paths.append(wsl_path)
                    print(f"[DEBUG]   + {f} → {wsl_path}")
        else:
            # 檔案：直接加入
            wsl_path = api.convert_path(win_path)
            expanded_paths.append(wsl_path)
            print(f"[DEBUG] {win_path} → {wsl_path}")

    if expanded_paths:
        # 傳送 JSON array 給前端
        paths_json = json.dumps(expanded_paths)
        js_code = f'handlePyWebViewDrop({paths_json})'
        print(f"[DEBUG] 執行 JS: handlePyWebViewDrop({len(expanded_paths)} 個檔案)")
        window.evaluate_js(js_code)


def bind(w):
    """綁定 DOM 事件"""
    global window
    window = w

    def on_loaded():
        """每次頁面加載後綁定 drop 事件"""
        print("[DEBUG] 頁面加載完成，綁定 drop 事件")
        window.dom.document.events.drop += DOMEventHandler(on_drop, True, True)

    # 監聽頁面加載事件（每次導航後都會觸發）
    window.events.loaded += on_loaded


if __name__ == '__main__':
    # 關閉自動開啟 DevTools，但保留右鍵選單
    webview.settings['OPEN_DEVTOOLS_IN_DEBUG'] = False

    window = webview.create_window(
        'JavHelper',
        'http://localhost:8000',
        js_api=api,
        width=1200,
        height=800
    )
    webview.start(bind, window, debug=True)
