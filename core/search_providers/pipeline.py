"""視窗換算與進度式補詳情（CD-175a-1、CD-175a-4；plan-175b CD-175b-2 的 I-A1～A5）。

- fetch_window：page-based provider 共用的「offset/limit → 頁」換算。
- verify_page：守衛。視窗前 GUARD_SIZE 部的詳情先抓，至少一部 belongs is True 才算這頁屬於該實體。
- run_window：seed → 逐部補詳情（slot 預配置、單部失敗降級、連續被擋斷路器）。

不變式（只寫不變式，驗證手段是 tests/unit/test_search_pipeline.py）：
  I-S1 一次呼叫最多一個 seed；I-S2 seed 只在視窗非空且守衛（若啟用）通過後才送；
  I-S4 守衛不通過 ⇒ 不送 seed、不送任何 result-item；
  I-A1 並行 ≤ MAX_WORKERS、每部做完至少 sleep(delay)；
  I-A2 單部失敗只降級那一張、不重試；I-A3 連續 BREAKER_THRESHOLD 次 SourceBlocked 後不再發起新請求；
  I-A5 守衛階段全例外 ⇒ UNREACHABLE。
本模組不補 `_source`、不送 status 事件（屬 provider／relay）。
"""

from __future__ import annotations

import concurrent.futures as cf
import queue
import re
import time
from collections import deque
from dataclasses import dataclass, replace
from typing import NamedTuple

from core import search_cancel
from core.logger import get_logger
from core.scrapers.errors import SourceBlocked
from core.search_providers.types import Enriched, Outcome, Page, Window, WindowResult, WorkItem

logger = get_logger(__name__)

BREAKER_THRESHOLD = 3
GUARD_SIZE = 3
_ON_FAIL_POLICIES = ("degrade", "drop")


# ---------------------------------------------------------------- 視窗換算
def fetch_window(page_size, fetch_page, w: Window, *, max_page=None) -> Page:
    """把 (offset, limit) 換成頁序列取回，回傳切好的 Page。

    fetch_page(page_no) -> Page（page_no 從 1 起）。空頁／has_next=False／超過 max_page 即停；
    超過 max_page 的頁不呼叫 fetch_page。頁數上界保留今天 JavBus 的 ((limit+skip)//page_size)+2。
    """
    first_page = w.offset // page_size + 1
    skip = w.offset % page_size
    need = skip + w.limit
    last_page = first_page + (need // page_size) + 1  # 含；range 上界 = +2 頁
    items: list[WorkItem] = []
    has_next = False
    total = None
    for page in range(first_page, last_page + 1):
        if max_page is not None and page > max_page:
            has_next = False
            break
        got = fetch_page(page)
        if not got.items:
            has_next = False
            break
        items.extend(got.items)
        has_next = got.has_next
        if got.total is not None:
            total = got.total
        if len(items) >= need or not got.has_next:
            break
    window_items = items[skip : skip + w.limit]
    return Page(window_items, has_next or len(items) > skip + w.limit, total)


# ---------------------------------------------------------------- 單部補詳情
def _resolve_delay(delay):
    if delay is not None:
        return delay
    from core.scraper import REQUEST_DELAY

    return REQUEST_DELAY


def _enrich_one(provider, item: WorkItem, ref, delay):
    """回 (Enriched, None) 或 (None, 例外)。except Exception 的寬度是契約（BE-TEST-33）；
    BaseException（如 OutboundConnectionViolation）不得被吞。"""
    try:
        enriched = provider.enrich(item, item.origin or ref)
        if enriched is None or not enriched.card:
            raise ValueError(f"empty card: {item.number}")
        return enriched, None
    except Exception as item_exc:
        logger.warning("enrich failed: %s (%s)", item.number, type(item_exc).__name__)
        return None, item_exc
    finally:
        time.sleep(delay)


def _degraded_card(item: WorkItem) -> dict:
    return {
        "number": item.number,
        "title": item.title,
        "actors": [],
        "date": item.date,
        "cover": item.cover_url,
        "source": item.source,
    }


def _run_jobs(provider, jobs, ref, delay, on_done):
    """jobs: [(slot, item)]。同時在途 ≤ MAX_WORKERS；on_done(slot, item, enriched, exc) 回 False
    ＝不再發起新請求（已在途的仍等它完成）。回傳從未發起的 jobs。"""
    from core.scraper import MAX_WORKERS

    pending = deque(jobs)
    inflight = 0
    done_q: queue.Queue = queue.Queue()  # 依真實完成順序入列（add_done_callback），不靠集合順序
    keep_going = True
    with cf.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        while True:
            while keep_going and pending and inflight < MAX_WORKERS:
                slot, item = pending.popleft()
                fut = search_cancel.submit(pool, _enrich_one, provider, item, ref, delay)
                fut.add_done_callback(lambda f, s=slot, i=item: done_q.put((s, i, f)))
                inflight += 1
            if not inflight:
                break
            slot, item, fut = done_q.get()
            inflight -= 1
            enriched, exc = fut.result()
            if on_done(slot, item, enriched, exc) is False:
                keep_going = False
    return list(pending)


# ---------------------------------------------------------------- 守衛
@dataclass
class GuardResult:
    passed: bool
    outcome: Outcome | None  # 通過時為 None
    cards: dict  # slot -> card dict；該部失敗為 None


def verify_page(provider, items, ref, *, delay=None) -> GuardResult:
    """視窗前 GUARD_SIZE 部（不足就用全部）各抓詳情，至少一個 belongs is True 才通過。
    沒有 True 且有任一部例外 ⇒ UNREACHABLE；否則 ⇒ NOT_ANSWERABLE（BE-PY-03）。守衛階段失敗不計入斷路器。"""
    delay = _resolve_delay(delay)
    results: dict = {}

    def collect(slot, item, enriched, exc):
        results[slot] = (enriched, exc)
        return True

    _run_jobs(provider, list(enumerate(items[:GUARD_SIZE])), ref, delay, collect)
    cards = {slot: (enr.card if enr is not None else None) for slot, (enr, _) in sorted(results.items())}
    verdicts = [enr.belongs for enr, _ in results.values() if enr is not None]
    passed = any(v is True for v in verdicts)
    if passed:
        return GuardResult(True, None, cards)
    any_failed = any(exc is not None for _, exc in results.values())
    return GuardResult(False, Outcome.UNREACHABLE if any_failed else Outcome.NOT_ANSWERABLE, cards)


# ---------------------------------------------------------------- run_window
class _Collector:
    """slot 預配置、依 on_fail 處理失敗、通知 result_callback、數連續 SourceBlocked。"""

    def __init__(self, items, result_callback, on_fail, breaker, on_item_done=None):
        self.items = items
        self.on_item_done = on_item_done
        self.slots: list = [None] * len(items)
        self.callback = result_callback
        self.on_fail = on_fail
        self.breaker = breaker
        self.blocked_streak = 0

    def put(self, slot, card):
        self.slots[slot] = card
        if self.callback:
            self.callback(slot, card)

    def put_ok(self, slot, card):
        self._notify(slot, True)
        self.put(slot, card)

    def put_failed(self, slot):
        self._notify(slot, False)
        if self.on_fail == "degrade":
            self.put(slot, _degraded_card(self.items[slot]))

    def _notify(self, slot, ok):
        if self.on_item_done is not None:
            self.on_item_done(slot, ok)

    def on_done(self, slot, item, enriched: Enriched | None, exc):
        if exc is None:
            self.blocked_streak = 0
            self.put_ok(slot, enriched.card)
            return True
        self.put_failed(slot)
        self.blocked_streak = self.blocked_streak + 1 if isinstance(exc, SourceBlocked) else 0
        return not (self.breaker and self.blocked_streak >= BREAKER_THRESHOLD)

    def cards(self):
        return [c for c in self.slots if c is not None]


def run_window(
    provider,
    items,
    ref=None,
    *,
    result_callback=None,
    on_fail="degrade",
    delay=None,
    guard=False,
    breaker=True,
    on_item_done=None,
) -> WindowResult:
    """對一個已切好的視窗（list[WorkItem]）送 seed、逐部補詳情，回 WindowResult。

    on_fail：'degrade'（失敗的那張用列表資料出降級卡）／'drop'（失敗的不出卡）。
    delay：None＝REQUEST_DELAY；T4／T5 傳 0（與今天相同），JavDB 不得傳比 REQUEST_DELAY 小的值。
    guard：需 ref；啟用則先 verify_page，不通過就不 seed。breaker：連續被擋斷路。並行度固定 MAX_WORKERS。
    on_item_done(slot, ok)：視窗內每一部各呼叫一次（成功 True；失敗／被丟棄／斷路後未發起 False），
    在呼叫端執行緒、先於該部的 result-item callback；守衛不通過則完全不呼叫。掛鉤內不得 sleep。
    """
    if on_fail not in _ON_FAIL_POLICIES:
        raise ValueError(f"on_fail must be one of {_ON_FAIL_POLICIES}")
    if guard and ref is None:
        raise ValueError("guard requires ref")
    if not items:
        return WindowResult(Outcome.NOT_ANSWERABLE, [], seeded=False)
    delay = _resolve_delay(delay)
    col = _Collector(items, result_callback, on_fail, breaker, on_item_done)
    verdict = verify_page(provider, items, ref, delay=delay) if guard else None
    if verdict is not None and verdict.outcome is Outcome.UNREACHABLE:
        return WindowResult(Outcome.UNREACHABLE, [], seeded=False)
    if verdict is not None and verdict.outcome is Outcome.NOT_ANSWERABLE:
        return WindowResult(Outcome.NOT_ANSWERABLE, [], seeded=False)
    seeded = result_callback is not None
    if seeded:
        result_callback(-1, [i.number for i in items])
    jobs = list(enumerate(items))
    if verdict is not None:
        _emit_guard_cards(col, verdict)
        jobs = jobs[len(verdict.cards) :]
    for slot, _ in _run_jobs(provider, jobs, ref, delay, col.on_done):
        col.put_failed(slot)
    cards = col.cards()
    return WindowResult(Outcome.ANSWERED if cards else Outcome.NOT_ANSWERABLE, cards, seeded=seeded)


def _emit_guard_cards(col: _Collector, verdict: GuardResult) -> None:
    for slot in sorted(verdict.cards):
        card = verdict.cards[slot]
        if card:
            col.put_ok(slot, card)
        else:
            col.put_failed(slot)


# ---------------------------------------------------------------- 多 ref 歸併（CD-175d-4）
DEFAULT_LIST_CHUNK = 30
_DATE_RE = re.compile(r"(\d{4})\D+(\d{1,2})(?:\D+(\d{1,2}))?")


class MergeResult(NamedTuple):
    items: list[WorkItem]  # 每部以 replace 副本設 origin；單頁內 number.upper() 不重複
    new_positions: list[int]  # 與 refs 等長：該 ref 累計消耗位置，或 -1（耗盡，之後不再呼叫）
    exhausted: bool  # 全部 -1


def _date_rank(date: str) -> int:
    """日期轉可比大小的整數（'/' 與 '-' 同義）；缺日期／無法解析 ⇒ -1（新→舊排序時殿後）。"""
    m = _DATE_RE.search(date or "")
    if not m:
        return -1
    return int(m.group(1)) * 10000 + int(m.group(2)) * 100 + int(m.group(3) or 0)


class _Lane:
    """一個 ref 的惰性游標：只在已取回的片段用完且未耗盡時才補取下一塊（offset = 起點 + 已取）。"""

    def __init__(self, ref, start: int):
        self.ref = ref
        self.start = start
        self.buf: deque[WorkItem] = deque()
        self.fetched = 0
        self.consumed = 0
        self.done = False  # 站方端已無更多（塊回空，或 has_next=False）

    @property
    def finished(self) -> bool:
        return self.start < 0 or (self.done and not self.buf)

    def head(self, provider, size: int) -> WorkItem | None:
        if not self.buf and not self.done:
            self._fill(provider, size)
        return self.buf[0] if self.buf else None

    def _fill(self, provider, size: int) -> None:
        # 取塊例外原樣往外丟：不吞、不回部分（I-M6）
        page = provider.list_entity(self.ref, Window(self.start + self.fetched, size))
        self.fetched += len(page.items)
        self.buf.extend(page.items)
        if not page.items or not page.has_next:
            self.done = True

    def pop(self) -> WorkItem:
        self.consumed += 1
        return self.buf.popleft()


def merge_windows(provider, refs, positions, limit) -> MergeResult:
    """把 refs 各自的清單做惰性 k 路歸併，累計 limit 個唯一作品即停。

    positions[i]＝該 ref 已消耗位置（第一頁全 0）或 -1（耗盡，不呼叫）。呼叫端保證 len(positions)==len(refs)。
    不變式（驗證手段是 tests/unit/test_search_merge_windows.py）：
      I-M1 單頁內 number.upper() 不重複；I-M2 依 (日期新→舊, ref 序, ref 內序) 單調、缺日期殿後；
      I-M3 逐頁走 new_positions ＝ 一次取到底再依各頁消耗數切段、段內各自去重；
      I-M4 -1 的 ref 不被呼叫；I-M5 每頁每 ref 的 list_entity ≤ ceil(limit/C)+1；
      I-M6 任一 ref 取塊丟例外 ⇒ 整個呼叫丟，不回殘缺清單。
    """
    size = getattr(provider, "list_chunk", DEFAULT_LIST_CHUNK)
    lanes = [_Lane(ref, pos) for ref, pos in zip(refs, positions, strict=True)]
    live = [i for i, pos in enumerate(positions) if pos >= 0]
    items: list[WorkItem] = []
    seen: set[str] = set()
    while len(items) < limit:
        heads = {i: lanes[i].head(provider, size) for i in live}
        live = [i for i in live if heads[i] is not None]
        if not live:
            break
        pick = min(live, key=lambda i: (-_date_rank(heads[i].date), i))
        item = lanes[pick].pop()
        key = item.number.upper()
        if key not in seen:
            seen.add(key)
            items.append(replace(item, origin=refs[pick]))
    new_positions = []
    for i, lane in enumerate(lanes):
        new_positions.append(-1 if lane.finished else positions[i] + lane.consumed)
    return MergeResult(items, new_positions, all(p < 0 for p in new_positions))
