"""自訂來源測試共用：FakeTransport 與回應小工具（只依賴 fetch.RawResponse）。"""

import json
import threading
from pathlib import Path

from core.custom_source.fetch import RawResponse


def page(body="", status=200, headers=None):
    data = body if isinstance(body, bytes) else body.encode("utf-8")
    return RawResponse(status, dict(headers or {}), data, None)


def redirect(location, status=302):
    return RawResponse(status, {"location": location}, b"", location)


class FakeTransport:
    """routes: url -> RawResponse | Exception | list(依序消耗、最後一個重複) | callable(url)。"""

    def __init__(self, routes, *, log=None):
        self.routes = dict(routes)
        self.calls = []
        self._log = log
        self._pos = {}

    def request(self, url):
        self.calls.append(url)
        if self._log is not None:
            self._log.append(("request", url))
        if url not in self.routes:
            raise AssertionError(f"unexpected request: {url}")
        route = self.routes[url]
        if isinstance(route, list):
            idx = self._pos.get(url, 0)
            self._pos[url] = idx + 1
            route = route[min(idx, len(route) - 1)]
        if callable(route) and not isinstance(route, RawResponse):
            route = route(url)
        if isinstance(route, Exception):
            raise route
        return route


class TrackedLock:
    """包真 RLock：記 acquire 次數、每 thread 的持鎖層數、以及「最外層持鎖編號」。"""

    def __init__(self):
        self._real = threading.RLock()
        self._local = threading.local()
        self._counter = 0
        self.acquired = 0
        self.in_callback = False
        self.violations = 0

    def acquire(self, *a, **k):
        self.acquired += 1
        if self.in_callback:
            self.violations += 1
        got = self._real.acquire(*a, **k)
        if got:
            depth = getattr(self._local, "depth", 0)
            if depth == 0:
                self._counter += 1
                self._local.hold = self._counter
            self._local.depth = depth + 1
        return got

    def release(self):
        self._local.depth -= 1
        if self._local.depth == 0:
            self._local.hold = None
        self._real.release()

    def hold_id(self):
        """目前 thread 的最外層持鎖編號；未持鎖回 None。"""
        return getattr(self._local, "hold", None) if getattr(self._local, "depth", 0) else None

    def held_by_current(self):
        return getattr(self._local, "depth", 0) > 0

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()


def gate_route(entered, release, response, safety_s=5):
    """給 FakeTransport 的可卡住 route：進入即 entered.set()，等 release（有安全上限）後回 response。"""

    def _route(url):
        entered.set()
        release.wait(safety_s)
        return response

    return _route


def put_source(root, stem, text, ext=".yaml"):
    d = Path(root) / "custom_sources"
    d.mkdir(exist_ok=True)
    path = d / f"{stem}{ext}"
    path.write_text(text, encoding="utf-8")
    return path


def finalize_root(root):
    (Path(root) / ".layout.json").write_text(json.dumps({"version": 1, "complete": True}), encoding="utf-8")
