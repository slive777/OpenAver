import os
import re

from core.query_intent import classify_query
from core.scrapers.utils import is_uncensored_route, normalize_number_impl, resolve_route_target

CLEAR_HIT_LEAD = 8

_SEG = r"[A-Za-z0-9._-]+"
_FRAME_RE = re.compile(rf"/thumb/{_SEG}/{_SEG}/{_SEG}\.webp")
_COVER_RE = re.compile(rf"/thumb/{_SEG}/covers/{_SEG}\.webp")
_COVER_NAME_RE = re.compile(r"^(.+)_cover_(full|left|right)$")
_TIME_RE = re.compile(r"^\d+-\d{2}-\d{2}$")


def map_code(code: str) -> tuple[str, bool]:
    number = normalize_number_impl(code)
    searchable = classify_query(number).mode == "exact" or is_uncensored_route(resolve_route_target(number))
    if searchable:
        return number, True
    return code, False


def is_clear_hit(sims: list[float]) -> tuple[bool, float | None]:
    if len(sims) < 2:
        return False, None
    lead = round(sims[0] - sims[1], 2)
    return lead >= CLEAR_HIT_LEAD, lead


def parse_frame_name(name: str) -> tuple[str, str | None, int | None, str | None]:
    stem, _ = os.path.splitext(name)
    m = _COVER_NAME_RE.fullmatch(stem)
    if m:
        return "cover", m.group(2), None, None
    if "_" not in stem:
        return "frame", None, None, None
    seg = stem.rsplit("_", 1)[1]
    if not _TIME_RE.fullmatch(seg):
        return "frame", None, None, None
    h, mi, s = seg.split("-")
    return "frame", None, int(h) * 3600 + int(mi) * 60 + int(s), seg.replace("-", ":")


def safe_thumb_path(path: object) -> bool:
    if not isinstance(path, str):
        return False
    if ".." in path:
        return False
    return bool(_FRAME_RE.fullmatch(path) or _COVER_RE.fullmatch(path))
