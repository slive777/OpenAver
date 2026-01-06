"""
JavHelper Windows Launcher
使用 PyWebView 連接 WSL 後端服務
"""
import webview


class Api:
    """供前端 JS 調用的 Python API"""

    def convert_path(self, win_path):
        """
        將 Windows 路徑轉換為 WSL 路徑
        C:\\Users\\peace\\Downloads\\SONE-205.mp4
        → /mnt/c/Users/peace/Downloads/SONE-205.mp4
        """
        if win_path and len(win_path) >= 2 and win_path[1] == ':':
            drive = win_path[0].lower()
            rest = win_path[2:].replace('\\', '/')
            return f'/mnt/{drive}{rest}'
        return win_path


if __name__ == '__main__':
    api = Api()
    window = webview.create_window(
        'JavHelper',
        'http://localhost:8000',
        js_api=api,
        width=1200,
        height=800
    )
    webview.start()
