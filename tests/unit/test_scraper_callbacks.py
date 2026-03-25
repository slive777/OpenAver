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

        def mock_search_actress(name, limit=20, offset=0, status_callback=None, result_callback=None):
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

        def mock_search_prefix(prefix, limit=20, offset=0, status_callback=None, result_callback=None):
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

        def mock_search_prefix(prefix, limit=20, offset=0, status_callback=None, result_callback=None):
            # Prefix search returns empty → triggers fallback to actress
            return []

        def mock_search_actress(name, limit=20, offset=0, status_callback=None, result_callback=None):
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

        def mock_search_actress(name, limit=20, offset=0, status_callback=None, result_callback=None):
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
