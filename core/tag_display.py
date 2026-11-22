"""顯示層標籤算法的唯一真相來源（205b-T1）。

回答兩件事：哪些字要藏（黑名單字若屬某使用者別名組則整組一起藏，
封面標章字永遠不藏）、一顆標籤該顯示成什麼字（別名組換成主名稱，
換完以完全相同字串去重、保留第一次出現的位置）。

純函式＋frozen dataclass，不碰 DB、不 import web。
`core.database` 一律函式內 lazy import（BE-PY-08）。
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from core.cover_attributes import protected_tag_words
from core.logger import get_logger

logger = get_logger(__name__)

COMMON_BLACKLIST_SUGGESTIONS: tuple[str, ...] = (
    "ハイビジョン",
    "独占配信",
    "高畫質",
    "DMM獨家",
    "単体作品",
    "ブルーレイ",
    "Blu-ray",
    "高解析度",
)


@dataclass(frozen=True)
class TagDisplayContext:
    hidden: frozenset[str]
    primary_of: dict[str, str]


def build_context(
    blacklist_names: Iterable[str],
    alias_groups: Iterable[list[str]],
    protected: Iterable[str] | None = None,
) -> TagDisplayContext:
    group_key_sets: list[set[str]] = []
    primary_of: dict[str, str] = {}
    for group in alias_groups or []:
        cleaned = [member.strip() for member in group]
        cleaned = [member for member in cleaned if member]
        if not cleaned:
            continue
        primary = cleaned[0]
        keys = {member.lower() for member in cleaned}
        for key in keys:
            primary_of[key] = primary
        group_key_sets.append(keys)
    key_to_group: dict[str, set[str]] = {}
    for keys in group_key_sets:
        for key in keys:
            key_to_group[key] = keys
    expanded: set[str] = set()
    for name in blacklist_names or []:
        key = name.strip().lower()
        if not key:
            continue
        members = key_to_group.get(key)
        if members is None:
            expanded.add(key)
        else:
            expanded.update(members)
    if protected is None:
        protected_keys = set(protected_tag_words())
    else:
        protected_keys = set()
        for word in protected:
            key = word.strip().lower()
            if key:
                protected_keys.add(key)
    protected_closure = set(protected_keys)
    for keys in group_key_sets:
        if keys & protected_keys:
            protected_closure.update(keys)
    hidden = expanded - protected_closure
    return TagDisplayContext(hidden=frozenset(hidden), primary_of=primary_of)


def load_context(db_path: Path | None = None) -> TagDisplayContext:
    from core.database import TagAliasRepository, TagBlacklistRepository

    try:
        blacklist_names = [
            row["name"] for row in TagBlacklistRepository(db_path).get_all()
        ]
        alias_groups = [
            [record.primary_name, *record.aliases]
            for record in TagAliasRepository(db_path).get_all()
        ]
    except Exception as exc:
        logger.warning(f"載入標籤顯示設定失敗：{exc}")
        return TagDisplayContext(hidden=frozenset(), primary_of={})
    return build_context(blacklist_names, alias_groups)


def display_tags(tags: Iterable[str], ctx: TagDisplayContext) -> list[str]:
    shown_tags: list[str] = []
    seen: set[str] = set()
    for raw in tags or []:
        if not isinstance(raw, str):
            continue
        tag = raw.strip()
        if not tag:
            continue
        key = tag.lower()
        if key in ctx.hidden:
            continue
        shown = ctx.primary_of.get(key, tag)
        if shown in seen:
            continue
        seen.add(shown)
        shown_tags.append(shown)
    return shown_tags


def is_hidden_tag(tag: str, ctx: TagDisplayContext) -> bool:
    if not isinstance(tag, str):
        return False
    return tag.strip().lower() in ctx.hidden
