"""
Tag 黑名單 API Router — /api/tag-blacklist

端點：
    GET    /api/tag-blacklist            列出黑名單＋建議字＋有效隱藏集
    POST   /api/tag-blacklist            新增黑名單字
    DELETE /api/tag-blacklist/{name}     刪除黑名單字（冪等，不存在也回 200）

封面標章字（含與其同別名組的字）不可加入（cover_badge）。
error response 固定中文，不洩漏例外訊息。
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.database import TagAliasRepository, TagBlacklistRepository, init_db
from core.logger import get_logger
from core.similar import canonicalize as _canonicalize_module
from core.similar.ranker_cache import SimilarRankerCache
from core.tag_display import (
    COMMON_BLACKLIST_SUGGESTIONS,
    build_context,
    is_hidden_tag,
    load_context,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api/tag-blacklist", tags=["tag-blacklist"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class CreateBlacklistRequest(BaseModel):
    name: str


# ---------------------------------------------------------------------------
# Helper — 寫入成功後失效相似排序快取（形狀照 tag_alias.py）
# ---------------------------------------------------------------------------

def _invalidate_caches() -> None:
    _canonicalize_module._invalidate_cache()
    try:
        SimilarRankerCache.invalidate()
    except Exception:
        logger.warning("[tag_blacklist] SimilarRankerCache.invalidate 失敗，不影響寫入", exc_info=True)


# ---------------------------------------------------------------------------
# 端點一：GET /api/tag-blacklist — 列出黑名單
# ---------------------------------------------------------------------------

@router.get("")
def list_blacklist():
    """列出黑名單字、建議字與有效隱藏集（正規化鍵，已排序）"""
    try:
        init_db()
        repo = TagBlacklistRepository()
        items = repo.get_all()
        ctx = load_context()
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "items": items,
                "suggestions": list(COMMON_BLACKLIST_SUGGESTIONS),
                "hidden": sorted(ctx.hidden),
            },
        )
    except Exception:
        logger.exception("[tag_blacklist] list_blacklist 失敗")
        return JSONResponse(status_code=500, content={"success": False, "error": "操作失敗"})


# ---------------------------------------------------------------------------
# 端點二：POST /api/tag-blacklist — 新增黑名單字
# ---------------------------------------------------------------------------

@router.post("")
def create_blacklist_entry(req: CreateBlacklistRequest):
    """
    新增黑名單字，寫入的是 strip 後的原字。

    失敗 code：empty、invalid、cover_badge → 400；duplicate → 409。
    error response 固定中文，不洩漏例外訊息。
    """
    try:
        init_db()
    except Exception:
        logger.exception("[tag_blacklist] create_blacklist_entry 失敗")
        return JSONResponse(status_code=500, content={"success": False, "error": "操作失敗"})
    name = req.name.strip()
    if not name:
        return JSONResponse(status_code=400, content={"success": False, "code": "empty"})
    if "," in name:
        return JSONResponse(status_code=400, content={"success": False, "code": "invalid"})
    if len(name) > 40:
        return JSONResponse(status_code=400, content={"success": False, "code": "invalid"})
    try:
        alias_groups = [[r.primary_name, *r.aliases] for r in TagAliasRepository().get_all()]
        probe = build_context([name], alias_groups)
    except Exception:
        logger.exception("[tag_blacklist] create_blacklist_entry 失敗")
        return JSONResponse(status_code=500, content={"success": False, "error": "操作失敗"})
    if not is_hidden_tag(name, probe):
        return JSONResponse(status_code=400, content={"success": False, "code": "cover_badge"})
    try:
        repo = TagBlacklistRepository()
        repo.add(name)
        _invalidate_caches()
        items = repo.get_all()
        return JSONResponse(status_code=200, content={"success": True, "items": items})
    except ValueError:
        return JSONResponse(status_code=409, content={"success": False, "code": "duplicate"})
    except Exception:
        logger.exception("[tag_blacklist] create_blacklist_entry 失敗")
        return JSONResponse(status_code=500, content={"success": False, "error": "操作失敗"})


# ---------------------------------------------------------------------------
# 端點三：DELETE /api/tag-blacklist/{name} — 刪除黑名單字
# ---------------------------------------------------------------------------

@router.delete("/{name:path}")
def delete_blacklist_entry(name: str):
    """
    依 key 刪除黑名單字。不存在也回 200（冪等）。
    """
    try:
        init_db()
        repo = TagBlacklistRepository()
        removed = repo.remove(name)
        if removed:
            logger.info("[tag_blacklist] 刪除：%s", name)
        _invalidate_caches()
        return JSONResponse(status_code=200, content={"success": True})
    except Exception:
        logger.exception("[tag_blacklist] delete_blacklist_entry 失敗")
        return JSONResponse(status_code=500, content={"success": False, "error": "操作失敗"})
