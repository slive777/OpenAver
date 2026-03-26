"""
新 Scraper 單元測試（全 mock，不發外部 request）

T4: D2Pass / HEYZO / DMM scraper tests + Pipeline routing + Proxy API + extract_number
"""
import json
import pytest
import requests
from unittest.mock import patch, MagicMock, call

from core.scrapers.d2pass import D2PassScraper
from core.scrapers.heyzo import HEYZOScraper
from core.scrapers.dmm import DMMScraper
from core.scrapers.javbus import JavBusScraper
from core.scrapers.models import Video, Actress, ScraperConfig
from core.scrapers.utils import extract_number
from core.scraper import search_jav, smart_search
from fastapi.testclient import TestClient
from web.app import app


# ============================================================
# 共用 Helper
# ============================================================

def _make_video(source: str, number: str = "TEST-001") -> Video:
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
    )


# ============================================================
# 共用 Mock Data
# ============================================================

SAMPLE_1PONDO_JSON = {
    "Status": True,
    "Title": "目覚ましフェラ",
    "TitleEn": "Morning Blowjob",
    "ActressesJa": ["一ノ瀬アメリ"],
    "Release": "2014-12-04",
    "ThumbHigh": "https://www.1pondo.tv/assets/sample/120415_201/str.jpg",
    "UCNAME": ["美尻", "69"],
    "AvgRating": 4.5,
}

HEYZO_EN_HTML = b"""
<html>
<head>
<script type="application/ld+json">
{
    "@type": "Movie",
    "name": "Slim Beauty's Seduction",
    "actor": {"@type": "Person", "name": "Airi Mashiro"},
    "dateCreated": "2015-01-17T00:00:00+09:00",
    "image": "//en.heyzo.com/contents/3000/0783/images/player_thumbnail_450.jpg",
    "aggregateRating": {"ratingValue": "4.22", "reviewCount": "56"}
}
</script>
</head>
<body>
<table class="movieInfo">
<tr><td>Series</td><td>Premium Collection</td></tr>
<tr><td>Type</td><td><a>Cute</a> <a>Slender</a></td></tr>
</table>
</body>
</html>
"""

DMM_SEARCH_RESPONSE = {
    "data": {
        "legacySearchPPV": {
            "result": {
                "contents": [{"id": "sone00205"}]
            }
        }
    }
}

DMM_DETAIL_RESPONSE = {
    "data": {
        "ppvContent": {
            "id": "sone00205",
            "title": "成人への卒業",
            "description": "テスト",
            "packageImage": {"largeUrl": "https://pics.dmm.co.jp/sone205pl.jpg"},
            "makerReleasedAt": "2024-03-19T00:00:00+09:00",
            "duration": 120,
            "actresses": [{"name": "Nana Miho"}],
            "directors": [],
            "series": {"name": ""},
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
# Class 1: TestD2PassScraper
# ============================================================

class TestD2PassScraper:
    """D2Pass 聯合爬蟲單元測試（全 mock）"""

    @pytest.fixture
    def scraper(self):
        return D2PassScraper()

    def test_d2pass_1pondo_success(self, scraper):
        """1Pondo 番號搜尋成功"""
        mock_resp = _make_mock_resp(status_code=200, json_data=SAMPLE_1PONDO_JSON)

        with patch.object(scraper._session, 'get', return_value=mock_resp) as mock_get:
            with patch('core.scrapers.utils.rate_limit'):
                video = scraper.search("120415_201")

        assert video is not None
        assert video.number == "120415_201"
        assert video.title == "目覚ましフェラ"
        assert video.source == "d2pass"
        assert len(video.actresses) == 1
        assert video.actresses[0].name == "一ノ瀬アメリ"
        assert video.date == "2014-12-04"
        assert "美尻" in video.tags

    def test_d2pass_caribbeancom_success(self, scraper):
        """Caribbeancom 番號（hyphen 格式）搜尋成功"""
        carib_json = {
            "Status": True,
            "Title": "キャットウォーク ...",
            "ActressesJa": ["鈴木さとみ"],
            "Release": "2009-07-14",
            "UCNAME": [],
        }
        mock_resp = _make_mock_resp(status_code=200, json_data=carib_json)

        with patch.object(scraper._session, 'get', return_value=mock_resp) as mock_get:
            with patch('core.scrapers.utils.rate_limit'):
                video = scraper.search("071409-113")

        assert video is not None
        assert video.source == "d2pass"
        assert video.title == "キャットウォーク ..."
        assert len(video.actresses) == 1
        assert video.actresses[0].name == "鈴木さとみ"
        # 驗證第一次呼叫的 URL 包含 caribbeancom
        first_call_url = mock_get.call_args_list[0][0][0]
        assert "caribbeancom" in first_call_url

    def test_d2pass_10musume_success(self, scraper):
        """10musume 番號（底線 2-digit suffix）搜尋成功"""
        musume_json = {
            "Status": True,
            "Title": "素人AV面接 ...",
            "ActressesJa": ["堀川麻紀"],
            "Release": "2012-09-28",
            "UCNAME": [],
        }
        mock_resp = _make_mock_resp(status_code=200, json_data=musume_json)

        with patch.object(scraper._session, 'get', return_value=mock_resp) as mock_get:
            with patch('core.scrapers.utils.rate_limit'):
                video = scraper.search("082912_01")

        assert video is not None
        assert video.source == "d2pass"
        assert video.title == "素人AV面接 ..."
        assert len(video.actresses) == 1
        assert video.actresses[0].name == "堀川麻紀"
        # 驗證第一次呼叫的 URL 包含 10musume
        first_call_url = mock_get.call_args_list[0][0][0]
        assert "10musume" in first_call_url

    def test_d2pass_site_detection(self, scraper):
        """_detect_site_order 根據番號格式回傳正確順序（純邏輯，不需 mock）"""
        assert scraper._detect_site_order("071409-113")[0] == "caribbeancom"
        assert scraper._detect_site_order("120415_201")[0] == "1pondo"
        assert scraper._detect_site_order("082912_01")[0] == "10musume"

    def test_d2pass_not_found(self, scraper):
        """全部 site 皆 404 時 search 回傳 None"""
        mock_resp = _make_mock_resp(status_code=404)

        with patch.object(scraper._session, 'get', return_value=mock_resp):
            video = scraper.search("999999_999")

        assert video is None

    def test_d2pass_timeout(self, scraper):
        """_session.get raise Timeout → _fetch_json catches it → search returns None"""
        # _fetch_json 內部 (line 95) 已捕捉 requests.Timeout 並 return None
        # 因此整個 search() 只會回傳 None，不會 raise TimeoutError
        with patch.object(scraper._session, 'get', side_effect=requests.Timeout):
            video = scraper.search("120415_201")

        assert video is None

    def test_d2pass_caribbeancom_cover_fallback(self, scraper):
        """Caribbeancom ThumbHigh=null 時，自動構造封面 URL"""
        carib_json = {
            "Status": True,
            "Title": "テスト動画",
            "ActressesJa": ["テスト"],
            "Release": "2024-02-09",
            "UCNAME": [],
            # ThumbHigh / MovieThumb 都不存在 → 觸發 fallback
        }
        mock_resp = _make_mock_resp(status_code=200, json_data=carib_json)

        with patch.object(scraper._session, 'get', return_value=mock_resp):
            with patch('core.scrapers.utils.rate_limit'):
                video = scraper.search("020924-001")

        assert video is not None
        assert video.title == "テスト動画"
        assert len(video.actresses) == 1
        assert video.actresses[0].name == "テスト"
        assert video.cover_url == "https://www.caribbeancom.com/moviepages/020924-001/images/l_l.jpg"

    def test_d2pass_1pondo_cover_fallback(self, scraper):
        """1Pondo ThumbHigh=null 時，自動構造封面 URL"""
        pondo_json = {
            "Status": True,
            "Title": "テスト動画",
            "ActressesJa": ["テスト"],
            "Release": "2024-04-23",
            "UCNAME": [],
            # ThumbHigh / MovieThumb 都不存在 → 觸發 fallback
        }
        mock_resp = _make_mock_resp(status_code=200, json_data=pondo_json)

        with patch.object(scraper._session, 'get', return_value=mock_resp):
            with patch('core.scrapers.utils.rate_limit'):
                video = scraper.search("042324_001")

        assert video is not None
        assert video.title == "テスト動画"
        assert len(video.actresses) == 1
        assert video.actresses[0].name == "テスト"
        assert video.cover_url == "https://www.1pondo.tv/assets/sample/042324_001/str.jpg"


# ============================================================
# Class 2: TestHEYZOScraper
# ============================================================

class TestHEYZOScraper:
    """HEYZO 爬蟲單元測試（全 mock）"""

    @pytest.fixture
    def scraper(self):
        return HEYZOScraper()

    def test_heyzo_success(self, scraper):
        """HEYZO-0783 搜尋成功，解析 JSON-LD 所有欄位"""
        mock_resp = _make_mock_resp(status_code=200, content=HEYZO_EN_HTML)

        with patch.object(scraper._session, 'get', return_value=mock_resp):
            with patch('core.scrapers.utils.rate_limit'):
                video = scraper.search("HEYZO-0783")

        assert video is not None
        assert video.number == "HEYZO-0783"
        assert video.title == "Slim Beauty's Seduction"
        assert len(video.actresses) == 1
        assert video.actresses[0].name == "Airi Mashiro"
        assert video.date == "2015-01-17"
        assert video.source == "heyzo"
        assert video.maker == "HEYZO"
        assert video.rating == 4.22

    def test_heyzo_strip_prefix(self, scraper):
        """_extract_heyzo_num 正確提取數字 ID（純邏輯，不需 mock）"""
        assert scraper._extract_heyzo_num("HEYZO-0783") == "0783"
        assert scraper._extract_heyzo_num("heyzo-1031") == "1031"
        assert scraper._extract_heyzo_num("0783") == "0783"
        assert scraper._extract_heyzo_num("INVALID") is None

    def test_heyzo_table_tags(self, scraper):
        """_extract_table_data 從 HTML table 提取 series 和 tags"""
        result = scraper._extract_table_data(HEYZO_EN_HTML)
        assert result['series'] == "Premium Collection"
        assert result['tags'] == ["Cute", "Slender"]

    def test_heyzo_not_found(self, scraper):
        """404 回應時 search 回傳 None"""
        mock_resp = _make_mock_resp(status_code=404)

        with patch.object(scraper._session, 'get', return_value=mock_resp):
            video = scraper.search("HEYZO-9999")

        assert video is None


# ============================================================
# Class 3: TestDMMScraper
# ============================================================

class TestDMMScraper:
    """DMM 爬蟲單元測試（全 mock + cache 隔離）"""

    @pytest.fixture
    def dmm_scraper(self, tmp_path, monkeypatch):
        """DMM scraper with isolated cache files"""
        import core.scrapers.dmm as dmm_module
        monkeypatch.setattr(dmm_module, "CACHE_FILE", tmp_path / "dmm_content_ids.json")
        monkeypatch.setattr(dmm_module, "PREFIX_FILE", tmp_path / "dmm_prefix_hints.json")
        config = ScraperConfig(proxy_url="http://test-proxy:8080")
        return DMMScraper(config)

    def test_dmm_proxy_required(self):
        """無 proxy_url 時 search 立即返回 None，不發任何請求"""
        scraper = DMMScraper()  # 無 proxy_url

        with patch.object(scraper._session, 'post') as mock_post:
            result = scraper.search("SONE-205")

        assert result is None
        mock_post.assert_not_called()

    def test_dmm_cache_hit(self, dmm_scraper, tmp_path, monkeypatch):
        """快取命中時不呼叫 search query（detail query + probe query，不超過 2 次）"""
        import core.scrapers.dmm as dmm_module
        cache_path = tmp_path / "dmm_content_ids.json"
        cache_path.write_text('{"SONE-205": "sone00205"}', encoding='utf-8')

        detail_resp = _make_mock_resp(status_code=200, json_data=DMM_DETAIL_RESPONSE)

        with patch.object(dmm_scraper._session, 'post', return_value=detail_resp) as mock_post:
            with patch('core.scrapers.utils.rate_limit'):
                video = dmm_scraper.search("SONE-205")

        assert video is not None
        assert video.title == "成人への卒業"
        assert video.number == "SONE-205"
        for call_args in mock_post.call_args_list:
            payload = call_args[1].get('json', {}) if call_args[1] else {}
            query_str = payload.get('query', '')
            assert 'legacySearchPPV' not in query_str, "Cache hit should not trigger search query"

    def test_dmm_graphql_success(self, dmm_scraper):
        """無快取時依次呼叫 search query + detail query，成功返回 Video"""
        search_resp = _make_mock_resp(status_code=200, json_data=DMM_SEARCH_RESPONSE)
        detail_resp = _make_mock_resp(status_code=200, json_data=DMM_DETAIL_RESPONSE)

        # 第一次 post = search query（prefix hint 無結果，直接呼叫 _search_content_id）
        # 實際流程：_convert_with_hints 返回 "sone00205"（無 hint 時用預設）→ _fetch_by_id
        # 若 detail 返回 None（我們讓第一次 post 是 detail，返回成功），流程會提早結束
        # 較安全的方式：讓前兩次 post 都返回相應 response
        with patch.object(dmm_scraper._session, 'post', side_effect=[
            _make_mock_resp(status_code=404),  # _convert_with_hints → _fetch_by_id → 404
            search_resp,                        # _search_content_id
            detail_resp,                        # _fetch_by_id(discovered_cid)
        ]):
            with patch('core.scrapers.utils.rate_limit'):
                video = dmm_scraper.search("SONE-205")

        assert video is not None
        assert video.number == "SONE-205"
        assert video.title == "成人への卒業"
        assert video.source == "dmm"
        assert "dmm.co.jp" in video.detail_url
        assert video.date == "2024-03-19"
        assert len(video.actresses) == 1
        assert video.actresses[0].name == "Nana Miho"
        assert video.maker == "S1 NO.1 STYLE"

    def test_dmm_cache_isolation(self, dmm_scraper, tmp_path):
        """搜尋成功後 cache 寫入 tmp_path，不污染 project root"""
        # 讓 _convert_with_hints → _fetch_by_id 成功（第一次 post）
        detail_resp = _make_mock_resp(status_code=200, json_data=DMM_DETAIL_RESPONSE)

        with patch.object(dmm_scraper._session, 'post', return_value=detail_resp):
            with patch('core.scrapers.utils.rate_limit'):
                video = dmm_scraper.search("SONE-205")

        # cache 應寫入 tmp_path 而非 project root
        assert (tmp_path / "dmm_content_ids.json").exists()


# ============================================================
# DMM_DETAIL_RESPONSE_FULL — 包含所有新欄位的完整 fixture
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
            "sampleImages": [
                {"imageUrl": "https://a.jpg"},
                {"imageUrl": "https://b.jpg"},
            ],
        }
    }
}


class TestDMMScraperNewFields:
    """DMM 爬蟲新欄位測試（director / duration / series / label / sample_images）"""

    @pytest.fixture
    def dmm_scraper(self, tmp_path, monkeypatch):
        import core.scrapers.dmm as dmm_module
        monkeypatch.setattr(dmm_module, "CACHE_FILE", tmp_path / "dmm_content_ids.json")
        monkeypatch.setattr(dmm_module, "PREFIX_FILE", tmp_path / "dmm_prefix_hints.json")
        config = ScraperConfig(proxy_url="http://test-proxy:8080")
        return DMMScraper(config)

    def _fetch(self, dmm_scraper, response_data, probe_return=([], "S1 NO.1 STYLE"),
               sample_images_return=[]):
        """Helper：用 mock response 呼叫 search，回傳 Video"""
        detail_resp = _make_mock_resp(status_code=200, json_data=response_data)
        with patch.object(dmm_scraper._session, 'post', return_value=detail_resp), \
             patch.object(dmm_scraper, '_probe_genres', return_value=probe_return), \
             patch.object(dmm_scraper, '_probe_sample_images', return_value=sample_images_return), \
             patch('core.scrapers.utils.rate_limit'):
            return dmm_scraper.search("SONE-205")

    # ------------------------------------------------------------------
    # Happy path — all fields present
    # ------------------------------------------------------------------

    def test_all_new_fields_happy_path(self, dmm_scraper):
        """duration / director / series / label / sample_images 全部正常"""
        video = self._fetch(
            dmm_scraper,
            DMM_DETAIL_RESPONSE_FULL,
            probe_return=([], "S1 NO.1 STYLE"),
            sample_images_return=["https://a.jpg", "https://b.jpg"],
        )

        assert video is not None
        # duration: 8966 // 60 == 149
        assert video.duration == 149
        # director
        assert video.director == "前田文豪"
        # series
        assert video.series == "S1 系列"
        # label from probe
        assert video.label == "S1 NO.1 STYLE"
        # sample_images from probe
        assert video.sample_images == ["https://a.jpg", "https://b.jpg"]

    # ------------------------------------------------------------------
    # duration edge cases
    # ------------------------------------------------------------------

    def test_duration_null(self, dmm_scraper):
        """duration=null → Video.duration is None"""
        data = {
            "data": {
                "ppvContent": {
                    **DMM_DETAIL_RESPONSE_FULL["data"]["ppvContent"],
                    "duration": None,
                }
            }
        }
        video = self._fetch(dmm_scraper, data)
        assert video is not None
        assert video.duration is None

    def test_duration_zero(self, dmm_scraper):
        """duration=0 → Video.duration == 0"""
        data = {
            "data": {
                "ppvContent": {
                    **DMM_DETAIL_RESPONSE_FULL["data"]["ppvContent"],
                    "duration": 0,
                }
            }
        }
        video = self._fetch(dmm_scraper, data)
        assert video is not None
        assert video.duration == 0

    # ------------------------------------------------------------------
    # director edge cases
    # ------------------------------------------------------------------

    def test_directors_empty_list(self, dmm_scraper):
        """directors=[] → Video.director == ''"""
        data = {
            "data": {
                "ppvContent": {
                    **DMM_DETAIL_RESPONSE_FULL["data"]["ppvContent"],
                    "directors": [],
                }
            }
        }
        video = self._fetch(dmm_scraper, data)
        assert video is not None
        assert video.director == ""

    def test_directors_null(self, dmm_scraper):
        """directors=null → Video.director == ''"""
        data = {
            "data": {
                "ppvContent": {
                    **DMM_DETAIL_RESPONSE_FULL["data"]["ppvContent"],
                    "directors": None,
                }
            }
        }
        video = self._fetch(dmm_scraper, data)
        assert video is not None
        assert video.director == ""

    # ------------------------------------------------------------------
    # series edge cases
    # ------------------------------------------------------------------

    def test_series_null(self, dmm_scraper):
        """series=null → Video.series == ''"""
        data = {
            "data": {
                "ppvContent": {
                    **DMM_DETAIL_RESPONSE_FULL["data"]["ppvContent"],
                    "series": None,
                }
            }
        }
        video = self._fetch(dmm_scraper, data)
        assert video is not None
        assert video.series == ""

    # ------------------------------------------------------------------
    # label edge cases (from _probe_genres return value)
    # ------------------------------------------------------------------

    def test_label_from_probe(self, dmm_scraper):
        """probe 回傳 label → Video.label 正確設定"""
        video = self._fetch(dmm_scraper, DMM_DETAIL_RESPONSE_FULL,
                            probe_return=([], "S1 NO.1 STYLE"))
        assert video is not None
        assert video.label == "S1 NO.1 STYLE"

    def test_label_probe_empty(self, dmm_scraper):
        """probe 回傳 '' → Video.label == ''"""
        video = self._fetch(dmm_scraper, DMM_DETAIL_RESPONSE_FULL,
                            probe_return=([], ""))
        assert video is not None
        assert video.label == ""

    # ------------------------------------------------------------------
    # sample_images edge cases
    # ------------------------------------------------------------------

    def test_sample_images_null(self, dmm_scraper):
        """_probe_sample_images 回傳 [] → video.sample_images == []"""
        video = self._fetch(dmm_scraper, DMM_DETAIL_RESPONSE_FULL,
                            probe_return=([], "S1 NO.1 STYLE"),
                            sample_images_return=[])
        assert video is not None
        assert video.sample_images == []

    def test_sample_images_empty_list(self, dmm_scraper):
        """_probe_sample_images 回傳空列表 → video.sample_images == []"""
        video = self._fetch(dmm_scraper, DMM_DETAIL_RESPONSE_FULL,
                            probe_return=([], "S1 NO.1 STYLE"),
                            sample_images_return=[])
        assert video is not None
        assert video.sample_images == []

    def test_sample_images_missing_imageUrl_filtered(self, dmm_scraper):
        """_probe_sample_images 過濾後回傳空列表 → sample_images == []"""
        video = self._fetch(dmm_scraper, DMM_DETAIL_RESPONSE_FULL,
                            probe_return=([], "S1 NO.1 STYLE"),
                            sample_images_return=[])
        assert video is not None
        assert video.sample_images == []


# ============================================================
# Class 4: TestProxyAPI
# ============================================================

class TestProxyAPI:
    """Proxy 測試 API 端點測試"""

    def test_proxy_test_endpoint_success(self, client):
        """Proxy 回傳 200 → success=True, reason='ok'"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("requests.post", return_value=mock_resp):
            resp = client.post("/api/proxy/test", json={"proxy_url": "http://test:8080"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["reason"] == "ok"

    def test_proxy_test_endpoint_403(self, client):
        """Proxy 回傳 403 → success=False, reason='non_jp'"""
        mock_resp = MagicMock()
        mock_resp.status_code = 403

        with patch("requests.post", return_value=mock_resp):
            resp = client.post("/api/proxy/test", json={"proxy_url": "http://test:8080"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["reason"] == "non_jp"

    def test_proxy_test_endpoint_timeout(self, client):
        """ConnectionError → success=False, reason='unreachable'"""
        with patch("requests.post", side_effect=requests.exceptions.ConnectionError):
            resp = client.post("/api/proxy/test", json={"proxy_url": "http://bad:9999"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["reason"] == "unreachable"

    def test_config_proxy_url_persistence(self, client, temp_config_path):
        """proxy_url 寫入 config 後可讀回"""
        # 先取得當前 config，修改 proxy_url，再用 PUT 寫入
        get_resp = client.get("/api/config")
        cfg = get_resp.json()["data"]
        cfg["search"]["proxy_url"] = "http://jp-proxy:8080"
        client.put("/api/config", json=cfg)

        resp = client.get("/api/config")

        assert resp.status_code == 200
        assert resp.json()["data"]["search"]["proxy_url"] == "http://jp-proxy:8080"


# ============================================================
# Class 5: TestPipeline
# ============================================================

class TestPipeline:
    """Pipeline routing 測試（mock scraper.search，驗證路由邏輯）"""

    def test_uncensored_detection_d2pass(self):
        """日期_底線格式番號 → 自動走無碼路徑 → D2PassScraper 被呼叫"""
        mock_video = _make_video("d2pass", "120415_201")

        with patch.object(D2PassScraper, 'search', return_value=mock_video) as mock_d2:
            with patch('core.scrapers.utils.rate_limit'):
                results = smart_search("120415_201")

        assert len(results) == 1
        assert results[0]['_mode'] == 'uncensored'
        mock_d2.assert_called()

    def test_uncensored_detection_heyzo(self):
        """HEYZO- 前綴番號 → 自動走無碼路徑 → HEYZOScraper 被呼叫"""
        mock_video = _make_video("heyzo", "HEYZO-0783")

        with patch.object(D2PassScraper, 'search', return_value=None):
            with patch.object(HEYZOScraper, 'search', return_value=mock_video) as mock_heyzo:
                with patch('core.scrapers.utils.rate_limit'):
                    results = smart_search("HEYZO-0783")

        assert len(results) == 1
        assert results[0]['_mode'] == 'uncensored'
        mock_heyzo.assert_called()

    def test_uncensored_mode_uses_new_sources(self):
        """uncensored_mode=True → D2PassScraper 和 HEYZOScraper 都被嘗試"""
        with patch.object(D2PassScraper, 'search', return_value=None) as mock_d2:
            with patch.object(HEYZOScraper, 'search', return_value=None) as mock_heyzo:
                with patch.object(DMMScraper, 'search', return_value=None):
                    with patch('core.scrapers.utils.rate_limit'):
                        # FC2 / AVSOX 也需要 mock 避免真實網路請求
                        from core.scrapers.fc2 import FC2Scraper
                        from core.scrapers.avsox import AVSOXScraper
                        with patch.object(FC2Scraper, 'search', return_value=None):
                            with patch.object(AVSOXScraper, 'search', return_value=None):
                                smart_search("SONE-205", uncensored_mode=True)

        mock_d2.assert_called()
        mock_heyzo.assert_called()

    def test_dmm_top1_when_proxy(self):
        """primary_source='dmm' + proxy_url + 番號格式 → DMM Top-1 shortcut 被觸發"""
        mock_video = _make_video("dmm", "SONE-205")

        with patch.object(DMMScraper, 'search', return_value=mock_video) as mock_dmm:
            with patch('core.scrapers.utils.rate_limit'):
                results = smart_search("SONE-205", proxy_url="http://proxy:8080", primary_source="dmm")

        mock_dmm.assert_called()
        assert len(results) >= 1
        assert results[0]['_mode'] == 'exact'

    def test_uncensored_mode_fast_path_fc2(self):
        """uncensored_mode=True + FC2 前綴 → D2PassScraper 不被呼叫"""
        mock_video = _make_video("fc2", "FC2-PPV-1234567")

        from core.scrapers.fc2 import FC2Scraper
        from core.scrapers.avsox import AVSOXScraper

        with patch.object(D2PassScraper, 'search', return_value=None) as mock_d2:
            with patch.object(HEYZOScraper, 'search', return_value=None):
                with patch.object(FC2Scraper, 'search', return_value=mock_video):
                    with patch.object(AVSOXScraper, 'search', return_value=None):
                        with patch('core.scrapers.utils.rate_limit'):
                            results = smart_search("FC2-PPV-1234567", uncensored_mode=True)

        assert len(results) == 1
        mock_d2.assert_not_called()

    def test_primary_source_javbus_skips_dmm_shortcut(self):
        """primary_source='javbus'（預設）→ 不走 DMM Top-1 shortcut，走 search_jav(auto)"""
        mock_video = _make_video("javbus", "SONE-205")
        with patch('core.scraper.search_jav', return_value=mock_video.to_legacy_dict()) as mock_sj:
            with patch.object(DMMScraper, 'search') as mock_dmm:
                with patch('core.scraper.get_all_variant_ids', return_value=[]):
                    results = smart_search("SONE-205", proxy_url="http://proxy:8080", primary_source="javbus")
        # DMM shortcut should NOT be called directly
        mock_dmm.assert_not_called()
        # search_jav(auto) should be called
        mock_sj.assert_called()

    def test_dmm_top1_when_proxy_primary_dmm(self):
        """primary_source='dmm' + proxy → DMM Top-1 shortcut"""
        mock_video = _make_video("dmm", "SONE-205")
        with patch.object(DMMScraper, 'search', return_value=mock_video) as mock_dmm:
            with patch('core.scrapers.utils.rate_limit'):
                results = smart_search("SONE-205", proxy_url="http://proxy:8080", primary_source="dmm")
        mock_dmm.assert_called()
        assert len(results) >= 1
        assert results[0]['_mode'] == 'exact'

    def test_primary_source_dmm_no_proxy_fallback(self):
        """primary_source='dmm' + 無 proxy → search_jav(auto) 不含 DMM"""
        mock_video = _make_video("javbus", "SONE-205")
        with patch('core.scraper.search_jav', return_value=mock_video.to_legacy_dict()) as mock_sj:
            with patch('core.scraper.get_all_variant_ids', return_value=[]):
                results = smart_search("SONE-205", proxy_url="", primary_source="dmm")
        # Should still work via search_jav(auto)
        mock_sj.assert_called()

    def test_merge_priority_dmm(self):
        """primary_source='dmm' → DMM 為 main_video"""
        from core.scrapers.jav321 import JAV321Scraper
        from core.scrapers.javdb import JavDBScraper
        from core.scrapers.fc2 import FC2Scraper
        from core.scrapers.avsox import AVSOXScraper
        dmm_video = _make_video("dmm", "SONE-205")
        javbus_video = _make_video("javbus", "SONE-205")

        with patch.object(DMMScraper, 'search', return_value=dmm_video), \
             patch.object(JavBusScraper, 'search', return_value=javbus_video), \
             patch.object(JAV321Scraper, 'search', return_value=None), \
             patch.object(JavDBScraper, 'search', return_value=None), \
             patch.object(FC2Scraper, 'search', return_value=None), \
             patch.object(AVSOXScraper, 'search', return_value=None), \
             patch('core.scrapers.utils.rate_limit'):
            result = search_jav("SONE-205", proxy_url="http://proxy:8080", primary_source="dmm")

        assert result['_source'] == 'dmm'

    def test_merge_priority_javbus(self):
        """primary_source='javbus' → JavBus 為 main_video（即使 DMM 也有結果）"""
        from core.scrapers.jav321 import JAV321Scraper
        from core.scrapers.javdb import JavDBScraper
        from core.scrapers.fc2 import FC2Scraper
        from core.scrapers.avsox import AVSOXScraper
        dmm_video = _make_video("dmm", "SONE-205")
        javbus_video = _make_video("javbus", "SONE-205")

        with patch.object(DMMScraper, 'search', return_value=dmm_video), \
             patch.object(JavBusScraper, 'search', return_value=javbus_video), \
             patch.object(JAV321Scraper, 'search', return_value=None), \
             patch.object(JavDBScraper, 'search', return_value=None), \
             patch.object(FC2Scraper, 'search', return_value=None), \
             patch.object(AVSOXScraper, 'search', return_value=None), \
             patch('core.scrapers.utils.rate_limit'):
            result = search_jav("SONE-205", proxy_url="http://proxy:8080", primary_source="javbus")

        assert result['_source'] == 'javbus'

    def test_get_fuzzy_source_dmm_no_proxy(self):
        """primary_source='dmm' + 無 proxy → fallback to javbus"""
        from core.scraper import _get_fuzzy_source
        assert _get_fuzzy_source('dmm', '') == 'javbus'
        assert _get_fuzzy_source('dmm', None) == 'javbus'
        assert _get_fuzzy_source('dmm', 'http://proxy') == 'dmm'
        assert _get_fuzzy_source('javbus', '') == 'javbus'
        assert _get_fuzzy_source('javbus', 'http://proxy') == 'javbus'

    def test_exact_mode_passes_primary_source(self):
        """REST mode=exact → search_jav() 收到 primary_source（不再被忽略）"""
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        from web.app import app
        from core.scraper import search_jav as real_search_jav

        client = TestClient(app)

        captured_kwargs = {}

        def fake_search_jav(number, source='auto', proxy_url='', primary_source='javbus'):
            captured_kwargs['primary_source'] = primary_source
            captured_kwargs['proxy_url'] = proxy_url
            return None  # no result needed; we only check kwargs

        with patch('core.config.load_config', return_value={
            'search': {
                'proxy_url': 'http://test-proxy:8080',
                'primary_source': 'dmm',
                'uncensored_mode_enabled': False,
            }
        }):
            with patch('web.routers.search.search_jav', side_effect=fake_search_jav):
                client.get("/api/search", params={"q": "SONE-205", "mode": "exact"})

        assert captured_kwargs.get('primary_source') == 'dmm', (
            "mode=exact branch must pass primary_source to search_jav(); "
            f"got {captured_kwargs.get('primary_source')!r}"
        )

    def test_search_actress_dmm_routing(self):
        """search_actress(primary_source='dmm', proxy_url=...) → DMM search_by_keyword_with_ids 先被呼叫"""
        from core.scraper import search_actress

        mock_video = _make_video("dmm", "SONE-205")
        mock_pairs = [("sone00205", mock_video)]

        with patch.object(DMMScraper, 'search_by_keyword_with_ids', return_value=mock_pairs) as mock_dmm_kw, \
             patch.object(DMMScraper, '_fetch_by_id', return_value=mock_video), \
             patch.object(JavBusScraper, 'get_ids_from_search', return_value=[]) as mock_jb, \
             patch('core.scrapers.utils.rate_limit'):
            results = search_actress(
                "未歩なな",
                limit=10,
                primary_source='dmm',
                proxy_url='http://test-proxy:8080',
            )

        mock_dmm_kw.assert_called_once()
        # JavBus should NOT be called since DMM returned results
        mock_jb.assert_not_called()
        assert len(results) == 1
        assert results[0]['source'] == 'dmm'

    def test_search_actress_dmm_fallback_to_javbus(self):
        """search_actress(primary_source='dmm') → DMM 無結果時 fallback 到 JavBus"""
        from core.scraper import search_actress
        from core.scrapers.javdb import JavDBScraper

        # DMM returns nothing → should fall through to JavBus path
        with patch.object(DMMScraper, 'search_by_keyword_with_ids', return_value=[]) as mock_dmm_kw, \
             patch.object(JavBusScraper, 'get_ids_from_search', return_value=[]) as mock_jb, \
             patch.object(JavDBScraper, 'search_by_keyword', return_value=[]) as mock_javdb_kw:
            results = search_actress(
                "未歩なな",
                limit=10,
                primary_source='dmm',
                proxy_url='http://test-proxy:8080',
            )

        mock_dmm_kw.assert_called_once()
        # After DMM returns nothing, JavBus path should be tried
        mock_jb.assert_called()


# ============================================================
# Mock Data — DMM Search List
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


# ============================================================
# Class 6: TestDMMSearchByKeyword
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

    # 1. no proxy → []
    def test_keyword_no_proxy(self):
        """無 proxy_url → search_by_keyword 立即返回 []，不發請求"""
        scraper = DMMScraper()  # no proxy_url

        with patch.object(scraper._session, 'post') as mock_post:
            result = scraper.search_by_keyword("未歩なな")

        assert result == []
        mock_post.assert_not_called()

    # 2. mock response → 2 Videos
    def test_keyword_returns_multiple(self, dmm_scraper):
        """mock response → 回傳 2 個 Video 物件"""
        mock_resp = _make_mock_resp(status_code=200, json_data=DMM_SEARCH_LIST_RESPONSE)

        with patch.object(dmm_scraper._session, 'post', return_value=mock_resp), \
             patch.object(dmm_scraper, '_fetch_by_id', return_value=None), \
             patch('core.scrapers.utils.rate_limit'):
            results = dmm_scraper.search_by_keyword("未歩なな")

        assert len(results) == 2

    # 3. verify each field (fallback path — _fetch_by_id returns None)
    def test_keyword_video_fields(self, dmm_scraper):
        """各欄位正確對應：title, cover_url, actresses, maker, source, number, detail_url"""
        mock_resp = _make_mock_resp(status_code=200, json_data=DMM_SEARCH_LIST_RESPONSE)

        with patch.object(dmm_scraper._session, 'post', return_value=mock_resp), \
             patch.object(dmm_scraper, '_fetch_by_id', return_value=None), \
             patch('core.scrapers.utils.rate_limit'):
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
             patch('core.scrapers.utils.rate_limit'):
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
             patch('core.scrapers.utils.rate_limit'):
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
             patch('core.scrapers.utils.rate_limit'):
            results = dmm_scraper.search_by_keyword("テスト")

        assert len(results) == 1
        assert results[0].cover_url == ""

    # 10. limit is passed to GraphQL variables
    def test_keyword_limit_passed(self, dmm_scraper):
        """limit 參數被正確傳入 GraphQL variables"""
        mock_resp = _make_mock_resp(status_code=200, json_data=DMM_SEARCH_LIST_RESPONSE)

        with patch.object(dmm_scraper._session, 'post', return_value=mock_resp) as mock_post, \
             patch.object(dmm_scraper, '_fetch_by_id', return_value=None), \
             patch('core.scrapers.utils.rate_limit'):
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
             patch('core.scrapers.utils.rate_limit'):
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
             patch('core.scrapers.utils.rate_limit'):
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
             patch('core.scrapers.utils.rate_limit'):
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
             patch('core.scrapers.utils.rate_limit'):
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
             patch('core.scrapers.utils.rate_limit'):
            dmm_scraper.search_by_keyword_with_ids("test")
        mock_fetch.assert_not_called()


# ============================================================
# T3: Facade progressive tests (in TestDMMPipeline class)
# ============================================================

class TestDMMProgressiveFacade:
    """DMM progressive SSE facade tests"""

    def test_search_actress_dmm_routing(self):
        """primary_source='dmm' + proxy → DMM search_by_keyword_with_ids called"""
        from core.scraper import search_actress

        mock_video = _make_video("dmm", "SONE-205")
        mock_pairs = [("sone00205", mock_video)]

        with patch.object(DMMScraper, 'search_by_keyword_with_ids', return_value=mock_pairs), \
             patch.object(DMMScraper, '_fetch_by_id', return_value=mock_video), \
             patch('core.scrapers.utils.rate_limit'):
            results = search_actress("三上悠亜", primary_source="dmm", proxy_url="http://proxy:8080")

        assert len(results) >= 1

    def test_search_actress_dmm_fallback_to_javbus(self):
        """DMM 無結果 → fallback to JavBus"""
        from core.scraper import search_actress

        with patch.object(DMMScraper, 'search_by_keyword_with_ids', return_value=[]), \
             patch.object(JavBusScraper, 'get_ids_from_search', return_value=[]), \
             patch('core.scrapers.utils.rate_limit'):
            results = search_actress("三上悠亜", primary_source="dmm", proxy_url="http://proxy:8080")

        # Falls through to JavBus path; empty result is fine as long as no exception
        assert isinstance(results, list)

    def test_dmm_progressive_fires_callback_per_item(self):
        """DMM progressive: result_callback fires per item via as_completed"""
        from core.scraper import search_actress

        mock_video = _make_video("dmm", "SONE-205")
        mock_pairs = [("sone00205", mock_video), ("sone00300", mock_video)]
        callbacks = []

        def mock_result_callback(slot, data):
            callbacks.append((slot, data))

        with patch.object(DMMScraper, 'search_by_keyword_with_ids', return_value=mock_pairs), \
             patch.object(DMMScraper, '_fetch_by_id', return_value=mock_video), \
             patch('core.scrapers.utils.rate_limit'):
            results = search_actress(
                "三上悠亜",
                primary_source="dmm",
                proxy_url="http://proxy:8080",
                result_callback=mock_result_callback,
            )

        # Should have seed (-1) + 2 items
        seed_calls = [c for c in callbacks if c[0] == -1]
        item_calls = [c for c in callbacks if c[0] >= 0]
        assert len(seed_calls) == 1
        assert len(item_calls) == 2

    def test_dmm_progressive_results_order_matches_seed(self):
        """DMM progressive: 最終回傳順序必須與 seed slot 一致，不受 as_completed 亂序影響"""
        from core.scraper import search_actress

        video1 = _make_video("dmm", "SONE-205")
        video2 = _make_video("dmm", "SONE-300")
        mock_pairs = [("sone00205", video1), ("sone00300", video2)]

        # _fetch_by_id returns enriched videos in predictable order
        enriched1 = Video(number="SONE-205", title="Title 1", source="dmm")
        enriched2 = Video(number="SONE-300", title="Title 2", source="dmm")

        with patch.object(DMMScraper, 'search_by_keyword_with_ids', return_value=mock_pairs), \
             patch.object(DMMScraper, '_fetch_by_id', side_effect=[enriched1, enriched2]), \
             patch('core.scrapers.utils.rate_limit'):
            results = search_actress(
                "三上悠亜",
                primary_source="dmm",
                proxy_url="http://proxy:8080",
            )

        # Results order must match seed order (SONE-205 first, SONE-300 second)
        assert results[0]['number'] == "SONE-205"
        assert results[1]['number'] == "SONE-300"

    def test_uncensored_mode_fast_path_heyzo(self):
        """uncensored_mode=True + HEYZO 前綴 → D2PassScraper 不被呼叫"""
        mock_video = _make_video("heyzo", "HEYZO-0783")

        from core.scrapers.fc2 import FC2Scraper
        from core.scrapers.avsox import AVSOXScraper

        with patch.object(D2PassScraper, 'search', return_value=None) as mock_d2:
            with patch.object(HEYZOScraper, 'search', return_value=mock_video) as mock_heyzo:
                with patch.object(FC2Scraper, 'search', return_value=None):
                    with patch.object(AVSOXScraper, 'search', return_value=None):
                        with patch('core.scrapers.utils.rate_limit'):
                            results = smart_search("HEYZO-0783", uncensored_mode=True)

        assert len(results) == 1
        mock_d2.assert_not_called()


# ============================================================
# Class 6: TestExtractNumber
# ============================================================

class TestExtractNumber:
    """extract_number 和 normalize_number 單元測試"""

    def test_extract_number_underscore_3digit(self):
        """底線格式 3-digit suffix 正確提取"""
        result = extract_number("120415_201.mp4")
        assert result == "120415_201"

    def test_extract_number_underscore_2digit(self):
        """底線格式 2-digit suffix 正確提取"""
        result = extract_number("082912_01.mp4")
        assert result == "082912_01"

    def test_normalize_number_preserves_underscore(self):
        """D2PassScraper.normalize_number 不破壞底線格式番號"""
        scraper = D2PassScraper()
        result = scraper.normalize_number("120415_201")
        assert result == "120415_201"

    def test_extract_number_hyphen_2digit(self):
        """hyphen 格式 2-digit suffix 正確提取（T6b regex 修正）"""
        result = extract_number("041417-41.mp4")
        assert result == "041417-41"


# ============================================================
# Class 7: TestDMMTags
# ============================================================

class TestDMMTags:
    """DMM Tags — GraphQL probe + HTML fallback fail-open 測試"""

    @pytest.fixture
    def dmm_scraper(self, tmp_path, monkeypatch):
        """DMM scraper with isolated cache + reset _genres_supported + _sample_images_supported"""
        import core.scrapers.dmm as dmm_module
        monkeypatch.setattr(dmm_module, "CACHE_FILE", tmp_path / "dmm_content_ids.json")
        monkeypatch.setattr(dmm_module, "PREFIX_FILE", tmp_path / "dmm_prefix_hints.json")
        monkeypatch.setattr(dmm_module, "_genres_supported", None)
        monkeypatch.setattr(dmm_module, "_sample_images_supported", None)
        config = ScraperConfig(proxy_url="http://test-proxy:8080")
        return DMMScraper(config)

    def test_dmm_probe_schema_error(self, dmm_scraper, monkeypatch):
        """GraphQL schema error → _genres_supported=False（永久停用）"""
        import core.scrapers.dmm as dmm_module

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'errors': [{'message': "Unknown field 'genres' on type 'PpvContent'"}]
        }

        with patch.object(dmm_scraper._session, 'post', return_value=mock_resp):
            tags, label = dmm_scraper._probe_genres("sone00205")

        assert tags == []
        assert label == ''
        assert dmm_module._genres_supported is False

    def test_dmm_probe_schema_error_cannot_query(self, dmm_scraper, monkeypatch):
        """GraphQL 'Cannot query field' 變體 → 同樣永久停用"""
        import core.scrapers.dmm as dmm_module

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'errors': [{'message': "Cannot query field 'genres' on type 'PpvContent'"}]
        }

        with patch.object(dmm_scraper._session, 'post', return_value=mock_resp):
            tags, label = dmm_scraper._probe_genres("sone00205")

        assert tags == []
        assert label == ''
        assert dmm_module._genres_supported is False

    def test_dmm_probe_timeout_keeps_none(self, dmm_scraper, monkeypatch):
        """網路錯誤 → _genres_supported 維持 None（暫時性，可重試）"""
        import core.scrapers.dmm as dmm_module

        with patch.object(dmm_scraper._session, 'post', side_effect=Exception("connection timeout")):
            tags, label = dmm_scraper._probe_genres("sone00205")

        assert tags == []
        assert label == ''
        assert dmm_module._genres_supported is None

    def test_dmm_probe_empty_tags_sets_true(self, dmm_scraper, monkeypatch):
        """GraphQL 正常回應但 genres 為空 → _genres_supported=True（schema 支援）"""
        import core.scrapers.dmm as dmm_module

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'data': {'ppvContent': {'genres': [], 'label': None}}
        }

        with patch.object(dmm_scraper._session, 'post', return_value=mock_resp):
            tags, label = dmm_scraper._probe_genres("sone00205")

        assert tags == []
        assert label == ''
        assert dmm_module._genres_supported is True

    def test_dmm_html_fallback_error(self, dmm_scraper):
        """HTML fallback HTTP 500 → 回傳 []，不 crash"""
        mock_resp = MagicMock()
        mock_resp.status_code = 500

        with patch.object(dmm_scraper._session, 'get', return_value=mock_resp):
            tags = dmm_scraper._fetch_tags_from_html("sone00205")

        assert tags == []

    def test_dmm_both_fail_video_intact(self, dmm_scraper, monkeypatch):
        """probe + HTML 都失敗 → Video 仍完整，tags=[]"""
        detail_resp = _make_mock_resp(status_code=200, json_data=DMM_DETAIL_RESPONSE)

        with patch.object(dmm_scraper, '_probe_genres', return_value=([], '')), \
             patch.object(dmm_scraper, '_fetch_tags_from_html', return_value=[]), \
             patch.object(dmm_scraper, '_probe_sample_images', return_value=[]), \
             patch.object(dmm_scraper._session, 'post', return_value=detail_resp), \
             patch('core.scrapers.utils.rate_limit'):
            video = dmm_scraper.search("SONE-205")

        assert video is not None
        assert video.title == "成人への卒業"
        assert video.cover_url == "https://pics.dmm.co.jp/sone205pl.jpg"
        assert video.source == 'dmm'
        assert video.tags == []

    def test_dmm_probe_cache_false_skip(self, dmm_scraper, monkeypatch):
        """_genres_supported=False → 直接跳過，不發 HTTP request"""
        import core.scrapers.dmm as dmm_module
        monkeypatch.setattr(dmm_module, '_genres_supported', False)

        with patch.object(dmm_scraper._session, 'post') as mock_post:
            tags, label = dmm_scraper._probe_genres("sone00205")

        assert tags == []
        assert label == ''
        mock_post.assert_not_called()

    def test_dmm_probe_cache_true_still_query(self, dmm_scraper, monkeypatch):
        """_genres_supported=True → 仍發 HTTP 查詢（該片可能有 tags）"""
        import core.scrapers.dmm as dmm_module
        monkeypatch.setattr(dmm_module, '_genres_supported', True)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'data': {
                'ppvContent': {
                    'genres': [{'name': '美少女'}, {'name': 'ハイビジョン'}],
                    'label': {'name': 'S1 NO.1 STYLE'}
                }
            }
        }

        with patch.object(dmm_scraper._session, 'post', return_value=mock_resp) as mock_post:
            tags, label = dmm_scraper._probe_genres("sone00205")

        mock_post.assert_called_once()
        assert tags == ['美少女', 'ハイビジョン']
        assert label == 'S1 NO.1 STYLE'
        assert dmm_module._genres_supported is True

    def test_sample_images_probe_schema_error(self, dmm_scraper, monkeypatch):
        """sampleImages schema error (HTTP 200) → 永久停用 sampleImages，但 genres 不受影響"""
        import core.scrapers.dmm as dmm_module
        monkeypatch.setattr(dmm_module, '_sample_images_supported', None)
        monkeypatch.setattr(dmm_module, '_genres_supported', True)

        # GraphQL schema errors come as HTTP 200 with errors in the body
        error_resp = _make_mock_resp(status_code=200, json_data={
            "errors": [{"message": "Cannot query field 'sampleImages' on type 'PPVContent'."}],
            "data": None
        })
        with patch.object(dmm_scraper._session, 'post', return_value=error_resp):
            result = dmm_scraper._probe_sample_images("sone00205")

        assert result == []
        assert dmm_module._sample_images_supported is False
        # genres should still be True (unaffected)
        assert dmm_module._genres_supported is True

    def test_sample_images_probe_success(self, dmm_scraper, monkeypatch):
        """sampleImages probe 成功 → 回傳圖片列表"""
        import core.scrapers.dmm as dmm_module
        monkeypatch.setattr(dmm_module, '_sample_images_supported', None)

        success_resp = _make_mock_resp(status_code=200, json_data={
            "data": {"ppvContent": {"sampleImages": [
                {"imageUrl": "https://a.jpg"},
                {"imageUrl": "https://b.jpg"}
            ]}}
        })
        with patch.object(dmm_scraper._session, 'post', return_value=success_resp):
            result = dmm_scraper._probe_sample_images("sone00205")

        assert result == ["https://a.jpg", "https://b.jpg"]
        assert dmm_module._sample_images_supported is True

    def test_sample_images_probe_high_res_url(self, dmm_scraper, monkeypatch):
        """sampleImages URL 轉換為高解析度版本（-N.jpg → jp-N.jpg）"""
        import core.scrapers.dmm as dmm_module
        monkeypatch.setattr(dmm_module, '_sample_images_supported', None)

        success_resp = _make_mock_resp(status_code=200, json_data={
            "data": {"ppvContent": {"sampleImages": [
                {"imageUrl": "https://pics.dmm.co.jp/digital/video/ipzz00698/ipzz00698-1.jpg"},
                {"imageUrl": "https://pics.dmm.co.jp/digital/video/ipzz00698/ipzz00698-10.jpg"},
            ]}}
        })
        with patch.object(dmm_scraper._session, 'post', return_value=success_resp):
            result = dmm_scraper._probe_sample_images("ipzz00698")

        assert result == [
            "https://pics.dmm.co.jp/digital/video/ipzz00698/ipzz00698jp-1.jpg",
            "https://pics.dmm.co.jp/digital/video/ipzz00698/ipzz00698jp-10.jpg",
        ]

    def test_sample_images_probe_non_jpg_preserved(self, dmm_scraper, monkeypatch):
        """非 -N.jpg 格式的 URL 原樣保留"""
        import core.scrapers.dmm as dmm_module
        monkeypatch.setattr(dmm_module, '_sample_images_supported', None)

        success_resp = _make_mock_resp(status_code=200, json_data={
            "data": {"ppvContent": {"sampleImages": [
                {"imageUrl": "https://example.com/sample.png"},
            ]}}
        })
        with patch.object(dmm_scraper._session, 'post', return_value=success_resp):
            result = dmm_scraper._probe_sample_images("test001")

        assert result == ["https://example.com/sample.png"]

    def test_sample_images_probe_already_high_res_idempotent(self, dmm_scraper, monkeypatch):
        """已是高解析度 jp-N.jpg → 不重複轉換（冪等性）"""
        import core.scrapers.dmm as dmm_module
        monkeypatch.setattr(dmm_module, '_sample_images_supported', None)

        success_resp = _make_mock_resp(status_code=200, json_data={
            "data": {"ppvContent": {"sampleImages": [
                {"imageUrl": "https://pics.dmm.co.jp/digital/video/ipzz00698/ipzz00698jp-1.jpg"},
            ]}}
        })
        with patch.object(dmm_scraper._session, 'post', return_value=success_resp):
            result = dmm_scraper._probe_sample_images("ipzz00698")

        # Should NOT become ipzz00698jpjp-1.jpg
        assert result == ["https://pics.dmm.co.jp/digital/video/ipzz00698/ipzz00698jp-1.jpg"]

    def test_sample_images_probe_cache_false_skip(self, dmm_scraper, monkeypatch):
        """_sample_images_supported=False → 不發請求"""
        import core.scrapers.dmm as dmm_module
        monkeypatch.setattr(dmm_module, '_sample_images_supported', False)

        with patch.object(dmm_scraper._session, 'post') as mock_post:
            result = dmm_scraper._probe_sample_images("sone00205")

        assert result == []
        mock_post.assert_not_called()


# ============================================================
# Class 8: TestFastPathRouting
# ============================================================

class TestFastPathRouting:
    """Fast-path routing 測試 — FC2/HEYZO 前綴直接路由到正確來源"""

    def test_fast_path_fc2(self):
        """FC2 前綴 → D2PassScraper 不被呼叫，FC2Scraper 被呼叫"""
        from core.scrapers.fc2 import FC2Scraper
        from core.scrapers.avsox import AVSOXScraper
        mock_video = _make_video("fc2", "FC2-PPV-1234567")

        with patch.object(D2PassScraper, 'search', return_value=None) as mock_d2:
            with patch.object(HEYZOScraper, 'search', return_value=None) as mock_heyzo:
                with patch.object(FC2Scraper, 'search', return_value=mock_video) as mock_fc2:
                    with patch.object(AVSOXScraper, 'search', return_value=None):
                        with patch('core.scrapers.utils.rate_limit'):
                            results = smart_search("FC2-PPV-1234567")

        assert len(results) == 1
        assert results[0]['_mode'] == 'uncensored'
        mock_fc2.assert_called()
        mock_d2.assert_not_called()
        mock_heyzo.assert_not_called()

    def test_fast_path_heyzo(self):
        """HEYZO 前綴 → D2PassScraper 不被呼叫，HEYZOScraper 被呼叫"""
        from core.scrapers.fc2 import FC2Scraper
        from core.scrapers.avsox import AVSOXScraper
        mock_video = _make_video("heyzo", "HEYZO-0783")

        with patch.object(D2PassScraper, 'search', return_value=None) as mock_d2:
            with patch.object(HEYZOScraper, 'search', return_value=mock_video) as mock_heyzo:
                with patch.object(FC2Scraper, 'search', return_value=None) as mock_fc2:
                    with patch.object(AVSOXScraper, 'search', return_value=None):
                        with patch('core.scrapers.utils.rate_limit'):
                            results = smart_search("HEYZO-0783")

        assert len(results) == 1
        assert results[0]['_mode'] == 'uncensored'
        mock_heyzo.assert_called()
        mock_d2.assert_not_called()
        mock_fc2.assert_not_called()

    def test_fast_path_d2pass_unchanged(self):
        """D2Pass 日期格式 → D2PassScraper 被呼叫（完整路由不變）"""
        mock_video = _make_video("d2pass", "120415_201")

        with patch.object(D2PassScraper, 'search', return_value=mock_video) as mock_d2:
            with patch('core.scrapers.utils.rate_limit'):
                results = smart_search("120415_201")

        assert len(results) == 1
        assert results[0]['_mode'] == 'uncensored'
        mock_d2.assert_called()


# ============================================================
# Class 9: TestUnknownSource
# ============================================================

class TestUnknownSource:
    """未知 source 驗證測試 — 確保 JavGuru 等已移除來源明確失敗"""

    def test_search_jav_unknown_source_returns_none(self):
        """search_jav 傳入未知來源（如 'javguru'）→ 立即返回 None，不走 auto mode"""
        # 確認完全不呼叫任何 scraper
        with patch.object(JavBusScraper, 'search', return_value=None) as mock_jb:
            with patch.object(DMMScraper, 'search', return_value=None) as mock_dmm:
                result = search_jav("SONE-205", source="javguru")

        assert result is None
        mock_jb.assert_not_called()
        mock_dmm.assert_not_called()

    def test_search_jav_unknown_source_no_fallback(self):
        """未知來源不應 fallback 到 auto mode — 即使 scraper 能找到結果也應被攔截"""
        from core.scrapers.models import Video

        mock_video = Video(
            number="SONE-205",
            title="Should Not Appear",
            actresses=[],
            date="2024-01-01",
            maker="Test",
            cover_url="",
            tags=[],
            source="javbus",
            detail_url="https://example.com",
        )

        with patch.object(JavBusScraper, 'search', return_value=mock_video):
            result = search_jav("SONE-205", source="javguru")

        assert result is None

    def test_api_unknown_source_returns_400(self):
        """GET /api/search?q=SONE-205&source=javguru → HTTP 400"""
        client = TestClient(app)
        resp = client.get("/api/search", params={"q": "SONE-205", "source": "javguru"})

        assert resp.status_code == 400
        data = resp.json()
        assert "error" in data
        assert "javguru" in data["error"]
