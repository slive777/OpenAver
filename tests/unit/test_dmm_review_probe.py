"""
TestDMMProbePayloadVariables — DMM GraphQL variables key 名鎖（TASK-118a-T13 後）

回歸守衛：每個 probe / detail query 送出的 GraphQL `variables` key
必須與 query string 宣告的變數名一致。誤打會讓真 API 收到 null、
silent 落空，而所有 mock 掉 payload 的測試仍會綠。
"""
import pytest
from unittest.mock import patch, MagicMock

from core.scrapers.dmm import DMMScraper
from core.proxy_policy import ProxySettings
from core.scrapers.models import ScraperConfig


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch):
    """跳過 rate_limit sleep，加速測試"""
    monkeypatch.setattr("core.scrapers.dmm.rate_limit", lambda *a, **kw: None)


@pytest.fixture(autouse=True)
def _reset_review_supported(monkeypatch):
    """
    _review_supported 是 module-level global，
    每個測試前重置為 None，避免測試間狀態洩漏。
    """
    monkeypatch.setattr("core.scrapers.dmm._review_supported", None)


@pytest.fixture(autouse=True)
def _reset_probe_supported(monkeypatch):
    """
    _genres_supported / _sample_images_supported 也是 module-level global，
    每個測試前重置為 None，避免測試間狀態洩漏。
    """
    monkeypatch.setattr("core.scrapers.dmm._genres_supported", None)
    monkeypatch.setattr("core.scrapers.dmm._sample_images_supported", None)


# ============================================================
# Mock Data
# ============================================================

DMM_DETAIL_RESPONSE_FULL = {
    "data": {
        "ppvContent": {
            "id": "sone00205",
            "title": "成人への卒業",
            "description": "テスト",
            "packageImage": {"largeUrl": "https://pics.dmm.co.jp/sone205pl.jpg"},
            "makerReleasedAt": "2024-03-19T00:00:00+09:00",
            "duration": 8966,
            "actresses": [{"name": "Nana Miho"}],
            "directors": [{"name": "前田文豪"}],
            "series": {"name": "S1 系列"},
            "maker": {"name": "S1 NO.1 STYLE"},
            "makerContentId": "SONE-205",
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


class TestDMMProbePayloadVariables:
    """
    回歸守衛：每個 probe / detail query 送出的 GraphQL `variables` key
    必須與 query string 宣告的變數名一致。

    背景：三個 query（DETAIL / GENRES / SAMPLE_IMAGES）宣告 $id，一個
    （REVIEW）宣告 $contentId。若 payload 的 key 誤打成另一個名字，真 API
    會收到 null、silent 落空——所有「mock 掉 payload」的測試仍會綠。
    此類直接 spy 實際 POST 的 `json['variables']`，並比對 query string
    的變數宣告，鎖死 key 名。
    """

    @pytest.fixture
    def dmm_scraper(self, monkeypatch):
        import core.scrapers.dmm as dmm_module
        monkeypatch.setattr(dmm_module, "_shipped_table_cache", {})
        config = ScraperConfig(proxy_settings=ProxySettings(url="http://test-proxy:8080"))
        return DMMScraper(config)

    def test_probe_genres_sends_id_variable(self, dmm_scraper):
        """_probe_genres 送出 {'id': ...}，且 GENRES_PROBE_QUERY 宣告 $id。"""
        assert '$id' in DMMScraper.GENRES_PROBE_QUERY
        assert '$contentId' not in DMMScraper.GENRES_PROBE_QUERY

        resp = _make_mock_resp(
            status_code=200,
            json_data={"data": {"ppvContent": {"genres": [], "label": None}}},
        )
        mock_post = MagicMock(return_value=resp)
        with patch.object(dmm_scraper._session, 'post', mock_post):
            dmm_scraper._probe_genres("cid123")

        payload = mock_post.call_args.kwargs['json']
        assert payload['variables'] == {'id': 'cid123'}

    def test_probe_sample_images_sends_id_variable(self, dmm_scraper):
        """_probe_sample_images 送出 {'id': ...}，且 query 宣告 $id。"""
        assert '$id' in DMMScraper.SAMPLE_IMAGES_PROBE_QUERY
        assert '$contentId' not in DMMScraper.SAMPLE_IMAGES_PROBE_QUERY

        resp = _make_mock_resp(
            status_code=200,
            json_data={"data": {"ppvContent": {"sampleImages": []}}},
        )
        mock_post = MagicMock(return_value=resp)
        with patch.object(dmm_scraper._session, 'post', mock_post):
            dmm_scraper._probe_sample_images("cid123")

        payload = mock_post.call_args.kwargs['json']
        assert payload['variables'] == {'id': 'cid123'}

    def test_fetch_by_id_detail_sends_id_variable(self, dmm_scraper):
        """_fetch_by_id 首個 POST（DETAIL_QUERY）送出 {'id': ...}，
        且 DETAIL_QUERY 宣告 $id。子 probe 全 mock，只驗 DETAIL POST。"""
        assert '$id' in DMMScraper.DETAIL_QUERY
        assert '$contentId' not in DMMScraper.DETAIL_QUERY

        detail_resp = _make_mock_resp(status_code=200, json_data=DMM_DETAIL_RESPONSE_FULL)
        mock_post = MagicMock(return_value=detail_resp)
        with patch.object(dmm_scraper._session, 'post', mock_post), \
             patch.object(dmm_scraper, '_probe_genres', return_value=([], "")), \
             patch.object(dmm_scraper, '_probe_sample_images', return_value=[]), \
             patch.object(dmm_scraper, '_probe_review', return_value=None), \
             patch.object(dmm_scraper, '_fetch_tags_from_html', return_value=[]):
            dmm_scraper._fetch_by_id("cid123")

        # 第一個 POST 即 DETAIL_QUERY（子 probe 已 mock 掉，不會發 POST）
        first_call = mock_post.call_args_list[0]
        payload = first_call.kwargs['json']
        assert payload['query'] == DMMScraper.DETAIL_QUERY
        assert payload['variables'] == {'id': 'cid123'}

    def test_probe_review_sends_contentId_variable(self, dmm_scraper):
        """_probe_review 送出 {'contentId': ...}，且 REVIEW_PROBE_QUERY 宣告 $contentId。"""
        assert '$contentId' in DMMScraper.REVIEW_PROBE_QUERY
        assert '$id' not in DMMScraper.REVIEW_PROBE_QUERY

        resp = _make_mock_resp(
            status_code=200,
            json_data={"data": {"reviewSummary": {"average": 4.26}}},
        )
        mock_post = MagicMock(return_value=resp)
        with patch.object(dmm_scraper._session, 'post', mock_post):
            dmm_scraper._probe_review("cid123")

        payload = mock_post.call_args.kwargs['json']
        assert payload['variables'] == {'contentId': 'cid123'}
