"""
女優爬蟲 Orchestrator — 四來源並行抓取（Phase 42b T3）

Routes:
    C1 text  : Minnano → Wikipedia → Graphis → None
    C2 parallel: minnano + wiki + graphis + gfriends (max_workers=4, 5s budget)
    C3 photo : Graphis prof_url → gfriends URL → Wiki photo_url → Minnano photo_url → None
    C4 return: nested new fields + legacy flat shortcuts
    TD-1     : current_age computed from text.birth, never read from source
"""

from datetime import datetime
from typing import Optional, Dict

from core.logger import get_logger

logger = get_logger(__name__)

# Cache 結構（模組層級變數）
_cache = {}          # key: str (正規化女優名), value: dict (profile + timestamp)
_CACHE_TTL = 3600    # 1 小時


def _normalize_name(name: str) -> str:
    """正規化女優名稱（用於 cache key）"""
    import unicodedata
    name = name.strip()
    # 全形 → 半形
    name = unicodedata.normalize('NFKC', name)
    # 統一空白符
    name = ' '.join(name.split())
    return name


def _compute_age_from_birth(birth: Optional[str]) -> Optional[int]:
    """Compute current age from birth 'YYYY-MM-DD'. Returns None if birth missing/invalid."""
    if not birth:
        return None
    try:
        birth_date = datetime.strptime(birth, '%Y-%m-%d')
    except (ValueError, TypeError):
        return None
    today = datetime.now()
    age = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        age -= 1
    return age


def get_actress_profile(name: str, makers: list = None) -> Optional[Dict]:
    """
    取得女優完整資料（minnano + wiki + graphis + gfriends 四來源並行）

    Phase 42b T3: 4-route parallel with C1 cascade, C4 mixed return shape, TD-1 age fix.

    Args:
        name: 女優名稱（日文）
        makers: 片商名稱列表（從搜尋結果統計，用於 gfriends 查表）

    Returns:
        C4 mixed shape dict (nested new fields + legacy flat shortcuts), or None if all sources miss.
    """
    import time
    from concurrent.futures import ThreadPoolExecutor
    from core.scrapers.actress.minnano_av import scrape_minnano_av
    from core.scrapers.actress.wiki_ja import scrape_wiki_ja
    from core.scrapers.actress.graphis import scrape_graphis_photo
    from core.scrapers.actress.gfriends import lookup_gfriends

    # Cache 檢查
    cache_key = _normalize_name(name)
    if cache_key in _cache:
        cached = _cache[cache_key]
        if time.time() - cached['timestamp'] < _CACHE_TTL:
            return cached['data']
        else:
            del _cache[cache_key]  # 過期清理

    # 並行抓取（4 routes，嚴格 5s 上限，shutdown 不等待背景執行緒）
    executor = ThreadPoolExecutor(max_workers=4)
    minnano_future  = executor.submit(scrape_minnano_av, name)
    wiki_future     = executor.submit(scrape_wiki_ja, name)
    graphis_future  = executor.submit(scrape_graphis_photo, name)
    gfriends_future = executor.submit(lookup_gfriends, name, makers)

    start = time.time()

    try:
        minnano_result = minnano_future.result(timeout=5)
    except Exception:
        minnano_result = None

    remaining = max(0, 5 - (time.time() - start))
    try:
        wiki_result = wiki_future.result(timeout=remaining)
    except Exception:
        wiki_result = None

    remaining = max(0, 5 - (time.time() - start))
    try:
        graphis_result = graphis_future.result(timeout=remaining)
    except Exception:
        graphis_result = None

    remaining = max(0, 5 - (time.time() - start))
    try:
        gfriends_url = gfriends_future.result(timeout=remaining)
    except Exception:
        gfriends_url = None

    executor.shutdown(wait=False)

    # Edge case: all routes returned nothing
    if not any([minnano_result, wiki_result, graphis_result, gfriends_url]):
        return None

    # C1 — text primary source cascade: Minnano → Wikipedia → Graphis → None
    if minnano_result:
        primary_text_source = "minnano"
        text = minnano_result
    elif wiki_result:
        primary_text_source = "wiki"
        text = wiki_result
    elif graphis_result:
        primary_text_source = "graphis"
        text = graphis_result
    else:
        primary_text_source = None
        text = None

    # Photo cascade (decoupled from text):
    # Graphis prof_url → gfriends URL → Wiki photo_url → Minnano photo_url → None
    if graphis_result and graphis_result.get("prof_url"):
        photo_url, photo_source = graphis_result["prof_url"], "graphis"
    elif gfriends_url:
        photo_url, photo_source = gfriends_url, "gfriends"
    elif wiki_result and wiki_result.get("photo_url"):
        photo_url, photo_source = wiki_result["photo_url"], "wiki"
    elif minnano_result and minnano_result.get("photo_url"):
        photo_url, photo_source = minnano_result["photo_url"], "minnano"
    else:
        photo_url, photo_source = None, None

    # Backdrop: Graphis only
    backdrop_url = (graphis_result or {}).get("backdrop_url")

    # TD-1: compute current age from birth — never read stale age from any source
    current_age = _compute_age_from_birth((text or {}).get("birth"))

    # C4 — mixed return shape: new nested fields + legacy flat shortcuts
    result = {
        # === NEW nested fields (Phase 43 consumers) ===
        "primary_text_source": primary_text_source,   # "minnano"|"wiki"|"graphis"|None
        "text": text,                                  # raw dict from chosen source, or None
        "photo_url": photo_url,                        # winner of photo cascade, or None
        "photo_source": photo_source,                  # "graphis"|"gfriends"|"wiki"|"minnano"|None
        "backdrop_url": backdrop_url,                  # Graphis-only, or None
        "current_age": current_age,                    # int or None (TD-1 fix)
        "all_sources": {
            "minnano":  minnano_result or None,        # dict or None
            "wiki":     wiki_result    or None,        # dict or None
            "graphis":  graphis_result or None,        # dict or None
            "gfriends": gfriends_url   or None,        # str URL or None
            "javbus":   None,                          # C2: permanent None schema slot (Phase 42d)
        },

        # === LEGACY flat shortcuts (derived) ===
        # Existing template/JS/test assertions depend on these keys.
        # Phase 43 can hard-cut these later.
        "name":     (text or {}).get("name_ja"),
        "name_en":  (text or {}).get("name_romaji") or (text or {}).get("name_en"),
        "img":      photo_url,                          # template: actress_profile.img
        "backdrop": backdrop_url,                       # template: actress_profile.backdrop
        "birth":    (text or {}).get("birth"),
        "age":      current_age,                        # TD-1: from text.birth
        "height":   (text or {}).get("height"),
        "cup":      (text or {}).get("cup"),
        "bust":     (text or {}).get("bust"),
        "waist":    (text or {}).get("waist"),
        "hip":      (text or {}).get("hip"),
        "hometown": (text or {}).get("hometown"),
        "hobby":    (text or {}).get("hobby"),
    }

    # Cache 寫入
    _cache[cache_key] = {
        'data': result,
        'timestamp': time.time()
    }

    return result
