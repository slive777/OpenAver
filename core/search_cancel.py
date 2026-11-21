"""搜尋取消閘：舊搜尋被取消後，不再對任何來源送出新請求。

實作方式是全域包住兩個第三方函式庫的送出方法（``requests.Session.send``、
``curl_cffi.requests.Session.request``），在呼叫原函式之前先跑 ``checkpoint()``，
旗標已 set 就拋 ``SearchCancelled``（零位元組送出）；未綁定、或綁定但旗標未 set
時，原樣轉呼叫（參數、回傳值、原函式拋的例外都不動）。

安裝只在首次 ``bound()`` 進入時做一次（冪等、帶鎖）；沒用到串流搜尋的行程，
類別方法完全沒被包到，行為零變化。
"""
from __future__ import annotations

import contextlib
import contextvars
import functools
import threading


class SearchCancelled(BaseException):
    pass


_current: contextvars.ContextVar = contextvars.ContextVar("search_cancel_event", default=None)

_gates_installed = False

_gates_lock = threading.Lock()


def _make_requests_gate(orig):
    @functools.wraps(orig)
    def wrapper(self, *args, **kwargs):
        checkpoint()  # gate: requests.Session.send
        return orig(self, *args, **kwargs)

    return wrapper


def _make_curl_cffi_gate(orig):
    @functools.wraps(orig)
    def wrapper(self, *args, **kwargs):
        checkpoint()  # gate: curl_cffi.requests.Session.request
        return orig(self, *args, **kwargs)

    return wrapper


def install_gates() -> None:
    global _gates_installed
    if _gates_installed:
        return
    with _gates_lock:
        if _gates_installed:
            return
        import requests

        requests.Session.send = _make_requests_gate(requests.Session.send)
        try:
            import curl_cffi.requests as cffi_requests
        except ImportError:
            cffi_requests = None
        if cffi_requests is not None:
            orig_request = getattr(cffi_requests.Session, "request", None)
            if orig_request is not None:
                cffi_requests.Session.request = _make_curl_cffi_gate(orig_request)
        _gates_installed = True


def current() -> threading.Event | None:
    return _current.get()


@contextlib.contextmanager
def bound(event: threading.Event):
    install_gates()
    token = _current.set(event)
    try:
        yield event
    finally:
        _current.reset(token)


def checkpoint() -> None:
    event = _current.get()
    if event is not None and event.is_set():
        raise SearchCancelled()


def submit(pool, fn, *args, **kwargs):
    ctx = contextvars.copy_context()
    return pool.submit(ctx.run, fn, *args, **kwargs)
