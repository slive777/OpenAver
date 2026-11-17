"""nfo_read.py — shared, stateless NFO tag-extraction primitives (CD-113a-2).

Seven pure functions that collapse the "fallback chain / any-depth / merge-
dedup" resilience rules that used to be hand-written three times independently
in `core.enricher._nfo_to_meta`, `core.gallery_scanner.VideoScanner.parse_nfo`,
and `core.readonly_producer._nfo_to_producer_meta` (spec-113 §2.5 / F-1) into
a single owner. Each function takes an already-parsed `xml.etree.ElementTree`
`<movie>` root and returns a plain Python value — this module knows nothing
about `VideoInfo`, producer-meta, or enricher-meta output shapes (CD-113a-1);
shaping/joining/post-processing stays in each caller.

Declared coupling (§1.4, NOT part of this task's replacement scope):
`core.nfo_updater.add_actor`
(`core/nfo_updater.py:199-209`) independently relies on the same "any-depth
`.//actor/name`" rule to do its pre-write duplicate check. It does NOT call
`nfo_actor_names` here (different responsibility — write-time dedup vs.
read-time extraction) but if the any-depth rule in `nfo_actor_names` ever
changes, `add_actor` must be reviewed for drift.

`core.nfo_field_edit`（T2a）寫入集合須與這三個常數與本檔讀取鏈同步（照
`add_actor` 先例的寫法）：`MAKER_TAGS`／`DATE_TAGS`／`MANUAL_MAKER_TAG`。

Companion module: `core.nfo_stat` (F-5, filesystem `.nfo` mtime) is named
symmetrically but deliberately not merged — orthogonal failure domains
(`ET.ParseError` here vs. `OSError` there).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

MAKER_TAGS = ('maker', 'studio')
DATE_TAGS = ('release', 'premiered', 'year')
MANUAL_MAKER_TAG = 'openaver_manual_maker'


def nfo_text(root: ET.Element, tag: str) -> str:
    """Read a single top-level-path tag's text, stripped; `''` if absent/empty.

    Covers "tag missing", "`.text` is `None`", and "`.text` is all-whitespace"
    uniformly by falling back to `''` before `.strip()`. Replaces the `_text()`
    helper duplicated (byte-identical apart from quote style) in
    `core.enricher._nfo_to_meta` and `core.readonly_producer._nfo_to_producer_meta`,
    plus 5 inline `find()`-and-check blocks in
    `core.gallery_scanner.VideoScanner.parse_nfo` (title/originaltitle/
    director/label/thumb).

    CD-113a-7 known limitation (deliberately kept, not a bug): `Element.text`
    only holds the text between the opening tag and its FIRST child element.
    A value wrapped in a nested child — e.g. `<studio><name>X</name></studio>`
    — has `.text is None` and this function returns `''`, silently missing
    `X` (see `BE-SCRAPER-05`). This matches the pre-existing behavior of all
    three callers being replaced; it is not changed here. Boundary cases are
    pinned by `tests/unit/test_nfo_read.py`.
    """
    elem = root.find(tag)
    return (elem.text or "").strip() if elem is not None else ""


def nfo_first_text(root: ET.Element, tags: tuple[str, ...]) -> str:
    """Try `tags` in order; return the first tag's stripped text that is
    present, non-`None`, and non-whitespace-only. `''` if all `tags` miss.

    Replaces three independent "fallback chain" implementations that were
    provably equivalent but written differently: `VideoScanner.parse_nfo`'s
    hand-rolled `for tag in [...]: ... break` loops (num/maker/date) and
    `_nfo_to_meta` / `_nfo_to_producer_meta`'s `_text(a) or _text(b) or ...`
    chains. Both styles short-circuit on the first non-empty stripped value;
    this was verified equivalent across "tag absent" / "`.text` is `None`" /
    "`.text` all-whitespace" / "`.text` has content" in the T1c CD-113a-8
    query and is not re-verified here.
    """
    for tag in tags:
        elem = root.find(tag)
        if elem is not None and elem.text and elem.text.strip():
            return elem.text.strip()
    return ""


def nfo_actor_names(root: ET.Element) -> list[str]:
    """Any-depth `.//actor/name` actor names, stripped; a name whose stripped
    text is empty (missing `.text`, `''`, or whitespace-only such as `'   '`)
    is filtered out and does NOT appear in the result.

    Codex PR review P1 fix (TASK-113a-T4): previously a whitespace-only
    `.text` was truthy in Python and survived filtering, ending up as `''`
    in the returned list. A non-empty list containing only `''` reads as
    "actresses present" to `_missing_fields` (`core/enricher.py`), so a
    third-party NFO with a blank `<name>` silently suppressed a scrape that
    should have run. Blank text is not data, so it is now filtered the same
    way a missing/`None` `.text` already was.

    Any-depth lookup matters because a direct-children-only
    `root.findall('actor')` silently returns `[]` for a third-party NFO
    shaped `<movie><actors><actor><name>X</name></actor></actors></movie>`
    (actors nested one level deeper than OpenAver's own flat
    `<movie><actor>` shape).

    MUTATION LOCK (moved verbatim from `core/readonly_producer.py:1341-1342`):
    reverting this to `root.findall('actor')` must turn
    `test_nested_actors_element_any_depth` RED (`test_readonly_producer.py`).
    """
    return [
        stripped
        for n in root.findall(".//actor/name")
        if (stripped := (n.text or "").strip())
    ]


def nfo_merged_tags(root: ET.Element) -> list[str]:
    """`<genre>` tags first, then `<tag>` tags, order-preserving dedup across
    BOTH loops (a `<tag>` value already seen as a `<genre>` is skipped too).
    A tag whose stripped text is empty (missing `.text`, `''`, or
    whitespace-only such as `'   '`) is filtered out and does NOT appear in
    the result.

    Codex PR review P1 fix (TASK-113a-T4): previously a whitespace-only
    `.text` was truthy in Python and survived filtering, ending up as `''`
    in the returned list. A non-empty list containing only `''` reads as
    "tags present" to `_missing_fields` (`core/enricher.py`), so a
    third-party NFO with a blank `<genre>`/`<tag>` silently suppressed a
    scrape that should have run. Blank text is not data, so it is now
    filtered the same way a missing/`None` `.text` already was.

    Replaces three independently hand-written genre/tag merge loops. Prior to
    T1c, `VideoScanner.parse_nfo`'s genre loop did not dedup among genres
    themselves (CD-113a-8(c)); T1c aligned it, and this function is the
    single remaining copy of that now-shared merge-with-dedup rule.
    """
    tags: list[str] = []
    for genre_elem in root.findall("genre"):
        t = (genre_elem.text or "").strip()
        if t and t not in tags:
            tags.append(t)
    for tag_elem in root.findall("tag"):
        t = (tag_elem.text or "").strip()
        if t and t not in tags:
            tags.append(t)
    return tags


def nfo_series_name(root: ET.Element) -> str:
    """`<set><name>...</name></set>` series name, stripped; `''` if absent.

    Path-style lookup (`root.find("set/name")`) — will skip past a first
    `<set>` element that has no `<name>` child and match a later
    `<set><name>` sibling (CD-113a-8(b)). Replaces the equivalent three-way
    duplicated read (one three-line ternary form, one inline-if form) in
    `_nfo_to_meta`, `VideoScanner.parse_nfo`, and `_nfo_to_producer_meta`.
    """
    elem = root.find("set/name")
    return (elem.text or "").strip() if elem is not None else ""


def nfo_runtime_minutes(root: ET.Element) -> int | None:
    """`<runtime>` parsed as `int` minutes; `None` if the tag is absent, its
    text is empty/whitespace-only, or it fails `int()` (non-numeric/decimal).
    Negative integers ARE accepted (no sign/range validation) — matches
    pre-existing behavior across all three replaced call sites.

    Replaces `_nfo_to_meta`'s `runtime_text = _text("runtime"); try: int(...)
    except ValueError: None`, `VideoScanner.parse_nfo`'s `if ... and
    runtime_elem.text:`-guarded try/except, and `_nfo_to_producer_meta`'s
    `if runtime_text:`-guarded try/except. The two guarded forms only skip
    `int('')` early; `int('')` itself already raises `ValueError`, which the
    bare try/except here catches identically — verified equivalent across
    "tag absent" / "empty" / "whitespace-only" / "non-numeric" / "valid
    integer (incl. negative)" in the T1b query and not re-verified here.
    """
    elem = root.find("runtime")
    text = (elem.text or "").strip() if elem is not None else ""
    try:
        return int(text)
    except ValueError:
        return None


def nfo_title_record(root: ET.Element) -> tuple[str, str] | None:
    """Read `<openaver_title_record>`'s `<written>` / `<body>` texts.

    Returns `(written, body)` only when both stripped texts are non-empty;
    otherwise `None` (record absent, either child missing, or either text
    empty/whitespace-only). Pure XML extraction — no title-format business
    logic (CD-154b-6).
    """
    record = root.find("openaver_title_record")
    if record is None:
        return None
    written_elem = record.find("written")
    body_elem = record.find("body")
    written = (written_elem.text or "").strip() if written_elem is not None else ""
    body = (body_elem.text or "").strip() if body_elem is not None else ""
    if written and body:
        return (written, body)
    return None
