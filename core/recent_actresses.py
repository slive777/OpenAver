"""core.recent_actresses — 「常收女優」新片流程（spec-184 §4.2–§4.5，CD-184-8／-9／-10）。

收藏女優依「最近常收」分數取前 TOP_N → 各自 resolve 成 DMM 女優 → 一次 OR 查詢逐頁列出
「近 90 天＋預購、女優 ≤4 人」的片 → 全部列完才補詳情並串流。只走 DMM，不接力（不呼叫 relay）。
錯誤碼三種互斥：連不上 ⇒ maker_unreachable；沒解析到人或第一頁就空 ⇒ recent_region_empty；
有列但全被過濾 ⇒ recent_none。絕不回 maker_not_found。
頂層不得 import core.database／core.scraper（BE-PY-08）。
"""

from __future__ import annotations

from datetime import datetime, timezone

from core.logger import get_logger
from core.recent_rules import MAX_PAGES, TOP_N, rank_recent
from core.search_providers.pipeline import run_window
from core.search_providers.types import Kind, MakerSearchResult, Window

logger = get_logger(__name__)

PAGE_LIMIT = 100


def _fail(code: str) -> MakerSearchResult:
    return MakerSearchResult([], False, code)


def _default_provider():
    """預設路徑：設定頁關掉 DMM ⇒ None（呼叫端回 maker_unreachable）。"""
    from core import scraper
    from core.search_providers import registry

    if not scraper.is_source_enabled("dmm"):
        return None
    return registry.new_provider("dmm")


def _default_stats() -> dict:
    from core.database.actress_library import get_favorite_actress_stats

    return get_favorite_actress_stats()


def _resolve_refs(provider, stats) -> list:
    """前 TOP_N 名用收藏名 resolve；回 None 的略過、不補位。例外原樣往外丟。"""
    values = stats.values() if isinstance(stats, dict) else stats
    refs = (provider.resolve(Kind.ACTOR, s.name) for s in rank_recent(values, TOP_N))
    return [ref for ref in refs if ref is not None]


def _list_all(provider, refs, now):
    """逐頁列出；回 (items, first_page_empty)。停止：整頁都過了切點／沒有下一頁／頁數到 MAX_PAGES。"""
    items, seen, first = [], set(), True
    for page_no in range(MAX_PAGES):
        page = provider.list_actors_page(refs, Window(page_no * PAGE_LIMIT, PAGE_LIMIT), now, seen)
        if first and page.raw_count == 0:
            return [], True
        first = False
        items.extend(page.items)
        if page.reached_cutoff or not page.has_next:
            return items, False
    logger.warning("recent actresses: stopped at MAX_PAGES=%d", MAX_PAGES)
    return items, False


def _stream(provider, items, result_callback) -> list[dict]:
    res = run_window(provider, items, None, result_callback=result_callback,
                     on_fail="degrade", delay=0, breaker=False, guard=False)
    for card in res.cards:
        card["_source"] = "dmm"
    return res.cards


def search_recent_actresses(*, now=None, status_callback=None, result_callback=None,
                            provider=None, stats=None) -> MakerSearchResult:
    """前 TOP_N 名常收女優的近期新片。provider／stats 注入時不讀設定頁開關與資料庫。"""
    if now is None:
        now = datetime.now(timezone.utc)
    if provider is None:
        provider = _default_provider()
        if provider is None:
            return _fail("maker_unreachable")
    if status_callback:
        status_callback("dmm", "searching")
    try:
        refs = _resolve_refs(provider, _default_stats() if stats is None else stats)
        if not refs:
            return _fail("recent_region_empty")
        items, first_empty = _list_all(provider, refs, now)
    except Exception as err:
        logger.warning("recent actresses failed (%s)", type(err).__name__)
        return _fail("maker_unreachable")
    if first_empty:
        return _fail("recent_region_empty")
    if not items:
        return _fail("recent_none")
    cards = _stream(provider, items, result_callback)
    if status_callback:
        status_callback("done", f"found:{len(cards)}")
    return MakerSearchResult(cards, False, None)
