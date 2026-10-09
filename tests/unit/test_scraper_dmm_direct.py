"""
DMMScraper 行為：未被 proxy policy 選中時尊重系統代理（CD-134-6），以及 DMM 刮削主體。

DMM 開關看膠囊、代理選擇看 core/proxy_policy.py（TASK-163a-T3a）。
"""
import os

import pytest
from unittest.mock import patch, MagicMock

from core.scrapers.dmm import DMMScraper
from core.proxy_policy import ProxySettings
from core.scrapers.models import ScraperConfig

_NO_PROXY = ScraperConfig(proxy_settings=ProxySettings(url=''))  # hermetic：不讀 live config


# ── TestDmmRespectsSystemProxy ───────────────────────────────────────────────

_PROXY_ENVS = (
    "HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy",
    "NO_PROXY", "no_proxy", "ALL_PROXY", "all_proxy",
)


@pytest.fixture
def clean_proxy_env(monkeypatch):
    for name in _PROXY_ENVS:
        monkeypatch.delenv(name, raising=False)
    # urllib 的 getproxies_environment（requests 經 get_environ_proxies 走它）掃的是
    # **任何以 `_proxy` 結尾**的變數，不只上面那 8 個——開發機上若有 ftp_proxy /
    # socks_proxy 之類殘留，「無代理」那支會假紅。清乾淨這一整類。
    for name in [n for n in os.environ if n.lower().endswith("_proxy")]:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def _resolved_proxies(scraper, url="https://api.video.dmm.co.jp/graphql"):
    """把 requests 對環境變數的解析結果變成可斷言的具體值。"""
    return scraper._session.merge_environment_settings(url, {}, None, None, None)["proxies"]


class TestDmmRespectsSystemProxy:
    """CD-134-6／F4：direct 模式尊重系統代理（環境變數，三象限，斷言值互不相同）"""

    def test_empty_proxy_url_trust_env_true(self):
        """proxy_url='' → trust_env=True（尊重系統代理，CD-134-6／F4 反轉後的新契約）"""
        scraper = DMMScraper(_NO_PROXY)
        assert scraper._session.trust_env is True, \
            "proxy_url='' 時 trust_env 必須為 True（尊重系統代理，見 spec-134 F4）"

    def test_empty_proxy_url_proxies_empty(self):
        """proxy_url='' → session.proxies 為空（交由 requests 依系統環境決定）"""
        scraper = DMMScraper(_NO_PROXY)
        assert not scraper._session.proxies, \
            "proxy_url='' 時 session.proxies 必須為空"

    def test_env_https_proxy_is_respected(self, clean_proxy_env):
        """HTTPS_PROXY 有設 → 解析結果含該 proxy"""
        clean_proxy_env.setenv("HTTPS_PROXY", "http://env-proxy:1")
        scraper = DMMScraper(_NO_PROXY)
        assert _resolved_proxies(scraper)["https"] == "http://env-proxy:1"

    def test_env_no_proxy_excludes_dmm_host(self, clean_proxy_env):
        """HTTPS_PROXY 有設 + NO_PROXY 命中 DMM API host → 代理被排除"""
        clean_proxy_env.setenv("HTTPS_PROXY", "http://env-proxy:1")
        clean_proxy_env.setenv("NO_PROXY", "api.video.dmm.co.jp")
        scraper = DMMScraper(_NO_PROXY)
        assert _resolved_proxies(scraper) == {}

    def test_env_no_proxy_vars_is_clean_direct(self, clean_proxy_env):
        """無任何代理環境變數 → 解析結果無代理"""
        scraper = DMMScraper(_NO_PROXY)
        assert _resolved_proxies(scraper) == {}


# ============================================================
# Mock Data (from test_new_scrapers.py)
# ============================================================

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
# Tests merged from integration/test_new_scrapers.py TestDMMScraper
# ============================================================

class TestDMMScraperIntegration:
    """DMM scraper tests (merged from test_new_scrapers.py)"""

    @pytest.fixture(autouse=True)
    def _no_rate_limit(self, monkeypatch):
        """跳過 rate_limit sleep，加速測試"""
        monkeypatch.setattr("core.scrapers.dmm.rate_limit", lambda *a, **kw: None)

    @pytest.fixture
    def dmm_scraper(self, monkeypatch):
        """DMM scraper fixture"""
        import core.scrapers.dmm as dmm_module
        monkeypatch.setattr(dmm_module, "_shipped_table_cache", {})
        config = ScraperConfig(proxy_settings=ProxySettings(url="http://test-proxy:8080"))
        return DMMScraper(config)

    def test_dmm_no_proxy_session_proxies_not_set(self):
        """Proxy 欄空白時 session.proxies 不被設定（直連模式）"""
        scraper = DMMScraper(_NO_PROXY)
        assert not scraper._session.proxies, \
            "proxy_url='' 時 session.proxies 不應被設定"

    def test_dmm_cache_hit(self, dmm_scraper):
        """前綴表命中時不呼叫 search query（detail query + probe query，不超過 2 次）"""
        detail_resp = _make_mock_resp(status_code=200, json_data=DMM_DETAIL_RESPONSE)

        with patch.object(dmm_scraper._session, 'post', return_value=detail_resp) as mock_post, \
             patch.object(dmm_scraper, '_fetch_tags_from_html', return_value=[]), \
             patch('core.scrapers.dmm.rate_limit'):
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

        with patch.object(dmm_scraper._session, 'post', side_effect=[
            _make_mock_resp(status_code=200, json_data={"data": {"ppvContent": None}}),  # 補零第一試 → 查無
            _make_mock_resp(status_code=200, json_data={"data": {"ppvContent": None}}),  # 不補零第二試 → 查無
            search_resp,                        # _search_content_id
            detail_resp,                        # _fetch_by_id(discovered_cid)
        ]), \
             patch.object(dmm_scraper, '_fetch_tags_from_html', return_value=[]), \
             patch('core.scrapers.dmm.rate_limit'):
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

    def test_dmm_search_success_writes_no_files(self, dmm_scraper, tmp_path, monkeypatch):
        """搜尋**成功**之後，專案根不得多出任何 DMM 資料檔（T12 DoD 2/3 的成功路徑那一半）。

        ⚠️ 2026-08-29 兩位 reviewer 各自指出：本測試改名前的斷言
        ``assert not (tmp_path / "dmm_content_ids.json").exists()`` **是恆真的**——
        沒有任何東西被指到 ``tmp_path``，就算有人把「寫快取」加回專案根，它也不會紅。

        姊妹測試 ``test_poisoned_local_files_do_not_affect_search`` 把 ``_fetch_by_id``
        mock 成恆回 ``None`` ⇒ 它只走得到**失敗**路徑，踩不到「搜尋成功後寫檔」那一段。
        ⇒ **成功路徑的「不寫檔」必須由這一支扛**，所以這裡把 ``PROJECT_ROOT`` 真的
        monkeypatch 到 ``tmp_path``，讓「有人把寫檔加回來」這件事在這裡看得見。
        """
        import core.scrapers.dmm as dmm_module
        monkeypatch.setattr(dmm_module, "PROJECT_ROOT", tmp_path)

        detail_resp = _make_mock_resp(status_code=200, json_data=DMM_DETAIL_RESPONSE)

        with patch.object(dmm_scraper._session, 'post', return_value=detail_resp), \
             patch.object(dmm_scraper, '_fetch_tags_from_html', return_value=[]), \
             patch('core.scrapers.dmm.rate_limit'):
            video = dmm_scraper.search("SONE-205")

        # 正向：這一輪真的成功了（否則下面的反向斷言會恆真）
        assert video is not None
        assert video.number == "SONE-205"

        # 反向：成功路徑一個檔都沒寫
        assert list(tmp_path.iterdir()) == [], (
            f"搜尋成功後 PROJECT_ROOT 多出檔案：{[p.name for p in tmp_path.iterdir()]}"
        )
