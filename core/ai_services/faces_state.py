"""Faces endpoint memory state + notification sink (CD-187a-15).

Module-level: restart clears everything. ``last_success_at`` persistence and
``job`` land in T4; this module only keeps the in-memory half.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from core.logger import get_logger

logger = get_logger(__name__)

NOTIFY_KEY = "notif.ai_faces_unreachable"

_lock = threading.Lock()

observed_model: Optional[str] = None
degraded: bool = False
last_error_kind: Optional[str] = None
last_error_check: Optional[str] = None
notified: bool = False
last_success_at: Optional[float] = None

_notification_sink: Optional[Callable[..., None]] = None


def set_notification_sink(fn: Callable[..., None]) -> None:
    """core cannot import web: web/app.py registers ``emit_notification`` (BE-LINT-09)."""
    global _notification_sink
    _notification_sink = fn


def observe_success(model: str) -> None:
    """External FOUND/NO_FACE: clear degraded, errors, notified; stamp success time."""
    global observed_model, degraded, last_error_kind, last_error_check, notified, last_success_at
    with _lock:
        observed_model = model
        degraded = False
        last_error_kind = last_error_check = None
        notified = False
        last_success_at = time.time()


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


def snapshot() -> dict:
    with _lock:
        return {
            "observed_model": observed_model,
            "degraded": degraded,
            "kind": last_error_kind,
            "check": last_error_check,
            "notified": notified,
            "last_success_at": last_success_at,
        }
