"""
OpenAver Web GUI - FastAPI Application
"""
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse
import asyncio
import contextlib
import ipaddress
import os
import re
import subprocess
import sys

# issue #66：全域保險，涵蓋 /static 以外的裸 FileResponse 也用 WHATWG canonical MIME。
import mimetypes
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from web.static_cache import NoCacheStaticFiles
from starlette.middleware.gzip import GZipMiddleware
from web.compression import GZIP_COMPRESS_LEVEL, GZIP_EXCLUDED_CONTENT_TYPES
from web.auto_organize_scheduler import auto_organize_loop
from fastapi.templating import Jinja2Templates

# 版本號（從 core/version.py 統一管理）
from core.version import VERSION

# 確保 logging 在非 standalone 模式（uvicorn 直接啟動）也有初始化
from core.logger import setup_logging, get_logger
setup_logging()

logger = get_logger(__name__)

from core.config import load_config, mutate_config
from core.data_layout import bootstrap_data_layout, consume_pending_bootstrap_result, consume_reset_access_auth_marker
from core.focal import device_state
from core.database import init_db
from core.database import backfill_readonly_nfo_mtime
from core.metatube.state import metatube_state as _mt_startup_state
from core.access_auth import ensure_schema, load_snapshot, snapshot, verify_ticket
from core import source_reachability
from core.platform_info import is_synology


# 路徑設定
BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# lifespan bootstrap 失敗的固定 exit code（EX_CONFIG）；避開 uvicorn 常用的 1/2/3
LIFESPAN_BOOTSTRAP_EXIT_CODE = 78
_LIFESPAN_BOOTSTRAP_STDERR = (
    "OpenAver 啟動失敗：資料位置尚未就緒或已損毀，詳細原因請查看 debug.log。"
)


def _maybe_notify_update(result: dict) -> None:
    """同一最新版本只發一次通知，並在設定鎖內保存已通知版本。"""
    if not result.get("has_update"):
        return
    latest = result.get("latest_version")
    cfg = load_config()
    if latest and latest != cfg.get("general", {}).get("last_notified_update_version", ""):
        emit_notification(
            "info", "notif.update_available",
            message=f"v{latest}", url=result.get("download_url", ""),
        )
        def _remember(config: dict) -> None:
            config.setdefault("general", {})["last_notified_update_version"] = latest
        mutate_config(_remember)


async def _startup_update_check() -> None:
    """啟動時背景檢查新版；任何錯誤只記錄，不阻斷啟動。"""
    try:
        _cfg = load_config()  # raw dict
        if not _cfg.get("general", {}).get("auto_check_update", True):
            return
        result = await check_update()  # 復用端點函式，check_update() 本體不動
        _maybe_notify_update(result)
    except Exception:
        logger.warning("lifespan: startup update check failed", exc_info=True)


async def _periodic_update_check_loop() -> None:
    """非桌面版每 24 小時重查一次；啟動當下已由 startup task 查過。"""
    if _is_windows_desktop() or _is_mac_desktop():
        return
    while True:
        await asyncio.sleep(86400)
        try:
            cfg = load_config()
            if cfg.get("general", {}).get("auto_check_update", True):
                _maybe_notify_update(await check_update())
        except Exception:
            logger.warning("lifespan: periodic update check failed", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── startup ───────────────────────────────────────────────
    # 資料根定版必須在 init_db()／任何 request 之前（CD-B2）；失敗走固定 stderr + os._exit。
    try:
        bootstrap_data_layout()
    except Exception as e:
        logger.error("lifespan: 資料根定版失敗: %s", e, exc_info=True)
        # ruff T201 禁 print；行為等同 print(..., file=sys.stderr)
        sys.stderr.write(_LIFESPAN_BOOTSTRAP_STDERR + "\n")
        sys.stderr.flush()
        os._exit(LIFESPAN_BOOTSTRAP_EXIT_CODE)
    # init_db() 必須在任何 request 前執行：執行 DROP COLUMN migration（v0.8.7：
    # 移除 legacy clip_embedding / clip_model_id），確保 Video.from_row cls(**data)
    # 不會因 legacy schema 欄位收到未知 keyword 而 500。CD-57b-8 contract。
    init_db()
    start_notification_persistence()

    _pending = consume_pending_bootstrap_result()
    if _pending is not None:
        if _pending.status == "finalized_legacy" and not is_synology():
            emit_notification("info", "notif.data_root_finalized", message=str(_pending.root))
        elif _pending.status == "recovered_existing":
            emit_notification("warn", "notif.data_root_recovered", message=str(_pending.root))
        # fresh／resumed：不 emit

    # TASK-114a-T2: 認證閘門的 schema 就緒動作，與 init_db() 同一段落一起跑
    # （CD-114a-3：兩者刻意不合併成同一支函式，但啟動時機一致）。idempotent
    # CREATE TABLE IF NOT EXISTS + 首次 load_snapshot() 暖 cache。
    ensure_schema()

    try:
        consume_reset_access_auth_marker()
    except Exception:
        logger.warning("lifespan: consume_reset_access_auth_marker failed unexpectedly", exc_info=True)

    # TASK-104: one-time heal for pre-0.12.6 readonly rows whose nfo_mtime was
    # hardcoded to 0.0 even though the sibling .nfo was really written next to
    # the cover (core/database/migrate.py::backfill_readonly_nfo_mtime docstring
    # has full context). Must run exactly once per app boot — NOT inside init_db()
    # (called on many showcase requests) and NOT on any per-request path.
    # Wrapped in try-except so any unexpected failure cannot crash startup.
    try:
        _backfill_config = load_config()
        _backfill_path_mappings = _backfill_config.get("gallery", {}).get("path_mappings", {})
        _healed = backfill_readonly_nfo_mtime(path_mappings=_backfill_path_mappings)
        if _healed > 0:
            logger.info("lifespan: backfilled nfo_mtime for %d readonly row(s)", _healed)
    except Exception:
        logger.warning("lifespan: backfill_readonly_nfo_mtime failed unexpectedly", exc_info=True)

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

    # TASK-107-P1-T2: 背景（非阻塞）啟動更新檢查。lifespan 不 await 此 task，
    # yield 立刻放行，App 啟動不被 GitHub 網路往返拖慢（AC-A6）。
    # create_task 回傳值須保留強引用（event loop 只持 weak ref），否則 task 可能
    # 執行中途被 GC 回收 —— 存 app.state（app 已建立、比 module global 乾淨，無需 global）。
    app.state.startup_check_task = asyncio.create_task(_startup_update_check())
    app.state.periodic_update_check_task = asyncio.create_task(_periodic_update_check_loop())

    # TASK-144-T5: 12 小時排程 loop；create_task 回傳值須保留強引用（同上一段理由，
    # event loop 只持 weak ref，task 可能執行中途被 GC 回收）。
    app.state.auto_organize_task = asyncio.create_task(auto_organize_loop())

    try:
        await source_reachability.schedule_reprobe_if_stale()
    except Exception:
        logger.warning("lifespan: source reachability startup probe failed unexpectedly", exc_info=True)

    yield
    # ── shutdown ──────────────────────────────────────────────
    # 每一步各自 try/except（同 startup 的既有精神）：通知 drain 失敗不可擋住
    # 排程 task 的 cancel，反之亦然。
    try:
        app.state.periodic_update_check_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await app.state.periodic_update_check_task
    except Exception:
        logger.warning("lifespan: periodic_update_check_task shutdown failed unexpectedly", exc_info=True)

    try:
        app.state.auto_organize_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await app.state.auto_organize_task
    except Exception:
        logger.warning("lifespan: auto_organize_task shutdown failed unexpectedly", exc_info=True)

    # v0.15.13 P2-1：writer thread 是 daemon，process 結束時會被直接砍掉、
    # 佇列裡還沒寫進 DB 的通知會消失。這裡把它 join 掉，讓佇列在真正結束前
    # 排空。thread.join() 本身是同步阻塞呼叫，丟進 asyncio.to_thread 避免卡住
    # event loop。**上限就是那支的 timeout（2 秒），由 thread.join() 自己保證**——
    # 它只做「放哨兵 ＋ join」，佇列的排空由 writer 在自己那條 thread 上完成，
    # 所以關閉時間與 DB 快慢完全解耦（`test_stop_notification_persistence_is_bounded_by_its_timeout`）。
    #
    # ⚠️ 這一段目前**只在 CLI 模式（uvicorn 直跑、Ctrl-C）與測試裡執行**。
    # 桌面版的伺服器跑在 `windows/standalone.py:558` 的 daemon thread 上，
    # 全庫沒有任何地方對它設 `should_exit`，所以關 App 時 lifespan shutdown 不會被跑到
    # ——桌面版的通知持久化靠的是「writer 平常就跟得上」（實測每筆約 18ms、
    # 佇列正常深度 0–1），不是靠這裡。要讓桌面版也走這條，得把 quit 鉤子接上，
    # 那是另一支 branch 的事（見 PR body 的 residual）。
    try:
        await asyncio.to_thread(stop_notification_persistence)
    except Exception:
        logger.warning("lifespan: stop_notification_persistence failed unexpectedly", exc_info=True)


# FastAPI 應用
app = FastAPI(
    title="OpenAver",
    description="JAV 影片元數據管理工具",
    version=VERSION,
    lifespan=lifespan,
)

# 靜態檔案
app.mount("/static", NoCacheStaticFiles(directory=STATIC_DIR), name="static")
app.add_middleware(GZipMiddleware, compresslevel=GZIP_COMPRESS_LEVEL, exclude_content_types=GZIP_EXCLUDED_CONTENT_TYPES)

# 模板引擎
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# ============ 註冊 API 路由 ============
from web.routers import search as search_router
from web.routers import config as config_router
from web.routers import scraper as scraper_router
from web.routers import translate as translate_router
from web.routers import scanner as scanner_router
from web.routers import gallery_media as gallery_media_router
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
from web.routers import cover_badges as cover_badges_router
from web.routers import tags as tags_router
from web.routers import notifications as notifications_router
# TASK-107-P1-T2: import emit_notification at module level so lifespan can call
# it directly and tests can patch("web.app.emit_notification") at the use-site.
from web.routers.notifications import emit_notification, start_notification_persistence, stop_notification_persistence
# feature/152c CD-152c-20：device_state 不可 import web/（import-linter 契約），
# 改由 web/app.py 在 module level 註冊通知埠——import 這件事在所有進入點
# （含不啟動 lifespan 的桌面版與 TestClient）都必然發生，比 lifespan 更早、更穩。
device_state.set_notification_sink(emit_notification)
from web.routers import similar as similar_router
from web.routers import settings_link as settings_link_router
from web.routers import scraper_sources as scraper_sources_router
from web.routers import settings_metatube as settings_metatube_router
from web.routers import cf as cf_router
from web.routers import diagnostics as diagnostics_router
from web.routers import access as access_router
from web.routers import wishlist as wishlist_router
from web.routers import insights as insights_router
from web.routers import source_probe as source_probe_router
# Module-level imports for startup_reconnect / _fire_probe so that
# patch("web.app.startup_reconnect") / patch("web.app._fire_probe") target the
# correct use-site binding (TASK-63e-1; function-local import would defeat patch).
from web.routers.settings_metatube import startup_reconnect, _fire_probe  # noqa: E402, PLC2701 — 既有註解（TASK-63e-1）已明講：module-level import 是為了讓 patch("web.app._fire_probe") 打中呼叫端 binding，函式內 import 會讓 patch 失效；_fire_probe 是 metatube 重連探測的內部 primitive，尚未升格為公開 API
app.include_router(search_router.router)
app.include_router(config_router.router)
app.include_router(scraper_router.router)
app.include_router(translate_router.router)
app.include_router(scanner_router.router)
app.include_router(gallery_media_router.router)
app.include_router(gemini_router.router)
app.include_router(openai_translate_router.router)
app.include_router(filename_router.router)
app.include_router(showcase_router.router)
app.include_router(motion_lab_router.router)
app.include_router(capabilities_router.router)
app.include_router(collection_router.router)
app.include_router(collection_router.user_tags_router)
app.include_router(collection_router.user_rating_router)
app.include_router(actress_router.router)
app.include_router(actress_alias_router.router)
app.include_router(tag_alias_router.router)
app.include_router(cover_badges_router.router)
app.include_router(tags_router.router)
app.include_router(notifications_router.router)
app.include_router(similar_router.router)
app.include_router(settings_link_router.router)
app.include_router(scraper_sources_router.router)
app.include_router(settings_metatube_router.router)
app.include_router(cf_router.router)
app.include_router(diagnostics_router.router)
app.include_router(access_router.router)
app.include_router(wishlist_router.router)
app.include_router(insights_router.router)
app.include_router(source_probe_router.router)


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


# ============ 認證閘門（TASK-114a-T2）============

# deny-by-default 放行清單：未認證下只有這兩組 (method, path) 可以通過。
# CD-114a-8；具名常數 + 長度斷言（測試層）防止未來「順手多放一個」。
_VERIFY_ENDPOINT = ("POST", "/api/access/verify")
_HEALTH_ENDPOINT = ("GET", "/api/health")
_AUTH_ALLOWLIST = frozenset({_VERIFY_ENDPOINT, _HEALTH_ENDPOINT})


def render_access_gate_page(request: Request):
    """偽裝頁：獨立完整 HTML，不透露任何真實內容存在與否。

    唯一產生點——正常的「未認證」分支、冷載失敗的 fail-closed 分支、以及 T3
    `POST /api/access/verify` 的成功/失敗回應都呼叫這支，不得各寫一次
    `TemplateResponse(...)`（逐位元組必須相同，寫兩次遲早會漂移）。公開名
    （無底線前綴）：`web/routers/access.py` 要 import 它，底線私有名會撞 ruff
    `PLC2701`（BE-LINT-01，正解是升格公開名，不是加 noqa）。
    """
    return templates.TemplateResponse(
        request, "access_gate.html", {},
        headers={"Cache-Control": "no-store"},
    )


def _is_cross_site_api_request(request: Request) -> bool:
    """這個請求是「由別的網站發起、打向 `/api/` 」嗎？

    Codex PR#129 round-2 P3 指出 `SameSite=Lax` 會在**跨站頂層 GET 導覽**時照送
    `sid`，而閘門後有真的會寫檔的 GET 端點——`/api/gallery/jellyfin-update` 覆寫
    poster/fanart（某些外部庫佈局下甚至就地裁切原始封面，本專案 0.13.x 已被這個
    bug 咬過一次，原圖裁壞回不來）、`/api/gallery/update` 覆寫 NFO、
    `/api/gallery/generate` 重建 DB。使用者只要開到一個知道你 LAN 位址的惡意頁，
    那頁就能把瀏覽器導去這些路徑，用受害者的票發動批次寫入。

    **沒有**改成 `SameSite=Strict`：那是 CD-114a-6 已拍板的決定，理由是分享情境
    ——LINE/QR code 點進來的第一次導覽會掉票，而掉票看到的是刻意無文字的偽裝頁，
    家人不會知道發生什麼事。改用這條的代價是零：分享連結一定指向頁面路由，不會
    有人分享 `/api/...`；反過來，跨站打 `/api/` 對一個區網私有服務永遠不合法。

    `Sec-Fetch-Site` 缺席時回 False（fail-open）——舊瀏覽器與 curl／AI agent 都
    不送這個 header，那些呼叫者本來就不是這條在防的對象（它防的是「使用者的
    瀏覽器被第三方網頁指使」，而瀏覽器一定會送）。
    """
    if request.headers.get("sec-fetch-site") != "cross-site":
        return False
    return request.url.path.startswith("/api/")


def _bearer_token(request: Request) -> str | None:
    """`Authorization: Bearer <token>` 的解析（CD-114b-3）。純函式、零 I/O、
    不查 DB、不查 snapshot()——只把 header 字串拆成 token 或 None，交給
    呼叫端（access_gate 第 8 步）自己餵給 verify_ticket()。不接受
    query-string token（spec C-5：憑證進 URL 會進 log／瀏覽器歷史／Referer）。
    """
    header = request.headers.get("authorization")
    if header is None:
        return None
    parts = header.split()
    if len(parts) != 2:
        return None
    scheme, token = parts
    if scheme.lower() != "bearer":
        return None
    token = token.strip()
    return token if token else None


@app.middleware("http")
async def access_gate(request: Request, call_next):
    """
    非 loopback 且認證已開啟時的 PIN 閘門。

    宣告在 `lan_access_gate`（下方）之前——依 Starlette 疊加語意（後宣告者
    最外層先執行，§1.2／§8.2 context7 結論），本 middleware 實際執行在
    `lan_access_gate` 放行**之後**（CD-114a-4）：`lan_access_gate` 先擋掉
    單機模式下的所有非 loopback 流量，本 middleware 只處理「已經被放行
    進來」的 LAN 流量要不要認證。

    本機判斷一律委派 `_is_loopback_host()`（CD-114a-5，比 `_LOOPBACK_HOSTS`
    寬的判斷），不得自行解析位址／比對字串。
    """
    client_host = request.client.host if request.client else None
    if _is_loopback_host(client_host):
        return await call_next(request)

    snap = snapshot()
    if snap is None:
        # 冷載：TestClient(app) 未當 context manager 用時 lifespan 不會跑，
        # ensure_schema() 從未執行過——這裡用 ensure_schema()（非單純
        # load_snapshot()）補跑一次：它的 CREATE TABLE IF NOT EXISTS 是
        # idempotent，即使目標 DB 檔案裡連 access_auth 表都還不存在（例如
        # 全新 checkout、或既有測試打的是完全不相干的 DB 路徑）也不會拋
        # `sqlite3.OperationalError: no such table`。這是熱路徑唯一允許
        # 的 DB 讀寫，且只發生在第一個請求（CD-114a-11）。
        try:
            await asyncio.to_thread(ensure_schema)
            snap = snapshot()
        except Exception:
            # fail-closed：無法確認認證狀態時一律當作「未認證」處理，直接回
            # 偽裝頁，不讓例外冒泡成 500——未認證訪客看到的東西必須永遠長
            # 一樣，500 錯誤頁跟偽裝頁是兩種不同形狀，本身就是一種洩漏。
            # 只有非 loopback 流量走得到這裡（loopback 在上面第 2 步已經
            # return），所以「DB 壞掉時擋住 LAN」不會把主人鎖在門外——他在
            # 自己機器上照常進得去，也才修得了 DB；反過來 fail-open 會變成
            # 「DB 一壞，全家都進得來」。
            logger.exception(
                "access_gate: cold-load ensure_schema() failed, "
                "fail-closed to masked page"
            )
            return render_access_gate_page(request)

    if not snap.enabled:
        return await call_next(request)

    method = request.method
    path = request.url.path
    authed = verify_ticket(request.cookies.get("sid")) or verify_ticket(_bearer_token(request))

    if (method, path) == _VERIFY_ENDPOINT:
        # 登入入口本身，永遠可達，不比對 authed。
        return await call_next(request)

    if (method, path) == _HEALTH_ENDPOINT:
        if authed:
            return await call_next(request)
        # 未認證：middleware 自己回應，不呼叫 handler（CD-114a-8 雙形狀）。
        return JSONResponse({"status": "ok"})

    if authed and _is_cross_site_api_request(request):
        # 持票但請求是「別的網站帶過來的、打向 /api/ 的」——一律當未認證處理
        # （Codex PR#129 round-2 P3 的替代修法，見 `_is_cross_site_api_request`）。
        # 回應與未認證完全同形，不新增可辨識的第四種形狀。
        return render_access_gate_page(request)

    if authed:
        return await call_next(request)

    if request.headers.get("authorization") is not None:
        # 讀者是程式不是人（§4.4／D-7）：只看 header 存不存在，不驗內容。
        return JSONResponse(
            {"success": False, "reason": "unauthorized"}, status_code=401
        )

    return render_access_gate_page(request)


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


def _is_loopback_host(host):
    """判斷 `host` 是否為本機（`/api/trigger-update` 三層護欄 CD-110b-5 用）。

    與 `_LOOPBACK_HOSTS`（:204）的關係：`_LOOPBACK_HOSTS` 是 middleware 的**短路
    名單**，只收兩個精確字面值，回答的是「要不要跳過讀 config」——這裡**不動它**。
    本函式回答的是另一個問題：「這個 client／Origin host 是不是本機」，用
    `ipaddress.is_loopback` 額外涵蓋 `127.0.0.0/8` 其餘位址、IPv4-mapped IPv6
    （`::ffff:127.0.0.1`），並加收 `localhost` 字面（純位址比對會漏它）。兩者
    判斷的集合都只可能來自本機，所以本函式是 `_LOOPBACK_HOSTS` 的**嚴格超集**，
    超集不製造安全缺口；反過來若本函式比 `_LOOPBACK_HOSTS` 更窄，才會出現
    「middleware 放行但端點誤拒」的桌面自鎖風險。
    """
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    # IPv4-mapped IPv6（`::ffff:127.0.0.1`）必須先解回 IPv4 才判得對：
    # 實測 `ipaddress.ip_address('::ffff:127.0.0.1').is_loopback` 是 **False**
    # （`is_loopback` 只認 `::1`）。dual-stack socket 上的 uvicorn 有機會把本機
    # 連線的 peer 回報成這個形式，不解就會把桌面版自己鎖在門外——那是 plan-110b
    # §4 風險表列為「最嚴重」的那一條。解回 IPv4 後 `127.0.0.1` 正常判 True。
    mapped = getattr(addr, "ipv4_mapped", None)
    if mapped is not None:
        addr = mapped
    return addr.is_loopback


def _is_loopback_origin(origin):
    """`Origin` header 是否解析出 loopback hostname（判 host 不判 port，CD-110b-5）。

    用 `urlparse` 取 `hostname`；`null`、malformed（`http://`、`not-a-url`）解析出的
    `hostname` 為 `None`／空字串，一律 fail-closed 回 False（不得當成「沒有 Origin」
    放行——「沒有 Origin」是呼叫端看 `origin is None` 另行判斷，不歸本函式管）。

    `urlparse` 本身也可能拋 `ValueError`（實測：未閉合的 IPv6 字面值
    `http://[::1` → `Invalid IPv6 URL`）。不接的話會變成未處理例外 → 500，
    既非 fail-closed 的 403、也把「被擋下」與「伺服器壞了」混在一起。一律接住回 False。
    """
    try:
        hostname = urlparse(origin).hostname
    except ValueError:
        return False
    return bool(hostname) and _is_loopback_host(hostname)


# ============ 輔助函數 ============


from web.lan_listener import get_lan_ip  # noqa: E402 — re-export for backward compat


def _is_windows_desktop() -> bool:
    """True のみ Windows 桌面 App（feature/82 T4：OPENAVER_STANDALONE env + win32 雙重條件）。
    非桌面 / 非 Windows → False，Settings 中不渲染 close_action 下拉。"""
    return os.environ.get("OPENAVER_STANDALONE") == "1" and sys.platform == "win32"


def _is_mac_desktop() -> bool:
    """True 僅限 macOS 桌面 App（OPENAVER_STANDALONE=1 AND darwin）。"""
    return os.environ.get("OPENAVER_STANDALONE") == "1" and sys.platform == "darwin"


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
    # 70-T5：cf_transport_available — standalone 已 register → true；dev/server → false
    from core.cf_transport import get_cf_transport as _get_cf_transport
    _cf_transport_available = _get_cf_transport() is not None

    # 118a-T9：per-site 可用性。cf_transport_available 是全域布林，答不了「這個來源
    # 能不能用」——standalone 在某個視窗建立失敗時仍會註冊一個只含另一站的 transport。
    # None ＝ 判不出來 → 前端沿用舊的全域旗標（fail-open，見 get_cf_available_sites）。
    from core.cf_transport import get_cf_available_sites as _get_cf_sites
    _cf_sites = _get_cf_sites()

    _server_mode = bool(config.get('general', {}).get('server_mode', False))

    return {
        "request": request,
        "config": config,
        "cf_transport_available": _cf_transport_available,
        "cf_sites": _cf_sites,
        "lan_ip": get_lan_ip() if _server_mode else None,
        "theme": config.get('general', {}).get('theme', 'light'),
        "sidebar_collapsed": config.get('general', {}).get('sidebar_collapsed', False),
        "font_size": font_size,
        "font_size_px": font_size_px,
        "version": VERSION,
        "locale": locale,
        "merged_translations": merged_translations,
        "t": _t_bound,
        "is_windows_desktop": _is_windows_desktop(),
        "is_desktop": _is_windows_desktop() or _is_mac_desktop(),
        "is_synology": is_synology(),
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
    # TASK-144-T7：「自動整理」鈕的 accent 狀態由伺服器 render，不由前端 fetch。
    # 前端拿的話，按鈕會先畫成 btn-outline、等請求回來才跳成 btn-accent——每次進
    # 搜尋頁閃一下，而且每次多一個請求。面板打開時才會再向 status 端點問一次最新值。
    # 沿用 get_common_context() 已經載好的那份 config（`:552`），不重讀一次磁碟。
    context["auto_organize_enabled"] = bool(
        context["config"].get("search", {}).get("auto_organize", {}).get("enabled", False)
    )
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


@app.get("/insights")
async def insights_page(request: Request):
    """片庫分析頁面"""
    context = get_common_context(request)
    context["page"] = "insights"
    return templates.TemplateResponse(request, "insights.html", context)


@app.get("/settings")
async def settings_page(request: Request):
    """設定頁面"""
    context = get_common_context(request)
    context["page"] = "settings"
    # 用 get_common_context 已載入的那一份 config（:517 → context["config"]），不再讀第二次
    # 磁碟——同一支函式裡的 _server_mode 也是這個形狀。純 dict 運算，
    # 不需要 asyncio.to_thread（BE-ASYNC-01 管的是阻塞 I/O，這行沒有）。
    context["focal_auto_enabled"] = not device_state.is_disabled_in(context["config"])
    return templates.TemplateResponse(request, "settings.html", context)


@app.get("/help")
async def help_page(request: Request):
    """使用說明頁面"""
    context = get_common_context(request)
    context["page"] = "help"
    # 81b-T5 + Codex P2：僅桌面主機（loopback）覆寫成可分享 LAN URL；
    # 遠端裝置走自身 request.base_url（已是可分享位址，nas.local / 反向代理皆保留）。
    lan_ip = context.get("lan_ip")
    from web.lan_listener import lan_listener
    lan_port = lan_listener.lan_port
    client_host = request.client.host if request.client else None  # 純 TCP 對端，不信任 XFF（同 80a 閘門）
    if client_host in _LOOPBACK_HOSTS and lan_ip and lan_port:
        context["base_url"] = f"http://{lan_ip}:{lan_port}"
    else:
        context["base_url"] = str(request.base_url).rstrip("/")

    # TASK-114b-T4（CD-114b-7）：agent 區塊渲染條件，與上面 base_url 用的
    # `client_host in _LOOPBACK_HOSTS`（窄）是不同判斷，不合併（plan §1.5）。
    snap = snapshot()
    if snap is None:
        snap = await asyncio.to_thread(load_snapshot)
    # 兩個旗標刻意分開（Codex PR review P2）：
    #   `show_agent_auth` 守的是**祕密**（token 面板）→ 密碼開啟時，
    #       只有本機或已用密碼登入的瀏覽器（cookie）可看到 token 真值。
    #   `auth_enabled` 守的是**事實陳述**（安全提示那句文案）→ 只看認證開沒開。
    # 兩者綁在一起的後果是：一台剛剛才輸完密碼的家人手機，打開說明頁看到的是
    # 「本程式不設帳號密碼」——它剛做的事就否證了這句話。而那句文案裡沒有任何
    # 祕密，持票人也早就知道認證是開著的（他才剛輸過），不存在洩漏面。
    authed = verify_ticket(request.cookies.get("sid"))
    show_agent_auth = snap.enabled and (_is_loopback_host(client_host) or authed)
    context["show_agent_auth"] = show_agent_auth
    context["auth_enabled"] = snap.enabled
    if show_agent_auth:
        context["agent_token"] = snap.agent_token

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


@app.get("/api/install-context")
async def get_install_context():
    """取得安裝路徑資訊，供 Help 頁更新 modal 分流使用（僅 desktop App）。"""
    if not (_is_windows_desktop() or _is_mac_desktop()):
        raise HTTPException(status_code=403, detail="此功能僅限桌面應用程式使用")
    try:
        exe = Path(sys.executable)
        if sys.platform == "darwin":
            install_dir = exe.parent.parent.parent  # python/bin/python3 → OpenAver/
        else:
            install_dir = exe.parent.parent          # python\pythonw.exe → OpenAver\
        default_dir = Path.home() / "OpenAver"
        is_default_path = install_dir == default_dir
    except Exception:
        is_default_path = True  # 偵測失敗視同情況 A（保守）
    return {"is_default_path": is_default_path}


@app.post("/api/trigger-update")
async def trigger_update(request: Request):
    """開啟外部終端視窗執行安裝 TUI（僅 desktop App，不揭露給 AI agent）。

    三層護欄（CD-110b-5，缺一不可）防範 ① 任何網站用 auto-submit `<form>` 觸發的
    CSRF ② `server_mode` 開啟時同網段裝置觸發桌面主機執行安裝腳本的 LAN 暴露面：
    ① 硬條件：desktop **且** loopback client（兩者皆須成立；同時關掉 server_mode
       的 LAN 暴露面）
    ② Origin 存在時只接受 loopback origin（判 host 不判 port）；不存在時不得因此
       放行，仍受①約束（PyWebView 可能不送 Origin）
    ③ 自訂 header `X-OpenAver-Desktop-Action` 存在（只檢查存在、不比對值——比對值
       不增加安全性，卻多一個日後改文案就破功的耦合點）
    四個檢查全部在 `subprocess.Popen` 之前：403 路徑零副作用。
    """
    client = request.client
    client_host = client.host if client else None
    origin = request.headers.get("origin")
    # 四個檢查對外一律回同一段文案（不讓外部探測出是哪一層擋的），但**對內記 log**：
    # plan-110b §4 把「護欄把桌面版自己鎖在門外」列為最嚴重風險，而那個情境在真機
    # 上只會看到一個 toast 錯誤。log 這一行是 owner 真機 hard-gate 失敗時唯一的
    # 分診依據——沒有它就得靠猜是哪一層。
    denied = None
    if not (_is_windows_desktop() or _is_mac_desktop()):
        denied = "not-desktop"
    elif not _is_loopback_host(client_host):
        denied = "non-loopback-client"
    elif origin is not None and not _is_loopback_origin(origin):
        # 註：`origin` 為空字串（header 存在但值為空）會走進這裡並被拒。這是刻意的
        # fail-closed，且合規瀏覽器不會產生該情境——同源 POST 若送 Origin 必為真實
        # origin 值，跨站沙箱情境送的是字面 `"null"` 而非空字串。
        denied = "non-loopback-origin"
    elif "X-OpenAver-Desktop-Action" not in request.headers:
        denied = "missing-desktop-action-header"
    if denied:
        # client_host／origin 是外部可控值。標準 HTTP 下 header 值不能含裸 CR/LF
        # （framing 層就會拒），所以換行式 log 偽造走不到這裡；但未消毒的外部輸入
        # 進 log 仍值得設上界——截斷成本近乎零，診斷用途也不需要長字串。
        logger.warning(
            "trigger-update 拒絕：layer=%s client_host=%.64s origin=%.128s",
            denied, str(client_host), str(origin),
        )
        raise HTTPException(status_code=403, detail="此功能僅限桌面應用程式使用")
    try:
        if sys.platform == "win32":
            subprocess.Popen(
                ["powershell.exe", "-ExecutionPolicy", "Bypass", "-NoProfile",
                 "-Command",
                 "irm https://raw.githubusercontent.com/slive777/OpenAver/main/install.ps1 | iex"],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        else:
            subprocess.Popen(
                ["osascript", "-e",
                 "tell application \"Terminal\" to do script "
                 "\"curl -fsSL https://raw.githubusercontent.com/slive777/OpenAver/main/install.sh | bash\""]
            )
    except Exception as e:
        logger.error("trigger-update 啟動外部終端失敗: %s", e)
        raise HTTPException(status_code=500, detail="啟動更新失敗，請查看日誌") from e
    return {"success": True}
