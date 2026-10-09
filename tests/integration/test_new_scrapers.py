"""
Integration tests for scraper-related API endpoints (TestClient).

Covers:
- Proxy test endpoint (success / 403 / timeout / config persistence)
- Unknown source returns HTTP 400
"""
import pytest
import requests
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient
from web.app import app


# ============================================================
# TestProxyAPI — proxy test endpoint via TestClient
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
        """DMM 回傳 403 → success=False, reason='refused'（假回應只驗接線）"""
        mock_resp = MagicMock()
        mock_resp.status_code = 403

        with patch("requests.post", return_value=mock_resp):
            resp = client.post("/api/proxy/test", json={"proxy_url": "http://test:8080"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["reason"] == "refused"
        assert "拒絕連線" in data["message"]
        assert "日本 IP" in data["message"]

    def test_proxy_test_500_is_refused_too(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        with patch("requests.post", return_value=mock_resp):
            data = client.post("/api/proxy/test", json={"proxy_url": "http://test:8080"}).json()
        assert data["success"] is False
        assert data["reason"] == "refused"

    @pytest.mark.parametrize("body", [{"proxy_url": ""}, {"proxy_url": "   "}, {}])
    def test_proxy_test_blank_uses_system_proxy(self, client, temp_config_path, body):
        """空白／省略 → requests.post 不帶 proxies kwarg（系統代理），即使 live config 有值"""
        from core.config import load_config, save_config
        cfg = load_config()
        cfg.setdefault("search", {})["proxy_url"] = "http://live:1111"
        save_config(cfg)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("requests.post", return_value=mock_resp) as m:
            data = client.post("/api/proxy/test", json=body).json()
        assert data["success"] is True and data["reason"] == "ok"
        assert "proxies" not in m.call_args.kwargs

    def test_proxy_test_uses_body_snapshot_not_live_config(self, client, temp_config_path):
        from core.config import load_config, save_config
        cfg = load_config()
        cfg.setdefault("search", {})["proxy_url"] = "http://live:1111"
        save_config(cfg)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("requests.post", return_value=mock_resp) as m:
            client.post("/api/proxy/test", json={"proxy_url": "http://body:2222"})
        assert m.call_args.kwargs["proxies"] == {"http": "http://body:2222", "https": "http://body:2222"}

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
# TestUnknownSource — unknown source returns HTTP 400
# ============================================================

class TestUnknownSource:
    """未知 source 驗證測試 — API 層回傳 HTTP 400"""

    def test_api_unknown_source_returns_400(self):
        """GET /api/search?q=SONE-205&source=javguru → HTTP 400"""
        client = TestClient(app)
        resp = client.get("/api/search", params={"q": "SONE-205", "source": "javguru"})

        assert resp.status_code == 400
        data = resp.json()
        assert "error" in data
        assert "javguru" in data["error"]
