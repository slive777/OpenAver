"""自訂來源 schema：載入即驗證，要嘛得到不可變 Spec，要嘛得到指出欄位與類別的 LoadError。"""
import dataclasses
import socket
from pathlib import Path

import pytest

from core.custom_source.errors import LOAD_REASONS, LoadError
import hashlib

from core.custom_source import schema
from core.custom_source.schema import ID_RE, MAX_BYTES, load_bytes, load_file, load_text, load_uploaded
from core.source_config import get_builtin_sources, get_manual_only_sources

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "custom_sources"
FIXTURE_STEMS = ["single-og", "single-og-min", "two-step", "candidates", "fuzzy", "text"]

BASE = """\
id: base
name: Base
fetch: plain
number_pattern: 'ABC-\\d+'
steps:
  - url: "https://base.example/{number_lower}"
fields:
  title: {css: "h1"}
tests:
  - number: ABC-123
    expect: {title: "x", tags_max: 3}
  - number: ABC-999
    status: not_found
"""

TWO = """\
id: two
name: Two
fetch: plain
number_pattern: 'ABC-\\d+'
steps:
  - url: "https://two.example/s/{number}"
    results: {css: "a.hit", keep_if_contains: "{number_lower}"}
  - {}
fields:
  title: {css: "h1"}
tests:
  - number: ABC-123
    expect: {title: "x", tags_max: 3}
  - number: ABC-999
    status: not_found
"""


NF_CASE = "  - number: ABC-999\n    status: not_found\n"


def sub(base, old, new):
    assert base.count(old) == 1, old
    return base.replace(old, new)


def rows():
    """(格名, 輸入文字, filename_stem, 預期 reason, 預期 field_path)；每格輸入各異。"""
    r = []

    def add(name, text, reason, path, stem=None):
        r.append((name, text, stem or ("two" if text.startswith("id: two") else "base"), reason, path))

    # YAML 層級
    add("yaml_syntax", "id: [unclosed", "yaml_syntax", "")
    add("yaml_multidoc", BASE + "---\nid: other\n", "yaml_syntax", "")
    add("dup_top", BASE + "name: Again\n", "duplicate_key", "")
    add("dup_nested", sub(BASE, 'title: {css: "h1"}', 'title: {css: "h1", css: "h2"}'), "duplicate_key", "")
    add("alias", sub(BASE, "fields:\n  title: {css: \"h1\"}",
                     "fields:\n  title: &a {css: \"h1\"}\n  cover: *a"), "alias", "")
    add("unsafe_tag", "id: !!python/name:os.getcwd\n", "unsafe_tag", "")
    add("too_large", BASE + "# " + "a" * 70000 + "\n", "too_large", "")
    add("too_large_multibyte", BASE + "# " + "中" * 22000 + "\n", "too_large", "")
    # unknown_key
    add("unknown_top", BASE + "censored: true\n", "unknown_key", "censored")
    add("unknown_step", sub(BASE, '{number_lower}"', '{number_lower}"\n    extra: 1'), "unknown_key", "steps[0].extra")
    add("unknown_field_key", sub(BASE, '{css: "h1"}', '{css: "h1", regexx: 1}'), "unknown_key", "fields.title.regexx")
    add("unknown_field_name", sub(BASE, 'title: {css: "h1"}', 'title: {css: "h1"}\n  keywords: {css: "p"}'),
        "unknown_key", "fields.keywords")
    add("unknown_case_key", sub(BASE, "  - number: ABC-123", "  - nummber: ABC-123\n    number: ABC-123"),
        "unknown_key", "tests[0].nummber")
    add("unknown_expect_old_tilde", sub(BASE, 'title: "x"', '"title~": "x"'), "unknown_key", "tests[0].expect.title~")
    # id / fetch
    add("bad_id_chars", sub(BASE, "id: base", "id: Bad_ID"), "bad_id", "id", stem="Bad_ID")
    add("bad_id_nonstr", sub(BASE, "id: base", "id: 123"), "bad_id", "id", stem="123")
    add("reserved_id", sub(BASE, "id: base", "id: dmm"), "reserved_id", "id", stem="dmm")
    add("id_mismatch", BASE, "id_filename_mismatch", "id", stem="other")
    add("fetch_cf", sub(BASE, "fetch: plain", "fetch: cf"), "fetch_cf_unsupported", "fetch")
    add("fetch_unknown", sub(BASE, "fetch: plain", "fetch: browser"), "unknown_fetch", "fetch")
    # pattern / template / selector / transform
    add("pattern_uncompilable", sub(BASE, "'ABC-\\d+'", "'('"), "bad_pattern", "number_pattern")
    add("pattern_too_long", sub(BASE, "'ABC-\\d+'", "'" + "a" * 201 + "'"), "bad_pattern", "number_pattern")
    add("regex_param_no_group", sub(BASE, '{css: "h1"}', '{css: "h1", then: [{regex: "abc"}]}'),
        "bad_pattern", "fields.title.then[0].regex")
    add("test_number_mismatch", sub(BASE, "number: ABC-123", "number: XYZ-123"), "bad_pattern", "tests[0].number")
    add("tpl_unknown_placeholder", sub(BASE, "{number_lower}", "{foo}"), "bad_template", "steps[0].url")
    add("tpl_unbalanced", sub(BASE, "{number_lower}", "{number"), "bad_template", "steps[0].url")
    add("tpl_in_host", sub(BASE, "base.example/{number_lower}", "{number}.example/x"), "bad_template", "steps[0].url")
    add("tpl_scheme", sub(BASE, "https://", "ftp://"), "bad_template", "steps[0].url")
    add("tpl_suffix_without_candidates", sub(BASE, "{number_lower}", "{suffix}"), "bad_template", "steps[0].url")
    add("tpl_localhost", sub(BASE, "https://base.example/", "http://localhost/"), "bad_template", "steps[0].url")
    add("tpl_ipv4", sub(BASE, "https://base.example/", "http://10.0.0.5/"), "bad_template", "steps[0].url")
    add("tpl_ipv6", sub(BASE, "https://base.example/", "http://[::1]/"), "bad_template", "steps[0].url")
    add("tpl_keep_suffix", sub(TWO, 'keep_if_contains: "{number_lower}"', 'keep_if_contains: "{suffix}"'),
        "bad_template", "steps[0].results.keep_if_contains")
    add("tpl_authority_backslash", sub(BASE, '"https://base.example/{number_lower}"',
                                       "'http://192.168.1.1\\@router.example/{number}'"), "bad_template", "steps[0].url")
    add("selector_field", sub(BASE, '{css: "h1"}', '{css: "a[href"}'), "bad_selector", "fields.title.css")
    add("selector_results", sub(TWO, "a.hit", "div >"), "bad_selector", "steps[0].results.css")
    add("transform_unknown", sub(BASE, '{css: "h1"}', '{css: "h1", then: [{eval: "1"}]}'),
        "unknown_transform", "fields.title.then[0]")
    # AC-4 負向
    add("no_negative", sub(BASE, ", tags_max: 3", ""), "missing_negative_assert", "tests")
    # CD-165-9：至少一案查無
    add("missing_not_found_case", sub(BASE, NF_CASE, ""), "missing_not_found_case", "tests")
    # bad_value：結構與值域
    add("empty_file", "", "bad_value", "")
    add("top_not_mapping", "- a\n- b\n", "bad_value", "")
    add("missing_id", sub(BASE, "id: base\n", ""), "bad_value", "id", stem="base")
    add("name_too_long", sub(BASE, "name: Base", "name: " + "n" * 41), "bad_value", "name")
    add("name_control_char", sub(BASE, "name: Base", 'name: "a\\x07b"'), "bad_value", "name")
    add("steps_three", sub(TWO, "  - {}\n", "  - {}\n  - {}\n"), "bad_value", "steps")
    add("single_step_with_results", sub(BASE, '{number_lower}"', '{number_lower}"\n    results: {css: "a", keep_if_contains: "x"}'),
        "bad_value", "steps[0].results")
    add("two_step_missing_results", sub(TWO, '    results: {css: "a.hit", keep_if_contains: "{number_lower}"}\n', ""),
        "bad_value", "steps[0].results")
    add("second_step_not_empty", sub(TWO, "  - {}\n", "  - {url: 'https://two.example/'}\n"), "bad_value", "steps[1]")
    add("candidates_in_two_step", sub(TWO, "    results:", '    candidates: ["a"]\n    results:'),
        "bad_value", "steps[0].candidates")
    add("candidates_too_many", sub(BASE, '{number_lower}"', '{number_lower}"\n    candidates: [a,b,c,d,e,f,g,h,i]'),
        "bad_value", "steps[0].candidates")
    add("candidate_too_long", sub(BASE, '{number_lower}"', '{number_lower}"\n    candidates: ["' + "c" * 17 + '"]'),
        "bad_value", "steps[0].candidates[0]")
    add("div_bool", sub(BASE, '{css: "h1"}', '{css: "h1", then: [{div: true}]}'), "bad_value", "fields.title.then[0].div")
    add("div_zero", sub(BASE, '{css: "h1"}', '{css: "h1", then: [{div: 0}]}'), "bad_value", "fields.title.then[0].div")
    add("urljoin_not_true", sub(BASE, '{css: "h1"}', '{css: "h1", then: [{urljoin: "yes"}]}'),
        "bad_value", "fields.title.then[0].urljoin")
    add("then_item_two_keys", sub(BASE, '{css: "h1"}', '{css: "h1", then: [{split: ",", div: 2}]}'),
        "bad_value", "fields.title.then[0]")
    add("field_two_sources", sub(BASE, '{css: "h1"}', '{css: "h1", meta: "og:title"}'), "bad_value", "fields.title")
    add("attr_with_meta", sub(BASE, '{css: "h1"}', '{meta: "og:title", attr: "href"}'), "bad_value", "fields.title.attr")
    add("jsonld_bad_shape", sub(BASE, '{css: "h1"}', '{jsonld: "NoDotHere"}'), "bad_value", "fields.title.jsonld")
    add("fields_no_title_cover", sub(BASE, 'title: {css: "h1"}', 'summary: {css: "p"}'), "bad_value", "fields")
    add("tests_empty", sub(BASE, BASE[BASE.index("tests:"):], "tests: []\n"), "bad_value", "tests")
    add("status_invalid", sub(BASE, "  - number: ABC-123", "  - number: ABC-123\n    status: maybe"),
        "bad_value", "tests[0].status")
    add("ok_without_positive", sub(BASE, 'title: "x", tags_max: 3', "tags_max: 3"), "bad_value", "tests[0].expect")
    add("max_on_scalar_field", sub(BASE, "tags_max: 3", "title_max: 3"), "bad_value", "tests[0].expect.title_max")
    add("expect_value_bool", sub(BASE, 'title: "x"', "title: true"), "bad_value", "tests[0].expect.title")
    add("non_str_key", sub(BASE, "steps:", "1: x\nsteps:"), "bad_value", "")
    add("negative_only_in_not_found", sub(BASE, ", tags_max: 3", "") + "  - number: ABC-456\n    status: not_found\n    expect: {tags_max: 0}\n",
        "missing_negative_assert", "tests")
    add("split_empty", sub(BASE, '{css: "h1"}', '{css: "h1", then: [{split: ""}]}'), "bad_value", "fields.title.then[0].split")
    add("strip_label_empty", sub(BASE, '{css: "h1"}', '{css: "h1", then: [{strip_label: ""}]}'),
        "bad_value", "fields.title.then[0].strip_label")
    add("all_not_bool", sub(BASE, '{css: "h1"}', '{css: "h1", all: 1}'), "bad_value", "fields.title.all")
    add("exclude_empty_list", sub(BASE, "tags_max: 3", "tags_exclude: []"), "bad_value", "tests[0].expect.tags_exclude")
    add("contains_empty", sub(BASE, 'title: "x"', 'title_contains: ""'), "bad_value", "tests[0].expect.title_contains")
    add("multiple_without_positive", sub(BASE, "  - number: ABC-123", "  - number: ABC-123\n    status: multiple")
        .replace('title: "x", ', ""), "bad_value", "tests[0].expect")
    add("div_huge_int", sub(BASE, '{css: "h1"}', '{css: "h1", then: [{div: 1' + "0" * 400 + '}]}'),
        "bad_value", "fields.title.then[0].div")
    add("div_inf", sub(BASE, '{css: "h1"}', '{css: "h1", then: [{div: .inf}]}'), "bad_value", "fields.title.then[0].div")
    add("div_nan", sub(BASE, '{css: "h1"}', '{css: "h1", then: [{div: .nan}]}'), "bad_value", "fields.title.then[0].div")
    add("tag_int_garbage", sub(BASE, "id: base", "id: !!int abc"), "yaml_syntax", "")
    add("tag_bool_garbage", sub(BASE, "name: Base", "name: !!bool nonsense"), "yaml_syntax", "")
    add("garbage_text", "\x00\x01\x02 ￾{{[", "yaml_syntax", "")
    return r


REJECTIONS = rows()


@pytest.mark.parametrize("name,text,stem,reason,path", REJECTIONS, ids=[r[0] for r in REJECTIONS])
def test_rejection_table(name, text, stem, reason, path):
    with pytest.raises(LoadError) as ei:
        load_text(text, stem)
    assert (ei.value.reason, ei.value.field_path) == (reason, path)
    assert reason in LOAD_REASONS


def test_rejection_table_size_and_coverage():
    assert len(REJECTIONS) >= 20
    assert len({r[0] for r in REJECTIONS}) == len(REJECTIONS)
    assert len({r[1] for r in REJECTIONS}) == len(REJECTIONS)
    assert {r[3] for r in REJECTIONS} == set(LOAD_REASONS)
    assert len(LOAD_REASONS) == 18


@pytest.mark.parametrize("stem", FIXTURE_STEMS)
def test_fixture_yaml_loads(stem):
    spec = load_file(FIXTURE_DIR / f"{stem}.yaml")
    assert spec.id == stem
    assert spec.hosts and all(h.endswith(".example") for h in spec.hosts)
    hash(spec)


def test_spec_is_immutable_and_hashable():
    spec = load_text(BASE, "base")
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.id = "x"
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.steps[0].url = "x"
    assert isinstance(hash(spec), int)
    assert spec.hosts == ("base.example",)


def test_spec_shape_two_step_and_candidates():
    two = load_file(FIXTURE_DIR / "two-step.yaml")
    assert len(two.steps) == 2 and two.steps[0].results.css and two.steps[0].candidates == ("",)
    assert two.steps[1].url is None and two.steps[1].candidates == ()
    cand = load_file(FIXTURE_DIR / "candidates.yaml")
    assert cand.steps[0].candidates == ("c", "uc", "")


def test_bom_and_crlf_file_loads(tmp_path):
    p = tmp_path / "base.yaml"
    p.write_bytes(b"\xef\xbb\xbf" + BASE.replace("\n", "\r\n").encode("utf-8"))
    assert load_file(p).id == "base"


def test_unquoted_date_expect_loads():
    text = sub(BASE, 'title: "x"', 'title: "x", date: 2024-05-01')
    spec = load_text(text, "base")
    assert ("date", "2024-05-01") in spec.tests[0].expect


def test_size_boundary_is_bytes_not_chars():
    pad = 65536 - len(BASE.encode("utf-8")) - 2
    assert pad > 0
    assert load_text(BASE + "#" + "a" * pad + "\n", "base").id == "base"
    with pytest.raises(LoadError) as ei:
        load_text(BASE + "#" + "a" * (pad + 1) + "\n", "base")
    assert ei.value.reason == "too_large"
    # 21000 個中文字是 63000 位元組，通過
    assert load_text(BASE + "#" + "中" * 21000 + "\n", "base").id == "base"


def test_load_does_no_dns(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("載入不得做 DNS")
    monkeypatch.setattr(socket, "getaddrinfo", boom)
    for stem in FIXTURE_STEMS:
        load_file(FIXTURE_DIR / f"{stem}.yaml")


def test_unsafe_tag_not_executed(tmp_path):
    sentinel = tmp_path / "sentinel"
    text = f'id: !!python/object/apply:os.system ["touch {sentinel}"]\n'
    with pytest.raises(LoadError) as ei:
        load_text(text, "base")
    assert ei.value.reason == "unsafe_tag"
    assert not sentinel.exists()


def test_any_input_yields_spec_or_loaderror():
    for text in ["\x00\x01\x02", "[" * 5000, "? [a]\n: b\n", "a: !!binary |\n  AAAA\n", "{a: 1, a: 2}", "﻿", "---\n---\n"]:
        try:
            load_text(text, "base")
        except LoadError:
            continue
        raise AssertionError(f"應被拒絕: {text[:20]!r}")


def test_reserved_ids_match_source_config():
    ids = {s.id for s in get_builtin_sources()} | {s.id for s in get_manual_only_sources()}
    ids |= {"auto", "metatube", "custom"}
    for rid in sorted(ids):
        with pytest.raises(LoadError) as ei:
            load_text(sub(BASE, "id: base", f"id: {rid}"), rid)
        assert ei.value.reason == "reserved_id", rid
    from core.custom_source import schema
    assert set(schema.RESERVED_IDS) == ids


@pytest.mark.parametrize("text", [
    sub(BASE, NF_CASE, ""),
    sub(BASE, NF_CASE, "  - number: ABC-456\n    status: multiple\n    expect: {title: \"y\"}\n"),
], ids=["ok_only", "ok_plus_multiple"])
def test_not_found_case_required(text):
    with pytest.raises(LoadError) as ei:
        load_text(text, "base")
    assert (ei.value.reason, ei.value.field_path) == ("missing_not_found_case", "tests")


def test_yaml_syntax_reports_one_based_line():
    text = "id: base\nname: Base\nfields:\n  title: {css: h1}\n   cover: {css: h2}\n"
    with pytest.raises(LoadError) as ei:
        load_text(text, "base")
    assert ei.value.reason == "yaml_syntax" and ei.value.line == 5
    with pytest.raises(LoadError) as ei:
        load_text(sub(BASE, "id: base", "id: Bad_ID"), "Bad_ID")
    assert ei.value.reason == "bad_id" and ei.value.line is None


def test_load_bytes_too_large():
    pad = MAX_BYTES - len(BASE.encode("utf-8")) - 2
    exact = (BASE + "#" + "a" * pad + "\n").encode("utf-8")
    assert len(exact) == MAX_BYTES
    assert load_bytes(exact, "base")[0].id == "base"
    with pytest.raises(LoadError) as ei:
        load_bytes(exact + b"#", "base")
    assert ei.value.reason == "too_large"


@pytest.mark.parametrize("bad_id, reason", [
    ("../x", "bad_id"), ("auto", "reserved_id"), ('"a\\n"', "bad_id"),
])
def test_load_uploaded_rejects_untrusted_id(bad_id, reason):
    with pytest.raises(LoadError) as ei:
        load_uploaded(sub(BASE, "id: base", f"id: {bad_id}"))
    assert ei.value.reason == reason


def test_load_uploaded_takes_id_from_yaml_without_filename():
    spec = load_uploaded(BASE)
    assert spec.id == "base" and spec == load_text(BASE, "base")
    with pytest.raises(LoadError) as ei:
        load_uploaded(sub(BASE, NF_CASE, ""))
    assert ei.value.reason == "missing_not_found_case"


def test_load_bytes_sha256_is_of_raw_bytes():
    raw = b"\xef\xbb\xbf" + BASE.replace("\n", "\r\n").encode("utf-8")
    spec, digest = load_bytes(raw, "base")
    assert spec.id == "base" and digest == hashlib.sha256(raw).hexdigest()


def test_id_re_is_public_and_fullmatch_only():
    assert not hasattr(schema, "_" + "ID_RE")
    assert ID_RE.fullmatch("a-b1") and not ID_RE.fullmatch("a\n") and not ID_RE.fullmatch("A_b")


# ---- T15：number_pattern 選填（缺席或 null＝任何非空番號都接受）
NO_PATTERN = sub(BASE, "number_pattern: 'ABC-\\d+'\n", "")
NULL_PATTERN = sub(BASE, "number_pattern: 'ABC-\\d+'", "number_pattern:")


@pytest.mark.parametrize("text", [NO_PATTERN, NULL_PATTERN], ids=["absent", "null"])
def test_number_pattern_optional(text):
    assert load_text(text, "base").number_pattern is None


def test_no_pattern_tests_numbers_not_blocked():
    text = sub(NO_PATTERN, "number: ABC-123", "number: DA003")
    assert load_text(text, "base").tests[0].number == "DA003"


def test_pattern_given_still_validated():
    with pytest.raises(LoadError) as e:
        load_text(sub(BASE, "number: ABC-123", "number: DA003"), "base")
    assert e.value.reason == "bad_pattern"
