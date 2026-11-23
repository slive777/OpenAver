"""Pure custom OpenAI group rules (CD-206-8 and CD-206-18)."""

import re
from collections.abc import Mapping

OPENAI_CUSTOM_ID_RE = r"oc[0-9a-f]{8}"
MAX_CUSTOM_GROUPS = 5
NAME_MAX_LENGTH = 30
RESERVED_NAME = "預設"  # 對應前端 reservedNames。


def is_valid_group_id(gid) -> bool:
    return isinstance(gid, str) and re.fullmatch(OPENAI_CUSTOM_ID_RE, gid) is not None


def parse_openai_provider(value) -> str | None:
    if not isinstance(value, str) or not value.startswith("openai:"):
        return None
    gid = value[len("openai:"):]
    return gid if is_valid_group_id(gid) else None


def custom_key_path(gid) -> str:
    if not is_valid_group_id(gid):
        raise ValueError("Invalid custom group ID")
    return f"translate.openai_custom.{gid}.api_key"


def validate_custom_groups(names_by_id: Mapping[str, str]) -> str | None:
    if len(names_by_id) > MAX_CUSTOM_GROUPS:
        return "too_many"
    if any(not is_valid_group_id(gid) for gid in names_by_id):
        return "invalid_group_id"
    seen: set[str] = set()
    for name in names_by_id.values():
        value = name.strip()
        if not value:
            return "empty"
        if len(value) > NAME_MAX_LENGTH:
            return "too_long"
        key = value.lower()
        if key == RESERVED_NAME:
            return "reserved"
        if key in seen:
            return "duplicate"
        seen.add(key)
    return None


def coerce_dangling_providers(payload: dict) -> None:
    translate = payload.get("translate") or {}
    ai_services = payload.get("ai_services") or {}
    tags = ai_services.get("tags") or {}
    groups = translate.get("openai_custom") or {}
    for holder in (translate, tags):
        provider = holder.get("provider")
        if isinstance(provider, str) and provider.startswith("openai:") and (
            parse_openai_provider(provider) not in groups
        ):
            holder["provider"] = "openai"
