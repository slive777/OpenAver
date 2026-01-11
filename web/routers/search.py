"""
搜尋 API 路由
"""

from fastapi import APIRouter, Query
from fastapi.responses import Response, StreamingResponse
from typing import Optional
import requests
import json
import asyncio
from queue import Queue
from threading import Thread

import sys
from pathlib import Path

# 加入 core 模組路徑
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.scraper import (
    search_jav, smart_search, is_partial_number, is_number_format,
    is_prefix_only, search_partial, search_actress, search_prefix
)

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


@router.get("/search")
def search(
    q: str = Query(..., description="番號、局部番號、或女優名"),
    mode: str = Query("auto", description="搜尋模式: auto/exact/partial/actress"),
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
    - **limit**: 每頁結果數（預設 20，最大 50）
    - **offset**: 跳過前 N 個結果，用於載入更多
    """
    q = q.strip()
    if not q or len(q) < 2:
        return {"success": False, "error": "請輸入有效的搜尋關鍵字", "data": [], "total": 0}

    # 自動模式使用 smart_search
    if mode == "auto":
        results = smart_search(q, limit=limit, offset=offset)
    elif mode == "exact":
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
        return {
            "success": True,
            "data": results,
            "total": len(results),
            "mode": detected_mode,
            "offset": offset,
            "has_more": has_more
        }

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

    status_queue = Queue()

    def status_callback(source: str, status: str):
        """狀態回調：放入佇列"""
        status_queue.put({'source': source, 'status': status})

    def run_search():
        """在背景執行搜尋"""
        return smart_search(q, limit=limit, offset=offset, status_callback=status_callback)

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
                yield f"data: {json.dumps({'type': 'result', 'success': bool(results), 'data': results, 'total': len(results), 'mode': mode, 'offset': offset, 'has_more': has_more})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/search/sources")
async def get_sources() -> dict:
    """取得可用的搜尋來源"""
    return {
        "sources": [
            {"id": "auto", "name": "自動", "description": "依優先順序自動選擇"},
            {"id": "javbus", "name": "JavBus", "description": "最常用的來源（封面無浮水印）"},
            {"id": "jav321", "name": "Jav321", "description": "備用來源"},
            {"id": "javdb", "name": "JavDB", "description": "女優/前綴搜尋用"},
        ]
    }
