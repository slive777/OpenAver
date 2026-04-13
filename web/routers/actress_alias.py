"""
女優別名 API Router — /api/actress-aliases

端點（按 FastAPI 路由解析順序定義）：
    GET    /api/actress-aliases                       列出所有別名組
    POST   /api/actress-aliases/search-online         線上搜尋建議別名（靜態路徑，必須在 /{name} 之前）
    POST   /api/actress-aliases                       新增別名組
    GET    /api/actress-aliases/{name}                查單一別名組（primary 或 alias 查）
    DELETE /api/actress-aliases/{name}                刪除別名組
    POST   /api/actress-aliases/{name}/alias          為 group 新增 alias
    DELETE /api/actress-aliases/{name}/alias/{alias}  移除單一 alias

注意：search-online 靜態路徑必須定義在 /{name} 動態路徑之前，
否則 FastAPI 會將 "search-online" 解析為 {name}。
"""

from typing import List, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from core.database import AliasRepository, init_db
from core.scrapers.actress.orchestrator import get_actress_profile
from core.logger import get_logger
from web.routers.actress import _flatten_aliases

logger = get_logger(__name__)

router = APIRouter(prefix="/api/actress-aliases", tags=["actress-aliases"])


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


class SearchOnlineRequest(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("name 不可為空")
        return v


# ---------------------------------------------------------------------------
# Helper — AliasRecord → response dict
# ---------------------------------------------------------------------------

def _record_to_dict(record) -> dict:
    """將 AliasRecord 序列化為 API response dict"""
    return {
        "primary_name": record.primary_name,
        "aliases": record.aliases,
        "source": record.source,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


# ---------------------------------------------------------------------------
# 端點一：GET /api/actress-aliases — 列出所有別名組
# ---------------------------------------------------------------------------

@router.get("")
def list_aliases():
    """列出所有別名組，依 primary_name 排序"""
    init_db()
    repo = AliasRepository()
    records = repo.get_all()
    groups = [_record_to_dict(r) for r in records]
    return JSONResponse(
        status_code=200,
        content={"success": True, "groups": groups, "total": len(groups)},
    )


# ---------------------------------------------------------------------------
# 端點七：POST /api/actress-aliases/search-online — 線上搜尋建議別名
# NOTE：靜態片段，必須定義在 /{name} 動態路徑之前
# ---------------------------------------------------------------------------

@router.post("/search-online")
def search_alias_online(req: SearchOnlineRequest):
    """
    呼叫 orchestrator 搜尋女優，從 profile 提取建議別名。

    回傳：
        200 + suggested_aliases（可空 list）
        200 + message 若查無此女優
        504 若 scraper 超時
    """
    result = get_actress_profile(req.name)

    if result.timed_out:
        logger.warning("[actress_alias] search-online timeout：%s", req.name)
        return JSONResponse(
            status_code=504,
            content={"error": "timeout", "message": "Scraper 超時"},
        )

    if result.data is None:
        logger.info("[actress_alias] search-online 查無：%s", req.name)
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "name": req.name,
                "suggested_aliases": [],
                "message": "查無此女優",
            },
        )

    raw_aliases = result.data.get("text", {}).get("aliases")
    suggested = _flatten_aliases(raw_aliases)
    logger.info("[actress_alias] search-online 成功：%s → %d 個建議", req.name, len(suggested))
    return JSONResponse(
        status_code=200,
        content={"success": True, "name": req.name, "suggested_aliases": suggested},
    )


# ---------------------------------------------------------------------------
# 端點三：POST /api/actress-aliases — 新增別名組
# ---------------------------------------------------------------------------

@router.post("")
def create_alias_group(req: CreateAliasRequest):
    """
    新增別名組。

    primary_name 或 aliases 有衝突 → 400。
    """
    init_db()
    repo = AliasRepository()
    try:
        record = repo.add(req.primary_name, req.aliases)
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": str(exc)},
        )
    logger.info("[actress_alias] 新增 group：%s", req.primary_name)
    return JSONResponse(
        status_code=200,
        content={"success": True, "group": _record_to_dict(record)},
    )


# ---------------------------------------------------------------------------
# 端點二：GET /api/actress-aliases/{name} — 查單一別名組
# ---------------------------------------------------------------------------

@router.get("/{name}")
def get_alias_group(name: str):
    """
    查詢別名組。先以 primary_name 查，miss 再以 alias 查。
    兩者皆 miss → 404。
    """
    init_db()
    repo = AliasRepository()
    record = repo.get_by_primary(name)
    if record is None:
        record = repo.find_by_alias(name)
    if record is None:
        return JSONResponse(status_code=404, content={"error": "not_found"})
    return JSONResponse(
        status_code=200,
        content={"success": True, "group": _record_to_dict(record)},
    )


# ---------------------------------------------------------------------------
# 端點四：DELETE /api/actress-aliases/{name} — 刪除別名組
# ---------------------------------------------------------------------------

@router.delete("/{name}")
def delete_alias_group(name: str):
    """
    刪除別名組。name 可為 primary 或 alias（repo 內部 resolve）。
    不存在 → 404。
    """
    init_db()
    repo = AliasRepository()
    deleted = repo.delete(name)
    if not deleted:
        return JSONResponse(status_code=404, content={"error": "not_found"})
    logger.info("[actress_alias] 刪除 group：%s", name)
    return JSONResponse(status_code=200, content={"success": True})


# ---------------------------------------------------------------------------
# 端點五：POST /api/actress-aliases/{name}/alias — 為 group 新增 alias
# NOTE：{name}/alias 必須在 /{name} 之後定義（FastAPI 以定義順序解析）
# ---------------------------------------------------------------------------

@router.post("/{name}/alias")
def add_alias(name: str, req: AddAliasRequest):
    """
    為既有 group 新增一個 alias。

    {name} 只接受 primary_name（不做 resolve），避免歧義。
    group 不存在 → 404；alias 衝突 → 400。
    """
    init_db()
    repo = AliasRepository()

    # 先確認 group 存在
    record = repo.get_by_primary(name)
    if record is None:
        return JSONResponse(status_code=404, content={"error": "not_found"})

    ok, msg = repo.add_alias(name, req.alias)
    if not ok:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": msg},
        )

    # re-read record
    updated = repo.get_by_primary(name)
    logger.info("[actress_alias] 新增 alias：%s → %s", name, req.alias)
    return JSONResponse(
        status_code=200,
        content={"success": True, "group": _record_to_dict(updated)},
    )


# ---------------------------------------------------------------------------
# 端點六：DELETE /api/actress-aliases/{name}/alias/{alias} — 移除單一 alias
# ---------------------------------------------------------------------------

@router.delete("/{name}/alias/{alias}")
def remove_alias(name: str, alias: str):
    """
    從 group 中移除一個 alias。

    {name} 只接受 primary_name。
    group 不存在 → 404；alias 不在 group → 404 error=alias_not_found。
    """
    init_db()
    repo = AliasRepository()

    # 先確認 group 存在
    record = repo.get_by_primary(name)
    if record is None:
        return JSONResponse(status_code=404, content={"error": "not_found"})

    removed = repo.remove_alias(name, alias)
    if not removed:
        return JSONResponse(status_code=404, content={"error": "alias_not_found"})

    logger.info("[actress_alias] 移除 alias：%s ← %s", name, alias)
    return JSONResponse(status_code=200, content={"success": True})
