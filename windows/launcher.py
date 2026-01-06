"""
JavHelper Windows Launcher
使用 PyWebView 連接 WSL 後端服務
"""
import webview
from webview.dom import DOMEventHandler


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
    """處理拖放事件，取得完整路徑並傳給前端"""
    global window

    print("[DEBUG] on_drop 被觸發")
    print(f"[DEBUG] event: {e}")

    files = e.get('dataTransfer', {}).get('files', [])
    if not files:
        print("[DEBUG] 沒有檔案")
        return

    # 取得第一個檔案的完整路徑
    file_info = files[0]
    print(f"[DEBUG] file_info: {file_info}")

    full_path = file_info.get('pywebviewFullPath', '')
    print(f"[DEBUG] Windows 路徑: {full_path}")

    if full_path:
        # 轉換為 WSL 路徑
        wsl_path = api.convert_path(full_path)
        print(f"[DEBUG] WSL 路徑: {wsl_path}")

        # 呼叫前端 JS 函數（需要跳脫引號）
        wsl_path_escaped = wsl_path.replace('\\', '\\\\').replace('"', '\\"')
        js_code = f'handlePyWebViewDrop("{wsl_path_escaped}")'
        print(f"[DEBUG] 執行 JS: {js_code}")
        window.evaluate_js(js_code)


def bind(w):
    """綁定 DOM 事件"""
    global window
    window = w
    print("[DEBUG] 綁定 drop 事件")
    # 訂閱 drop 事件（prevent_default=True, stop_propagation=True）
    window.dom.document.events.drop += DOMEventHandler(on_drop, True, True)


if __name__ == '__main__':
    window = webview.create_window(
        'JavHelper',
        'http://localhost:8000',
        js_api=api,
        width=1200,
        height=800
    )
    webview.start(bind, window)
