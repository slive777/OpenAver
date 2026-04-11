"""
女優爬蟲 Orchestrator - 三來源並行抓取與合併
"""

from typing import Optional, Dict

from core.logger import get_logger

logger = get_logger(__name__)

# Cache 結構（模組層級變數）
_cache = {}  # key: str (正規化女優名), value: dict (profile + timestamp)
_CACHE_TTL = 3600  # 1 小時


def _normalize_name(name: str) -> str:
    """正規化女優名稱（用於 cache key）"""
    import unicodedata
    name = name.strip()
    # 全形 → 半形
    name = unicodedata.normalize('NFKC', name)
    # 統一空白符
    name = ' '.join(name.split())
    return name


def get_actress_profile(name: str, makers: list = None) -> Optional[Dict]:
    """
    取得女優完整資料（gfriends + Graphis + JavBus 三來源並行）

    Args:
        name: 女優名稱（日文）
        makers: 片商名稱列表（從搜尋結果統計，用於 gfriends 查表）

    Returns:
        {
            'name': str,           # 姓名
            'img': str,            # 頭像 URL（gfriends > Graphis > JavBus）
            'backdrop': str,       # 背景 URL（僅 Graphis 有）
            'birth': str,          # 生日 "1996-12-03"
            'age': int,            # 年齡
            'height': str,         # 身高 "160cm"
            'cup': str,            # 罩杯 "G"
            'bust': str,           # 胸圍 "90cm"
            'waist': str,          # 腰圍 "55cm"
            'hip': str,            # 臀圍 "86cm"
            'hometown': str,       # 出身地
            'hobby': str,          # 興趣
        }
        三邊都沒資料返回 None
    """
    import time
    from concurrent.futures import ThreadPoolExecutor
    from core.scrapers.actress.graphis import scrape_graphis_photo
    from core.scrapers.actress.gfriends import lookup_gfriends
    from core.scrapers.actress.javbus import scrape_actress_profile

    # Cache 檢查
    cache_key = _normalize_name(name)
    if cache_key in _cache:
        cached = _cache[cache_key]
        if time.time() - cached['timestamp'] < _CACHE_TTL:
            return cached['data']
        else:
            del _cache[cache_key]  # 過期清理

    # 並行抓取（嚴格 5s 上限，shutdown 不等待背景執行緒）
    executor = ThreadPoolExecutor(max_workers=3)
    graphis_future = executor.submit(scrape_graphis_photo, name)
    javbus_future = executor.submit(scrape_actress_profile, name)
    gfriends_future = executor.submit(lookup_gfriends, name, makers)

    start = time.time()

    try:
        graphis_result = graphis_future.result(timeout=5)
    except Exception:
        graphis_result = None

    remaining = max(0, 5 - (time.time() - start))
    try:
        javbus_result = javbus_future.result(timeout=remaining)
    except Exception:
        javbus_result = None

    remaining = max(0, 5 - (time.time() - start))
    try:
        gfriends_url = gfriends_future.result(timeout=remaining)
    except Exception:
        gfriends_url = None

    executor.shutdown(wait=False)

    # 資料合併
    if javbus_result:
        result = javbus_result.copy()
    elif graphis_result:
        result = {'name': name}
    elif gfriends_url:
        result = {'name': name, 'img': gfriends_url}
    else:
        return None

    # Image priority: gfriends > graphis > javbus
    if gfriends_url:
        result['img'] = gfriends_url
    elif graphis_result:
        result['img'] = graphis_result['prof_url']
    # else: javbus img 保留

    # Backdrop: graphis only（gfriends 無 backdrop）
    if graphis_result:
        result['backdrop'] = graphis_result['backdrop_url']

    # Text: graphis > javbus
    if graphis_result:
        for field in ('age', 'height', 'cup', 'bust', 'waist', 'hip', 'hobby'):
            if graphis_result.get(field):
                result[field] = graphis_result[field]
        if graphis_result.get('name_en'):
            result['name_en'] = graphis_result['name_en']
    # birth, hometown: JavBus only（不覆蓋）

    # Cache 寫入
    _cache[cache_key] = {
        'data': result,
        'timestamp': time.time()
    }

    return result
