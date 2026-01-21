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
        rest = path[2:].rstrip('\\').replace('\\', '/')
        return f'/mnt/{drive}{rest}' if rest else f'/mnt/{drive}'

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


def expand_env_vars(path: str) -> str:
    """
    展開環境變數並轉換路徑

    支援：
    - %USERPROFILE%\\Downloads → /mnt/c/Users/<user>/Downloads (WSL)
    - %USERPROFILE%\\Downloads → C:\\Users\\<user>\\Downloads (Windows)
    - ~/Downloads → /home/<user>/Downloads (Unix)

    Args:
        path: 包含環境變數的路徑

    Returns:
        展開並轉換後的路徑
    """
    if not path:
        return path

    # 處理 Unix 波浪號
    if path.startswith('~'):
        from pathlib import Path
        return str(Path(path).expanduser())

    # 處理 Windows 環境變數 %USERPROFILE%
    if '%USERPROFILE%' in path.upper():
        if CURRENT_ENV == 'wsl':
            # WSL 環境：從 /etc/passwd 或 cmd.exe 取得 Windows 用戶名
            import subprocess
            try:
                # 透過 cmd.exe 取得 Windows 的 USERPROFILE
                result = subprocess.run(
                    ['cmd.exe', '/c', 'echo', '%USERPROFILE%'],
                    capture_output=True, text=True, timeout=5
                )
                win_userprofile = result.stdout.strip()
                if win_userprofile and win_userprofile != '%USERPROFILE%':
                    # 不區分大小寫替換環境變數
                    import re as regex_module
                    path = regex_module.sub(
                        r'%USERPROFILE%',
                        lambda m: win_userprofile,
                        path,
                        flags=regex_module.IGNORECASE
                    )
                    # 轉換成 WSL 路徑
                    return normalize_path(path)
            except Exception:
                pass

            # Fallback: 假設 Windows 用戶名與 WSL 用戶名相同
            import os
            import re as regex_module
            wsl_user = os.environ.get('USER', 'user')
            win_path = f'C:\\Users\\{wsl_user}'
            path = regex_module.sub(
                r'%USERPROFILE%',
                lambda m: win_path,
                path,
                flags=regex_module.IGNORECASE
            )
            return normalize_path(path)

        elif CURRENT_ENV == 'windows':
            # Windows 環境：使用 os.path.expandvars
            import os
            return os.path.expandvars(path)

        else:
            # 純 Linux/Mac：無法處理 Windows 環境變數
            raise ValueError(f'當前環境不支援 Windows 環境變數: {path}')

    # 其他情況：直接 normalize
    return normalize_path(path)


def get_environment() -> str:
    """取得當前環境"""
    return CURRENT_ENV


def to_file_uri(fs_path: str, path_mappings: dict = None) -> str:
    """
    將檔案系統路徑轉換為 file:/// URI

    支援輸入：
    - C:\\Videos\\xxx.mp4 → file:///C:/Videos/xxx.mp4
    - /mnt/c/Videos/xxx.mp4 → file:///C:/Videos/xxx.mp4
    - \\\\NAS\\share\\xxx.mp4 → file:///NAS/share/xxx.mp4

    Args:
        fs_path: 檔案系統路徑
        path_mappings: 路徑映射表（WSL 環境用）

    Returns:
        file:/// 格式的 URI
    """
    # 統一使用正斜線
    abs_path = fs_path.replace(chr(92), '/')

    # Windows 路徑：C:/... 格式
    if len(abs_path) >= 2 and abs_path[1] == ':':
        return f"file:///{abs_path}"

    # WSL mount 路徑：/mnt/c/... → C:/...
    if abs_path.startswith('/mnt/') and len(abs_path) > 5:
        drive = abs_path[5].upper()
        rest = abs_path[6:] if len(abs_path) > 6 else ''
        return f"file:///{drive}:{rest}"

    # UNC 路徑：//server/share/... → file://///server/share/...
    # 需要使用 file:/// + //path 格式，與 scan_file() 產生的格式一致
    if abs_path.startswith('//'):
        return f"file:///{abs_path}"

    # 其他 Unix 路徑：使用 path_mappings 轉換
    if path_mappings and CURRENT_ENV == 'wsl':
        # 嘗試找到匹配的映射
        for wsl_prefix, win_prefix in path_mappings.items():
            if abs_path.startswith(wsl_prefix):
                win_path = win_prefix + abs_path[len(wsl_prefix):]
                win_path = win_path.replace(chr(92), '/')
                return f"file:///{win_path}"

    # Fallback：直接用原路徑
    return f"file:///{abs_path}"
