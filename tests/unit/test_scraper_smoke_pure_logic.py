"""
test_scraper_smoke_pure_logic.py — 桶 D 純邏輯守衛（TASK-73e-T1）

搬自 tests/smoke/test_scrapers.py 的純離線測試（從不連網）。
不加 pytestmark = pytest.mark.smoke，CI 正常收錄。
"""
import pytest
from unittest.mock import MagicMock, patch

from core.scrapers import (
    JavBusScraper, JAV321Scraper, JavDBScraper,
    FC2JavtenScraper, FC2OfficialScraper, AVSOXScraper,
    Video, Actress,
)


# ============================================================
# FC2 番號正規化（5-case 版，保留純數字 case，源自 test_scrapers.py:144–150）
# ============================================================

class TestFC2NormalizePureLogic:
    """FC2 番號正規化——純字串邏輯，零連網"""

    @pytest.fixture
    def scraper(self):
        return FC2JavtenScraper()

    def test_normalize_fc2_number(self, scraper):
        """測試：FC2 番號正規化（5 case 含純數字輸入）"""
        assert scraper._normalize_fc2_number("FC2-PPV-1723984") == "1723984"
        assert scraper._normalize_fc2_number("FC2PPV1723984") == "1723984"
        assert scraper._normalize_fc2_number("FC2-1723984") == "1723984"
        assert scraper._normalize_fc2_number("fc2ppv-1723984") == "1723984"
        assert scraper._normalize_fc2_number("1723984") == "1723984"


class TestFC2OfficialNormalizePureLogic:
    """FC2OfficialScraper 番號正規化——與 javten 版等價（CD-118b-2）"""

    @pytest.fixture
    def scraper(self):
        return FC2OfficialScraper()

    def test_normalize_fc2_number(self, scraper):
        """測試：官方站版 FC2 番號正規化（5 case 含純數字輸入）"""
        assert scraper._normalize_fc2_number("FC2-PPV-1723984") == "1723984"
        assert scraper._normalize_fc2_number("FC2PPV1723984") == "1723984"
        assert scraper._normalize_fc2_number("FC2-1723984") == "1723984"
        assert scraper._normalize_fc2_number("fc2ppv-1723984") == "1723984"
        assert scraper._normalize_fc2_number("1723984") == "1723984"


# ============================================================
# FC2 負向合約——搬離線（TASK-73e-T1，CD-73e-7）
# mock navigate_and_settle 回 /search?kw= → search() 短路回 None
# 禁止 stub search 本身
# ============================================================

class TestFC2SearchMissReturnsNone:
    """FC2 不存在番號搜尋→ None（patch HTTP 層，不 stub search 本身）"""

    @pytest.fixture
    def scraper(self):
        with patch("core.scrapers.fc2_javten.rate_limit"):
            yield FC2JavtenScraper()

    def test_search_invalid_number_returns_none(self, scraper):
        """FC2-PPV-9999999999 不存在→ 最終 URL 仍是 /search?kw= → search() 回 None"""
        transport = MagicMock()
        transport.navigate_and_settle.return_value = (
            "https://javten.com/search?kw=9999999999"
        )
        with patch("core.scrapers.fc2_javten.get_cf_transport", return_value=transport):
            result = scraper.search("FC2-PPV-9999999999")
        assert result is None


# ============================================================
# JavBus 番號正規化（源自 test_scrapers.py:92–96）
# ============================================================

class TestJavBusNormalizePureLogic:
    """JavBus 番號正規化——純字串邏輯，零連網"""

    @pytest.fixture
    def scraper(self):
        return JavBusScraper()

    def test_normalize_number(self, scraper):
        """測試：番號正規化（3 種輸入格式）"""
        assert scraper.normalize_number("sone205") == "SONE-205"
        assert scraper.normalize_number("SONE-205") == "SONE-205"
        assert scraper.normalize_number("  sone-205  ") == "SONE-205"


# ============================================================
# 向後相容性——舊 API（源自 test_scrapers.py:196–205）
# 只搬 extract_number() 斷言（不連網段落）
# ============================================================

class TestBackwardCompatibility:
    """向後相容性——舊 API 離線段落"""

    def test_old_api_still_works(self):
        """測試：extract_number() 從檔名解析番號（不連網）"""
        from core.scraper import extract_number

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


# ============================================================
# 多來源整合——介面與唯一性（源自 test_scrapers.py:231–266）
# ============================================================

class TestMultiSourceIntegration:
    """多來源整合——純 reflection，不連網"""

    def test_all_scrapers_have_same_interface(self):
        """測試：所有爬蟲實作相同介面"""
        scrapers = [
            JavBusScraper(),
            JAV321Scraper(),
            JavDBScraper(),
            FC2JavtenScraper(),
            FC2OfficialScraper(),
            AVSOXScraper(),
        ]

        for scraper in scrapers:
            assert hasattr(scraper, 'search')
            assert hasattr(scraper, 'search_by_keyword')
            assert hasattr(scraper, 'normalize_number')
            assert hasattr(scraper, 'source_name')

            assert isinstance(scraper.source_name, str)
            assert len(scraper.source_name.strip()) > 0

    def test_scraper_source_names_unique(self):
        """測試：各爬蟲來源名稱唯一"""
        scrapers = [
            JavBusScraper(),
            JAV321Scraper(),
            JavDBScraper(),
            FC2OfficialScraper(),
            FC2JavtenScraper(),
            AVSOXScraper(),
        ]

        source_names = [s.source_name for s in scrapers]
        assert len(source_names) == len(set(source_names)), "來源名稱應唯一"

        expected_names = {"javbus", "jav321", "javdb", "fc2", "fc-javten", "avsox"}
        assert set(source_names) == expected_names
