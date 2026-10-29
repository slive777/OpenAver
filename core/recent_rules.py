"""core.recent_rules — 「最近常收」分數的 DB-free 純函式（spec-184，CD-184-1／-2）。

不得頂層 import core.database／core.scraper（BE-PY-08）。
"""
import math
from typing import NamedTuple

HALF_LIFE_DAYS = 120
SCORE_FLOOR = 0.125
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
