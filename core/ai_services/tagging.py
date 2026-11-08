"""AI tagging pure functions: prompt / parse / name map / failure / conn.

I/O orchestration (`tag_video`) lives in T7b.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass, field

from core.ai_services import tags_state
from core.ai_services.image_prep import poster_to_data_uri
from core.ai_services.tagging_vocab import VocabItem
from core.ai_services.tagging_vocab import merged
from core.ai_services.vision_chat import VisionConn
from core.ai_services.vision_chat import vision_chat
from core.cloud_translate import TranslateError
from core.config import load_config
from core.database import VideoRepository
from core.logger import get_logger
from core.openai_client import OPENAI_OFFICIAL_BASE_URL
from core.path_utils import uri_to_local_fs_path
from core.secret_fields import read_secret
from core.similar.canonicalize import alias_key
from core.user_tags_write import apply_user_tags

logger = get_logger(__name__)

USER_TEXT = "請標這張海報。"

TAGGING_FAILURE_REASONS = frozenset(
    {
        "unreachable",
        "model_unsupported",
        "bad_response",
        "not_configured",
        "disabled",
        "not_found",
        "no_cover",
        "write_failed",
    }
)

_REFUSAL_KINDS = frozenset({"blocked", "refused"})
_UNREACHABLE_KINDS = frozenset(
    {
        "connection_timeout",
        "connection_failed",
        "auth_failed",
        "forbidden",
        "not_found",
        "rate_limited",
    }
)
_MODEL_UNSUPPORTED_STATUSES = frozenset({400, 413, 415, 422})
_VALID_PROVIDERS = frozenset(
    {"ollama", "gemini", "claude", "openai", "openai_official"}
)

_PROMPT_HEAD = (
    "你是成人影片封面的標籤助手。只看這張海報上「人物的服裝、腿部、身材外觀、場景」，"
    "從下面的詞表挑出畫面上看得到的項目。\n規則：\n"
    "- 只能用詞表裡的名稱，一字不改。\n"
    "- 只根據畫面上看得到的人物與服裝判斷；海報上印的文字一律忽略，不得當作依據。\n"
    "- 看不清楚就不要選。\n"
    "- 沒有符合的就回空陣列 {\"tags\":[]}，這是正常結果，不要為了有輸出而硬標。\n"
    "- 只拍到臉或上半身、看不到服裝細節時，通常就是空陣列。\n"
    "- 便服（T 恤、牛仔褲、短褲、一般洋裝、外套）不屬於任何一項，不要硬套最接近的詞。\n"
    "- 寧可漏標，不要標錯。\n"
    "- 每個標籤給 confidence：high（一眼確定）／mid（大致看得出）。\n"
    "只輸出 JSON：{\"tags\":[{\"tag\":\"...\",\"confidence\":\"high\"}]}\n\n詞表：\n"
)


class TaggingFailure(Exception):
    """Tagging failure; `.reason` is the stable code for callers."""

    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason
        self.detail = detail
        super().__init__(reason)


@dataclass(frozen=True)
class TagOutcome:
    added: list[str]
    refused: bool = False
    user_tags: list[str] = field(default_factory=list)
    nfo_updated: bool = False
    readonly_no_output: bool = False
    nfo_write_blocked: bool = False


@dataclass(frozen=True)
class ParsedTags:
    status: str
    tags: list[str]


def _vocab_line(item: VocabItem) -> str:
    if item.definition:
        return f"- 「{item.model_name}」 ＝ {item.definition}"
    return f"- 「{item.model_name}」"


def build_system_prompt(vocab: Sequence[VocabItem]) -> str:
    """Compose system prompt; template matches poc/run_v5.py SYS verbatim."""
    lines: list[str] = []
    for group in dict.fromkeys(item.group for item in vocab):
        lines.append(f"【{group}】")
        lines += [_vocab_line(item) for item in vocab if item.group == group]
    return _PROMPT_HEAD + "\n".join(lines)


def parse_tags(text: str) -> ParsedTags:
    """Parse model reply into ok / refused / bad (CD-188b-11)."""
    start = text.find("{")
    if start < 0:
        return ParsedTags("refused" if text.strip() else "bad", [])
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
    except ValueError:
        return ParsedTags("bad", [])
    if not isinstance(obj, dict) or not isinstance(obj.get("tags"), list):
        return ParsedTags("bad", [])
    tags: list[str] = []
    for el in obj["tags"]:
        if isinstance(el, str):
            tags.append(el)
        elif isinstance(el, dict) and isinstance(el.get("tag"), str):
            tags.append(el["tag"])
    return ParsedTags("ok", tags)


def to_display_names(raw: Sequence[object], vocab: Sequence[VocabItem]) -> list[str]:
    """Map model_name / display name → display name; drop unknowns; keep order."""
    lookup: dict[str, str] = {}
    for item in vocab:
        lookup[item.name] = item.name
    for item in vocab:
        lookup.setdefault(item.model_name, item.name)
    out: list[str] = []
    seen: set[str] = set()
    for el in raw:
        if not isinstance(el, str):
            continue
        name = lookup.get(el.strip())
        if name is None:
            continue
        if name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def classify_failure(exc: TranslateError) -> TaggingFailure | None:
    """Map TranslateError → TaggingFailure; None = API-layer refusal (CD-188b-10)."""
    if exc.kind in _REFUSAL_KINDS:
        return None
    if exc.kind in _UNREACHABLE_KINDS:
        return TaggingFailure("unreachable", detail=exc.kind)
    if exc.kind == "http_error":
        if exc.status in _MODEL_UNSUPPORTED_STATUSES:
            return TaggingFailure("model_unsupported", detail=exc.kind)
        return TaggingFailure("unreachable", detail=exc.kind)
    return TaggingFailure("bad_response", detail=exc.kind)


def _tags_section(config: dict) -> dict:
    ai = config.get("ai_services")
    if not isinstance(ai, dict):
        return {}
    tags = ai.get("tags")
    return tags if isinstance(tags, dict) else {}


def _require_key(config: dict, dotted: str, detail: str) -> str:
    value = read_secret(config, dotted).strip()
    if not value:
        raise TaggingFailure("not_configured", detail=detail)
    return value


def resolve_vision_conn(config: dict) -> VisionConn:
    """Resolve VisionConn from raw config dict (CD-188b-14). Ignores enabled."""
    tags = _tags_section(config)
    provider = str(tags.get("provider") or "").strip()
    model = str(tags.get("model") or "").strip()
    if not provider or provider not in _VALID_PROVIDERS:
        raise TaggingFailure("not_configured", detail="provider")
    if not model:
        raise TaggingFailure("not_configured", detail="model")

    if provider == "ollama":
        url = read_secret(config, "translate.ollama.url").strip()
        return VisionConn(
            provider=provider,
            model=model,
            base_url=url or "http://localhost:11434",
            api_key="",
        )
    if provider in ("gemini", "claude"):
        key = _require_key(config, f"translate.{provider}.api_key", "api_key")
        return VisionConn(provider=provider, model=model, base_url="", api_key=key)
    if provider == "openai":
        base = _require_key(config, "translate.openai.base_url", "base_url")
        key = read_secret(config, "translate.openai.api_key").strip()
        return VisionConn(provider=provider, model=model, base_url=base, api_key=key)
    # openai_official
    key = _require_key(config, "translate.openai_official.api_key", "api_key")
    return VisionConn(
        provider=provider,
        model=model,
        base_url=OPENAI_OFFICIAL_BASE_URL,
        api_key=key,
    )


@dataclass(frozen=True)
class _Prepared:
    cfg: dict
    repo: object
    conn: VisionConn
    poster_uri: str
    vocab: list[VocabItem]
    local_fs_path: str


def _mark_ran_best_effort(repo, file_path: str) -> None:
    try:
        repo.mark_ai_tagged(file_path)
    except Exception:
        logger.exception("[tagging] mark_ai_tagged failed")


def _prepare(file_path: str, config: dict | None) -> _Prepared:
    """All synchronous I/O before the model call (CD-188b-12)."""
    cfg = config if config is not None else load_config()
    if not _tags_section(cfg).get("enabled"):
        raise TaggingFailure("disabled")
    conn = resolve_vision_conn(cfg)
    repo = VideoRepository()
    video = repo.get_by_path(file_path)
    if video is None:
        raise TaggingFailure("not_found")
    mappings = cfg.get("gallery", {}).get("path_mappings", {}) or {}
    poster_uri = None
    if video.cover_path:
        cover_fs = uri_to_local_fs_path(video.cover_path, mappings)
        poster_uri = poster_to_data_uri(
            cover_fs,
            video.crop_mode,
            video.auto_focal,
        )
    if poster_uri is None:
        if video.cover_path and os.path.isdir(os.path.dirname(cover_fs)):
            _mark_ran_best_effort(repo, file_path)
        raise TaggingFailure("no_cover")
    return _Prepared(
        cfg=cfg,
        repo=repo,
        conn=conn,
        poster_uri=poster_uri,
        vocab=list(merged()),
        local_fs_path=uri_to_local_fs_path(file_path, mappings),
    )


async def _ask_model(prep: _Prepared, vision_fn) -> tuple[list[str], bool]:
    """Ask the model (no lock held). Returns (display names, refused)."""
    system = build_system_prompt(prep.vocab)
    try:
        text = await vision_fn(prep.conn, system, USER_TEXT, prep.poster_uri)
    except TranslateError as exc:
        failure = classify_failure(exc)
        if failure is None:
            return [], True
        raise failure from None
    parsed = parse_tags(text)
    if parsed.status == "refused":
        return [], True
    if parsed.status == "bad":
        raise TaggingFailure("bad_response", detail="bad_json")
    names = to_display_names(parsed.tags, prep.vocab)
    hidden = {item.name for item in prep.vocab if item.hidden}
    return [n for n in names if n not in hidden], False


def _make_add_filter(names: list[str]):
    """In-lock filter: drop names whose alias group is already in scraped tags."""

    def _filter(video) -> list[str]:
        have = {alias_key(t) for t in video.tags if isinstance(t, str)}
        return [n for n in names if alias_key(n) not in have]

    return _filter


def _write(
    prep: _Prepared, file_path: str, names: list[str], refused: bool
) -> TagOutcome:
    """Write user tags + ai_tagged_at under the shared lock (CD-188b-13)."""
    result = apply_user_tags(
        prep.repo,
        file_path,
        prep.local_fs_path,
        prep.cfg,
        add=[],
        remove=[],
        ai_tagged=True,
        add_filter=_make_add_filter(names),
    )
    if not result.ok:
        raise TaggingFailure("write_failed", detail=result.error)
    return TagOutcome(
        added=result.added,
        refused=refused,
        user_tags=result.user_tags,
        nfo_updated=result.nfo_updated,
        readonly_no_output=result.readonly_no_output,
        nfo_write_blocked=result.nfo_write_blocked,
    )


async def tag_video(
    file_path: str, *, config: dict | None = None, vision_fn=None
) -> TagOutcome:
    """Tag one video from its poster (CD-188b-12). `file_path` = videos.path URI."""
    ask = vision_fn or vision_chat
    prep = await asyncio.to_thread(_prepare, file_path, config)
    try:
        names, refused = await _ask_model(prep, ask)
    except TaggingFailure as exc:
        try:
            tags_state.observe_failure(exc.reason, exc.detail)
        except Exception:
            logger.exception("[tagging] observe_failure failed")
        raise
    try:
        await asyncio.to_thread(tags_state.observe_success)
    except Exception:
        logger.exception("[tagging] observe_success failed")
    return await asyncio.to_thread(_write, prep, file_path, names, refused)


def tag_video_sync(
    file_path: str, *, config: dict | None = None, vision_fn=None
) -> TagOutcome:
    """Sync wrapper; only call from a worker thread with no running event loop."""
    return asyncio.run(tag_video(file_path, config=config, vision_fn=vision_fn))


_TEST_UNUSABLE_REASONS = frozenset({"model_unsupported", "bad_response"})


async def run_vision_test(conn, vocab, sample_uri, *, vision_fn=None) -> dict:
    """One-shot vision probe for the settings test button (no writes)."""
    ask = vision_fn or vision_chat
    prep = _Prepared(
        cfg={},
        repo=None,
        conn=conn,
        poster_uri=sample_uri,
        vocab=list(vocab),
        local_fs_path="",
    )
    try:
        names, refused = await _ask_model(prep, ask)
    except TaggingFailure as exc:
        if exc.reason in _TEST_UNUSABLE_REASONS:
            return {"ok": False, "outcome": "unusable", "detail": exc.reason}
        return {
            "ok": False,
            "outcome": "unreachable",
            "detail": exc.detail or exc.reason,
        }
    if refused:
        return {"ok": False, "outcome": "unusable", "detail": "refused"}
    if not names:
        return {"ok": False, "outcome": "unusable", "detail": "no_tags"}
    return {"ok": True, "outcome": "ok", "tags": names}
