"""OpenAI-compatible image embeddings client (CD-186-6)."""

from __future__ import annotations

import math
from dataclasses import dataclass

import httpx

from core.logger import get_logger

logger = get_logger(__name__)

_DIM_MIN = 128
_DIM_MAX = 4096
_DEFAULT_MODEL = "openaver-image-embedding"


class EndpointError(Exception):
    """Embeddings endpoint failure: kind is ``unreachable`` or ``contract``."""

    def __init__(
        self,
        kind: str,
        check: str | None = None,
        status: int | None = None,
    ):
        self.kind = kind
        self.check = check
        self.status = status
        super().__init__(kind, check, status)


@dataclass(frozen=True)
class EmbedResult:
    vector: list[float]
    model: str
    dim: int


def _new_client(timeout: httpx.Timeout) -> httpx.Client:
    """Factory seam for tests (patch this, not global ``httpx.Client``)."""
    return httpx.Client(timeout=timeout)


def _timeout_for(first: bool) -> httpx.Timeout:
    if first:
        return httpx.Timeout(30.0, connect=5.0, read=90.0)
    return httpx.Timeout(30.0, connect=5.0)


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

    url = f"{base.rstrip('/')}/v1/embeddings"
    model = (getattr(cfg, "model", None) or "").strip() or _DEFAULT_MODEL
    payload = {"model": model, "input": [data_uri]}
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
        "[ai_services.embed] status=%s kind=%s check=%s body_len=%s",
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
            if attempt == 0:
                continue
            _log_failure(None, "unreachable", None, "")
            raise EndpointError("unreachable", None, None) from e
        except httpx.TransportError as e:
            _log_failure(None, "unreachable", None, "")
            raise EndpointError("unreachable", None, None) from e
        except httpx.InvalidURL as e:
            _log_failure(None, "unreachable", None, "")
            raise EndpointError("unreachable", None, None) from e

        if 500 <= resp.status_code < 600 and attempt == 0:
            continue
        return resp

    assert resp is not None
    return resp


def _parse_response(resp: httpx.Response) -> EmbedResult:
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

    try:
        emb = data["data"][0]["embedding"]
    except (KeyError, IndexError, TypeError):
        _log_failure(status, "contract", "shape", body_text)
        raise EndpointError("contract", "shape", status) from None

    if not isinstance(emb, list):
        _fail("shape")

    vec: list[float] = []
    for x in emb:
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            _fail("not_numeric")
        try:
            fx = float(x)
        except (OverflowError, ValueError):
            # Huge ints / bad coercions must not escape as 500 (P2).
            _fail("shape")
        if not math.isfinite(fx):
            _fail("not_numeric")
        vec.append(fx)

    dim = len(vec)
    if not (_DIM_MIN <= dim <= _DIM_MAX):
        _fail("dim_range")

    try:
        norm = math.sqrt(math.sumprod(vec, vec))
    except (OverflowError, ValueError):
        _fail("shape")
    if not math.isfinite(norm):
        _fail("shape")
    if norm == 0.0:
        _fail("zero_norm")

    vec = [x / norm for x in vec]
    return EmbedResult(vector=vec, model=model, dim=dim)


def embed(cfg, data_uri: str, *, first: bool = False) -> EmbedResult:
    """POST ``{base}/v1/embeddings``; return L2-normalised vector.

    Raises ``EndpointError`` on unreachable transport or contract mismatch.
    """
    url, headers, payload = _build_request(cfg, data_uri)
    timeout = _timeout_for(first)
    with _new_client(timeout) as client:
        resp = _send_with_retry(client, url, headers, payload)
    return _parse_response(resp)
