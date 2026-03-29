"""
tests/unit/test_scraper_locale.py — JavBus 語系接線單元測試

測試 _get_javbus_lang() 與各搜尋函數的 lang 參數傳遞。
全 mock，不連網。
"""

import pytest
from unittest.mock import patch, MagicMock
from core.scraper import _get_javbus_lang, _LOCALE_TO_JAVBUS, search_prefix


class TestGetJavbusLang:
    """_get_javbus_lang() 對各 locale 轉換的測試"""

    def test_zh_tw_returns_zh_tw(self):
        with patch('core.scraper.load_config', return_value={'general': {'locale': 'zh-TW'}}):
            assert _get_javbus_lang() == "zh-tw"

    def test_zh_cn_uses_zh_tw(self):
        """zh-CN 無簡中版 JavBus，應使用繁中 zh-tw"""
        with patch('core.scraper.load_config', return_value={'general': {'locale': 'zh-CN'}}):
            assert _get_javbus_lang() == "zh-tw"

    def test_ja_returns_ja(self):
        with patch('core.scraper.load_config', return_value={'general': {'locale': 'ja'}}):
            assert _get_javbus_lang() == "ja"

    def test_en_returns_en(self):
        with patch('core.scraper.load_config', return_value={'general': {'locale': 'en'}}):
            assert _get_javbus_lang() == "en"

    def test_missing_locale_key_returns_zh_tw(self):
        """config 中無 locale key，應 fallback 為 zh-tw"""
        with patch('core.scraper.load_config', return_value={'general': {}}):
            assert _get_javbus_lang() == "zh-tw"

    def test_missing_general_section_returns_zh_tw(self):
        """config 中無 general section，應 fallback 為 zh-tw"""
        with patch('core.scraper.load_config', return_value={}):
            assert _get_javbus_lang() == "zh-tw"

    def test_config_exception_returns_zh_tw(self):
        """load_config 拋例外，應安全 fallback 為 zh-tw 不影響搜尋"""
        with patch('core.scraper.load_config', side_effect=Exception("config error")):
            assert _get_javbus_lang() == "zh-tw"

    def test_unknown_locale_returns_zh_tw(self):
        """未知 locale 應 fallback 為 zh-tw"""
        with patch('core.scraper.load_config', return_value={'general': {'locale': 'fr'}}):
            assert _get_javbus_lang() == "zh-tw"

    def test_locale_to_javbus_mapping_completeness(self):
        """確認 mapping 包含所有支援的 locale"""
        assert "zh-TW" in _LOCALE_TO_JAVBUS
        assert "zh-CN" in _LOCALE_TO_JAVBUS
        assert "ja" in _LOCALE_TO_JAVBUS
        assert "en" in _LOCALE_TO_JAVBUS
        assert _LOCALE_TO_JAVBUS["zh-CN"] == "zh-tw"  # zh-CN 沿用繁中


class TestSearchPrefixLangParam:
    """search_prefix 建立的 JavBusScraper 應傳入正確 lang"""

    def test_javbus_receives_ja_lang(self):
        with patch('core.scraper.load_config', return_value={'general': {'locale': 'ja'}}):
            with patch('core.scraper.JavBusScraper') as MockScraper:
                mock_instance = MagicMock()
                mock_instance.get_ids_from_search.return_value = []
                MockScraper.return_value = mock_instance
                search_prefix("SONE")
                MockScraper.assert_called_once_with(lang="ja")

    def test_javbus_receives_en_lang(self):
        with patch('core.scraper.load_config', return_value={'general': {'locale': 'en'}}):
            with patch('core.scraper.JavBusScraper') as MockScraper:
                mock_instance = MagicMock()
                mock_instance.get_ids_from_search.return_value = []
                MockScraper.return_value = mock_instance
                search_prefix("SONE")
                MockScraper.assert_called_once_with(lang="en")

    def test_javbus_receives_zh_tw_lang(self):
        with patch('core.scraper.load_config', return_value={'general': {'locale': 'zh-TW'}}):
            with patch('core.scraper.JavBusScraper') as MockScraper:
                mock_instance = MagicMock()
                mock_instance.get_ids_from_search.return_value = []
                MockScraper.return_value = mock_instance
                search_prefix("SONE")
                MockScraper.assert_called_once_with(lang="zh-tw")
