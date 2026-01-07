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

    def select_files(self):
        """
        開啟檔案選擇對話框，選取影片檔案
        Returns: 選取的檔案路徑陣列（Windows 路徑）
        """
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
        """
        開啟資料夾選擇對話框，展開內部影片檔案
        Returns: 資料夾內影片檔案的路徑陣列（Windows 路徑）
        """
        global window
        result = window.create_file_dialog(webview.FOLDER_DIALOG)
        if result and len(result) > 0:
            folder_path = result[0]
            print(f"[DEBUG] 選取資料夾: {folder_path}")
            # 展開第一層影片檔案
            files = []
            for f in os.listdir(folder_path):
                file_path = os.path.join(folder_path, f)
                if os.path.isfile(file_path) and is_video_file(f):
                    files.append(file_path)
                    print(f"[DEBUG]   + {f}")
            return files
        return []


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

    # 收集所有項目（用 Windows 路徑判斷檔案/資料夾，傳原始路徑給後端）
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
                    expanded_paths.append(file_win_path)
                    print(f"[DEBUG]   + {f}")
        else:
            # 檔案：直接加入
            expanded_paths.append(win_path)
            print(f"[DEBUG] 檔案: {win_path}")

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
