"""自訂來源 T4：五種變換與欄位型別層（純函式、全離線）。"""
import re
from pathlib import Path

import pytest

from core.custom_source import schema
from core.custom_source.extract import extract_fields, parse_html
from core.custom_source.transforms import apply_transforms, round_half_up

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "custom_sources"
BASE = "https://site.example/a/b/page.html"


def T(name, arg=True):
    return schema.Transform(name, arg)


def F(name, kind, selector, attr=None, all=False, then=()):
    return schema.Field(name, kind, selector, attr, all, tuple(then))


def run(html, *fields, base=BASE):
    return extract_fields(html, base, tuple(fields))


@pytest.mark.parametrize("values,transforms,expected", [
    (["SONE-205 標題"], [T("regex", r"^(\S+)")], ["SONE-205"]),
    (["abc"], [T("regex", r"^(\d+)")], []),
    (["x"], [T("regex", r"(a)?x")], []),
    (["番號：ABP-1"], [T("strip_label", "番號：")], ["ABP-1"]),
    (["ABP-2"], [T("strip_label", "番號：")], ["ABP-2"]),
    (["a, b ,, c"], [T("split", ",")], ["a", "b", "c"]),
    (["x/y.jpg"], [T("urljoin")], ["https://site.example/a/b/x/y.jpg"]),
    (["120", "abc", "nan", "inf"], [T("div", 60)], ["2"]),
    (["k:1|k:2", "3"], [T("split", "|"), T("strip_label", "k:")], ["1", "2", "3"]),
])
def test_transform_table(values, transforms, expected):
    assert apply_transforms(values, tuple(transforms), BASE) == expected


def test_regex_no_match_drops_element():
    assert apply_transforms(["沒有番號"], (T("regex", r"\[(\w+)\]"),), BASE) == []


def test_div_rounds_half_up():
    assert apply_transforms(["8910"], (T("div", 60),), BASE) == ["149"]
    assert round_half_up(148.5) == 149


@pytest.mark.parametrize("raw,expected", [
    ("2024-05-01", "2024-05-01"),
    ("2024/5/1", "2024-05-01"),
    ("2024.05.01", "2024-05-01"),
    ("2024-05-01T10:00:00+09:00", "2024-05-01"),
    ("2024-05-01T10:00:00Z", "2024-05-01"),
    ("2024-05-01T10:00:00", "2024-05-01"),
    ("2024年5月1日", "2024-05-01"),
    (" 2024-05-01 ", "2024-05-01"),
    ("2024-05-01T23:30:00-05:00", "2024-05-01"),
    ("2024-05-01T00:30:00+09:00", "2024-05-01"),
])
def test_date_shapes(raw, expected):
    html = f'<meta name="d" content="{raw}">'
    assert run(html, F("date", "meta", "d"))["date"] == expected


@pytest.mark.parametrize("raw", [
    "May 1, 2024", "20240501", "2024-02-30", "2024-13-45", "2024-05-01 abc",
    "", "2024-05/01", "發行 2024-05-01 日",
])
def test_date_unparsable_is_empty(raw):
    html = f'<meta name="d" content="{raw}">'
    assert run(html, F("date", "meta", "d"))["date"] == ""


@pytest.mark.parametrize("raw,expected", [
    ("149", 149), ("約 120.5 分", 121), ("n/a", None), ("0", None), ("90分", 90), ("9" * 400, None),
])
def test_duration(raw, expected):
    html = f'<meta name="m" content="{raw}">'
    assert run(html, F("duration", "meta", "m"))["duration"] == expected


def test_non_http_urls_dropped():
    html = ('<div><a href="javascript:void(0)">1</a><a href="data:image/png;base64,AA">2</a>'
            '<a href="/ok1.jpg">3</a><a href="mailto:a@b.c">4</a><a href="ftp://x.example/f.jpg">6</a><a href="file://host/f.jpg">7</a><a href="https://x.example/ok2.jpg">5</a></div>')
    out = run(html, F("sample_images", "css", "a", attr="href", all=True))
    assert out["sample_images"] == ["https://site.example/ok1.jpg", "https://x.example/ok2.jpg"]


def test_unparsable_url_drops_only_itself():
    html = '<img src="https://[">'+'<img src="/ok.jpg">'
    out = run(html, F("sample_images", "css", "img", attr="src", all=True))
    assert out["sample_images"] == ["https://site.example/ok.jpg"]
    assert apply_transforms(["https://[", "/x"], (T("urljoin"),), BASE) == ["https://site.example/x"]
    assert run(html, F("cover", "css", "img", attr="src"))["cover"] == ""


def test_relative_urls_joined_to_final_url():
    html = '<img class="c" src="/img/a.jpg"><i class="p" data-s="//cdn.example/p.jpg">'
    out = run(html, F("cover", "css", "img.c", attr="src"))
    assert out["cover"] == "https://site.example/img/a.jpg"
    out = run(html, F("cover", "css", "i.p", attr="data-s"))
    assert out["cover"] == "https://cdn.example/p.jpg"


def test_lists_dedupe_keep_order():
    html = '<b class="t">B</b><b class="t">A</b><b class="t">B</b><b class="t">C</b><b class="t">A</b>'
    assert run(html, F("tags", "css", ".t", all=True))["tags"] == ["B", "A", "C"]


def test_empty_names_dropped():
    html = '<i class="a">女優：A</i><i class="a">女優：</i><i class="a">女優：B</i>'
    out = run(html, F("actors", "css", ".a", all=True, then=[T("strip_label", "女優：")]))
    assert out["actors"] == ["A", "B"]


def test_meta_matches_property_and_name():
    html = '<meta property="og:x" content="P"><meta name="description" content="N"><meta name="nocontent">'
    assert run(html, F("title", "meta", "og:x"))["title"] == "P"
    assert run(html, F("summary", "meta", "description"))["summary"] == "N"
    assert run(html, F("maker", "meta", "nocontent"))["maker"] == ""


def test_css_text_keeps_br_boundary():
    html = "<p>第一行<br>第二行</p>"
    assert run(html, F("summary", "css", "p"))["summary"] == "第一行 第二行"


def test_css_attr_and_multivalue_attr():
    html = '<a class="x y" href="/h">t</a>'
    assert run(html, F("maker", "css", "a", attr="class"))["maker"] == "x y"
    assert run(html, F("maker", "css", "a", attr="data-none"))["maker"] == ""


def _ld(*blobs):
    return "".join(f'<script type="application/ld+json">{b}</script>' for b in blobs)


@pytest.mark.parametrize("html,sel,expected", [
    (_ld('{"@type":"VideoObject","name":"top"}'), "VideoObject.name", "top"),
    (_ld('[{"@type":"Other"},{"@type":"VideoObject","name":"lst"}]'), "VideoObject.name", "lst"),
    (_ld('{"@graph":[{"@type":"WebSite"},{"@type":"VideoObject","name":"gr"}]}'), "VideoObject.name", "gr"),
    (_ld('{"@type":["Thing","VideoObject"],"name":"multi"}'), "VideoObject.name", "multi"),
    (_ld('{broken', '{"@type":"VideoObject","name":"after-bad"}'), "VideoObject.name", "after-bad"),
    (_ld('{"@type":"Person","name":"x"}'), "VideoObject.name", ""),
    (_ld('{"@type":"VideoObject","name":null}'), "VideoObject.name", ""),
    (_ld('{"@type":"VideoObject","name":["l1","l2"]}'), "VideoObject.name", "l1"),
])
def test_jsonld_shapes(html, sel, expected):
    assert run(html, F("title", "jsonld", sel))["title"] == expected


def test_all_vs_first_and_chain_drops_empty():
    html = '<s class="t">a</s><s class="t"> </s><s class="t">b</s>'
    assert run(html, F("tags", "css", ".t"))["tags"] == ["a"]
    assert run(html, F("tags", "css", ".t", all=True))["tags"] == ["a", "b"]
    assert run(html, F("title", "css", ".t", all=True))["title"] == "a"
    html2 = '<s class="t">zz</s><s class="t">ok</s>'
    assert run(html2, F("title", "css", ".t", then=[T("regex", r"(ok)")]))["title"] == "ok"


@pytest.mark.parametrize("page", ["", "\x00�<<>>&&", "<html><body></body></html>"])
def test_garbage_page_gives_empty_shape(page):
    fields = (F("title", "css", "h1"), F("date", "meta", "d"), F("duration", "css", ".x"),
              F("tags", "css", ".t", all=True), F("cover", "jsonld", "A.b"))
    assert extract_fields(page, BASE, fields) == {
        "title": "", "date": "", "duration": None, "tags": [], "cover": ""}


def test_only_declared_fields_and_accepts_soup():
    soup = parse_html("<h1>T</h1>")
    assert extract_fields(soup, BASE, (F("title", "css", "h1"),)) == {"title": "T"}


@pytest.mark.parametrize("spec_id,page", [
    ("single-og", "single-og.html"), ("single-og-min", "single-og-min.html"),
    ("two-step", "two-step-detail-a.html"), ("fuzzy", "fuzzy-detail.html"),
    ("text", "text-detail.html"),
])
def test_fixtures_shapes(spec_id, page):
    spec = schema.load_file(FIX / f"{spec_id}.yaml")
    html = (FIX / page).read_text(encoding="utf-8")
    out = extract_fields(html, f"https://{spec_id}.example/x", spec.fields)
    assert set(out) == {f.name for f in spec.fields}
    assert out["cover"].startswith("http")
    assert out["tags"] and all(isinstance(t, str) and t for t in out["tags"])
    if "date" in out:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", out["date"])
    if spec_id == "single-og":
        assert out["duration"] == 149  # div: 60 對 8967 秒有作用（唯一站方值相等格）
        assert isinstance(out["duration"], int)


def test_deep_nested_jsonld_isolated():
    deep = "[" * 5000 + "]" * 5000
    html = _ld(deep, '{"@type":"VideoObject","name":"ok"}')
    assert run(html, F("title", "jsonld", "VideoObject.name"))["title"] == "ok"
