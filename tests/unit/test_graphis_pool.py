"""Graphis 池純規則（185-T1）：名字比對、網址白名單、exclude 挑選。"""
import pytest

from core.scrapers.actress.graphis_pool import (
    candidate_id, is_collectible_url, match_entries, parse_exclude, select_next,
)

_B = "https://data.graphis.ne.jp/free/model/"


@pytest.mark.parametrize("pairs,names,expected", [
    ([("a_miru", "miru"), ("b_emi", "桃瀬えみる")], {"miru"}, ["a_miru"]),
    ([("b_emi", "桃瀬えみる")], {"えみる"}, []),
    ([("a_miru", "miru"), ("a_miru", "坂道みる"), ("c", "x")], {"miru", "坂道みる"}, ["a_miru"]),
    ([("a_miru", "miru")], set(), []),
])
def test_match_entries_exact_name_only(pairs, names, expected):
    assert match_entries(pairs, names) == expected


def test_exclude_pipeline():
    pool = [f"{_B}e/photo/{i:03d}/pic.jpg" for i in range(1, 7)]
    ids = [candidate_id(u) for u in pool]
    assert len(set(ids)) == 6 and len(ids[0]) == 8
    exclude = set()
    for _ in range(3):
        got = select_next(pool, exclude, 2)
        assert len(got) == 2 and not {candidate_id(u) for u in got} & exclude
        exclude |= {candidate_id(u) for u in got}
    assert exclude == set(ids)
    assert select_next(pool, set(ids[:2]), 3) == pool[2:5]
    assert select_next(pool, set(ids), 3) == []
    assert parse_exclude(f"{ids[0]},zzz,'; drop,aaaaaaaa") == {ids[0], "aaaaaaaa"}
    assert parse_exclude(None) == set() and parse_exclude("") == set()
    toks = [f"{i:08x}" for i in range(501)]
    got = parse_exclude(",".join(["zz"] + toks[:2] + ["bad"] + toks[2:]))
    assert got == set(toks[:500])


@pytest.mark.parametrize("url,ok", [
    (f"{_B}E1/prof.jpg", True),
    (f"{_B}E1/model.jpg", True),
    (f"{_B}E1/photo/001/pic.jpg", True),
    (f"{_B}E1/video/01/movs.jpg", False),
    ("https://file.graphis.ne.jp/free/model/E1/sample/img/01.jpg", False),
    (f"{_B}E1/photo/001/thumb/s001.jpg", False),
    (f"{_B}E2/photo/001/pic.jpg", False),
])
def test_is_collectible_url_whitelist(url, ok):
    assert is_collectible_url(url, "E1") is ok
