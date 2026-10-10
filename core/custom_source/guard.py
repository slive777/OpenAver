"""自訂來源的請求目標守衛：只放行公網位址（fail-closed）。"""

import ipaddress
import socket
from urllib.parse import urlparse

from urllib3.util import parse_url

from core.custom_source.errors import BlockedTarget

GUARD_REASONS = frozenset({"bad_scheme", "bad_url", "bad_host", "bad_authority", "non_ascii_host", "non_public", "unresolvable"})

_BLOCKED_NAME_SUFFIXES = (".localhost", ".local", ".internal")


def resolve_host(host):
    """主機名 → 位址字串列表（去 %scope、去重、保序）；任何解析失敗回 []。"""
    try:
        infos = socket.getaddrinfo(host, None)
    except (OSError, UnicodeError):
        return []
    seen = []
    for info in infos:
        text = str(info[4][0]).split("%", 1)[0]
        if text not in seen:
            seen.append(text)
    return seen


def _is_public(addr):
    addr = getattr(addr, "ipv4_mapped", None) or addr
    return addr.is_global and not addr.is_multicast


def _blocked_name(host):
    name = host.rstrip(".").lower()
    return name == "localhost" or name.endswith(_BLOCKED_NAME_SUFFIXES)


def _authority(url):
    rest = url.split("://", 1)[-1]
    for i, ch in enumerate(rest):
        if ch in "/?#":
            return rest[:i]
    return rest


def _connect_host_differs(url, host):
    """守衛判斷的 host 必須與 urllib3（requests 實際連線者）讀到的一致；解析例外視為不一致。"""
    try:
        other = parse_url(url).host
    except Exception:
        return True
    return (other or "").strip("[]").lower() != host.strip("[]").lower()


def check(url):
    """通過回 None；違規拋 BlockedTarget。訊息為固定文字，不含 URL 任何部分。"""
    try:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        host = parsed.hostname
        parsed.port  # noqa: B018 - 存取時才驗證範圍
    except (ValueError, AttributeError, TypeError):
        raise BlockedTarget("bad_url", "網址格式不正確") from None
    if scheme not in ("http", "https"):
        raise BlockedTarget("bad_scheme", "只允許 http／https")
    if not host:
        raise BlockedTarget("bad_host", "網址沒有主機名稱")
    if not host.isascii():
        raise BlockedTarget("non_ascii_host", "主機名稱含非 ASCII 字元，請改用 punycode（xn--）")
    if "\\" in _authority(url) or _connect_host_differs(url, host):
        raise BlockedTarget("bad_authority", "網址的主機段格式不正確")
    if _blocked_name(host):
        raise BlockedTarget("bad_host", "不允許的主機名稱")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if not _is_public(literal):
            raise BlockedTarget("non_public", "目標不是公網位址")
        return None
    resolved = resolve_host(host)
    if not resolved:
        raise BlockedTarget("unresolvable", "無法解析目標主機")
    for text in resolved:
        try:
            addr = ipaddress.ip_address(text)
        except ValueError:
            raise BlockedTarget("unresolvable", "無法解析目標主機") from None
        if not _is_public(addr):
            raise BlockedTarget("non_public", "目標不是公網位址")
    return None
