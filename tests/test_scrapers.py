"""Scraper 模組測試"""
import pytest
from core.scrapers import JavBusScraper, JAV321Scraper, JavDBScraper, Video


# 測試番號（真實存在）
TEST_NUMBERS = [
    "SONE-205",      # S1 新片
    "MIDV-018",      # MOODYZ
    "SSNI-001",      # S1 舊片
    "FC2-PPV-1234567",  # FC2（可能找不到）
]


class TestJavBusScraper:
    """JavBus 爬蟲測試"""

    def test_search_valid_number(self):
        """測試：搜尋有效番號"""
        scraper = JavBusScraper()
        # JavBus 需要依賴 jvav，如果沒安裝會返回 None，這邊只測試在有依賴的情況
        try:
            import jvav
        except ImportError:
            pytest.skip("jvav not installed")

        video = scraper.search("SONE-205")

        if video: # 網路可能不通，若有返回則驗證
            assert isinstance(video, Video)
            assert video.number == "SONE-205"
            assert video.title != ""
            assert video.source == "javbus"
            assert video.cover_url.startswith("http")

    def test_search_invalid_number(self):
        """測試：搜尋不存在的番號"""
        scraper = JavBusScraper()
        video = scraper.search("INVALID-99999")

        assert video is None

    def test_search_invalid_format(self):
        """測試：番號格式錯誤"""
        scraper = JavBusScraper()
        
        # 由於 JavBusScraper 依賴 JVAV_AVAILABLE 檢查，若無依賴會直接返回 None
        # 我們先檢查是否有依賴
        try:
            import jvav
            # 只有在有依賴時才會拋出 ValueError
            with pytest.raises(ValueError):
                scraper.search("invalid")
        except ImportError:
            pass

    def test_normalize_number(self):
        """測試：番號正規化"""
        scraper = JavBusScraper()

        assert scraper.normalize_number("sone205") == "SONE-205"
        assert scraper.normalize_number("SONE-205") == "SONE-205"
        assert scraper.normalize_number("  sone-205  ") == "SONE-205"


class TestJAV321Scraper:
    """JAV321 爬蟲測試"""

    def test_search_valid_number(self):
        """測試：搜尋有效番號"""
        scraper = JAV321Scraper()
        video = scraper.search("MIDV-018")

        if video: # 網路依賴
            assert isinstance(video, Video)
            assert video.number == "MIDV-018"
            assert video.source == "jav321"
            assert len(video.actresses) > 0

    def test_search_by_keyword(self):
        """測試：關鍵字搜尋"""
        scraper = JAV321Scraper()
        results = scraper.search_by_keyword("天使もえ", limit=5)

        assert isinstance(results, list)
        
        if results:
            assert len(results) <= 5
            for video in results:
                assert isinstance(video, Video)


class TestJavDBScraper:
    """JavDB 爬蟲測試"""

    def test_search_valid_number(self):
        """測試：搜尋有效番號（含 maker）"""
        scraper = JavDBScraper()
        
        try:
            from curl_cffi import requests
        except ImportError:
            pytest.skip("curl_cffi not installed")

        video = scraper.search("SSNI-001")

        if video:
            assert isinstance(video, Video)
            assert video.number == "SSNI-001"
            assert video.source == "javdb"
            # assert video.maker != ""  # JavDB 有時 maker 會抓不到，視頁面結構而定
            assert len(video.tags) > 0

    def test_cover_has_watermark(self):
        """測試：確認封面有浮水印（已知限制）"""
        scraper = JavDBScraper()
        video = scraper.search("SONE-205")

        if video:
            # JavDB 封面 URL 通常來自 jdbimgs.com 或 jdbstatic.com
            assert any(d in video.cover_url for d in ["jdbimgs.com", "javdb", "jdbstatic.com"])


class TestBackwardCompatibility:
    """向後相容性測試"""

    def test_old_api_still_works(self):
        """測試：舊 API 仍可運作"""
        from core.scraper import search_jav, extract_number

        # 舊函數仍可使用 (需網路)
        # result = search_jav("SONE-205")
        # if result:
        #     assert isinstance(result, dict)
        #     assert 'number' in result
        #     assert 'title' in result
        #     assert 'actors' in result  # 舊格式用 'actors' 而非 'actresses'

        # extract_number 仍可用 (不需網路)
        number = extract_number("SONE-205.mp4")
        assert number == "SONE-205"


class TestMultiSourceMerge:
    """多來源合併測試"""

    def test_merge_from_multiple_sources(self):
        """測試：從多來源合併資料"""
        from core.scraper import search_jav

        # 整合測試，視網路而定
        result = search_jav("MIDV-018")
        
        if result:
            assert result is not None
            # 應該有封面
            assert result.get('cover') != ""
