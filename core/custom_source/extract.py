"""自訂來源的欄位抽取：HTML＋欄位宣告 → 形狀固定的 dict。

來源有 css／meta／jsonld 三種；抽出後先跑作者的變換鏈，
再依欄位名套用型別層（日期、片長、網址、清單）。內容再亂也不拋例外。
"""
import datetime
import json
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from core.custom_source.transforms import apply_transforms, round_half_up
from core.custom_source.urls import public_url

LIST_FIELDS = frozenset({"tags", "actors", "sample_images"})
URL_FIELDS = frozenset({"cover", "sample_images"})

_DATE_SEP_RE = re.compile(r"(\d{4})([-/.])(\d{1,2})\2(\d{1,2})(?:T[0-9:.+\-Zz]*)?")
_DATE_CJK_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def parse_html(html):
    return BeautifulSoup(html, "lxml")


# ---------------------------------------------------------------- 來源

def _from_css(soup, field):
    try:
        elements = soup.select(field.selector)
    except Exception:
        return []
    if field.attr:
        return [_attr_text(el.get(field.attr)) for el in elements]
    values = [el.get_text(" ", strip=True) for el in elements]
    return values


def _attr_text(raw):
    if isinstance(raw, list):
        return " ".join(raw)
    return raw


def _from_meta(soup, field):
    key = field.selector
    found = []
    for tag in soup.find_all("meta"):
        if tag.get("property") == key or tag.get("name") == key:
            found.append(_attr_text(tag.get("content")))
    return found


def _jsonld_nodes(soup):
    nodes = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "")
        except (ValueError, TypeError, RecursionError):
            continue
        for item in data if isinstance(data, list) else [data]:
            if not isinstance(item, dict):
                continue
            nodes.append(item)
            graph = item.get("@graph")
            if isinstance(graph, list):
                nodes.extend(g for g in graph if isinstance(g, dict))
    return nodes


def _type_matches(node, wanted):
    node_type = node.get("@type")
    if isinstance(node_type, list):
        return wanted in node_type
    return node_type == wanted


def _json_values(raw):
    items = raw if isinstance(raw, list) else [raw]
    out = []
    for item in items:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, (int, float)) and not isinstance(item, bool):
            out.append(str(item))
    return out


def _from_jsonld(soup, field):
    wanted, _, key = field.selector.partition(".")
    for node in _jsonld_nodes(soup):
        if _type_matches(node, wanted) and key in node:
            return _json_values(node[key])
    return []


_SOURCES = {"css": _from_css, "meta": _from_meta, "jsonld": _from_jsonld}


# ---------------------------------------------------------------- 型別層

def _parse_date(text):
    match = _DATE_SEP_RE.fullmatch(text)
    if match:
        parts = (match.group(1), match.group(3), match.group(4))
    else:
        match = _DATE_CJK_RE.fullmatch(text)
        parts = match.groups() if match else None
    if parts is None:
        return None
    try:
        return datetime.date(*(int(p) for p in parts))
    except ValueError:
        return None


def _norm_date(text):
    parsed = _parse_date(text.strip())
    if parsed is None:
        return ""
    return parsed.isoformat()


def _norm_duration(text):
    match = _NUMBER_RE.search(text)
    if not match:
        return None
    try:
        minutes = round_half_up(float(match.group(0)))
    except (ValueError, OverflowError):
        return None
    return minutes if minutes > 0 else None


def _norm_url(value, base_url):
    if not value.strip():
        return None
    try:
        joined = urljoin(base_url, value.strip())
        parsed = urlparse(joined)
    except ValueError:
        return None
    if urlparse(joined).scheme not in ("http", "https"):
        return None
    if not parsed.netloc:
        return None
    # 圖片網址是欄位值（不會拿去抓頁面），帳密只用於抓頁，不可外流
    return public_url(joined) or None


def _clean_list(values):
    cleaned = [v.strip() for v in values if v.strip()]
    return list(dict.fromkeys(cleaned))


# ---------------------------------------------------------------- 組裝

def _raw_values(soup, field, base_url):
    values = _SOURCES[field.kind](soup, field)
    values = [v for v in values if v is not None]
    return apply_transforms(values, field.then, base_url)


def _first_nonblank(values):
    return [v for v in values if v.strip()][:1]


def _list_field(field, values, base_url):
    picked = values if field.all else _first_nonblank(values)
    if field.name in URL_FIELDS:
        urls = [_norm_url(v, base_url) for v in picked]
        picked = [u for u in urls if u is not None]
    return _clean_list(picked)


def _scalar_field(field, values, base_url):
    first = _first_nonblank(values)
    text = first[0].strip() if first else ""
    if field.name == "date":
        return _norm_date(text)
    if field.name == "duration":
        return _norm_duration(text)
    if field.name in URL_FIELDS:
        return _norm_url(text, base_url) or ""
    return text


def extract_fields(page, final_url, fields):
    soup = parse_html(page) if isinstance(page, str) else page
    result = {}
    for field in fields:
        values = _raw_values(soup, field, final_url)
        if field.name in LIST_FIELDS:
            result[field.name] = _list_field(field, values, final_url)
        else:
            result[field.name] = _scalar_field(field, values, final_url)
    return result
