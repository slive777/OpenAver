"""Showcase files router — GET /api/showcase/video/files（TASK-200b-T5）。

讀取端點：影片檔現場狀態。**純讀，零寫入。**
"""
from __future__ import annotations

from typing import NamedTuple

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from core.config import get_configured_gallery_dirs, load_config
from core.database import VideoRepository, get_db_path, init_db
from core.logger import get_logger
from core.path_utils import is_path_under_dir
from core.video_files_info import build_files_info, stat_kind

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
