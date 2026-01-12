"""
Debug 路由 - 開發測試用 API
"""

from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from core.actress_scraper import scrape_actress_profile


# Router 設定
router = APIRouter(prefix="/api/debug", tags=["debug"])

# 模板（需要在 app.py 中設定，這裡用相對路徑）
from pathlib import Path
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")


# ============ Request/Response Models ============

class ScrapeActressRequest(BaseModel):
    name: str


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


# ============ Debug Pages ============

# 頁面路由使用不同的 prefix
page_router = APIRouter(tags=["debug-pages"])


@page_router.get("/debug/actress", response_class=HTMLResponse)
async def actress_debug_page(request: Request):
    """女優爬蟲測試頁面"""
    return templates.TemplateResponse("debug_actress.html", {"request": request})
