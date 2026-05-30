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


# ── T2: source / javbus_lang 參數傳遞 ────────────────────────────────────────

class TestSourceJavbusLangParams:
    def test_source_param_passed_to_enrich_single(self, client, mocker):
        """T2: source='dmm' 正確傳入 enrich_single"""
        mock_fn = mocker.patch(
            "web.routers.scraper.enrich_single",
            return_value=_ok_result(source_used="dmm"),
        )
        client.post("/api/enrich-single", json={
            "file_path": "/video/SONE-205.mp4",
            "number": "SONE-205",
            "source": "dmm",
        })
        call_kwargs = mock_fn.call_args.kwargs
        assert call_kwargs.get("source") == "dmm"

    def test_javbus_lang_param_passed_to_enrich_single(self, client, mocker):
        """T2: javbus_lang='ja' 正確傳入 enrich_single"""
        mock_fn = mocker.patch(
            "web.routers.scraper.enrich_single",
            return_value=_ok_result(),
        )
        client.post("/api/enrich-single", json={
            "file_path": "/video/SONE-205.mp4",
            "number": "SONE-205",
            "javbus_lang": "ja",
        })
        call_kwargs = mock_fn.call_args.kwargs
        assert call_kwargs.get("javbus_lang") == "ja"

    def test_source_none_by_default(self, client, mocker):
        """T2: source 未提供時，傳入 enrich_single 的值為 None（向後相容）"""
        mock_fn = mocker.patch(
            "web.routers.scraper.enrich_single",
            return_value=_ok_result(),
        )
        client.post("/api/enrich-single", json={
            "file_path": "/video/SONE-205.mp4",
            "number": "SONE-205",
        })
        call_kwargs = mock_fn.call_args.kwargs
        assert call_kwargs.get("source") is None


# ── P2: mode Literal 驗證 ─────────────────────────────────────────────────────

class TestEnrichSingleModeValidation:
    def test_enrich_single_invalid_mode_returns_422(self, client):
        """mode='bad_mode' → HTTP 422（Pydantic Literal 驗證）"""
        response = client.post("/api/enrich-single", json={
            "file_path": "/video/SONE-205.mp4",
            "number": "SONE-205",
            "mode": "bad_mode",
        })
        assert response.status_code == 422


# ── CD-62-4: refresh_full + overwrite_existing=false 分裂陷阱智慧防呆 ──────────

class TestEnrichRefreshFullOverwriteGuard:
    """智慧版守衛：refresh_full+overwrite=false 時，若這組設定不會寫出任何 sidecar
    （NFO/cover）卻仍 _db_upsert（純分裂）才回 400。一個 sidecar「會寫」= write 旗標開
    且檔案缺。兩者皆不會寫 → 400；任一會寫 → 放行（缺封面 quick-enrich 零回歸）。
    涵蓋 write_nfo/write_cover 皆 false 的純 DB-only 路徑（Codex P1）。
    mock 由 patch resolve_nfo_cover_paths（router 命名空間）+ os.path.exists。"""

    def _patch_paths(self, mocker, nfo_exists, cover_exists):
        """mock resolve_nfo_cover_paths 回固定路徑 + os.path.exists 依旗標回應。"""
        mocker.patch(
            "web.routers.scraper.resolve_nfo_cover_paths",
            return_value=("/video/SONE-205.nfo", "/video/SONE-205.jpg"),
        )
        exists_map = {
            "/video/SONE-205.nfo": nfo_exists,
            "/video/SONE-205.jpg": cover_exists,
        }
        mocker.patch(
            "web.routers.scraper.os.path.exists",
            side_effect=lambda p: exists_map.get(p, False),
        )

    def test_refresh_full_overwrite_false_both_files_exist_returns_400(self, client, mocker):
        """NFO+cover 皆存在 → 400，enrich_single 未被呼叫。"""
        self._patch_paths(mocker, nfo_exists=True, cover_exists=True)
        mock_enrich = mocker.patch(
            "web.routers.scraper.enrich_single", return_value=_ok_result()
        )

        response = client.post("/api/enrich-single", json={
            "file_path": "/video/SONE-205.mp4",
            "number": "SONE-205",
            "mode": "refresh_full",
            "overwrite_existing": False,
        })

        assert response.status_code == 400
        detail = response.json().get("detail", "")
        assert "overwrite" in detail or "分裂" in detail
        mock_enrich.assert_not_called()

    def test_refresh_full_overwrite_false_cover_missing_passes(self, client, mocker):
        """cover 不存在（NFO 存在）→ 200 放行，enrich_single 被呼叫（quick-enrich 零回歸關鍵測試）。"""
        self._patch_paths(mocker, nfo_exists=True, cover_exists=False)
        mock_enrich = mocker.patch(
            "web.routers.scraper.enrich_single", return_value=_ok_result()
        )

        response = client.post("/api/enrich-single", json={
            "file_path": "/video/SONE-205.mp4",
            "number": "SONE-205",
            "mode": "refresh_full",
            "overwrite_existing": False,
        })

        assert response.status_code == 200
        assert response.json()["success"] is True
        mock_enrich.assert_called_once()

    def test_refresh_full_overwrite_false_both_missing_passes(self, client, mocker):
        """NFO+cover 皆不存在（新卡）→ 200 放行。"""
        self._patch_paths(mocker, nfo_exists=False, cover_exists=False)
        mock_enrich = mocker.patch(
            "web.routers.scraper.enrich_single", return_value=_ok_result()
        )

        response = client.post("/api/enrich-single", json={
            "file_path": "/video/SONE-205.mp4",
            "number": "SONE-205",
            "mode": "refresh_full",
            "overwrite_existing": False,
        })

        assert response.status_code == 200
        mock_enrich.assert_called_once()

    def test_refresh_full_overwrite_true_passes(self, client, mocker):
        """overwrite_existing=true → 200，守衛不觸發（不論檔案是否存在）。"""
        self._patch_paths(mocker, nfo_exists=True, cover_exists=True)
        mock_enrich = mocker.patch(
            "web.routers.scraper.enrich_single", return_value=_ok_result()
        )

        response = client.post("/api/enrich-single", json={
            "file_path": "/video/SONE-205.mp4",
            "number": "SONE-205",
            "mode": "refresh_full",
            "overwrite_existing": True,
        })

        assert response.status_code == 200
        mock_enrich.assert_called_once()

    def test_fill_missing_overwrite_false_still_allowed(self, client, mocker):
        """fill_missing+overwrite=false（預設）→ 200，不被守衛誤殺。"""
        self._patch_paths(mocker, nfo_exists=True, cover_exists=True)
        mock_enrich = mocker.patch(
            "web.routers.scraper.enrich_single", return_value=_ok_result()
        )

        response = client.post("/api/enrich-single", json={
            "file_path": "/video/SONE-205.mp4",
            "number": "SONE-205",
            "mode": "fill_missing",
            "overwrite_existing": False,
        })

        assert response.status_code == 200
        mock_enrich.assert_called_once()

    def test_refresh_full_overwrite_false_write_flags_off_returns_400(self, client, mocker):
        """write_nfo=false + write_cover=false，檔案皆缺 → 仍 400（零寫檔純 DB-only 分裂），
        enrich_single 未被呼叫（Codex P1：存在性 AND 檢查補上 write 旗標）。"""
        self._patch_paths(mocker, nfo_exists=False, cover_exists=False)
        mock_enrich = mocker.patch(
            "web.routers.scraper.enrich_single", return_value=_ok_result()
        )

        response = client.post("/api/enrich-single", json={
            "file_path": "/video/SONE-205.mp4",
            "number": "SONE-205",
            "mode": "refresh_full",
            "overwrite_existing": False,
            "write_nfo": False,
            "write_cover": False,
        })

        assert response.status_code == 400
        detail = response.json().get("detail", "")
        assert "overwrite" in detail or "分裂" in detail
        mock_enrich.assert_not_called()

    def test_refresh_full_overwrite_false_one_flag_off_one_will_write_passes(self, client, mocker):
        """write_cover=false 但 write_nfo=true 且 NFO 缺 → will_write_nfo=true → 200 放行。"""
        self._patch_paths(mocker, nfo_exists=False, cover_exists=True)
        mock_enrich = mocker.patch(
            "web.routers.scraper.enrich_single", return_value=_ok_result()
        )

        response = client.post("/api/enrich-single", json={
            "file_path": "/video/SONE-205.mp4",
            "number": "SONE-205",
            "mode": "refresh_full",
            "overwrite_existing": False,
            "write_nfo": True,
            "write_cover": False,
        })

        assert response.status_code == 200
        mock_enrich.assert_called_once()

    def test_refresh_full_overwrite_false_extrafanart_only_returns_400(self, client, mocker):
        """write_nfo=false + write_cover=false + write_extrafanart=true，NFO/cover 皆存在
        → 守衛應擋回 400，enrich_single 未被呼叫。

        extrafanart intent alone 不計入「保證會寫 sidecar」，因為 _write_extrafanart 無 overwrite gate
        且只在 scraper 回 sample_images 才寫；若 scraper 無 samples → 零磁碟寫出但 _db_upsert 照跑
        = DB/磁碟分裂（守衛本要防的）。
        補劇照請改用 /api/scraper/fetch-samples（Codex PR#47 round-2 P2-A revert）。
        """
        self._patch_paths(mocker, nfo_exists=True, cover_exists=True)
        mock_enrich = mocker.patch(
            "web.routers.scraper.enrich_single", return_value=_ok_result(extrafanart_written=3)
        )

        response = client.post("/api/enrich-single", json={
            "file_path": "/video/SONE-205.mp4",
            "number": "SONE-205",
            "mode": "refresh_full",
            "overwrite_existing": False,
            "write_nfo": False,
            "write_cover": False,
            "write_extrafanart": True,
        })

        assert response.status_code == 400, (
            f"extrafanart-only refresh_full 應被守衛擋 400（分裂洞），實際 status={response.status_code}"
        )
        detail = response.json().get("detail", "")
        assert "overwrite" in detail or "分裂" in detail or "fetch-samples" in detail, (
            f"400 detail 應說明分裂風險並指向 fetch-samples，實際: {detail!r}"
        )
        mock_enrich.assert_not_called()
