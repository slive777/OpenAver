from __future__ import annotations

import contextlib
import contextvars
import threading


class SearchCancelled(BaseException):
    pass


_current: contextvars.ContextVar = contextvars.ContextVar("search_cancel_event", default=None)

_gates_installed = False


def install_gates() -> None:
    global _gates_installed
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
