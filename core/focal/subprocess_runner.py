"""Parent-side focal detection subprocess runner (TASK-152b-T1b).

Spawns a child via spawn_fn (default: core.focal._detect_child), waits with a
background reader thread + queue.Queue (CD-152b-18), classifies FOUND / NO_FACE
/ ABANDONED, reaps before releasing the single slot lock, and maintains a
session-level circuit breaker (CD-152b-17).
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import dataclasses
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from core.logger import get_logger

logger = get_logger(__name__)

_STARTUP_TIMEOUT_S = 10.0
_BREAKER_THRESHOLD = 3
_slot_lock = threading.Lock()
_breaker_streak = 0

_TIMEOUT = object()  # sentinel from queue.get timeout


@dataclass(frozen=True)
class RunnerOutcome:
    """Three-way result of run_detection (CD-152b-3)."""

    kind: str  # "FOUND" | "NO_FACE" | "ABANDONED"
    focal: tuple[float, float] | None = None
    reason: str | None = None
    model: str | None = None  # set only for external (faces endpoint) results
    external_failure: str | None = None  # why external fell back; not a `reason`


def _found(x: float, y: float) -> RunnerOutcome:
    return RunnerOutcome(kind="FOUND", focal=(x, y))


def _no_face() -> RunnerOutcome:
    return RunnerOutcome(kind="NO_FACE")


def _abandoned(reason: str) -> RunnerOutcome:
    return RunnerOutcome(kind="ABANDONED", reason=reason)


class _CallState:
    """Per-invocation abandon reason (monotonic write-once; never module-level)."""

    __slots__ = ("abandon_reason",)

    def __init__(self) -> None:
        self.abandon_reason: str | None = None

    def set_abandon(self, reason: str) -> None:
        if self.abandon_reason is None:
            self.abandon_reason = reason


def _default_spawn(fs_path: str, ratio: float):
    """Spawn core.focal._detect_child per CD-152b-1."""
    import core.focal as focal_pkg

    root = Path(focal_pkg.__file__).resolve().parents[2]
    cmd = [
        sys.executable,
        "-u",
        "-m",
        "core.focal._detect_child",
        fs_path,
        str(ratio),
    ]
    kwargs: dict[str, Any] = {
        "args": cmd,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "cwd": str(root),
        "env": {**os.environ, "PYTHONPATH": str(root)},
        "text": True,
        "encoding": "utf-8",
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return subprocess.Popen(**kwargs)


def _start_reader(stdout, event_q: queue.Queue) -> None:
    def _read() -> None:
        try:
            while True:
                line = stdout.readline()
                if line == "" or line is None:
                    event_q.put(("eof", None))
                    return
                event_q.put(("line", line.rstrip("\r\n")))
        except Exception:
            logger.exception(
                "focal stdout reader failed; treating as child EOF"
            )
            event_q.put(("eof", None))

    threading.Thread(target=_read, name="focal-stdout-reader", daemon=True).start()


def _start_stderr_drain(stderr) -> None:
    if stderr is None:
        return

    def _drain() -> None:
        try:
            for line in stderr:
                logger.debug("focal child stderr: %s", line.rstrip())
        except Exception:
            logger.debug("focal child stderr drain ended", exc_info=True)

    threading.Thread(target=_drain, name="focal-stderr-drain", daemon=True).start()


def _queue_get(event_q: queue.Queue, timeout_s: float):
    try:
        return event_q.get(timeout=timeout_s)
    except queue.Empty:
        return _TIMEOUT


def _safe_kill(child) -> None:
    try:
        child.kill()
    except Exception:
        logger.exception("focal child kill failed")


def _parse_result_line(text: str) -> RunnerOutcome | None:
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict) or "focal" not in payload:
        return None
    focal = payload["focal"]
    if focal is None:
        return _no_face()
    if (
        isinstance(focal, (list, tuple))
        and len(focal) == 2
        and all(isinstance(v, (int, float)) for v in focal)
    ):
        return _found(float(focal[0]), float(focal[1]))
    return None


def _classify_event(event, call_state: _CallState) -> RunnerOutcome:
    """Classify at the moment an event is consumed (CD-152b-3)."""
    # Under T1b's single-writer design this branch is only hit by the direct
    # unit test (normal flow returns ABANDONED on queue.Empty without consuming
    # a late event). Kept for CD-152b-3: once abandon_reason is set, late JSON
    # and EOF are discarded. 152d's cancel() adds a second cross-thread writer
    # and will exercise this path in the live flow.
    if call_state.abandon_reason is not None:
        return _abandoned(call_state.abandon_reason)
    if event is None or event is _TIMEOUT or event[0] == "eof":
        return _abandoned("crashed")
    parsed = _parse_result_line(event[1])
    if parsed is None:
        return _abandoned("crashed")
    return parsed


def _apply_breaker(outcome: RunnerOutcome) -> bool:
    """Update the circuit-breaker streak. Returns True iff this call is the
    one that pushed the streak from threshold-1 to threshold (the log trigger
    added by 152b pre-merge branch review P2-2); the increment/reset semantics
    themselves are unchanged from CD-152b-17."""
    global _breaker_streak
    if outcome.kind in ("FOUND", "NO_FACE"):
        _breaker_streak = 0
        return False
    if outcome.kind != "ABANDONED":
        return False
    reason = outcome.reason
    just_tripped = False
    if reason in ("startup_timeout", "crashed"):
        _breaker_streak += 1
        just_tripped = _breaker_streak == _BREAKER_THRESHOLD
    elif reason == "detect_timeout":
        _breaker_streak = 0
    # circuit_open / skipped_disabled: neither increment nor reset
    return just_tripped


def _log_abandoned(outcome: RunnerOutcome, fs_path: str, just_tripped: bool) -> None:
    """留一條可事後判讀的線索，說明某次 focal 偵測為何被判 ABANDONED（152b pre-merge branch review P2-2）。

    只加 log，不動控制流／斷路器語意。just_tripped 只在 streak 剛好跨過
    _BREAKER_THRESHOLD 的那一次為 True，避免斷路器開路後每次呼叫都刷屏。
    """
    logger.warning(
        "focal detection abandoned: reason=%s path=%s streak=%d/%d",
        outcome.reason, fs_path, _breaker_streak, _BREAKER_THRESHOLD,
    )
    if just_tripped:
        logger.warning(
            "focal circuit breaker tripped (streak=%d) — automatic focal "
            "detection is now stopped for the rest of this App session; "
            "restart the App to recover. path=%s",
            _breaker_streak, fs_path,
        )


def _run_child_phases(
    child,
    timeout_s: float,
    call_state: _CallState,
) -> RunnerOutcome:
    """Startup + detect phases. Returns classification only.

    Whether to kill is decided by the caller from the outcome (ABANDONED ⇒
    kill before wait), so live children that printed garbage cannot deadlock
    the slot lock on an unbounded wait().
    """
    event_q: queue.Queue = queue.Queue()
    _start_reader(child.stdout, event_q)
    _start_stderr_drain(getattr(child, "stderr", None))

    startup_limit = _STARTUP_TIMEOUT_S  # read module attr at call time
    event = _queue_get(event_q, startup_limit)
    if event is _TIMEOUT:
        # Write abandon reason before kill (kill happens in caller's finally).
        call_state.set_abandon("startup_timeout")
        return _abandoned("startup_timeout")

    # Same CD-152b-3 precedence; see comment on _classify_event.
    if call_state.abandon_reason is not None:
        return _classify_event(event, call_state)
    if event[0] == "eof":
        return _abandoned("crashed")
    if event[1] != "READY":
        return _abandoned("crashed")

    event = _queue_get(event_q, timeout_s)
    if event is _TIMEOUT:
        call_state.set_abandon("detect_timeout")
        return _abandoned("detect_timeout")

    return _classify_event(event, call_state)


def _run_local_detection(
    fs_path: str,
    ratio: float,
    *,
    job_key: str,
    timeout_s: float,
    spawn_fn: Callable[..., Any] = _default_spawn,
    pre_spawn_check: Callable[[], bool] | None = None,
    on_outcome: Callable[[RunnerOutcome], None] | None = None,
) -> RunnerOutcome:
    """Run one focal detection in a child process (CD-152b-3/4/10/17/18).

    pre_spawn_check / on_outcome are the 152c device-disable hooks (CD-152b-9).
    pre_spawn_check runs inside the slot-lock critical section, *after* the
    authoritative breaker recheck, and returning True short-circuits to
    ABANDONED("skipped_disabled") without spawning, timing, logging a WARNING or
    calling on_outcome; its exceptions fail open. on_outcome runs in the finally
    block after wait() and *before* releasing the slot lock, so the next job sees
    whatever it recorded; its exceptions are logged and swallowed and never alter
    the outcome returned to the caller.

    What on_outcome actually receives (stated here because it is decided at five
    separate return sites and is otherwise only derivable by reading all of them):
    FOUND / NO_FACE / ABANDONED(startup_timeout|detect_timeout|crashed), plus
    ABANDONED(circuit_open) from the *in-lock* breaker recheck. It never receives
    ABANDONED(skipped_disabled) -- deliberate, see the comment at that return --
    nor circuit_open from the lock-free short-circuit, which returns before the
    try/finally exists. The two circuit_open sites therefore differ; harmless
    today because record_outcome no-ops circuit_open either way, and left alone at
    152c pre-merge rather than rewriting this branch's own mechanism for a
    zero-user-impact tidy (pre-merge step 0.1). If a future on_outcome consumer
    cares about circuit_open, make the two sites agree *before* relying on it.
    """
    logger.debug("run_detection job_key=%s path=%s", job_key, fs_path)
    if _breaker_streak >= _BREAKER_THRESHOLD:
        outcome = _abandoned("circuit_open")
        _log_abandoned(outcome, fs_path, just_tripped=False)
        return outcome

    child = None
    need_kill = False
    call_state = _CallState()
    outcome_for_callback: RunnerOutcome | None = None

    _slot_lock.acquire()
    try:
        # Authoritative recheck under the lock: callers that passed the
        # lock-free short-circuit may still find the streak already open
        # by the time they enter the critical section.
        if _breaker_streak >= _BREAKER_THRESHOLD:
            outcome = _abandoned("circuit_open")
            _log_abandoned(outcome, fs_path, just_tripped=False)
            outcome_for_callback = outcome
            return outcome

        if pre_spawn_check is not None:
            try:
                disabled = pre_spawn_check()
            except Exception:
                logger.warning("focal pre_spawn_check raised; failing open", exc_info=True)
                disabled = False
            if disabled:
                # 故意不設定 outcome_for_callback：skipped_disabled 不得餵給
                # on_outcome（CD-152b-9）。把賦值「統一」提到每個 return 前面
                # 會讓裝置停用後的每次 gate 命中都寫一次 config.json。
                return _abandoned("skipped_disabled")

        try:
            child = spawn_fn(fs_path, ratio)
        except OSError:
            logger.exception("focal spawn_fn raised")
            outcome = _abandoned("crashed")
            just_tripped = _apply_breaker(outcome)
            _log_abandoned(outcome, fs_path, just_tripped)
            outcome_for_callback = outcome
            return outcome

        outcome = _run_child_phases(child, timeout_s, call_state)
        # Any abandon => terminate before wait (CD-152b-10). Harmless if child
        # already exited; required if it is still alive after garbage stdout.
        need_kill = outcome.kind == "ABANDONED"
        just_tripped = _apply_breaker(outcome)
        if outcome.kind == "ABANDONED":
            _log_abandoned(outcome, fs_path, just_tripped)
        outcome_for_callback = outcome
        return outcome
    finally:
        if child is not None:
            if need_kill:
                _safe_kill(child)
            try:
                child.wait()
            except Exception:
                logger.exception("focal child wait failed")
        if on_outcome is not None and outcome_for_callback is not None:
            try:
                on_outcome(outcome_for_callback)
            except Exception:
                logger.exception("focal on_outcome callback raised")
        _slot_lock.release()


_local_disabled_probe: Callable[[], bool] | None = None


def set_local_disabled_probe(fn: Callable[[], bool]) -> None:
    """device_state registers its local-only disabled read here (same shape as
    device_state.set_notification_sink); tests replace the module attribute."""
    global _local_disabled_probe
    _local_disabled_probe = fn


def _local_disabled_via_probe() -> bool:
    probe = _local_disabled_probe
    if probe is None:
        return False
    try:
        return bool(probe())
    except Exception:
        logger.warning("focal local-disabled probe raised; failing open", exc_info=True)
        return False


def _try_external(
    fs_path: str, ratio: float, profile: str
) -> tuple[RunnerOutcome | None, str | None]:
    """Ask the faces endpoint (CD-187a-1). Returns ``(final, failure)``.

    ``final`` set = FOUND / NO_FACE from the endpoint; ``failure`` set = endpoint
    tried and failed (fall back to local); both None = external not applicable.
    Never calls on_outcome / breaker / slot (I-A, I-B).
    """
    from core.ai_services import faces_detect

    result = faces_detect.detect(fs_path, ratio, profile=profile)
    if result is None:
        return None, None
    if result.kind == "FOUND" and result.focal is not None:
        return RunnerOutcome(kind="FOUND", focal=result.focal, model=result.model), None
    if result.kind == "NO_FACE":
        return RunnerOutcome(kind="NO_FACE", model=result.model), None
    return None, result.failure or "external_contract"


def run_detection(
    fs_path: str,
    ratio: float,
    *,
    job_key: str,
    timeout_s: float,
    spawn_fn: Callable[..., Any] = _default_spawn,
    pre_spawn_check: Callable[[], bool] | None = None,
    on_outcome: Callable[[RunnerOutcome], None] | None = None,
    external_profile: str = "background",
) -> RunnerOutcome:
    """External faces endpoint first (CD-187a-1), else the local child path.

    External success returns before any breaker / slot / on_outcome. External
    failure falls back to ``_run_local_detection`` unless the local machine is
    already judged too slow (probe), and tags the result with ``external_failure``.
    """
    final, failure = _try_external(fs_path, ratio, external_profile)
    if final is not None:
        return final
    if failure is not None and _local_disabled_via_probe():
        return dataclasses.replace(_abandoned("skipped_disabled"), external_failure=failure)
    out = _run_local_detection(
        fs_path, ratio, job_key=job_key, timeout_s=timeout_s, spawn_fn=spawn_fn,
        pre_spawn_check=pre_spawn_check, on_outcome=on_outcome,
    )
    if failure is not None:
        out = dataclasses.replace(out, external_failure=failure)
    return out
