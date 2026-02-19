"""
OpenAver Windows Launcher
使用 PyWebView 連接 WSL 後端服務
"""
import os
import sys

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

if __name__ == '__main__':
    window = webview.create_window(
        'OpenAver',
        'http://localhost:8000',
        js_api=api,
        width=1200,
        height=800
    )
    webview.start(bind_events, window)
