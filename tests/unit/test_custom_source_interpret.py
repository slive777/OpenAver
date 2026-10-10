"""自訂來源解譯器：scrape／scrape_detail／run_tests 的行為（全離線，FakeTransport）。"""

import dataclasses
import itertools
from unittest.mock import Mock

import pytest

from core.custom_source import schema
import core.custom_source.interpret as interpret
from core.custom_source.extract import parse_html
from core.custom_source.fetch import FetchError
from core.custom_source.interpret import accepts_number, format_results, run_tests, scrape, scrape_detail
from core.proxy_policy import ProxySettings
from core.scrapers.models import ScraperConfig
from tests.unit._custom_source_fake import FakeTransport, page, redirect
from tests.unit._custom_source_pages import FIXTURE_DIR, PAGES


@pytest.fixture(autouse=True)
def _no_real_dns_or_sleep(monkeypatch):
    monkeypatch.setattr("core.custom_source.guard.resolve_host", lambda host: ["8.8.8.8"])
    monkeypatch.setattr("core.custom_source.fetch.rate_limit", lambda delay=0: None)


def _txt(name):
    return PAGES[name]


def _pg(name):
    return page(_txt(name))


def _spec(name):
    return schema.load_file(FIXTURE_DIR / f"{name}.yaml")


def _hrefs(name, css):
    return [a["href"] for a in parse_html(_txt(name)).select(css)]


def _step0(name, **changes):
    spec = _spec(name)
    return dataclasses.replace(spec, steps=(dataclasses.replace(spec.steps[0], **changes), *spec.steps[1:]))


def _cands(*suffixes):
    return _step0("candidates", candidates=suffixes)


def _run(spec, number, routes):
    transport = FakeTransport(routes)
    return scrape(spec, number, CFG, transport), transport


CFG = ScraperConfig(proxy_settings=ProxySettings())
CAND = "https://candidates.example/video/chinese-subtitles/sone-205"
SOG = "https://single-og.example/sone-205"
TWO = "https://two-step.example/search/"
TEXT = "https://text.example/search/?q=FC2PPV"


def _routes_for(name):
    if name == "single-og":
        return {SOG: _pg("single-og"), "https://single-og.example/zzzz-999": page("", 404)}
    if name == "single-og-min":
        return {"https://single-og-min.example/videos/sone-205/": _pg("single-og-min"),
                "https://single-og-min.example/videos/zzzz-999/": page("", 404)}
    if name == "text":
        hit = _hrefs("text-search", ".card-video__title a")[0]
        return {TEXT + "2439990": _pg("text-search"), hit: _pg("text-detail"),
                TEXT + "9999999": _pg("text-search-empty")}
    if name == "two-step":
        uc, c = _hrefs("two-step-search", "h3.entry-title a")
        return {TWO + "SONE-205": _pg("two-step-search"), uc: _pg("two-step-detail-a"),
                c: _pg("two-step-detail-b"), TWO + "ZZZZ-999": _pg("two-step-empty")}
    if name == "fuzzy":
        hit = _hrefs("fuzzy-search", "h3.jeg_post_title a")[0]
        return {"https://fuzzy.example/?s=IPZZ-100": _pg("fuzzy-search"), hit: _pg("fuzzy-detail"),
                "https://fuzzy.example/?s=ZZZZ-999": _pg("fuzzy-search")}
    miss = CAND.replace("sone-205", "zzzz-999")
    return {CAND + "c/": _pg("two-step-detail-a"), CAND + "uc/": _pg("two-step-detail-b"),
            CAND + "/": redirect(CAND + "c/"),
            miss + "c/": page("", 404), miss + "uc/": page("", 404), miss + "/": page("", 404)}


@pytest.mark.parametrize("name, number", [("text", "SONE-205"), ("single-og", "12345"), ("fuzzy", "FC2-2439990")])
def test_pattern_mismatch_skipped_without_requests(name, number):
    result, transport = _run(_spec(name), number, {})
    assert (result.status, transport.calls) == ("skipped", [])


@pytest.mark.parametrize("name, number, first_call", [
    ("single-og", "sone205", SOG),
    ("single-og", "SONE-205", SOG),
    ("fuzzy", "ipzz100", "https://fuzzy.example/?s=IPZZ-100"),
    ("text", "fc2ppv2439990", TEXT + "2439990"),
    ("candidates", "sone-205", CAND + "c/"),
])
def test_template_placeholders_render_request_url(name, number, first_call):
    result, transport = _run(_spec(name), number, _routes_for(name) | _routes_for("fuzzy"))
    assert transport.calls[0] == first_call


@pytest.mark.parametrize("limit, expected_calls", [(5, 6), (2, 3), (1, 2)])
def test_results_capped_at_max_detail_fetch(monkeypatch, limit, expected_calls):
    monkeypatch.setattr(interpret, "MAX_DETAIL_FETCH", limit)
    urls = [f"https://two-step.example/v/sone-205-{i}/" for i in range(20)]
    html = "".join(f'<h3 class="entry-title"><a href="{u}">SONE-205 v{i}</a></h3>' for i, u in enumerate(urls))
    routes = {TWO + "SONE-205": page(html)} | {u: _pg("two-step-detail-a") for u in urls}
    result, transport = _run(_spec("two-step"), "SONE-205", routes)
    assert (len(transport.calls), len(result.items)) == (expected_calls, expected_calls - 1)


def test_result_links_filtered_by_href_or_text():
    html = (
        '<h3 class="entry-title"><a href="/v/sone-205-x/">no text hit</a></h3>'
        '<h3 class="entry-title"><a href="/v/12345">SONE-205 text hit</a></h3>'
        '<h3 class="entry-title"><a href="/v/999">unrelated</a></h3>'
        '<h3 class="entry-title"><a href="javascript:void(0)">SONE-205 script</a></h3>'
        '<h3 class="entry-title"><a href="https://[">SONE-205 malformed</a></h3>'
    )
    routes = {TWO + "SONE-205": page(html),
              "https://two-step.example/v/sone-205-x/": _pg("two-step-detail-a"),
              "https://two-step.example/v/12345": _pg("two-step-detail-b")}
    result, transport = _run(_spec("two-step"), "SONE-205", routes)
    assert transport.calls[1:] == ["https://two-step.example/v/sone-205-x/", "https://two-step.example/v/12345"]


@pytest.mark.parametrize("hrefs, status, count", [
    (["/x"] * 6, "ok", 1),
    (["/x#a", "/x#b"], "ok", 1),
    ([f"/x#{c}" for c in "abcde"] + ["/y"], "multiple", 2),
])
def test_duplicate_and_fragment_links_collapse_to_one_request(hrefs, status, count):
    html = "".join(f'<h3 class="entry-title"><a href="{h}">SONE-205</a></h3>' for h in hrefs)
    base = "https://two-step.example"
    routes = {TWO + "SONE-205": page(html), base + "/x": _pg("two-step-detail-a"), base + "/y": _pg("two-step-detail-b")}
    result, transport = _run(_spec("two-step"), "SONE-205", routes)
    assert (result.status, len(result.items), len(transport.calls)) == (status, count, count + 1)
    assert not any("#" in u for u in transport.calls)


@pytest.mark.parametrize("number, hit, status, calls", [
    ("SONE-205C", "", "not_found", 1),
    ("HEYZO-1234", '<div class="card-video__title"><a href="/v/1234">x</a></div>', "ok", 2),
])
def test_empty_filter_string_matches_nothing(number, hit, status, calls):
    html = "".join(f'<div class="card-video__title"><a href="/v/n{i}">Title {i}</a></div>' for i in range(5)) + hit
    spec = dataclasses.replace(_step0("text", url="https://text.example/search/?q={number}"), number_pattern="[A-Z0-9-]+")
    routes = {"https://text.example/search/?q=" + number: page(html), "https://text.example/v/1234": _pg("text-detail")}
    result, transport = _run(spec, number, routes)
    assert (result.status, len(transport.calls)) == (status, calls)


@pytest.mark.parametrize("name, number, requested", [
    ("candidates", "ABC-123-C", False), ("candidates", "ABC-123", True),
    ("text", "ABC-123-C", False), ("text", "ABC-123", True),
])
def test_empty_url_placeholder_skips_request(name, number, requested):
    spec = dataclasses.replace(_step0(name, url="https://a.example/v/{number_digits}"), number_pattern="[A-Z0-9-]+")
    result, transport = _run(spec, number, {"https://a.example/v/123": page("", 404)})
    assert bool(transport.calls) is requested
    assert requested or result.status == "not_found"


def test_candidates_deduped_by_final_url():
    result, transport = _run(_spec("candidates"), "SONE-205", _routes_for("candidates"))
    assert transport.calls == [CAND + "c/", CAND + "uc/", CAND + "/", CAND + "c/"]
    assert (result.status, [i.detail_url for i in result.items]) == ("multiple", [CAND + "c/", CAND + "uc/"])


def test_number_mismatch_candidate_dropped():
    spec = _spec("candidates")
    other = page(_txt("two-step-detail-a").replace("SONE-205", "SONE-999"))
    routes = {CAND.replace("205", "206") + s: _pg("two-step-detail-a") for s in ("c/", "uc/", "/")}
    result, _ = _run(spec, "SONE-206", routes)
    assert result.status == "not_found"
    result, _ = _run(spec, "SONE-205", {CAND + "c/": _pg("two-step-detail-a"), CAND + "uc/": other, CAND + "/": page("", 404)})
    assert (result.status, [i.detail_url for i in result.items], result.items[0].fields["number"]) == ("ok", [CAND + "c/"], "SONE-205")


def test_declared_number_empty_is_parse_empty_but_other_number_is_not_found():
    spec = _cands("c")
    broken = dataclasses.replace(spec, fields=tuple(
        dataclasses.replace(f, selector="h6.none") if f.name == "number" else f for f in spec.fields))
    result, _ = _run(broken, "SONE-205", {CAND + "c/": _pg("two-step-detail-a")})
    assert (result.status, result.reason) == ("error", "parse_empty")
    result, _ = _run(spec, "SONE-205", {CAND + "c/": page(_txt("two-step-detail-a").replace("SONE-205", "SONE-999"))})
    assert result.status == "not_found"


@pytest.mark.parametrize("uc_page, c_page, order, dates", [
    (_pg("two-step-detail-a"), _pg("two-step-detail-b"), ["c", "uc"], ["2025-12-17", "2024-06-01"]),
    (page(_txt("two-step-detail-b").replace("uploadDate", "uploadDateX")), _pg("two-step-detail-a"), ["c", "uc"], ["2024-06-01", ""]),
    (_pg("two-step-detail-a"), _pg("two-step-detail-a"), ["uc", "c"], ["2024-06-01", "2024-06-01"]),
])
def test_multiple_sorted_by_date_desc(uc_page, c_page, order, dates):
    uc, c = _hrefs("two-step-search", "h3.entry-title a")
    result, _ = _run(_spec("two-step"), "SONE-205", {TWO + "SONE-205": _pg("two-step-search"), uc: uc_page, c: c_page})
    assert result.status == "multiple" and [i.detail_url for i in result.items] == [{"uc": uc, "c": c}[o] for o in order]
    assert [i.fields["date"] for i in result.items] == dates


def test_single_stage_404_is_not_found():
    result, transport = _run(_spec("single-og"), "ZZZZ-999", _routes_for("single-og"))
    assert (result.status, transport.calls) == ("not_found", ["https://single-og.example/zzzz-999"])


def test_results_filter_empty_is_not_found():
    result, transport = _run(_spec("text"), "FC2-9999999", _routes_for("text"))
    assert (result.status, transport.calls) == ("not_found", [TEXT + "9999999"])


def test_body_contains_hit_is_not_found():
    result, transport = _run(_step0("two-step", not_found_body="sone-205c"), "SONE-205", _routes_for("two-step"))
    assert (result.status, transport.calls) == ("not_found", [TWO + "SONE-205"])
    result, _ = _run(_step0("single-og", not_found_body="<h1"), "SONE-205", _routes_for("single-og"))
    assert result.status == "not_found"


_HOPS = [SOG] + [f"https://single-og.example/h{i}" for i in range(1, 7)]
@pytest.mark.parametrize("routes, reason, status", [
    pytest.param({SOG: page("", 503)}, "http_status", 503, id="http503"),
    pytest.param({SOG: page("", 500)}, "http_status", 500, id="http500"),
    pytest.param({SOG: redirect("http://10.0.0.5/")}, "blocked_target", None, id="blocked"),
    pytest.param({SOG: FetchError("network")}, "network", None, id="network"),
    pytest.param({SOG: FetchError("timeout")}, "timeout", None, id="timeout"),
    pytest.param({SOG: FetchError("too_large")}, "too_large", None, id="too_large"),
    pytest.param({_HOPS[i]: redirect(_HOPS[i + 1]) for i in range(6)}, "redirect_limit", None, id="loop"),
    pytest.param({SOG: page("")}, "parse_empty", None, id="empty_body"),
])
def test_error_reasons(routes, reason, status):
    result, _ = _run(_spec("single-og"), "SONE-205", routes)
    assert (result.status, result.reason, result.http_status) == ("error", reason, status)


def test_search_page_404_is_error_not_not_found():
    result, _ = _run(_spec("two-step"), "SONE-205", {TWO + "SONE-205": page("", 404)})
    assert (result.status, result.reason, result.http_status) == ("error", "http_status", 404)


def test_transport_unavailable_and_unexpected_never_raise(monkeypatch):
    monkeypatch.setattr(interpret, "make_transport", Mock(side_effect=FetchError("transport_unavailable")))
    result = scrape(_spec("single-og"), "SONE-205", CFG)
    assert (result.status, result.reason) == ("error", "transport_unavailable")
    monkeypatch.setattr(interpret, "extract_fields", Mock(side_effect=ValueError("boom")))
    result, _ = _run(_spec("single-og"), "SONE-205", _routes_for("single-og"))
    assert (result.status, result.reason) == ("error", "unexpected")


@pytest.mark.parametrize("c_route, uc_route, status, reason, count", [
    (_pg("two-step-detail-a"), page("", 500), "ok", None, 1),
    (page("", 500), _pg("two-step-detail-a"), "ok", None, 1),
    (_pg("two-step-detail-a"), redirect("https://["), "ok", None, 1),
    (page(""), _pg("two-step-detail-a"), "ok", None, 1),
    (page("", 500), page("", 500), "error", "http_status", 0),
    (page("", 404), page("", 500), "error", "http_status", 0),
    (page("", 404), page("", 404), "not_found", None, 0),
])
def test_partial_failure_returns_successes(c_route, uc_route, status, reason, count):
    result, _ = _run(_cands("c", "uc"), "SONE-205", {CAND + "c/": c_route, CAND + "uc/": uc_route})
    assert (result.status, result.reason, len(result.items)) == (status, reason, count)


def _boundary_hit(keep, prefix, suffix):
    blocked = "abcdefghijklmnopqrstuvwxyz" if keep[0].isalpha() else "0123456789"
    return not (prefix and prefix[-1] in blocked) and not (suffix and suffix[0] in "0123456789")


@pytest.mark.parametrize("keep, prefix, suffix", itertools.product(
    ("sone-205", "2439990"), ("", " ", "/", "-", "中文字幕", "x", "1"), ("", "c", "uc", " ", "/", "0")))
def test_link_match_respects_number_boundaries(keep, prefix, suffix):
    hit = _boundary_hit(keep, prefix, suffix)
    assert interpret._link_matches(keep, prefix + keep + suffix, "") is hit
    assert interpret._link_matches(keep, "/v/123", (prefix + keep + suffix).upper()) is hit


@pytest.mark.parametrize("routes, calls, status, reason, count", [
    ({"a": FetchError("timeout")}, 1, "error", "timeout", 0),
    ({"a": _pg("two-step-detail-a"), "b": FetchError("network")}, 2, "ok", None, 1),
    ({"a": page("", 500), "b": _pg("two-step-detail-a"), "c": page("", 404)}, 3, "ok", None, 1),
])
def test_outage_stops_remaining_candidates(routes, calls, status, reason, count):
    result, transport = _run(_cands("a", "b", "c"), "SONE-205", {f"{CAND}{k}/": v for k, v in routes.items()})
    assert (len(transport.calls), result.status, result.reason, len(result.items)) == (calls, status, reason, count)


@pytest.mark.parametrize("url, routes, secrets", [
    ("https://a.example/v/x?apikey=SECRET1#frag", {"https://a.example/v/x?apikey=SECRET1#frag": page("", 500)}, ("SECRET1", "apikey", "frag")),
    ("https://a.example/v/y", {"https://a.example/v/y": redirect("https://a.example/z?token=SECRET2"),
                              "https://a.example/z?token=SECRET2": page("")}, ("SECRET2", "token")),
])
def test_failure_log_drops_query_and_fragment(caplog, url, routes, secrets):
    caplog.set_level("INFO")
    result, _ = _run(_step0("single-og", url=url), "SONE-205", routes)
    assert result.status == "error" and "a.example/" in caplog.text
    assert not any(word in caplog.text for word in secrets)


def test_first_failure_in_candidate_order_wins():
    spec = _cands("c", "uc")
    result, _ = _run(spec, "SONE-205", {CAND + "c/": page("<html></html>"), CAND + "uc/": page("", 503)})
    assert (result.status, result.reason, result.http_status) == ("error", "parse_empty", None)


@pytest.mark.parametrize("failure", [page("", 500), FetchError("timeout"), FetchError("network")])
def test_two_stage_detail_failure_keeps_other_hit(failure):
    uc, c = _hrefs("two-step-search", "h3.entry-title a")
    routes = {TWO + "SONE-205": _pg("two-step-search"), uc: failure, c: _pg("two-step-detail-b")}
    result, transport = _run(_spec("two-step"), "SONE-205", routes)
    assert (result.status, len(transport.calls), [i.detail_url for i in result.items]) == ("ok", 3, [c])


def test_single_stage_request_budget_is_bounded():
    routes = {}
    for s in "abcdefgh":
        chain = [f"{CAND}{s}/"] + [f"{CAND}{s}/h{n}" for n in range(1, 6)]
        routes.update({chain[n]: redirect(chain[n + 1]) for n in range(5)})
        routes[chain[5]] = _pg("two-step-detail-a")
    result, transport = _run(_cands(*"abcdefgh"), "SONE-205", routes)
    assert (len(transport.calls), result.status) == (48, "multiple")


@pytest.mark.parametrize("spec_name, number, route, status, calls", [
    ("single-og", "SONE-205", _pg("single-og"), "ok", 1),
    ("single-og", "SONE-205", page("", 404), "not_found", 1),
    ("single-og", "SONE-206", _pg("single-og"), "not_found", 1),
    ("text", "SONE-205", _pg("single-og"), "skipped", 0),
])
def test_scrape_detail(spec_name, number, route, status, calls):
    transport = FakeTransport({SOG: route})
    result = scrape_detail(_spec(spec_name), SOG, number, CFG, transport)
    assert (result.status, len(transport.calls)) == (status, calls)


@pytest.mark.parametrize("name", ["single-og", "single-og-min", "two-step", "fuzzy", "text", "candidates"])
def test_fixture_tests_all_pass(name):
    results = run_tests(_spec(name), CFG, FakeTransport(_routes_for(name)))
    assert results and all(r.passed for r in results), format_results(results)


def _with_cases(*cases):
    spec = _spec("single-og")
    return dataclasses.replace(spec, tests=tuple(schema.Case("SONE-205", "ok", c) for c in cases))


@pytest.mark.parametrize("expect, key, expected, actual_of", [
    ((("title", "WRONG"),), "title", "WRONG", lambda f: f["title"]),
    ((("title_contains", "no-such-text"),), "title_contains", "no-such-text", lambda f: f["title"]),
    ((("tags_include", ("no-such-tag",)),), "tags_include", ["no-such-tag"], lambda f: f["tags"]),
    ((("tags_exclude", ("PLACEHOLDER",)),), "tags_exclude", None, lambda f: f["tags"]),
    ((("tags_max", 0),), "tags_max", 0, lambda f: len(f["tags"])),
    ((("actors", ("nobody",)),), "actors", ["nobody"], lambda f: f["actors"]),
])
def test_run_tests_reports_key_expected_actual(expect, key, expected, actual_of):
    fields = _run(_spec("single-og"), "SONE-205", _routes_for("single-og"))[0].items[0].fields
    if key == "tags_exclude":
        expect = ((key, (fields["tags"][0],)),)
        expected = [fields["tags"][0]]
    results = run_tests(_with_cases((("tags_max", 99),), expect), CFG, FakeTransport(_routes_for("single-og")))
    assert results[0].passed and results[1].index == 2 and not results[1].passed
    mismatch = results[1].mismatches[0]
    assert (mismatch.key, mismatch.expected) == (key, expected)
    assert mismatch.actual == actual_of(fields)
    assert mismatch.url == SOG


def test_run_tests_status_mismatch_and_format():
    cases = (schema.Case("ZZZZ-999", "ok", (("title", "x"),)), schema.Case("ZZZZ-999", "not_found", ()))
    spec = dataclasses.replace(_spec("single-og"), tests=cases)
    results = run_tests(spec, CFG, FakeTransport(_routes_for("single-og")))
    first = results[0].mismatches[0]
    assert (results[0].index, first.key, first.expected, first.actual, first.url) == (1, "status", "ok", "not_found", "")
    assert results[1].passed
    text = format_results(results)
    assert "FAIL case 1 ZZZZ-999" in text and "PASS case 2 ZZZZ-999" in text
    assert "  status: expected 'ok', actual 'not_found'" in text


def test_format_results_all_pass_has_no_fail():
    ok = run_tests(_spec("single-og"), CFG, FakeTransport(_routes_for("single-og")))
    assert "FAIL" not in format_results(ok)


# ---------- 165-T2：detail_host / public_url / nf_step / 預算 / accepts_number ----------

def test_run_tests_flags_cross_domain_detail_host():
    other = "https://detail.other.test/x"
    routes = {SOG: redirect(other), other: _pg("single-og")}
    spec = _with_cases((("title_contains", "Sample Title One"),))
    results = run_tests(spec, CFG, FakeTransport(routes))
    assert not results[0].passed
    assert results[0].mismatches == (interpret.Mismatch("detail_host", "同站 host", "detail.other.test", other),)


def test_run_tests_mismatch_url_has_no_userinfo():
    target = "https://u:p@single-og.example/x?id=1"
    routes = {SOG: redirect(target), target: _pg("single-og")}
    results = run_tests(_with_cases((("title", "WRONG"),)), CFG, FakeTransport(routes))
    mismatch = results[0].mismatches[0]
    assert mismatch.key == "title"
    assert "u:p@" not in mismatch.url and "?id=1" in mismatch.url


def _userinfo_routes():
    import re
    target = "https://alice:secret@single-og.example/x"
    body = re.sub(r'(og:image"\s+content=")[^"]*', r'\1/cover.jpg', _txt("single-og"))
    assert 'content="/cover.jpg"' in body
    return target, {SOG: redirect(target), target: page(body)}


def test_run_tests_mismatch_actual_has_no_userinfo_from_relative_image():
    _, routes = _userinfo_routes()
    results = run_tests(_with_cases((("cover", "WRONG"),)), CFG, FakeTransport(routes))
    mismatch = results[0].mismatches[0]
    assert mismatch.key == "cover"
    assert "alice:secret@" not in repr(results[0].mismatches)
    assert mismatch.actual == ["https://single-og.example/cover.jpg"] or mismatch.actual == "https://single-og.example/cover.jpg"


def test_to_video_images_from_credentialed_template_have_no_userinfo():
    from core.custom_source.scraper import CustomScraper
    _, routes = _userinfo_routes()
    spec = _spec("single-og")
    result = scrape(spec, "SONE-205", CFG, FakeTransport(routes))
    video = CustomScraper(spec, "c", CFG)._to_video(result.items[0], "SONE-205")
    assert video.cover_url == "https://single-og.example/cover.jpg"
    assert "alice:secret@" not in repr(video.__dict__)


def test_urljoin_transform_fields_have_no_userinfo():
    target, routes = _userinfo_routes()
    spec = _spec("single-og")
    fields = tuple(
        schema.Field(f.name, "css", f.selector, "href", True, (schema.Transform("urljoin", True),)) if f.name == "tags" else f
        for f in spec.fields
    )
    transport = FakeTransport(routes)
    result = scrape(dataclasses.replace(spec, fields=fields), "SONE-205", CFG, transport)
    tags = result.items[0].fields["tags"]
    assert tags and all(t.startswith("https://single-og.example/") for t in tags)
    assert "alice:secret@" not in repr(tags)
    assert target in transport.calls


def test_extracted_images_have_no_userinfo_but_page_still_fetched_with_it():
    target, routes = _userinfo_routes()
    transport = FakeTransport(routes)
    result = scrape(_spec("single-og"), "SONE-205", CFG, transport)
    assert result.items[0].fields["cover"] == "https://single-og.example/cover.jpg"
    assert target in transport.calls


def test_scrape_detail_applies_not_found_when_for_single_stage():
    marker = "<h1"
    assert marker in _txt("single-og") and marker in _txt("two-step-detail-a")
    single = _step0("single-og", not_found_body=marker)
    result = scrape_detail(single, SOG, "SONE-205", CFG, FakeTransport({SOG: _pg("single-og")}))
    assert result.status == "not_found"
    # 兩段式：steps[0] 是搜尋頁標記，不可擋詳情頁
    detail = "https://two-step.example/v/a/"
    two = _step0("two-step", not_found_body=marker)
    result = scrape_detail(two, detail, "SONE-205", CFG, FakeTransport({detail: _pg("two-step-detail-a")}))
    assert result.status in ("ok", "multiple")


@pytest.mark.parametrize("name, number, expected", [
    ("single-og", "SONE-205", True),
    ("single-og", "sone205", True),
    ("single-og", "12345", False),
    ("single-og", "", False),
    ("text", "SONE-205", False),
    ("text", "FC2-2439990", True),
])
def test_accepts_number_table(name, number, expected):
    assert accepts_number(_spec(name), number) is expected


def test_guarded_delegates_to_accepts_number(monkeypatch):
    monkeypatch.setattr(interpret, "accepts_number", lambda spec, number: False)
    result, transport = _run(_spec("single-og"), "SONE-205", _routes_for("single-og"))
    assert (result.status, transport.calls) == ("skipped", [])


def _fake_clock(monkeypatch, step=10):
    ticks = itertools.count(0, step)
    monkeypatch.setattr("core.custom_source.fetch._now", lambda: next(ticks))


def test_budget_stops_requests_after_deadline(monkeypatch):
    _fake_clock(monkeypatch)
    transport = FakeTransport(_routes_for("candidates"))
    result = scrape(_spec("candidates"), "SONE-205", CFG, transport, budget_s=25)
    assert len(transport.calls) == 2
    assert result.status in ("ok", "multiple")


def test_no_budget_means_no_deadline(monkeypatch):
    _fake_clock(monkeypatch)
    transport = FakeTransport(_routes_for("candidates"))
    scrape(_spec("candidates"), "SONE-205", CFG, transport, budget_s=None)
    assert len(transport.calls) == 4


def test_run_tests_total_budget_times_out_later_cases(monkeypatch):
    now = [0]
    monkeypatch.setattr("core.custom_source.fetch._now", lambda: now[0])

    def slow(url):
        now[0] += 30
        return _pg("single-og")

    cases = tuple(schema.Case("SONE-205", "ok", (("title_contains", "Sample Title One"),)) for _ in range(3))
    spec = dataclasses.replace(_spec("single-og"), tests=cases)
    transport = FakeTransport({SOG: slow})
    results = run_tests(spec, CFG, transport, total_budget_s=25)
    assert [r.passed for r in results] == [True, False, False]
    assert results[1].mismatches == (interpret.Mismatch("status", "ok", "error:timeout", ""),)
    assert len(transport.calls) == 1
