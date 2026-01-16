"""
test_api_search.py - 搜尋 API 整合測試

使用 mocker.patch Mock 爬蟲回應，驗證搜尋 API 行為。
"""

import pytest
import json
from pathlib import Path


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
        mocker.patch('core.scraper.search_jav', return_value=mock_data)

        response = client.get('/api/search', params={'q': 'SONE-103', 'mode': 'exact'})

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['data'][0]['number'] == 'SONE-103'
        assert data['total'] == 1

    def test_search_auto_mode(self, client, mocker):
        """自動模式搜尋"""
        mock_data = load_fixture('responses/javbus/SONE-103.json')
        mocker.patch('core.scraper.smart_search', return_value=[mock_data])

        response = client.get('/api/search', params={'q': 'SONE-103'})

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert len(data['data']) >= 1

    def test_search_no_results(self, client, mocker):
        """搜尋無結果"""
        mocker.patch('core.scraper.smart_search', return_value=[])

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
        mocker.patch('core.scraper.search_partial', return_value=mock_results)

        response = client.get('/api/search', params={'q': 'SONE-10', 'mode': 'partial'})

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert len(data['data']) >= 1

    def test_search_actress_mode(self, client, mocker):
        """女優搜尋模式"""
        mock_results = load_fixture('responses/javdb/actress_search.json')
        mocker.patch('core.scraper.search_actress', return_value=mock_results)

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
        mocker.patch('core.scraper.smart_search', return_value=mock_results[:5])

        response = client.get('/api/search', params={'q': 'SONE', 'limit': 5})

        assert response.status_code == 200
        data = response.json()
        assert data['total'] <= 5

    def test_search_with_offset(self, client, mocker):
        """分頁 offset 參數"""
        mock_results = [{'number': f'SONE-{i}', 'title': f'Title {i}'} for i in range(100, 110)]
        mocker.patch('core.scraper.smart_search', return_value=mock_results)

        response = client.get('/api/search', params={'q': 'SONE', 'limit': 5, 'offset': 5})

        assert response.status_code == 200
        data = response.json()
        assert 'offset' in data
