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
import os
import random
import re
import tempfile
from io import BytesIO
from typing import Optional, List
from urllib.parse import quote

from fastapi import APIRouter, UploadFile, File
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel
from PIL import Image
from core.maker_mapping import load_prefix_mapping

from core.database import ActressRepository, AliasRepository, VideoRepository, Actress, init_db
from core.actress_photo import (
    download_actress_photo, get_local_photo_path, delete_local_photo,
    crop_video_cover, GFRIENDS_DIR, CONTENT_TYPE_MAP, validate_photo_url,
)
from core.focal import detect_focal, format_focal, parse_focal
from core.organizer import sanitize_filename
from core.path_utils import to_file_uri as to_file_uri, uri_to_fs_path, uri_to_local_fs_path, coerce_to_file_uri
from core.config import load_config
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


class SetActressPhotoRequest(BaseModel):
    source: str                          # "graphis"|"gfriends"|"wiki"|"minnano"|"local_crop"
    url: Optional[str] = None            # 雲端來源：照片 URL（必填）
    video_path: Optional[str] = None     # local_crop：影片 file:/// URI（必填）
    crop_spec: Optional[str] = "v1"      # local_crop：裁切規格（預設 v1）


class SetActressFocalRequest(BaseModel):
    """POST /{name}/focal body（TASK-100a-T4）：focal（'x.xxxx,y.xxxx' 格式字串）。

    CD-3：女優 focal 無背景 writer 會與此端點交錯寫入，`ActressRepository.
    update_manual_focal(name, focal)` 刻意不吃 compare token（對照
    video.py 的 `expected_cover_path`）——本 request model 亦不帶該欄位。
    """
    focal: str


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
        "auto_focal": actress.auto_focal,
        "crop_mode": actress.crop_mode,
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

    使用 AliasRepository.resolve 展開 alias set，以 get_videos_by_actress_names
    多名查詢，涵蓋所有 alias 標記的影片。無 alias 時 resolve 回 {actress_name}，
    行為等價舊版。雲端路徑不受影響（仍只用 primary name）。

    Returns:
        Video list（最多 count 筆，有 cover_path 且非空）
    """
    try:
        init_db()
        repo = VideoRepository()
        alias_repo = AliasRepository()
        names = list(alias_repo.resolve(actress_name))  # 雙向展開；無 alias 時回 {actress_name}
        videos = repo.get_videos_by_actress_names(names)
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
    _, actress = await asyncio.to_thread(_load_actress, name)
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

        if cloud_sources:
            tasks = [asyncio.ensure_future(fetch_source(src)) for src in cloud_sources]
            for coro in asyncio.as_completed(tasks):
                src, url = await coro
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
                # Fix 1 (T2): cover_path 在 DB 存 file:/// URI，crop endpoint 需要 FS path
                cover_fs_path = uri_to_fs_path(str(video.cover_path)) if video.cover_path else ""  # uri-no-reverse: URL identifier stays canonical; actress_crop reverse-maps at disk I/O
                if not cover_fs_path:
                    # skip broken candidate，避免送空路徑的 URL
                    continue
                encoded_path = quote(cover_fs_path)
                crop_url = f"/api/actresses/actress-crop?path={encoded_path}&spec=v1"
                # Fix 2 (T2): video.path 在 DB 已是 file:/// URI（gallery_scanner.scan_file 透過 to_file_uri 寫入）
                # 若萬一是 FS path（legacy / 異常），coerce_to_file_uri 做 idempotent 轉換
                try:
                    video_path_uri = coerce_to_file_uri(str(video.path))  # uri-no-reverse: coerce_to_file_uri forward URI build, D2 complement
                except Exception as e:
                    logger.warning("[actress] coerce_to_file_uri 失敗 path=%s: %s", video.path, e)
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

def _check_cover_path(fs_path: str) -> bool:
    """Threadpool helper: init DB + check cover path is known (防任意檔案讀取).

    db-ns-ok: enforced at callsites — 本體內 is_known_cover_path(fs_path) primitive sink
    命名空間正確性委派給呼叫端保證（TASK-91b-T1 wrapper sink 登記，callsite 各自標記）。
    """
    init_db()
    return VideoRepository().is_known_cover_path(fs_path)


def _load_actress(name: str):
    """Threadpool helper: init DB + load ActressRepository + fetch actress by name.

    Returns (repo, actress) tuple so the caller can reuse the same repo instance
    for repo.save() later, preserving original semantics.
    """
    init_db()
    repo = ActressRepository()
    return repo, repo.get_by_name(name)


def _get_actress_videos(name: str) -> list:
    """Threadpool helper: fetch videos for actress (init_db already ran in _load_actress)."""
    return VideoRepository().get_videos_by_actress(name)


def _write_actress_photo(name: str, crop_bytes: bytes, ext: str = ".jpg") -> None:
    """Threadpool helper: atomically write crop_bytes to GFRIENDS_DIR, replacing old files.

    Lock-free: same-actress concurrent writers are last-writer-wins (acceptable).
    清舊檔的 unlink(missing_ok=True) 吞掉 glob/unlink TOCTOU（併發寫者搶先刪掉同一
    殘檔＝良性競態，不該進 log）；外層 try/except 另吞 PermissionError 等（Windows
    檔案鎖，見下方 P2-B 註解）——兩者分工不同，缺一不可。temp+os.replace 避免
    torn reads（66b-T4b）。

    ext: 目標副檔名（含開頭 `.`，如 `.png`），預設 `.jpg` 保持既有 caller
    （set_actress_photo 的 local_crop 分支）行為不變。CD-5（TASK-100a-T2）：
    上傳端點依 PIL 驗出的真實格式傳入對應 ext，避免 PNG/WebP bytes 被存成
    `.jpg` 檔名導致 GET /photo/{name} 依副檔名查表回錯誤 MIME。
    """
    safe = sanitize_filename(name)
    GFRIENDS_DIR.mkdir(parents=True, exist_ok=True)
    dest = GFRIENDS_DIR / f"{safe}{ext}"
    fd, tmp = tempfile.mkstemp(dir=GFRIENDS_DIR, suffix=ext)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(crop_bytes)
        os.replace(tmp, dest)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    # 🔴 清舊檔必須在 os.replace 成功「之後」（TASK-100a-T2 review finding）：
    # 原本是先 glob 刪光 {safe}.* 再寫入 → 寫檔失敗時舊照片已經沒了，使用者的
    # 照片直接消失。而 spec-100 §3.3 的失敗矩陣（CD-4 pre-invalidate 的整個賣點）
    # 明文宣稱「寫檔失敗 → 舊圖 + 已清焦點 → 置中裁（輕微退化）」——先刪再寫讓
    # 那句話是假的。改成寫入成功後才清掉「其他副檔名」的殘檔（dest 本身除外），
    # 該承諾才成立：寫檔失敗 → 舊圖原封不動。
    # 成功路徑行為不變（最終仍只留 dest 一個檔），故既有 caller 不受影響。
    # 🔴 PR#108 Codex P2-B：清舊檔的每一支 unlink 各自包 try/except（不只吞
    # FileNotFoundError 的 missing_ok，還要吞 PermissionError 等）。Windows
    # 縮圖快取／防毒即時掃描持有舊副檔名檔的 handle 時 unlink 會拋
    # PermissionError；此時新圖已由上面的 os.replace 成功落地、_pre_invalidate_focal
    # 也已清完舊焦點——若讓例外往上拋，呼叫端會回 500，但新圖其實已經換好、只是
    # 清舊殘檔失敗，屬於 core/actress_photo.py:166-175 download_actress_photo 既有
    # warn-and-continue 缺的雙胞胎（該處已修，本函式當時漏補）。log 後繼續下一個
    # sibling 檔，不中斷、不上拋。missing_ok=True 保留在 try 內：良性 TOCTOU（併發
    # 寫者搶先刪掉同一殘檔）靜默通過、不留 warning log；try 只負責真異常（PermissionError）。
    for old in GFRIENDS_DIR.glob(f"{safe}.*"):
        if old != dest:
            try:
                old.unlink(missing_ok=True)
            except Exception as e:
                logger.warning(
                    "[actress] 清舊照片檔失敗 path=%s err=%s", old, e,
                )


async def _pre_invalidate_focal(repo: ActressRepository, name: str, *, ctx: str, err_msg: str):
    """🔴 CD-4 pre-invalidate（承重，spec-100 §3.3）：換主圖前先作廢舊焦點。

    三個「換掉女優主圖」的入口（upload／cloud 候選／local_crop 候選）共用同一段——
    刻意抽出而非各寫一份：三份逐字複製的 try/except 會漂移（改一份忘另一份），
    而這段是承重碼，漂移＝spec §3.3 的保證在某條路徑上悄悄失效。

    呼叫端一律：
        err = await _pre_invalidate_focal(repo, name, ctx="...", err_msg=...)
        if err:
            return err
        ...才可以安裝新圖

    Args:
        ctx: log 前綴用的情境名（"upload" / "set_photo"），只影響 log 不影響行為。
        err_msg: 失敗時回給前端的固定中文（CD-8：各端點沿用自己的字串）。

    Returns:
        失敗 → JSONResponse(500)，呼叫端必須直接 return 它、**絕不可繼續寫檔**；
        成功 → None。
    """
    try:
        cleared = await asyncio.to_thread(clear_focal, repo, name)
    except Exception:
        logger.exception("[actress] %s clear_focal 例外 name=%s", ctx, name)
        return JSONResponse(status_code=500, content={"error": err_msg})
    if not cleared:
        logger.warning("[actress] %s clear_focal 回 False name=%s", ctx, name)
        return JSONResponse(status_code=500, content={"error": err_msg})
    return None


async def _persist_photo_source(repo: ActressRepository, actress, source: str, *, ctx: str, err_msg: str):
    """CD-7：photo_source 持久化（換主圖的三個入口共用）。

    只回 response 不持久化 → 重載後顯示舊來源。`_ACTRESS_FOCAL_PRESERVE` 保住
    focal 五欄不被 save() 覆寫，故這裡 save() 不會踩掉 clear_focal 剛寫的值。

    **為何要 try/except**（Codex P2）：DB 寫入失敗若逸出 async 路由，Starlette 的
    預設 handler 會回**純文字 "Internal Server Error"**（`web/app.py` 只註冊了
    RequestValidationError handler、無 catch-all）——不是 JSON、更不是
    `AGENTS.md:33` 要求的固定中文。此時新圖已經安裝、photo_source 卻沒更新，
    使用者至少該拿到一個看得懂的錯誤。T4 的 set_actress_focal 本來就有這個
    guard，T2/T3 漏了——這是同一 branch 內部的不對稱，不是新規則。

    Returns:
        失敗 → JSONResponse(500)，呼叫端直接 return 它；成功 → None。
    """
    actress.photo_source = source
    try:
        await asyncio.to_thread(repo.save, actress)
    except Exception:
        logger.exception("[actress] %s photo_source 持久化失敗 name=%s", ctx, actress.name)
        return JSONResponse(status_code=500, content={"error": err_msg})
    return None


async def _photo_url_with_fp_cache_bust(name: str, *, ctx: str, err_msg: str):
    """CD-6 重解析 + CD-11 fp cache-bust——安裝新圖後產生 photo_url。

    同樣三個入口共用。CD-6：實體 path 隨真實格式改變（cloud 由 Content-Type 定、
    upload 由 PIL 驗出的格式定），故一律 `get_local_photo_path` 重解析，不可假設
    `{safe}.jpg`。CD-11：`?v={mtime_ns}-{size}`——秒級 `int(time.time())` 在同秒
    連續換圖會產生相同 URL、瀏覽器沿用舊圖。

    ⚠️ `st_mtime_ns` 的精度由檔案系統決定（實測 ext4 約 4ms），不是奈秒——
    見 gotchas-backend.md。production 的兩次操作間隔遠超 4ms，故無影響；
    但測試若背靠背打兩次會撞號。

    Returns:
        (photo_url, None) 成功；(None, JSONResponse(500)) 失敗，呼叫端直接 return 它。
    """
    photo_fs = await asyncio.to_thread(get_local_photo_path, name)
    if photo_fs is None:
        logger.error("[actress] %s 安裝新圖後重解析路徑失敗 name=%s", ctx, name)
        return None, JSONResponse(status_code=500, content={"error": err_msg})
    try:
        st = await asyncio.to_thread(photo_fs.stat)
    except OSError:
        logger.exception("[actress] %s stat 失敗 name=%s path=%s", ctx, name, photo_fs)
        return None, JSONResponse(status_code=500, content={"error": err_msg})
    return f"/api/actresses/photo/{quote(name)}?v={st.st_mtime_ns}-{st.st_size}", None


def clear_focal(repo: ActressRepository, name: str) -> bool:
    """Threadpool helper: repo.clear_focal(name) 轉呼叫（CD-4 pre-invalidate，TASK-100a-T2）。

    刻意用不帶底線的模組層級名稱 `clear_focal`（而非 `_clear_focal`）：讓測試可以
    直接 `patch('web.routers.actress.clear_focal', ...)` 模擬清焦點失敗/拋例外
    （gotchas-backend.md「測試 Mock Patch Target」#1：patch 使用端綁定，不是
    `core.database.actress.ActressRepository.clear_focal` 定義端）。
    """
    return repo.clear_focal(name)


@router.get("/actress-crop")
async def actress_crop(path: str, spec: str = "v1"):
    """
    對指定本機封面圖做 crop，回傳 JPEG bytes。
    path: 本機 FS 路徑（URL-encoded）；若傳入 file:/// URI 也接受（防禦性轉換）
    spec: crop 規格版本（預設 v1）
    """
    # Fix 2 (T2): uri_to_fs_path 已 idempotent（非 URI 直接 normalize_path），直接呼叫
    path_mappings = (await asyncio.to_thread(load_config)).get('gallery', {}).get('path_mappings', {})
    cover_fs_for_db = uri_to_fs_path(path)  # uri-no-reverse: DB round-trip (is_known_cover_path) must stay in DB namespace; disk crop uses reverse-mapped below  # db-ns-ok: _for_db, sourced from existing DB URI (uri_to_fs_path, not reverse-mapped), round-trips to mapped namespace
    fs_path = uri_to_local_fs_path(path, path_mappings)
    # Security: cover_path 必須是 DB 中某個 video 的 cover_path（防任意檔案讀取）
    allowed = await asyncio.to_thread(_check_cover_path, cover_fs_for_db)
    if not allowed:
        return Response(b"", status_code=403)
    result = await asyncio.to_thread(crop_video_cover, fs_path, spec)
    if result is None:
        return Response(b"", status_code=404)
    return Response(content=result, media_type="image/jpeg")


# ---------------------------------------------------------------------------
# 端點九：POST /api/actresses/{name}/photo — 設定女優照片
# NOTE：必須定義在 GET /{name} 之前！
# ---------------------------------------------------------------------------

CLOUD_SOURCES = {"graphis", "gfriends", "wiki", "minnano"}

# CD-8（AGENTS.md:33）：T3 在本端點新增的失敗路徑一律固定中文；既有 7 個
# snake_case 錯誤字面（not_found/unknown_source/... ）是舊碼遺留，範圍外不動
# （TASK-100a-T3 決策點：新增 code 就得守新規則，不因「既有端點還沒遷移」而
# 再新增一條 snake_case 違規）。
_SET_PHOTO_ERR_FAILED = "設定照片失敗，請稍後再試"
_SET_PHOTO_ERR_INVALID_URL = "照片來源網址不合法"


@router.post("/{name}/photo")
async def set_actress_photo(name: str, req: SetActressPhotoRequest):
    """
    設定女優照片。
    - 雲端來源（graphis/gfriends/wiki/minnano）：先清焦點成功，才下載並覆蓋本機照片
    - local_crop：crop 出候選 bytes 後，先清焦點成功，才寫入 GFRIENDS_DIR

    CD-4 pre-invalidate（承重，spec §3.3 唯一「不做就會比現況更差」的項目）：換圖
    必須先作廢舊焦點、成功後才安裝新圖，避免中途失敗把偏側焦點誤套到新圖上。
    兩分支插入點刻意不同（TASK-100a-T3 Opus 裁決）：
      - cloud：`download_actress_photo` 是「下載+覆蓋寫入」合一的不透明呼叫（不在
        本 task 修改範圍），`clear_focal` 只能插在 url_required 驗證之後、該呼叫之前。
      - local_crop：`crop_video_cover` 是純運算、零 side effect，不是「安裝新圖」，
        `clear_focal` 插在它成功之後、`_write_actress_photo` 之前——crop 失敗與
        「換圖」本身無關，沒必要為了一次注定失敗的運算就先清掉使用者存好的焦點。
    `clear_focal` 失敗或拋例外 → 500 + 固定中文，絕不觸碰檔案寫入。

    覆蓋時先 glob 刪舊副檔名，再寫入新圖。更新 DB photo_source 欄位。
    回傳帶 CD-11 fp cache-bust（`?v={mtime_ns}-{size}`，取代舊秒級 `?t=`）的新
    photo_url；`auto_focal`/`crop_mode` 直接寫死（clear_focal 語意已知，不多一次
    DB round-trip），與 T2 上傳端點回應對稱（plan-100b CD-10 需要）。
    """
    repo, actress = await asyncio.to_thread(_load_actress, name)
    if actress is None:
        return JSONResponse(status_code=404, content={"error": "not_found"})

    if req.source not in CLOUD_SOURCES and req.source != "local_crop":
        return JSONResponse(status_code=400, content={"error": "unknown_source"})

    if req.source in CLOUD_SOURCES:
        if not req.url:
            return JSONResponse(status_code=400, content={"error": "url_required"})
        # 🔴 白名單驗證必須在清焦點「之前」（Codex P2）：validate_photo_url 是純函式、
        # 零 side effect、不做任何 I/O，而 download_actress_photo 內部也會再驗一次
        # （SSRF 防禦不依賴呼叫端，此處是提前擋，不是取代）。不提前擋的話，一個
        # 白名單外的 URL 會先把使用者的手動焦點清掉、才發現這個請求注定失敗
        # → 舊圖留著但焦點無聲消失。
        # 這與 local_crop 分支「clear_focal 插在 crop 成功之後」是同一條原則
        # （TASK-100a-T3 Opus 裁決）：**不為一次注定失敗的操作先清掉焦點**。
        # T3 當時只把該原則套用到 local_crop，漏了 cloud 這條同構的路徑。
        # 可達性：set_actress_photo 已揭露於 capabilities（:964，side_effect），
        # AI agent 可直接 POST 任意 url —— 不是只有 UI 那條可信路徑。
        # CD-8：新增路徑一律固定中文（不因為旁邊的 url_required／unknown_source
        # 是舊碼 snake_case 就跟著新增一條違規——TASK-100a-T3 已裁決過同一件事）。
        if not validate_photo_url(req.url, req.source):
            logger.warning("[actress] set_photo URL 不在白名單 source=%s", req.source)
            return JSONResponse(status_code=400, content={"error": _SET_PHOTO_ERR_INVALID_URL})
        # 🔴 CD-4 pre-invalidate：cloud 分支插入點——download_actress_photo 之前。
        err = await _pre_invalidate_focal(repo, name, ctx="set_photo", err_msg=_SET_PHOTO_ERR_FAILED)
        if err:
            return err
        ok = await asyncio.to_thread(download_actress_photo, name, req.url, req.source)
        if not ok:
            return JSONResponse(status_code=500, content={"error": "download_failed"})

    elif req.source == "local_crop":
        if not req.video_path:
            return JSONResponse(status_code=400, content={"error": "video_path_required"})
        # file:/// URI → FS path（禁止手動 strip）
        video_fs_path = uri_to_fs_path(req.video_path)  # uri-no-reverse: comparison-only, matched against DB v.path below, no disk I/O
        # 從 DB 取該影片的 cover_path
        videos = await asyncio.to_thread(_get_actress_videos, name)
        # Fix 3 (T3): v.path 在 DB 存 file:/// URI（gallery_scanner 用 to_file_uri 寫入），
        # 比對前雙邊都正規化為 FS path，避免 URI vs FS path 永遠 fail
        match = next(
            (v for v in videos if uri_to_fs_path(str(v.path)) == video_fs_path),  # uri-no-reverse: comparison-only, no disk I/O
            None,
        )
        if match is None or not match.cover_path:
            return JSONResponse(status_code=404, content={"error": "video_or_cover_not_found"})
        # Fix 3 (T3): match.cover_path 也是 URI，傳給 crop_video_cover 前先轉 FS path
        path_mappings = (await asyncio.to_thread(load_config)).get('gallery', {}).get('path_mappings', {})
        cover_fs_path = uri_to_local_fs_path(str(match.cover_path), path_mappings) if match.cover_path else ""
        if not cover_fs_path:
            return JSONResponse(status_code=404, content={"error": "video_or_cover_not_found"})
        # crop → bytes
        crop_bytes = await asyncio.to_thread(
            crop_video_cover, cover_fs_path, req.crop_spec or "v1"
        )
        if crop_bytes is None:
            return JSONResponse(status_code=500, content={"error": "crop_failed"})
        # 🔴 CD-4 pre-invalidate：local_crop 分支插入點——crop 成功之後、寫入之前。
        err = await _pre_invalidate_focal(repo, name, ctx="set_photo", err_msg=_SET_PHOTO_ERR_FAILED)
        if err:
            return err
        # glob 刪舊副檔名 + 寫入
        # 🔴 PR#108 Codex P2-B：比照 upload_actress_photo（:898-902）補外層 try/except——
        # local_crop 分支原本完全沒有，_write_actress_photo 內部例外（含清舊檔殘留的
        # PermissionError 等）會逸出成未捕捉例外、FastAPI 回裸文字 500，而非本檔統一的
        # 錯誤信封格式。錯誤信封對齊：照片家族一律裸 dict `{"error": ...}`（非 upload
        # 端點也用同一 _SET_PHOTO_ERR_FAILED 固定中文，與 CD-8 一致）。
        try:
            await asyncio.to_thread(_write_actress_photo, name, crop_bytes)
        except Exception:
            logger.exception("[actress] set_photo local_crop 寫檔失敗 name=%s", name)
            return JSONResponse(status_code=500, content={"error": _SET_PHOTO_ERR_FAILED})

    # 更新 photo_source + 回傳（CD-7）
    err = await _persist_photo_source(
        repo, actress, req.source, ctx="set_photo", err_msg=_SET_PHOTO_ERR_FAILED)
    if err:
        return err

    # CD-6：logical slot vs physical path，寫檔/下載後不可假設 {safe}.jpg，一律重
    # 解析（cloud 分支副檔名由 Content-Type 決定，core/actress_photo.py）。重解析
    # 可能回 None（GFRIENDS_DIR 綁定不一致／外部同時刪除）——不 guard 會 None.stat()
    # 拋 AttributeError（mirror T2 review finding）。
    photo_url, err = await _photo_url_with_fp_cache_bust(
        name, ctx="set_photo", err_msg=_SET_PHOTO_ERR_FAILED)
    if err:
        return err
    return JSONResponse(status_code=200, content={
        "photo_url": photo_url,
        "photo_source": req.source,
        "auto_focal": "",
        "crop_mode": "auto",
    })


# ---------------------------------------------------------------------------
# 端點九之二：POST /api/actresses/{name}/photo/upload — 上傳女優照片（TASK-100a-T2）
# NOTE：必須定義在 GET /{name} 之前！
# ---------------------------------------------------------------------------

_UPLOAD_MAX_BYTES = 10 * 1024 * 1024
_UPLOAD_MAX_PIXELS = 50_000_000
_UPLOAD_FORMAT_TO_EXT = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "GIF": ".gif"}

# CD-8：錯誤訊息一律固定中文，機械分流走 HTTP status（不用 snake_case error code）。
_UPLOAD_ERR_TOO_LARGE = "圖片太大（檔案上限 10MB、尺寸上限 50M 像素）"
_UPLOAD_ERR_UNSUPPORTED_FORMAT = "不支援的圖片格式"
_UPLOAD_ERR_NOT_FOUND = "查無此女優"
_UPLOAD_ERR_FAILED = "上傳照片失敗，請稍後再試"

# ruff B008：fastapi.File 不在 ruff 預設 immutable-calls 允許清單內（Query/Depends/Body/
# Form 都在，File 不在）。用模組層級單例取代 inline File(...) 呼叫，避免逐一 noqa 或改動
# 全域 pyproject.toml 設定。
_UPLOAD_FILE_PARAM = File(...)


def _validate_uploaded_photo(data: bytes):
    """Threadpool helper: 像素上限 + 真實格式驗證（CD-9/CD-5，TASK-100a-T2）。

    研究實測（PIL 12.2.0）：Image.open(BytesIO(非圖片 bytes)) 本身就會拋
    UnidentifiedImageError（不是只有 .verify() 才會失敗），故 open()／.verify()
    必須共用同一個 try/except → 415；但像素超限（413）是 verify() 之前的明確
    return，不可被這個 except 吞掉。

    同步（PIL 解碼），呼叫端須經 asyncio.to_thread（async-offload 守衛：
    Image.open()/.verify() 是 AST 掃描認定的阻塞呼叫，即使操作對象是 in-memory
    BytesIO 也一視同仁，故不可裸跑在 async def 路由 body 內）。

    Returns:
        (status, error_msg, ext) — 驗證失敗時 status/error_msg 非 None、ext 為 None；
        成功時 status/error_msg 為 None、ext 為 PIL 驗出的真實格式副檔名。
    """
    try:
        img = Image.open(BytesIO(data))
        w, h = img.size  # header-only，不解碼像素
        if w * h > _UPLOAD_MAX_PIXELS:
            return 413, _UPLOAD_ERR_TOO_LARGE, None
        img.verify()
    except Exception:
        # 細節必須進 log（DoD⑨）。不可靜默吞——v0.11.12 的 javdb 事故就是
        # `except ImportError` 靜默吞掉真實失敗、零 log，事後「排查最貴的成本
        # 就是零 log」。使用者上傳壞檔是預期內的事，故用 warning 不用 exception，
        # 但至少要留下「是什麼炸的」。
        logger.warning("[actress] upload 圖片驗證失敗（回 415）", exc_info=True)
        return 415, _UPLOAD_ERR_UNSUPPORTED_FORMAT, None

    ext = _UPLOAD_FORMAT_TO_EXT.get(img.format)
    if ext is None:
        return 415, _UPLOAD_ERR_UNSUPPORTED_FORMAT, None
    return None, None, ext


@router.post("/{name}/photo/upload")
async def upload_actress_photo(name: str, file: UploadFile = _UPLOAD_FILE_PARAM):
    """
    上傳女優照片（multipart/form-data）。

    驗證順序（全部先於任何寫入，CD-10/CD-9/CD-5）：
        1. 大小 >10MB → 413
        2. Content-Type 不在 core.actress_photo.CONTENT_TYPE_MAP 白名單 → 415
        3. 像素上限 w*h>50M（Image.open 只讀 header）→ 413；PIL 驗證真實格式失敗 → 415
        4. 女優不存在 → 404
    CD-4 pre-invalidate（承重）：先 clear_focal 成功後才寫入新圖，避免「新圖配舊焦點」
    的中途失敗污染；clear_focal 失敗（含拋例外）→ 500，不得觸碰檔案寫入。
    不跑自動偵測、不寫焦點、無等待（CD-1）——要對焦走 POST /{name}/focal（T4）。

    CD-13：不揭露進 web/routers/capabilities.py——multipart binary body，
    AI agent 與 server 未必同機，無法從本機路徑上傳，揭露也用不起來（spec §4-4）。
    """
    # 1. 大小（CD-10）：.size 可讀就先擋；.size 為 None（理論上真實 multipart 解析器
    # 恆設為非 None，此分支防禦不可信任的呼叫端）則讀出後用 len(data) 判斷。
    if file.size is not None and file.size > _UPLOAD_MAX_BYTES:
        return JSONResponse(status_code=413, content={"error": _UPLOAD_ERR_TOO_LARGE})
    data = await file.read()
    if len(data) > _UPLOAD_MAX_BYTES:
        return JSONResponse(status_code=413, content={"error": _UPLOAD_ERR_TOO_LARGE})

    # 2. Content-Type 白名單（複用 core.actress_photo.CONTENT_TYPE_MAP 的 key 集合，
    # 不重新定義一份）——粗篩，不需要讀 bytes 內容，故在 Image.open() 之前執行。
    if file.content_type not in CONTENT_TYPE_MAP:
        return JSONResponse(status_code=415, content={"error": _UPLOAD_ERR_UNSUPPORTED_FORMAT})

    # 3. 像素上限 + 真實格式（CD-9/CD-5）——PIL 解碼須過 asyncio.to_thread
    # （async-offload 守衛：Image.open/.verify() 是阻塞呼叫，不可裸跑在 event loop 上）。
    err_status, err_msg, ext = await asyncio.to_thread(_validate_uploaded_photo, data)
    if err_status is not None:
        return JSONResponse(status_code=err_status, content={"error": err_msg})

    # 4. 女優存在
    repo, actress = await asyncio.to_thread(_load_actress, name)
    if actress is None:
        return JSONResponse(status_code=404, content={"error": _UPLOAD_ERR_NOT_FOUND})

    # 🔴 CD-4 pre-invalidate：先清焦點，成功後才安裝新圖。失敗（含拋例外）一律視為
    # 失敗，函式在此直接 return，絕不執行 _write_actress_photo——此時女優已確認存在，
    # clear_focal 理論上不該回 False（唯一情境是驗證與寫入之間女優被刪除的 race，
    # spec §1.4 明示接受），不論哪種失敗原因行為必須一致：不寫檔、不動 DB 其他欄位，
    # 舊照片與舊焦點原封不動。
    err = await _pre_invalidate_focal(repo, name, ctx="upload", err_msg=_UPLOAD_ERR_FAILED)
    if err:
        return err

    try:
        await asyncio.to_thread(_write_actress_photo, name, data, ext)
    except Exception:
        logger.exception("[actress] upload 寫檔失敗 name=%s", name)
        return JSONResponse(status_code=500, content={"error": _UPLOAD_ERR_FAILED})

    # CD-7：photo_source 必須持久化；clear_focal 語意已知（''/'auto'），直接寫死，
    # 不多一次 DB round-trip 只為了讀已知的值。
    err = await _persist_photo_source(
        repo, actress, "upload", ctx="upload", err_msg=_UPLOAD_ERR_FAILED)
    if err:
        return err

    photo_url, err = await _photo_url_with_fp_cache_bust(
        name, ctx="upload", err_msg=_UPLOAD_ERR_FAILED)
    if err:
        return err
    return JSONResponse(status_code=200, content={
        "photo_url": photo_url,
        "photo_source": "upload",
        "auto_focal": "",
        "crop_mode": "auto",
    })


# ---------------------------------------------------------------------------
# 端點十／十一：POST /api/actresses/{name}/detect-focal、POST /api/actresses/{name}/focal
# （TASK-100a-T4，鏡射 web/routers/showcase.py 的 /video/detect-focal、/video/save-focal）
# NOTE：必須定義在 GET /{name} 之前！
# ---------------------------------------------------------------------------

# 女優裁窗 3/4 置中（非影片 showcase.py 的 0.71 右裁基準），spec §3.4。
#
# 🔴 軸向對齊注意（plan-100b CD-2）：detect_focal(fs, ratio) 內部
# （core/focal/detector.py:280-307，`:303` 呼叫 `_dominant_axis_by_ratio`）
# 會依這個 ratio 自行選軸（`:143-147`：`int(height*ratio) < width → 軸=X`，
# 否則軸=Y）。plan-100b CD-2 的前端也獨立算 `a = W/H > r → 軸=X`——兩者數學上
# 完全等價（對整數 width：`int(h*r) < w ⟺ h*r < w ⟺ (w/h) > r`，`int()` 截斷
# 不影響不等式方向），但**沒有任何機制強制兩邊同步**。若之後只改其中一邊
# （例如調整女優裁窗比例卻漏改另一邊），會產生「後端回 Y 軸座標、前端卻鎖
# X 軸拖曳」的錯框。改這個常數時，務必同時檢查 plan-100b.md CD-2 的前端
# 常數是否也要跟著動。
_FOCAL_DETECT_RATIO = 0.75

_FOCAL_ERR_NOT_FOUND = _UPLOAD_ERR_NOT_FOUND  # "查無此女優"（複用既有常數，同語意）
_FOCAL_ERR_NO_PHOTO = "找不到照片檔案"          # mirror showcase.py:264 的「找不到封面檔案」措辭家族
_FOCAL_ERR_DETECT_FAILED = "偵測焦點失敗"        # 複用 showcase.py 字面
_FOCAL_ERR_INVALID_FORMAT = "無效的焦點座標格式"  # 複用 showcase.py 字面
_FOCAL_ERR_SAVE_FAILED = "存入手動焦點失敗"      # 複用 showcase.py 字面


@router.post("/{name}/detect-focal")
async def detect_actress_focal(name: str):
    """使用者主動觸發焦點偵測預覽（純預覽，不寫 DB）。

    鏡射 `web/routers/showcase.py::detect_video_focal`，ratio 改 **0.75**
    （女優裁窗 3/4 置中，見 `_FOCAL_DETECT_RATIO` 註解）。與影片版的差異：
    - 女優端點吃 `name`（URL path segment，本來就是 DB primary key），不是
      client 傳入的檔案路徑——沒有影片版 `is_known_cover_path` 那類「client
      傳路徑、後端驗證是否已知合法」的攻擊面（照片路徑全由後端
      `get_local_photo_path(name)` 內部推導）。
    - 無 configured-dir scope guard：女優收藏本來就是全域概念，不像影片有
      「是否在收藏範圍內」的問題。

    流程：
    1. 女優不存在 → 404，固定中文。
    2. 女優存在但無本機照片（`get_local_photo_path` 回 None）→ 400，固定中文
       （🔴 Opus 裁決 2026-07-15：mirror showcase.py:264-266 的「找不到封面檔案」
       400 家族，理由：女優**存在**只是沒照片，404 語意會與「查無此女優」混淆）。
       **不呼叫 detect_focal**（沒有檔案可偵測）。
    3. 偵測（無臉 → `format_focal(None)` == ''，不崩，§3.7-6）。
    4. 回應恆為 `{"success": bool, "auto_focal": str}`（錯誤時 "error" 取代
       "auto_focal"）——**無 photo_url/cover_path，無任何 FS 路徑欄位**（DoD⑤）。

    `async def` + 顯式 `await asyncio.to_thread(...)`：延續 actress.py 既有
    「新增端點」慣例（`list_photo_candidates`/`actress_crop`/`set_actress_photo`/
    `upload_actress_photo` 皆同），而非 showcase.py 的 `def` 隱性 threadpool
    寫法——同檔案內部一致性優先。`detect_focal` 是真正的 pigo 人臉偵測
    （~2.2s），`tests/integration/test_async_offload_guard.py` 的 AST 偵測清單
    不包含它，守衛不會因為裸跑而報錯，但仍必須經 `asyncio.to_thread` 離開
    event loop（守衛測不出這點，實作/review 階段人工把關）。

    CD-13：不進 `web/routers/capabilities.py`（比照 showcase 的兩支 focal
    端點皆未揭露——同家族純預覽/寫入端點對 AI agent 用起來無明顯優勢）。
    """
    try:
        _, actress = await asyncio.to_thread(_load_actress, name)
        if actress is None:
            return JSONResponse(status_code=404, content={"success": False, "error": _FOCAL_ERR_NOT_FOUND})

        photo_fs = await asyncio.to_thread(get_local_photo_path, name)
        if photo_fs is None:
            return JSONResponse(status_code=400, content={"success": False, "error": _FOCAL_ERR_NO_PHOTO})

        focal = await asyncio.to_thread(detect_focal, str(photo_fs), _FOCAL_DETECT_RATIO)
        auto_focal = format_focal(focal)  # None → ''，純預覽不寫 DB
        return JSONResponse(status_code=200, content={"success": True, "auto_focal": auto_focal})
    except Exception:
        logger.exception("[actress] 偵測焦點失敗 name=%s", name)
        return JSONResponse(status_code=500, content={"success": False, "error": _FOCAL_ERR_DETECT_FAILED})


@router.post("/{name}/focal")
async def set_actress_focal(name: str, req: SetActressFocalRequest):
    """使用者手動存入焦點座標（單一 UPDATE 同寫 `auto_focal` + `crop_mode='manual'`）。

    鏡射 `web/routers/showcase.py::set_manual_focal`。**`parse_focal` 驗證是函式
    第一行**——在 `_load_actress`/任何 DB 存取之前，非法格式完全不碰 DB
    （DoD④）。

    CD-3：**無 compare token、無 409。** `ActressRepository.update_manual_focal
    (name, focal)`（T1）刻意不吃 `expected_fp`/`expected_cover_path`（對照
    `VideoRepository.update_manual_focal` 的 `AND cover_path = ?`）——女優
    focal 沒有背景 writer 會與此端點交錯寫入，`WHERE name = ?` 已足夠，不需要
    compare-and-store 防 race。`update_manual_focal` 回 `False` 只可能是驗證
    與寫入之間女優被刪除的罕見 race（spec §1.4 明示接受），本端點視為 500
    （非 409——沒有「封面已變更」這種語意可用）。

    `update_manual_focal` 是啞的原子寫入器（T1 已定案的分層）：格式驗證的責任
    在呼叫端（本函式），寫入端點**不檢查照片是否存在**——座標與照片存在與否
    是兩件獨立的事，換圖必清焦點的責任在 T2/T3 的 `clear_focal`，不在此處
    （加這個檢查會是死碼）。

    回應恆為 `{"success": bool, "auto_focal": str}`（錯誤時 "error" 取代
    "auto_focal"）——與 detect-focal 同一組收斂形狀，無任何 FS 路徑欄位（DoD⑤）。

    `async def` + `asyncio.to_thread`（同 detect-focal，理由見該端點 docstring）。
    CD-13：不進 capabilities（同 detect-focal）。
    """
    parsed = parse_focal(req.focal)
    if parsed is None:
        return JSONResponse(status_code=400, content={"success": False, "error": _FOCAL_ERR_INVALID_FORMAT})

    try:
        repo, actress = await asyncio.to_thread(_load_actress, name)
        if actress is None:
            return JSONResponse(status_code=404, content={"success": False, "error": _FOCAL_ERR_NOT_FOUND})

        normalized = format_focal(parsed)
        written = await asyncio.to_thread(repo.update_manual_focal, name, normalized)
        if not written:
            # 理論不該發生（女優已確認存在）——唯一情境是驗證與寫入之間的 race，
            # spec §1.4 明示接受。無 compare token 可用，故視為一般失敗，非 409。
            logger.warning("[actress] update_manual_focal 回 False（race）name=%s", name)
            return JSONResponse(status_code=500, content={"success": False, "error": _FOCAL_ERR_SAVE_FAILED})
        return JSONResponse(status_code=200, content={"success": True, "auto_focal": normalized})
    except Exception:
        logger.exception("[actress] 存入手動焦點失敗 name=%s", name)
        return JSONResponse(status_code=500, content={"success": False, "error": _FOCAL_ERR_SAVE_FAILED})


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
