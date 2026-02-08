"""
Showcase API 路由 - 影片展示資料端點
"""

import sys
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import JSONResponse

# 加入 core 模組路徑
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.database import VideoRepository, get_db_path

router = APIRouter(prefix="/api/showcase", tags=["showcase"])


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

        repo = VideoRepository(db_path)
        all_videos = repo.get_all()

        # 轉換為前端格式
        videos_json = []
        for v in all_videos:
            # cover_path 轉換：file:///C:/path/to/cover.jpg → /api/gallery/image?path=C:/path/to/cover.jpg
            cover_url = ""
            if v.cover_path:
                # 移除 file:/// 前綴
                clean_path = v.cover_path.replace('file:///', '')
                # URL encode 路徑
                cover_url = f"/api/gallery/image?path={quote(clean_path, safe='')}"

            videos_json.append({
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
                "mtime": int(v.mtime) if v.mtime else 0                  # Unix timestamp 整數
            })

        return JSONResponse({
            "success": True,
            "videos": videos_json,
            "total": len(videos_json)
        })

    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e),
            "videos": [],
            "total": 0
        }, status_code=500)
