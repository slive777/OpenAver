"""core.recent_rules — 「最近常收」分數的 DB-free 純函式（spec-184，CD-184-1／-2）。

頂層不得 import 資料庫或爬蟲層模組（BE-PY-08）。
"""
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import NamedTuple

HALF_LIFE_DAYS = 120
SCORE_FLOOR = 0.125
TOP_N = 10
WINDOW_DAYS = 90
MAX_CO_ACTORS = 4
MAX_PAGES = 10
RECENT_ACTRESSES_KEY = "__recent_actresses__"
FUTURE_TOLERANCE_SECONDS = 86400
_SECONDS_PER_DAY = 86400.0


class FavStat(NamedTuple):
    """單一收藏女優的聚合結果：video_count 為去重片數，score 已套 effective_score。"""
    name: str
    video_count: int
    score: float


def _usable_mtime(mtime) -> bool:
    if isinstance(mtime, bool) or not isinstance(mtime, (int, float)):
        return False
    return math.isfinite(mtime) and mtime > 0


def video_weight(mtime, now: float) -> float:
    """單片權重：半衰期 HALF_LIFE_DAYS 天。異常 mtime 回 0.0（片數仍由呼叫端計入）。"""
    if not _usable_mtime(mtime):
        return 0.0
    if mtime > now + FUTURE_TOLERANCE_SECONDS:
        return 0.0
    age_days = max(0.0, (now - mtime) / _SECONDS_PER_DAY)
    return 0.5 ** (age_days / HALF_LIFE_DAYS)


def effective_score(raw: float) -> float:
    """門檻：小而舊的片庫（<= SCORE_FLOOR）歸 0.0。"""
    return 0.0 if raw <= SCORE_FLOOR else raw


# ---------------------------------------------------------------- 「常收女優」新片範圍（CD-184-6／-9）
@dataclass(frozen=True)
class RecentRow:
    """列表一列的我方形狀：when 為 None＝發行日缺／無法解析；upcoming＝預購或發行日在未來。"""
    content_id: str
    when: datetime | None
    upcoming: bool
    actress_count: int


def rank_recent(stats, n: int = TOP_N) -> list[FavStat]:
    """前 n 名：只收 score > 0；分數降冪、作品數降冪、名字升冪（決定性）。"""
    eligible = [s for s in stats if s.score > 0]
    return sorted(eligible, key=lambda s: (-s.score, -s.video_count, s.name))[:n]


def _in_range(row: RecentRow, now: datetime) -> bool:
    """預購，或發行日不早於 now 往前 WINDOW_DAYS 天。"""
    return row.upcoming or (row.when is not None and row.when >= now - timedelta(days=WINDOW_DAYS))


def select_recent(rows, now: datetime, seen: set) -> tuple[list[RecentRow], bool]:
    """逐列過濾 → (kept, reached_cutoff)。seen 跨頁共用，收下的 id 會加進去。
    reached_cutoff＝本頁沒有任何一列在範圍內（只看日期／預購，不看人數或重複）。"""
    rows = list(rows)
    kept: list[RecentRow] = []
    for row in rows:
        if row.content_id in seen or row.actress_count > MAX_CO_ACTORS or not _in_range(row, now):
            continue
        seen.add(row.content_id)
        kept.append(row)
    reached_cutoff = not any(_in_range(r, now) for r in rows)
    return kept, reached_cutoff
