"""
test_api_search.py - 搜尋 API 整合測試

使用 mocker.patch Mock 爬蟲回應，驗證搜尋 API 行為。
"""

import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock, call


def load_fixture(filename: str) -> dict:
    """載入 Mock JSON fixture"""
    fixture_path = Path(__file__).parent.parent / 'fixtures' / filename
    with open(fixture_path, 'r', encoding='utf-8') as f:
        return json.load(f)


# ============ 番號搜尋 ============

class TestSearchByNumber:
    """測試番號搜尋 API"""

    def test_search_exact_number_success(self, client, mocker):
        """精確番號搜尋成功"""
        mock_data = load_fixture('responses/javbus/SONE-103.json')
        mocker.patch('web.routers.search.search_jav', return_value=mock_data)

        response = client.get('/api/search', params={'q': 'SONE-103', 'mode': 'exact'})

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['data'][0]['number'] == 'SONE-103'
        assert data['total'] == 1

    def test_search_auto_mode(self, client, mocker):
        """自動模式搜尋"""
        mock_data = load_fixture('responses/javbus/SONE-103.json')
        mocker.patch('web.routers.search.smart_search', return_value=[mock_data])

        response = client.get('/api/search', params={'q': 'SONE-103'})

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert len(data['data']) >= 1

    def test_search_no_results(self, client, mocker):
        """搜尋無結果"""
        mocker.patch('web.routers.search.smart_search', return_value=[])

        response = client.get('/api/search', params={'q': 'FAKE-999'})

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is False
        assert '找不到' in data['error']
        assert data['total'] == 0


class TestSearchValidation:
    """測試搜尋輸入驗證"""

    def test_search_empty_query(self, client):
        """空查詢應返回錯誤"""
        response = client.get('/api/search', params={'q': ''})

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is False
        assert '有效' in data['error'] or len(data['data']) == 0

    def test_search_single_char(self, client):
        """單字元查詢應返回錯誤"""
        response = client.get('/api/search', params={'q': 'A'})

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is False

    def test_search_whitespace_only(self, client):
        """純空白查詢應返回錯誤"""
        response = client.get('/api/search', params={'q': '   '})

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is False


class TestSearchModes:
    """測試不同搜尋模式"""

    def test_search_partial_mode(self, client, mocker):
        """局部番號搜尋模式"""
        mock_results = [
            {'number': 'SONE-101', 'title': 'Title 1'},
            {'number': 'SONE-102', 'title': 'Title 2'},
            {'number': 'SONE-103', 'title': 'Title 3'},
        ]
        mocker.patch('web.routers.search.search_partial', return_value=mock_results)

        response = client.get('/api/search', params={'q': 'SONE-10', 'mode': 'partial'})

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert len(data['data']) >= 1

    def test_search_actress_mode(self, client, mocker):
        """女優搜尋模式"""
        mock_results = load_fixture('responses/javdb/actress_search.json')
        mocker.patch('web.routers.search.search_actress', return_value=mock_results)

        response = client.get('/api/search', params={'q': '石川澪', 'mode': 'actress'})

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert len(data['data']) >= 1


class TestSearchPagination:
    """測試搜尋分頁"""

    def test_search_with_limit(self, client, mocker):
        """分頁 limit 參數"""
        mock_results = [{'number': f'SONE-{i}', 'title': f'Title {i}'} for i in range(10)]
        mocker.patch('web.routers.search.smart_search', return_value=mock_results[:5])

        response = client.get('/api/search', params={'q': 'SONE', 'limit': 5})

        assert response.status_code == 200
        data = response.json()
        assert data['total'] <= 5

    def test_search_with_offset(self, client, mocker):
        """分頁 offset 參數"""
        mock_results = [{'number': f'SONE-{i}', 'title': f'Title {i}'} for i in range(100, 110)]
        mocker.patch('web.routers.search.smart_search', return_value=mock_results)

        response = client.get('/api/search', params={'q': 'SONE', 'limit': 5, 'offset': 5})

        assert response.status_code == 200
        data = response.json()
        assert 'offset' in data


class TestSearchSources:
    """搜尋來源 API 測試"""

    def test_get_sources(self, client):
        """測試取得搜尋來源"""
        response = client.get("/api/search/sources")
        assert response.status_code == 200
        data = response.json()

        # 檢查 sources 存在且內容合理
        assert "sources" in data
        assert isinstance(data["sources"], list)
        assert len(data["sources"]) >= 2  # 至少有 auto 和特定爬蟲來源
        assert all(isinstance(s, dict) for s in data["sources"])
        assert all("id" in s and "name" in s for s in data["sources"])

        # 檢查 auto 選項存在
        source_ids = [s["id"] for s in data["sources"]]
        assert "auto" in source_ids

    def test_sources_has_order(self, client):
        """測試 sources 包含 order 欄位"""
        response = client.get("/api/search/sources")
        assert response.status_code == 200
        data = response.json()

        # 檢查 order 存在且內容合理
        assert "order" in data
        assert isinstance(data["order"], list)
        assert len(data["order"]) >= 2
        assert all(isinstance(s, str) for s in data["order"])

        # 檢查順序包含基本來源
        assert "javbus" in data["order"]
        assert "jav321" in data["order"]

    def test_sources_order_matches_sources(self, client):
        """測試 order 與 sources 一致"""
        response = client.get("/api/search/sources")
        data = response.json()

        # order 中的所有來源都應該在 sources 中（除了 auto）
        source_ids = [s["id"] for s in data["sources"] if s["id"] != "auto"]
        for source in data["order"]:
            assert source in source_ids


# ============ SSE Stream 協議測試 ============

class TestSearchStreamSSE:
    """測試 /api/search/stream SSE 協議行為"""

    def test_exact_mode_sends_result_event(self, client, parse_sse_events):
        """exact 番號搜尋應送傳統 result event，不受 seed/result-item 影響（C8）"""
        mock_result = {
            'number': 'SSIS-816',
            'title': 'Some Title',
            'actors': ['三上悠亜'],
            '_mode': 'exact'
        }

        def mock_smart_search(q, limit=20, offset=0, status_callback=None,
                              result_callback=None, **kwargs):
            # exact mode: status_callback only, no result_callback calls
            if status_callback:
                status_callback('javbus', 'searching')
                status_callback('done', 'found:1')
            return [mock_result]

        with patch('web.routers.search.smart_search', side_effect=mock_smart_search):
            response = client.get('/api/search/stream?q=SSIS-816')

        events = parse_sse_events(response.text)
        result_events = [e for e in events if e.get('type') == 'result']

        assert len(result_events) == 1, f"Exact mode should have exactly 1 result event, got {result_events}"
        result_event = result_events[0]
        assert result_event['success'] is True
        assert 'data' in result_event
        assert result_event['total'] == 1

        # Must NOT have seed or result-item or result-complete for exact mode
        assert not any(e.get('type') == 'seed' for e in events), \
            "Exact mode should not send seed event"
        assert not any(e.get('type') == 'result-item' for e in events), \
            "Exact mode should not send result-item event"
        assert not any(e.get('type') == 'result-complete' for e in events), \
            "Exact mode should not send result-complete event"

    @pytest.fixture
    def actress_mode_events(self, client, parse_sse_events):
        """共用 fixture：執行 actress 模式的 smart_search 並回傳解析後的 SSE events"""
        ids = ['SONE-100', 'SONE-101', 'SONE-102']
        items = {
            'SONE-100': {'number': 'SONE-100', 'title': 'Title 100', 'actors': ['三上悠亜']},
            'SONE-101': {'number': 'SONE-101', 'title': 'Title 101', 'actors': ['三上悠亜']},
            'SONE-102': {'number': 'SONE-102', 'title': 'Title 102', 'actors': ['三上悠亜']},
        }

        def mock_smart_search(q, limit=20, offset=0, status_callback=None,
                              result_callback=None, **kwargs):
            if status_callback:
                status_callback('javbus', 'searching')
                status_callback('javbus', f'found:{len(ids)}')
            if result_callback:
                result_callback(-1, ids)
            for idx, num in enumerate(ids):
                if result_callback:
                    result_callback(idx, items[num])
            if status_callback:
                status_callback('done', f'found:{len(ids)}')
            return list(items.values())

        with patch('web.routers.search.smart_search', side_effect=mock_smart_search):
            response = client.get('/api/search/stream?q=三上悠亜')

        events = parse_sse_events(response.text)
        return events, ids

    def test_actress_mode_sends_seed_event(self, actress_mode_events):
        """actress 模式下 SSE 應送出 seed event"""
        events, ids = actress_mode_events
        seed_events = [e for e in events if e.get('type') == 'seed']
        assert len(seed_events) == 1, f"Expected 1 seed event, got {seed_events}"
        seed_event = seed_events[0]
        assert seed_event['total'] == 3
        assert set(seed_event['slots']) == set(ids)

    def test_actress_mode_sends_result_items(self, actress_mode_events):
        """actress 模式下 SSE 應送出 N 個 result-item"""
        events, ids = actress_mode_events
        item_events = [e for e in events if e.get('type') == 'result-item']
        assert len(item_events) == 3, f"Expected 3 result-item events, got {len(item_events)}"
        for item_event in item_events:
            assert 'slot' in item_event
            assert 'data' in item_event
            slot = item_event['slot']
            assert 0 <= slot < len(ids)
            assert item_event['data']['number'] == ids[slot]

    def test_actress_mode_sends_result_complete(self, actress_mode_events):
        """actress 模式下 SSE 應送出 result-complete event，含 merged_results 與 actress_profile"""
        events, _ = actress_mode_events
        complete_events = [e for e in events if e.get('type') == 'result-complete']
        assert len(complete_events) == 1, f"Expected 1 result-complete event, got {complete_events}"
        complete_event = complete_events[0]
        assert 'total' in complete_event
        assert 'has_more' in complete_event
        assert 'actress_profile' in complete_event
        assert complete_event['total'] == 3

    def test_actress_mode_sends_result_and_ordering(self, actress_mode_events):
        """actress 模式下 SSE 應送出 result event，且 result-complete 在 result 之前"""
        events, _ = actress_mode_events
        result_events = [e for e in events if e.get('type') == 'result']
        assert len(result_events) == 1
        result_event = result_events[0]
        assert result_event['success'] is True
        assert 'data' in result_event
        assert isinstance(result_event['data'], list)
        assert result_event['total'] == 3
        assert 'mode' in result_event

        complete_idx = next(i for i, e in enumerate(events) if e.get('type') == 'result-complete')
        result_idx = next(i for i, e in enumerate(events) if e.get('type') == 'result')
        assert complete_idx < result_idx, "result-complete must appear before result event in the stream"

    def test_javdb_fallback_sends_result_event(self, client, parse_sse_events):
        """JavDB fallback（no result_callback called）應走傳統 result event（C12）"""
        results = [
            {'number': 'SONE-100', 'actors': ['三上悠亜']},
            {'number': 'SONE-101', 'actors': ['三上悠亜']},
            {'number': 'SONE-102', 'actors': ['三上悠亜']},
        ]

        def mock_smart_search(q, limit=20, offset=0, status_callback=None,
                              result_callback=None, **kwargs):
            # JavDB path: result_callback is never called → sent_seed stays False
            if status_callback:
                status_callback('javdb', 'searching')
                status_callback('done', f'found:{len(results)}')
            return results

        with patch('web.routers.search.smart_search', side_effect=mock_smart_search):
            response = client.get('/api/search/stream?q=三上悠亜')

        events = parse_sse_events(response.text)

        # Should have traditional result event
        result_events = [e for e in events if e.get('type') == 'result']
        assert len(result_events) == 1, f"JavDB fallback should send traditional result event"
        result_event = result_events[0]
        assert result_event['success'] is True
        assert 'data' in result_event

        # Must NOT have seed or result-complete
        assert not any(e.get('type') == 'seed' for e in events), \
            "JavDB fallback should not send seed event"
        assert not any(e.get('type') == 'result-complete' for e in events), \
            "JavDB fallback should not send result-complete event"

    def test_double_seed_protection(self, client, parse_sse_events):
        """prefix→actress fallback 修正後：fallback 不傳 result_callback，只有一個 seed
        且最終 result event 包含正確資料"""
        ids1 = ['SONE-100', 'SONE-101']
        final_results = [{'number': 'SONE-100', 'title': 'T1'}, {'number': 'SONE-101', 'title': 'T2'}]

        def mock_smart_search(q, limit=20, offset=0, status_callback=None,
                              result_callback=None, **kwargs):
            # Real behavior after fix: prefix sends seed, fallback actress gets no callback
            if result_callback:
                result_callback(-1, ids1)  # only one seed (from prefix path)
                result_callback(0, final_results[0])
                result_callback(1, final_results[1])
            return final_results

        with patch('web.routers.search.smart_search', side_effect=mock_smart_search):
            response = client.get('/api/search/stream?q=SONE')

        events = parse_sse_events(response.text)

        # Exactly one seed event
        seed_events = [e for e in events if e.get('type') == 'seed']
        assert len(seed_events) == 1, \
            f"Only 1 seed should be sent after fix, got {len(seed_events)}"
        assert set(seed_events[0]['slots']) == set(ids1), \
            "Seed slots should be from prefix path"

        # MUST have traditional result event (always sent)
        result_events = [e for e in events if e.get('type') == 'result']
        assert len(result_events) == 1, \
            f"Must have exactly 1 result event, got {len(result_events)}"
        result_event = result_events[0]
        assert result_event['success'] is True
        assert result_event['total'] == 2

        # MUST have result-complete (since sent_seed=True)
        complete_events = [e for e in events if e.get('type') == 'result-complete']
        assert len(complete_events) == 1, \
            f"Must have result-complete when seed was sent, got {len(complete_events)}"

    def test_always_sends_result_event_with_incremental(self, client, parse_sse_events):
        """當 sent_seed=True 時，SSE 流必須包含 result-complete（前）和 result（後）兩個事件"""
        ids = ['IPZZ-100', 'IPZZ-101']
        items_list = [
            {'number': 'IPZZ-100', 'title': 'Title 100', 'actors': ['桜空もも']},
            {'number': 'IPZZ-101', 'title': 'Title 101', 'actors': ['桜空もも']},
        ]

        def mock_smart_search(q, limit=20, offset=0, status_callback=None,
                              result_callback=None, **kwargs):
            if result_callback:
                result_callback(-1, ids)  # send seed
                for idx, item in enumerate(items_list):
                    result_callback(idx, item)  # send result-items
            if status_callback:
                status_callback('done', f'found:{len(items_list)}')
            return items_list

        with patch('web.routers.search.smart_search', side_effect=mock_smart_search):
            response = client.get('/api/search/stream?q=IPZZ')

        events = parse_sse_events(response.text)
        event_types = [e.get('type') for e in events]

        # Both result-complete and result must be present
        assert 'result-complete' in event_types, \
            f"Stream must contain result-complete when seed was sent. Events: {event_types}"
        assert 'result' in event_types, \
            f"Stream must always contain result event. Events: {event_types}"

        # result-complete appears before result
        complete_idx = event_types.index('result-complete')
        result_idx = event_types.index('result')
        assert complete_idx < result_idx, \
            "result-complete must appear before result in the event stream"

        # result event has correct structure
        result_event = next(e for e in events if e.get('type') == 'result')
        assert 'success' in result_event
        assert 'data' in result_event
        assert isinstance(result_event['data'], list)
        assert 'total' in result_event
        assert 'mode' in result_event
        assert 'has_more' in result_event
        assert 'actress_profile' in result_event

    def test_result_complete_has_actress_profile_and_has_more(self, client, parse_sse_events):
        """result-complete event 應包含 actress_profile 和 has_more 欄位"""
        ids = ['SONE-100', 'SONE-101', 'SONE-102']
        items_list = [
            {'number': 'SONE-100', 'actors': ['桜空もも']},
            {'number': 'SONE-101', 'actors': ['桜空もも']},
            {'number': 'SONE-102', 'actors': ['桜空もも']},
        ]

        def mock_smart_search(q, limit=20, offset=0, status_callback=None,
                              result_callback=None, **kwargs):
            if result_callback:
                result_callback(-1, ids)
                for idx, item in enumerate(items_list):
                    result_callback(idx, item)
            if status_callback:
                status_callback('done', f'found:{len(ids)}')
            return items_list

        mock_profile = {'name': '桜空もも', 'img': 'https://graphis.ne.jp/prof.jpg'}

        with patch('web.routers.search.smart_search', side_effect=mock_smart_search), \
             patch('core.actress_scraper.get_actress_profile', return_value=mock_profile):
            response = client.get('/api/search/stream?q=桜空もも')

        events = parse_sse_events(response.text)
        complete_events = [e for e in events if e.get('type') == 'result-complete']
        assert len(complete_events) == 1

        complete_event = complete_events[0]
        assert 'has_more' in complete_event
        assert 'actress_profile' in complete_event

    def test_status_events_have_type_field(self, client, parse_sse_events):
        """status event 應包含 type 欄位"""
        def mock_smart_search(q, limit=20, offset=0, status_callback=None,
                              result_callback=None, **kwargs):
            if status_callback:
                status_callback('javbus', 'searching')
                status_callback('done', 'found:0')
            return []

        with patch('web.routers.search.smart_search', side_effect=mock_smart_search):
            response = client.get('/api/search/stream?q=TESTXYZ')

        events = parse_sse_events(response.text)
        status_events = [e for e in events if e.get('type') == 'status']
        assert len(status_events) >= 1, "Should have at least 1 status event"

        for event in status_events:
            assert event.get('type') == 'status', "Status events must have type='status'"
            assert 'source' in event
            assert 'status' in event

class TestFilterFiles:
    """Test /api/search/filter-files"""

    def test_filter_files_basic(self, client, tmp_path, monkeypatch):
        """基本過濾功能測試"""
        # 建立一個合格影片
        p1 = tmp_path / "good.mp4"
        p1.write_bytes(b'x' * (1 * 1024 * 1024 + 1))
        
        # 建立一個副檔名不符的
        p2 = tmp_path / "bad.txt"
        p2.write_bytes(b'x')
        
        # 不存在的檔案
        p3 = tmp_path / "not_exist.mp4"
        
        test_config = {
            "scraper": {"video_extensions": [".mp4"]},
            "gallery": {"min_size_mb": 1},
        }
        monkeypatch.setattr("core.config.load_config", lambda: test_config)
        
        response = client.post(
            "/api/search/filter-files",
            json={"paths": [str(p1), str(p2), str(p3)]}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["files"]) == 1
        assert str(p1) in data["files"]
        assert data["rejected"]["extension"] == 1
        assert data["rejected"]["not_found"] == 1

    def test_strm_not_filtered_by_min_size(self, client, tmp_path, monkeypatch):
        """.strm file should NOT be filtered by min_size setting"""
        # Create a .strm file (100 bytes)
        strm_file = tmp_path / "test.strm"
        strm_file.write_bytes(b'http://example.com/video.mp4')

        # Create config with .strm in video_extensions and min_size_mb=1
        test_config = {
            "scraper": {"video_extensions": [".mp4", ".strm"]},
            "gallery": {"min_size_mb": 1},
        }

        def mock_load_config():
            return test_config
        monkeypatch.setattr("core.config.load_config", mock_load_config)

        response = client.post(
            "/api/search/filter-files",
            json={"paths": [str(strm_file)]}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["files"]) == 1, \
            ".strm file should NOT be filtered by min_size (ZERO_SIZE_EXTENSIONS exemption)"
        assert data["rejected"]["size"] == 0

    def test_small_mp4_still_filtered_by_min_size(self, client, tmp_path, monkeypatch):
        """A small .mp4 file should still be filtered by min_size"""
        # Create a small .mp4 file (100 bytes)
        mp4_file = tmp_path / "small.mp4"
        mp4_file.write_bytes(b'\x00' * 100)

        test_config = {
            "scraper": {"video_extensions": [".mp4", ".strm"]},
            "gallery": {"min_size_mb": 1},
        }

        def mock_load_config():
            return test_config
        monkeypatch.setattr("core.config.load_config", mock_load_config)

        response = client.post(
            "/api/search/filter-files",
            json={"paths": [str(mp4_file)]}
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["files"]) == 0, \
            "Small .mp4 file should be filtered by min_size"
        assert data["rejected"]["size"] == 1


class TestFavoriteFiles:
    """Test /api/search/favorite-files"""

    def test_get_favorite_files_success(self, client, tmp_path, monkeypatch):
        """測試取得我的最愛資料夾檔案成功"""
        fav_dir = tmp_path / "fav"
        fav_dir.mkdir()
        
        video_file = fav_dir / "test_fav.mp4"
        video_file.write_bytes(b'x' * (1 * 1024 * 1024 + 1))
        
        txt_file = fav_dir / "test.txt"
        txt_file.write_bytes(b'hello')
        
        test_config = {
            "scraper": {"video_extensions": [".mp4"]},
            "gallery": {"min_size_mb": 1},
            "search": {"favorite_folder": str(fav_dir)}
        }
        monkeypatch.setattr("core.config.load_config", lambda: test_config)
        
        response = client.get("/api/search/favorite-files")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["files"]) == 1
        assert "test_fav.mp4" in data["files"][0]

    def test_get_favorite_files_empty(self, client, tmp_path, monkeypatch):
        """測試取得空目錄時返回錯誤訊息"""
        fav_dir = tmp_path / "fav_empty"
        fav_dir.mkdir()
        
        test_config = {"search": {"favorite_folder": str(fav_dir)}}
        monkeypatch.setattr("core.config.load_config", lambda: test_config)
        
        response = client.get("/api/search/favorite-files")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "無有效影片" in data["error"]

    def test_get_favorite_files_not_found(self, client, monkeypatch):
        """測試目標目錄不存在時的防呆"""
        test_config = {"search": {"favorite_folder": "/path/not/exists/123"}}
        monkeypatch.setattr("core.config.load_config", lambda: test_config)
        
        response = client.get("/api/search/favorite-files")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "不存在" in data["error"]


class TestSearchStreamSSEProtocol:
    """測試 /api/search/stream SSE 協議行為 — seed event 結構與欄位"""

    def test_seed_event_has_mode_total_slots(self, client, parse_sse_events):
        """seed event 應包含 mode、total、slots 欄位"""
        ids = ['SONE-100', 'SONE-101']

        def mock_smart_search(q, limit=20, offset=0, status_callback=None,
                              result_callback=None, **kwargs):
            if result_callback:
                result_callback(-1, ids)
                for idx, num in enumerate(ids):
                    result_callback(idx, {'number': num})
            return [{'number': num} for num in ids]

        with patch('web.routers.search.smart_search', side_effect=mock_smart_search):
            response = client.get('/api/search/stream?q=SONE')

        events = parse_sse_events(response.text)
        seed_events = [e for e in events if e.get('type') == 'seed']
        assert len(seed_events) == 1

        seed = seed_events[0]
        assert 'mode' in seed, "seed event must have 'mode' field"
        assert 'total' in seed, "seed event must have 'total' field"
        assert 'slots' in seed, "seed event must have 'slots' field"
        assert seed['total'] == len(ids)
        assert seed['slots'] == ids


# ============ T5a — 新欄位透傳 + proxy-image Referer ============

class TestSearchNewFields:
    """測試 T5a 新欄位（director/duration/label/series/sample_images）透傳"""

    def test_search_result_contains_new_fields(self, client, mocker):
        """REST GET /api/search?mode=exact 回傳 data[0] 含新欄位"""
        mock_data = load_fixture('responses/javbus/SONE-103.json')
        mocker.patch('web.routers.search.search_jav', return_value=mock_data)

        response = client.get('/api/search', params={'q': 'SONE-103', 'mode': 'exact'})

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert len(data['data']) == 1
        item = data['data'][0]

        # 驗證所有新欄位存在
        assert 'director' in item, "director key must be present"
        assert 'duration' in item, "duration key must be present"
        assert 'label' in item, "label key must be present"
        assert 'series' in item, "series key must be present"
        assert 'sample_images' in item, "sample_images key must be present"

        # 驗證值正確
        assert item['director'] == 'イナバール'
        assert item['duration'] == 119
        assert item['label'] == 'S1 NO.1 STYLE'
        assert item['series'] == ''
        assert isinstance(item['sample_images'], list)
        assert len(item['sample_images']) == 3

    def test_new_fields_empty_values_still_present(self, client, mocker):
        """新欄位空值時，key 仍必須出現在 response 中（前端可安全 access data.director ?? ""）"""
        mock_data = {
            'number': 'FAKE-001',
            'title': 'Some Title',
            'cover': '',
            'actors': [],
            'maker': '',
            'tags': [],
            'date': '',
            'source': 'javbus',
            'url': '',
            'director': '',
            'duration': None,
            'label': '',
            'series': '',
            'sample_images': [],
        }
        mocker.patch('web.routers.search.search_jav', return_value=mock_data)

        response = client.get('/api/search', params={'q': 'FAKE-001', 'mode': 'exact'})

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        item = data['data'][0]

        # 空值時 key 仍須存在
        assert 'director' in item
        assert 'duration' in item
        assert 'label' in item
        assert 'series' in item
        assert 'sample_images' in item

        # 值為空
        assert item['director'] == ''
        assert item['duration'] is None
        assert item['label'] == ''
        assert item['series'] == ''
        assert item['sample_images'] == []

    def test_sse_result_item_contains_new_fields(self, client, parse_sse_events):
        """SSE result-item event 的 data 應包含新欄位"""
        ids = ['SONE-103']
        item_with_new_fields = {
            'number': 'SONE-103',
            'title': '新人 専属19歳AVデビュー 石川澪',
            'actors': ['石川澪'],
            'director': 'イナバール',
            'duration': 119,
            'label': 'S1 NO.1 STYLE',
            'series': '',
            'sample_images': [
                'https://awsimgsrc.dmm.co.jp/pics_dig/mono/movie/adult/sone103/sone103jp-1.jpg',
            ],
        }

        def mock_smart_search(q, limit=20, offset=0, status_callback=None,
                              result_callback=None, **kwargs):
            if result_callback:
                result_callback(-1, ids)
                result_callback(0, item_with_new_fields)
            if status_callback:
                status_callback('done', 'found:1')
            return [item_with_new_fields]

        with patch('web.routers.search.smart_search', side_effect=mock_smart_search):
            response = client.get('/api/search/stream?q=SONE-103')

        events = parse_sse_events(response.text)
        item_events = [e for e in events if e.get('type') == 'result-item']
        assert len(item_events) == 1

        item_data = item_events[0]['data']
        assert 'director' in item_data, "SSE result-item data must have director"
        assert 'duration' in item_data, "SSE result-item data must have duration"
        assert 'label' in item_data, "SSE result-item data must have label"
        assert 'series' in item_data, "SSE result-item data must have series"
        assert 'sample_images' in item_data, "SSE result-item data must have sample_images"
        assert item_data['director'] == 'イナバール'
        assert item_data['duration'] == 119


class TestProxyImageReferer:
    """測試 /api/proxy-image DMM 樣品圖像 Referer 設定"""

    def _make_mock_response(self, content=b'\xff\xd8\xff', content_type='image/jpeg'):
        """建立 mock requests.Response"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = content
        mock_resp.headers = {'Content-Type': content_type}
        return mock_resp

    def test_proxy_image_dmm_sample_referer(self, client):
        """`awsimgsrc.dmm.co.jp` URL 發送請求時 Referer 應為 https://www.dmm.co.jp/"""
        url = 'https://awsimgsrc.dmm.co.jp/pics_dig/mono/movie/adult/sone103/sone103jp-1.jpg'

        with patch('web.routers.search.requests.get', return_value=self._make_mock_response()) as mock_get:
            response = client.get('/api/proxy-image', params={'url': url})

        assert response.status_code == 200
        mock_get.assert_called_once()
        _, call_kwargs = mock_get.call_args
        headers_sent = call_kwargs.get('headers', {})
        assert headers_sent.get('Referer') == 'https://www.dmm.co.jp/', \
            f"Expected Referer 'https://www.dmm.co.jp/', got '{headers_sent.get('Referer')}'"

    def test_proxy_image_pics_dmm_referer(self, client):
        """`pics.dmm.co.jp` URL 發送請求時 Referer 應為 https://www.dmm.co.jp/"""
        url = 'https://pics.dmm.co.jp/mono/movie/adult/sone103/sone103jp-3.jpg'

        with patch('web.routers.search.requests.get', return_value=self._make_mock_response()) as mock_get:
            response = client.get('/api/proxy-image', params={'url': url})

        assert response.status_code == 200
        mock_get.assert_called_once()
        _, call_kwargs = mock_get.call_args
        headers_sent = call_kwargs.get('headers', {})
        assert headers_sent.get('Referer') == 'https://www.dmm.co.jp/', \
            f"Expected Referer 'https://www.dmm.co.jp/', got '{headers_sent.get('Referer')}'"

    def test_proxy_image_javbus_referer(self, client):
        """`javbus.com` URL 發送請求時 Referer 應為 https://www.javbus.com/"""
        url = 'https://www.javbus.com/pics/cover/abc.jpg'

        with patch('web.routers.search.requests.get', return_value=self._make_mock_response()) as mock_get:
            response = client.get('/api/proxy-image', params={'url': url})

        assert response.status_code == 200
        mock_get.assert_called_once()
        _, call_kwargs = mock_get.call_args
        headers_sent = call_kwargs.get('headers', {})
        assert headers_sent.get('Referer') == 'https://www.javbus.com/'

    def test_proxy_image_unknown_domain_no_referer(self, client):
        """未知 domain 發送請求時 Referer 應為空字串（仍正常代理）"""
        url = 'https://cdn.example.com/image.jpg'

        with patch('web.routers.search.requests.get', return_value=self._make_mock_response()) as mock_get:
            response = client.get('/api/proxy-image', params={'url': url})

        assert response.status_code == 200
        mock_get.assert_called_once()
        _, call_kwargs = mock_get.call_args
        headers_sent = call_kwargs.get('headers', {})
        assert headers_sent.get('Referer') == ''

    def test_proxy_image_external_failure_returns_404(self, client):
        """外部請求失敗時應回傳 HTTP 404 空 body"""
        url = 'https://awsimgsrc.dmm.co.jp/pics_dig/mono/movie/adult/sone103/sone103jp-1.jpg'

        with patch('web.routers.search.requests.get', side_effect=Exception('timeout')):
            response = client.get('/api/proxy-image', params={'url': url})

        assert response.status_code == 404
        assert response.content == b''
