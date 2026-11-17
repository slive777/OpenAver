"""nfo_field_edit.py — NFO 欄位寫入核心：純樹處理（TASK-200c-T2a）。

九個進階編輯欄位（片名、原文片名、女優、片商、系列、發行日、簡介、
簡介譯文、標籤）的寫入集合＝`core.nfo_read` 讀取鏈；只改該欄元素、
其餘元素（含註解、處理指令、不認得的元素）一個不少。

純樹處理層與 IO 編排層。
"""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date as _date

from core import nfo_title_format as _ntf
from core import nfo_utils as _nu
from core.atomic_write import atomic_write
from core.config import get_configured_gallery_dirs
from core.cover_attributes import effective_tags, is_source_4k_tag
from core.gallery_scanner import VideoScanner
from core.logger import get_logger
from core.nfo_stat import nfo_mtime_or_none
from core.path_utils import is_path_under_dir, uri_to_local_fs_path
from core.readonly_paths import resolve_owning_output_root
from core.source_reachability import is_path_on_unreachable_source
from core.version_group import resolve_work, version_containing
from core.video_files_info import source_root_unreachable, stat_kind
from core.video_nfo_locate import locate_readonly_nfo, locate_video_nfo
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


logger = get_logger(__name__)


def _nc(p):
    return os.path.normcase(p)


def _within(real, root):
    try:
        return os.path.commonpath([_nc(real), _nc(root)]) == _nc(root)
    except ValueError:
        return False


def _roots(video, config, mappings, owning):
    if owning is not None:
        return [os.path.realpath(uri_to_local_fs_path(owning[2], mappings))]
    dirs, _ = get_configured_gallery_dirs(config)
    return [os.path.realpath(uri_to_local_fs_path(uri, mappings))
            for uri in dirs if is_path_under_dir(video.path, uri)]


def _absent_reason(repo, video, config, mappings):
    if source_root_unreachable(video.path, config.get('gallery', {})):
        return 'unreachable'
    work = resolve_work(repo, video.path, mappings)
    if work is not None and work.data_source is not None and work.data_source != version_containing(work, video.path):
        return 'borrowed'
    return 'no_nfo'


def locate_editable_nfo(repo, video, config, path_mappings):
    if is_path_on_unreachable_source(video.path, config.get('gallery', {})):
        return None, 'unreachable'
    owning = resolve_owning_output_root(video.path, config)
    if owning is not None:
        nfo, reason = locate_readonly_nfo(video, path_mappings, owning[2])
        if reason:
            return None, 'readonly_no_nfo' if reason == 'no_nfo' else reason
    else:
        nfo, reason = locate_video_nfo(video, config, path_mappings)
        if reason:
            return None, reason
        kind, _ = stat_kind(nfo)
        if kind == 'absent':
            return None, _absent_reason(repo, video, config, path_mappings)
        if kind == 'unreadable':
            return None, 'nfo_unreadable'
    real = os.path.realpath(nfo)
    if not any(_within(real, root) for root in _roots(video, config, path_mappings, owning)):
        return None, 'nfo_link_outside'
    return nfo, None


def write_nfo_atomic(nfo_fs, data: bytes, roots):
    real = os.path.realpath(nfo_fs)
    if not any(_within(real, os.path.realpath(root)) for root in roots):
        raise FieldEditError('nfo_link_outside')
    old = os.stat(real)
    with atomic_write(real) as f:
        if hasattr(os, 'fchmod'):
            try:
                os.fchmod(f.fileno(), stat.S_IMODE(old.st_mode))
            except OSError:
                logger.exception('NFO mode preservation failed')
        if hasattr(os, 'fchown'):
            try:
                os.fchown(f.fileno(), -1, old.st_gid)
            except OSError:
                logger.exception('NFO group preservation failed')
        f.write(data)


def _tag_view(tags, filename):
    filename_tags = {t.strip().lower() for t in effective_tags(filename, [])}
    return [{'text': t, 'from_filename': t.strip().lower() in filename_tags}
            for t in tags if not is_source_4k_tag(t)]


def _filename(video, mappings):
    return os.path.basename(uri_to_local_fs_path(video.path, mappings))


def read_edit_view(repo, video, config, path_mappings):
    readonly = resolve_owning_output_root(video.path, config) is not None
    nfo, reason = locate_editable_nfo(repo, video, config, path_mappings)
    if not reason:
        try:
            plot, translation = read_plot_pair(load_tree(Path(nfo).read_bytes()))
        except (OSError, FieldEditError):
            reason = 'nfo_unreadable'
    if reason:
        return {'success': True, 'state': 'blocked', 'reason': reason, 'readonly': readonly}
    values = {k: getattr(video, k) for k in ('title', 'original_title', 'actresses', 'maker', 'series', 'release_date')}
    values['series'] = values['series'] or ''
    values.update(plot=plot, plot_translation=translation)
    return {'success': True, 'state': 'ok', 'reason': None, 'readonly': readonly,
            'values': values, 'tags': _tag_view(video.tags, _filename(video, path_mappings))}


def _read_back(nfo, video, filename, mappings, fmt):
    scanner = VideoScanner(path_mappings=mappings, nfo_title_format=fmt)
    info = scanner.parse_nfo(nfo)
    if info is None:
        raise ValueError('NFO read failed')
    plots = read_plot_pair(load_tree(Path(nfo).read_bytes()))
    return {'title': info.title, 'original_title': info.originaltitle,
            'actresses': [a.strip() for a in info.actor.split(',') if a.strip()],
            'maker': scanner.normalize_maker(info.num or video.number or '', info.maker, pinned=info.maker_pinned),
            'series': info.series or '', 'release_date': info.date,
            'tags': effective_tags(filename, [g.strip() for g in info.genre.split(',') if g.strip()]),
            'has_plot': info.has_plot, 'plot': plots[0], 'plot_translation': plots[1]}


def _update_readback(repo, video, result, values, nfo):
    fields = {key: values[key] for key in result.db_fields}
    if not result.changed:
        fields = {k: v for k, v in fields.items()
                  if ((getattr(video, k) or '') != (v or '') if k == 'series'
                      else getattr(video, k) != v)}
    mtime = (nfo_mtime_or_none(Path(nfo)) if result.changed else None)
    if fields and not repo.update_nfo_fields(video.path, fields, mtime if mtime is not None else video.nfo_mtime):
        raise RuntimeError('NFO database update failed')


def _rollback_nfo(nfo_fs, raw, roots):
    try:
        write_nfo_atomic(nfo_fs, raw, roots)
    except Exception:
        logger.exception('NFO rollback failed')


def _response(field, result, values, filename):
    if field == 'tags':
        return {'success': True, 'unchanged': not result.changed, 'nfo_updated': result.changed,
                'values': {}, 'tags': _tag_view(values['tags'], filename)}
    keys = ('plot', 'plot_translation') if field in ('plot', 'plot_translation') else (field,)
    return {'success': True, 'unchanged': not result.changed, 'nfo_updated': result.changed,
            'values': {key: values[key] for key in keys}}


def _prepare_edit(nfo, field, payload, video, fmt):
    try:
        raw = Path(nfo).read_bytes()
    except OSError:
        raise FieldEditError('nfo_unreadable') from None
    root = load_tree(raw)
    result = apply_field(root, field, payload, EditContext(video.number or '', fmt))
    return raw, root, result


def apply_edit(repo, video, field, payload, config, path_mappings):
    if field not in FIELD_DB_FIELDS:
        return {'success': False, 'error': 'invalid_field'}
    nfo_fs, reason = locate_editable_nfo(repo, video, config, path_mappings)
    if reason:
        return {'success': False, 'error': reason}
    owning = resolve_owning_output_root(video.path, config)
    roots = _roots(video, config, path_mappings, owning)
    filename = _filename(video, path_mappings)
    fmt = config.get('scraper', {}).get('nfo_title_format', _DEFAULT_FORMAT)
    try:
        raw, root, result = _prepare_edit(nfo_fs, field, payload, video, fmt)
    except FieldEditError as exc:
        return {'success': False, 'error': exc.code}
    if result.changed:
        try:
            write_nfo_atomic(nfo_fs, dump_tree(root), roots)
        except FieldEditError as exc:
            return {'success': False, 'error': exc.code}
        except Exception:
            logger.exception('NFO write failed')
            return {'success': False, 'error': 'nfo_write_failed'}
    try:
        values = _read_back(nfo_fs, video, filename, path_mappings, fmt)
        _update_readback(repo, video, result, values, nfo_fs)
    except Exception:  # BE-TEST-33
        logger.exception('NFO readback or database update failed')
        if not result.changed:
            return {'success': False, 'error': 'db_write_failed'}
        _rollback_nfo(nfo_fs, raw, roots)
        return {'success': False, 'error': 'db_write_failed'}
    return _response(field, result, values, filename)
