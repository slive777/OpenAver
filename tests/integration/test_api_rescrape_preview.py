"""
test_api_rescrape_preview.py - POST /api/rescrape/preview 端點整合測試

預覽端點只搜不寫，復用 B1 搜尋路徑（auto → search_jav，具體源 → search_jav_single_source）。
使用 FastAPI TestClient + mocker，mock core 層搜尋函數。
"""

import pytest


def _scraper_dict(**kw):
    """建立成功的 scraper 回傳 dict（mirror to_legacy_dict shape，CD-62-3 key 命名）。"""
    d = dict(
        number="SONE-205",
        title="Test Title",
        maker="Test Maker",
        date="2024-01-01",
        cover="https://example.com/cover.jpg",
        tags=["tag1"],
        source="javbus",
        url="https://example.com/SONE-205",
        director="",
        duration=120,
        label="",
        series="",
        sample_images=[],
        actors=["Actor A"],
        _source="javbus",
    )
    d.update(kw)
    return d


class TestRescrapePreviewEndpoint:
    def test_preview_specific_source_calls_single_source(self, client, mocker):
        """具體來源 → 呼叫 search_jav_single_source(number, source, proxy_url)，回 dict + success:True。"""
        mock_single = mocker.patch(
            "web.routers.scraper.search_jav_single_source",
            return_value=_scraper_dict(),
        )

        response = client.post("/api/rescrape/preview", json={
            "number": "SONE-205",
            "source": "javdb",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["title"] == "Test Title"
        assert mock_single.called
        args = mock_single.call_args.args
        # (number, source, proxy_url) — number/source 在 args 前兩位
        assert args[0] == "SONE-205"
        assert args[1] == "javdb"

    def test_preview_specific_source_does_not_call_search_jav_auto_path(self, client, mocker):
        """具體來源不走 auto 版 search_jav（直接攔截 single_source 命名空間）。"""
        mocker.patch(
            "web.routers.scraper.search_jav_single_source",
            return_value=_scraper_dict(),
        )
        mock_auto = mocker.patch(
            "web.routers.scraper.search_jav",
            return_value=_scraper_dict(),
        )

        client.post("/api/rescrape/preview", json={
            "number": "SONE-205",
            "source": "javdb",
        })

        mock_auto.assert_not_called()

    def test_preview_auto_calls_search_jav(self, client, mocker):
        """source=auto → 呼叫 search_jav，source='auto' + proxy/primary 從 config。"""
        mock_auto = mocker.patch(
            "web.routers.scraper.search_jav",
            return_value=_scraper_dict(),
        )

        response = client.post("/api/rescrape/preview", json={
            "number": "SONE-205",
            "source": "auto",
        })

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert mock_auto.called
        kwargs = mock_auto.call_args.kwargs
        assert kwargs.get("source") == "auto"

    def test_preview_auto_default_source(self, client, mocker):
        """省略 source 走預設 auto → search_jav。"""
        mock_auto = mocker.patch(
            "web.routers.scraper.search_jav",
            return_value=_scraper_dict(),
        )

        response = client.post("/api/rescrape/preview", json={
            "number": "SONE-205",
        })

        assert response.status_code == 200
        assert mock_auto.called
        assert mock_auto.call_args.kwargs.get("source") == "auto"

    def test_preview_writes_nothing(self, client, mocker):
        """preview 不呼叫 enrich_single（不寫任何檔）。"""
        mocker.patch(
            "web.routers.scraper.search_jav",
            return_value=_scraper_dict(),
        )
        mock_enrich = mocker.patch("web.routers.scraper.enrich_single")

        client.post("/api/rescrape/preview", json={
            "number": "SONE-205",
            "source": "auto",
        })

        mock_enrich.assert_not_called()

    def test_preview_not_found_returns_success_false(self, client, mocker):
        """搜尋回 None → 200 {success:False}。"""
        mocker.patch(
            "web.routers.scraper.search_jav",
            return_value=None,
        )

        response = client.post("/api/rescrape/preview", json={
            "number": "SONE-999",
            "source": "auto",
        })

        assert response.status_code == 200
        assert response.json()["success"] is False

    def test_preview_reads_proxy_and_primary_from_search_config(self, client, mocker):
        """proxy_url / primary_source 從 config['search'] 取得。"""
        mock_auto = mocker.patch(
            "web.routers.scraper.search_jav",
            return_value=_scraper_dict(),
        )
        mocker.patch("web.routers.scraper.load_config", return_value={
            "search": {
                "proxy_url": "http://proxy.test:8888",
                "primary_source": "javdb",
            },
        })

        client.post("/api/rescrape/preview", json={
            "number": "SONE-205",
            "source": "auto",
        })

        kwargs = mock_auto.call_args.kwargs
        assert kwargs.get("proxy_url") == "http://proxy.test:8888"
        assert kwargs.get("primary_source") == "javdb"

    def test_preview_missing_number_returns_422(self, client):
        """漏 number → 422（Pydantic）。"""
        response = client.post("/api/rescrape/preview", json={
            "source": "auto",
        })
        assert response.status_code == 422

    def test_preview_exception_returns_success_false(self, client, mocker):
        """搜尋拋例外 → 200 {success:False}，且原始 exception 訊息不洩漏。"""
        mocker.patch(
            "web.routers.scraper.search_jav",
            side_effect=RuntimeError("boom"),
        )

        response = client.post("/api/rescrape/preview", json={
            "number": "SONE-205",
            "source": "auto",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "boom" not in str(data.get("error", ""))
