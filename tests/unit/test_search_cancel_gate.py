"""TASK-204-T2a：requests／curl_cffi 取消閘的守衛測試。"""
import threading

import pytest

import requests

import curl_cffi.requests as cffi_requests

from core import search_cancel

URL = "http://127.0.0.1:9/x"


def test_requests_gate_blocks_new_request_after_cancel(monkeypatch):
    calls = []
    placeholder = object()
    event = threading.Event()

    def fake_send(self, *args, **kwargs):
        calls.append((args, kwargs))
        event.set()
        return placeholder

    monkeypatch.setattr(requests.Session, "send", fake_send)
    monkeypatch.setattr(search_cancel, "_gates_installed", False)
    search_cancel.install_gates()

    sess = requests.Session()
    with search_cancel.bound(event):
        first = sess.get(URL, timeout=3)
        assert first is placeholder
        assert len(calls) >= 1
        with pytest.raises(search_cancel.SearchCancelled) as ei:
            sess.get(URL, timeout=3)
        assert not isinstance(ei.value, Exception)
        assert len(calls) == 1


def test_curl_cffi_gate_blocks_new_request_after_cancel(monkeypatch):
    calls = []
    placeholder = object()
    event = threading.Event()

    def fake_request(self, *args, **kwargs):
        calls.append((args, kwargs))
        event.set()
        return placeholder

    monkeypatch.setattr(cffi_requests.Session, "request", fake_request)
    monkeypatch.setattr(search_cancel, "_gates_installed", False)
    search_cancel.install_gates()

    with search_cancel.bound(event):
        first = cffi_requests.get(URL, impersonate="chrome120", timeout=3)
        assert first is placeholder
        assert len(calls) >= 1
        with pytest.raises(search_cancel.SearchCancelled) as ei:
            cffi_requests.get(URL, impersonate="chrome120", timeout=3)
        assert not isinstance(ei.value, Exception)
        assert len(calls) == 1


def test_gates_pass_through_when_unbound_or_not_cancelled(monkeypatch):
    req_calls = []
    cffi_calls = []
    req_placeholder = object()
    cffi_placeholder = object()
    req_mode = {"exc": None}
    cffi_mode = {"exc": None}

    def fake_send(self, *args, **kwargs):
        req_calls.append((args, kwargs))
        if req_mode["exc"] is not None:
            raise req_mode["exc"]
        return req_placeholder

    def fake_request(self, *args, **kwargs):
        cffi_calls.append((args, kwargs))
        if cffi_mode["exc"] is not None:
            raise cffi_mode["exc"]
        return cffi_placeholder

    monkeypatch.setattr(requests.Session, "send", fake_send)
    monkeypatch.setattr(cffi_requests.Session, "request", fake_request)
    monkeypatch.setattr(search_cancel, "_gates_installed", False)
    search_cancel.install_gates()

    assert requests.Session.send is not fake_send
    assert cffi_requests.Session.request is not fake_request

    sess = requests.Session()
    assert sess.get(URL, timeout=3) is req_placeholder
    assert len(req_calls) >= 1
    assert req_calls[0][1]["timeout"] == 3
    assert req_calls[0][0][0].url == URL

    sentinel_prep = object()
    assert requests.Session.send(sess, sentinel_prep, timeout=9) is req_placeholder
    assert req_calls[-1][0][0] is sentinel_prep
    assert req_calls[-1][1] == {"timeout": 9}

    boom_req = RuntimeError("boom-req")
    req_mode["exc"] = boom_req
    try:
        with pytest.raises(RuntimeError) as ei:
            sess.get(URL, timeout=3)
        assert ei.value is boom_req
    finally:
        req_mode["exc"] = None

    assert cffi_requests.get(URL, impersonate="chrome120", timeout=3) is cffi_placeholder
    assert len(cffi_calls) >= 1
    assert cffi_calls[0][1]["method"] == "GET"
    assert cffi_calls[0][1]["url"] == URL
    assert cffi_calls[0][1]["timeout"] == 3
    assert cffi_calls[0][1]["impersonate"] == "chrome120"

    assert cffi_requests.Session.request(object(), "POST", URL, timeout=5) is cffi_placeholder
    assert cffi_calls[-1][0] == ("POST", URL)
    assert cffi_calls[-1][1] == {"timeout": 5}

    boom_cffi = RuntimeError("boom-cffi")
    cffi_mode["exc"] = boom_cffi
    try:
        with pytest.raises(RuntimeError) as ei2:
            cffi_requests.get(URL, impersonate="chrome120", timeout=3)
        assert ei2.value is boom_cffi
    finally:
        cffi_mode["exc"] = None

    installed_send = requests.Session.send
    installed_request = cffi_requests.Session.request
    search_cancel.install_gates()
    assert requests.Session.send is installed_send
    assert cffi_requests.Session.request is installed_request
