"""
搜尋 API 路由

端點：
- GET  /api/proxy-image              — 代理外部圖片請求（解決防盜鏈問題）
- GET  /api/search                   — 搜尋 JAV 資訊（REST，支援番號/女優/局部番號）
- GET  /api/search/stream            — 搜尋 JAV 資訊（SSE 串流，即時回報狀態與結果）
- GET  /api/search/sources           — 取得可用的搜尋來源列表
- GET  /api/search/favorite-files    — 取得我的最愛資料夾的影片檔案列表
- POST /api/search/filter-files      — 過濾檔案列表（移除非影片或過小檔案）
- GET  /api/search/local-status      — 批次查詢番號在本地庫的存在狀態
"""

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response, StreamingResponse, JSONResponse
from typing import Optional, List, Dict
import re
import requests
import json
import asyncio
from collections import Counter
from pathlib import Path
from queue import Queue
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

from pydantic import BaseModel

from core.logger import get_logger
from core.video_extensions import ZERO_SIZE_EXTENSIONS, get_video_extensions
logger = get_logger(__name__)

from core.database import VideoRepository, get_db_path as get_db_path, init_db
from core.image_codec import (
    decode_image_payload,
    image_media_type,
    looks_like_image,
)
from core.image_host_policy import (
    codec_for_host,
    proxy_verdict,
)
from core.maker_mapping import load_prefix_mapping
from core.source_config import validate_source_id
from web.routers._custom_gate import refusal_for # noqa: PLC2701 — 卡片指定的 web 內部底線模組（165-T7b），同 router 層共用 gate 句表，尚未升格為公開名
from core.source_settings import get_switchable_source_ids_ordered, is_uncensored_mode_effective
from core.auto_organize_state import mark_manual_activity, request_abort, get_status
from core.config import load_config, mutate_config
from core.favorite_scan import resolve_favorite_folder
from core.proxy_policy import proxy_kwargs
from web import auto_organize_scheduler

from core.scraper import (
    search_jav, smart_search, is_partial_number, is_number_format,
    is_prefix_only, search_partial, search_actress,
)
from core.scrapers.utils import SOURCE_NAMES, resolve_route_target

router = APIRouter(prefix="/api", tags=["search"])

# 載入片商前綴對照表（啟動時一次性載入）
_MAKER_MAPPING = load_prefix_mapping()


def _is_allowed_image_url(url: str) -> bool:
    """判準本體已搬到 `core/image_host_policy.proxy_verdict()`（132b review round-2）。

    搬家的理由不是整潔：`core/scrapers/javdb_api.py` 的圖片閘也要問同一個問題，
    而 core 不能 import web。留在這裡就只能在 core 再寫一份近似判斷，
    然後那份會比這份寬鬆（放行 `http://` 與 download-only 的 host）。

    本函式現在只剩 log——403 的原因字串仍由這裡輸出，格式不變。
    """
    verdict = proxy_verdict(url)
    if verdict.allowed:
        return True
    logger.warning(
        "proxy_image 拒絕: host=%s scheme=%s 原因=%s",
        verdict.host, verdict.scheme, verdict.reason,
    )
    return False


@router.get("/proxy-image")
def proxy_image(url: str = Query(..., description="圖片 URL")):
    """
    圖片代理 - 解決防盜鏈問題
    """
    if not _is_allowed_image_url(url):
        return Response(status_code=403)
    try:
        # 根據 URL 設置對應的 Referer
        referer = ""
        if "javbus.com" in url:
            referer = "https://www.javbus.com/"
        elif "dmm.co.jp" in url:
            referer = "https://www.dmm.co.jp/"
        elif "jav321.com" in url:
            referer = "https://www.jav321.com/"

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': referer,
        }

        # SSRF guard: 不跟隨 redirect（CD-113c-7）。白名單只驗原始 URL，
        # 若對方 30x 到內網，跟隨會繞過驗證。照抄 core/metatube/client.py。
        resp = requests.get(url, headers=headers, timeout=10, allow_redirects=False, **proxy_kwargs('image', url=url))
        if 300 <= resp.status_code < 400:
            location = resp.headers.get("Location", "")
            try:
                loc_host = urlparse(location).hostname or "<unparseable>"
            except Exception:
                loc_host = "<unparseable>"
            req_host = urlparse(url).hostname or ""
            logger.warning(
                "proxy_image 拒絕 3xx: host=%s status=%s location_host=%s",
                req_host, resp.status_code, loc_host,
            )
        elif resp.status_code == 200:
            host = (urlparse(url).hostname or "").lower()
            # 沒標 codec 的 host（既有 28 筆全部）走原路：內容與標頭逐位元不變。
            # 範圍為什麼不擴到全部 host，見 core/organizer.py 同一處的註解。
            if codec_for_host(host) is None:
                return Response(
                    content=resp.content,
                    media_type=resp.headers.get("Content-Type", "image/jpeg"),
                    headers={"Cache-Control": "public, max-age=86400"},
                )
            payload = decode_image_payload(host, resp.content)
            if not looks_like_image(payload):
                logger.warning(
                    "proxy_image 拒絕: host=%s 原因=解碼後不是圖片", host
                )
            else:
                # 上游回的是 binary/octet-stream；沿用它的話瀏覽器不會 render。
                # 型別改用**解出來的位元組**判定。
                return Response(
                    content=payload,
                    media_type=image_media_type(payload) or "image/jpeg",
                    headers={"Cache-Control": "public, max-age=86400"},
                )
    except Exception:
        # CD-113c-8 的同一條原則（圖片 URL 常帶簽名／token，不記完整 URL）套用到
        # 例外路徑：原本這行記的是**完整 url**——含 query 的 token，以及 T3b 之後
        # 可能出現的 metatube base_url userinfo（Codex PR review P1 的相鄰洩漏點，
        # 由 review subagent 實測指出）。改記 host + path，保留診斷價值、去掉機密。
        _p = urlparse(url)
        logger.exception(
            "proxy_image failed: host=%s path=%s", _p.hostname, _p.path
        )

    # 返回空圖片
    return Response(content=b'', media_type='image/jpeg', status_code=404)


@router.get("/search")
def search(
    q: str = Query(..., description="番號、局部番號、或女優名"),
    mode: str = Query("auto", description="搜尋模式: auto/exact/partial/actress"),
    source: Optional[str] = Query(None, description="指定來源: javbus/jav321/javdb/fc2/avsox"),
    limit: int = Query(20, description="每頁結果數", ge=1, le=50),
    offset: int = Query(0, description="跳過前 N 個結果（用於分頁）", ge=0),
    since: Optional[str] = Query(None, description="日期過濾（YYYY-MM-DD），只回傳此日期之後的結果"),
    discovery: bool = Query(False, description="輕量探索模式：只取番號+標題，不取封面/女優詳情")
) -> dict:
    """
    搜尋 JAV 資訊

    - **q**: 搜尋關鍵字（必填）
    - **mode**: 搜尋模式
        - auto: 自動判斷（預設）
        - exact: 精確番號搜尋
        - partial: 局部番號搜尋
        - actress: 女優搜尋
    - **source**: 指定來源（僅 exact 模式有效）
        - javbus: JavBus
        - jav321: Jav321
        - javdb: JavDB
        - fc2: FC2
        - avsox: AVSOX
    - **limit**: 每頁結果數（預設 20，最大 50）
    - **offset**: 跳過前 N 個結果，用於載入更多
    """
    q = q.strip()
    if not q or len(q) < 2:
        return {"success": False, "error": "請輸入有效的搜尋關鍵字", "data": [], "total": 0}

    # 驗證 since 格式
    if since is not None:
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', since):
            return JSONResponse(status_code=400, content={"success": False, "error": "since 參數格式錯誤，需為 YYYY-MM-DD"})

    # 驗證 source 參數
    if source is not None and not validate_source_id(source):
        return JSONResponse(status_code=400, content={"success": False, "error": f"未知來源: {source}"})

    # source 只在 exact 模式生效（CD-135-9 / AC-13）；auto 語意上不是「指定了具體來源」
    # （見 core/source_config.py:244 的特判），不受本檢查限制
    if source is not None and source != "auto" and mode != "exact":
        return JSONResponse(status_code=400, content={"success": False, "error": "source 僅在 mode=exact 時生效，請改用 mode=exact 或移除 source"})

    # 讀取設定（無碼模式）
    from core.config import load_config
    config = load_config()
    uncensored_mode = is_uncensored_mode_effective(config)

    # discovery 僅在明確指定 actress/partial/prefix 模式時生效
    # auto 不含：auto 內部自動選路，discovery_only 會干擾 keyword fallback
    use_discovery = discovery and mode in ('actress', 'partial', 'prefix')

    # 自動模式使用 smart_search
    if mode == "auto":
        results = smart_search(q, limit=limit, offset=offset, uncensored_mode=uncensored_mode, discovery_only=use_discovery)
    elif mode == "exact":
        if source:
            # 指定來源搜索
            from core.scraper import search_jav_single_source, access_error_info
            from core.scrapers.errors import SourceBlocked, SourceParseEmpty, SourceUnreachable
            from core.cf_transport import CfChallengeRequired, CfTransportUnavailable
            if source.startswith('custom:'):
                refused = refusal_for(source, q)
                if refused:
                    return JSONResponse(status_code=400, content={
                        "success": False, "error": refused[1],
                        "reason": "custom_source_refused", "custom_reason": refused[0],
                    })
            try:
                data = search_jav_single_source(
                    q, source, surface_access_errors=True,
                )
            # CD-70c-4: search entry does NOT wire the interactive CF flow (no begin_solve,
            # no cf_needed). The JavLibrary pill is hidden in search context when
            # cf_transport_available is false (frontend isJlUnavailable), so this path is
            # UI-unreachable; these blocks exist only as a structured 500-guard fallback.
            # TASK-118a-T4：這條路 UI 不可達（CD-70c-4），字面對 fc-javten 不準，刻意不動。
            except CfChallengeRequired:
                logger.warning("search: CfChallengeRequired for source=%s q=%s", source, q)
                return {
                    "success": False,
                    "error": "JavLibrary 需要解決 CF 驗證（請使用桌面應用程式）",
                    "data": [],
                    "total": 0,
                    "mode": "exact",
                    "has_more": False,
                    "actress_profile": None,
                }
            except CfTransportUnavailable:
                logger.warning("search: CfTransportUnavailable for source=%s q=%s", source, q)
                return {
                    "success": False,
                    "error": "JavLibrary 僅限桌面應用程式（standalone）使用",
                    "data": [],
                    "total": 0,
                    "mode": "exact",
                    "has_more": False,
                    "actress_profile": None,
                }
            except SourceParseEmpty:
                from web.routers._custom_preview import parse_empty_text  # noqa: PLC2701 — 卡片指定的 web 內部底線模組（165-T7b）；lazy import 以免 import 時載入 core.custom_source*（AC-165-8）
                logger.warning("search: parse_empty source=%s q=%s", source, q)
                return {
                    "success": False,
                    "error": parse_empty_text(source),
                    "custom_error": "parse_empty",
                    "source": source,
                    "data": [],
                    "total": 0,
                    "mode": "exact",
                    "has_more": False,
                    "actress_profile": None,
                }
            except (SourceBlocked, SourceUnreachable) as e:
                info = access_error_info(e, source)
                logger.warning("search: %s source=%s q=%s", info["access_error"], source, q)
                return {
                    "success": False,
                    "error": info["message"],
                    "access_error": info["access_error"],
                    "source": source,
                    "data": [],
                    "total": 0,
                    "mode": "exact",
                    "has_more": False,
                    "actress_profile": None,
                }
            results = [data] if data else []
        else:
            # 精確搜索（使用 smart_search 的 exact 模式）
            data = search_jav(q)
            results = [data] if data else []
    elif mode == "partial":
        results = search_partial(q, discovery_only=use_discovery)
    elif mode == "actress":
        results = search_actress(q, limit=limit, offset=offset, discovery_only=use_discovery)
    else:
        results = smart_search(q, limit=limit, offset=offset, discovery_only=use_discovery)

    detected_mode = mode if mode != "auto" else _detect_mode(q)

    # since post-filter: 保留 date >= since 的結果（缺 date 或空 date 保留）
    if since and results:
        results = [r for r in results if not r.get('date') or r['date'] >= since]

    if results:
        # discovery 模式不觸發 actress_profile / consistency check
        actress_profile = None
        if not use_discovery and detected_mode in ('actress', 'prefix'):
            top_actor = _analyze_top_actor(results, threshold=0.8, min_samples=3)
            if top_actor:
                logger.info(f"[Actress Profile] Fetching profile for: {top_actor}")
                actress_profile = _fetch_actress_profile_with_db(top_actor, _extract_top_makers(results))
                if not actress_profile:
                    logger.info(f"[Actress Profile] Not found for: {top_actor}")

        # 判斷是否還有更多結果（prefix/actress 模式且結果數 = limit）
        has_more = detected_mode in ('prefix', 'actress') and len(results) >= limit

        response_data = {
            "success": True,
            "data": results,
            "total": len(results),
            "mode": detected_mode,
            "offset": offset,
            "has_more": has_more,
            "actress_profile": actress_profile
        }
        # discovery flag 只在實際走 discovery 路徑時才標記（auto→exact 不算）
        if use_discovery and detected_mode in ('actress', 'partial', 'prefix'):
            response_data["discovery"] = True
        return response_data

    base_response = {
        "success": False,
        "error": f"找不到 {q} 的資料",
        "data": [],
        "total": 0,
        "mode": detected_mode,
        "has_more": False,
        "actress_profile": None
    }
    if use_discovery and detected_mode in ('actress', 'partial', 'prefix'):
        base_response["discovery"] = True
    return base_response


def _extract_top_makers(results: list) -> list:
    """從搜尋結果統計出現最多的前 2 個片商名"""
    counter = Counter()
    for r in results:
        number = r.get('number', '')
        match = re.match(r'^([A-Za-z]+)', number)
        if match:
            prefix = match.group(1).upper()
            maker = _MAKER_MAPPING.get(prefix)
            if maker:
                counter[maker] += 1
    return [maker for maker, _ in counter.most_common(2)]


def _detect_mode(q: str) -> str:
    """偵測搜尋模式"""
    target = resolve_route_target(q)
    if is_number_format(target):
        return "exact"
    elif is_partial_number(q):
        return "partial"
    elif is_prefix_only(q):
        return "prefix"
    else:
        return "actress"


def _normalize_actress_name(name: str) -> str:
    """正規化女優名稱（consistency check 用）"""
    import unicodedata
    name = name.strip()
    # 全形 → 半形
    name = unicodedata.normalize('NFKC', name)
    # 統一空白符
    name = ' '.join(name.split())
    return name


def _analyze_top_actor(results: List[Dict], threshold: float = 0.8, min_samples: int = 3) -> Optional[str]:
    """
    分析搜尋結果中的主要演員（consistency check）

    Args:
        results: 搜尋結果列表
        threshold: 演員佔比閾值（預設 80%）
        min_samples: 最小樣本數（少於此數不觸發）

    Returns:
        主要演員名稱，未通過檢查返回 None

    邏輯：
    1. 結果數 < min_samples → 跳過
    2. 統計有 actors 欄位的結果中各女優出現次數
    3. 最多者佔比 >= threshold → 通過
    4. 名稱正規化：strip + 全形→半形 + 統一空白
    """
    from collections import Counter

    if not results or len(results) < min_samples:
        return None

    # 統計演員出現次數
    actor_counter = Counter()
    valid_results_count = 0  # 有 actors 欄位的結果數

    for result in results:
        actors = result.get('actors', [])
        if not actors:
            continue  # 無 actors 欄位 → 不計入分母

        valid_results_count += 1

        # 處理不同格式
        if isinstance(actors, list):
            for actor in actors:
                if isinstance(actor, str):
                    actor_name = actor
                elif isinstance(actor, dict):
                    actor_name = actor.get('name', '')
                else:
                    continue

                if actor_name:
                    # 正規化名稱
                    normalized = _normalize_actress_name(actor_name)
                    actor_counter[normalized] += 1
        elif isinstance(actors, str):
            if actors:
                normalized = _normalize_actress_name(actors)
                actor_counter[normalized] += 1

    if not actor_counter or valid_results_count < min_samples:
        return None

    # 找出出現最多的演員
    top_actor, top_count = actor_counter.most_common(1)[0]

    # 計算佔比（分母 = 有 actors 的結果數）
    ratio = top_count / valid_results_count

    logger.info(f"[Consistency] Top actor: {top_actor} ({top_count}/{valid_results_count} = {ratio:.1%})")

    if ratio >= threshold:
        return top_actor
    else:
        logger.info(f"[Consistency] Ratio {ratio:.1%} < {threshold:.0%}, skip actress_profile")
        return None


def _fetch_actress_profile_with_db(top_actor: str, makers: list) -> Optional[dict]:
    """
    DB 優先查詢：
    1. 查 ActressRepository
    2. DB hit → 組裝 response（本地照片 URL），附加 is_favorite=True
    3. DB miss → 走 orchestrator，附加 is_favorite=False

    Returns:
        profile dict（前端 actressProfile），或 None（查無資料）
    """
    from core.database import ActressRepository, AliasRepository, init_db
    from web.routers.actress import _actress_to_response  # noqa: PLC2701 — 共用 serializer，避免重複邏輯：DB-hit 分支需要與 actress router 用同一份序列化，維持兩處回應欄位一致

    init_db()
    repo = ActressRepository()
    alias_repo = AliasRepository()
    names = alias_repo.resolve(top_actor)  # set[str], miss → {top_actor}
    actress = None
    for n in names:
        actress = repo.get_by_name(n)
        if actress:
            break

    if actress:
        # DB hit：組裝 actressProfile（前端 legacy flat shape 相容）
        profile = _actress_to_response(actress)
        profile["is_favorite"] = True
        # 補 legacy flat shortcuts（現有 template 依賴）
        profile["img"] = profile.get("photo_url")
        return profile

    # DB miss：走 orchestrator（ProfileResult 回傳型別，T3 已改）
    from core.scrapers.actress.orchestrator import get_actress_profile
    result = get_actress_profile(top_actor, makers=makers)
    profile = result.data  # ProfileResult.data
    if profile:
        profile["is_favorite"] = False
        # 補齊前端需要的頂層欄位（orchestrator legacy flat shape 缺 aliases/tags 等）
        from web.routers.actress import _flatten_aliases  # noqa: PLC2701 — orchestrator legacy flat shape 缺 aliases 欄位，需要借用 actress router 同一套別名扁平化補齊，理由同 web/routers/actress_alias.py:26（同一私有名的另一個呼叫點）
        text = profile.get("text") or {}
        profile["aliases"] = _flatten_aliases(text.get("aliases"))
        profile["tags"] = text.get("tags") or []
        profile["agency"] = text.get("agency")
        profile["nickname"] = text.get("nickname")
        profile["debut_work"] = text.get("debut_work")
        profile["blog_url"] = text.get("blog_url")
        profile["official_url"] = text.get("official_url")
        profile["primary_text_source"] = profile.get("primary_text_source")
        profile["photo_source"] = profile.get("photo_source")
    return profile


_BATCH_MAX_WORKERS = 2


class BatchSearchRequest(BaseModel):
    numbers: List[str]
    include_covers: bool = True


@router.post("/batch-search", summary="批量番號搜尋")
def batch_search(body: BatchSearchRequest) -> dict:
    """
    批量番號搜尋

    - **numbers**: 番號列表（必填，最多 50 筆）
    - **include_covers**: 是否回傳封面 URL（預設 true）

    回傳：
    ```json
    {
      "results": {
        "SONE-205": {"found": true, "title": "...", "cover_url": "..."},
        "FAKE-999": {"found": false}
      },
      "summary": {"total": 2, "found": 1, "not_found": 1}
    }
    ```
    """
    numbers = list(dict.fromkeys(
        n.strip().upper() for n in body.numbers if isinstance(n, str) and n.strip()
    ))

    if not numbers:
        return JSONResponse(status_code=400, content={"success": False, "error": "numbers 不可為空"})

    if len(numbers) > 50:
        return JSONResponse(status_code=422, content={"success": False, "error": "最多支援 50 筆批量搜尋"})

    results = {}

    def _search_one(num: str):
        try:
            data = smart_search(num, limit=1)
            if data:
                entry = data[0]
                entry['found'] = True
                return num, entry
        except Exception:
            logger.error('batch_search: %s failed', num)
        return num, {'found': False}

    with ThreadPoolExecutor(max_workers=_BATCH_MAX_WORKERS) as executor:
        futures = {executor.submit(_search_one, num): num for num in numbers}
        for future in as_completed(futures):
            num, entry = future.result()
            results[num] = entry

    if not body.include_covers:
        for entry in results.values():
            entry.pop('cover_url', None)

    found_count = sum(1 for e in results.values() if e.get('found'))
    return {
        "results": results,
        "summary": {
            "total": len(numbers),
            "found": found_count,
            "not_found": len(numbers) - found_count
        }
    }


@router.get("/search/stream")
async def search_stream(
    q: str = Query(..., description="番號、局部番號、或女優名"),
    limit: int = Query(20, description="每頁結果數", ge=1, le=50),
    offset: int = Query(0, description="跳過前 N 個結果（用於分頁）", ge=0)
):
    """
    串流搜尋 API（SSE）- 即時回報搜尋狀態

    返回 Server-Sent Events:
    - status: 搜尋狀態更新
    - result: 搜尋結果
    """
    mark_manual_activity()
    q = q.strip()
    if not q or len(q) < 2:
        async def error_gen():
            yield f"data: {json.dumps({'type': 'error', 'message': '請輸入有效的搜尋關鍵字'})}\n\n"
        return StreamingResponse(error_gen(), media_type="text/event-stream")

    # 讀取設定（無碼模式）
    from core.config import load_config
    config = await asyncio.to_thread(load_config)
    uncensored_mode = is_uncensored_mode_effective(config)

    status_queue = Queue()
    sent_seed = False

    def status_callback(source: str, status: str):
        """狀態回調：放入佇列（type='status'）"""
        status_queue.put({'type': 'status', 'source': source, 'status': status})

    def result_callback(slot: int, data):
        """結果回調：seed（slot=-1）或 result-item（slot>=0）放入佇列"""
        nonlocal sent_seed
        if slot == -1:
            if sent_seed:
                return  # 雙 seed 保護：prefix→actress fallback 不送第二個 seed
            sent_seed = True
            status_queue.put({'type': 'seed', 'slots': data})
        else:
            status_queue.put({'type': 'result-item', 'slot': slot, 'data': data})

    def run_search():
        """在背景執行搜尋"""
        return smart_search(q, limit=limit, offset=offset, status_callback=status_callback, uncensored_mode=uncensored_mode, result_callback=result_callback)

    async def event_generator():
        nonlocal sent_seed
        # 偵測模式
        mode = _detect_mode(q)
        yield f"data: {json.dumps({'type': 'mode', 'mode': mode})}\n\n"

        # 啟動搜尋線程
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run_search)

            # 持續讀取狀態更新
            while not future.done():
                try:
                    # 非阻塞讀取：drain queue，依 type 分支處理
                    while not status_queue.empty():
                        item = status_queue.get_nowait()
                        event_type = item.get('type')
                        if event_type == 'status':
                            yield f"data: {json.dumps({'type': 'status', 'source': item['source'], 'status': item['status']})}\n\n"
                        elif event_type == 'seed':
                            yield f"data: {json.dumps({'type': 'seed', 'mode': mode, 'total': len(item['slots']), 'slots': item['slots']})}\n\n"
                        elif event_type == 'result-item':
                            yield f"data: {json.dumps({'type': 'result-item', 'slot': item['slot'], 'data': item['data']})}\n\n"
                    await asyncio.sleep(0.1)
                except Exception:
                    break

            # 讀取剩餘佇列（搜尋完成後可能還有 result-item）
            while not status_queue.empty():
                item = status_queue.get_nowait()
                event_type = item.get('type')
                if event_type == 'status':
                    yield f"data: {json.dumps({'type': 'status', 'source': item['source'], 'status': item['status']})}\n\n"
                elif event_type == 'seed':
                    yield f"data: {json.dumps({'type': 'seed', 'mode': mode, 'total': len(item['slots']), 'slots': item['slots']})}\n\n"
                elif event_type == 'result-item':
                    yield f"data: {json.dumps({'type': 'result-item', 'slot': item['slot'], 'data': item['data']})}\n\n"

            # 取得結果
            try:
                results = future.result()

                # 從實際結果更新 mode（smart_search 內部可能 fallback，
                # 例如 prefix→actress 或 actress→keyword）
                if results and results[0].get('_mode'):
                    mode = results[0]['_mode']

                # Consistency check（與 REST 相同邏輯）
                actress_profile = None
                if mode in ('actress', 'prefix'):
                    top_actor = _analyze_top_actor(results, threshold=0.8, min_samples=3)
                    if top_actor:
                        logger.info(f"[Actress Profile] Fetching profile for: {top_actor}")
                        # 66 Codex P1：event_generator 是 async generator、跑在 event loop 上，
                        # 此 helper 做 init_db/repo + DB-miss 時同步 scraper HTTP → 必須 to_thread
                        actress_profile = await asyncio.to_thread(
                            _fetch_actress_profile_with_db, top_actor, _extract_top_makers(results)
                        )
                        if not actress_profile:
                            logger.info(f"[Actress Profile] Not found for: {top_actor}")

                # 判斷是否還有更多結果
                has_more = mode in ('prefix', 'actress') and len(results) >= limit

                # 若漸進路徑被使用，先送 result-complete（供 T4 消費者用）
                if sent_seed:
                    complete_response = {
                        'type': 'result-complete',
                        'total': len(results),
                        'has_more': has_more,
                        'actress_profile': actress_profile
                    }
                    yield f"data: {json.dumps(complete_response)}\n\n"

                # 永遠送傳統 result event（向後相容，前端的 source of truth）
                response = {
                    'type': 'result',
                    'success': bool(results),
                    'data': results,
                    'total': len(results),
                    'mode': mode,
                    'offset': offset,
                    'has_more': has_more,
                    'actress_profile': actress_profile
                }
                yield f"data: {json.dumps(response)}\n\n"

            except Exception as e:
                logger.error("串流搜尋失敗: %s", e)
                yield f"data: {json.dumps({'type': 'error', 'message': '搜尋失敗', 'actress_profile': None})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/search/sources")
async def get_sources() -> dict:
    """取得可用的搜尋來源"""
    # 來源描述（保留向後相容）
    source_descriptions = {
        "auto": "依優先順序自動選擇",
        "dmm": "日本官方（需 Proxy）",
        "javbus": "最常用的來源（封面無浮水印）",
        "jav321": "備用來源（封面完整）",
        "javdb": "資料完整（有片商）",
        "d2pass": "1Pondo / Caribbeancom / 10musume",
        "heyzo": "HEYZO 專用",
        "fc2": "FC2 專用",
        "avsox": "無碼片源",
    }

    # ⟳ switch-source 可輪替來源（builtin non-manual，依 config 拖曳順序；D7 修正）
    switchable_ids = get_switchable_source_ids_ordered()

    # 動態生成 sources 列表
    sources = [{"id": "auto", "name": "自動", "description": source_descriptions["auto"]}]
    for source_id in switchable_ids:
        sources.append({
            "id": source_id,
            "name": SOURCE_NAMES.get(source_id, source_id),
            "description": source_descriptions.get(source_id, "")
        })

    return {
        "sources": sources,
        "order": switchable_ids  # 與 sources 同源 switchable_ids，保 order⊆sources 契約
    }


@router.get("/search/favorite-files")
def get_favorite_files() -> dict:
    """取得我的最愛資料夾的檔案列表（已過濾）

    Returns:
        {
            "success": True,
            "files": ["path1", "path2", ...],
            "folder": "/path/to/folder",
            "total": 50
        }
    """
    mark_manual_activity()
    request_abort()
    from core.config import load_config
    from core.favorite_scan import list_favorite_video_files, resolve_favorite_folder

    config = load_config()
    original_folder = config.get('search', {}).get('favorite_folder', '').strip()

    # 處理資料夾路徑
    try:
        folder = resolve_favorite_folder(config)
    except ValueError as e:
        logger.error("路徑轉換失敗: %s", e)
        return {
            "success": False,
            "error": "路徑轉換失敗，請檢查我的最愛資料夾設定",
            "folder": original_folder
        }

    if not folder:
        return {"success": False, "error": "favorite_folder_unset", "folder": ""}

    folder_path = Path(folder)
    if not folder_path.exists():
        return {
            "success": False,
            "error": f"資料夾不存在：{original_folder or folder}",
            "folder": original_folder or folder
        }

    # 掃描資料夾（不遞迴，只掃描第一層）
    try:
        files = list_favorite_video_files(folder, config)
    except PermissionError:
        return {
            "success": False,
            "error": "無權限讀取資料夾",
            "folder": folder
        }

    if len(files) == 0:
        return {
            "success": False,
            "error": "資料夾內無有效影片檔案",
            "folder": folder
        }

    return {
        "success": True,
        "files": files,
        "folder": folder,
        "total": len(files)
    }


def _looks_unmounted_drive(path: str) -> bool:
    """P2-T6 啟發式：路徑形如 WSL 掛載點 `/mnt/<letter>/…` 但該碟未掛載 → 存取不到（非「檔案不存在」）。

    owner 拍板（spec-107 功能 D）：WSL2 開發者拖入未掛載的 Windows 碟時 stat 拋 FileNotFoundError，
    與「真的不存在的本地檔」同例外，只能靠路徑外觀區分。`/mnt/<letter>` 已掛載但檔案真缺 → is_mount()
    為 True → 回 False（歸 not_found，正確）。非 `/mnt/<letter>` 形狀（Windows 原生 Z: 碟、本地 `/home/…`）
    一律 False，不誤判。SMB/UNC 由 normalize_path ValueError 另行歸類、不經此函式。
    """
    m = re.match(r'^/mnt/([a-z])(?:/|$)', path)
    if not m:
        return False
    try:
        return not Path(f'/mnt/{m.group(1)}').is_mount()
    except OSError:
        return False


def _filter_files_sync(paths: list) -> dict:
    """Threadpool helper（CD-66-3 外層）：load_config + 檔案走訪（stat/iterdir）。

    整段同步阻塞 I/O，由 filter_files 經 await asyncio.to_thread 移出 event loop。
    """
    from core.config import load_config
    from core.favorite_scan import detect_nfo
    from core.path_utils import normalize_path
    from core.scrapers.utils import extract_number
    from core.database import organize_failures

    # 載入設定
    config = load_config()
    video_exts = get_video_extensions(config)
    min_size_mb = config.get("gallery", {}).get("min_size_mb", 0)
    min_size_bytes = min_size_mb * 1024 * 1024

    # P2-T6: inaccessible 桶＝無讀權限（PermissionError）＋未掛載/UNC（啟發式），與 not_found 分流
    rejected = {"extension": 0, "size": 0, "not_found": 0, "inaccessible": 0}
    candidates = []  # [(original_path, normalized_path), ...]，保留原始迭代順序

    for original_path in paths:
        # 轉換路徑格式（Windows -> WSL）
        try:
            path = normalize_path(original_path)
        except ValueError:
            # WSL 不支援的 SMB/UNC 網路路徑＝存取不到的網路碟（非「檔案不存在」）
            rejected["inaccessible"] += 1
            continue

        p = Path(path)
        # P2-T6 stat-early：取代 p.exists()（會把權限吞成 False→not_found），且預設 min_size_mb=0
        # 時原本根本不 stat、permission/未掛載無從判別。一次 stat 供權限判別 + 後續 size 重用。
        try:
            stat_result = p.stat()
        except PermissionError:
            rejected["inaccessible"] += 1
            continue
        except (FileNotFoundError, OSError):
            rejected["inaccessible" if _looks_unmounted_drive(path) else "not_found"] += 1
            continue

        suffix = p.suffix.lower()
        if suffix not in video_exts:
            rejected["extension"] += 1
            continue

        if min_size_bytes > 0 and suffix not in ZERO_SIZE_EXTENSIONS:
            if stat_result.st_size < min_size_bytes:
                rejected["size"] += 1
                continue

        candidates.append((original_path, path))

    # NFO 同 stem 偵測（case-insensitive，批次一次算完，父目錄 listing cache 才有效）
    nfo_map = detect_nfo([path for _, path in candidates])
    path_mappings = config.get("gallery", {}).get("path_mappings", {})
    # 失敗記憶（灰字「查無結果」／橘色「重複」）是**加值**，不是這個端點的職責。
    # DB 一鎖住（背景掃描或定時整理正在寫）就讓整包清單失敗的話，前端 setFileList()
    # 只 console.error 然後帶著**空的 hasNfoMap** 繼續 ⇒ `has_nfo` 全變 false ⇒
    # 使用者按「整理全部」會把已經刮好的整批片重新整理、NFO 整份重寫。
    # ⇒ 失敗就退回 T6 之前的行為（skip_reason 留空），has_nfo 照常回。
    # 一次請求只記一行 log（1965 個檔不能記 1965 行）。
    memory_ok = True
    filtered = []
    for original_path, path in candidates:
        skip_reason = ""
        duplicate_target = ""

        # 番號一律從 basename 取：與 core/auto_organize.py::run_one_round 同源（CD-144-8 要求兩邊算出同一個鍵），等價性由 tests/unit/test_number_extraction_key_parity.py 守
        number = extract_number(Path(path).name)
        if number and memory_ok:
            try:
                dup_key = organize_failures.duplicate_key(path, path_mappings)
                if organize_failures.should_skip("duplicate", dup_key):
                    skip_reason = "duplicate"
                    duplicate_target = organize_failures.get_duplicate_target(dup_key)
                elif organize_failures.should_skip("not_found", number.upper()):
                    skip_reason = "not_found"
            except Exception:
                memory_ok = False
                skip_reason = ""
                duplicate_target = ""
                logger.warning(
                    "[filter_files] 讀取失敗記憶失敗，本次清單不顯示「查無結果」／「重複」標記；"
                    "檔案清單與 NFO 判斷不受影響",
                    exc_info=True,
                )

        filtered.append({
            "path": original_path,
            "has_nfo": nfo_map.get(path, False),
            "skip_reason": skip_reason,
            "duplicate_target": duplicate_target,
        })

    return {
        "success": True,
        "files": filtered,
        "rejected": rejected,
        "total_rejected": sum(rejected.values())
    }


@router.post("/search/filter-files")
async def filter_files(request: Request) -> dict:
    """過濾檔案列表：移除非影片檔與過小檔案

    Args:
        request: {"paths": ["/path/to/file1.mp4", "C:\\path\\to\\file2.txt", ...]}

    Returns:
        {
            "success": True,
            "files": ["filtered paths"],
            "rejected": {"extension": 0, "size": 0, "not_found": 0, "inaccessible": 0},
            "total_rejected": 0
        }
    """
    data = await request.json()
    paths = data.get("paths", [])
    return await asyncio.to_thread(_filter_files_sync, paths)


@router.get("/search/local-status")
def get_local_status(numbers: str = Query(..., description="逗號分隔的番號列表")) -> dict:
    """查詢番號在本地庫的存在狀態

    Args:
        numbers: 逗號分隔的番號列表 (e.g., "SONE-205,ABW-001")

    Returns:
        {
            "SONE-205": { "exists": true, "count": 2, "paths": ["/path/1.mp4", "/path/2.mp4"] },
            "ABW-001": { "exists": false }
        }

    Notes:
        - 大小寫不敏感比對
        - 限制單次查詢最多 100 個番號
    """
    # 解析番號列表
    number_list = [n.strip() for n in numbers.split(',') if n.strip()]

    if not number_list:
        return {}

    # 限制單次查詢最多 100 個番號
    if len(number_list) > 100:
        number_list = number_list[:100]

    # 查詢資料庫
    init_db()  # 確保 DB 存在
    repo = VideoRepository()
    videos_by_number = repo.get_by_numbers(number_list)

    # 建立回應
    result = {}
    for number in number_list:
        videos = videos_by_number.get(number, [])
        if videos:
            result[number] = {
                "exists": True,
                "count": len(videos),
                "paths": [v.path for v in videos]
            }
        else:
            result[number] = {
                "exists": False
            }

    return result


class AutoOrganizeConfigRequest(BaseModel):
    enabled: bool


@router.post("/search/auto-organize/config")
def update_auto_organize_config(body: AutoOrganizeConfigRequest) -> dict:
    """開關「自動整理」排程（輕量端點，比照 web/routers/config.py:211
    update_general_field() 的「單一欄位」形狀）。

    未設最愛資料夾時只允許寫 False（D8：未設資料夾不准開排程）。sync def：
    mutate_config 走檔案 I/O，依 async-offload 守衛（BE-ASYNC-01）不可寫成
    async def 卡 event loop。
    """
    config = load_config()
    favorite_folder = config.get("search", {}).get("favorite_folder", "").strip()
    if body.enabled and not favorite_folder:
        return {"success": False, "error": "favorite_folder_unset"}

    def _mut(cfg):
        cfg.setdefault("search", {}).setdefault("auto_organize", {})["enabled"] = body.enabled

    mutate_config(_mut)
    if not body.enabled:
        # 撥掉開關＝叫停。沒有這一行的話，使用者關掉排程之後**正在跑的那一輪照樣
        # 搬檔改名到跑完為止**（1965 個檔的第一輪是數小時等級），而面板上沒有任何
        # 停止鈕、`request_abort()` 全庫唯一的呼叫點是「我的最愛」按鈕（:740）
        # ⇒ 使用者唯一的脫身方式是關掉整個 App。
        # 安全性：`request_abort()` 沒在跑時不設旗標，且 `enter_cron()` 進場時
        # 會把旗標歸零，所以不會外溢到之後的任何一輪（core/auto_organize_state.py:52-63）。
        request_abort()
    # 撥開關的當下重新計時（[NEEDS CLARIFICATION]⑤ 裁決：同步呼叫，成功寫入之後、
    # 回應之前）——不重置的話，關掉再開回來仍沿用舊的到期時間，可能立刻觸發。
    auto_organize_scheduler.reset_due_time()
    return {"success": True}


@router.post("/search/auto-organize/use-resolved-folder")
def use_resolved_auto_organize_folder() -> dict:
    """把目前「手動用的那個路徑」（含系統下載資料夾 fallback）寫進
    search.favorite_folder（spec §F1「就用這個資料夾」）。
    """
    config = load_config()
    resolved = resolve_favorite_folder(config)
    if not resolved:
        return {"success": False, "error": "favorite_folder_unset"}

    def _mut(cfg):
        cfg.setdefault("search", {})["favorite_folder"] = resolved

    mutate_config(_mut)
    return {"success": True, "folder": resolved}


@router.post("/search/auto-organize/run-now")
async def run_auto_organize_now() -> dict:
    """立刻執行一次；毫秒級返回，輪在背景 task 跑（見
    web/auto_organize_scheduler.py 檔頭 🚫：絕不可 await 整輪跑完）。

    ⚠️ 必須是 `async def`，不可比照 update_auto_organize_config() 寫成
    sync def：`enter_and_start()` 內部呼叫 `asyncio.create_task()`，這支
    API 只有在**目前執行緒就是 event loop 執行緒**時才不拋
    `RuntimeError: no running event loop`。sync def 的 handler body 被
    Starlette 丟進 threadpool 執行（另一條 OS thread），不是 event loop
    執行緒——會讓這支端點每次呼叫都 500。本函式體內完全沒有 `await`
    不影響「毫秒級返回」：FastAPI 對 `async def` handler 直接在 event loop
    上執行，沒有 threadpool 調度的額外開銷，反而更快。
    """
    return auto_organize_scheduler.enter_and_start("run_now")


@router.get("/search/auto-organize/status")
def get_auto_organize_status() -> dict:
    """面板 openPanel() 的**唯一**讀取端點：一次給完面板要顯示的全部東西。

    回 6 個 key：`running`／`current_number`（純記憶體，來自 auto_organize_state）
    ＋ `enabled`／`folder`／`folder_is_set`／`resolved_folder`（來自 config）。

    ⚠️ **為什麼是一支肥一點的端點，而不是讓面板打三支**（2026-09-05 主 session 修正）：
    初版承重段把這支定成「純記憶體兩 key」，於是面板為了拿到「還沒設資料夾時要顯示的候選
    路徑」，只好去打 `GET /api/search/favorite-files`——那支會把整個系統下載資料夾**列完
    並逐檔 stat**，只為了讀回一個路徑字串，而且它的 handler 帶有 `mark_manual_activity()`
    ／`request_abort()` 兩個副作用。**還沒設資料夾的人正是最常打開這個面板的人**，下載夾大
    的話面板會卡著不出現。改成這支一次回完，面板開一次只發一個請求，零副作用。

    `resolved_folder` 走 `resolve_favorite_folder()`（＝「就用這個資料夾」會寫進去的那個值），
    所以灰字顯示的路徑與按下去真正生效的路徑保證同源。

    **純讀**：不呼叫 `mark_manual_activity()`／`request_abort()`／`mutate_config()`，
    不改變任何 module-level 狀態（D8）。sync def——`load_config()` 是檔案 I/O，
    依 BE-ASYNC-01 不可寫成 async def 卡 event loop。
    """
    config = load_config()
    folder = config.get("search", {}).get("favorite_folder", "").strip()
    return {
        **get_status(),
        "enabled": bool(
            config.get("search", {}).get("auto_organize", {}).get("enabled", False)
        ),
        "folder": folder,
        "folder_is_set": bool(folder),
        "resolved_folder": resolve_favorite_folder(config),
    }
