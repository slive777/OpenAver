"""自訂來源的抓取層：逐跳守衛、兩種 transport、body 上限、節流。"""

from dataclasses import dataclass
import time
from importlib.metadata import PackageNotFoundError
from typing import NamedTuple, Optional, Protocol
from urllib.parse import urljoin

import requests

from core.custom_source import guard
from core.custom_source.errors import BlockedTarget
from core.proxy_policy import new_session, proxy_kwargs
from core.scrapers.utils import DEFAULT_HEADERS, rate_limit

MAX_REDIRECTS = 5
MAX_BODY_BYTES = 5 * 1024 * 1024
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_DATA_STATUSES = frozenset({200, 404})
_CHUNK_SIZE = 64 * 1024
_now = time.monotonic


class FetchError(Exception):
    """抓取失敗。reason 屬於 SCRAPE_ERROR_REASONS；訊息只含 reason 與狀態碼。"""

    def __init__(self, reason, http_status=None):
        self.reason = reason
        self.http_status = http_status
        super().__init__(reason, http_status)

    def __str__(self):
        if self.http_status is not None:
            return f"[{self.reason}] {self.http_status}"
        return f"[{self.reason}]"


@dataclass(frozen=True)
class RawResponse:
    status: int
    headers: dict
    body_bytes: bytes
    location: Optional[str] = None


class FetchedPage(NamedTuple):
    status: int
    text: str
    final_url: str


class Transport(Protocol):
    """單跳請求：不跟隨重導向、不重試。"""

    def request(self, url: str) -> RawResponse: ...


def _lower_headers(headers):
    return {str(k).lower(): v for k, v in headers.items()}


class PlainTransport:
    """requests 單跳請求；讀到上限立即關閉連線。"""

    def __init__(self, source_id, config):
        self._session = new_session(source_id, settings=config.proxy_settings)
        self._headers = dict(DEFAULT_HEADERS)
        self._timeout = config.timeout

    def request(self, url):
        resp = None
        try:
            resp = self._session.get(url, headers=self._headers, timeout=self._timeout, allow_redirects=False, stream=True)  # plain-hop
            chunks = []
            total = 0
            for chunk in resp.iter_content(chunk_size=_CHUNK_SIZE):
                total += len(chunk)
                if total > MAX_BODY_BYTES:
                    raise FetchError("too_large")
                chunks.append(chunk)
            headers = _lower_headers(resp.headers)
            return RawResponse(resp.status_code, headers, b"".join(chunks), headers.get("location"))
        except requests.exceptions.Timeout:
            raise FetchError("timeout") from None
        except requests.exceptions.RequestException:
            raise FetchError("network") from None
        finally:
            if resp is not None:
                resp.close()


class TlsTransport:
    """curl_cffi（chrome 指紋）單跳請求；讀完再檢查大小。"""

    def __init__(self, source_id, config):
        try:
            from curl_cffi import requests as cffi_requests
        except (ImportError, PackageNotFoundError):
            raise FetchError("transport_unavailable") from None
        self._session = cffi_requests.Session(impersonate="chrome")
        self._timeout_exc = cffi_requests.exceptions.Timeout
        self._timeout = config.timeout
        self._proxy_kw = proxy_kwargs("source_query", source_id=source_id, settings=config.proxy_settings)

    def request(self, url):
        try:
            resp = self._session.get(url, timeout=self._timeout, allow_redirects=False, **self._proxy_kw)  # tls-hop
            body = bytes(resp.content)
            status = resp.status_code
            headers = _lower_headers(resp.headers)
        except self._timeout_exc:
            raise FetchError("timeout") from None
        except Exception:
            raise FetchError("network") from None
        if len(body) > MAX_BODY_BYTES:
            raise FetchError("too_large")
        return RawResponse(status, headers, body, headers.get("location"))


class DeadlineTransport:
    """包住另一個 transport：建構後超過 budget_s 秒，之後每次 request() 直接 timeout。"""

    def __init__(self, inner, budget_s):
        self._inner = inner
        self._deadline = _now() + budget_s

    def request(self, url):
        if _now() >= self._deadline:
            raise FetchError("timeout")
        return self._inner.request(url)


def make_transport(fetch, source_id, config):
    if fetch == "plain":
        return PlainTransport(source_id, config)
    if fetch == "tls":
        return TlsTransport(source_id, config)
    raise ValueError(f"unknown fetch mode: {fetch}")


def _decode(raw):
    charset = "utf-8"
    for part in str(raw.headers.get("content-type", "")).split(";")[1:]:
        key, _, value = part.strip().partition("=")
        if key.lower() == "charset" and value.strip():
            charset = value.strip().strip("\"'")
    try:
        return raw.body_bytes.decode(charset, errors="replace")
    except LookupError:
        return raw.body_bytes.decode("utf-8", errors="replace")


def fetch_page(url, transport, config):
    """逐跳抓取；每一跳先 guard、再節流、才送出。回傳 FetchedPage(status, text, final_url)。"""
    redirects = 0
    while True:
        try:
            guard.check(url)
        except BlockedTarget:
            raise FetchError("blocked_target") from None
        rate_limit(config.delay)
        raw = transport.request(url)
        if raw.status in _REDIRECT_STATUSES and raw.location:
            if redirects >= MAX_REDIRECTS:
                raise FetchError("redirect_limit")
            redirects += 1
            try:
                url = urljoin(url, raw.location)
            except ValueError:
                raise FetchError("blocked_target") from None
            continue
        if raw.status not in _DATA_STATUSES:
            raise FetchError("http_status", http_status=raw.status)
        return FetchedPage(raw.status, _decode(raw), url)
