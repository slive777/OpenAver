"""Faces endpoint memory state + notification sink (CD-187a-15).

Module-level: restart clears memory. ``last_success_at`` persistence is throttled
(≤60s) into ``app_meta``; ``job`` tracks the current recompute pass.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from core.ai_services import backfill_state
from core.logger import get_logger

logger = get_logger(__name__)

NOTIFY_KEY = "notif.ai_faces_unreachable"
META_LAST_SUCCESS = "ai.faces.last_success_at"

# monkeypatch seam for observe_success throttle tests (DoD 4)
_monotonic = time.monotonic

# 共用欄位（notified／last_success_at／job／鎖／sink／節流）在 ``_STATE``（189a-T8）；
# ``degraded`` 語意是「任何失敗都設」，與 ``_STATE.unreachable`` 不同，留在模組層。
_STATE = backfill_state.BackfillState(name="faces_state", task_type="ai_faces")

observed_model: Optional[str] = None
degraded: bool = False
last_error_kind: Optional[str] = None
last_error_check: Optional[str] = None


def set_notification_sink(fn: Callable[..., None]) -> None:
    """core cannot import web: web/app.py registers ``emit_notification`` (BE-LINT-09)."""
    _STATE.set_sink(fn)


def meta_get(key: str) -> Optional[str]:
    """Read one ``app_meta`` value (None if absent)."""
    return backfill_state.meta_get(key)


def meta_set(key: str, value: str) -> None:
    """Upsert one ``app_meta`` value."""
    backfill_state.meta_set(key, value)


def observe_success(model: str) -> None:
    """External FOUND/NO_FACE: clear degraded, errors, notified; stamp success time.

    Persist ``ai.faces.last_success_at`` at most once per 60s (first call immediate).
    """
    global observed_model, degraded, last_error_kind, last_error_check
    now = time.time()
    now_mono = _monotonic()
    persist = False
    with _STATE.lock:
        observed_model = model
        degraded = False
        last_error_kind = last_error_check = None
        _STATE.notified = False
        _STATE.last_success_at = now
        persist = _STATE.persist_due(now_mono)
    if persist:
        try:
            meta_set(META_LAST_SUCCESS, repr(now))
        except Exception:
            logger.exception("[faces_state] persist last_success_at failed")


def observe_failure(kind: Optional[str], check: Optional[str]) -> None:
    """Any endpoint failure: mark degraded and record kind/check."""
    global degraded, last_error_kind, last_error_check
    with _STATE.lock:
        degraded = True
        last_error_kind, last_error_check = kind, check


def note_failure() -> bool:
    """Return True once per round (first background failure that should notify)."""
    return _STATE.note_failure()


def new_round() -> None:
    """Scan-round reset: only clears the notification dedupe flag."""
    _STATE.reset_notified()


def emit_unreachable() -> None:
    """Fire the sidebar notice via the registered sink (no-op if unset)."""
    _STATE.emit(NOTIFY_KEY)


def job_begin(kind: str) -> None:
    _STATE.job_begin(kind)


def job_progress() -> None:
    _STATE.job_progress()


def job_end(outcome: str) -> None:
    _STATE.job_end(outcome)


def snapshot() -> dict:
    with _STATE.lock:
        return {
            "observed_model": observed_model,
            "degraded": degraded,
            "kind": last_error_kind,
            "check": last_error_check,
            "notified": _STATE.notified,
            "last_success_at": _STATE.last_success_at,
            "job": dict(_STATE.job),
        }
