"""自訂來源：hosts 基底規則（detail_host_allowed）、模板 www 載入、public_url（純函式，全離線）。"""

import dataclasses

import pytest

from core.custom_source import schema
from core.custom_source.schema import detail_host_allowed
from core.custom_source.urls import public_url
from tests.unit._custom_source_pages import FIXTURE_DIR


def _spec_with_base(base):
    spec = schema.load_file(FIXTURE_DIR / "single-og.yaml")
    return dataclasses.replace(spec, hosts=(base,))


@pytest.mark.parametrize("base, url, allowed", [
    ("a.example", "https://a.example/x", True),
    ("a.example", "https://www.a.example/x", True),
    ("a.example", "https://video.a.example/x", True),
    ("a.example", "HTTPS://A.Example:8443/x", True),
    ("a.example", "https://www.a.example:8443/x?id=1", True),
    ("a.example", "https://nota.example/x", False),
    ("a.example", "https://a.example.evil.test/x", False),
    ("a.example", "https://a.example@evil.test/", False),
    ("a.example", "https://other.test/x", False),
    ("b.example", "https://a.example/x", False),
    ("a.example", "file:///x", False),
    ("a.example", "http://[::1", False),
    ("a.example", "", False),
])
def test_host_rule_table(base, url, allowed):
    assert detail_host_allowed(_spec_with_base(base), url) is allowed


def test_www_template_loads_as_base_host():
    text = (FIXTURE_DIR / "single-og.yaml").read_text(encoding="utf-8")
    assert text.count("https://single-og.example/") == 1
    raw = text.replace("https://single-og.example/", "https://WWW.Single-OG.example/").encode("utf-8")
    spec, _digest = schema.load_bytes(raw, "single-og")
    assert spec.hosts == ("single-og.example",)
    assert detail_host_allowed(spec, "https://single-og.example/x") is True
    assert detail_host_allowed(spec, "https://notsingle-og.example/x") is False


@pytest.mark.parametrize("url, expected", [
    ("https://u:p@x.example/a?id=1", "https://x.example/a?id=1"),
    ("https://x.example/a?id=1", "https://x.example/a?id=1"),
    ("https://u:p%40q@x.example:8443/a", "https://x.example:8443/a"),
    ("https://x.example/a?mail=a@b", "https://x.example/a?mail=a@b"),
    ("https://u:p@[2001:db8::1]:8080/a#frag", "https://[2001:db8::1]:8080/a#frag"),
    ("https://user@x.example/", "https://x.example/"),
    ("http://[::1", ""),
])
def test_public_url_table(url, expected):
    assert public_url(url) == expected
