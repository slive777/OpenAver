"""
TestDMMReviewProbe — DMM 評分 _probe_review 獨立 root probe 測試（TASK-93-T2）

三態邏輯 + 降級（probe 失敗不影響主 metadata）
比照 test_dmm_fields.py 的 mock 模式。
"""
import pytest
from unittest.mock import patch, MagicMock

from core.scrapers.dmm import DMMScraper
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


# ============================================================
# Tests
# ============================================================

class TestDMMReviewProbe:
    """_probe_review 三態 + 降級測試"""

    @pytest.fixture
    def dmm_scraper(self, tmp_path, monkeypatch):
        import core.scrapers.dmm as dmm_module
        monkeypatch.setattr(dmm_module, "CACHE_FILE", tmp_path / "dmm_content_ids.json")
        monkeypatch.setattr(dmm_module, "PREFIX_FILE", tmp_path / "dmm_prefix_hints.json")
        config = ScraperConfig(proxy_url="http://test-proxy:8080")
        return DMMScraper(config)

    # ------------------------------------------------------------------
    # 邊界 1：schema-unsupported → False，且後續不再發 POST
    # ------------------------------------------------------------------

    def test_schema_unsupported_disables_future_probe(self, dmm_scraper):
        """errors 含 'Cannot query field reviewSummary' → _review_supported=False，
        第二次呼叫不再發 POST（省請求）。"""
        import core.scrapers.dmm as m

        schema_err_resp = _make_mock_resp(
            status_code=200,
            json_data={
                "errors": [
                    {"message": "Cannot query field reviewSummary on type Query"}
                ]
            },
        )
        mock_post = MagicMock(return_value=schema_err_resp)
        with patch.object(dmm_scraper._session, 'post', mock_post):
            result1 = dmm_scraper._probe_review("sone00205")
            assert result1 is None
            assert m._review_supported is False
            assert mock_post.call_count == 1

            # 第二次呼叫：False 態直接跳過，不再 POST
            result2 = dmm_scraper._probe_review("sone00205")
            assert result2 is None
            assert mock_post.call_count == 1

    # ------------------------------------------------------------------
    # 邊界 2：正常有值 → rating 值 + True
    # ------------------------------------------------------------------

    def test_normal_average_returns_float(self, dmm_scraper):
        """reviewSummary.average = 4.26 → 回傳 4.26，_review_supported=True。"""
        import core.scrapers.dmm as m

        resp = _make_mock_resp(
            status_code=200,
            json_data={"data": {"reviewSummary": {"average": 4.26}}},
        )
        mock_post = MagicMock(return_value=resp)
        with patch.object(dmm_scraper._session, 'post', mock_post):
            result = dmm_scraper._probe_review("sone00205")
            assert result == 4.26
            assert m._review_supported is True
            # D4 硬約束：arg 名必須是 contentId（非 id）——誤打會讓真 API 拒查、
            # rating 永遠 silent 落空且所有 mock 測試仍綠。此斷言鎖死 arg 名。
            payload = mock_post.call_args.kwargs['json']
            assert payload['variables'] == {'contentId': 'sone00205'}

    # ------------------------------------------------------------------
    # 邊界 3：reviewSummary null → None + True（此片無評分）
    # ------------------------------------------------------------------

    def test_null_review_summary_returns_none_but_supported(self, dmm_scraper):
        """reviewSummary=null → 回傳 None（此片無評分），但 _review_supported=True。"""
        import core.scrapers.dmm as m

        resp = _make_mock_resp(
            status_code=200,
            json_data={"data": {"reviewSummary": None}},
        )
        with patch.object(dmm_scraper._session, 'post', return_value=resp):
            result = dmm_scraper._probe_review("sone00205")
            assert result is None
            assert m._review_supported is True

    # ------------------------------------------------------------------
    # 邊界 4：降級 A — probe POST 拋例外 → Video 完整、rating None
    # ------------------------------------------------------------------

    def test_degradation_probe_exception_keeps_main_metadata(self, dmm_scraper):
        """probe POST 拋例外 → _fetch_by_id 仍回 Video，
        title/cover/actresses 完整、rating is None。"""
        import core.scrapers.dmm as m

        detail_resp = _make_mock_resp(status_code=200, json_data=DMM_DETAIL_RESPONSE_FULL)
        # 第一次 POST（DETAIL_QUERY）成功，第二次（review probe）拋例外
        with patch.object(dmm_scraper._session, 'post',
                          side_effect=[detail_resp, Exception("boom")]), \
             patch.object(dmm_scraper, '_probe_genres', return_value=([], "S1 NO.1 STYLE")), \
             patch.object(dmm_scraper, '_probe_sample_images', return_value=[]):
            video = dmm_scraper._fetch_by_id("sone00205")

        assert video is not None
        assert video.title == "成人への卒業"
        assert video.cover_url == "https://pics.dmm.co.jp/sone205pl.jpg"
        assert [a.name for a in video.actresses] == ["Nana Miho"]
        assert video.rating is None
        # 例外為暫時性失敗，不設 False
        assert m._review_supported is None

    # ------------------------------------------------------------------
    # 邊界 5：降級 B — probe 回 HTTP 500 → Video 完整、rating None、cache 不變
    # ------------------------------------------------------------------

    def test_degradation_probe_http_500_keeps_main_metadata(self, dmm_scraper):
        """probe 回 HTTP 500 → _fetch_by_id 仍回 Video，
        rating is None，_review_supported 維持 None（暫時性）。"""
        import core.scrapers.dmm as m

        detail_resp = _make_mock_resp(status_code=200, json_data=DMM_DETAIL_RESPONSE_FULL)
        resp_500 = _make_mock_resp(status_code=500)
        with patch.object(dmm_scraper._session, 'post',
                          side_effect=[detail_resp, resp_500]), \
             patch.object(dmm_scraper, '_probe_genres', return_value=([], "S1 NO.1 STYLE")), \
             patch.object(dmm_scraper, '_probe_sample_images', return_value=[]):
            video = dmm_scraper._fetch_by_id("sone00205")

        assert video is not None
        assert video.title == "成人への卒業"
        assert video.cover_url == "https://pics.dmm.co.jp/sone205pl.jpg"
        assert [a.name for a in video.actresses] == ["Nana Miho"]
        assert video.rating is None
        assert m._review_supported is None

    # ------------------------------------------------------------------
    # 邊界 6：正常 probe 有值時 _fetch_by_id 帶入 rating（接線驗證）
    # ------------------------------------------------------------------

    def test_fetch_by_id_wires_rating_from_probe(self, dmm_scraper):
        """probe 回 4.26 → _fetch_by_id 產生的 Video.rating == 4.26。"""
        detail_resp = _make_mock_resp(status_code=200, json_data=DMM_DETAIL_RESPONSE_FULL)
        review_resp = _make_mock_resp(
            status_code=200,
            json_data={"data": {"reviewSummary": {"average": 4.26}}},
        )
        with patch.object(dmm_scraper._session, 'post',
                          side_effect=[detail_resp, review_resp]), \
             patch.object(dmm_scraper, '_probe_genres', return_value=([], "S1 NO.1 STYLE")), \
             patch.object(dmm_scraper, '_probe_sample_images', return_value=[]):
            video = dmm_scraper._fetch_by_id("sone00205")

        assert video is not None
        assert video.rating == 4.26
