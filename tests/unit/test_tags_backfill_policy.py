"""T2: tags_backfill_policy — failure classify / degrade / 429 state machine."""

from __future__ import annotations

import pytest

from core.ai_services.tagging import TaggingFailure
from core.ai_services.tags_backfill_policy import (
    WAIT_429_S,
    MAX_CONCURRENCY,
    RunPolicy,
    classify_failure,
)


# Each row = one truth-table action + stop_reason pair (different outcomes).
@pytest.mark.parametrize(
    "exc, expect_action, expect_stop, expect_degrade",
    [
        # unreachable / rate_limited → wait then resend same title
        (
            TaggingFailure("unreachable", "rate_limited"),
            "wait_retry",
            None,
            False,
        ),
        # unreachable / connection_timeout → degrade + retry once then halt
        (
            TaggingFailure("unreachable", "connection_timeout"),
            "retry_then_halt",
            "unreachable",
            True,
        ),
        # unreachable others → retry once then halt (auth vs unreachable stop codes)
        (
            TaggingFailure("unreachable", "auth_failed"),
            "retry_then_halt",
            "auth",
            False,
        ),
        (
            TaggingFailure("unreachable", "forbidden"),
            "retry_then_halt",
            "auth",
            False,
        ),
        (
            TaggingFailure("unreachable", "connection_failed"),
            "retry_then_halt",
            "unreachable",
            False,
        ),
        # endpoint 404 (detail=not_found) ≠ title-row not_found
        (
            TaggingFailure("unreachable", "not_found"),
            "retry_then_halt",
            "unreachable",
            False,
        ),
        (
            TaggingFailure("unreachable", "http_error"),
            "retry_then_halt",
            "unreachable",
            False,
        ),
        (
            TaggingFailure("model_unsupported"),
            "retry_then_halt",
            "model_unsupported",
            False,
        ),
        # immediate halt
        (TaggingFailure("not_configured"), "halt", "not_configured", False),
        (TaggingFailure("disabled"), "halt", "disabled", False),
        # skip this title, continue batch
        (TaggingFailure("bad_response"), "skip", None, False),
        (TaggingFailure("no_cover"), "skip", None, False),
        (TaggingFailure("write_failed"), "skip", None, False),
        # title row already deleted
        (TaggingFailure("not_found"), "skip", None, False),
        # non-TaggingFailure → skip
        (RuntimeError("x"), "skip", None, False),
    ],
)
def test_failure_policy_truth_table(exc, expect_action, expect_stop, expect_degrade):
    """一部讀不出封面 → 跳過；金鑰錯 → 重試一次就停；剛關掉開關 → 立停。"""
    verdict = classify_failure(exc)
    assert verdict.action == expect_action
    assert verdict.stop_reason == expect_stop
    assert verdict.degrade is expect_degrade

    if expect_action == "retry_then_halt":
        p = RunPolicy()
        started = p.attempt_started()
        first = p.on_failure(verdict, started, retries_used=0)
        assert first.action == "retry"
        assert first.stop_reason is None
        if expect_degrade:
            assert p.limit == 1
            assert p.degraded is True
        started2 = p.attempt_started()
        second = p.on_failure(verdict, started2, retries_used=1)
        assert second.action == "halt"
        assert second.stop_reason == expect_stop
        assert second.wait_s == 0
    elif expect_action == "halt":
        p = RunPolicy()
        started = p.attempt_started()
        d = p.on_failure(verdict, started, retries_used=0)
        assert d.action == "halt"
        assert d.stop_reason == expect_stop
        assert d.wait_s == 0
    elif expect_action == "skip":
        p = RunPolicy()
        started = p.attempt_started()
        d = p.on_failure(verdict, started, retries_used=0)
        assert d.action == "skip"
        assert d.stop_reason is None
    elif expect_action == "wait_retry":
        p = RunPolicy()
        started = p.attempt_started()
        d = p.on_failure(verdict, started, retries_used=0)
        assert d.action == "wait_retry"
        assert d.wait_s == WAIT_429_S
        assert d.stop_reason is None
        # 429 does not consume retries_used
        started2 = p.attempt_started()
        d2 = p.on_failure(verdict, started2, retries_used=1)
        assert d2.action == "wait_retry"
        assert d2.wait_s == WAIT_429_S


def test_timeout_and_429_degrade_limit_to_one_and_never_recover():
    """服務已在限流 → 使用者看到「已改為逐部處理」，不再以 4 條硬打。"""
    # timeout path
    p = RunPolicy()
    assert p.limit == MAX_CONCURRENCY
    started = p.attempt_started()
    v = classify_failure(TaggingFailure("unreachable", "connection_timeout"))
    p.on_failure(v, started, retries_used=0)
    assert p.limit == 1
    p.on_success()
    p.on_success()
    started2 = p.attempt_started()
    p.on_failure(classify_failure(TaggingFailure("bad_response")), started2, 0)
    assert p.limit == 1

    # 429 path — fresh policy
    p2 = RunPolicy()
    assert p2.limit == MAX_CONCURRENCY
    started = p2.attempt_started()
    v = classify_failure(TaggingFailure("unreachable", "rate_limited"))
    p2.on_failure(v, started, retries_used=0)
    assert p2.limit == 1
    p2.on_success()
    p2.on_success()
    started2 = p2.attempt_started()
    p2.on_failure(classify_failure(TaggingFailure("no_cover")), started2, 0)
    assert p2.limit == 1


def test_consecutive_429_counts_only_post_degrade_and_resets_on_success():
    """偶發限流不誤判額度用完；真用完時也不會永遠等下去。"""
    rate = TaggingFailure("unreachable", "rate_limited")

    def do_429(policy: RunPolicy, retries_used: int = 0):
        started = policy.attempt_started()
        return policy.on_failure(
            classify_failure(rate), started, retries_used=retries_used
        )

    # Sequence A: pre-degrade 429 (uncounted) then 429,429,success,429,429,429
    # → 4th/5th of post sequence do NOT halt; 6th halts with quota
    p = RunPolicy()
    d0 = do_429(p)
    assert d0.action == "wait_retry"
    assert p.degraded is True
    assert p.limit == 1

    d1 = do_429(p)  # post #1
    assert d1.action == "wait_retry"
    d2 = do_429(p)  # post #2
    assert d2.action == "wait_retry"
    p.on_success()  # reset counter
    d4 = do_429(p)  # post #4 (count=1) — must NOT halt
    assert d4.action == "wait_retry"
    d5 = do_429(p)  # post #5 (count=2) — must NOT halt
    assert d5.action == "wait_retry"
    d6 = do_429(p)  # post #6 (count=3) — halt
    assert d6.action == "halt"
    assert d6.stop_reason == "quota"
    assert d6.wait_s == 0

    # Sequence B: post-degrade 429×3 → halt on 3rd
    p2 = RunPolicy()
    assert do_429(p2).action == "wait_retry"  # trigger degrade
    assert do_429(p2).action == "wait_retry"
    assert do_429(p2).action == "wait_retry"
    d = do_429(p2)
    assert d.action == "halt"
    assert d.stop_reason == "quota"

    # Sequence C: two in-flight attempt_started() both False before degrade;
    # first 429 degrades, second (still False) uncounted; then 3 post-degrade → halt
    p3 = RunPolicy()
    s1 = p3.attempt_started()
    s2 = p3.attempt_started()
    assert s1 is False
    assert s2 is False
    v = classify_failure(rate)
    assert p3.on_failure(v, s1, 0).action == "wait_retry"
    assert p3.degraded is True
    assert p3.on_failure(v, s2, 0).action == "wait_retry"  # uncounted sibling
    assert do_429(p3).action == "wait_retry"  # post #1
    assert do_429(p3).action == "wait_retry"  # post #2
    d = do_429(p3)  # post #3 → halt
    assert d.action == "halt"
    assert d.stop_reason == "quota"
