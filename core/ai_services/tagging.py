"""AI tagging pure functions: prompt / parse / name map / failure / conn.

I/O orchestration (`tag_video`) lives in T7b.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field

from core.ai_services.tagging_vocab import VocabItem
from core.ai_services.vision_chat import VisionConn
from core.cloud_translate import TranslateError
from core.openai_client import OPENAI_OFFICIAL_BASE_URL
from core.secret_fields import read_secret

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
