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
<tr><th>Series</th><td>Premium Collection</td></tr>
<tr><th>Actress Type</th><td><a>Cute</a> <a>Slender</a></td></tr>
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
        # 快取命中 → 不呼叫 search query；payload 中不含 legacySearchPPV
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
        assert video.number != ""
        assert video.title != ""
        assert video.source == "dmm"
        assert "dmm.co.jp" in video.detail_url

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
# Class 4: TestProxyAPI
# ============================================================

class TestProxyAPI:
    """Proxy 測試 API 端點測試"""

    @pytest.fixture
    def client(self):
        return TestClient(app)

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

    def _make_video(self, source: str, number: str = "TEST-001") -> Video:
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

    def test_uncensored_detection_d2pass(self):
        """日期_底線格式番號 → 自動走無碼路徑 → D2PassScraper 被呼叫"""
        mock_video = self._make_video("d2pass", "120415_201")

        with patch.object(D2PassScraper, 'search', return_value=mock_video) as mock_d2:
            with patch('core.scrapers.utils.rate_limit'):
                results = smart_search("120415_201")

        assert len(results) == 1
        assert results[0]['_mode'] == 'uncensored'
        mock_d2.assert_called()

    def test_uncensored_detection_heyzo(self):
        """HEYZO- 前綴番號 → 自動走無碼路徑 → HEYZOScraper 被呼叫"""
        mock_video = self._make_video("heyzo", "HEYZO-0783")

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
        """有 proxy_url 且搜尋番號格式 → DMM 優先於 variant IDs"""
        mock_video = self._make_video("dmm", "SONE-205")

        with patch.object(DMMScraper, 'search', return_value=mock_video) as mock_dmm:
            with patch('core.scrapers.utils.rate_limit'):
                results = smart_search("SONE-205", proxy_url="http://proxy:8080")

        mock_dmm.assert_called()
        assert len(results) >= 1
        assert results[0]['_mode'] == 'exact'

    def test_uncensored_mode_fast_path_fc2(self):
        """uncensored_mode=True + FC2 前綴 → D2PassScraper 不被呼叫"""
        mock_video = self._make_video("fc2", "FC2-PPV-1234567")

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

    def test_uncensored_mode_fast_path_heyzo(self):
        """uncensored_mode=True + HEYZO 前綴 → D2PassScraper 不被呼叫"""
        mock_video = self._make_video("heyzo", "HEYZO-0783")

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
        """DMM scraper with isolated cache + reset _genres_supported"""
        import core.scrapers.dmm as dmm_module
        monkeypatch.setattr(dmm_module, "CACHE_FILE", tmp_path / "dmm_content_ids.json")
        monkeypatch.setattr(dmm_module, "PREFIX_FILE", tmp_path / "dmm_prefix_hints.json")
        monkeypatch.setattr(dmm_module, "_genres_supported", None)
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
             patch.object(dmm_scraper._session, 'post', return_value=detail_resp), \
             patch('core.scrapers.utils.rate_limit'):
            video = dmm_scraper.search("SONE-205")

        assert video is not None
        assert video.title != ''
        assert video.cover_url != ''
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


# ============================================================
# Class 8: TestFastPathRouting
# ============================================================

class TestFastPathRouting:
    """Fast-path routing 測試 — FC2/HEYZO 前綴直接路由到正確來源"""

    def _make_video(self, source: str, number: str = "TEST-001") -> Video:
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

    def test_fast_path_fc2(self):
        """FC2 前綴 → D2PassScraper 不被呼叫，FC2Scraper 被呼叫"""
        from core.scrapers.fc2 import FC2Scraper
        from core.scrapers.avsox import AVSOXScraper
        mock_video = self._make_video("fc2", "FC2-PPV-1234567")

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
        mock_video = self._make_video("heyzo", "HEYZO-0783")

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
        mock_video = self._make_video("d2pass", "120415_201")

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
