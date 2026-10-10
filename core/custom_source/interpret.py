"""自訂來源解譯器：照 Spec 找一個番號並跑 YAML 驗收案例；節流與逐跳守衛都在 fetch_page。"""
import re
from dataclasses import dataclass
from urllib.parse import quote, urldefrag, urljoin, urlparse, urlsplit

from core.custom_source import fetch as fetch_mod
from core.custom_source.extract import extract_fields, parse_html
from core.custom_source.fetch import DeadlineTransport, FetchError, fetch_page, make_transport
from core.custom_source.schema import detail_host_allowed
from core.custom_source.urls import public_url
from core.logger import get_logger
from core.scrapers.utils import normalize_number_impl

MAX_DETAIL_FETCH = 5
log = get_logger(__name__)
_PLACEHOLDER_RE = re.compile(r"\{(number|number_lower|number_digits|suffix)\}")
_KEY_RE = re.compile(r"(.*?)(_contains|_include|_exclude|_max|)")


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
    if not all(values[k] for k in _PLACEHOLDER_RE.findall(template) if k != "suffix"):
        return ""
    shown = {k: quote(v, safe="") for k, v in values.items()} if encode else values
    return _PLACEHOLDER_RE.sub(lambda match: shown.get(match.group(1), ""), template)


def _log_url(url):
    try:
        parts = urlsplit(url)
    except ValueError:
        return "<invalid url>"
    return f"{parts.scheme}://{parts.netloc.rpartition('@')[2]}{parts.path}"


def _fetch_ok(url, transport, config):
    page = fetch_page(url, transport, config)
    if page.status == 404:
        return None
    return page


def _body_hit(step, text):
    return step.not_found_body is not None and step.not_found_body in text


def _fetch_unique(urls, transport, config, errors, nf_step=None, stop_on_outage=False):
    pages, seen = [], set()
    for order, requested in enumerate(urls):
        try:
            page = _fetch_ok(requested, transport, config)
        except FetchError as exc:
            log.info("custom source page failed: %s %s", exc, _log_url(requested))
            errors.append((order, exc))
            if stop_on_outage and exc.reason in ("network", "timeout"):
                break
            continue
        if page is None:
            continue
        if urldefrag(page.final_url)[0] in seen:
            continue
        seen.add(urldefrag(page.final_url)[0])
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
    for link in (parse_html(page.text).select(step.results.css) if keep else ()):
        href = (link.get("href") or "").strip()
        try:
            url = urldefrag(urljoin(page.final_url, href))[0] if href else ""
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
            log.info("custom source page failed: %s %s", exc, _log_url(page.final_url))
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
    return ScrapeResult("ok" if len(items) == 1 else "multiple", items=tuple(_sort_items(items)))


def _single_stage(spec, canon, transport, config):
    step, errors = spec.steps[0], []
    urls = [u for u in (_render(step.url, dict(_values(canon), suffix=s)) for s in step.candidates) if u]
    pages = _fetch_unique(urls, transport, config, errors, nf_step=step, stop_on_outage=True)
    return _finish(spec, pages, canon, errors)


def _two_stage(spec, canon, transport, config):
    step = spec.steps[0]
    values = _values(canon)
    if not (url := _render(step.url, values)):
        return ScrapeResult("not_found")
    search = fetch_page(url, transport, config)
    if search.status != 200:
        raise FetchError("http_status", search.status)
    if _body_hit(step, search.text):
        return ScrapeResult("not_found")
    errors = []
    pages = _fetch_unique(_cap(_search_hits(search, step, values)), transport, config, errors)
    return _finish(spec, pages, canon, errors)


def accepts_number(spec, number):
    """番號正規化後符合 spec.number_pattern 才會被這個來源處理。"""
    return re.fullmatch(spec.number_pattern, normalize_number_impl(number)) is not None


def _guarded(spec, number, config, transport, work, budget_s=None):
    if not accepts_number(spec, number):
        return ScrapeResult("skipped")
    canon = normalize_number_impl(number)
    try:
        tr = transport or make_transport(spec.fetch, f"custom:{spec.id}", config)
        return work(canon, tr if budget_s is None else DeadlineTransport(tr, budget_s))
    except FetchError as exc:
        return ScrapeResult("error", reason=exc.reason, http_status=exc.http_status)
    except Exception:
        log.exception("custom source %s: unexpected failure", spec.id)
        return ScrapeResult("error", reason="unexpected")


def scrape(spec, number, config, transport=None, budget_s=None):
    stage = _two_stage if len(spec.steps) == 2 else _single_stage
    return _guarded(spec, number, config, transport, lambda canon, tr: stage(spec, canon, tr, config), budget_s)


def scrape_detail(spec, detail_url, number, config, transport=None, budget_s=None):
    nf_step = spec.steps[0] if len(spec.steps) == 1 else None

    def work(canon, tr):
        errors = []
        pages = _fetch_unique([detail_url], tr, config, errors, nf_step=nf_step)
        return _finish(spec, pages, canon, errors)

    return _guarded(spec, number, config, transport, work, budget_s)


def _as_list(value):
    return list(value) if isinstance(value, (list, tuple)) else value


_CHECKS = {
    "": lambda actual, want: _as_list(actual) == want,
    "_contains": lambda actual, want: isinstance(actual, str) and want in actual,
    "_include": lambda actual, want: isinstance(actual, list) and set(want) <= set(actual),
    "_exclude": lambda actual, want: isinstance(actual, list) and not set(want) & set(actual),
    "_max": lambda actual, want: actual <= want,
}


def _public_value(value):
    """mismatch 的 expected/actual：http(s) 字串去帳密（防其他欄位外流）。"""
    if isinstance(value, (list, tuple)):
        return [_public_value(v) for v in value]
    if isinstance(value, str) and value.lower().startswith(("http://", "https://")) and "@" in value:
        return public_url(value) or value
    return value


def _check_expect(key, expected, fields):
    name, suffix = _KEY_RE.fullmatch(key).groups()
    actual = fields.get(name)
    want = _as_list(expected)
    if suffix == "_max":
        actual = len(actual) if isinstance(actual, list) else None
    ok = actual is not None and _CHECKS[suffix](actual, want)
    return None if ok else (_public_value(want), _public_value(actual))


def _host_of(url):
    try:
        return urlsplit(url).hostname or ""
    except ValueError:
        return ""


def _host_mismatches(spec, items):
    return [Mismatch("detail_host", "同站 host", _host_of(i.detail_url), public_url(i.detail_url)) for i in items if not detail_host_allowed(spec, i.detail_url)]


def _expect_mismatches(checked):
    return [Mismatch(key, bad[0], bad[1], public_url(item.detail_url)) for item, key, bad in checked if bad is not None]


def _check_case(spec, case, result):
    got = f"error:{result.reason}" if result.status == "error" else result.status
    if got != case.status:
        return [Mismatch("status", case.status, got, "")]
    if case.status == "not_found":
        return []
    checked = [(item, key, _check_expect(key, want, item.fields)) for item in result.items for key, want in case.expect]
    return _expect_mismatches(checked) + _host_mismatches(spec, result.items)


def _run_case(spec, index, case, config, transport, budget_s, total_deadline):
    if total_deadline is not None and fetch_mod._now() >= total_deadline:
        found = [Mismatch("status", case.status, "error:timeout", "")]
    else:
        if total_deadline is not None:
            remaining = total_deadline - fetch_mod._now()
            budget_s = remaining if budget_s is None else min(budget_s, remaining)
        found = _check_case(spec, case, scrape(spec, case.number, config, transport, budget_s=budget_s))
    return CaseResult(index, case.number, not found, tuple(found))


def run_tests(spec, config, transport=None, budget_s=None, total_budget_s=None):
    total_deadline = None if total_budget_s is None else fetch_mod._now() + total_budget_s
    return tuple(_run_case(spec, i, c, config, transport, budget_s, total_deadline) for i, c in enumerate(spec.tests, 1))


def format_results(results):
    lines = (f"{'PASS' if r.passed else 'FAIL'} case {r.index} {r.number}" for r in results)
    return "\n".join(line + "".join(f"\n  {m.key}: expected {m.expected!r}, actual {m.actual!r}" for m in r.mismatches)
                     for line, r in zip(lines, results, strict=True))
