"""「常收女優」的規則與流程（TASK-184-T3a）。輸入全是我方 RecentRow／FavStat／stub provider；不造站方回應。"""
from datetime import datetime, timedelta, timezone

import pytest

from core.recent_actresses import search_recent_actresses
from core.recent_rules import FavStat, RecentRow, rank_recent, select_recent
from core.search_providers.dmm import ActorsPage
from core.search_providers.types import EntityRef, Enriched, Kind, MakerSearchResult, WorkItem

NOW = datetime(2026, 10, 29, tzinfo=timezone(timedelta(hours=9)))
DAY = timedelta(days=1)


def R(cid, days_ago=1, actors=1, upcoming=False, when="auto"):
    w = NOW - days_ago * DAY if when == "auto" else when
    return RecentRow(cid, w, upcoming, actors)


@pytest.mark.parametrize("rows, seen, kept_ids, cutoff", [
    # 預購保留（遠未來、when=None 但 upcoming）；舊片剔除
    ([R("a", -200, upcoming=True), R("b", when=None, upcoming=True), R("c", 200)], set(), ["a", "b"], False),
    # 恰跨 90 天邊界：差 1 天剔除、剛好 90 天保留；整頁皆舊 ⇒ True
    ([R("a", 91), R("b", 90)], set(), ["b"], False),
    ([R("a", 91), R("b", 400), R("c", when=None)], set(), [], True),
    # 交錯 09-15 → 09-03 → 10-02：舊片後面還有新片 ⇒ False
    ([R("a", 44), R("b", 56), R("c", 27)], set(), ["a", "b", "c"], False),
    ([R("old", 200), R("new", 27)], set(), ["new"], False),
    # 人數 5 排除、4 與 1 保留；整頁只有 5 人合輯仍算在範圍內（False）
    ([R("a", actors=5), R("b", actors=4), R("c", actors=1)], set(), ["b", "c"], False),
    ([R("a", actors=5)], set(), [], False),
    # 同頁重複與跨頁（seen 已有）只一次
    ([R("a"), R("a"), R("b")], {"b"}, ["a"], False),
    ([], set(), [], True),
])
def test_select_recent_rules(rows, seen, kept_ids, cutoff):
    """〔新片清單混進多人合輯、漏掉單人／預購，或翻頁在還有新片時提早停：畫面看起來都合理〕"""
    shared = set(seen)
    kept, reached = select_recent(rows, NOW, shared)
    assert [r.content_id for r in kept] == kept_ids
    assert reached is cutoff
    assert shared >= set(kept_ids)
    again, _ = select_recent(rows, NOW, shared)  # 同一個 seen 再來一頁：已收的不重複
    assert again == []


class StubProvider:
    def __init__(self, known, pages=(), boom_on_page=None, resolve_boom=False):
        self.known, self.pages, self.boom_on_page, self.resolve_boom = known, list(pages), boom_on_page, resolve_boom
        self.asked, self.calls = [], []

    def resolve(self, kind, name):
        self.asked.append(name)
        if self.resolve_boom:
            raise RuntimeError("down")
        return EntityRef(Kind.ACTOR, name + "-id", name) if name in self.known else None

    def list_actors_page(self, refs, w, now, seen):
        self.calls.append(([r.label for r in refs], w.offset))
        if self.boom_on_page == len(self.calls):
            raise RuntimeError("down")
        return self.pages[len(self.calls) - 1]

    def enrich(self, item, ref=None):
        return Enriched({"number": item.number}, None)


def _page(numbers, raw=None, has_next=False, cutoff=True):
    items = [WorkItem(n, "t", "", "", None, "dmm") for n in numbers]
    return ActorsPage(items, len(items) if raw is None else raw, has_next, cutoff)


def _run(provider, stats):
    got = []
    out = search_recent_actresses(now=NOW, provider=provider, stats=stats,
                                  result_callback=lambda *a: got.append(a))
    return out, got


STATS = {f"a{i:02d}": FavStat(f"a{i:02d}", 3, 20.0 - i) for i in range(12)}


def test_search_recent_error_codes():
    """〔被擋地區使用者看到「查無結果」以為功能壞了；連不上與沒新片被混成同一句〕三種輸入互不相同"""
    # region：一個 ref 都解析不到
    out, got = _run(StubProvider(known=set()), STATS)
    assert out == MakerSearchResult([], False, "recent_region_empty") and got == []
    # region：解析得到但第一頁 raw_count=0
    out, got = _run(StubProvider(set(STATS), [_page([], raw=0)]), STATS)
    assert out == MakerSearchResult([], False, "recent_region_empty") and got == []
    # none：有列但全被過濾
    out, got = _run(StubProvider(set(STATS), [_page([], raw=7)]), STATS)
    assert out == MakerSearchResult([], False, "recent_none") and got == []
    # unreachable：第 2 頁拋例外 ⇒ 零 seed、零部分結果；resolve 拋例外同
    p = StubProvider(set(STATS), [_page(["A-1"], has_next=True, cutoff=False), _page(["B-1"])], boom_on_page=2)
    out, got = _run(p, STATS)
    assert out == MakerSearchResult([], False, "maker_unreachable") and got == []
    out, got = _run(StubProvider(set(STATS), resolve_boom=True), STATS)
    assert out == MakerSearchResult([], False, "maker_unreachable") and got == []
    # 正向：兩頁都收，翻頁 offset 逐頁 +100，最後一頁停
    p = StubProvider(set(STATS), [_page(["A-1"], has_next=True, cutoff=False), _page(["B-1"])])
    out, got = _run(p, STATS)
    assert [c["number"] for c in out.results] == ["A-1", "B-1"] and out.error_code is None
    assert [off for _, off in p.calls] == [0, 100]


def test_rank_recent_top_n():
    """〔名單選錯人：分數歸零者入選、超過 10 位、或排序不跟分數／作品數走〕"""
    stats = [FavStat(f"n{i:02d}", 5, 1.0 + i) for i in range(11)]
    stats += [FavStat("zero", 99, 0.0), FavStat("tieB", 3, 0.5), FavStat("tieA", 9, 0.5)]
    top = rank_recent(stats)
    assert len(top) == 10 and top[0].name == "n10"
    assert "zero" not in [s.name for s in rank_recent(stats, 99)]
    low = rank_recent([FavStat("tieB", 3, 0.5), FavStat("tieA", 9, 0.5), FavStat("tieC", 9, 0.5)])
    assert [s.name for s in low] == ["tieA", "tieC", "tieB"]
    other = rank_recent([FavStat("x", 1, 2.0)])
    assert [s.name for s in other] == ["x"]  # 換輸入名單跟著變
    # 前 10 名中兩位 resolve 不到：只用其餘 8 位，不補位到第 11 名
    known = set(STATS) - {"a01", "a05"}
    p = StubProvider(known, [_page(["A-1"])])
    out, _ = _run(p, STATS)
    assert p.asked == [f"a{i:02d}" for i in range(10)]
    assert p.calls[0][0] == [f"a{i:02d}" for i in (0, 2, 3, 4, 6, 7, 8, 9)]
    assert out.error_code is None
