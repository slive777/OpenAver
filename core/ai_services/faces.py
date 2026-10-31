"""Faces detection client (CD-187a-4 / CD-187a-6)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import NamedTuple

import httpx

from core.ai_services.embeddings import EndpointError
from core.logger import get_logger

logger = get_logger(__name__)

_PROFILES: dict[str, dict] = {
    "background": {
        "timeout": httpx.Timeout(30.0, connect=5.0),
        "retry_5xx": True,
        "retry_timeout": True,
    },
    "sync": {
        "timeout": httpx.Timeout(15.0, connect=5.0),
        "retry_5xx": True,
        "retry_timeout": False,
    },
    "manual": {
        "timeout": httpx.Timeout(4.0, connect=2.0),
        "retry_5xx": False,
        "retry_timeout": False,
    },
    "warmup": {
        "timeout": httpx.Timeout(30.0, connect=5.0, read=90.0),
        "retry_5xx": True,
        "retry_timeout": True,
    },
}


class Box(NamedTuple):
    x: float
    y: float
    w: float
    h: float
    score: float


@dataclass(frozen=True)
class FacesResult:
    boxes: list[Box]
    model: str


def _new_client(timeout: httpx.Timeout) -> httpx.Client:
    """Factory seam for tests (patch this, not global ``httpx.Client``)."""
    return httpx.Client(timeout=timeout)


def _profile_cfg(profile: str) -> dict:
    cfg = _PROFILES.get(profile)
    if cfg is None:
        raise ValueError(f"unknown faces profile: {profile!r}")
    return cfg


def _build_request(cfg, data_uri: str) -> tuple[str, dict[str, str], dict]:
    base = (getattr(cfg, "url", None) or "").strip()
    if not base:
        raise EndpointError("unreachable", None, None)
    try:
        parsed = httpx.URL(base)
    except httpx.InvalidURL as e:
        raise EndpointError("unreachable", None, None) from e
    if parsed.scheme not in ("http", "https"):
        raise EndpointError("unreachable", None, None)

    url = f"{base.rstrip('/')}/v1/faces"
    payload = {"input": data_uri, "with_embedding": False}
    headers: dict[str, str] = {}
    key = (getattr(cfg, "api_key", None) or "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return url, headers, payload


def _log_failure(
    status: int | None,
    kind: str,
    check: str | None,
    body: str,
) -> None:
    # Never log body content — endpoints may echo secrets in JSON-escaped form.
    logger.warning(
        "[ai_services.faces] status=%s kind=%s check=%s body_len=%s",
        status,
        kind,
        check,
        len(body or ""),
    )


def _send_with_retry(
    client: httpx.Client,
    url: str,
    headers: dict[str, str],
    payload: dict,
    *,
    retry_5xx: bool,
    retry_timeout: bool,
) -> httpx.Response:
    resp: httpx.Response | None = None
    for attempt in range(2):
        try:
            resp = client.post(url, headers=headers, json=payload)
        except (httpx.LocalProtocolError, UnicodeEncodeError):
            # Key with whitespace / non-ASCII → h11 rejects; str(e) contains the key.
            _log_failure(None, "contract", "auth", "")
            raise EndpointError("contract", "auth", None) from None
        except httpx.TimeoutException as e:
            if retry_timeout and attempt == 0:
                continue
            _log_failure(None, "unreachable", "timeout", "")
            raise EndpointError("unreachable", "timeout", None) from e
        except httpx.TransportError as e:
            _log_failure(None, "unreachable", None, "")
            raise EndpointError("unreachable", None, None) from e
        except httpx.InvalidURL as e:
            _log_failure(None, "unreachable", None, "")
            raise EndpointError("unreachable", None, None) from e

        if 500 <= resp.status_code < 600 and retry_5xx and attempt == 0:
            continue
        return resp

    assert resp is not None
    return resp


def _finite_number(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        fx = float(value)
    except (OverflowError, ValueError):
        return None
    if not math.isfinite(fx):
        return None
    return fx


def _clamp01(v: float) -> float:
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


def _parse_box(entry: object, fail) -> Box:
    if not isinstance(entry, dict):
        fail("shape")
    raw_box = entry.get("box")
    if not isinstance(raw_box, list) or len(raw_box) != 4:
        fail("box")
    nums: list[float] = []
    for v in raw_box:
        fx = _finite_number(v)
        if fx is None:
            fail("box")
        nums.append(_clamp01(fx))
    score = _finite_number(entry.get("score"))
    if score is None:
        fail("score")
    return Box(nums[0], nums[1], nums[2], nums[3], score)


def _parse_response(resp: httpx.Response) -> FacesResult:
    status = resp.status_code
    body_text = ""
    try:
        body_text = resp.text or ""
    except Exception:
        body_text = ""

    def _fail(check: str) -> None:
        _log_failure(status, "contract", check, body_text)
        raise EndpointError("contract", check, status)

    if status in (401, 403):
        _fail("auth")
    if 400 <= status < 500:
        _fail("http_4xx")
    if 500 <= status < 600:
        _fail("http_5xx")

    try:
        data = resp.json()
    except Exception:
        _log_failure(status, "contract", "not_json", body_text)
        raise EndpointError("contract", "not_json", status) from None

    if not isinstance(data, dict):
        _fail("shape")

    model = data.get("model")
    if not isinstance(model, str) or model == "":
        _fail("no_model")

    faces_raw = data.get("faces")
    if not isinstance(faces_raw, list):
        _fail("shape")

    boxes = [_parse_box(entry, _fail) for entry in faces_raw]
    return FacesResult(boxes=boxes, model=model)


def detect(cfg, data_uri: str, *, profile: str = "background") -> FacesResult:
    """POST ``{base}/v1/faces``; return boxes + model.

    Raises ``EndpointError`` on unreachable transport or contract mismatch.
    """
    pcfg = _profile_cfg(profile)
    url, headers, payload = _build_request(cfg, data_uri)
    with _new_client(pcfg["timeout"]) as client:
        resp = _send_with_retry(
            client,
            url,
            headers,
            payload,
            retry_5xx=pcfg["retry_5xx"],
            retry_timeout=pcfg["retry_timeout"],
        )
    return _parse_response(resp)
