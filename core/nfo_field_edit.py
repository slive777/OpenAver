"""nfo_field_edit.py — NFO 欄位寫入核心：純樹處理（TASK-200c-T2a）。

九個進階編輯欄位（片名、原文片名、女優、片商、系列、發行日、簡介、
簡介譯文、標籤）的寫入集合＝`core.nfo_read` 讀取鏈；只改該欄元素、
其餘元素（含註解、處理指令、不認得的元素）一個不少。

純函式層：不做任何 IO（不碰檔案系統、不讀寫檔）。
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date as _date

from core import nfo_title_format as _ntf
from core import nfo_utils as _nu
from core.cover_attributes import is_source_4k_tag
from core.nfo_read import (
    DATE_TAGS,
    MAKER_TAGS,
    MANUAL_MAKER_TAG,
    nfo_actor_names,
    nfo_first_text,
    nfo_merged_tags,
    nfo_text,
    nfo_title_record,
)
from core.nfo_title_format import build_display_title, resolve_title_body
from core.nfo_updater import set_element_text
from core.title_writeback import apply_title_elements, strip_illegal_xml_chars

ERROR_CODES = (
    "not_found",
    "invalid_path",
    "invalid_field",
    "invalid_value",
    "invalid_date",
    "title_empty",
    "tag_invalid",
    "tag_hidden",
    "borrowed",
    "no_nfo",
    "readonly_no_nfo",
    "nfo_ambiguous",
    "nfo_unreadable",
    "nfo_link_outside",
    "unreachable",
    "nfo_write_failed",
    "db_write_failed",
)

FIELD_DB_FIELDS = {
    "title": ("title",),
    "original_title": ("original_title",),
    "actresses": ("actresses",),
    "maker": ("maker",),
    "series": ("series",),
    "release_date": ("release_date",),
    "plot": ("has_plot",),
    "plot_translation": ("has_plot",),
    "tags": ("tags",),
}

_DEFAULT_FORMAT = "[{num}]{title}"

_PLACEHOLDER_ACTRESS = frozenset({"actor", "actors"})
_PLACEHOLDER_MAKER = frozenset({"maker"})
_PLACEHOLDER_DATE = frozenset({"date", "year", "month", "day"})


class FieldEditError(Exception):
    def __init__(self, code: str):
        if code not in ERROR_CODES:
            raise ValueError(code)
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class EditContext:
    number: str
    nfo_title_format: str = "[{num}]{title}"


@dataclass(frozen=True)
class FieldResult:
    changed: bool
    db_fields: tuple[str, ...]


_PROTECTED_RE = re.compile(rb'<!--.*?-->|<\?.*?\?>|<!\[CDATA\[.*?\]\]>', re.DOTALL)


def repair_bare_amp(raw: bytes) -> bytes:
    parts = []
    pos = 0
    for m in _PROTECTED_RE.finditer(raw):
        parts.append(_nu._BARE_AMP_RE.sub(b"&amp;", raw[pos:m.start()]))
        parts.append(m.group())
        pos = m.end()
    parts.append(_nu._BARE_AMP_RE.sub(b"&amp;", raw[pos:]))
    return b"".join(parts)


def _parse_keep_comments(raw: bytes) -> ET.Element:
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True, insert_pis=True))
    parser.feed(raw)
    return parser.close()


def load_tree(raw: bytes) -> ET.Element:
    try:
        return _parse_keep_comments(raw)
    except ET.ParseError:
        pass
    try:
        return _parse_keep_comments(repair_bare_amp(raw))
    except ET.ParseError as e:
        raise FieldEditError("nfo_unreadable") from e


def dump_tree(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def format_placeholders(template: str) -> frozenset[str]:
    return frozenset(_ntf._PLACEHOLDER_RE.findall(template or ""))


def read_plot_pair(root: ET.Element) -> tuple[str, str]:
    plot = nfo_text(root, "plot")
    orig = nfo_text(root, "originalplot")
    if orig:
        return orig, plot
    return plot, ""


def _snapshot(node) -> tuple:
    if callable(node.tag):
        return ("#node:" + node.tag.__name__, (node.text or "").strip(), (), ())
    kids = tuple(_snapshot(c) for c in node)
    return (node.tag, (node.text or "").strip(), tuple(sorted(node.attrib.items())), kids)


def _chain_elements(root: ET.Element, tags) -> list:
    out = []
    for t in tags:
        e = root.find(t)
        if e is not None:
            out.append(e)
    return out


def _clean(value: str) -> str:
    return strip_illegal_xml_chars(value).strip()


def _need_title_recalc(fmt: str, field: str) -> bool:
    if field == "title":
        return True
    if fmt == _DEFAULT_FORMAT and field != "title":
        return False
    ph = format_placeholders(fmt)
    if field == "actresses":
        return bool(ph & _PLACEHOLDER_ACTRESS)
    if field == "maker":
        return bool(ph & _PLACEHOLDER_MAKER)
    if field == "release_date":
        return bool(ph & _PLACEHOLDER_DATE)
    return False


def _title_body_before(root, ctx, field):
    if not _need_title_recalc(ctx.nfo_title_format, field):
        return None
    body0 = resolve_title_body(
        nfo_text(root, "title"), ctx.number, nfo_actor_names(root),
        nfo_first_text(root, MAKER_TAGS), nfo_first_text(root, DATE_TAGS),
        ctx.nfo_title_format, nfo_title_record(root))
    return body0 or None


def _recalc_title_after(root, ctx, field, body0) -> None:
    if body0 is None:
        return
    apply_title_elements(
        root, number=ctx.number, title_body=body0, original_title=None,
        actors=nfo_actor_names(root), maker=nfo_first_text(root, MAKER_TAGS),
        date=nfo_first_text(root, DATE_TAGS), nfo_title_format=ctx.nfo_title_format)


def _edit_title(root, value, ctx) -> None:
    if nfo_text(root, "title"):
        old_record = nfo_title_record(root)
        old_body = resolve_title_body(
            nfo_text(root, "title"), ctx.number, nfo_actor_names(root),
            nfo_first_text(root, MAKER_TAGS), nfo_first_text(root, DATE_TAGS),
            ctx.nfo_title_format, old_record)
    else:
        old_body = ""
    if value == old_body:
        return
    number = ctx.number or ""
    _, body = build_display_title(
        number, value, "", nfo_actor_names(root),
        nfo_first_text(root, MAKER_TAGS), nfo_first_text(root, DATE_TAGS),
        ctx.nfo_title_format)
    if not body:
        raise FieldEditError("title_empty")
    apply_title_elements(
        root, number=number, title_body=value, original_title=None,
        actors=nfo_actor_names(root), maker=nfo_first_text(root, MAKER_TAGS),
        date=nfo_first_text(root, DATE_TAGS), nfo_title_format=ctx.nfo_title_format)


def _edit_original_title(root, value, ctx) -> None:
    elem = root.find("originaltitle")
    if not value:
        if elem is not None:
            elem.text = ""
        return
    if elem is not None:
        elem.text = value
    else:
        set_element_text(root, "originaltitle", value, after_tag="title")


def _edit_maker(root, value, ctx) -> None:
    elems = _chain_elements(root, MAKER_TAGS)
    if not value:
        for e in elems:
            e.text = ""
        old = root.find(MANUAL_MAKER_TAG)
        if old is not None:
            root.remove(old)
        return
    for e in elems:
        e.text = value
    if not elems:
        set_element_text(root, "studio", value)
    pin = root.find(MANUAL_MAKER_TAG)
    if pin is not None:
        pin.text = "1"
    else:
        set_element_text(root, MANUAL_MAKER_TAG, "1")


def _edit_series(root, value, ctx) -> None:
    if not value:
        for name_elem in list(root.findall("set/name")):
            parent = next((p for p in root.iter() if name_elem in list(p)), None)
            if parent is not None:
                parent.remove(name_elem)
        return
    target = root.find("set/name")
    if target is not None:
        target.text = value
        return
    first_set = root.find("set")
    if first_set is not None:
        sub = ET.SubElement(first_set, "name")
        sub.text = value
        return
    new_set = ET.SubElement(root, "set")
    sub = ET.SubElement(new_set, "name")
    sub.text = value


def _edit_date(root, value, ctx) -> None:
    if not value:
        for t in DATE_TAGS:
            e = root.find(t)
            if e is not None:
                e.text = ""
        return
    for t in ("release", "premiered"):
        e = root.find(t)
        if e is not None:
            e.text = value
    if root.find("release") is None and root.find("premiered") is None:
        set_element_text(root, "premiered", value)
    e = root.find("year")
    if e is not None:
        e.text = value[:4]


def _read_actors(root) -> tuple[list, list]:
    parent = {c: p for p in root.iter() for c in p}
    found = []
    for name_elem in root.findall(".//actor/name"):
        if not ((name_elem.text or "").strip()):
            continue
        actor = parent.get(name_elem)
        if actor is None:
            continue
        holder = parent.get(actor, root)
        found.append((actor, holder, (name_elem.text or "").strip()))
    return found, parent


def _dedup_nonempty(items) -> list:
    seen = set()
    return [t for t in items if t and not (t in seen or seen.add(t))]


def _actors_keep(found, names) -> dict:
    keep = {}
    for actor, _holder, n in found:
        if n in names and n not in keep:
            keep[n] = actor
    return keep


def _actors_need_rebuild(root, found, keep, ordered_unique) -> bool:
    parents = set()
    for a in keep.values():
        par = next((p for p in root.iter() if a in list(p)), root)
        parents.add(id(par))
    tail_ok = len(parents) <= 1 if keep else True
    if keep:
        first_actor = next(iter(keep.values()))
        first_parent = next((p for p in root.iter() if first_actor in list(p)), root)
        kids = list(first_parent)
        idx = [kids.index(a) for a in keep.values() if a in kids]
        tail_ok = tail_ok and idx == sorted(idx)
    kept_ordered = [n for n in ordered_unique if n in keep]
    new_names = [n for n in ordered_unique if n not in keep]
    trailing = ordered_unique[len(kept_ordered):] if kept_ordered else ordered_unique
    return (set(keep) != set(n for _a, _h, n in found)
            or [n for _a, _h, n in found if n in keep] != kept_ordered
            or not tail_ok
            or new_names != trailing)


def _actors_append_tail(root, keep, ordered_unique) -> None:
    for n in ordered_unique:
        if n in keep:
            continue
        new_actor = ET.Element("actor")
        ET.SubElement(new_actor, "name").text = n
        last = next(reversed([a for a in keep.values()]), None)
        par = next((p for p in root.iter() if last in list(p)), root) if last is not None else root
        kids = list(par)
        par.insert(kids.index(last) + 1 if last in kids else len(kids), new_actor)
        keep[n] = new_actor


def _actors_rebuild(root, found, keep, ordered_unique) -> None:
    first_actor = found[0][0]
    anchor_parent = next((p for p in root.iter() if first_actor in list(p)), root)
    anchor_idx = list(anchor_parent).index(first_actor)
    for actor, _holder, _n in list(found):
        par = next((p for p in root.iter() if actor in list(p)), None)
        if par is not None:
            par.remove(actor)
    for i, n in enumerate(ordered_unique):
        if n in keep:
            elem = keep[n]
        else:
            elem = ET.Element("actor")
            ET.SubElement(elem, "name").text = n
        anchor_parent.insert(anchor_idx + i, elem)


def _actors_clear(root, found) -> None:
    for actor, _holder, _n in list(found):
        par = next((p for p in root.iter() if actor in list(p)), None)
        if par is not None:
            par.remove(actor)


def _edit_actresses(root, names, ctx) -> None:
    found, _parent = _read_actors(root)
    if not names:
        _actors_clear(root, found)
        return
    keep = _actors_keep(found, names)
    ordered_unique = list(dict.fromkeys(names))
    if _actors_need_rebuild(root, found, keep, ordered_unique):
        _actors_rebuild(root, found, keep, ordered_unique)
    else:
        _actors_append_tail(root, keep, ordered_unique)


def _write_plots(root, plot_val, orig_val) -> None:
    if not plot_val and not orig_val:
        e = root.find("plot")
        if e is not None:
            e.text = ""
        old = root.find("originalplot")
        if old is not None:
            root.remove(old)
        return
    if plot_val and not orig_val:
        if root.find("plot") is not None:
            root.find("plot").text = plot_val
        else:
            set_element_text(root, "plot", plot_val, after_tag="premiered")
        old = root.find("originalplot")
        if old is not None:
            root.remove(old)
        return
    if plot_val and orig_val:
        if root.find("plot") is not None:
            root.find("plot").text = orig_val
        else:
            set_element_text(root, "plot", orig_val, after_tag="premiered")
        old = root.find("originalplot")
        if old is not None:
            old.text = plot_val
        else:
            rec = ET.Element("originalplot")
            rec.text = plot_val
            kids = list(root)
            pi = next((i for i, c in enumerate(kids) if c.tag == "plot"), len(kids))
            root.insert(pi + 1, rec)
        return
    if root.find("plot") is not None:
        root.find("plot").text = orig_val
    else:
        set_element_text(root, "plot", orig_val, after_tag="premiered")
    old = root.find("originalplot")
    if old is not None:
        root.remove(old)


def _edit_tags(root, add, remove) -> None:
    merged = nfo_merged_tags(root)
    for t in remove:
        for elem in list(root.findall("tag")):
            if (elem.text or "").strip() == t:
                root.remove(elem)
        for elem in list(root.findall("genre")):
            if (elem.text or "").strip() == t:
                root.remove(elem)
    merged = [t for t in merged if t not in set(remove)]
    for t in add:
        if t in merged:
            continue
        tag_elem = ET.SubElement(root, "tag")
        tag_elem.text = t
        genre_elem = ET.SubElement(root, "genre")
        genre_elem.text = t
        merged.append(t)


_HANDLERS = ("title", "original_title", "actresses", "maker", "series",
             "release_date", "plot", "plot_translation", "tags")


def _validate_tags_payload(payload) -> tuple:
    add = payload.get("add", [])
    remove = payload.get("remove", [])
    for key in ("add", "remove"):
        if key in payload and not isinstance(payload[key], list):
            raise FieldEditError("invalid_value")
        for item in payload.get(key, []):
            if not isinstance(item, str):
                raise FieldEditError("invalid_value")
    add_u = _dedup_nonempty([_clean(t) for t in add])
    rem_u = _dedup_nonempty([_clean(t) for t in remove])
    for t in add_u:
        if "," in t:
            raise FieldEditError("tag_invalid")
        if is_source_4k_tag(t):
            raise FieldEditError("tag_hidden")
    return [t for t in add_u if t not in set(rem_u)], rem_u


def _clean_single_value(value) -> str:
    if not isinstance(value, str):
        raise FieldEditError("invalid_value")
    return _clean(value)


def _validate_date(cleaned) -> None:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", cleaned):
        raise FieldEditError("invalid_date")
    try:
        _date.fromisoformat(cleaned)
    except ValueError:
        raise FieldEditError("invalid_date") from None


def _edit_scalar(root, field, cleaned, ctx, body0=None, before=None) -> None:
    if field == "original_title":
        _edit_original_title(root, cleaned, ctx)
    elif field == "maker":
        _edit_maker(root, cleaned, ctx)
        if before is None or _snapshot(root) != before:
            _recalc_title_after(root, ctx, field, body0)
    elif field == "series":
        _edit_series(root, cleaned, ctx)
    elif field == "release_date":
        _edit_date(root, cleaned, ctx)
        if before is None or _snapshot(root) != before:
            _recalc_title_after(root, ctx, field, body0)
    elif field == "plot":
        _write_plots(root, cleaned, read_plot_pair(root)[1])
    else:
        _write_plots(root, read_plot_pair(root)[0], cleaned)


def apply_field(root: ET.Element, field: str, payload: dict, ctx: EditContext) -> FieldResult:
    if field not in _HANDLERS:
        raise FieldEditError("invalid_field")
    if not isinstance(payload, dict):
        raise FieldEditError("invalid_value")
    if field == "tags":
        eff_add, rem_u = _validate_tags_payload(payload)
        before = _snapshot(root)
        _edit_tags(root, eff_add, rem_u)
        return FieldResult(_snapshot(root) != before, FIELD_DB_FIELDS[field])
    if "value" not in payload:
        raise FieldEditError("invalid_value")
    if field == "actresses":
        raw_names = payload["value"]
        if not isinstance(raw_names, list) or any(not isinstance(n, str) for n in raw_names):
            raise FieldEditError("invalid_value")
        names = _dedup_nonempty([_clean(n) for n in raw_names])
        body0 = _title_body_before(root, ctx, field)
        before = _snapshot(root)
        _edit_actresses(root, names, ctx)
        if _snapshot(root) != before:
            _recalc_title_after(root, ctx, field, body0)
        return FieldResult(_snapshot(root) != before, FIELD_DB_FIELDS[field])
    value = payload["value"]
    if field == "title":
        if not isinstance(value, str):
            raise FieldEditError("invalid_value")
        cleaned = strip_illegal_xml_chars(value).strip()
        if not cleaned:
            raise FieldEditError("title_empty")
        before = _snapshot(root)
        _edit_title(root, cleaned, ctx)
        return FieldResult(_snapshot(root) != before, FIELD_DB_FIELDS[field])
    cleaned = _clean_single_value(value)
    if field == "release_date" and cleaned:
        _validate_date(cleaned)
    body0 = _title_body_before(root, ctx, field)
    before = _snapshot(root)
    _edit_scalar(root, field, cleaned, ctx, body0, before)
    return FieldResult(_snapshot(root) != before, FIELD_DB_FIELDS[field])
