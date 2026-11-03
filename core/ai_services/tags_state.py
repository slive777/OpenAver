"""AI 標籤的記憶體觀察值與 ``app_meta`` 讀寫（188c-T4a，CD-188c-2／-3）。

只放「最近一次跟模型互動看到什麼」：``unreachable``（目前連不上）、``last_success_at``
（上次成功）、``job``（本輪補完全庫進度）、``notified``（本輪是否已通知過）。全是記憶體、
重啟即歸零；「上次成功」節流寫進 ``app_meta``，真理在 DB。

不 import ``tagging``／``tags_backfill``（``tagging`` 要 import 本模組，避免循環）。
本模組不建立任何背景執行緒，讀函式不打網路、不寫 DB（I-STATUS）。
"""

from __future__ import annotations

import threading
import time
from contextlib import closing
from typing import Callable, Optional

from core.database import connection
from core.logger import get_logger

logger = get_logger(__name__)

META_LAST_SUCCESS = "ai.tags.last_success_at"
META_BACKFILL_OPEN = "ai.tags.backfill_open"
_PERSIST_INTERVAL_S = 60.0
_JOB_SET_FIELDS = frozenset({"slow", "waiting", "stop_reason"})

# monkeypatch seam for observe_success throttle tests (same as faces_state)
_monotonic = time.monotonic

_lock = threading.Lock()


def _new_job(kind: Optional[str] = None) -> dict:
    return {
        "kind": kind, "done": 0, "skipped": 0, "slow": False, "waiting": False,
        "stop_reason": None, "outcome": None,
    }


unreachable: bool = False
last_success_at: Optional[float] = None
job: dict = _new_job()
notified: bool = False

_last_persist_mono: Optional[float] = None
_notification_sink: Optional[Callable[..., None]] = None


# ── app_meta ─────────────────────────────────────────────────────────────────

def meta_get(key: str) -> Optional[str]:
    """Read one ``app_meta`` value (None if absent)."""
    with closing(connection.get_connection()) as conn:
        row = conn.execute("SELECT value FROM app_meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def meta_set(key: str, value: str) -> None:
    """Upsert one ``app_meta`` value."""
    with closing(connection.get_connection()) as conn:
        conn.execute("INSERT OR REPLACE INTO app_meta (key, value) VALUES (?, ?)", (key, value))
        conn.commit()


def meta_delete(key: str) -> None:
    """Delete one ``app_meta`` value (no-op if absent)."""
    with closing(connection.get_connection()) as conn:
        conn.execute("DELETE FROM app_meta WHERE key = ?", (key,))
        conn.commit()


# ── 觀察值 ───────────────────────────────────────────────────────────────────

def observe_success() -> None:
    """模型正常回來（含拒答）：清「連不上」旗標、記上次成功。

    ``app_meta['ai.tags.last_success_at']`` 至多每 60 秒寫一次（第一次立即寫）。
    含同步 sqlite 寫入 → 呼叫端須 ``asyncio.to_thread``。
    """
    global unreachable, last_success_at, _last_persist_mono
    now = time.time()
    now_mono = _monotonic()
    persist = False
    with _lock:
        unreachable = False
        last_success_at = now
        if _last_persist_mono is None or (now_mono - _last_persist_mono) >= _PERSIST_INTERVAL_S:
            _last_persist_mono = now_mono
            persist = True
    if persist:
        try:
            meta_set(META_LAST_SUCCESS, repr(now))
        except Exception:
            logger.exception("[tags_state] persist last_success_at failed")


def observe_failure(reason: str, detail: Optional[str]) -> None:
    """只動記憶體旗標：``bad_response`` 清旗標（模型有回應）；``unreachable``（非 429）與
    ``model_unsupported`` 設旗標；其餘（含 429）不動。"""
    global unreachable
    with _lock:
        if reason == "bad_response":
            unreachable = False
        elif reason == "model_unsupported" or (reason == "unreachable" and detail != "rate_limited"):
            unreachable = True


# ── 通知（T4b 使用；sink 由 web 註冊，core 不 import web，BE-LINT-09）───────────

def set_notification_sink(fn: Callable[..., None]) -> None:
    global _notification_sink
    _notification_sink = fn


def note_failure() -> bool:
    """每個 job 第一次回 True（``job_begin`` 重置）。"""
    global notified
    with _lock:
        if notified:
            return False
        notified = True
        return True


def emit(key: str) -> None:
    """透過已註冊的 sink 發側欄通知（sink 為 None 時 no-op；sink 例外只記 log）。"""
    sink = _notification_sink
    if sink is None:
        return
    try:
        sink("warn", key, task_type="ai_tags")
    except Exception:
        logger.exception("[tags_state] notification sink failed")


# ── job 進度 ─────────────────────────────────────────────────────────────────

def job_begin(kind: str) -> None:
    global job, notified
    with _lock:
        job = _new_job(kind)
        notified = False


def job_progress() -> None:
    with _lock:
        job["done"] += 1


def job_skip() -> None:
    with _lock:
        job["skipped"] += 1


def job_set(**fields) -> None:
    """只准 ``slow``／``waiting``／``stop_reason``，其他鍵 ``ValueError``。"""
    bad = set(fields) - _JOB_SET_FIELDS
    if bad:
        raise ValueError(f"job_set: unsupported fields {sorted(bad)}")
    with _lock:
        job.update(fields)


def job_end(outcome: str) -> None:
    with _lock:
        job["outcome"] = outcome


def snapshot() -> dict:
    with _lock:
        return {
            "unreachable": unreachable,
            "last_success_at": last_success_at,
            "notified": notified,
            "job": dict(job),
        }
