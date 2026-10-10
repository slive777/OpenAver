"""自訂來源的網址整理：對外顯示／寫入前去掉帳密。"""
from urllib.parse import urlsplit


def public_url(url):
    """去掉 user:pass@，其餘（含 query）原樣保留；解析失敗回空字串。"""
    try:
        parts = urlsplit(url)
        host = parts.hostname
        port = parts.port
    except ValueError:
        return ""
    if not host:
        return ""
    shown = f"[{host}]" if ":" in host else host
    netloc = shown if port is None else f"{shown}:{port}"
    out = f"{parts.scheme}://{netloc}{parts.path}"
    if parts.query:
        out += "?" + parts.query
    if parts.fragment:
        out += "#" + parts.fragment
    return out
