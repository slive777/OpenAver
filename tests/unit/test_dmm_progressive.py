"""
TestDMMProgressiveFacade — DMM progressive SSE facade 測試
（搬自 tests/integration/test_new_scrapers.py TestDMMProgressiveFacade）

3 non-duplicate tests（排除與 TestPipeline 重複的 2 個）
"""
import pytest
from unittest.mock import patch, MagicMock

from core.scrapers.d2pass import D2PassScraper
from core.scrapers.heyzo import HEYZOScraper
from core.scrapers.dmm import DMMScraper
from core.scrapers.javbus import JavBusScraper
from core.scrapers.models import Video
from core.scraper import smart_search


# ============================================================
# Helper
# ============================================================

def _make_video(source: str, number: str = "TEST-001") -> Video:
    return Video(
        number=number,
        title="Test Title",
        actresses=[],
        date="2024-01-01",
        maker="Test Maker",
        cover_url="",
        tags=[],
        source=source,
        detail_url="https://example.com",
    )


# ============================================================
# Tests
# ============================================================

@pytest.fixture(autouse=True)
def _dmm_capsule(monkeypatch):
    """DMM 開關看膠囊（BE-TEST-01 使用端 patch）：本檔案例都預期 DMM 被呼叫。"""
    monkeypatch.setattr("core.scraper.is_source_enabled", lambda sid: True)


class TestDMMProgressiveFacade:
    """DMM progressive SSE facade tests"""

    def test_dmm_progressive_fires_callback_per_item(self):
        """DMM progressive: result_callback fires per item via as_completed"""
        from core.scraper import search_actress

        mock_video = _make_video("dmm", "SONE-205")
        mock_pairs = [("sone00205", mock_video), ("sone00300", mock_video)]
        callbacks = []

        def mock_result_callback(slot, data):
            callbacks.append((slot, data))

        with patch('core.scraper.get_all_source_ids_ordered', return_value=['dmm', 'javbus', 'jav321', 'javdb']), \
             patch.object(DMMScraper, 'search_by_keyword_with_ids', return_value=mock_pairs), \
             patch.object(DMMScraper, '_fetch_by_id', return_value=mock_video), \
             patch('core.scrapers.dmm.rate_limit'):
            results = search_actress(
                "三上悠亜",
                result_callback=mock_result_callback,
            )

        # Should have seed (-1) + 2 items
        seed_calls = [c for c in callbacks if c[0] == -1]
        item_calls = [c for c in callbacks if c[0] >= 0]
        assert len(seed_calls) == 1
        assert len(item_calls) == 2

    def test_dmm_progressive_results_order_matches_seed(self):
        """DMM progressive: 最終回傳順序必須與 seed slot 一致，不受 as_completed 亂序影響"""
        from core.scraper import search_actress

        video1 = _make_video("dmm", "SONE-205")
        video2 = _make_video("dmm", "SONE-300")
        mock_pairs = [("sone00205", video1), ("sone00300", video2)]

        # _fetch_by_id returns enriched videos in predictable order
        enriched1 = Video(number="SONE-205", title="Title 1", source="dmm")
        enriched2 = Video(number="SONE-300", title="Title 2", source="dmm")

        with patch('core.scraper.get_all_source_ids_ordered', return_value=['dmm', 'javbus', 'jav321', 'javdb']), \
             patch.object(DMMScraper, 'search_by_keyword_with_ids', return_value=mock_pairs), \
             patch.object(DMMScraper, '_fetch_by_id', side_effect=[enriched1, enriched2]), \
             patch('core.scrapers.dmm.rate_limit'):
            results = search_actress(
                "三上悠亜",
            )

        # Results order must match seed order (SONE-205 first, SONE-300 second)
        assert results[0]['number'] == "SONE-205"
        assert results[1]['number'] == "SONE-300"

    def test_uncensored_mode_fast_path_heyzo(self):
        """uncensored_mode=True + HEYZO 前綴 → D2PassScraper 不被呼叫"""
        mock_video = _make_video("heyzo", "HEYZO-0783")

        from core.scrapers.fc2_official import FC2OfficialScraper
        from core.scrapers.avsox import AVSOXScraper

        with patch.object(D2PassScraper, 'search', return_value=None) as mock_d2:
            with patch.object(HEYZOScraper, 'search', return_value=mock_video) as mock_heyzo:
                with patch.object(FC2OfficialScraper, 'search', return_value=None):
                    with patch.object(AVSOXScraper, 'search', return_value=None):
                        with patch('core.scrapers.dmm.rate_limit'):
                            results = smart_search("HEYZO-0783", uncensored_mode=True)

        assert len(results) == 1
        mock_d2.assert_not_called()
