"""
tests/unit/test_scraper_locale.py — JavBus 語系接線單元測試

測試 get_javbus_lang() 與各搜尋函數的 lang 參數傳遞。
全 mock，不連網。
"""

from unittest.mock import patch, MagicMock
from core.scraper import get_javbus_lang, search_prefix


class TestGetJavbusLang:
    """get_javbus_lang() 對各 locale 轉換的測試"""


    def test_zh_cn_uses_zh_tw(self):
        """zh-CN 無簡中版 JavBus，應使用繁中 zh-tw"""
        with patch('core.scraper.load_config', return_value={'general': {'locale': 'zh-CN'}}):
            assert get_javbus_lang() == "zh-tw"

    def test_ko_uses_ja_javbus(self):
        """ko 無韓文版 JavBus，應使用日文 ja（標題含假名才會被翻成韓文）"""
        with patch('core.scraper.load_config', return_value={'general': {'locale': 'ko'}}):
            assert get_javbus_lang() == "ja"


class TestSearchPrefixLangParam:
    """search_prefix 建立的 JavBusScraper 應傳入正確 lang"""

    def test_javbus_receives_ja_lang(self):
        with patch('core.scraper.load_config', return_value={'general': {'locale': 'ja'}}):
            with patch('core.scraper.get_all_source_ids_ordered', return_value=['javbus']), \
                 patch('core.scraper.JavBusScraper') as MockScraper:
                mock_instance = MagicMock()
                mock_instance.get_ids_from_search.return_value = []
                MockScraper.return_value = mock_instance
                search_prefix("SONE")
                MockScraper.assert_called_once_with(lang="ja")


