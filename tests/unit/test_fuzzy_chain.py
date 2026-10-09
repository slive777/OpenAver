"""
TestFuzzyChain — 模糊 fallback 鏈 unit tests (TASK-65c-1)

覆蓋 spec §4 US-3 驗收條件，13 個邊界條件全部。
Mock 策略：monkeypatch get_all_source_ids_ordered + patch.object on scraper classes.
"""
import pytest
from unittest.mock import patch, MagicMock, call

from core.scrapers.dmm import DMMScraper
from core.scrapers.javbus import JavBusScraper
from core.scrapers.jav321 import JAV321Scraper
from core.scrapers.javdb import JavDBScraper
from core.scrapers.models import Video


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


def _make_dict(source: str, number: str = "TEST-001") -> dict:
    return {"number": number, "title": "Test Title", "source": source}


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch):
    """跳過 rate_limit / time.sleep，加速測試"""
    monkeypatch.setattr("core.scrapers.dmm.rate_limit", lambda *a, **kw: None)
    monkeypatch.setattr("core.scraper.time.sleep", lambda *a: None)


@pytest.fixture(autouse=True)
def _dmm_capsule(monkeypatch):
    """DMM 開關看膠囊（BE-TEST-01：patch 使用端 core.scraper.is_source_enabled）。
    預設膠囊開；要測「膠囊關」的案例自己再 setattr 成 False。"""
    monkeypatch.setattr("core.scraper.is_source_enabled", lambda sid: True)


# ============================================================
# TestFuzzyChain — 13 boundary conditions
# ============================================================

class TestFuzzyChain:
    """模糊鏈邊界條件測試（spec §4 US-3 驗收條件 1-13）"""

    # ---- 1. 鏈順序跟 Active Row（非寫死） ----
    def test_chain_follows_active_row_order(self, monkeypatch):
        """mock order=['javbus','dmm']，javbus 空 → dmm 命中（TASK-65g: 2 源池）"""
        from core.scraper import _fuzzy_search_chain

        monkeypatch.setattr("core.scraper.get_all_source_ids_ordered",
                            lambda: ['javbus', 'dmm'])

        with patch.object(JavBusScraper, 'get_ids_from_search', return_value=[]) as mock_jb, \
             patch('core.scraper._dmm_keyword_search_progressive',
                   return_value=[{'number': 'MIDE-100', 'source': 'dmm'}]) as mock_dmm:
            results = _fuzzy_search_chain("some actress")

        mock_jb.assert_called()          # javbus reached but returned empty
        mock_dmm.assert_called_once()    # dmm reached and hit
        assert len(results) == 1
        assert results[0]['source'] == 'dmm'  # order-driven: javbus empty → dmm hit

    # ---- 2. DMM 排第一但膠囊關 → 跳過，繼續到 javbus ----
    def test_dmm_first_capsule_off_falls_through_to_javbus(self, monkeypatch):
        """DMM 排第一 + DMM 膠囊關 → DMM 不呼叫，javbus 命中"""
        from core.scraper import _fuzzy_search_chain

        monkeypatch.setattr("core.scraper.is_source_enabled", lambda sid: False)

        monkeypatch.setattr("core.scraper.get_all_source_ids_ordered",
                            lambda: ['dmm', 'javbus', 'jav321', 'javdb'])

        with patch.object(DMMScraper, 'search_by_keyword_with_ids') as mock_dmm, \
             patch.object(JavBusScraper, 'get_ids_from_search',
                          return_value=['SONE-205']) as mock_jb, \
             patch('core.scraper.search_jav',
                   return_value=_make_dict("javbus", "SONE-205")):
            results = _fuzzy_search_chain("三上悠亜")

        mock_dmm.assert_not_called()  # DMM bypassed — capsule off
        mock_jb.assert_called()
        assert len(results) >= 1
        assert results[0]['source'] == 'javbus'

    # ---- 3. AVSOX 排第一 → 跳過 ----
    def test_non_fuzzy_source_avsox_skipped(self, monkeypatch):
        """avsox 不在 FUZZY_SEARCH_SOURCES → 跳過，直達 javbus"""
        from core.scraper import _fuzzy_search_chain
        from core.scrapers.avsox import AVSOXScraper

        monkeypatch.setattr("core.scraper.get_all_source_ids_ordered",
                            lambda: ['avsox', 'javbus', 'dmm', 'jav321', 'javdb'])

        # side_effect: first page returns ids, subsequent pages empty (stops pagination)
        with patch.object(AVSOXScraper, 'search', return_value=None) as mock_avsox, \
             patch.object(JavBusScraper, 'get_ids_from_search',
                          side_effect=[['TEST-001'], []]) as mock_jb, \
             patch('core.scraper.search_jav',
                   return_value=_make_dict("javbus", "TEST-001")):
            results = _fuzzy_search_chain("actress")

        mock_avsox.assert_not_called()
        mock_jb.assert_called()
        assert len(results) >= 1
        assert results[0]['source'] == 'javbus'

    # ---- 4. 停用的候選池源模糊仍用（always-on） ----
    def test_disabled_source_still_reached_by_chain(self, monkeypatch):
        """get_all_source_ids_ordered 回含 javbus（不管 enabled），鏈仍能到達並命中"""
        from core.scraper import _fuzzy_search_chain

        # get_all_source_ids_ordered 不過濾 enabled，停用但仍在列表
        monkeypatch.setattr("core.scraper.get_all_source_ids_ordered",
                            lambda: ['javbus'])

        with patch.object(JavBusScraper, 'get_ids_from_search',
                          side_effect=[['SONE-111'], []]) as mock_jb, \
             patch('core.scraper.search_jav',
                   return_value=_make_dict("javbus", "SONE-111")):
            results = _fuzzy_search_chain("actress")

        mock_jb.assert_called()
        assert len(results) >= 1

    # ---- 5. 非模糊源 / metatube 排最前 → 跳過 ----
    def test_metatube_and_fc2_skipped(self, monkeypatch):
        """metatube:abc 和 fc2 不在 FUZZY_SEARCH_SOURCES → 鏈從 javbus 開始"""
        from core.scraper import _fuzzy_search_chain
        from core.scrapers.fc2_official import FC2OfficialScraper

        monkeypatch.setattr("core.scraper.get_all_source_ids_ordered",
                            lambda: ['metatube:abc', 'fc2', 'javbus', 'dmm'])

        with patch.object(FC2OfficialScraper, 'search', return_value=None) as mock_fc2, \
             patch.object(JavBusScraper, 'get_ids_from_search',
                          side_effect=[['FC2-TEST'], []]) as mock_jb, \
             patch('core.scraper.search_jav',
                   return_value=_make_dict("javbus", "FC2-TEST")):
            results = _fuzzy_search_chain("actress")

        mock_fc2.assert_not_called()
        mock_jb.assert_called()
        assert len(results) >= 1
        assert results[0]['source'] == 'javbus'

    # ---- 6. 候選池 4 源排在一堆非模糊源之後 ----
    def test_fuzzy_sources_reached_after_non_fuzzy_sources(self, monkeypatch):
        """heyzo、d2pass、metatube:x 排前面，javbus 排後面 → 鏈最終到達 javbus"""
        from core.scraper import _fuzzy_search_chain
        from core.scrapers.heyzo import HEYZOScraper
        from core.scrapers.d2pass import D2PassScraper

        monkeypatch.setattr("core.scraper.get_all_source_ids_ordered",
                            lambda: ['heyzo', 'd2pass', 'metatube:x', 'javbus', 'dmm'])

        with patch.object(HEYZOScraper, 'search', return_value=None), \
             patch.object(D2PassScraper, 'search', return_value=None), \
             patch.object(JavBusScraper, 'get_ids_from_search',
                          side_effect=[['SONE-001'], []]) as mock_jb, \
             patch('core.scraper.search_jav',
                   return_value=_make_dict("javbus", "SONE-001")):
            results = _fuzzy_search_chain("actress")

        mock_jb.assert_called()
        assert len(results) >= 1

    # ---- 7. 空鏈（所有候選池源都被過濾掉）→ [] ----
    def test_empty_chain_returns_empty_list(self, monkeypatch):
        """get_all_source_ids_ordered 只回 heyzo、fc2 → chain=[] → 回 []"""
        from core.scraper import _fuzzy_search_chain

        monkeypatch.setattr("core.scraper.get_all_source_ids_ordered",
                            lambda: ['heyzo', 'fc2'])

        results = _fuzzy_search_chain("actress")
        assert results == []

    # ---- 8. seed 只由第一個實際發動源送 ----
    def test_seed_sent_exactly_once_by_first_dispatched_source(self, monkeypatch):
        """order=['dmm','javbus']，DMM 膠囊關（DMM 被跳過）→ seed 由 javbus 送，恰好 1 次"""
        from core.scraper import _fuzzy_search_chain

        monkeypatch.setattr("core.scraper.is_source_enabled", lambda sid: False)

        monkeypatch.setattr("core.scraper.get_all_source_ids_ordered",
                            lambda: ['dmm', 'javbus', 'jav321', 'javdb'])

        seed_calls = []

        def mock_result_callback(slot, data):
            if slot == -1:
                seed_calls.append(data)

        with patch.object(DMMScraper, 'search_by_keyword_with_ids') as mock_dmm, \
             patch.object(JavBusScraper, 'get_ids_from_search',
                          side_effect=[['SONE-205'], []]) as mock_jb, \
             patch('core.scraper.search_jav',
                   return_value=_make_dict("javbus", "SONE-205")):
            results = _fuzzy_search_chain(
                "三上悠亜",
                result_callback=mock_result_callback,
            )

        mock_dmm.assert_not_called()
        assert len(seed_calls) == 1, f"Expected 1 seed, got {len(seed_calls)}"
        assert 'SONE-205' in seed_calls[0]

    # ---- 9. DMM None 視為空 → 繼續試下一個 ----
    def test_dmm_none_result_falls_through_to_javbus(self, monkeypatch):
        """DMM search_by_keyword_with_ids 回 []（progressive 回 None）→ adapter 轉 []
        → 鏈繼續，javbus 命中"""
        from core.scraper import _fuzzy_search_chain

        monkeypatch.setattr("core.scraper.get_all_source_ids_ordered",
                            lambda: ['dmm', 'javbus', 'jav321', 'javdb'])

        with patch.object(DMMScraper, 'search_by_keyword_with_ids',
                          return_value=[]) as mock_dmm, \
             patch.object(JavBusScraper, 'get_ids_from_search',
                          side_effect=[['SONE-205'], []]) as mock_jb, \
             patch('core.scraper.search_jav',
                   return_value=_make_dict("javbus", "SONE-205")), \
             patch('core.scrapers.dmm.rate_limit'):
            results = _fuzzy_search_chain("actress")

        mock_dmm.assert_called_once()  # DMM called but returned nothing
        mock_jb.assert_called()        # JavBus tried as next
        assert len(results) == 1

    # ---- 10. javdb 不在 FUZZY_SEARCH_SOURCES → 鏈忽略 javdb（TASK-65g） ----
    def test_javdb_excluded_from_fuzzy_pool(self, monkeypatch):
        """javdb 不在 FUZZY_SEARCH_SOURCES → order=['javdb'] 交集後 chain=[] → 回 []"""
        from core.scraper import _fuzzy_search_chain

        monkeypatch.setattr("core.scraper.get_all_source_ids_ordered",
                            lambda: ['javdb'])

        with patch.object(JavDBScraper, 'search_by_keyword', return_value=[]) as mock_javdb:
            results = _fuzzy_search_chain("actress")

        mock_javdb.assert_not_called()  # javdb filtered out by FUZZY_SEARCH_SOURCES intersection
        assert results == []

    # ---- 11. `_get_fuzzy_source` 已刪 ----
    def test_get_fuzzy_source_deleted(self):
        """_get_fuzzy_source 函式已從 core.scraper 移除 → ImportError / AttributeError"""
        import core.scraper
        assert not hasattr(core.scraper, '_get_fuzzy_source'), \
            "_get_fuzzy_source 應已刪除，但仍存在於 core.scraper"

    # ---- 12. `search_actress` 簽章不含 `primary_source` ----
    def test_search_actress_no_primary_source_param(self):
        """search_actress(primary_source='dmm') → TypeError"""
        from core.scraper import search_actress
        with pytest.raises(TypeError, match="primary_source"):
            search_actress("actress", primary_source="dmm")

    # ---- 13. discovery_only=True 路徑不回歸 ----
    def test_discovery_only_returns_stub_list(self, monkeypatch):
        """search_actress("abc", discovery_only=True) → [{'number':..., 'title':''}]"""
        from core.scraper import search_actress

        monkeypatch.setattr("core.scraper.get_all_source_ids_ordered",
                            lambda: ['javbus', 'dmm', 'jav321', 'javdb'])

        with patch.object(JavBusScraper, 'get_ids_from_search',
                          side_effect=[['TEST-001'], []]):
            results = search_actress("abc", discovery_only=True)

        assert len(results) == 1
        assert results[0] == {'number': 'TEST-001', 'title': ''}

    # ---- 14. 迴歸：DMM 排第一 + proxy + discovery_only=True → DMM 不呼叫，回 javbus stubs ----
    def test_dmm_first_discovery_only_skips_dmm(self, monkeypatch):
        """Regression: DMM first in Active Row + discovery_only=True
        → DMMScraper.search_by_keyword_with_ids must NOT be called;
        result must be javbus stub list [{'number': ..., 'title': ''}]."""
        from core.scraper import search_actress

        monkeypatch.setattr("core.scraper.get_all_source_ids_ordered",
                            lambda: ['dmm', 'javbus', 'jav321', 'javdb'])

        with patch.object(DMMScraper, 'search_by_keyword_with_ids') as mock_dmm, \
             patch.object(JavBusScraper, 'get_ids_from_search',
                          side_effect=[['SONE-999'], []]):
            results = search_actress(
                "三上悠亜",
                discovery_only=True,
            )

        # DMM keyword search must NOT be called in discovery_only mode
        mock_dmm.assert_not_called()
        assert len(results) == 1
        assert results[0] == {'number': 'SONE-999', 'title': ''}, \
            f"Expected javbus stub, got {results[0]}"

    # ---- 15. discovery_only=True, javbus 排第一 → stubs 回傳，無 enrichment ----
    def test_discovery_only_javbus_first_returns_stubs_no_enrichment(self, monkeypatch):
        """Companion: discovery_only=True with javbus first → javbus stubs returned,
        no ThreadPool enrichment (search_jav not called)."""
        from core.scraper import search_actress

        monkeypatch.setattr("core.scraper.get_all_source_ids_ordered",
                            lambda: ['javbus', 'dmm', 'jav321', 'javdb'])

        search_jav_calls = []

        def fake_search_jav(num, source='javbus'):
            search_jav_calls.append(num)
            return {'number': num, 'title': f'Title {num}'}

        with patch.object(JavBusScraper, 'get_ids_from_search',
                          side_effect=[['ABC-001', 'ABC-002'], []]), \
             patch('core.scraper.search_jav', side_effect=fake_search_jav):
            results = search_actress("actress", discovery_only=True)

        assert search_jav_calls == [], \
            f"search_jav must not be called in discovery_only mode, got {search_jav_calls}"
        assert len(results) == 2
        for r in results:
            assert r['title'] == '', f"Expected empty title stub, got title={r['title']!r}"


# ============================================================
# Regression: smart_search fuzzy else-branch — no post-chain jav321 fallback (CD-plan-65-5)
# ============================================================

class TestSmartSearchFuzzyNoPostChainFallback:
    """Regression tests for Codex finding: smart_search fuzzy else-branch must NOT
    call search_jav321_keyword after the chain is exhausted (CD-plan-65-5).

    The Active Row order is the single source of truth.  A hardcoded jav321
    fallback after _fuzzy_search_chain returns [] would:
      (a) bypass Active Row ordering entirely, and
      (b) call jav321 a second time if it was already in the chain.
    """

    # ---- 16. No fuzzy candidates → smart_search returns [] (no order bypass) ----
    def test_smart_search_no_fuzzy_candidates_returns_empty(self, monkeypatch):
        """Codex regression: get_all_source_ids_ordered=['heyzo','fc2'] (no fuzzy
        candidates) + non-number keyword → smart_search returns [] and
        JAV321Scraper.search_by_keyword is NEVER called."""
        from core.scraper import smart_search
        from core.scrapers.jav321 import JAV321Scraper

        monkeypatch.setattr(
            "core.scraper.get_all_source_ids_ordered",
            lambda: ['heyzo', 'fc2'],
        )

        with patch.object(JAV321Scraper, 'search_by_keyword', return_value=[_make_video('jav321')]) as mock_jav321:
            results = smart_search("蒼井そら", limit=5)

        # JAV321Scraper.search_by_keyword must NOT be called when jav321 is not in the Active Row
        mock_jav321.assert_not_called()
        assert results == [], \
            f"Expected [] when chain has no fuzzy candidates, got {results}"

    # ---- 17. jav321 removed from fuzzy pool → never called via chain ----
    def test_jav321_removed_from_fuzzy_pool_not_called(self, monkeypatch):
        """jav321 is NOT in FUZZY_SEARCH_SOURCES (TASK-65g) → order=['javbus'],
        javbus empty → chain exhausted → search_jav321_keyword call_count == 0."""
        from core.scraper import smart_search

        monkeypatch.setattr(
            "core.scraper.get_all_source_ids_ordered",
            lambda: ['javbus'],
        )

        call_count = []

        def fake_jav321_search(query, limit=20, status_callback=None):
            call_count.append(1)
            return []

        with patch('core.scraper.search_jav321_keyword', side_effect=fake_jav321_search), \
             patch.object(JavBusScraper, 'get_ids_from_search', return_value=[]):
            results = smart_search("some keyword query", limit=5)

        assert len(call_count) == 0, \
            f"search_jav321_keyword must NOT be called via fuzzy chain (jav321 removed from pool), got {len(call_count)} calls"
        assert results == [], \
            f"Expected [] when chain exhausted, got {results}"


# ============================================================
# TestFuzzyDmmSource — DMM _source 一致性（TASK-65g）
# ============================================================

class TestFuzzyDmmSource:
    """DMM 模糊結果攜帶 _source='dmm'（TASK-65g）"""

    def test_dmm_fuzzy_result_carries_internal_source(self, monkeypatch):
        """DMM 命中時，每個結果 dict 應含 _source='dmm'（鏡像 javbus 在 search_jav L354 的行為）"""
        from core.scraper import _fuzzy_search_chain

        monkeypatch.setattr("core.scraper.get_all_source_ids_ordered",
                            lambda: ['dmm', 'javbus'])

        # DMM returns 1 result (no _source yet — _fuzzy_one must add it)
        monkeypatch.setattr(
            "core.scraper._dmm_keyword_search_progressive",
            lambda *a, **kw: [{'number': 'STARS-001', 'source': 'dmm'}],
        )

        # 膠囊開（autouse fixture）所以 DMM 閘放行
        results = _fuzzy_search_chain("actress")

        assert len(results) == 1, f"Expected 1 result, got {results}"
        assert results[0]['_source'] == 'dmm', \
            f"Expected _source='dmm', got {results[0].get('_source')!r}"
