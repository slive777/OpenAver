"""自訂來源的請求目標守衛：只放行公網位址（fail-closed）。"""

import ipaddress
import socket
from urllib.parse import urlparse

from core.custom_source.errors import BlockedTarget

GUARD_REASONS = frozenset({"bad_scheme", "bad_url", "bad_host", "non_ascii_host", "non_public", "unresolvable"})

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
