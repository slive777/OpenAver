"""TASK-163a-T5 — DMM 兩個主查詢的存取錯誤分類。

假回應只驗接線；2026-10-09 實測台灣直連活站回 200，沒有可重現的真封鎖回應。
本檔不宣稱驗證了站方行為，只驗「非 200 / 連不到 / 查無」三種結果被分開。
"""
from unittest.mock import MagicMock, patch

import pytest
import requests

from core.proxy_policy import ProxySettings
from core.scrapers.dmm import DMMScraper
from core.scrapers.errors import SourceBlocked, SourceUnreachable
from core.scrapers.models import ScraperConfig


def _resp(status_code=200, json_data=None, json_exc=None):
    r = MagicMock()
    r.status_code = status_code
    if json_exc is not None:
        r.json = MagicMock(side_effect=json_exc)
    else:
        r.json = lambda: json_data
    return r


@pytest.fixture
def dmm(monkeypatch):
    import core.scrapers.dmm as dmm_module

    monkeypatch.setattr(dmm_module, "rate_limit", lambda *a, **kw: None)
    return DMMScraper(ScraperConfig(proxy_settings=ProxySettings(url="")))


def _call_search_content_id(s):
    return s._search_content_id("SONE-205")


def _call_fetch_by_id(s):
    return s._fetch_by_id("sone00205")


QUERIES = [_call_search_content_id, _call_fetch_by_id]


@pytest.mark.parametrize("status", [403, 500])
@pytest.mark.parametrize("call", QUERIES)
def test_dmm_non_200_main_queries_raise_source_blocked(dmm, call, status):
    with patch.object(dmm._session, "post", return_value=_resp(status)):
        with pytest.raises(SourceBlocked) as ei:
            call(dmm)
    assert str(status) in str(ei.value)


@pytest.mark.parametrize("exc", [requests.ConnectionError("x"), requests.Timeout("x")])
@pytest.mark.parametrize("call", QUERIES)
def test_dmm_connection_error_raises_source_unreachable(dmm, call, exc):
    with patch.object(dmm._session, "post", side_effect=exc):
        with pytest.raises(SourceUnreachable):
            call(dmm)


@pytest.mark.parametrize("call,empty", [
    (_call_search_content_id, {"data": {"legacySearchPPV": {"result": {"contents": []}}}}),
    (_call_search_content_id, {"data": None}),
    (_call_fetch_by_id, {"data": {"ppvContent": None}}),
    (_call_fetch_by_id, {"data": None}),
])
def test_dmm_200_empty_and_non_json_stay_not_found(dmm, call, empty):
    with patch.object(dmm._session, "post", return_value=_resp(200, empty)):
        assert call(dmm) is None
    # 200 但 body 不是 JSON：JSONDecodeError 是 RequestException 子類，仍須是「查無」
    bad = _resp(200, json_exc=requests.exceptions.JSONDecodeError("bad", "<html>", 0))
    with patch.object(dmm._session, "post", return_value=bad):
        assert call(dmm) is None


def test_dmm_search_stops_at_first_detail_403(dmm):
    """第一個詳情查詢被拒 → 整個 search 拋 SourceBlocked，不繼續第二試。"""
    post = MagicMock(return_value=_resp(403))
    with patch.object(dmm._session, "post", post):
        with pytest.raises(SourceBlocked):
            dmm.search("SONE-205")
    assert post.call_count == 1
