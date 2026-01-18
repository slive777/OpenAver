"""
test_scraper_live.py - 爬蟲連通 Smoke Tests

Phase 16 Task 2: 測試 6 個爬蟲的網路連通性

執行方式：
    pytest tests/smoke/test_scraper_live.py -v -m smoke

注意：
- 只用於本地手動測試，不進 CI（避免被 ban）
- 無法連線時自動 skip，不算失敗
- DMM 需要日本 VPN
"""

import pytest
from core.scraper import search_jav


# ========== 舊 API 連通測試 ==========

@pytest.mark.smoke
class TestOldAPIConnectivity:
    """舊 API 連通測試（search_jav）"""

    def test_javbus_connectivity(self):
        """JavBus 連通性測試"""
        result = search_jav("SONE-103", source="javbus")
        if result is None:
            pytest.skip("JavBus 無法連線或無結果")

        assert result.get('number') == 'SONE-103', f"番號不符: {result.get('number')}"
        assert result.get('title'), "標題為空"

    def test_jav321_connectivity(self):
        """Jav321 連通性測試"""
        result = search_jav("SONE-103", source="jav321")
        if result is None:
            pytest.skip("Jav321 無法連線或無結果")

        assert result.get('number') == 'SONE-103', f"番號不符: {result.get('number')}"
        assert result.get('title'), "標題為空"

    def test_javdb_connectivity(self):
        """JavDB 連通性測試"""
        result = search_jav("SONE-103", source="javdb")
        if result is None:
            pytest.skip("JavDB 無法連線或無結果")

        assert result.get('number') == 'SONE-103', f"番號不符: {result.get('number')}"
        assert result.get('title'), "標題為空"

    def test_auto_source_connectivity(self):
        """自動來源連通性測試（至少一個來源可用）"""
        result = search_jav("MIDV-139", source="auto")
        if result is None:
            pytest.skip("所有來源無法連線")

        assert result.get('number'), "無番號返回"


# ========== 新爬蟲模組連通測試 ==========

@pytest.mark.smoke
class TestNewScraperConnectivity:
    """新爬蟲模組連通測試（Phase 16 Task 2）"""

    def test_javbus_scraper(self):
        """JavBusScraper 連通性"""
        from core.scrapers import JavBusScraper

        scraper = JavBusScraper()
        video = scraper.search("SONE-205")

        if video is None:
            pytest.skip("JavBusScraper 無法連線")

        assert video.number == "SONE-205"
        assert video.source == "javbus"
        assert video.cover_url.startswith("http")

    def test_jav321_scraper(self):
        """JAV321Scraper 連通性"""
        from core.scrapers import JAV321Scraper

        scraper = JAV321Scraper()
        video = scraper.search("MIDV-018")

        if video is None:
            pytest.skip("JAV321Scraper 無法連線")

        assert "MIDV" in video.number.upper()
        assert video.source == "jav321"

    def test_javdb_scraper(self):
        """JavDBScraper 連通性"""
        from core.scrapers import JavDBScraper

        try:
            from curl_cffi import requests
        except ImportError:
            pytest.skip("curl_cffi not installed")

        scraper = JavDBScraper()
        video = scraper.search("SSNI-001")

        if video is None:
            pytest.skip("JavDBScraper 無法連線")

        assert video.number == "SSNI-001"
        assert video.source == "javdb"

    def test_fc2_scraper(self):
        """FC2Scraper 連通性"""
        from core.scrapers import FC2Scraper

        scraper = FC2Scraper()
        video = scraper.search("FC2-PPV-1723984")

        if video is None:
            pytest.skip("FC2Scraper 無法連線")

        assert "FC2" in video.number
        assert video.source == "fc2"
        assert video.title != ""

    def test_avsox_scraper(self):
        """AVSOXScraper 連通性（無碼專用）"""
        from core.scrapers import AVSOXScraper

        scraper = AVSOXScraper()
        video = scraper.search("051119-917")

        if video is None:
            pytest.skip("AVSOXScraper 無法連線")

        assert video.source == "avsox"
        assert len(video.actresses) > 0

    @pytest.mark.skip(reason="需要日本 VPN - 開啟 Surfshark 日本節點後移除此標記")
    def test_dmm_scraper(self):
        """
        DMMScraper 連通性

        ⚠️ 此測試需要日本 VPN：
        1. 開啟 VPN 並連接日本節點
        2. 移除 @pytest.mark.skip 裝飾器
        3. 執行測試
        """
        from core.scrapers import DMMScraper

        scraper = DMMScraper()
        video = scraper.search("SONE-205")

        if video is None:
            pytest.fail("DMMScraper 無法連線 - 請確認 VPN 已連接日本節點")

        assert video.source == "dmm"
        assert video.cover_url != ""


# ========== 女優搜尋測試 ==========

@pytest.mark.smoke
class TestActressSearch:
    """女優搜尋連通測試"""

    def test_actress_search_connectivity(self):
        """女優搜尋連通性"""
        from core.scraper import search_actress

        results = search_actress("三上悠亞", limit=5)
        if not results:
            pytest.skip("女優搜尋無法連線或無結果")

        assert len(results) >= 1, "至少應返回 1 個結果"
        assert results[0].get('number'), "結果應包含番號"


# ========== 特殊番號測試 ==========

@pytest.mark.smoke
class TestSpecialNumbers:
    """特殊番號格式測試"""

    def test_fc2_number_formats(self):
        """FC2 各種格式測試"""
        from core.scrapers import FC2Scraper

        scraper = FC2Scraper()

        # 測試不同格式都能正規化
        formats = [
            "FC2-PPV-1723984",
            "FC2PPV-1723984",
            "FC2-1723984",
            "fc2ppv1723984",
        ]

        for fmt in formats:
            normalized = scraper._normalize_fc2_number(fmt)
            assert normalized == "1723984", f"{fmt} 正規化失敗: {normalized}"

    def test_uncensored_smart_search(self):
        """無碼番號 smart_search 觸發測試"""
        from core.scraper import smart_search

        test_cases = [
            ("FC2-PPV-2200414", "fc2"),
            ("FC2-PPV-2781063", "fc2"),
            ("FC2-PPV-2865434", "fc2"),
            ("010120-001", "1pondo"),
            ("031515-828", "carib"),
        ]

        for number, desc in test_cases:
            results = smart_search(number, limit=1)
            if results:
                assert results[0].get('_mode') == 'uncensored', \
                    f"{number} ({desc}) 應為 uncensored 模式，實際: {results[0].get('_mode')}"
            else:
                pytest.skip(f"{number} ({desc}) 無法搜尋到結果")

    def test_stars_prefix_conversion(self):
        """STARS 前綴轉換（DMM 特殊格式）"""
        from core.scrapers import DMMScraper

        scraper = DMMScraper()

        # STARS 系列在 DMM 需要加 "1" 前綴
        cid = scraper._convert_with_hints("STARS-804")
        assert cid == "1stars00804"

        # SONE 系列無前綴
        cid = scraper._convert_with_hints("SONE-205")
        assert cid == "sone00205"
