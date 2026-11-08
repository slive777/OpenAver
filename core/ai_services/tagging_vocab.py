"""AI tagging vocabulary: shipped builtin JSON + custom store on data root."""

from __future__ import annotations

import json
import threading
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from core.atomic_write import atomic_write
from core.data_root import get_data_root, is_layout_finalized
from core.logger import get_logger

logger = get_logger(__name__)

NAME_MAX = 20
DEF_MAX = 100
CUSTOM_MAX = 40
CUSTOM_FILENAME = "ai_tag_vocab.json"

_LOCK = threading.Lock()


@dataclass(frozen=True)
class VocabItem:
    name: str
    source: str
    group: str
    definition: str
    model_name: str
    aliases: tuple[str, ...] = ()
    hidden: bool = False


class VocabError(Exception):
    """Validation / store error; `.reason` is the stable code for callers."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


_builtin_cache: list[VocabItem] | None = None


def load_builtin() -> list[VocabItem]:
    """Load shipped vocab once; module-level cache (immutable at runtime)."""
    global _builtin_cache
    if _builtin_cache is not None:
        return _builtin_cache
    path = Path(__file__).with_name("tagging_vocab.json")
    rows = json.loads(path.read_text(encoding="utf-8"))
    items: list[VocabItem] = []
    for row in rows:
        aliases = row.get("aliases") or []
        items.append(
            VocabItem(
                name=row["display_name"],
                source="builtin",
                group=row["group"],
                definition=row["def"],
                model_name=row["model_name"],
                aliases=tuple(aliases),
                hidden=bool(row.get("hidden", False)),
            )
        )
    _builtin_cache = items
    return items


def _builtin_names() -> set[str]:
    names: set[str] = set()
    for item in load_builtin():
        names.add(item.name)
        names.add(item.model_name)
    return names


def _custom_path() -> Path:
    return get_data_root() / CUSTOM_FILENAME


def _parse_custom_entry(entry: object) -> VocabItem | None:
    if not isinstance(entry, dict):
        return None
    name = entry.get("name")
    if not isinstance(name, str) or not name:
        return None
    definition = entry.get("definition", "")
    if not isinstance(definition, str):
        definition = ""
    return VocabItem(
        name=name,
        source="custom",
        group="自訂",
        definition=definition,
        model_name=name,
        aliases=(),
    )


def _load_custom(*, strict: bool) -> list[VocabItem]:
    """Read custom vocab. Missing file → []. Display degrades; write raises."""
    path = _custom_path()
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        if strict:
            raise VocabError("custom_unreadable") from None
        logger.warning("ai_tag_vocab: unreadable or corrupt %s", path)
        return []
    if not isinstance(raw, dict) or not isinstance(raw.get("items"), list):
        if strict:
            raise VocabError("custom_unreadable")
        logger.warning("ai_tag_vocab: bad top-level shape at %s", path)
        return []
    out: list[VocabItem] = []
    for entry in raw["items"]:
        item = _parse_custom_entry(entry)
        if item is not None:
            out.append(item)
    return out


def load_custom() -> list[VocabItem]:
    """Read custom vocab from data root every time (no cache; degrade on error)."""
    return _load_custom(strict=False)


_warned_custom_collisions: set[str] = set()


def merged() -> list[VocabItem]:
    return [*load_builtin(), *_custom_without_collisions()]


def _custom_without_collisions() -> list[VocabItem]:
    builtin_names: set[str] = set()
    for item in load_builtin():
        builtin_names.add(item.name)
        builtin_names.add(item.model_name)
    out: list[VocabItem] = []
    for custom in load_custom():
        if custom.name in builtin_names:
            if custom.name not in _warned_custom_collisions:
                _warned_custom_collisions.add(custom.name)
                logger.warning(
                    "ai_tag_vocab: custom %r collides with builtin, builtin wins",
                    custom.name,
                )
            continue
        out.append(custom)
    return out


def _has_control_char(text: str) -> bool:
    return any(unicodedata.category(c)[0] == "C" for c in text)


def _validate_definition(definition: str) -> str:
    text = definition.strip()
    if "\n" in text or "\r" in text:
        raise VocabError("definition_invalid")
    if len(text) > DEF_MAX:
        raise VocabError("definition_invalid")
    return text


def _write_custom(items: list[VocabItem]) -> None:
    path = _custom_path()
    payload = {
        "version": 1,
        "items": [{"name": i.name, "definition": i.definition} for i in items],
    }
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    with atomic_write(path, mode="wb") as handle:
        handle.write(data)


def add_custom(name: str, definition: str = "") -> VocabItem:
    """Validate then append one custom word; returns the stored item."""
    name = name.strip()
    if not name:
        raise VocabError("name_empty")
    if len(name) > NAME_MAX:
        raise VocabError("name_too_long")
    if _has_control_char(name):
        raise VocabError("name_invalid")
    if name in _builtin_names():
        raise VocabError("name_conflict_builtin")
    definition = _validate_definition(definition)
    if not is_layout_finalized(get_data_root()):
        raise VocabError("data_root_not_ready")
    with _LOCK:
        current = _load_custom(strict=True)
        if any(item.name == name for item in current):
            raise VocabError("name_exists")
        if len(current) >= CUSTOM_MAX:
            raise VocabError("vocab_full")
        item = VocabItem(
            name=name,
            source="custom",
            group="自訂",
            definition=definition,
            model_name=name,
            aliases=(),
        )
        _write_custom([*current, item])
        return item


def remove_custom(name: str) -> None:
    """Remove one custom word by exact stored name (after strip)."""
    name = name.strip()
    if not is_layout_finalized(get_data_root()):
        raise VocabError("data_root_not_ready")
    with _LOCK:
        current = _load_custom(strict=True)
        kept = [item for item in current if item.name != name]
        if len(kept) == len(current):
            raise VocabError("not_found")
        _write_custom(kept)
