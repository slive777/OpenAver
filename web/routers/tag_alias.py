"""
Tag 別名 API Router — /api/tag-aliases

端點（按 FastAPI 路由解析順序定義）：
    GET    /api/tag-aliases                       列出所有別名組
    POST   /api/tag-aliases                       新增別名組
    GET    /api/tag-aliases/{name}                查單一別名組（primary 或 alias 查）
    DELETE /api/tag-aliases/{name}                刪除別名組
    POST   /api/tag-aliases/{name}/alias          為 group 新增 alias
    DELETE /api/tag-aliases/{name}/alias/{alias}  移除單一 alias

注意：無 search-online 端點（CD-58-4）。
衝突回 409（CD-58-9）；error response 固定中文，不 leak str(exc)（CD-58-14）。
"""

from typing import List

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from core.database import TagAliasRepository, init_db
from core.logger import get_logger
from core.similar import canonicalize as _canonicalize_module
from core.similar.ranker_cache import SimilarRankerCache

logger = get_logger(__name__)

router = APIRouter(prefix="/api/tag-aliases", tags=["tag-aliases"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class CreateAliasRequest(BaseModel):
    primary_name: str
    aliases: List[str] = []

    @field_validator("primary_name")
    @classmethod
    def primary_name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("primary_name 不可為空")
        return v.strip()

    @field_validator("aliases")
    @classmethod
    def strip_aliases(cls, v: List[str]) -> List[str]:
        return [a.strip() for a in v if a.strip()]


class AddAliasRequest(BaseModel):
    alias: str

    @field_validator("alias")
    @classmethod
    def alias_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("alias 不可為空")
        return v.strip()


# ---------------------------------------------------------------------------
# Helper — TagAliasRecord → response dict
# ---------------------------------------------------------------------------

def _record_to_dict(record) -> dict:
    """將 TagAliasRecord 序列化為 API response dict"""
    return {
        "primary_name": record.primary_name,
        "aliases": record.aliases,
        "source": record.source,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


# ---------------------------------------------------------------------------
# 端點一：GET /api/tag-aliases — 列出所有別名組
# ---------------------------------------------------------------------------

@router.get("")
def list_aliases():
    """列出所有 tag 別名組，依 primary_name 排序"""
    try:
        init_db()
        repo = TagAliasRepository()
        records = repo.get_all()
        groups = [_record_to_dict(r) for r in records]
        return JSONResponse(
            status_code=200,
            content={"success": True, "groups": groups, "total": len(groups)},
        )
    except Exception:
        logger.exception("[tag_alias] list_aliases 失敗")
        return JSONResponse(status_code=500, content={"success": False, "error": "操作失敗"})


# ---------------------------------------------------------------------------
# 端點二：POST /api/tag-aliases — 新增別名組
# ---------------------------------------------------------------------------

@router.post("")
def create_alias_group(req: CreateAliasRequest):
    """
    新增 tag 別名組。

    primary_name 或 aliases 有衝突 → 409（CD-58-9）。
    error response 固定中文，不 leak str(exc)（CD-58-14）。
    """
    try:
        init_db()
        repo = TagAliasRepository()
        record = repo.add(req.primary_name, req.aliases)
        logger.info("[tag_alias] 新增 group：%s", req.primary_name)
        _canonicalize_module._invalidate_cache()
        try:
            SimilarRankerCache.invalidate()
        except Exception:
            logger.warning("[tag_alias] SimilarRankerCache.invalidate 失敗，不影響寫入", exc_info=True)
        return JSONResponse(
            status_code=200,
            content={"success": True, "group": _record_to_dict(record)},
        )
    except ValueError:
        return JSONResponse(
            status_code=409,
            content={"success": False, "error": "Tag 別名衝突（名字已屬其他組）"},
        )
    except Exception:
        logger.exception("[tag_alias] create_alias_group 失敗")
        return JSONResponse(status_code=500, content={"success": False, "error": "操作失敗"})


# ---------------------------------------------------------------------------
# 端點三：GET /api/tag-aliases/{name} — 查單一別名組
# ---------------------------------------------------------------------------

@router.get("/{name}")
def get_alias_group(name: str):
    """
    查詢 tag 別名組。先以 primary_name 查，miss 再以 alias 查。
    兩者皆 miss → 404。
    """
    try:
        init_db()
        repo = TagAliasRepository()
        record = repo.get_by_primary(name)
        if record is None:
            record = repo.find_by_alias(name)
        if record is None:
            return JSONResponse(status_code=404, content={"error": "not_found"})
        return JSONResponse(
            status_code=200,
            content={"success": True, "group": _record_to_dict(record)},
        )
    except Exception:
        logger.exception("[tag_alias] get_alias_group 失敗")
        return JSONResponse(status_code=500, content={"success": False, "error": "操作失敗"})


# ---------------------------------------------------------------------------
# 端點四：DELETE /api/tag-aliases/{name} — 刪除別名組
# ---------------------------------------------------------------------------

@router.delete("/{name}")
def delete_alias_group(name: str):
    """
    刪除 tag 別名組。name 可為 primary 或 alias（repo 內部 resolve）。
    不存在 → 404。
    """
    try:
        init_db()
        repo = TagAliasRepository()
        deleted = repo.delete(name)
        if not deleted:
            return JSONResponse(status_code=404, content={"error": "not_found"})
        logger.info("[tag_alias] 刪除 group：%s", name)
        _canonicalize_module._invalidate_cache()
        try:
            SimilarRankerCache.invalidate()
        except Exception:
            logger.warning("[tag_alias] SimilarRankerCache.invalidate 失敗，不影響寫入", exc_info=True)
        return JSONResponse(status_code=200, content={"success": True})
    except Exception:
        logger.exception("[tag_alias] delete_alias_group 失敗")
        return JSONResponse(status_code=500, content={"success": False, "error": "操作失敗"})


# ---------------------------------------------------------------------------
# 端點五：POST /api/tag-aliases/{name}/alias — 為 group 新增 alias
# ---------------------------------------------------------------------------

@router.post("/{name}/alias")
def add_alias(name: str, req: AddAliasRequest):
    """
    為既有 tag group 新增一個 alias。

    {name} 只接受 primary_name（不做 resolve），避免歧義。
    group 不存在 → 404；alias 衝突 → 409（CD-58-9）。
    error response 固定中文，不 leak repo 的內部 msg（CD-58-14）。
    """
    try:
        init_db()
        repo = TagAliasRepository()

        # 先確認 group 存在
        record = repo.get_by_primary(name)
        if record is None:
            return JSONResponse(status_code=404, content={"error": "not_found"})

        ok, _msg = repo.add_alias(name, req.alias)
        if not ok:
            return JSONResponse(
                status_code=409,
                content={"success": False, "error": "Tag 別名衝突（名字已屬其他組）"},
            )

        # re-read record
        updated = repo.get_by_primary(name)
        logger.info("[tag_alias] 新增 alias：%s → %s", name, req.alias)
        _canonicalize_module._invalidate_cache()
        try:
            SimilarRankerCache.invalidate()
        except Exception:
            logger.warning("[tag_alias] SimilarRankerCache.invalidate 失敗，不影響寫入", exc_info=True)
        return JSONResponse(
            status_code=200,
            content={"success": True, "group": _record_to_dict(updated)},
        )
    except Exception:
        logger.exception("[tag_alias] add_alias 失敗")
        return JSONResponse(status_code=500, content={"success": False, "error": "操作失敗"})


# ---------------------------------------------------------------------------
# 端點六：DELETE /api/tag-aliases/{name}/alias/{alias} — 移除單一 alias
# ---------------------------------------------------------------------------

@router.delete("/{name}/alias/{alias}")
def remove_alias(name: str, alias: str):
    """
    從 tag group 中移除一個 alias。

    {name} 只接受 primary_name。
    group 不存在 → 404；alias 不在 group → 404 error=alias_not_found。
    """
    try:
        init_db()
        repo = TagAliasRepository()

        # 先確認 group 存在
        record = repo.get_by_primary(name)
        if record is None:
            return JSONResponse(status_code=404, content={"error": "not_found"})

        removed = repo.remove_alias(name, alias)
        if not removed:
            return JSONResponse(status_code=404, content={"error": "alias_not_found"})

        logger.info("[tag_alias] 移除 alias：%s ← %s", name, alias)
        _canonicalize_module._invalidate_cache()
        try:
            SimilarRankerCache.invalidate()
        except Exception:
            logger.warning("[tag_alias] SimilarRankerCache.invalidate 失敗，不影響寫入", exc_info=True)
        return JSONResponse(status_code=200, content={"success": True})
    except Exception:
        logger.exception("[tag_alias] remove_alias 失敗")
        return JSONResponse(status_code=500, content={"success": False, "error": "操作失敗"})
