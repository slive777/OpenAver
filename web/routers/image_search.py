"""POST /api/image-search：以圖查番號（193-T3）。

只做送出前把關（大小／格式）、錯誤碼對應、候選信封與 in_library；
閘與送出在 core.avscan.client.lookup，這裡不認識閘、不自己限速。
"""
import time

from fastapi import APIRouter, UploadFile
from fastapi.responses import JSONResponse

from core.auto_organize_state import mark_manual_activity
from core.avscan.client import AvscanError, AvscanInvalidImage, AvscanRateLimited, AvscanUnparseable, lookup
from core.avscan.image_prep import ImageTooLarge, ImageUnsupported, prepare_image
from core.avscan.rules import is_clear_hit, map_code
from core.database import VideoRepository, init_db
from core.image_codec import image_media_type
from core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["image-search"])

MAX_BYTES = 8 * 1024 * 1024
_ALLOWED_MEDIA = frozenset({"image/jpeg", "image/png", "image/webp"})

_MESSAGES = {
    "rate_limited": "avscan 要求稍等幾秒後再送，請依 retry_after 秒數重試",
    "unreachable": "avscan 目前連不上，請稍後再試",
    "unparseable": "avscan 回應格式與預期不同（站方可能改版），請稍後再試",
    "file_too_large": "圖片太大（上限 8MB）",
    "unsupported_image": "只支援 JPG、PNG、WEBP 圖片",
}


def _error(code: str, status: int, retry_after: int | None = None) -> JSONResponse:
    logger.info("image-search error: %s", code)
    body = {"success": False, "error": code, "message": _MESSAGES[code]}
    if retry_after is not None:
        body["retry_after"] = retry_after
    return JSONResponse(status_code=status, content=body)


def _in_library(numbers: list[str]) -> list[bool | None]:
    """一次批次查片庫；查失敗每筆回 None（查不到 False 與查失敗 None 要分得出來）。"""
    try:
        init_db()
        found = VideoRepository().get_by_numbers([n.upper() for n in numbers])
    except Exception:
        logger.warning("image-search: 片庫查詢失敗，in_library 回 null", exc_info=True)
        return [None] * len(numbers)
    return [bool(found.get(n.upper())) for n in numbers]


def _build_candidates(raw: list[dict]) -> list[dict]:
    mapped = [map_code(c["code"]) for c in raw]
    in_lib = _in_library([number for number, _ in mapped])
    return [
        {
            "rank": rank,
            "code": c["code"],
            "number": number,
            "searchable": searchable,
            "similarity": c["similarity"],
            "match": c["match"],
            "in_library": in_lib[rank - 1],
        }
        for rank, (c, (number, searchable)) in enumerate(zip(raw, mapped, strict=True), start=1)
    ]


@router.post("/image-search")
def image_search(file: UploadFile):
    """上傳一張圖，回最多 5 部候選番號（multipart 欄位 `file`）。不寫檔、不存圖。"""
    mark_manual_activity()
    started = time.monotonic()
    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        return _error("file_too_large", 413)
    media = image_media_type(data)
    if media not in _ALLOWED_MEDIA:
        return _error("unsupported_image", 415)
    try:
        prepared = prepare_image(data)
    except ImageTooLarge:
        return _error("file_too_large", 413)
    except ImageUnsupported:
        return _error("unsupported_image", 415)
    try:
        raw = lookup(prepared)
    except AvscanRateLimited as exc:
        return _error("rate_limited", 429, retry_after=exc.retry_after)
    except AvscanUnparseable:
        return _error("unparseable", 502)
    except AvscanInvalidImage:
        return _error("unsupported_image", 415)
    except AvscanError:
        return _error("unreachable", 502)
    clear_hit, lead = is_clear_hit([c["similarity"] for c in raw])
    candidates = _build_candidates(raw) if raw else []
    logger.info(
        "image-search ok: %d candidates, clear_hit=%s (%d ms)",
        len(candidates), clear_hit, int((time.monotonic() - started) * 1000),
    )
    return {"success": True, "source": "avscan", "clear_hit": clear_hit, "lead": lead, "candidates": candidates}
