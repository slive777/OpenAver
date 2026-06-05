"""
web/routers/settings_metatube.py — metatube connection settings API (CD-63b-1).

Endpoints (prefix /api/settings/metatube):
  POST /connect    — validate URL, fetch providers, persist config, fire probe
  POST /disconnect — mark disconnected (config preserved for prefill)
  GET  /status     — return runtime connection + probe state
  POST /test       — re-probe all known providers in background
"""
import asyncio
import threading

from fastapi import APIRouter
from pydantic import BaseModel

from core.config import mutate_config
from core.logger import get_logger
from core.metatube.client import MetatubeHttpClient
from core.metatube.errors import MetatubeAuthError, MetatubeError
from core.metatube.probe import METATUBE_PROBE_CANARIES, probe_all
from core.metatube.state import metatube_state as state
from core.metatube.validation import validate_metatube_url
from core.source_config import build_metatube_sources

logger = get_logger(__name__)

router = APIRouter(prefix="/api/settings/metatube", tags=["settings-metatube"])

# 66 Codex P2 (round 2)：connect 序列化鎖。offload 後 _connect_sync 跑在 threadpool
# thread、兩個並發 /connect 會交錯各自的 state.connect()/save_config()/rollback
# （config↔runtime 不一致、rollback 拆掉別人的連線）。pre-branch event loop 隱式序列
# 化了這段；此鎖在 threadpool thread 上阻塞（不卡 event loop）以還原該序列化。
# connect/persist-allow-lan 皆罕見管理動作，序列化其慢 I/O 可接受。
_connect_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class ConnectRequest(BaseModel):
    url: str
    token: str = ""
    allow_lan: bool = False


# ---------------------------------------------------------------------------
# Sync helper: token canary (shared by connect + startup_reconnect) — Codex P1
# ---------------------------------------------------------------------------

def _verify_token_canary(base_url: str, token: str, providers: dict) -> None:
    """Verify the token is accepted by a real auth-required endpoint.

    Selects the first provider present in METATUBE_PROBE_CANARIES from the
    given providers dict, then calls search() to confirm the token works.

    Raises:
        MetatubeAuthError: if the server returns HTTP 401 (definitive token failure).
        MetatubeError (non-401): re-raised; caller decides whether to block or continue.

    Returns None (without raising) when:
        - No canary provider is available in the providers list (skip → pass).
        - search() succeeds (token OK).
    """
    names = list(providers.keys())
    canary_provider = next((n for n in names if n in METATUBE_PROBE_CANARIES), None)
    if canary_provider is None:
        # No known canary in this server's provider list — skip, treat as pass.
        return
    MetatubeHttpClient(base_url, token, timeout=5).search(
        canary_provider, METATUBE_PROBE_CANARIES[canary_provider]
    )


# ---------------------------------------------------------------------------
# Sync helper: persist allow_lan only (for dedup early-return path) — Codex P2
# ---------------------------------------------------------------------------

def _persist_allow_lan(url: str, token: str, allow_lan: bool) -> bool:
    """Update config.metatube.allow_lan if the stored url+token match.

    Called before the dedup early-return in connect() so that a second call
    with the same url/token but a different allow_lan value still updates the
    persisted config.  Does NOT touch runtime state, does NOT trigger a
    reconnect, does NOT write any other field.

    Returns True on success (or no-op when url/token don't match), False if the
    config write fails — caller must surface the failure rather than reporting
    success, otherwise the LAN opt-in is silently lost (Codex P2).

    66 Codex P2 (round 2)：與 _connect_sync 共用 _connect_lock —— 兩個並發
    dedup-save，或 dedup-save 與 full-connect-save 競爭同一個 config.json，會互相
    clobber。序列化即可避免。
    """
    # 鎖序：外 _connect_lock → 內 _config_write_lock（經 mutate_config）。
    with _connect_lock:
        try:
            def _mut(config):
                mt = config.get("metatube") or {}
                if mt.get("url") == url and mt.get("token") == token:
                    mt["allow_lan"] = allow_lan
                    config["metatube"] = mt
                # url/token 不符 → 不改 cfg（mutate_config 仍會 byte-identical 重存，可接受）
            mutate_config(_mut)
            return True
        except Exception:
            logger.exception("_persist_allow_lan: failed to update allow_lan in config")
            return False


# ---------------------------------------------------------------------------
# Sync helper: disconnect serialized against in-flight connect — Codex P2
# ---------------------------------------------------------------------------

def _disconnect_sync() -> None:
    """Acquire _connect_lock then state.disconnect().

    66 Codex P2：序列化 disconnect 對在途的 _connect_sync —— 連線 HTTP/config I/O
    執行期間送出的 disconnect 會等該 connect 完成後才斷線，確保 last-action-wins，
    避免 connect worker 在使用者已 disconnect 後又把 connected 設回 True。
    連線完成後 disconnect 把 generation 推進 → connect 的 stale 探測被 generation
    guard 擋下（探測本就不會動 connected）。
    必須經 asyncio.to_thread 呼叫：在 event loop thread 上直接 acquire 已被持有的
    threading.Lock 會卡死整個 loop。
    """
    with _connect_lock:
        state.disconnect()


# ---------------------------------------------------------------------------
# Sync: startup reconnect — TASK-63e-1
# ---------------------------------------------------------------------------

def startup_reconnect(config: dict) -> list[str] | None:
    """Re-establish metatube connection from persisted config at startup.

    Reads the metatube section of *config* (a raw dict as returned by
    load_config()), validates the stored URL, fetches providers, verifies the
    token via canary, then calls state.connect().

    Returns:
        list[str]  — provider names if successfully reconnected.
        None       — if reconnect was skipped or failed (state stays disconnected).

    This function is intentionally synchronous so it can be called from
    lifespan via loop.run_in_executor() without any async context dependency.
    It never raises; all error paths log a warning and return None.
    """
    mt = config.get("metatube") or {}

    # enabled guard
    if mt.get("enabled") is not True:
        return None

    url = mt.get("url", "").strip()
    token = mt.get("token", "")
    allow_lan = bool(mt.get("allow_lan", False))

    if not url:
        return None

    # SSRF validation — honour the allow_lan that was persisted at connect time
    err = validate_metatube_url(url, allow_lan=allow_lan)
    if err:
        logger.warning("startup_reconnect: SSRF blocked for stored URL: %s", err)
        return None

    # Fetch provider list
    try:
        providers = MetatubeHttpClient(url, token).list_providers()
    except MetatubeError:
        logger.warning("startup_reconnect: list_providers failed for url=%r", url)
        return None

    # Token canary (Codex P1) — same semantics as connect endpoint
    try:
        _verify_token_canary(url, token, providers)
    except MetatubeAuthError:
        logger.warning(
            "startup_reconnect: token rejected (401) — not reconnecting"
        )
        return None
    except MetatubeError:
        # Non-401: transient / canary issue — log and continue (same as connect)
        logger.info(
            "startup_reconnect: canary non-401 error, continuing with reconnect"
        )

    # Reconnect runtime state
    names = list(providers.keys())
    state.connect(url, token, names)
    logger.info("startup_reconnect: reconnected to %r with %d providers", url, len(names))
    return names


# ---------------------------------------------------------------------------
# Module-level probe helper (must be called from inside an async handler
# so asyncio.get_running_loop() works)
# ---------------------------------------------------------------------------

def _fire_probe(base_url: str, token: str, names: list[str], generation: int) -> None:
    """Schedule a background probe via the running event loop's executor."""
    def _run_probe():
        state.set_probe_started(generation=generation)
        try:
            probe_all(
                base_url,
                token,
                state,
                names,
                on_progress=lambda done, total: state.set_probe_progress(done, total, generation=generation),
                generation=generation,
            )
        except Exception:
            logger.exception("metatube probe failed")
        finally:
            state.set_probe_done(generation=generation)

    asyncio.get_running_loop().run_in_executor(None, _run_probe)


# ---------------------------------------------------------------------------
# POST /connect
# ---------------------------------------------------------------------------

def _connect_sync(url: str, token: str, allow_lan: bool) -> dict:
    """Threadpool entry for /connect — serializes via _connect_lock then delegates.

    66 Codex P2 (round 2)：整個連線臨界段（Step3–5 + rollback）在 _connect_lock 內
    執行，避免兩個並發 connect 交錯（config↔runtime 不一致、rollback 拆別人連線）。
    鎖在 threadpool thread 上阻塞、不卡 event loop。_fire_probe 仍在外層 async
    handler（需 running loop），不在此鎖內。
    """
    with _connect_lock:
        return _connect_sync_impl(url, token, allow_lan)


def _connect_sync_impl(url: str, token: str, allow_lan: bool) -> dict:
    """Threadpool helper: Step3 list_providers + Step3b canary + Step4 state.connect
    + Step5 load_config / merge / save_config (+ rollback state.disconnect on failure).

    Returns:
        {"ok": True,  "names": [...]}
        {"ok": False, "error": "<exact error string>"}

    Error-string / catch-order is preserved exactly as the original connect() body:
      - Step3 MetatubeError (catches MetatubeAuthError subclass too) → "無法連線..."
      - Step3b MetatubeAuthError → "Token 錯誤..."
      - Step3b non-401 MetatubeError → log only, continue
      - Step5 Exception → state.disconnect() rollback → "設定儲存失敗，請重試。"
    """
    # Step 3: fetch provider list from the metatube server
    try:
        providers = MetatubeHttpClient(url, token).list_providers()
    except MetatubeError:
        logger.exception("metatube connect: list_providers failed for url=%r", url)
        return {
            "ok": False,
            "error": "無法連線到 metatube server，請確認 URL 與 token",
        }

    names = list(providers.keys())

    # Step 3b: token canary — verify token is accepted by an auth-required endpoint.
    # list_providers() calls GET /v1/providers which is AUTH-FREE (returns 200 even
    # without a token).  We must probe a token-required endpoint before persisting.
    # _verify_token_canary: 401 → MetatubeAuthError; non-401 MetatubeError → re-raised;
    # no canary provider in list → returns (skip, treat as pass).
    try:
        _verify_token_canary(url, token, providers)
    except MetatubeAuthError:
        return {
            "ok": False,
            "error": "Token 錯誤或缺少：無法通過 metatube server 驗證，請確認 Bearer Token",
        }
    except MetatubeError as e:
        # Non-401 errors (timeout, 404, 5xx, …) are canary / transient issues.
        # Log class name only — do NOT include token or request detail.
        logger.info(
            "metatube connect: canary non-401 error (%s), not blocking connect",
            type(e).__name__,
        )

    # Step 4: update runtime state (thread-safe: metatube_state uses threading.Lock)
    # 66 Codex P2：capture THIS connect 設的 generation 一路帶回給 _fire_probe，
    # 不可在 await 後重讀 state.generation（並發 connect/disconnect 會推進它 → 探測
    # 會用錯的 generation 蓋掉現役連線的 availability）
    gen = state.connect(url, token, names)

    # Step 5: persist to config.json (CD-63b-3 merge)
    # 鎖序：caller _connect_sync 已持 _connect_lock（外）→ mutate_config 取
    # _config_write_lock（內）。整個 load+merge 在 mutator 內、單一 critical section。
    def _merge_mutator(config):
        # Persist metatube URL + token + allow_lan, preserving existing `enabled`
        # flag (CD-63b-3).  Do NOT wipe `enabled` on reconnect — user's toggle
        # state must survive.  allow_lan is stored so startup_reconnect can honour
        # the user's LAN opt-in when re-connecting after a restart (TASK-63e-1).
        mt = config.get("metatube") or {}
        mt["url"] = url
        mt["token"] = token
        mt["allow_lan"] = allow_lan
        config["metatube"] = mt

        # Merge metatube sources (preserve existing enabled flags)
        existing_mt: dict[str, dict] = {
            s["id"]: s
            for s in config.get("sources", [])
            if s.get("type") == "metatube"
        }
        non_mt: list[dict] = [
            s for s in config.get("sources", [])
            if s.get("type") != "metatube"
        ]

        merged_mt: list[dict] = []
        seen: set[str] = set()

        for sc in build_metatube_sources(names):
            d = sc.model_dump()
            # Offset: metatube providers sort after all builtins (order 0–7)
            d["order"] = d["order"] + 100
            # Preserve user's enabled toggle if this provider existed before
            if sc.id in existing_mt:
                d["enabled"] = existing_mt[sc.id].get("enabled", False)
            merged_mt.append(d)
            seen.add(sc.id)

        # Preserve old metatube providers no longer present (keep user data)
        for sid, s in existing_mt.items():
            if sid not in seen:
                merged_mt.append(s)

        config["sources"] = non_mt + merged_mt

    try:
        mutate_config(_merge_mutator)
    except Exception:
        logger.exception("metatube connect: failed to persist config")
        state.disconnect()  # rollback — don't stay connected with unsaved config
        return {"ok": False, "error": "設定儲存失敗，請重試。"}

    return {"ok": True, "names": names, "generation": gen}


@router.post("/connect")
async def connect(req: ConnectRequest):
    """Connect to a metatube HTTP server.

    Validates URL (SSRF guard), fetches provider list, persists config,
    and fires a background probe of all providers.
    """
    # Step 1: SSRF validation
    err = validate_metatube_url(req.url, req.allow_lan)
    if err:
        return {"success": False, "error": err}

    # Step 2: dedup — already connected to same URL and token.
    # Even on dedup hit we still need to persist allow_lan in case the user
    # changed it (Codex P2: _persist_allow_lan updates config without re-connecting).
    if state.is_connected and state.base_url == req.url and state.token == req.token:
        # 66 Codex P1：dedup path 也跑在 loop，_persist_allow_lan 做 load/save_config → to_thread
        if not await asyncio.to_thread(_persist_allow_lan, req.url, req.token, req.allow_lan):
            # Mirror Step5 semantics: don't report success if the opt-in wasn't
            # persisted, otherwise the restart bug silently returns (Codex P2).
            return {"success": False, "error": "設定儲存失敗，請重試。"}
        return {"success": True, "provider_count": state.provider_count}

    # Step 3–5: run blocking I/O (HTTP + config) in threadpool
    result = await asyncio.to_thread(_connect_sync, req.url, req.token, req.allow_lan)
    if not result["ok"]:
        return {"success": False, "error": result["error"]}

    # Step 6: fire background probe (must stay on loop — uses asyncio.get_running_loop())
    # 66 Codex P2：用 _connect_sync 回傳的 generation（此次 connect 設的），不重讀
    # state.generation（avoid stale/superseded generation under concurrent connects）
    _fire_probe(req.url, req.token, result["names"], result["generation"])

    return {"success": True, "provider_count": len(result["names"])}


# ---------------------------------------------------------------------------
# POST /disconnect
# ---------------------------------------------------------------------------

@router.post("/disconnect")
async def disconnect():
    """Mark metatube as disconnected.

    URL/token are NOT cleared from config.json so they can prefill the
    next connect dialog.  Source enabled flags are also untouched.

    66 Codex P2：經 _connect_lock 序列化（via to_thread），等在途 connect 完成後
    才斷線 → last-action-wins，不會被 connect worker 的晚到完成蓋回 connected。
    """
    await asyncio.to_thread(_disconnect_sync)
    return {"success": True}


# ---------------------------------------------------------------------------
# GET /status
# ---------------------------------------------------------------------------

@router.get("/status")
async def status():
    """Return current runtime connection + probe state."""
    return state.status_dict()


# ---------------------------------------------------------------------------
# POST /test
# ---------------------------------------------------------------------------

@router.post("/test")
async def test_connection():
    """Re-probe all currently known providers in the background."""
    names = [k.split(":", 1)[1] for k in state.availability_map()]
    gen = state.generation
    _fire_probe(state.base_url or "", state.token or "", names, gen)
    return {"success": True, "message": "probe started"}
