"""
測試女優資料卡功能（Graphis + JavBus 雙來源）

包含：
- Graphis scraper mock 測試
- get_actress_profile 合併邏輯 mock 測試
- Cache 機制測試（全 mock，不打外部）
- Consistency check 單元測試（純邏輯，不需 mock）
- API 整合測試（mock search 結果 + mock actress profile）
"""

import json

import pytest
from unittest.mock import patch, MagicMock

# ---------------------------------------------------------------------------
# Datetime freeze (for TD-1: current_age computed from birth via datetime.now)
# ---------------------------------------------------------------------------
from datetime import datetime as _real_datetime

# Frozen instant for age computation: 2026-04-11 (current project date)
_FROZEN_NOW = _real_datetime(2026, 4, 11, 0, 0, 0)


class _FrozenDatetime(_real_datetime):
    """datetime subclass with now() overridden to a frozen instant.
    strptime/other methods inherited from real datetime."""
    @classmethod
    def now(cls, tz=None):
        return _FROZEN_NOW


@pytest.fixture(autouse=True)
def _freeze_orchestrator_datetime(monkeypatch):
    """Autouse: freeze datetime.now() as seen by
    core.scrapers.actress.orchestrator._compute_age_from_birth."""
    monkeypatch.setattr(
        "core.scrapers.actress.orchestrator.datetime",
        _FrozenDatetime,
    )


@pytest.fixture(autouse=True)
def clear_actress_cache():
    from core.scrapers.actress.orchestrator import _cache
    _cache.clear()
    yield
    _cache.clear()


# ============================================================================
# 共用測試 HTML 常數
# ============================================================================

_LISTING_HTML = """
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

MODEL_PHP_HTML = """
<html>
    <p class="pan-link">TOP > モデル一覧 > 桜空もも/Momo Sakurazora</p>
    <li class="model-prof">
      <ul>
        <li><span>年齢 /age：</span><span>28</span></li>
        <li><span>身長 /height：</span><span> 160cm</span></li>
        <li><span>スリーサイズ /BWH：</span><span>B90(G) W55 H86</span></li>
        <li><span>趣味 /hobby：</span><span>ゲーム</span></li>
      </ul>
    </li>
</html>
"""


# ============================================================================
# Graphis Scraper 測試（Mock）
# ============================================================================

def test_scrape_graphis_photo_success():
    """測試 Graphis 爬蟲成功案例（Mock）— 雙 request: listing + model.php"""
    from core.scrapers.actress.graphis import scrape_graphis_photo

    with patch('requests.get') as mock_get:
        listing_resp = MagicMock(status_code=200, text=_LISTING_HTML)
        listing_resp.raise_for_status = MagicMock()
        model_resp = MagicMock(status_code=200, text=MODEL_PHP_HTML)
        mock_get.side_effect = [listing_resp, model_resp]

        result = scrape_graphis_photo("桜空もも")

        assert result is not None
        assert result['name'] == "桜空もも"
        assert 'prof_url' in result
        assert 'backdrop_url' in result
        assert '/prof.jpg' in result['prof_url']
        assert '/model.jpg' in result['backdrop_url']
        # Verify profile fields parsed from model.php
        assert result['name_en'] == 'Momo Sakurazora'
        assert result['age'] == 28
        assert result['height'] == '160cm'
        assert result['cup'] == 'G'


def test_scrape_graphis_photo_not_found():
    """測試女優不存在於 Graphis（Mock）"""
    from core.scrapers.actress.graphis import scrape_graphis_photo

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
    from core.scrapers.actress.graphis import scrape_graphis_photo
    import requests

    with patch('requests.get') as mock_get:
        mock_get.side_effect = requests.exceptions.Timeout()

        result = scrape_graphis_photo("桜空もも")
        assert result is None  # fail-open


def test_scrape_graphis_photo_request_error():
    """測試 request error 處理（Mock）"""
    from core.scrapers.actress.graphis import scrape_graphis_photo
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
    from core.scrapers.actress.orchestrator import get_actress_profile, _cache

    # Mock Graphis 回傳照片（含 birth/height/cup 供 TD-1 + text cascade 測試）
    def mock_graphis(name):
        return {
            'name': name,
            'prof_url': 'https://graphis.ne.jp/prof.jpg',
            'backdrop_url': 'https://graphis.ne.jp/model.jpg',
            'birth': '1997-12-03',
            'height': '160cm',
            'cup': 'G',
        }

    # Mock JavBus 回傳資料（新 orchestrator 不呼叫 javbus，留作舊 patch chain 參考）
    def mock_javbus(name):
        return {
            'name': name,
            'img': 'https://javbus.com/img.jpg',
            'birth': '1996-12-03',
            'age': 29,
            'height': '160cm',
            'cup': 'G'
        }

    with patch('core.scrapers.actress.minnano_av.scrape_minnano_av', return_value=None), \
         patch('core.scrapers.actress.wiki_ja.scrape_wiki_ja', return_value=None), \
         patch('core.scrapers.actress.graphis.scrape_graphis_photo', side_effect=mock_graphis), \
         patch('core.scrapers.actress.javbus.scrape_actress_profile', side_effect=mock_javbus), \
         patch('core.scrapers.actress.gfriends.lookup_gfriends', return_value=None):

        result = get_actress_profile("桜空もも")

        assert result is not None
        # Graphis 照片優先（gfriends 回傳 None）
        assert result['img'] == 'https://graphis.ne.jp/prof.jpg'
        assert result['backdrop'] == 'https://graphis.ne.jp/model.jpg'

        # graphis text wins cascade (minnano/wiki mocked None by T4.3)
        assert result['birth'] == '1997-12-03'   # from graphis (via text cascade)
        assert result['age'] == 28                # TD-1: from birth 1997-12-03 + frozen 2026-04-11
        assert result['height'] == '160cm'
        assert result['cup'] == 'G'


def test_get_actress_profile_all_routes_none_javbus_ignored():
    """T4.3 semantic: javbus is schema-only (not data). When all active routes
    (minnano/wiki/graphis/gfriends) return None, result is None — even if the legacy
    javbus safety-net mock has data. Validates that the new orchestrator ignores javbus."""
    from core.scrapers.actress.orchestrator import get_actress_profile, _cache

    def mock_javbus(name):
        return {
            'name': name,
            'img': 'https://javbus.com/img.jpg',
            'birth': '1996-12-03',
            'age': 29
        }

    with patch('core.scrapers.actress.minnano_av.scrape_minnano_av', return_value=None), \
         patch('core.scrapers.actress.wiki_ja.scrape_wiki_ja', return_value=None), \
         patch('core.scrapers.actress.graphis.scrape_graphis_photo', return_value=None), \
         patch('core.scrapers.actress.javbus.scrape_actress_profile', side_effect=mock_javbus), \
         patch('core.scrapers.actress.gfriends.lookup_gfriends', return_value=None):

        result = get_actress_profile("桜空もも")

        # All active routes return None → orchestrator returns None (javbus is ignored)
        assert result is None


def test_get_actress_profile_graphis_only():
    """測試只有 Graphis 有資料（Mock）"""
    from core.scrapers.actress.orchestrator import get_actress_profile, _cache

    def mock_graphis(name):
        return {
            'name': name,
            'name_ja': name,   # T4.3: orchestrator reads name_ja for result['name']
            'prof_url': 'https://graphis.ne.jp/prof.jpg',
            'backdrop_url': 'https://graphis.ne.jp/model.jpg'
        }

    with patch('core.scrapers.actress.minnano_av.scrape_minnano_av', return_value=None), \
         patch('core.scrapers.actress.wiki_ja.scrape_wiki_ja', return_value=None), \
         patch('core.scrapers.actress.graphis.scrape_graphis_photo', side_effect=mock_graphis), \
         patch('core.scrapers.actress.javbus.scrape_actress_profile', return_value=None), \
         patch('core.scrapers.actress.gfriends.lookup_gfriends', return_value=None):

        result = get_actress_profile("桜空もも")

        assert result is not None
        assert result['name'] == '桜空もも'
        assert result['img'] == 'https://graphis.ne.jp/prof.jpg'
        assert result['backdrop'] == 'https://graphis.ne.jp/model.jpg'


def test_get_actress_profile_both_fail():
    """測試雙來源都失敗（Mock）"""
    from core.scrapers.actress.orchestrator import get_actress_profile, _cache

    with patch('core.scrapers.actress.minnano_av.scrape_minnano_av', return_value=None), \
         patch('core.scrapers.actress.wiki_ja.scrape_wiki_ja', return_value=None), \
         patch('core.scrapers.actress.graphis.scrape_graphis_photo', return_value=None), \
         patch('core.scrapers.actress.javbus.scrape_actress_profile', return_value=None), \
         patch('core.scrapers.actress.gfriends.lookup_gfriends', return_value=None):

        result = get_actress_profile("不存在的女優")
        assert result is None


# ============================================================================
# Cache 機制測試（全 mock）
# ============================================================================

def test_get_actress_profile_cache_hit():
    """測試 cache 命中（Mock）"""
    from core.scrapers.actress.orchestrator import get_actress_profile, _cache

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

    with patch('core.scrapers.actress.minnano_av.scrape_minnano_av', return_value=None) as minnano_mock, \
         patch('core.scrapers.actress.wiki_ja.scrape_wiki_ja', return_value=None) as wiki_mock, \
         patch('core.scrapers.actress.graphis.scrape_graphis_photo', side_effect=mock_graphis) as graphis_mock, \
         patch('core.scrapers.actress.javbus.scrape_actress_profile', side_effect=mock_javbus) as javbus_mock, \
         patch('core.scrapers.actress.gfriends.lookup_gfriends', return_value=None):

        # 第一次呼叫
        result1 = get_actress_profile("桜空もも")
        assert result1 is not None
        assert graphis_mock.call_count == 1
        # T4.3: javbus is not called by new orchestrator — safety-net mock stays at 0
        assert javbus_mock.call_count == 0

        # 第二次呼叫（應從 cache 取得）
        result2 = get_actress_profile("桜空もも")
        assert result2 is not None
        assert result1 == result2
        # Mock 不應被再次呼叫
        assert graphis_mock.call_count == 1
        assert javbus_mock.call_count == 0


def test_get_actress_profile_cache_expired():
    """測試 cache 過期（Mock）"""
    from core.scrapers.actress.orchestrator import get_actress_profile, _cache, _CACHE_TTL

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
         patch('core.scrapers.actress.minnano_av.scrape_minnano_av', return_value=None), \
         patch('core.scrapers.actress.wiki_ja.scrape_wiki_ja', return_value=None), \
         patch('core.scrapers.actress.graphis.scrape_graphis_photo', side_effect=mock_graphis) as graphis_mock, \
         patch('core.scrapers.actress.javbus.scrape_actress_profile', side_effect=mock_javbus) as javbus_mock, \
         patch('core.scrapers.actress.gfriends.lookup_gfriends', return_value=None):

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
    from core.scrapers.actress.orchestrator import get_actress_profile, _cache

    def mock_graphis(name):
        return {
            'name': name,
            'prof_url': 'https://graphis.ne.jp/prof.jpg',
            'backdrop_url': 'https://graphis.ne.jp/model.jpg'
        }

    def mock_javbus(name):
        return {'name': name, 'img': 'https://javbus.com/img.jpg'}

    with patch('core.scrapers.actress.minnano_av.scrape_minnano_av', return_value=None), \
         patch('core.scrapers.actress.wiki_ja.scrape_wiki_ja', return_value=None), \
         patch('core.scrapers.actress.graphis.scrape_graphis_photo', side_effect=mock_graphis) as graphis_mock, \
         patch('core.scrapers.actress.javbus.scrape_actress_profile', side_effect=mock_javbus), \
         patch('core.scrapers.actress.gfriends.lookup_gfriends', return_value=None):

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
    def mock_fn(name, **kwargs):
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


def test_search_api_actress_with_profile(client, mock_search_actress, mock_actress_profile):
    """測試女優搜尋 API（有 actress_profile）"""
    with patch('web.routers.search.search_actress', side_effect=mock_search_actress), \
         patch('core.scrapers.actress.orchestrator.get_actress_profile', side_effect=mock_actress_profile):

        resp = client.get("/api/search?q=桜空もも&mode=actress")
        data = resp.json()

        assert data['success'] is True
        assert data['mode'] == 'actress'
        assert 'actress_profile' in data
        assert data['actress_profile'] is not None
        assert data['actress_profile']['name'] == '桜空もも'
        assert 'graphis.ne.jp' in data['actress_profile']['img']


def test_search_api_exact_no_profile(client):
    """測試番號搜尋（無 actress_profile）"""
    def mock_search_jav(q, **kwargs):
        return {'number': 'SONE-205', 'actors': ['桜空もも']}

    with patch('web.routers.search.search_jav', side_effect=mock_search_jav):
        resp = client.get("/api/search?q=SONE-205&mode=exact")
        data = resp.json()

        assert data['success'] is True
        assert 'actress_profile' in data
        # exact 模式不觸發 consistency check
        assert data['actress_profile'] is None


def test_search_api_mixed_results_no_profile(client):
    """測試混合結果（consistency < 80%）"""
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

    with patch('web.routers.search.smart_search', side_effect=mock_smart_search), \
         patch('web.routers.search.search_actress', side_effect=mock_search_actress):
        resp = client.get("/api/search?q=古川")
        data = resp.json()

        assert data['success'] is True
        assert 'actress_profile' in data
        assert data['actress_profile'] is None  # 未通過 consistency check


def test_search_api_few_results_no_profile(client):
    """測試結果 < 3 筆（不觸發）"""
    def mock_smart_search(q, **kwargs):
        return [
            {'number': 'SONE-205', 'actors': ['桜空もも']},
            {'number': 'SONE-180', 'actors': ['桜空もも']},
        ]

    with patch('web.routers.search.smart_search', side_effect=mock_smart_search):
        resp = client.get("/api/search?q=test")
        data = resp.json()

        assert 'actress_profile' in data
        assert data['actress_profile'] is None  # < 3 筆不觸發


def test_search_api_graceful_failure(client, mock_search_actress):
    """測試雙來源失敗時不影響搜尋結果"""
    # Mock 雙來源都失敗
    with patch('web.routers.search.search_actress', side_effect=mock_search_actress), \
         patch('core.scrapers.actress.orchestrator.get_actress_profile', return_value=None):

        resp = client.get("/api/search?q=桜空もも&mode=actress")
        data = resp.json()

        assert data['success'] is True  # 搜尋結果正常
        assert data['actress_profile'] is None  # 資料卡為空
        assert isinstance(data['data'], list)
        assert len(data['data']) == 3  # mock 會提供 3 筆結果
        assert data['data'][0]['number'] == 'SONE-205'


def test_search_api_variant_id_no_profile(client):
    """測試 variant_id 路徑有 actress_profile 欄位"""
    def mock_search_variant(variant_id, q):
        return {'number': 'SONE-205', 'actors': ['桜空もも']}

    with patch('web.routers.search.search_by_variant_id', side_effect=mock_search_variant):
        resp = client.get("/api/search?q=SONE-205&variant_id=javbus-SONE-205")
        data = resp.json()

        assert 'actress_profile' in data
        assert data['actress_profile'] is None  # variant_id 路徑不觸發


def test_sse_includes_actress_profile(client, mock_search_actress, mock_actress_profile):
    """SSE result event 應包含 actress_profile"""
    with patch('web.routers.search.smart_search', side_effect=mock_search_actress), \
         patch('core.scrapers.actress.orchestrator.get_actress_profile', side_effect=mock_actress_profile):

        response = client.get('/api/search/stream?q=桜空もも')

        # Parse SSE events
        events = []
        for line in response.text.strip().split('\n'):
            if line.startswith('data: '):
                event_data = json.loads(line[6:])  # Remove 'data: ' prefix
                events.append(event_data)

        # Find result event
        result_events = [e for e in events if e.get('type') == 'result']
        assert len(result_events) == 1

        result_event = result_events[0]
        assert result_event['success'] is True
        assert 'actress_profile' in result_event
        assert result_event['actress_profile'] is not None
        assert result_event['actress_profile']['name'] == '桜空もも'
        assert 'graphis.ne.jp' in result_event['actress_profile']['img']


# ============================================================================
# gfriends Lookup 測試（Mock HEAD requests）
# ============================================================================

def test_lookup_gfriends_top1_hit():
    """Top1 片商 folder HEAD 200 → 回傳 CDN URL"""
    from core.scrapers.actress.gfriends import lookup_gfriends, CDN_BASE

    with patch('requests.head') as mock_head:
        hit_resp = MagicMock(status_code=200)
        mock_head.return_value = hit_resp

        result = lookup_gfriends("桜空もも", makers=["S1"])

        assert result is not None
        assert CDN_BASE in result
        assert "7-S1" in result
        assert "桜空もも" in result


def test_lookup_gfriends_top1_miss_top2_hit():
    """Top1 非 200, Top2 命中 → fallback 成功"""
    from core.scrapers.actress.gfriends import lookup_gfriends, CDN_BASE

    with patch('requests.head') as mock_head:
        miss_resp = MagicMock(status_code=403)
        hit_resp = MagicMock(status_code=200)
        # Top1 folder (7-S1): {name}.jpg miss, AI-Fix miss
        # Top2 folder (7-Moodyz): {name}.jpg hit
        mock_head.side_effect = [miss_resp, miss_resp, hit_resp]

        result = lookup_gfriends("桜空もも", makers=["S1", "Moodyz"])

        assert result is not None
        assert CDN_BASE in result
        assert "7-Moodyz" in result
        assert "桜空もも" in result


def test_lookup_gfriends_avdbs_fallback():
    """Top1 + Top2 folder 都 miss → AVDBS fallback 命中"""
    from core.scrapers.actress.gfriends import lookup_gfriends, CDN_BASE, FALLBACK_FOLDER

    with patch('requests.head') as mock_head:
        miss_resp = MagicMock(status_code=404)
        hit_resp = MagicMock(status_code=200)
        # Top1 (7-S1): {name}.jpg miss, AI-Fix miss
        # Top2 (8-Ideapocket): {name}.jpg miss, AI-Fix miss
        # AVDBS: {name}.jpg hit
        mock_head.side_effect = [
            miss_resp, miss_resp,  # 7-S1: miss + AI-Fix miss
            miss_resp, miss_resp,  # 8-Ideapocket: miss + AI-Fix miss
            hit_resp,              # AVDBS: hit
        ]

        result = lookup_gfriends("桜空もも", makers=["S1", "IdeaPocket"])

        assert result is not None
        assert CDN_BASE in result
        assert FALLBACK_FOLDER in result
        assert "桜空もも" in result


def test_lookup_gfriends_all_miss():
    """全部 folder 都非 200 → 回傳 None"""
    from core.scrapers.actress.gfriends import lookup_gfriends

    with patch('requests.head') as mock_head:
        miss_resp = MagicMock(status_code=404)
        # Top1 (7-S1): miss + AI-Fix miss
        # AVDBS: miss + AI-Fix miss
        mock_head.side_effect = [
            miss_resp, miss_resp,  # 7-S1: miss + AI-Fix miss
            miss_resp, miss_resp,  # AVDBS: miss + AI-Fix miss
        ]

        result = lookup_gfriends("不存在女優", makers=["S1"])

        assert result is None


def test_lookup_gfriends_ai_fix_prefix():
    """{name}.jpg 非 200，AI-Fix-{name}.jpg 命中 → 回傳 AI-Fix URL"""
    from core.scrapers.actress.gfriends import lookup_gfriends, CDN_BASE

    with patch('requests.head') as mock_head:
        miss_resp = MagicMock(status_code=403)
        hit_resp = MagicMock(status_code=200)
        # Top1 (7-S1): {name}.jpg miss, AI-Fix hit
        mock_head.side_effect = [miss_resp, hit_resp]

        result = lookup_gfriends("桜空もも", makers=["S1"])

        assert result is not None
        assert CDN_BASE in result
        assert "AI-Fix-桜空もも" in result


def test_lookup_gfriends_timeout():
    """requests.head 拋出 Timeout → 回傳 None（fail-open）"""
    from core.scrapers.actress.gfriends import lookup_gfriends
    import requests

    with patch('requests.head') as mock_head:
        mock_head.side_effect = requests.exceptions.Timeout()

        result = lookup_gfriends("桜空もも", makers=["S1"])

        assert result is None


# ============================================================================
# Graphis Profile 解析測試
# ============================================================================

def test_parse_graphis_profile_full():
    """完整 model.php HTML → 所有欄位正確解析"""
    from core.scrapers.actress.graphis import _parse_graphis_profile

    result = _parse_graphis_profile(MODEL_PHP_HTML)

    assert result['name_en'] == 'Momo Sakurazora'
    assert result['age'] == 28
    assert result['height'] == '160cm'
    assert result['cup'] == 'G'
    assert result['bust'] == '90cm'
    assert result['waist'] == '55cm'
    assert result['hip'] == '86cm'
    assert result['hobby'] == 'ゲーム'


def test_parse_graphis_profile_bwh_regex():
    """BWH regex 解析：有 cup 與無 cup 兩種情境"""
    from core.scrapers.actress.graphis import _parse_graphis_profile

    # With cup: B86(E) W61 H88
    html_with_cup = """
    <html>
        <p class="pan-link">TOP > モデル一覧 > 神宮寺ナオ/Nao Jinguji</p>
        <li class="model-prof">
          <ul>
            <li><span>スリーサイズ /BWH：</span><span>B86(E) W61 H88</span></li>
          </ul>
        </li>
    </html>
    """
    result_with_cup = _parse_graphis_profile(html_with_cup)
    assert result_with_cup['bust'] == '86cm'
    assert result_with_cup['cup'] == 'E'
    assert result_with_cup['waist'] == '61cm'
    assert result_with_cup['hip'] == '88cm'

    # Without cup: B86 W61 H88
    html_no_cup = """
    <html>
        <li class="model-prof">
          <ul>
            <li><span>スリーサイズ /BWH：</span><span>B86 W61 H88</span></li>
          </ul>
        </li>
    </html>
    """
    result_no_cup = _parse_graphis_profile(html_no_cup)
    assert result_no_cup['bust'] == '86cm'
    assert result_no_cup['cup'] == ''  # No cup info
    assert result_no_cup['waist'] == '61cm'
    assert result_no_cup['hip'] == '88cm'


def test_scrape_graphis_photo_with_profile():
    """listing + model.php 雙 mock → profile 欄位存在於回傳值"""
    from core.scrapers.actress.graphis import scrape_graphis_photo

    with patch('requests.get') as mock_get:
        listing_resp = MagicMock(status_code=200, text=_LISTING_HTML)
        listing_resp.raise_for_status = MagicMock()
        model_resp = MagicMock(status_code=200, text=MODEL_PHP_HTML)
        mock_get.side_effect = [listing_resp, model_resp]

        result = scrape_graphis_photo("桜空もも")

        assert result is not None
        assert result['name'] == '桜空もも'
        assert result['name_en'] == 'Momo Sakurazora'
        assert result['age'] == 28
        assert result['height'] == '160cm'
        assert result['cup'] == 'G'
        assert result['bust'] == '90cm'
        assert result['waist'] == '55cm'
        assert result['hip'] == '86cm'
        assert result['hobby'] == 'ゲーム'


def test_scrape_graphis_photo_profile_fail():
    """model.php 回傳 500 → 仍回傳圖片 URL，profile 欄位為空"""
    from core.scrapers.actress.graphis import scrape_graphis_photo

    with patch('requests.get') as mock_get:
        listing_resp = MagicMock(status_code=200, text=_LISTING_HTML)
        listing_resp.raise_for_status = MagicMock()
        model_resp = MagicMock(status_code=500, text='')
        mock_get.side_effect = [listing_resp, model_resp]

        result = scrape_graphis_photo("桜空もも")

        assert result is not None
        assert '/prof.jpg' in result['prof_url']
        assert '/model.jpg' in result['backdrop_url']
        # Profile fields should be empty (model.php failed)
        assert result['name_en'] == ''
        assert result['age'] is None
        assert result['height'] == ''
        assert result['cup'] == ''


# ============================================================================
# get_actress_profile 合併邏輯測試（T2/T3 新增）
# ============================================================================

def _make_graphis_result(name="桜空もも", **overrides):
    """Helper: 建立完整的 graphis mock 回傳值（含所有欄位）"""
    base = {
        'name': name,
        'prof_url': 'https://graphis.ne.jp/prof.jpg',
        'backdrop_url': 'https://graphis.ne.jp/model.jpg',
        'name_en': 'Momo Sakurazora',
        'birth': '1997-12-03',  # TD-1: birth 1997-12-03 + frozen 2026-04-11 → age 28
        'age': 28,
        'height': '160cm',
        'cup': 'G',
        'bust': '90cm',
        'waist': '55cm',
        'hip': '86cm',
        'hobby': 'ゲーム',
    }
    base.update(overrides)
    return base


def _make_javbus_result(name="桜空もも", **overrides):
    """Helper: 建立完整的 javbus mock 回傳值"""
    base = {
        'name': name,
        'img': 'https://javbus.com/img.jpg',
        'birth': '1996-12-03',
        'age': 27,
        'height': '155cm',
        'cup': 'F',
        'bust': '88cm',
        'waist': '58cm',
        'hip': '85cm',
        'hometown': '東京都',
        'hobby': '読書',
    }
    base.update(overrides)
    return base


def test_get_actress_profile_gfriends_wins():
    """gfriends 圖片勝出：graphis 無 prof_url 時，gfriends 應成為 photo cascade 的 winner。
    T4.3 note: orchestrator photo cascade = graphis prof_url → gfriends → wiki → minnano.
    To let gfriends win, graphis must have prof_url=None."""
    from core.scrapers.actress.orchestrator import get_actress_profile, _cache

    gfriends_url = 'https://cdn.jsdelivr.net/gh/gfriends/gfriends@master/Content/7-S1/桜空もも.jpg'

    with patch('core.scrapers.actress.minnano_av.scrape_minnano_av', return_value=None), \
         patch('core.scrapers.actress.wiki_ja.scrape_wiki_ja', return_value=None), \
         patch('core.scrapers.actress.graphis.scrape_graphis_photo', return_value=_make_graphis_result(prof_url=None)), \
         patch('core.scrapers.actress.javbus.scrape_actress_profile', return_value=_make_javbus_result()), \
         patch('core.scrapers.actress.gfriends.lookup_gfriends', return_value=gfriends_url):

        result = get_actress_profile("桜空もも", makers=['S1'])

        assert result is not None
        # gfriends wins photo cascade (graphis has no prof_url, javbus is ignored)
        assert result['img'] == gfriends_url
        # Backdrop still comes from graphis
        assert result['backdrop'] == 'https://graphis.ne.jp/model.jpg'


def test_get_actress_profile_graphis_text_wins():
    """graphis 文字欄位優先（age/height/cup）
    NOTE (T4.2 semantic shift): Post-T3 orchestrator has no javbus route.
    After T4.3 adds minnano/wiki mocks → None, graphis wins the C1 cascade as the
    only available text source (not "beats javbus" anymore, just "graphis fallback").
    age == 28 is still correct: _compute_age_from_birth('1997-12-03') under frozen 2026-04-11.
    """
    from core.scrapers.actress.orchestrator import get_actress_profile, _cache

    with patch('core.scrapers.actress.minnano_av.scrape_minnano_av', return_value=None), \
         patch('core.scrapers.actress.wiki_ja.scrape_wiki_ja', return_value=None), \
         patch('core.scrapers.actress.graphis.scrape_graphis_photo', return_value=_make_graphis_result(age=28, height='160cm', cup='G')), \
         patch('core.scrapers.actress.javbus.scrape_actress_profile', return_value=_make_javbus_result(age=27, height='155cm', cup='F')), \
         patch('core.scrapers.actress.gfriends.lookup_gfriends', return_value=None):

        result = get_actress_profile("桜空もも")

        assert result is not None
        # Graphis text wins
        assert result['age'] == 28
        assert result['height'] == '160cm'
        assert result['cup'] == 'G'


def test_get_actress_profile_name_en():
    """graphis name_en 正確傳遞到最終結果"""
    from core.scrapers.actress.orchestrator import get_actress_profile, _cache

    with patch('core.scrapers.actress.minnano_av.scrape_minnano_av', return_value=None), \
         patch('core.scrapers.actress.wiki_ja.scrape_wiki_ja', return_value=None), \
         patch('core.scrapers.actress.graphis.scrape_graphis_photo', return_value=_make_graphis_result(name_en='Momo Sakurazora')), \
         patch('core.scrapers.actress.javbus.scrape_actress_profile', return_value=_make_javbus_result()), \
         patch('core.scrapers.actress.gfriends.lookup_gfriends', return_value=None):

        result = get_actress_profile("桜空もも")

        assert result is not None
        assert result.get('name_en') == 'Momo Sakurazora'


def test_get_actress_profile_birth_javbus_only():
    """T4.3 semantic: In new orchestrator (T3+), javbus is schema-only; birth/hometown come
    from the cascade winner (graphis here). birth comes from graphis ('1997-12-03');
    hometown is None because graphis has no hometown field and javbus is ignored."""
    from core.scrapers.actress.orchestrator import get_actress_profile, _cache

    # Graphis result has birth='1997-12-03' (added by T4.2) but no hometown
    graphis = _make_graphis_result()

    javbus = _make_javbus_result(birth='1996-12-03', hometown='東京都')

    with patch('core.scrapers.actress.minnano_av.scrape_minnano_av', return_value=None), \
         patch('core.scrapers.actress.wiki_ja.scrape_wiki_ja', return_value=None), \
         patch('core.scrapers.actress.graphis.scrape_graphis_photo', return_value=graphis), \
         patch('core.scrapers.actress.javbus.scrape_actress_profile', return_value=javbus), \
         patch('core.scrapers.actress.gfriends.lookup_gfriends', return_value=None):

        result = get_actress_profile("桜空もも")

        assert result is not None
        # birth comes from graphis cascade winner (javbus ignored)
        assert result.get('birth') == '1997-12-03'
        # hometown is None: graphis has no hometown, javbus is ignored
        assert result.get('hometown') is None


def test_get_actress_profile_gfriends_only():
    """gfriends 有圖但 javbus/graphis 都沒資料 → 仍回傳 minimal profile"""
    from core.scrapers.actress.orchestrator import get_actress_profile, _cache

    gfriends_url = 'https://cdn.jsdelivr.net/gh/gfriends/gfriends@master/Content/7-S1/桜空もも.jpg'

    with patch('core.scrapers.actress.minnano_av.scrape_minnano_av', return_value=None), \
         patch('core.scrapers.actress.wiki_ja.scrape_wiki_ja', return_value=None), \
         patch('core.scrapers.actress.graphis.scrape_graphis_photo', return_value=None), \
         patch('core.scrapers.actress.javbus.scrape_actress_profile', return_value=None), \
         patch('core.scrapers.actress.gfriends.lookup_gfriends', return_value=gfriends_url):

        result = get_actress_profile("桜空もも", makers=['S1'])

        assert result is not None
        # Bug 2 fix: name falls back to queried name arg when all text sources are None
        assert result['name'] == '桜空もも'
        assert result['img'] == gfriends_url


# ============================================================================
# Router makers 傳遞測試
# ============================================================================

def test_search_api_passes_makers_to_profile(client):
    """REST /api/search 路徑：_extract_top_makers 的結果應傳給 get_actress_profile"""
    def mock_smart_search(q, **kwargs):
        return [
            {'number': 'SONE-205', 'actors': ['桜空もも']},
            {'number': 'SONE-180', 'actors': ['桜空もも']},
            {'number': 'SONE-162', 'actors': ['桜空もも']},
        ]

    mock_profile = MagicMock(return_value={
        'name': '桜空もも',
        'img': 'https://graphis.ne.jp/prof.jpg',
        'backdrop': 'https://graphis.ne.jp/model.jpg',
    })

    # Patch smart_search in the router's own namespace (it's imported at module load time)
    with patch('web.routers.search.smart_search', side_effect=mock_smart_search), \
         patch('core.scrapers.actress.orchestrator.get_actress_profile', mock_profile):

        resp = client.get("/api/search?q=桜空もも")
        data = resp.json()

        assert data['success'] is True
        # get_actress_profile should have been called with makers kwarg
        assert mock_profile.called
        call_kwargs = mock_profile.call_args
        # Should have been called with makers=['S1']
        # (SONE prefix maps to 'S1' in maker_mapping.json)
        makers_arg = call_kwargs.kwargs.get('makers')
        assert makers_arg is not None
        assert isinstance(makers_arg, list)
        assert 'S1' in makers_arg


def test_sse_passes_makers_to_profile(client):
    """SSE /api/search/stream 路徑：_extract_top_makers 的結果應傳給 get_actress_profile"""
    def mock_smart_search(q, **kwargs):
        return [
            {'number': 'SONE-205', 'actors': ['桜空もも']},
            {'number': 'SONE-180', 'actors': ['桜空もも']},
            {'number': 'SONE-162', 'actors': ['桜空もも']},
        ]

    mock_profile = MagicMock(return_value={
        'name': '桜空もも',
        'img': 'https://graphis.ne.jp/prof.jpg',
        'backdrop': 'https://graphis.ne.jp/model.jpg',
    })

    with patch('web.routers.search.smart_search', side_effect=mock_smart_search), \
         patch('core.scrapers.actress.orchestrator.get_actress_profile', mock_profile):

        response = client.get('/api/search/stream?q=桜空もも')

        # SSE should have triggered get_actress_profile
        assert mock_profile.called
        call_kwargs = mock_profile.call_args
        # Should have been called with makers=['S1']
        # (SONE prefix maps to 'S1' in maker_mapping.json)
        makers_arg = call_kwargs.kwargs.get('makers')
        assert makers_arg is not None
        assert isinstance(makers_arg, list)
        assert 'S1' in makers_arg
