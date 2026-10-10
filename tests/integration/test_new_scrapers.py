"""
Integration tests for scraper-related API endpoints (TestClient).

Covers:
- Proxy config persistence
- Unknown source returns HTTP 400
"""
from fastapi.testclient import TestClient
from web.app import app


# ============================================================
# TestProxyConfigPersistence — proxy_url 存檔還原
# ============================================================

class TestProxyConfigPersistence:
    """Proxy 設定存檔測試"""

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
