"""
core/metatube/validation.py

SSRF URL validator for the metatube connect endpoint (US5).

Public API
----------
validate_metatube_url(url, allow_lan=False) -> str | None
    Returns None when the URL passes all checks.
    Returns a fixed Chinese error string when the URL is blocked.
"""

import ipaddress
import socket
from urllib.parse import urlparse

from core.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Fixed user-facing error strings (Chinese, no internal detail leaked)
# ---------------------------------------------------------------------------

_ERR_SCHEME = "網址格式不支援，請使用 http 或 https。"
_ERR_EMPTY_HOST = "網址缺少主機名稱，請確認輸入是否正確。"
_ERR_LOCALHOST = "不允許連線至本機迴路位址。"
_ERR_DOT_LOCAL = "不允許連線至 mDNS（.local）位址。"
_ERR_LOOPBACK = "不允許連線至迴路位址。"
_ERR_LINK_LOCAL = "不允許連線至鏈路本地位址。"
_ERR_PRIVATE = "不允許連線至私有網路位址（請開啟「允許區域網路」選項）。"
_ERR_RESOLVE = "無法解析主機名稱，連線已拒絕。"


# ---------------------------------------------------------------------------
# Internal IP classification helper
# ---------------------------------------------------------------------------

def _classify_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address, allow_lan: bool) -> str | None:
    """
    Return an error string if the IP is blocked, or None if it passes.

    Loopback and link-local are ALWAYS blocked regardless of allow_lan.
    Private (RFC1918 / fc00::/7) is blocked only when allow_lan=False.
    """
    if ip.is_loopback:
        return _ERR_LOOPBACK
    if ip.is_link_local:
        return _ERR_LINK_LOCAL
    if ip.is_private:
        if not allow_lan:
            return _ERR_PRIVATE
    return None


# ---------------------------------------------------------------------------
# Public validator
# ---------------------------------------------------------------------------

def validate_metatube_url(url: str, allow_lan: bool = False) -> str | None:
    """
    Validate *url* against SSRF rules.

    Returns
    -------
    None
        URL passes all checks — safe to connect.
    str
        A fixed Chinese error message describing why the URL is blocked.
        The returned string never contains the raw hostname or IP.
    """
    # Step 1: scheme check
    try:
        parsed = urlparse(url)
    except Exception:
        logger.exception("urlparse failed for input")
        return _ERR_SCHEME

    if parsed.scheme not in ("http", "https"):
        logger.info("Blocked: invalid scheme '%s'", parsed.scheme)
        return _ERR_SCHEME

    # Step 2: host must be present
    host = parsed.hostname  # urlparse strips brackets from IPv6 literals
    if not host:
        logger.info("Blocked: empty host")
        return _ERR_EMPTY_HOST

    host_lower = host.lower()

    # Step 3: localhost / *.localhost — ALWAYS block, before ip_address attempt
    if host_lower == "localhost" or host_lower.endswith(".localhost"):
        logger.info("Blocked: localhost alias")
        return _ERR_LOCALHOST

    # Step 4: .local mDNS — always block
    if host_lower.endswith(".local"):
        logger.info("Blocked: .local mDNS")
        return _ERR_DOT_LOCAL

    # Step 5: try to parse as IP literal
    try:
        ip = ipaddress.ip_address(host)
        # It IS an IP literal — classify directly
        err = _classify_ip(ip, allow_lan)
        if err:
            logger.info("Blocked IP literal: %s", err)
            return err
        # Public IP literal — pass
        return None
    except ValueError:
        pass  # Not an IP literal — fall through to DNS resolution

    # Step 6: hostname — resolve and check every returned address
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        logger.exception("getaddrinfo failed for host (blocked)")
        return _ERR_RESOLVE

    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            logger.info("Could not parse resolved address, blocking conservatively")
            return _ERR_RESOLVE
        err = _classify_ip(ip, allow_lan)
        if err:
            logger.info("Blocked via DNS resolution: %s", err)
            return err

    # Step 7: all resolved addresses passed
    return None
