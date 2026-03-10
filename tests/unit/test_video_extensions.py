"""test_video_extensions.py - core/video_extensions.py unit tests"""
import importlib.util
import pytest


class TestNormalizeExtensions:
    """normalize_extensions() tests"""

    def test_lowercase(self):
        """uppercase extensions are lowercased"""
        from core.video_extensions import normalize_extensions
        result = normalize_extensions(['.MP4', '.AVI'])
        assert '.mp4' in result
        assert '.avi' in result

    def test_add_dot_prefix(self):
        """extensions without leading dot get one added"""
        from core.video_extensions import normalize_extensions
        result = normalize_extensions(['mp4', 'avi'])
        assert '.mp4' in result
        assert '.avi' in result

    def test_dedup(self):
        """duplicate extensions are removed"""
        from core.video_extensions import normalize_extensions
        result = normalize_extensions(['.mp4', '.MP4', 'mp4'])
        assert len(result) == 1
        assert '.mp4' in result

    def test_strip_whitespace(self):
        """leading/trailing whitespace is stripped"""
        from core.video_extensions import normalize_extensions
        result = normalize_extensions(['  .mp4  ', ' avi '])
        assert '.mp4' in result
        assert '.avi' in result

    def test_empty_list(self):
        """empty list returns empty set"""
        from core.video_extensions import normalize_extensions
        result = normalize_extensions([])
        assert result == set()

    def test_returns_set(self):
        """return type is set"""
        from core.video_extensions import normalize_extensions
        result = normalize_extensions(['.mp4'])
        assert isinstance(result, set)

    def test_string_input_wrapped_in_list(self):
        """a bare string input is wrapped in a list instead of iterating chars"""
        from core.video_extensions import normalize_extensions
        result = normalize_extensions('.mp4')
        assert result == {'.mp4'}, \
            "String input should be wrapped in list, not iterated as characters"


class TestGetVideoExtensions:
    """get_video_extensions(config) tests"""

    def test_reads_from_config(self):
        """reads extensions from config scraper.video_extensions"""
        from core.video_extensions import get_video_extensions
        config = {'scraper': {'video_extensions': ['.mp4', '.avi']}}
        result = get_video_extensions(config)
        assert '.mp4' in result
        assert '.avi' in result

    def test_fallback_when_empty(self):
        """falls back to DEFAULT when video_extensions is empty list"""
        from core.video_extensions import get_video_extensions, DEFAULT_VIDEO_EXTENSIONS
        config = {'scraper': {'video_extensions': []}}
        result = get_video_extensions(config)
        assert result == set(DEFAULT_VIDEO_EXTENSIONS)

    def test_fallback_when_missing(self):
        """falls back to DEFAULT when scraper key is missing"""
        from core.video_extensions import get_video_extensions, DEFAULT_VIDEO_EXTENSIONS
        config = {}
        result = get_video_extensions(config)
        assert result == set(DEFAULT_VIDEO_EXTENSIONS)

    def test_fallback_when_none_config(self):
        """falls back to DEFAULT when config is None"""
        from core.video_extensions import get_video_extensions, DEFAULT_VIDEO_EXTENSIONS
        result = get_video_extensions(None)
        assert result == set(DEFAULT_VIDEO_EXTENSIONS)

    def test_normalizes_config_values(self):
        """config values are normalized (lowercase, dot prefix)"""
        from core.video_extensions import get_video_extensions
        config = {'scraper': {'video_extensions': ['MP4', 'avi']}}
        result = get_video_extensions(config)
        assert '.mp4' in result
        assert '.avi' in result

    def test_fallback_when_string_instead_of_list(self):
        """falls back to DEFAULT when video_extensions is a string (malformed config)"""
        from core.video_extensions import get_video_extensions, DEFAULT_VIDEO_EXTENSIONS
        config = {'scraper': {'video_extensions': '.mp4'}}
        result = get_video_extensions(config)
        assert result == set(DEFAULT_VIDEO_EXTENSIONS), \
            "String config value should fall back to DEFAULT, not iterate over characters"


class TestGetProxyExtensions:
    """get_proxy_extensions(config) tests"""

    def test_intersection_with_safe(self):
        """result is intersection of config extensions and SAFE_PROXY_EXTENSIONS"""
        from core.video_extensions import get_proxy_extensions, SAFE_PROXY_EXTENSIONS
        config = {'scraper': {'video_extensions': ['.mp4', '.avi', '.exe']}}
        result = get_proxy_extensions(config)
        assert '.mp4' in result
        assert '.avi' in result
        assert '.exe' not in result

    def test_unsafe_ext_excluded(self):
        """unsafe extension like .exe is excluded"""
        from core.video_extensions import get_proxy_extensions
        config = {'scraper': {'video_extensions': ['.exe']}}
        result = get_proxy_extensions(config)
        assert '.exe' not in result
        assert len(result) == 0

    def test_strm_not_in_proxy(self):
        """.strm is NOT in proxy extensions (it's a text file, not a video stream)"""
        from core.video_extensions import get_proxy_extensions, DEFAULT_VIDEO_EXTENSIONS
        config = {'scraper': {'video_extensions': list(DEFAULT_VIDEO_EXTENSIONS)}}
        result = get_proxy_extensions(config)
        assert '.strm' not in result


class TestConstants:
    """Constants tests"""

    def test_zero_size_extensions_contains_strm(self):
        """.strm is in ZERO_SIZE_EXTENSIONS"""
        from core.video_extensions import ZERO_SIZE_EXTENSIONS
        assert '.strm' in ZERO_SIZE_EXTENSIONS

    def test_default_contains_strm(self):
        """DEFAULT_VIDEO_EXTENSIONS contains .strm"""
        from core.video_extensions import DEFAULT_VIDEO_EXTENSIONS
        assert '.strm' in DEFAULT_VIDEO_EXTENSIONS

    def test_default_contains_webm(self):
        """DEFAULT_VIDEO_EXTENSIONS contains .webm"""
        from core.video_extensions import DEFAULT_VIDEO_EXTENSIONS
        assert '.webm' in DEFAULT_VIDEO_EXTENSIONS

    def test_default_contains_iso(self):
        """DEFAULT_VIDEO_EXTENSIONS contains .iso"""
        from core.video_extensions import DEFAULT_VIDEO_EXTENSIONS
        assert '.iso' in DEFAULT_VIDEO_EXTENSIONS

    def test_default_is_tuple(self):
        """DEFAULT_VIDEO_EXTENSIONS is a tuple (immutable, stable order)"""
        from core.video_extensions import DEFAULT_VIDEO_EXTENSIONS
        assert isinstance(DEFAULT_VIDEO_EXTENSIONS, tuple)

    def test_safe_proxy_is_frozenset(self):
        """SAFE_PROXY_EXTENSIONS is a frozenset"""
        from core.video_extensions import SAFE_PROXY_EXTENSIONS
        assert isinstance(SAFE_PROXY_EXTENSIONS, frozenset)

    def test_zero_size_is_frozenset(self):
        """ZERO_SIZE_EXTENSIONS is a frozenset"""
        from core.video_extensions import ZERO_SIZE_EXTENSIONS
        assert isinstance(ZERO_SIZE_EXTENSIONS, frozenset)


@pytest.mark.skipif(
    not importlib.util.find_spec("webview"),
    reason="pywebview not installed (Windows-only)"
)
class TestIsVideoFile:
    """is_video_file() from pywebview_api tests"""

    def test_default_extensions(self):
        """without extensions param, uses module-level VIDEO_EXTENSIONS"""
        from windows.pywebview_api import is_video_file
        assert is_video_file('test.mp4') is True
        assert is_video_file('test.txt') is False

    def test_custom_extensions(self):
        """with extensions param, uses provided set"""
        from windows.pywebview_api import is_video_file
        custom = {'.xyz', '.abc'}
        assert is_video_file('test.xyz', extensions=custom) is True
        assert is_video_file('test.mp4', extensions=custom) is False

    def test_custom_extensions_none_uses_default(self):
        """with extensions=None, falls back to module-level default"""
        from windows.pywebview_api import is_video_file
        assert is_video_file('test.mp4', extensions=None) is True
