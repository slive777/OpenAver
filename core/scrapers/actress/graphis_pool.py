"""Graphis 池純規則（185-T1）：名字比對、網址白名單、候選 id、exclude 解析、挑選。

無 I/O、無全域狀態。
"""
import hashlib
import re

_BASE = "https://data.graphis.ne.jp/free/model/"
_EXCLUDE_TOKEN_RE = re.compile(r"^[0-9a-f]{8}$")
_EXCLUDE_MAX = 500


def match_entries(pairs, names):
    """回傳 jp_name 與 names 任一完全相同的 entry_id（依原順序、去重）。"""
    seen = set()
    out = []
    for entry_id, jp_name in pairs:
        if jp_name in names and entry_id not in seen:
            seen.add(entry_id)
            out.append(entry_id)
    return out


def entry_base_urls(entry_id):
    return [f"{_BASE}{entry_id}/prof.jpg", f"{_BASE}{entry_id}/model.jpg"]


def is_collectible_url(url, entry_id):
    if url in entry_base_urls(entry_id):
        return True
    pat = rf"^{re.escape(_BASE)}{re.escape(entry_id)}/photo/\d{{3}}/pic\.jpg$"
    return re.match(pat, url) is not None


def candidate_id(url):
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]


def parse_exclude(raw):
    """只收前 500 個合法 8-hex token；永不拋例外。"""
    out = set()
    if not raw or not isinstance(raw, str):
        return out
    n = 0
    for tok in raw.split(","):
        tok = tok.strip()
        if _EXCLUDE_TOKEN_RE.match(tok):
            out.add(tok)
            n += 1
            if n >= _EXCLUDE_MAX:
                break
    return out


def select_next(pool, exclude_ids, k):
    return [u for u in pool if candidate_id(u) not in exclude_ids][:k]
