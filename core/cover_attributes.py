"""檔名後綴 → 屬性 tag 的單一資料來源，加上合併／去重純函式。

表的列數不固定，`-UC` 不是獨立列：id 有 subtitle / cracked / ltx / leaked / 4k / vr，
`-UC` / `-CU` 是 subtitle 與 cracked 共用的 token。
「無碼」（片商本身無碼）不在本表。
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

_BARE_LEFT = r"(?<![0-9A-Za-z一-鿿])"
_BARE_RIGHT = r"(?![0-9A-Za-z一-鿿])"
_PREFIXED_RIGHT = r"(?=[-_.\s]|$)"


@dataclass(frozen=True)
class AttributeRule:
    id: str
    canonical_tag: str
    display_name: str
    match_aliases: tuple[str, ...]
    display_order: int
    i18n_key: str
    source: str
    tokens: tuple[str, ...] = ()
    supersedes: tuple[str, ...] = ()


_LTX_TOKENS = ("-ltx", "_ltx", ".ltx")


ATTRIBUTE_TABLE: tuple[AttributeRule, ...] = (
    AttributeRule(
        id="subtitle",
        canonical_tag="中文字幕",
        display_name="中字",
        match_aliases=("中文字幕", "中字", "字幕"),
        display_order=1,
        i18n_key="settings.gallery.cover_badge.subtitle",
        source="filename_token",
        tokens=("-C", "_C", "-ch", "-UC", "-CU"),
    ),
    AttributeRule(
        id="cracked",
        canonical_tag="無碼破解",
        display_name="AI",
        match_aliases=("無碼破解", "破解", "克破", "AI"),
        display_order=2,
        i18n_key="settings.gallery.cover_badge.cracked",
        source="filename_token",
        tokens=("-U", "_U", "umr", "破解", "克破", "-UC", "-CU") + _LTX_TOKENS,
    ),
    AttributeRule(
        id="ltx",
        canonical_tag="LTX",
        display_name="LTX",
        match_aliases=("LTX",),
        display_order=2,
        i18n_key="settings.gallery.cover_badge.ltx",
        source="filename_token",
        tokens=_LTX_TOKENS,
        supersedes=("cracked",),
    ),
    AttributeRule(
        id="leaked",
        canonical_tag="無碼流出",
        display_name="LEAK",
        match_aliases=("無碼流出", "流出", "leak"),
        display_order=2,
        i18n_key="settings.gallery.cover_badge.leaked",
        source="filename_token",
        tokens=("-leak", "-uncensored", "leaked", "流出"),
    ),
    AttributeRule(
        id="4k",
        canonical_tag="4K",
        display_name="4K",
        match_aliases=("4K",),
        display_order=4,
        i18n_key="settings.gallery.cover_badge.4k",
        source="filename_token",
        tokens=("-4K", "-uhd", "-8k"),
    ),
    AttributeRule(
        id="vr",
        canonical_tag="VR",
        display_name="VR",
        match_aliases=("VR",),
        display_order=3,
        i18n_key="settings.gallery.cover_badge.vr",
        source="filename_token",
        tokens=("-VR",),
    ),
)


def _compile_token(token: str) -> re.Pattern[str]:
    escaped = re.escape(token.lower())
    if token[:1] in "-_.":
        return re.compile(escaped + _PREFIXED_RIGHT)
    return re.compile(_BARE_LEFT + escaped + _BARE_RIGHT)


_RULE_PATTERNS: tuple[tuple[AttributeRule, tuple[re.Pattern[str], ...]], ...] = tuple(
    (rule, tuple(_compile_token(token) for token in rule.tokens))
    for rule in ATTRIBUTE_TABLE
)

_RULE_4K = next(rule for rule in ATTRIBUTE_TABLE if rule.id == "4k")
_TAG_4K = _RULE_4K.canonical_tag
# 既有 scraper genre 的 4K 合流值（spec-121 §4.1 最後一條）：由 4K 那一列**自己的 token**
# 去掉前綴分隔符推導，不在這裡另寫一份字面清單——§4.7 要求表是單一資料來源，
# 手寫一份等於「新增一個 4K 同義詞要改兩個地方」。目前推導出 {"4k", "uhd", "8k"}。
_GENRE_4K_EQUIVALENTS = frozenset(token.lstrip("-_").lower() for token in _RULE_4K.tokens)

_MANIFEST_KEYS = (
    "id",
    "canonical_tag",
    "display_name",
    "match_aliases",
    "display_order",
    "i18n_key",
    "supersedes",
)


def _dedup_keep_first(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.strip().lower()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def effective_tags(filename: str, existing_tags: Iterable[str] | None) -> list[str]:
    if existing_tags is None:
        base: list[str] = []
    else:
        base = [t for t in existing_tags if t]

    lowered_name = filename.lower()
    candidates: list[str] = []
    for rule, patterns in _RULE_PATTERNS:
        if any(pattern.search(lowered_name) for pattern in patterns):
            candidates.append(rule.canonical_tag)

    for item in base:
        if item.strip().lower() in _GENRE_4K_EQUIVALENTS:
            candidates.append(_TAG_4K)
            break

    return _dedup_keep_first(base + candidates)


def _json_value(value):
    """序列型欄位（本表用 tuple 存）統一轉 list——JSON / pydantic 只會吐 array，
    端點回應與 manifest_payload() 才比得起來（test_response_equals_manifest_payload）。
    用型別判斷而非欄位名判斷：日後再加一個序列型欄位不必記得回來改這裡。"""
    return list(value) if isinstance(value, tuple) else value


def manifest_payload() -> list[dict]:
    return [
        {key: _json_value(getattr(rule, key)) for key in _MANIFEST_KEYS}
        for rule in ATTRIBUTE_TABLE
    ]
