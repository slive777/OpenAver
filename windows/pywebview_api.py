"""
OpenAver PyWebView 共用 API 模組
供 launcher.py 和 standalone.py 共用
"""
import os
import sys
import json
import subprocess
import webview
from pathlib import Path
from core.path_utils import uri_to_fs_path
from core.video_extensions import DEFAULT_VIDEO_EXTENSIONS, get_video_extensions
from webview.dom import DOMEventHandler

# 支援的影片副檔名（from core.video_extensions Single Source of Truth）
VIDEO_EXTENSIONS = set(DEFAULT_VIDEO_EXTENSIONS)

# 全域 window 參考（由 launcher/standalone 設定）
_window = None


def set_window(w):
    """設定全域 window 參考"""
    global _window
    _window = w


def get_window():
    """取得全域 window 參考"""
    return _window


def is_video_file(filename, extensions=None):
    """檢查是否為影片檔案

    Args:
        filename: 檔案名稱
        extensions: 可選的副檔名集合，未提供時使用模組級 VIDEO_EXTENSIONS 預設值
    """
    ext = os.path.splitext(filename)[1].lower()
    if extensions is not None:
        return ext in extensions
    return ext in VIDEO_EXTENSIONS


class Api:
    """供前端 JS 調用的 Python API"""

    def select_files(self):
        """
        開啟檔案選擇對話框，選取影片檔案
        Returns: 選取的檔案路徑陣列（Windows 路徑）
        """
        window = get_window()
        # Dynamically build file filter from config (fallback to DEFAULT_VIDEO_EXTENSIONS)
        exts = self._get_video_extensions()
        ext_filter = ';'.join(f'*{ext}' for ext in sorted(exts))
        file_types = (f'影片檔案 ({ext_filter})',
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
            # 用 config-driven extensions 展開第一層影片檔案
            exts = self._get_video_extensions()
            files = []
            for f in os.listdir(folder_path):
                file_path = os.path.join(folder_path, f)
                if os.path.isfile(file_path) and is_video_file(f, exts):
                    files.append(file_path)
            # 返回資料夾路徑和檔案列表（Scanner 用 folder，Search 用 files）
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
        path = uri_to_fs_path(path)

        if not os.path.exists(path):
            return False

        # 讀取設定，檢查是否有指定播放器
        player = self._get_player_path()

        if player and os.path.exists(player):
            try:
                subprocess.Popen([player, path])
                return True
            except Exception:
                pass  # fallback 到系統預設

        # 跨平台開啟檔案
        try:
            if sys.platform == 'win32':
                os.startfile(path)
            elif sys.platform == 'darwin':
                subprocess.run(['open', path])
            else:
                subprocess.run(['xdg-open', path])
            return True
        except Exception:
            return False

    def open_url(self, url: str) -> bool:
        """用系統預設瀏覽器開啟 URL

        僅接受 http:// 或 https:// 開頭的 URL，其他 scheme 一律拒絕。
        任何例外均捕捉並回傳 False，不讓異常傳播。

        Args:
            url: 要開啟的 URL 字串

        Returns:
            True 表示成功呼叫系統 API，False 表示驗證失敗或系統呼叫拋出例外
        """
        if not isinstance(url, str) or not url.startswith(('http://', 'https://')):
            return False
        try:
            if sys.platform == 'win32':
                os.startfile(url)
                return True
            elif sys.platform == 'darwin':
                result = subprocess.run(['open', url])
                return result.returncode == 0
            else:
                result = subprocess.run(['xdg-open', url])
                return result.returncode == 0
        except Exception:
            return False

    def open_folder(self, path):
        """用系統檔案管理員開啟檔案所在資料夾

        支援格式同 open_file()：
        - file:///C:/path/to/file.mp4
        - C:/path/to/file.mp4
        - C:\\path\\to\\file.mp4

        Windows: explorer /select, → 打開資料夾並選中檔案
        macOS:   open -R          → Finder 中顯示檔案
        Linux:   xdg-open         → 打開所在資料夾
        """
        path = uri_to_fs_path(path)

        if not os.path.exists(path):
            # 檔案不存在，嘗試開啟父資料夾
            parent = os.path.dirname(path)
            if not os.path.exists(parent):
                return False
            path = parent

        try:
            if sys.platform == 'win32':
                # /select, 會打開資料夾並選中該檔案
                subprocess.Popen(['explorer', '/select,', path])
                return True
            elif sys.platform == 'darwin':
                # -R 會在 Finder 中顯示並選中該檔案
                result = subprocess.run(['open', '-R', path])
                return result.returncode == 0
            else:
                # Linux: 開啟所在資料夾
                folder = os.path.dirname(path) if os.path.isfile(path) else path
                result = subprocess.run(['xdg-open', folder])
                return result.returncode == 0
        except Exception:
            return False

    def _get_video_extensions(self):
        """Get video extensions from config, fallback to DEFAULT_VIDEO_EXTENSIONS"""
        try:
            possible_paths = [
                Path(__file__).parent.parent / 'web' / 'config.json',
                Path(__file__).parent / 'config.json',
            ]
            for config_path in possible_paths:
                if config_path.exists():
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                        return get_video_extensions(config)
        except Exception:
            pass
        return set(DEFAULT_VIDEO_EXTENSIONS)

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


def _load_config_extensions():
    """Load video extensions from config file (for module-level functions)."""
    try:
        possible_paths = [
            Path(__file__).parent.parent / 'web' / 'config.json',
            Path(__file__).parent / 'config.json',
        ]
        for config_path in possible_paths:
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    return get_video_extensions(config)
    except Exception:
        pass
    return set(DEFAULT_VIDEO_EXTENSIONS)


def on_drop(e):
    """處理拖放事件，取得完整路徑並傳給前端（支援多檔案和資料夾）"""
    window = get_window()

    files = e.get('dataTransfer', {}).get('files', [])
    if not files:
        return

    # 收集所有項目
    expanded_paths = []  # 影片檔案路徑（給 search 用）
    folder_paths = []    # 資料夾路徑（給 scanner 用）

    # 用 config-driven extensions
    exts = _load_config_extensions()

    for file_info in files:
        win_path = file_info.get('pywebviewFullPath', '')
        if not win_path:
            continue

        if os.path.isdir(win_path):
            # 記錄資料夾路徑（給 scanner 用）
            folder_paths.append(win_path)
            # 資料夾：展開第一層影片檔案（給 search 用）
            for f in os.listdir(win_path):
                file_win_path = os.path.join(win_path, f)
                if os.path.isfile(file_win_path) and is_video_file(f, exts):
                    expanded_paths.append(file_win_path)
        else:
            # 檔案：直接加入
            expanded_paths.append(win_path)

    # 傳送影片檔案路徑（search 頁面用）
    if expanded_paths:
        paths_json = json.dumps(expanded_paths)
        window.evaluate_js(f'if(typeof handlePyWebViewDrop === "function") handlePyWebViewDrop({paths_json})')

    # 傳送資料夾路徑（scanner 頁面用）
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
