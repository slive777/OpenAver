"""
test_api_enrich.py - POST /api/enrich-single 端點整合測試

使用 FastAPI TestClient + mocker，mock core 層函數。
"""

import pytest
from unittest.mock import patch, MagicMock
from dataclasses import dataclass, field
from typing import List, Optional


# ── helper: EnrichResult stub ────────────────────────────────────────────────

def _ok_result(**kwargs):
    """建立成功的 EnrichResult-like dict 作為 mock 回傳值"""
    from core.enricher import EnrichResult
    defaults = dict(
        success=True,
        nfo_written=True,
        cover_written=True,
        extrafanart_written=0,
        fields_filled=[],
        source_used="db",
        error=None,
    )
    defaults.update(kwargs)
    return EnrichResult(**defaults)


def _err_result(error: str):
    from core.enricher import EnrichResult
    return EnrichResult(
        success=False,
        nfo_written=False,
        cover_written=False,
        extrafanart_written=0,
        fields_filled=[],
        source_used="",
        error=error,
    )


# ── 端點基本測試 ──────────────────────────────────────────────────────────────

class TestEnrichSingleEndpoint:
    def test_success_returns_200(self, client, mocker):
        """正常請求回傳 200，success=True"""
        mocker.patch("web.routers.scraper.enrich_single", return_value=_ok_result())

        response = client.post("/api/enrich-single", json={
            "file_path": "/video/SONE-205.mp4",
            "number": "SONE-205",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["nfo_written"] is True

    def test_file_not_found_returns_error(self, client, mocker):
        """檔案不存在 → success=False"""
        mocker.patch(
            "web.routers.scraper.enrich_single",
            return_value=_err_result("檔案不存在"),
        )

        response = client.post("/api/enrich-single", json={
            "file_path": "/nonexistent/SONE-205.mp4",
            "number": "SONE-205",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "不存在" in data["error"]

    def test_missing_number_field_returns_422(self, client):
        """number 為必填：未提供時回傳 422"""
        response = client.post("/api/enrich-single", json={
            "file_path": "/video/SONE-205.mp4",
            # number 省略
        })
        assert response.status_code == 422

    def test_missing_file_path_returns_422(self, client):
        """file_path 為必填：未提供時回傳 422"""
        response = client.post("/api/enrich-single", json={
            "number": "SONE-205",
        })
        assert response.status_code == 422

    def test_mode_fill_missing_passed(self, client, mocker):
        """mode=fill_missing 正確傳入 enrich_single"""
        mock_fn = mocker.patch(
            "web.routers.scraper.enrich_single",
            return_value=_ok_result(source_used="db"),
        )

        client.post("/api/enrich-single", json={
            "file_path": "/video/SONE-205.mp4",
            "number": "SONE-205",
            "mode": "fill_missing",
        })

        call_kwargs = mock_fn.call_args
        assert call_kwargs is not None
        # 確認 mode 正確傳入
        kwargs = call_kwargs.kwargs if call_kwargs.kwargs else {}
        args = call_kwargs.args if call_kwargs.args else ()
        # mode 可能是 positional 或 keyword
        assert "fill_missing" in str(call_kwargs)

    def test_mode_db_to_sidecar_passed(self, client, mocker):
        """mode=db_to_sidecar 正確傳入"""
        mock_fn = mocker.patch(
            "web.routers.scraper.enrich_single",
            return_value=_ok_result(source_used="db"),
        )

        client.post("/api/enrich-single", json={
            "file_path": "/video/SONE-205.mp4",
            "number": "SONE-205",
            "mode": "db_to_sidecar",
        })

        assert "db_to_sidecar" in str(mock_fn.call_args)

    def test_mode_refresh_full_passed(self, client, mocker):
        """mode=refresh_full 正確傳入"""
        mock_fn = mocker.patch(
            "web.routers.scraper.enrich_single",
            return_value=_ok_result(source_used="javbus"),
        )

        client.post("/api/enrich-single", json={
            "file_path": "/video/SONE-205.mp4",
            "number": "SONE-205",
            "mode": "refresh_full",
        })

        assert "refresh_full" in str(mock_fn.call_args)

    def test_write_flags_passed(self, client, mocker):
        """write_nfo/write_cover/write_extrafanart/overwrite_existing 正確傳入"""
        mock_fn = mocker.patch(
            "web.routers.scraper.enrich_single",
            return_value=_ok_result(),
        )

        client.post("/api/enrich-single", json={
            "file_path": "/video/SONE-205.mp4",
            "number": "SONE-205",
            "write_nfo": False,
            "write_cover": False,
            "write_extrafanart": True,
            "overwrite_existing": True,
        })

        call_kwargs = mock_fn.call_args.kwargs
        assert call_kwargs["write_nfo"] is False
        assert call_kwargs["write_cover"] is False
        assert call_kwargs["write_extrafanart"] is True
        assert call_kwargs["overwrite_existing"] is True

    def test_error_from_enricher_propagated(self, client, mocker):
        """enricher 回傳 error → 端點也回傳 success=False"""
        mocker.patch(
            "web.routers.scraper.enrich_single",
            return_value=_err_result("找不到 SONE-999 的資料"),
        )

        response = client.post("/api/enrich-single", json={
            "file_path": "/video/SONE-999.mp4",
            "number": "SONE-999",
        })

        data = response.json()
        assert data["success"] is False
        assert "SONE-999" in data["error"]

    def test_unexpected_exception_returns_error(self, client, mocker):
        """enrich_single 拋出例外 → 端點回傳 success=False，且不洩漏原始 exception 訊息"""
        mocker.patch(
            "web.routers.scraper.enrich_single",
            side_effect=RuntimeError("kaboom"),
        )

        response = client.post("/api/enrich-single", json={
            "file_path": "/video/SONE-205.mp4",
            "number": "SONE-205",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "kaboom" not in data.get("error", "")

    def test_default_mode_is_fill_missing(self, client, mocker):
        """未指定 mode 時預設為 fill_missing"""
        mock_fn = mocker.patch(
            "web.routers.scraper.enrich_single",
            return_value=_ok_result(),
        )

        client.post("/api/enrich-single", json={
            "file_path": "/video/SONE-205.mp4",
            "number": "SONE-205",
        })

        assert "fill_missing" in str(mock_fn.call_args)

    def test_extrafanart_written_in_response(self, client, mocker):
        """回應中含 extrafanart_written 欄位"""
        mocker.patch(
            "web.routers.scraper.enrich_single",
            return_value=_ok_result(extrafanart_written=3),
        )

        response = client.post("/api/enrich-single", json={
            "file_path": "/video/SONE-205.mp4",
            "number": "SONE-205",
        })

        data = response.json()
        assert data.get("extrafanart_written") == 3

    def test_fields_filled_in_response(self, client, mocker):
        """回應中含 fields_filled 欄位"""
        mocker.patch(
            "web.routers.scraper.enrich_single",
            return_value=_ok_result(fields_filled=["director", "series"]),
        )

        response = client.post("/api/enrich-single", json={
            "file_path": "/video/SONE-205.mp4",
            "number": "SONE-205",
        })

        data = response.json()
        assert "director" in data.get("fields_filled", [])

    def test_source_used_in_response(self, client, mocker):
        """回應中含 source_used 欄位"""
        mocker.patch(
            "web.routers.scraper.enrich_single",
            return_value=_ok_result(source_used="javbus"),
        )

        response = client.post("/api/enrich-single", json={
            "file_path": "/video/SONE-205.mp4",
            "number": "SONE-205",
        })

        data = response.json()
        assert data.get("source_used") == "javbus"


# ── F4: enrich endpoint 從 config["search"] 取 proxy_url / primary_source ─────

class TestEnrichEndpointReadsSearchConfig:
    def test_proxy_url_taken_from_search_config(self, client, mocker):
        """F4: proxy_url 應從 config['search'] 取，不從 config['scraper'] 取"""
        captured_calls = []

        def fake_enrich(**kwargs):
            captured_calls.append(kwargs)
            return _ok_result()

        mocker.patch("web.routers.scraper.enrich_single", side_effect=fake_enrich)
        mocker.patch("web.routers.scraper.load_config", return_value={
            "search": {
                "proxy_url": "http://proxy.test:8888",
                "primary_source": "javdb",
            },
            "scraper": {
                # 舊的錯誤區段（不應從這裡讀）
                "proxy_url": "http://wrong.proxy:9999",
                "primary_source": "wrong_source",
            },
        })

        client.post("/api/enrich-single", json={
            "file_path": "/video/SONE-205.mp4",
            "number": "SONE-205",
        })

        assert captured_calls, "enrich_single 應被呼叫"
        call_kwargs = captured_calls[0]
        assert call_kwargs.get("proxy_url") == "http://proxy.test:8888", (
            f"proxy_url 應從 config['search'] 取得，實際: {call_kwargs.get('proxy_url')}"
        )
        assert call_kwargs.get("primary_source") == "javdb", (
            f"primary_source 應從 config['search'] 取得，實際: {call_kwargs.get('primary_source')}"
        )
