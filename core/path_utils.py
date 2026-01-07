"""
跨平台路徑處理模組

支援環境：Windows / WSL / Linux / Mac
支援輸入格式：Windows 本地、WSL 網路路徑、Unix 路徑
"""
import platform
import re


def detect_environment() -> str:
    """
    偵測當前執行環境

    Returns:
        'windows' | 'wsl' | 'linux' | 'mac'
    """
    system = platform.system()

    if system == 'Windows':
        return 'windows'
    elif system == 'Linux':
        # 檢查是否在 WSL
        try:
            with open('/proc/version', 'r') as f:
                if 'microsoft' in f.read().lower():
                    return 'wsl'
        except:
            pass
        return 'linux'
    elif system == 'Darwin':
        return 'mac'

    return 'linux'  # 預設當作 Linux


# 啟動時偵測一次
CURRENT_ENV = detect_environment()


def normalize_path(path: str) -> str:
    """
    將任意格式路徑轉換成當前環境可用的路徑

    Args:
        path: 任意格式的路徑

    Returns:
        當前環境可用的路徑

    Raises:
        ValueError: 路徑格式不支援當前環境
    """
    if not path:
        return path

    if CURRENT_ENV == 'wsl':
        return to_wsl_path(path)
    elif CURRENT_ENV == 'windows':
        return to_windows_path(path)
    else:  # linux, mac
        return to_unix_path(path)


def to_wsl_path(path: str) -> str:
    """
    轉換成 WSL 路徑格式

    支援輸入：
    - C:\\Users\\... → /mnt/c/Users/...
    - \\\\wsl.localhost\\Ubuntu\\home\\... → /home/...
    - \\\\wsl$\\Ubuntu\\home\\... → /home/...
    - /home/... → /home/... (不變)
    - /mnt/c/... → /mnt/c/... (不變)
    """
    # 已經是 Unix 路徑，不用轉換
    if path.startswith('/'):
        return path

    # WSL 網路路徑: \\wsl.localhost\distro\path 或 \\wsl$\distro\path
    if path.startswith('\\\\wsl.localhost\\') or path.startswith('\\\\wsl$\\'):
        # 移除前綴
        path = path.replace('\\\\wsl.localhost\\', '').replace('\\\\wsl$\\', '')
        # 移除發行版名稱 (第一個 \ 之前的部分)
        parts = path.split('\\', 1)
        if len(parts) > 1:
            return '/' + parts[1].replace('\\', '/')
        return '/'

    # SMB/UNC 路徑: \\server\share\...
    if path.startswith('\\\\'):
        raise ValueError(f'WSL 環境不支援 SMB 路徑: {path}')

    # Windows 本地路徑: C:\Users\...
    if len(path) >= 2 and path[1] == ':':
        drive = path[0].lower()
        rest = path[2:].replace('\\', '/')
        return f'/mnt/{drive}{rest}'

    # 其他格式，嘗試直接返回
    return path


def to_windows_path(path: str) -> str:
    """
    轉換成 Windows 路徑格式

    支援輸入：
    - /mnt/c/Users/... → C:\\Users\\...
    - C:\\Users\\... → C:\\Users\\... (不變)
    - \\\\NAS\\share\\... → \\\\NAS\\share\\... (不變)
    - /home/... → \\\\wsl.localhost\\<distro>\\home\\... (需要知道 distro)
    """
    # 已經是 Windows 路徑
    if len(path) >= 2 and path[1] == ':':
        return path

    # UNC/SMB 路徑，不用轉換
    if path.startswith('\\\\'):
        return path

    # WSL mount 路徑: /mnt/c/... → C:\...
    match = re.match(r'^/mnt/([a-z])(/.*)?$', path)
    if match:
        drive = match.group(1).upper()
        rest = (match.group(2) or '').replace('/', '\\')
        return f'{drive}:{rest}'

    # Unix 路徑 /home/... 在純 Windows 環境無法直接存取
    if path.startswith('/'):
        raise ValueError(f'Windows 環境無法存取 Unix 路徑: {path}')

    return path


def to_unix_path(path: str) -> str:
    """
    轉換成 Unix 路徑格式 (Linux/Mac)

    支援輸入：
    - /home/... → /home/... (不變)
    - 其他格式不支援
    """
    # 已經是 Unix 路徑
    if path.startswith('/'):
        return path

    # Windows 路徑在純 Linux/Mac 環境不支援
    if len(path) >= 2 and path[1] == ':':
        raise ValueError(f'Linux/Mac 環境不支援 Windows 路徑: {path}')

    if path.startswith('\\\\'):
        raise ValueError(f'Linux/Mac 環境不支援 UNC 路徑: {path}')

    return path


def get_environment() -> str:
    """取得當前環境"""
    return CURRENT_ENV
