"""
女優 API Router — /api/actresses

端點：
    POST   /api/actresses/favorite          收藏女優
    GET    /api/actresses/photo/{name}      取得本地照片（binary）
    GET    /api/actresses/{name}            查詢已收藏女優
    DELETE /api/actresses/{name}            刪除已收藏女優

注意：photo/{name} 必須定義在 {name} 之前，否則 FastAPI 會將 "photo" 解析為 {name}。
"""

import asyncio
import json
import random
import re
from typing import Optional, List
from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel
from core.maker_mapping import load_prefix_mapping

from core.database import ActressRepository, AliasRepository, VideoRepository, Actress, init_db
from core.actress_photo import download_actress_photo, get_local_photo_path, delete_local_photo, crop_video_cover
from core.path_utils import to_file_uri
from core.scrapers.actress.orchestrator import (
    get_cached_profile,
    get_actress_profile,
    _compute_age_from_birth as _compute_age,
    _cache as _actress_cache,
    _normalize_name as _normalize_actress_name,
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
    actress = repo.get_by_name(actress.name) or actress  # re-read for created_at
    logger.info("[actress] 收藏女優：%s", actress.name)

    # Sync aliases to actress_aliases table
    try:
        alias_repo = AliasRepository()
        sync_result = alias_repo.sync_from_favorite(
            actress.name, actress.aliases or []
        )
        skipped_aliases = sync_result.get("skipped_aliases", [])
        if skipped_aliases:
            logger.warning("[actress] alias sync skipped: %s", skipped_aliases)
    except Exception as e:
        logger.warning("[actress] alias sync failed (non-blocking): %s", e)
        skipped_aliases = []

    # 5. 下載照片（photo_url 可能為 None，函數內部已有 guard）
    photo_downloaded = download_actress_photo(
        actress.name, profile.get("photo_url"), profile.get("photo_source")
    )

    alias_repo = AliasRepository()
    video_count = repo.count_videos_for_actress_names(alias_repo.resolve(actress.name))
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "actress": _actress_to_response(actress, video_count),
            "photo_downloaded": photo_downloaded,
            "skipped_aliases": skipped_aliases,
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
    alias_repo = AliasRepository()
    actresses = repo.get_all()
    result = []
    for actress in actresses:
        video_count = repo.count_videos_for_actress_names(alias_repo.resolve(actress.name))
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
# Helper functions for photo-candidates SSE endpoint
# 注意：必須放 module-level，不可嵌套在 generator 內
# ---------------------------------------------------------------------------

def _fetch_single_source(name: str, source: str) -> Optional[str]:
    """
    從指定雲端來源抓取女優照片 URL。
    同步函數（用 asyncio.to_thread 呼叫）。

    Returns:
        URL str 或 None
    """
    try:
        if source == "graphis":
            from core.scrapers.actress.graphis import scrape_graphis_photo
            r = scrape_graphis_photo(name)
            return r.get("prof_url") if r else None
        elif source == "gfriends":
            from core.scrapers.actress.gfriends import lookup_gfriends
            return lookup_gfriends(name, None)
        elif source == "wiki":
            from core.scrapers.actress.wiki_ja import scrape_wiki_ja
            r = scrape_wiki_ja(name)
            return r.get("photo_url") if r else None
        elif source == "minnano":
            from core.scrapers.actress.minnano_av import scrape_minnano_av
            r = scrape_minnano_av(name)
            return r.get("photo_url") if r else None
        else:
            return None
    except Exception as e:
        logger.warning("[actress] _fetch_single_source 失敗 source=%s: %s", source, e)
        return None


def _get_random_videos_with_covers(actress_name: str, count: int) -> list:
    """
    取得女優隨機影片（有封面的）。

    Returns:
        Video list（最多 count 筆，有 cover_path 且非空）
    """
    try:
        init_db()
        repo = VideoRepository()
        videos = repo.get_videos_by_actress(actress_name)
        with_covers = [v for v in videos if v.cover_path]
        random.shuffle(with_covers)
        return with_covers[:count]
    except Exception as e:
        logger.warning("[actress] _get_random_videos_with_covers 失敗: %s", e)
        return []


# ---------------------------------------------------------------------------
# 端點七：GET /api/actresses/{name}/photo-candidates — SSE 候選照片串流
# NOTE：必須定義在 GET /{name} 之前！
# ---------------------------------------------------------------------------

@router.get("/{name}/photo-candidates")
async def list_photo_candidates(name: str):
    """
    SSE 串流回傳女優候選照片（最多 6 張）。
    雲端 0–3 張並行抓取 + 本機影片封面 crop 補足至 6 張。
    actress 不存在 → JSONResponse 404。
    """
    init_db()
    repo = ActressRepository()
    actress = repo.get_by_name(name)
    if actress is None:
        return JSONResponse(
            status_code=404,
            content={"error": "not_found"}
        )

    current_source = actress.photo_source
    cloud_sources = [s for s in ["graphis", "gfriends", "wiki", "minnano"] if s != current_source]

    async def generate():
        total = 0
        max_cloud = 3

        # 雲端並行抓取
        async def fetch_source(src: str):
            try:
                url = await asyncio.wait_for(
                    asyncio.to_thread(_fetch_single_source, name, src),
                    timeout=5.0,
                )
                return (src, url)
            except Exception:
                return (src, None)

        tasks = [asyncio.ensure_future(fetch_source(src)) for src in cloud_sources]
        if tasks:
            done_set, _ = await asyncio.wait(tasks, return_when=asyncio.ALL_COMPLETED)
            for task in done_set:
                src, url = task.result()
                if url and total < max_cloud:
                    event_data = json.dumps({
                        "source": src,
                        "thumb_url": url,
                        "full_url": url,
                    })
                    yield f"event: candidate\ndata: {event_data}\n\n"
                    total += 1

        # 本機 crop 補足
        needed = 6 - total
        if needed > 0:
            local_videos = await asyncio.to_thread(
                _get_random_videos_with_covers, name, needed
            )
            for video in local_videos:
                cover_path_str = str(video.cover_path)
                encoded_path = quote(cover_path_str)
                crop_url = f"/api/actresses/actress-crop?path={encoded_path}&spec=v1"
                try:
                    video_path_uri = to_file_uri(str(video.path))
                except Exception as e:
                    logger.warning("[actress] to_file_uri 轉換失敗 path=%s: %s", video.path, e)
                    video_path_uri = str(video.path)
                event_data = json.dumps({
                    "source": "local_crop",
                    "video_path": video_path_uri,
                    "thumb_url": crop_url,
                    "full_url": crop_url,
                })
                yield f"event: candidate\ndata: {event_data}\n\n"
                total += 1

        # done event
        done_data = json.dumps({"total": total})
        yield f"event: done\ndata: {done_data}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# 端點八：GET /api/actresses/actress-crop — on-demand 封面 crop
# NOTE：必須定義在 GET /{name} 之前！
# ---------------------------------------------------------------------------

@router.get("/actress-crop")
async def actress_crop(path: str, spec: str = "v1"):
    """
    對指定本機封面圖做 crop，回傳 JPEG bytes。
    path: 本機 FS 路徑（URL-encoded）
    spec: crop 規格版本（預設 v1）
    """
    result = await asyncio.to_thread(crop_video_cover, path, spec)
    if result is None:
        return Response(b"", status_code=404)
    return Response(content=result, media_type="image/jpeg")


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

    # P1 fix: bypass cache — evict before scraping
    _actress_cache.pop(_normalize_actress_name(name), None)
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
    actress = repo.get_by_name(actress.name) or actress  # re-read for created_at
    logger.info("[actress] 重抓女優資料：%s", actress.name)

    photo_downloaded = download_actress_photo(
        actress.name, profile.get("photo_url"), profile.get("photo_source")
    )

    # P1 Codex fix: rescrape 後同步 alias index（與 add_favorite 同 pattern）
    alias_repo = AliasRepository()
    try:
        alias_repo.sync_from_favorite(actress.name, actress.aliases or [])
    except Exception:
        logger.warning("[actress] rescrape alias sync failed: %s", actress.name)
    video_count = repo.count_videos_for_actress_names(alias_repo.resolve(actress.name))
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
