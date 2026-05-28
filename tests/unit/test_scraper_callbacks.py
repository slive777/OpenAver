"""
test_scraper_callbacks.py - result_callback 參數行為單元測試

測試範圍：
- result_callback slot index 正確性
- seed event 時機（found:N 後送出）
- 空 target_ids 守衛（不呼叫 result_callback(-1, [])）
- 向後相容性（result_callback=None 不改變行為）
"""

import pytest
from unittest.mock import patch, MagicMock, call
from concurrent.futures import ThreadPoolExecutor


# ============ Fixtures ============

def make_mock_scraper_prefix(ids):
    """Mock JavBusScraper for prefix search.
    Returns ids on the first call, then [] on subsequent calls (simulates single page).
    """
    mock_scraper = MagicMock()
    mock_scraper.get_ids_from_search.side_effect = [ids, []]
    return mock_scraper


def make_mock_scraper_actress(ids_per_page):
    """Mock JavBusScraper for actress search (multi-page).
    ids_per_page: list of list[str] — each inner list is one page of IDs.
    For single page, pass [ids].
    """
    mock_scraper = MagicMock()
    # side_effect 讓每次呼叫回傳下一頁，用完後回傳 []
    mock_scraper.get_ids_from_search.side_effect = list(ids_per_page) + [[]]
    return mock_scraper




# ============ search_prefix result_callback 測試 ============

class TestSearchPrefixResultCallback:
    """測試 search_prefix() 的 result_callback 行為"""

    def test_result_callback_none_default_no_error(self, make_mock_search_jav):
        """result_callback=None（預設）不會拋出錯誤，行為與現在完全相同"""
        from core.scraper import search_prefix

        ids = ['SONE-100', 'SONE-101', 'SONE-102']
        results_map = {
            'SONE-100': {'number': 'SONE-100', 'title': 'Title 100'},
            'SONE-101': {'number': 'SONE-101', 'title': 'Title 101'},
            'SONE-102': {'number': 'SONE-102', 'title': 'Title 102'},
        }

        mock_scraper = make_mock_scraper_prefix(ids)

        with patch('core.scraper.JavBusScraper', return_value=mock_scraper), \
             patch('core.scraper.search_jav', side_effect=make_mock_search_jav(results_map)):
            # No result_callback passed — should not raise
            results = search_prefix('SONE', limit=20)
            assert isinstance(results, list)

    def test_seed_sent_after_found(self, make_mock_search_jav):
        """result_callback(-1, target_ids) 應在 found:N 後被呼叫一次"""
        from core.scraper import search_prefix

        ids = ['SONE-100', 'SONE-101']
        results_map = {
            'SONE-100': {'number': 'SONE-100', 'title': 'Title 100'},
            'SONE-101': {'number': 'SONE-101', 'title': 'Title 101'},
        }

        mock_scraper = make_mock_scraper_prefix(ids)
        callback_calls = []

        def result_callback(slot, data):
            callback_calls.append((slot, data))

        with patch('core.scraper.JavBusScraper', return_value=mock_scraper), \
             patch('core.scraper.search_jav', side_effect=make_mock_search_jav(results_map)):
            search_prefix('SONE', limit=20, result_callback=result_callback)

        # seed (slot=-1) must have been called exactly once
        seed_calls = [(s, d) for s, d in callback_calls if s == -1]
        assert len(seed_calls) == 1, f"Expected 1 seed call, got {len(seed_calls)}"

        # seed data should be the target_ids list
        seed_slot, seed_data = seed_calls[0]
        assert seed_slot == -1
        assert set(seed_data) == set(ids)

    def test_slot_index_matches_target_ids_order(self, make_mock_search_jav):
        """result-item slot index 必須對應 target_ids 的原始 index"""
        from core.scraper import search_prefix

        ids = ['SONE-100', 'SONE-101', 'SONE-102']
        results_map = {
            'SONE-100': {'number': 'SONE-100', 'title': 'Title 100'},
            'SONE-101': {'number': 'SONE-101', 'title': 'Title 101'},
            'SONE-102': {'number': 'SONE-102', 'title': 'Title 102'},
        }

        mock_scraper = make_mock_scraper_prefix(ids)
        callback_calls = []

        def result_callback(slot, data):
            callback_calls.append((slot, data))

        with patch('core.scraper.JavBusScraper', return_value=mock_scraper), \
             patch('core.scraper.search_jav', side_effect=make_mock_search_jav(results_map)):
            search_prefix('SONE', limit=20, result_callback=result_callback)

        # Collect result-item calls (slot >= 0)
        item_calls = [(s, d) for s, d in callback_calls if s >= 0]
        assert len(item_calls) == 3, f"Expected 3 item calls, got {len(item_calls)}"

        # Each slot must correspond to target_ids[slot]
        for slot, data in item_calls:
            expected_number = ids[slot]
            assert data['number'] == expected_number, (
                f"Slot {slot} should correspond to {expected_number}, "
                f"but got {data['number']}"
            )

    def test_empty_target_ids_no_seed(self, make_mock_search_jav):
        """found:0 時不應呼叫 result_callback(-1, [])"""
        from core.scraper import search_prefix

        mock_scraper = make_mock_scraper_prefix([])  # empty ids
        callback_calls = []

        def result_callback(slot, data):
            callback_calls.append((slot, data))

        with patch('core.scraper.JavBusScraper', return_value=mock_scraper):
            search_prefix('SONE', limit=20, result_callback=result_callback)

        seed_calls = [(s, d) for s, d in callback_calls if s == -1]
        assert len(seed_calls) == 0, f"Should not send seed for empty results, but got {seed_calls}"

    def test_result_item_not_called_for_none_data(self, make_mock_search_jav):
        """search_jav 回傳 None 時不應呼叫 result_callback(idx, None)"""
        from core.scraper import search_prefix

        ids = ['SONE-100', 'SONE-FAIL']
        results_map = {
            'SONE-100': {'number': 'SONE-100', 'title': 'Title 100'},
            'SONE-FAIL': None,  # scraper fails for this one
        }

        mock_scraper = make_mock_scraper_prefix(ids)
        callback_calls = []

        def result_callback(slot, data):
            callback_calls.append((slot, data))

        with patch('core.scraper.JavBusScraper', return_value=mock_scraper), \
             patch('core.scraper.search_jav', side_effect=make_mock_search_jav(results_map)):
            search_prefix('SONE', limit=20, result_callback=result_callback)

        # Only successful items should trigger result-item callback
        item_calls = [(s, d) for s, d in callback_calls if s >= 0]
        for slot, data in item_calls:
            assert data is not None, "result_callback should not be called with None data"

    def test_search_prefix_cross_page_boundary(self, make_mock_search_jav):
        """offset=20 + limit=20 需要跨頁抓取，不能只拿 10 筆"""
        from core.scraper import search_prefix

        # 模擬兩頁：page 1 有 30 筆，page 2 有 30 筆
        page1_ids = [f'SONE-{i:03d}' for i in range(1, 31)]   # SONE-001 ~ SONE-030
        page2_ids = [f'SONE-{i:03d}' for i in range(31, 61)]  # SONE-031 ~ SONE-060

        mock_scraper = MagicMock()
        mock_scraper.get_ids_from_search.side_effect = [page1_ids, page2_ids, []]

        # 每筆 search_jav 都回傳有效結果
        all_ids = page1_ids + page2_ids
        results_map = {num: {'number': num, 'title': f'Title {num}'} for num in all_ids}

        with patch('core.scraper.JavBusScraper', return_value=mock_scraper), \
             patch('core.scraper.search_jav', side_effect=make_mock_search_jav(results_map)):
            results = search_prefix('SONE', limit=20, offset=20)

        # offset=20 意味著跳過前 20 筆，應該拿到 SONE-021 ~ SONE-040（20 筆）
        assert len(results) == 20, f"Expected 20 results, got {len(results)}"

    def test_search_prefix_results_sorted_by_date(self, make_mock_search_jav):
        """同步 API 回傳結果應按日期排序"""
        from core.scraper import search_prefix

        ids = ['SONE-100', 'SONE-101', 'SONE-102']
        results_map = {
            'SONE-100': {'number': 'SONE-100', 'title': 'T1', 'date': '2025-01-01'},
            'SONE-101': {'number': 'SONE-101', 'title': 'T2', 'date': '2025-03-01'},
            'SONE-102': {'number': 'SONE-102', 'title': 'T3', 'date': '2025-02-01'},
        }

        mock_scraper = MagicMock()
        mock_scraper.get_ids_from_search.side_effect = [ids, []]

        with patch('core.scraper.JavBusScraper', return_value=mock_scraper), \
             patch('core.scraper.search_jav', side_effect=make_mock_search_jav(results_map)):
            results = search_prefix('SONE', limit=20)

        dates = [r['date'] for r in results]
        assert dates == sorted(dates, reverse=True), f"Results not sorted by date: {dates}"


# ============ search_actress result_callback 測試 ============

class TestSearchActressResultCallback:
    """測試 search_actress() 的 result_callback 行為"""

    def test_result_callback_none_default_no_error(self, make_mock_search_jav):
        """result_callback=None（預設）不會拋出錯誤"""
        from core.scraper import search_actress

        ids = ['SONE-100', 'SONE-101']
        results_map = {
            'SONE-100': {'number': 'SONE-100', 'title': 'Title 100', 'actors': ['三上悠亜']},
            'SONE-101': {'number': 'SONE-101', 'title': 'Title 101', 'actors': ['三上悠亜']},
        }

        mock_scraper = make_mock_scraper_actress([ids])

        with patch('core.scraper.JavBusScraper', return_value=mock_scraper), \
             patch('core.scraper.search_jav', side_effect=make_mock_search_jav(results_map)):
            results = search_actress('三上悠亜', limit=20)
            assert isinstance(results, list)

    def test_seed_sent_after_found(self, make_mock_search_jav):
        """result_callback(-1, target_ids) 應在 JavBus found:N 後被呼叫一次"""
        from core.scraper import search_actress

        ids = ['SONE-100', 'SONE-101', 'SONE-102']
        results_map = {
            'SONE-100': {'number': 'SONE-100', 'title': 'Title 100', 'actors': ['三上悠亜']},
            'SONE-101': {'number': 'SONE-101', 'title': 'Title 101', 'actors': ['三上悠亜']},
            'SONE-102': {'number': 'SONE-102', 'title': 'Title 102', 'actors': ['三上悠亜']},
        }

        mock_scraper = make_mock_scraper_actress([ids])
        callback_calls = []

        def result_callback(slot, data):
            callback_calls.append((slot, data))

        # limit=3 ensures target_ids is exactly ids (no extra page fetching)
        with patch('core.scraper.JavBusScraper', return_value=mock_scraper), \
             patch('core.scraper.search_jav', side_effect=make_mock_search_jav(results_map)):
            search_actress('三上悠亜', limit=3, result_callback=result_callback)

        seed_calls = [(s, d) for s, d in callback_calls if s == -1]
        assert len(seed_calls) == 1, f"Expected 1 seed call, got {len(seed_calls)}"

        seed_slot, seed_data = seed_calls[0]
        assert seed_slot == -1
        assert set(seed_data) == set(ids)

    def test_slot_index_matches_target_ids_order(self, make_mock_search_jav):
        """result-item slot index 必須對應 target_ids 的原始 index"""
        from core.scraper import search_actress

        ids = ['SONE-100', 'SONE-101', 'SONE-102']
        results_map = {
            'SONE-100': {'number': 'SONE-100', 'title': 'Title 100', 'actors': ['三上悠亜']},
            'SONE-101': {'number': 'SONE-101', 'title': 'Title 101', 'actors': ['三上悠亜']},
            'SONE-102': {'number': 'SONE-102', 'title': 'Title 102', 'actors': ['三上悠亜']},
        }

        mock_scraper = make_mock_scraper_actress([ids])
        callback_calls = []

        def result_callback(slot, data):
            callback_calls.append((slot, data))

        # limit=3 ensures target_ids is exactly 3 items (no extra page fetching)
        with patch('core.scraper.JavBusScraper', return_value=mock_scraper), \
             patch('core.scraper.search_jav', side_effect=make_mock_search_jav(results_map)):
            search_actress('三上悠亜', limit=3, result_callback=result_callback)

        item_calls = [(s, d) for s, d in callback_calls if s >= 0]
        assert len(item_calls) == 3, f"Expected 3 item calls, got {len(item_calls)}: {item_calls}"

        for slot, data in item_calls:
            expected_number = ids[slot]
            assert data['number'] == expected_number, (
                f"Slot {slot} should be {expected_number}, got {data['number']}"
            )

    def test_javdb_fallback_no_seed(self, make_mock_search_jav):
        """JavDB fallback 路徑 (JavBus 找不到) 不應呼叫 result_callback"""
        from core.scraper import search_actress

        callback_calls = []

        def result_callback(slot, data):
            callback_calls.append((slot, data))

        # JavBusScraper returns empty list — triggers JavDB fallback
        mock_scraper = make_mock_scraper_actress([[]])

        mock_db_scraper = MagicMock()
        mock_video = MagicMock()
        mock_video.to_legacy_dict.return_value = {'number': 'SONE-100', 'actors': ['三上悠亜']}
        mock_db_scraper.search_by_keyword.return_value = [mock_video]

        with patch('core.scraper.JavBusScraper', return_value=mock_scraper), \
             patch('core.scraper.JavDBScraper', return_value=mock_db_scraper):
            results = search_actress('三上悠亜', limit=20, result_callback=result_callback)

        assert callback_calls == [], f"JavDB fallback should not call result_callback, got {callback_calls}"


# ============ smart_search result_callback 透傳測試 ============

class TestSmartSearchResultCallback:
    """測試 smart_search() 的 result_callback 透傳行為"""

    def test_result_callback_passthrough_actress_mode(self, make_mock_search_jav):
        """smart_search 在 actress 模式下應透傳 result_callback 給 search_actress"""
        from core.scraper import smart_search

        received_callbacks = {}

        def mock_search_actress(name, limit=20, offset=0, status_callback=None, result_callback=None, **kwargs):
            received_callbacks['actress_callback'] = result_callback
            return [{'number': 'SONE-100', 'actors': ['三上悠亜'], '_mode': 'actress'}]

        my_callback = MagicMock()

        with patch('core.scraper.search_actress', side_effect=mock_search_actress), \
             patch('core.scraper.is_number_format', return_value=False), \
             patch('core.scraper.is_partial_number', return_value=False), \
             patch('core.scraper.is_prefix_only', return_value=False):
            smart_search('三上悠亜', result_callback=my_callback)

        assert received_callbacks.get('actress_callback') is my_callback, \
            "smart_search should pass result_callback to search_actress"

    def test_result_callback_passthrough_prefix_mode(self, make_mock_search_jav):
        """smart_search 在 prefix 模式下應透傳 result_callback 給 search_prefix"""
        from core.scraper import smart_search

        received_callbacks = {}

        def mock_search_prefix(prefix, limit=20, offset=0, status_callback=None, result_callback=None, **kwargs):
            received_callbacks['prefix_callback'] = result_callback
            return [{'number': 'SONE-100', '_mode': 'prefix'}]

        my_callback = MagicMock()

        with patch('core.scraper.search_prefix', side_effect=mock_search_prefix), \
             patch('core.scraper.is_number_format', return_value=False), \
             patch('core.scraper.is_partial_number', return_value=False), \
             patch('core.scraper.is_prefix_only', return_value=True):
            smart_search('SONE', result_callback=my_callback)

        assert received_callbacks.get('prefix_callback') is my_callback, \
            "smart_search should pass result_callback to search_prefix"

    def test_result_callback_not_passed_to_exact_mode(self, make_mock_search_jav):
        """exact 搜尋模式下 result_callback 不應影響（callback 不被呼叫）"""
        from core.scraper import smart_search

        callback_calls = []

        def my_callback(slot, data):
            callback_calls.append((slot, data))

        mock_result = {'number': 'SONE-100', 'title': 'Title', '_mode': 'exact'}

        with patch('core.scraper.is_number_format', return_value=True), \
             patch('core.scraper.normalize_number', return_value='SONE-100'), \
             patch('core.scraper.get_all_variant_ids', return_value=[]), \
             patch('core.scraper.search_jav', return_value=mock_result):
            results = smart_search('SONE-100', result_callback=my_callback)

        assert callback_calls == [], \
            f"result_callback should not be called in exact mode, got {callback_calls}"

    def test_result_callback_none_default_smart_search(self, make_mock_search_jav):
        """smart_search result_callback=None 不應改變行為"""
        from core.scraper import smart_search

        mock_result = {'number': 'SONE-100', 'title': 'Title', '_mode': 'exact'}

        with patch('core.scraper.is_number_format', return_value=True), \
             patch('core.scraper.normalize_number', return_value='SONE-100'), \
             patch('core.scraper.get_all_variant_ids', return_value=[]), \
             patch('core.scraper.search_jav', return_value=mock_result):
            # No result_callback — should not raise
            results = smart_search('SONE-100')
            assert isinstance(results, list)

    def test_smart_search_prefix_fallback_does_not_pass_callback(self, make_mock_search_jav):
        """prefix→actress fallback 時，actress call 不應收到 result_callback（避免 stale seed）"""
        from core.scraper import smart_search

        actress_received_callback = {}

        def mock_search_prefix(prefix, limit=20, offset=0, status_callback=None, result_callback=None, **kwargs):
            # Prefix search returns empty → triggers fallback to actress
            return []

        def mock_search_actress(name, limit=20, offset=0, status_callback=None, result_callback=None, **kwargs):
            actress_received_callback['callback'] = result_callback
            return [{'number': 'SONE-100', 'actors': ['三上悠亜'], '_mode': 'actress'}]

        my_callback = MagicMock()

        with patch('core.scraper.search_prefix', side_effect=mock_search_prefix), \
             patch('core.scraper.search_actress', side_effect=mock_search_actress), \
             patch('core.scraper.is_number_format', return_value=False), \
             patch('core.scraper.is_partial_number', return_value=False), \
             patch('core.scraper.is_prefix_only', return_value=True):
            smart_search('SONE', result_callback=my_callback)

        assert actress_received_callback.get('callback') is None, \
            "prefix→actress fallback must NOT pass result_callback to search_actress " \
            f"(got {actress_received_callback.get('callback')})"

    def test_smart_search_passes_result_callback_to_actress_direct(self, make_mock_search_jav):
        """smart_search 在 actress 模式下（非 fallback）應透傳 result_callback 給 search_actress"""
        from core.scraper import smart_search

        received_callbacks = {}

        def mock_search_actress(name, limit=20, offset=0, status_callback=None, result_callback=None, **kwargs):
            received_callbacks['actress_callback'] = result_callback
            return [{'number': 'SONE-100', 'actors': ['三上悠亜'], '_mode': 'actress'}]

        my_callback = MagicMock()

        # actress mode: is_prefix_only=False, is_number_format=False, is_partial_number=False
        with patch('core.scraper.search_actress', side_effect=mock_search_actress), \
             patch('core.scraper.is_number_format', return_value=False), \
             patch('core.scraper.is_partial_number', return_value=False), \
             patch('core.scraper.is_prefix_only', return_value=False):
            smart_search('三上悠亜', result_callback=my_callback)

        assert received_callbacks.get('actress_callback') is my_callback, \
            "Direct actress mode must pass result_callback to search_actress"


# ============ discovery_only 參數測試 ============

class TestDiscoveryOnly:
    """測試 discovery_only=True 讓各子函數跳過 Step 2 enrichment"""

    def test_search_prefix_discovery_only_returns_ids_no_enrich(self, make_mock_search_jav):
        """discovery_only=True: search_prefix 只做 get_ids_from_search，不呼叫 search_jav"""
        from core.scraper import search_prefix

        ids = ['SONE-100', 'SONE-101', 'SONE-102']
        mock_scraper = make_mock_scraper_prefix(ids)
        search_jav_calls = []

        def fake_search_jav(num, source='javbus'):
            search_jav_calls.append(num)
            return {'number': num, 'title': f'Title {num}'}

        with patch('core.scraper.JavBusScraper', return_value=mock_scraper), \
             patch('core.scraper.search_jav', side_effect=fake_search_jav):
            results = search_prefix('SONE', limit=20, discovery_only=True)

        assert search_jav_calls == [], \
            f"discovery_only=True: search_jav should not be called, but was called for {search_jav_calls}"
        assert len(results) == 3
        for r in results:
            assert 'number' in r
            assert r.get('title', '') == ''  # title is empty in discovery mode

    def test_search_prefix_discovery_only_false_still_enriches(self, make_mock_search_jav):
        """discovery_only=False（預設）: search_prefix 仍呼叫 search_jav 做 enrichment"""
        from core.scraper import search_prefix

        ids = ['SONE-100', 'SONE-101']
        results_map = {
            'SONE-100': {'number': 'SONE-100', 'title': 'Title 100'},
            'SONE-101': {'number': 'SONE-101', 'title': 'Title 101'},
        }
        mock_scraper = make_mock_scraper_prefix(ids)

        with patch('core.scraper.JavBusScraper', return_value=mock_scraper), \
             patch('core.scraper.search_jav', side_effect=make_mock_search_jav(results_map)) as mock_jav:
            results = search_prefix('SONE', limit=20, discovery_only=False)

        assert mock_jav.call_count == 2, \
            f"search_jav should be called twice (once per ID), got {mock_jav.call_count}"

    def test_search_actress_discovery_only_returns_ids_no_enrich(self, make_mock_search_jav):
        """discovery_only=True: search_actress 只做 get_ids_from_search，不呼叫 search_jav"""
        from core.scraper import search_actress

        ids = ['SONE-100', 'SONE-101']
        mock_scraper = make_mock_scraper_actress([ids])
        search_jav_calls = []

        def fake_search_jav(num, source='javbus'):
            search_jav_calls.append(num)
            return {'number': num, 'title': f'Title {num}'}

        with patch('core.scraper.JavBusScraper', return_value=mock_scraper), \
             patch('core.scraper.search_jav', side_effect=fake_search_jav):
            results = search_actress('三上悠亜', limit=20, discovery_only=True)

        assert search_jav_calls == [], \
            f"discovery_only=True: search_jav should not be called, got {search_jav_calls}"
        assert len(results) == 2
        for r in results:
            assert 'number' in r

    def test_search_partial_discovery_only_returns_candidates_no_enrich(self):
        """discovery_only=True: search_partial 只展開候選番號，不呼叫 search_jav"""
        from core.scraper import search_partial

        candidates = ['SONE-100', 'SONE-101']
        search_jav_calls = []

        def fake_search_jav(num, source='javbus'):
            search_jav_calls.append(num)
            return {'number': num, 'title': f'Title {num}'}

        with patch('core.scraper.expand_partial_number', return_value=candidates), \
             patch('core.scraper.search_jav', side_effect=fake_search_jav):
            results = search_partial('SONE-10', discovery_only=True)

        assert search_jav_calls == [], \
            f"discovery_only=True: search_jav should not be called, got {search_jav_calls}"
        assert len(results) == 2
        for r in results:
            assert 'number' in r

    def test_smart_search_passes_discovery_only_to_actress(self, make_mock_search_jav):
        """smart_search(discovery_only=True) 在 actress 模式下傳遞給 search_actress"""
        from core.scraper import smart_search

        received = {}

        def mock_search_actress(name, limit=20, offset=0, status_callback=None,
                                 result_callback=None, discovery_only=False, **kwargs):
            received['discovery_only'] = discovery_only
            return [{'number': 'SONE-100', '_mode': 'actress'}]

        with patch('core.scraper.search_actress', side_effect=mock_search_actress), \
             patch('core.scraper.is_number_format', return_value=False), \
             patch('core.scraper.is_partial_number', return_value=False), \
             patch('core.scraper.is_prefix_only', return_value=False):
            smart_search('三上悠亜', discovery_only=True)

        assert received.get('discovery_only') is True, \
            "smart_search should pass discovery_only=True to search_actress"

    def test_smart_search_passes_discovery_only_to_prefix(self, make_mock_search_jav):
        """smart_search(discovery_only=True) 在 prefix 模式下傳遞給 search_prefix"""
        from core.scraper import smart_search

        received = {}

        def mock_search_prefix(prefix, limit=20, offset=0, status_callback=None,
                                result_callback=None, discovery_only=False):
            received['discovery_only'] = discovery_only
            return [{'number': 'SONE-100', '_mode': 'prefix'}]

        with patch('core.scraper.search_prefix', side_effect=mock_search_prefix), \
             patch('core.scraper.is_number_format', return_value=False), \
             patch('core.scraper.is_partial_number', return_value=False), \
             patch('core.scraper.is_prefix_only', return_value=True):
            smart_search('SONE', discovery_only=True)

        assert received.get('discovery_only') is True, \
            "smart_search should pass discovery_only=True to search_prefix"

    def test_smart_search_exact_ignores_discovery_only(self, make_mock_search_jav):
        """smart_search(discovery_only=True) 在 exact 模式下忽略 discovery_only"""
        from core.scraper import smart_search

        mock_result = {'number': 'SONE-100', 'title': 'Title', '_mode': 'exact'}

        with patch('core.scraper.is_number_format', return_value=True), \
             patch('core.scraper.normalize_number', return_value='SONE-100'), \
             patch('core.scraper.get_all_variant_ids', return_value=[]), \
             patch('core.scraper.search_jav', return_value=mock_result):
            results = smart_search('SONE-100', discovery_only=True)

        # exact mode should still return a result (not empty)
        assert len(results) == 1
        assert results[0]['number'] == 'SONE-100'


# ============ Rule 4b: JavBus variant probe gating (CD-61-19) ============

class TestRule4bVariantProbeGating:
    """JavBus variant probe（get_all_variant_ids）僅在 'javbus' ∈ get_enabled_source_ids() 時觸發。

    JavBus 停用 → 跳過 variant 探查 + 不發 ('javbus','searching') status（靜默降級），
    落一般 search_jav。JavBus 啟用 → variant 探查照舊。
    """

    def test_javbus_disabled_skips_variant_probe(self, make_mock_search_jav):
        """JavBus 不在 Active Row → get_all_variant_ids 不被呼叫，無 javbus status，落一般 search_jav"""
        from core.scraper import smart_search

        status_calls = []

        def status_cb(source, status):
            status_calls.append((source, status))

        mock_result = {'number': 'SONE-100', 'title': 'Title'}
        mock_variant = MagicMock(return_value=['SONE-100-variant'])

        with patch('core.scraper.is_number_format', return_value=True), \
             patch('core.scraper.normalize_number', return_value='SONE-100'), \
             patch('core.scraper.get_enabled_source_ids', return_value=['jav321', 'javdb']), \
             patch('core.scraper.get_all_variant_ids', mock_variant), \
             patch('core.scraper.search_jav', return_value=mock_result):
            results = smart_search('SONE-100', status_callback=status_cb)

        # variant probe 不觸發
        mock_variant.assert_not_called()
        # callback 序列不含 javbus
        assert ('javbus', 'searching') not in status_calls, \
            f"JavBus disabled but status sequence contains javbus: {status_calls}"
        # 仍落一般 search_jav 取得結果
        assert len(results) == 1
        assert results[0]['number'] == 'SONE-100'

    def test_javbus_enabled_fires_variant_probe(self, make_mock_search_jav):
        """JavBus 在 Active Row → get_all_variant_ids 被呼叫，發出 javbus status"""
        from core.scraper import smart_search

        status_calls = []

        def status_cb(source, status):
            status_calls.append((source, status))

        mock_result = {'number': 'SONE-100', 'title': 'Title'}
        mock_variant = MagicMock(return_value=[])

        with patch('core.scraper.is_number_format', return_value=True), \
             patch('core.scraper.normalize_number', return_value='SONE-100'), \
             patch('core.scraper.get_enabled_source_ids', return_value=['javbus', 'jav321']), \
             patch('core.scraper.get_all_variant_ids', mock_variant), \
             patch('core.scraper.search_jav', return_value=mock_result):
            results = smart_search('SONE-100', status_callback=status_cb)

        # variant probe 觸發
        mock_variant.assert_called_once()
        # callback 序列含 javbus
        assert ('javbus', 'searching') in status_calls, \
            f"JavBus enabled but status sequence missing javbus: {status_calls}"
        assert len(results) == 1

    def test_javbus_enabled_variant_hit_returns_variant_result(self, make_mock_search_jav):
        """JavBus 啟用且找到變體 → 走 search_by_variant_id，結果帶 _all_variant_ids"""
        from core.scraper import smart_search

        variant_result = {'number': 'SONE-100', 'title': 'Variant'}

        with patch('core.scraper.is_number_format', return_value=True), \
             patch('core.scraper.normalize_number', return_value='SONE-100'), \
             patch('core.scraper.get_enabled_source_ids', return_value=['javbus']), \
             patch('core.scraper.get_all_variant_ids', return_value=['SONE-100', 'SONE-101']), \
             patch('core.scraper.search_by_variant_id', return_value=variant_result):
            results = smart_search('SONE-100')

        assert len(results) == 1
        assert results[0].get('_all_variant_ids') == ['SONE-100', 'SONE-101']

    def test_javbus_disabled_does_not_use_variant_id_path(self, make_mock_search_jav):
        """JavBus 停用即使「會有變體」也不走 search_by_variant_id（probe 根本沒跑）"""
        from core.scraper import smart_search

        mock_result = {'number': 'SONE-100', 'title': 'Title'}
        mock_variant = MagicMock(return_value=['SONE-100-v'])
        mock_by_variant = MagicMock(return_value={'number': 'SONE-100', '_all_variant_ids': ['x']})

        with patch('core.scraper.is_number_format', return_value=True), \
             patch('core.scraper.normalize_number', return_value='SONE-100'), \
             patch('core.scraper.get_enabled_source_ids', return_value=['avsox']), \
             patch('core.scraper.get_all_variant_ids', mock_variant), \
             patch('core.scraper.search_by_variant_id', mock_by_variant), \
             patch('core.scraper.search_jav', return_value=mock_result):
            results = smart_search('SONE-100')

        mock_variant.assert_not_called()
        mock_by_variant.assert_not_called()
        # 結果來自一般 search_jav，無 _all_variant_ids
        assert len(results) == 1
        assert '_all_variant_ids' not in results[0]


# ============ Disabled source absent from auto-search routing (EC-6) ============

class TestDisabledSourceRouting:
    """停用 / 不在 Active Row 的來源不出現在自動搜尋 fan-out 序列；全關仍不 crash（EC-8）。"""

    @staticmethod
    def _instantiated_scraper_mocks():
        """回傳一組 (patch context managers, searched tracker) — 每個 scraper class
        被 patch 成 mock：instance.search() 記錄被搜尋的來源並回 None。

        以 .search() 而非建構為準：normalize_number() 會建立一個 JavBusScraper 但不呼叫
        .search()，用建構計數會誤報 javbus。"""
        instantiated = []

        def make_cls(name):
            def factory(*args, **kwargs):
                inst = MagicMock()
                def _search(*a, **k):
                    instantiated.append(name)
                    return None
                inst.search.side_effect = _search
                return inst
            return factory

        cms = [
            patch('core.scraper.JavBusScraper', side_effect=make_cls('javbus')),
            patch('core.scraper.JAV321Scraper', side_effect=make_cls('jav321')),
            patch('core.scraper.JavDBScraper', side_effect=make_cls('javdb')),
            patch('core.scraper.D2PassScraper', side_effect=make_cls('d2pass')),
            patch('core.scraper.HEYZOScraper', side_effect=make_cls('heyzo')),
            patch('core.scraper.FC2Scraper', side_effect=make_cls('fc2')),
            patch('core.scraper.AVSOXScraper', side_effect=make_cls('avsox')),
            patch('core.scraper.DMMScraper', side_effect=make_cls('dmm')),
        ]
        return cms, instantiated

    def test_disabled_source_absent_from_auto_fanout(self, make_mock_search_jav):
        """auto fan-out 只跑 get_enabled_source_ids() 子集 — 停用來源不被建立 / 搜尋"""
        from core.scraper import search_jav
        from contextlib import ExitStack

        cms, instantiated = self._instantiated_scraper_mocks()
        with ExitStack() as stack:
            for cm in cms:
                stack.enter_context(cm)
            # 只啟用 jav321 + javdb（停用 javbus / dmm 等）
            stack.enter_context(
                patch('core.scraper.get_enabled_source_ids', return_value=['jav321', 'javdb'])
            )
            result = search_jav('SONE-100', source='auto')

        assert 'javbus' not in instantiated, \
            f"disabled javbus should not be instantiated, got {instantiated}"
        assert 'dmm' not in instantiated
        assert set(instantiated) <= {'jav321', 'javdb'}

    def test_all_disabled_auto_returns_none_no_crash(self, make_mock_search_jav):
        """全關（0 enabled）→ search_jav('auto') 回 None，不 crash（EC-8）"""
        from core.scraper import search_jav
        from contextlib import ExitStack

        cms, instantiated = self._instantiated_scraper_mocks()
        with ExitStack() as stack:
            for cm in cms:
                stack.enter_context(cm)
            stack.enter_context(
                patch('core.scraper.get_enabled_source_ids', return_value=[])
            )
            result = search_jav('SONE-100', source='auto')

        assert result is None
        assert instantiated == [], "no scraper should be instantiated when all disabled"

    def test_all_disabled_uncensored_fallback_still_works(self, make_mock_search_jav):
        """全關但 Rule 2 無碼 always-on：FC2 番號仍透過 _get_uncensored_sources 硬寫清單搜尋"""
        from core.scraper import smart_search

        searched = []
        fc2_result = {'number': 'FC2-PPV-123', 'title': 'FC2'}

        def fake_search_jav(num, source='auto', proxy_url='', primary_source='javbus', javbus_lang=None):
            searched.append(source)
            return fc2_result if source == 'fc2' else None

        # 全關 enabled，但 Rule 2 走 _get_uncensored_sources（builtin-only 硬寫）不受 enabled 影響
        with patch('core.scraper.get_enabled_source_ids', return_value=[]), \
             patch('core.scraper.search_jav', side_effect=fake_search_jav):
            results = smart_search('FC2-PPV-123', uncensored_mode=True)

        # Rule 2 always-on：fc2 仍被搜尋（不被 enabled filter 跳過）
        assert 'fc2' in searched, \
            f"uncensored Rule 2 fallback should search fc2 even when all disabled, got {searched}"
        assert len(results) == 1
