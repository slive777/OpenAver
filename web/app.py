"""
OpenAver Web GUI - FastAPI Application
"""
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# 版本號（從 core/version.py 統一管理）
from core.version import VERSION

# 確保 logging 在非 standalone 模式（uvicorn 直接啟動）也有初始化
from core.logger import setup_logging
setup_logging()

# 路徑設定
BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# FastAPI 應用
app = FastAPI(
    title="OpenAver",
    description="JAV 影片元數據管理工具",
    version=VERSION
)

# 靜態檔案
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# 模板引擎
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# ============ 註冊 API 路由 ============
from web.routers import search as search_router
from web.routers import config as config_router
from web.routers import scraper as scraper_router
from web.routers import translate as translate_router
from web.routers import scanner as scanner_router
from web.routers import gemini as gemini_router
from web.routers import filename as filename_router
from web.routers import showcase as showcase_router
app.include_router(search_router.router)
app.include_router(config_router.router)
app.include_router(scraper_router.router)
app.include_router(translate_router.router)
app.include_router(scanner_router.router)
app.include_router(gemini_router.router)
app.include_router(filename_router.router)
app.include_router(showcase_router.router)


# ============ 輔助函數 ============

def get_common_context(request: Request) -> dict:
    """取得共用的模板 Context (包含設定)"""
    from web.routers.config import load_config
    config = load_config()

    # Font size mapping
    FONT_SIZE_MAP = {"xs": 13, "sm": 14, "md": 16, "lg": 18, "xl": 20}
    font_size = config.get('general', {}).get('font_size', 'md')
    font_size_px = FONT_SIZE_MAP.get(font_size, 16)

    return {
        "request": request,
        "config": config,
        "theme": config.get('general', {}).get('theme', 'light'),
        "sidebar_collapsed": config.get('general', {}).get('sidebar_collapsed', False),
        "font_size": font_size,
        "font_size_px": font_size_px,
        "version": VERSION
    }


# ============ 頁面路由 ============

@app.get("/")
async def index(request: Request):
    """首頁 - 重定向到預設頁面"""
    from web.routers.config import load_config
    config = load_config()
    default_page = config.get('general', {}).get('default_page', 'search')

    # 向後兼容：舊配置 "gallery" 映射到新路由 "/scanner"
    if default_page == 'gallery':
        default_page = 'scanner'

    # 驗證頁面名稱
    valid_pages = ['search', 'scanner', 'showcase']
    if default_page not in valid_pages:
        default_page = 'search'

    return RedirectResponse(url=f"/{default_page}", status_code=302)


@app.get("/search")
async def search_page(request: Request):
    """搜尋頁面"""
    context = get_common_context(request)
    context["page"] = "search"
    return templates.TemplateResponse("search.html", context)


@app.get("/scraper")
async def scraper_page(request: Request):
    """刮削器頁面"""
    context = get_common_context(request)
    context["page"] = "scraper"
    return templates.TemplateResponse("scraper.html", context)


@app.get("/updater")
async def updater_page(request: Request):
    """更新器頁面"""
    context = get_common_context(request)
    context["page"] = "updater"
    return templates.TemplateResponse("updater.html", context)


@app.get("/scanner")
async def scanner_page(request: Request):
    """Scanner 頁面"""
    context = get_common_context(request)
    context["page"] = "scanner"
    return templates.TemplateResponse("scanner.html", context)


@app.get("/gallery")
async def gallery_redirect():
    """Legacy redirect: /gallery → /scanner"""
    return RedirectResponse(url="/scanner", status_code=302)


@app.get("/showcase")
async def showcase_page(request: Request):
    """Showcase 頁面"""
    context = get_common_context(request)
    context["page"] = "showcase"
    return templates.TemplateResponse("showcase.html", context)


@app.get("/settings")
async def settings_page(request: Request):
    """設定頁面"""
    context = get_common_context(request)
    context["page"] = "settings"
    return templates.TemplateResponse("settings.html", context)


@app.get("/help")
async def help_page(request: Request):
    """使用說明頁面"""
    context = get_common_context(request)
    context["page"] = "help"
    return templates.TemplateResponse("help.html", context)


@app.get("/design-system")
async def design_system_page(request: Request):
    """設計系統展示頁面"""
    context = get_common_context(request)
    context["page"] = "design-system"
    return templates.TemplateResponse("design-system.html", context)


# ============ API 路由（稍後移到 routers/）============

@app.get("/api/health")
async def health_check():
    """健康檢查"""
    return {"status": "ok", "version": VERSION}


@app.get("/api/version")
async def get_version():
    """取得應用程式版本"""
    return {"success": True, "version": VERSION}


@app.get("/api/check-update")
async def check_update():
    """手動檢查 GitHub 是否有新版本（保護隱私，不自動連網）"""
    import httpx

    current_version = VERSION
    github_api = "https://api.github.com/repos/slive777/OpenAver/releases/latest"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(github_api, headers={"Accept": "application/vnd.github.v3+json"})

            if resp.status_code == 404:
                # 還沒有 release
                return {"success": True, "has_update": False, "current_version": current_version}

            resp.raise_for_status()
            data = resp.json()

            latest_version = data.get("tag_name", "").lstrip("v")
            download_url = data.get("html_url", "")

            # 簡單版本比較
            has_update = latest_version > current_version

            return {
                "success": True,
                "has_update": has_update,
                "current_version": current_version,
                "latest_version": latest_version,
                "download_url": download_url
            }
    except httpx.TimeoutException:
        return {"success": False, "error": "連線逾時"}
    except Exception as e:
        return {"success": False, "error": str(e)}
