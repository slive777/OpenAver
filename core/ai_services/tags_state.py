"""AI 標籤的記憶體觀察值與 ``app_meta`` 讀寫（188c-T4a，CD-188c-2／-3）。

只放「最近一次跟模型互動看到什麼」：``unreachable``（目前連不上）、``last_success_at``
（上次成功）、``job``（本輪補完全庫進度）、``notified``（本輪是否已通知過）。全是記憶體、
重啟即歸零；「上次成功」節流寫進 ``app_meta``，真理在 DB。

不 import ``tagging``／``tags_backfill``（``tagging`` 要 import 本模組，避免循環）。
本模組不建立任何背景執行緒，讀函式不打網路、不寫 DB（I-STATUS）。
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from core.ai_services import backfill_state
from core.logger import get_logger

logger = get_logger(__name__)

META_LAST_SUCCESS = "ai.tags.last_success_at"
META_BACKFILL_OPEN = "ai.tags.backfill_open"
_JOB_SET_FIELDS = frozenset({"slow", "waiting", "stop_reason"})

# monkeypatch seam for observe_success throttle tests (same as faces_state)
_monotonic = time.monotonic


def _new_job(kind: Optional[str] = None) -> dict:
    return {
        "kind": kind, "done": 0, "skipped": 0, "slow": False, "waiting": False,
        "stop_reason": None, "outcome": None,
    }


# 共用欄位（unreachable／last_success_at／job／notified／hook_notified／鎖／sink／節流）
# 都在 ``_STATE``（189a-T8）；``hook_notified`` 與補完全庫的 ``notified`` 互不影響。
_STATE = backfill_state.BackfillState(name="tags_state", task_type="ai_tags", new_job=_new_job)


# ── app_meta ─────────────────────────────────────────────────────────────────

def meta_get(key: str) -> Optional[str]:
    """Read one ``app_meta`` value (None if absent)."""
    return backfill_state.meta_get(key)


def meta_set(key: str, value: str) -> None:
    """Upsert one ``app_meta`` value."""
    backfill_state.meta_set(key, value)


def meta_delete(key: str) -> None:
    """Delete one ``app_meta`` value (no-op if absent)."""
    backfill_state.meta_delete(key)


# ── 觀察值 ───────────────────────────────────────────────────────────────────

def observe_success() -> None:
    """模型正常回來（含拒答）：清「連不上」旗標、記上次成功。

    ``app_meta['ai.tags.last_success_at']`` 至多每 60 秒寫一次（第一次立即寫）。
    含同步 sqlite 寫入 → 呼叫端須 ``asyncio.to_thread``。
    """
    now = time.time()
    now_mono = _monotonic()
    persist = False
    with _STATE.lock:
        _STATE.unreachable = False
        _STATE.last_success_at = now
        persist = _STATE.persist_due(now_mono)
    if persist:
        try:
            meta_set(META_LAST_SUCCESS, repr(now))
        except Exception:
            logger.exception("[tags_state] persist last_success_at failed")


def observe_failure(reason: str, detail: Optional[str]) -> None:
    """只動記憶體旗標：``bad_response`` 清旗標（模型有回應）；``unreachable``（非 429）與
    ``model_unsupported`` 設旗標；其餘（含 429）不動。"""
    with _STATE.lock:
        if reason == "bad_response":
            _STATE.unreachable = False
        elif reason == "model_unsupported" or (reason == "unreachable" and detail != "rate_limited"):
            _STATE.unreachable = True


# ── 通知（T4b 使用；sink 由 web 註冊，core 不 import web，BE-LINT-09）───────────

def set_notification_sink(fn: Callable[..., None]) -> None:
    _STATE.set_sink(fn)


def note_failure() -> bool:
    """每個 job 第一次回 True（``job_begin`` 重置）。"""
    return _STATE.note_failure()


def note_hook_failure() -> bool:
    """入庫後掛勾每輪第一次回 True（``new_round`` 重置）；不碰補完全庫的 ``notified``。"""
    return _STATE.note_hook_failure()


def new_round() -> None:
    """新一輪掛勾通知：只清 ``hook_notified``（189a）。"""
    _STATE.new_hook_round()


def emit(key: str) -> None:
    """透過已註冊的 sink 發側欄通知（sink 為 None 時 no-op；sink 例外只記 log）。"""
    _STATE.emit(key)


# ── job 進度 ─────────────────────────────────────────────────────────────────

def job_begin(kind: str) -> None:
    _STATE.job_begin(kind, reset_notified=True)


def job_progress() -> None:
    _STATE.job_progress()


def job_skip() -> None:
    with _STATE.lock:
        _STATE.job["skipped"] += 1


def job_set(**fields) -> None:
    """只准 ``slow``／``waiting``／``stop_reason``，其他鍵 ``ValueError``。"""
    bad = set(fields) - _JOB_SET_FIELDS
    if bad:
        raise ValueError(f"job_set: unsupported fields {sorted(bad)}")
    with _STATE.lock:
        _STATE.job.update(fields)


def job_end(outcome: str) -> None:
    _STATE.job_end(outcome)


def snapshot() -> dict:
    with _STATE.lock:
        return {
            "unreachable": _STATE.unreachable,
            "last_success_at": _STATE.last_success_at,
            "notified": _STATE.notified,
            "job": dict(_STATE.job),
        }
