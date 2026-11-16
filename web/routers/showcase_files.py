"""Showcase files router — GET /api/showcase/video/files（TASK-200b-T5）。

讀取端點：影片檔現場狀態。**純讀，零寫入。**

POST /api/showcase/video/poster-regenerate・/reprobe：
寫入端點。追加於讀取端點之後，讀取端點既有碼不動。
"""
from __future__ import annotations

import stat
from typing import NamedTuple

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core import media_probe
from core.config import get_configured_gallery_dirs, load_config
from core.config import STEM_IMAGE_MODES, normalize_external_manager
from core.database import VideoRepository, get_db_path, init_db
from core.logger import get_logger
from core.media_probe_force import probe_now
from core.path_utils import is_path_under_dir
from core.path_utils import uri_to_local_fs_path
from core.poster_refresh import refresh_poster
from core.readonly_paths import resolve_owning_output_root
from core.source_reachability import is_path_on_unreachable_source
from core.video_files_info import build_files_info, stat_kind
from core.video_files_info import poster_regen_verdict, summarize_media
from web.routers.showcase import _focal_save_lock, cover_outside_readonly_output_root  # noqa: PLC2701 — 卡片指定的同一把 save-focal 互斥鎖

logger = get_logger(__name__)

router = APIRouter(prefix="/api/showcase", tags=["showcase"])


class ScopeCtx(NamedTuple):
    repo: object
    row: object
    config: dict
    path_mappings: dict


def _resolve_scope(path: str):
    """DB 存在、get_by_path 有列、列在收藏範圍內；成功回 (ctx, None)，失敗回 (None, JSONResponse)。"""
    db_path = get_db_path()
    if stat_kind(str(db_path))[0] != "ok":
        return None, JSONResponse(
            {"success": False, "error": "找不到影片"}, status_code=404,
        )
    init_db(db_path)
    repo = VideoRepository(db_path)
    row = repo.get_by_path(path)
    if row is None:
        return None, JSONResponse(
            {"success": False, "error": "找不到影片"}, status_code=404,
        )
    config = load_config()
    configured_dir_uris, path_mappings = get_configured_gallery_dirs(config)
    if not any(is_path_under_dir(row.path, uri) for uri in configured_dir_uris):
        return None, JSONResponse(
            {"success": False, "error": "此影片不在收藏範圍"}, status_code=403,
        )
    return ScopeCtx(repo=repo, row=row, config=config, path_mappings=path_mappings), None


@router.get("/video/files")
def get_video_files(path: str = Query(...)):
    """燈箱進階編輯：這部片的檔案現在長怎樣（純讀）。"""
    try:
        ctx, err = _resolve_scope(path)
        if err is not None:
            return err
        return {"success": True, **build_files_info(
            ctx.row, repo=ctx.repo, config=ctx.config,
            path_mappings=ctx.path_mappings,
        )}
    except ValueError:
        return JSONResponse(
            {"success": False, "error": "檔案路徑格式無效"}, status_code=400,
        )
    except Exception as e:
        logger.error("[files] 未預期錯誤: %s", e)
        return JSONResponse(
            {"success": False, "error": "讀取檔案資訊失敗"}, status_code=500,
        )


class VideoPathRequest(BaseModel):
    """POST /video/poster-regenerate・/reprobe body：path（DB key）。"""

    path: str


def _refresh_poster_status(cover_fs, row, external_mode_on):
    """呼叫 refresh_poster；例外或「none」一律轉 failed（不讓 none 漏到前端）。"""
    try:
        result = refresh_poster(cover_fs, row.auto_focal, external_mode_on=external_mode_on, crop_mode=row.crop_mode, create_if_missing=True)
    except Exception:
        logger.warning("[poster-regenerate] 海報重產失敗", exc_info=True)
        return "failed"
    if result.status == "none":
        return "failed"
    return result.status


def _locked_regen_status(repo, path, config, path_mappings, external_mode_on):
    """鎖內：重讀列，決定與執行都用這一份；回 (ok_body, None) 或 (None, err_body)。"""
    row = repo.get_by_path(path)
    if row is None:
        return None, JSONResponse(
            {"success": False, "error": "找不到影片"}, status_code=404,
        )
    try:
        cover_fs = uri_to_local_fs_path(row.cover_path, path_mappings) if row.cover_path else ""
    except ValueError:
        cover_fs = ""
    kind, cover_st = stat_kind(cover_fs) if cover_fs else ("absent", None)
    has_cover_file = kind == "ok" and stat.S_ISREG(cover_st.st_mode)
    try:
        video_fs = uri_to_local_fs_path(row.path, path_mappings)
    except ValueError:
        video_fs = ""
    ro_owner = resolve_owning_output_root(row.path, config)
    readonly = ro_owner is not None
    _can_regen, blocked = poster_regen_verdict(
        external_mode_on=external_mode_on, has_cover_file=has_cover_file,
        cover_fs=cover_fs, video_fs=video_fs, readonly=readonly,
    )
    if blocked is not None:
        return None, {"success": False, "error": blocked}
    if cover_outside_readonly_output_root(ro_owner, row.cover_path):
        return None, {"success": False, "error": "readonly_output_not_current"}
    return {
        "success": True,
        "poster": {"status": _refresh_poster_status(cover_fs, row, external_mode_on)},
    }, None


@router.post("/video/poster-regenerate")
def regenerate_video_poster(req: VideoPathRequest):
    """沒有海報檔也能由封面新產一張（位置照目前的手動／自動焦點）。"""
    try:
        ctx, err = _resolve_scope(req.path)
        if err is not None:
            return err
        if is_path_on_unreachable_source(ctx.row.path, ctx.config.get("gallery", {})):
            return {"success": False, "error": "unreachable"}
        external_mode_on = normalize_external_manager(
            (ctx.config.get("scraper") or {}).get("external_manager", "off"),
        ) in STEM_IMAGE_MODES
        if not external_mode_on:
            return {"success": True, "poster": {"status": "skipped"}}
        with _focal_save_lock:
            body, err_body = _locked_regen_status(
                ctx.repo, req.path, ctx.config, ctx.path_mappings, external_mode_on,
            )
            return err_body if body is None else body
    except Exception as e:
        logger.error("[poster-regenerate] 未預期錯誤: %s", e)
        return JSONResponse(
            {"success": False, "error": "重新產生海報失敗"}, status_code=500,
        )


@router.post("/video/reprobe")
def reprobe_video(req: VideoPathRequest):
    """同步重讀這一個影片檔的影片資訊並回報這一次的結果。"""
    try:
        ctx, err = _resolve_scope(req.path)
        if err is not None:
            return err
        if is_path_on_unreachable_source(ctx.row.path, ctx.config.get("gallery", {})):
            return {"success": False, "error": "unreachable"}
        readonly = resolve_owning_output_root(ctx.row.path, ctx.config) is not None
        view = ctx.repo.get_media_probe_view(ctx.row.path)
        if view is None:
            return JSONResponse(
                {"success": False, "error": "找不到影片"}, status_code=404,
            )
        if not media_probe.is_available():
            return {
                "success": True, "status": "unavailable", "readonly": readonly,
                "media": summarize_media(view),
            }
        try:
            fs_path = uri_to_local_fs_path(ctx.row.path, ctx.path_mappings)
        except ValueError:
            fs_path = ""
        status = (
            probe_now(ctx.repo, ctx.row.path, fs_path, view.mtime, view.size_bytes)
            if fs_path else "unreadable"
        )
        return {
            "success": True, "status": status, "readonly": readonly,
            "media": summarize_media(ctx.repo.get_media_probe_view(ctx.row.path)),
        }
    except Exception as e:
        logger.exception("[reprobe] 未預期錯誤: %s", e)
        return JSONResponse(
            {"success": False, "error": "重新讀取影片資訊失敗"}, status_code=500,
        )


class RepathRequest(BaseModel):
    path: str
    new_path: str
    confirm_name_change: bool = False


@router.post('/video/repath')
def repath_endpoint(request: RepathRequest):
    from core.video_repath import repath_video

    ctx, err = _resolve_scope(request.path)
    if err is not None:
        return err
    return repath_video(ctx.repo, ctx.row, request.new_path, request.confirm_name_change,
                        ctx.config, ctx.path_mappings)
