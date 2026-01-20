"""
utils.py 擴充函數的單元測試
"""
import pytest
from core.scrapers.utils import (
    has_japanese, has_chinese, check_subtitle,
    format_number, SOURCE_ORDER, SOURCE_NAMES
)


class TestHasJapanese:
    """has_japanese() 測試"""

    def test_hiragana(self):
        """平假名應返回 True"""
        assert has_japanese("これはテスト") is True

    def test_katakana(self):
        """片假名應返回 True"""
        assert has_japanese("カタカナ") is True

    def test_mixed(self):
        """日文混合中文應返回 True"""
        assert has_japanese("日本語と中文") is True

    def test_chinese_only(self):
        """純中文應返回 False"""
        assert has_japanese("中文標題") is False

    def test_english_only(self):
        """純英文應返回 False"""
        assert has_japanese("English Title") is False

    def test_empty(self):
        """空字串應返回 False"""
        assert has_japanese("") is False

    def test_none(self):
        """None 應返回 False"""
        assert has_japanese(None) is False


class TestHasChinese:
    """has_chinese() 測試"""

    def test_chinese(self):
        """中文應返回 True"""
        assert has_chinese("中文") is True

    def test_mixed(self):
        """中文混合英文應返回 True"""
        assert has_chinese("中文 Title") is True

    def test_japanese_hiragana(self):
        """純平假名應返回 False"""
        assert has_chinese("ひらがな") is False

    def test_japanese_katakana(self):
        """純片假名應返回 False"""
        assert has_chinese("カタカナ") is False

    def test_english_only(self):
        """純英文應返回 False"""
        assert has_chinese("English") is False

    def test_empty(self):
        """空字串應返回 False"""
        assert has_chinese("") is False

    def test_none(self):
        """None 應返回 False"""
        assert has_chinese(None) is False


class TestCheckSubtitle:
    """check_subtitle() 測試"""

    def test_c_suffix(self):
        """-C 後綴應返回 True"""
        assert check_subtitle("ABC-123-C.mp4") is True

    def test_c_underscore(self):
        """_C 後綴應返回 True"""
        assert check_subtitle("ABC-123_C.mp4") is True

    def test_chinese_subtitle_tag(self):
        """中文字幕標記應返回 True"""
        assert check_subtitle("[中文字幕] ABC-123.mp4") is True

    def test_subtitle_tag(self):
        """字幕標記應返回 True"""
        assert check_subtitle("ABC-123 字幕.mp4") is True

    def test_zhongzi_tag(self):
        """中字標記應返回 True"""
        assert check_subtitle("[中字] ABC-123.mp4") is True

    def test_no_subtitle(self):
        """無字幕標記應返回 False"""
        assert check_subtitle("ABC-123.mp4") is False

    def test_c_in_number(self):
        """番號中的 C 不應誤判"""
        assert check_subtitle("CAWD-123.mp4") is False

    def test_empty(self):
        """空字串應返回 False"""
        assert check_subtitle("") is False

    def test_none(self):
        """None 應返回 False"""
        assert check_subtitle(None) is False


class TestFormatNumber:
    """format_number() 測試"""

    def test_lowercase(self):
        """小寫應轉大寫"""
        assert format_number("sone-205") == "SONE-205"

    def test_whitespace(self):
        """應去除前後空白"""
        assert format_number("  ABC-123  ") == "ABC-123"

    def test_already_formatted(self):
        """已格式化的應保持不變"""
        assert format_number("ABC-123") == "ABC-123"

    def test_empty(self):
        """空字串應返回空字串"""
        assert format_number("") == ""

    def test_none(self):
        """None 應返回 None"""
        assert format_number(None) is None


class TestSourceConfig:
    """來源配置常數測試"""

    def test_source_order_not_empty(self):
        """SOURCE_ORDER 不應為空"""
        assert len(SOURCE_ORDER) > 0

    def test_source_order_content(self):
        """SOURCE_ORDER 應包含預期來源"""
        assert 'javbus' in SOURCE_ORDER
        assert 'jav321' in SOURCE_ORDER
        assert 'javdb' in SOURCE_ORDER

    def test_source_names_match_order(self):
        """SOURCE_NAMES 應包含所有 SOURCE_ORDER 的鍵"""
        for source in SOURCE_ORDER:
            assert source in SOURCE_NAMES

    def test_source_names_values(self):
        """SOURCE_NAMES 的值應為字串"""
        for name in SOURCE_NAMES.values():
            assert isinstance(name, str)
            assert len(name) > 0
