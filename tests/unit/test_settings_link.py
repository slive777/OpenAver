"""
Unit tests for core/settings_link.py — find_matched_directory()
全 mock，無外部依賴。
"""
import pytest
from unittest.mock import patch
from core.path_utils import to_file_uri as _real_to_file_uri


# ─────────────────────────────────────────────
# import subject under test
# ─────────────────────────────────────────────

from core.settings_link import find_matched_directory  # noqa: E402


# ─────────────────────────────────────────────
# T1: empty favorite → None
# ─────────────────────────────────────────────

class TestEmptyFavorite:
    def test_empty_string_returns_none(self):
        result = find_matched_directory('', ['/mnt/e/media'])
        assert result is None

    def test_whitespace_only_returns_none(self):
        result = find_matched_directory('   ', ['/mnt/e/media'])
        assert result is None


# ─────────────────────────────────────────────
# T2: exact match
# ─────────────────────────────────────────────

class TestExactMatch:
    def test_exact_match_returns_directory(self):
        """favorite 精確等於 directory → 回傳該 directory"""
        with patch('core.settings_link.expand_env_vars', return_value='/mnt/e/media'), \
             patch('core.settings_link.normalize_path', side_effect=lambda x: x), \
             patch('core.settings_link.to_file_uri', side_effect=_real_to_file_uri):
            result = find_matched_directory('/mnt/e/media', ['/mnt/e/media'])
        assert result == '/mnt/e/media'

    def test_uri_form_directory_matched(self):
        """PR#91: directory 已是 file:/// URI（schema「FS 路徑或 URI」）→ 仍能命中。

        pre-fix `normalize_path` 對 URI 原樣通過 → `to_file_uri` 二次包成
        file:///file:///… → 永不命中（RED）。改用 uri_to_fs_path 後冪等命中。
        favorite 端維持 FS 路徑（真實使用者最愛資料夾）。
        """
        uri_dir = _real_to_file_uri('/home/user/media')
        with patch('core.settings_link.expand_env_vars', return_value='/home/user/media/jav'), \
             patch('core.settings_link.normalize_path', side_effect=lambda x: x), \
             patch('core.settings_link.to_file_uri', side_effect=_real_to_file_uri):
            result = find_matched_directory('/home/user/media/jav', [uri_dir])
        assert result == uri_dir

    def test_exact_match_first_of_multiple(self):
        """多個 directories，精確命中第一個"""
        with patch('core.settings_link.expand_env_vars', return_value='/mnt/e/media'), \
             patch('core.settings_link.normalize_path', side_effect=lambda x: x), \
             patch('core.settings_link.to_file_uri', side_effect=_real_to_file_uri):
            result = find_matched_directory(
                '/mnt/e/media',
                ['/mnt/e/media', '/mnt/f/videos']
            )
        assert result == '/mnt/e/media'


# ─────────────────────────────────────────────
# T3: subdirectory match
# ─────────────────────────────────────────────

class TestSubdirectoryMatch:
    def test_subdirectory_returns_parent_directory(self):
        """favorite 是某 directory 子目錄 → 回傳父 directory"""
        with patch('core.settings_link.expand_env_vars', return_value='/mnt/e/media/jav'), \
             patch('core.settings_link.normalize_path', side_effect=lambda x: x), \
             patch('core.settings_link.to_file_uri', side_effect=_real_to_file_uri):
            result = find_matched_directory(
                '/mnt/e/media/jav',
                ['/mnt/e/media', '/mnt/f/videos']
            )
        assert result == '/mnt/e/media'


# ─────────────────────────────────────────────
# T4: no match
# ─────────────────────────────────────────────

class TestNoMatch:
    def test_not_under_any_directory(self):
        """favorite 不在任何 directory 範圍 → None"""
        with patch('core.settings_link.expand_env_vars', return_value='/mnt/g/other'), \
             patch('core.settings_link.normalize_path', side_effect=lambda x: x), \
             patch('core.settings_link.to_file_uri', side_effect=_real_to_file_uri):
            result = find_matched_directory(
                '/mnt/g/other',
                ['/mnt/e/media', '/mnt/f/videos']
            )
        assert result is None

    def test_prefix_collision_not_matched(self):
        """E:/media 不可誤匹配 E:/media2 (前綴碰撞防護)"""
        with patch('core.settings_link.expand_env_vars', return_value='/mnt/e/media2'), \
             patch('core.settings_link.normalize_path', side_effect=lambda x: x), \
             patch('core.settings_link.to_file_uri', side_effect=_real_to_file_uri):
            result = find_matched_directory(
                '/mnt/e/media2',
                ['/mnt/e/media']
            )
        assert result is None


# ─────────────────────────────────────────────
# T5: empty directories list
# ─────────────────────────────────────────────

class TestEmptyDirectories:
    def test_empty_directories_list_returns_none(self):
        with patch('core.settings_link.expand_env_vars', return_value='/mnt/e/media'), \
             patch('core.settings_link.normalize_path', side_effect=lambda x: x), \
             patch('core.settings_link.to_file_uri', side_effect=_real_to_file_uri):
            result = find_matched_directory('/mnt/e/media', [])
        assert result is None


# ─────────────────────────────────────────────
# T6: WSL path_mappings forwarded
# ─────────────────────────────────────────────

class TestPathMappings:
    def test_path_mappings_passed_to_to_file_uri(self):
        """path_mappings 必須轉傳給 to_file_uri（CD-58-B1-3a）"""
        call_args = []

        def fake_to_file_uri(p, pm=None):
            call_args.append(pm)
            return _real_to_file_uri(p, pm)

        mappings = {'/mnt/e': 'E:'}
        with patch('core.settings_link.expand_env_vars', return_value='/mnt/e/media'), \
             patch('core.settings_link.normalize_path', side_effect=lambda x: x), \
             patch('core.settings_link.to_file_uri', side_effect=fake_to_file_uri):
            find_matched_directory('/mnt/e/media', ['/mnt/e/media'], path_mappings=mappings)

        # 所有呼叫都帶了 path_mappings
        assert all(pm == mappings for pm in call_args), \
            f"Expected all calls with mappings={mappings}, got {call_args}"


# ─────────────────────────────────────────────
# T7: expand_env_vars ValueError on Linux/Mac
# ─────────────────────────────────────────────

class TestExpandEnvVarsError:
    def test_value_error_returns_none(self):
        """Linux/Mac 對 %USERPROFILE% 拋 ValueError → find_matched_directory 回 None（不 crash）"""
        with patch('core.settings_link.expand_env_vars',
                   side_effect=ValueError("當前環境不支援 Windows 環境變數")):
            result = find_matched_directory(
                '%USERPROFILE%\\Downloads',
                ['/mnt/c/Users/user/Downloads']
            )
        assert result is None

    def test_value_error_on_linux_real_expand(self):
        """實際呼叫 expand_env_vars (不 mock)：Linux 環境對 %USERPROFILE% 拋 ValueError"""
        import sys
        if sys.platform == 'win32':
            pytest.skip("Windows 環境不適用此 test")

        # 若非 WSL 亦非 Windows，expand_env_vars 應拋 ValueError
        from core.path_utils import get_environment
        env = get_environment()
        if env in ('wsl', 'windows'):
            pytest.skip(f"WSL/Windows 環境不適用此 test (env={env})")

        # 純 Linux/Mac：直接呼叫真實函式
        result = find_matched_directory(
            '%USERPROFILE%\\Downloads',
            ['/home/user/Downloads']
        )
        assert result is None


# ─────────────────────────────────────────────
# T8: tilde expansion
# ─────────────────────────────────────────────

class TestTildeExpansion:
    def test_tilde_expanded_and_matched(self):
        """favorite 含 ~ → expand_env_vars 展開後比對"""
        import os
        home = os.path.expanduser('~')

        with patch('core.settings_link.expand_env_vars', return_value=home), \
             patch('core.settings_link.normalize_path', side_effect=lambda x: x), \
             patch('core.settings_link.to_file_uri', side_effect=_real_to_file_uri):
            result = find_matched_directory('~', [home])
        assert result == home
