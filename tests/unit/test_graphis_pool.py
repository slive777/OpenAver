"""Graphis 池純規則（185-T1）：名字比對、網址白名單、exclude 挑選。"""
import random
import threading
import time

import pytest

from core.scrapers.actress import graphis_pool
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


@pytest.fixture(autouse=True)
def _clean_caches():
    graphis_pool._SEARCH_CACHE.clear()
    graphis_pool._ENTRY_CACHE.clear()
    yield
    graphis_pool._SEARCH_CACHE.clear()
    graphis_pool._ENTRY_CACHE.clear()


def _drain(query, size_source=None):
    """連續換照片直到回 []，回傳全部候選（即整個池）。"""
    seen, got = set(), []
    while True:
        nxt = graphis_pool.graphis_candidates("miru", query, size_source, seen, rng=random.Random(0))
        if not nxt:
            return got
        got += nxt
        seen |= {candidate_id(u) for u in nxt}


def test_pool_assembly_merge_and_shrink(monkeypatch):
    searches = {
        "miru": [("a", "miru"), ("c", "坂道みる")],
        "坂道みる": [("c", "坂道みる"), ("d", "坂道みる")],
    }
    calls = []
    names = {"v": {"miru", "坂道みる"}}

    def fake_search(q, timeout):
        calls.append(q)
        return searches[q]

    monkeypatch.setattr(graphis_pool, "_search_entries", fake_search)
    monkeypatch.setattr(graphis_pool, "_fetch_entry_photos", lambda e, t: [f"{_B}{e}/prof.jpg", f"{_B}{e}/photo/001/pic.jpg"])
    monkeypatch.setattr(graphis_pool, "_names_for", lambda pk, q: names["v"])

    assert _drain("miru")  # 先查主名，快取 miru
    pool = _drain("坂道みる")  # 再查別名：miru 走快取併池
    assert calls == ["miru", "坂道みる"]
    assert len(pool) == len(set(pool)) == 9  # a/c/d 各 3 張，c 被兩次搜尋命中只算一份
    assert {u[len(_B):].split("/")[0] for u in pool} == {"a", "c", "d"}

    names["v"] = {"miru"}  # 別名被移除：舊名條目退出
    pool = _drain("miru")
    assert pool and all(f"/{e}/" not in u for u in pool for e in ("c", "d"))
    assert len(pool) == len(set(pool)) == 3


def test_deadline_budget(monkeypatch):
    monkeypatch.setattr(graphis_pool, "_search_entries", lambda q, t: [("a", "miru"), ("b", "miru")])
    monkeypatch.setattr(graphis_pool, "_names_for", lambda pk, q: {"miru"})
    monkeypatch.setattr(graphis_pool, "_local_photo_size", lambda pk: 123)
    heads = []

    def slow_head(url, timeout):
        heads.append(url)
        time.sleep(1.0)

    monkeypatch.setattr(graphis_pool, "_head_content_length", slow_head)
    base = threading.active_count()
    for fetch_s in (1.5, 0.2):  # 條目頁耗盡預算；條目頁用掉大部分預算、HEAD 開始但超時
        graphis_pool._SEARCH_CACHE.clear()
        graphis_pool._ENTRY_CACHE.clear()
        heads.clear()
        monkeypatch.setattr(graphis_pool, "_fetch_entry_photos",
                            lambda e, t, s=fetch_s: (time.sleep(s), [f"{_B}{e}/photo/001/pic.jpg"])[1])
        t0 = time.time()
        got = graphis_pool.graphis_candidates("miru", "miru", "graphis", set(), budget_s=0.3)
        assert time.time() - t0 < 0.8
        assert got and all(u.endswith(("/prof.jpg", "/model.jpg")) or "/photo/" in u for u in got)
        assert any(u.endswith("/prof.jpg") for u in got)
        if fetch_s > 0.3:
            assert heads == []  # 預算耗盡：跳過 HEAD
        for _ in range(60):  # 等背景條目頁跑完填快取
            if graphis_pool._cache_get(graphis_pool._ENTRY_CACHE, "a") is not None:
                break
            time.sleep(0.05)
        assert graphis_pool._cache_get(graphis_pool._ENTRY_CACHE, "a")
    for _ in range(100):  # 等睡眠中的背景執行緒結束，不污染下一條
        if threading.active_count() <= base:
            break
        time.sleep(0.05)
