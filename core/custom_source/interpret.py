"""自訂來源解譯器：照 Spec 找一個番號並跑 YAML 驗收案例；節流與逐跳守衛都在 fetch_page。"""
import re
from dataclasses import dataclass
from urllib.parse import quote, urljoin, urlparse

from core.custom_source.extract import extract_fields, parse_html
from core.custom_source.fetch import FetchError, fetch_page, make_transport
from core.logger import get_logger
from core.scrapers.utils import normalize_number_impl

MAX_DETAIL_FETCH = 5

log = get_logger(__name__)

_OUTAGE_REASONS = frozenset({"network", "timeout"})
_PLACEHOLDER_RE = re.compile(r"\{(number|number_lower|number_digits|suffix)\}")
_KEY_RE = re.compile(r"(.*?)(_contains|_include|_exclude|_max)?")


@dataclass(frozen=True)
class ScrapedItem:
    detail_url: str
    fields: dict


@dataclass(frozen=True)
class ScrapeResult:
    status: str
    items: tuple = ()
    reason: object = None
    http_status: object = None


@dataclass(frozen=True)
class Mismatch:
    key: str
    expected: object
    actual: object
    url: str


@dataclass(frozen=True)
class CaseResult:
    index: int
    number: str
    passed: bool
    mismatches: tuple


def _values(canon):
    tail = re.search(r"\d+$", canon)
    return {"number": canon, "number_lower": canon.lower(), "number_digits": tail.group(0) if tail else ""}


def _render(template, values, encode=True):
    shown = {k: quote(v, safe="") for k, v in values.items()} if encode else values
    return _PLACEHOLDER_RE.sub(lambda match: shown.get(match.group(1), ""), template)


def _fetch_ok(url, transport, config):
    page = fetch_page(url, transport, config)
    if page.status == 404:
        return None
    return page


def _body_hit(step, text):
    return step.not_found_body is not None and step.not_found_body in text


def _fetch_unique(urls, transport, config, errors, nf_step=None):
    pages, seen = [], set()
    for order, requested in enumerate(urls):
        try:
            page = _fetch_ok(requested, transport, config)
        except FetchError as exc:
            log.info("custom source page failed: %s %s", exc, requested)
            errors.append((order, exc))
            if exc.reason in _OUTAGE_REASONS:
                break
            continue
        if page is None:
            continue
        if page.final_url in seen:
            continue
        seen.add(page.final_url)
        if nf_step is not None and _body_hit(nf_step, page.text):
            continue
        pages.append((order, page))
    return pages


def _link_matches(keep, href, text):
    rx = re.compile((r"(?<!\d)" if keep[:1].isdigit() else r"(?<![a-z])") + re.escape(keep) + r"(?!\d)")
    return rx.search(href.lower()) is not None or rx.search(text.lower()) is not None


def _search_hits(page, step, values):
    keep = _render(step.results.keep_if_contains, values, encode=False).lower()
    hits = []
    for link in parse_html(page.text).select(step.results.css):
        href = (link.get("href") or "").strip()
        try:
            url = urljoin(page.final_url, href) if href else ""
            web = urlparse(url).scheme in ("http", "https")
        except ValueError:
            continue
        if web and url not in hits and _link_matches(keep, href, link.get_text(" ", strip=True)):
            hits.append(url)
    return hits


def _cap(hits):
    kept = hits[:MAX_DETAIL_FETCH]
    if len(kept) < len(hits):
        log.info("custom source: dropped %d extra hits", len(hits) - len(kept))
    return kept


def _same_number(fields, canon):
    if "number" not in fields:
        return True
    if not fields["number"].strip():
        raise FetchError("parse_empty")
    return normalize_number_impl(fields["number"]) == canon


def _make_item(spec, page, canon):
    fields = extract_fields(page.text, page.final_url, spec.fields)
    if not fields.get("title") and not fields.get("cover"):
        raise FetchError("parse_empty")
    return ScrapedItem(page.final_url, dict(fields, number=canon)) if _same_number(fields, canon) else None


def _make_items(spec, pages, canon, errors):
    items = []
    for order, page in pages:
        try:
            item = _make_item(spec, page, canon)
        except FetchError as exc:
            log.info("custom source page failed: %s %s", exc, page.final_url)
            errors.append((order, exc))
            continue
        if item is not None:
            items.append(item)
    return items


def _date_key(item):
    return item.fields.get("date") or ""


def _sort_items(items):
    return sorted(items, key=_date_key, reverse=True)


def _finish(spec, pages, canon, errors):
    items = _make_items(spec, pages, canon, errors)
    if errors and not items:
        first = min(errors, key=lambda entry: entry[0])[1]
        return ScrapeResult("error", reason=first.reason, http_status=first.http_status)
    if not items:
        return ScrapeResult("not_found")
    if len(items) == 1:
        return ScrapeResult("ok", items=tuple(items))
    return ScrapeResult("multiple", items=tuple(_sort_items(items)))


def _single_stage(spec, canon, transport, config):
    step, errors = spec.steps[0], []
    urls = [_render(step.url, dict(_values(canon), suffix=s)) for s in step.candidates]
    pages = _fetch_unique(urls, transport, config, errors, nf_step=step)
    return _finish(spec, pages, canon, errors)


def _two_stage(spec, canon, transport, config):
    step = spec.steps[0]
    values = _values(canon)
    search = fetch_page(_render(step.url, values), transport, config)
    if search.status != 200:
        raise FetchError("http_status", search.status)
    if _body_hit(step, search.text):
        return ScrapeResult("not_found")
    errors = []
    pages = _fetch_unique(_cap(_search_hits(search, step, values)), transport, config, errors)
    return _finish(spec, pages, canon, errors)


def _guarded(spec, number, config, transport, work):
    canon = normalize_number_impl(number)
    if re.fullmatch(spec.number_pattern, canon) is None:
        return ScrapeResult("skipped")
    try:
        return work(canon, transport or make_transport(spec.fetch, f"custom:{spec.id}", config))
    except FetchError as exc:
        return ScrapeResult("error", reason=exc.reason, http_status=exc.http_status)
    except Exception:
        log.exception("custom source %s: unexpected failure", spec.id)
        return ScrapeResult("error", reason="unexpected")


def scrape(spec, number, config, transport=None):
    stage = _two_stage if len(spec.steps) == 2 else _single_stage
    return _guarded(spec, number, config, transport, lambda canon, tr: stage(spec, canon, tr, config))


def _detail_page(spec, canon, transport, config, url):
    errors = []
    return _finish(spec, _fetch_unique([url], transport, config, errors), canon, errors)


def scrape_detail(spec, detail_url, number, config, transport=None):
    return _guarded(spec, number, config, transport, lambda canon, tr: _detail_page(spec, canon, tr, config, detail_url))


def _as_list(value):
    return list(value) if isinstance(value, (list, tuple)) else value


_CHECKS = {
    "": lambda actual, want: _as_list(actual) == want,
    "_contains": lambda actual, want: isinstance(actual, str) and want in actual,
    "_include": lambda actual, want: isinstance(actual, list) and set(want) <= set(actual),
    "_exclude": lambda actual, want: isinstance(actual, list) and not set(want) & set(actual),
    "_max": lambda actual, want: actual <= want,
}


def _check_expect(key, expected, fields):
    name, suffix = _KEY_RE.fullmatch(key).groups()
    suffix = suffix or ""
    actual = fields.get(name)
    want = _as_list(expected)
    if suffix == "_max":
        actual = len(actual) if isinstance(actual, list) else None
    ok = actual is not None and _CHECKS[suffix](actual, want)
    return None if ok else (want, actual)


def _check_case(case, result):
    got = f"error:{result.reason}" if result.status == "error" else result.status
    if got != case.status:
        return [Mismatch("status", case.status, got, "")]
    if case.status == "not_found":
        return []
    checked = [(item, key, _check_expect(key, want, item.fields)) for item in result.items for key, want in case.expect]
    return [Mismatch(key, bad[0], bad[1], item.detail_url) for item, key, bad in checked if bad is not None]


def run_tests(spec, config, transport=None):
    runs = [(i, c, _check_case(c, scrape(spec, c.number, config, transport))) for i, c in enumerate(spec.tests, 1)]
    return tuple(CaseResult(i, c.number, not found, tuple(found)) for i, c, found in runs)


def format_results(results):
    lines = []
    for res in results:
        lines.append(f"{'PASS' if res.passed else 'FAIL'} case {res.index} {res.number}")
        lines += [f"  {m.key}: expected {m.expected!r}, actual {m.actual!r}" for m in res.mismatches]
    return "\n".join(lines)
