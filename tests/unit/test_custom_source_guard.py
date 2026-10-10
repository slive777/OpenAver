"""自訂來源位址守衛：站方導向內網／組播位址時，請求不得發出。"""

import socket

import pytest

from core.custom_source import guard
from core.custom_source.errors import BlockedTarget

_REAL_RESOLVE_HOST = guard.resolve_host


@pytest.fixture(autouse=True)
def _public_dns(monkeypatch):
    monkeypatch.setattr("core.custom_source.guard.resolve_host", lambda host: ["8.8.8.8"])


# (url, 期望 reason；None＝放行)
TRUTH_TABLE = [
    ("http://127.0.0.1/", "non_public"),
    ("http://10.0.0.5/", "non_public"),
    ("http://192.168.1.1/", "non_public"),
    ("http://172.16.0.1/", "non_public"),
    ("http://169.254.169.254/", "non_public"),
    ("http://100.64.0.1/", "non_public"),
    ("http://0.0.0.0/", "non_public"),
    ("http://224.0.0.1/", "non_public"),
    ("http://[::1]/", "non_public"),
    ("http://[fe80::1]/", "non_public"),
    ("http://[fc00::1]/", "non_public"),
    ("http://[ff02::1]/", "non_public"),
    ("http://[::ffff:100.64.0.1]/", "non_public"),
    ("http://[::ffff:224.0.0.1]/", "non_public"),
    ("http://[::ffff:127.0.0.1]/", "non_public"),
    ("http://[::]/", "non_public"),
    ("http://[::ffff:192.168.1.1]/", "non_public"),
    ("http://faß.example/", "non_ascii_host"),
    ("http://xn--fa-hia.example/", None),
    ("http://localhost/", "bad_host"),
    ("http://LOCALHOST./", "bad_host"),
    ("http://x.localhost/", "bad_host"),
    ("http://nas.local/", "bad_host"),
    ("http://svc.internal/", "bad_host"),
    ("ftp://example.com/", "bad_scheme"),
    ("file:///etc/passwd", "bad_scheme"),
    ("http:///x", "bad_host"),
    ("http://[::1", "bad_url"),
    ("http://example.com:99999/", "bad_url"),
    ("http://8.8.8.8/", None),
    ("https://1.1.1.1/", None),
    ("http://[2606:4700:4700::1111]/", None),
    ("http://[::ffff:8.8.8.8]/", None),
    ("https://example.com/path?q=1", None),
]


@pytest.mark.parametrize("url,reason", TRUTH_TABLE)
def test_guard_truth_table(url, reason):
    if reason is None:
        assert guard.check(url) is None
        return
    with pytest.raises(BlockedTarget) as ei:
        guard.check(url)
    assert ei.value.reason == reason
    assert reason in guard.GUARD_REASONS


@pytest.mark.parametrize("resolved,reason", [
    (["10.0.0.5"], "non_public"),
    (["8.8.8.8", "10.0.0.5"], "non_public"),
    (["224.0.0.1"], "non_public"),
    ([], "unresolvable"),
    (["not-an-ip"], "unresolvable"),
])
def test_domain_resolving_to_non_public_is_blocked(monkeypatch, resolved, reason):
    monkeypatch.setattr("core.custom_source.guard.resolve_host", lambda host: resolved)
    with pytest.raises(BlockedTarget) as ei:
        guard.check("http://example.com/")
    assert ei.value.reason == reason


def test_domain_resolving_to_public_passes(monkeypatch):
    monkeypatch.setattr("core.custom_source.guard.resolve_host", lambda host: ["8.8.8.8", "1.1.1.1"])
    assert guard.check("https://example.com/") is None


def test_blocked_message_leaks_no_credentials_or_query():
    with pytest.raises(BlockedTarget) as ei:
        guard.check("http://user:pw@127.0.0.1/x?token=1")
    text = str(ei.value) + ei.value.message + repr(ei.value)
    for secret in ("pw", "token", "user", "127.0.0.1", "/x"):
        assert secret not in text


def test_real_resolve_host_failure_returns_empty(monkeypatch):
    def boom(*a, **k):
        raise OSError("dns down")
    monkeypatch.setattr(socket, "getaddrinfo", boom)
    assert _REAL_RESOLVE_HOST("example.com") == []

    def bad_label(*a, **k):
        raise UnicodeError("label too long")
    monkeypatch.setattr(socket, "getaddrinfo", bad_label)
    assert _REAL_RESOLVE_HOST("example.com") == []


def test_real_resolve_host_strips_scope_and_dedupes(monkeypatch):
    infos = [
        (0, 0, 0, "", ("fe80::1%eth0", 0, 0, 0)),
        (0, 0, 0, "", ("fe80::1", 0, 0, 0)),
        (0, 0, 0, "", ("8.8.8.8", 0)),
    ]
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: infos)
    assert _REAL_RESOLVE_HOST("example.com") == ["fe80::1", "8.8.8.8"]
