"""Faces endpoint memory state + notification sink (CD-187a-15).

Module-level: restart clears memory. ``last_success_at`` persistence is throttled
(≤60s) into ``app_meta``; ``job`` tracks the current recompute pass.
"""

from __future__ import annotations

import threading
import time
from contextlib import closing
from typing import Callable, Optional

from core.database import connection
from core.logger import get_logger

logger = get_logger(__name__)

NOTIFY_KEY = "notif.ai_faces_unreachable"
META_LAST_SUCCESS = "ai.faces.last_success_at"
_PERSIST_INTERVAL_S = 60.0

# monkeypatch seam for observe_success throttle tests (DoD 4)
_monotonic = time.monotonic

_lock = threading.Lock()

observed_model: Optional[str] = None
degraded: bool = False
last_error_kind: Optional[str] = None
last_error_check: Optional[str] = None
notified: bool = False
last_success_at: Optional[float] = None
job: dict = {"kind": None, "done": 0, "outcome": None}

_last_persist_mono: Optional[float] = None
_notification_sink: Optional[Callable[..., None]] = None


def set_notification_sink(fn: Callable[..., None]) -> None:
    """core cannot import web: web/app.py registers ``emit_notification`` (BE-LINT-09)."""
    global _notification_sink
    _notification_sink = fn


def meta_get(key: str) -> Optional[str]:
    """Read one ``app_meta`` value (None if absent)."""
    with closing(connection.get_connection()) as conn:
        row = conn.execute(
            "SELECT value FROM app_meta WHERE key = ?", (key,)
        ).fetchone()
    return row[0] if row else None


def meta_set(key: str, value: str) -> None:
    """Upsert one ``app_meta`` value."""
    with closing(connection.get_connection()) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO app_meta (key, value) VALUES (?, ?)",
            (key, value),
        )
        conn.commit()


def observe_success(model: str) -> None:
    """External FOUND/NO_FACE: clear degraded, errors, notified; stamp success time.

    Persist ``ai.faces.last_success_at`` at most once per 60s (first call immediate).
    """
    global observed_model, degraded, last_error_kind, last_error_check, notified
    global last_success_at, _last_persist_mono
    now = time.time()
    now_mono = _monotonic()
    persist = False
    with _lock:
        observed_model = model
        degraded = False
        last_error_kind = last_error_check = None
        notified = False
        last_success_at = now
        if _last_persist_mono is None or (now_mono - _last_persist_mono) >= _PERSIST_INTERVAL_S:
            _last_persist_mono = now_mono
            persist = True
    if persist:
        try:
            meta_set(META_LAST_SUCCESS, repr(now))
        except Exception:
            logger.exception("[faces_state] persist last_success_at failed")


def observe_failure(kind: Optional[str], check: Optional[str]) -> None:
    """Any endpoint failure: mark degraded and record kind/check."""
    global degraded, last_error_kind, last_error_check
    with _lock:
        degraded = True
        last_error_kind, last_error_check = kind, check


def note_failure() -> bool:
    """Return True once per round (first background failure that should notify)."""
    global notified
    with _lock:
        if notified:
            return False
        notified = True
        return True


def new_round() -> None:
    """Scan-round reset: only clears the notification dedupe flag."""
    global notified
    with _lock:
        notified = False


def emit_unreachable() -> None:
    """Fire the sidebar notice via the registered sink (no-op if unset)."""
    sink = _notification_sink
    if sink is None:
        return
    try:
        sink("warn", NOTIFY_KEY, task_type="ai_faces")
    except Exception:
        logger.exception("[faces_state] notification sink failed")


def job_begin(kind: str) -> None:
    global job
    with _lock:
        job = {"kind": kind, "done": 0, "outcome": None}


def job_progress() -> None:
    with _lock:
        job["done"] += 1


def job_end(outcome: str) -> None:
    with _lock:
        job["outcome"] = outcome


def snapshot() -> dict:
    with _lock:
        return {
            "observed_model": observed_model,
            "degraded": degraded,
            "kind": last_error_kind,
            "check": last_error_check,
            "notified": notified,
            "last_success_at": last_success_at,
            "job": dict(job),
        }
