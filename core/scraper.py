"""
Scraper 模組（向後相容層）

此模組封裝了新的核心爬蟲模組，並提供與舊版 API 完全相容的介面。
包含 smart_search 等高階搜尋邏輯。
"""
import re
import time

from core.logger import get_logger
from core.config import load_config

logger = get_logger(__name__)
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List, Dict, Any, Callable

# 引入新版爬蟲模組
from core.scrapers import (
    JavBusScraper, JAV321Scraper, JavDBScraper,
    FC2Scraper, AVSOXScraper,
    D2PassScraper, HEYZOScraper, DMMScraper,
    JavLibraryScraper,          # T3 新增
    Video, ScraperConfig
)
from core.scrapers.utils import extract_number as _new_extract_number, FUZZY_SEARCH_SOURCES, normalize_number_impl
from core.maker_mapping import get_maker_by_prefix
from core.source_merger import merge_results
from core.source_config import validate_source_id
from core.source_settings import get_enabled_source_ids, get_all_source_ids_ordered

# 63c metatube routing imports（CD-63c-1 / CD-63c-2 / CD-63c-3）
from core.metatube.client import MetatubeHttpClient, pick_movie_result
from core.metatube.mapper import map_movie_info
from core.metatube.state import metatube_state
from core.metatube.errors import MetatubeUnavailable, MetatubeNotFound, MetatubeAuthError


# ============ 全域設定 ============

MAX_WORKERS = 2
REQUEST_DELAY = 0.3

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
    return normalize_number_impl(number)


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


# ============ 63c metatube internal carrier keys + strip helper ============

_INTERNAL_NFO_KEYS = ('_summary', '_rating')


def internal_nfo_carriers(video) -> dict:
    """search_jav 注入、to_legacy_dict 刻意省略的內部 NFO carrier（_summary / _rating）。

    NFO writer 的 <plot>/<rating> 吃這組 `_` 前綴 carrier（見 enricher._scraper_to_meta），
    DB 不收。detail_url 預餵路徑（confirm 多版本）跳過 search_jav，需補同一組以對齊既有
    javlibrary 重刮的 NFO 輸出，否則 NFO 評分/簡介會掉（CD-63c-5 / PR #89 Codex P2）。
    key 集合必須與 _INTERNAL_NFO_KEYS 一致。
    """
    return {'_summary': video.summary, '_rating': video.rating}


def strip_internal_nfo_keys(result_dict: dict) -> dict:
    """移除 internal NFO carrier 鍵（_summary / _rating），回傳 shallow copy。

    保留 _source / _mode / _all_variant_ids 等前端所需 _ 前綴鍵。
    （spec §161 enforcement，CD-63c-5）
    """
    return {k: v for k, v in result_dict.items() if k not in _INTERNAL_NFO_KEYS}


# ============ 63c _MetatubeShim（CD-63c-3）============

class _MetatubeShim:
    """metatube provider 的 scraper-compatible shim（CD-63c-3）。

    讓 metatube provider 能插入現有 source_to_scraper 架構，
    使用相同的 .search() 介面，不改 search_jav() 的 scraper 迭代邏輯。
    """
    def __init__(self, provider: str, base_url: str, token: str) -> None:
        self.source = f'metatube:{provider}'
        self._provider = provider
        self._client = MetatubeHttpClient(base_url, token)

    def search(self, number: str) -> 'Video | None':
        try:
            results = self._client.search(self._provider, number)
            picked = pick_movie_result(results)
            if not picked:
                return None
            info = self._client.get_info(self._provider, picked['id'])
            if not info:
                return None
            video = map_movie_info(info)
            # routing 期 success → mark available（lazy liveness）
            metatube_state.mark_available(self.source)
            return video
        except MetatubeUnavailable:
            metatube_state.mark_failed(self.source)
            raise
        except MetatubeNotFound:
            # 404 = 番號不在此源 = 不算失敗（spec §5.3 / CD-63a-6）
            return None
        except MetatubeAuthError:
            # Token 錯誤：不 mark_failed（連線層問題，非 provider 問題）
            logger.warning('metatube auth error for %s', self.source)
            return None
        except Exception:
            logger.exception('metatube shim unexpected error for %s', self.source)
            return None


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


VALID_JAVBUS_LANGS = {'zh-tw', 'ja', 'en'}


def search_jav(number: str, source: str = 'auto', proxy_url: str = '', javbus_lang: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    搜尋 JAV 資訊（向後相容函數）
    """
    all_data: Dict[str, Video] = {}

    # 標準化番號
    number = normalize_number(number)

    # 來源 id 驗證（TASK-61a-3）：改用 validate_source_id() 取代舊 VALID_SOURCES set。
    # 'auto' 與 8 個 builtin id 通過；其餘 → return None（保留「未知來源不 raise」契約）。
    if not validate_source_id(source):
        logger.warning(f"[Search] 未知來源: {source}")
        return None

    # DMM 需要日本 IP（proxy 或 direct），有啟用才建立
    dmm_config = ScraperConfig(proxy_url=_dmm_proxy_url(proxy_url)) if _is_dmm_enabled(proxy_url) else None

    # javbus_lang 校驗 + config fallback（auto 與 explicit javbus 共用）
    if javbus_lang is not None and javbus_lang not in VALID_JAVBUS_LANGS:
        logger.warning("[Search] 無效的 javbus_lang: %s，fallback 到 config", javbus_lang)
        javbus_lang = None
    _javbus_lang = javbus_lang if javbus_lang is not None else _get_javbus_lang()

    # 來源 id → scraper factory（無參數 callable，回 scraper instance list）。
    # DMM 與 JavBus 是攜帶 closure 參數的特例：
    #   - dmm：proxy-gated，dmm_config 為 None（無 proxy）時回 []（不建立）。
    #   - javbus：帶校驗後的 lang。
    # explicit 指定來源與 auto fan-out 共用同一份定義。
    source_to_scraper = {
        'dmm': lambda: [DMMScraper(dmm_config)] if dmm_config else [],
        'javbus': lambda: [JavBusScraper(lang=_javbus_lang)],
        'jav321': lambda: [JAV321Scraper()],
        'javdb': lambda: [JavDBScraper()],
        'd2pass': lambda: [D2PassScraper()],
        'heyzo': lambda: [HEYZOScraper()],
        'fc2': lambda: [FC2Scraper()],
        'avsox': lambda: [AVSOXScraper()],
        'javlibrary': lambda: [JavLibraryScraper()],
    }

    # 63c：動態注入 metatube provider（CD-63c-2）
    # availability_map 的 False entry 仍加進 source_to_scraper——
    # get_enabled_source_ids(availability_map) 已在上一層排除不可達的 source，
    # 不需 double-gate（explicit picker 選當前 probe-failed provider 也應能試打）。
    if metatube_state.is_connected:
        _mt_url = metatube_state.base_url or ''
        _mt_token = metatube_state.token or ''
        for _mt_name, _mt_avail in metatube_state.availability_map().items():
            _mt_provider = _mt_name[len('metatube:'):]
            # 用 default arg 固定 closure variable capture（風險點 a）
            source_to_scraper[_mt_name] = (
                lambda _pname=_mt_provider, _url=_mt_url, _tok=_mt_token:
                    [_MetatubeShim(_pname, _url, _tok)]
            )

    # 決定要跑哪些爬蟲（auto vs. explicit）
    logger.info(f"[Search] {number} 使用來源: {source}")
    if source == 'auto':
        # auto fan-out（CD-63c-4）：
        # - builtin：循序執行（維持既有行為）
        # - metatube：defer 到 ThreadPoolExecutor 並行（bounded parallel fan-out）
        # - 結果以 enabled_sids 順序重建 all_data（保全 user-drag merge 優先度）
        # get_enabled_source_ids 傳入 availability_map 讓 metatube gate 生效（🔴 CRITICAL）
        enabled_sids = get_enabled_source_ids(availability_map=metatube_state.availability_map())
        results_by_source: Dict[str, Video] = {}
        metatube_shims = []  # list of (sid, shim) for parallel dispatch

        for sid in enabled_sids:
            factory = source_to_scraper.get(sid)
            if not factory:
                continue
            if sid.startswith('metatube:'):
                metatube_shims.extend((sid, s) for s in factory())  # defer
            else:
                for scraper in factory():  # builtin：循序，維持既有行為
                    try:
                        scraper_name = scraper.__class__.__name__
                        logger.debug(f"[Search] 嘗試 {scraper_name}...")
                        v = scraper.search(number)
                        if v:
                            results_by_source[v.source] = v
                            logger.debug(f"[Search] {scraper_name} 找到結果")
                    except Exception as e:
                        logger.debug(f"[Search] {scraper_name} 錯誤: {e}")
                        continue

        # metatube subset：bounded parallel
        if metatube_shims:
            with ThreadPoolExecutor(max_workers=min(len(metatube_shims), 5)) as ex:
                futs = [(sid, ex.submit(shim.search, number)) for sid, shim in metatube_shims]
                for _sid, fut in futs:  # 按 user order 收（submit 順序 = user order；非 as_completed）
                    try:
                        v = fut.result()
                        if v:
                            results_by_source[v.source] = v
                    except Exception:  # noqa: S112 — intentional skip-on-error in parallel scraper loop; individual source failure should not abort others
                        continue

        # rebuild all_data 按 enabled_sids（user-drag）順序，保全 merge 優先度契約
        # v.source == sid，對 builtin 和 metatube 均成立（mapper 設 source='metatube:{provider}'）
        all_data = {
            sid: results_by_source[sid]
            for sid in enabled_sids
            if sid in results_by_source
        }
    else:
        # explicit 單一來源 dispatch（CD-63c-6）。未知 id 理論上已被 validate_source_id 攔截，
        # factory 缺失時回空 list（行為等同舊 dead-else fallback）。
        factory = source_to_scraper.get(source)
        scrapers = factory() if factory else []

        for scraper in scrapers:
            try:
                scraper_name = scraper.__class__.__name__
                logger.debug(f"[Search] 嘗試 {scraper_name}...")
                video = scraper.search(number)
                if video:
                    all_data[video.source] = video
                    logger.debug(f"[Search] {scraper_name} 找到結果")
            except Exception as e:
                from core.cf_transport import CfChallengeRequired, CfTransportUnavailable
                if isinstance(e, (CfChallengeRequired, CfTransportUnavailable)):
                    raise          # bubble 給 router，不 continue
                # [CF-DIAG] DEBUG→INFO + 例外型別：explicit 分支是 JL 的唯一路徑
                # （manual_only）。型別讓 40 分鐘重現能分辨 WebViewException（死窗）
                # vs TimeoutError（靜默死亡）vs 其他——之前藏在 DEBUG 看不到。
                logger.info("[Search] %s 例外 %s: %s", scraper_name, type(e).__name__, e)
                continue

    if not all_data:
        logger.info(f"[Search] {number} 無結果")
        return None

    # 合併邏輯（TASK-61a-6 / CD-61-9）：
    # - explicit 單一來源（source != 'auto'）：整包贏，不走 merger（語意顯式化）。
    # - auto fan-out：呼叫 pure merger。封面跟 user_order（CD-plan-65-2）。
    if source != 'auto':
        # 單一來源直通：該來源資料原封不動
        main_video = next(iter(all_data.values()))
    else:
        # auto path: merge winner = first source in Active Row drag-sort order
        # (get_enabled_source_ids order); DMM Top-1 shortcut removed in feature/65.
        user_order = list(all_data.keys())  # already in get_enabled_source_ids() / drag order
        main_video = merge_results(all_data, user_order)

    # 補全 maker
    if not main_video.maker:
        maker = get_maker_by_prefix(number)
        if maker:
            main_video = main_video.model_copy(update={'maker': maker})

    result = main_video.to_legacy_dict()
    result['_source'] = main_video.source  # 保留內部欄位
    result.update(internal_nfo_carriers(main_video))  # _summary / _rating（NFO 用，to_legacy_dict 省略）
    logger.info(f"[Search] {number} 完成，來源: {main_video.source}")
    return result


def search_jav_single_source(
    number: str, source: str, proxy_url: str = '', javbus_lang: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """指定單一來源搜尋"""
    return search_jav(number, source=source, proxy_url=proxy_url, javbus_lang=javbus_lang)


def search_javlib_versions(number: str) -> List[Dict[str, Any]]:
    """javlibrary 同番號全版本列舉 → list[dict]（各版本 to_legacy_dict()）。

    CF 例外（CfChallengeRequired / CfTransportUnavailable）propagate 給呼叫端。
    """
    scraper = JavLibraryScraper()
    videos = scraper.search_all_versions(number)
    return [v.to_legacy_dict() for v in videos]


def fetch_javlib_by_detail_url(detail_url: str, number: str) -> Optional[Video]:
    """javlibrary 直抓單一 detail URL → Video（confirm 用）。

    CF 例外 propagate 給呼叫端。
    """
    scraper = JavLibraryScraper()
    return scraper.fetch_by_detail_url(detail_url, number)


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


def _javbus_keyword_search(
    name: str,
    limit: int,
    offset: int,
    status_callback: Optional[Callable[[str, str], None]],
    result_callback: Optional[Callable[[int, Any], None]],
    discovery_only: bool = False,
) -> List[Dict[str, Any]]:
    """JavBus keyword search — extracted from search_actress.

    Returns list[dict] (empty list on failure / no ids).
    JavDB fallback is NOT included; fuzzy fallback is limited to FUZZY_SEARCH_SOURCES.
    """
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
                        logger.error('_javbus_keyword_search: %s failed', num)

            if status_callback:
                status_callback('done', f'found:{len(results)}')
            return sort_results_by_date(results)

    except Exception as e:
        logger.error('_javbus_keyword_search failed: %s', e)

    return []


def _fuzzy_one(
    source: str,
    query: str,
    limit: int,
    offset: int,
    proxy_url: str,
    status_callback: Optional[Callable[[str, str], None]],
    result_callback: Optional[Callable[[int, Any], None]],
    discovery_only: bool = False,
) -> List[Dict[str, Any]]:
    """統一 adapter：將兩個 keyword 入口歸一為 list[dict]（空 → []，永不回 None）。

    Caller must already have confirmed DMM is enabled before passing 'dmm' here.

    discovery_only semantics: only javbus has a stub-return mode; all other sources
    perform full enrichment and therefore must NOT participate when discovery_only=True.
    """
    if discovery_only and source != 'javbus':
        return []

    if source == 'dmm':
        if status_callback:
            status_callback('dmm', 'searching')
        dmm_config = ScraperConfig(proxy_url=_dmm_proxy_url(proxy_url))
        dmm_scraper = DMMScraper(dmm_config)
        result = _dmm_keyword_search_progressive(
            dmm_scraper, query, limit, status_callback, result_callback, offset=offset
        )
        result = result if result is not None else []
        for d in result:
            d['_source'] = 'dmm'  # 鏡像 javbus（search_jav L354）：模糊結果補內部來源標記
        return result

    if source == 'javbus':
        return _javbus_keyword_search(
            query, limit, offset, status_callback, result_callback,
            discovery_only=discovery_only,
        )

    return []


def _fuzzy_search_chain(
    query: str,
    limit: int = 20,
    offset: int = 0,
    proxy_url: str = '',
    status_callback: Optional[Callable[[str, str], None]] = None,
    result_callback: Optional[Callable[[int, Any], None]] = None,
    discovery_only: bool = False,
) -> List[Dict[str, Any]]:
    """Active-Row-ordered fuzzy fallback chain (CD-plan-65-5).

    Iterates get_all_source_ids_ordered() ∩ FUZZY_SEARCH_SOURCES in order.
    Stops at first non-empty result. Passes result_callback only to the first
    actually-dispatched source (seed rule). Returns [] when chain is exhausted.
    """
    chain = [s for s in get_all_source_ids_ordered() if s in FUZZY_SEARCH_SOURCES]
    first_dispatched = False
    for source in chain:
        if source == 'dmm' and not _is_dmm_enabled(proxy_url):
            continue  # 不可達，跳過（不算 dispatched）
        cb = result_callback if not first_dispatched else None
        results = _fuzzy_one(
            source, query, limit, offset, proxy_url, status_callback, cb,
            discovery_only=discovery_only,
        )
        first_dispatched = True  # 第一個實際發動後，後續 seed 不送
        if results:
            return results
    return []


def search_actress(
    name: str,
    limit: int = 20,
    offset: int = 0,
    status_callback: Optional[Callable[[str, str], None]] = None,
    result_callback: Optional[Callable[[int, Any], None]] = None,
    proxy_url: str = '',
    discovery_only: bool = False,
) -> List[Dict[str, Any]]:
    """女優搜尋 — thin wrapper delegating to _fuzzy_search_chain."""
    return _fuzzy_search_chain(
        name,
        limit=limit,
        offset=offset,
        proxy_url=proxy_url,
        status_callback=status_callback,
        result_callback=result_callback,
        discovery_only=discovery_only,
    )


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


def _get_uncensored_sources(search_term: str) -> list[str]:
    """
    根據番號前綴決定無碼來源搜尋順序（spec US4 staged promotion，CD-63c-8）。

    先取 Active Row 中 enabled + available 且符合對應能力的 metatube 無碼 provider，
    prepend 到 builtin 清單前；fallback builtin 順序不變：
    - FC2 前綴 → metatube(FC2/FC2PPVDB/fc2hub) + ['fc2', 'avsox']
    - HEYZO 前綴 → metatube(HEYZO) + ['heyzo', 'avsox']
    - 其他（D2Pass 日期格式等）→ metatube(日期型 11) + ['d2pass', 'heyzo', 'fc2', 'avsox']

    無任何 metatube 無碼源啟用 → mt_pick=[] → 回傳純 builtin（與 B1 行為一致）。
    """
    # metatube_state / get_enabled_source_ids 皆已 module-level import（63c-1，line 29/34）
    from core.scrapers.utils import METATUBE_DATE_UNCENSORED

    # enabled + available + !manual_only 的 metatube 來源（按 order，含 availability gate）
    avail_map = metatube_state.availability_map()
    mt_enabled = [
        sid for sid in get_enabled_source_ids(availability_map=avail_map)
        if sid.startswith('metatube:')
    ]

    term_lower = search_term.lower().strip()
    if term_lower.startswith('fc2'):
        builtin = ['fc2', 'avsox']
        mt_pick = [s for s in mt_enabled
                   if s[len('metatube:'):] in ('FC2', 'FC2PPVDB', 'fc2hub')]
    elif term_lower.startswith('heyzo'):
        builtin = ['heyzo', 'avsox']
        mt_pick = [s for s in mt_enabled if s == 'metatube:HEYZO']
    else:
        builtin = ['d2pass', 'heyzo', 'fc2', 'avsox']
        mt_pick = [s for s in mt_enabled
                   if s[len('metatube:'):] in METATUBE_DATE_UNCENSORED]

    return mt_pick + builtin


def smart_search(query: str, limit: int = 20, offset: int = 0, status_callback: Optional[Callable[[str, str], None]] = None, uncensored_mode: bool = False, proxy_url: str = '', result_callback: Optional[Callable[[int, Any], None]] = None, discovery_only: bool = False) -> List[Dict[str, Any]]:
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
    #
    # ⚠️ 設計語意（feature/65 CL-3 / CD-65-7）：無碼模式下對女優名/關鍵字做模糊搜尋
    # **預期回空，此為設計而非 bug**。女優名經 _new_extract_number 取不到番號 → search_term
    # 退回原字串 → 丟給只做精確番號查的無碼來源（D2Pass/HEYZO/FC2/AVSOX）→ 必然無命中 →
    # 回空並於下方 return（永遠不會落到後面的模糊鏈 else 分支）。無碼番號命名無通則、模糊本
    # 就難命中；維持「安靜回空」是真正零改動的選擇（接 AVSOX keyword 搜或改走有碼 always-on
    # 反而要動更多 code，見 CD-65-7）。未來維護者勿把此處的空結果誤判為 bug。
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

    # 1. 精確搜尋 — 依優先序串接直打，命中即回（spec-85 B1，CD-85-1）
    if is_number_format(query):
        query = normalize_number(query)
        if offset > 0:
            return []

        avail_map = metatube_state.availability_map()
        enabled_sids = get_enabled_source_ids(availability_map=avail_map)
        for sid in enabled_sids:
            if status_callback:
                status_callback(sid, 'searching')
            try:
                res = search_jav_single_source(query, sid, proxy_url=proxy_url)
                if res:
                    res['_mode'] = 'exact'
                    if status_callback:
                        status_callback('done', 'found:1')
                    return [res]
            except Exception as e:
                logger.debug('fast-path %s miss/error: %s', sid, e)

        # 全部 miss（極冷門番號/打錯字）
        if status_callback:
            status_callback('done', 'found:0')
        return []

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
             results = search_actress(query, limit=limit, status_callback=status_callback, proxy_url=proxy_url)
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
        # CD-plan-65-5: chain = get_all_source_ids_ordered() ∩ FUZZY_SEARCH_SOURCES.
        # Chain result (including []) is final — "Active Row order is truth".
        # No post-chain fallback: a hardcoded jav321 fallback here would bypass Active Row
        # order and run jav321 a second time if it was already in the chain.
        results = search_actress(
            query,
            limit=limit,
            offset=offset,
            proxy_url=proxy_url,
            status_callback=status_callback,
            result_callback=result_callback if not discovery_only else None,
            discovery_only=discovery_only,
        )
        for r in results: r['_mode'] = 'actress'
        return results
