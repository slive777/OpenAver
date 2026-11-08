"""
跨平台路徑處理模組

支援環境：Windows / WSL / Linux / Mac
支援輸入格式：Windows 本地、WSL 網路路徑、Unix 路徑
"""
import os
import platform
import re
import unicodedata
from typing import Optional
from urllib.parse import unquote

from core.logger import get_logger

logger = get_logger(__name__)


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
        except:  # noqa: E722,S110 — probe /proc/version; bare except intentional to handle any OS-level read failure silently
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
    - C:/Users/... → C:\\Users\\... (正斜線轉反斜線)
    - \\\\NAS\\share\\... → \\\\NAS\\share\\... (不變)
    - //192.168.1.177/share/... → \\\\192.168.1.177\\share\\... (UNC 正斜線)
    - /home/... → \\\\wsl.localhost\\<distro>\\home\\... (需要知道 distro)
    """
    # 已經是 Windows 路徑
    if len(path) >= 2 and path[1] == ':':
        return path.replace('/', '\\')

    # UNC/SMB 路徑，不用轉換
    if path.startswith('\\\\'):
        return path

    # UNC/SMB 正斜線格式：//server/share/... → \\server\share\...
    # 先正規化成恆定 2 個前導斜線（防禦 ////server/... 異常輸入）
    if path.startswith('//'):
        normalized = '//' + path.lstrip('/')
        return normalized.replace('/', '\\')

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
            except Exception:  # noqa: S110 — regex path probe; fall through to fallback on any error
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


def strip_verbatim_prefix(path: str) -> str:
    r"""移除 Windows verbatim prefix（\\?\UNC\ 或 \\?\<drive>:\）。

    Args:
        path: Windows FS 路徑（backslash 或 forward-slash 均可）

    Returns:
        - ``\\?\UNC\server\share\...`` → ``\\server\share\...``
        - ``\\?\C:\...``              → ``C:\...``
        - 其他輸入（POSIX、普通 UNC、drive-letter）→ 原樣

    Notes:
        同時容忍 backslash (``\``) 與 forward-slash (``/``) 寫法，
        例如 ``//?/UNC/server/share`` 也可正確處理。
    """
    if not path:
        return path

    # 統一以 forward-slash 做前綴偵測（不修改原 path，只看開頭）
    fwd = path.replace('\\', '/')

    # verbatim UNC: //?/UNC/server/... → //server/...
    # Note: UNC prefix is always uppercase in practice; fwd.upper() is redundant but kept for safety
    if fwd.upper().startswith('//?/UNC/'):
        # strip 8 chars（\\?\UNC\ 或 //?/UNC/ 皆恰 8 字元），保留 server\share\...
        # 再 prepend \\ 還原標準 UNC
        rest = path[8:]   # skip len('\\\\?\\UNC\\') == 8 chars
        return '\\\\' + rest

    # verbatim local: //?/C:/... → C:/...
    if fwd.startswith('//?/') and len(fwd) >= 7 and fwd[4].isalpha() and fwd[5] == ':':
        return path[4:]  # skip \\?\

    return path


def _is_windows_style_uri(uri: str) -> bool:
    """判斷 file:/// URI 是否為 Windows-style（UNC 或 drive-letter）。

    Windows-style 判斷規則（依 to_file_uri 實際輸出）：
    - UNC：``file://///`` 開頭（file:/// + //server/...）
    - Drive-letter：``file:///[A-Za-z]:`` 開頭

    Returns:
        True 表示 Windows-style（比對時需 casefold），否則 POSIX（大小寫敏感）。
    """
    if uri.startswith('file://///'):
        return True
    # drive-letter：file:///X: — 需 uri[8]（字母）與 uri[9]（冒號）存在，下限 len 10
    # （涵蓋 root-only 'file:///C:' len=10 / 'file:///C:/' len=11）
    if len(uri) >= 10 and uri.startswith('file:///') and uri[8].isalpha() and uri[9] == ':':
        return True
    return False


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

    Notes:
        - mapping branch 只在 CURRENT_ENV == 'wsl' 且有 path_mappings 時生效。
        - 大小寫敏感（known limitation, T7）：startswith 比對是 case-sensitive，
          與 T6 reverse_path_mapping 對稱，沿用相同 limitation 標記。
        - 命中 boundary check（T7 P1 fix）：tail 必須為空或以 separator 開頭，
          避免 /home/user/share 誤命中 /home/user/share2。
        - trailing separator normalize（T7 P2 fix）：wsl_prefix 與 win_prefix 結尾的
          / 或 \\ 會被 rstrip('/\\\\') 清掉，避免拼接時缺斜線或雙斜線。
    """
    # 0. 移除 verbatim prefix（\\?\UNC\ → \\；\\?\ → C:\）
    #    必須在正規化斜線之前執行，因為 strip_verbatim_prefix 偵測 backslash 形式
    fs_path = strip_verbatim_prefix(fs_path)

    # 統一使用正斜線
    abs_path = fs_path.replace(chr(92), '/')

    # Windows 路徑：C:/... 格式
    if len(abs_path) >= 2 and abs_path[1] == ':':
        return f"file:///{abs_path}"

    # WSL mount 路徑：/mnt/c/... → C:/...
    # 只認 /mnt/<單一字母>（後接 / 或結尾），且只在 WSL／Windows（Windows 維持修前行為，
    # 讓 WSL 時期留下的 /mnt/c 設定仍對得上 C:）；純 Linux／Mac 的 /mnt/nas、/mnt/d 是
    # 一般掛載點，保留原路徑（否則 /mnt/backup → B:ackup 反解不回來）。
    if CURRENT_ENV in ('wsl', 'windows'):
        m = re.match(r'^/mnt/([A-Za-z])(/.*)?$', abs_path)
        if m:
            return f"file:///{m.group(1).upper()}:{m.group(2) or ''}"

    # UNC 路徑：//server/share/... → file://///server/share/...
    # 需要使用 file:/// + //path 格式，與 scan_file() 產生的格式一致
    # 正規化：移除多餘的前導斜線，確保恆定 2 個（避免 //// 變成 7 斜線）
    if abs_path.startswith('//'):
        abs_path = '//' + abs_path.lstrip('/')
        return f"file:///{abs_path}"

    # 其他 Unix 路徑：使用 path_mappings 轉換
    if path_mappings and CURRENT_ENV == 'wsl':
        SEPS = ('/', '\\')
        # 嘗試找到匹配的映射
        for wsl_prefix, win_prefix in path_mappings.items():
            # T7 P2 fix: strip trailing separators（charset rstrip）
            wsl_clean = wsl_prefix.rstrip('/\\')
            win_clean = win_prefix.rstrip('/\\')

            if not abs_path.startswith(wsl_clean):
                continue
            tail = abs_path[len(wsl_clean):]
            # T7 P1 fix: boundary check（tail 必須為空或以 separator 開頭）
            if tail and tail[0] not in SEPS:
                continue  # boundary fail（e.g. share vs share2）

            win_path = win_clean + tail
            win_path = win_path.replace(chr(92), '/')
            return f"file:///{win_path}"

    # Fallback：直接用原路徑
    return f"file:///{abs_path}"


def reverse_path_mapping(fs_path: str, path_mappings: dict) -> Optional[str]:
    """
    反向映射：將 Windows/UNC FS 路徑轉回 WSL local FS 路徑。

    `to_file_uri(path, mappings)` 的反向操作：
    - forward:  /home/user/nas/video.mp4  →（via mappings）→ file:///NAS/share/video.mp4
    - reverse:  //NAS/share/video.mp4     →（via mappings）→ /home/user/nas/video.mp4
                \\NAS\\share\\video.mp4                        （同上）

    Args:
        fs_path:       已 normalize 的 FS 路徑（可能是 UNC forward/backslash 形式）
        path_mappings: {local_prefix: win_prefix} 映射表（settings.path_mappings）

    Returns:
        命中映射時回傳 local FS 路徑；未命中或映射為空回傳 None。

    Notes:
        - 用 to_windows_path() 把 win_prefix 統一轉成 backslash 形式再做 startswith 比對，
          確保 forward-slash UNC 與 backslash UNC 輸入均可命中。
        - to_windows_path() 對某些 Unix 路徑（如 /home/...）在某些環境會拋 ValueError，
          此情況以 try/except 捕捉後跳過該 mapping，不中斷整個查找。
        - suffix（prefix 之後的部分）一律轉成 POSIX forward slash 再拼接 local_prefix。
        - 大小寫敏感（known limitation, T6）：startswith 比對是 case-sensitive。
          Windows 路徑大小寫不敏感、POSIX 大小寫敏感、UNC server 視 server 而定。
          目前不做 case folding 以避免誤傷 POSIX path。
        - 命中 boundary check（T6 P1 fix）：tail（命中後的剩餘部分）必須為空或以
          separator 開頭，避免 //NAS/share 誤命中 //NAS/share2。
        - trailing separator normalize（T6 P2 fix）：win_prefix 與 local_prefix 結尾
          的 / 或 \\ 會被 rstrip('/\\\\') 清掉，避免拼接時缺斜線或雙斜線。
        - WSL-mount candidate（91b P2 fix）：drive-letter remote（如 ``Z:/share``）經
          uri_to_fs_path() 在 WSL 環境會被 to_wsl_path() 正規化成 ``/mnt/z/share``
          （非 win_bs/win_fwd 任一形式），若不額外加入這個候選前綴，
          reverse_path_mapping 永遠 miss、fallback 回未反解的 /mnt/z/... 路徑。
          此候選以 to_wsl_path(win_prefix) 產生，try/except 包裹
          （SMB backslash UNC 會讓 to_wsl_path 拋 ValueError，略過即可，
          UNC 本身已由 win_fwd 命中，不受影響）。
    """
    if not fs_path or not path_mappings:
        return None

    SEPS = ('/', '\\')

    for local_prefix, win_prefix in path_mappings.items():
        try:
            win_bs_raw = to_windows_path(win_prefix)
        except ValueError:
            continue

        # P2 fix: strip trailing separators from both prefixes（charset rstrip）
        local_clean = local_prefix.rstrip('/\\')
        win_bs = win_bs_raw.rstrip('/\\')
        win_fwd = win_bs.replace('\\', '/')

        # 91b P2 fix: 額外加入 WSL-mount 形式候選（/mnt/<drive>/...），
        # 與 uri_to_fs_path() 對 drive-letter URI 的正規化結果對齊。
        # to_wsl_path 對 UNC 直接原樣回傳（等同 win_fwd），dedup 後不重複比對。
        candidates = [win_bs, win_fwd]
        try:
            win_mnt = to_wsl_path(win_prefix).rstrip('/\\')
            if win_mnt not in candidates:
                candidates.append(win_mnt)
        except ValueError:
            pass

        for prefix in candidates:
            if not fs_path.startswith(prefix):
                continue
            tail = fs_path[len(prefix):]
            # P1 fix: boundary check — tail 必須為空或以 separator 開頭
            if tail and tail[0] not in SEPS:
                continue  # boundary fail（e.g. share vs share2）
            suffix = tail.replace('\\', '/')
            return local_clean + suffix

    return None


def uri_to_local_fs_path(uri: str, path_mappings: dict) -> str:
    """file:/// URI → 本機『實際可存取』FS 路徑（含 WSL+mapping 反解）。

    專供「即將對回傳值做真實磁碟 I/O」的呼叫端使用。
    非 WSL 或無 mappings → 與 uri_to_fs_path(uri) 字面等價（reverse 分支不觸發）。

    與 coerce_to_file_uri（正向建 URI）方向相反、互補：各自呼叫，不要疊加（D2）。
    """
    fs = uri_to_fs_path(uri)
    if CURRENT_ENV == 'wsl' and path_mappings:
        fs = reverse_path_mapping(fs, path_mappings) or fs
    return fs


def uri_to_fs_path(uri: str) -> str:
    """file:/// URI → 當前環境檔案系統路徑。

    strip prefix → restore leading / → unquote → normalize_path。
    非 file:/// 輸入原樣通過 normalize_path。
    """
    path = uri
    if path.startswith('file:///'):
        path = path[8:]
        # 非 Windows drive-letter 且非 UNC → 還原前導 /
        if not (len(path) >= 2 and path[1] == ':') and not path.startswith('/'):
            path = '/' + path
    path = unquote(path)
    try:
        return normalize_path(path)
    except ValueError:
        return path


def file_uri_to_server_path(value: str) -> str:
    """file:/// URI → 伺服器命名空間裸字串（不依當前環境，無 I/O）。

    file:////media/x → /media/x；file:///D:/AV/x → D:/AV/x（保持正斜線）；
    file://///nas/s/x → //nas/s/x。不呼叫 normalize_path。
    非 file:/// 輸入逐字原樣返回（不 unquote）。
    """
    path = value
    if not path.startswith('file:///'):
        return path
    path = path[8:]
    # 非 Windows drive-letter 且非 UNC → 還原前導 /
    if not (len(path) >= 2 and path[1] == ':') and not path.startswith('/'):
        path = '/' + path
    return unquote(path)


def is_path_under_dir(path: str, dir_uri: str) -> bool:
    """
    判斷 file:/// URI 路徑是否在指定目錄底下。

    避免裸 startswith 前綴碰撞（如 E:/media 誤匹配 E:/media2）。
    要求 path 在 dir_uri 之後緊接 '/' 或完全相等。

    Windows-style URI（UNC ``file://///`` 或 drive ``file:///X:``）做大小寫不敏感比對
    （Windows 路徑不區分大小寫）；POSIX URI 維持大小寫敏感（Linux/Mac 路徑敏感）。
    """
    # 判斷是否為 Windows-style URI（任一方為 Windows-style 即採用不敏感比對）
    if _is_windows_style_uri(path) or _is_windows_style_uri(dir_uri):
        # NFC first, then casefold（正確順序：NFC → casefold）
        # NFC 先正規化，統一 NFC/NFD 混合形式；casefold 再做大小寫不敏感比對
        path_cf = unicodedata.normalize('NFC', path).casefold()
        dir_cf = unicodedata.normalize('NFC', dir_uri).casefold()
        if path_cf == dir_cf:
            return True
        prefix = dir_cf if dir_cf.endswith('/') else dir_cf + '/'
        return path_cf.startswith(prefix)

    # POSIX：原大小寫敏感邏輯
    if path == dir_uri:
        return True
    prefix = dir_uri if dir_uri.endswith('/') else dir_uri + '/'
    return path.startswith(prefix)


def is_fs_path_under_dir(fs_path: str, root_fs_path: str) -> bool:
    r"""
    判斷原生 FS path 是否在指定根目錄底下。

    與 is_path_under_dir(path, dir_uri) 的職責分界：
    - is_path_under_dir：吃 file:/// URI，純字串前綴比對，不解析 `..`、不解析
      symlink。呼叫端（不附行號，行號會過期）：core/readonly_paths.py、
      core/readonly_source.py、core/settings_link.py。
    - is_fs_path_under_dir（本函式）：吃原生 FS path（非 URI），先用
      os.path.realpath 解析 `..` 與 symlink 再比對。呼叫端：整理流程的寫入錨點
      （core/organizer.py 的 target_dir / target_path）、唯讀來源的輸出夾邊界
      （core/readonly_producer.py），以及**唯讀來源封面改名前的零寫入邊界**
      （core/readonly_assets.py::_rename_stale_cover_group，151b／AC-12——
      這一道擋的是「DB 的 cover_path 指到輸出夾以外」時不得改名使用者的來源檔）。

    兩者不得互相取代：硬套 URI 版要在呼叫端各做一次 URI 往返，等於正規化疊加；
    本函式也不得再串接 normalize_path() / to_file_uri()，只做下列這一條鏈。

    演算法（一步都不能省）：
        1. root_real = os.path.realpath(root_fs_path)
           realpath 已含 abspath；strict 保持預設 False——root_fs_path 對應的
           target_dir 在檢查當下本來就可能尚未建立。
        2. target_real = os.path.realpath(fs_path)
        3. 兩端各過 os.path.normcase（Windows 路徑大小寫不對稱）。
        4. 明確前綴比對：target_n == root_n → True；否則 target_n 是否以
           「root_n + 分隔符」開頭（分隔符取 os.path.sep）。這能正確處理
           UNC bare share root（如 \\server\share vs \\server\share\x），
           並擋下前綴碰撞（\\server\share vs \\server\shared）與跨磁碟機。
        5. 例外一律 fail-closed：ValueError（路徑字串本身不合法，如 embedded
           null byte）或 OSError（WinFsp/rclone 掛載點等）都記錄實際例外內容
           後回 False，不吞例外放行。比對結果為 False 時也記 WARNING，帶上
           root_n／target_n 兩個 resolved 值方便排錯。

    Args:
        fs_path: 待檢查的原生 FS path（非 URI）。
        root_fs_path: 根目錄的原生 FS path（非 URI）。

    Returns:
        fs_path 是否等於或位於 root_fs_path 底下；**路徑解析類**例外（ValueError /
        OSError）一律回 False。

    Note:
        **fail-closed 的範圍只涵蓋 ValueError 與 OSError。** 呼叫端須自行保證兩個
        參數都是 str（非 None）——傳 None 會讓 os.path.realpath 拋 TypeError 直接
        往外炸，本函式**刻意不吞它**：那是呼叫端契約違反（型別標註已寫明 str），
        大聲炸比靜默回 False 更容易查。T4/T5 的接線端不要以為「所有例外都被這裡
        擋掉了」。

        **空字串 root 的語意（刻意不擋，讀者必看）**：`root_fs_path=''` 會經
        `os.path.realpath('')` 解析成**當前工作目錄（CWD）**，比對照常進行、不報錯。
        這對「root 真的就是 CWD」的呼叫端是**正確**行為——例：`organize_file` 的
        `original_dir = os.path.dirname(file_path)`，當 `file_path` 是不含目錄的
        相對檔名時 `original_dir` 就是 `''`，而該檔確實位於 CWD。
        反過來，若某個呼叫端的空 root 意思是「**尚未設定**輸出根目錄」，那它**必須
        自己在上游擋掉**，不能指望本函式把空字串當成拒絕——本函式無從分辨這兩種
        語意。`core/readonly_producer.py` 即屬後者，已有三道上游 guard
        （`web/routers/scraper.py` 的單片與批次入口、`produce_source` 本身）確保
        空 `output_root` 永遠到不了這裡。

        **本檢查不防 TOCTOU（pre-merge SA-pre-9，刻意不治）**：它回答的是「檢查當下
        這條路徑在不在 root 底下」，不保證「呼叫端稍後真的寫入時仍是同一個目錄」。
        若有並行程序在檢查通過後、`makedirs`／`move` 之前把目標換成指向 root 外的
        symlink，寫入會跟著出去。**這在本專案宣告的威脅模型之外**——攻擊者是被刮削
        的網站（能力邊界＝往 HTTP 回應塞字串），不是本機並行程序；AGENTS.md 明載
        預設模型不含敵意的已認證 LAN 使用者，而能在本機任意建 symlink 的攻擊者根本
        不需要繞這道檢查、直接寫檔就好。真要關這個窗需要 `O_NOFOLLOW` + `openat`
        系列的 dirfd 相對操作，Windows（本專案主平台）無等價語意。
        詳見 `plan-110b.md` 附錄 A 的 B9。
    """
    _stage = "root_fs_path"
    try:
        root_real = os.path.realpath(root_fs_path)
        _stage = "fs_path"
        target_real = os.path.realpath(fs_path)
        root_n = os.path.normcase(root_real)
        target_n = os.path.normcase(target_real)
        if target_n == root_n:
            return True
        sep = os.path.sep
        root_with_sep = root_n if root_n.endswith(sep) else root_n + sep
        if not target_n.startswith(root_with_sep):
            logger.warning(
                f"is_fs_path_under_dir: 比對結果為 False — "
                f"fs_path={fs_path!r}, root_fs_path={root_fs_path!r}, "
                f"root_n={root_n!r}, target_n={target_n!r}"
            )
        return target_n.startswith(root_with_sep)
    except ValueError as e:
        logger.warning(
            f"is_fs_path_under_dir: realpath({_stage}) 路徑字串不合法 — "
            f"fs_path={fs_path!r}, root_fs_path={root_fs_path!r}, error={e}"
        )
        return False
    except OSError as e:
        logger.warning(
            f"is_fs_path_under_dir: realpath({_stage}) 解析失敗（可能掛載點異常）— "
            f"fs_path={fs_path!r}, root_fs_path={root_fs_path!r}, error={e}"
        )
        return False


def coerce_to_file_uri(value: str, path_mappings: dict = None) -> str:
    """Idempotent file URI 轉換：value 可能是 FS path 或已是 file:/// URI。

    已是 file:/// 開頭→ 原樣回傳，否則 to_file_uri()。
    用於 DB cover_path / video.path 這類格式不確定的場合，避免在 caller 做 startswith 判斷。

    Args:
        value: FS path 或已是 file:/// URI。
        path_mappings: 路徑映射表（WSL 環境用）；僅在 value 為 FS path 時傳入 to_file_uri。
    """
    if not value:
        return value
    if value.startswith("file:///"):
        return value
    return to_file_uri(value, path_mappings)
