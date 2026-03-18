"""
Motion Lab router — 動畫沙盒頁
與 /design-system 相同，直接公開（開源專案不需 debug guard）
"""

from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core.database import VideoRepository, get_db_path, init_db
from core.path_utils import uri_to_fs_path
from core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="", tags=["motion-lab"])


@router.get("/motion-lab")
async def motion_lab_page(request: Request):
    """Motion Lab 沙盒頁（HTML）"""
    # 延遲 import，避免循環依賴
    from web.app import get_common_context, templates
    context = get_common_context(request)
    context["page"] = "motion-lab"
    return templates.TemplateResponse("motion_lab.html", context)


@router.get("/api/motion-lab/data")
async def motion_lab_data():
    """取得前 30 筆影片資料（用於 Motion Lab 沙盒頁）"""
    try:
        db_path = get_db_path()

        # DB 不存在 → 空結果（不拋例外）
        if not db_path.exists():
            return JSONResponse({
                "success": True,
                "videos": [],
                "total": 0
            })

        init_db(db_path)  # 確保 schema 存在
        repo = VideoRepository(db_path)

        # 取全部後 Python slice（30 筆資料量小，效能可接受）
        all_videos = repo.get_all()
        videos_30 = all_videos[:30]

        # 轉換為前端格式
        videos_json = []
        for v in videos_30:
            # cover_path 轉換：file:///C:/path/to/cover.jpg → /api/gallery/image?path=C:/path/to/cover.jpg
            cover_url = ""
            if v.cover_path:
                local_path = uri_to_fs_path(v.cover_path)
                cover_url = f"/api/gallery/image?path={quote(local_path, safe='')}"

            videos_json.append({
                "path": v.path,
                "title": v.title,
                "number": v.number or "",
                "actresses": v.actresses if v.actresses else [],
                "maker": v.maker,
                "release_date": v.release_date,
                "cover_url": cover_url,
                "tags": v.tags if v.tags else [],
            })

        return JSONResponse({
            "success": True,
            "videos": videos_json,
            "total": len(videos_json)
        })

    except Exception as e:
        logger.error("取得 motion-lab 資料失敗: %s", e)
        return JSONResponse({
            "success": False,
            "error": "取得資料失敗",
            "videos": [],
            "total": 0
        }, status_code=500)
