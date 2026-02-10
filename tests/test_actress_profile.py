"""
測試女優資料卡功能（Graphis + JavBus 雙來源）

包含：
- Graphis scraper mock 測試
- get_actress_profile 合併邏輯 mock 測試
- Cache 機制測試（全 mock，不打外部）
- Consistency check 單元測試（純邏輯，不需 mock）
- API 整合測試（mock search 結果 + mock actress profile）
"""

import pytest
from unittest.mock import patch, MagicMock
import time


# ============================================================================
# Graphis Scraper 測試（Mock）
# ============================================================================

def test_scrape_graphis_photo_success():
    """測試 Graphis 爬蟲成功案例（Mock）"""
    from core.graphis_scraper import scrape_graphis_photo

    mock_html = """
    <html>
        <div class="gp-model-box">
            <ul>
                <li><a><img src="https://data.graphis.ne.jp/free/model/170519_momo-sakura/prof.jpg"/></a></li>
            </ul>
        </div>
        <ul>
            <li class="name-jp"><span>桜空もも</span></li>
        </ul>
    </html>
    """

    with patch('requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = mock_html
        mock_get.return_value = mock_response

        result = scrape_graphis_photo("桜空もも")

        assert result is not None
        assert result['name'] == "桜空もも"
        assert 'prof_url' in result
        assert 'backdrop_url' in result
        assert '/prof.jpg' in result['prof_url']
        assert '/model.jpg' in result['backdrop_url']


def test_scrape_graphis_photo_not_found():
    """測試女優不存在於 Graphis（Mock）"""
    from core.graphis_scraper import scrape_graphis_photo

    mock_html = """
    <html>
        <div class="gp-model-box">
            <ul>
                <li><a><img src="https://data.graphis.ne.jp/free/model/some-actress/prof.jpg"/></a></li>
            </ul>
        </div>
        <ul>
            <li class="name-jp"><span>其他女優</span></li>
        </ul>
    </html>
    """

    with patch('requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = mock_html
        mock_get.return_value = mock_response

        result = scrape_graphis_photo("不存在的女優")
        assert result is None


def test_scrape_graphis_photo_timeout():
    """測試 timeout 處理（Mock）"""
    from core.graphis_scraper import scrape_graphis_photo
    import requests

    with patch('requests.get') as mock_get:
        mock_get.side_effect = requests.exceptions.Timeout()

        result = scrape_graphis_photo("桜空もも")
        assert result is None  # fail-open


def test_scrape_graphis_photo_request_error():
    """測試 request error 處理（Mock）"""
    from core.graphis_scraper import scrape_graphis_photo
    import requests

    with patch('requests.get') as mock_get:
        mock_get.side_effect = requests.exceptions.RequestException("Network error")

        result = scrape_graphis_photo("桜空もも")
        assert result is None  # fail-open


# ============================================================================
# get_actress_profile 測試（Mock）
# ============================================================================

def test_get_actress_profile_both_sources():
    """測試雙來源合併邏輯（Mock）"""
    from core.actress_scraper import get_actress_profile, _cache

    # 清空 cache
    _cache.clear()

    # Mock Graphis 回傳照片
    def mock_graphis(name):
        return {
            'name': name,
            'prof_url': 'https://graphis.ne.jp/prof.jpg',
            'backdrop_url': 'https://graphis.ne.jp/model.jpg'
        }

    # Mock JavBus 回傳資料
    def mock_javbus(name):
        return {
            'name': name,
            'img': 'https://javbus.com/img.jpg',
            'birth': '1996-12-03',
            'age': 29,
            'height': '160cm',
            'cup': 'G'
        }

    with patch('core.graphis_scraper.scrape_graphis_photo', side_effect=mock_graphis), \
         patch('core.actress_scraper.scrape_actress_profile', side_effect=mock_javbus):

        result = get_actress_profile("桜空もも")

        assert result is not None
        # Graphis 照片優先
        assert result['img'] == 'https://graphis.ne.jp/prof.jpg'
        assert result['backdrop'] == 'https://graphis.ne.jp/model.jpg'

        # JavBus 資料保留
        assert result['birth'] == '1996-12-03'
        assert result['age'] == 29
        assert result['height'] == '160cm'
        assert result['cup'] == 'G'


def test_get_actress_profile_javbus_only():
    """測試只有 JavBus 有資料（Mock）"""
    from core.actress_scraper import get_actress_profile, _cache

    # 清空 cache
    _cache.clear()

    def mock_javbus(name):
        return {
            'name': name,
            'img': 'https://javbus.com/img.jpg',
            'birth': '1996-12-03',
            'age': 29
        }

    with patch('core.graphis_scraper.scrape_graphis_photo', return_value=None), \
         patch('core.actress_scraper.scrape_actress_profile', side_effect=mock_javbus):

        result = get_actress_profile("桜空もも")

        assert result is not None
        assert result['img'] == 'https://javbus.com/img.jpg'
        assert result['birth'] == '1996-12-03'


def test_get_actress_profile_graphis_only():
    """測試只有 Graphis 有資料（Mock）"""
    from core.actress_scraper import get_actress_profile, _cache

    # 清空 cache
    _cache.clear()

    def mock_graphis(name):
        return {
            'name': name,
            'prof_url': 'https://graphis.ne.jp/prof.jpg',
            'backdrop_url': 'https://graphis.ne.jp/model.jpg'
        }

    with patch('core.graphis_scraper.scrape_graphis_photo', side_effect=mock_graphis), \
         patch('core.actress_scraper.scrape_actress_profile', return_value=None):

        result = get_actress_profile("桜空もも")

        assert result is not None
        assert result['name'] == '桜空もも'
        assert result['img'] == 'https://graphis.ne.jp/prof.jpg'
        assert result['backdrop'] == 'https://graphis.ne.jp/model.jpg'


def test_get_actress_profile_both_fail():
    """測試雙來源都失敗（Mock）"""
    from core.actress_scraper import get_actress_profile, _cache

    # 清空 cache
    _cache.clear()

    with patch('core.graphis_scraper.scrape_graphis_photo', return_value=None), \
         patch('core.actress_scraper.scrape_actress_profile', return_value=None):

        result = get_actress_profile("不存在的女優")
        assert result is None


# ============================================================================
# Cache 機制測試（全 mock）
# ============================================================================

def test_get_actress_profile_cache_hit():
    """測試 cache 命中（Mock）"""
    from core.actress_scraper import get_actress_profile, _cache

    # 清空 cache
    _cache.clear()

    def mock_graphis(name):
        return {
            'name': name,
            'prof_url': 'https://graphis.ne.jp/prof.jpg',
            'backdrop_url': 'https://graphis.ne.jp/model.jpg'
        }

    def mock_javbus(name):
        return {
            'name': name,
            'img': 'https://javbus.com/img.jpg',
            'birth': '1996-12-03',
            'age': 29
        }

    with patch('core.graphis_scraper.scrape_graphis_photo', side_effect=mock_graphis) as graphis_mock, \
         patch('core.actress_scraper.scrape_actress_profile', side_effect=mock_javbus) as javbus_mock:

        # 第一次呼叫
        result1 = get_actress_profile("桜空もも")
        assert result1 is not None
        assert graphis_mock.call_count == 1
        assert javbus_mock.call_count == 1

        # 第二次呼叫（應從 cache 取得）
        result2 = get_actress_profile("桜空もも")
        assert result2 is not None
        assert result1 == result2
        # Mock 不應被再次呼叫
        assert graphis_mock.call_count == 1
        assert javbus_mock.call_count == 1


def test_get_actress_profile_cache_expired():
    """測試 cache 過期（Mock）"""
    from core.actress_scraper import get_actress_profile, _cache, _CACHE_TTL

    # 清空 cache
    _cache.clear()

    def mock_graphis(name):
        return {
            'name': name,
            'prof_url': 'https://graphis.ne.jp/prof.jpg',
            'backdrop_url': 'https://graphis.ne.jp/model.jpg'
        }

    def mock_javbus(name):
        return {
            'name': name,
            'img': 'https://javbus.com/img.jpg'
        }

    # Mock time.time 使用固定值
    fixed_time = [1000.0]

    def mock_time():
        return fixed_time[0]

    with patch('time.time', side_effect=mock_time), \
         patch('core.graphis_scraper.scrape_graphis_photo', side_effect=mock_graphis) as graphis_mock, \
         patch('core.actress_scraper.scrape_actress_profile', side_effect=mock_javbus) as javbus_mock:

        # 第一次呼叫
        result1 = get_actress_profile("桜空もも")
        assert result1 is not None
        assert graphis_mock.call_count == 1

        # 模擬時間過期（超過 TTL）
        fixed_time[0] = 1000.0 + _CACHE_TTL + 1

        # 第二次呼叫（應重新抓取）
        result2 = get_actress_profile("桜空もも")
        assert result2 is not None
        assert graphis_mock.call_count == 2  # 應被再次呼叫


def test_get_actress_profile_cache_name_normalization():
    """測試 cache key 名稱正規化（Mock）"""
    from core.actress_scraper import get_actress_profile, _cache

    # 清空 cache
    _cache.clear()

    def mock_graphis(name):
        return {
            'name': name,
            'prof_url': 'https://graphis.ne.jp/prof.jpg',
            'backdrop_url': 'https://graphis.ne.jp/model.jpg'
        }

    def mock_javbus(name):
        return {'name': name, 'img': 'https://javbus.com/img.jpg'}

    with patch('core.graphis_scraper.scrape_graphis_photo', side_effect=mock_graphis) as graphis_mock, \
         patch('core.actress_scraper.scrape_actress_profile', side_effect=mock_javbus):

        # 第一次：正常名稱
        result1 = get_actress_profile("桜空もも")
        assert result1 is not None
        assert graphis_mock.call_count == 1

        # 第二次：帶前後空白（應命中 cache）
        result2 = get_actress_profile("  桜空もも  ")
        assert result2 is not None
        assert result1 == result2
        assert graphis_mock.call_count == 1  # 不應再次呼叫


# ============================================================================
# Consistency Check 單元測試（純邏輯，不需 mock）
# ============================================================================

def test_analyze_top_actor_single_actress():
    """測試單一女優佔比 100%"""
    from web.routers.search import _analyze_top_actor

    results = [
        {'actors': ['桜空もも']},
        {'actors': ['桜空もも']},
        {'actors': ['桜空もも']},
    ]

    top_actor = _analyze_top_actor(results, threshold=0.8, min_samples=3)
    assert top_actor == '桜空もも'


def test_analyze_top_actor_mixed_below_threshold():
    """測試混合結果（佔比 < 80%）"""
    from web.routers.search import _analyze_top_actor

    results = [
        {'actors': ['古川いおり']},
        {'actors': ['古川いおり']},
        {'actors': ['古川いおり']},
        {'actors': ['古川祐子']},
        {'actors': ['古川ななせ']},
    ]

    top_actor = _analyze_top_actor(results, threshold=0.8, min_samples=3)
    assert top_actor is None  # 3/5 = 60% < 80%


def test_analyze_top_actor_few_samples():
    """測試結果 < 3 筆（不觸發）"""
    from web.routers.search import _analyze_top_actor

    results = [
        {'actors': ['桜空もも']},
        {'actors': ['桜空もも']},
    ]

    top_actor = _analyze_top_actor(results, threshold=0.8, min_samples=3)
    assert top_actor is None  # < min_samples


def test_analyze_top_actor_no_actors_field():
    """測試無 actors 欄位的結果"""
    from web.routers.search import _analyze_top_actor

    results = [
        {'title': 'video1'},
        {'title': 'video2'},
        {'title': 'video3'},
    ]

    top_actor = _analyze_top_actor(results, threshold=0.8, min_samples=3)
    assert top_actor is None


def test_analyze_top_actor_mixed_formats():
    """測試 actors 多種格式"""
    from web.routers.search import _analyze_top_actor

    results = [
        {'actors': ['桜空もも']},
        {'actors': [{'name': '桜空もも'}]},
        {'actors': '桜空もも'},
        {'actors': ['桜空もも']},
    ]

    top_actor = _analyze_top_actor(results, threshold=0.8, min_samples=3)
    assert top_actor == '桜空もも'  # 4/4 = 100%


def test_analyze_top_actor_name_normalization():
    """測試名稱正規化（全形/半形空白）"""
    from web.routers.search import _analyze_top_actor

    results = [
        {'actors': ['桜空もも']},
        {'actors': ['  桜空もも  ']},  # 前後空白
        {'actors': ['桜空　もも']},  # 全形空白
        {'actors': ['桜空もも']},
        {'actors': ['桜空もも']},  # 多加一筆確保 >= 80%
    ]

    top_actor = _analyze_top_actor(results, threshold=0.8, min_samples=3)
    assert top_actor == '桜空もも'  # 正規化後應為同一人（5/5 = 100%）


def test_analyze_top_actor_80_percent_threshold():
    """測試剛好 80% 閾值"""
    from web.routers.search import _analyze_top_actor

    results = [
        {'actors': ['桜空もも']},
        {'actors': ['桜空もも']},
        {'actors': ['桜空もも']},
        {'actors': ['桜空もも']},
        {'actors': ['其他女優']},
    ]

    top_actor = _analyze_top_actor(results, threshold=0.8, min_samples=3)
    assert top_actor == '桜空もも'  # 4/5 = 80% 剛好通過


# ============================================================================
# API 整合測試（Mock search 結果 + mock actress profile）
# ============================================================================

@pytest.fixture
def mock_search_actress():
    """Mock 女優搜尋結果"""
    def mock_fn(q, **kwargs):
        return [
            {'number': 'SONE-205', 'actors': ['桜空もも']},
            {'number': 'SONE-180', 'actors': ['桜空もも']},
            {'number': 'SONE-162', 'actors': ['桜空もも']},
        ]
    return mock_fn


@pytest.fixture
def mock_actress_profile():
    """Mock 女優資料"""
    def mock_fn(name):
        if name == '桜空もも':
            return {
                'name': '桜空もも',
                'img': 'https://graphis.ne.jp/prof.jpg',
                'backdrop': 'https://graphis.ne.jp/model.jpg',
                'birth': '1996-12-03',
                'age': 29
            }
        return None
    return mock_fn


def test_search_api_actress_with_profile(mock_search_actress, mock_actress_profile):
    """測試女優搜尋 API（有 actress_profile）"""
    from fastapi.testclient import TestClient
    from web.app import app

    client = TestClient(app)

    with patch('core.scraper.search_actress', side_effect=mock_search_actress), \
         patch('core.actress_scraper.get_actress_profile', side_effect=mock_actress_profile):

        resp = client.get("/api/search?q=桜空もも&mode=actress")
        data = resp.json()

        assert data['success'] is True
        assert data['mode'] == 'actress'
        assert 'actress_profile' in data
        assert data['actress_profile'] is not None
        assert data['actress_profile']['name'] == '桜空もも'
        assert 'graphis.ne.jp' in data['actress_profile']['img']


def test_search_api_exact_no_profile():
    """測試番號搜尋（無 actress_profile）"""
    from fastapi.testclient import TestClient
    from web.app import app

    client = TestClient(app)

    def mock_search_jav(q):
        return {'number': 'SONE-205', 'actors': ['桜空もも']}

    with patch('core.scraper.search_jav', side_effect=mock_search_jav):
        resp = client.get("/api/search?q=SONE-205&mode=exact")
        data = resp.json()

        assert data['success'] is True
        assert 'actress_profile' in data
        # exact 模式不觸發 consistency check
        assert data['actress_profile'] is None


def test_search_api_mixed_results_no_profile():
    """測試混合結果（consistency < 80%）"""
    from fastapi.testclient import TestClient
    from web.app import app

    client = TestClient(app)

    def mock_smart_search(q, **kwargs):
        return [
            {'number': 'FUGA-001', 'actors': ['古川いおり']},
            {'number': 'FUGA-002', 'actors': ['古川いおり']},
            {'number': 'FUGA-003', 'actors': ['古川祐子']},
            {'number': 'FUGA-004', 'actors': ['古川ななせ']},
            {'number': 'FUGA-005', 'actors': ['古川未波']},
        ]

    def mock_search_actress(q, **kwargs):
        # Mock actress mode 也回傳混合結果
        return [
            {'number': 'FUGA-001', 'actors': ['古川いおり']},
            {'number': 'FUGA-002', 'actors': ['古川いおり']},
            {'number': 'FUGA-003', 'actors': ['古川祐子']},
            {'number': 'FUGA-004', 'actors': ['古川ななせ']},
            {'number': 'FUGA-005', 'actors': ['古川未波']},
        ]

    with patch('core.scraper.smart_search', side_effect=mock_smart_search), \
         patch('core.scraper.search_actress', side_effect=mock_search_actress):
        resp = client.get("/api/search?q=古川")
        data = resp.json()

        assert data['success'] is True
        assert 'actress_profile' in data
        assert data['actress_profile'] is None  # 未通過 consistency check


def test_search_api_few_results_no_profile():
    """測試結果 < 3 筆（不觸發）"""
    from fastapi.testclient import TestClient
    from web.app import app

    client = TestClient(app)

    def mock_smart_search(q, **kwargs):
        return [
            {'number': 'SONE-205', 'actors': ['桜空もも']},
            {'number': 'SONE-180', 'actors': ['桜空もも']},
        ]

    with patch('core.scraper.smart_search', side_effect=mock_smart_search):
        resp = client.get("/api/search?q=test")
        data = resp.json()

        assert 'actress_profile' in data
        assert data['actress_profile'] is None  # < 3 筆不觸發


def test_search_api_graceful_failure(mock_search_actress):
    """測試雙來源失敗時不影響搜尋結果"""
    from fastapi.testclient import TestClient
    from web.app import app

    client = TestClient(app)

    # Mock 雙來源都失敗
    with patch('core.scraper.search_actress', side_effect=mock_search_actress), \
         patch('core.actress_scraper.get_actress_profile', return_value=None):

        resp = client.get("/api/search?q=桜空もも&mode=actress")
        data = resp.json()

        assert data['success'] is True  # 搜尋結果正常
        assert data['actress_profile'] is None  # 資料卡為空
        assert len(data['data']) > 0  # 有搜尋結果


def test_search_api_variant_id_no_profile():
    """測試 variant_id 路徑有 actress_profile 欄位"""
    from fastapi.testclient import TestClient
    from web.app import app

    client = TestClient(app)

    def mock_search_variant(variant_id, q):
        return {'number': 'SONE-205', 'actors': ['桜空もも']}

    with patch('core.scraper.search_by_variant_id', side_effect=mock_search_variant):
        resp = client.get("/api/search?q=SONE-205&variant_id=javbus-SONE-205")
        data = resp.json()

        assert 'actress_profile' in data
        assert data['actress_profile'] is None  # variant_id 路徑不觸發
