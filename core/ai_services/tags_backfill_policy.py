"""與 similar_index.py／faces_recompute.py 為三份刻意重複的骨架，統一留給 189。"""

from __future__ import annotations

from dataclasses import dataclass

from core.ai_services.tagging import TaggingFailure

WAIT_429_S = 60
MAX_CONCURRENCY = 4

_REASON_ACTION = {
    "bad_response": "skip",
    "no_cover": "skip",
    "write_failed": "skip",
    "not_found": "skip",
    "not_configured": "halt",
    "disabled": "halt",
    "model_unsupported": "retry_then_halt",
    "unreachable": "retry_then_halt",
}


@dataclass(frozen=True)
class Verdict:
    action: str
    degrade: bool
    stop_reason: str | None


@dataclass(frozen=True)
class Decision:
    action: str
    wait_s: int
    stop_reason: str | None


def stop_reason(failure: BaseException) -> str | None:
    """Return the batch-terminating reason code for this failure, or None."""
    if not isinstance(failure, TaggingFailure):
        return None
    reason = failure.reason
    detail = failure.detail
    if reason == "unreachable" and detail == "rate_limited":
        return None
    if reason in ("not_configured", "disabled", "model_unsupported"):
        return reason
    if reason == "unreachable":
        if detail in ("auth_failed", "forbidden"):
            return "auth"
        return "unreachable"
    return None


def classify_failure(exc: BaseException) -> Verdict:
    """Map an exception to a Verdict (action / degrade / stop_reason)."""
    if not isinstance(exc, TaggingFailure):
        return Verdict("skip", False, None)

    reason = exc.reason
    detail = exc.detail

    # 429 must be checked before other unreachable → retry_then_halt
    if reason == "unreachable" and detail == "rate_limited":
        return Verdict("wait_retry", False, None)

    if reason == "unreachable" and detail == "connection_timeout":
        return Verdict("retry_then_halt", True, "unreachable")

    action = _REASON_ACTION.get(reason, "skip")
    if action == "skip":
        return Verdict("skip", False, None)
    return Verdict(action, False, stop_reason(exc))


class RunPolicy:
    """Per-job concurrency / consecutive-429 state (no threads, no I/O)."""

    def __init__(self) -> None:
        self.degraded: bool = False
        self.q429: int = 0

    @property
    def limit(self) -> int:
        return 1 if self.degraded else MAX_CONCURRENCY

    def attempt_started(self) -> bool:
        """Whether the job was already degraded when this attempt began."""
        return self.degraded

    def on_success(self) -> None:
        self.q429 = 0

    def on_failure(
        self,
        verdict: Verdict,
        started_degraded: bool,
        retries_used: int,
    ) -> Decision:
        if verdict.degrade:
            self.degraded = True

        if verdict.action == "skip":
            return Decision("skip", 0, None)

        if verdict.action == "wait_retry":
            self.degraded = True
            if started_degraded:
                self.q429 += 1
                if self.q429 >= 3:
                    return Decision("halt", 0, "quota")
            return Decision("wait_retry", WAIT_429_S, None)

        if verdict.action == "halt":
            return Decision("halt", 0, verdict.stop_reason)

        # retry_then_halt
        if retries_used < 1:
            return Decision("retry", 0, None)
        return Decision("halt", 0, verdict.stop_reason)
