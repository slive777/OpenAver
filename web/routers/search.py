"""
搜尋 API 路由
"""

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response, StreamingResponse, FileResponse
from typing import Optional, List
import requests
import json
import asyncio
from queue import Queue
from threading import Thread
import tempfile

import sys
from pathlib import Path

# 加入 core 模組路徑
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.database import VideoRepository, get_db_path, init_db
from core.scraper import (
    search_jav, smart_search, is_partial_number, is_number_format,
    is_prefix_only, search_partial, search_actress, search_prefix,
    search_by_variant_id
)
from core.scrapers.utils import SOURCE_ORDER, SOURCE_NAMES

router = APIRouter(prefix="/api", tags=["search"])


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


@router.get("/search/gallery-view")
async def gallery_view(path: str):
    """
    讀取並回傳暫存的 Gallery HTML

    Args:
        path: Gallery HTML 檔案的絕對路徑

    Returns:
        HTML 檔案內容
    """
    try:
        # 安全檢查：只允許讀取系統暫存目錄下的 openaver_gallery 資料夾
        safe_dir = Path(tempfile.gettempdir()) / "openaver_gallery"
        safe_dir.mkdir(parents=True, exist_ok=True)

        target_path = Path(path).resolve()

        # 路徑安全驗證
        if not str(target_path).startswith(str(safe_dir.resolve())):
            return Response(status_code=403, content="Access Denied")

        if not target_path.exists():
            return Response(status_code=404, content="File Not Found")

        return FileResponse(target_path, media_type="text/html")

    except Exception as e:
        return Response(status_code=500, content=str(e))


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
            "mode": "exact"
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
        # 判斷是否還有更多結果（prefix/actress 模式且結果數 = limit）
        has_more = detected_mode in ('prefix', 'actress') and len(results) >= limit

        response = {
            "success": True,
            "data": results,
            "total": len(results),
            "mode": detected_mode,
            "offset": offset,
            "has_more": has_more
        }

        # 如果是女優搜尋 且結果 > 閾值，生成 Gallery HTML
        # 取得設定
        from web.routers.config import load_config
        config = load_config()
        gallery_enabled = config.get('search', {}).get('gallery_mode_enabled', False)
        gallery_min_results = 10 if gallery_enabled else 999  # 關閉時設為 999（永不觸發）

        if detected_mode == "actress" and results and len(results) > gallery_min_results:
            try:
                # 取得主題設定
                theme = config.get('general', {}).get('theme', 'dark')

                # 生成 Gallery
                from core.search_gallery_service import SearchGalleryService
                service = SearchGalleryService()
                gallery_path = service.generate_search_gallery(
                    query=q,
                    theme=theme,
                    limit=limit
                )

                if gallery_path:
                    response["gallery_url"] = f"/api/search/gallery-view?path={gallery_path}"

            except Exception as e:
                # Gallery 生成失敗不影響主搜尋，只記錄錯誤
                print(f"[Gallery Generation Error] {e}")

        return response

    return {
        "success": False,
        "error": f"找不到 {q} 的資料",
        "data": [],
        "total": 0,
        "mode": detected_mode,
        "has_more": False
    }


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
                # 判斷是否還有更多結果
                has_more = mode in ('prefix', 'actress') and len(results) >= limit

                response = {
                    'type': 'result',
                    'success': bool(results),
                    'data': results,
                    'total': len(results),
                    'mode': mode,
                    'offset': offset,
                    'has_more': has_more
                }

                # 如果是女優搜尋 且結果 > 閾值，生成 Gallery HTML
                # 取得設定
                from web.routers.config import load_config
                config = load_config()
                gallery_enabled = config.get('search', {}).get('gallery_mode_enabled', False)
                gallery_min_results = 10 if gallery_enabled else 999  # 關閉時設為 999（永不觸發）

                if mode == "actress" and results and len(results) > gallery_min_results:
                    try:
                        theme = config.get('general', {}).get('theme', 'dark')

                        from core.search_gallery_service import SearchGalleryService
                        service = SearchGalleryService()
                        gallery_path = service.generate_search_gallery(
                            query=q,
                            theme=theme,
                            limit=limit
                        )

                        if gallery_path:
                            response["gallery_url"] = f"/api/search/gallery-view?path={gallery_path}"

                    except Exception as e:
                        print(f"[Gallery Generation Error] {e}")

                yield f"data: {json.dumps(response)}\n\n"

            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

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
