"""
搜尋 API 路由
"""

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response, StreamingResponse
from typing import Optional, List, Dict
import re
import requests
import json
import asyncio
from collections import Counter
from queue import Queue
from threading import Thread

import sys
from pathlib import Path

# 加入 core 模組路徑
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.logger import get_logger
logger = get_logger(__name__)

from core.database import VideoRepository, get_db_path, init_db
from core.scraper import (
    search_jav, smart_search, is_partial_number, is_number_format,
    is_prefix_only, search_partial, search_actress, search_prefix,
    search_by_variant_id
)
from core.scrapers.utils import SOURCE_ORDER, SOURCE_NAMES

router = APIRouter(prefix="/api", tags=["search"])

# 載入 maker_mapping.json（啟動時一次性載入）
_MAKER_MAPPING = {}
_maker_mapping_path = Path(__file__).parent.parent.parent / "maker_mapping.json"
if _maker_mapping_path.exists():
    _MAKER_MAPPING = json.loads(_maker_mapping_path.read_text(encoding='utf-8'))


@router.get("/proxy-image")
def proxy_image(url: str = Query(..., description="圖片 URL")):
    """
    圖片代理 - 解決防盜鏈問題
    """
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

        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            content_type = resp.headers.get('Content-Type', 'image/jpeg')
            return Response(content=resp.content, media_type=content_type)
    except Exception:
        pass

    # 返回空圖片
    return Response(content=b'', media_type='image/jpeg', status_code=404)


@router.get("/search")
def search(
    q: str = Query(..., description="番號、局部番號、或女優名"),
    mode: str = Query("auto", description="搜尋模式: auto/exact/partial/actress"),
    source: Optional[str] = Query(None, description="指定來源: javbus/jav321/javdb/fc2/avsox"),
    variant_id: Optional[str] = Query(None, description="變體 ID: 用於切換版本"),
    limit: int = Query(20, description="每頁結果數", ge=1, le=50),
    offset: int = Query(0, description="跳過前 N 個結果（用於分頁）", ge=0)
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

    # 如果指定了 variant_id，直接搜索該版本
    if variant_id:
        data = search_by_variant_id(variant_id, q)
        results = [data] if data else []
        return {
            "success": bool(results),
            "data": results,
            "total": len(results),
            "mode": "exact",
            "actress_profile": None
        }

    # 讀取無碼模式設定
    from web.routers.config import load_config
    config = load_config()
    uncensored_mode = config.get('search', {}).get('uncensored_mode_enabled', False)

    # 自動模式使用 smart_search
    if mode == "auto":
        results = smart_search(q, limit=limit, offset=offset, uncensored_mode=uncensored_mode)
    elif mode == "exact":
        if source:
            # 指定來源搜索
            from core.scraper import search_jav_single_source
            data = search_jav_single_source(q, source)
            results = [data] if data else []
        else:
            # 精確搜索（使用 smart_search 的 exact 模式）
            data = search_jav(q)
            results = [data] if data else []
    elif mode == "partial":
        from core.scraper import search_partial
        results = search_partial(q)
    elif mode == "actress":
        from core.scraper import search_actress
        results = search_actress(q, limit=limit, offset=offset)
    else:
        results = smart_search(q, limit=limit, offset=offset)

    detected_mode = mode if mode != "auto" else _detect_mode(q)

    if results:
        # Consistency check（僅 actress/prefix 模式觸發）
        actress_profile = None
        if detected_mode in ('actress', 'prefix'):
            top_actor = _analyze_top_actor(results, threshold=0.8, min_samples=3)
            if top_actor:
                logger.info(f"[Actress Profile] Fetching profile for: {top_actor}")
                from core.actress_scraper import get_actress_profile
                actress_profile = get_actress_profile(top_actor, makers=_extract_top_makers(results))
                if not actress_profile:
                    logger.info(f"[Actress Profile] Not found for: {top_actor}")

        # 判斷是否還有更多結果（prefix/actress 模式且結果數 = limit）
        has_more = detected_mode in ('prefix', 'actress') and len(results) >= limit

        return {
            "success": True,
            "data": results,
            "total": len(results),
            "mode": detected_mode,
            "offset": offset,
            "has_more": has_more,
            "actress_profile": actress_profile
        }

    return {
        "success": False,
        "error": f"找不到 {q} 的資料",
        "data": [],
        "total": 0,
        "mode": detected_mode,
        "has_more": False,
        "actress_profile": None
    }


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
    if is_number_format(q):
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
    q = q.strip()
    if not q or len(q) < 2:
        async def error_gen():
            yield f"data: {json.dumps({'type': 'error', 'message': '請輸入有效的搜尋關鍵字'})}\n\n"
        return StreamingResponse(error_gen(), media_type="text/event-stream")

    # 讀取無碼模式設定
    from web.routers.config import load_config
    config = load_config()
    uncensored_mode = config.get('search', {}).get('uncensored_mode_enabled', False)

    status_queue = Queue()

    def status_callback(source: str, status: str):
        """狀態回調：放入佇列"""
        status_queue.put({'source': source, 'status': status})

    def run_search():
        """在背景執行搜尋"""
        return smart_search(q, limit=limit, offset=offset, status_callback=status_callback, uncensored_mode=uncensored_mode)

    async def event_generator():
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
                    # 非阻塞讀取
                    while not status_queue.empty():
                        status = status_queue.get_nowait()
                        yield f"data: {json.dumps({'type': 'status', **status})}\n\n"
                    await asyncio.sleep(0.1)
                except Exception:
                    break

            # 讀取剩餘狀態
            while not status_queue.empty():
                status = status_queue.get_nowait()
                yield f"data: {json.dumps({'type': 'status', **status})}\n\n"

            # 取得結果
            try:
                results = future.result()

                # Consistency check（與 REST 相同邏輯）
                actress_profile = None
                if mode in ('actress', 'prefix'):
                    top_actor = _analyze_top_actor(results, threshold=0.8, min_samples=3)
                    if top_actor:
                        logger.info(f"[Actress Profile] Fetching profile for: {top_actor}")
                        from core.actress_scraper import get_actress_profile
                        actress_profile = get_actress_profile(top_actor, makers=_extract_top_makers(results))
                        if not actress_profile:
                            logger.info(f"[Actress Profile] Not found for: {top_actor}")

                # 判斷是否還有更多結果
                has_more = mode in ('prefix', 'actress') and len(results) >= limit

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
                yield f"data: {json.dumps({'type': 'error', 'message': str(e), 'actress_profile': None})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/search/sources")
async def get_sources() -> dict:
    """取得可用的搜尋來源"""
    # 來源描述（保留向後相容）
    source_descriptions = {
        "auto": "依優先順序自動選擇",
        "javbus": "最常用的來源（封面無浮水印）",
        "jav321": "備用來源（封面完整）",
        "javdb": "資料完整（有片商）",
        "fc2": "FC2 專用",
        "avsox": "無碼片源"
    }

    # 動態生成 sources 列表
    sources = [{"id": "auto", "name": "自動", "description": source_descriptions["auto"]}]
    for source_id in SOURCE_ORDER:
        sources.append({
            "id": source_id,
            "name": SOURCE_NAMES.get(source_id, source_id),
            "description": source_descriptions.get(source_id, "")
        })

    return {
        "sources": sources,
        "order": SOURCE_ORDER  # 新增：來源優先順序
    }


@router.get("/search/favorite-files")
async def get_favorite_files() -> dict:
    """取得我的最愛資料夾的檔案列表（已過濾）

    Returns:
        {
            "success": True,
            "files": ["path1", "path2", ...],
            "folder": "/path/to/folder",
            "total": 50
        }
    """
    from web.routers.config import load_config
    from core.path_utils import expand_env_vars, get_environment

    config = load_config()
    original_folder = config.get('search', {}).get('favorite_folder', '').strip()

    # 處理資料夾路徑
    try:
        if not original_folder:
            # 空字串 = 使用系統下載資料夾
            if get_environment() == 'wsl':
                # WSL 環境：使用 Windows 下載資料夾
                folder = expand_env_vars('%USERPROFILE%\\Downloads')
            else:
                # 其他環境：使用本地 home 下載資料夾
                folder = str(Path.home() / "Downloads")
        else:
            # 使用 expand_env_vars 處理環境變數並轉換路徑
            folder = expand_env_vars(original_folder)
    except ValueError as e:
        return {
            "success": False,
            "error": str(e),
            "folder": original_folder
        }

    folder_path = Path(folder)
    if not folder_path.exists():
        return {
            "success": False,
            "error": f"資料夾不存在：{original_folder or folder}",
            "folder": original_folder or folder
        }

    # 過濾設定
    video_exts = [ext.lower() for ext in config.get("scraper", {}).get("video_extensions", [])]
    min_size_mb = config.get("gallery", {}).get("min_size_mb", 0)
    min_size_bytes = min_size_mb * 1024 * 1024

    # 掃描資料夾（不遞迴，只掃描第一層）
    files = []
    try:
        for f in folder_path.iterdir():
            if not f.is_file():
                continue
            if f.suffix.lower() not in video_exts:
                continue
            if min_size_bytes > 0 and f.stat().st_size < min_size_bytes:
                continue
            files.append(str(f))
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


@router.post("/search/filter-files")
async def filter_files(request: Request) -> dict:
    """過濾檔案列表：移除非影片檔與過小檔案

    Args:
        request: {"paths": ["/path/to/file1.mp4", "C:\\path\\to\\file2.txt", ...]}

    Returns:
        {
            "success": True,
            "files": ["filtered paths"],
            "rejected": {"extension": 0, "size": 0, "not_found": 0},
            "total_rejected": 0
        }
    """
    from web.routers.config import load_config
    from core.path_utils import normalize_path

    data = await request.json()
    paths = data.get("paths", [])

    # 載入設定
    config = load_config()
    video_exts = [ext.lower() for ext in config.get("scraper", {}).get("video_extensions", [])]
    min_size_mb = config.get("gallery", {}).get("min_size_mb", 0)
    min_size_bytes = min_size_mb * 1024 * 1024

    filtered = []
    rejected = {"extension": 0, "size": 0, "not_found": 0}

    for original_path in paths:
        # 轉換路徑格式（Windows -> WSL）
        try:
            path = normalize_path(original_path)
        except ValueError:
            rejected["not_found"] += 1
            continue

        p = Path(path)
        if not p.exists():
            rejected["not_found"] += 1
            continue

        suffix = p.suffix.lower()
        if suffix not in video_exts:
            rejected["extension"] += 1
            continue

        if min_size_bytes > 0:
            try:
                if p.stat().st_size < min_size_bytes:
                    rejected["size"] += 1
                    continue
            except OSError:
                rejected["not_found"] += 1
                continue

        # 保留原始路徑（前端需要）
        filtered.append(original_path)

    return {
        "success": True,
        "files": filtered,
        "rejected": rejected,
        "total_rejected": sum(rejected.values())
    }


@router.get("/search/local-status")
async def get_local_status(numbers: str = Query(..., description="逗號分隔的番號列表")) -> dict:
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
