"""CustomScraper：ScrapeResult 到 Video 的對應、例外映射、host 限制（全離線）。"""

import pytest

from core.custom_source import schema
from core.custom_source.extract import parse_html
from core.custom_source.interpret import ScrapedItem, ScrapeResult
from core.custom_source.scraper import CustomScraper
from core.proxy_policy import ProxySettings
from core.scrapers.errors import SourceBlocked, SourceParseEmpty, SourceUnreachable
from core.scrapers.models import ScraperConfig
from tests.unit._custom_source_fake import FakeTransport, page
from tests.unit._custom_source_pages import FIXTURE_DIR, PAGES

SID = "custom:t"
SOG = "https://single-og.example/sone-205"
CAND_DETAIL = "https://candidates.example/video/chinese-subtitles/sone-205c/"
S = "T"
FIELDS = {
    "title": S, "maker": "M", "director": "D", "label": "L", "series": "R", "summary": "Y",
    "date": "2000-01-02", "actors": ["A1", "", "A2"], "cover": "https://x.example/c.jpg",
    "tags": ["g1", "g2"], "sample_images": ["https://x.example/1.jpg"], "duration": 90,
}


@pytest.fixture(autouse=True)
def _no_real_dns_or_sleep(monkeypatch):
    monkeypatch.setattr("core.custom_source.guard.resolve_host", lambda host: ["8.8.8.8"])
    monkeypatch.setattr("core.custom_source.fetch.rate_limit", lambda delay=0: None)


def _cfg():
    return ScraperConfig(proxy_settings=ProxySettings())


def _spec(name="single-og"):
    return schema.load_file(FIXTURE_DIR / f"{name}.yaml")


def _txt(name):
    return PAGES[name]


def _scraper(name="single-og"):
    return CustomScraper(_spec(name), SID, _cfg())


def _item(url="https://s.example/a", **extra):
    return ScrapedItem(url, dict(FIELDS, **extra))


def _fake_scrape(monkeypatch, result, target="scrape"):
    seen = []

    def fake(*args, **kwargs):
        seen.append(args)
        return result

    monkeypatch.setattr(f"core.custom_source.scraper.{target}", fake)
    return seen


def _wire(monkeypatch, routes):
    transport = FakeTransport(routes)
    monkeypatch.setattr("core.custom_source.interpret.make_transport", lambda *a, **k: transport)
    return transport


def _err(reason, status=None):
    return ScrapeResult("error", reason=reason, http_status=status)


def test_construct_and_trivial_entry_points(monkeypatch):
    transport = _wire(monkeypatch, {})
    sc = _scraper()
    assert sc.source_name == SID == sc.source_id
    assert sc.search_by_keyword("anything") == [] and sc.probe_plan(5) is None
    assert transport.calls == []


def test_fields_map_to_video(monkeypatch):
    seen = _fake_scrape(monkeypatch, ScrapeResult("ok", items=(_item(),)))
    sc = _scraper()
    video = sc.search("sone205")
    assert seen[0][2] is sc.config
    assert video.number == "SONE-205" and video.source == SID
    assert video.detail_url == "https://s.example/a"
    assert [a.name for a in video.actresses] == ["A1", "A2"]
    for name, key in [("title", "title"), ("maker", "maker"), ("director", "director"), ("label", "label"),
                      ("series", "series"), ("summary", "summary"), ("date", "date"), ("cover_url", "cover")]:
        assert getattr(video, name) == FIELDS[key]
    assert video.tags == FIELDS["tags"] and video.sample_images == FIELDS["sample_images"]
    assert video.duration == FIELDS["duration"]


def test_undeclared_fields_use_defaults(monkeypatch):
    _fake_scrape(monkeypatch, ScrapeResult("ok", items=(ScrapedItem("https://s.example/a", {"title": S}),)))
    video = _scraper().search("SONE-205")
    assert (video.maker, video.actresses, video.tags, video.sample_images, video.duration) == ("", [], [], [], None)


@pytest.mark.parametrize("status", ["not_found", "skipped"])
def test_empty_statuses_give_empty_results(monkeypatch, status):
    seen = _fake_scrape(monkeypatch, ScrapeResult(status))
    _fake_scrape(monkeypatch, ScrapeResult(status), "scrape_detail")
    sc = _scraper("candidates")
    assert sc.search("SONE-205") is None and sc.search_all_versions("SONE-205") == []
    assert sc.fetch_by_detail_url(CAND_DETAIL, "SONE-205") is None
    assert len(seen) == 2


def _two_versions(monkeypatch):
    new, old = _item("https://s.example/new", date="2025-01-01"), _item("https://s.example/old", date="2001-01-01")
    _fake_scrape(monkeypatch, ScrapeResult("multiple", items=(new, old)))
    return new, old


def test_multiple_keeps_scrape_order(monkeypatch):
    new, old = _two_versions(monkeypatch)
    assert [v.detail_url for v in _scraper().search_all_versions("SONE-205")] == [new.detail_url, old.detail_url]


def test_search_returns_newest_version(monkeypatch):
    new, _old = _two_versions(monkeypatch)
    assert _scraper().search("SONE-205").detail_url == new.detail_url


def test_invalid_item_dropped_others_kept(monkeypatch):
    bad, good = _item("https://s.example/bad", duration="abc"), _item("https://s.example/good")
    _fake_scrape(monkeypatch, ScrapeResult("multiple", items=(bad, good)))
    assert [v.detail_url for v in _scraper().search_all_versions("SONE-205")] == [good.detail_url]
    _fake_scrape(monkeypatch, ScrapeResult("multiple", items=(bad, bad)))
    with pytest.raises(SourceParseEmpty) as ei:
        _scraper().search_all_versions("SONE-205")
    assert str(ei.value) == f"{SID}: parse_empty"


def test_video_source_equals_source_id(monkeypatch):
    _fake_scrape(monkeypatch, ScrapeResult("multiple", items=(_item("https://s.example/a"), _item("https://s.example/b"))))
    for sid in ("custom:one", "custom:two"):
        videos = CustomScraper(_spec(), sid, _cfg()).search_all_versions("SONE-205")
        assert [v.source for v in videos] == [sid, sid]


@pytest.mark.parametrize("status, exc", [
    (403, SourceBlocked), (429, SourceBlocked), (503, SourceBlocked),
    (500, RuntimeError), (404, RuntimeError), (502, RuntimeError), (None, RuntimeError),
])
def test_http_status_maps_to_typed_exception(monkeypatch, status, exc):
    _fake_scrape(monkeypatch, _err("http_status", status))
    with pytest.raises(RuntimeError) as ei:
        _scraper().search("SONE-205")
    assert type(ei.value) is exc and str(ei.value) == f"{SID}: http_status"


@pytest.mark.parametrize("reason", ["network", "timeout"])
def test_unreachable_reasons_map_to_source_unreachable(monkeypatch, reason):
    _fake_scrape(monkeypatch, _err(reason))
    with pytest.raises(SourceUnreachable):
        _scraper().search_all_versions("SONE-205")


@pytest.mark.parametrize("reason", ["blocked_target", "too_large", "redirect_limit",
                                    "transport_unavailable", "unexpected"])
def test_other_error_reasons_are_plain_runtime_error(monkeypatch, reason):
    _fake_scrape(monkeypatch, _err(reason, 403))
    with pytest.raises(RuntimeError) as ei:
        _scraper().search("SONE-205")
    assert type(ei.value) is RuntimeError and str(ei.value) == f"{SID}: {reason}"


@pytest.mark.parametrize("status, exc", [(503, SourceBlocked), (500, RuntimeError)])
def test_end_to_end_status_through_interpret(monkeypatch, status, exc):
    _wire(monkeypatch, {SOG: page("", status)})
    with pytest.raises(RuntimeError) as ei:
        _scraper().search("SONE-205")
    assert type(ei.value) is exc


def test_end_to_end_not_found_and_unexpected_extract(monkeypatch):
    _wire(monkeypatch, {"https://single-og.example/zzzz-999": page("", 404), SOG: page(_txt("single-og"))})
    sc = _scraper()
    assert sc.search("ZZZZ-999") is None and sc.search_all_versions("ZZZZ-999") == []

    def boom(*args, **kwargs):
        raise ValueError("canary")

    monkeypatch.setattr("core.custom_source.interpret.extract_fields", boom)
    with pytest.raises(RuntimeError) as ei:
        sc.search("SONE-205")
    assert type(ei.value) is RuntimeError and "canary" not in str(ei.value)


def test_end_to_end_two_step_versions_newest_first(monkeypatch):
    base = "https://two-step.example/search/"
    hrefs = [a["href"] for a in parse_html(_txt("two-step-search")).select("h3.entry-title a")]
    older, newer = hrefs
    _wire(monkeypatch, {base + "SONE-205": page(_txt("two-step-search")),
                        older: page(_txt("two-step-detail-a")), newer: page(_txt("two-step-detail-b"))})
    sc = CustomScraper(_spec("two-step"), "custom:two-step", _cfg())
    videos = sc.search_all_versions("SONE-205")
    assert len(videos) == 2 and [v.date for v in videos] == sorted((v.date for v in videos), reverse=True)
    assert {v.source for v in videos} == {"custom:two-step"}
    assert sc.search("SONE-205").detail_url == videos[0].detail_url


def test_fetch_by_detail_url_same_host_and_subdomain_pass(monkeypatch):
    sub = "https://www.candidates.example/video/x/"
    transport = _wire(monkeypatch, {CAND_DETAIL: page(_txt("two-step-detail-a")),
                                    sub: page(_txt("two-step-detail-b"))})
    sc = _scraper("candidates")
    for url in (CAND_DETAIL, sub):
        video = sc.fetch_by_detail_url(url, "SONE-205")
        assert video.detail_url == url and video.source == SID
    assert transport.calls == [CAND_DETAIL, sub]


@pytest.mark.parametrize("url", [
    "https://other.example/video/x/",
    "https://candidates.example.evil.example/video/x/",
    "https://evil-candidates.example/video/x/",
    "https://candidates.example@evil.example/",
    "http://[::1",
    "file:///x",
])
def test_fetch_by_detail_url_rejects_foreign_host(monkeypatch, url):
    transport = _wire(monkeypatch, {})
    with pytest.raises(RuntimeError) as ei:
        _scraper("candidates").fetch_by_detail_url(url, "SONE-205")
    assert type(ei.value) is RuntimeError and str(ei.value) == f"{SID}: blocked_target"
    assert transport.calls == []


def test_to_video_strips_userinfo_keeps_query():
    item = _item("https://u:p@s.example/a?id=1")
    video = _scraper()._to_video(item, "SONE-205")
    assert video.detail_url == "https://s.example/a?id=1"


def test_to_video_images_from_credentialed_page_have_no_userinfo():
    from core.custom_source.extract import extract_fields
    from core.custom_source.schema import Field
    html = '<img class="c" src="/c.jpg"><a class="s" href="/s1.jpg">x</a>'
    fields = [Field("cover", "css", ".c", "src", False, ()), Field("sample_images", "css", ".s", "href", True, ())]
    out = extract_fields(html, "https://u:p@s.example/a?id=1", fields)
    video = _scraper()._to_video(ScrapedItem("https://u:p@s.example/a?id=1", out), "SONE-205")
    assert video.cover_url == "https://s.example/c.jpg"
    assert video.sample_images == ["https://s.example/s1.jpg"]


def test_parse_empty_maps_to_source_parse_empty(monkeypatch):
    _fake_scrape(monkeypatch, _err("parse_empty"))
    with pytest.raises(SourceParseEmpty) as ei:
        _scraper().search("SONE-205")
    assert str(ei.value) == f"{SID}: parse_empty"


def _kwargs_scrape(monkeypatch, target):
    seen = []

    def fake(*args, **kwargs):
        seen.append(kwargs)
        return ScrapeResult("not_found")

    monkeypatch.setattr(f"core.custom_source.scraper.{target}", fake)
    return seen


def test_custom_budget_passed_to_search_all_versions(monkeypatch):
    seen = _kwargs_scrape(monkeypatch, "scrape")
    monkeypatch.setattr("core.custom_source.scraper.CUSTOM_BUDGET_S", 7)
    _scraper().search_all_versions("SONE-205")
    assert seen == [{"budget_s": 7}]


def test_custom_budget_passed_to_fetch_by_detail_url(monkeypatch):
    seen = _kwargs_scrape(monkeypatch, "scrape_detail")
    monkeypatch.setattr("core.custom_source.scraper.CUSTOM_BUDGET_S", 9)
    _scraper().fetch_by_detail_url("https://single-og.example/x", "SONE-205")
    assert seen == [{"budget_s": 9}]
