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

import logging
import ntpath
import os
import types

import pytest
from unittest.mock import patch, mock_open

# 測試目標模組
import core.path_utils as path_utils


# ============ TestDetectEnvironment ============

class TestDetectEnvironment:
    """測試環境偵測邏輯"""


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


# ============ TestToWslPath ============

class TestToWslPath:
    """測試 Windows/WSL 路徑轉換成 WSL 格式"""

    # --- Windows 本地路徑 ---


    # --- WSL 網路路徑 ---
    def test_wsl_localhost_ubuntu(self):
        """\\\\wsl.localhost\\Ubuntu 格式"""
        result = path_utils.to_wsl_path(r'\\wsl.localhost\Ubuntu\home\user')
        assert result == '/home/user'


    # --- 已是 Unix 路徑 ---


    # --- 錯誤處理 ---


# ============ TestToWindowsPath ============

class TestToWindowsPath:
    """測試 WSL 路徑轉換成 Windows 格式"""

    # --- WSL mount 路徑 ---


    # --- 已是 Windows 路徑 ---


    # --- UNC 路徑 ---
    def test_unc_path_unchanged(self):
        """UNC 路徑不變"""
        result = path_utils.to_windows_path(r'\\NAS\share')
        assert result == r'\\NAS\share'

    # --- 錯誤處理 ---


    def test_unc_forward_slash_ip(self):
        """正斜線 UNC + IP 位址轉反斜線"""
        result = path_utils.to_windows_path('//192.168.1.177/media/video.mp4')
        assert result == r'\\192.168.1.177\media\video.mp4'


    def test_drive_letter_forward_slash(self):
        """C:/... 正斜線轉反斜線"""
        result = path_utils.to_windows_path('C:/Users/peace/video.mp4')
        assert result == r'C:\Users\peace\video.mp4'


# ============ TestToUnixPath ============


# ============ TestNormalizePath ============

class TestNormalizePath:
    """測試根據當前環境自動轉換路徑"""

    def test_wsl_env_windows_input(self, monkeypatch):
        """WSL 環境下輸入 Windows 路徑"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'wsl')
        result = path_utils.normalize_path(r'C:\Users\test')
        assert result == '/mnt/c/Users/test'


    def test_windows_env_mnt_input(self, monkeypatch):
        """Windows 環境下輸入 WSL mount 路徑"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'windows')
        result = path_utils.normalize_path('/mnt/c/Users/test')
        assert result == r'C:\Users\test'


    def test_linux_env_windows_input_raises(self, monkeypatch):
        """Linux 環境下輸入 Windows 路徑應報錯"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'linux')
        with pytest.raises(ValueError):
            path_utils.normalize_path(r'C:\test')


# ============ TestExpandEnvVars ============


# ============ TestGetEnvironment ============


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


    # --- WSL mount 路徑 ---
    @pytest.mark.parametrize('fs_path, expected', [
        ('/mnt/c/Videos/test.mp4', 'file:///C:/Videos/test.mp4'),
        ('/mnt/d', 'file:///D:'),
        # WSL 裡自己掛的 /mnt/<多字母> 不是磁碟代號
        ('/mnt/nas/av/test.mp4', 'file:////mnt/nas/av/test.mp4'),
    ])
    @pytest.mark.parametrize('env', ['wsl', 'windows'])
    def test_wsl_mount_drive_letter_only(self, monkeypatch, env, fs_path, expected):
        """WSL／Windows：只有 /mnt/<單一字母> 才是 Windows 磁碟（Windows 上是 WSL 時期的舊設定）"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', env)
        assert path_utils.to_file_uri(fs_path) == expected

    @pytest.mark.parametrize('env', ['linux', 'mac'])
    @pytest.mark.parametrize('fs_path', [
        '/mnt/backup/av/test.mp4',
        '/mnt/nas/av/test.mp4',
        '/mnt/d/av/test.mp4',
        '/mnt/c/Videos/test.mp4',
    ])
    def test_non_wsl_mnt_path_round_trips(self, monkeypatch, env, fs_path):
        """Linux／Mac：片庫在 /mnt 底下，轉成 URI 再轉回來必須是原路徑（不得變成 B:ackup/...）"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', env)
        uri = path_utils.to_file_uri(fs_path)
        assert uri == 'file:///' + fs_path
        assert path_utils.uri_to_fs_path(uri) == fs_path


    # --- UNC 路徑（網路路徑） ---
    def test_unc_standard_backslash(self):
        """標準 UNC 反斜線路徑"""
        result = path_utils.to_file_uri(r'\\server\share\test.mp4')
        assert result == 'file://///server/share/test.mp4'


    # --- UNC 邊緣案例（D.1.3 修復） ---


    # --- 一致性測試（確保與 scan_file 相同） ---

    # --- path_mappings 測試 ---
    def test_path_mappings_unc(self, monkeypatch):
        """WSL 環境下 path_mappings 轉換 UNC"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'wsl')
        mappings = {'/home/user/nas': r'\\DiskStation\share'}
        result = path_utils.to_file_uri('/home/user/nas/Videos/test.mp4', mappings)
        assert result == 'file://///DiskStation/share/Videos/test.mp4'


    # -------- T7 P1 boundary check --------

    def test_p1_boundary_share_vs_share2(self, monkeypatch):
        """P1 主案例：wsl_prefix /home/user/share 不應命中 /home/user/share2/..."""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'wsl')
        mappings = {'/home/user/share': '//NAS/share'}
        result = path_utils.to_file_uri('/home/user/share2/video.mp4', mappings)
        # 期望：fallback 為原路徑 file:/// 形式
        assert result == 'file:////home/user/share2/video.mp4'
        # 注意：abs_path 是 POSIX 路徑（不以 / 結尾），fallback 走 L294 → file:/// + abs_path
        # = file:/// + /home/user/share2/video.mp4 = file:////home/user/share2/video.mp4（4 個斜線）


    # -------- T7 P2 trailing slash --------


    def test_p2_both_prefixes_trailing_slash(self, monkeypatch):
        """P2 兩邊都有 trailing /，結果正確"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'wsl')
        mappings = {'/home/user/share/': '//NAS/share/'}
        result = path_utils.to_file_uri('/home/user/share/video.mp4', mappings)
        assert result == 'file://///NAS/share/video.mp4'

    # -------- T7 edge cases --------


    def test_non_wsl_env_no_mapping_branch(self, monkeypatch):
        """edge：CURRENT_ENV='linux' 不走 mapping branch，直接 fallback"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'linux')
        mappings = {'/home/user/share': '//NAS/share'}
        result = path_utils.to_file_uri('/home/user/share/video.mp4', mappings)
        assert result == 'file:////home/user/share/video.mp4'


class TestToFileUriPlainUnix:
    """測試 to_file_uri() 對純 Unix 路徑的處理（無 path_mappings）"""

    def test_to_file_uri_plain_unix(self):
        """純 Unix 路徑在無 mappings 時直接 fallback 為 file:////home/..."""
        result = path_utils.to_file_uri('/home/user/video.mp4')
        assert result == 'file:////home/user/video.mp4'


class TestIsPathUnderDir:
    """測試 is_path_under_dir — 避免前綴碰撞"""


    def test_prefix_collision_rejected(self):
        """E:/media 不應匹配 E:/media2 底下的檔案"""
        from core.path_utils import is_path_under_dir
        assert is_path_under_dir("file:///E:/media2/video.mp4", "file:///E:/media") is False


    # ---- 新增：UNC 大小寫不敏感 cases ----

    def test_unc_host_uppercase(self):
        """UNC host 大寫：DISKSTATION vs DiskStation → True（Windows 不分大小寫）"""
        from core.path_utils import is_path_under_dir, to_file_uri
        path_uri = to_file_uri(r'\\DISKSTATION\usbshare1\a.jpg')
        dir_uri = to_file_uri(r'\\DiskStation\usbshare1')
        assert is_path_under_dir(path_uri, dir_uri) is True


    def test_posix_case_sensitive(self):
        """POSIX 路徑大小寫敏感：/home/User ≠ /home/user → False"""
        from core.path_utils import is_path_under_dir, to_file_uri
        path_uri = to_file_uri('/home/User/a.jpg')
        dir_uri = to_file_uri('/home/user')
        assert is_path_under_dir(path_uri, dir_uri) is False


# ============ TestStripVerbatimPrefix ============

class TestStripVerbatimPrefix:
    r"""測試 strip_verbatim_prefix() — 移除 Windows verbatim \\?\ 前綴"""


    def test_verbatim_drive(self):
        r"""\\?\C:\Videos\a.jpg → C:\Videos\a.jpg"""
        from core.path_utils import strip_verbatim_prefix
        result = strip_verbatim_prefix(r'\\?\C:\Videos\a.jpg')
        assert result == r'C:\Videos\a.jpg'


    def test_to_file_uri_verbatim_equals_plain_unc(self):
        r"""to_file_uri(\\?\UNC\DiskStation\...) == to_file_uri(\\DiskStation\...)（strip 生效）"""
        from core.path_utils import to_file_uri
        verbatim = to_file_uri(r'\\?\UNC\DiskStation\usbshare1\a.jpg')
        plain = to_file_uri(r'\\DiskStation\usbshare1\a.jpg')
        assert verbatim == plain


# ============ TestIsWindowsStyleUri ============


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


    def test_valueerror_fallback(self, monkeypatch):
        """normalize_path 拋 ValueError 時返回原路徑（Linux 環境下 Windows 路徑）"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'linux')
        # Linux 環境收到 Windows drive-letter → normalize_path 拋 ValueError → 原樣返回
        result = path_utils.uri_to_fs_path('file:///C:/Videos/test.mp4')
        # C:/Videos/test.mp4 — normalize_path raises ValueError, fallback to unquoted path
        assert result == 'C:/Videos/test.mp4'


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


# ============ TestReversePathMapping ============

class TestReversePathMapping:
    """測試 reverse_path_mapping() - 邊界條件 1-11"""


    def test_multi_mapping_second_wins(self):
        """邊界 6：多個 mapping，第二個才命中"""
        from core.path_utils import reverse_path_mapping
        mappings = {
            "/mnt/other": "//OTHER/share",
            "/mnt/nas": "//NAS/share",
        }
        result = reverse_path_mapping("//NAS/share/movie.mp4", mappings)
        assert result == "/mnt/nas/movie.mp4"


    def test_drive_letter_mapping(self):
        """邊界 9：Windows drive letter mapping"""
        from core.path_utils import reverse_path_mapping
        mappings = {"/mnt/c/Videos": "C:/Videos"}
        result = reverse_path_mapping("C:\\Videos\\movie.mp4", mappings)
        assert result == "/mnt/c/Videos/movie.mp4"


    # -------- P1 boundary check (新增 T6) --------

    def test_p1_forward_slash_share_vs_share2(self):
        """邊界 2：//NAS/share2/video.mp4 不應命中 //NAS/share mapping（P1 主案例）"""
        from core.path_utils import reverse_path_mapping
        mappings = {"/local": "//NAS/share"}
        result = reverse_path_mapping("//NAS/share2/video.mp4", mappings)
        assert result is None


    # -------- P2 trailing separator normalize (新增 T6) --------


    def test_p2_both_prefixes_trailing_slash(self):
        """邊界 3+12：win_prefix 和 local_prefix 都含 trailing /，結果仍正確"""
        from core.path_utils import reverse_path_mapping
        mappings = {"/local/": "//NAS/share/"}
        result = reverse_path_mapping("//NAS/share/video.mp4", mappings)
        assert result == "/local/video.mp4"

    # -------- P1 edge cases --------


    # -------- 91b P2 fix：drive-letter remote WSL-mount 候選 --------


# ============ TestIsPathUnderDirNFC ============

class TestIsPathUnderDirNFC:
    """
    TASK-62-path-unicode-nfc：is_path_under_dir Windows-style 分支 NFC/NFD 正規化守衛。

    所有 NFC/NFD 形式一律用 unicodedata.normalize() 程式化產生。
    POSIX 安全負向 case（Codex P1）確保 POSIX 分支維持 byte-exact 不折疊。
    """

    # ------------------------------------------------------------------
    # 邊界 1：UNC NFC dir + NFD path → True
    # ------------------------------------------------------------------
    def test_unc_nfc_dir_nfd_path(self):
        """UNC：NFC 目錄 + NFD 子路徑 → True（Windows-style NFC 正規化）"""
        import unicodedata
        from core.path_utils import is_path_under_dir, to_file_uri

        base = 'Répertoire'
        dir_nfc = unicodedata.normalize('NFC', base)   # é = U+00E9
        path_nfd = unicodedata.normalize('NFD', base)  # é = e + U+0301

        dir_uri  = to_file_uri(rf'\\NAS\{dir_nfc}')
        path_uri = to_file_uri(rf'\\NAS\{path_nfd}\video.jpg')

        assert is_path_under_dir(path_uri, dir_uri) is True

    # ------------------------------------------------------------------
    # 邊界 2：UNC NFD dir + NFC path → True（反向）
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # 邊界 3：UNC NFD + 大寫 → 命中 NFC + 小寫（驗 NFC→casefold 順序）
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # 邊界 4：Drive-letter NFD path → 命中 NFC dir
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # 邊界 5：韓文 Hangul NFC vs NFD（UNC）
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # 邊界 5b：Drive-letter Hangul NFC vs NFD
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # 邊界 6：Windows-style 同形式不回歸（NFC/NFC、NFD/NFD 仍 True）
    # ------------------------------------------------------------------


    # ------------------------------------------------------------------
    # POSIX 安全負向 case 7（Codex P1）：POSIX byte-exact，NFC ≠ NFD → False
    # ------------------------------------------------------------------
    def test_posix_nfc_dir_does_not_match_nfd_path(self):
        """
        Codex P1 安全守衛：POSIX NFC 目錄白名單不放行 NFD byte-distinct 子路徑。

        Linux ext4/xfs 的 NFC 與 NFD 是不同的 byte 序列 → 不同路徑，可並存。
        折疊它們 = 誤放行白名單外的檔案（安全漏洞）。
        """
        import unicodedata
        from core.path_utils import is_path_under_dir, to_file_uri, _is_windows_style_uri

        base = 'Répertoire'
        nfc_str = unicodedata.normalize('NFC', base)
        nfd_str = unicodedata.normalize('NFD', base)

        # 確認 NFC != NFD（若相等測試無意義）
        assert nfc_str != nfd_str, 'NFC == NFD，無 byte 差異，測試前提不成立'

        # 產生 POSIX URI（4 斜線）
        dir_uri  = to_file_uri(f'/media/{nfc_str}')   # file:////media/Répertoire(NFC)
        path_uri = to_file_uri(f'/media/{nfd_str}/video.mp4')  # NFD 子路徑

        # 確認 _is_windows_style_uri 對 POSIX URI 回 False
        assert _is_windows_style_uri(dir_uri)  is False, f'期望 POSIX URI，但 {dir_uri!r} 被判為 Windows-style'
        assert _is_windows_style_uri(path_uri) is False, f'期望 POSIX URI，但 {path_uri!r} 被判為 Windows-style'

        # 關鍵安全斷言：POSIX 分支維持 byte-exact，NFD 子路徑不被 NFC 白名單放行
        assert is_path_under_dir(path_uri, dir_uri) is False

    # ------------------------------------------------------------------
    # POSIX 不回歸 8：NFC/NFC 同形式 → True
    # ------------------------------------------------------------------
    def test_posix_nfc_nfc_same_form(self):
        """POSIX NFC/NFC 兩邊 bytes 相同 → True（不回歸）"""
        import unicodedata
        from core.path_utils import is_path_under_dir, to_file_uri

        nfc = unicodedata.normalize('NFC', 'Répertoire')
        dir_uri  = to_file_uri(f'/media/{nfc}')
        path_uri = to_file_uri(f'/media/{nfc}/video.mp4')
        assert is_path_under_dir(path_uri, dir_uri) is True

    # ------------------------------------------------------------------
    # POSIX 不回歸 9：前綴碰撞（/media2 不命中 /media）
    # ------------------------------------------------------------------
    def test_posix_prefix_collision_not_regressed(self):
        """POSIX /media2 不誤命中 /media 白名單"""
        import unicodedata
        from core.path_utils import is_path_under_dir, to_file_uri

        nfc = unicodedata.normalize('NFC', 'Répertoire')
        dir_uri  = to_file_uri(f'/media/{nfc}')
        path_uri = to_file_uri(f'/media2/{nfc}/video.mp4')
        assert is_path_under_dir(path_uri, dir_uri) is False


# ============ TestUriToLocalFsPath ============

class TestUriToLocalFsPath:
    """測試 uri_to_local_fs_path()：file:/// URI → 本機實際可存取 FS 路徑（含 WSL+mapping 反解）"""

    def test_wsl_mapping_hit(self, monkeypatch):
        """WSL + mapping 命中 → 回本機 local FS 路徑，且不等於裸 uri_to_fs_path"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'wsl')
        mappings = {'/home/user/nas': '//NAS/share'}
        uri = 'file://///NAS/share/video.mp4'
        result = path_utils.uri_to_local_fs_path(uri, mappings)
        assert result == '/home/user/nas/video.mp4'
        assert result != path_utils.uri_to_fs_path(uri)

    def test_wsl_mapping_miss(self, monkeypatch):
        """WSL + mapping 未命中 → reverse 回 None → or fs 退回 uri_to_fs_path"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'wsl')
        mappings = {'/home/user/nas': '//NAS/share'}
        uri = 'file:///D:/other/video.mp4'
        result = path_utils.uri_to_local_fs_path(uri, mappings)
        assert result == path_utils.uri_to_fs_path(uri)

    def test_non_wsl_equivalent(self, monkeypatch):
        """非 WSL（即使傳 mappings）→ reverse 分支不觸發，字面等價於 uri_to_fs_path"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'windows')
        mappings = {'/home/user/nas': '//NAS/share'}
        uri = 'file://///NAS/share/video.mp4'
        result = path_utils.uri_to_local_fs_path(uri, mappings)
        assert result == path_utils.uri_to_fs_path(uri)


    def test_drive_letter_remote_reverse_maps_correctly(self, monkeypatch):
        """91b P2：drive-letter remote（Z:/share）經 to_wsl_path 正規化為 /mnt/z/share 後，
        reverse_path_mapping 須能反解回 local_prefix，不可 fallback 回未反解的 /mnt/z/... 路徑"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', 'wsl')
        mappings = {'/nas': 'Z:/share'}
        uri = 'file:///Z:/share/movie.mp4'
        result = path_utils.uri_to_local_fs_path(uri, mappings)
        assert result == '/nas/movie.mp4'
        assert result != path_utils.uri_to_fs_path(uri)


# ============ TestIsFsPathUnderDir ============

class _PartialOsPathProxy:
    """局部覆寫版 os.path proxy，供 is_fs_path_under_dir 的 mock 測試使用。

    只覆寫傳入的函式名稱，其餘屬性一律轉呼叫真正的 os.path——這樣即使
    mutation 自驗換掉實作內部呼叫的函式名稱（例如 realpath 換成 normpath），
    proxy 仍能正常運作、不會因為「這個假物件根本沒有這個屬性」炸出不相干的
    AttributeError，掩蓋掉本來該看到的語意層級紅/綠。

    指派對象是 path_utils 模組自己的 `os` 名稱（見各測試的 monkeypatch.setattr(
    path_utils, 'os', ...)），不是真正全域的 os 模組本身——直接改真 os.path
    的函式會連 pytest 自己組 traceback 用到的路徑解析都一併打壞，一旦這條測試
    在 mutation 驗證中真的斷言失敗，會變成 INTERNALERROR 而不是乾淨的紅。
    """

    def __init__(self, **overrides):
        self._overrides = overrides

    def __getattr__(self, name):
        if name in self._overrides:
            return self._overrides[name]
        return getattr(os.path, name)


class TestIsFsPathUnderDir:
    """測試 is_fs_path_under_dir(fs_path, root_fs_path) —— 原生 FS path containment
    checker（realpath 兩端 → normcase 兩端 → 明確前綴比對 → 例外 fail-closed）。

    與既有 is_path_under_dir(path, dir_uri) 的職責分界：
    - is_path_under_dir：吃 file:/// URI，純字串前綴比對，不解析 ..、不解析 symlink，
      唯一呼叫端 core/readonly_producer.py:418，本 task 零改動。
    - is_fs_path_under_dir：吃原生 FS path，先 realpath 解析 .. 與 symlink 再比對，
      供 T4/T5 兩個新寫入錨點共用。兩者不得互相取代（互套會造成正規化疊加）。
    """

    def test_normal_subdirectory(self, tmp_path):
        """案例 1：正常子目錄 root/a/b vs root → True（happy path）"""
        root = tmp_path / "root"
        target = root / "a" / "b"
        target.mkdir(parents=True)
        assert path_utils.is_fs_path_under_dir(str(target), str(root)) is True

    def test_parent_traversal_escapes_root(self, tmp_path):
        """案例 2（核心）：root/../.. vs root → False。

        CD-110b-4 實測反例：os.path.commonpath(['/base/videos',
        '/base/videos/../../..']) 會回傳 '/base/videos'，若未先 realpath 就比對，
        逃逸路徑會被誤判為「在 root 底下」。
        """
        root = tmp_path / "root"
        root.mkdir()
        target = str(root / ".." / "..")
        assert path_utils.is_fs_path_under_dir(target, str(root)) is False


    def test_root_itself_is_under_root(self, tmp_path):
        """案例 4：root 自身 vs root → True（create_folder=False 的既有路徑會走到這）"""
        root = tmp_path / "root"
        root.mkdir()
        assert path_utils.is_fs_path_under_dir(str(root), str(root)) is True


    def test_symlink_escaping_root_is_rejected(self, tmp_path):
        """案例 6（核心）：symlink 指向 root 外部 → False。

        鎖住「為什麼一定要用 realpath 而不是 normpath」——normpath 只做詞法正規化，
        不會 follow symlink，會讓這條逃逸路徑被誤判為在 root 底下。
        """
        root = tmp_path / "root"
        root.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        link = root / "escape_link"
        link.symlink_to(outside, target_is_directory=True)
        assert path_utils.is_fs_path_under_dir(str(link), str(root)) is False

    def test_not_yet_created_target_path(self, tmp_path):
        """案例 7：目標路徑尚不存在（root/not/created/yet）→ True。

        鎖住 os.path.realpath 的預設 strict=False 語意——target_dir 在檢查時本來就
        還沒建立，若誤傳 strict=True 會對不存在路徑拋 OSError，導致整個整理功能
        fail-closed 壞掉。
        """
        root = tmp_path / "root"
        root.mkdir()
        target = root / "not" / "created" / "yet"
        assert path_utils.is_fs_path_under_dir(str(target), str(root)) is True


    def test_realpath_oserror_fails_closed_and_logs(self, monkeypatch, caplog):
        """案例 9：realpath 拋 OSError（mock，如 WinFsp/rclone 掛載點）→ False 且有
        warning 記錄。monkeypatch 範圍同案例 8，只換掉 path_utils 自己的 `os` 名稱。
        """

        def _raise_os_error(*args, **kwargs):
            raise OSError("mocked mount point failure")

        fake_os = types.SimpleNamespace(path=_PartialOsPathProxy(realpath=_raise_os_error))
        monkeypatch.setattr(path_utils, 'os', fake_os)
        with caplog.at_level(logging.WARNING):
            result = path_utils.is_fs_path_under_dir('/root/target', '/root')
        assert result is False
        assert any(record.levelname == 'WARNING' for record in caplog.records)

    def test_windows_case_insensitive_match(self, monkeypatch):
        """Windows 大小寫（C:\\Foo vs c:\\foo\\bar）→ True（不因大小寫誤殺，
        BE-PATH-01 #9）。

        realpath／normcase 用 ntpath mock；sep 必須明確覆寫為 ntpath.sep，否則
        fallback 到 Linux 的 `/` 會讓前綴比對用錯分隔符。新演算法是大小寫敏感的
        字串比較，normcase 一旦被刪，這條自然轉紅。

        monkeypatch 目標是 path_utils 模組自己的 `os` 名稱，不是真正的全域 os 模組。
        """
        fake_os = types.SimpleNamespace(path=_PartialOsPathProxy(
            realpath=ntpath.realpath,
            normcase=ntpath.normcase,
            sep=ntpath.sep,
        ))
        monkeypatch.setattr(path_utils, 'os', fake_os)
        assert path_utils.is_fs_path_under_dir(r'c:\foo\bar', r'C:\Foo') is True

    def test_unc_share_root_child_is_under_root(self, monkeypatch):
        """UNC bare share root：\\\\server\\share\\x vs \\\\server\\share → True。

        本次 bug 的直接回歸——舊 commonpath 對這組輸入會拋 ValueError 被誤判為
        超出範圍；新前綴比對必須回 True。
        """
        fake_os = types.SimpleNamespace(path=_PartialOsPathProxy(
            realpath=ntpath.realpath,
            normcase=ntpath.normcase,
            sep=ntpath.sep,
        ))
        monkeypatch.setattr(path_utils, 'os', fake_os)
        assert path_utils.is_fs_path_under_dir(r'\\server\share\x', r'\\server\share') is True


    def test_prefix_collision_not_bare_startswith(self, tmp_path):
        """案例 11：前綴碰撞 /base/media2 vs /base/media → False。

        鎖住「不是裸 startswith」——is_path_under_dir 的既有 docstring 說明它存在
        就是為了擋 E:/media 誤匹配 E:/media2，這裡驗證本 helper 的前綴比對是**帶
        分隔符邊界**的（root_n + os.path.sep），不是裸 startswith，且有測試守住
        （未來若被「優化」成不帶分隔符的 startswith 要有東西變紅）。
        """
        base = tmp_path / "base"
        media = base / "media"
        media2 = base / "media2"
        media.mkdir(parents=True)
        media2.mkdir(parents=True)
        assert path_utils.is_fs_path_under_dir(str(media2), str(media)) is False


# ============ TestFileUriToServerPath ============

class TestFileUriToServerPath:
    """測試 file_uri_to_server_path() — file:/// URI → 伺服器命名空間裸字串（不依環境）"""

    @pytest.mark.parametrize('uri, expected', [
        ('file:////media/x.mp4', '/media/x.mp4'),
        ('file://///nas/s/x.mp4', '//nas/s/x.mp4'),
        ('file:///home/u/x.mp4', '/home/u/x.mp4'),
    ])
    def test_posix_and_unc_shapes(self, uri, expected):
        """四斜線 Linux / UNC 五斜線 / 舊式三斜線 Unix → 以 / 開頭的伺服器路徑"""
        assert path_utils.file_uri_to_server_path(uri) == expected

    def test_windows_drive_uri_keeps_drive_form(self):
        """file:///D:/AV/x.mp4 → D:/AV/x.mp4（不補前導 /、不轉反斜線）"""
        assert path_utils.file_uri_to_server_path('file:///D:/AV/x.mp4') == 'D:/AV/x.mp4'

    @pytest.mark.parametrize('uri, expected', [
        ('file:///D:/AV/%E4%B8%AD%E6%96%87/x.mp4', 'D:/AV/中文/x.mp4'),
    ])
    def test_percent_encoding_is_decoded(self, uri, expected):
        """URI 內的 %20 / 中文百分比編碼 → 解碼後的路徑"""
        assert path_utils.file_uri_to_server_path(uri) == expected

    @pytest.mark.parametrize('value', [
        '/volume1/av/a%20b.mp4',
    ])
    def test_non_uri_passthrough_verbatim(self, value):
        """非 URI 輸入逐字不變（%20 不被解碼）"""
        assert path_utils.file_uri_to_server_path(value) == value

    @pytest.mark.parametrize('env', ['windows', ])
    def test_independent_of_current_env(self, monkeypatch, env):
        """CURRENT_ENV 為 windows / linux / wsl 輸出皆相同"""
        monkeypatch.setattr(path_utils, 'CURRENT_ENV', env)
        assert path_utils.file_uri_to_server_path('file:////media/x.mp4') == '/media/x.mp4'
        assert path_utils.file_uri_to_server_path('file:///D:/AV/x.mp4') == 'D:/AV/x.mp4'
