"""
test_scraper_partial.py - search_partial() callback 行為單元測試

測試範圍：
- search_partial() seed callback (-1, candidates) 正確性
- search_partial() result-item callback (idx, data) 正確性
- 向後相容性（result_callback=None 不改變行為）
- slot mapping 確定性（as_completed 順序不影響 idx 對位）
- smart_search() partial 分支透傳 result_callback / status_callback
"""

import pytest
from unittest.mock import patch, MagicMock


# ============ Helpers ============

def make_mock_search_jav(results_map):
    """Return mock search_jav that maps num -> result dict."""
    def mock_fn(num, source='javbus'):
        return results_map.get(num)
    return mock_fn


# ============ search_partial result_callback tests ============

class TestSearchPartialCallback:
    """Tests for search_partial() callback behaviour."""

    def test_search_partial_calls_seed_callback(self):
        """seed callback (-1, candidates) should be called exactly once."""
        from core.scraper import search_partial

        candidates = ['IPZZ-030', 'IPZZ-031']
        results_map = {
            'IPZZ-030': {'number': 'IPZZ-030', 'title': 'Title 030'},
            'IPZZ-031': {'number': 'IPZZ-031', 'title': 'Title 031'},
        }

        callback_calls = []

        def result_callback(slot, data):
            callback_calls.append((slot, data))

        with patch('core.scraper.expand_partial_number', return_value=candidates), \
             patch('core.scraper.search_jav', side_effect=make_mock_search_jav(results_map)), \
             patch('core.scraper.time.sleep'):
            search_partial('IPZZ-03', result_callback=result_callback)

        seed_calls = [(s, d) for s, d in callback_calls if s == -1]
        assert len(seed_calls) == 1, f"Expected 1 seed call, got {len(seed_calls)}"

        seed_slot, seed_data = seed_calls[0]
        assert seed_slot == -1
        assert seed_data == ['IPZZ-030', 'IPZZ-031']

    def test_search_partial_calls_result_item_callback(self):
        """Each successful result should trigger result_callback(idx, data) with idx >= 0."""
        from core.scraper import search_partial

        candidates = ['IPZZ-030', 'IPZZ-031']
        results_map = {
            'IPZZ-030': {'number': 'IPZZ-030', 'title': 'Title 030'},
            'IPZZ-031': {'number': 'IPZZ-031', 'title': 'Title 031'},
        }

        callback_calls = []

        def result_callback(slot, data):
            callback_calls.append((slot, data))

        with patch('core.scraper.expand_partial_number', return_value=candidates), \
             patch('core.scraper.search_jav', side_effect=make_mock_search_jav(results_map)), \
             patch('core.scraper.time.sleep'):
            search_partial('IPZZ-03', result_callback=result_callback)

        item_calls = [(s, d) for s, d in callback_calls if s >= 0]
        assert len(item_calls) == 2, f"Expected 2 item calls, got {len(item_calls)}"

        for slot, data in item_calls:
            assert slot >= 0, f"result-item slot should be >= 0, got {slot}"
            assert data is not None, "result-item data should not be None"
            assert data.get('title'), "result-item data should have a title"

    def test_search_partial_no_callback_backward_compat(self):
        """Calling search_partial without callbacks should not raise and should return a list."""
        from core.scraper import search_partial

        candidates = ['IPZZ-030', 'IPZZ-031']
        results_map = {
            'IPZZ-030': {'number': 'IPZZ-030', 'title': 'Title 030'},
            'IPZZ-031': {'number': 'IPZZ-031', 'title': 'Title 031'},
        }

        with patch('core.scraper.expand_partial_number', return_value=candidates), \
             patch('core.scraper.search_jav', side_effect=make_mock_search_jav(results_map)), \
             patch('core.scraper.time.sleep'):
            results = search_partial('IPZZ-03')

        assert isinstance(results, list)
        assert len(results) == 2

    def test_search_partial_deterministic_slot_mapping(self):
        """idx in result-item callback must correspond to candidates[idx], regardless of as_completed order."""
        from core.scraper import search_partial

        candidates = ['IPZZ-031', 'IPZZ-032']
        results_map = {
            'IPZZ-031': {'number': 'IPZZ-031', 'title': 'Title 031'},
            'IPZZ-032': {'number': 'IPZZ-032', 'title': 'Title 032'},
        }

        callback_calls = []

        def result_callback(slot, data):
            callback_calls.append((slot, data))

        with patch('core.scraper.expand_partial_number', return_value=candidates), \
             patch('core.scraper.search_jav', side_effect=make_mock_search_jav(results_map)), \
             patch('core.scraper.time.sleep'):
            search_partial('IPZZ-03', result_callback=result_callback)

        # Verify seed received the full candidates list
        seed_calls = [(s, d) for s, d in callback_calls if s == -1]
        assert len(seed_calls) == 1
        assert seed_calls[0][1] == ['IPZZ-031', 'IPZZ-032']

        # Verify result-item idx set covers all slots
        item_calls = [(s, d) for s, d in callback_calls if s >= 0]
        idx_set = {s for s, d in item_calls}
        assert idx_set == {0, 1}, f"Expected idx set {{0, 1}}, got {idx_set}"

        # Verify each (idx, data) maps to the correct candidate
        for idx, data in item_calls:
            expected_number = candidates[idx]
            assert data['number'] == expected_number, (
                f"Slot {idx} should correspond to {expected_number}, "
                f"but got {data['number']}"
            )


# ============ smart_search partial passthrough test ============

class TestSmartSearchPartialPassthrough:
    """Test that smart_search() passes callbacks to search_partial()."""

    def test_smart_search_partial_passes_callback(self):
        """smart_search in partial mode should pass result_callback and status_callback to search_partial."""
        from core.scraper import smart_search

        received_callbacks = {}

        def mock_search_partial(partial, status_callback=None, result_callback=None):
            received_callbacks['result_callback'] = result_callback
            received_callbacks['status_callback'] = status_callback
            return []

        my_cb = MagicMock()
        my_status_cb = MagicMock()

        with patch('core.scraper.search_partial', side_effect=mock_search_partial), \
             patch('core.scraper.is_number_format', return_value=False), \
             patch('core.scraper.is_partial_number', return_value=True), \
             patch('core.scraper.is_prefix_only', return_value=False):
            smart_search('ipzz03', result_callback=my_cb, status_callback=my_status_cb)

        assert received_callbacks.get('result_callback') is my_cb, \
            "smart_search should pass result_callback to search_partial"
        assert received_callbacks.get('status_callback') is my_status_cb, \
            "smart_search should pass status_callback to search_partial"
