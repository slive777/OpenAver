"""
Scraper 模組（向後相容層）

此模組封裝了新的核心爬蟲模組，並提供與舊版 API 完全相容的介面。
包含 smart_search 等高階搜尋邏輯。
"""
import re
import time
from pathlib import Path

from core.logger import get_logger
from core.config import load_config

logger = get_logger(__name__)
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List, Dict, Union, Any, Callable, Type

# 引入新版爬蟲模組
from core.scrapers import (
    JavBusScraper, JAV321Scraper, JavDBScraper,
    FC2Scraper, AVSOXScraper,
    D2PassScraper, HEYZOScraper, DMMScraper,
    Video, ScraperConfig, BaseScraper
)
from core.scrapers.utils import extract_number as _new_extract_number
from core.maker_mapping import get_maker_by_prefix


# ============ 全域設定 ============

MAX_WORKERS = 2
REQUEST_DELAY = 0.3

# 爬蟲優先順序
SCRAPER_CLASSES: List[Type[BaseScraper]] = [
    JavBusScraper, JAV321Scraper, JavDBScraper,
    FC2Scraper, AVSOXScraper,
    D2PassScraper, HEYZOScraper,
]

# JavBus 語系對應表（zh-CN 無簡中版，沿用繁中 zh-tw）
_LOCALE_TO_JAVBUS = {"zh-TW": "zh-tw", "zh-CN": "zh-tw", "ja": "ja", "en": "en"}


def _get_javbus_lang() -> str:
    """從 config 讀取 locale 並轉換為 JavBus lang code"""
    try:
        config = load_config()
        locale = config.get('general', {}).get('locale', 'zh-TW')
        return _LOCALE_TO_JAVBUS.get(locale, "zh-tw")
    except Exception as e:
        logger.warning("[i18n] 讀取 locale config 失敗，使用預設語系: %s", e)
        return "zh-tw"


# ============ 輔助函數 (與舊版相容) ============

def extract_number(filename: str) -> Optional[str]:
    """從檔名提取番號 (Delegate to new utils)"""
    return _new_extract_number(filename)


def normalize_number(number: str) -> str:
    """標準化番號格式"""
    return JavBusScraper().normalize_number(number)


def is_number_format(s: str) -> bool:
    """判斷是否為完整番號格式 (如 SONE-001, ABC-123, SONE-103-UC)"""
    s = s.strip()
    # 清理常見後綴（需有分隔符，避免誤刪 JUC-123 等合法前綴）
    s = re.sub(
        r'[-_](UC|UNCEN|UNCENSORED|LEAK|LEAKED)(?=[-_.\s]|$)',
        '', s, flags=re.IGNORECASE
    )
    return bool(re.match(r'^[a-zA-Z]+-?\d{3,}$', s))


def is_partial_number(s: str) -> bool:
    """判斷是否為部分番號 (如 SONE-0, IPZZ-03)"""
    match = re.match(r'^([a-zA-Z]+)-?(\d{1,2})$', s.strip())
    return bool(match)


def is_prefix_only(s: str) -> bool:
    """判斷是否為純前綴 (如 IPZZ, SONE)"""
    s = s.strip().upper()
    return bool(re.match(r'^[A-Z]{2,6}$', s))


def sort_results_by_date(results: List[Dict[str, Any]], reverse: bool = True) -> List[Dict[str, Any]]:
    """按發行日期排序搜尋結果"""
    def sort_key(item: Dict[str, Any]) -> tuple[str, str]:
        date = str(item.get('date', '') or '0000-00-00')
        number = str(item.get('number', ''))
        return (date, number)

    return sorted(results, key=sort_key, reverse=reverse)


def expand_partial_number(partial: str) -> List[str]:
    """展開部分番號"""
    match = re.match(r'^([a-zA-Z]+)-?(\d+)$', partial.strip())
    if not match:
        return [partial]

    prefix, num = match.groups()
    prefix = prefix.upper()

    if len(num) >= 3:
        return [f"{prefix}-{num}"]

    candidates = []
    for i in range(10):
        full_num = num + str(i)
        while len(full_num) < 3:
            full_num = '0' + full_num
        candidates.append(f"{prefix}-{full_num}")
    return candidates


# ============ 核心搜尋函數 ============

def _is_dmm_enabled(proxy_url: str) -> bool:
    """空字串 → False；'direct' / 真 proxy → True"""
    return bool(proxy_url and proxy_url.strip())


def _dmm_proxy_url(proxy_url: str) -> str:
    """'direct'（大小寫不敏感）→ ''（直連）；其他 → 原值"""
    if not proxy_url:
        return ''
    if proxy_url.strip().lower() == 'direct':
        return ''
    return proxy_url


def _get_fuzzy_source(primary_source: str, proxy_url: str) -> str:
    """決定實際使用的模糊搜尋來源（含降級）"""
    if primary_source == 'dmm' and not _is_dmm_enabled(proxy_url):
        logger.info("[Search] primary_source=dmm but no proxy, fallback to javbus")
        return 'javbus'
    return primary_source


def search_jav(number: str, source: str = 'auto', proxy_url: str = '', primary_source: str = 'javbus') -> Optional[Dict[str, Any]]:
    """
    搜尋 JAV 資訊（向後相容函數）
    """
    all_data: Dict[str, Video] = {}

    # 標準化番號
    number = normalize_number(number)

    VALID_SOURCES = {'auto', 'dmm', 'javbus', 'jav321', 'javdb', 'd2pass', 'heyzo', 'fc2', 'avsox'}
    if source not in VALID_SOURCES:
        logger.warning(f"[Search] 未知來源: {source}")
        return None

    # DMM 需要日本 IP（proxy 或 direct），有啟用才建立
    dmm_config = ScraperConfig(proxy_url=_dmm_proxy_url(proxy_url)) if _is_dmm_enabled(proxy_url) else None

    # 決定要跑哪些爬蟲
    scrapers = []
    if source == 'auto':
        lang = _get_javbus_lang()
        base = [JavBusScraper(lang=lang) if cls is JavBusScraper else cls() for cls in SCRAPER_CLASSES]
        if dmm_config:
            scrapers = [DMMScraper(dmm_config)] + base
        else:
            scrapers = base
    elif source == 'dmm':
        scrapers = [DMMScraper(dmm_config)] if dmm_config else []
    elif source == 'javbus':
        scrapers = [JavBusScraper(lang=_get_javbus_lang())]
    elif source == 'jav321':
        scrapers = [JAV321Scraper()]
    elif source == 'javdb':
        scrapers = [JavDBScraper()]
    elif source == 'd2pass':
        scrapers = [D2PassScraper()]
    elif source == 'heyzo':
        scrapers = [HEYZOScraper()]
    elif source == 'fc2':
        scrapers = [FC2Scraper()]
    elif source == 'avsox':
        scrapers = [AVSOXScraper()]
    else:
        # 安全 fallback — 理論上已被上方 VALID_SOURCES 攔截，不應執行到此
        scrapers = [cls() for cls in SCRAPER_CLASSES]

    # 執行搜尋
    logger.info(f"[Search] {number} 使用來源: {source}")
    for scraper in scrapers:
        try:
            scraper_name = scraper.__class__.__name__
            logger.debug(f"[Search] 嘗試 {scraper_name}...")
            video = scraper.search(number)
            if video:
                all_data[video.source] = video
                logger.debug(f"[Search] {scraper_name} 找到結果")
        except Exception as e:
            logger.debug(f"[Search] {scraper_name} 錯誤: {e}")
            continue

    if not all_data:
        logger.info(f"[Search] {number} 無結果")
        return None

    # 合併邏輯
    main_video = None
    if primary_source == 'dmm' and 'dmm' in all_data:
        main_video = all_data['dmm']
    elif 'javbus' in all_data:
        main_video = all_data['javbus']
    elif 'dmm' in all_data:
        main_video = all_data['dmm']
    elif 'jav321' in all_data:
        main_video = all_data['jav321']
    else:
        main_video = list(all_data.values())[0]

    # 用其他來源補全
    for source_name, backup_video in all_data.items():
        if backup_video == main_video:
            continue
        
        # 使用 Pydantic 的 model_copy(update={}) 邏輯不好寫，
        # 這裡為了方便，轉成 dict 處理後再說，或者直接修改 main_video 的屬性（如果是 mutable）
        # 但 model 是 frozen 的。所以要用 model_copy。
        
        updates: Dict[str, Any] = {}
        if not main_video.title and backup_video.title:
            updates['title'] = backup_video.title
        if not main_video.maker and backup_video.maker:
            updates['maker'] = backup_video.maker
        if not main_video.date and backup_video.date:
            updates['date'] = backup_video.date
        if not main_video.actresses and backup_video.actresses:
            updates['actresses'] = backup_video.actresses
        if not main_video.cover_url and backup_video.cover_url:
            updates['cover_url'] = backup_video.cover_url
        if not main_video.tags and backup_video.tags:
            updates['tags'] = backup_video.tags
        if not main_video.director and backup_video.director:
            updates['director'] = backup_video.director
        if main_video.duration is None and backup_video.duration is not None:
            updates['duration'] = backup_video.duration
        if not main_video.label and backup_video.label:
            updates['label'] = backup_video.label
        if not main_video.series and backup_video.series:
            updates['series'] = backup_video.series
        if not main_video.sample_images and backup_video.sample_images:
            updates['sample_images'] = backup_video.sample_images

        if updates:
            main_video = main_video.model_copy(update=updates)

    # 補全 maker
    if not main_video.maker:
        maker = get_maker_by_prefix(number)
        if maker:
            main_video = main_video.model_copy(update={'maker': maker})

    result = main_video.to_legacy_dict()
    result['_source'] = main_video.source # 保留內部欄位
    logger.info(f"[Search] {number} 完成，來源: {main_video.source}")
    return result


def search_jav_single_source(number: str, source: str, proxy_url: str = '') -> Optional[Dict[str, Any]]:
    """指定單一來源搜尋"""
    return search_jav(number, source=source, proxy_url=proxy_url)


def search_partial(partial: str,
                   status_callback: Optional[Callable[[str, str], None]] = None,
                   result_callback: Optional[Callable[[int, Any], None]] = None,
                   discovery_only: bool = False) -> List[Dict[str, Any]]:
    """局部搜尋"""
    candidates = expand_partial_number(partial)
    results = []

    if status_callback:
        status_callback('javbus', 'searching')

    # Seed callback: 通知前端準備 skeleton grid
    if candidates and result_callback:
        result_callback(-1, candidates)

    if discovery_only:
        if status_callback:
            status_callback('done', f'found:{len(candidates)}')
        return [{'number': num, 'title': ''} for num in candidates]

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 記錄 slot index 以支援 result_callback 正確定位
        futures = {}
        for idx, num in enumerate(candidates):
            future = executor.submit(search_jav, num, 'javbus')
            futures[future] = (idx, num)

        for future in as_completed(futures):
            idx, num = futures[future]
            try:
                data = future.result()
                if data and data.get('title'):
                    results.append(data)
                    if result_callback:
                        result_callback(idx, data)
            except Exception:
                logger.error('search_partial: %s failed', num)
            time.sleep(REQUEST_DELAY)

    if status_callback:
        status_callback('done', f'found:{len(results)}')

    return sort_results_by_date(results)


def search_prefix(prefix: str, limit: int = 20, offset: int = 0, status_callback: Optional[Callable[[str, str], None]] = None, result_callback: Optional[Callable[[int, Any], None]] = None, discovery_only: bool = False) -> List[Dict[str, Any]]:
    """前綴搜尋"""
    results = []
    prefix = prefix.strip().upper()

    if status_callback:
        status_callback('javbus', 'searching')

    try:
        scraper = JavBusScraper(lang=_get_javbus_lang())
        start_page = (offset // 30) + 1
        skip_in_page = offset % 30
        pages_needed = ((limit + skip_in_page) // 30) + 2

        all_ids: List[str] = []
        for page in range(start_page, start_page + pages_needed):
            ids = scraper.get_ids_from_search(prefix, page=page, search_type=1)
            if ids:
                all_ids.extend(ids)
                if len(all_ids) >= limit + skip_in_page:
                    break
            else:
                break

        if not all_ids:
            if status_callback:
                status_callback('javbus', 'found:0')
            return []

        target_ids = all_ids[skip_in_page:][:limit]

        if status_callback:
            status_callback('javbus', f'found:{len(target_ids)}')

        if discovery_only:
            if status_callback:
                status_callback('done', f'found:{len(target_ids)}')
            return [{'number': num, 'title': ''} for num in target_ids]

        if status_callback:
            status_callback('javbus', 'fetching_details')

        if target_ids and result_callback:
            result_callback(-1, target_ids)

        completed_count = 0
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {}
            for idx, num in enumerate(target_ids):
                future = executor.submit(search_jav, num, 'javbus')
                futures[future] = (idx, num)

            for future in as_completed(futures):
                idx, num = futures[future]
                completed_count += 1
                if status_callback:
                    status_callback('javbus', f'details:{completed_count}/{len(target_ids)}')
                try:
                    data = future.result()
                    if data and data.get('title'):
                        results.append(data)
                        if result_callback:
                            result_callback(idx, data)
                except Exception:
                    logger.error('search_prefix: %s failed', num)
                time.sleep(REQUEST_DELAY)

    except Exception as e:
        logger.error('search_prefix failed: %s', e)

    if status_callback:
        status_callback('done', f'found:{len(results)}')

    return sort_results_by_date(results)


def _dmm_keyword_search_progressive(
    dmm_scraper,
    query: str,
    limit: int,
    status_callback,
    result_callback,
    offset: int = 0,
) -> Optional[List[Dict[str, Any]]]:
    """DMM keyword search with progressive enrichment (mirrors JavBus pattern).

    Returns a list of result dicts on success, or None if DMM returned nothing
    (caller should fall through to JavBus).
    """
    pairs = dmm_scraper.search_by_keyword_with_ids(query, limit=limit, offset=offset)
    if not pairs:
        return None

    # Seed: frontend renders skeleton cards immediately
    if result_callback:
        seed_ids = [video.number for _, video in pairs]
        result_callback(-1, seed_ids)

    results = [None] * len(pairs)  # pre-allocate to preserve seed order
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {}
        for idx, (content_id, shallow) in enumerate(pairs):
            future = executor.submit(dmm_scraper._fetch_by_id, content_id)
            futures[future] = (idx, content_id, shallow)

        for future in as_completed(futures):
            idx, content_id, shallow = futures[future]
            try:
                video = future.result()
                if video is None:
                    video = shallow
            except Exception:
                logger.error('DMM enrichment failed: %s', content_id)
                video = shallow
            data = video.to_legacy_dict()
            results[idx] = data  # slot-indexed, not append
            if result_callback:
                result_callback(idx, data)

    if status_callback:
        status_callback('done', f'found:{len(results)}')
    return results


def search_actress(name: str, limit: int = 20, offset: int = 0, status_callback: Optional[Callable[[str, str], None]] = None, result_callback: Optional[Callable[[int, Any], None]] = None, primary_source: str = 'javbus', proxy_url: str = '', discovery_only: bool = False) -> List[Dict[str, Any]]:
    """女優搜尋"""
    # DMM routing: when primary_source='dmm' and proxy is available, try DMM first
    fuzzy_source = _get_fuzzy_source(primary_source, proxy_url)
    if fuzzy_source == 'dmm' and not discovery_only:
        if status_callback:
            status_callback('dmm', 'searching')
        dmm_config = ScraperConfig(proxy_url=_dmm_proxy_url(proxy_url))
        dmm_scraper = DMMScraper(dmm_config)
        dmm_results = _dmm_keyword_search_progressive(
            dmm_scraper, name, limit, status_callback, result_callback, offset=offset
        )
        if dmm_results is not None:
            return dmm_results
        # DMM returned nothing → fall through to JavBus path

    try:
        if status_callback:
            status_callback('javbus', 'searching')

        scraper = JavBusScraper(lang=_get_javbus_lang())
        start_page = (offset // 30) + 1
        skip_in_page = offset % 30
        pages_needed = ((limit + skip_in_page) // 30) + 2

        all_ids = []
        for page in range(start_page, start_page + pages_needed):
            ids = scraper.get_ids_from_search(name, page=page)
            if ids:
                all_ids.extend(ids)
                if len(all_ids) >= limit + skip_in_page:
                    break
            else:
                break

        if all_ids:
            all_ids = all_ids[skip_in_page:]
            target_ids = all_ids[:limit]

            if status_callback:
                status_callback('javbus', f'found:{len(target_ids)}')

            if discovery_only:
                if status_callback:
                    status_callback('done', f'found:{len(target_ids)}')
                return [{'number': num, 'title': ''} for num in target_ids]

            if target_ids and result_callback:
                result_callback(-1, target_ids)

            results = []
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {}
                for idx, num in enumerate(target_ids):
                    future = executor.submit(search_jav, num, 'javbus')
                    futures[future] = (idx, num)

                for future in as_completed(futures):
                    idx, num = futures[future]
                    try:
                        data = future.result()
                        if data and data.get('title'):
                            results.append(data)
                            if result_callback:
                                result_callback(idx, data)
                    except Exception:
                        logger.error('search_actress: %s failed', num)

            if status_callback:
                status_callback('done', f'found:{len(results)}')
            return sort_results_by_date(results)

    except Exception as e:
        logger.error('search_actress failed: %s', e)

    # Fallback: JavDB 關鍵字搜尋（JavBus 失敗時）
    if status_callback:
        status_callback('javdb', 'searching')

    scraper = JavDBScraper()
    videos = scraper.search_by_keyword(name, limit=limit)
    results = [v.to_legacy_dict() for v in videos]

    if status_callback:
        status_callback('done', f'found:{len(results)}')

    return results


def search_jav321_keyword(keyword: str, limit: int = 20, status_callback: Optional[Callable[[str, str], None]] = None) -> List[Dict[str, Any]]:
    """Jav321 關鍵字搜尋"""
    if status_callback:
        status_callback('jav321', 'searching')
    
    scraper = JAV321Scraper()
    videos = scraper.search_by_keyword(keyword, limit=limit)
    results = [v.to_legacy_dict() for v in videos]
    
    if status_callback:
        status_callback('jav321', f'found:{len(results)}')
        
    return results


def get_all_variant_ids(number: str) -> List[str]:
    """獲取變體 ID"""
    number = normalize_number(number)
    variant_ids = []

    try:
        scraper = JavBusScraper(lang=_get_javbus_lang())
        ids = scraper.get_ids_from_search(number, page=1, search_type=0)
        if ids:
            number_normalized = number.upper().replace('-', '')
            for id in ids:
                base_id = id.split('_')[0]
                if base_id.upper().replace('-', '') == number_normalized:
                    variant_ids.append(id)
            variant_ids.sort(reverse=True)
    except Exception as e:
        logger.error('get_all_variant_ids failed: %s', e)

    return variant_ids


def search_by_variant_id(variant_id: str, base_number: str) -> Optional[Dict[str, Any]]:
    """搜索變體"""
    try:
        scraper = JavBusScraper(lang=_get_javbus_lang())
        video = scraper._fetch_by_id(variant_id)
        if video:
            result = video.to_legacy_dict()
            # 用 base_number 覆蓋（保持與舊邏輯一致）
            result['number'] = base_number
            # 補 maker
            if not result.get('maker'):
                result['maker'] = get_maker_by_prefix(base_number)
            result['_source'] = 'javbus'
            result['_variant_id'] = variant_id
            return result
    except Exception as e:
        logger.error('search_by_variant_id failed: %s', e)
    return None


def _get_uncensored_sources(search_term: str) -> list[str]:
    """
    根據番號前綴決定無碼來源搜尋順序。

    - FC2 前綴 → ['fc2', 'avsox']（省 D2Pass + HEYZO）
    - HEYZO 前綴 → ['heyzo', 'avsox']（省 D2Pass）
    - 其他（D2Pass 日期格式等）→ ['d2pass', 'heyzo', 'fc2', 'avsox']（原始順序）
    """
    term_lower = search_term.lower().strip()
    if term_lower.startswith('fc2'):
        return ['fc2', 'avsox']
    elif term_lower.startswith('heyzo'):
        return ['heyzo', 'avsox']
    else:
        return ['d2pass', 'heyzo', 'fc2', 'avsox']


def smart_search(query: str, limit: int = 20, offset: int = 0, status_callback: Optional[Callable[[str, str], None]] = None, uncensored_mode: bool = False, proxy_url: str = '', result_callback: Optional[Callable[[int, Any], None]] = None, primary_source: str = 'javbus', discovery_only: bool = False) -> List[Dict[str, Any]]:
    """
    智慧搜尋：自動判斷搜尋類型並執行

    Args:
        query: 搜尋關鍵字
        limit: 結果數量限制
        offset: 分頁偏移
        status_callback: 狀態回調函數
        uncensored_mode: 無碼模式（只搜 AVSOX / FC2）
    """
    query = query.strip()

    if not query or len(query) < 2:
        return []

    # 無碼模式：D2Pass → HEYZO → FC2 → AVSOX
    if uncensored_mode:
        if status_callback:
            status_callback('mode', 'uncensored')

        extracted = _new_extract_number(query)
        search_term = extracted if extracted else query

        result = None
        unc_sources = _get_uncensored_sources(search_term)
        for unc_source in unc_sources:
            if status_callback:
                status_callback(unc_source, 'searching')
            result = search_jav(search_term, source=unc_source, proxy_url=proxy_url)
            if result:
                break

        results = [result] if result else []
        if status_callback:
            status_callback('done', f'found:{len(results)}')
        for r in results:
            r['_mode'] = 'uncensored'
        return results

    # 0. 無碼特殊處理 - 自動偵測（FC2 / HEYZO / 日期-編號格式）
    is_uncensored = (
        query.lower().strip().startswith('fc2') or
        query.lower().strip().startswith('heyzo') or
        re.match(r'^\d{6}-\d{2,}$', query) or
        re.match(r'^\d{6}_\d{2,}$', query)
    )
    if is_uncensored:
        if status_callback:
            status_callback('mode', 'uncensored')
        extracted = _new_extract_number(query)
        search_term = extracted if extracted else query
        result = None
        unc_sources = _get_uncensored_sources(search_term)
        for unc_source in unc_sources:
            if status_callback:
                status_callback(unc_source, 'searching')
            result = search_jav(search_term, source=unc_source, proxy_url=proxy_url)
            if result:
                break
        results = [result] if result else []
        if status_callback:
            status_callback('done', f'found:{len(results)}')
        for r in results:
            r['_mode'] = 'uncensored'
        return results

    # 1. 精確搜尋
    if is_number_format(query):
        query = normalize_number(query)
        if offset > 0:
            return []

        # DMM Top-1（primary_source='dmm' 且 DMM 已啟用時精確搜尋優先用 DMM）
        if primary_source == 'dmm' and _is_dmm_enabled(proxy_url):
            if status_callback:
                status_callback('dmm', 'searching')
            res = search_jav(query, source='dmm', proxy_url=proxy_url)
            if res:
                res['_mode'] = 'exact'
                if status_callback: status_callback('done', 'found:1')
                return [res]

        if status_callback:
            status_callback('javbus', 'searching')

        # 嘗試找變體
        variant_ids = get_all_variant_ids(query)
        if variant_ids:
            first = variant_ids[0]
            # 用 variant id 搜
            res = search_by_variant_id(first, query)
            if res:
                res['_all_variant_ids'] = variant_ids
                if status_callback: status_callback('done', 'found:1')
                return [res]

        # 一般搜尋
        res = search_jav(query, proxy_url=proxy_url, primary_source=primary_source)
        results = [res] if res else []
        if status_callback: status_callback('done', f'found:{len(results)}')
        for r in results: r['_mode'] = 'exact'
        return results

    # 2. 局部搜尋
    elif is_partial_number(query):
        if offset > 0: return []
        results = search_partial(query, status_callback=status_callback, result_callback=result_callback, discovery_only=discovery_only)
        for r in results: r['_mode'] = 'partial'
        return results

    # 3. 前綴搜尋
    elif is_prefix_only(query):
        results = search_prefix(query, limit=limit, offset=offset, status_callback=status_callback, result_callback=result_callback, discovery_only=discovery_only)
        mode = 'prefix'

        if not results:
             # Fallback to actress（不透傳 result_callback：prefix 的 seed 已送出，
             # actress fallback 不可送第二個 seed，避免 slot index 錯位）
             if status_callback: status_callback('mode', 'actress')
             results = search_actress(query, limit=limit, status_callback=status_callback, primary_source=primary_source, proxy_url=proxy_url)
             if results: mode = 'actress'

        if not results:
             # Fallback to keyword（search_jav321_keyword 無 as_completed，不透傳 result_callback）
             if status_callback: status_callback('mode', 'keyword')
             results = search_jav321_keyword(query, limit=limit, status_callback=status_callback)
             if results: mode = 'keyword'

        for r in results: r['_mode'] = mode
        return results

    # 4. 女優/關鍵字搜尋
    else:
        # 模糊搜尋路由
        fuzzy_source = _get_fuzzy_source(primary_source, proxy_url)
        if fuzzy_source == 'dmm' and not discovery_only:
            # DMM keyword search (progressive)
            if status_callback:
                status_callback('dmm', 'searching')
            dmm_config = ScraperConfig(proxy_url=_dmm_proxy_url(proxy_url))
            dmm_scraper = DMMScraper(dmm_config)
            dmm_results = _dmm_keyword_search_progressive(
                dmm_scraper, query, limit, status_callback, result_callback, offset=offset
            )
            if dmm_results is not None:
                for r in dmm_results:
                    r['_mode'] = 'actress'
                return dmm_results
            # DMM returned nothing → fall through to JavBus

        results = search_actress(query, limit=limit, offset=offset, status_callback=status_callback, result_callback=result_callback, primary_source=primary_source, proxy_url=proxy_url, discovery_only=discovery_only)
        mode = 'actress'

        if not results and not discovery_only:
            if status_callback: status_callback('mode', 'keyword')
            results = search_jav321_keyword(query, limit=limit, status_callback=status_callback)
            if results: mode = 'keyword'

        for r in results: r['_mode'] = mode
        return results
