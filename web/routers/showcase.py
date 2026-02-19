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

from core.database import VideoRepository, get_db_path, init_db
from core.path_utils import normalize_path, to_file_uri, is_path_under_dir, uri_to_fs_path
from core.logger import get_logger
from web.routers.config import load_config

logger = get_logger(__name__)

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

        init_db(db_path)  # 確保 schema 存在（防止半毀損 DB）
        repo = VideoRepository(db_path)

        # 只取「當前設定資料夾」底下的記錄（DB 保留全部當 cache）
        config = load_config()
        gallery_config = config.get('gallery', {})
        directories = gallery_config.get('directories', [])
        path_mappings = gallery_config.get('path_mappings', {})

        configured_dir_uris = set()
        for d in directories:
            try:
                configured_dir_uris.add(to_file_uri(normalize_path(d), path_mappings))
            except ValueError:
                continue

        all_videos = [v for v in repo.get_all()
                      if any(is_path_under_dir(v.path, uri) for uri in configured_dir_uris)]

        # 轉換為前端格式
        videos_json = []
        for v in all_videos:
            # cover_path 轉換：file:///C:/path/to/cover.jpg → /api/gallery/image?path=C:/path/to/cover.jpg
            cover_url = ""
            if v.cover_path:
                local_path = uri_to_fs_path(v.cover_path)
                cover_url = f"/api/gallery/image?path={quote(local_path, safe='')}"

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
        logger.error("取得影片資料失敗: %s", e)
        return JSONResponse({
            "success": False,
            "error": "取得影片資料失敗",
            "videos": [],
            "total": 0
        }, status_code=500)
