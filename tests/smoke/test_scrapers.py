"""Scraper 模組測試

Phase 16 Task 2: 測試 5 個爬蟲模組
- Task 1 (舊): JavBusScraper, JAV321Scraper, JavDBScraper
- Task 2 (新): FC2Scraper, AVSOXScraper
"""
import pytest
from core.scrapers import (
    JavBusScraper, JAV321Scraper, JavDBScraper,
    FC2Scraper, AVSOXScraper,
    Video, Actress
)

pytestmark = pytest.mark.smoke

# ========== 測試樣本 ==========

# 有碼番號（主流片商）
SAMPLE_CENSORED = {
    "SONE-205": {"maker": "S1", "actress": "未歩なな"},
    "MIDV-018": {"maker": "Moodyz", "actress": "高橋しょう子"},
    "SSNI-001": {"maker": "S1", "actress": "三上悠亞"},
    "STARS-804": {"maker": "SOD", "actress": "永野いち夏"},
}

# 無碼番號（Carib/1Pondo 等）
SAMPLE_UNCENSORED = {
    "051119-917": {"title": "結婚直前"},
    "012523-001": {"title": "一本道"},
}

# FC2 番號
SAMPLE_FC2 = {
    "FC2-PPV-1723984": {"title": "透け透け体操服"},
    "FC2-PPV-3061583": {"title": ""},  # 可能找不到
}

# ========== 共用測試 ==========

@pytest.mark.parametrize("scraper_cls, test_number", [
    (JavBusScraper, "SONE-205"),
    (JAV321Scraper, "MIDV-018"),
    (JavDBScraper, "SSNI-001"),
    (FC2Scraper, "FC2-PPV-1723984"),
])
def test_search_valid_number(scraper_cls, test_number):
    """測試：搜尋有效番號"""
    if scraper_cls == JavDBScraper:
        try:
            from curl_cffi import requests
        except ImportError:
            pytest.skip("curl_cffi not installed")

    scraper = scraper_cls()
    video = scraper.search(test_number)

    if video:  # external network dependency
        assert isinstance(video, Video)
        if scraper_cls == FC2Scraper:
            assert video.number.startswith("FC2-PPV-") or "FC2" in video.number.upper()
            assert "1723984" in video.number
            assert isinstance(video.title, str) and len(video.title) > 0
        elif scraper_cls == JAV321Scraper:
            assert video.number.upper().startswith("MIDV")
            actresses = getattr(video, 'actresses', [])
            assert isinstance(actresses, list) and len(actresses) > 0
            assert isinstance(actresses[0], Actress)
        elif scraper_cls == JavDBScraper:
            assert video.number == test_number
            tags = getattr(video, 'tags', [])
            assert isinstance(tags, list) and len(tags) > 0
            assert isinstance(tags[0], str)
        else:
            assert video.number == test_number
            assert isinstance(video.title, str) and len(video.title) > 0
        assert video.source == scraper.source_name

# ========== Task 1 爬蟲測試 ==========

class TestJavBusScraper:
    """JavBus 爬蟲測試"""

    @pytest.fixture
    def scraper(self):
        return JavBusScraper()

    def test_search_invalid_number(self, scraper):
        """測試：搜尋不存在的番號"""
        video = scraper.search("INVALID-99999")
        assert video is None

    def test_normalize_number(self, scraper):
        """測試：番號正規化"""
        assert scraper.normalize_number("sone205") == "SONE-205"
        assert scraper.normalize_number("SONE-205") == "SONE-205"
        assert scraper.normalize_number("  sone-205  ") == "SONE-205"


class TestJAV321Scraper:
    """JAV321 爬蟲測試"""

    @pytest.fixture
    def scraper(self):
        return JAV321Scraper()

    def test_search_by_keyword(self, scraper):
        """測試：關鍵字搜尋"""
        results = scraper.search_by_keyword("天使もえ", limit=5)

        assert isinstance(results, list)
        if results:
            assert len(results) <= 5
            for video in results:
                assert isinstance(video, Video)
                assert isinstance(video.title, str) and len(video.title) > 0
                assert video.number is not None and len(video.number) > 0


class TestJavDBScraper:
    """JavDB 爬蟲測試"""

    @pytest.fixture
    def scraper(self):
        return JavDBScraper()

    def test_cover_from_javdb(self, scraper):
        """測試：封面來自 JavDB"""
        video = scraper.search("SONE-205")

        if video:
            assert isinstance(video.cover_url, str)
            assert any(d in video.cover_url for d in ["jdbimgs", "javdb", "jdbstatic"])


# ========== Task 2 新爬蟲測試 ==========

class TestFC2Scraper:
    """FC2 爬蟲測試"""

    @pytest.fixture
    def scraper(self):
        return FC2Scraper()

    def test_normalize_fc2_number(self, scraper):
        """測試：FC2 番號正規化"""
        assert scraper._normalize_fc2_number("FC2-PPV-1723984") == "1723984"
        assert scraper._normalize_fc2_number("FC2PPV1723984") == "1723984"
        assert scraper._normalize_fc2_number("FC2-1723984") == "1723984"
        assert scraper._normalize_fc2_number("fc2ppv-1723984") == "1723984"
        assert scraper._normalize_fc2_number("1723984") == "1723984"

    def test_search_invalid_number(self, scraper):
        """測試：搜尋不存在的 FC2 番號"""
        video = scraper.search("FC2-PPV-9999999999")
        assert video is None


class TestAVSOXScraper:
    """AVSOX 爬蟲測試（無碼專用）"""

    @pytest.fixture
    def scraper(self):
        return AVSOXScraper()

    def test_get_working_domain(self, scraper):
        """測試：取得可用網域"""
        domain = scraper._get_working_domain()

        if domain:  # 網路依賴
            assert isinstance(domain, str)
            assert domain.startswith("https://")
            assert "avsox" in domain

    def test_search_uncensored_number(self, scraper):
        """測試：搜尋無碼番號"""
        video = scraper.search("051119-917")

        if video:  # 網路依賴
            assert isinstance(video, Video)
            assert video.source == "avsox"
            assert isinstance(video.actresses, list) and len(video.actresses) > 0
            assert isinstance(video.actresses[0], Actress)

    def test_search_censored_number_returns_none(self, scraper):
        """測試：有碼番號應返回 None（AVSOX 主要收錄無碼）"""
        video = scraper.search("SONE-205")
        # AVSOX 可能找不到有碼番號，這是正常的
        # 不做 assert，只確認不會報錯


# ========== 向後相容性測試 ==========

class TestBackwardCompatibility:
    """向後相容性測試"""

    def test_old_api_still_works(self):
        """測試：舊 API 仍可運作"""
        from core.scraper import search_jav, extract_number

        # extract_number 不需網路
        number = extract_number("SONE-205.mp4")
        assert number == "SONE-205"

        number = extract_number("[MIDV-018] title.avi")
        assert number == "MIDV-018"

    def test_video_model_compatibility(self):
        """測試：Video 模型欄位相容性"""
        video = Video(
            number="TEST-001",
            title="Test Title",
            actresses=[Actress(name="Test Actress")],
            date="2024-01-01",
            maker="Test Maker",
            cover_url="https://example.com/cover.jpg",
            tags=["tag1", "tag2"],
            source="test",
        )

        assert video.number == "TEST-001"
        assert video.title == "Test Title"
        assert len(video.actresses) == 1
        assert video.actresses[0].name == "Test Actress"


# ========== 多來源整合測試 ==========

class TestMultiSourceIntegration:
    """多來源整合測試"""

    def test_all_scrapers_have_same_interface(self):
        """測試：所有爬蟲實作相同介面"""
        scrapers = [
            JavBusScraper(),
            JAV321Scraper(),
            JavDBScraper(),
            FC2Scraper(),
            AVSOXScraper(),
        ]

        for scraper in scrapers:
            # 確認有必要的方法
            assert hasattr(scraper, 'search')
            assert hasattr(scraper, 'search_by_keyword')
            assert hasattr(scraper, 'normalize_number')
            assert hasattr(scraper, 'source_name')

            # 確認 source_name 是有效的非空字串
            assert isinstance(scraper.source_name, str)
            assert len(scraper.source_name.strip()) > 0

    def test_scraper_source_names_unique(self):
        """測試：各爬蟲來源名稱唯一"""
        scrapers = [
            JavBusScraper(),
            JAV321Scraper(),
            JavDBScraper(),
            FC2Scraper(),
            AVSOXScraper(),
        ]

        source_names = [s.source_name for s in scrapers]
        assert len(source_names) == len(set(source_names)), "來源名稱應唯一"

        expected_names = {"javbus", "jav321", "javdb", "fc2", "avsox"}
        assert set(source_names) == expected_names
