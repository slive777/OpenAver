"""
OpenAver Windows 單機版啟動器
整合 FastAPI 後端 + PyWebView 前端於同一進程
"""
import os
import sys
import time
import threading
import socket
import urllib.request
import urllib.error
import logging
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

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
PORT = 49152  # 使用動態/私有端口範圍 (49152-65535)，避免權限問題
STARTUP_TIMEOUT = 30  # 最多等待 30 秒

# 全域 logger
logger = None


# ============ 日誌系統 ============

def setup_logging():
    """設定日誌系統（RotatingFileHandler）"""
    global logger

    # 日誌目錄：%USERPROFILE%/OpenAver/logs/
    log_dir = Path.home() / "OpenAver" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / "debug.log"

    # 配置 RotatingFileHandler (5 個檔案 x 10MB)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )

    # 格式
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)

    # 設定 root logger
    logger = logging.getLogger('OpenAver')
    logger.setLevel(logging.DEBUG)
    logger.addHandler(file_handler)

    # 同時輸出到 console（INFO 以上）
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    logger.info(f"日誌系統初始化完成：{log_file}")
    return logger


def log(msg):
    """輸出日誌（相容舊版）"""
    if logger:
        logger.info(msg)
    else:
        print(f"[OpenAver] {msg}")


# ============ WebView2 檢查 ============

def check_webview2_installed():
    """檢查 WebView2 Runtime 是否已安裝"""
    try:
        import winreg
        # 檢查 Registry - 64 位元路徑
        key_path = r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path):
            return True
    except (FileNotFoundError, OSError):
        pass

    try:
        import winreg
        # 備用路徑 - 32 位元
        key_path = r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path):
            return True
    except (FileNotFoundError, OSError):
        pass

    return False


def show_webview2_prompt():
    """顯示 WebView2 安裝提示"""
    try:
        import tkinter as tk
        from tkinter import messagebox
        import webbrowser

        root = tk.Tk()
        root.withdraw()

        message = (
            "OpenAver 需要 Microsoft Edge WebView2 Runtime 才能運行。\n\n"
            "這是 Windows 10/11 的標準元件，但您的系統尚未安裝。\n\n"
            "是否前往下載頁面？（約 2MB，安裝需 1 分鐘）"
        )

        result = messagebox.askyesno("需要 WebView2 Runtime", message)

        if result:
            webbrowser.open("https://go.microsoft.com/fwlink/p/?LinkId=2124703")

        root.destroy()
        return result
    except Exception as e:
        log(f"無法顯示 WebView2 提示視窗：{e}")
        return False


# ============ 錯誤處理 ============

def show_error(title, message, details=None):
    """顯示錯誤訊息視窗"""
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()

        full_message = message
        if details:
            full_message += f"\n\n錯誤詳情：\n{details[:500]}"  # 限制詳情長度

        messagebox.showerror(title, full_message)
        root.destroy()
    except Exception:
        # tkinter 不可用時，只輸出到 console/log
        log(f"[ERROR] {title}: {message}")
        if details:
            log(f"[DETAILS] {details}")


# ============ 核心功能 ============

def find_free_port(start_port=49152, max_attempts=100):
    """尋找可用端口（改進版，使用動態端口範圍避免權限問題）"""
    last_error = None
    tested_ports = []

    for port in range(start_port, start_port + max_attempts):
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # 設置 SO_REUSEADDR 選項（允許快速重用端口）
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # 設置超時避免卡住
            sock.settimeout(1)
            sock.bind((HOST, port))
            sock.close()

            # 記錄成功找到的端口
            if logger:
                logger.info(f"找到可用端口: {port}")

            return port
        except OSError as e:
            last_error = e
            tested_ports.append(port)
            # 記錄詳細的失敗信息（僅前 5 次和最後 5 次，避免日誌過多）
            if len(tested_ports) <= 5 or len(tested_ports) >= max_attempts - 5:
                if logger:
                    logger.debug(f"端口 {port} 不可用: {e}")
            continue
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass

    # 提供更詳細的錯誤信息和解決方案
    error_msg = f"無法找到可用端口 ({start_port}-{start_port + max_attempts - 1})"
    if last_error:
        error_code = getattr(last_error, 'winerror', None) or getattr(last_error, 'errno', None)
        error_msg += f"\n最後錯誤: {last_error}"

        # 針對 Windows Error 10013 提供具體建議
        if error_code == 10013:
            error_msg += "\n\n[解決方案]"
            error_msg += "\n1. 暫時關閉防火牆或安全軟件（如 360、McAfee）"
            error_msg += "\n2. 右鍵點擊 OpenAver.bat，選擇「以系統管理員身分執行」"
            error_msg += "\n3. 檢查 Windows Defender 防火牆設定"
            error_msg += "\n4. 重新啟動電腦後再試"

        error_msg += f"\n已測試 {len(tested_ports)} 個端口"

    if logger:
        logger.error(error_msg)

    raise RuntimeError(error_msg)


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
    global logger
    logger = setup_logging()
    log("正在啟動...")

    # 0. 檢查 WebView2（僅 Windows）
    if sys.platform == 'win32':
        if not check_webview2_installed():
            log("WebView2 Runtime 未安裝")
            if not show_webview2_prompt():
                log("用戶取消安裝，程式結束")
                sys.exit(0)
            else:
                log("請安裝 WebView2 後重新啟動")
                sys.exit(0)

    # 1. 尋找可用端口
    try:
        port = find_free_port(PORT)
        log(f"使用端口: {port}")
    except RuntimeError as e:
        # 端口綁定失敗，顯示詳細的解決方案
        show_error(
            "啟動失敗 - 無法綁定端口",
            str(e),
            None
        )
        sys.exit(1)

    # 2. 在背景 thread 啟動 FastAPI
    log("啟動伺服器...")
    server_thread = threading.Thread(target=run_server, args=(port,), daemon=True)
    server_thread.start()

    # 3. 等待伺服器就緒
    log("等待伺服器就緒...")
    if not wait_for_server(port):
        log("錯誤：伺服器啟動逾時")
        show_error(
            "啟動失敗",
            "伺服器啟動逾時。\n\n請檢查是否有其他程式佔用端口 8000。"
        )
        sys.exit(1)
    log("伺服器已就緒")

    # 4. 啟動 PyWebView 窗口
    log("啟動視窗...")
    webview.settings['OPEN_DEVTOOLS_IN_DEBUG'] = False

    window = webview.create_window(
        'OpenAver',
        f'http://{HOST}:{port}',
        js_api=api,
        width=1200,
        height=800
    )

    # 5. 開始 GUI 事件循環（阻塞直到窗口關閉）
    webview.start(bind_events, window, gui='edgechromium')


if __name__ == '__main__':
    try:
        main()
    except ImportError as e:
        show_error(
            "啟動失敗 - 缺少依賴",
            "缺少必要的 Python 套件。\n\n請確認是否使用打包版執行，或檢查虛擬環境。",
            str(e)
        )
        sys.exit(1)
    except PermissionError as e:
        show_error(
            "啟動失敗 - 權限不足",
            "無法存取必要的檔案或目錄。\n\n請以一般使用者權限執行（不要用管理員）。",
            str(e)
        )
        sys.exit(1)
    except Exception as e:
        error_details = traceback.format_exc()
        # 確保錯誤也寫入日誌
        if logger:
            logger.error(f"未預期的錯誤：{e}\n{error_details}")
        show_error(
            "啟動失敗 - 未知錯誤",
            "OpenAver 啟動時發生錯誤。\n\n請將錯誤詳情回報到 GitHub Issues。",
            error_details
        )
        sys.exit(1)
