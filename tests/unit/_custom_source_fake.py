"""自訂來源測試共用：FakeTransport 與回應小工具（只依賴 fetch.RawResponse）。"""

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
