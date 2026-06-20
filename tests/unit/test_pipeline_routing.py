"""
TestPipeline + TestUnknownSource — Pipeline routing 測試
（搬自 tests/integration/test_new_scrapers.py TestPipeline + TestUnknownSource）

mock scraper.search，驗證路由邏輯（不含 TestClient 測試）
"""
import pytest
from unittest.mock import patch, MagicMock

from core.scrapers.d2pass import D2PassScraper
from core.scrapers.heyzo import HEYZOScraper
from core.scrapers.dmm import DMMScraper
from core.scrapers.javbus import JavBusScraper
from core.scrapers.models import Video
from core.scrapers.utils import SOURCE_ORDER
from core.scraper import search_jav, smart_search


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch):
    """跳過 rate_limit / REQUEST_DELAY sleep，加速測試"""
    monkeypatch.setattr("core.scrapers.dmm.rate_limit", lambda *a, **kw: None)
    monkeypatch.setattr("core.scraper.time.sleep", lambda *a: None)


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
# TestPipeline — smart_search routing 測試
# ============================================================

class TestPipeline:
    """Pipeline routing 測試（mock scraper.search，驗證路由邏輯）"""

    @pytest.fixture(autouse=True)
    def _all_sources_enabled(self, monkeypatch):
        """隔離 ambient web/config.json 的啟用來源集合。

        TASK-61a-3 起 search_jav(source='auto') 改讀 get_enabled_source_ids()
        →（讀 live web/config.json）決定 fan-out 來源。本檔的 merge-priority
        測試假設 8 個 builtin 來源（含 dmm/javbus）全部啟用；若開發者把有碼來源
        停用（例如開無碼模式），dmm/javbus 會被排除 → search_jav 回 None →
        assertion 觸發 TypeError，測試變得 config-coupled 且不確定。

        此 fixture 把 search_jav 實際呼叫的 core.scraper.get_enabled_source_ids
        monkeypatch 成回傳全部 8 個 builtin id（canonical 順序），讓 merge
        測試只驗證 MERGER 在所有來源可用時的行為，與環境 config 無關。
        """
        monkeypatch.setattr(
            "core.scraper.get_enabled_source_ids",
            lambda availability_map=None: list(SOURCE_ORDER),
        )

    def test_uncensored_detection_d2pass(self):
        """日期_底線格式番號 → 自動走無碼路徑 → D2PassScraper 被呼叫"""
        mock_video = _make_video("d2pass", "120415_201")

        with patch.object(D2PassScraper, 'search', return_value=mock_video) as mock_d2:
            with patch('core.scrapers.dmm.rate_limit'):
                results = smart_search("120415_201")

        assert len(results) == 1
        assert results[0]['_mode'] == 'uncensored'
        mock_d2.assert_called()

    def test_uncensored_detection_heyzo(self):
        """HEYZO- 前綴番號 → 自動走無碼路徑 → HEYZOScraper 被呼叫"""
        mock_video = _make_video("heyzo", "HEYZO-0783")

        with patch.object(D2PassScraper, 'search', return_value=None):
            with patch.object(HEYZOScraper, 'search', return_value=mock_video) as mock_heyzo:
                with patch('core.scrapers.dmm.rate_limit'):
                    results = smart_search("HEYZO-0783")

        assert len(results) == 1
        assert results[0]['_mode'] == 'uncensored'
        mock_heyzo.assert_called()

    def test_uncensored_mode_uses_new_sources(self):
        """uncensored_mode=True → D2PassScraper 和 HEYZOScraper 都被嘗試"""
        with patch.object(D2PassScraper, 'search', return_value=None) as mock_d2:
            with patch.object(HEYZOScraper, 'search', return_value=None) as mock_heyzo:
                with patch.object(DMMScraper, 'search', return_value=None):
                    with patch('core.scrapers.dmm.rate_limit'):
                        # FC2 / AVSOX 也需要 mock 避免真實網路請求
                        from core.scrapers.fc2 import FC2Scraper
                        from core.scrapers.avsox import AVSOXScraper
                        with patch.object(FC2Scraper, 'search', return_value=None):
                            with patch.object(AVSOXScraper, 'search', return_value=None):
                                smart_search("SONE-205", uncensored_mode=True)

        mock_d2.assert_called()
        mock_heyzo.assert_called()

    def test_dmm_top1_when_proxy(self):
        """DMM first in Active Row order + proxy_url → exact path goes fan-out, DMM wins merge.

        DMM Top-1 shortcut removed in feature/65; exact path runs Rule 4b (JavBus
        variant probe) first, then falls through to search_jav(auto) fan-out + merge.
        DMM排第一 + 有 proxy → search_jav(auto) fan-out → merge winner _source == 'dmm'.
        """
        from core.scrapers.jav321 import JAV321Scraper
        from core.scrapers.javdb import JavDBScraper
        from core.scrapers.fc2 import FC2Scraper
        from core.scrapers.avsox import AVSOXScraper
        dmm_video = _make_video("dmm", "SONE-205")

        # Class autouse fixture already sets get_enabled_source_ids → SOURCE_ORDER (dmm first).
        with patch.object(DMMScraper, 'search', return_value=dmm_video), \
             patch.object(JavBusScraper, 'search', return_value=None), \
             patch.object(JAV321Scraper, 'search', return_value=None), \
             patch.object(JavDBScraper, 'search', return_value=None), \
             patch.object(FC2Scraper, 'search', return_value=None), \
             patch.object(AVSOXScraper, 'search', return_value=None), \
             patch('core.scrapers.dmm.rate_limit'), \
             patch('core.scraper.get_all_variant_ids', return_value=[]):
            results = smart_search("SONE-205", proxy_url="http://proxy:8080")

        assert len(results) >= 1
        assert results[0]['_mode'] == 'exact'
        assert results[0]['_source'] == 'dmm'

    def test_uncensored_mode_fast_path_fc2(self):
        """uncensored_mode=True + FC2 前綴 → D2PassScraper 不被呼叫"""
        mock_video = _make_video("fc2", "FC2-PPV-1234567")

        from core.scrapers.fc2 import FC2Scraper
        from core.scrapers.avsox import AVSOXScraper

        with patch.object(D2PassScraper, 'search', return_value=None) as mock_d2:
            with patch.object(HEYZOScraper, 'search', return_value=None):
                with patch.object(FC2Scraper, 'search', return_value=mock_video):
                    with patch.object(AVSOXScraper, 'search', return_value=None):
                        with patch('core.scrapers.dmm.rate_limit'):
                            results = smart_search("FC2-PPV-1234567", uncensored_mode=True)

        assert len(results) == 1
        mock_d2.assert_not_called()

    def test_exact_path_always_fan_out(self):
        """精確番號路徑一律走 fan-out，不論 proxy 是否為空。

        DMM Top-1 shortcut removed in feature/65; exact path runs Rule 4b (JavBus
        variant probe) first, then falls through to search_jav(auto) fan-out + merge.
        proxy_url='' → search_jav(auto) fan-out still called,
        DMM simply returns no data (dmm_config=None when proxy empty), merge winner = other source.
        """
        mock_video = _make_video("javbus", "SONE-205")
        with patch('core.scraper.search_jav', return_value=mock_video.to_legacy_dict()) as mock_sj:
            with patch('core.scraper.get_all_variant_ids', return_value=[]):
                with patch.object(JavBusScraper, 'search', return_value=None):
                    results = smart_search("SONE-205", proxy_url="")
        # Exact path always calls search_jav(auto) fan-out regardless of proxy
        mock_sj.assert_called()

    def test_javbus_fastpath_hit(self):
        """乾淨番號 + JavBusScraper.search 回傳非 None Video → fast-path 命中。

        - get_all_variant_ids 未被呼叫
        - 回傳 1 筆結果
        - _source == 'javbus', _mode == 'exact'
        - _all_variant_ids == [normalize_number('SONE-205')]
        - _summary 和 _rating 存在且值來自 mock video
        """
        from core.scraper import normalize_number

        def _make_video_with_summary(source, number, summary="Test summary", rating=8.5):
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
                summary=summary,
                rating=rating,
            )

        mock_video = _make_video_with_summary("javbus", "SONE-205", summary="My summary", rating=9.0)

        with patch.object(JavBusScraper, 'search', return_value=mock_video) as mock_search, \
             patch('core.scraper.get_all_variant_ids') as mock_gavi:
            results = smart_search("SONE-205")

        # fast-path hit → get_all_variant_ids must NOT be called
        mock_gavi.assert_not_called()
        assert len(results) == 1
        r = results[0]
        assert r['_source'] == 'javbus'
        assert r['_mode'] == 'exact'
        assert r['_all_variant_ids'] == [normalize_number('SONE-205')]
        assert r['_summary'] == "My summary"
        assert r['_rating'] == 9.0

    def test_javbus_fastpath_miss_fallback(self):
        """JavBusScraper.search 回傳 None → fallback 到 get_all_variant_ids"""
        with patch.object(JavBusScraper, 'search', return_value=None), \
             patch('core.scraper.get_all_variant_ids', return_value=[]) as mock_gavi, \
             patch('core.scraper.search_jav', return_value=None):
            smart_search("SONE-205")

        # miss → fallback → get_all_variant_ids must be called
        mock_gavi.assert_called()

    def test_javbus_fastpath_exception_fallback(self):
        """JavBusScraper.search 拋出 Exception → 不 propagate，fallback 到 get_all_variant_ids"""
        with patch.object(JavBusScraper, 'search', side_effect=Exception('timeout')), \
             patch('core.scraper.get_all_variant_ids', return_value=[]) as mock_gavi, \
             patch('core.scraper.search_jav', return_value=None):
            # Must not raise
            smart_search("SONE-205")

        # exception caught → fallback → get_all_variant_ids must be called
        mock_gavi.assert_called()

    def test_variant_hit_has_summary_and_rating(self):
        """variant-hit 路徑（search_by_variant_id）回傳 dict 含 _summary 和 _rating。

        mock get_all_variant_ids 回 ['SONE-205']，
        mock JavBusScraper._fetch_by_id 回帶 summary/rating 的 Video，
        驗證結果 dict 含 _summary 和 _rating 且值正確。
        """
        def _make_video_with_summary(source, number, summary="Test summary", rating=8.5):
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
                summary=summary,
                rating=rating,
            )

        mock_video = _make_video_with_summary("javbus", "SONE-205", summary="Variant summary", rating=7.5)

        # fast-path misses (search returns None), then variant probe hits
        with patch.object(JavBusScraper, 'search', return_value=None), \
             patch('core.scraper.get_all_variant_ids', return_value=['SONE-205']), \
             patch.object(JavBusScraper, '_fetch_by_id', return_value=mock_video):
            results = smart_search("SONE-205")

        assert len(results) == 1
        r = results[0]
        assert '_summary' in r
        assert '_rating' in r
        assert r['_summary'] == "Variant summary"
        assert r['_rating'] == 7.5

    def test_merge_winner_first_in_order_dmm(self, monkeypatch):
        """merge text-winner = first successful source in drag-sort order (get_enabled_source_ids order).

        Class fixture sets SOURCE_ORDER (dmm first) as the enabled order.
        With dmm first in order + dmm returning data → winner _source == 'dmm'.
        This is ORDER-driven, NOT primary_source-driven (CD-61-14: primary_source
        no longer overrides merge winner; DMM Top-1 shortcut removed in feature/65;
        this test exercises search_jav(auto) merge directly, not the smart_search exact path).
        """
        from core.scrapers.jav321 import JAV321Scraper
        from core.scrapers.javdb import JavDBScraper
        from core.scrapers.fc2 import FC2Scraper
        from core.scrapers.avsox import AVSOXScraper
        dmm_video = _make_video("dmm", "SONE-205")
        javbus_video = _make_video("javbus", "SONE-205")

        # Class autouse fixture already monkeypatches get_enabled_source_ids → SOURCE_ORDER
        # (dmm is first in SOURCE_ORDER) — no override needed here.
        with patch.object(DMMScraper, 'search', return_value=dmm_video), \
             patch.object(JavBusScraper, 'search', return_value=javbus_video), \
             patch.object(JAV321Scraper, 'search', return_value=None), \
             patch.object(JavDBScraper, 'search', return_value=None), \
             patch.object(FC2Scraper, 'search', return_value=None), \
             patch.object(AVSOXScraper, 'search', return_value=None), \
             patch('core.scrapers.dmm.rate_limit'):
            result = search_jav("SONE-205", proxy_url="http://proxy:8080")

        assert result['_source'] == 'dmm'

    def test_merge_winner_first_in_order_javbus(self, monkeypatch):
        """merge text-winner = first successful source in drag-sort order.

        Override enabled order so javbus is FIRST (dmm absent / after javbus).
        With javbus first in order + javbus returning data → winner _source == 'javbus',
        even though dmm also returns data.
        This proves drag-order determines the merge winner, NOT primary_source.
        """
        from core.scrapers.jav321 import JAV321Scraper
        from core.scrapers.javdb import JavDBScraper
        from core.scrapers.fc2 import FC2Scraper
        from core.scrapers.avsox import AVSOXScraper
        dmm_video = _make_video("dmm", "SONE-205")
        javbus_video = _make_video("javbus", "SONE-205")

        # Override the class fixture: javbus first, dmm SECOND (still fanned out + returns
        # data) — proves first-in-order beats a later successful source, not just absence.
        javbus_first_order = ['javbus', 'dmm', 'jav321', 'javdb', 'fc2', 'avsox', 'heyzo']
        monkeypatch.setattr(
            "core.scraper.get_enabled_source_ids",
            lambda availability_map=None: javbus_first_order,
        )

        with patch.object(DMMScraper, 'search', return_value=dmm_video), \
             patch.object(JavBusScraper, 'search', return_value=javbus_video), \
             patch.object(JAV321Scraper, 'search', return_value=None), \
             patch.object(JavDBScraper, 'search', return_value=None), \
             patch.object(FC2Scraper, 'search', return_value=None), \
             patch.object(AVSOXScraper, 'search', return_value=None), \
             patch('core.scrapers.dmm.rate_limit'):
            result = search_jav("SONE-205", proxy_url="http://proxy:8080")

        assert result['_source'] == 'javbus'

    def test_fuzzy_chain_dmm_no_proxy_falls_through(self):
        """DMM 排第一 + 無 proxy → 跳過 DMM，fallback 到 javbus（新鏈行為）"""
        from core.scraper import search_actress
        from core.scrapers.javdb import JavDBScraper

        mock_video = _make_video("javbus", "SONE-205")

        with patch('core.scraper.get_all_source_ids_ordered', return_value=['dmm', 'javbus', 'jav321', 'javdb']), \
             patch.object(DMMScraper, 'search_by_keyword_with_ids') as mock_dmm_kw, \
             patch.object(JavBusScraper, 'get_ids_from_search', return_value=['SONE-205']), \
             patch('core.scraper.search_jav', return_value=mock_video.to_legacy_dict()), \
             patch.object(JavDBScraper, 'search_by_keyword', return_value=[]):
            results = search_actress("未歩なな", limit=1, proxy_url='')

        # DMM must NOT be called when proxy_url is empty
        mock_dmm_kw.assert_not_called()
        assert len(results) >= 1

    def test_search_actress_dmm_routing(self):
        """DMM 排第一 + proxy 有效 → DMM search_by_keyword_with_ids 先被呼叫，JavBus 不呼叫"""
        from core.scraper import search_actress

        mock_video = _make_video("dmm", "SONE-205")
        mock_pairs = [("sone00205", mock_video)]

        with patch('core.scraper.get_all_source_ids_ordered', return_value=['dmm', 'javbus', 'jav321', 'javdb']), \
             patch.object(DMMScraper, 'search_by_keyword_with_ids', return_value=mock_pairs) as mock_dmm_kw, \
             patch.object(DMMScraper, '_fetch_by_id', return_value=mock_video), \
             patch.object(JavBusScraper, 'get_ids_from_search', return_value=[]) as mock_jb, \
             patch('core.scrapers.dmm.rate_limit'):
            results = search_actress(
                "未歩なな",
                limit=10,
                proxy_url='http://test-proxy:8080',
            )

        mock_dmm_kw.assert_called_once()
        # JavBus should NOT be called since DMM returned results
        mock_jb.assert_not_called()
        assert len(results) == 1
        assert results[0]['source'] == 'dmm'

    def test_search_actress_dmm_fallback_to_javbus(self):
        """DMM 排第一 + proxy 有效 + DMM 無結果 → fallback 到 JavBus"""
        from core.scraper import search_actress
        from core.scrapers.javdb import JavDBScraper

        # DMM returns nothing → should fall through to JavBus path
        with patch('core.scraper.get_all_source_ids_ordered', return_value=['dmm', 'javbus', 'jav321', 'javdb']), \
             patch.object(DMMScraper, 'search_by_keyword_with_ids', return_value=[]) as mock_dmm_kw, \
             patch.object(JavBusScraper, 'get_ids_from_search', return_value=[]) as mock_jb, \
             patch.object(JavDBScraper, 'search_by_keyword', return_value=[]) as mock_javdb_kw:
            results = search_actress(
                "未歩なな",
                limit=10,
                proxy_url='http://test-proxy:8080',
            )

        mock_dmm_kw.assert_called_once()
        # After DMM returns nothing, JavBus path should be tried
        mock_jb.assert_called()


# ============================================================
# TestUnknownSource (2 mock-only tests)
# ============================================================

class TestUnknownSource:
    """未知 source 驗證測試 — 確保 JavGuru 等已移除來源明確失敗"""

    def test_search_jav_unknown_source_returns_none(self):
        """search_jav 傳入未知來源（如 'javguru'）→ 立即返回 None，不走 auto mode"""
        # 確認完全不呼叫任何 scraper
        with patch.object(JavBusScraper, 'search', return_value=None) as mock_jb:
            with patch.object(DMMScraper, 'search', return_value=None) as mock_dmm:
                result = search_jav("SONE-205", source="javguru")

        assert result is None
        mock_jb.assert_not_called()
        mock_dmm.assert_not_called()

    def test_search_jav_unknown_source_no_fallback(self):
        """未知來源不應 fallback 到 auto mode — 即使 scraper 能找到結果也應被攔截"""
        mock_video = Video(
            number="SONE-205",
            title="Should Not Appear",
            actresses=[],
            date="2024-01-01",
            maker="Test",
            cover_url="",
            tags=[],
            source="javbus",
            detail_url="https://example.com",
        )

        with patch.object(JavBusScraper, 'search', return_value=mock_video):
            result = search_jav("SONE-205", source="javguru")

        assert result is None
