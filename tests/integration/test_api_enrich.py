"""
test_api_enrich.py - POST /api/enrich-single 端點整合測試

使用 FastAPI TestClient + mocker，mock core 層函數。
"""

import hashlib
import json
import os
from pathlib import Path

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


# ── TASK-104-T3 (CD-104-5): enrich-single 唯讀來源改道 output_dir ────────────
#
# 唯讀來源片不再一律拒絕：`resolve_owning_output_root` 依 canonical URI 找最內層
# 唯讀來源；找到 → 走 `resolve_ingest_plan` + `_produce_one`（router-level 測試
# patch 這三者 + `VideoRepository`，鏡像既有 `enrich_single`/`resolve_nfo_cover_paths`
# patch 慣例，CD-104-10）；None（非唯讀）→ 落既有 400-guard + `enrich_single` 路徑，
# byte-identical。深度整合測試（真檔案雜湊/DB row/來源零寫入）見
# `TestReadonlyRoutingE2E`（本檔案尾端）。


def _readonly_gallery_config(path, path_mappings=None, readonly=True):
    return {
        "gallery": {
            "directories": [{"path": path, "readonly": readonly}],
            "path_mappings": path_mappings or {},
        },
        "search": {},
        "scraper": {},
    }


def _owning_stub(path="/tmp/ro_src", output_root="/out/ro_src-abcdef", output_uri="file:///out/ro_src-abcdef"):
    """`resolve_owning_output_root` 的成功回傳 stub：(source, output_root, output_uri)。"""
    source = MagicMock()
    source.path = path
    return (source, output_root, output_uri)


class TestEnrichSingleReadonlyGuard:
    """唯讀來源片透過 enrich-single 改道 output_dir（TASK-104-T3，不再拒絕）。"""

    def _mock_routing(self, mocker, meta=None, cover_strategy=('none',), existing="__default__"):
        mock_owning = mocker.patch(
            "web.routers.scraper.resolve_owning_output_root", return_value=_owning_stub()
        )
        mock_plan = mocker.patch(
            "web.routers.scraper.resolve_ingest_plan",
            return_value=(meta if meta is not None else {"number": "ABC-001", "title": "T", "cover": ""}, cover_strategy),
        )
        # _produce_one now returns (movie_dir, assets) — CD-104-5 P2 review
        # (2026-07-21): a bare MagicMock() return_value doesn't unpack as a
        # 2-tuple (`a, b = MagicMock()` raises), so every router-level mock of
        # this collaborator needs an explicit tuple default. cover_fs non-empty
        # by default so tests that don't care land on cover_written=True.
        mock_produce = mocker.patch(
            "web.routers.scraper._produce_one",
            return_value=(Path("/out/ro_src-abcdef/ABC-001"), {"cover_fs": "/out/ro_src-abcdef/ABC-001/ABC-001.jpg", "sample_fs": [], "nfo_mtime": 1.0}),
        )
        mock_repo = mocker.patch("web.routers.scraper.VideoRepository")
        # existing=None (explicit) → 落 os.path.getsize/getmtime fallback（不在此測試組覆蓋，
        # 真檔案雜湊/落盤驗證交給 TestReadonlyRoutingE2E）；預設給一個 non-None stub，避免
        # 對不存在的假路徑觸發真實 stat（FileNotFoundError）。
        mock_repo.return_value.get_by_path.return_value = (
            MagicMock(size_bytes=1000, mtime=1.0) if existing == "__default__" else existing
        )
        return mock_owning, mock_plan, mock_produce, mock_repo

    # case 1（歷史命名保留；TASK-104-T3 改寫為「改道」斷言，不可為保綠而還原新碼，
    # CD-104-10）：唯讀來源片 → 產出成功，絕不落到既有 400-guard（refresh_full 分裂
    # 防呆對唯讀無意義）或舊版 enrich_single。
    def test_readonly_blocks_enrich(self, client, mocker):
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=_readonly_gallery_config("/tmp/ro_src"),
        )
        mock_resolve = mocker.patch("web.routers.scraper.resolve_nfo_cover_paths")
        mock_enrich = mocker.patch("web.routers.scraper.enrich_single")
        mock_owning, mock_plan, mock_produce, mock_repo = self._mock_routing(
            mocker,
            meta={"number": "ABC-001", "title": "T", "cover": "http://x/c.jpg"},
            cover_strategy=("download", "http://x/c.jpg"),
        )

        response = client.post("/api/enrich-single", json={
            "file_path": "/tmp/ro_src/ABC-001.mp4",
            "number": "ABC-001",
            "mode": "refresh_full",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        mock_owning.assert_called_once()
        mock_plan.assert_called_once()
        # readonly_action 未帶 → 預設 'ingest'（安全預設）
        assert mock_plan.call_args.kwargs["action"] == "ingest"
        mock_produce.assert_called_once()
        assert mock_produce.call_args.kwargs["assets_mode"] == "full"
        # 唯讀分支早 return，絕不 fall-through 到既有 400-guard / 舊 enrich_single 路徑
        mock_resolve.assert_not_called()
        mock_enrich.assert_not_called()

    # readonly_action='rescrape' 明確帶 → resolve_ingest_plan 收到 action='rescrape'
    def test_readonly_explicit_rescrape_action_passed_through(self, client, mocker):
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=_readonly_gallery_config("/tmp/ro_src"),
        )
        _, mock_plan, mock_produce, _ = self._mock_routing(
            mocker,
            meta={"number": "ABC-001", "title": "Candidate", "cover": "http://x/new.jpg"},
            cover_strategy=("download", "http://x/new.jpg"),
        )

        response = client.post("/api/enrich-single", json={
            "file_path": "/tmp/ro_src/ABC-001.mp4",
            "number": "ABC-001",
            "readonly_action": "rescrape",
        })

        assert response.json()["success"] is True
        assert mock_plan.call_args.kwargs["action"] == "rescrape"
        mock_produce.assert_called_once()

    # P2 review (2026-07-21): the readonly enrich-single success response was
    # `{"success": True}` only — no nfo_written/cover_written — inconsistent
    # with the non-readonly path's `asdict(EnrichResult)` shape. The showcase
    # lightbox's enrichVideo() success handler (state-lightbox.js) only checks
    # `result.success` today (doesn't consume these fields), but they're added
    # for consistency/forward-compat regardless — harmless either way.
    def test_readonly_enrich_single_success_carries_nfo_and_cover_written(self, client, mocker):
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=_readonly_gallery_config("/tmp/ro_src"),
        )
        _, _, mock_produce, _ = self._mock_routing(
            mocker,
            meta={"number": "ABC-001", "title": "T", "cover": "http://x/c.jpg"},
            cover_strategy=("download", "http://x/c.jpg"),
        )
        mock_produce.return_value = (
            Path("/out/ro_src-abcdef/ABC-001"),
            {"cover_fs": "/out/ro_src-abcdef/ABC-001/ABC-001.jpg", "sample_fs": [], "nfo_mtime": 1.0},
        )

        response = client.post("/api/enrich-single", json={
            "file_path": "/tmp/ro_src/ABC-001.mp4",
            "number": "ABC-001",
        })

        data = response.json()
        assert data["success"] is True
        assert data["nfo_written"] is True
        assert data["cover_written"] is True

    def test_readonly_enrich_single_cover_written_false_when_no_cover(self, client, mocker):
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=_readonly_gallery_config("/tmp/ro_src"),
        )
        _, _, mock_produce, _ = self._mock_routing(
            mocker,
            meta={"number": "ABC-001", "title": "T", "cover": ""},
            cover_strategy=("none",),
        )
        mock_produce.return_value = (
            Path("/out/ro_src-abcdef/ABC-001"),
            {"cover_fs": "", "sample_fs": [], "nfo_mtime": 1.0},
        )

        response = client.post("/api/enrich-single", json={
            "file_path": "/tmp/ro_src/ABC-001.mp4",
            "number": "ABC-001",
        })

        data = response.json()
        assert data["success"] is True
        assert data["nfo_written"] is True
        assert data["cover_written"] is False

    # 未設定媒體庫輸出路徑（media-server flavour 空 output_path）→ 結構化錯誤，不寫
    def test_readonly_empty_output_root_returns_error_no_write(self, client, mocker):
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=_readonly_gallery_config("/tmp/ro_src"),
        )
        mocker.patch(
            "web.routers.scraper.resolve_owning_output_root",
            return_value=_owning_stub(output_root="", output_uri=""),
        )
        mock_plan = mocker.patch("web.routers.scraper.resolve_ingest_plan")
        mock_produce = mocker.patch("web.routers.scraper._produce_one")

        response = client.post("/api/enrich-single", json={
            "file_path": "/tmp/ro_src/ABC-001.mp4",
            "number": "ABC-001",
        })

        data = response.json()
        assert data["success"] is False
        assert "輸出路徑" in data["error"]
        mock_plan.assert_not_called()
        mock_produce.assert_not_called()

    # resolve_ingest_plan 找不到可用資料（meta=None）→ 結構化錯誤，不 raise
    def test_readonly_no_meta_returns_error(self, client, mocker):
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=_readonly_gallery_config("/tmp/ro_src"),
        )
        mock_owning, mock_plan, mock_produce, _ = self._mock_routing(
            mocker, meta=None, cover_strategy=("none",),
        )
        mock_plan.return_value = (None, ("none",))

        response = client.post("/api/enrich-single", json={
            "file_path": "/tmp/ro_src/ABC-001.mp4",
            "number": "ABC-001",
        })

        data = response.json()
        assert data["success"] is False
        assert data["error"]
        mock_produce.assert_not_called()

    # FIX P2-A / FIX#4 (P2 parity closeout): a readonly not-found enrich-single
    # attempt must mirror the non-readonly path's bookkeeping — non-readonly
    # core.enricher.py:391/429 marks scrape_attempted_at on not-found; bulk
    # readonly_producer.py:1559-1561 does insert_if_ignore THEN
    # update_scrape_attempted_at (stub row created first — update_scrape_
    # attempted_at is a bare UPDATE...WHERE path=? that silently no-ops on a
    # missing row). Also: reason must be 'not_found' (matches batch sibling
    # and core.enricher.py:393/431), not the generic 'error'.
    def test_readonly_no_meta_marks_scrape_attempted_and_reason_not_found(self, client, mocker):
        from core.path_utils import coerce_to_file_uri

        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=_readonly_gallery_config("/tmp/ro_src"),
        )
        mock_owning, mock_plan, mock_produce, mock_repo = self._mock_routing(
            mocker, meta=None, cover_strategy=("none",),
        )
        mock_plan.return_value = (None, ("none",))

        response = client.post("/api/enrich-single", json={
            "file_path": "/tmp/ro_src/ABC-001.mp4",
            "number": "ABC-001",
        })

        data = response.json()
        assert data["success"] is False
        assert data["reason"] == "not_found"
        mock_produce.assert_not_called()

        repo_instance = mock_repo.return_value
        repo_instance.insert_if_ignore.assert_called_once()
        repo_instance.update_scrape_attempted_at.assert_called_once()

        # Stub-row-before-update ordering: insert_if_ignore MUST happen before
        # update_scrape_attempted_at, else a first-touch file (no existing DB
        # row) gets no bookkeeping at all (update silently no-ops on a
        # missing row).
        call_names = [c[0] for c in repo_instance.method_calls]
        assert call_names.index("insert_if_ignore") < call_names.index("update_scrape_attempted_at")

        stub_video = repo_instance.insert_if_ignore.call_args.args[0]
        canonical = coerce_to_file_uri("/tmp/ro_src/ABC-001.mp4", {})
        assert stub_video.path == canonical
        assert stub_video.number == "ABC-001"
        assert stub_video.title == "ABC-001.mp4"

        attempted_args = repo_instance.update_scrape_attempted_at.call_args.args
        assert attempted_args[0] == canonical
        assert attempted_args[1] > 0

    # case 4: 非唯讀來源零回歸 → 走既有路徑，enrich_single 照常被呼叫（byte-identical）
    def test_non_readonly_passes_through(self, client, mocker):
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=_readonly_gallery_config("/tmp/rw_src", readonly=False),
        )
        mock_enrich = mocker.patch(
            "web.routers.scraper.enrich_single", return_value=_ok_result()
        )
        mock_produce = mocker.patch("web.routers.scraper._produce_one")

        response = client.post("/api/enrich-single", json={
            "file_path": "/tmp/rw_src/ABC-001.mp4",
            "number": "ABC-001",
            "mode": "fill_missing",
        })

        assert response.status_code == 200
        assert response.json()["success"] is True
        mock_enrich.assert_called_once()
        mock_produce.assert_not_called()

    # 相容鎖：非唯讀 + 完全不帶 readonly_action → 不 422、byte-identical
    def test_non_readonly_without_readonly_action_field_still_succeeds(self, client, mocker):
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
        })

        assert response.status_code == 200
        assert response.json()["success"] is True
        mock_enrich.assert_called_once()

    # 非唯讀 + 明確帶 readonly_action（任一值）→ 仍完全忽略，byte-identical
    @pytest.mark.parametrize("action", ["ingest", "rescrape"])
    def test_non_readonly_ignores_readonly_action(self, client, mocker, action):
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=_readonly_gallery_config("/tmp/rw_src", readonly=False),
        )
        mock_enrich = mocker.patch(
            "web.routers.scraper.enrich_single", return_value=_ok_result()
        )
        mock_owning = mocker.patch(
            "web.routers.scraper.resolve_owning_output_root", return_value=None
        )

        response = client.post("/api/enrich-single", json={
            "file_path": "/tmp/rw_src/ABC-001.mp4",
            "number": "ABC-001",
            "readonly_action": action,
        })

        assert response.json()["success"] is True
        mock_enrich.assert_called_once()
        # resolve_owning_output_root 仍被呼叫判斷（回 None）——分支邏輯本身不吃 action，
        # 但 action 完全不影響非唯讀路徑的下游呼叫（enrich_single 仍是唯一寫入者）。
        mock_owning.assert_called_once()


# ── Codex PR#113 P2#3/P2#4（round 2，owner-confirmed 全面對齊）：readonly
# enrich-single 的 cover-preserve gate + cover-written focal reset/re-submit.
# Router-level mock（同 TestEnrichSingleReadonlyGuard 慣例）——只驗證「傳給
# _produce_one 的 cover_strategy」與「focal 函式是否被呼叫」本身的邏輯正確性；
# 真檔案雜湊/落盤驗證見 TestReadonlyRoutingE2E。


class TestEnrichSingleReadonlyCoverPreserveGate:
    def _mock_routing(
        self, mocker, *, existing_cover_path="",
        plan_cover_strategy=("download", "http://x/new.jpg"),
        produce_cover_fs="/out/ro_src-abcdef/ABC-001/ABC-001.jpg",
        cover_file_exists=True,
    ):
        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=_owning_stub())
        mocker.patch(
            "web.routers.scraper.resolve_ingest_plan",
            return_value=(
                {"number": "ABC-001", "title": "T", "maker": "M", "cover": "http://x/new.jpg"},
                plan_cover_strategy,
            ),
        )
        mock_produce = mocker.patch(
            "web.routers.scraper._produce_one",
            return_value=(
                Path("/out/ro_src-abcdef/ABC-001"),
                {"cover_fs": produce_cover_fs, "sample_fs": [], "nfo_mtime": 1.0},
            ),
        )
        mock_repo = mocker.patch("web.routers.scraper.VideoRepository")
        # cover_path='' (default) → had_cover=False；帶字串 URI → had_cover=True
        # (前提是 os.path.exists 也判存在，見下方 mock).
        mock_repo.return_value.get_by_path.return_value = MagicMock(
            size_bytes=1000, mtime=1.0, cover_path=existing_cover_path,
        )
        # Codex PR#113 P2 round-6 fix：had_cover 現在還要求輸出封面檔實際存在於
        # 磁碟（對齊 core.enricher._write_cover 的 os.path.exists(cover_path)
        # 語意）——預設 True 讓既有測試（模型「DB 有 cover_path 且檔案也還在」
        # 的一般情境）維持原 had_cover=True 行為；cover_file_exists=False 用來
        # 模擬 round-6 回報的 bug 場景（DB row 殘留、輸出檔已被刪除/對應不到）。
        mocker.patch("web.routers.scraper.os.path.exists", return_value=cover_file_exists)
        # feature/105 patch-target migration (CD-105-8): has_servable_cover 的磁碟
        # 複驗隨 compute_has_servable_cover 從 web.routers.scraper 搬進
        # core.enrich_contract；顯式 patch 該命名空間讓「哪個 mock 餵 has_servable_cover」
        # 自我文件化（os.path 為共享 module singleton，機械上與上一行同物件，
        # 兩者一致即可）。cover_file_exists 同時餵 had_cover（scraper）與
        # has_servable_cover（enrich_contract）兩道 gate。
        mocker.patch("core.enrich_contract.os.path.exists", return_value=cover_file_exists)
        # TASK-105-T6: reset+submit 收斂進 schedule_focal_after_cover_write（住
        # core.focal_trigger）；maybe_submit_video_focal 的實際呼叫端隨之從
        # web.routers.scraper 移到 core.focal_trigger（bare name 在該模組 global
        # namespace 內解析），patch target 需對齊使用端（gotchas-backend.md §1）。
        mock_focal = mocker.patch("core.focal_trigger.maybe_submit_video_focal")
        return mock_produce, mock_repo, mock_focal

    def _post(self, client, **overrides):
        body = {
            "file_path": "/tmp/ro_src/ABC-001.mp4",
            "number": "ABC-001",
            "readonly_action": "ingest",
        }
        body.update(overrides)
        return client.post("/api/enrich-single", json=body)

    # ── P2#3: cover-preserve gate ────────────────────────────────────────────

    def test_fill_missing_with_existing_cover_preserves_cover(self, client, mocker):
        """放大鏡-with-cover（fill_missing + overwrite=False + 既有 cover_path）
        → cover_strategy 被覆蓋為 ('none',)，即使 resolve_ingest_plan 本來想下載。
        MUTATION LOCK：拿掉 preserve gate 這條會讓本測試 RED（cover_strategy 會維持
        resolve_ingest_plan 的原值 ('download', ...)）。"""
        mocker.patch("web.routers.scraper.load_config", return_value=_readonly_gallery_config("/tmp/ro_src"))
        mock_produce, _, _ = self._mock_routing(mocker, existing_cover_path="file:///out/old.jpg")

        response = self._post(client, mode="fill_missing", overwrite_existing=False)

        assert response.json()["success"] is True
        assert mock_produce.call_args.kwargs["cover_strategy"] == ("none",)

    def test_fill_missing_without_existing_cover_writes(self, client, mocker):
        """放大鏡-no-cover：既有 row 沒有 cover_path（had_cover=False）→ 不觸發
        preserve，cover_strategy 原樣傳給 _produce_one。"""
        mocker.patch("web.routers.scraper.load_config", return_value=_readonly_gallery_config("/tmp/ro_src"))
        mock_produce, _, _ = self._mock_routing(mocker, existing_cover_path="")

        response = self._post(client, mode="fill_missing", overwrite_existing=False)

        assert response.json()["success"] is True
        assert mock_produce.call_args.kwargs["cover_strategy"] == ("download", "http://x/new.jpg")

    # ── Codex PR#113 P2 round-6（found in 2 readonly branches）：had_cover 必須
    # 連同輸出封面檔是否實際存在於磁碟一起判斷，不能只看 DB 有沒有 cover_path
    # （對齊 core.enricher._write_cover 的 os.path.exists(cover_path) 語意，見上方
    # _write_cover skip 語意註解）────────────────────────────────────────────

    def test_fill_missing_with_cover_path_but_file_missing_on_disk_rebuilds_cover(
        self, client, mocker,
    ):
        """放大鏡-with-cover，但 DB 的 cover_path 對應到的輸出檔已被刪除（或路徑
        對應後在磁碟上不存在）→ had_cover 必須是 False，不得 preserve，
        cover_strategy 原樣傳給 _produce_one（重建封面）。round-6 回報的 bug：
        readonly 分支只看 DB `existing.cover_path` 就當作「已有封面」而跳過重建，
        與非唯讀 core.enricher._write_cover 的 os.path.exists 語意不一致。
        MUTATION LOCK：把 had_cover 改回純 DB 判斷
        （bool(existing and existing.cover_path)）會讓本測試 RED
        （cover_strategy 會變成 ('none',)）。"""
        mocker.patch("web.routers.scraper.load_config", return_value=_readonly_gallery_config("/tmp/ro_src"))
        mock_produce, _, _ = self._mock_routing(
            mocker, existing_cover_path="file:///out/old.jpg", cover_file_exists=False,
        )

        response = self._post(client, mode="fill_missing", overwrite_existing=False)

        assert response.json()["success"] is True
        assert mock_produce.call_args.kwargs["cover_strategy"] == ("download", "http://x/new.jpg")

    def test_fill_missing_with_cover_path_and_file_present_preserves_cover(self, client, mocker):
        """同場景但輸出封面檔仍實際存在於磁碟 → 維持既有 preserve 行為
        （無回歸，鏡射 test_fill_missing_with_existing_cover_preserves_cover）。"""
        mocker.patch("web.routers.scraper.load_config", return_value=_readonly_gallery_config("/tmp/ro_src"))
        mock_produce, _, _ = self._mock_routing(
            mocker, existing_cover_path="file:///out/old.jpg", cover_file_exists=True,
        )

        response = self._post(client, mode="fill_missing", overwrite_existing=False)

        assert response.json()["success"] is True
        assert mock_produce.call_args.kwargs["cover_strategy"] == ("none",)

    # ── feature/105 T2 AC4 delta：移除唯讀 mode=='fill_missing' 顯式閘後，唯讀保留
    # 政策與非唯讀 core.enricher._write_cover 完全 mode-agnostic 對齊。refresh_full
    # + overwrite=false + 既有可服務封面 → 保留（改前 mode 閘 False 會靜默覆蓋）。
    # MUTATION SELF-CHECK：把 mode 閘加回（preserve = (not write_cover) or
    # (request.mode == 'fill_missing' and not overwrite and had_cover)）會讓本測試
    # RED（cover_strategy 變回 ('download', ...)）——已於實作時驗證。─────────────
    def test_refresh_full_no_overwrite_existing_cover_preserves_mode_agnostic(
        self, client, mocker,
    ):
        """AC4：refresh_full + overwrite=false + 既有封面（磁碟檔在）→ preserve
        （('none',)），與 enricher _write_cover 同輸入
        should_preserve_cover(write_cover=True, overwrite=False, cover_exists=True)
        =True 一致。"""
        mocker.patch("web.routers.scraper.load_config", return_value=_readonly_gallery_config("/tmp/ro_src"))
        mock_produce, _, _ = self._mock_routing(
            mocker, existing_cover_path="file:///out/old.jpg", cover_file_exists=True,
        )

        response = self._post(client, mode="refresh_full", overwrite_existing=False)

        assert response.json()["success"] is True
        assert mock_produce.call_args.kwargs["cover_strategy"] == ("none",)

    # ── P2 review round 3 (FIX#1): reason reflects a SERVABLE cover, not just
    # this-call cover_written ────────────────────────────────────────────────

    def test_fill_missing_with_existing_cover_reason_is_hit_despite_cover_written_false(
        self, client, mocker,
    ):
        """同 test_fill_missing_with_existing_cover_preserves_cover 場景（放大鏡-
        with-cover）：cover_strategy 被覆蓋為 ('none',) → cover_written=False，但
        既有封面（existing.cover_path）仍可服務 → reason 必須是 'hit'（不是
        'no_cover'），對齊 core.enricher.enrich_single 的 has_servable_cover 解耦
        語意（enricher.py:589-604）。MUTATION LOCK：把 reason 改回
        `'hit' if cover_written else 'no_cover'` 會讓本測試 RED。"""
        mocker.patch("web.routers.scraper.load_config", return_value=_readonly_gallery_config("/tmp/ro_src"))
        # produce_cover_fs="" — the mocked _produce_one echoes whatever fixture
        # value it's given regardless of cover_strategy (it's a mock, not the
        # real preserve logic), so this must be explicit to model "preserve
        # gate suppressed the write" → assets['cover_fs'] empty → cover_written
        # False (same as test_cover_preserved_skips_focal's setup).
        mock_produce, _, _ = self._mock_routing(
            mocker, existing_cover_path="file:///out/old.jpg", produce_cover_fs="",
        )

        response = self._post(client, mode="fill_missing", overwrite_existing=False)

        data = response.json()
        assert data["success"] is True
        assert mock_produce.call_args.kwargs["cover_strategy"] == ("none",)
        assert data["cover_written"] is False
        assert data["reason"] == "hit"

    # ── feature/105 AC2 (Bug 1 fix): reason must be 'no_cover' when the DB has a
    # residual cover_path but the physical cover file is gone on disk. Before the
    # fix enrich-single only checked the DB row → wrongly reported 'hit' → the
    # frontend built a /api/gallery/thumb URL that 404s (broken fly-in image).
    # MUTATION LOCK: revert enrich-single's has_servable_cover to the DB-only
    # `bool(assets.get('cover_fs')) or bool(existing and existing.cover_path)` and
    # this test goes RED (reason flips back to 'hit'). ────────────────────────
    def test_residual_cover_path_but_file_deleted_reason_is_no_cover(self, client, mocker):
        mocker.patch("web.routers.scraper.load_config", return_value=_readonly_gallery_config("/tmp/ro_src"))
        # DB row still has cover_path, but the output cover file no longer exists on
        # disk (cover_file_exists=False) and this call wrote nothing (produce_cover_fs="").
        mock_produce, _, _ = self._mock_routing(
            mocker, existing_cover_path="file:///out/old.jpg",
            produce_cover_fs="", cover_file_exists=False,
        )

        response = self._post(client, mode="fill_missing", overwrite_existing=False)

        data = response.json()
        assert data["success"] is True
        assert data["cover_written"] is False
        assert data["reason"] == "no_cover"

    def test_gear_refresh_full_overwrite_true_writes_regardless_of_had_cover(self, client, mocker):
        """gear rescrape（refresh_full + overwrite=True，state-rescrape.js:404/408
        的實際送法）→ 即使既有 cover_path 也不 preserve，cover_strategy 原樣傳給
        _produce_one（回歸鎖：不得被 P2#3 誤擋）。"""
        mocker.patch("web.routers.scraper.load_config", return_value=_readonly_gallery_config("/tmp/ro_src"))
        mock_produce, _, _ = self._mock_routing(mocker, existing_cover_path="file:///out/old.jpg")

        response = self._post(
            client, readonly_action="rescrape", mode="refresh_full", overwrite_existing=True,
        )

        assert response.json()["success"] is True
        assert mock_produce.call_args.kwargs["cover_strategy"] == ("download", "http://x/new.jpg")

    def test_write_cover_false_preserves_regardless_of_mode(self, client, mocker):
        """write_cover=false → 不論 mode/overwrite 為何，一律 preserve。用
        refresh_full+overwrite=True（gear 語意）刻意排除 fill_missing 分支才會
        觸發的條件，證明是 `not write_cover` 這條在起作用。"""
        mocker.patch("web.routers.scraper.load_config", return_value=_readonly_gallery_config("/tmp/ro_src"))
        mock_produce, _, _ = self._mock_routing(mocker, existing_cover_path="file:///out/old.jpg")

        response = self._post(
            client, readonly_action="rescrape", mode="refresh_full",
            overwrite_existing=True, write_cover=False,
        )

        assert response.json()["success"] is True
        assert mock_produce.call_args.kwargs["cover_strategy"] == ("none",)

    # ── P2#4: cover-written focal reset + re-submit ──────────────────────────

    def test_cover_written_resets_and_resubmits_focal(self, client, mocker):
        """本次實際寫入新封面（assets['cover_fs'] 非空）→ reset_focal_to_auto +
        maybe_submit_video_focal 都被呼叫，且參數對齊 enricher.py:537-547
        （video_path_uri=canonical DB key、cover_fs_path=assets['cover_fs']、
        cover_path_uri=to_file_uri(assets['cover_fs'], path_mappings)）。
        MUTATION LOCK：拿掉整個 focal 區塊會讓本測試 RED。"""
        from core.path_utils import to_file_uri

        mocker.patch("web.routers.scraper.load_config", return_value=_readonly_gallery_config("/tmp/ro_src"))
        cover_fs = "/out/ro_src-abcdef/ABC-001/ABC-001.jpg"
        mock_produce, mock_repo, mock_focal = self._mock_routing(
            mocker, existing_cover_path="", produce_cover_fs=cover_fs,
        )

        response = self._post(client, mode="refresh_full")

        assert response.json()["success"] is True
        assert response.json()["cover_written"] is True
        canonical = to_file_uri("/tmp/ro_src/ABC-001.mp4", {})
        mock_repo.return_value.reset_focal_to_auto.assert_called_once_with(canonical)
        mock_focal.assert_called_once()
        args, kwargs = mock_focal.call_args
        assert args[0] == "ABC-001"       # number
        assert args[1] == "M"             # maker
        assert args[2] == canonical       # video_path_uri (DB key)
        assert args[3] == cover_fs        # cover_fs_path
        assert kwargs["cover_path_uri"] == to_file_uri(cover_fs, {})

    def test_cover_preserved_skips_focal(self, client, mocker):
        """preserve_cover=True → assets['cover_fs'] 空 → focal 兩函式皆不呼叫，
        既有 manual 焦點原樣保留（cover_written=False 閘門，同 enricher.py:534）。"""
        mocker.patch("web.routers.scraper.load_config", return_value=_readonly_gallery_config("/tmp/ro_src"))
        mock_produce, mock_repo, mock_focal = self._mock_routing(
            mocker, existing_cover_path="file:///out/old.jpg",
            produce_cover_fs="",  # preserved → _produce_one 沒寫新封面
        )

        response = self._post(client, mode="fill_missing", overwrite_existing=False)

        assert response.json()["success"] is True
        assert response.json()["cover_written"] is False
        mock_repo.return_value.reset_focal_to_auto.assert_not_called()
        mock_focal.assert_not_called()


# ── P2 review round 3 (FIX#4): readonly + mode='db_to_sidecar' clean rejection ──
# db_to_sidecar means "write current DB metadata to the SOURCE sidecar NFO, no
# scrape" — for a readonly source the source sidecar cannot be written at all
# (zero-write wall), and the output_dir NFO is auto-managed by the produce flow,
# so this mode is not meaningful for readonly. A documented, defensible by-design
# divergence: reject early with a clean, full-shape EnrichResult instead of
# silently doing a full ingest/rescrape (the readonly branch otherwise ignores
# request.mode entirely).


class TestEnrichSingleReadonlyDbToSidecarRejection:
    def test_db_to_sidecar_readonly_rejected_cleanly(self, client, mocker):
        """MUTATION LOCK：拿掉這條 early-return 會讓 resolve_ingest_plan/_produce_one
        被呼叫（本測試斷言它們不被呼叫），本測試會 RED。"""
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=_readonly_gallery_config("/tmp/ro_src"),
        )
        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=_owning_stub())
        mock_plan = mocker.patch("web.routers.scraper.resolve_ingest_plan")
        mock_produce = mocker.patch("web.routers.scraper._produce_one")

        response = client.post("/api/enrich-single", json={
            "file_path": "/tmp/ro_src/ABC-001.mp4",
            "number": "ABC-001",
            "mode": "db_to_sidecar",
        })

        data = response.json()
        assert data["success"] is False
        assert data["error"]
        assert data["nfo_written"] is False
        assert data["cover_written"] is False
        assert data["extrafanart_written"] == 0
        assert data["fields_filled"] == []
        assert data["source_used"] == ""
        assert data["reason"] == "error"
        assert set(data) >= _ENRICH_RESULT_KEYS
        mock_plan.assert_not_called()
        mock_produce.assert_not_called()


# ── P1 revert + reject (round-3 review 2026-07-21, owner-confirmed): readonly +
# write_nfo=false clean rejection ── Codex PR#113 round-3 threaded a write_nfo
# skip-gate into the readonly produce path (_write_movie_assets/_produce_one) —
# that was a P1 data-loss (a title-changing rescrape with write_nfo=False
# skipped the new NFO write while stale-cleanup still unlinked the OLD one,
# losing the NFO entirely while the DB kept a stale nfo_mtime claiming it
# exists). Readonly produce is HOLISTIC (a library entry always has an NFO),
# so write_nfo=false is rejected here the same way db_to_sidecar is above,
# instead of threading a skip flag down into the write path.


class TestEnrichSingleReadonlyNoNfoRejection:
    def test_write_nfo_false_readonly_rejected_cleanly(self, client, mocker):
        """MUTATION LOCK：拿掉這條 early-return 會讓 resolve_ingest_plan/_produce_one
        被呼叫（本測試斷言它們不被呼叫），本測試會 RED。"""
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=_readonly_gallery_config("/tmp/ro_src"),
        )
        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=_owning_stub())
        mock_plan = mocker.patch("web.routers.scraper.resolve_ingest_plan")
        mock_produce = mocker.patch("web.routers.scraper._produce_one")

        response = client.post("/api/enrich-single", json={
            "file_path": "/tmp/ro_src/ABC-001.mp4",
            "number": "ABC-001",
            "write_nfo": False,
        })

        data = response.json()
        assert data["success"] is False
        assert data["error"]
        assert data["nfo_written"] is False
        assert data["cover_written"] is False
        assert data["extrafanart_written"] == 0
        assert data["fields_filled"] == []
        assert data["source_used"] == ""
        assert data["reason"] == "error"
        assert set(data) >= _ENRICH_RESULT_KEYS
        mock_plan.assert_not_called()
        mock_produce.assert_not_called()


# ── TASK-104-T3 (CD-104-5): fetch-samples 唯讀來源改道 output_dir（samples_only）──


class TestFetchSamplesReadonlyGuard:
    def _ok_samples(self, **kwargs):
        from core.enricher import EnrichResult
        defaults = dict(
            success=True, nfo_written=False, cover_written=False,
            extrafanart_written=3, fields_filled=[], source_used="javbus", error=None,
        )
        defaults.update(kwargs)
        return EnrichResult(**defaults)

    # case 1（歷史命名保留；TASK-104-T3 改寫）：唯讀 → 改道，search_jav 找到劇照
    # → samples_only 落 output_dir，不再拒絕。
    def test_readonly_blocks_fetch_samples(self, client, mocker):
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=_readonly_gallery_config("/tmp/ro_src"),
        )
        mocker.patch(
            "web.routers.scraper.resolve_owning_output_root", return_value=_owning_stub()
        )
        mock_search = mocker.patch(
            "web.routers.scraper.search_jav",
            return_value={"number": "ABC-001", "sample_images": ["http://x/s1.jpg", "http://x/s2.jpg"]},
        )
        mock_repo = mocker.patch("web.routers.scraper.VideoRepository")
        mock_repo.return_value.get_by_path.return_value = MagicMock(size_bytes=1000, mtime=1.0)
        # _produce_one now returns (movie_dir, assets) — both requested URLs
        # actually downloaded here (sample_fs has 2 entries, matching the 2
        # requested), so extrafanart_written == 2 stays the happy-path value.
        # See test_fetch_samples_reports_actual_written_count_not_requested (P2
        # review) for the case where they diverge.
        mock_produce = mocker.patch(
            "web.routers.scraper._produce_one",
            return_value=(
                Path("/out/ro_src-abcdef/ABC-001"),
                {"sample_fs": ["/out/ro_src-abcdef/ABC-001/extrafanart/fanart1.jpg",
                                "/out/ro_src-abcdef/ABC-001/extrafanart/fanart2.jpg"]},
            ),
        )
        mock_fetch = mocker.patch("web.routers.scraper.fetch_samples_only")

        response = client.post("/api/scraper/fetch-samples", json={
            "file_path": "/tmp/ro_src/ABC-001.mp4",
            "number": "ABC-001",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["extrafanart_written"] == 2
        # P2 review round 3 (FIX#2): fetch_samples_only NEVER sets `reason` (stays
        # the EnrichResult dataclass default, None, on every path) — the readonly
        # branch must match field-for-field, not invent 'hit'/'no_cover' values.
        # MUTATION LOCK: reintroducing `reason='hit' if written else 'no_cover'`
        # would make this RED.
        assert data["reason"] is None
        mock_search.assert_called_once()
        mock_produce.assert_called_once()
        assert mock_produce.call_args.kwargs["assets_mode"] == "samples_only"
        assert mock_produce.call_args.kwargs["cover_strategy"] == ("none",)
        # 唯讀分支不用舊版 samples_only helper（改走 resolve_ingest_plan 的姊妹路徑）
        mock_fetch.assert_not_called()

    # P2 review (2026-07-21): INTENDED CONTRACT CHANGE, not a weakening.
    # `data["extrafanart_written"]` previously echoed `len(meta["sample_images"])`
    # (the REQUESTED count) verbatim, regardless of how many of those downloads
    # actually succeeded. Here 3 sample URLs are requested but only 1 file
    # actually lands in `assets['sample_fs']` (the other 2 download attempts
    # failed inside `_write_movie_assets`) — the endpoint must report 1, the
    # ACTUAL written count, not 3.
    def test_fetch_samples_reports_actual_written_count_not_requested(self, client, mocker):
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=_readonly_gallery_config("/tmp/ro_src"),
        )
        mocker.patch(
            "web.routers.scraper.resolve_owning_output_root", return_value=_owning_stub()
        )
        mocker.patch(
            "web.routers.scraper.search_jav",
            return_value={
                "number": "ABC-001",
                "sample_images": ["http://x/s1.jpg", "http://x/s2.jpg", "http://x/s3.jpg"],
            },
        )
        mock_repo = mocker.patch("web.routers.scraper.VideoRepository")
        mock_repo.return_value.get_by_path.return_value = MagicMock(size_bytes=1000, mtime=1.0)
        mocker.patch(
            "web.routers.scraper._produce_one",
            return_value=(
                Path("/out/ro_src-abcdef/ABC-001"),
                {"sample_fs": ["/out/ro_src-abcdef/ABC-001/extrafanart/fanart1.jpg"]},  # only 1 of 3 survived
            ),
        )

        response = client.post("/api/scraper/fetch-samples", json={
            "file_path": "/tmp/ro_src/ABC-001.mp4",
            "number": "ABC-001",
        })

        data = response.json()
        assert data["success"] is True
        assert data["extrafanart_written"] == 1, (
            "must report the ACTUAL written count (assets['sample_fs']), "
            "not the requested count (meta['sample_images'])"
        )

    # P2 review companion case: ALL downloads fail → assets['sample_fs'] == [] →
    # extrafanart_written == 0 (not 3, the requested count). The DB-side "must
    # not clobber existing sample_images to []" half of this same finding is
    # unit-tested directly against `_upsert_db` in
    # tests/unit/test_readonly_producer.py::TestUpsertDbSamplesOnly (router-level
    # here only has a mocked `_produce_one`, so it cannot observe the DB write —
    # this test only pins the endpoint's reported count).
    def test_fetch_samples_zero_downloads_reports_zero_not_requested(self, client, mocker):
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=_readonly_gallery_config("/tmp/ro_src"),
        )
        mocker.patch(
            "web.routers.scraper.resolve_owning_output_root", return_value=_owning_stub()
        )
        mocker.patch(
            "web.routers.scraper.search_jav",
            return_value={
                "number": "ABC-001",
                "sample_images": ["http://x/s1.jpg", "http://x/s2.jpg", "http://x/s3.jpg"],
            },
        )
        mock_repo = mocker.patch("web.routers.scraper.VideoRepository")
        mock_repo.return_value.get_by_path.return_value = MagicMock(size_bytes=1000, mtime=1.0)
        mocker.patch(
            "web.routers.scraper._produce_one",
            return_value=(Path("/out/ro_src-abcdef/ABC-001"), {"sample_fs": []}),  # every download failed
        )

        response = client.post("/api/scraper/fetch-samples", json={
            "file_path": "/tmp/ro_src/ABC-001.mp4",
            "number": "ABC-001",
        })

        data = response.json()
        assert data["success"] is True
        assert data["extrafanart_written"] == 0

    # P2 review round 3 (FIX#3): split what used to be one combined test into
    # the two branches core.enricher.fetch_samples_only itself distinguishes —
    # TOTAL search failure (search_jav → None, enricher.py:715-718) is a real
    # failure (success=False + error), NOT the same as "found metadata but it
    # happens to have no sample_images" (still success=True/extrafanart_written=0,
    # meta.get("sample_images", []) just defaults to []). The old combined test
    # asserted success=True for BOTH cases, silently swallowing total search
    # failures — this is an intentional contract fix, not a regression.
    def test_readonly_search_jav_none_is_a_failure(self, client, mocker):
        """search_jav 完全找不到資料（回 None）→ success=False + error 帶出，對齊
        fetch_samples_only 的 total-not-found 分支（enricher.py:715-718）。
        MUTATION LOCK：把 `if not meta:` 改回 `if not meta or not
        meta.get("sample_images")` 會讓本測試 RED（success 會變回 True）。"""
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=_readonly_gallery_config("/tmp/ro_src"),
        )
        mocker.patch(
            "web.routers.scraper.resolve_owning_output_root", return_value=_owning_stub()
        )
        mocker.patch("web.routers.scraper.search_jav", return_value=None)
        mock_produce = mocker.patch("web.routers.scraper._produce_one")

        response = client.post("/api/scraper/fetch-samples", json={
            "file_path": "/tmp/ro_src/ABC-001.mp4",
            "number": "ABC-001",
        })

        data = response.json()
        assert data["success"] is False
        assert data["error"]
        assert data["extrafanart_written"] == 0
        assert data["reason"] is None
        mock_produce.assert_not_called()

    def test_readonly_meta_found_but_no_sample_images_is_not_an_error(self, client, mocker):
        """search_jav 有找到資料，但該筆沒有 sample_images → 非錯誤，
        extrafanart_written=0，reason 保持 None（fetch_samples_only 從不設
        reason）。"""
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=_readonly_gallery_config("/tmp/ro_src"),
        )
        mocker.patch(
            "web.routers.scraper.resolve_owning_output_root", return_value=_owning_stub()
        )
        mocker.patch(
            "web.routers.scraper.search_jav",
            return_value={"number": "ABC-001", "source": "javbus", "sample_images": []},
        )
        mock_produce = mocker.patch("web.routers.scraper._produce_one")

        response = client.post("/api/scraper/fetch-samples", json={
            "file_path": "/tmp/ro_src/ABC-001.mp4",
            "number": "ABC-001",
        })

        data = response.json()
        assert data["success"] is True
        assert data["extrafanart_written"] == 0
        assert data["reason"] is None
        mock_produce.assert_not_called()

    # 未設定媒體庫輸出路徑 → 結構化錯誤，不寫
    def test_readonly_empty_output_root_returns_error(self, client, mocker):
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=_readonly_gallery_config("/tmp/ro_src"),
        )
        mocker.patch(
            "web.routers.scraper.resolve_owning_output_root",
            return_value=_owning_stub(output_root="", output_uri=""),
        )
        mock_search = mocker.patch("web.routers.scraper.search_jav")

        response = client.post("/api/scraper/fetch-samples", json={
            "file_path": "/tmp/ro_src/ABC-001.mp4",
            "number": "ABC-001",
        })

        data = response.json()
        assert data["success"] is False
        assert "輸出路徑" in data["error"]
        assert data["extrafanart_written"] == 0
        mock_search.assert_not_called()

    # 非唯讀零回歸 → 走既有路徑，fetch_samples_only 被呼叫（byte-identical）
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
        mock_produce = mocker.patch("web.routers.scraper._produce_one")

        response = client.post("/api/scraper/fetch-samples", json={
            "file_path": "/tmp/rw_src/ABC-001.mp4",
            "number": "ABC-001",
        })

        assert response.status_code == 200
        assert response.json()["success"] is True
        mock_fetch.assert_called_once()
        mock_produce.assert_not_called()


# ── Codex PR#113 one-pass alignment (2026-07-21): readonly endpoints now build
# an ACTUAL EnrichResult dataclass and asdict() it, so their response shape is
# structurally guaranteed to carry every field the non-readonly contract does
# (success/nfo_written/cover_written/extrafanart_written/fields_filled/
# source_used/error/reason) — success AND failure paths alike. This closes the
# whole class of "readonly branch forgot field X" findings Codex peeled off one
# at a time across earlier rounds, instead of relying on ad-hoc per-field tests.

_ENRICH_RESULT_KEYS = {
    'success', 'nfo_written', 'cover_written', 'extrafanart_written',
    'fields_filled', 'source_used', 'error', 'reason',
}


class TestReadonlyEnrichResultShapeParity:
    """enrich-single / fetch-samples readonly branches: full EnrichResult shape
    on every return path (success + every failure early-return)."""

    def test_enrich_single_success_has_full_shape(self, client, mocker):
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=_readonly_gallery_config("/tmp/ro_src"),
        )
        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=_owning_stub())
        mocker.patch(
            "web.routers.scraper.resolve_ingest_plan",
            return_value=({"number": "ABC-001", "title": "T", "cover": ""}, ("none",)),
        )
        mocker.patch(
            "web.routers.scraper._produce_one",
            return_value=(Path("/out/ro_src-abcdef/ABC-001"),
                          {"cover_fs": "", "sample_fs": [], "nfo_mtime": 1.0}),
        )
        mock_repo = mocker.patch("web.routers.scraper.VideoRepository")
        mock_repo.return_value.get_by_path.return_value = MagicMock(size_bytes=1000, mtime=1.0, cover_path="")

        response = client.post("/api/enrich-single", json={
            "file_path": "/tmp/ro_src/ABC-001.mp4",
            "number": "ABC-001",
        })

        data = response.json()
        assert data["success"] is True
        assert set(data) >= _ENRICH_RESULT_KEYS

    def test_enrich_single_no_output_root_has_full_shape(self, client, mocker):
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=_readonly_gallery_config("/tmp/ro_src"),
        )
        mocker.patch(
            "web.routers.scraper.resolve_owning_output_root",
            return_value=_owning_stub(output_root="", output_uri=""),
        )

        response = client.post("/api/enrich-single", json={
            "file_path": "/tmp/ro_src/ABC-001.mp4",
            "number": "ABC-001",
        })

        data = response.json()
        assert data["success"] is False
        assert set(data) >= _ENRICH_RESULT_KEYS

    def test_enrich_single_no_meta_has_full_shape(self, client, mocker):
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=_readonly_gallery_config("/tmp/ro_src"),
        )
        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=_owning_stub())
        mocker.patch("web.routers.scraper.resolve_ingest_plan", return_value=(None, ("none",)))

        response = client.post("/api/enrich-single", json={
            "file_path": "/tmp/ro_src/ABC-001.mp4",
            "number": "ABC-001",
        })

        data = response.json()
        assert data["success"] is False
        assert set(data) >= _ENRICH_RESULT_KEYS

    def test_enrich_single_exception_has_full_shape(self, client, mocker):
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=_readonly_gallery_config("/tmp/ro_src"),
        )
        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=_owning_stub())
        mocker.patch(
            "web.routers.scraper.resolve_ingest_plan",
            side_effect=RuntimeError("boom"),
        )

        response = client.post("/api/enrich-single", json={
            "file_path": "/tmp/ro_src/ABC-001.mp4",
            "number": "ABC-001",
        })

        data = response.json()
        assert data["success"] is False
        assert set(data) >= _ENRICH_RESULT_KEYS

    def test_fetch_samples_success_has_full_shape(self, client, mocker):
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=_readonly_gallery_config("/tmp/ro_src"),
        )
        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=_owning_stub())
        mocker.patch(
            "web.routers.scraper.search_jav",
            return_value={"number": "ABC-001", "source": "javbus", "sample_images": ["http://x/s1.jpg"]},
        )
        mock_repo = mocker.patch("web.routers.scraper.VideoRepository")
        mock_repo.return_value.get_by_path.return_value = MagicMock(size_bytes=1000, mtime=1.0)
        mocker.patch(
            "web.routers.scraper._produce_one",
            return_value=(Path("/out/ro_src-abcdef/ABC-001"), {"sample_fs": ["/out/x/fanart1.jpg"]}),
        )

        response = client.post("/api/scraper/fetch-samples", json={
            "file_path": "/tmp/ro_src/ABC-001.mp4",
            "number": "ABC-001",
        })

        data = response.json()
        assert data["success"] is True
        assert set(data) >= _ENRICH_RESULT_KEYS
        assert data["nfo_written"] is False
        assert data["cover_written"] is False

    def test_fetch_samples_no_output_root_has_full_shape(self, client, mocker):
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=_readonly_gallery_config("/tmp/ro_src"),
        )
        mocker.patch(
            "web.routers.scraper.resolve_owning_output_root",
            return_value=_owning_stub(output_root="", output_uri=""),
        )

        response = client.post("/api/scraper/fetch-samples", json={
            "file_path": "/tmp/ro_src/ABC-001.mp4",
            "number": "ABC-001",
        })

        data = response.json()
        assert data["success"] is False
        assert set(data) >= _ENRICH_RESULT_KEYS

    def test_fetch_samples_no_samples_found_has_full_shape(self, client, mocker):
        """search_jav → None（total not-found，FIX#3）→ success=False, 但仍是
        full EnrichResult shape。"""
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=_readonly_gallery_config("/tmp/ro_src"),
        )
        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=_owning_stub())
        mocker.patch("web.routers.scraper.search_jav", return_value=None)

        response = client.post("/api/scraper/fetch-samples", json={
            "file_path": "/tmp/ro_src/ABC-001.mp4",
            "number": "ABC-001",
        })

        data = response.json()
        assert data["success"] is False
        assert set(data) >= _ENRICH_RESULT_KEYS

    def test_fetch_samples_meta_found_no_samples_has_full_shape(self, client, mocker):
        """search_jav 找到資料但 sample_images 為空 → success=True，仍是 full
        EnrichResult shape。"""
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=_readonly_gallery_config("/tmp/ro_src"),
        )
        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=_owning_stub())
        mocker.patch(
            "web.routers.scraper.search_jav",
            return_value={"number": "ABC-001", "source": "javbus", "sample_images": []},
        )

        response = client.post("/api/scraper/fetch-samples", json={
            "file_path": "/tmp/ro_src/ABC-001.mp4",
            "number": "ABC-001",
        })

        data = response.json()
        assert data["success"] is True
        assert set(data) >= _ENRICH_RESULT_KEYS

    def test_fetch_samples_exception_has_full_shape(self, client, mocker):
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=_readonly_gallery_config("/tmp/ro_src"),
        )
        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=_owning_stub())
        mocker.patch(
            "web.routers.scraper.search_jav",
            side_effect=RuntimeError("boom"),
        )

        response = client.post("/api/scraper/fetch-samples", json={
            "file_path": "/tmp/ro_src/ABC-001.mp4",
            "number": "ABC-001",
        })

        data = response.json()
        assert data["success"] is False
        assert set(data) >= _ENRICH_RESULT_KEYS

    # fields_filled: 對於帶有多個非空 meta 欄位的片，回傳非空清單（"what got written"
    # 摘要）——readonly ingest/rescrape 沒有 _merge_meta 的部分合併概念，改列非空頂層
    # metadata keys。
    def test_enrich_single_fields_filled_non_empty(self, client, mocker):
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value=_readonly_gallery_config("/tmp/ro_src"),
        )
        mocker.patch("web.routers.scraper.resolve_owning_output_root", return_value=_owning_stub())
        mocker.patch(
            "web.routers.scraper.resolve_ingest_plan",
            return_value=(
                {
                    "number": "ABC-001", "title": "T", "cover": "",
                    "actors": ["A"], "tags": ["t1"], "date": "2024-01-01",
                    "maker": "M", "director": "D", "series": "S", "label": "L",
                },
                ("none",),
            ),
        )
        mocker.patch(
            "web.routers.scraper._produce_one",
            return_value=(Path("/out/ro_src-abcdef/ABC-001"),
                          {"cover_fs": "", "sample_fs": [], "nfo_mtime": 1.0}),
        )
        mock_repo = mocker.patch("web.routers.scraper.VideoRepository")
        mock_repo.return_value.get_by_path.return_value = MagicMock(size_bytes=1000, mtime=1.0, cover_path="")

        response = client.post("/api/enrich-single", json={
            "file_path": "/tmp/ro_src/ABC-001.mp4",
            "number": "ABC-001",
        })

        data = response.json()
        assert data["success"] is True
        assert set(data["fields_filled"]) == {
            "title", "actors", "tags", "date", "maker", "director", "series", "label",
        }


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


# ═══════════════════════════════════════════════════════════════════════════
# TASK-104-T3 (CD-104-5/9): 深度端對端整合 — 真檔案 + 真 DB，經 TestClient 打真實
# 端點，只 mock 外部邊界（search_jav / download_image / generate_jellyfin_images，
# 落點 core.readonly_producer.*，比照 tests/integration/test_readonly_offflavor_e2e.py
# 既有慣例）。generate_nfo 刻意保留真實（非 mock）——輸出 NFO 的 <title> 才是
# genuine 產物，能真正驗「候選版本 title 落地」而非 mock 斷言呼叫參數。
# ═══════════════════════════════════════════════════════════════════════════

def _e2e_off_config(src_path):
    return {
        "gallery": {
            "directories": [{"path": str(src_path), "readonly": True}],
            "path_mappings": {},
        },
        "scraper": {
            "external_manager": "off",
            "folder_layers": [],
            "folder_format": "",
            "filename_format": "{num}",
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": [],
        },
        "search": {"proxy_url": ""},
    }


def _e2e_snapshot(root):
    snap = {}
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            fp = Path(dirpath) / f
            st = fp.stat()
            digest = hashlib.sha256(fp.read_bytes()).hexdigest()
            snap[str(fp.relative_to(root))] = (st.st_size, st.st_mtime_ns, digest, st.st_ino)
    return snap


def _e2e_fake_generate_jellyfin_images(cover_fs, base_stem, **_kw):
    Path(base_stem + "-poster.jpg").write_bytes(b"POSTER")
    Path(base_stem + "-fanart.jpg").write_bytes(b"FANART")
    return {"poster": True, "fanart": True}


def _e2e_download_writes_url_bytes(url, dest):
    """side_effect for download_image: content is a deterministic function of the
    URL itself, so two downloads of two different URLs are trivially distinguishable
    by hash (used to prove a gear-rescrape cover overwrite actually happened)."""
    p = Path(dest)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(f"COVER-BYTES:{url}".encode())
    return True


class TestReadonlyRoutingE2E:
    """TASK-104-T3 DoD 逐條：放大鏡 ingest / gear rescrape 撞號覆蓋 / 補劇照
    samples_only / batch-enrich 唯讀項改道 / 被刪封面復原 / URI round-trip。"""

    def _wire(self, mocker, monkeypatch, config, db_path):
        from core.database import VideoRepository as RealRepo

        mocker.patch("web.routers.scraper.load_config", return_value=config)
        monkeypatch.setattr("core.readonly_producer.get_db_path", lambda: db_path)
        mocker.patch(
            "web.routers.scraper.VideoRepository",
            side_effect=lambda *a, **kw: RealRepo(db_path),
        )
        mocker.patch(
            "core.readonly_producer.generate_jellyfin_images",
            side_effect=_e2e_fake_generate_jellyfin_images,
        )

    def _init_db(self, tmp_path):
        from core.database import init_db
        db_path = tmp_path / "db" / "test.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        init_db(db_path)
        return db_path

    def _repo(self, db_path):
        from core.database import VideoRepository
        return VideoRepository(db_path)

    # ── 放大鏡 ingest：有 .nfo + 本地封面 → 零網路、落 output_dir、來源零寫入 ────

    def test_magnifier_ingest_local_first_zero_source_write(self, tmp_path, client, mocker, monkeypatch):
        from core.path_utils import to_file_uri, uri_to_local_fs_path

        src = tmp_path / "src"
        src.mkdir()
        video = src / "IN-001.mp4"
        video.write_bytes(b"FAKE-VIDEO")
        (src / "IN-001.nfo").write_text(
            "<movie><num>IN-001</num><title>[IN-001]Ingest Title</title></movie>",
            encoding="utf-8",
        )
        (src / "IN-001.jpg").write_bytes(b"LOCAL-COVER-BYTES")  # L1 same-stem cover hit

        db_path = self._init_db(tmp_path)
        config = _e2e_off_config(src)
        self._wire(mocker, monkeypatch, config, db_path)
        mock_search = mocker.patch("core.readonly_producer.search_jav")
        mock_download = mocker.patch("core.readonly_producer.download_image")

        before = _e2e_snapshot(src)

        canonical = to_file_uri(str(video))
        response = client.post("/api/enrich-single", json={
            "file_path": canonical,
            "number": "IN-001",
            "readonly_action": "ingest",
        })

        assert response.status_code == 200
        assert response.json()["success"] is True
        # ingest 有效 NFO + 本地封面命中 → 零網路（既不搜也不下載）
        mock_search.assert_not_called()
        mock_download.assert_not_called()

        # 來源 tree 零寫入（CD-104-9：內容雜湊 + stat metadata 前後相同）
        assert _e2e_snapshot(src) == before

        repo = self._repo(db_path)
        row = repo.get_by_path(canonical)
        assert row is not None
        assert row.title == "Ingest Title"  # _strip_num_prefixes 剝掉 [IN-001]
        assert row.output_dir  # 落 output_dir（非來源旁）
        movie_dir = uri_to_local_fs_path(row.output_dir, {})
        # movie_dir 內有封面 + 衍生 -poster/-fanart 三個 .jpg；glob 順序 filesystem-
        # dependent（本機 vs CI runner 不同），須明確排除 poster/fanart 只取主封面，
        # 否則 cover_fs[0] 可能是 -poster.jpg（CI flaky，比照 :1637 gear 測既有寫法）。
        cover_fs = [p for p in Path(movie_dir).glob("*.jpg")
                    if "-poster" not in p.name and "-fanart" not in p.name]
        assert cover_fs, "應有封面落 output_dir（copy 自本地）"
        assert len(cover_fs) == 1
        assert cover_fs[0].read_bytes() == b"LOCAL-COVER-BYTES"  # copy 非 download

    # ── gear rescrape：撞號候選遠端封面覆蓋舊本地封面（雜湊驗新封面 + NFO title） ──

    def test_gear_rescrape_overwrites_cover_with_candidate_and_title(self, tmp_path, client, mocker, monkeypatch):
        from core.path_utils import to_file_uri, uri_to_local_fs_path
        from core.scrapers.models import Video

        src = tmp_path / "src"
        src.mkdir()
        video = src / "RG-001.mp4"
        video.write_bytes(b"FAKE-VIDEO")
        # 無 .nfo / 無本地封面 → 第一次 ingest 走 search_jav+download（建出初版 movie_dir）

        db_path = self._init_db(tmp_path)
        config = _e2e_off_config(src)
        self._wire(mocker, monkeypatch, config, db_path)
        canonical = to_file_uri(str(video))

        # 第一次呼叫（ingest）：建出「舊」封面，之後被 gear rescrape 覆蓋
        mocker.patch(
            "core.readonly_producer.search_jav",
            return_value={
                "number": "RG-001", "title": "Old Title",
                "cover": "http://x/old.jpg", "actors": [], "tags": [],
                "date": "", "maker": "", "sample_images": [],
            },
        )
        mocker.patch(
            "core.readonly_producer.download_image", side_effect=_e2e_download_writes_url_bytes,
        )
        resp1 = client.post("/api/enrich-single", json={
            "file_path": canonical, "number": "RG-001", "readonly_action": "ingest",
        })
        assert resp1.json()["success"] is True

        repo = self._repo(db_path)
        row_before = repo.get_by_path(canonical)
        movie_dir = uri_to_local_fs_path(row_before.output_dir, {})
        old_cover_files = list(Path(movie_dir).glob("*.jpg"))
        old_cover_files = [p for p in old_cover_files if "-poster" not in p.name and "-fanart" not in p.name]
        assert len(old_cover_files) == 1
        old_cover_path = old_cover_files[0]
        old_hash = hashlib.sha256(old_cover_path.read_bytes()).hexdigest()
        assert old_cover_path.read_bytes() == b"COVER-BYTES:http://x/old.jpg"

        # 第二次呼叫（gear rescrape）：撞號候選 → 遠端覆蓋，NEVER 沿用舊本地封面
        fake_video = MagicMock(spec=Video)
        fake_video.to_legacy_dict.return_value = {
            "number": "RG-001", "title": "Candidate Title",
            "cover": "http://x/new.jpg", "actors": [], "tags": [],
            "date": "", "maker": "", "source": "javlibrary",
            "url": "https://www.javlibrary.com/ja/?v=abcxyz",
            "director": "", "duration": None, "label": "", "series": "",
            "sample_images": [],
        }
        fake_video.rating = None
        fake_video.summary = ""
        mocker.patch("web.routers.scraper.fetch_javlib_by_detail_url", return_value=fake_video)

        resp2 = client.post("/api/enrich-single", json={
            "file_path": canonical, "number": "RG-001",
            "readonly_action": "rescrape",
            "source": "javlibrary",
            "detail_url": "https://www.javlibrary.com/ja/?v=abcxyz",
            "mode": "refresh_full",
            # overwrite_existing:True 對齊真實齒輪重刮（state-rescrape.js:404）；feature/105 AC4 後 refresh_full 保留政策綁 overwrite_existing
            "overwrite_existing": True,
        })
        assert resp2.json()["success"] is True

        new_cover_path = old_cover_path  # 同一 movie_dir、同一 basename → 同路徑覆寫
        assert new_cover_path.exists()
        new_hash = hashlib.sha256(new_cover_path.read_bytes()).hexdigest()
        assert new_hash != old_hash, "gear rescrape 必須覆蓋舊封面（雜湊須變）"
        assert new_cover_path.read_bytes() == b"COVER-BYTES:http://x/new.jpg"

        nfo_path = Path(movie_dir) / "RG-001.nfo"
        assert nfo_path.exists()
        nfo_text = nfo_path.read_text(encoding="utf-8")
        assert "Candidate Title" in nfo_text
        assert "Old Title" not in nfo_text

    # ── 「被刪封面」case：output_dir 封面被刪 → gear rescrape → 復原 ─────────────

    def test_gear_rescrape_restores_deleted_output_cover(self, tmp_path, client, mocker, monkeypatch):
        from core.path_utils import to_file_uri, uri_to_local_fs_path
        from core.scrapers.models import Video

        src = tmp_path / "src"
        src.mkdir()
        video = src / "DL-001.mp4"
        video.write_bytes(b"FAKE-VIDEO")

        db_path = self._init_db(tmp_path)
        config = _e2e_off_config(src)
        self._wire(mocker, monkeypatch, config, db_path)
        canonical = to_file_uri(str(video))

        mocker.patch(
            "core.readonly_producer.search_jav",
            return_value={
                "number": "DL-001", "title": "T", "cover": "http://x/c.jpg",
                "actors": [], "tags": [], "date": "", "maker": "", "sample_images": [],
            },
        )
        mocker.patch(
            "core.readonly_producer.download_image", side_effect=_e2e_download_writes_url_bytes,
        )
        resp1 = client.post("/api/enrich-single", json={
            "file_path": canonical, "number": "DL-001", "readonly_action": "ingest",
        })
        assert resp1.json()["success"] is True

        repo = self._repo(db_path)
        row = repo.get_by_path(canonical)
        movie_dir = uri_to_local_fs_path(row.output_dir, {})
        cover_path = Path(movie_dir) / "DL-001.jpg"
        assert cover_path.exists()
        cover_path.unlink()  # 模擬使用者手動刪除 output_dir 封面
        assert not cover_path.exists()

        fake_video = MagicMock(spec=Video)
        fake_video.to_legacy_dict.return_value = {
            "number": "DL-001", "title": "Restored", "cover": "http://x/restored.jpg",
            "actors": [], "tags": [], "date": "", "maker": "", "source": "javlibrary",
            "url": "https://www.javlibrary.com/ja/?v=restored", "director": "",
            "duration": None, "label": "", "series": "", "sample_images": [],
        }
        fake_video.rating = None
        fake_video.summary = ""
        mocker.patch("web.routers.scraper.fetch_javlib_by_detail_url", return_value=fake_video)

        resp2 = client.post("/api/enrich-single", json={
            "file_path": canonical, "number": "DL-001",
            "readonly_action": "rescrape", "source": "javlibrary",
            "detail_url": "https://www.javlibrary.com/ja/?v=restored",
            # Codex PR#113 P2#3（round 2）：real gear 一律送 mode='refresh_full'+
            # overwrite_existing=true（state-rescrape.js:404/408）——這兩個欄位漏帶
            # 會落到 EnrichRequest 預設 mode='fill_missing'/overwrite_existing=False，
            # 誤觸新的 cover-preserve gate（DB 仍有舊 cover_path，即使檔案已被使用者
            # 手動刪除），讓本測試想驗的「gear rescrape 復原被刪封面」失真。
            "mode": "refresh_full", "overwrite_existing": True,
        })
        assert resp2.json()["success"] is True
        assert cover_path.exists(), "gear rescrape 須復原被刪的 output_dir 封面"
        assert cover_path.read_bytes() == b"COVER-BYTES:http://x/restored.jpg"

    # ── Codex PR#113 P2#3（round 2）：放大鏡 fill_missing 在「已有封面」的片上點
    # 只補 NFO，絕不動既有封面（真檔案雜湊驗證；router-level mock 版見
    # TestEnrichSingleReadonlyCoverPreserveGate） ──────────────────────────────

    def test_magnifier_fill_missing_preserves_existing_cover_bytes(self, tmp_path, client, mocker, monkeypatch):
        from core.path_utils import to_file_uri, uri_to_local_fs_path

        src = tmp_path / "src"
        src.mkdir()
        video = src / "PV-001.mp4"
        video.write_bytes(b"FAKE-VIDEO")
        # 無 .nfo / 無本地封面 → 第一次呼叫走 search_jav+download 建出既有封面

        db_path = self._init_db(tmp_path)
        config = _e2e_off_config(src)
        self._wire(mocker, monkeypatch, config, db_path)
        canonical = to_file_uri(str(video))

        mocker.patch(
            "core.readonly_producer.search_jav",
            return_value={
                "number": "PV-001", "title": "First Title",
                "cover": "http://x/first.jpg", "actors": [], "tags": [],
                "date": "", "maker": "", "sample_images": [],
            },
        )
        mock_download = mocker.patch(
            "core.readonly_producer.download_image", side_effect=_e2e_download_writes_url_bytes,
        )
        resp1 = client.post("/api/enrich-single", json={
            "file_path": canonical, "number": "PV-001", "readonly_action": "ingest",
        })
        assert resp1.json()["success"] is True
        assert resp1.json()["cover_written"] is True

        repo = self._repo(db_path)
        row1 = repo.get_by_path(canonical)
        movie_dir = uri_to_local_fs_path(row1.output_dir, {})
        cover_fs_path = Path(movie_dir) / "PV-001.jpg"
        assert cover_fs_path.exists()
        before_bytes = cover_fs_path.read_bytes()
        before_hash = hashlib.sha256(before_bytes).hexdigest()
        assert before_bytes == b"COVER-BYTES:http://x/first.jpg"

        # 第二次呼叫（放大鏡 fill_missing，預設 mode/overwrite_existing/write_cover）：
        # search_jav 這次回一個「不同」的遠端封面 URL —— 若 preserve gate 沒生效，
        # download_image 會被再叫一次、封面雜湊會變成 second.jpg 的內容。
        mocker.patch(
            "core.readonly_producer.search_jav",
            return_value={
                "number": "PV-001", "title": "Second Title",
                "cover": "http://x/second.jpg", "actors": [], "tags": [],
                "date": "", "maker": "", "sample_images": [],
            },
        )
        mock_download.reset_mock()

        resp2 = client.post("/api/enrich-single", json={
            "file_path": canonical, "number": "PV-001", "readonly_action": "ingest",
            "mode": "fill_missing", "overwrite_existing": False,
        })
        assert resp2.json()["success"] is True
        # cover_written=False：本次沒有實際寫入新封面（preserve gate 生效）
        assert resp2.json()["cover_written"] is False

        mock_download.assert_not_called()
        after_bytes = cover_fs_path.read_bytes()
        assert hashlib.sha256(after_bytes).hexdigest() == before_hash, (
            "fill_missing + overwrite=False 不得動既有封面內容"
        )
        assert after_bytes == b"COVER-BYTES:http://x/first.jpg"

        row2 = repo.get_by_path(canonical)
        assert row2.cover_path == row1.cover_path, "DB cover_path 必須保留既有值"

        # NFO 仍照第二次的 metadata 重新寫出（只補 NFO，不動封面）
        nfo_path = Path(movie_dir) / "PV-001.nfo"
        assert nfo_path.exists()
        assert "Second Title" in nfo_path.read_text(encoding="utf-8")

    def test_magnifier_write_cover_false_preserves_cover_regardless_of_mode(
        self, tmp_path, client, mocker, monkeypatch,
    ):
        """write_cover=false → 即使 mode=refresh_full（理論上「一律寫」），封面仍
        必須被保留 —— 對齊 core.enricher._write_cover 的 `if not write_cover: return
        False` 短路（write_cover 的優先序高於 mode）。"""
        from core.path_utils import to_file_uri, uri_to_local_fs_path

        src = tmp_path / "src"
        src.mkdir()
        video = src / "WCF-001.mp4"
        video.write_bytes(b"FAKE-VIDEO")

        db_path = self._init_db(tmp_path)
        config = _e2e_off_config(src)
        self._wire(mocker, monkeypatch, config, db_path)
        canonical = to_file_uri(str(video))

        mocker.patch(
            "core.readonly_producer.search_jav",
            return_value={
                "number": "WCF-001", "title": "T", "cover": "http://x/c.jpg",
                "actors": [], "tags": [], "date": "", "maker": "", "sample_images": [],
            },
        )
        mock_download = mocker.patch(
            "core.readonly_producer.download_image", side_effect=_e2e_download_writes_url_bytes,
        )
        resp1 = client.post("/api/enrich-single", json={
            "file_path": canonical, "number": "WCF-001", "readonly_action": "ingest",
        })
        assert resp1.json()["success"] is True

        repo = self._repo(db_path)
        row1 = repo.get_by_path(canonical)
        movie_dir = uri_to_local_fs_path(row1.output_dir, {})
        cover_fs_path = Path(movie_dir) / "WCF-001.jpg"
        before_hash = hashlib.sha256(cover_fs_path.read_bytes()).hexdigest()

        mock_download.reset_mock()
        resp2 = client.post("/api/enrich-single", json={
            "file_path": canonical, "number": "WCF-001", "readonly_action": "ingest",
            "mode": "refresh_full", "overwrite_existing": True, "write_cover": False,
        })
        assert resp2.json()["success"] is True
        assert resp2.json()["cover_written"] is False
        mock_download.assert_not_called()
        assert hashlib.sha256(cover_fs_path.read_bytes()).hexdigest() == before_hash

    # P1 revert + reject (round-3 review 2026-07-21, owner-confirmed): a Codex
    # PR#113 round-3 write_nfo skip-gate here was a P1 data-loss (a title-
    # changing rescrape with write_nfo=False skipped the new NFO write while
    # stale-cleanup still unlinked the OLD one — NFO lost, DB kept a stale
    # nfo_mtime claiming it exists). Readonly produce is holistic (a library
    # entry always has an NFO) — write_nfo=false is now REJECTED up front
    # instead of "honored". This test used to assert the (buggy) skip
    # behaviour; repurposed to assert the rejection + that nothing on disk/DB
    # changes as a result of the rejected call.
    def test_magnifier_write_nfo_false_rejected_nfo_untouched(
        self, tmp_path, client, mocker, monkeypatch,
    ):
        """write_nfo=false → rejected before any I/O; the existing NFO on disk
        (bytes + mtime) and DB nfo_mtime are completely untouched (not even
        re-read/re-written) by the rejected call."""
        from core.path_utils import to_file_uri, uri_to_local_fs_path

        src = tmp_path / "src"
        src.mkdir()
        video = src / "WNF-001.mp4"
        video.write_bytes(b"FAKE-VIDEO")

        db_path = self._init_db(tmp_path)
        config = _e2e_off_config(src)
        self._wire(mocker, monkeypatch, config, db_path)
        canonical = to_file_uri(str(video))

        mocker.patch(
            "core.readonly_producer.search_jav",
            return_value={
                "number": "WNF-001", "title": "T", "cover": "http://x/c.jpg",
                "actors": [], "tags": [], "date": "", "maker": "", "sample_images": [],
            },
        )
        mocker.patch(
            "core.readonly_producer.download_image", side_effect=_e2e_download_writes_url_bytes,
        )
        resp1 = client.post("/api/enrich-single", json={
            "file_path": canonical, "number": "WNF-001", "readonly_action": "ingest",
        })
        assert resp1.json()["success"] is True
        assert resp1.json()["nfo_written"] is True

        repo = self._repo(db_path)
        row1 = repo.get_by_path(canonical)
        movie_dir = uri_to_local_fs_path(row1.output_dir, {})
        nfo_path = Path(movie_dir) / "WNF-001.nfo"
        assert nfo_path.exists()
        before_hash = hashlib.sha256(nfo_path.read_bytes()).hexdigest()
        before_mtime_ns = nfo_path.stat().st_mtime_ns
        before_db_nfo_mtime = row1.nfo_mtime
        assert before_db_nfo_mtime > 0

        resp2 = client.post("/api/enrich-single", json={
            "file_path": canonical, "number": "WNF-001", "readonly_action": "ingest",
            "mode": "refresh_full", "overwrite_existing": True, "write_nfo": False,
        })
        data2 = resp2.json()
        assert data2["success"] is False
        assert data2["nfo_written"] is False
        assert data2["cover_written"] is False
        assert data2["extrafanart_written"] == 0
        assert data2["fields_filled"] == []
        assert data2["source_used"] == ""
        assert data2["error"]
        assert data2["reason"] == "error"
        assert set(data2) >= _ENRICH_RESULT_KEYS

        assert nfo_path.stat().st_mtime_ns == before_mtime_ns
        assert hashlib.sha256(nfo_path.read_bytes()).hexdigest() == before_hash

        row2 = repo.get_by_path(canonical)
        assert row2.nfo_mtime == before_db_nfo_mtime, (
            "a rejected write_nfo=false call must not touch the DB row at all"
        )

    # P1 regression (round-3 revert, 2026-07-21): the exact scenario the
    # round-3 write_nfo skip-gate broke — a title-changing rescrape/re-ingest
    # (old_base != new_base) with write_nfo left at its (now only-supported)
    # True default must write the NEW basename's NFO and clean up the OLD
    # basename's NFO, leaving exactly one NFO on disk, never zero.
    def test_magnifier_title_change_writes_new_nfo_and_cleans_old(
        self, tmp_path, client, mocker, monkeypatch,
    ):
        from core.path_utils import to_file_uri, uri_to_local_fs_path

        src = tmp_path / "src"
        src.mkdir()
        video = src / "TC-001.mp4"
        video.write_bytes(b"FAKE-VIDEO")

        db_path = self._init_db(tmp_path)
        config = _e2e_off_config(src)
        # title-driven basename (default filename_format) — needed so old_base
        # != new_base across the title change below (P1 repro precondition).
        config["scraper"]["filename_format"] = "{num} {title}"
        self._wire(mocker, monkeypatch, config, db_path)
        canonical = to_file_uri(str(video))

        mocker.patch(
            "core.readonly_producer.search_jav",
            return_value={
                "number": "TC-001", "title": "First Title", "cover": "",
                "actors": [], "tags": [], "date": "", "maker": "", "sample_images": [],
            },
        )
        resp1 = client.post("/api/enrich-single", json={
            "file_path": canonical, "number": "TC-001", "readonly_action": "ingest",
        })
        assert resp1.json()["success"] is True
        assert resp1.json()["nfo_written"] is True

        repo = self._repo(db_path)
        row1 = repo.get_by_path(canonical)
        movie_dir = Path(uri_to_local_fs_path(row1.output_dir, {}))
        old_nfos = list(movie_dir.glob("*.nfo"))
        assert len(old_nfos) == 1
        old_nfo_path = old_nfos[0]
        assert "First Title" in old_nfo_path.read_text(encoding="utf-8")

        mocker.patch(
            "core.readonly_producer.search_jav",
            return_value={
                "number": "TC-001", "title": "Second Title", "cover": "",
                "actors": [], "tags": [], "date": "", "maker": "", "sample_images": [],
            },
        )
        resp2 = client.post("/api/enrich-single", json={
            "file_path": canonical, "number": "TC-001", "readonly_action": "ingest",
            "mode": "refresh_full", "overwrite_existing": True,
        })
        assert resp2.json()["success"] is True
        assert resp2.json()["nfo_written"] is True

        nfos_after = list(movie_dir.glob("*.nfo"))
        assert len(nfos_after) == 1, (
            f"exactly one NFO must survive a title change (old cleaned, new "
            f"written) — never zero (the P1) or two: {nfos_after}"
        )
        assert not old_nfo_path.exists(), (
            "OLD basename's NFO must be cleaned up — this is the exact P1 the "
            "round-3 write_nfo skip-gate introduced (skip-write + stale-cleanup "
            "still ran => NFO lost entirely)"
        )
        assert nfos_after[0] != old_nfo_path
        assert "Second Title" in nfos_after[0].read_text(encoding="utf-8")

        row2 = repo.get_by_path(canonical)
        assert row2.nfo_mtime > 0

    # Codex PR#113 one-pass alignment (2026-07-21): resolve_ingest_plan must set
    # meta['source'] = 'nfo' for the NFO-sourced ingest branch so the readonly
    # EnrichResult's source_used field isn't silently ''.
    def test_magnifier_ingest_from_valid_nfo_reports_source_used_nfo(
        self, tmp_path, client, mocker, monkeypatch,
    ):
        from core.path_utils import to_file_uri

        src = tmp_path / "src"
        src.mkdir()
        video = src / "SU-001.mp4"
        video.write_bytes(b"FAKE-VIDEO")
        (src / "SU-001.nfo").write_text(
            "<movie><num>SU-001</num><title>[SU-001]NFO Title</title></movie>",
            encoding="utf-8",
        )

        db_path = self._init_db(tmp_path)
        config = _e2e_off_config(src)
        self._wire(mocker, monkeypatch, config, db_path)
        mock_search = mocker.patch("core.readonly_producer.search_jav")
        canonical = to_file_uri(str(video))

        response = client.post("/api/enrich-single", json={
            "file_path": canonical, "number": "SU-001", "readonly_action": "ingest",
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["source_used"] == "nfo"
        mock_search.assert_not_called()  # valid NFO → zero network, source is 'nfo' not a scraper name

    # P1 revert + reject (round-3 review 2026-07-21): write_nfo=false is now
    # REJECTED regardless of write_cover — readonly produce is holistic (a
    # library entry always has an NFO), so there is no longer a "write_nfo=
    # false + write_cover=false DB-only" path to not-crash on; the whole call
    # is rejected up front, before resolve_ingest_plan/search_jav/download are
    # ever reached, and no DB row is created at all.
    def test_magnifier_write_nfo_false_and_write_cover_false_rejected_no_db_row(
        self, tmp_path, client, mocker, monkeypatch,
    ):
        from core.path_utils import to_file_uri

        src = tmp_path / "src"
        src.mkdir()
        video = src / "DBO-001.mp4"
        video.write_bytes(b"FAKE-VIDEO")

        db_path = self._init_db(tmp_path)
        config = _e2e_off_config(src)
        self._wire(mocker, monkeypatch, config, db_path)
        canonical = to_file_uri(str(video))

        mock_search = mocker.patch("core.readonly_producer.search_jav")
        mock_download = mocker.patch("core.readonly_producer.download_image")

        response = client.post("/api/enrich-single", json={
            "file_path": canonical, "number": "DBO-001", "readonly_action": "ingest",
            "write_nfo": False, "write_cover": False,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["nfo_written"] is False
        assert data["cover_written"] is False
        assert data["error"]
        assert data["reason"] == "error"
        mock_search.assert_not_called()
        mock_download.assert_not_called()

        repo = self._repo(db_path)
        assert repo.get_by_path(canonical) is None  # rejected before any DB upsert

    # ── 補劇照唯讀：只劇照落 output_dir，nfo/封面 stat+雜湊未變 ─────────────────

    def test_fetch_samples_readonly_only_touches_extrafanart(self, tmp_path, client, mocker, monkeypatch):
        from core.path_utils import to_file_uri, uri_to_local_fs_path

        src = tmp_path / "src"
        src.mkdir()
        video = src / "SM-001.mp4"
        video.write_bytes(b"FAKE-VIDEO")

        db_path = self._init_db(tmp_path)
        config = _e2e_off_config(src)
        self._wire(mocker, monkeypatch, config, db_path)
        canonical = to_file_uri(str(video))

        mocker.patch(
            "core.readonly_producer.search_jav",
            return_value={
                "number": "SM-001", "title": "T", "cover": "http://x/c.jpg",
                "actors": [], "tags": [], "date": "", "maker": "", "sample_images": [],
            },
        )
        mocker.patch(
            "core.readonly_producer.download_image", side_effect=_e2e_download_writes_url_bytes,
        )
        resp1 = client.post("/api/enrich-single", json={
            "file_path": canonical, "number": "SM-001", "readonly_action": "ingest",
        })
        assert resp1.json()["success"] is True

        repo = self._repo(db_path)
        row = repo.get_by_path(canonical)
        movie_dir = Path(uri_to_local_fs_path(row.output_dir, {}))
        nfo_snapshot_before = _e2e_snapshot(movie_dir)

        # fetch-samples 走 web.routers.scraper.search_jav（獨立呼叫點，非 resolve_ingest_plan）
        mocker.patch(
            "web.routers.scraper.search_jav",
            return_value={
                "number": "SM-001",
                "sample_images": ["http://x/s1.jpg", "http://x/s2.jpg"],
            },
        )

        resp2 = client.post("/api/scraper/fetch-samples", json={
            "file_path": canonical, "number": "SM-001",
        })
        data2 = resp2.json()
        assert data2["success"] is True
        assert data2["extrafanart_written"] == 2

        ef_dir = movie_dir / "extrafanart"
        ef_files = sorted(ef_dir.glob("*.jpg")) if ef_dir.exists() else []
        assert len(ef_files) == 2

        # nfo + 封面 + poster/fanart 的 stat+雜湊完全不變（samples_only 不得碰它們）
        after = _e2e_snapshot(movie_dir)
        for relpath, before_stat in nfo_snapshot_before.items():
            assert after[relpath] == before_stat, f"{relpath} 被 samples_only 動到了"

    # ── P1/P2 grok-review：full-mode 再入（gear rescrape）不得清空既有樣張(磁碟+DB) ──

    def test_full_mode_reentry_preserves_samples_disk_and_db(self, tmp_path, client, mocker, monkeypatch):
        """ingest → 補劇照(samples_only，磁碟+DB 都有樣張) → gear rescrape
        (assets_mode='full'，resolve_ingest_plan 的 rescrape 分支 meta['sample_images']
        恆為 []，CD-104-3) — 樣張必須在磁碟(extrafanart/)與 DB(sample_images) 都存活，
        不可被第三步的 full-mode 再入清空（P1 finding）。"""
        from core.path_utils import to_file_uri, uri_to_local_fs_path
        from core.scrapers.models import Video

        src = tmp_path / "src"
        src.mkdir()
        video = src / "PR-001.mp4"
        video.write_bytes(b"FAKE-VIDEO")

        db_path = self._init_db(tmp_path)
        config = _e2e_off_config(src)
        self._wire(mocker, monkeypatch, config, db_path)
        canonical = to_file_uri(str(video))

        # Step 1: ingest — 建出 movie_dir + 初版封面。
        mocker.patch(
            "core.readonly_producer.search_jav",
            return_value={
                "number": "PR-001", "title": "T", "cover": "http://x/c.jpg",
                "actors": [], "tags": [], "date": "", "maker": "", "sample_images": [],
            },
        )
        mocker.patch(
            "core.readonly_producer.download_image", side_effect=_e2e_download_writes_url_bytes,
        )
        resp1 = client.post("/api/enrich-single", json={
            "file_path": canonical, "number": "PR-001", "readonly_action": "ingest",
        })
        assert resp1.json()["success"] is True

        # Step 2: 補劇照 — DB sample_images + 磁碟 extrafanart/ 都落地 2 張。
        mocker.patch(
            "web.routers.scraper.search_jav",
            return_value={
                "number": "PR-001",
                "sample_images": ["http://x/s1.jpg", "http://x/s2.jpg"],
            },
        )
        resp_samples = client.post("/api/scraper/fetch-samples", json={
            "file_path": canonical, "number": "PR-001",
        })
        assert resp_samples.json()["success"] is True
        assert resp_samples.json()["extrafanart_written"] == 2

        repo = self._repo(db_path)
        row = repo.get_by_path(canonical)
        assert len(row.sample_images) == 2
        movie_dir = Path(uri_to_local_fs_path(row.output_dir, {}))
        ef_dir = movie_dir / "extrafanart"
        assert len(list(ef_dir.glob("*.jpg"))) == 2

        # Step 3: gear rescrape（撞號選版）— full-mode RE-ENTRY，本輪 meta 無劇照。
        fake_video = MagicMock(spec=Video)
        fake_video.to_legacy_dict.return_value = {
            "number": "PR-001", "title": "Rescraped Title", "cover": "http://x/new.jpg",
            "actors": [], "tags": [], "date": "", "maker": "", "source": "javlibrary",
            "url": "https://www.javlibrary.com/ja/?v=pr001", "director": "",
            "duration": None, "label": "", "series": "", "sample_images": [],
        }
        fake_video.rating = None
        fake_video.summary = ""
        mocker.patch("web.routers.scraper.fetch_javlib_by_detail_url", return_value=fake_video)

        resp2 = client.post("/api/enrich-single", json={
            "file_path": canonical, "number": "PR-001",
            "readonly_action": "rescrape", "source": "javlibrary",
            "detail_url": "https://www.javlibrary.com/ja/?v=pr001",
        })
        assert resp2.json()["success"] is True

        row2 = repo.get_by_path(canonical)
        assert len(row2.sample_images) == 2, "full-mode 再入不得清空 DB sample_images"
        assert row2.sample_images == row.sample_images
        assert len(list(ef_dir.glob("*.jpg"))) == 2, "full-mode 再入不得清空磁碟 extrafanart"

    # ── P2 grok-review：full-mode 再入候選封面為空 → 不得清空既有 DB cover_path ────

    def test_full_mode_reentry_empty_candidate_cover_preserves_db_cover_path(
        self, tmp_path, client, mocker, monkeypatch,
    ):
        """gear rescrape 候選封面為空（cover_strategy=('none',)）— DB cover_path
        必須保留既有值，不可被清成 ''（P2 finding：破圖 + 放大鏡誤重現）。"""
        from core.path_utils import to_file_uri, uri_to_local_fs_path
        from core.scrapers.models import Video

        src = tmp_path / "src"
        src.mkdir()
        video = src / "PC-001.mp4"
        video.write_bytes(b"FAKE-VIDEO")

        db_path = self._init_db(tmp_path)
        config = _e2e_off_config(src)
        self._wire(mocker, monkeypatch, config, db_path)
        canonical = to_file_uri(str(video))

        # Step 1: ingest — 建出既有封面。
        mocker.patch(
            "core.readonly_producer.search_jav",
            return_value={
                "number": "PC-001", "title": "T", "cover": "http://x/c.jpg",
                "actors": [], "tags": [], "date": "", "maker": "", "sample_images": [],
            },
        )
        mocker.patch(
            "core.readonly_producer.download_image", side_effect=_e2e_download_writes_url_bytes,
        )
        resp1 = client.post("/api/enrich-single", json={
            "file_path": canonical, "number": "PC-001", "readonly_action": "ingest",
        })
        assert resp1.json()["success"] is True

        repo = self._repo(db_path)
        row = repo.get_by_path(canonical)
        assert row.cover_path

        # Step 2: gear rescrape — 候選版本 cover 為空字串 → resolve_ingest_plan 的
        # rescrape 分支給 ('none',)，_write_movie_assets 不寫封面、cover_fs=''。
        fake_video = MagicMock(spec=Video)
        fake_video.to_legacy_dict.return_value = {
            "number": "PC-001", "title": "Candidate No Cover", "cover": "",
            "actors": [], "tags": [], "date": "", "maker": "", "source": "javlibrary",
            "url": "https://www.javlibrary.com/ja/?v=pc001", "director": "",
            "duration": None, "label": "", "series": "", "sample_images": [],
        }
        fake_video.rating = None
        fake_video.summary = ""
        mocker.patch("web.routers.scraper.fetch_javlib_by_detail_url", return_value=fake_video)
        mock_download = mocker.patch(
            "core.readonly_producer.download_image", side_effect=_e2e_download_writes_url_bytes,
        )

        resp2 = client.post("/api/enrich-single", json={
            "file_path": canonical, "number": "PC-001",
            "readonly_action": "rescrape", "source": "javlibrary",
            "detail_url": "https://www.javlibrary.com/ja/?v=pc001",
        })
        assert resp2.json()["success"] is True
        mock_download.assert_not_called()  # ('none',) 分支不下載

        row2 = repo.get_by_path(canonical)
        assert row2.cover_path == row.cover_path, (
            "候選封面為空時 DB cover_path 必須保留既有值，不可清成 ''"
        )
        assert row2.cover_path != "", "破圖回歸：DB cover_path 被清空"
        # 磁碟上原本的封面檔案也仍在（沒被清 stale-singleton 誤刪）
        movie_dir = Path(uri_to_local_fs_path(row.output_dir, {}))
        assert list(movie_dir.glob("*.jpg")), "既有封面檔仍應留在磁碟上"

    # ── batch-enrich 唯讀項改道 ingest（router-level：驗 offload 結構 + 呼叫序）───

    def test_batch_enrich_mixed_readonly_routes_via_executor(self, client, mocker):
        """混合批（1 唯讀 + 1 可寫）：唯讀項不再拒絕，經 run_in_executor offload
        呼叫 resolve_owning_output_root → resolve_ingest_plan → _produce_one；
        可寫項照常 enrich_single；整批不中斷。"""
        config = {
            "gallery": {
                "directories": [{"path": "/tmp/ro_src", "readonly": True}],
                "path_mappings": {},
            },
            "search": {}, "scraper": {},
        }
        mocker.patch("web.routers.scraper.load_config", return_value=config)
        source_stub = MagicMock()
        source_stub.path = "/tmp/ro_src"
        mocker.patch(
            "web.routers.scraper.resolve_owning_output_root",
            return_value=(source_stub, "/out/ro_src-x", "file:///out/ro_src-x"),
        )
        mock_plan = mocker.patch(
            "web.routers.scraper.resolve_ingest_plan",
            return_value=({"number": "RO-001", "title": "T", "cover": ""}, ("none",)),
        )
        # _produce_one now returns (movie_dir, assets) — tuple default so the
        # router's `_, assets = _produce_one(...)` unpack succeeds.
        mock_produce = mocker.patch(
            "web.routers.scraper._produce_one",
            return_value=(Path("/out/ro_src-x/RO-001"), {"cover_fs": "", "sample_fs": [], "nfo_mtime": 1.0}),
        )
        mock_repo = mocker.patch("web.routers.scraper.VideoRepository")
        mock_repo.return_value.get_by_path.return_value = MagicMock(size_bytes=10, mtime=1.0)
        mock_enrich = mocker.patch(
            "web.routers.scraper.enrich_single", return_value=_ok_result()
        )

        response = client.post("/api/batch-enrich", json={
            "items": [
                {"file_path": "/tmp/ro_src/RO-001.mp4", "number": "RO-001"},
                {"file_path": "/tmp/rw/RW-002.mp4", "number": "RW-002"},
            ],
            "mode": "refresh_full",
        })

        assert response.status_code == 200
        events = [
            json.loads(line[6:])
            for line in response.text.strip().split("\n") if line.startswith("data: ")
        ]
        result_items = [e for e in events if e["type"] == "result-item"]
        by_number = {e["number"]: e for e in result_items}

        # 唯讀項：不再拒絕，改道成功
        assert by_number["RO-001"]["success"] is True
        mock_plan.assert_called_once()
        assert mock_plan.call_args.kwargs["action"] == "ingest"
        mock_produce.assert_called_once()
        assert mock_produce.call_args.kwargs["assets_mode"] == "full"
        # 可寫項：照常走既有 enrich_single 路徑
        assert by_number["RW-002"]["success"] is True
        mock_enrich.assert_called_once()

        done = [e for e in events if e["type"] == "done"][0]
        assert done["summary"] == {"total": 2, "success": 2, "failed": 0}

    def test_batch_enrich_readonly_item_no_scrape_when_no_nfo_and_search_fails(self, client, mocker):
        """唯讀項無 .nfo 且 search_jav 回 None → reason='not_found'（Codex PR#113
        one-pass alignment，對齊 core.enricher 自己的 not_found reason 值），
        failed_count+=1，不中斷整批（另一唯讀項 stub 省略；此測試聚焦單一唯讀項
        失敗語意）。"""
        config = {
            "gallery": {
                "directories": [{"path": "/tmp/ro_src", "readonly": True}],
                "path_mappings": {},
            },
            "search": {}, "scraper": {},
        }
        mocker.patch("web.routers.scraper.load_config", return_value=config)
        source_stub = MagicMock()
        source_stub.path = "/tmp/ro_src"
        mocker.patch(
            "web.routers.scraper.resolve_owning_output_root",
            return_value=(source_stub, "/out/ro_src-x", "file:///out/ro_src-x"),
        )
        mocker.patch(
            "web.routers.scraper.resolve_ingest_plan", return_value=(None, ("none",)),
        )
        mock_produce = mocker.patch("web.routers.scraper._produce_one")

        response = client.post("/api/batch-enrich", json={
            "items": [{"file_path": "/tmp/ro_src/NS-001.mp4", "number": "NS-001"}],
            "mode": "refresh_full",
        })

        events = [
            json.loads(line[6:])
            for line in response.text.strip().split("\n") if line.startswith("data: ")
        ]
        result_items = [e for e in events if e["type"] == "result-item"]
        assert result_items[0]["success"] is False
        assert result_items[0]["reason"] == "not_found"
        mock_produce.assert_not_called()

    # ── URI round-trip 不變式：to_file_uri(uri_to_local_fs_path(u, pm), pm) == u ──

    def test_uri_round_trip_invariant(self, monkeypatch):
        """_produce_one 內 `src_uri = to_file_uri(file_info['path'], path_mappings)`
        必須與呼叫端傳入的 canonical URI（`existing = repo.get_by_path(canonical)` 用的
        同一個值）一致，否則 upsert 開新 row / 與既有 row 錯位（卡片「特有邊界」#1）。
        canonical 一律取自 `to_file_uri(fs_path, pm)` 的真實輸出（而非手寫字面 URI ——
        `to_file_uri` 對純 POSIX 絕對路徑的斜線數是它自己的既有行為，不是本 task 的
        契約，手寫字面值會誤測到與本 task 無關的既有行為）。

        含 WSL+path_mappings 的映射命名空間案例（第三案）——這正是 T3 review nit：
        唯讀來源常掛在映射過的 NAS 路徑，round-trip 若在映射分支破掉，_produce_one
        會用映射後 URI upsert、卻與 get_by_path(canonical) 讀的 row 錯位。映射分支只在
        CURRENT_ENV=='wsl' 且 path_mappings 非空時啟用，故需 monkeypatch。"""
        from core import path_utils
        from core.path_utils import to_file_uri, uri_to_local_fs_path

        # (fs_path, path_mappings, wsl_env) — wsl_env 才啟用 to_file_uri 映射分支
        cases = [
            ("/tmp/ro_src/ABC-001.mp4", {}, False),
            (r"\\NAS\share\ABC-001.mp4", {}, False),
            ("/home/user/nas/dir/ABC-001.mp4", _WSL_UNC_MAPPINGS, True),
        ]
        for fs_path, pm, wsl_env in cases:
            monkeypatch.setattr(path_utils, "CURRENT_ENV", "wsl" if wsl_env else path_utils.CURRENT_ENV)
            canonical = to_file_uri(fs_path, pm)
            if wsl_env:
                # 映射確有生效（canonical 落映射命名空間，非原生本機路徑）
                assert canonical.startswith("file://///NAS/share/"), canonical
            round_tripped_fs = uri_to_local_fs_path(canonical, pm)
            assert to_file_uri(round_tripped_fs, pm) == canonical, (
                f"round-trip 不變式破了: fs_path={fs_path!r} pm={pm!r} canonical={canonical!r} -> "
                f"{round_tripped_fs!r} -> {to_file_uri(round_tripped_fs, pm)!r}"
            )


# ── AC3 (feature/105 Bug 2): 非唯讀 refresh_full 重刮回空 → 保留既有原文標題 ─────

class TestEnrichSinglePreservesOriginalTitle:
    """AC3 (feature/105 T3, Bug 2): a non-readonly `refresh_full` re-scrape whose
    source returned an EMPTY original_title must NOT clobber the existing value —
    BOTH the written NFO <originaltitle> AND the DB row must preserve it.

    Drives the REAL enrich_single with a REAL VideoRepository(temp db) + REAL
    generate_nfo (only search_jav is mocked). Before the fix, both were cleared to
    '' (the injection line `meta['original_title'] = effective_original_title(...)`
    is the load-bearing preserve — remove it and this test goes RED)."""

    def _scraper_data_without_original_title(self, number="TEST-001"):
        # 重刮這次來源未回傳 original_title（key 缺 → _scraper_to_meta 落 ''）
        return {
            "number": number,
            "title": "新しいタイトル",
            "actors": ["女優A"],
            "cover": "",
            "date": "2024-01-01",
            "maker": "SOD",
            "director": "監督",
            "series": "シリーズ",
            "label": "LABEL",
            "tags": ["タグ"],
            "sample_images": [],
            "duration": 120,
            "url": "https://www.javbus.com/TEST-001",
        }

    def test_refresh_full_empty_rescrape_preserves_original_title_in_nfo_and_db(
        self, tmp_path, mocker
    ):
        import xml.etree.ElementTree as ET
        from core.database import init_db, VideoRepository, Video
        from core.enricher import enrich_single
        from core.path_utils import to_file_uri

        db_path = tmp_path / "ac3.db"
        init_db(db_path)
        repo = VideoRepository(db_path)

        video_file = tmp_path / "TEST-001.mp4"
        video_file.write_bytes(b"\x00")
        path_uri = to_file_uri(str(video_file))

        # 既有 DB row 帶非空 original_title（對應 NFO 也將被寫）
        repo.upsert(Video(
            path=path_uri, number="TEST-001", title="既存タイトル",
            original_title="既存の原題",
        ))

        # enrich_single 內部 new VideoRepository() → 指向同一 temp DB
        mocker.patch("core.enricher.VideoRepository", return_value=repo)
        mocker.patch(
            "core.enricher.search_jav",
            return_value=self._scraper_data_without_original_title(),
        )

        result = enrich_single(
            file_path=path_uri, number="TEST-001", mode="refresh_full",
            write_nfo=True, write_cover=False, write_extrafanart=False,
        )
        assert result.success, result.error

        # DB row 保留既有原文標題
        assert repo.get_by_path(path_uri).original_title == "既存の原題"

        # 寫出的 NFO <originaltitle> 保留既有原文標題（改前皆清成 ''）
        nfo_file = video_file.with_suffix(".nfo")
        assert nfo_file.exists(), "NFO 應被寫出"
        root = ET.parse(nfo_file).getroot()
        assert root.findtext("originaltitle") == "既存の原題"
