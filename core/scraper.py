"""
Scraper 模組（向後相容層）

此模組封裝了新的核心爬蟲模組，並提供與舊版 API 完全相容的介面。
包含 smart_search 等高階搜尋邏輯。
"""
import re
import time
import json
from pathlib import Path

from core.logger import get_logger

logger = get_logger(__name__)
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List, Dict, Union, Any, Callable, Type

# 引入新版爬蟲模組
from core.scrapers import (
    JavBusScraper, JAV321Scraper, JavDBScraper,
    FC2Scraper, AVSOXScraper,
    D2PassScraper, HEYZOScraper, JavGuruScraper, DMMScraper,
    Video, ScraperConfig, BaseScraper
)
from core.scrapers.utils import extract_number as _new_extract_number

# 嘗試載入 jvav（部分高階搜尋仍依賴此庫）
try:
    from jvav import JavBusUtil
    JVAV_AVAILABLE = True
except ImportError:
    JVAV_AVAILABLE = False


# ============ 全域設定 ============

MAX_WORKERS = 2
REQUEST_DELAY = 0.3

# 爬蟲優先順序
SCRAPER_CLASSES: List[Type[BaseScraper]] = [
    JavBusScraper, JAV321Scraper, JavDBScraper,
    JavGuruScraper, FC2Scraper, AVSOXScraper,
    D2PassScraper, HEYZOScraper,
]

# 片商對照表檔案路徑
MAKER_MAPPING_FILE = Path(__file__).parent.parent / "maker_mapping.json"
_maker_mapping_cache: Dict[str, str] = {}
_maker_mapping_loaded = False


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


def load_maker_mapping() -> Dict[str, str]:
    """載入片商對照表"""
    global _maker_mapping_cache, _maker_mapping_loaded
    if _maker_mapping_loaded:
        return _maker_mapping_cache

    if MAKER_MAPPING_FILE.exists():
        try:
            with open(MAKER_MAPPING_FILE, 'r', encoding='utf-8') as f:
                _maker_mapping_cache = json.load(f)
        except (json.JSONDecodeError, IOError):
            _maker_mapping_cache = {}
    _maker_mapping_loaded = True
    return _maker_mapping_cache


def save_maker_mapping(mapping: Dict[str, str]) -> None:
    """儲存片商對照表"""
    global _maker_mapping_cache, _maker_mapping_loaded
    try:
        with open(MAKER_MAPPING_FILE, 'w', encoding='utf-8') as f:
            json.dump(mapping, f, ensure_ascii=False, indent=2)
        _maker_mapping_cache = mapping
        _maker_mapping_loaded = True
    except IOError:
        pass


def get_maker_by_prefix(number: str) -> str:
    """
    從對照表查片商，沒有則查 JavDB 並更新對照表
    """
    mapping = load_maker_mapping()
    match = re.match(r'^([A-Za-z]+)', number)
    if not match:
        return ""

    prefix = match.group(1).upper()
    if prefix in mapping:
        return mapping[prefix]

    # 查 JavDB
    try:
        scraper = JavDBScraper()
        # 這裡可能會觸發網路請求，如果是測試環境可能會失敗，加 try-except
        video = scraper.search(number)
        if video and video.maker and not re.match(r'^\d{4}(-\d{2}){0,2}$', video.maker):
            mapping[prefix] = video.maker
            save_maker_mapping(mapping)
            return video.maker
    except Exception:
        pass

    return ""


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

def search_jav(number: str, source: str = 'auto', proxy_url: str = '') -> Optional[Dict[str, Any]]:
    """
    搜尋 JAV 資訊（向後相容函數）
    """
    all_data: Dict[str, Video] = {}

    # 標準化番號
    number = normalize_number(number)

    # DMM 需要 proxy，有 proxy_url 才建立
    dmm_config = ScraperConfig(proxy_url=proxy_url) if proxy_url else None

    # 決定要跑哪些爬蟲
    scrapers = []
    if source == 'auto':
        base = [cls() for cls in SCRAPER_CLASSES]
        if dmm_config:
            scrapers = [DMMScraper(dmm_config)] + base
        else:
            scrapers = base
    elif source == 'dmm':
        scrapers = [DMMScraper(dmm_config)] if dmm_config else []
    elif source == 'javbus':
        scrapers = [JavBusScraper()]
    elif source == 'jav321':
        scrapers = [JAV321Scraper()]
    elif source == 'javdb':
        scrapers = [JavDBScraper()]
    elif source == 'javguru':
        scrapers = [JavGuruScraper()]
    elif source == 'd2pass':
        scrapers = [D2PassScraper()]
    elif source == 'heyzo':
        scrapers = [HEYZOScraper()]
    elif source == 'fc2':
        scrapers = [FC2Scraper()]
    elif source == 'avsox':
        scrapers = [AVSOXScraper()]
    else:
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
    if 'dmm' in all_data:
        main_video = all_data['dmm']
    elif 'javbus' in all_data:
        main_video = all_data['javbus']
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


def search_partial(partial: str) -> List[Dict[str, Any]]:
    """局部搜尋"""
    candidates = expand_partial_number(partial)
    results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(search_jav, num): num for num in candidates}
        for future in as_completed(futures):
            try:
                data = future.result()
                if data and data.get('title'):
                    results.append(data)
            except Exception:
                pass
            time.sleep(REQUEST_DELAY)

    return sort_results_by_date(results)


def search_prefix(prefix: str, limit: int = 20, offset: int = 0, status_callback: Optional[Callable[[str, str], None]] = None) -> List[Dict[str, Any]]:
    """前綴搜尋 (Delegate to JavBusUtil for list functionality)"""
    if not JVAV_AVAILABLE:
        # Fallback: 使用 JavDB 關鍵字搜尋
        scraper = JavDBScraper()
        videos = scraper.search_by_keyword(prefix, limit=limit)
        return [v.to_legacy_dict() for v in videos]

    # 使用 jvav (Code borrowed from original scraper.py)
    results = []
    prefix = prefix.strip().upper()
    
    if status_callback:
        status_callback('javbus', 'searching')

    try:
        jb = JavBusUtil()
        page = (offset // 30) + 1
        skip_in_page = offset % 30
        
        search_url = f'https://www.javbus.com/search/{prefix}&type=1'
        code, ids = jb.get_ids_from_page(search_url, page=page)
        
        if code != 200 or not ids:
             if status_callback:
                 status_callback('javbus', 'found:0')
             return []

        target_ids = ids[skip_in_page:][:limit]
        
        if status_callback:
            status_callback('javbus', f'found:{len(target_ids)}')
            status_callback('javbus', 'fetching_details')
            
        completed_count = 0
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # 只用 JavBus 來源，避免 fan out 到所有爬蟲
            futures = {executor.submit(search_jav, num, 'javbus'): num for num in target_ids}
            for future in as_completed(futures):
                completed_count += 1
                if status_callback:
                     status_callback('javbus', f'details:{completed_count}/{len(target_ids)}')
                try:
                    data = future.result()
                    if data:
                        results.append(data)
                except Exception:
                    pass
                time.sleep(REQUEST_DELAY)

    except Exception:
        pass

    if status_callback:
        status_callback('done', f'found:{len(results)}')

    return results # 這裡不需再排序，JavBus 返回的本身就是按日期排序


def search_actress(name: str, limit: int = 20, offset: int = 0, status_callback: Optional[Callable[[str, str], None]] = None) -> List[Dict[str, Any]]:
    """女優搜尋"""
    # 嘗試使用新版 Jav321Scraper 或 JavDBScraper 做關鍵字搜尋
    # 但舊版是用 jvav 的 get_ids_by_star_name 來精確抓取女優作品列表
    # 為了最佳相容性，若有 jvav 則優先使用，否則 fallback 到關鍵字搜尋
    
    if JVAV_AVAILABLE:
        # 使用 jvav 邏輯 (簡化版)
        try:
             if status_callback: status_callback('javbus', 'searching')
             jb = JavBusUtil()
             start_page = (offset // 30) + 1
             skip_in_page = offset % 30
             pages_needed = ((limit + skip_in_page) // 30) + 2
             
             all_ids = []
             for page in range(start_page, start_page + pages_needed):
                 code, ids = jb.get_ids_by_star_name(name, page)
                 if code == 200 and ids:
                     all_ids.extend(ids)
                     if len(all_ids) >= limit + skip_in_page:
                         break
                 else:
                     break
                 
             if all_ids:
                 # 跳過 offset 對應的部分
                 all_ids = all_ids[skip_in_page:]

                 if status_callback: status_callback('javbus', f'found:{len(all_ids[:limit])}')
                 results = []

                 target_ids = all_ids[:limit]
                 with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                    # 只用 JavBus 來源，避免 fan out 到所有爬蟲
                    futures = {executor.submit(search_jav, num, 'javbus'): num for num in target_ids}
                    for future in as_completed(futures):
                        try:
                            data = future.result()
                            if data:
                                results.append(data)
                        except Exception:
                            pass
                 if status_callback: status_callback('done', f'found:{len(results)}')
                 return sort_results_by_date(results)
                 
        except Exception:
            pass

    # Fallback: 使用 JavDB 關鍵字搜尋 (通常效果不錯)
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
    """獲取變體 ID (依賴 jvav)"""
    if not JVAV_AVAILABLE:
        return []
    
    number = normalize_number(number)
    variant_ids = []
    
    try:
        jb = JavBusUtil()
        search_url = f'https://www.javbus.com/search/{number}&type=0'
        code, ids = jb.get_ids_from_page(search_url, page=1)
        if code == 200 and ids:
            # 過濾出真正匹配的番號
            number_normalized = number.upper().replace('-', '')
            for id in ids:
                base_id = id.split('_')[0]
                if base_id.upper().replace('-', '') == number_normalized:
                    variant_ids.append(id)

            # 按日期排序（新的在前）- 帶日期後綴的會排在前面
            variant_ids.sort(reverse=True)
    except Exception:
        pass
        
    return variant_ids


def search_by_variant_id(variant_id: str, base_number: str) -> Optional[Dict[str, Any]]:
    """搜索變體"""
    # 直接用 JavBusScraper，但 JavBusScraper 目前只能搜標準番號
    # 這裡我們 trick 一下，JavBusScraper.search 其實是調用 jvav.get_av_by_id
    # 如果傳入的是 variant_id，JavBusScraper 的 validate_number 可能會失敗
    # 所以直接用 jvav
    if not JVAV_AVAILABLE:
        return None
        
    try:
        jb = JavBusUtil()
        code, data = jb.get_av_by_id(variant_id, False, False)
        if code == 200 and data:
            # 手動轉 old format，因為沒經過 Video model
            data['source'] = 'javbus'
            # 補 maker
            if not data.get('maker'):
                data['maker'] = get_maker_by_prefix(base_number)
            
            # 轉換 legacy structure if needed (jb return is mostly compatible)
            # jb returns: title, img, date, stars(list of dict/str), tags, maker
            # legacy needs: actors (list of names)
            
            actors = []
            for s in data.get('stars', []):
                if isinstance(s, dict):
                    actors.append(s.get('name', ''))
                elif isinstance(s, str):
                    actors.append(s)
            
            return {
                'number': base_number,
                'title': data.get('title', ''),
                'actors': actors,
                'date': data.get('date', ''),
                'maker': data.get('maker', ''),
                'cover': data.get('img', ''),
                'tags': data.get('tags', []),
                'source': 'javbus',
                'url': data.get('url', ''),
                '_source': 'javbus',
                '_variant_id': variant_id
            }
    except Exception:
        pass
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


def smart_search(query: str, limit: int = 20, offset: int = 0, status_callback: Optional[Callable[[str, str], None]] = None, uncensored_mode: bool = False, proxy_url: str = '') -> List[Dict[str, Any]]:
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
        'fc2' in query.lower() or
        'heyzo' in query.lower() or
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

        # DMM Top-1（proxy 有值時精確搜尋優先用 DMM）
        if proxy_url:
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
        res = search_jav(query, proxy_url=proxy_url)
        results = [res] if res else []
        if status_callback: status_callback('done', f'found:{len(results)}')
        for r in results: r['_mode'] = 'exact'
        return results

    # 2. 局部搜尋
    elif is_partial_number(query):
        if offset > 0: return []
        if status_callback: status_callback('javbus', 'searching')
        results = search_partial(query)
        if status_callback: status_callback('done', f'found:{len(results)}')
        for r in results: r['_mode'] = 'partial'
        return results

    # 3. 前綴搜尋
    elif is_prefix_only(query):
        results = search_prefix(query, limit=limit, offset=offset, status_callback=status_callback)
        mode = 'prefix'
        
        if not results:
             # Fallback to actress
             if status_callback: status_callback('mode', 'actress')
             results = search_actress(query, limit=limit, status_callback=status_callback)
             if results: mode = 'actress'
             
        if not results:
             # Fallback to keyword
             if status_callback: status_callback('mode', 'keyword')
             results = search_jav321_keyword(query, limit=limit, status_callback=status_callback)
             if results: mode = 'keyword'
             
        for r in results: r['_mode'] = mode
        return results

    # 4. 女優/關鍵字搜尋
    else:
        results = search_actress(query, limit=limit, offset=offset, status_callback=status_callback)
        mode = 'actress'
        
        if not results:
            if status_callback: status_callback('mode', 'keyword')
            results = search_jav321_keyword(query, limit=limit, status_callback=status_callback)
            if results: mode = 'keyword'
            
        for r in results: r['_mode'] = mode
        return results
