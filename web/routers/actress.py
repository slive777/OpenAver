"""
女優 API Router — /api/actresses

端點：
    POST   /api/actresses/favorite          收藏女優
    GET    /api/actresses/photo/{name}      取得本地照片（binary）
    GET    /api/actresses/{name}            查詢已收藏女優
    DELETE /api/actresses/{name}            刪除已收藏女優

注意：photo/{name} 必須定義在 {name} 之前，否則 FastAPI 會將 "photo" 解析為 {name}。
"""

import re
from typing import Optional, List
from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from core.maker_mapping import load_prefix_mapping

from core.database import ActressRepository, Actress, init_db
from core.actress_photo import download_actress_photo, get_local_photo_path, delete_local_photo
from core.scrapers.actress.orchestrator import (
    get_cached_profile,
    get_actress_profile,
    _compute_age_from_birth as _compute_age,
)
from core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/actresses", tags=["actresses"])


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------

class FavoriteRequest(BaseModel):
    name: str
    makers: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _safe_int(v) -> Optional[int]:
    """帶單位字串（如 '80cm'）或 None → int 或 None"""
    if v is None:
        return None
    try:
        stripped = re.sub(r"[^\d]", "", str(v))
        return int(stripped) if stripped else None
    except (ValueError, TypeError):
        return None


def _flatten_aliases(raw) -> list:
    """
    將 aliases 欄位統一轉為純字串 list。

    minnano scraper 回傳 dict list（每筆含 ja/hiragana/romaji），
    wiki scraper 回傳純字串 list。
    前端需要純字串 list，此 helper 統一兩種格式。

    Args:
        raw: list of dict | list of str | None

    Returns:
        list of str（空 list 若 raw 為 None 或 []）
    """
    if not raw:
        return []
    return [a.get("ja", "") if isinstance(a, dict) else str(a) for a in raw]


def _actress_to_response(actress: Actress, video_count: int = 0) -> dict:
    """將 Actress dataclass 轉為 API response dict"""
    local_path = get_local_photo_path(actress.name)
    if local_path is not None:
        photo_url = f"/api/actresses/photo/{quote(actress.name)}"
    else:
        photo_url = None

    return {
        "name": actress.name,
        "name_en": actress.name_en,
        "birth": actress.birth,
        "age": _compute_age(actress.birth),
        "height": actress.height,
        "cup": actress.cup,
        "bust": actress.bust,
        "waist": actress.waist,
        "hip": actress.hip,
        "hometown": actress.hometown,
        "hobby": actress.hobby,
        "aliases": actress.aliases or [],
        "agency": actress.agency,
        "debut_work": actress.debut_work,
        "tags": actress.tags or [],
        "nickname": actress.nickname,
        "blog_url": actress.blog_url,
        "official_url": actress.official_url,
        "photo_url": photo_url,
        "photo_source": actress.photo_source,
        "primary_text_source": actress.primary_text_source,
        "created_at": actress.created_at.isoformat() if actress.created_at else None,
        "video_count": video_count,
        "is_favorite": True,
    }


# ---------------------------------------------------------------------------
# 端點一：POST /api/actresses/favorite — 收藏女優
# ---------------------------------------------------------------------------

@router.post("/favorite")
def add_favorite(req: FavoriteRequest):
    """
    收藏女優。

    流程：
    1. 檢查是否已收藏 → 409
    2. 嘗試從 cache 取得 profile（不打網路）
    3. cache miss → 呼叫 orchestrator 重新抓取
    4. 組裝 Actress → DB save → 下載照片
    5. 回傳 200 with actress data
    """
    name = req.name.strip()
    if not name:
        return JSONResponse(
            status_code=422,
            content={"error": "invalid_name", "message": "name 不可為空"}
        )

    init_db()
    repo = ActressRepository()

    # 1. 已收藏檢查 → 409
    if repo.exists(name):
        existing = repo.get_by_name(name)
        return JSONResponse(
            status_code=409,
            content={
                "error": "already_exists",
                "actress": _actress_to_response(existing),
            }
        )

    # 2. 番號前綴 → 片商名轉換（前端傳 SSIS，gfriends 需要 S1）
    resolved_makers = None
    if req.makers:
        prefix_map = load_prefix_mapping()
        seen = set()
        ordered = []
        for p in req.makers:
            maker = prefix_map.get(p.upper())
            if maker and maker not in seen:
                seen.add(maker)
                ordered.append(maker)
        resolved_makers = ordered or None

    # 3. cache hit — 不打網路
    profile = get_cached_profile(name)

    # 4. cache miss → 重新抓取
    if profile is None:
        result = get_actress_profile(name, makers=resolved_makers)
        if result.data is None:
            if result.timed_out:
                return JSONResponse(
                    status_code=504,
                    content={"error": "timeout", "message": "Scraper 超時"}
                )
            else:
                return JSONResponse(
                    status_code=404,
                    content={"error": "not_found", "message": "查無此女優"}
                )
        profile = result.data

    # 4. 組裝 Actress dataclass
    text = profile.get("text") or {}

    actress = Actress(
        name=profile.get("name") or name,
        name_en=profile.get("name_en"),
        birth=text.get("birth"),
        height=text.get("height"),
        cup=text.get("cup"),
        bust=_safe_int(text.get("bust")),
        waist=_safe_int(text.get("waist")),
        hip=_safe_int(text.get("hip")),
        hometown=text.get("hometown"),
        hobby=text.get("hobby"),
        aliases=_flatten_aliases(text.get("aliases")),
        agency=text.get("agency"),
        debut_work=text.get("debut_work"),
        tags=text.get("tags") or [],
        nickname=text.get("nickname"),
        blog_url=text.get("blog_url"),
        official_url=text.get("official_url"),
        photo_source=profile.get("photo_source"),
        primary_text_source=profile.get("primary_text_source"),
    )

    # DB save（ON CONFLICT DO UPDATE）
    repo.save(actress)
    logger.info("[actress] 收藏女優：%s", actress.name)

    # 5. 下載照片（photo_url 可能為 None，函數內部已有 guard）
    photo_downloaded = download_actress_photo(
        actress.name, profile.get("photo_url"), profile.get("photo_source")
    )

    video_count = repo.count_videos_for_actress(actress.name)
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "actress": _actress_to_response(actress, video_count),
            "photo_downloaded": photo_downloaded,
        }
    )


# ---------------------------------------------------------------------------
# 端點四：GET /api/actresses/photo/{name} — 本地照片 binary response
# NOTE：必須定義在 GET /{name} 之前！
# ---------------------------------------------------------------------------

@router.get("/photo/{name}")
def get_actress_photo(name: str):
    """
    取得女優本地照片（binary image response）。
    FastAPI 自動 decode URL-encoded path parameter。
    """
    path = get_local_photo_path(name)
    if path is None:
        return Response(b"", status_code=404)

    _MIME_MAP = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif",
    }
    media_type = _MIME_MAP.get(path.suffix.lower(), "image/jpeg")

    return Response(
        content=path.read_bytes(),
        media_type=media_type,
    )


# ---------------------------------------------------------------------------
# 端點五：GET /api/actresses — 列出所有已收藏女優（含 video_count）
# NOTE：必須定義在 GET /{name} 之前！
# ---------------------------------------------------------------------------

@router.get("")
def list_actresses():
    """
    列出所有已收藏女優，每筆含 video_count 和 created_at。
    """
    init_db()
    repo = ActressRepository()
    actresses = repo.get_all()
    result = []
    for actress in actresses:
        video_count = repo.count_videos_for_actress(actress.name)
        result.append(_actress_to_response(actress, video_count))
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "actresses": result,
            "total": len(result),
        }
    )


# ---------------------------------------------------------------------------
# 端點六：POST /api/actresses/{name}/rescrape — 強制重抓女優資料
# ---------------------------------------------------------------------------

@router.post("/{name}/rescrape")
def rescrape_actress(name: str):
    """
    強制重抓女優資料（bypass cache），覆蓋 DB + 照片。
    name 不在 DB 時允許（直接 scrape + save 等同新增）。
    """
    init_db()
    repo = ActressRepository()

    result = get_actress_profile(name)

    if result.timed_out:
        return JSONResponse(
            status_code=504,
            content={"error": "timeout"}
        )

    if result.data is None:
        return JSONResponse(
            status_code=404,
            content={"error": "not_found"}
        )

    profile = result.data
    text = profile.get("text") or {}

    actress = Actress(
        name=profile.get("name") or name,
        name_en=profile.get("name_en"),
        birth=text.get("birth"),
        height=text.get("height"),
        cup=text.get("cup"),
        bust=_safe_int(text.get("bust")),
        waist=_safe_int(text.get("waist")),
        hip=_safe_int(text.get("hip")),
        hometown=text.get("hometown"),
        hobby=text.get("hobby"),
        aliases=_flatten_aliases(text.get("aliases")),
        agency=text.get("agency"),
        debut_work=text.get("debut_work"),
        tags=text.get("tags") or [],
        nickname=text.get("nickname"),
        blog_url=text.get("blog_url"),
        official_url=text.get("official_url"),
        photo_source=profile.get("photo_source"),
        primary_text_source=profile.get("primary_text_source"),
    )

    repo.save(actress)
    logger.info("[actress] 重抓女優資料：%s", actress.name)

    photo_downloaded = download_actress_photo(
        actress.name, profile.get("photo_url"), profile.get("photo_source")
    )

    video_count = repo.count_videos_for_actress(actress.name)
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "actress": _actress_to_response(actress, video_count),
            "photo_downloaded": photo_downloaded,
        }
    )


# ---------------------------------------------------------------------------
# 端點二：GET /api/actresses/{name} — 查詢已收藏女優
# ---------------------------------------------------------------------------

@router.get("/{name}")
def get_actress(name: str):
    """
    查詢已收藏的女優資料。
    """
    init_db()
    repo = ActressRepository()
    actress = repo.get_by_name(name)
    if actress is None:
        return JSONResponse(
            status_code=404,
            content={"error": "not_found"}
        )

    return JSONResponse(
        status_code=200,
        content={
            "actress": _actress_to_response(actress),
            "is_favorite": True,
        }
    )


# ---------------------------------------------------------------------------
# 端點三：DELETE /api/actresses/{name} — 刪除已收藏女優
# ---------------------------------------------------------------------------

@router.delete("/{name}")
def delete_actress(name: str):
    """
    刪除已收藏的女優（DB + 本地照片）。
    """
    init_db()
    repo = ActressRepository()

    if not repo.exists(name):
        return JSONResponse(
            status_code=404,
            content={"error": "not_found"}
        )

    repo.delete_by_name(name)
    delete_local_photo(name)  # idempotent，不需檢查回傳值
    logger.info("[actress] 刪除女優：%s", name)

    return JSONResponse(
        status_code=200,
        content={"success": True}
    )
