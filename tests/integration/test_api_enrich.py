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


# ── TASK-90c-T1: enrich-single 唯讀來源 guard ────────────────────────────────
#
# guard 抽成模組級 helper `_readonly_source_error(file_path)`，插在 enrich-single
# 的 `config = load_config()` 後、refresh_full 預檢（resolve_nfo_cover_paths /
# os.path.exists）之前。唯讀 → success:False + 唯讀 error，下游
# resolve_nfo_cover_paths / enrich_single 皆 assert_not_called。
# 鏡像 scrape_single guard 既有 case 1/3/4/7（load_config patch 呼叫處 binding，
# iter_gallery_sources 用 real）。


def _readonly_gallery_config(path, path_mappings=None, readonly=True):
    return {
        "gallery": {
            "directories": [{"path": path, "readonly": readonly}],
            "path_mappings": path_mappings or {},
        },
        "search": {},
        "scraper": {},
    }


class TestEnrichSingleReadonlyGuard:
    """唯讀來源片透過 enrich-single 無法觸發寫檔（correctness 地板）。"""

    # case 1: 唯讀來源 → 擋（refresh_full 讓 resolve_nfo_cover_paths 有意義）
    def test_readonly_blocks_enrich(self, client, mocker):
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=_readonly_gallery_config("/tmp/ro_src"),
        )
        mock_resolve = mocker.patch("web.routers.scraper.resolve_nfo_cover_paths")
        mock_enrich = mocker.patch("web.routers.scraper.enrich_single")

        response = client.post("/api/enrich-single", json={
            "file_path": "/tmp/ro_src/ABC-001.mp4",
            "number": "ABC-001",
            "mode": "refresh_full",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "唯讀" in data["error"]
        # guard 早於 refresh_full 預檢與 enrich_single
        mock_resolve.assert_not_called()
        mock_enrich.assert_not_called()

    # case 3: UNC 唯讀來源 → guard 不拋 ValueError（Codex P2）
    def test_readonly_unc_no_valueerror(self, client, mocker):
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=_readonly_gallery_config(r"\\server\share"),
        )
        mock_resolve = mocker.patch("web.routers.scraper.resolve_nfo_cover_paths")
        mock_enrich = mocker.patch("web.routers.scraper.enrich_single")

        response = client.post("/api/enrich-single", json={
            "file_path": r"\\server\share\ABC-001.mp4",
            "number": "ABC-001",
            "mode": "refresh_full",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "唯讀" in data["error"]
        mock_resolve.assert_not_called()
        mock_enrich.assert_not_called()

    # case 7: canonical file:/// URI 輸入（enrich 主要真實輸入形態）→ 仍命中
    def test_readonly_file_uri_input_blocks(self, client, mocker):
        from core.path_utils import to_file_uri
        file_uri = to_file_uri("C:/ro_src/ABC-001.mp4", {})
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=_readonly_gallery_config("C:/ro_src"),
        )
        mock_resolve = mocker.patch("web.routers.scraper.resolve_nfo_cover_paths")
        mock_enrich = mocker.patch("web.routers.scraper.enrich_single")

        response = client.post("/api/enrich-single", json={
            "file_path": file_uri,
            "number": "ABC-001",
            "mode": "refresh_full",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "唯讀" in data["error"]
        mock_resolve.assert_not_called()
        mock_enrich.assert_not_called()

    # case 4: 非唯讀來源零回歸 → 走既有路徑，enrich_single 照常被呼叫
    def test_non_readonly_passes_through(self, client, mocker):
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=_readonly_gallery_config("/tmp/rw_src", readonly=False),
        )
        mock_enrich = mocker.patch(
            "web.routers.scraper.enrich_single", return_value=_ok_result()
        )

        response = client.post("/api/enrich-single", json={
            "file_path": "/tmp/rw_src/ABC-001.mp4",
            "number": "ABC-001",
            "mode": "fill_missing",
        })

        assert response.status_code == 200
        assert response.json()["success"] is True
        mock_enrich.assert_called_once()


# ── TASK-90c-T1: fetch-samples 唯讀來源 guard（此端點新增專屬測試組）─────────────
#
# guard 插在 fetch-samples 函式開頭（config = load_config() 後、DB/uri work 前）。
# 唯讀 → success:False + 唯讀，fetch_samples_only assert_not_called。


class TestFetchSamplesReadonlyGuard:
    def _ok_samples(self, **kwargs):
        from core.enricher import EnrichResult
        defaults = dict(
            success=True, nfo_written=False, cover_written=False,
            extrafanart_written=3, fields_filled=[], source_used="javbus", error=None,
        )
        defaults.update(kwargs)
        return EnrichResult(**defaults)

    # 唯讀 → 擋，fetch_samples_only 未被呼叫
    def test_readonly_blocks_fetch_samples(self, client, mocker):
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=_readonly_gallery_config("/tmp/ro_src"),
        )
        mock_repo = mocker.patch("web.routers.scraper.VideoRepository")
        mock_fetch = mocker.patch("web.routers.scraper.fetch_samples_only")

        response = client.post("/api/scraper/fetch-samples", json={
            "file_path": "/tmp/ro_src/ABC-001.mp4",
            "number": "ABC-001",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "唯讀" in data["error"]
        mock_fetch.assert_not_called()
        # guard 早於 DB 查詢
        mock_repo.return_value.count_videos_in_folder.assert_not_called()

    # UNC 唯讀 → guard 不拋 ValueError
    def test_readonly_unc_no_valueerror(self, client, mocker):
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=_readonly_gallery_config(r"\\server\share"),
        )
        mocker.patch("web.routers.scraper.VideoRepository")
        mock_fetch = mocker.patch("web.routers.scraper.fetch_samples_only")

        response = client.post("/api/scraper/fetch-samples", json={
            "file_path": r"\\server\share\ABC-001.mp4",
            "number": "ABC-001",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "唯讀" in data["error"]
        mock_fetch.assert_not_called()

    # canonical file:/// 輸入 → 仍命中
    def test_readonly_file_uri_input_blocks(self, client, mocker):
        from core.path_utils import to_file_uri
        file_uri = to_file_uri("C:/ro_src/ABC-001.mp4", {})
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=_readonly_gallery_config("C:/ro_src"),
        )
        mocker.patch("web.routers.scraper.VideoRepository")
        mock_fetch = mocker.patch("web.routers.scraper.fetch_samples_only")

        response = client.post("/api/scraper/fetch-samples", json={
            "file_path": file_uri,
            "number": "ABC-001",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "唯讀" in data["error"]
        mock_fetch.assert_not_called()

    # 非唯讀零回歸 → 走既有路徑，fetch_samples_only 被呼叫
    def test_non_readonly_passes_through(self, client, mocker):
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=_readonly_gallery_config("/tmp/rw_src", readonly=False),
        )
        mock_repo = mocker.patch("web.routers.scraper.VideoRepository")
        mock_repo.return_value.count_videos_in_folder.return_value = 1
        mock_fetch = mocker.patch(
            "web.routers.scraper.fetch_samples_only", return_value=self._ok_samples()
        )

        response = client.post("/api/scraper/fetch-samples", json={
            "file_path": "/tmp/rw_src/ABC-001.mp4",
            "number": "ABC-001",
        })

        assert response.status_code == 200
        assert response.json()["success"] is True
        mock_fetch.assert_called_once()


# ── F4: enrich endpoint 從 config["search"] 取 proxy_url ─────

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
            },
            "scraper": {
                # 舊的錯誤區段（不應從這裡讀）
                "proxy_url": "http://wrong.proxy:9999",
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

    def _patch_paths_jellyfin(self, mocker, nfo_exists, cover_exists, poster_exists, fanart_exists):
        """jellyfin モード用：mock resolve_nfo_cover_paths + load_config(jellyfin) +
        uri_to_fs_path + os.path.exists（NFO/cover/poster/fanart の 4 経路すべて）。"""
        mocker.patch(
            "web.routers.scraper.resolve_nfo_cover_paths",
            return_value=("/video/SONE-205.nfo", "/video/SONE-205.jpg"),
        )
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value={"scraper": {"external_manager": "jellyfin"}, "search": {}},
        )
        mocker.patch(
            "web.routers.scraper.uri_to_fs_path",
            return_value="/video/SONE-205.mp4",
        )
        exists_map = {
            "/video/SONE-205.nfo": nfo_exists,
            "/video/SONE-205.jpg": cover_exists,
            "/video/SONE-205-poster.jpg": poster_exists,
            "/video/SONE-205-fanart.jpg": fanart_exists,
        }
        mocker.patch(
            "web.routers.scraper.os.path.exists",
            side_effect=lambda p: exists_map.get(p, False),
        )

    def test_refresh_full_overwrite_false_external_images_missing_passes(self, client, mocker):
        """72d-P2A：jellyfin mode + NFO+cover 齊 + stem-poster/fanart 缺 → 200 放行
        （守衛不應因只檢查 will_write_nfo/will_write_cover 就回 400）。"""
        self._patch_paths_jellyfin(
            mocker,
            nfo_exists=True, cover_exists=True,
            poster_exists=False, fanart_exists=False,
        )
        mock_enrich = mocker.patch(
            "web.routers.scraper.enrich_single", return_value=_ok_result()
        )

        response = client.post("/api/enrich-single", json={
            "file_path": "file:///video/SONE-205.mp4",
            "number": "SONE-205",
            "mode": "refresh_full",
            "overwrite_existing": False,
        })

        assert response.status_code == 200, (
            f"jellyfin mode + external images missing 應 200 放行，實際 {response.status_code}: {response.json()}"
        )
        mock_enrich.assert_called_once()

    def test_refresh_full_overwrite_false_external_images_all_exist_returns_400(self, client, mocker):
        """72d-P2A：jellyfin mode + NFO+cover+poster+fanart 全齊 → 400（無任何寫出機會）。"""
        self._patch_paths_jellyfin(
            mocker,
            nfo_exists=True, cover_exists=True,
            poster_exists=True, fanart_exists=True,
        )
        mock_enrich = mocker.patch(
            "web.routers.scraper.enrich_single", return_value=_ok_result()
        )

        response = client.post("/api/enrich-single", json={
            "file_path": "file:///video/SONE-205.mp4",
            "number": "SONE-205",
            "mode": "refresh_full",
            "overwrite_existing": False,
        })

        assert response.status_code == 400, (
            f"全齊時應 400，實際 {response.status_code}: {response.json()}"
        )
        detail = response.json().get("detail", "")
        assert "overwrite" in detail or "分裂" in detail
        mock_enrich.assert_not_called()


class TestEnrichSingleThumbnailInvalidation:
    """feature/71 T8 邊界3/4/6：enrich/rescrape 成功 → invalidate 用 canonical key；失敗不呼叫。

    PR #60 Codex P2 回歸：生產的 file_path 已是 DB 的 file:/// URI（前端送 v.path）。
    縮圖 canonical key = 該 URI 原字串 hash（generate/serve/prewarm 同源）。端點須用冪等
    coerce_to_file_uri（已是 URI 原樣回），**不可**再套 to_file_uri 造成 file:///file:///
    double-encode 砍錯 hash → 舊縮圖殘留。舊測餵裸 FS path 並斷言 double-encode 後的 mapped
    URI，是把 bug 行為當合約鎖死，已整套重寫。"""

    # 生產真實輸入：DB v.path（前端 currentLightboxVideo.path / missing-check / rescrape 皆此）
    _VIDEO_URI = "file:///NAS/share/v.mp4"

    def _patch_config(self, mocker):
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value={"gallery": {}, "search": {}},
        )

    def test_success_invalidates_with_canonical_uri(self, client, mocker):
        """邊界3：enrich 成功 → invalidate 被以 canonical key（= 輸入 URI 原值）呼叫，
        非 double-encoded。與縮圖 generate 的 key 同源（thumb_file_for(uri) 同 hash）。"""
        import core.thumbnail_cache as tc
        self._patch_config(mocker)
        mocker.patch("web.routers.scraper.enrich_single", return_value=_ok_result())
        inval_spy = mocker.patch("web.routers.scraper.thumbnail_cache.invalidate")

        response = client.post("/api/enrich-single", json={
            "file_path": self._VIDEO_URI,
            "number": "SONE-205",
        })

        assert response.status_code == 200
        # canonical：invalidate 用輸入 URI 原值（前端送的 DB v.path）
        inval_spy.assert_called_once_with(self._VIDEO_URI)
        invalidated_key = inval_spy.call_args[0][0]
        # 防 double-encode 回歸（PR #60 Codex P2）
        assert "file:///file:///" not in invalidated_key, \
            f"invalidate key double-encoded: {invalidated_key!r}"
        # 與縮圖生成端 canonical key 同 hash（invalidate 砍到的正是 generate 寫的那張）
        assert tc.thumb_file_for(invalidated_key) == tc.thumb_file_for(self._VIDEO_URI)

    def test_failure_does_not_invalidate(self, client, mocker):
        """邊界4：enrich 回 success=False → invalidate 不被呼叫（封面未換）。"""
        self._patch_config(mocker)
        mocker.patch(
            "web.routers.scraper.enrich_single",
            return_value=_err_result("找不到番號資料"),
        )
        inval_spy = mocker.patch("web.routers.scraper.thumbnail_cache.invalidate")

        response = client.post("/api/enrich-single", json={
            "file_path": self._VIDEO_URI,
            "number": "SONE-205",
        })

        assert response.status_code == 200
        inval_spy.assert_not_called()

    def test_exception_does_not_invalidate(self, client, mocker):
        """enrich_single 拋例外 → 端點吞成 success=False，invalidate 不被呼叫。"""
        self._patch_config(mocker)
        mocker.patch(
            "web.routers.scraper.enrich_single",
            side_effect=RuntimeError("boom"),
        )
        inval_spy = mocker.patch("web.routers.scraper.thumbnail_cache.invalidate")

        response = client.post("/api/enrich-single", json={
            "file_path": self._VIDEO_URI,
            "number": "SONE-205",
        })

        assert response.status_code == 200
        assert response.json()["success"] is False
        inval_spy.assert_not_called()

    def test_refresh_full_success_invalidates(self, client, mocker):
        """邊界6：rescrape（refresh_full）成功 → invalidate 用 canonical key（與 #3 同掛鉤點，不漏）。"""
        self._patch_config(mocker)
        # refresh_full + overwrite=True 繞過分裂守衛
        mocker.patch("web.routers.scraper.enrich_single", return_value=_ok_result())
        inval_spy = mocker.patch("web.routers.scraper.thumbnail_cache.invalidate")

        response = client.post("/api/enrich-single", json={
            "file_path": self._VIDEO_URI,
            "number": "SONE-205",
            "mode": "refresh_full",
            "overwrite_existing": True,
        })

        assert response.status_code == 200
        inval_spy.assert_called_once_with(self._VIDEO_URI)
        assert "file:///file:///" not in inval_spy.call_args[0][0]


# ── 72b-T6：endpoint 穿線 external_manager（方案 B）─────────────────────────

class TestEnrichEndpointExternalManagerThreading:
    """enrich_single_endpoint 從 config['scraper']['external_manager'] 取值穿線進 enrich_single。"""

    def test_external_manager_from_config_passed_to_enrich_single(self, client, mocker):
        """F4-T6：external_manager='jellyfin' 從 config 取出並傳入 enrich_single。"""
        captured_calls = []

        def fake_enrich(**kwargs):
            captured_calls.append(kwargs)
            return _ok_result()

        mocker.patch("web.routers.scraper.enrich_single", side_effect=fake_enrich)
        mocker.patch("web.routers.scraper.load_config", return_value={
            "search": {"proxy_url": ""},
            "scraper": {"external_manager": "jellyfin"},
        })

        client.post("/api/enrich-single", json={
            "file_path": "/video/SONE-205.mp4",
            "number": "SONE-205",
        })

        assert captured_calls, "enrich_single 應被呼叫"
        assert captured_calls[0].get("external_manager") == "jellyfin", (
            f"external_manager 應從 config['scraper'] 取，實際: {captured_calls[0].get('external_manager')}"
        )

    def test_emby_manager_from_config_passed_to_enrich_single(self, client, mocker):
        """F4-T6：external_manager='emby' 從 config 取出並傳入 enrich_single（等價 jellyfin）。"""
        captured_calls = []

        def fake_enrich(**kwargs):
            captured_calls.append(kwargs)
            return _ok_result()

        mocker.patch("web.routers.scraper.enrich_single", side_effect=fake_enrich)
        mocker.patch("web.routers.scraper.load_config", return_value={
            "search": {"proxy_url": ""},
            "scraper": {"external_manager": "emby"},
        })

        client.post("/api/enrich-single", json={
            "file_path": "/video/SONE-205.mp4",
            "number": "SONE-205",
        })

        assert captured_calls, "enrich_single 應被呼叫"
        assert captured_calls[0].get("external_manager") == "emby", (
            f"external_manager 應從 config['scraper'] 取，實際: {captured_calls[0].get('external_manager')}"
        )

    def test_external_manager_defaults_to_off_when_missing(self, client, mocker):
        """config 無 scraper.external_manager → 穿線 'off'（byte-identical 邊界）。"""
        captured_calls = []

        def fake_enrich(**kwargs):
            captured_calls.append(kwargs)
            return _ok_result()

        mocker.patch("web.routers.scraper.enrich_single", side_effect=fake_enrich)
        mocker.patch("web.routers.scraper.load_config", return_value={
            "search": {},
            "scraper": {},  # 無 external_manager
        })

        client.post("/api/enrich-single", json={
            "file_path": "/video/SONE-205.mp4",
            "number": "SONE-205",
        })

        assert captured_calls, "enrich_single 應被呼叫"
        assert captured_calls[0].get("external_manager") == "off"

    def test_kodi_external_manager_passed(self, client, mocker):
        """external_manager='kodi' 正確穿線。"""
        captured_calls = []

        def fake_enrich(**kwargs):
            captured_calls.append(kwargs)
            return _ok_result()

        mocker.patch("web.routers.scraper.enrich_single", side_effect=fake_enrich)
        mocker.patch("web.routers.scraper.load_config", return_value={
            "search": {},
            "scraper": {"external_manager": "kodi"},
        })

        client.post("/api/enrich-single", json={
            "file_path": "/video/SONE-205.mp4",
            "number": "SONE-205",
        })

        assert captured_calls[0].get("external_manager") == "kodi"


# ── TASK-91-T3 站台4：enrich_single_endpoint external_manager 分支 WSL+UNC path_mappings ──

_WSL_UNC_MAPPINGS = {"/home/user/nas": "//NAS/share"}
_WSL_UNC_URI = "file://///NAS/share/dir/movie.mp4"
_WSL_UNC_REVERSED_DIR = "/home/user/nas/dir"


class TestEnrichSingleExternalManagerPathMappingReverse:
    """站台4（:322 stem = os.path.splitext(uri_to_fs_path(...))[0]）改用
    uri_to_local_fs_path 後，poster/fanart_path 存在性檢查必須落在反解後的本機目錄
    （mutation-sensitive）；並確認與站台3 cover_path 的 dirname 一致（邊界5）。"""

    def _patch_common(self, mocker):
        mocker.patch(
            "web.routers.scraper.resolve_nfo_cover_paths",
            return_value=(
                f"{_WSL_UNC_REVERSED_DIR}/movie.nfo",
                f"{_WSL_UNC_REVERSED_DIR}/movie.jpg",
            ),
        )
        mocker.patch("web.routers.scraper.load_config", return_value={
            "search": {},
            "scraper": {"external_manager": "jellyfin"},
            "gallery": {"path_mappings": _WSL_UNC_MAPPINGS},
        })
        mocker.patch("web.routers.scraper.enrich_single", return_value=_ok_result())

    def test_wsl_unc_mapping_reverses_stem_for_poster_fanart(self, client, mocker, monkeypatch):
        from core import path_utils
        monkeypatch.setattr(path_utils, "CURRENT_ENV", "wsl")
        self._patch_common(mocker)

        captured_exists = []

        def fake_exists(p):
            captured_exists.append(p)
            return True

        mocker.patch("web.routers.scraper.os.path.exists", side_effect=fake_exists)

        client.post("/api/enrich-single", json={
            "file_path": _WSL_UNC_URI,
            "number": "SONE-205",
            "mode": "refresh_full",
            "overwrite_existing": False,
        })

        poster_calls = [p for p in captured_exists if p.endswith("-poster.jpg")]
        fanart_calls = [p for p in captured_exists if p.endswith("-fanart.jpg")]
        assert poster_calls, "poster_path 存在性應被檢查"
        assert fanart_calls, "fanart_path 存在性應被檢查"
        assert poster_calls[0] == f"{_WSL_UNC_REVERSED_DIR}/movie-poster.jpg", (
            f"poster_path 應反解為本機路徑，實際: {poster_calls[0]!r}"
        )
        assert fanart_calls[0] == f"{_WSL_UNC_REVERSED_DIR}/movie-fanart.jpg", (
            f"fanart_path 應反解為本機路徑，實際: {fanart_calls[0]!r}"
        )

    def test_stem_dirname_matches_resolve_nfo_cover_paths_dirname(self, client, mocker, monkeypatch):
        """邊界5：cover_path（站台3）與 poster/fanart_path（站台4）dirname 須一致，
        否則 will_write_external 判斷會因命名空間不一致誤判。"""
        import os as _os
        from core import path_utils
        monkeypatch.setattr(path_utils, "CURRENT_ENV", "wsl")
        self._patch_common(mocker)

        captured_exists = []

        def fake_exists(p):
            captured_exists.append(p)
            return True

        mocker.patch("web.routers.scraper.os.path.exists", side_effect=fake_exists)

        client.post("/api/enrich-single", json={
            "file_path": _WSL_UNC_URI,
            "number": "SONE-205",
            "mode": "refresh_full",
            "overwrite_existing": False,
        })

        poster_calls = [p for p in captured_exists if p.endswith("-poster.jpg")]
        assert poster_calls
        cover_dirname = _os.path.dirname(f"{_WSL_UNC_REVERSED_DIR}/movie.jpg")
        poster_dirname = _os.path.dirname(poster_calls[0])
        assert cover_dirname == poster_dirname == _WSL_UNC_REVERSED_DIR


# ── TASK-91-T3 站台5：fetch_samples_endpoint outer to_file_uri 補傳 path_mappings ──

class TestFetchSamplesFolderPrefixPathMappingReverse:
    """站台5（:409 folder_uri_prefix = to_file_uri(os.path.dirname(uri_to_fs_path(...))) + '/'）：
    外層 to_file_uri 補傳 path_mappings 後，folder_uri_prefix 須落在映射命名空間，
    DB LIKE 比對才能命中 scanner 以映射端 URI 寫入的 path（mutation-sensitive）。"""

    def _ok_samples(self, **kwargs):
        from core.enricher import EnrichResult
        defaults = dict(
            success=True, nfo_written=False, cover_written=False,
            extrafanart_written=3, fields_filled=[], source_used="javbus", error=None,
        )
        defaults.update(kwargs)
        return EnrichResult(**defaults)

    def test_case2_native_input_prefix_mapped_to_unc_namespace(self, client, mocker, monkeypatch):
        """Case 2（本機原生輸入）：加了 path_mappings 後 prefix 落在映射命名空間
        （沒傳 path_mappings 現況 bug 會落在原生命名空間，永遠比對不到 DB）。"""
        from core import path_utils
        monkeypatch.setattr(path_utils, "CURRENT_ENV", "wsl")
        mocker.patch("web.routers.scraper.load_config", return_value={
            "search": {}, "scraper": {},
            "gallery": {"path_mappings": _WSL_UNC_MAPPINGS},
        })
        mock_repo = mocker.patch("web.routers.scraper.VideoRepository")
        mock_repo.return_value.count_videos_in_folder.return_value = 1
        mocker.patch(
            "web.routers.scraper.fetch_samples_only", return_value=self._ok_samples()
        )

        response = client.post("/api/scraper/fetch-samples", json={
            "file_path": "file:///home/user/nas/dir/movie.mp4",
            "number": "SONE-205",
        })

        assert response.status_code == 200
        mock_repo.return_value.count_videos_in_folder.assert_called_once()
        prefix = mock_repo.return_value.count_videos_in_folder.call_args[0][0]
        assert prefix == "file://///NAS/share/dir/", (
            f"folder_uri_prefix 應落在映射命名空間，實際: {prefix!r}"
        )

    def test_case1_unc_input_prefix_unaffected_by_mappings(self, client, mocker, monkeypatch):
        """Case 1（UNC 輸入）零回歸：加不加 path_mappings 對 folder_uri_prefix 結果相同
        （UNC branch 在 to_file_uri 內提早 return，不受 path_mappings 影響）。"""
        from core import path_utils
        monkeypatch.setattr(path_utils, "CURRENT_ENV", "wsl")

        captured_prefixes = {}
        for label, pm in (("with_mapping", _WSL_UNC_MAPPINGS), ("without_mapping", {})):
            mocker.patch("web.routers.scraper.load_config", return_value={
                "search": {}, "scraper": {},
                "gallery": {"path_mappings": pm},
            })
            mock_repo = mocker.patch("web.routers.scraper.VideoRepository")
            mock_repo.return_value.count_videos_in_folder.return_value = 1
            mocker.patch(
                "web.routers.scraper.fetch_samples_only", return_value=self._ok_samples()
            )

            client.post("/api/scraper/fetch-samples", json={
                "file_path": _WSL_UNC_URI,
                "number": "SONE-205",
            })

            call_args = mock_repo.return_value.count_videos_in_folder.call_args
            captured_prefixes[label] = call_args[0][0]

        assert captured_prefixes["with_mapping"] == captured_prefixes["without_mapping"], (
            f"UNC 輸入下 path_mappings 不應影響結果: {captured_prefixes!r}"
        )
        assert captured_prefixes["with_mapping"] == "file://///NAS/share/dir/"
