"""
Scraper API 路由 - 單檔刮削
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import sys
from pathlib import Path

# 加入 core 模組路徑
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.organizer import organize_file
from core.scraper import search_jav
from core.logger import get_logger
from web.routers.config import load_config

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["scraper"])


class ScrapeRequest(BaseModel):
    file_path: str
    number: Optional[str] = None
    # 前端可直接傳入 metadata，避免重新搜尋
    metadata: Optional[dict] = None


class ScrapeResponse(BaseModel):
    success: bool
    error: Optional[str] = None
    original_path: Optional[str] = None
    new_folder: Optional[str] = None
    new_filename: Optional[str] = None
    cover_path: Optional[str] = None
    nfo_path: Optional[str] = None


@router.post("/scrape-single")
def scrape_single(request: ScrapeRequest) -> dict:
    """
    單檔刮削 API

    流程:
    1. 搜尋元數據
    2. 建立資料夾
    3. 重命名影片
    4. 下載封面
    5. 生成 NFO
    """
    file_path = request.file_path
    number = request.number

    # 如果沒有提供番號，嘗試從檔名提取
    if not number:
        from core.scraper import extract_number
        number = extract_number(file_path)

    if not number:
        return {
            "success": False,
            "error": "無法識別番號，請手動輸入"
        }

    # 優先使用前端傳來的 metadata
    if request.metadata:
        metadata = request.metadata
        metadata['number'] = number
    else:
        # 沒有 metadata 才重新搜尋
        metadata = search_jav(number)
        if not metadata:
            return {
                "success": False,
                "error": f"找不到 {number} 的資料"
            }
        metadata['number'] = number

    logger.debug(f"[scraper] cover URL: {metadata.get('cover', 'NO COVER')}")

    # 載入設定
    config = load_config()
    scraper_config = config.get('scraper', {})

    # 執行整理
    result = organize_file(file_path, metadata, scraper_config)

    return result
