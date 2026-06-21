"""
OpenAver Web GUI - FastAPI Application
"""
from contextlib import asynccontextmanager
from pathlib import Path
import re

# issue #66：全域保險，涵蓋 /static 以外的裸 FileResponse 也用 WHATWG canonical MIME。
import mimetypes
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("text/css", ".css")

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from web.static_cache import NoCacheStaticFiles
from fastapi.templating import Jinja2Templates

# 版本號（從 core/version.py 統一管理）
from core.version import VERSION

# 確保 logging 在非 standalone 模式（uvicorn 直接啟動）也有初始化
from core.logger import setup_logging, get_logger
setup_logging()

logger = get_logger(__name__)

from core.config import load_config
from core.database import init_db
from core.metatube.state import metatube_state as _mt_startup_state


# 路徑設定
BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── startup ───────────────────────────────────────────────
    # init_db() 必須在任何 request 前執行：執行 DROP COLUMN migration（v0.8.7：
    # 移除 legacy clip_embedding / clip_model_id），確保 Video.from_row cls(**data)
    # 不會因 legacy schema 欄位收到未知 keyword 而 500。CD-57b-8 contract。
    init_db()

    # TASK-63e-1: auto-reconnect metatube from persisted config.
    # Wrapped in try-except so any unexpected failure cannot crash startup.
    try:
        import asyncio as _asyncio
        _config = load_config()
        _loop = _asyncio.get_event_loop()
        _res = await _loop.run_in_executor(None, lambda: startup_reconnect(_config))
        if _res:
            # Use the generation returned by startup_reconnect (captured under
            # state's lock at connect time) — never re-read state.generation
            # after the await/executor boundary (CD-66b-2). base_url/token are
            # still read from state; a concurrent connect that advanced the
            # generation makes this probe's writes stale, which the
            # mark_available/failed generation guard drops harmlessly.
            _names, _gen = _res
            _fire_probe(_mt_startup_state.base_url, _mt_startup_state.token, _names, _gen)
    except Exception:
        logger.warning("lifespan: startup_reconnect failed unexpectedly", exc_info=True)

    yield
    # ── shutdown ──────────────────────────────────────────────
    # 目前無 shutdown 邏輯（setup_logging 是 module-level，不需 teardown）


# FastAPI 應用
app = FastAPI(
    title="OpenAver",
    description="JAV 影片元數據管理工具",
    version=VERSION,
    lifespan=lifespan,
)

# 靜態檔案
app.mount("/static", NoCacheStaticFiles(directory=STATIC_DIR), name="static")

# 模板引擎
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# ============ 註冊 API 路由 ============
from web.routers import search as search_router
from web.routers import config as config_router
from web.routers import scraper as scraper_router
from web.routers import translate as translate_router
from web.routers import scanner as scanner_router
from web.routers import gemini as gemini_router
from web.routers import openai_translate as openai_translate_router
from web.routers import filename as filename_router
from web.routers import showcase as showcase_router
from web.routers import motion_lab as motion_lab_router
from web.routers import capabilities as capabilities_router
from web.routers import collection as collection_router
from web.routers import actress as actress_router
from web.routers import actress_alias as actress_alias_router
from web.routers import tag_alias as tag_alias_router
from web.routers import tags as tags_router
from web.routers import notifications as notifications_router
from web.routers import similar as similar_router
from web.routers import settings_link as settings_link_router
from web.routers import scraper_sources as scraper_sources_router
from web.routers import settings_metatube as settings_metatube_router
from web.routers import cf as cf_router
from web.routers import diagnostics as diagnostics_router
# Module-level imports for startup_reconnect / _fire_probe so that
# patch("web.app.startup_reconnect") / patch("web.app._fire_probe") target the
# correct use-site binding (TASK-63e-1; function-local import would defeat patch).
from web.routers.settings_metatube import startup_reconnect, _fire_probe  # noqa: E402
app.include_router(search_router.router)
app.include_router(config_router.router)
app.include_router(scraper_router.router)
app.include_router(translate_router.router)
app.include_router(scanner_router.router)
app.include_router(gemini_router.router)
app.include_router(openai_translate_router.router)
app.include_router(filename_router.router)
app.include_router(showcase_router.router)
app.include_router(motion_lab_router.router)
app.include_router(capabilities_router.router)
app.include_router(collection_router.router)
app.include_router(collection_router.user_tags_router)
app.include_router(actress_router.router)
app.include_router(actress_alias_router.router)
app.include_router(tag_alias_router.router)
app.include_router(tags_router.router)
app.include_router(notifications_router.router)
app.include_router(similar_router.router)
app.include_router(settings_link_router.router)
app.include_router(scraper_sources_router.router)
app.include_router(settings_metatube_router.router)
app.include_router(cf_router.router)
app.include_router(diagnostics_router.router)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"error": "validation_error", "message": "請求格式錯誤，缺少必要欄位"}
    )


# ============ LAN 存取閘門 ============

# loopback 主機集合 —— 單一真理，middleware 短路與決策核心共用（避免兩處定義漂移）。
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1"})


def _lan_access_allowed(client_host, server_mode):
    """LAN access gate decision-core (testable, no I/O)。

    這是 middleware 實際委派的決策函式（非平行複製）——middleware 在非 loopback
    分支呼叫本函式，loopback 短路同樣比對 `_LOOPBACK_HOSTS`，故測得即所跑。
    """
    if client_host in _LOOPBACK_HOSTS:
        return True
    return bool(server_mode)


@app.middleware("http")
async def lan_access_gate(request: Request, call_next):
    """
    非 loopback 流量依 general.server_mode 決定放行或 403。
    Loopback 短路：不讀 config，零成本（與 _lan_access_allowed 共用 _LOOPBACK_HOSTS）。
    不信任 X-Forwarded-For（無反向 proxy；只用 TCP 對端 request.client.host）。
    """
    client = request.client
    client_host = client.host if client else None
    # loopback 短路：桌面 App 自連，零 config I/O
    if client_host in _LOOPBACK_HOSTS:
        return await call_next(request)
    # 非 loopback：讀 config 後委派決策核心（測得即所跑）
    server_mode = load_config().get("general", {}).get("server_mode", False)
    if _lan_access_allowed(client_host, server_mode):
        return await call_next(request)
    return PlainTextResponse("Forbidden", status_code=403)


# ============ 輔助函數 ============


from web.lan_listener import get_lan_ip  # noqa: E402 — re-export for backward compat


def get_common_context(request: Request) -> dict:
    """取得共用的模板 Context (包含設定)"""
    from core.config import load_config, mutate_config
    from core.i18n import t as _t, get_merged_translations, detect_locale_from_accept_language
    config = load_config()

    # Font size mapping
    FONT_SIZE_MAP = {"xs": 13, "sm": 14, "md": 16, "lg": 18, "xl": 20}
    font_size = config.get('general', {}).get('font_size', 'md')
    font_size_px = FONT_SIZE_MAP.get(font_size, 16)

    # i18n: 取得 locale，首次偵測時從 Accept-Language 推斷並寫入 config
    locale = config.get('general', {}).get('locale') or ''
    if not locale:
        locale = detect_locale_from_accept_language(
            request.headers.get('accept-language', '')
        )
        # 首次偵測：寫入 config 避免每次 request 重新偵測
        try:
            if 'general' not in config:
                config['general'] = {}
            config['general']['locale'] = locale  # 本地副本供 template context 用
            # 66b（Codex P2）：get_common_context 跑在 event loop thread，舊裸 RMW
            # （load_config→mutate→save_config）跨兩次 lock，會與 threadpool 上的
            # config/metatube 寫入交錯 → lost-update。改 mutate_config 在單一
            # critical section 內「只設 locale」於 fresh-load 的 cfg，不蓋他人欄位。
            def _persist_locale(cfg):
                cfg.setdefault('general', {})['locale'] = locale
            mutate_config(_persist_locale)
        except Exception as e:
            logger.warning("[i18n] 首次偵測語系寫入 config 失敗: %s", e)

    merged_translations = get_merged_translations(locale)

    def _t_bound(key, **params):
        return _t(key, locale=locale, **params)

    # 63c-3：per-source routable / available 注入（CD-63c-9）。在 save_config 之後 mutate，
    # 確保 transient 欄位不被寫回 config.json。_advanced_search_bootstrap.html 做
    # config.sources|tojson → routable/available 自動帶出（不需逐欄改 template）。
    # builtin 永遠 routable+available；metatube 依 runtime 連線 + availability gate。
    from core.metatube.state import metatube_state as _mt_state
    _avail_map = _mt_state.availability_map()
    _mt_connected = _mt_state.is_connected
    for _src in (config.get('sources') or []):
        if not isinstance(_src, dict):
            continue
        _sid = _src.get('id', '')
        if isinstance(_sid, str) and _sid.startswith('metatube:'):
            _src['routable'] = _mt_connected
            _src['available'] = _avail_map.get(_sid, False)
        else:
            _src['routable'] = True
            _src['available'] = True
    # 63c-3 / 63c-6：proxy 是否已設定（DMM requires_proxy 灰化 Surface 2 用，獨立 context key）
    _proxy_url = (config.get('search') or {}).get('proxy_url') or ''
    proxy_configured = len(_proxy_url) > 0

    # 70-T5：cf_transport_available — standalone 已 register → true；dev/server → false
    from core.cf_transport import get_cf_transport as _get_cf_transport
    _cf_transport_available = _get_cf_transport() is not None

    _server_mode = bool(config.get('general', {}).get('server_mode', False))

    return {
        "request": request,
        "config": config,
        "proxy_configured": proxy_configured,
        "cf_transport_available": _cf_transport_available,
        "lan_ip": get_lan_ip() if _server_mode else None,
        "theme": config.get('general', {}).get('theme', 'light'),
        "sidebar_collapsed": config.get('general', {}).get('sidebar_collapsed', False),
        "font_size": font_size,
        "font_size_px": font_size_px,
        "version": VERSION,
        "locale": locale,
        "merged_translations": merged_translations,
        "t": _t_bound,
    }


# ============ 頁面路由 ============

@app.get("/")
async def index(request: Request):
    """首頁 - 重定向到預設頁面"""
    from core.config import load_config
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
    return templates.TemplateResponse(request, "search.html", context)


@app.get("/scraper")
async def scraper_page(request: Request):
    """刮削器頁面"""
    context = get_common_context(request)
    context["page"] = "scraper"
    return templates.TemplateResponse(request, "scraper.html", context)


@app.get("/updater")
async def updater_page(request: Request):
    """更新器頁面"""
    context = get_common_context(request)
    context["page"] = "updater"
    return templates.TemplateResponse(request, "updater.html", context)


@app.get("/scanner")
async def scanner_page(request: Request):
    """Scanner 頁面"""
    context = get_common_context(request)
    context["page"] = "scanner"
    return templates.TemplateResponse(request, "scanner.html", context)


@app.get("/gallery")
async def gallery_redirect():
    """Legacy redirect: /gallery → /scanner"""
    return RedirectResponse(url="/scanner", status_code=302)


@app.get("/showcase")
async def showcase_page(request: Request):
    """Showcase 頁面"""
    context = get_common_context(request)
    context["page"] = "showcase"
    return templates.TemplateResponse(request, "showcase.html", context)


@app.get("/settings")
async def settings_page(request: Request):
    """設定頁面"""
    context = get_common_context(request)
    context["page"] = "settings"
    return templates.TemplateResponse(request, "settings.html", context)


@app.get("/help")
async def help_page(request: Request):
    """使用說明頁面"""
    context = get_common_context(request)
    context["page"] = "help"
    context["base_url"] = str(request.base_url).rstrip("/")
    return templates.TemplateResponse(request, "help.html", context)


@app.get("/design-system")
async def design_system_page(request: Request):
    """設計系統展示頁面"""
    context = get_common_context(request)
    context["page"] = "design-system"
    return templates.TemplateResponse(request, "design-system.html", context)


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
    import asyncio
    import httpx

    current_version = VERSION
    github_api = "https://api.github.com/repos/slive777/OpenAver/releases/latest"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await asyncio.wait_for(
                client.get(github_api, headers={"Accept": "application/vnd.github.v3+json"}),
                timeout=5.0,
            )

            if resp.status_code == 404:
                # 還沒有 release
                return {"success": True, "has_update": False, "current_version": current_version}

            resp.raise_for_status()
            data = resp.json()

            latest_version = data.get("tag_name", "").lstrip("v")
            download_url = data.get("html_url", "")

            # 語意版本比較（tuple 比較避免 "0.10.0" < "0.9.0" 問題）
            def _parse_ver(v):
                # Strip prerelease/build suffixes: "0.10.0-rc1" → "0.10.0"
                m = re.match(r'(\d+(?:\.\d+)*)', v)
                if not m:
                    raise ValueError(f"Cannot parse version: {v}")
                return tuple(int(x) for x in m.group(1).split('.'))
            try:
                has_update = _parse_ver(latest_version) > _parse_ver(current_version)
            except (ValueError, AttributeError):
                has_update = False

            return {
                "success": True,
                "has_update": has_update,
                "current_version": current_version,
                "latest_version": latest_version,
                "download_url": download_url
            }
    except (httpx.TimeoutException, TimeoutError):
        return {"success": False, "error": "連線逾時"}
    except Exception as e:
        logger.error("檢查更新失敗: %s", e)
        return {"success": False, "error": "檢查更新失敗"}
