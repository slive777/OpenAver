"""
JavHelper Windows Launcher
使用 PyWebView 連接 WSL 後端服務
"""
import webview
from pywebview_api import api, bind_events

if __name__ == '__main__':
    window = webview.create_window(
        'JavHelper',
        'http://localhost:8000',
        js_api=api,
        width=1200,
        height=800
    )
    webview.start(bind_events, window)
