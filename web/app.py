"""
JavHelper Web GUI - FastAPI Application
"""
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# 路徑設定
BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# FastAPI 應用
app = FastAPI(
    title="JavHelper",
    description="JAV 影片元數據管理工具",
    version="0.1.0"
)

# 靜態檔案
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# 模板引擎
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# ============ 註冊 API 路由 ============
from web.routers import search as search_router
app.include_router(search_router.router)


# ============ 頁面路由 ============

@app.get("/")
async def index(request: Request):
    """首頁 - 重定向到搜尋頁面"""
    return templates.TemplateResponse("search.html", {
        "request": request,
        "page": "search"
    })


@app.get("/search")
async def search_page(request: Request):
    """搜尋頁面"""
    return templates.TemplateResponse("search.html", {
        "request": request,
        "page": "search"
    })


@app.get("/scraper")
async def scraper_page(request: Request):
    """刮削器頁面"""
    return templates.TemplateResponse("scraper.html", {
        "request": request,
        "page": "scraper"
    })


@app.get("/updater")
async def updater_page(request: Request):
    """更新器頁面"""
    return templates.TemplateResponse("updater.html", {
        "request": request,
        "page": "updater"
    })


@app.get("/avlist")
async def avlist_page(request: Request):
    """列表生成頁面"""
    return templates.TemplateResponse("avlist.html", {
        "request": request,
        "page": "avlist"
    })


@app.get("/settings")
async def settings_page(request: Request):
    """設定頁面"""
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "page": "settings"
    })


# ============ API 路由（稍後移到 routers/）============

@app.get("/api/health")
async def health_check():
    """健康檢查"""
    return {"status": "ok", "version": "0.1.0"}
