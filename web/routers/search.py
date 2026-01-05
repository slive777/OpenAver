"""
搜尋 API 路由
"""

from fastapi import APIRouter, Query
from fastapi.responses import Response
from typing import Optional
import requests

import sys
from pathlib import Path

# 加入 core 模組路徑
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.scraper import search_jav, smart_search, is_partial_number, is_number_format

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/proxy-image")
async def proxy_image(url: str = Query(..., description="圖片 URL")):
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
async def search(
    q: str = Query(..., description="番號、局部番號、或女優名"),
    mode: str = Query("auto", description="搜尋模式: auto/exact/partial/actress")
) -> dict:
    """
    搜尋 JAV 資訊

    - **q**: 搜尋關鍵字（必填）
    - **mode**: 搜尋模式
        - auto: 自動判斷（預設）
        - exact: 精確番號搜尋
        - partial: 局部番號搜尋
        - actress: 女優搜尋
    """
    q = q.strip()
    if not q or len(q) < 2:
        return {"success": False, "error": "請輸入有效的搜尋關鍵字", "data": [], "total": 0}

    # 自動模式使用 smart_search
    if mode == "auto":
        results = smart_search(q)
    elif mode == "exact":
        data = search_jav(q)
        results = [data] if data else []
    elif mode == "partial":
        from core.scraper import search_partial
        results = search_partial(q)
    elif mode == "actress":
        from core.scraper import search_actress
        results = search_actress(q)
    else:
        results = smart_search(q)

    if results:
        return {
            "success": True,
            "data": results,
            "total": len(results),
            "mode": mode if mode != "auto" else _detect_mode(q)
        }

    return {
        "success": False,
        "error": f"找不到 {q} 的資料",
        "data": [],
        "total": 0
    }


def _detect_mode(q: str) -> str:
    """偵測搜尋模式"""
    if is_partial_number(q):
        return "partial"
    elif is_number_format(q):
        return "exact"
    else:
        return "actress"


@router.get("/search/sources")
async def get_sources() -> dict:
    """取得可用的搜尋來源"""
    return {
        "sources": [
            {"id": "auto", "name": "自動", "description": "依優先順序自動選擇"},
            {"id": "javbus", "name": "JavBus", "description": "最常用的來源"},
            {"id": "jav321", "name": "Jav321", "description": "備用來源"},
            {"id": "dmm", "name": "DMM", "description": "日本官方"},
            {"id": "avsox", "name": "AVSOX", "description": "無碼內容"},
            {"id": "mgstage", "name": "MGStage", "description": "MGS 專用"},
        ]
    }
