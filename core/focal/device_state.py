"""Device-level focal auto-disable (feature/152c TASK-4).

Two consecutive ABANDONED("detect_timeout") outcomes mark the machine as too
slow for auto-focus. Version mismatch lazy-resets: reads look enabled
immediately; the next write clears streak/disabled before applying the event
(CD-152b-5 / CD-152b-7 / CD-152b-8).

feature/152d TASK-D1 adds ``set_by_user``: when the user owns the value,
auto-disable and version lazy-reset no longer overwrite their decision.
"""

from __future__ import annotations

from typing import Callable, Optional

from core.ai_services.faces_config import active_in
from core.config import load_config, mutate_config
from core.focal import subprocess_runner
from core.focal.subprocess_runner import RunnerOutcome
from core.logger import get_logger
from core.version import VERSION

logger = get_logger(__name__)

_DISABLE_THRESHOLD = 2

# CD-152c-20：依賴反轉的通知埠。core/ 不可 import web/（import-linter 契約），
# 所以 web/app.py 在 module level 呼叫 set_notification_sink(emit_notification)
# 註冊真正的實作；未註冊時是 no-op，純 core 測試與非 web 進入點自然靜音。
_notification_sink: Optional[Callable[..., None]] = None


def set_notification_sink(fn: Callable[..., None]) -> None:
    """Register the callable record_outcome() uses to emit a disable notice."""
    global _notification_sink
    _notification_sink = fn


def local_disabled_in(cfg: dict) -> bool:
    """Local-device disabled rule, answered from a config dict the caller already holds.

    Exists so the disabled-read rule has exactly one implementation. Callers that
    already loaded the config (e.g. a page handler that got it from
    get_common_context) must use this instead of re-deriving the rule.

    Two branches (feature/152d CD-152d-2):
    - ``set_by_user`` is true → return ``disabled`` directly (version-independent;
      the user's decision survives App upgrades).
    - otherwise → ``disabled and judged_at_version == VERSION`` (152c lazy reset:
      a stale ``disabled`` from a previous version reads as enabled).

    ⚠️ The caller owns freshness. Only pass a snapshot taken in the same request /
    call; a long-lived snapshot answers about the past (see BE-CONFIG-05).
    """
    fd = cfg.get("focal_device", {})
    if bool(fd.get("set_by_user", False)):
        return bool(fd.get("disabled", False))
    return bool(fd.get("disabled", False)) and fd.get("judged_at_version", "") == VERSION


def is_disabled_in(cfg: dict) -> bool:
    """External faces active → never disabled; else the local-device rule."""
    if active_in(cfg):
        return False
    return local_disabled_in(cfg)


def is_disabled() -> bool:
    """True when focal is disabled under the is_disabled_in() read rule."""
    return is_disabled_in(load_config())


def local_is_disabled() -> bool:
    """Local-only disabled probe (ignores external faces); for T3b registration."""
    return local_disabled_in(load_config())


def _apply_outcome_core(
    fd: dict,
    outcome: RunnerOutcome,
    *,
    count_timeouts: bool = True,
) -> bool:
    """Shared mutator core for background / (future) manual outcome paths.

    Mutates ``fd`` in place. Returns ``just_disabled`` (False→True crossing only).

    ``count_timeouts=True`` (background ``record_outcome``): increment streak and
    flip ``disabled`` when streak hits ``_DISABLE_THRESHOLD``.
    ``count_timeouts=False`` (T-D2 ``record_manual_outcome``): leave the streak
    alone and flip ``disabled`` on a single ``detect_timeout``.

    When ``set_by_user`` is true: skip the whole lazy-reset block, and suppress
    only the ``disabled=True`` flip — version stamp and (background) count still
    run (CD-152d-2b③ + owner override: one condition, one landing).
    """
    just_disabled = False
    set_by_user = bool(fd.get("set_by_user", False))
    judged_version = fd.get("judged_at_version", "")
    if judged_version != VERSION and not set_by_user:
        fd["disabled"] = False
        fd["consecutive_timeout_count"] = 0

    if outcome.kind in ("FOUND", "NO_FACE"):
        if count_timeouts:
            fd["consecutive_timeout_count"] = 0
    elif outcome.kind == "ABANDONED":
        reason = outcome.reason
        if reason == "detect_timeout":
            if count_timeouts:
                count = int(fd.get("consecutive_timeout_count", 0)) + 1
                fd["consecutive_timeout_count"] = count
                should_disable = count >= _DISABLE_THRESHOLD
            else:
                # T-D2 path: one timeout is enough, and the streak counter is not touched.
                should_disable = True
            # 一個條件、一個落點：`set_by_user` 的抑制只寫在這裡。兩條路徑（背景連兩次 /
            # 前景一次）差的只是 should_disable 怎麼算出來，翻旗標這件事不可以有第二份拷貝
            # ——Codex 第一輪那條 P3 就是同一種漂移（`count_timeouts` 守住了一半忘了另一半）。
            if should_disable and not set_by_user:
                was_disabled = bool(fd.get("disabled", False))
                fd["disabled"] = True
                just_disabled = not was_disabled
        # startup_timeout / crashed / skipped_disabled / circuit_open: no-op

    fd["judged_at_version"] = VERSION
    return just_disabled


def record_outcome(outcome: RunnerOutcome) -> bool:
    """Apply one RunnerOutcome to focal_device. Returns just_disabled.

    just_disabled is True only on the False→True crossing of ``disabled``
    (same shape as subprocess_runner._apply_breaker's just_tripped). Exceptions
    from mutate_config / save propagate unchanged — callers own the try/except.
    """
    just_disabled = False

    def mutator(cfg: dict) -> None:
        nonlocal just_disabled
        # Reset first: mutate_config does not retry, but a stale True would
        # make T10 emit a spurious "auto-focus disabled" notification.
        just_disabled = False

        fd = cfg.setdefault("focal_device", {})
        just_disabled = _apply_outcome_core(fd, outcome, count_timeouts=True)

    mutate_config(mutator)

    if just_disabled and _notification_sink is not None:
        try:
            _notification_sink("warn", "notif.focal_auto_disabled")
        except Exception:
            logger.exception("focal_device notification sink raised; record_outcome result unaffected")

    return just_disabled


def record_manual_outcome(outcome: RunnerOutcome) -> bool:
    """Apply one manual-detect RunnerOutcome. Returns just_disabled.

    Same shell as ``record_outcome``, but ``count_timeouts=False`` (single
    timeout flips ``disabled``) and **no** notification sink call (CD-152d-5:
    the user is staring at the page; no sidebar duplicate).
    """
    just_disabled = False

    def mutator(cfg: dict) -> None:
        nonlocal just_disabled
        just_disabled = False
        fd = cfg.setdefault("focal_device", {})
        just_disabled = _apply_outcome_core(fd, outcome, count_timeouts=False)

    mutate_config(mutator)
    return just_disabled


def classify_manual_reason(outcome: RunnerOutcome, just_disabled: bool) -> str:
    """Map a manual-detect outcome (+ lock-time decision) to the ``reason`` field.

    Values per CD-152d-4b plus ``endpoint_down`` (CD-187a-16). ``just_disabled``
    must come from the ``on_outcome`` callback (via
    ``decision.get("just_disabled", False)``), never from a pre-spawn snapshot.
    ``ABANDONED(skipped_disabled)`` with ``external_failure`` is also
    ``endpoint_down`` (endpoint failed first; local was already disabled).
    """
    if outcome.kind in ("FOUND", "NO_FACE"):
        if getattr(outcome, "external_failure", None):
            return "endpoint_down"
        return ""
    if outcome.kind == "ABANDONED":
        if outcome.reason == "skipped_disabled" and getattr(outcome, "external_failure", None):
            return "endpoint_down"
        if outcome.reason == "skipped_disabled":
            return "device_disabled"
        if outcome.reason == "detect_timeout":
            if just_disabled:
                return "too_slow_auto_disabled"
            return "too_slow"
        return "failed"
    return "failed"


def set_disabled_by_user(disabled: bool) -> None:
    """Persist a user-owned focal enable/disable decision (T-D3 toggle entrypoint).

    Writes only ``disabled`` and ``set_by_user=True`` in one ``mutate_config``
    transaction. Does **not** touch ``consecutive_timeout_count`` or
    ``judged_at_version`` (CD-152d-4).

    This is the sole write path T-D3's toggle endpoint must call. After this
    returns, auto-disable and version lazy-reset will not overwrite the value
    until the user toggles again.
    """

    def mutator(cfg: dict) -> None:
        fd = cfg.setdefault("focal_device", {})
        fd["disabled"] = bool(disabled)
        fd["set_by_user"] = True

    mutate_config(mutator)


subprocess_runner.set_local_disabled_probe(local_is_disabled)
