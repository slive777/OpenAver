"""
63c-1 routing 測試：_MetatubeShim / validate_source_id / auto fan-out / explicit dispatch
/ strip_internal_nfo_keys / API echo regression guard

Mock patch target：core.scraper.metatube_state（使用端，非定義端，Gotcha §1）。
"""
import time
import threading
import pytest
from unittest.mock import patch, MagicMock, PropertyMock, call

from fastapi.testclient import TestClient

from core.scraper import (
    search_jav,
    _MetatubeShim,
    strip_internal_nfo_keys,
    _INTERNAL_NFO_KEYS,
)
from core.scrapers.models import Video
from core.scrapers.utils import SOURCE_ORDER


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_video(source: str, number: str = "TEST-001", summary: str = "", rating=None) -> Video:
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


def _mock_state(is_connected=True, base_url="http://mt:8080", token="tok",
                avail_map=None):
    """Build a mock metatube_state object."""
    state = MagicMock()
    type(state).is_connected = PropertyMock(return_value=is_connected)
    type(state).base_url = PropertyMock(return_value=base_url)
    type(state).token = PropertyMock(return_value=token)
    state.availability_map.return_value = avail_map or {}
    return state


# ===========================================================================
# 1. strip_internal_nfo_keys
# ===========================================================================

class TestStripInternalNfoKeys:
    def test_removes_summary_and_rating(self):
        d = {'_source': 'javbus', '_summary': 'some text', '_rating': 4.5, 'title': 'T'}
        result = strip_internal_nfo_keys(d)
        assert '_summary' not in result
        assert '_rating' not in result

    def test_keeps_source_mode_variant_ids(self):
        d = {'_source': 'javbus', '_mode': 'exact', '_all_variant_ids': ['a'], '_summary': 'x'}
        result = strip_internal_nfo_keys(d)
        assert result['_source'] == 'javbus'
        assert result['_mode'] == 'exact'
        # _all_variant_ids 不在 _INTERNAL_NFO_KEYS 中 → strip 不誤刪該欄位（後方互換守衛）
        assert result['_all_variant_ids'] == ['a']

    def test_idempotent_no_internal_keys(self):
        d = {'title': 'T', '_source': 'javbus'}
        result = strip_internal_nfo_keys(d)
        assert result == d

    def test_returns_copy_not_same_object(self):
        d = {'_summary': 'x', 'title': 'T'}
        result = strip_internal_nfo_keys(d)
        assert result is not d

    def test_constant_tuple_contents(self):
        assert '_summary' in _INTERNAL_NFO_KEYS
        assert '_rating' in _INTERNAL_NFO_KEYS
        assert '_source' not in _INTERNAL_NFO_KEYS


# ===========================================================================
# 2. auto 路徑：metatube provider enabled + available → shim 被建立並呼叫
# ===========================================================================

@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch):
    """跳過 rate_limit / REQUEST_DELAY sleep"""
    monkeypatch.setattr("core.scraper.time.sleep", lambda *a: None)


class TestAutoFanOut:

    @pytest.fixture(autouse=True)
    def _isolate_builtin_sources(self, monkeypatch):
        """隔離 get_enabled_source_ids：只回 javbus + metatube:FANZA（user order）。

        注意：63c 改後 search_jav auto 內部直接呼叫
        get_enabled_source_ids(availability_map=...) 而非無參數版本，
        所以 monkeypatch 要讓帶 availability_map kwarg 也能正常回傳。
        """
        def _mock_enabled(availability_map=None):
            # 模擬 user order：metatube:FANZA 在 javbus 前
            return ['metatube:FANZA', 'javbus']

        monkeypatch.setattr("core.scraper.get_enabled_source_ids", _mock_enabled)

    def test_auto_available_shim_called(self, monkeypatch):
        """auto + metatube:FANZA enabled+available → shim.search 被呼叫"""
        mock_state = _mock_state(
            avail_map={'metatube:FANZA': True},
        )
        monkeypatch.setattr("core.scraper.metatube_state", mock_state)

        mt_video = _make_video("metatube:FANZA", "ABF-001", summary="plot", rating=4.2)
        shim_search_mock = MagicMock(return_value=mt_video)

        with patch("core.scraper._MetatubeShim.search", shim_search_mock):
            with patch("core.scrapers.javbus.JavBusScraper.search", return_value=None):
                result = search_jav("ABF-001", source='auto')

        shim_search_mock.assert_called_once_with("ABF-001")
        assert result is not None
        assert result['_source'] == 'metatube:FANZA'

    def test_auto_result_contains_summary_and_rating(self, monkeypatch):
        """auto 路徑 metatube → result 含 _summary / _rating"""
        mock_state = _mock_state(avail_map={'metatube:FANZA': True})
        monkeypatch.setattr("core.scraper.metatube_state", mock_state)

        mt_video = _make_video("metatube:FANZA", "ABF-001", summary="test summary", rating=3.7)

        with patch("core.scraper._MetatubeShim.search", return_value=mt_video):
            with patch("core.scrapers.javbus.JavBusScraper.search", return_value=None):
                result = search_jav("ABF-001", source='auto')

        assert result is not None
        assert result['_summary'] == 'test summary'
        assert result['_rating'] == 3.7

    def test_auto_builtin_result_summary_empty_rating_none(self, monkeypatch):
        """auto 路徑 builtin 來源 → _summary='' / _rating=None（builtin Video 預設）"""
        mock_state = _mock_state(avail_map={'metatube:FANZA': False})
        monkeypatch.setattr("core.scraper.metatube_state", mock_state)

        javbus_video = _make_video("javbus", "SONE-205")  # summary='', rating=None by default

        with patch("core.scraper._MetatubeShim.search", return_value=None):
            with patch("core.scrapers.javbus.JavBusScraper.search", return_value=javbus_video):
                result = search_jav("SONE-205", source='auto')

        assert result is not None
        assert result.get('_summary', '') == ''
        assert result.get('_rating') is None

    def test_auto_unavailable_shim_not_called(self, monkeypatch):
        """auto + metatube unavailable（availability_map False + not in enabled_sids）→ shim 不呼叫

        get_enabled_source_ids(availability_map) 排除不可達的 metatube provider。
        這裡 monkeypatch enabled 只回 ['javbus']（metatube:FANZA 被 gate 掉）。
        """
        def _mock_enabled_no_mt(availability_map=None):
            return ['javbus']  # gate 已排除 metatube

        monkeypatch.setattr("core.scraper.get_enabled_source_ids", _mock_enabled_no_mt)

        mock_state = _mock_state(avail_map={'metatube:FANZA': False})
        monkeypatch.setattr("core.scraper.metatube_state", mock_state)

        shim_search_mock = MagicMock(return_value=None)
        javbus_video = _make_video("javbus", "SONE-205")

        with patch("core.scraper._MetatubeShim.search", shim_search_mock):
            with patch("core.scrapers.javbus.JavBusScraper.search", return_value=javbus_video):
                result = search_jav("SONE-205", source='auto')

        shim_search_mock.assert_not_called()


# ===========================================================================
# 3. explicit dispatch
# ===========================================================================

class TestExplicitDispatch:

    def test_explicit_metatube_shim_called_result_wins(self, monkeypatch):
        """explicit source='metatube:FANZA' → shim.search 呼叫，結果整包贏"""
        mock_state = _mock_state(avail_map={'metatube:FANZA': True})
        monkeypatch.setattr("core.scraper.metatube_state", mock_state)

        mt_video = _make_video("metatube:FANZA", "ABF-001", summary="s", rating=4.0)

        with patch("core.scraper._MetatubeShim.search", return_value=mt_video):
            result = search_jav("ABF-001", source='metatube:FANZA')

        assert result is not None
        assert result['_source'] == 'metatube:FANZA'
        assert result['_summary'] == 's'
        assert result['_rating'] == 4.0

    def test_explicit_metatube_shim_returns_none(self, monkeypatch):
        """explicit + shim.search 回 None → search_jav 回 None"""
        mock_state = _mock_state(avail_map={'metatube:FANZA': True})
        monkeypatch.setattr("core.scraper.metatube_state", mock_state)

        with patch("core.scraper._MetatubeShim.search", return_value=None):
            result = search_jav("ABF-001", source='metatube:FANZA')

        assert result is None


# ===========================================================================
# 4. _MetatubeShim error handling
# ===========================================================================

class TestMetatubeShimErrors:
    """測試 _MetatubeShim 內部 error handling（直接單元測試 shim.search）"""

    def _make_shim(self, mock_client=None):
        shim = _MetatubeShim.__new__(_MetatubeShim)
        shim.source = 'metatube:FANZA'
        shim._provider = 'FANZA'
        shim._client = mock_client or MagicMock()
        return shim

    def test_unavailable_mark_failed_and_reraise(self):
        """MetatubeUnavailable → mark_failed 被呼叫 + 異常 re-raise"""
        from core.metatube.errors import MetatubeUnavailable
        shim = self._make_shim()
        shim._client.search.side_effect = MetatubeUnavailable("server down")

        with patch("core.scraper.metatube_state") as mock_state:
            with pytest.raises(MetatubeUnavailable):
                shim.search("ABF-001")
            mock_state.mark_failed.assert_called_once_with('metatube:FANZA')
            mock_state.mark_available.assert_not_called()

    def test_notfound_no_mark_failed_returns_none(self):
        """MetatubeNotFound → mark_failed 不呼叫，回 None"""
        from core.metatube.errors import MetatubeNotFound
        shim = self._make_shim()
        shim._client.search.side_effect = MetatubeNotFound("not found")

        with patch("core.scraper.metatube_state") as mock_state:
            result = shim.search("ABF-001")

        assert result is None
        mock_state.mark_failed.assert_not_called()

    def test_auth_error_no_mark_failed_returns_none(self):
        """MetatubeAuthError → mark_failed 不呼叫，回 None"""
        from core.metatube.errors import MetatubeAuthError
        shim = self._make_shim()
        shim._client.search.side_effect = MetatubeAuthError("bad token")

        with patch("core.scraper.metatube_state") as mock_state:
            result = shim.search("ABF-001")

        assert result is None
        mock_state.mark_failed.assert_not_called()

    def test_generic_exception_returns_none(self):
        """其他 Exception → logger.exception，回 None（不 mark_failed）"""
        shim = self._make_shim()
        shim._client.search.side_effect = RuntimeError("unexpected")

        with patch("core.scraper.metatube_state") as mock_state:
            result = shim.search("ABF-001")

        assert result is None
        mock_state.mark_failed.assert_not_called()

    def test_unavailable_in_auto_fanout_continue(self, monkeypatch):
        """auto fan-out：shim.search 拋 MetatubeUnavailable → auto fan-out 繼續，javbus 結果勝出。

        注意：此測試 mock _MetatubeShim.search 整個方法（side_effect raises），
        所以內部 mark_failed 不被真正觸發（mock 已替換）。
        這裡驗收的是 fan-out 的 continue 行為（其他 scraper 繼續執行），
        mark_failed 本身的行為在 TestMetatubeShimErrors 的 unit test 中獨立驗收。
        """
        from core.metatube.errors import MetatubeUnavailable

        def _mock_enabled(availability_map=None):
            return ['metatube:FANZA', 'javbus']

        monkeypatch.setattr("core.scraper.get_enabled_source_ids", _mock_enabled)

        mock_state = _mock_state(avail_map={'metatube:FANZA': True})
        monkeypatch.setattr("core.scraper.metatube_state", mock_state)

        javbus_video = _make_video("javbus", "SONE-205")

        # shim 拋 Unavailable，javbus 繼續回結果（驗 fan-out continue 不中斷）
        with patch("core.scraper._MetatubeShim.search", side_effect=MetatubeUnavailable("down")):
            with patch("core.scrapers.javbus.JavBusScraper.search", return_value=javbus_video):
                result = search_jav("SONE-205", source='auto')

        assert result is not None
        assert result['_source'] == 'javbus'


# ===========================================================================
# 5. 並行 fan-out 確定性 merge 測試
# ===========================================================================

class TestParallelFanOutOrdering:
    """驗證 ThreadPoolExecutor 按 user order 收（submit 順序），非 as_completed 順序"""

    def test_two_shims_user_order_preserved(self, monkeypatch):
        """shim-A 較慢、shim-B 較快，enabled_sids 中 A 在前 → all_data key 順序 A,B"""
        barrier = threading.Event()

        def slow_search_a(number):
            barrier.wait(timeout=2)
            return _make_video("metatube:A", number)

        def fast_search_b(number):
            barrier.set()
            return _make_video("metatube:B", number)

        # Mock two separate shims
        shim_a = MagicMock()
        shim_a.source = 'metatube:A'
        shim_a.search.side_effect = slow_search_a

        shim_b = MagicMock()
        shim_b.source = 'metatube:B'
        shim_b.search.side_effect = fast_search_b

        def _mock_enabled(availability_map=None):
            return ['metatube:A', 'metatube:B']

        monkeypatch.setattr("core.scraper.get_enabled_source_ids", _mock_enabled)

        mock_state = _mock_state(avail_map={'metatube:A': True, 'metatube:B': True})
        monkeypatch.setattr("core.scraper.metatube_state", mock_state)

        factory_calls = []

        def mock_factory(pname, url, tok):
            if pname == 'A':
                return shim_a
            else:
                return shim_b

        # Patch _MetatubeShim.__init__ to return our pre-built shims
        with patch("core.scraper._MetatubeShim") as MockShim:
            MockShim.side_effect = lambda pname, url, tok: shim_a if pname == 'A' else shim_b
            result = search_jav("TEST-001", source='auto')

        assert result is not None
        # all_data rebuild 按 user order (A, B) → merge winner = A（user order first）
        assert result['_source'] == 'metatube:A'

    def test_interleaved_order_metatube_before_builtin(self, monkeypatch):
        """enabled_sids = ['metatube:A', 'javbus', 'metatube:B']
        → merged all_data key order = metatube:A, javbus, metatube:B
        (metatube-A merge priority 高於 javbus，驗 user-drag 排序不被反轉)
        """
        def _mock_enabled(availability_map=None):
            return ['metatube:A', 'javbus', 'metatube:B']

        monkeypatch.setattr("core.scraper.get_enabled_source_ids", _mock_enabled)

        mock_state = _mock_state(avail_map={'metatube:A': True, 'metatube:B': True})
        monkeypatch.setattr("core.scraper.metatube_state", mock_state)

        video_a = _make_video("metatube:A", "TEST-001")
        video_javbus = _make_video("javbus", "TEST-001")
        video_b = _make_video("metatube:B", "TEST-001")

        def make_shim(pname, url, tok):
            shim = MagicMock()
            shim.source = f'metatube:{pname}'
            if pname == 'A':
                shim.search.return_value = video_a
            else:
                shim.search.return_value = video_b
            return shim

        with patch("core.scraper._MetatubeShim", side_effect=make_shim):
            with patch("core.scrapers.javbus.JavBusScraper.search", return_value=video_javbus):
                result = search_jav("TEST-001", source='auto')

        # merge winner = first key in user order = metatube:A
        assert result is not None
        assert result['_source'] == 'metatube:A'


# ===========================================================================
# 6. API echo strip regression guard（integration TestClient）
# ===========================================================================

class TestApiEchoStrip:
    """spec §161 enforcement：API responses must not contain _summary / _rating"""

    @pytest.fixture
    def client(self):
        from web.app import app
        return TestClient(app)

    def _mock_search_result(self):
        """Simulate a search result dict WITH internal keys (as if from search_jav)"""
        return {
            'title': 'Test Movie',
            '_source': 'metatube:FANZA',
            '_mode': 'exact',
            '_summary': 'this must not appear',
            '_rating': 4.5,
            'number': 'ABF-001',
            'date': '2024-01-01',
        }

    def test_get_api_search_no_internal_nfo_keys(self, client, monkeypatch):
        """GET /api/search response body never contains _summary / _rating / summary / rating"""
        mock_result = self._mock_search_result()

        # search_jav_single_source is imported inline inside the route handler,
        # so patch at the definition (usage) end: core.scraper.search_jav_single_source
        with patch("core.scraper.search_jav_single_source", return_value=mock_result):
            with patch("core.config.load_config", return_value={
                'search': {
                    'proxy_url': '',
                    'uncensored_mode_enabled': False,
                }
            }):
                resp = client.get("/api/search", params={
                    "q": "ABF-001",
                    "mode": "exact",
                    "source": "metatube:FANZA"
                })

        assert resp.status_code == 200
        data = resp.json()
        items = data.get('data', [])
        assert len(items) > 0
        for item in items:
            assert '_summary' not in item, "_summary must not appear in API response"
            assert '_rating' not in item, "_rating must not appear in API response"
            # canonical keys also must not appear (to_legacy_dict excludes them, double check)
            assert 'summary' not in item
            assert 'rating' not in item

    def test_post_rescrape_preview_no_internal_nfo_keys(self, client, monkeypatch):
        """POST /api/rescrape/preview response never contains _summary / _rating"""
        mock_result = self._mock_search_result()

        with patch("web.routers.scraper.search_jav_single_source", return_value=mock_result):
            with patch("core.config.load_config", return_value={
                'search': {
                    'proxy_url': '',
                    'uncensored_mode_enabled': False,
                }
            }):
                resp = client.post("/api/rescrape/preview", json={
                    "number": "ABF-001",
                    "source": "metatube:FANZA",
                })

        assert resp.status_code == 200
        data = resp.json()
        assert '_summary' not in data, "_summary must not appear in rescrape/preview response"
        assert '_rating' not in data, "_rating must not appear in rescrape/preview response"
        assert 'summary' not in data
        assert 'rating' not in data


# ===========================================================================
# 7. scanner auto coverage（smart_search → search_jav('auto') 含 metatube entry）
# ===========================================================================

class TestScannerAutoConverage:
    """spec 驗收：scanner 走 smart_search → search_jav('auto')，metatube 自動進入 fan-out"""

    def test_smart_search_includes_metatube_entry(self, monkeypatch):
        """mock metatube enabled+available，cascade 依優先序串接直打，metatube 在 enabled_sids 中參與。

        新 cascade（spec-85 B1，CD-85-1/2）：依 get_enabled_source_ids 優先序串接直打，
        metatube provider 在 availability_map 中 available → 進入 cascade 並被呼叫。
        search_jav_single_source mock 讓 metatube:FANZA call 回 mt_video。
        """
        from core.scraper import smart_search

        def _mock_enabled(availability_map=None):
            return ['metatube:FANZA', 'javbus']

        monkeypatch.setattr("core.scraper.get_enabled_source_ids", _mock_enabled)

        mock_state = _mock_state(avail_map={'metatube:FANZA': True})
        monkeypatch.setattr("core.scraper.metatube_state", mock_state)

        mt_result = {'number': 'ABF-001', 'title': 'T', '_source': 'metatube:FANZA'}

        def _single_source(number, source, proxy_url=''):
            if source == 'metatube:FANZA':
                return mt_result
            return None

        with patch("core.scraper.search_jav_single_source", side_effect=_single_source) as mock_ss:
            results = smart_search("ABF-001")

        mock_ss.assert_called()
        assert any(r.get('_source') == 'metatube:FANZA' for r in results)
