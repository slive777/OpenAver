"""
TestDMMSearchByKeyword — DMM search_by_keyword() 單元測試
（搬自 tests/integration/test_new_scrapers.py TestDMMSearchByKeyword）

全 mock，不發外部 request
"""
import pytest
import requests
from unittest.mock import patch, MagicMock

from core.scrapers.dmm import DMMScraper
from core.scrapers.models import Video, ScraperConfig


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch):
    """跳過 rate_limit sleep，加速測試"""
    monkeypatch.setattr("core.scrapers.dmm.rate_limit", lambda *a, **kw: None)


# ============================================================
# Mock Data
# ============================================================

DMM_SEARCH_LIST_RESPONSE = {
    "data": {
        "legacySearchPPV": {
            "result": {
                "contents": [
                    {
                        "id": "sone00205",
                        "title": "成人への卒業",
                        "packageImage": {"largeUrl": "https://pics.dmm.co.jp/sone205pl.jpg"},
                        "actresses": [{"name": "未歩なな"}],
                        "maker": {"name": "S1 NO.1 STYLE"},
                    },
                    {
                        "id": "sone00300",
                        "title": "第二作品",
                        "packageImage": {"largeUrl": "https://pics.dmm.co.jp/sone300pl.jpg"},
                        "actresses": [{"name": "星宮一花"}, {"name": "三上悠亜"}],
                        "maker": {"name": "S1 NO.1 STYLE"},
                    },
                ]
            }
        }
    }
}


def _make_mock_resp(status_code=200, json_data=None, content=None):
    """Build a MagicMock that mimics requests.Response."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    if json_data is not None:
        mock_resp.json = lambda: json_data
    if content is not None:
        mock_resp.content = content
    return mock_resp


# ============================================================
# Tests
# ============================================================

class TestDMMSearchByKeyword:
    """DMM search_by_keyword() 單元測試（全 mock）"""

    @pytest.fixture
    def dmm_scraper(self, tmp_path, monkeypatch):
        import core.scrapers.dmm as dmm_module
        monkeypatch.setattr(dmm_module, "CACHE_FILE", tmp_path / "dmm_content_ids.json")
        monkeypatch.setattr(dmm_module, "PREFIX_FILE", tmp_path / "dmm_prefix_hints.json")
        config = ScraperConfig(proxy_url="http://test-proxy:8080")
        return DMMScraper(config)

    # 1. no proxy → session.proxies not set (direct mode)
    def test_keyword_no_proxy_session_not_set(self):
        """無 proxy_url → session.proxies 不設定（直連模式）

        37d T3：guard 已移至呼叫端（scraper.py），DMMScraper 建立即執行。
        本測試確認 proxy_url='' 時 session.proxies 為空。
        """
        scraper = DMMScraper()  # no proxy_url
        assert not scraper._session.proxies, \
            "proxy_url='' 時 session.proxies 不應被設定"

    # 2. mock response → 2 Videos
    def test_keyword_returns_multiple(self, dmm_scraper):
        """mock response → 回傳 2 個 Video 物件"""
        mock_resp = _make_mock_resp(status_code=200, json_data=DMM_SEARCH_LIST_RESPONSE)

        with patch.object(dmm_scraper._session, 'post', return_value=mock_resp), \
             patch.object(dmm_scraper, '_fetch_by_id', return_value=None), \
             patch('core.scrapers.dmm.rate_limit'):
            results = dmm_scraper.search_by_keyword("未歩なな")

        assert len(results) == 2

    # 3. verify each field (fallback path — _fetch_by_id returns None)
    def test_keyword_video_fields(self, dmm_scraper):
        """各欄位正確對應：title, cover_url, actresses, maker, source, number, detail_url"""
        mock_resp = _make_mock_resp(status_code=200, json_data=DMM_SEARCH_LIST_RESPONSE)

        with patch.object(dmm_scraper._session, 'post', return_value=mock_resp), \
             patch.object(dmm_scraper, '_fetch_by_id', return_value=None), \
             patch('core.scrapers.dmm.rate_limit'):
            results = dmm_scraper.search_by_keyword("未歩なな")

        v0 = results[0]
        assert v0.number == "SONE-205"
        assert v0.title == "成人への卒業"
        assert v0.cover_url == "https://pics.dmm.co.jp/sone205pl.jpg"
        assert len(v0.actresses) == 1
        assert v0.actresses[0].name == "未歩なな"
        assert v0.maker == "S1 NO.1 STYLE"
        assert v0.source == "dmm"
        assert "sone00205" in v0.detail_url

        v1 = results[1]
        assert v1.number == "SONE-300"
        assert len(v1.actresses) == 2
        assert v1.actresses[0].name == "星宮一花"
        assert v1.actresses[1].name == "三上悠亜"

    # 3b. number format conversion
    def test_keyword_number_format(self, dmm_scraper):
        """content_id → 標準番號格式（strip leading zeros + uppercase）"""
        mock_resp = _make_mock_resp(status_code=200, json_data=DMM_SEARCH_LIST_RESPONSE)
        with patch.object(dmm_scraper._session, 'post', return_value=mock_resp), \
             patch.object(dmm_scraper, '_fetch_by_id', return_value=None), \
             patch('core.scrapers.dmm.rate_limit'):
            results = dmm_scraper.search_by_keyword("未歩なな")
        # sone00205 → SONE-205 (not SONE-00205)
        assert results[0].number == "SONE-205"
        # sone00300 → SONE-300
        assert results[1].number == "SONE-300"

    # 3c. _content_id_to_number helper unit test
    def test_content_id_to_number_conversion(self, dmm_scraper):
        """_content_id_to_number 各種格式"""
        assert dmm_scraper._content_id_to_number("sone00205") == "SONE-205"
        assert dmm_scraper._content_id_to_number("1stars00804") == "STARS-804"
        assert dmm_scraper._content_id_to_number("ofje00709") == "OFJE-709"
        assert dmm_scraper._content_id_to_number("ssni00001") == "SSNI-001"  # NOT SSNI-1
        assert dmm_scraper._content_id_to_number("abc00001") == "ABC-001"    # NOT ABC-1
        # 4-digit number preserved
        assert dmm_scraper._content_id_to_number("abp01234") == "ABP-1234"
        # edge: no leading zeros
        assert dmm_scraper._content_id_to_number("test123") == "TEST-123"
        # edge: fallback for non-matching format
        assert dmm_scraper._content_id_to_number("weird-format") == "weird-format"

    # 4. contents=[] → []
    def test_keyword_empty_results(self, dmm_scraper):
        """contents=[] → 回傳空列表"""
        empty_resp = {
            "data": {
                "legacySearchPPV": {
                    "result": {"contents": []}
                }
            }
        }
        mock_resp = _make_mock_resp(status_code=200, json_data=empty_resp)

        with patch.object(dmm_scraper._session, 'post', return_value=mock_resp):
            results = dmm_scraper.search_by_keyword("xyz")

        assert results == []

    # 5. HTTP 500 → []
    def test_keyword_http_error(self, dmm_scraper):
        """HTTP 500 → 回傳空列表"""
        mock_resp = _make_mock_resp(status_code=500)

        with patch.object(dmm_scraper._session, 'post', return_value=mock_resp):
            results = dmm_scraper.search_by_keyword("未歩なな")

        assert results == []

    # 6. data=null → []
    def test_keyword_data_null(self, dmm_scraper):
        """data=null in response → 回傳空列表"""
        null_resp = {"data": None}
        mock_resp = _make_mock_resp(status_code=200, json_data=null_resp)

        with patch.object(dmm_scraper._session, 'post', return_value=mock_resp):
            results = dmm_scraper.search_by_keyword("未歩なな")

        assert results == []

    # 7. requests.Timeout → []
    def test_keyword_network_exception(self, dmm_scraper):
        """requests.Timeout → 回傳空列表（不 raise）"""
        with patch.object(dmm_scraper._session, 'post', side_effect=requests.Timeout):
            results = dmm_scraper.search_by_keyword("未歩なな")

        assert results == []

    # 8. actresses=[] → Video.actresses==[]
    def test_keyword_actresses_empty(self, dmm_scraper):
        """actresses=[] → Video.actresses 為空列表"""
        no_actress_resp = {
            "data": {
                "legacySearchPPV": {
                    "result": {
                        "contents": [{
                            "id": "test00001",
                            "title": "テスト",
                            "packageImage": {"largeUrl": "https://example.com/cover.jpg"},
                            "actresses": [],
                            "maker": {"name": "TestMaker"},
                        }]
                    }
                }
            }
        }
        mock_resp = _make_mock_resp(status_code=200, json_data=no_actress_resp)

        with patch.object(dmm_scraper._session, 'post', return_value=mock_resp), \
             patch.object(dmm_scraper, '_fetch_by_id', return_value=None), \
             patch('core.scrapers.dmm.rate_limit'):
            results = dmm_scraper.search_by_keyword("テスト")

        assert len(results) == 1
        assert results[0].actresses == []

    # 9. packageImage=null → cover_url==""
    def test_keyword_cover_null(self, dmm_scraper):
        """packageImage=null → cover_url 為空字串"""
        no_cover_resp = {
            "data": {
                "legacySearchPPV": {
                    "result": {
                        "contents": [{
                            "id": "test00002",
                            "title": "テスト2",
                            "packageImage": None,
                            "actresses": [{"name": "テスト女優"}],
                            "maker": {"name": "TestMaker"},
                        }]
                    }
                }
            }
        }
        mock_resp = _make_mock_resp(status_code=200, json_data=no_cover_resp)

        with patch.object(dmm_scraper._session, 'post', return_value=mock_resp), \
             patch.object(dmm_scraper, '_fetch_by_id', return_value=None), \
             patch('core.scrapers.dmm.rate_limit'):
            results = dmm_scraper.search_by_keyword("テスト")

        assert len(results) == 1
        assert results[0].cover_url == ""

    # 10. limit is passed to GraphQL variables
    def test_keyword_limit_passed(self, dmm_scraper):
        """limit 參數被正確傳入 GraphQL variables"""
        mock_resp = _make_mock_resp(status_code=200, json_data=DMM_SEARCH_LIST_RESPONSE)

        with patch.object(dmm_scraper._session, 'post', return_value=mock_resp) as mock_post, \
             patch.object(dmm_scraper, '_fetch_by_id', return_value=None), \
             patch('core.scrapers.dmm.rate_limit'):
            dmm_scraper.search_by_keyword("未歩なな", limit=5)

        # First call is the list query; check its variables
        call_kwargs = mock_post.call_args_list[0][1]
        payload = call_kwargs.get('json', {})
        assert payload['variables']['limit'] == 5

    # 11. enrichment — _fetch_by_id called per item
    def test_keyword_enrichment_calls_fetch_by_id(self, dmm_scraper):
        """search_by_keyword 對每筆結果呼叫 _fetch_by_id"""
        list_resp = _make_mock_resp(status_code=200, json_data=DMM_SEARCH_LIST_RESPONSE)
        enriched_video1 = Video(number="SONE-205", title="Full Title 1", source="dmm",
                                date="2024-03-19", director="Director1", duration=149,
                                tags=["tag1"], sample_images=["https://img1.jpg"])
        enriched_video2 = Video(number="SONE-300", title="Full Title 2", source="dmm",
                                date="2024-05-01", director="Director2", duration=120)

        with patch.object(dmm_scraper._session, 'post', return_value=list_resp), \
             patch.object(dmm_scraper, '_fetch_by_id', side_effect=[enriched_video1, enriched_video2]) as mock_fetch, \
             patch('core.scrapers.dmm.rate_limit'):
            results = dmm_scraper.search_by_keyword("test")

        assert mock_fetch.call_count == 2
        mock_fetch.assert_any_call("sone00205")
        mock_fetch.assert_any_call("sone00300")
        assert results[0].date == "2024-03-19"
        assert results[0].director == "Director1"
        assert results[1].date == "2024-05-01"

    # 12. enrichment fallback — _fetch_by_id returns None → shallow Video
    def test_keyword_enrichment_fallback_on_fetch_fail(self, dmm_scraper):
        """_fetch_by_id 返回 None → fallback 到 shallow Video"""
        list_resp = _make_mock_resp(status_code=200, json_data=DMM_SEARCH_LIST_RESPONSE)

        with patch.object(dmm_scraper._session, 'post', return_value=list_resp), \
             patch.object(dmm_scraper, '_fetch_by_id', return_value=None), \
             patch('core.scrapers.dmm.rate_limit'):
            results = dmm_scraper.search_by_keyword("test")

        assert len(results) == 2
        assert results[0].title == "成人への卒業"
        assert results[0].number == "SONE-205"
        assert results[0].date == ""
        assert results[0].tags == []

    def test_keyword_enrichment_fallback_on_fetch_raise(self, dmm_scraper):
        """_fetch_by_id 拋 exception → per-item catch，不清空整批結果"""
        list_resp = _make_mock_resp(status_code=200, json_data=DMM_SEARCH_LIST_RESPONSE)

        with patch.object(dmm_scraper._session, 'post', return_value=list_resp), \
             patch.object(dmm_scraper, '_fetch_by_id', side_effect=TimeoutError('boom')), \
             patch('core.scrapers.dmm.rate_limit'):
            results = dmm_scraper.search_by_keyword("test")

        # Should still get 2 shallow fallback results (not [])
        assert len(results) == 2
        assert results[0].title == "成人への卒業"
        assert results[0].date == ""  # not enriched

    # 13. rate_limit called per item (not once for the whole batch)
    def test_keyword_rate_limit_per_item(self, dmm_scraper):
        """rate_limit 逐筆呼叫（不是整批一次）"""
        list_resp = _make_mock_resp(status_code=200, json_data=DMM_SEARCH_LIST_RESPONSE)
        enriched = Video(number="SONE-205", title="test", source="dmm")

        with patch.object(dmm_scraper._session, 'post', return_value=list_resp), \
             patch.object(dmm_scraper, '_fetch_by_id', return_value=enriched), \
             patch('core.scrapers.dmm.rate_limit') as mock_rl:
            dmm_scraper.search_by_keyword("test")

        # 2 items in DMM_SEARCH_LIST_RESPONSE → rate_limit called 2 times
        assert mock_rl.call_count == 2

    # ============================================================
    # T3: search_by_keyword_with_ids() tests
    # ============================================================

    def test_keyword_with_ids_returns_tuples(self, dmm_scraper):
        """search_by_keyword_with_ids 回傳 (content_id, Video) tuples"""
        list_resp = _make_mock_resp(status_code=200, json_data=DMM_SEARCH_LIST_RESPONSE)
        with patch.object(dmm_scraper._session, 'post', return_value=list_resp), \
             patch('core.scrapers.dmm.rate_limit'):
            pairs = dmm_scraper.search_by_keyword_with_ids("test")

        assert len(pairs) == 2
        assert pairs[0][0] == "sone00205"   # content_id
        assert pairs[0][1].number == "SONE-205"  # shallow Video
        assert pairs[1][0] == "sone00300"

    def test_keyword_with_ids_no_enrichment(self, dmm_scraper):
        """search_by_keyword_with_ids 不呼叫 _fetch_by_id"""
        list_resp = _make_mock_resp(status_code=200, json_data=DMM_SEARCH_LIST_RESPONSE)
        with patch.object(dmm_scraper._session, 'post', return_value=list_resp), \
             patch.object(dmm_scraper, '_fetch_by_id') as mock_fetch, \
             patch('core.scrapers.dmm.rate_limit'):
            dmm_scraper.search_by_keyword_with_ids("test")
        mock_fetch.assert_not_called()

    # ============================================================
    # T5: offset 參數傳遞測試
    # ============================================================

    def test_keyword_with_ids_offset_passed(self, dmm_scraper):
        """search_by_keyword_with_ids(offset=40) → GraphQL variables.offset == 40"""
        mock_resp = _make_mock_resp(status_code=200, json_data=DMM_SEARCH_LIST_RESPONSE)

        with patch.object(dmm_scraper._session, 'post', return_value=mock_resp) as mock_post, \
             patch('core.scrapers.dmm.rate_limit'):
            dmm_scraper.search_by_keyword_with_ids("未歩なな", limit=20, offset=40)

        call_kwargs = mock_post.call_args_list[0][1]
        payload = call_kwargs.get('json', {})
        assert payload['variables']['offset'] == 40

    def test_keyword_offset_passed(self, dmm_scraper):
        """search_by_keyword(offset=40) → GraphQL variables.offset == 40"""
        mock_resp = _make_mock_resp(status_code=200, json_data=DMM_SEARCH_LIST_RESPONSE)

        with patch.object(dmm_scraper._session, 'post', return_value=mock_resp) as mock_post, \
             patch.object(dmm_scraper, '_fetch_by_id', return_value=None), \
             patch('core.scrapers.dmm.rate_limit'):
            dmm_scraper.search_by_keyword("未歩なな", limit=20, offset=40)

        call_kwargs = mock_post.call_args_list[0][1]
        payload = call_kwargs.get('json', {})
        assert payload['variables']['offset'] == 40
