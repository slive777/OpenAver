"""AI tags HTTP endpoints (TASK-188b-T9a / CD-188b-15)."""

from __future__ import annotations

import asyncio
import copy
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from core.ai_services import tags_backfill
from core.ai_services.image_prep import poster_to_data_uri, poster_to_jpeg_bytes
from core.ai_services.tagging import (
    TaggingFailure,
    resolve_vision_conn,
    run_vision_test,
    tag_video,
)
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
from core.secret_fields import read_secret, resolve_secret
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


class TagsTestRequest(BaseModel):
    """Optional overrides. Absent (None) → stored config; present → use given value."""

    provider: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None


def _prepare_tags_test(body: TagsTestRequest):
    """Sync prep for POST /tags/test: copy config → apply overrides → resolve conn."""
    config = copy.deepcopy(load_config())
    tags = config.setdefault("ai_services", {}).setdefault("tags", {})
    if body.provider is not None:
        tags["provider"] = body.provider
    if body.model is not None:
        tags["model"] = body.model

    provider = str(tags.get("provider") or "").strip()

    stored_key = (
        read_secret(config, f"translate.{provider}.api_key") if provider else ""
    )
    if body.api_key is None:
        api_key = stored_key
    else:
        api_key = resolve_secret(body.api_key, stored_key)
    if provider in ("gemini", "claude", "openai", "openai_official"):
        config.setdefault("translate", {}).setdefault(provider, {})["api_key"] = api_key

    if body.base_url is not None:
        if provider == "openai":
            config.setdefault("translate", {}).setdefault("openai", {})[
                "base_url"
            ] = body.base_url
        elif provider == "ollama":
            config.setdefault("translate", {}).setdefault("ollama", {})[
                "url"
            ] = body.base_url

    conn = resolve_vision_conn(config)
    return conn, list(merged()), _tags_sample_uri()


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
    if getattr(item, "hidden", False):
        row["hidden"] = True
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
        path = get_project_root() / "web/static/img/showcase/sc-11.jpg"
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


@router.delete("/tags/vocab/{name:path}")
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


def _reread_union_sync(file_uri: str) -> list:
    """成功回應的作品聯集重讀（同步 helper，呼叫端走 asyncio.to_thread，BE-ASYNC-01）。

    `tag_video` 只寫目前版本；切版本時燈箱要看到剛加的標籤，回應帶整部作品聯集。
    """
    from core.version_group import reread_work_user_tags

    config = load_config()
    path_mappings = config.get("gallery", {}).get("path_mappings", {}) or {}
    repo = VideoRepository()
    return reread_work_user_tags(repo, file_uri, path_mappings)


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
    try:
        union = await asyncio.to_thread(_reread_union_sync, file_uri)
    except Exception as e:
        logger.warning("[ai-tags] 重讀作品聯集失敗: %s", e)
        union = list(outcome.user_tags)
    return {
        "success": True,
        "added": outcome.added,
        "refused": outcome.refused,
        "user_tags": outcome.user_tags,
        "nfo_updated": outcome.nfo_updated,
        "readonly_no_output": outcome.readonly_no_output,
        "nfo_write_blocked": outcome.nfo_write_blocked,
        "work_user_tags": union,
    }


@router.get("/sample/tags")
def sample_tags():
    return {
        "inputs": [_tags_sample_uri()],
        "steps": list(_TAGS_SAMPLE_STEPS),
    }


@router.post("/tags/test")
async def post_tags_test(body: TagsTestRequest | None = None):
    """Probe vision with current (or overridden) settings; no config/DB writes."""
    req = body or TagsTestRequest()
    try:
        conn, vocab, sample_uri = await asyncio.to_thread(_prepare_tags_test, req)
    except TaggingFailure as exc:
        if exc.reason == "not_configured":
            return {
                "ok": False,
                "outcome": "not_configured",
                "detail": exc.detail,
            }
        raise
    return await run_vision_test(conn, vocab, sample_uri)


def _tags_feature_enabled(config: dict) -> bool:
    tags = (config.get("ai_services") or {}).get("tags")
    return bool(isinstance(tags, dict) and tags.get("enabled"))


def _backfill_refusal(*, rebuild: bool) -> dict | None:
    """前置判斷：not_enabled → not_configured → nothing_to_do；通過回 None。"""
    config = load_config()
    if not _tags_feature_enabled(config):
        return {"ok": False, "status": "not_enabled"}
    try:
        resolve_vision_conn(config)
    except TaggingFailure as exc:
        if exc.reason == "not_configured":
            return {"ok": False, "status": "not_configured"}
        raise
    total, pending = VideoRepository().count_ai_tag_progress()
    if rebuild:
        if total == 0:
            return {"ok": False, "status": "nothing_to_do"}
    elif pending == 0:
        return {"ok": False, "status": "nothing_to_do"}
    return None


@router.get("/tags/backfill/status")
def get_tags_backfill_status():
    return tags_backfill.status()


@router.post("/tags/backfill")
def post_tags_backfill():
    refusal = _backfill_refusal(rebuild=False)
    if refusal is not None:
        return refusal
    return tags_backfill.start_build()


@router.post("/tags/backfill/rebuild")
def post_tags_backfill_rebuild():
    refusal = _backfill_refusal(rebuild=True)
    if refusal is not None:
        return refusal
    return tags_backfill.start_rebuild()


@router.post("/tags/backfill/stop")
def post_tags_backfill_stop():
    return tags_backfill.request_stop()
