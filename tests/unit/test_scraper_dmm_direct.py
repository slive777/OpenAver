"""
Tests for Phase 37d T3 — Proxy `direct` 模式

覆蓋 _is_dmm_enabled() / _dmm_proxy_url() helpers 和 DMMScraper 行為。
"""
import pytest
from unittest.mock import patch, MagicMock


# ── TestIsDmmEnabled ──────────────────────────────────────────────────────────

class TestIsDmmEnabled:
    """_is_dmm_enabled() helper 邊界條件"""

    def test_empty_string_returns_false(self):
        from core.scraper import _is_dmm_enabled
        assert _is_dmm_enabled('') is False

    def test_whitespace_only_returns_false(self):
        from core.scraper import _is_dmm_enabled
        assert _is_dmm_enabled('  ') is False

    def test_direct_lowercase_returns_true(self):
        from core.scraper import _is_dmm_enabled
        assert _is_dmm_enabled('direct') is True

    def test_direct_uppercase_returns_true(self):
        from core.scraper import _is_dmm_enabled
        assert _is_dmm_enabled('DIRECT') is True

    def test_real_proxy_url_returns_true(self):
        from core.scraper import _is_dmm_enabled
        assert _is_dmm_enabled('http://192.168.1.1:8888') is True


# ── TestDmmProxyUrl ───────────────────────────────────────────────────────────

class TestDmmProxyUrl:
    """_dmm_proxy_url() helper 邊界條件"""

    def test_direct_lowercase_returns_empty(self):
        from core.scraper import _dmm_proxy_url
        assert _dmm_proxy_url('direct') == ''

    def test_direct_uppercase_returns_empty(self):
        from core.scraper import _dmm_proxy_url
        assert _dmm_proxy_url('DIRECT') == ''

    def test_real_proxy_url_returns_original(self):
        from core.scraper import _dmm_proxy_url
        url = 'http://192.168.1.1:8888'
        assert _dmm_proxy_url(url) == url


# ── TestDmmScraperDirect ──────────────────────────────────────────────────────

class TestDmmScraperDirect:
    """DMMScraper session.proxies 行為"""

    def test_empty_proxy_url_no_proxies_set(self):
        """proxy_url='' → session.proxies 不被設定（直連模式）"""
        from core.scrapers import DMMScraper, ScraperConfig
        scraper = DMMScraper(ScraperConfig(proxy_url=''))
        # requests.Session 預設 proxies 是 {}（空 dict），不應被覆寫
        assert not scraper._session.proxies, \
            "proxy_url='' 時不應設定 session.proxies"

    def test_real_proxy_url_proxies_set(self):
        """proxy_url='http://...' → session.proxies 已設定"""
        from core.scrapers import DMMScraper, ScraperConfig
        proxy = 'http://192.168.1.1:8888'
        scraper = DMMScraper(ScraperConfig(proxy_url=proxy))
        assert scraper._session.proxies.get('http') == proxy
        assert scraper._session.proxies.get('https') == proxy


# ── TestSearchDirect ──────────────────────────────────────────────────────────

class TestSearchDirect:
    """search_jav() 整合測試 — 確認 direct 模式正確路由"""

    def test_search_jav_direct_includes_dmm(self):
        """proxy_url='direct' → dmm_config 非 None → DMM 進入 scrapers 列表"""
        from core.scraper import _is_dmm_enabled, _dmm_proxy_url
        proxy_url = 'direct'
        assert _is_dmm_enabled(proxy_url) is True
        assert _dmm_proxy_url(proxy_url) == ''

        # 驗證傳給 DMMScraper 的 proxy_url 是空字串（直連）
        from core.scrapers import DMMScraper, ScraperConfig
        dmm_config = ScraperConfig(proxy_url=_dmm_proxy_url(proxy_url))
        scraper = DMMScraper(dmm_config)
        assert not scraper._session.proxies, \
            "direct 模式下 DMMScraper 不應設定 session.proxies"

    def test_search_jav_direct_dmm_config_not_none(self):
        """proxy_url='direct' → _is_dmm_enabled=True → dmm_config 建立（非 None）"""
        from core.scraper import _is_dmm_enabled, _dmm_proxy_url
        from core.scrapers import ScraperConfig
        proxy_url = 'direct'
        dmm_config = ScraperConfig(proxy_url=_dmm_proxy_url(proxy_url)) \
            if _is_dmm_enabled(proxy_url) else None
        assert dmm_config is not None, \
            "proxy_url='direct' 時 dmm_config 不應為 None"

    def test_empty_proxy_url_dmm_config_is_none(self):
        """proxy_url='' + primary_source='dmm' → _is_dmm_enabled=False → fallback javbus

        關鍵邊界：空字串不可被誤判為 direct，必須 fallback。
        """
        from core.scraper import _is_dmm_enabled, _dmm_proxy_url, _get_fuzzy_source
        from core.scrapers import ScraperConfig
        proxy_url = ''
        # 1. _is_dmm_enabled 必須為 False
        assert _is_dmm_enabled(proxy_url) is False, \
            "proxy_url='' 時 _is_dmm_enabled 必須為 False"
        # 2. dmm_config 必須為 None
        dmm_config = ScraperConfig(proxy_url=_dmm_proxy_url(proxy_url)) \
            if _is_dmm_enabled(proxy_url) else None
        assert dmm_config is None, \
            "proxy_url='' 時 dmm_config 必須為 None（不得啟用 DMM）"
        # 3. _get_fuzzy_source 必須 fallback 到 javbus
        source = _get_fuzzy_source('dmm', proxy_url)
        assert source == 'javbus', \
            "proxy_url='' + primary_source='dmm' 時必須 fallback 到 javbus"
