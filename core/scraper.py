"""
Scraper 模組（向後相容層）

此模組封裝了新的核心爬蟲模組，並提供與舊版 API 完全相容的介面。
包含 smart_search 等高階搜尋邏輯。
"""
import re
import time  # noqa: F401  # 測試 patch 點（core.scraper.time.sleep）＋provider 延後取用

from core.logger import get_logger
from core.config import load_config

logger = get_logger(__name__)
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, List, Dict, Any, Callable

# 引入新版爬蟲模組
from core.scrapers import (
    JavBusScraper, JAV321Scraper, JavDBScraper,
    FC2OfficialScraper, FC2JavtenScraper, AVSOXScraper,
    D2PassScraper, HEYZOScraper, DMMScraper,
    JavLibraryScraper,          # T3 新增
    Video
)
from core.scrapers.errors import SourceBlocked, SourceParseEmpty, SourceUnreachable
from core.scrapers.errors import CustomSourceRefused
from core.proxy_policy import source_needs_jp_ip
from core.scrapers.utils import (
    SOURCE_NAMES,
    extract_number as _new_extract_number,
    normalize_number_impl,
    is_strict_number,
    is_uncensored_route,
    resolve_route_target,
)
from core.maker_mapping import get_maker_by_prefix
from core.maker_latest import resolve_maker_studio  # noqa: F401  # 測試 patch 點＋provider 延後取用
from core.search_providers.javbus import JavBusProvider
from core.search_providers import registry
from core.search_providers.relay import search_by_intent, search_maker
from core.search_providers.types import Kind, MakerSearchResult, Window  # noqa: F401  # MakerSearchResult 重新匯出（web/routers/search.py 使用）
from core.source_merger import merge_results
from core.source_config import validate_source_id
from core.source_settings import get_enabled_source_ids
from core.source_settings import get_all_source_ids_ordered, is_source_enabled  # noqa: F401  # relay 與測試 patch 點（呼叫當下經 core.scraper 讀）

# 63c metatube routing imports（CD-63c-1 / CD-63c-2 / CD-63c-3）
from core.metatube.client import MetatubeHttpClient, pick_movie_result
from core.metatube.mapper import map_movie_info
from core.metatube.state import metatube_state
from core.metatube.errors import MetatubeUnavailable, MetatubeNotFound, MetatubeAuthError


# ============ 全域設定 ============

MAX_WORKERS = 2
REQUEST_DELAY = 0.3

# 前綴搜尋用到的全部 kinds＝前綴鏈（CODE）∪ actress 退路鏈（KEYWORD＋四個實體）；判斷「使用者有沒有開任何一家」用
_PREFIX_LADDER_KINDS = frozenset({Kind.CODE, Kind.KEYWORD, Kind.ACTOR, Kind.SERIES, Kind.DIRECTOR, Kind.LABEL})

# JavBus 語系對應表（zh-CN 無簡中版，沿用繁中 zh-tw）
_LOCALE_TO_JAVBUS = {"zh-TW": "zh-tw", "zh-CN": "zh-tw", "ja": "ja", "en": "en"}


def get_javbus_lang() -> str:
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
    return is_strict_number(s)


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


# ============ 63c metatube internal carrier keys ============

def internal_nfo_carriers(video) -> dict:
    """search_jav 注入、to_legacy_dict 刻意省略的內部 NFO carrier（_summary / _rating）。

    NFO writer 的 <plot>/<rating> 吃這組 `_` 前綴 carrier（見 enricher._scraper_to_meta），
    DB 不收。detail_url 預餵路徑（confirm 多版本）跳過 search_jav，需補同一組以對齊既有
    javlibrary 重刮的 NFO 輸出，否則 NFO 評分/簡介會掉（CD-63c-5 / PR #89 Codex P2）。
    key 集合是 `_summary` / `_rating`。
    """
    return {'_summary': video.summary, '_rating': video.rating}


# ============ 63c _MetatubeShim（CD-63c-3）============

class _MetatubeShim:
    """metatube provider 的 scraper-compatible shim（CD-63c-3）。

    讓 metatube provider 能插入現有 source_to_scraper 架構，
    使用相同的 .search() 介面，不改 search_jav() 的 scraper 迭代邏輯。
    """
    def __init__(self, provider: str, base_url: str, token: str,
                 generation: int | None = None) -> None:
        self.source = f'metatube:{provider}'
        self._provider = provider
        # TASK-113c-T3b：把已經傳進來的 base_url 存起來，供 map_movie_info() 出生時
        # 綁定 preview_cover_url 用（不新增 metatube_state 讀取點，值已在建構子參數裡）。
        self._base_url = base_url
        # TASK-130b-T6：建立這顆 shim 時的連線世代。search() 的兩個狀態回寫都帶著它，
        # 好讓一個屬於「已經被重連取代掉的舊連線」的遲到回應，寫不進新連線的狀態
        # （不變式 I-2）。與 core/metatube/probe.py:185/188 同一個契約——那邊早就接上了，
        # 搜尋這條路徑是唯一漏掉的一處。None = 不設圍欄（既有 mark_* 語意，供直接建構的測試用）。
        self._generation = generation
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
            video = map_movie_info(info, base_url=self._base_url)
            # routing 期 success → mark available（lazy liveness）
            metatube_state.mark_available(self.source, generation=self._generation)
            return video
        except MetatubeUnavailable:
            metatube_state.mark_failed(self.source, generation=self._generation)
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


# ============ 自訂來源（165）============

def _custom_factory(source: str, number: str) -> Callable[[], list]:
    """gate 通過 → 用 gate 檢查過的那份快照建 factory；不過 raise CustomSourceRefused。

    lazy import：只有 custom: 分支才會載入 core.custom_source（auto 與一般 import 零影響）。
    """
    from core.custom_source import gate, registry
    gate_result = gate.check_usable(source.split(':', 1)[1], number)
    if not gate_result.ok:
        raise CustomSourceRefused(gate_result.reason)
    return registry.factory_for(gate_result.loaded)


def search_custom_versions(source: str, number: str) -> List[Dict[str, Any]]:
    """custom:<id> 同番號全版本列舉 → list[dict]（形狀同 search_javlib_versions）。

    gate 不過 raise CustomSourceRefused；抓取例外原樣上拋給呼叫端映射。
    """
    scraper = _custom_factory(source, normalize_number(number))()[0]
    return [v.to_legacy_dict() for v in scraper.search_all_versions(number)]


def fetch_custom_by_detail_url(source: str, detail_url: str, number: str) -> Optional[Video]:
    """custom:<id> 直抓單一 detail URL → Video。跨網域由 CustomScraper 拋 blocked_target，原樣上拋。"""
    scraper = _custom_factory(source, normalize_number(number))()[0]
    return scraper.fetch_by_detail_url(detail_url, number)


def _source_display_name(source: str) -> str:
    """顯示名；custom: 取 YAML name，載入失敗／畸形 id 回 source 原字串；不過 gate、不拋。"""
    if not source.startswith('custom:'):
        return SOURCE_NAMES.get(source, source)
    try:
        from core.custom_source import registry
        loaded = registry.load_one(source.split(':', 1)[1])
        if loaded is not None and loaded.spec is not None:
            return loaded.spec.name
    except Exception:
        logger.debug("[Search] 自訂來源顯示名載入失敗: %s", source)
    return source


# ============ 核心搜尋函數 ============

VALID_JAVBUS_LANGS = {'zh-tw', 'ja', 'en'}


def build_card(video: Video, number: str) -> Dict[str, Any]:
    """單一來源的 Video → 結果卡 dict（legacy 形狀）。search_jav 尾段原樣抽出，JavBus 實體清單的 enrich 共用。

    number 是呼叫端已正規化的番號（缺 maker 時依它的前綴補）。
    """
    # 補全 maker
    if not video.maker:
        maker = get_maker_by_prefix(number)
        if maker:
            video = video.model_copy(update={'maker': maker})

    result = video.to_legacy_dict()
    result['_source'] = video.source  # 保留內部欄位
    result.update(internal_nfo_carriers(video))  # _summary / _rating（NFO 用，to_legacy_dict 省略）
    logger.info(f"[Search] {number} 完成，來源: {video.source}")
    return result


def search_jav(
    number: str, source: str = 'auto', javbus_lang: Optional[str] = None,
    surface_access_errors: bool = False, *, skip_format_check: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    搜尋 JAV 資訊（向後相容函數）

    surface_access_errors=True 時，explicit 單一來源遇到 SourceBlocked／SourceUnreachable
    （自訂來源另含 SourceParseEmpty；gate 不過則拋 CustomSourceRefused）
    會往上拋（讓呼叫端分得出「被拒／連不到」與「查無」）；預設 False 維持吞掉。auto 不受影響。
    """
    all_data: Dict[str, Video] = {}

    # 標準化番號
    number = normalize_number(number)

    # 來源 id 驗證（TASK-61a-3）：改用 validate_source_id() 取代舊 VALID_SOURCES set。
    # 'auto' 與 8 個 builtin id 通過；其餘 → return None（保留「未知來源不 raise」契約）。
    if not validate_source_id(source):
        logger.warning(f"[Search] 未知來源: {source}")
        return None
    skip_format_check = bool(skip_format_check) and source == 'javdb'

    # javbus_lang 校驗 + config fallback（auto 與 explicit javbus 共用）
    if javbus_lang is not None and javbus_lang not in VALID_JAVBUS_LANGS:
        logger.warning("[Search] 無效的 javbus_lang: %s，fallback 到 config", javbus_lang)
        javbus_lang = None
    _javbus_lang = javbus_lang if javbus_lang is not None else get_javbus_lang()

    # 來源 id → scraper factory（無參數 callable，回 scraper instance list）。
    # DMM 與 JavBus 是攜帶 closure 參數的特例：
    #   - dmm：一律建立（開關看膠囊；代理由 proxy policy 決定）。
    #   - javbus：帶校驗後的 lang。
    # explicit 指定來源與 auto fan-out 共用同一份定義。
    source_to_scraper = {
        'dmm': lambda: [DMMScraper()],
        'javbus': lambda: [JavBusScraper(lang=_javbus_lang)],
        'jav321': lambda: [JAV321Scraper()],
        'javdb': lambda: [JavDBScraper(skip_format_check=skip_format_check)],
        'd2pass': lambda: [D2PassScraper()],
        'heyzo': lambda: [HEYZOScraper()],
        'fc2': lambda: [FC2OfficialScraper()],
        'avsox': lambda: [AVSOXScraper()],
        'javlibrary': lambda: [JavLibraryScraper()],
        'fc-javten': lambda: [FC2JavtenScraper()],
    }

    # 63c：動態注入 metatube provider（CD-63c-2）
    # availability_map 的 False entry 仍加進 source_to_scraper——
    # get_enabled_source_ids(availability_map) 已在上一層排除不可達的 source，
    # 不需 double-gate（explicit picker 選當前 probe-failed provider 也應能試打）。
    if metatube_state.is_connected:
        # TASK-130b-T6：四個值必須來自同一次鎖獲取（不變式 I-1）。過去這裡是
        # base_url / token / availability_map() 三次獨立讀取，重連可以穿插在中間，
        # 做出一顆「拿著新連線的網址、卻蓋著舊連線世代章」的 shim。probe_snapshot()
        # 是現成的單鎖快照（CD-66b-3 為同一類 race 而生），直接用，不新增讀取點。
        _mt_names, _mt_gen, _mt_url, _mt_token = metatube_state.probe_snapshot()
        for _mt_provider in _mt_names:
            _mt_name = f'metatube:{_mt_provider}'
            # 用 default arg 固定 closure variable capture（風險點 a）
            source_to_scraper[_mt_name] = (
                lambda _pname=_mt_provider, _url=_mt_url, _tok=_mt_token, _gen=_mt_gen:
                    [_MetatubeShim(_pname, _url, _tok, _gen)]
            )

    # 165：explicit custom:<id> 先過 gate，通過才用 gate 檢查過的那份快照建 scraper；
    # auto 路徑完全不碰 custom（不 import、不 gate、不讀目錄）。
    if source.startswith('custom:'):
        try:
            source_to_scraper[source] = _custom_factory(source, number)
        except CustomSourceRefused as refused:
            if surface_access_errors:
                raise
            logger.info("[Search] 自訂來源 %s 未放行: %s", source, refused.reason)
            return None

    # 決定要跑哪些爬蟲（auto vs. explicit）
    logger.info(f"[Search] {number} 使用來源: {source}")
    if source == 'auto':
        # auto fan-out（CD-63c-4）：
        # - builtin：循序執行（維持既有行為）
        # - metatube：defer 到 ThreadPoolExecutor 並行（bounded parallel fan-out）
        # - 結果以 enabled_sids 順序重建 all_data（保全 user-drag merge 優先度）
        # get_enabled_source_ids 傳入 routing_availability_map 讓 metatube gate 生效（🔴 CRITICAL；routing 版含冷卻樂觀重試，顯示端不得用）
        enabled_sids = get_enabled_source_ids(availability_map=metatube_state.routing_availability_map())
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
                if surface_access_errors and isinstance(e, (SourceBlocked, SourceParseEmpty, SourceUnreachable)):
                    raise
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

    return build_card(main_video, number)


def search_jav_single_source(
    number: str, source: str, javbus_lang: Optional[str] = None,
    surface_access_errors: bool = False, *, skip_format_check: bool = False,
) -> Optional[Dict[str, Any]]:
    """指定單一來源搜尋"""
    return search_jav(
        number, source=source, javbus_lang=javbus_lang,
        surface_access_errors=surface_access_errors, skip_format_check=skip_format_check,
    )


def access_error_info(exc: Exception, source: str) -> Dict[str, str]:
    """SourceBlocked／SourceUnreachable → {access_error, source, message}（兩個端點共用）。"""
    name = _source_display_name(source)
    if not isinstance(exc, SourceBlocked):
        return {
            "access_error": "unreachable", "source": source,
            "message": f"{name} 連不到，請檢查網路或代理設定",
        }
    message = f"{name} 拒絕連線"
    if source_needs_jp_ip(source):
        message += "。部分地區需要日本 IP，可在 Proxy 欄設定"
    return {"access_error": "refused", "source": source, "message": message}


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
                   discovery_only: bool = False,
                   *, cursor: Optional[str] = None, meta: Optional[dict] = None) -> List[Dict[str, Any]]:
    """局部搜尋（175a-T7：經 relay 接力；partial 不看 limit）。cursor／meta 為 175d 續頁契約，原樣轉給 relay。"""
    return search_by_intent("partial", partial, Window(0, 0), status_callback=status_callback, result_callback=result_callback, discovery_only=discovery_only, cursor=cursor, meta=meta)


def search_prefix(prefix: str, limit: int = 20, offset: int = 0, status_callback: Optional[Callable[[str, str], None]] = None, result_callback: Optional[Callable[[int, Any], None]] = None, discovery_only: bool = False, *, cursor: Optional[str] = None, meta: Optional[dict] = None) -> List[Dict[str, Any]]:
    """前綴搜尋（175a-T7：經 relay 接力）。cursor／meta 為 175d 續頁契約，原樣轉給 relay。"""
    return search_by_intent("prefix", prefix, Window(offset, limit), status_callback=status_callback, result_callback=result_callback, discovery_only=discovery_only, cursor=cursor, meta=meta)


def _javbus_keyword_search(
    name: str,
    limit: int,
    offset: int,
    status_callback: Optional[Callable[[str, str], None]],
    result_callback: Optional[Callable[[int, Any], None]],
    discovery_only: bool = False,
    *,
    ids_provider: Optional[Callable[[JavBusScraper, int], List[str]]] = None,
) -> List[Dict[str, Any]]:
    """JavBus keyword search — extracted from search_actress（175a-T4：實作搬進 JavBusProvider，此處為 shim）。

    ids_provider（173）：取代「取番號那一步」，簽名 (scraper, page) -> ids；None＝關鍵字搜尋。
    Returns list[dict] (empty list on failure / no ids).
    JavDB fallback is NOT included; 模糊搜尋的來源由 search_providers 註冊表決定。
    """
    return JavBusProvider().run_keyword(name, limit, offset, status_callback, result_callback, discovery_only, ids_provider=ids_provider)


def search_maker_latest(
    maker_key: str,
    label: str,
    spellings,
    offset: int,
    *,
    titles,
    today,
    status_callback: Optional[Callable[[str, str], None]] = None,
    result_callback: Optional[Callable[[int, Any], None]] = None,
    db_path=None,
    cursor: Optional[str] = None,
    meta: Optional[dict] = None,
) -> MakerSearchResult:
    """片商最新作品（經 relay 接力，限 30 部一頁；175b-T8b）。cursor／meta 為 175d 續頁契約，原樣轉給 relay。"""
    return search_maker(maker_key, label, spellings, offset, titles=titles, today=today, status_callback=status_callback, result_callback=result_callback, db_path=db_path, cursor=cursor, meta=meta)


def search_actress(
    name: str,
    limit: int = 20,
    offset: int = 0,
    status_callback: Optional[Callable[[str, str], None]] = None,
    result_callback: Optional[Callable[[int, Any], None]] = None,
    discovery_only: bool = False,
    *,
    cursor: Optional[str] = None,
    meta: Optional[dict] = None,
) -> List[Dict[str, Any]]:
    """女優搜尋（175a-T7：經 relay 接力；來源與順序由註冊表＋設定頁順序決定）。cursor／meta 為 175d 續頁契約。"""
    return search_by_intent("actress", name, Window(offset, limit), status_callback=status_callback, result_callback=result_callback, discovery_only=discovery_only, cursor=cursor, meta=meta)


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
    avail_map = metatube_state.routing_availability_map()
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


def _library_title_list(db_path):
    """邏輯片單（同 web/routers/search.py 的 _library_titles；T9 不重構舊碼，兩份並存）。"""
    from core.config import get_configured_gallery_dirs
    from core.database import VideoRepository
    from core.library_titles import logical_title_firsts

    configured_dir_uris, path_mappings = get_configured_gallery_dirs(load_config())
    repo = VideoRepository(db_path)
    return logical_title_firsts(repo.get_library_title_rows(), configured_dir_uris, path_mappings)


def _search_maker_intent(query, maker_key, limit, offset, status_callback, result_callback, meta=None, cursor=None):
    """smart_search 的 maker 分支：片庫樣本＋拼法交給 relay.search_maker，逐卡標 _mode（不送 mode 事件）。

    meta 同時交給 relay（它寫 cursor／answered_by）；這裡只加 has_more。"""
    import datetime

    from core.database import get_db_path
    from core.maker_names import maker_spellings

    db_path = get_db_path()
    try:
        titles = _library_title_list(db_path)
    except Exception as e:  # 片庫只是樣本來源，探針仍可答（待審 D1）
        logger.warning('maker search: 無法讀取片庫片單，以空片單繼續（%s）', e)
        titles = []
    result = search_maker(
        maker_key, query, maker_spellings(query), offset, limit=limit, titles=titles,
        today=datetime.date.today(), status_callback=status_callback,
        result_callback=result_callback, db_path=db_path, cursor=cursor, meta=meta,
    )
    for card in result.results:
        card['_mode'] = 'maker'
    if meta is not None:
        meta['has_more'] = result.has_more
    return result.results


def smart_search(query: str, limit: int = 20, offset: int = 0, status_callback: Optional[Callable[[str, str], None]] = None, uncensored_mode: bool = False, result_callback: Optional[Callable[[int, Any], None]] = None, discovery_only: bool = False, resolve_makers: bool = False, *, meta: Optional[dict] = None, cursor: Optional[str] = None) -> List[Dict[str, Any]]:  # noqa: C901 — 無碼/有碼兩條搜尋鏈並存於同一函式；CD-65-7 已明文交代無碼模式模糊搜尋「預期回空」的設計語意，拆分會把這段語意說明從呼叫點剝離、增加誤讀風險
    """
    智慧搜尋：自動判斷搜尋類型並執行

    Args:
        query: 搜尋關鍵字
        limit: 結果數量限制
        offset: 分頁偏移
        status_callback: 狀態回調函數
        uncensored_mode: 無碼模式（只搜 AVSOX / FC2）
        resolve_makers: 互動搜尋才傳 True（175b 接線）；預設不讀片庫、不辨識片商
        meta: 呼叫端傳入的空 dict，由 relay／maker 分支寫 has_more／cursor／answered_by
        cursor: 上一頁回傳的續頁 token（175d）；只在 offset>0 才有作用
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
            result = search_jav(search_term, source=unc_source)
            if result:
                break

        results = [result] if result else []
        if status_callback:
            status_callback('done', f'found:{len(results)}')
        for r in results:
            r['_mode'] = 'uncensored'
        return results

    # 139b-T9（CD-b3 B＋ 對稱修法）：candidate 只算一次，G 與 C 都問它。
    target = resolve_route_target(query)

    # 0. 無碼特殊處理 - 自動偵測（FC2 / HEYZO / 日期-編號格式）
    is_uncensored = is_uncensored_route(target)
    if is_uncensored:
        if status_callback:
            status_callback('mode', 'uncensored')
        search_term = target
        result = None
        unc_sources = _get_uncensored_sources(search_term)
        for unc_source in unc_sources:
            if status_callback:
                status_callback(unc_source, 'searching')
            result = search_jav(search_term, source=unc_source)
            if result:
                break
        results = [result] if result else []
        if status_callback:
            status_callback('done', f'found:{len(results)}')
        for r in results:
            r['_mode'] = 'uncensored'
        return results

    # 查詢分類（175a-T7：core.query_intent.classify_query；兩道前置閘留在其前）
    from core.query_intent import classify_query
    from core.maker_names import known_makers
    known = known_makers() if resolve_makers else frozenset()
    intent = classify_query(query, known, resolve_makers=resolve_makers)
    if intent.mode == 'maker':
        return _search_maker_intent(query, intent.maker_key, limit, offset, status_callback, result_callback, meta, cursor)

    # 1. 精確搜尋 — 依優先序串接直打，命中即回（spec-85 B1，CD-85-1）
    if intent.mode == 'exact':
        query = normalize_number(target)
        if offset > 0:
            return []

        avail_map = metatube_state.routing_availability_map()
        enabled_sids = get_enabled_source_ids(availability_map=avail_map)
        for sid in enabled_sids:
            if status_callback:
                status_callback(sid, 'searching')
            try:
                res = search_jav_single_source(query, sid)
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
    elif intent.mode == 'partial':
        if offset > 0: return []
        results = search_partial(query, status_callback=status_callback, result_callback=result_callback, discovery_only=discovery_only)
        for r in results: r['_mode'] = 'partial'
        return results

    # 3. 前綴搜尋
    elif intent.mode == 'prefix':
        if not registry.providers_for(_PREFIX_LADDER_KINDS):
            return []
        results = search_prefix(query, limit=limit, offset=offset, status_callback=status_callback, result_callback=result_callback, discovery_only=discovery_only, cursor=cursor, meta=meta)
        mode = 'prefix'

        # 載入更多（offset>0）時清單已經存在：前綴到底就是到底，不退到女優／jav321（那是另一份清單的第一頁；CD-175d-9）
        if not results and offset > 0:
            return []

        if not results:
             # Fallback to actress（不透傳 result_callback：prefix 的 seed 已送出，
             # actress fallback 不可送第二個 seed，避免 slot index 錯位）
             if status_callback: status_callback('mode', 'actress')
             results = search_actress(query, limit=limit, status_callback=status_callback, discovery_only=discovery_only, meta=meta)
             if results: mode = 'actress'

        if not results and is_source_enabled('jav321'):
             # Fallback to keyword（search_jav321_keyword 無 as_completed，不透傳 result_callback）
             if status_callback: status_callback('mode', 'keyword')
             results = search_jav321_keyword(query, limit=limit, status_callback=status_callback)
             if results: mode = 'keyword'

        for r in results: r['_mode'] = mode
        return results

    # 4. 女優/關鍵字搜尋
    else:
        # CD-plan-65-5: chain = 設定頁順序 ∩ search_providers 註冊表（175a-T7）。
        # Chain result (including []) is final — "Active Row order is truth".
        # No post-chain fallback: a hardcoded jav321 fallback here would bypass Active Row
        # order and run jav321 a second time if it was already in the chain.
        results = search_actress(
            query,
            limit=limit,
            offset=offset,
            status_callback=status_callback,
            result_callback=result_callback if not discovery_only else None,
            discovery_only=discovery_only,
            cursor=cursor,
            meta=meta,
        )
        for r in results: r['_mode'] = 'actress'
        return results
