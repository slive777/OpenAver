"""Graphis 照片池（185）：T1 純規則（名字比對、網址白名單、候選 id、exclude、挑選）＋
T2 抓取層（搜尋／條目頁快取、池組裝、目前那張的大小比對、時間預算）。
"""
import hashlib
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from core.database.alias import AliasRepository
from core.logger import get_logger
from core.proxy_policy import proxy_kwargs

logger = get_logger(__name__)

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


# ---- T2：抓取層 ----

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
_TTL = 3600
_LIMITS = (128, 256)
_K = 6
_LOCK = threading.Lock()
_SEARCH_CACHE = {}  # query -> (ts, [(entry_id, jp_name)])，只存成功（含 0 條目）
_ENTRY_CACHE = {}   # entry_id -> (ts, [photo_url])，條目頁失敗不存
_PROF_RE = re.compile(r"/model/([^/]+)/prof\.jpg")


def _now():
    return time.time()


def _remaining(deadline, cap):
    return min(cap, deadline - _now())


def _cache_get(cache, key):
    """純讀；過期視為沒有（清理只在寫入端）。"""
    with _LOCK:
        hit = cache.get(key)
    if hit and _now() - hit[0] < _TTL:
        return hit[1]
    return None


def _cache_put(cache, key, value):
    limit = _LIMITS[0] if cache is _SEARCH_CACHE else _LIMITS[1]
    now = _now()
    with _LOCK:
        for k in [k for k, v in cache.items() if now - v[0] >= _TTL]:
            del cache[k]
        while len(cache) >= limit and key not in cache:
            del cache[min(cache, key=lambda k: cache[k][0])]
        cache[key] = (now, value)


def _search_entries(query, timeout):
    """回 [(entry_id, jp_name)]；成功但 0 條目回 []；失敗（網路／配對長度不等）回 None。"""
    try:
        resp = requests.get(f"https://graphis.ne.jp/monthly/?K={quote(query)}", headers=_UA,
                            timeout=timeout, **proxy_kwargs('actress'))
        resp.raise_for_status()
    except requests.RequestException:
        return None
    soup = BeautifulSoup(resp.text, 'html.parser')
    imgs = soup.select('div.gp-model-box ul li a img')
    names = [e.get_text(strip=True) for e in soup.select('li.name-jp span')]
    if len(imgs) != len(names):
        return None
    out = []
    for img, name in zip(imgs, names, strict=True):
        m = _PROF_RE.search(img.get('src', ''))
        if m:
            out.append((m.group(1), name))
    return out


def _fetch_entry_photos(entry_id, timeout):
    """回條目頁上通過白名單的圖；失敗回 None。"""
    try:
        resp = requests.get(f"https://graphis.ne.jp/monthly/model.php?ID={quote(entry_id)}",
                            headers=_UA, timeout=timeout, **proxy_kwargs('actress'))
        resp.raise_for_status()
    except requests.RequestException:
        return None
    soup = BeautifulSoup(resp.text, 'html.parser')
    urls = (img.get('src', '') for img in soup.find_all('img'))
    return list(dict.fromkeys(u for u in urls if is_collectible_url(u, entry_id)))


def _head_content_length(url, timeout):
    try:
        resp = requests.head(url, headers=_UA, timeout=timeout, allow_redirects=False,
                             **proxy_kwargs('actress'))
        return int(resp.headers["Content-Length"])
    except (requests.RequestException, KeyError, ValueError):
        return None


def _names_for(person_key, query_name):
    return AliasRepository().resolve(person_key) | {person_key, query_name}


def _local_photo_size(person_key):
    from core.actress_photo import get_local_photo_path
    path = get_local_photo_path(person_key)
    return path.stat().st_size if path else None


def _live_search(query, deadline):
    timeout = _remaining(deadline, 2.5)
    if timeout <= 0:
        return None
    pairs = _search_entries(query, timeout)
    if pairs is not None:
        _cache_put(_SEARCH_CACHE, query, pairs)
    return pairs


def _load_entry(entry_id, timeout):
    photos = _fetch_entry_photos(entry_id, timeout)
    if photos is not None:
        _cache_put(_ENTRY_CACHE, entry_id, photos)
    return photos


def _parallel(fn, items, timeout, workers=6):
    """並行跑 fn(item)；逾時未完成的丟給背景（不取消），回 {item: 結果}（只含已完成）。"""
    if not items or timeout <= 0:
        return {}
    ex = ThreadPoolExecutor(max_workers=workers)
    futs = {ex.submit(fn, it): it for it in items}
    done, _ = wait(futs, timeout=timeout)
    ex.shutdown(wait=False)
    return {futs[f]: f.result() for f in done if f.exception() is None}


def _assemble_pool(query_name, names, deadline, rng):
    """None＝搜尋失敗；否則為隨機排序後的 URL 池（URL 唯一）。"""
    search_names = [query_name, *sorted(names - {query_name})]
    entry_ids = []
    for name in search_names:
        pairs = _cache_get(_SEARCH_CACHE, name)
        if pairs is None and name == query_name:
            pairs = _live_search(name, deadline)
            if pairs is None:
                return None
        entry_ids.extend(match_entries(pairs or [], names))
    entry_ids = list(dict.fromkeys(entry_ids))
    missing = [e for e in entry_ids if _cache_get(_ENTRY_CACHE, e) is None]
    t = _remaining(deadline, 3.0)
    _parallel(lambda e: _load_entry(e, max(t, 0.1)), missing, t)
    pool = []
    for e in entry_ids:
        pool += dict.fromkeys(entry_base_urls(e) + (_cache_get(_ENTRY_CACHE, e) or []))
    return rng.sample(pool, len(pool))


def _resolve_current_excluded(picks, size, deadline):
    """HEAD 的 Content-Length 等於目前那張大小者 → 其 candidate_id；任何失敗不排除。"""
    t = _remaining(deadline, 2.0)
    lengths = _parallel(lambda u: _head_content_length(u, max(t, 0.1)), picks, t)
    return {candidate_id(u) for u, n in lengths.items() if n == size}


def _select_excluding_current(pool, exclude_ids, person_key, deadline):
    exclude = set(exclude_ids)
    picks = select_next(pool, exclude, _K)
    try:
        size = _local_photo_size(person_key) if _remaining(deadline, 1) > 0 else None
    except OSError:
        size = None
    for _ in range(2 if size else 0):
        if _remaining(deadline, 1) <= 0:
            break
        hits = _resolve_current_excluded(picks, size, deadline)
        if not hits:
            break
        exclude |= hits
        picks = select_next(pool, exclude, _K)
    return picks


def graphis_candidates(person_key, query_name, photo_source, exclude_ids, *, budget_s=4.0, rng=None):
    """最多 6 個 Graphis 候選 URL；任何失敗回 []（不丟）。"""
    try:
        deadline = _now() + budget_s
        try:
            names = _names_for(person_key, query_name) if _remaining(deadline, 1) > 0 else None
        except Exception as e:
            logger.warning(f"[graphis_pool] alias resolve failed: {e}")
            names = None
        names = names or {person_key, query_name}
        pool = _assemble_pool(query_name, names, deadline, rng or random.Random())
        if not pool:
            return []
        if photo_source != 'graphis':
            return select_next(pool, exclude_ids, _K)
        return _select_excluding_current(pool, exclude_ids, person_key, deadline)
    except Exception as e:
        logger.warning(f"[graphis_pool] candidates failed for {person_key}: {e}")
        return []
