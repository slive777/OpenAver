"""186-T3: embeddings client error classification / consistency / retry."""

from __future__ import annotations

import json
import math
from types import SimpleNamespace

import httpx
import pytest

from core.ai_services import embeddings
from core.ai_services.embeddings import EmbedResult, EndpointError, embed
from core.ai_services.samples import check_consistency


def _cfg(**kw):
    base = dict(url="http://embed.test", api_key="", model="m-test")
    base.update(kw)
    return SimpleNamespace(**base)


def _install(monkeypatch, handler):
    """Patch the module-local client factory (BE-TEST-29); do not touch global httpx.Client."""

    def _factory(timeout=None):
        return httpx.Client(
            transport=httpx.MockTransport(handler),
            timeout=timeout or httpx.Timeout(30.0, connect=5.0),
        )

    monkeypatch.setattr(embeddings, "_new_client", _factory)


def _unit(n: int, i: int = 0) -> list[float]:
    v = [0.0] * n
    v[i] = 1.0
    return v


def _pair_at_cos(cos: float, n: int = 128) -> tuple[list[float], list[float]]:
    """Two L2-unit vectors with exact cosine ``cos`` (in span of e0/e1)."""
    s = math.sqrt(1.0 - cos * cos)
    a = _unit(n, 0)
    b = [0.0] * n
    b[0] = cos
    b[1] = s
    return a, b


def _er(vec: list[float], model: str = "m") -> EmbedResult:
    return EmbedResult(vector=list(vec), model=model, dim=len(vec))


# ---------------------------------------------------------------------------
# (a) error classification
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "case,kind,check",
    [
        ("connect", "unreachable", None),
        ("read_timeout", "unreachable", None),
        ("http_400", "contract", "http_4xx"),
        ("http_401", "contract", "auth"),
        ("not_json", "contract", "not_json"),
        ("dim_range", "contract", "dim_range"),
        ("zero_norm", "contract", "zero_norm"),
        ("bad_key", "contract", "auth"),
        ("auth_body_leak", "contract", "auth"),
        ("overflow", "contract", "shape"),
    ],
)
def test_error_classification(monkeypatch, caplog, case, kind, check):
    fake_key = "sk-FAKE-KEY"
    # Quote + backslash → JSON body carries escaped form (k\"ey\\x), not raw key.
    leak_key = 'k"ey\\x'

    def handler(request: httpx.Request) -> httpx.Response:
        if case == "connect":
            raise httpx.ConnectError("boom", request=request)
        if case == "read_timeout":
            raise httpx.ReadTimeout("boom", request=request)
        if case == "http_400":
            return httpx.Response(400, json={"error": "bad"})
        if case == "http_401":
            return httpx.Response(401, json={"error": "nope"})
        if case == "not_json":
            return httpx.Response(200, content=b"not-json{{")
        if case == "dim_range":
            return httpx.Response(
                200,
                json={
                    "model": "m",
                    "data": [{"embedding": [1.0] * 64}],
                },
            )
        if case == "zero_norm":
            return httpx.Response(
                200,
                json={
                    "model": "m",
                    "data": [{"embedding": [0.0] * 128}],
                },
            )
        if case == "bad_key":
            raise httpx.LocalProtocolError(
                f"Illegal header value b'{fake_key}'"
            )
        if case == "auth_body_leak":
            return httpx.Response(
                401, json={"error": f"invalid api key {leak_key}"}
            )
        if case == "overflow":
            # ~310 digits: JSON-ok, but float() raises OverflowError → contract/shape
            huge = 10**309
            return httpx.Response(
                200,
                json={
                    "model": "m",
                    "data": [{"embedding": [huge] + [0] * 127}],
                },
            )
        raise AssertionError(f"unknown case {case}")

    _install(monkeypatch, handler)
    cfg = _cfg(
        api_key=(
            fake_key
            if case == "bad_key"
            else leak_key
            if case == "auth_body_leak"
            else ""
        )
    )
    with caplog.at_level("DEBUG"), pytest.raises(EndpointError) as ei:
        embed(cfg, "data:image/jpeg;base64,xx")
    err = ei.value
    assert err.kind == kind
    assert err.check == check
    if case == "bad_key":
        assert fake_key not in str(err)
        assert fake_key not in (caplog.text or "")
    if case == "auth_body_leak":
        log = caplog.text or ""
        assert leak_key not in str(err)
        assert leak_key not in log
        # Body holds json.dumps form; that escaped substring must also stay out of log.
        escaped = json.dumps(leak_key)[1:-1]
        assert escaped not in log


# ---------------------------------------------------------------------------
# (b) check_consistency
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "label,a1,a2,b,ok,failed",
    [
        (
            "stable",
            _er(_unit(128, 0)),
            _er(_unit(128, 0)),
            _er(_unit(128, 1)),
            True,
            None,
        ),
        (
            "unstable",
            _er(_pair_at_cos(0.98)[0]),
            _er(_pair_at_cos(0.98)[1]),
            _er(_unit(128, 2)),
            False,
            "unstable",
        ),
        (
            "boundary_same_ok",
            _er(_pair_at_cos(0.99)[0]),
            _er(_pair_at_cos(0.99)[1]),
            _er(_unit(128, 2)),
            True,
            None,
        ),
        (
            "not_discriminative",
            _er(_unit(128, 0)),
            _er(_unit(128, 0)),
            _er(_pair_at_cos(0.95)[1]),  # cos with e0 ≈ 0.95 ≥ 0.9
            False,
            "not_discriminative",
        ),
        (
            "boundary_diff_fail",
            _er(_unit(128, 0)),
            _er(_unit(128, 0)),
            _er(_pair_at_cos(0.9)[1]),  # cos == 0.9 → not < 0.9
            False,
            "not_discriminative",
        ),
        (
            "dim_mismatch",
            _er(_unit(128, 0)),
            _er(_unit(256, 0)),
            _er(_unit(128, 1)),
            False,
            "dim_mismatch",
        ),
    ],
)
def test_check_consistency(label, a1, a2, b, ok, failed):
    got_ok, got_failed = check_consistency(a1, a2, b)
    assert (got_ok, got_failed) == (ok, failed), label


# ---------------------------------------------------------------------------
# (c) retry policy
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "mode,expect_calls,kind,check",
    [
        ("5xx", 2, "contract", "http_5xx"),
        ("timeout", 2, "unreachable", None),
        ("4xx", 1, "contract", "http_4xx"),
    ],
)
def test_retry_policy(monkeypatch, mode, expect_calls, kind, check):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if mode == "5xx":
            return httpx.Response(503, json={"error": "cold"})
        if mode == "timeout":
            raise httpx.ReadTimeout("slow", request=request)
        if mode == "4xx":
            return httpx.Response(400, json={"error": "bad"})
        raise AssertionError(mode)

    _install(monkeypatch, handler)
    with pytest.raises(EndpointError) as ei:
        embed(_cfg(), "data:image/jpeg;base64,xx")
    assert calls["n"] == expect_calls
    assert ei.value.kind == kind
    assert ei.value.check == check
