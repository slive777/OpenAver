"""
Showcase API 路由 - 影片展示資料端點

端點：
- GET /api/showcase/videos        — 取得所有影片資料（供 Showcase 頁面客戶端渲染）
- GET /api/showcase/video?path=   — 取得單筆影片資料（供 T3 enrich 後刷新卡片）
"""

from urllib.parse import quote

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from core.database import VideoRepository, get_db_path, init_db
from core.path_utils import to_file_uri, is_path_under_dir, uri_to_fs_path
from core.logger import get_logger
from core.config import load_config

logger = get_logger(__name__)

router = APIRouter(prefix="/api/showcase", tags=["showcase"])


def _serialize_video(v, path_mappings: dict) -> dict:
    """將 Video ORM 物件序列化為前端 JSON dict（列表端點與單筆端點共用）"""
    cover_url = ""
    if v.cover_path:
        local_path = uri_to_fs_path(v.cover_path)
        cover_url = f"/api/gallery/image?path={quote(local_path, safe='')}"

    sample_urls = []
    for img_uri in (v.sample_images or []):
        local_path = uri_to_fs_path(img_uri)
        sample_urls.append(f"/api/gallery/image?path={quote(local_path, safe='')}")

    return {
        "path": v.path,                                          # file:/// URI（開啟影片用）
        "title": v.title,
        "original_title": v.original_title,
        "actresses": ','.join(v.actresses) if v.actresses else '',  # 逗號分隔字串
        "number": v.number or '',
        "maker": v.maker,
        "release_date": v.release_date,
        "tags": ','.join(v.tags) if v.tags else '',              # 逗號分隔字串
        "size": v.size_bytes,
        "cover_url": cover_url,                                  # /api/gallery/image?path=...
        "mtime": int(v.mtime) if v.mtime else 0,                 # Unix timestamp 整數
        "director": v.director or '',
        "duration": v.duration,                                  # Optional[int]，None 時前端 x-show 隱藏
        "series": v.series or '',
        "label": v.label or '',
        "sample_images": sample_urls,
        "user_tags": v.user_tags or [],              # list[str]，空時回空 list
        "has_cover": bool(v.cover_path),             # DB 初判（不做 IO）
        "has_nfo": (v.nfo_mtime or 0) > 0,          # 對齊 41a nfo_mtime 寫入契約，防禦 NULL
    }


def _get_configured_dirs(config: dict) -> tuple[set, dict]:
    """從 config 取出 configured_dir_uris 與 path_mappings（列表與單筆端點共用）"""
    gallery_config = config.get('gallery', {})
    directories = gallery_config.get('directories', [])
    path_mappings = gallery_config.get('path_mappings', {})

    configured_dir_uris: set = set()
    for d in directories:
        try:
            configured_dir_uris.add(to_file_uri(d, path_mappings))
        except ValueError:
            continue

    return configured_dir_uris, path_mappings


@router.get("/videos")
async def get_videos():
    """取得所有影片資料（用於 Showcase 頁面客戶端渲染）"""
    try:
        db_path = get_db_path()

        # 空庫情境：資料庫檔案不存在
        if not db_path.exists():
            return JSONResponse({
                "success": True,
                "videos": [],
                "total": 0
            })

        init_db(db_path)  # 確保 schema 存在（防止半毀損 DB）
        repo = VideoRepository(db_path)

        # 只取「當前設定資料夾」底下的記錄（DB 保留全部當 cache）
        config = load_config()
        configured_dir_uris, path_mappings = _get_configured_dirs(config)

        all_videos = [v for v in repo.get_all()
                      if any(is_path_under_dir(v.path, uri) for uri in configured_dir_uris)]

        videos_json = [_serialize_video(v, path_mappings) for v in all_videos]

        return JSONResponse({
            "success": True,
            "videos": videos_json,
            "total": len(videos_json)
        })

    except Exception as e:
        logger.error("取得影片資料失敗: %s", e)
        return JSONResponse({
            "success": False,
            "error": "取得影片資料失敗",
            "videos": [],
            "total": 0
        }, status_code=500)


@router.get("/video")
async def get_video(path: str = Query(..., description="file:/// URI")):
    """取得單筆影片資料（用於 T3 refreshVideoData enrich 後刷新卡片）"""
    try:
        db_path = get_db_path()
        if not db_path.exists():
            return JSONResponse({"success": False, "error": "video not found"}, status_code=404)

        init_db(db_path)
        repo = VideoRepository(db_path)

        config = load_config()
        configured_dir_uris, path_mappings = _get_configured_dirs(config)

        if not any(is_path_under_dir(path, uri) for uri in configured_dir_uris):
            return JSONResponse({"success": False, "error": "video not found"}, status_code=404)

        v = repo.get_by_path(path)
        if v is None:
            return JSONResponse({"success": False, "error": "video not found"}, status_code=404)

        return JSONResponse({"success": True, "video": _serialize_video(v, path_mappings)})

    except Exception as e:
        logger.error("取得單筆影片失敗: %s", e)
        return JSONResponse({"success": False, "error": "取得影片資料失敗"}, status_code=500)
