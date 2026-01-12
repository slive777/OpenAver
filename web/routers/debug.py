"""
Debug 路由 - 開發測試用 API
"""

from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from core.actress_scraper import scrape_actress_profile
from core.search_gallery_service import SearchGalleryService


# Router 設定
router = APIRouter(prefix="/api/debug", tags=["debug"])

# 模板（需要在 app.py 中設定，這裡用相對路徑）
from pathlib import Path
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


# ============ Request/Response Models ============

class ScrapeActressRequest(BaseModel):
    name: str


class SearchGalleryRequest(BaseModel):
    query: str
    theme: str = "dark"


# ============ API Endpoints ============

@router.post("/scrape-actress")
async def scrape_actress_api(request: ScrapeActressRequest):
    """
    測試女優爬蟲
    
    Args:
        name: 女優名字
        
    Returns:
        女優資料或錯誤訊息
    """
    if not request.name or not request.name.strip():
        return {"success": False, "error": "請輸入女優名字"}
    
    try:
        result = scrape_actress_profile(request.name.strip())
        if result:
            return {"success": True, "data": result}
        else:
            return {"success": False, "error": f"找不到「{request.name}」的資料"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/search-gallery")
async def search_gallery_api(request: SearchGalleryRequest):
    """
    生成搜尋結果 Gallery
    
    Args:
        query: 搜尋關鍵字
        theme: 主題 (light/dark)
        
    Returns:
        Gallery HTML 的 URL
    """
    if not request.query or not request.query.strip():
        return {"success": False, "error": "請輸入搜尋關鍵字"}
    
    try:
        service = SearchGalleryService()
        html_path = service.generate_search_gallery(
            query=request.query.strip(),
            theme=request.theme
        )
        
        if html_path:
            # 回傳可以載入的 URL
            return {
                "success": True, 
                "url": f"/api/debug/gallery-view?path={html_path}"
            }
        else:
            return {"success": False, "error": f"搜尋「{request.query}」沒有結果"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/gallery-view")
async def gallery_view(path: str):
    """返回生成的 Gallery HTML"""
    from pathlib import Path
    file_path = Path(path)
    if file_path.exists() and file_path.suffix == '.html':
        return FileResponse(path, media_type="text/html")
    return {"error": "File not found"}


# ============ Debug Pages ============

# 頁面路由使用不同的 prefix
page_router = APIRouter(tags=["debug-pages"])


@page_router.get("/debug/actress", response_class=HTMLResponse)
async def actress_debug_page(request: Request):
    """女優爬蟲測試頁面"""
    return templates.TemplateResponse("debug_actress.html", {"request": request})

