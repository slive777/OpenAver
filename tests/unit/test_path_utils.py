"""
test_path_utils.py - 跨平台路徑轉換單元測試

測試範圍：
- detect_environment(): 環境偵測
- to_wsl_path(): Windows/WSL 網路路徑 → WSL 路徑
- to_windows_path(): WSL mount 路徑 → Windows 路徑
- to_unix_path(): Unix 路徑驗證
- normalize_path(): 根據當前環境自動轉換
- expand_env_vars(): 環境變數展開
"""

import pytest
from unittest.mock import patch, mock_open

# 測試目標模組
import core.path_utils as path_utils


# ============ TestDetectEnvironment ============

class TestDetectEnvironment:
    """測試環境偵測邏輯"""

    def test_detect_windows(self, monkeypatch):
        """純 Windows 環境"""
        monkeypatch.setattr('platform.system', lambda: 'Windows')
        result = path_utils.detect_environment()
        assert result == 'windows'

    def test_detect_mac(self, monkeypatch):
        """macOS 環境"""
        monkeypatch.setattr('platform.system', lambda: 'Darwin')
        result = path_utils.detect_environment()
        assert result == 'mac'

    def test_detect_linux(self, monkeypatch):
        """純 Linux 環境（非 WSL）"""
        monkeypatch.setattr('platform.system', lambda: 'Linux')
        # Mock /proc/version 不含 microsoft
        mock_file = mock_open(read_data='Linux version 5.4.0-generic')
        with patch('builtins.open', mock_file):
            result = path_utils.detect_environment()
        assert result == 'linux'

    def test_detect_wsl(self, monkeypatch):
        """WSL 環境（Linux + microsoft 標記）"""
        monkeypatch.setattr('platform.system', lambda: 'Linux')
        mock_file = mock_open(read_data='Linux version 5.15.0-microsoft-standard-WSL2')
        with patch('builtins.open', mock_file):
            result = path_utils.detect_environment()
        assert result == 'wsl'

    def test_detect_wsl_case_insensitive(self, monkeypatch):
        """WSL 偵測不區分大小寫"""
        monkeypatch.setattr('platform.system', lambda: 'Linux')
        mock_file = mock_open(read_data='Linux version 5.4.0-Microsoft-Standard')
        with patch('builtins.open', mock_file):
            result = path_utils.detect_environment()
        assert result == 'wsl'

    def test_detect_linux_proc_not_found(self, monkeypatch):
        """Linux 環境，/proc/version 不存在"""
        monkeypatch.setattr('platform.system', lambda: 'Linux')
        with patch('builtins.open', side_effect=FileNotFoundError):
            result = path_utils.detect_environment()
        assert result == 'linux'

    def test_detect_unknown_defaults_to_linux(self, monkeypatch):
        """未知系統預設為 Linux"""
        monkeypatch.setattr('platform.system', lambda: 'FreeBSD')
        result = path_utils.detect_environment()
        assert result == 'linux'


# ============ TestToWslPath ============

class TestToWslPath:
    """測試 Windows/WSL 路徑轉換成 WSL 格式"""

    # --- Windows 本地路徑 ---
    def test_windows_c_drive(self):
        """C: 磁碟機轉換"""
        result = path_utils.to_wsl_path(r'C:\Users\test')
        assert result == '/mnt/c/Users/test'

    def test_windows_d_drive(self):
        """D: 磁碟機轉換"""
        result = path_utils.to_wsl_path(r'D:\Downloads\file.mp4')
        assert result == '/mnt/d/Downloads/file.mp4'

    def test_windows_lowercase_drive(self):
        """小寫磁碟機轉換"""
        result = path_utils.to_wsl_path(r'e:\games\test.exe')
        assert result == '/mnt/e/games/test.exe'

    def test_windows_root_only(self):
        """只有磁碟機根目錄"""
        result = path_utils.to_wsl_path(r'C:\\')
        # 修正後行為：C:\\ → /mnt/c（正確移除尾斜線）
        assert result == '/mnt/c'

    def test_windows_nested_path(self):
        """深層巢狀路徑"""
        result = path_utils.to_wsl_path(r'C:\Users\admin\Documents\Project\src\main.py')
        assert result == '/mnt/c/Users/admin/Documents/Project/src/main.py'

    # --- WSL 網路路徑 ---
    def test_wsl_localhost_ubuntu(self):
        """\\\\wsl.localhost\\Ubuntu 格式"""
        result = path_utils.to_wsl_path(r'\\wsl.localhost\Ubuntu\home\user')
        assert result == '/home/user'

    def test_wsl_dollar_sign(self):
        """\\\\wsl$\\Ubuntu 格式"""
        result = path_utils.to_wsl_path(r'\\wsl$\Ubuntu\home\user')
        assert result == '/home/user'

    def test_wsl_localhost_debian(self):
        """不同發行版 Debian"""
        result = path_utils.to_wsl_path(r'\\wsl.localhost\Debian\var\log')
        assert result == '/var/log'

    def test_wsl_localhost_root(self):
        """WSL 根目錄"""
        result = path_utils.to_wsl_path(r'\\wsl.localhost\Ubuntu')
        assert result == '/'

    # --- 已是 Unix 路徑 ---
    def test_already_unix_home(self):
        """已經是 Unix 路徑 /home"""
        result = path_utils.to_wsl_path('/home/user')
        assert result == '/home/user'

    def test_already_unix_mnt(self):
        """已經是 WSL mount 路徑"""
        result = path_utils.to_wsl_path('/mnt/c/test')
        assert result == '/mnt/c/test'

    def test_already_unix_root(self):
        """Unix 根目錄"""
        result = path_utils.to_wsl_path('/')
        assert result == '/'

    # --- 錯誤處理 ---
    def test_smb_path_raises_error(self):
        """SMB/UNC 路徑應拋出 ValueError"""
        with pytest.raises(ValueError, match='不支援 SMB 路徑'):
            path_utils.to_wsl_path(r'\\NAS\share\file.mp4')

    def test_network_share_raises_error(self):
        """網路芳鄰路徑應拋出 ValueError"""
        with pytest.raises(ValueError, match='不支援 SMB 路徑'):
            path_utils.to_wsl_path(r'\\192.168.1.100\shared')


# ============ TestToWindowsPath ============

class TestToWindowsPath:
    """測試 WSL 路徑轉換成 Windows 格式"""

    # --- WSL mount 路徑 ---
    def test_mnt_c_drive(self):
        """/mnt/c → C:\\"""
        result = path_utils.to_windows_path('/mnt/c/Users/test')
        assert result == r'C:\Users\test'

    def test_mnt_d_drive(self):
        """/mnt/d → D:\\"""
        result = path_utils.to_windows_path('/mnt/d/Downloads')
        assert result == r'D:\Downloads'

    def test_mnt_root_only(self):
        """只有 mount 根目錄"""
        result = path_utils.to_windows_path('/mnt/c')
        assert result == 'C:'

    def test_mnt_with_trailing_slash(self):
        """帶尾斜線"""
        result = path_utils.to_windows_path('/mnt/c/')
        assert result == r'C:\ '[:-1]  # r'C:\'

    # --- 已是 Windows 路徑 ---
    def test_already_windows_path(self):
        """已經是 Windows 路徑"""
        result = path_utils.to_windows_path(r'C:\test')
        assert result == r'C:\test'

    def test_already_windows_lowercase(self):
        """小寫 Windows 路徑"""
        result = path_utils.to_windows_path(r'd:\downloads')
        assert result == r'd:\downloads'

    # --- UNC 路徑 ---
    def test_unc_path_unchanged(self):
        """UNC 路徑不變"""
        result = path_utils.to_windows_path(r'\\NAS\share')
        assert result == r'\\NAS\share'

    # --- 錯誤處理 ---
    def test_pure_unix_path_raises_error(self):
        """純 Unix 路徑在 Windows 環境無法存取"""
        with pytest.raises(ValueError, match='無法存取 Unix 路徑'):
            path_utils.to_windows_path('/home/user')

    def test_etc_path_raises_error(self):
        """/etc 系統路徑無法存取"""
        with pytest.raises(ValueError, match='無法存取 Unix 路徑'):
            path_utils.to_windows_path('/etc/passwd')

    def test_unc_forward_slash_ip(self):
        """正斜線 UNC + IP 位址轉反斜線"""
        result = path_utils.to_windows_path('//192.168.1.177/media/video.mp4')
        assert result == r'\\192.168.1.177\media\video.mp4'

    def test_unc_extra_leading_slashes(self):
        """多餘前導斜線先正規化再轉反斜線"""
        result = path_utils.to_windows_path('////server/share/file.mp4')
        assert result == r'\\server\share\file.mp4'

    def test_drive_letter_forward_slash(self):
        """C:/... 正斜線轉反斜線"""
        result = path_utils.to_windows_path('C:/Users/peace/video.mp4')
        assert result == r'C:\Users\peace\video.mp4'


# ============ TestToUnixPath ============

class TestToUnixPath:
    """測試 Unix 路徑驗證（Linux/Mac）"""

    # --- 正常 Unix 路徑 ---
    def test_home_path(self):
        """/home 路徑"""
        result = path_utils.to_unix_path('/home/user')
        assert result == '/home/user'

    def test_var_path(self):
        """/var 路徑"""
        result = path_utils.to_unix_path('/var/log/syslog')
        assert result == '/var/log/syslog'

    def test_root_path(self):
        """根目錄"""
        result = path_utils.to_unix_path('/')
        assert result == '/'

    def test_tmp_path(self):
        """/tmp 路徑"""
        result = path_utils.to_unix_path('/tmp/test.txt')
        assert result == '/tmp/test.txt'

    # --- 錯誤處理 ---
    def test_windows_path_raises_error(self):
        """Windows 路徑不支援"""
        with pytest.raises(ValueError, match='不支援 Windows 路徑'):
            path_utils.to_unix_path(r'C:\test')

    def test_unc_path_raises_error(self):
        """UNC 路徑不支援"""
        with pytest.raises(ValueError, match='不支援 UNC 路徑'):
            path_utils.to_unix_path(r'\\NAS\share')


# ============ TestNormalizePath ============

class TestNormalizePath:
    """測試根據當前環境自動轉換路徑"""

    def test_wsl_env_windows_input(self, monkeypatch):
        """WSL 環境下輸入 Windows 路徑"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'wsl')
        result = path_utils.normalize_path(r'C:\Users\test')
        assert result == '/mnt/c/Users/test'

    def test_wsl_env_unix_input(self, monkeypatch):
        """WSL 環境下輸入 Unix 路徑"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'wsl')
        result = path_utils.normalize_path('/home/user')
        assert result == '/home/user'

    def test_windows_env_mnt_input(self, monkeypatch):
        """Windows 環境下輸入 WSL mount 路徑"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'windows')
        result = path_utils.normalize_path('/mnt/c/Users/test')
        assert result == r'C:\Users\test'

    def test_windows_env_windows_input(self, monkeypatch):
        """Windows 環境下輸入 Windows 路徑"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'windows')
        result = path_utils.normalize_path(r'D:\Downloads')
        assert result == r'D:\Downloads'

    def test_linux_env_unix_input(self, monkeypatch):
        """Linux 環境下輸入 Unix 路徑"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'linux')
        result = path_utils.normalize_path('/home/user')
        assert result == '/home/user'

    def test_linux_env_windows_input_raises(self, monkeypatch):
        """Linux 環境下輸入 Windows 路徑應報錯"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'linux')
        with pytest.raises(ValueError):
            path_utils.normalize_path(r'C:\test')

    def test_mac_env_unix_input(self, monkeypatch):
        """Mac 環境下輸入 Unix 路徑"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'mac')
        result = path_utils.normalize_path('/Users/test')
        assert result == '/Users/test'

    def test_empty_path(self, monkeypatch):
        """空路徑直接返回"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'linux')
        result = path_utils.normalize_path('')
        assert result == ''

    def test_none_like_falsy(self, monkeypatch):
        """Falsy 路徑處理"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'linux')
        # 空字串
        assert path_utils.normalize_path('') == ''


# ============ TestExpandEnvVars ============

class TestExpandEnvVars:
    """測試環境變數展開"""

    def test_tilde_expansion_linux(self, monkeypatch, tmp_path):
        """Linux 環境 ~ 展開"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'linux')
        # ~ 會被 pathlib 展開為實際 home 目錄
        result = path_utils.expand_env_vars('~/Downloads')
        assert result.endswith('/Downloads')
        assert '~' not in result

    def test_tilde_expansion_mac(self, monkeypatch):
        """Mac 環境 ~ 展開"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'mac')
        result = path_utils.expand_env_vars('~/Documents')
        assert result.endswith('/Documents')
        assert '~' not in result

    def test_userprofile_in_linux_raises(self, monkeypatch):
        """Linux 環境不支援 %USERPROFILE%"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'linux')
        with pytest.raises(ValueError, match='不支援 Windows 環境變數'):
            path_utils.expand_env_vars(r'%USERPROFILE%\Downloads')

    def test_empty_path_returns_empty(self, monkeypatch):
        """空路徑返回空"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'linux')
        result = path_utils.expand_env_vars('')
        assert result == ''

    def test_no_env_var_normalize(self, monkeypatch):
        """無環境變數直接 normalize"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'linux')
        result = path_utils.expand_env_vars('/home/user/test')
        assert result == '/home/user/test'


# ============ TestGetEnvironment ============

class TestGetEnvironment:
    """測試 get_environment() 輔助函數"""

    def test_returns_current_env(self, monkeypatch):
        """返回當前環境值"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'wsl')
        assert path_utils.get_environment() == 'wsl'

        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'windows')
        assert path_utils.get_environment() == 'windows'

        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'linux')
        assert path_utils.get_environment() == 'linux'


# ============ TestToFileUri ============

class TestToFileUri:
    """測試 to_file_uri() 路徑轉換為 file:/// URI

    這是 D.1 新增的函數，用於統一路徑格式以確保快取命中。
    所有路徑最終都應轉換為 file:/// 格式，與 scan_file() 產生的格式一致。
    """

    # --- Windows 本地路徑 ---
    def test_windows_backslash(self):
        """Windows 反斜線路徑"""
        result = path_utils.to_file_uri(r'C:\Videos\test.mp4')
        assert result == 'file:///C:/Videos/test.mp4'

    def test_windows_forward_slash(self):
        """Windows 正斜線路徑"""
        result = path_utils.to_file_uri('C:/Videos/test.mp4')
        assert result == 'file:///C:/Videos/test.mp4'

    def test_windows_lowercase_drive(self):
        """小寫磁碟機"""
        result = path_utils.to_file_uri(r'd:\downloads\file.mp4')
        assert result == 'file:///d:/downloads/file.mp4'

    def test_windows_root_only(self):
        """只有磁碟機根目錄"""
        result = path_utils.to_file_uri('C:\\')
        assert result == 'file:///C:/'

    # --- WSL mount 路徑 ---
    def test_wsl_mount_c(self):
        """/mnt/c 路徑"""
        result = path_utils.to_file_uri('/mnt/c/Videos/test.mp4')
        assert result == 'file:///C:/Videos/test.mp4'

    def test_wsl_mount_d(self):
        """/mnt/d 路徑"""
        result = path_utils.to_file_uri('/mnt/d/Downloads/file.mp4')
        assert result == 'file:///D:/Downloads/file.mp4'

    def test_wsl_mount_root_only(self):
        """只有 mount 根目錄"""
        result = path_utils.to_file_uri('/mnt/c')
        assert result == 'file:///C:'

    # --- UNC 路徑（網路路徑） ---
    def test_unc_standard_backslash(self):
        """標準 UNC 反斜線路徑"""
        result = path_utils.to_file_uri(r'\\server\share\test.mp4')
        assert result == 'file://///server/share/test.mp4'

    def test_unc_ip_address(self):
        """UNC IP 位址路徑"""
        result = path_utils.to_file_uri(r'\\192.168.1.177\downloads\test.mp4')
        assert result == 'file://///192.168.1.177/downloads/test.mp4'

    def test_unc_forward_slash(self):
        """UNC 已經是正斜線"""
        result = path_utils.to_file_uri('//server/share/test.mp4')
        assert result == 'file://///server/share/test.mp4'

    # --- UNC 邊緣案例（D.1.3 修復） ---
    def test_unc_extra_slashes(self):
        """UNC 多餘斜線應正規化"""
        result = path_utils.to_file_uri('////server/share/test.mp4')
        assert result == 'file://///server/share/test.mp4'

    def test_unc_many_extra_slashes(self):
        """UNC 超多斜線應正規化"""
        result = path_utils.to_file_uri('////////server/share/test.mp4')
        assert result == 'file://///server/share/test.mp4'

    def test_unc_mixed_format(self):
        """UNC 混合格式（反斜線 + 正斜線）"""
        result = path_utils.to_file_uri(r'\\//server/share/test.mp4')
        assert result == 'file://///server/share/test.mp4'

    # --- 一致性測試（確保與 scan_file 相同） ---
    def test_all_formats_produce_5_slashes_for_unc(self):
        """所有 UNC 格式都應產生 5 斜線"""
        test_cases = [
            r'\\server\share\file.mp4',
            '//server/share/file.mp4',
            '////server/share/file.mp4',
            r'\\//server/share/file.mp4',
        ]
        for path in test_cases:
            result = path_utils.to_file_uri(path)
            # 計算 file: 後的斜線數
            after_file = result[5:]  # 移除 'file:'
            leading_slashes = len(after_file) - len(after_file.lstrip('/'))
            assert leading_slashes == 5, f"Path {path} produced {leading_slashes} slashes, expected 5"

    # --- path_mappings 測試 ---
    def test_path_mappings_unc(self, monkeypatch):
        """WSL 環境下 path_mappings 轉換 UNC"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'wsl')
        mappings = {'/home/user/nas': r'\\DiskStation\share'}
        result = path_utils.to_file_uri('/home/user/nas/Videos/test.mp4', mappings)
        assert result == 'file://///DiskStation/share/Videos/test.mp4'

    def test_path_mappings_not_matched(self, monkeypatch):
        """path_mappings 不匹配時 fallback"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'wsl')
        mappings = {'/home/other': r'\\Server\share'}
        result = path_utils.to_file_uri('/home/user/test.mp4', mappings)
        # 不匹配，直接返回原路徑
        assert result == 'file:////home/user/test.mp4'


class TestToFileUriPlainUnix:
    """測試 to_file_uri() 對純 Unix 路徑的處理（無 path_mappings）"""

    def test_to_file_uri_plain_unix(self):
        """純 Unix 路徑在無 mappings 時直接 fallback 為 file:////home/..."""
        result = path_utils.to_file_uri('/home/user/video.mp4')
        assert result == 'file:////home/user/video.mp4'


class TestNormalizePathEdgeCases:
    """補齊 normalize_path() 測試矩陣缺口"""

    def test_normalize_path_url_encoded(self, monkeypatch):
        """Windows 環境下，URL-encoded 路徑原樣通過（C:/My%20Videos/...）"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'windows')
        result = path_utils.normalize_path('C:/My%20Videos/test.mp4')
        # to_windows_path 偵測到 path[1]==':' → 轉反斜線回傳（未解 URL encoding）
        assert result == 'C:\\My%20Videos\\test.mp4'

    def test_normalize_path_unc(self, monkeypatch):
        """Windows 環境下，UNC 路徑原樣通過（\\\\server\\share\\...）"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'windows')
        result = path_utils.normalize_path(r'\\server\share\test.mp4')
        # to_windows_path 偵測到 startswith('\\\\') → 原樣回傳
        assert result == r'\\server\share\test.mp4'


class TestIsPathUnderDir:
    """測試 is_path_under_dir — 避免前綴碰撞"""

    def test_file_directly_under_dir(self):
        from core.path_utils import is_path_under_dir
        assert is_path_under_dir("file:///E:/media/SONE-205.mp4", "file:///E:/media") is True

    def test_file_in_subdirectory(self):
        from core.path_utils import is_path_under_dir
        assert is_path_under_dir("file:///E:/media/sub/video.mp4", "file:///E:/media") is True

    def test_prefix_collision_rejected(self):
        """E:/media 不應匹配 E:/media2 底下的檔案"""
        from core.path_utils import is_path_under_dir
        assert is_path_under_dir("file:///E:/media2/video.mp4", "file:///E:/media") is False

    def test_exact_match(self):
        from core.path_utils import is_path_under_dir
        assert is_path_under_dir("file:///E:/media", "file:///E:/media") is True

    def test_dir_with_trailing_slash(self):
        from core.path_utils import is_path_under_dir
        assert is_path_under_dir("file:///E:/media/video.mp4", "file:///E:/media/") is True

    def test_unrelated_path(self):
        from core.path_utils import is_path_under_dir
        assert is_path_under_dir("file:///C:/Videos/video.mp4", "file:///E:/media") is False


# ============ TestUriToFsPath ============

class TestUriToFsPath:
    """測試 uri_to_fs_path() — file:/// URI → 檔案系統路徑"""

    def test_windows_drive_letter(self, monkeypatch):
        """Windows drive-letter: file:///C:/Videos/test.mp4 → C:\\Videos\\test.mp4（Windows 環境）"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'windows')
        result = path_utils.uri_to_fs_path('file:///C:/Videos/test.mp4')
        assert result == 'C:\\Videos\\test.mp4'

    def test_unix_path_linux(self, monkeypatch):
        """Unix path: file:///home/user/test.mp4 → /home/user/test.mp4（Linux 環境）"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'linux')
        result = path_utils.uri_to_fs_path('file:///home/user/test.mp4')
        assert result == '/home/user/test.mp4'

    def test_wsl_path(self, monkeypatch):
        """WSL mount path: file:///mnt/c/Videos/test.mp4 → /mnt/c/Videos/test.mp4（WSL 環境）"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'wsl')
        result = path_utils.uri_to_fs_path('file:///mnt/c/Videos/test.mp4')
        assert result == '/mnt/c/Videos/test.mp4'

    def test_url_encoded_spaces(self, monkeypatch):
        """URL decode: file:///C:/My%20Videos/test.mp4 → C:\\My Videos\\test.mp4（Windows 環境）"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'windows')
        result = path_utils.uri_to_fs_path('file:///C:/My%20Videos/test.mp4')
        assert result == 'C:\\My Videos\\test.mp4'

    def test_non_file_uri_passthrough(self, monkeypatch):
        """非 file:/// 輸入原樣通過 normalize_path（Linux 環境）"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'linux')
        result = path_utils.uri_to_fs_path('/mnt/c/test.mp4')
        assert result == '/mnt/c/test.mp4'

    def test_valueerror_fallback(self, monkeypatch):
        """normalize_path 拋 ValueError 時返回原路徑（Linux 環境下 Windows 路徑）"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'linux')
        # Linux 環境收到 Windows drive-letter → normalize_path 拋 ValueError → 原樣返回
        result = path_utils.uri_to_fs_path('file:///C:/Videos/test.mp4')
        # C:/Videos/test.mp4 — normalize_path raises ValueError, fallback to unquoted path
        assert result == 'C:/Videos/test.mp4'

    def test_unc_path(self, monkeypatch):
        """UNC path: file://///server/share/test.mp4 → \\\\server\\share\\test.mp4（Windows 環境）"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'windows')
        result = path_utils.uri_to_fs_path('file://///server/share/test.mp4')
        # 剝除 file:/// → //server/share/test.mp4，to_windows_path 轉換為 \\server\share\test.mp4
        assert result == '\\\\server\\share\\test.mp4'

    def test_unc_ip_windows_env(self, monkeypatch):
        """UNC IP URI 在 Windows 環境轉為反斜線 UNC 路徑"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'windows')
        result = path_utils.uri_to_fs_path('file://///192.168.1.177/media/video.mp4')
        assert result == r'\\192.168.1.177\media\video.mp4'

    def test_unc_roundtrip(self, monkeypatch):
        """to_file_uri → uri_to_fs_path 雙向轉換應還原原始 UNC 路徑（Windows env）"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'windows')
        unc_path = r'\\server\share\video.mp4'
        uri = path_utils.to_file_uri(unc_path)
        assert uri == 'file://///server/share/video.mp4'
        result = path_utils.uri_to_fs_path(uri)
        assert result == unc_path

    def test_url_encoded_cjk(self, monkeypatch):
        """URL decode CJK: file:///home/user/%E5%BD%B1%E7%89%87/test.mp4 → /home/user/影片/test.mp4"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'linux')
        result = path_utils.uri_to_fs_path('file:///home/user/%E5%BD%B1%E7%89%87/test.mp4')
        assert result == '/home/user/影片/test.mp4'


# ============ 回歸守衛測試（Phase 29 踩過的坑） ============

class TestRegressionGuards:
    """回歸守衛測試 — 防止已修復的錯誤模式重新出現"""

    def test_to_file_uri_windows_path_any_platform(self):
        """T2 回歸守衛：to_file_uri() 接受 Windows 路徑，不依賴 normalize_path()

        根因：showcase.py 原本用 to_file_uri(normalize_path(d))，
        Linux CI 下 normalize_path("E:/media") 拋 ValueError，
        導致所有 directory 被 skip、11 個測試失敗。
        """
        result = path_utils.to_file_uri("E:/media")
        assert result == "file:///E:/media"

    def test_to_file_uri_unc_path_any_platform(self):
        """UNC 正斜線直通守衛：to_file_uri() 接受正斜線 UNC，任何平台皆可

        確保 //IP/share 格式在 Linux CI 和 Windows prod 都能正確轉換。
        """
        result = path_utils.to_file_uri("//192.168.1.177/share")
        assert result == "file://///192.168.1.177/share"

    def test_no_normalize_before_to_file_uri(self):
        """靜態掃描守衛：確認專案中沒有 to_file_uri(normalize_path(...)) 疊加模式

        此模式會讓 Linux CI 拒絕 Windows 路徑（normalize_path 拋 ValueError），
        等同 linting 規則。
        """
        import os
        import re

        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        pattern = re.compile(r'to_file_uri\s*\(\s*normalize_path\s*\(')
        scan_dirs = ['core', 'web', 'windows']
        violations = []

        for scan_dir in scan_dirs:
            dir_path = os.path.join(project_root, scan_dir)
            if not os.path.isdir(dir_path):
                continue
            for root, _dirs, files in os.walk(dir_path):
                for fname in files:
                    if not fname.endswith('.py'):
                        continue
                    py_file = os.path.join(root, fname)
                    rel = os.path.relpath(py_file, project_root)
                    with open(py_file, encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    if pattern.search(content):
                        violations.append(rel)

        assert violations == [], (
            f"發現 to_file_uri(normalize_path(...)) 疊加模式，"
            f"請改用 to_file_uri(d, path_mappings)：{violations}"
        )
