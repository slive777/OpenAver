"""
OpenAver PyWebView 共用 API 模組
供 launcher.py 和 standalone.py 共用
"""
import os
import json
import subprocess
import webview
from pathlib import Path
from urllib.parse import unquote
from webview.dom import DOMEventHandler

# 支援的影片副檔名
VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mkv', '.wmv', '.rmvb', '.flv', '.mov', '.m4v', '.ts'}

# 全域 window 參考（由 launcher/standalone 設定）
_window = None


def set_window(w):
    """設定全域 window 參考"""
    global _window
    _window = w


def get_window():
    """取得全域 window 參考"""
    return _window


def is_video_file(filename):
    """檢查是否為影片檔案"""
    ext = os.path.splitext(filename)[1].lower()
    return ext in VIDEO_EXTENSIONS


class Api:
    """供前端 JS 調用的 Python API"""

    def select_files(self):
        """
        開啟檔案選擇對話框，選取影片檔案
        Returns: 選取的檔案路徑陣列（Windows 路徑）
        """
        window = get_window()
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
        """
        開啟資料夾選擇對話框，返回資料夾路徑和內部影片檔案
        Returns: { folder: 資料夾路徑, files: 影片檔案陣列 }
        """
        window = get_window()
        result = window.create_file_dialog(webview.FOLDER_DIALOG)
        if result and len(result) > 0:
            folder_path = result[0]
            # 展開第一層影片檔案
            files = []
            for f in os.listdir(folder_path):
                file_path = os.path.join(folder_path, f)
                if os.path.isfile(file_path) and is_video_file(f):
                    files.append(file_path)
            # 返回資料夾路徑和檔案列表（AVList 用 folder，Search 用 files）
            return {"folder": folder_path, "files": files}
        return None

    def select_folder_path(self):
        """開啟資料夾選擇對話框，只返回資料夾路徑"""
        window = get_window()
        result = window.create_file_dialog(webview.FOLDER_DIALOG)
        if result and len(result) > 0:
            return result[0]
        return None

    def open_file(self, path):
        """用系統預設程式或指定播放器開啟檔案

        支援格式：
        - file:///C:/path/to/file.mp4
        - C:/path/to/file.mp4
        - C:\\path\\to\\file.mp4
        """
        # 移除 file:/// 前綴
        if path.startswith('file:///'):
            path = path[8:]  # 移除 'file:///'

        # URL decode（處理 %20 等編碼）
        path = unquote(path)

        # 轉換斜線為反斜線（Windows 格式）
        path = path.replace('/', '\\')

        if not os.path.exists(path):
            return False

        # 讀取設定，檢查是否有指定播放器
        player = self._get_player_path()

        if player and os.path.exists(player):
            try:
                subprocess.Popen([player, path])
                return True
            except Exception:
                # fallback 到系統預設
                os.startfile(path)
                return True
        else:
            # 使用系統預設程式
            os.startfile(path)
            return True

    def _get_player_path(self):
        """從設定檔讀取播放器路徑"""
        try:
            # 嘗試多個可能的設定檔路徑
            possible_paths = [
                Path(__file__).parent.parent / 'web' / 'config.json',
                Path(__file__).parent / 'config.json',
            ]
            for config_path in possible_paths:
                if config_path.exists():
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                        return config.get('showcase', {}).get('player', '')
        except Exception:
            pass
        return ''


def on_drop(e):
    """處理拖放事件，取得完整路徑並傳給前端（支援多檔案和資料夾）"""
    window = get_window()

    files = e.get('dataTransfer', {}).get('files', [])
    if not files:
        return

    # 收集所有項目
    expanded_paths = []  # 影片檔案路徑（給 search 用）
    folder_paths = []    # 資料夾路徑（給 avlist 用）

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
            # 檔案：直接加入
            expanded_paths.append(win_path)

    # 傳送影片檔案路徑（search 頁面用）
    if expanded_paths:
        paths_json = json.dumps(expanded_paths)
        window.evaluate_js(f'if(typeof handlePyWebViewDrop === "function") handlePyWebViewDrop({paths_json})')

    # 傳送資料夾路徑（avlist 頁面用）
    if folder_paths:
        folders_json = json.dumps(folder_paths)
        window.evaluate_js(f'if(typeof handleFolderDrop === "function") handleFolderDrop({folders_json})')


def bind_events(w):
    """綁定 DOM 事件（頁面加載後綁定 drop 事件）"""
    set_window(w)

    def on_loaded():
        """每次頁面加載後綁定 drop 事件"""
        window = get_window()
        window.dom.document.events.drop += DOMEventHandler(on_drop, True, True)

    # 監聯頁面加載事件（每次導航後都會觸發）
    w.events.loaded += on_loaded


# 建立全域 api 實例
api = Api()
