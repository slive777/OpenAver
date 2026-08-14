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
                        from core.scrapers.fc2_official import FC2OfficialScraper
                        from core.scrapers.avsox import AVSOXScraper
                        with patch.object(FC2OfficialScraper, 'search', return_value=None):
                            with patch.object(AVSOXScraper, 'search', return_value=None):
                                smart_search("SONE-205", uncensored_mode=True)

        mock_d2.assert_called()
        mock_heyzo.assert_called()

    def test_dmm_top1_when_proxy(self):
        """DMM first in enabled order + proxy_url → cascade 直打 DMM 命中，javbus 不被呼叫。

        新 cascade（spec-85 B1，CD-85-1）：依 get_enabled_source_ids 優先序串接直打，
        DMM 排第一 → cascade 直打 DMM → 命中 → early-return，javbus 不被試到。
        """
        from unittest.mock import ANY
        mock_result = {'number': 'SONE-205', 'title': 'T', '_source': 'dmm'}

        def _single_source(number, source, proxy_url=''):
            if source == 'dmm':
                return mock_result
            return None

        with patch('core.scraper.get_enabled_source_ids', return_value=['dmm', 'javbus']), \
             patch('core.scraper.metatube_state') as mock_mt, \
             patch('core.scraper.search_jav_single_source', side_effect=_single_source) as mock_ss:
            mock_mt.availability_map.return_value = {}
            results = smart_search("SONE-205", proxy_url="http://proxy:8080")

        assert len(results) == 1
        assert results[0]['_mode'] == 'exact'
        assert results[0]['_source'] == 'dmm'
        mock_ss.assert_called_once_with('SONE-205', 'dmm', proxy_url=ANY)

    def test_uncensored_mode_fast_path_fc2(self):
        """uncensored_mode=True + FC2 前綴 → D2PassScraper 不被呼叫"""
        mock_video = _make_video("fc2", "FC2-PPV-1234567")

        from core.scrapers.fc2_official import FC2OfficialScraper
        from core.scrapers.avsox import AVSOXScraper

        with patch.object(D2PassScraper, 'search', return_value=None) as mock_d2:
            with patch.object(HEYZOScraper, 'search', return_value=None):
                with patch.object(FC2OfficialScraper, 'search', return_value=mock_video):
                    with patch.object(AVSOXScraper, 'search', return_value=None):
                        with patch('core.scrapers.dmm.rate_limit'):
                            results = smart_search("FC2-PPV-1234567", uncensored_mode=True)

        assert len(results) == 1
        mock_d2.assert_not_called()

    def test_exact_path_no_fan_out(self):
        """精確番號路徑：cascade 不呼叫 fan-out（merge_results 不被呼叫），全 miss → []。

        新 cascade（spec-85 B1，CD-85-1）：串接直打不走 wait-all fan-out。
        全 miss → [] 且 merge_results.assert_not_called()（fan-out 守衛）。
        """
        with patch('core.scraper.get_enabled_source_ids', return_value=['dmm', 'javbus']), \
             patch('core.scraper.metatube_state') as mock_mt, \
             patch('core.scraper.search_jav_single_source', return_value=None), \
             patch('core.scraper.merge_results') as mock_merge:
            mock_mt.availability_map.return_value = {}
            results = smart_search("SONE-205", proxy_url="")

        assert results == []
        mock_merge.assert_not_called()

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
        from core.scrapers.fc2_official import FC2OfficialScraper
        from core.scrapers.avsox import AVSOXScraper
        dmm_video = _make_video("dmm", "SONE-205")
        javbus_video = _make_video("javbus", "SONE-205")

        # Class autouse fixture already monkeypatches get_enabled_source_ids → SOURCE_ORDER
        # (dmm is first in SOURCE_ORDER) — no override needed here.
        with patch.object(DMMScraper, 'search', return_value=dmm_video), \
             patch.object(JavBusScraper, 'search', return_value=javbus_video), \
             patch.object(JAV321Scraper, 'search', return_value=None), \
             patch.object(JavDBScraper, 'search', return_value=None), \
             patch.object(FC2OfficialScraper, 'search', return_value=None), \
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
        from core.scrapers.fc2_official import FC2OfficialScraper
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
             patch.object(FC2OfficialScraper, 'search', return_value=None), \
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


# ============================================================
# TestFc2Dispatch — TASK-118-T3：fc2 source id 建的是官方站類別
# ============================================================

class TestFc2Dispatch:
    """dispatch 路徑：source='fc2' 必須建構 FC2OfficialScraper，不是 javten FC2JavtenScraper。"""

    def test_fc2_source_constructs_official_scraper(self):
        """search_jav(source='fc2') 建出來的是 FC2OfficialScraper。"""
        constructed = []

        def factory(*args, **kwargs):
            constructed.append(True)
            inst = MagicMock()
            inst.search.return_value = None
            return inst

        with patch('core.scraper.FC2OfficialScraper', side_effect=factory) as mock_official:
            result = search_jav("FC2-PPV-1234567", source="fc2")

        assert mock_official.called
        assert len(constructed) == 1
        assert result is None


class TestFcJavtenDispatch:
    """TASK-118a-T4：dispatch 表必須含 fc-javten → FC2JavtenScraper。"""

    def test_source_to_scraper_includes_fc_javten(self):
        """search_jav(source='fc-javten') 必須建構並呼叫 FC2JavtenScraper.search。"""
        from core.scrapers.fc2_javten import FC2JavtenScraper

        with patch.object(FC2JavtenScraper, 'search', return_value=None) as mock_search:
            result = search_jav("FC2-PPV-1234567", source="fc-javten")

        mock_search.assert_called()
        assert result is None


# ============================================================
# TestFuzzyGuard — CD-65-4 always-on 與 partial 能力約束護欄
# （T4，CD-85-7：fuzzy chain always-on / partial javbus 寫死）
# ============================================================

class TestFuzzyGuard:
    """fuzzy chain 永遠含 javbus（always-on，CD-65-4），
    partial 固定走 javbus（能力約束），兩者不受 enabled_sids 影響。

    這些測試守既有行為——現在就 GREEN，T1a cascade 改動後也必須 GREEN。
    Patch target 一律指使用端 core.scraper.*（gotchas-backend.md §Mock Patch Target）。
    """

    def test_fuzzy_chain_always_on_even_if_javbus_disabled(self):
        """javbus 停用（get_enabled_source_ids→[]）→ fuzzy chain 仍含 javbus（always-on, CD-65-4）

        突變有效性：把 _fuzzy_search_chain L674 改為 get_enabled_source_ids() →
        chain=[]，get_ids_from_search 不被呼叫 → assert_called() RED。
        """
        from core.scraper import search_actress

        with patch('core.scraper.get_enabled_source_ids', return_value=[]), \
             patch('core.scraper.get_all_source_ids_ordered', return_value=['javbus', 'dmm']), \
             patch.object(JavBusScraper, 'get_ids_from_search', return_value=['SONE-205']) as mock_jb, \
             patch('core.scraper.search_jav', return_value={'number': 'SONE-205', 'title': 'Test', 'source': 'javbus'}):
            results = search_actress("テスト", limit=1, proxy_url='')

        # javbus must be called even though get_enabled_source_ids returned []
        mock_jb.assert_called()
        assert len(results) >= 1

    def test_partial_search_always_uses_javbus(self):
        """partial（MIDV-01）固定走 javbus（能力約束），不受 enabled_sids 影響。

        突變有效性：把 search_partial L397 改為 search_jav(num, enabled_sids[0]) →
        enabled=[] → IndexError 或 call_count=0 → 斷言 RED；
        或改為 'dmm' → source 斷言 RED。
        """
        from core.scraper import search_partial

        with patch('core.scraper.get_enabled_source_ids', return_value=[]), \
             patch('core.scraper.expand_partial_number', return_value=['MIDV-010', 'MIDV-011']), \
             patch('core.scraper.search_jav', return_value=None) as mock_search_jav:
            search_partial('MIDV-01')

        # search_jav must have been called with source='javbus' (hardcoded, not from enabled list)
        assert mock_search_jav.call_count >= 1, "search_partial must call search_jav (hardcoded javbus)"


# ============================================================
# TestCascadeExactBranch — TDD-lite RED→GREEN cascade 測試
# （T1a，spec-85 B1，CD-85-1/2）
# ============================================================

class TestCascadeExactBranch:
    """exact 番號分支新 cascade：依 get_enabled_source_ids 優先序串接直打、命中即回。

    standalone（不繼承 TestPipeline），自行 patch get_enabled_source_ids 以控制
    enabled 順序，避免 autouse fixture 干擾。
    Patch target 一律指使用端 core.scraper.*（gotchas-backend.md §Mock Patch Target）。
    """

    def test_firstsource_fastpath_hit_dmm(self):
        """enabled=['dmm','javbus']，DMM 命中 → 只呼叫 dmm、不呼叫 javbus（early-return）。

        突變有效性：把 cascade early-return 拿掉（跑完所有才回）→
        assert_called_once_with('HMN-706', 'dmm', ...) 轉 RED（javbus 也被試了）。
        """
        from core.scraper import smart_search
        from unittest.mock import ANY

        mock_result = {'number': 'HMN-706', 'title': 'T', '_source': 'dmm'}

        def _single_source(number, source, proxy_url=''):
            if source == 'dmm':
                return mock_result
            return None

        with patch('core.scraper.get_enabled_source_ids', return_value=['dmm', 'javbus']), \
             patch('core.scraper.metatube_state') as mock_mt, \
             patch('core.scraper.search_jav_single_source', side_effect=_single_source) as mock_ss:
            mock_mt.availability_map.return_value = {}
            results = smart_search('HMN-706')

        assert len(results) == 1
        assert results[0]['_source'] == 'dmm'
        assert results[0]['_mode'] == 'exact'
        mock_ss.assert_called_once_with('HMN-706', 'dmm', proxy_url=ANY)

    def test_firstsource_fastpath_hit_javbus(self):
        """enabled=['javbus','dmm']，javbus 命中 → 只呼叫 javbus、不呼叫 dmm。"""
        from core.scraper import smart_search
        from unittest.mock import ANY

        mock_result = {'number': 'HMN-706', 'title': 'T', '_source': 'javbus'}

        def _single_source(number, source, proxy_url=''):
            if source == 'javbus':
                return mock_result
            return None

        with patch('core.scraper.get_enabled_source_ids', return_value=['javbus', 'dmm']), \
             patch('core.scraper.metatube_state') as mock_mt, \
             patch('core.scraper.search_jav_single_source', side_effect=_single_source) as mock_ss:
            mock_mt.availability_map.return_value = {}
            results = smart_search('HMN-706')

        assert len(results) == 1
        assert results[0]['_source'] == 'javbus'
        assert results[0]['_mode'] == 'exact'
        mock_ss.assert_called_once_with('HMN-706', 'javbus', proxy_url=ANY)

    def test_fastpath_sequential_miss_then_hit(self):
        """enabled=['dmm','javbus']，dmm miss → javbus 命中 → call_count==2。

        突變有效性：若 miss 後不繼續下一個 sid → call_count==1 → RED。
        """
        from core.scraper import smart_search

        mock_result = {'number': 'HMN-706', 'title': 'T', '_source': 'javbus'}

        def _single_source(number, source, proxy_url=''):
            if source == 'javbus':
                return mock_result
            return None  # dmm miss

        with patch('core.scraper.get_enabled_source_ids', return_value=['dmm', 'javbus']), \
             patch('core.scraper.metatube_state') as mock_mt, \
             patch('core.scraper.search_jav_single_source', side_effect=_single_source) as mock_ss:
            mock_mt.availability_map.return_value = {}
            results = smart_search('HMN-706')

        assert len(results) == 1
        assert results[0]['_source'] == 'javbus'
        assert mock_ss.call_count == 2  # dmm 試了、javbus 試了

    def test_fastpath_exception_no_propagate(self):
        """enabled=['dmm','javbus']，dmm 拋 Exception → 不 propagate，繼續試 javbus。

        突變有效性：去掉 try/except → TEST RED（例外 propagate）。
        """
        from core.scraper import smart_search

        mock_result = {'number': 'HMN-706', 'title': 'T', '_source': 'javbus'}

        def _single_source(number, source, proxy_url=''):
            if source == 'dmm':
                raise Exception('timeout')
            return mock_result

        with patch('core.scraper.get_enabled_source_ids', return_value=['dmm', 'javbus']), \
             patch('core.scraper.metatube_state') as mock_mt, \
             patch('core.scraper.search_jav_single_source', side_effect=_single_source):
            mock_mt.availability_map.return_value = {}
            results = smart_search('HMN-706')  # must not raise

        assert len(results) == 1
        assert results[0]['_source'] == 'javbus'

    def test_fastpath_all_miss_returns_empty(self):
        """enabled=['dmm','javbus']，全 miss → [] 且 merge_results 不被呼叫（fan-out 守衛）。

        突變有效性：把 cascade 的 return [] 改成呼叫 fan-out →
        merge_results.assert_not_called() 轉 RED。
        """
        from core.scraper import smart_search

        with patch('core.scraper.get_enabled_source_ids', return_value=['dmm', 'javbus']), \
             patch('core.scraper.metatube_state') as mock_mt, \
             patch('core.scraper.search_jav_single_source', return_value=None), \
             patch('core.scraper.merge_results') as mock_merge:
            mock_mt.availability_map.return_value = {}
            results = smart_search('HMN-706')

        assert results == []
        mock_merge.assert_not_called()

    def test_cascade_status_callback_sequence(self):
        """status_callback 逐 sid emit 序列（CD-85-10）。

        全 miss：[('dmm','searching'),('javbus','searching'),('done','found:0')]
        dmm 命中：[('dmm','searching'),('done','found:1')]（javbus 不 emit，early-return）

        突變有效性：拿掉迴圈內 emit (sid,'searching') → miss 序列首兩個 tuple 消失 → RED；
        拿掉全 miss 的 ('done','found:0') → miss 序列尾 tuple 消失 → RED。
        """
        from core.scraper import smart_search

        # --- 全 miss 序列 ---
        miss_calls = []
        with patch('core.scraper.get_enabled_source_ids', return_value=['dmm', 'javbus']), \
             patch('core.scraper.metatube_state') as mock_mt, \
             patch('core.scraper.search_jav_single_source', return_value=None):
            mock_mt.availability_map.return_value = {}
            smart_search('HMN-706', status_callback=lambda a, b: miss_calls.append((a, b)))

        assert miss_calls == [
            ('dmm', 'searching'),
            ('javbus', 'searching'),
            ('done', 'found:0'),
        ]

        # --- dmm 命中序列（javbus 不 emit）---
        hit_calls = []
        mock_result = {'number': 'HMN-706', 'title': 'T', '_source': 'dmm'}

        def _single_source(number, source, proxy_url=''):
            return mock_result if source == 'dmm' else None

        with patch('core.scraper.get_enabled_source_ids', return_value=['dmm', 'javbus']), \
             patch('core.scraper.metatube_state') as mock_mt, \
             patch('core.scraper.search_jav_single_source', side_effect=_single_source):
            mock_mt.availability_map.return_value = {}
            smart_search('HMN-706', status_callback=lambda a, b: hit_calls.append((a, b)))

        assert hit_calls == [
            ('dmm', 'searching'),
            ('done', 'found:1'),
        ]
