"""
女優 API Router — /api/actresses

端點：
    POST   /api/actresses/favorite          收藏女優
    GET    /api/actresses/photo/{name}      取得本地照片（binary）
    GET    /api/actresses/library           列出庫內全部女優（依 alias group 聚合，TASK-117-T1）
    GET    /api/actresses/{name}            查詢已收藏女優
    DELETE /api/actresses/{name}            刪除已收藏女優

注意：photo/{name}、library 都必須定義在 {name} 之前，否則 FastAPI 會將 "photo"／
"library" 解析為 {name}。
"""

import asyncio
import json
import random
import re
import uuid
from datetime import datetime
from io import BytesIO
from typing import Optional, List
from urllib.parse import quote

from fastapi import APIRouter, UploadFile, File, Query, HTTPException
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, ValidationError
from PIL import Image
from core.atomic_write import atomic_write
from core.database.version_tracker import bump_showcase_revision
from core.database.actress_library import get_favorite_actress_stats
from core.maker_mapping import load_prefix_mapping
from core.scrapers.actress.graphis_pool import (
    candidate_id, parse_exclude, graphis_candidates,
)

from core.database import (
    ActressRepository, AliasRepository, VideoRepository, Actress, init_db,
    get_library_actresses,
)
from core.actress_photo import (
    download_actress_photo, get_local_photo_path, delete_local_photo,
    crop_video_cover, GFRIENDS_DIR, CONTENT_TYPE_MAP, validate_photo_url,
)
from core.focal import device_state, format_focal, parse_focal
from core.focal.subprocess_runner import run_detection
from core.organizer import sanitize_filename
from core.path_utils import to_file_uri as to_file_uri, uri_to_fs_path, uri_to_local_fs_path, coerce_to_file_uri
from core.config import load_config
from core.scrapers.actress.orchestrator import (
    get_cached_profile,
    get_actress_profile,
    get_actress_profile_preview,
    _sources_to_photo_candidates,  # noqa: PLC2701 — 預覽端點回應要附照片候選，CD-157-2 規定由 orchestrator 的純函式產生，不在 router 重寫一份
    _compute_age_from_birth as _compute_age,  # noqa: PLC2701 — actress router 的回應組裝（_actress_to_response）需要即時算年齡，直接借用 orchestrator 內部同一套生日換算邏輯，避免在 router 層重寫一份容易漂移的年齡計算；尚未升格為公開名
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


class PreviewActressRequest(BaseModel):
    name: str


class SetActressPhotoRequest(BaseModel):
    source: str                          # "graphis"|"gfriends"|"wiki"|"xcity"|"local_crop"
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
# Response model（TASK-117-T1）：本 router 目前全用裸 JSONResponse，GET /library 是
# 第一支用 response_model 的端點（plan CD 明文指定，非隨意引入新風格）。
# ---------------------------------------------------------------------------

class LibraryActressItem(BaseModel):
    primary_name: str
    names: List[str]
    video_count: int
    is_favorite: bool


class LibraryActressesResponse(BaseModel):
    success: bool
    actresses: List[LibraryActressItem]
    total: int


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


_ACTRESS_SUBMIT_STR_FIELDS = frozenset({
    "name_en", "birth", "height", "cup", "hometown", "hobby",
    "agency", "debut_work", "nickname", "blog_url", "official_url",
})
_ACTRESS_SUBMIT_MEASURES = {"bust": (50, 150), "waist": (40, 120), "hip": (50, 150)}
_ACTRESS_SUBMIT_RESERVED = frozenset({
    "photo_source", "primary_text_source", "auto_focal", "crop_mode",
    "photo_fp_path", "photo_fp_mtime_ns", "photo_fp_size", "aliases",
    "name", "created_at", "updated_at",
})


def _validate_actress_submit_fields(payload: dict) -> None:
    """提交前逐欄驗證；任何一項錯誤都在 DB 寫入前擋回。"""
    for k, v in payload.items():
        if k in _ACTRESS_SUBMIT_RESERVED:
            raise HTTPException(400, detail=f"{k} 為保留欄位，AI 不可透過此端點寫入")
        if k == "photo":
            if v is not None:
                if not isinstance(v, dict) or not isinstance(v.get("source"), str) or v["source"] not in CLOUD_SOURCES | {"local_crop"}:
                    raise HTTPException(400, detail="照片來源不合法")
                if v["source"] in CLOUD_SOURCES:
                    url = v.get("url")
                    if not isinstance(url, str) or not url or not validate_photo_url(url, v["source"]):
                        raise HTTPException(400, detail="照片來源網址不合法")
                elif not isinstance(v.get("video_path"), str) or not v["video_path"]:
                    raise HTTPException(400, detail="照片影片路徑不合法")
        elif k == "tags":
            if not isinstance(v, list) or not all(isinstance(item, str) for item in v):
                raise HTTPException(400, detail="tags 型別錯誤，必須是字串列表")
        elif k == "height":
            if v != "":
                # TASK-157-F4：\d+ 不限位數，4301+ 位數字字串會讓下面 int() 撞上
                # Python 3.11+ 的 int-string 轉換位數上限（sys.int_info.default_max_str_digits
                # = 4300）丟出未接住的 ValueError → 500。身高合理範圍最多 3 位數
                # （100–220cm），\d{1,3} 同時擋掉超長字串與超出範圍的數字，
                # 不必再另外包 try/except 重複判一次。
                if isinstance(v, bool) or not (
                    (isinstance(v, int) and -999 <= v <= 999) or
                    (isinstance(v, str) and re.fullmatch(r"\d{1,3}(?:cm)?", v))
                ):
                    raise HTTPException(400, detail="height 格式錯誤")
                height = int(str(v).removesuffix("cm"))
                if not 100 <= height <= 220:
                    raise HTTPException(400, detail="height 超出合理範圍")
        elif k in _ACTRESS_SUBMIT_MEASURES:
            if v is not None:
                if isinstance(v, bool) or not isinstance(v, (int, str)):
                    raise HTTPException(400, detail=f"{k} 型別錯誤")
                number = _safe_int(v)
                lower, upper = _ACTRESS_SUBMIT_MEASURES[k]
                if number is None or not lower <= number <= upper:
                    raise HTTPException(400, detail=f"{k} 超出合理範圍或格式錯誤")
        elif k in _ACTRESS_SUBMIT_STR_FIELDS:
            if not isinstance(v, str):
                raise HTTPException(400, detail=f"{k} 型別錯誤，必須是字串")
            if k == "birth" and v:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
                    raise HTTPException(400, detail="birth 日期格式錯誤")
                try:
                    datetime.strptime(v, "%Y-%m-%d")
                except ValueError:
                    raise HTTPException(400, detail="birth 日期無效") from None
            if k == "cup" and v and not re.fullmatch(r"[A-Z]", v):
                raise HTTPException(400, detail="cup 格式錯誤")
        else:
            raise HTTPException(400, detail=f"包含未知欄位: {k}")


def _flatten_aliases(raw) -> list:
    """
    將 aliases 欄位統一轉為純字串 list。

    dict-list 格式來源回傳 dict list（每筆含 ja/hiragana/romaji），
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


def _safe_recent_score(name: str, repo, alias_repo) -> float:
    """add_favorite 用：取單一女優的 recent_score，任何例外 → 0.0（排序分數不該擋收藏）。"""
    try:
        st = get_favorite_actress_stats(actress_repo=repo, alias_repo=alias_repo).get(name)
        return st.score if st else 0.0
    except Exception:
        logger.warning("[actress] recent_score 計算失敗 name=%s", name, exc_info=True)
        return 0.0


def _actress_to_response(actress: Actress, video_count: int = 0, *, recent_score: float = 0.0) -> dict:
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
        "recent_score": round(recent_score, 6),
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
        # covered_names（TASK-117-T1）：此路徑無 sync_from_favorite 呼叫（女優已存在，
        # 不重新抓 profile），「sync_primary」概念在此就是 name 本身。
        alias_repo = AliasRepository()
        covered_names = alias_repo.resolve(name) | {name}
        return JSONResponse(
            status_code=409,
            content={
                "error": "already_exists",
                "actress": _actress_to_response(existing),
                "covered_names": sorted(covered_names),
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
    local_crop_ok = False
    crop_attempted = False
    if profile is None:
        result = get_actress_profile(name, makers=resolved_makers)
        if result.data is None:
            if result.timed_out:
                return JSONResponse(
                    status_code=504,
                    content={"error": "timeout", "message": "Scraper 超時"}
                )
            # TASK-122-T10：五來源全 miss、非超時 —— 片庫裡若有這位女優的片
            # （NFO 已掃描寫進 videos.actresses），改建一張只有名字的本地卡，
            # 照片 best-effort 從她任一部有封面的片裁右側 3:4。庫裡沒有她的
            # 片才維持現行 404（見 CD-T10-2）。
            crop_attempted = True
            videos = _get_actress_videos(name)
            if not videos:
                return JSONResponse(
                    status_code=404,
                    content={"error": "not_found", "message": "查無此女優"}
                )
            local_crop_ok = _try_local_crop_photo(name, videos)
            profile = {
                "name": name,
                "text": {},
                "photo_url": None,
                "photo_source": "local_crop" if local_crop_ok else None,
                "primary_text_source": "local",
            }
        else:
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
    # covered_names（TASK-117-T1）：預設 sync_primary = actress.name，若 sync 失敗（例外
    # 分支）也要有值可用——resolve() 對未知名字回 {name} 自身，語意等價「沒有 group」。
    sync_result = {"primary_name": actress.name}
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

    # TASK-174-T3a / CD-174-17：沒有任何雲端照片 → 從片庫挑片裁封面（cache hit／miss 共用）。
    # 必須在別名同步「之後」：新別名（例：維基／avbase 帶來的舊藝名）剛寫進 actress_aliases，
    # 她的片可能全以舊名登錄；影片查詢與 video_count 同一來源（resolve(actress.name)），
    # 被拒的衝突別名自然不納入。不碰 profile（共享快取 dict，I-P1）；只更新 DB 與本次回應。
    if not profile.get("photo_url") and not crop_attempted:
        videos = _get_actress_videos(actress.name)
        if videos and _try_local_crop_photo(actress.name, videos):
            local_crop_ok = True
            actress.photo_source = "local_crop"
            repo.update_fields(actress.name, {"photo_source": "local_crop"})

    # 5. 下載照片（photo_url 可能為 None，函數內部已有 guard）
    # TASK-122-T10：local_crop fallback 已經裁圖成功時（local_crop_ok=True）
    # short-circuit，不呼叫 download_actress_photo（沒有 profile["photo_url"] 可下載）。
    photo_downloaded = local_crop_ok or download_actress_photo(
        actress.name, profile.get("photo_url"), profile.get("photo_source")
    )

    alias_repo = AliasRepository()
    video_count = repo.count_videos_for_actress_names(alias_repo.resolve(actress.name))
    # covered_names（TASK-117-T1）：sync 後完整 DB group ∪ 使用者這次點的 name——不得
    # 寫回 actress_aliases 表，聯集只存在於這次 HTTP 回應（CD-117-9）。
    sync_primary = sync_result["primary_name"]
    covered_names = alias_repo.resolve(sync_primary) | {name}
    recent_score = _safe_recent_score(actress.name, repo, alias_repo)
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "actress": _actress_to_response(actress, video_count, recent_score=recent_score),
            "photo_downloaded": photo_downloaded,
            "skipped_aliases": skipped_aliases,
            "covered_names": sorted(covered_names),
        }
    )


# ---------------------------------------------------------------------------
# POST /api/actresses/preview — 只讀預覽五個來源與片庫目前資料
# ---------------------------------------------------------------------------

@router.post("/preview")
def preview_actress(req: PreviewActressRequest):
    try:
        name = req.name.strip()
        if not name:
            return JSONResponse(status_code=422, content={"error": "女優名字不可為空"})

        preview = get_actress_profile_preview(name)
        repo = ActressRepository()
        # 🔴 PR #211 第三輪 v2：alias 判斷不再只在「name 自己沒有 row」時才跑——
        # 命中已收藏 primary 的別名時（不論該別名是否自有 row），alias_of 一律
        # 附上，current 回 primary 的資料（各來源 sources 仍以請求的別名抓取，
        # 不受影響）。與 submit_actress 用同一個 _favorited_primary_for_alias
        # 判準，避免兩處漂移。
        primary_name = _favorited_primary_for_alias(repo, name)
        if primary_name:
            primary_actress = repo.get_by_name(primary_name)
            result = {
                "name": name,
                "sources": preview["sources"],
                "current": _actress_to_response(primary_actress) if primary_actress else None,
                "photo_candidates": _sources_to_photo_candidates(preview["sources"]),
                "alias_of": primary_name,
            }
        else:
            actress = repo.get_by_name(name)
            result = {
                "name": name,
                "sources": preview["sources"],
                "current": _actress_to_response(actress) if actress else None,
                "photo_candidates": _sources_to_photo_candidates(preview["sources"]),
            }
        return result
    except HTTPException:
        raise
    except Exception:
        logger.exception("[actress] preview_actress 失敗 name=%s", req.name)
        return JSONResponse(status_code=500, content={"error": "操作失敗"})


# ---------------------------------------------------------------------------
# 端點九之三：POST /api/actresses/{name} — 提交審過的女優文字資料
# ---------------------------------------------------------------------------

def _favorited_primary_for_alias(repo: ActressRepository, name: str) -> Optional[str]:
    """CD-157 alias 身分判準（preview_actress／submit_actress／upload_actress_photo／
    set_actress_photo 共用）。

    若 `name` 是某位「已收藏」女優的別名，回傳該 primary 的名字；否則 None。
    判準是 alias 記錄存在 **且** 其 primary_name 目前已收藏
    （`repo.exists`）——orphan alias group（primary 尚未收藏）不受影響，仍可
    用 alias 本名建立新收藏（見 test_submit_actress_orphan_alias_group_creates_new_actress）。

    🔴 PR #211 Codex P2-2：呼叫端必須在**觸碰任何 row 之前**（含判斷該 name
    自己有沒有既有 row）就先跑這條檢查——`name` 自己是否已有一筆 actresses row
    與「它是不是別人的別名」是兩件獨立的事：舊版把這條檢查塞在「name 自己沒有
    row」的分支裡，若 name 意外自己也有一筆 row（例如曾被單獨收藏過，之後才
    被同步成某個 primary 的別名），該分支永遠不會執行，等於直接放行覆寫/新增
    到這個「別名自己的 row」，繞過「一律擋下並告知正確名字」的身分守衛。

    只回傳 primary 名稱或 None——訊息文字由各呼叫端自己組（PR #211 第三輪
    v2：preview 需要 alias_of／current，submit／upload／set_actress_photo 需要
    各自的 400 擋下訊息，欄位形狀不同，不該共用同一個「訊息字串」）。
    """
    alias_record = AliasRepository().find_by_alias(name)
    if alias_record and repo.exists(alias_record.primary_name):
        return alias_record.primary_name
    return None


def _save_actress_submission(name: str, fields: dict):
    """Run the submit DB read/write sequence in a worker thread."""
    init_db()
    repo = ActressRepository()
    primary_name = _favorited_primary_for_alias(repo, name)
    if primary_name:
        raise HTTPException(
            400, detail=f"{name} 是 {primary_name} 的別名，請改用「{primary_name}」提交")

    old_actress = repo.get_by_name(name)
    if old_actress is not None:
        if not repo.update_fields(name, fields):
            logger.error("[actress] AI 提交更新失敗 name=%s", name)
            raise HTTPException(500, detail="操作失敗")
    else:
        repo.save(Actress(name=name, **fields))

    actress = repo.get_by_name(name)
    return repo, old_actress, actress


def _compensate_actress_submission(repo: ActressRepository, name: str,
                                   old_actress: Optional[Actress], fields: dict) -> None:
    """Restore text only when the photo operation failed before installing a file."""
    try:
        if old_actress is None:
            restored = repo.delete_by_name(name)
        else:
            old_fields = {key: getattr(old_actress, key) for key in fields}
            restored = repo.update_fields(name, old_fields)
        if not restored:
            logger.warning("[actress] AI 提交補償未完成 name=%s", name)
    except Exception:
        logger.warning("[actress] AI 提交補償失敗 name=%s", name, exc_info=True)


@router.post("/{name}")
async def submit_actress(name: str, payload: dict):
    # 🔴 PR #211 第三輪 delta review P3：整個函式主體包在一個外層 try/except——
    # name 正規化／`_validate_actress_submit_fields`／`SetActressPhotoRequest`
    # 驗證／欄位正規化（`int()`/`_safe_int` 等）原本完全沒有防護，這些都發生在
    # `_save_actress_submission` 之前、片庫**零寫入**，非預期例外（不是下面已
    # 明確 raise 的 HTTPException）逸出會回裸文字 500（違反 AGENTS.md:81），且
    # 因為還沒寫過任何東西，不需要補償。HTTPException 原樣放行（400 驗證／
    # 別名擋下／500 update_fields 回 False 都是本函式既有的正常控制流）；其餘
    # 例外一律 log 後回固定中文 JSON 500，body 形狀沿用 `{"detail": ...}`
    # （不是照片家族用的 `{"error": ...}`）。
    try:
        name = name.strip()
        if not name:
            raise HTTPException(400, detail="女優名字不可為空")

        _validate_actress_submit_fields(payload)
        photo_req = None
        if payload.get("photo") is not None:
            try:
                photo_req = SetActressPhotoRequest.model_validate(payload["photo"])
            except ValidationError:
                raise HTTPException(400, detail="照片欄位格式錯誤") from None
        fields = {k: v for k, v in payload.items() if k != "photo"}
        if "height" in fields and fields["height"] != "":
            fields["height"] = f"{int(str(fields['height']).removesuffix('cm'))}cm"
        for key in _ACTRESS_SUBMIT_MEASURES:
            if key in fields and fields[key] is not None:
                fields[key] = _safe_int(fields[key])
        fields["primary_text_source"] = "ai"

        try:
            repo, old_actress, actress = await asyncio.to_thread(_save_actress_submission, name, fields)
        except HTTPException:
            raise
        except Exception:
            # P3-2（PR #211 review）：_save_actress_submission 在 worker thread 跑 DB
            # 讀寫，非預期例外（sqlite locked／disk full）若不接住，asyncio.to_thread
            # 會原樣逸出到這個 async route。同一種 body 形狀 `{"detail": ...}`，沿用
            # 同一函式內既有的 `raise HTTPException(500, detail="操作失敗")`（:477）。
            logger.exception("[actress] AI 提交寫入失敗 name=%s", name)
            return JSONResponse(status_code=500, content={"detail": "操作失敗"})

        # 🔴 PR #211 第三輪 v3（owner 拍板保守補償）：`rollback_safe` 只在
        # `_apply_photo_change` 五個「確定尚未觸碰任何照片檔」的 return 點為
        # True，其餘一律 False（狀態不明或已寫檔，不補償）。照片安裝後的重讀／
        # `_actress_to_response` 也在同一段外層防護內——此時文字已寫入成功，
        # 例外時只回固定中文 500，不做補償。
        if photo_req is not None:
            _, err, rollback_safe = await _apply_photo_change(repo, actress, name, photo_req)
            if err:
                if rollback_safe:
                    await asyncio.to_thread(_compensate_actress_submission, repo, name, old_actress, fields)
                return _translate_submit_photo_err(err)
            actress = await asyncio.to_thread(repo.get_by_name, name)
        return {"success": True, "actress": await asyncio.to_thread(_actress_to_response, actress)}
    except HTTPException:
        raise
    except Exception:
        logger.exception("[actress] AI 提交處理失敗 name=%s", name)
        return JSONResponse(status_code=500, content={"detail": "操作失敗"})


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
    stats = get_favorite_actress_stats(actress_repo=repo, alias_repo=AliasRepository())
    result = []
    for actress in actresses:
        st = stats.get(actress.name)
        result.append(_actress_to_response(
            actress,
            st.video_count if st else 0,
            recent_score=st.score if st else 0.0,
        ))
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "actresses": result,
            "total": len(result),
        }
    )


# ---------------------------------------------------------------------------
# 端點五之二：GET /api/actresses/library — 列出庫內全部女優（依 alias group 聚合，TASK-117-T1）
# NOTE：必須定義在 GET /{name} 之前！
# ---------------------------------------------------------------------------

@router.get("/library", response_model=LibraryActressesResponse)
def list_library_actresses() -> LibraryActressesResponse:
    """列出庫內全部女優（依 alias group 聚合，含片數與收藏狀態）。

    分組／聚合邏輯的單一所有者是 core.database.actress_library.get_library_actresses()
    （Opus 裁決①）——本端點函式本體只做 init_db() → 呼叫聚合函式 → 包 response model，
    不含任何分組邏輯。函式名刻意與 core.database.get_library_actresses 不同名，避免
    import 遮蔽。
    """
    init_db()
    groups = get_library_actresses()
    return LibraryActressesResponse(success=True, actresses=groups, total=len(groups))


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
        elif source == "xcity":
            from core.scrapers.actress.xcity import scrape_xcity
            r = scrape_xcity(name)
            return r.get("photo_url") if r else None
        else:
            return None
    except Exception as e:
        logger.warning("[actress] _fetch_single_source 失敗 source=%s: %s", source, e)
        return None


_GRAPHIS_TIMEOUT_S = 5.0  # 呼叫時讀取（不綁預設參數），測試可 monkeypatch


def local_crop_url(video) -> str:
    """本機影片封面 → actress-crop URL；cover_path 空或轉不出 FS 路徑回 ''（skip broken candidate）。"""
    # Fix 1 (T2): cover_path 在 DB 存 file:/// URI，crop endpoint 需要 FS path
    cover_fs_path = uri_to_fs_path(str(video.cover_path)) if video.cover_path else ""  # uri-no-reverse: URL identifier stays canonical; actress_crop reverse-maps at disk I/O
    if not cover_fs_path:
        return ""
    return f"/api/actresses/actress-crop?path={quote(cover_fs_path)}&spec=v1"


def _get_random_videos_with_covers(actress_name: str, count: int, exclude_ids=frozenset()) -> list:
    """
    取得女優隨機影片（有封面的）。

    使用 AliasRepository.resolve 展開 alias set，以 get_videos_by_actress_names
    多名查詢，涵蓋所有 alias 標記的影片。無 alias 時 resolve 回 {actress_name}，
    行為等價舊版。雲端路徑不受影響（仍只用 primary name）。
    exclude_ids：crop URL 的 candidate_id 命中者先濾掉再 shuffle／截取。

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
        picked, picked_ids = [], set(exclude_ids)  # 同時排除 exclude 與已選 crop id（共用封面不佔名額）
        for v in with_covers:
            url = local_crop_url(v)
            cid = candidate_id(url)
            if not url or cid in picked_ids:
                continue
            picked_ids.add(cid)
            picked.append(v)
            if len(picked) >= count:
                break
        return picked
    except Exception as e:
        logger.warning("[actress] _get_random_videos_with_covers 失敗: %s", e)
        return []


# ---------------------------------------------------------------------------
# 端點七：GET /api/actresses/{name}/photo-candidates — SSE 候選照片串流
# NOTE：必須定義在 GET /{name} 之前！
# ---------------------------------------------------------------------------

@router.get("/{name}/photo-candidates")
async def list_photo_candidates(name: str, attempt: int = Query(0, ge=0), exclude: str = Query("")):
    """
    SSE 串流回傳女優候選照片（最多 6 張）。
    雲端最多 5 張（gfriends／wiki／xcity 最多 3 張 + Graphis 遞補，合計 ≤5）並行抓取，
    本機影片封面 crop 補足至總數最多 6 張。
    actress 不存在 → JSONResponse 404。

    attempt（TASK-102b-T1，spec-102 Part B）：optional 輪替序號，stateless。
    0/省略＝請求 name；N>0＝依 alias 穩定排序輪替雲端查詢名，只影響雲端 4 源，
    本機補位與 current_source 排除邏輯不受影響（CD-7）。

    exclude（spec-185）：逗號分隔的候選 id（8 位 hex），容錯解析；命中者不再送。
    Graphis 候選獨立於三源（gfriends/wiki/xcity），最多 5 張雲端總額，缺的由本機補。
    """
    _, actress = await asyncio.to_thread(_load_actress, name)
    if actress is None:
        return JSONResponse(
            status_code=404,
            content={"error": "not_found"}
        )

    current_source = actress.photo_source
    cloud_sources = [s for s in ["gfriends", "wiki", "xcity"] if s != current_source]
    exclude_ids = parse_exclude(exclude)

    def _resolve_query_names(n: str) -> list:
        # CD-2：序位 0 = 請求的 name（URL path param），不是 record.primary_name。
        # resolve() 是雙向解析——若燈箱女優名恰是 alias-hit，取 record primary 當
        # 序位 0 會讓 attempt=0 的查詢名與 0.12.3 不同，破壞「無 alias／既有路徑
        # 逐位一致」的回歸底線。正常情境（請求名＝主名）下與 spec §4.2「主名固定
        # 第一」等價。其餘名字用 sorted() 保穩定序（resolve() 回傳的是無序 set）。
        resolved = AliasRepository().resolve(n)  # set；miss → {n}
        return [n] + sorted(resolved - {n})

    if attempt == 0:
        # names[0] 恆為請求 name（見上方 CD-2 註解），attempt=0 不需要 resolve()
        # 就能算出 query_name==name——省一次 DB 呼叫，也讓 attempt 省略/0 的路徑
        # 與 0.12.3（未帶輪替邏輯前）resolve() 呼叫次數逐位一致，不動既有回歸測試。
        query_name = name
    else:
        names = await asyncio.to_thread(_resolve_query_names, name)
        query_name = names[attempt % len(names)]  # len(names) >= 1 恆成立
    logger.info(
        "[actress] photo-candidates attempt=%d query_name=%s", attempt, query_name
    )  # CD-10(b)：不對此行寫斷言

    def _event(payload: dict) -> str:
        return f"event: candidate\ndata: {json.dumps({**payload, 'id': candidate_id(payload['full_url'])})}\n\n"

    async def generate():
        seen_ids = set()
        cloud_total = 0
        total = 0
        max_cloud = 3
        cloud_count = 0  # 三源實際送出張數（n3）

        async def fetch_source(src: str):
            try:
                url = await asyncio.wait_for(
                    asyncio.to_thread(_fetch_single_source, query_name, src),
                    timeout=5.0,
                )
                return (src, url)
            except Exception:
                return (src, None)

        async def fetch_graphis():
            try:
                r = await asyncio.wait_for(
                    asyncio.to_thread(
                        graphis_candidates, actress.name, query_name,
                        actress.photo_source, exclude_ids,
                    ),
                    timeout=_GRAPHIS_TIMEOUT_S,
                )
                return [u for u in (r or []) if isinstance(u, str) and u]
            except Exception as e:
                logger.warning("[actress] graphis_candidates 失敗: %s", e)
                return []

        def take_graphis(urls):
            """回傳可送出的 Graphis 事件字串（已濾 exclude／已送過者）。"""
            out = []
            for u in urls:
                cid = candidate_id(u)
                if cid in exclude_ids or cid in seen_ids:
                    continue
                seen_ids.add(cid)
                out.append(_event({"source": "graphis", "thumb_url": u, "full_url": u}))
            return out

        graphis_task = asyncio.ensure_future(fetch_graphis())
        src_tasks = [asyncio.ensure_future(fetch_source(src)) for src in cloud_sources]
        pending = set(src_tasks) | {graphis_task}
        picks = None
        early_done = False  # Graphis 先完成並已送 picks[:2]
        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for t in done:
                if t is graphis_task:
                    picks = t.result()
                    if pending - {graphis_task}:
                        for ev in take_graphis(picks[:2]):
                            yield ev
                            cloud_total += 1
                        early_done = True
                    continue
                src, url = t.result()
                if url and candidate_id(url) not in exclude_ids and cloud_count < max_cloud:
                    cid = candidate_id(url)
                    if cid in seen_ids:
                        continue
                    seen_ids.add(cid)
                    yield _event({"source": src, "thumb_url": url, "full_url": url})
                    cloud_count += 1
                    cloud_total += 1
        if picks:
            n3 = cloud_count
            g_target = min(len(picks), 5 - n3)
            for ev in take_graphis(picks[2:g_target] if early_done else picks[:g_target]):
                yield ev
                cloud_total += 1
        total = cloud_total

        # 本機 crop 補足
        needed = 6 - total
        if needed > 0:
            local_videos = await asyncio.to_thread(
                _get_random_videos_with_covers, name, needed, exclude_ids
            )
            for video in local_videos:
                crop_url = local_crop_url(video)
                if not crop_url:
                    # skip broken candidate，避免送空路徑的 URL
                    continue
                cid = candidate_id(crop_url)
                if cid in exclude_ids or cid in seen_ids:
                    continue
                seen_ids.add(cid)
                # Fix 2 (T2): video.path 在 DB 已是 file:/// URI（gallery_scanner.scan_file 透過 to_file_uri 寫入）
                # 若萬一是 FS path（legacy / 異常），coerce_to_file_uri 做 idempotent 轉換
                try:
                    video_path_uri = coerce_to_file_uri(str(video.path))  # uri-no-reverse: coerce_to_file_uri forward URI build, D2 complement
                except Exception as e:
                    logger.warning("[actress] coerce_to_file_uri 失敗 path=%s: %s", video.path, e)
                    video_path_uri = str(video.path)
                yield _event({
                    "source": "local_crop",
                    "video_path": video_path_uri,
                    "thumb_url": crop_url,
                    "full_url": crop_url,
                })
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
    """Threadpool helper: fetch videos across the actress's alias set
    (init_db already ran in _load_actress).

    Part A（spec-102 §3）：與候選端 _get_random_videos_with_covers 同一對
    API（resolve + get_videos_by_actress_names），兩端對稱——別名片候選
    才通得過儲存驗證。無 alias 時 resolve 回 {name}，行為等價舊版單名查詢。
    """
    names = list(AliasRepository().resolve(name))
    return VideoRepository().get_videos_by_actress_names(names)


def _try_local_crop_photo(name: str, videos: list) -> bool:
    """TASK-122-T10 best-effort：從 `videos` 中挑一部有封面的片，裁右側 3:4 當女優照片。

    只裁「唯一的初始照片」（CD-T10-1/CD-T10-3）：依 `str(v.path)` 排序取穩定序第一筆，
    不 shuffle、失敗不換下一張重試——換圖有 photo-candidates 可用。

    全程 try/except 包住：cover_path 全空／URI 反解回空字串／crop_video_cover 回
    None／寫檔拋例外，任一失敗都只 log warning 回 False，不影響呼叫端建卡、不上拋。

    不呼叫 `_pre_invalidate_focal`（新 row 無舊焦點可作廢，見 TASK-122-T10 現況分析 §3）。
    """
    try:
        candidates = sorted(
            (v for v in videos if v.cover_path),
            key=lambda v: str(v.path),
        )
        if not candidates:
            return False
        cover_uri = str(candidates[0].cover_path)
        path_mappings = load_config().get('gallery', {}).get('path_mappings', {})
        cover_fs_path = uri_to_local_fs_path(cover_uri, path_mappings)
        if not cover_fs_path:
            return False
        crop_bytes = crop_video_cover(cover_fs_path, "v1")
        if crop_bytes is None:
            return False
        _write_actress_photo(name, crop_bytes)
        return True
    except Exception as e:
        logger.warning("[actress] _try_local_crop_photo 失敗 name=%s err=%s", name, e)
        return False


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
    # dest.parent 恆等於 GFRIENDS_DIR（安全用 dest 而非另傳 dir=GFRIENDS_DIR）：
    # 見 TASK-113d-T1.md「Q-5」段的恆等證明（safe 不含路徑分隔符 + ext 固定白名單）。
    dest = GFRIENDS_DIR / f"{safe}{ext}"
    with atomic_write(dest, suffix=ext) as f:
        f.write(crop_bytes)
    # 純檔案 I/O，不經過 DB commit → 不會自動 bump revision（PR#207 Codex P2）。
    # 寫檔成功（os.replace 已落地）即手動 bump，讓 ETag（insights.py hasPhoto）對
    # 得上這次新圖；下方清舊副檔名殘檔是 best-effort、不影響「新圖已裝好」這件事。
    bump_showcase_revision()
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

    只回 response 不持久化 → 重載後顯示舊來源。

    🔴 單欄寫入（PR #211 Codex P2-1）：`actress` 是呼叫端在本次 request 較早
    時間點讀出的快照，之後經過至少一次 `await`（clear_focal / 下載 / 裁切 /
    寫檔）才走到這裡——若同一段時間內有另一個 writer 改了這筆女優的其他文字
    欄位（例如另一個 request 同時提交 height/birth），原本 `actress.photo_source
    = source` 後整份 `repo.save(actress)` 會把那些欄位覆寫回呼叫端手上的舊快照
    值，等於憑空吃掉別人剛寫的東西。改用 `repo.update_fields` 只動
    `photo_source` 這一欄，其餘欄位不論是誰、什麼時候寫的都不會被踩。
    `photo_source` 不在 `_ACTRESS_FOCAL_PRESERVE` 白名單內，`update_fields` 可以
    正常寫它。

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
        updated = await asyncio.to_thread(
            repo.update_fields, actress.name, {"photo_source": source})
    except Exception:
        logger.exception("[actress] %s photo_source 持久化失敗 name=%s", ctx, actress.name)
        return JSONResponse(status_code=500, content={"error": err_msg})
    if not updated:
        # 與同檔案 clear_focal 呼叫端（:906）同一種防禦式失敗處理：name 在驗證與
        # 寫入之間被刪除的 race——理論上極窄，但既然 update_fields 回了 bool 就不
        # 該吞掉，行為對齊「回 False 視為失敗」而非靜默假裝成功。
        logger.warning("[actress] %s photo_source update_fields 回 False name=%s", ctx, actress.name)
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

CLOUD_SOURCES = {"graphis", "gfriends", "wiki", "xcity"}

# CD-8（AGENTS.md:33）：T3 在本端點新增的失敗路徑一律固定中文；既有 7 個
# snake_case 錯誤字面（not_found/unknown_source/... ）是舊碼遺留，範圍外不動
# （TASK-100a-T3 決策點：新增 code 就得守新規則，不因「既有端點還沒遷移」而
# 再新增一條 snake_case 違規）。
_SET_PHOTO_ERR_FAILED = "設定照片失敗，請稍後再試"
_SET_PHOTO_ERR_INVALID_URL = "照片來源網址不合法"

# P3-1（PR #211 review）：_apply_photo_change 是 set_actress_photo（UI 端點）與
# submit_actress（AI-facing API 端點）共用的函式。set_actress_photo 沿用下列
# snake_case code 是 TASK-100a-T3 已裁決的「範圍外不動」——UI 前端只判斷
# resp.ok／status code，從不讀 body.error 內容，故沿用不影響任何前端契約
# （已核對 web/static/js、web/templates 全庫無任何字面比對）。但 submit_actress
# 是 AI 呼叫的 API contract，AGENTS.md:81 要求新增／AI 呼叫路徑一律回固定中文，
# 不可把內部 code 原樣透給呼叫端——故只在 submit_actress 收到 err 之後做轉譯，
# 不動 _apply_photo_change 本體（set_actress_photo 既有測試仍斷言舊 code）。
_SUBMIT_PHOTO_ERR_ZH = {
    "unknown_source": "不支援的照片來源",
    "url_required": "缺少照片網址",
    "video_path_required": "缺少對應的影片路徑",
    "video_or_cover_not_found": "找不到對應的影片或封面",
    "crop_failed": "裁切照片失敗，請稍後再試",
    "download_failed": "下載照片失敗，請稍後再試",
}


def _translate_submit_photo_err(err: JSONResponse) -> JSONResponse:
    """把 _apply_photo_change 回傳的舊 snake_case code 轉成固定中文，只給
    submit_actress 用（見上方模組層註解）。非上表涵蓋的 code（例如已經是固定
    中文的 _SET_PHOTO_ERR_FAILED／_SET_PHOTO_ERR_INVALID_URL）原樣放行，避免
    重複轉譯或誤改其他欄位。
    """
    body = json.loads(bytes(err.body))
    zh = _SUBMIT_PHOTO_ERR_ZH.get(body.get("error"))
    if zh is None:
        return err
    body["error"] = zh
    return JSONResponse(status_code=err.status_code, content=body)


async def _apply_photo_change(repo: ActressRepository, actress: Actress, name: str,
                              req: SetActressPhotoRequest):
    """Return (URL, error, rollback_safe).

    v3（owner 拍板，PR #211 第三輪 followup2）：不追蹤「照片是否已安裝」，改追蹤
    「這個失敗是否確定發生在任何寫檔／clear_focal 之前」——`rollback_safe=True`
    只用於五個明確、在第一個寫入動作之前就 return 的分支：unknown_source／
    url_required／照片網址不合法／local_crop 缺 video_path／找不到對應影片或
    封面（兩個 return 點）。其餘一律 False（含 download_failed／crop_failed／
    local_crop 寫檔失敗／photo_source 持久化失敗／照片路徑重解析失敗／任何非
    預期例外）——這些狀態不明或已經動過檔案，submit_actress 不補償回滾文字。
    整段主體包 try/except：HTTPException 原樣放行（目前本函式內部一律回傳
    JSONResponse，不主動 raise，但呼叫的子函式若意外 raise 也要放行控制流）；
    其他非預期例外 log 後轉既有固定中文 JSON 500，rollback_safe=False（狀態不
    明，不補償）。
    """
    try:
        if req.source not in CLOUD_SOURCES and req.source != "local_crop":
            return None, JSONResponse(status_code=400, content={"error": "unknown_source"}), True

        if req.source in CLOUD_SOURCES:
            if not req.url:
                return None, JSONResponse(status_code=400, content={"error": "url_required"}), True
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
                return None, JSONResponse(status_code=400, content={"error": _SET_PHOTO_ERR_INVALID_URL}), True
            # 🔴 CD-4 pre-invalidate：cloud 分支插入點——download_actress_photo 之前。
            err = await _pre_invalidate_focal(repo, name, ctx="set_photo", err_msg=_SET_PHOTO_ERR_FAILED)
            if err:
                return None, err, False
            ok = await asyncio.to_thread(download_actress_photo, name, req.url, req.source)
            if not ok:
                return None, JSONResponse(status_code=500, content={"error": "download_failed"}), False

        elif req.source == "local_crop":
            if not req.video_path:
                return None, JSONResponse(status_code=400, content={"error": "video_path_required"}), True
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
                return None, JSONResponse(status_code=404, content={"error": "video_or_cover_not_found"}), True
            # Fix 3 (T3): match.cover_path 也是 URI，傳給 crop_video_cover 前先轉 FS path
            path_mappings = (await asyncio.to_thread(load_config)).get('gallery', {}).get('path_mappings', {})
            cover_fs_path = uri_to_local_fs_path(str(match.cover_path), path_mappings) if match.cover_path else ""
            if not cover_fs_path:
                return None, JSONResponse(status_code=404, content={"error": "video_or_cover_not_found"}), True
            # crop → bytes
            crop_bytes = await asyncio.to_thread(
                crop_video_cover, cover_fs_path, req.crop_spec or "v1"
            )
            if crop_bytes is None:
                # crop_failed 早於任何寫入，但 owner 保守語義刻意排除在補償白名單外
                # （final3.txt：符合 owner 選擇的保守語義，不因它「其實也在寫入前」而放行）。
                return None, JSONResponse(status_code=500, content={"error": "crop_failed"}), False
            # 🔴 CD-4 pre-invalidate：local_crop 分支插入點——crop 成功之後、寫入之前。
            err = await _pre_invalidate_focal(repo, name, ctx="set_photo", err_msg=_SET_PHOTO_ERR_FAILED)
            if err:
                return None, err, False
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
                return None, JSONResponse(status_code=500, content={"error": _SET_PHOTO_ERR_FAILED}), False

        # 更新 photo_source + 回傳（CD-7）——此時檔案已寫入，失敗一律 rollback_safe=False。
        err = await _persist_photo_source(
            repo, actress, req.source, ctx="set_photo", err_msg=_SET_PHOTO_ERR_FAILED)
        if err:
            return None, err, False

        # CD-6：logical slot vs physical path，寫檔/下載後不可假設 {safe}.jpg，一律重
        # 解析（cloud 分支副檔名由 Content-Type 決定，core/actress_photo.py）。重解析
        # 可能回 None（GFRIENDS_DIR 綁定不一致／外部同時刪除）——不 guard 會 None.stat()
        # 拋 AttributeError（mirror T2 review finding）。
        photo_url, err = await _photo_url_with_fp_cache_bust(
            name, ctx="set_photo", err_msg=_SET_PHOTO_ERR_FAILED)
        if err:
            return None, err, False
        return photo_url, None, False
    except HTTPException:
        raise
    except Exception:
        logger.exception("[actress] set_photo 未預期例外 name=%s", name)
        return None, JSONResponse(status_code=500, content={"error": _SET_PHOTO_ERR_FAILED}), False


@router.post("/{name}/photo")
async def set_actress_photo(name: str, req: SetActressPhotoRequest):
    """
    設定女優照片。
    - 雲端來源（graphis/gfriends/wiki/xcity）：先清焦點成功，才下載並覆蓋本機照片
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
    # 🔴 PR #211 第三輪 v3：身分守衛擴及本端點（原本只有 submit_actress／
    # upload_actress_photo 擋，set_actress_photo 完全沒查）——在判斷「女優是否
    # 存在」之前先查別名，命中已收藏 primary 一律 400 並點名正確名字，不讓
    # 「別名自己意外也有一筆孤兒 row」的換圖請求悄悄寫進那筆孤兒 row。
    # 承認邊界：UI 換照片（showcase picker）只會用女優牆上的本名呼叫，全域
    # 唯一性檢查下本名不會同時是他人別名，故不影響 UI 既有流程；此守衛只在
    # 「異常狀態」（同名 row 恰好也是另一位已收藏女優的別名）時才會擋下。
    primary_name = await asyncio.to_thread(_favorited_primary_for_alias, repo, name)
    if primary_name:
        return JSONResponse(status_code=400, content={
            "error": f"{name} 是 {primary_name} 的別名，請改用「{primary_name}」提交"})
    if actress is None:
        return JSONResponse(status_code=404, content={"error": "not_found"})

    photo_url, err, _ = await _apply_photo_change(repo, actress, name, req)
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

    已揭露進 web/routers/capabilities.py 為 upload_actress_photo（TASK-157-T8／
    CD-157-9）。舊版本假設「AI agent 與 server 未必同機，無法從本機路徑上傳」
    不成立：正確用法是 AI 自己下載圖片 bytes 後以 multipart 上傳，與是否同機
    無關，任何 HTTP client（含 AI agent 自己發的 multipart request）都不需要
    與 server 共享檔案系統。

    整段主體包 try/except（PR #211 第三輪 followup）：本端點前段（大小／格式／
    女優載入）原本完全沒有防護，DB 或其他非預期例外會逸出成裸文字 500。
    HTTPException（別名擋下的 400）原樣放行；其他例外一律 log 後回既有固定
    中文 `_UPLOAD_ERR_FAILED`，不洩漏例外內容。
    """
    try:
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

        # 4. 女優存在 + 別名擋下（CD-157 身分守衛，同 submit_actress 的判準，
        # PR #211 Codex P2-2）——必須在任何寫入之前執行，且不論 name 自己有沒有
        # 一筆既有 row 都要查，理由見 _favorited_primary_for_alias 的 docstring。
        repo, actress = await asyncio.to_thread(_load_actress, name)
        primary_name = await asyncio.to_thread(_favorited_primary_for_alias, repo, name)
        if primary_name:
            raise HTTPException(
                400, detail=f"{name} 是 {primary_name} 的別名，請改用「{primary_name}」提交")
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
    except HTTPException:
        raise
    except Exception:
        logger.exception("[actress] upload_actress_photo 未預期例外 name=%s", name)
        return JSONResponse(status_code=500, content={"error": _UPLOAD_ERR_FAILED})


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
_MANUAL_DETECT_TIMEOUT_S = 5.0  # D2/D9: 前景與背景共用同一個 5 秒定義（CD-152d-1），不是批次上限外的安全網

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
    4. 成功回應為 `{"success": bool, "auto_focal": str, "reason": str}`（錯誤時
       "error" 取代 "auto_focal"／"reason"）——**無 photo_url/cover_path，無任何
       FS 路徑欄位**（DoD⑤）。``reason`` 五值見 CD-152d-4b。

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

        # 152d-T-D8：同 showcase，停用時不要進 run_detection 的全域鎖排隊。
        # 這支沒有預先載入的 config，而 is_disabled() 內部會讀檔 + 取鎖 ⇒ 必須 to_thread。
        # 152d-T-D9：fail-open，鏡射 runner 內 pre_spawn_check 的既有契約
        # （subprocess_runner.py:309-315）。「config 查詢失敗」與「這台機器算不算得動人臉」
        # 是兩回事——查不到不可以當成停用，更不可以讓整個請求失敗。
        try:
            _focal_disabled = await asyncio.to_thread(device_state.is_disabled)
        except Exception:
            logger.warning("focal 停用查詢失敗，fail-open 繼續偵測", exc_info=True)
            _focal_disabled = False
        if _focal_disabled:
            return JSONResponse(
                status_code=200,
                content={"success": True, "auto_focal": "", "reason": "device_disabled"},
            )

        decision = {}

        def _on_outcome(o):
            decision["just_disabled"] = device_state.record_manual_outcome(o)

        outcome = await asyncio.to_thread(
            run_detection, str(photo_fs), _FOCAL_DETECT_RATIO,
            job_key=str(uuid.uuid4()), timeout_s=_MANUAL_DETECT_TIMEOUT_S,
            pre_spawn_check=device_state.is_disabled, on_outcome=_on_outcome,
        )
        focal = outcome.focal if outcome.kind == "FOUND" else None
        auto_focal = format_focal(focal)  # None → ''，純預覽不寫 DB
        reason = device_state.classify_manual_reason(
            outcome, decision.get("just_disabled", False),
        )
        return JSONResponse(
            status_code=200,
            content={"success": True, "auto_focal": auto_focal, "reason": reason},
        )
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
