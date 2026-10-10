"""
63c-1 routing 測試：_MetatubeShim / validate_source_id / auto fan-out / explicit dispatch
/ API echo preserves NFO carriers

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
                avail_map=None, generation=1):
    """Build a mock metatube_state object."""
    state = MagicMock()
    type(state).is_connected = PropertyMock(return_value=is_connected)
    type(state).base_url = PropertyMock(return_value=base_url)
    type(state).token = PropertyMock(return_value=token)
    type(state).generation = PropertyMock(return_value=generation)
    state.availability_map.return_value = avail_map or {}
    state.routing_availability_map.return_value = avail_map or {}
    # TASK-130b-T6：search_jav 建 shim 時改吃單鎖原子快照 probe_snapshot()
    # （names 已去掉 'metatube:' 前綴，見 core/metatube/state.py:222）。
    state.probe_snapshot.return_value = (
        [k.split(":", 1)[1] for k in (avail_map or {})],
        generation,
        base_url or "",
        token or "",
    )
    return state


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

    def test_explicit_source_passthrough_preserves_preview_cover_url(self, monkeypatch):
        """TASK-113c-T3b DoD-2③：source != 'auto' 單一來源直通不走 merge_results()，
        preview_cover_url 與 cover_url 皆原封不動流到 to_legacy_dict()（不因繞過 merger
        而被清空）"""
        mock_state = _mock_state(avail_map={'metatube:FANZA': True})
        monkeypatch.setattr("core.scraper.metatube_state", mock_state)

        mt_video = Video(
            number="ABF-001",
            source="metatube:FANZA",
            cover_url="https://img.fanza.com/cover.jpg",
            preview_cover_url="http://mt:8080/v1/images/primary/FANZA/ABF-001?url=x&ratio=0&quality=100",
        )

        with patch("core.scraper._MetatubeShim.search", return_value=mt_video):
            result = search_jav("ABF-001", source='metatube:FANZA')

        assert result is not None
        assert result['cover'] == "https://img.fanza.com/cover.jpg"
        assert result['preview_cover_url'] == (
            "http://mt:8080/v1/images/primary/FANZA/ABF-001?url=x&ratio=0&quality=100"
        )


# ===========================================================================
# 4. _MetatubeShim error handling
# ===========================================================================

class TestMetatubeShimErrors:
    """測試 _MetatubeShim 內部 error handling（直接單元測試 shim.search）"""

    def _make_shim(self, mock_client=None, generation=None):
        shim = _MetatubeShim.__new__(_MetatubeShim)
        shim.source = 'metatube:FANZA'
        shim._provider = 'FANZA'
        # TASK-130b-T6：這個 helper 繞過 __init__，所以要自己補上 shim 建立時的
        # 連線世代（search() 的兩個狀態回寫都帶著它）。None = 不設圍欄。
        shim._generation = generation
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
            mock_state.mark_failed.assert_called_once_with('metatube:FANZA', generation=None)
            mock_state.mark_available.assert_not_called()

    @pytest.mark.parametrize("exc_name, msg", [
        ("MetatubeNotFound", "not found"),
        ("MetatubeAuthError", "bad token"),
        ("RuntimeError", "unexpected"),
    ])
    def test_notfound_no_mark_failed_returns_none(self, exc_name, msg):
        """查無／token 錯誤／一般例外 → mark_failed 不呼叫，回 None"""
        from core.metatube import errors
        exc_cls = {
            "MetatubeNotFound": errors.MetatubeNotFound,
            "MetatubeAuthError": errors.MetatubeAuthError,
            "RuntimeError": RuntimeError,
        }[exc_name]
        shim = self._make_shim()
        shim._client.search.side_effect = exc_cls(msg)

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

        def mock_factory(pname, url, tok, gen=None):
            if pname == 'A':
                return shim_a
            else:
                return shim_b

        # Patch _MetatubeShim.__init__ to return our pre-built shims
        with patch("core.scraper._MetatubeShim") as MockShim:
            MockShim.side_effect = lambda pname, url, tok, gen=None: shim_a if pname == 'A' else shim_b
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

        def make_shim(pname, url, tok, gen=None):
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
# 6. API echo preserves NFO carriers（integration TestClient）
# ===========================================================================

class TestApiEchoPreservesNfoCarriers:
    """147c-T1：API responses must preserve _summary / _rating carriers"""

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

    def test_get_api_search_preserves_internal_nfo_keys(self, client, monkeypatch):
        """GET /api/search response body preserves _summary / _rating; canonical keys absent"""
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
            assert item['_summary'] == 'this must not appear'
            assert item['_rating'] == 4.5
            # canonical keys also must not appear (to_legacy_dict excludes them, double check)
            assert 'summary' not in item
            assert 'rating' not in item

    def test_post_rescrape_preview_preserves_internal_nfo_keys(self, client, monkeypatch):
        """POST /api/rescrape/preview response preserves _summary / _rating"""
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
        assert data['_summary'] == 'this must not appear'
        assert data['_rating'] == 4.5
        assert 'summary' not in data
        assert 'rating' not in data

# ===========================================================================
# 7. scanner auto coverage（smart_search → search_jav('auto') 含 metatube entry）
# ===========================================================================

class TestScannerAutoConverage:
    """spec 驗收：scanner 走 smart_search → search_jav('auto')，metatube 自動進入 fan-out"""


def test_metatube_shim_exception_log_does_not_leak_credentials(caplog):
    """`_MetatubeShim.search()` 的 `logger.exception` 會把整個 traceback（含例外訊息）
    寫進 log——而這條路徑跑在**一般搜尋**上，不是只有管理員操作的 connect/probe。

    它的乾淨度來自 client 層例外訊息已 redacted（Codex 三審 P1 的根因修正）。
    這支獨立鎖在**這一層**：不靠「上游修好了就會傳播下來」，任何人日後在別處
    重新用完整 URL 組訊息，這裡就會紅。
    """
    import logging

    from core.metatube.errors import MetatubeProtocolError
    from core.scraper import _MetatubeShim

    shim = _MetatubeShim('FANZA', 'http://admin:S3cr3tPass@10.0.0.5:8900', 'tok_ABC123')
    with caplog.at_level(logging.ERROR, logger='OpenAver.core.scraper'):
        with patch.object(
            shim._client, 'search',
            side_effect=MetatubeProtocolError(
                'Response from 10.0.0.5:8900/v1/movies/FANZA/X is not a JSON object'
            ),
        ):
            shim.search('SSIS-001')

    assert 'metatube shim' in caplog.text  # 正向：這條 log 真的跑到了
    for secret in ('S3cr3tPass', 'admin@', 'tok_ABC123'):
        assert secret not in caplog.text, f"shim exception log 洩漏 {secret!r}"


# ===========================================================================
# 8. routing_availability_map behavior tests (TASK-130b-T3)
# ===========================================================================

def test_auto_fanout_uses_routing_map_expired_source_retried(monkeypatch):
    """auto fan-out 吃 routing_availability_map：冷卻過期 (routing=True, display=False) 來源會被重試。
    兩張 map 均為 False 則不被呼叫。"""
    from core import source_settings
    from core.scraper import search_jav

    # 提供真實 config 使 get_enabled_source_ids 真正執行 gate 判斷
    fake_config = {
        'sources': [
            {'id': 'javbus', 'type': 'builtin', 'enabled': True, 'order': 0, 'manual_only': False},
            {'id': 'metatube:FANZA', 'type': 'metatube', 'enabled': True, 'order': 1, 'manual_only': False},
        ]
    }
    monkeypatch.setattr(source_settings, "load_config", lambda: fake_config)

    # 1. 正向：availability_map 為 False 但 routing_availability_map 為 True（冷卻已過期）
    mock_state = _mock_state(
        avail_map={'metatube:FANZA': False},
    )
    mock_state.routing_availability_map.return_value = {'metatube:FANZA': True}
    monkeypatch.setattr("core.scraper.metatube_state", mock_state)

    mt_video = _make_video("metatube:FANZA", "ABF-001")
    shim_search_mock = MagicMock(return_value=mt_video)

    with patch("core.scraper._MetatubeShim.search", shim_search_mock):
        with patch("core.scrapers.javbus.JavBusScraper.search", return_value=None):
            result = search_jav("ABF-001", source='auto')

    shim_search_mock.assert_called_once_with("ABF-001")
    assert result is not None
    assert result['_source'] == 'metatube:FANZA'

    # 2. 反向：routing_availability_map 亦為 False → 不被呼叫
    mock_state_both_false = _mock_state(avail_map={'metatube:FANZA': False})
    mock_state_both_false.routing_availability_map.return_value = {'metatube:FANZA': False}
    monkeypatch.setattr("core.scraper.metatube_state", mock_state_both_false)

    shim_search_mock_2 = MagicMock(return_value=None)
    javbus_video = _make_video("javbus", "ABF-001")
    with patch("core.scraper._MetatubeShim.search", shim_search_mock_2):
        with patch("core.scrapers.javbus.JavBusScraper.search", return_value=javbus_video):
            result_2 = search_jav("ABF-001", source='auto')

    shim_search_mock_2.assert_not_called()
    assert result_2['_source'] == 'javbus'


def test_exact_cascade_uses_routing_map_expired_source_retried(monkeypatch):
    """smart_search exact cascade 吃 routing_availability_map：冷卻過期 (routing=True, display=False) 來源會被重試。
    兩張 map 均為 False 則不被呼叫。"""
    from core import source_settings
    from core.scraper import smart_search

    fake_config = {
        'sources': [
            {'id': 'metatube:FANZA', 'type': 'metatube', 'enabled': True, 'order': 0, 'manual_only': False},
            {'id': 'javbus', 'type': 'builtin', 'enabled': True, 'order': 1, 'manual_only': False},
        ]
    }
    monkeypatch.setattr(source_settings, "load_config", lambda: fake_config)

    # 1. 正向：availability_map 為 False 但 routing_availability_map 為 True
    mock_state = _mock_state(avail_map={'metatube:FANZA': False})
    mock_state.routing_availability_map.return_value = {'metatube:FANZA': True}
    monkeypatch.setattr("core.scraper.metatube_state", mock_state)

    mt_result = {'number': 'ABF-001', 'title': 'T', '_source': 'metatube:FANZA'}
    mock_ss = MagicMock(return_value=mt_result)

    with patch("core.scraper.search_jav_single_source", mock_ss):
        results = smart_search("ABF-001")

    mock_ss.assert_called_once_with('ABF-001', 'metatube:FANZA')
    assert len(results) == 1
    assert results[0]['_source'] == 'metatube:FANZA'

    # 2. 反向：兩張 map 皆為 False → metatube 被 gate 掉，直打 javbus
    mock_state_both_false = _mock_state(avail_map={'metatube:FANZA': False})
    mock_state_both_false.routing_availability_map.return_value = {'metatube:FANZA': False}
    monkeypatch.setattr("core.scraper.metatube_state", mock_state_both_false)

    def _single_source(number, source):
        if source == 'javbus':
            return {'number': 'ABF-001', 'title': 'T', '_source': 'javbus'}
        return None

    with patch("core.scraper.search_jav_single_source", side_effect=_single_source) as mock_ss_2:
        results_2 = smart_search("ABF-001")

    assert mock_ss_2.call_count == 1
    mock_ss_2.assert_called_once_with('ABF-001', 'javbus')
    assert len(results_2) == 1
    assert results_2[0]['_source'] == 'javbus'



# ===========================================================================
# 9. TASK-130b-T6：連線世代圍欄（Codex PR review P2）
#
# 不變式：
#   I-1  一顆 shim 的 base_url / token / generation 來自同一次鎖獲取
#   I-2  一顆 shim 的狀態回寫，只在「當前世代 == 建立時的世代」時生效
#
# 這幾支刻意用**真的** MetatubeConnectionState（不是 MagicMock）——圍欄的正確性
# 取決於 generation 的真實遞增行為，用假物件驗不出來。
# ===========================================================================

def _real_state_with_shim(monkeypatch, provider='FANZA'):
    """連上真 state、回傳 (state, 建 shim 用的 generation)。"""
    from core.metatube.state import MetatubeConnectionState
    state = MetatubeConnectionState()
    gen = state.connect('http://mt:8080', 'tok', [provider])
    monkeypatch.setattr('core.scraper.metatube_state', state)
    return state, gen


def test_stale_generation_shim_failure_does_not_poison_new_connection(monkeypatch):
    """使用者搜尋還在跑的時候按了重新連線 → 舊那次請求逾時回來，不得把剛連好的
    provider 又標成失敗（否則設定頁膠囊會灰五分鐘、那五分鐘內自動搜尋也少一家，
    而那是假訊息——重連其實成功了）。"""
    from core.metatube.errors import MetatubeUnavailable

    state, old_gen = _real_state_with_shim(monkeypatch)
    shim = _MetatubeShim('FANZA', 'http://mt:8080', 'tok', old_gen)
    shim._client = MagicMock()
    shim._client.search.side_effect = MetatubeUnavailable('server down')

    # 使用者按「重新連線」——世代前進，provider 回到乾淨的可用狀態
    new_gen = state.connect('http://mt:8080', 'tok', ['FANZA'])
    assert new_gen != old_gen

    # 舊那次請求現在才逾時回來
    with pytest.raises(MetatubeUnavailable):
        shim.search('ABF-001')

    assert state.is_available('metatube:FANZA') is True
    assert state._failed_at == {}


def test_stale_generation_shim_success_does_not_touch_new_connection(monkeypatch):
    """反方向的同一件事：舊連線的一次遲到成功，不得洗掉新連線上正確的失敗紀錄。

    使用者換了一台 metatube 伺服器、新那台的某家其實是壞的，卻因為舊那台的一個
    遲到回應而顯示正常 → 搜尋每次都去打它、每次都白等。"""
    state, old_gen = _real_state_with_shim(monkeypatch)
    shim = _MetatubeShim('FANZA', 'http://mt:8080', 'tok', old_gen)
    shim._client = MagicMock()
    shim._client.search.return_value = [{'id': 'X'}]
    shim._client.get_info.return_value = {'id': 'X'}

    # 換一台伺服器，新那台的 FANZA 被正確地標成失敗
    state.connect('http://mt2:9090', 'tok2', ['FANZA'])
    state.mark_failed('metatube:FANZA')
    assert state.is_available('metatube:FANZA') is False
    stamped = state._failed_at['metatube:FANZA']

    # 舊連線的請求現在才成功回來
    with patch('core.scraper.pick_movie_result', return_value={'id': 'X'}), \
         patch('core.scraper.map_movie_info', return_value=_make_video('metatube:FANZA', 'ABF-001')):
        shim.search('ABF-001')

    assert state.is_available('metatube:FANZA') is False
    assert state._failed_at['metatube:FANZA'] == stamped


def test_current_generation_shim_writeback_still_works(monkeypatch):
    """圍欄不得把 lazy liveness 自癒一起擋掉：同世代的回寫照常生效。"""
    from core.metatube.errors import MetatubeUnavailable

    state, gen = _real_state_with_shim(monkeypatch)

    # 失敗方向
    failing = _MetatubeShim('FANZA', 'http://mt:8080', 'tok', gen)
    failing._client = MagicMock()
    failing._client.search.side_effect = MetatubeUnavailable('down')
    with pytest.raises(MetatubeUnavailable):
        failing.search('ABF-001')
    assert state.is_available('metatube:FANZA') is False
    assert 'metatube:FANZA' in state._failed_at

    # 成功方向（自癒）
    ok = _MetatubeShim('FANZA', 'http://mt:8080', 'tok', gen)
    ok._client = MagicMock()
    ok._client.search.return_value = [{'id': 'X'}]
    ok._client.get_info.return_value = {'id': 'X'}
    with patch('core.scraper.pick_movie_result', return_value={'id': 'X'}), \
         patch('core.scraper.map_movie_info', return_value=_make_video('metatube:FANZA', 'ABF-001')):
        ok.search('ABF-001')
    assert state.is_available('metatube:FANZA') is True
    assert state._failed_at == {}


def test_shim_snapshot_is_atomic_single_lock_acquisition(monkeypatch):
    """I-1：建 shim 用的四個值必須來自 probe_snapshot() 一次鎖獲取。

    這支不驗行為、驗的是「有沒有分成好幾次去讀」——分開讀就代表重連可以穿插在
    中間，做出一顆拿著新網址、蓋著舊世代章的 shim。
    """
    state = _mock_state(avail_map={'metatube:FANZA': True})
    # oracle：這三個舊讀取點只要被碰到就爆——比計數更直接，
    # 因為「有沒有分開讀」正是這支要守的東西。
    type(state).base_url = PropertyMock(
        side_effect=AssertionError('base_url 被單獨讀取：四個值必須來自 probe_snapshot() 一次快照'))
    type(state).token = PropertyMock(
        side_effect=AssertionError('token 被單獨讀取：四個值必須來自 probe_snapshot() 一次快照'))
    type(state).generation = PropertyMock(
        side_effect=AssertionError('generation 被單獨讀取：四個值必須來自 probe_snapshot() 一次快照'))
    state.availability_map.side_effect = AssertionError(
        'availability_map() 被用來建 shim：那是顯示端的地圖，且它是另一次鎖獲取')

    def _mock_enabled(availability_map=None):
        return ['metatube:FANZA']

    monkeypatch.setattr('core.scraper.get_enabled_source_ids', _mock_enabled)
    monkeypatch.setattr('core.scraper.metatube_state', state)

    with patch('core.scraper._MetatubeShim.search', return_value=None):
        search_jav('ABF-001', source='auto')

    state.probe_snapshot.assert_called_once()
