"""
TASK-80a-T2: get_lan_ip() 單元測試

驗證 web/lan_listener.get_lan_ip() helper（canonical location）：
  - 正常路徑：回傳非空字串（區網 IP）
  - 失敗路徑：socket.connect 拋例外 → 回傳 None（不 throw，不空字串）

web.app re-exports get_lan_ip from web.lan_listener for backward compatibility;
tests import from the canonical location (web.lan_listener) and also verify the
re-export works.
"""
import socket


def test_get_lan_ip_returns_string_or_none():
    """
    在正常環境下 get_lan_ip() 應回傳非空字串（或 None 若無網路）。
    本測試允許兩種情況，確保不拋例外。
    """
    from web.lan_listener import get_lan_ip
    result = get_lan_ip()
    if result is not None:
        assert isinstance(result, str), f"get_lan_ip() 應回傳 str，得到 {type(result)}"
        assert len(result) > 0, "get_lan_ip() 回傳空字串（應回傳 None 而非空字串）"


def test_get_lan_ip_reexported_from_web_app():
    """web.app re-exports get_lan_ip from web.lan_listener（backward compat）。"""
    from web.app import get_lan_ip as app_fn
    from web.lan_listener import get_lan_ip as ll_fn
    assert app_fn is ll_fn, "web.app.get_lan_ip 應是 web.lan_listener.get_lan_ip 的 re-export"


def test_get_lan_ip_returns_none_on_socket_error(monkeypatch):
    """
    socket.connect 拋出例外時 get_lan_ip() 回傳 None（不重拋、不回空字串）。
    """
    import web.lan_listener as _ll_mod
    from web.lan_listener import get_lan_ip

    class _FailSocket:
        def __init__(self, *args, **kwargs):
            pass

        def connect(self, *args, **kwargs):
            raise OSError("simulated network failure")

        def close(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(_ll_mod.socket, "socket", _FailSocket)

    result = get_lan_ip()
    assert result is None, (
        f"socket 失敗時 get_lan_ip() 應回傳 None，得到 {result!r}"
    )


def test_get_lan_ip_no_exception_propagated(monkeypatch):
    """
    任何 Exception 都不應傳出 get_lan_ip()（含非 OSError 例外）。
    """
    import web.lan_listener as _ll_mod
    from web.lan_listener import get_lan_ip

    class _BustedSocket:
        def __init__(self, *args, **kwargs):
            pass

        def connect(self, *args, **kwargs):
            raise RuntimeError("unexpected failure")

        def close(self):
            pass

    monkeypatch.setattr(_ll_mod.socket, "socket", _BustedSocket)

    # 不應 raise
    result = get_lan_ip()
    assert result is None


def test_get_lan_ip_closes_socket_on_error(monkeypatch):
    """
    socket.connect 拋例外後，socket.close() 仍應被呼叫（finally 保證）。
    """
    import web.lan_listener as _ll_mod
    from web.lan_listener import get_lan_ip

    close_called = {"n": 0}

    class _TrackSocket:
        def __init__(self, *args, **kwargs):
            pass

        def connect(self, *args, **kwargs):
            raise OSError("simulated")

        def close(self):
            close_called["n"] += 1

    monkeypatch.setattr(_ll_mod.socket, "socket", _TrackSocket)

    get_lan_ip()
    assert close_called["n"] == 1, (
        f"socket.close() 應被呼叫 1 次，實際 {close_called['n']} 次"
    )
