"""TASK-200c-T2a — core.nfo_field_edit 九欄寫入純樹層測試。"""

import xml.etree.ElementTree as ET

import pytest

from core import nfo_read
from core.gallery_scanner import VideoScanner
from core.nfo_field_edit import (
    EditContext,
    FieldEditError,
    apply_field,
    dump_tree,
    load_tree,
    read_plot_pair,
)
from core.nfo_read import MANUAL_MAKER_TAG
from core.nfo_title_format import resolve_title_body
from core.title_writeback import rewrite_nfo_titles

NUM = "ABC-123"
DEF = "[{num}]{title}"
NON = "{num} {title} - {actor}"
NON2 = "[{num}]{actor} {title}"

NFO_OWN = """<?xml version="1.0" encoding="utf-8"?>
<movie>
  <title>[ABC-123]Old body</title>
  <originaltitle>Old orig</originaltitle>
  <num>ABC-123</num>
  <premiered>2024-05-06</premiered>
  <release>2024-05-06</release>
  <year>2024</year>
  <studio>OldMaker</studio>
  <set><name>OldSeries</name></set>
  <actor><name>A1</name><role>R1</role><thumb>t1.jpg</thumb></actor>
  <actor><name>A2</name></actor>
  <plot>Old plot</plot>
  <originalplot>Old orig plot</originalplot>
  <tag>g1</tag>
  <genre>g1</genre>
  <website>http://x/?a=1&amp;b=2</website>
  <poster>ABC-123-poster.jpg</poster>
  <uniqueid type="home" default="true">ABC-123</uniqueid>
  <user_tag>u1</user_tag>
  <mystery>zzz</mystery>
  <!-- keep me -->
  <?mypi data?>
</movie>
"""

NFO_THIRD = """<?xml version="1.0" encoding="utf-8"?>
<movie>
  <title>[ABC-123]Third body</title>
  <id>ABC-123</id>
  <premiered>2023-01-02</premiered>
  <maker>ThirdMaker</maker>
  <studio>ThirdStudio</studio>
  <set><name>ThirdSeries</name></set>
  <actors><actor><name>T1</name><role>TR</role><thumb>tt.jpg</thumb></actor><actor><name>T2</name><role>TR2</role></actor></actors>
  <plot>Third plot</plot>
  <genre>only-genre</genre>
  <website>http://y/</website>
</movie>
"""

NFO_THIRD_MAKER_ONLY = """<?xml version="1.0" encoding="utf-8"?>
<movie>
  <title>t</title>
  <num>ABC-123</num>
  <maker>MO</maker>
  <plot>p</plot>
</movie>
"""

NFO_THIRD_STUDIO_ONLY = """<?xml version="1.0" encoding="utf-8"?>
<movie>
  <title>t</title>
  <num>ABC-123</num>
  <studio>SO</studio>
  <plot>p</plot>
</movie>
"""

NFO_THIRD_MAKER_STUDIO = """<?xml version="1.0" encoding="utf-8"?>
<movie>
  <title>t</title>
  <num>ABC-123</num>
  <maker>MO</maker>
  <studio>SO</studio>
  <plot>p</plot>
</movie>
"""

NFO_THIRD_SET_NONAME = """<?xml version="1.0" encoding="utf-8"?>
<movie>
  <title>t</title>
  <num>ABC-123</num>
  <set><other>x</other></set>
  <plot>p</plot>
</movie>
"""

NFO_THIRD_YEAR_ONLY = """<?xml version="1.0" encoding="utf-8"?>
<movie>
  <title>t</title>
  <num>ABC-123</num>
  <year>2023</year>
  <plot>p</plot>
</movie>
"""

NFO_COMMENT_AMP = """<?xml version="1.0" encoding="utf-8"?>
<movie>
  <title>t</title>
  <num>ABC-123</num>
  <!-- ref ?a=1&b=2 -->
  <plot>p</plot>
</movie>
"""

NFO_BARE_AMP = """<?xml version="1.0" encoding="utf-8"?>
<movie>
  <title>t</title>
  <num>ABC-123</num>
  <!-- ref ?a=1&b=2 -->
  <plot>A & B</plot>
</movie>
"""

NFO_TITLE_NO_NUM = """<?xml version="1.0" encoding="utf-8"?>
<movie>
  <title>Old body</title>
  <plot>p</plot>
</movie>
"""


def _load(text):
    return load_tree(text.encode("utf-8"))


def _canon(node):
    if callable(node.tag):
        return ("#node:" + node.tag.__name__, (node.text or "").strip(), (), ())
    return (
        node.tag,
        (node.text or "").strip(),
        tuple(sorted(node.attrib.items())),
        tuple(_canon(c) for c in node),
    )


def _children_snap(root):
    return [_canon(c) for c in root]


def _read_back_nfo(root, fmt=DEF):
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "ABC-123.nfo"
        p.write_bytes(dump_tree(root))
        return VideoScanner(nfo_title_format=fmt).parse_nfo(str(p))


def test_written_value_reads_back_via_nfo_read():
    cases = [
        ("title", {"value": "Val1"}, DEF, NFO_OWN),
        ("original_title", {"value": "Val2"}, DEF, NFO_OWN),
        ("actresses", {"value": ["N1", "N2"]}, DEF, NFO_OWN),
        ("maker", {"value": "Val4"}, DEF, NFO_OWN),
        ("series", {"value": "Val5"}, DEF, NFO_OWN),
        ("release_date", {"value": "2024-06-07"}, DEF, NFO_OWN),
        ("plot", {"value": "Val7"}, DEF, NFO_OWN),
        ("plot_translation", {"value": "Val8"}, DEF, NFO_OWN),
        ("tags", {"add": ["Val9"]}, DEF, NFO_OWN),
        ("title", {"value": "Val1"}, DEF, NFO_THIRD),
        ("original_title", {"value": "Val2"}, DEF, NFO_THIRD),
        ("actresses", {"value": ["N1", "N2"]}, NON2, NFO_THIRD),
        ("maker", {"value": "Val4"}, DEF, NFO_THIRD),
        ("series", {"value": "Val5"}, DEF, NFO_THIRD),
        ("release_date", {"value": "2024-06-07"}, DEF, NFO_THIRD),
        ("plot", {"value": "Val7"}, DEF, NFO_THIRD),
        ("plot_translation", {"value": "Val8"}, DEF, NFO_THIRD),
        ("tags", {"add": ["Val9"]}, DEF, NFO_THIRD),
    ]
    for field, payload, fmt, text in cases:
        root = _load(text)
        res = apply_field(root, field, payload, EditContext(NUM, fmt))
        assert res.changed is True
        info = _read_back_nfo(root, fmt)
        read_fn = {
            "title": lambda r, _fmt=fmt: resolve_title_body(
                nfo_read.nfo_text(r, "title"), NUM,
                nfo_read.nfo_actor_names(r), nfo_read.nfo_first_text(r, ("maker", "studio")),
                nfo_read.nfo_first_text(r, ("release", "premiered", "year")), _fmt,
                nfo_read.nfo_title_record(r)),
            "original_title": lambda r: nfo_read.nfo_text(r, "originaltitle"),
            "actresses": lambda r: nfo_read.nfo_actor_names(r),
            "maker": lambda r: nfo_read.nfo_first_text(r, ("maker", "studio")),
            "series": lambda r: nfo_read.nfo_series_name(r),
            "release_date": lambda r: nfo_read.nfo_first_text(r, ("release", "premiered", "year")),
            "plot": lambda r: read_plot_pair(r)[0],
            "plot_translation": lambda r: read_plot_pair(r)[1],
            "tags": lambda r: nfo_read.nfo_merged_tags(r),
        }[field]
        got = read_fn(load_tree(dump_tree(root)))
        exp_map = {
            "title": "Val1", "original_title": "Val2", "actresses": ["N1", "N2"],
            "maker": "Val4", "series": "Val5", "release_date": "2024-06-07",
            "plot": "Val7", "plot_translation": "Val8", "tags": ["Val9"],
        }
        if field == "tags":
            assert "Val9" in got
        else:
            assert got == exp_map[field], (field, text[:40], got)
        if field == "maker":
            assert info.maker_pinned is True
        if field == "release_date":
            assert info.date == "2024-06-07"
    root = _load(NFO_THIRD_MAKER_ONLY)
    apply_field(root, "maker", {"value": "ZZ"}, EditContext(NUM))
    assert nfo_read.nfo_text(load_tree(dump_tree(root)), "maker") == "ZZ"
    root = _load(NFO_THIRD_STUDIO_ONLY)
    apply_field(root, "maker", {"value": "ZZ"}, EditContext(NUM))
    assert nfo_read.nfo_text(load_tree(dump_tree(root)), "studio") == "ZZ"
    root = _load(NFO_THIRD_YEAR_ONLY)
    apply_field(root, "release_date", {"value": "2025-08-09"}, EditContext(NUM))
    back = load_tree(dump_tree(root))
    assert nfo_read.nfo_text(back, "year") == "2025"
    assert nfo_read.nfo_text(back, "premiered") == "2025-08-09"
    root = _load(NFO_THIRD_SET_NONAME)
    apply_field(root, "series", {"value": "SS"}, EditContext(NUM))
    assert nfo_read.nfo_series_name(load_tree(dump_tree(root))) == "SS"
    root = _load(NFO_THIRD)
    apply_field(root, "maker", {"value": ""}, EditContext(NUM))
    assert nfo_read.nfo_first_text(load_tree(dump_tree(root)), ("maker", "studio")) == ""
    assert load_tree(dump_tree(root)).find(MANUAL_MAKER_TAG) is None
    for field, payload in [
        ("actresses", {"value": []}),
        ("release_date", {"value": ""}),
        ("series", {"value": ""}),
        ("original_title", {"value": ""}),
    ]:
        root = _load(NFO_OWN)
        res = apply_field(root, field, payload, EditContext(NUM))
        assert res.changed is True
        back = load_tree(dump_tree(root))
        if field == "actresses":
            assert nfo_read.nfo_actor_names(back) == []
            assert _read_back_nfo(root).actor == ""
        elif field == "release_date":
            assert nfo_read.nfo_first_text(back, ("release", "premiered", "year")) == ""
            assert _read_back_nfo(root).date == ""
        elif field == "series":
            assert nfo_read.nfo_series_name(back) == ""
            assert _read_back_nfo(root).series == ""
        elif field == "original_title":
            assert nfo_read.nfo_text(back, "originaltitle") == ""
            assert _read_back_nfo(root).originaltitle == ""
    only_plot_nfo = """<?xml version="1.0" encoding="utf-8"?><movie><title>t</title><num>ABC-123</num><plot>Solo</plot></movie>"""
    root = _load(only_plot_nfo)
    res = apply_field(root, "plot", {"value": ""}, EditContext(NUM))
    assert res.changed is True
    back = load_tree(dump_tree(root))
    assert read_plot_pair(back)[0] == ""
    assert _read_back_nfo(root).has_plot is False
    root = _load(NFO_OWN)
    apply_field(root, "plot_translation", {"value": ""}, EditContext(NUM))
    apply_field(root, "plot", {"value": ""}, EditContext(NUM))
    back = load_tree(dump_tree(root))
    assert read_plot_pair(back) == ("", "")
    assert _read_back_nfo(root).has_plot is False


def test_other_elements_survive_field_edit():
    fields = [
        ("title", {"value": "NV"}),
        ("original_title", {"value": "NV"}),
        ("actresses", {"value": ["NV"]}),
        ("maker", {"value": "NV"}),
        ("series", {"value": "NV"}),
        ("release_date", {"value": "2024-06-07"}),
        ("plot", {"value": "NV"}),
        ("plot_translation", {"value": "NV"}),
        ("tags", {"add": ["NV"]}),
    ]
    allowed = {
        "title": {"title", "num", "openaver_title_record"},
        "original_title": {"originaltitle", "title"},
        "actresses": {"actor", "actors", "title", "openaver_title_record", "num"},
        "maker": {"maker", "studio", MANUAL_MAKER_TAG, "title", "openaver_title_record", "num"},
        "series": {"set"},
        "release_date": {"release", "premiered", "year", "title", "openaver_title_record", "num"},
        "plot": {"plot", "originalplot"},
        "plot_translation": {"plot", "originalplot"},
        "tags": {"tag", "genre"},
    }
    for field, payload in fields:
        root = _load(NFO_OWN)
        fmt = NON2 if field == "actresses" else DEF
        before = _children_snap(root)
        apply_field(root, field, payload, EditContext(NUM, fmt))
        after = _children_snap(root)
        fb = [s for s in before if s[0] not in allowed[field]]
        fa = [s for s in after if s[0] not in allowed[field]]
        assert len(fb) == len(fa), (field, len(fb), len(fa))
        for b, a in zip(fb, fa, strict=True):
            assert b == a, (field, b, a)
    root = _load(NFO_COMMENT_AMP)
    apply_field(root, "maker", {"value": "NV"}, EditContext(NUM))
    comments = [c for c in root.iter() if not isinstance(getattr(c, "tag", None), str)]
    assert any((c.text or "") == " ref ?a=1&b=2 " for c in comments)
    root = _load(NFO_BARE_AMP)
    apply_field(root, "maker", {"value": "NV"}, EditContext(NUM))
    comments = [c for c in root.iter() if not isinstance(getattr(c, "tag", None), str)]
    assert any((c.text or "") == " ref ?a=1&b=2 " for c in comments)
    back = load_tree(dump_tree(root))
    assert (back.find("plot").text or "") == "A & B"


def test_actress_set_diff_keeps_roles_and_order():
    root = _load(NFO_OWN)
    res = apply_field(root, "actresses", {"value": ["A2", "N1", "A1"]}, EditContext(NUM))
    assert res.changed is True
    names = [n.text for n in root.findall(".//actor/name")]
    assert names == ["A2", "N1", "A1"]
    by_name = {}
    for a in root.findall(".//actor"):
        n = a.find("name")
        if n is not None and (n.text or "").strip():
            by_name[(n.text or "").strip()] = a
    assert by_name["A1"].find("role") is not None
    assert by_name["A1"].find("thumb") is not None
    assert "A2" in by_name
    root = _load(NFO_OWN)
    apply_field(root, "actresses", {"value": ["A1"]}, EditContext(NUM))
    assert [n.text for n in root.findall(".//actor/name")] == ["A1"]
    assert root.find(".//actor/name").text == "A1"
    root = _load(NFO_THIRD)
    apply_field(root, "actresses", {"value": ["T2", "N9"]}, EditContext(NUM))
    names = [n.text for n in root.findall(".//actor/name")]
    assert names == ["T2", "N9"]
    actors_parent = None
    for p in root.iter():
        for c in list(p):
            if c.tag == "actors":
                actors_parent = c
    assert actors_parent is not None
    kept = [a for a in actors_parent.findall("actor")]
    assert all(a.find("role") is not None or (a.find("name").text or "") == "N9" for a in kept)


def test_tag_add_remove_net_effect_and_hidden_stays():
    root = _load(NFO_OWN)
    res = apply_field(root, "tags", {"add": ["g1", "n1"], "remove": ["g1"]}, EditContext(NUM))
    assert res.changed is True
    tags = nfo_read.nfo_merged_tags(load_tree(dump_tree(root)))
    assert "g1" not in tags
    assert "n1" in tags
    root = _load(NFO_OWN)
    apply_field(root, "tags", {"remove": ["g1"]}, EditContext(NUM))
    tags = nfo_read.nfo_merged_tags(load_tree(dump_tree(root)))
    assert "g1" not in tags
    root = _load(NFO_OWN)
    res = apply_field(root, "tags", {"add": ["g1"]}, EditContext(NUM))
    assert res.changed is False
    assert root.findall("tag") and root.findall("genre")
    root = _load(NFO_OWN)
    res = apply_field(root, "tags", {"add": [], "remove": []}, EditContext(NUM))
    assert res.changed is False


def test_plot_four_combos_and_create_from_missing():
    a, t = read_plot_pair(_load(NFO_OWN))
    assert (a, t) == ("Old orig plot", "Old plot")
    only_plot = """<?xml version="1.0" encoding="utf-8"?><movie><title>t</title><num>ABC-123</num><plot>P</plot></movie>"""
    assert read_plot_pair(_load(only_plot)) == ("P", "")
    root = _load(NFO_OWN)
    apply_field(root, "plot_translation", {"value": ""}, EditContext(NUM))
    apply_field(root, "plot", {"value": ""}, EditContext(NUM))
    back = load_tree(dump_tree(root))
    assert (back.find("plot") is None) or ((back.find("plot").text or "") == "")
    assert back.find("originalplot") is None
    root = _load(NFO_OWN)
    apply_field(root, "plot", {"value": "A2"}, EditContext(NUM))
    a, t = read_plot_pair(load_tree(dump_tree(root)))
    assert (a, t) == ("A2", "Old plot")
    root = _load(NFO_OWN)
    apply_field(root, "plot", {"value": "A2"}, EditContext(NUM))
    apply_field(root, "plot_translation", {"value": "T2"}, EditContext(NUM))
    a, t = read_plot_pair(load_tree(dump_tree(root)))
    assert (a, t) == ("A2", "T2")
    root = _load(NFO_OWN)
    apply_field(root, "plot", {"value": ""}, EditContext(NUM))
    back = load_tree(dump_tree(root))
    assert (back.find("plot").text or "") == "Old plot"
    assert back.find("originalplot") is None
    no_plot = """<?xml version="1.0" encoding="utf-8"?><movie><title>t</title><num>ABC-123</num><premiered>2024-01-01</premiered></movie>"""
    root = _load(no_plot)
    apply_field(root, "plot", {"value": "Hello"}, EditContext(NUM))
    back = load_tree(dump_tree(root))
    assert (back.find("plot").text or "") == "Hello"
    root = _load(NFO_OWN)
    apply_field(root, "plot_translation", {"value": "TT"}, EditContext(NUM))
    a, t = read_plot_pair(load_tree(dump_tree(root)))
    assert a == "Old orig plot" and t == "TT"


def test_title_sidecar_default_untouched_nondefault_rewritten():
    root = _load(NFO_OWN)
    old_title = root.find("title").text
    apply_field(root, "actresses", {"value": ["ZZ"]}, EditContext(NUM, DEF))
    assert root.find("title").text == old_title
    assert root.find("openaver_title_record") is None
    info = _read_back_nfo(root, DEF)
    assert info.title == "Old body"
    third_plain = """<?xml version="1.0" encoding="utf-8"?><movie><title>Old body</title><num>ABC-123</num><actor><name>A1</name></actor><studio>SM</studio><premiered>2024-05-06</premiered><plot>p</plot></movie>"""
    for field, payload in [
        ("actresses", {"value": ["ZZ"]}),
        ("maker", {"value": "NM"}),
        ("release_date", {"value": "2025-01-02"}),
    ]:
        root = _load(third_plain)
        res = apply_field(root, field, payload, EditContext(NUM, DEF))
        assert root.find("title").text == "Old body"
        assert root.find("openaver_title_record") is None
        assert res.changed is True
    root = _load(NFO_OWN)
    apply_field(root, "actresses", {"value": ["ZZ"]}, EditContext(NUM, NON2))
    assert root.find("title").text != old_title
    assert "ZZ" in (root.find("title").text or "")
    assert root.find("openaver_title_record") is not None
    info = _read_back_nfo(root, NON2)
    assert info.title == "Old body"
    root = _load(NFO_TITLE_NO_NUM)
    apply_field(root, "actresses", {"value": ["ZZ"]}, EditContext(NUM, NON2))
    info = _read_back_nfo(root, NON2)
    assert info.title == "Old body"
    assert "[ABC-123]" not in (info.title or "")
    norecord = """<?xml version="1.0" encoding="utf-8"?><movie><title>ABC-123 Foo - A1</title><num>ABC-123</num><actor><name>A1</name></actor><plot>p</plot></movie>"""
    root = _load(norecord)
    apply_field(root, "actresses", {"value": ["B9"]}, EditContext(NUM, NON))
    assert root.find("title").text == "ABC-123 Foo - B9"
    rec = root.find("openaver_title_record")
    assert rec is not None and rec.find("body").text == "Foo"
    info = _read_back_nfo(root, NON)
    assert info.title == "Foo"
    maker_fmt = "{num} {title} [{maker}]"
    root = _load(NFO_OWN)
    apply_field(root, "maker", {"value": "NM2"}, EditContext(NUM, maker_fmt))
    assert "NM2" in (root.find("title").text or "")
    assert root.find("openaver_title_record") is not None
    year_fmt = "{num} {title} ({year})"
    root = _load(NFO_OWN)
    apply_field(root, "release_date", {"value": "2025-08-09"}, EditContext(NUM, year_fmt))
    assert "2025" in (root.find("title").text or "")
    assert root.find("openaver_title_record") is not None
    root = _load(NFO_OWN)
    res = apply_field(root, "maker", {"value": "NM3"}, EditContext(NUM, NON2))
    assert root.find("title").text == old_title
    root = _load(NFO_OWN)
    res = apply_field(root, "release_date", {"value": "2025-08-09"}, EditContext(NUM, NON2))
    assert root.find("title").text == old_title
    same_fmt = "[{num}]{actor} {title}"
    same_nfo = """<?xml version="1.0" encoding="utf-8"?><movie><title>[ABC-123]A1 Foo</title><num>ABC-123</num><actor><name>A1</name></actor><plot>p</plot></movie>"""
    root = _load(same_nfo)
    before = _children_snap(root)
    res = apply_field(root, "actresses", {"value": ["A1"]}, EditContext(NUM, same_fmt))
    assert res.changed is False
    assert _children_snap(root) == before


def test_validation_and_sanitization_raise_before_tree_change():
    for field, payload, code in [
        ("release_date", {"value": "bad"}, "invalid_date"),
        ("release_date", {"value": "2024-02-30"}, "invalid_date"),
        ("title", {"value": "   "}, "title_empty"),
        ("title", {"value": ""}, "title_empty"),
        ("tags", {"add": ["a,b"]}, "tag_invalid"),
        ("tags", {"add": ["a,b"], "remove": ["g1"]}, "tag_invalid"),
        ("tags", {"add": ["4K"]}, "tag_hidden"),
        ("tags", {"add": ["uhd"]}, "tag_hidden"),
        ("number", {"value": "x"}, "invalid_field"),
        ("title", {"value": 123}, "invalid_value"),
        ("actresses", {"value": "nope"}, "invalid_value"),
        ("tags", {"add": "nope"}, "invalid_value"),
        ("plot", {}, "invalid_value"),
    ]:
        root = _load(NFO_OWN)
        before = _children_snap(root)
        with pytest.raises(FieldEditError) as e:
            apply_field(root, field, payload, EditContext(NUM))
        assert e.value.code == code
        assert _children_snap(root) == before
    root = _load(NFO_OWN)
    apply_field(root, "title", {"value": "A\x07B"}, EditContext(NUM))
    raw = dump_tree(root)
    assert b"\x07" not in raw
    ET.fromstring(raw)


def test_no_change_when_value_equals_current_or_absent():
    pinned = NFO_OWN.replace("</movie>", "<openaver_manual_maker>1</openaver_manual_maker></movie>")
    root = _load(pinned)
    res = apply_field(root, "maker", {"value": "OldMaker"}, EditContext(NUM))
    assert res.changed is False
    root = _load(NFO_OWN)
    res = apply_field(root, "series", {"value": "OldSeries"}, EditContext(NUM))
    assert res.changed is False
    no_set = """<?xml version="1.0" encoding="utf-8"?><movie><title>t</title><num>ABC-123</num></movie>"""
    root = _load(no_set)
    res = apply_field(root, "series", {"value": ""}, EditContext(NUM))
    assert res.changed is False
    assert root.find("set") is None
    root = _load(no_set)
    res = apply_field(root, "original_title", {"value": ""}, EditContext(NUM))
    assert res.changed is False
    assert root.find("originaltitle") is None
    root = _load(NFO_OWN)
    res = apply_field(root, "tags", {"add": ["g1"]}, EditContext(NUM))
    assert res.changed is False


GOLDEN_DEFAULT_SRC = """<?xml version="1.0" encoding="utf-8"?>
<movie>
  <title>[ABC-123]Old body</title>
  <originaltitle>Old orig</originaltitle>
  <num>ABC-123</num>
  <plot>p</plot>
  <website>http://x/?a=1&amp;b=2</website>
  <poster>ABC-123-poster.jpg</poster>
  <uniqueid type="home" default="true">ABC-123</uniqueid>
  <actor><name>A1</name></actor>
  <actor><name>A2</name></actor>
  <genre>g1</genre>
  <tag>g1</tag>
</movie>
"""

GOLDEN_NO_NUM_SRC = """<?xml version="1.0" encoding="utf-8"?>
<movie>
  <title>Old title</title>
  <plot>p</plot>
</movie>
"""

GOLDEN_SORTTITLE_SRC = """<?xml version="1.0" encoding="utf-8"?>
<movie>
  <title>[ABC-123]Old body</title>
  <sorttitle>[ABC-123]Old body</sorttitle>
  <num>ABC-123</num>
  <plot>p</plot>
</movie>
"""

GOLDEN_DEFAULT = b'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n<movie>\n  <title>[ABC-123]NewBody</title>\n  <originaltitle>NewOrig</originaltitle>\n  <num>ABC-123</num>\n  <plot>p</plot>\n  <website>http://x/?a=1&amp;b=2</website>\n  <poster>ABC-123-poster.jpg</poster>\n  <uniqueid type="home" default="true">ABC-123</uniqueid>\n  <actor><name>A1</name></actor>\n  <actor><name>A2</name></actor>\n  <genre>g1</genre>\n  <tag>g1</tag>\n</movie>'

GOLDEN_NONDEFAULT = b'<?xml version=\'1.0\' encoding=\'utf-8\'?>\n<movie>\n  <title>ABC-123 NewBody - A1</title>\n  <originaltitle>NewOrig</originaltitle>\n  <num>ABC-123</num>\n  <plot>p</plot>\n  <website>http://x/?a=1&amp;b=2</website>\n  <poster>ABC-123-poster.jpg</poster>\n  <uniqueid type="home" default="true">ABC-123</uniqueid>\n  <actor><name>A1</name></actor>\n  <actor><name>A2</name></actor>\n  <genre>g1</genre>\n  <tag>g1</tag>\n<openaver_title_record><written>ABC-123 NewBody - A1</written><body>NewBody</body></openaver_title_record></movie>'

GOLDEN_NO_NUM = b"<?xml version='1.0' encoding='utf-8'?>\n<movie>\n  <title>[ABC-123]NewBody</title>\n  <originaltitle>NewOrig</originaltitle><num>ABC-123</num><plot>p</plot>\n</movie>"

GOLDEN_SORTTITLE = b"<?xml version='1.0' encoding='utf-8'?>\n<movie>\n  <title>[ABC-123]NewBody</title>\n  <originaltitle>NewOrig</originaltitle><sorttitle>[ABC-123]NewBody</sorttitle>\n  <num>ABC-123</num>\n  <plot>p</plot>\n</movie>"


def _golden_call(tmp_path, text, name, **kw):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    base = dict(number="ABC-123", title_body="NewBody", original_title="NewOrig",
                actors=["A1", "A2"], maker="Mk", date="2024-05-06",
                nfo_title_format=DEF)
    base.update(kw)
    return rewrite_nfo_titles(str(p), **base)


def test_rewrite_nfo_titles_bytes_unchanged_after_extract(tmp_path):
    assert _golden_call(tmp_path, GOLDEN_DEFAULT_SRC, "a.nfo") == GOLDEN_DEFAULT
    assert _golden_call(tmp_path, GOLDEN_DEFAULT_SRC, "b.nfo", nfo_title_format=NON) == GOLDEN_NONDEFAULT
    assert _golden_call(tmp_path, GOLDEN_NO_NUM_SRC, "c.nfo") == GOLDEN_NO_NUM
    assert _golden_call(tmp_path, GOLDEN_SORTTITLE_SRC, "d.nfo") == GOLDEN_SORTTITLE
