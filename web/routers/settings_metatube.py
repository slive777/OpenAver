"""
web/routers/settings_metatube.py — metatube connection settings API (CD-63b-1).

Endpoints (prefix /api/settings/metatube):
  POST /connect    — validate URL, fetch providers, persist config, fire probe
  POST /disconnect — mark disconnected (config preserved for prefill)
  GET  /status     — return runtime connection + probe state
  POST /test       — re-probe all known providers in background
"""
import asyncio

from fastapi import APIRouter
from pydantic import BaseModel

from core.config import load_config, save_config
from core.logger import get_logger
from core.metatube.client import MetatubeHttpClient
from core.metatube.errors import MetatubeAuthError, MetatubeError
from core.metatube.probe import METATUBE_PROBE_CANARIES, probe_all
from core.metatube.state import metatube_state as state
from core.metatube.validation import validate_metatube_url
from core.source_config import build_metatube_sources

logger = get_logger(__name__)

router = APIRouter(prefix="/api/settings/metatube", tags=["settings-metatube"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class ConnectRequest(BaseModel):
    url: str
    token: str = ""
    allow_lan: bool = False


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

    # Step 2: dedup — already connected to same URL and token
    if state.is_connected and state.base_url == req.url and state.token == req.token:
        return {"success": True, "provider_count": state.provider_count}

    # Step 3: fetch provider list from the metatube server
    try:
        providers = MetatubeHttpClient(req.url, req.token).list_providers()
    except MetatubeError:
        logger.exception("metatube connect: list_providers failed for url=%r", req.url)
        return {
            "success": False,
            "error": "無法連線到 metatube server，請確認 URL 與 token",
        }

    names = list(providers.keys())

    # Step 3b: token canary — verify token is accepted by an auth-required endpoint.
    # list_providers() calls GET /v1/providers which is AUTH-FREE (returns 200 even
    # without a token).  We must probe a token-required endpoint before persisting.
    # Only MetatubeAuthError (HTTP 401) is a definitive token failure; all other
    # MetatubeError subclasses are transient/canary issues and must NOT block connect.
    _canary_provider = next((n for n in names if n in METATUBE_PROBE_CANARIES), None)
    if _canary_provider is not None:
        try:
            MetatubeHttpClient(req.url, req.token, timeout=5).search(
                _canary_provider, METATUBE_PROBE_CANARIES[_canary_provider]
            )
        except MetatubeAuthError:
            return {
                "success": False,
                "error": "Token 錯誤或缺少：無法通過 metatube server 驗證，請確認 Bearer Token",
            }
        except MetatubeError as e:
            # Non-401 errors (timeout, 404, 5xx, …) are canary / transient issues.
            # Log class name only — do NOT include token or request detail.
            logger.info(
                "metatube connect: canary non-401 error (%s), not blocking connect",
                type(e).__name__,
            )
    # If _canary_provider is None (server has no provider in METATUBE_PROBE_CANARIES),
    # skip canary verification entirely — defensive design, do NOT block connect.

    # Step 4: update runtime state
    state.connect(req.url, req.token, names)

    # Step 5: persist to config.json (CD-63b-3 merge)
    try:
        config = load_config()

        # Persist metatube URL + token, preserving existing `enabled` flag (CD-63b-3).
        # Do NOT wipe `enabled` on reconnect — user's toggle state must survive.
        mt = config.get("metatube") or {}
        mt["url"] = req.url
        mt["token"] = req.token
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
        save_config(config)
    except Exception:
        logger.exception("metatube connect: failed to persist config")
        state.disconnect()  # rollback — don't stay connected with unsaved config
        return {"success": False, "error": "設定儲存失敗，請重試。"}

    # Step 6: fire background probe
    gen = state.generation
    _fire_probe(req.url, req.token, names, gen)

    return {"success": True, "provider_count": len(names)}


# ---------------------------------------------------------------------------
# POST /disconnect
# ---------------------------------------------------------------------------

@router.post("/disconnect")
async def disconnect():
    """Mark metatube as disconnected.

    URL/token are NOT cleared from config.json so they can prefill the
    next connect dialog.  Source enabled flags are also untouched.
    """
    state.disconnect()
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
