"""AI tags HTTP endpoints (TASK-188b-T9a / CD-188b-15)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from core.ai_services.image_prep import poster_to_data_uri, poster_to_jpeg_bytes
from core.ai_services.tagging import TaggingFailure, tag_video
from core.ai_services.tagging_vocab import (
    VocabError,
    add_custom,
    load_builtin,
    merged,
    remove_custom,
)
from core.config import load_config
from core.data_root import get_project_root
from core.database import VideoRepository
from core.logger import get_logger
from core.path_utils import uri_to_local_fs_path
from web.routers.collection import _normalize_to_uri  # noqa: PLC2701 — CD-188b-15 指定沿用 collection 的路徑正規化

logger = get_logger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai_tags"])

_VOCAB_STATUS = {
    "name_empty": 400,
    "name_too_long": 400,
    "name_invalid": 400,
    "name_conflict_builtin": 400,
    "definition_invalid": 400,
    "vocab_full": 400,
    "builtin": 400,
    "name_exists": 409,
    "data_root_not_ready": 409,
    "custom_unreadable": 409,
    "not_found": 404,
}

_TAGS_SAMPLE_STEPS = [
    "Open inputs[0] as a JPEG poster crop (default right-half window).",
    "Confirm the image is readable before calling POST /api/ai/tags/videos.",
]

_cache_tags: str | None = None


class VocabAddRequest(BaseModel):
    name: str
    definition: str = ""


class TagVideoRequest(BaseModel):
    file_path: str


def _vocab_error(reason: str, status: int | None = None):
    code = status if status is not None else _VOCAB_STATUS.get(reason, 500)
    return JSONResponse(
        status_code=code,
        content={"success": False, "reason": reason},
    )


def _failure_body(exc: TaggingFailure):
    body: dict = {"success": False, "reason": exc.reason}
    if exc.detail:
        body["detail"] = exc.detail
    return body


def _vocab_item_payload(item) -> dict:
    row = {
        "name": item.name,
        "source": item.source,
        "definition": item.definition,
    }
    if item.source == "builtin":
        row["group"] = item.group
    return row


def _poster_bytes(file_path: str):
    config = load_config()
    path_mappings = config.get("gallery", {}).get("path_mappings", {}) or {}
    file_uri = _normalize_to_uri(file_path, path_mappings)
    if not file_uri:
        return _vocab_error("not_found", 404)
    video = VideoRepository().get_by_path(file_uri)
    if video is None:
        return _vocab_error("not_found", 404)
    if not video.cover_path:
        return _vocab_error("no_cover", 404)
    fs_path = uri_to_local_fs_path(video.cover_path, path_mappings)
    jpeg = poster_to_jpeg_bytes(fs_path, video.crop_mode, video.auto_focal)
    if jpeg is None:
        return _vocab_error("no_cover", 404)
    return Response(content=jpeg, media_type="image/jpeg")


def _tags_sample_uri() -> str:
    global _cache_tags
    if _cache_tags is None:
        path = get_project_root() / "web/static/img/demo/sone-103.jpg"
        uri = poster_to_data_uri(str(path), "default", "")
        if uri is None:
            raise FileNotFoundError(f"tags sample unreadable: {path}")
        _cache_tags = uri
    return _cache_tags


def _is_builtin_name(name: str) -> bool:
    for item in load_builtin():
        if name == item.name or name == item.model_name:
            return True
    return False


@router.get("/tags/vocab")
def get_vocab():
    return {"items": [_vocab_item_payload(item) for item in merged()]}


@router.post("/tags/vocab")
def post_vocab(body: VocabAddRequest):
    try:
        item = add_custom(body.name, body.definition)
    except VocabError as exc:
        return _vocab_error(exc.reason)
    return {"success": True, "item": _vocab_item_payload(item)}


@router.delete("/tags/vocab/{name}")
def delete_vocab(name: str):
    target = name.strip()
    if _is_builtin_name(target):
        return _vocab_error("builtin")
    try:
        remove_custom(target)
    except VocabError as exc:
        return _vocab_error(exc.reason)
    return {"success": True}


@router.get("/tags/poster")
def get_poster(file_path: str):
    return _poster_bytes(file_path)


@router.post("/tags/videos")
async def post_tag_video(body: TagVideoRequest):
    if not (body.file_path or "").strip():
        return _failure_body(TaggingFailure("not_found"))
    file_uri = await asyncio.to_thread(_normalize_to_uri, body.file_path)
    if not file_uri:
        return _failure_body(TaggingFailure("not_found"))
    try:
        outcome = await tag_video(file_uri)
    except TaggingFailure as exc:
        return _failure_body(exc)
    return {
        "success": True,
        "added": outcome.added,
        "refused": outcome.refused,
        "user_tags": outcome.user_tags,
        "nfo_updated": outcome.nfo_updated,
        "readonly_no_output": outcome.readonly_no_output,
        "nfo_write_blocked": outcome.nfo_write_blocked,
    }


@router.get("/sample/tags")
def sample_tags():
    return {
        "inputs": [_tags_sample_uri()],
        "steps": list(_TAGS_SAMPLE_STEPS),
    }
