"""
Scraper API 路由 - 單檔刮削

端點：
- POST /api/scrape-single  — 單一影片刮削（搜尋元數據、建資料夾、重命名、下載封面、產生 NFO）
- POST /api/batch-enrich   — 批次原地補完（SSE streaming）
"""

import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Literal, Optional

from core.database import VideoRepository
from core.enricher import enrich_single
from core.organizer import organize_file
from core.path_utils import to_file_uri
from core.scraper import search_jav
from core.logger import get_logger
from core.config import load_config

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["scraper"])


class ScrapeRequest(BaseModel):
    file_path: str
    number: Optional[str] = None
    # 前端可直接傳入 metadata，避免重新搜尋
    metadata: Optional[dict] = None


class ScrapeResponse(BaseModel):
    success: bool
    error: Optional[str] = None
    original_path: Optional[str] = None
    new_folder: Optional[str] = None
    new_filename: Optional[str] = None
    cover_path: Optional[str] = None
    nfo_path: Optional[str] = None


@router.post("/scrape-single")
def scrape_single(request: ScrapeRequest) -> dict:
    """
    單檔刮削 API

    流程:
    1. 搜尋元數據
    2. 建立資料夾
    3. 重命名影片
    4. 下載封面
    5. 生成 NFO
    """
    file_path = request.file_path
    number = request.number

    # 如果沒有提供番號，嘗試從檔名提取
    if not number:
        from core.scraper import extract_number
        number = extract_number(file_path)

    if not number:
        return {
            "success": False,
            "error": "無法識別番號，請手動輸入"
        }

    # 優先使用前端傳來的 metadata
    if request.metadata:
        metadata = request.metadata
        metadata['number'] = number
    else:
        # 沒有 metadata 才重新搜尋
        metadata = search_jav(number)
        if not metadata:
            return {
                "success": False,
                "error": f"找不到 {number} 的資料"
            }
        metadata['number'] = number

    logger.debug(f"[scraper] cover URL: {metadata.get('cover', 'NO COVER')}")

    # 載入設定
    config = load_config()
    scraper_config = config.get('scraper', {})

    # 執行整理（scraper_config 已包含 suffix_keywords，organize_file 自行偵測）
    result = organize_file(file_path, metadata, scraper_config)

    # 覆蓋保護：目標路徑已存在時回傳 duplicate 狀態（不覆蓋）
    if result.get('duplicate'):
        return {
            "success": False,
            "duplicate": True,
            "duplicate_target": result.get('duplicate_target', ''),
        }

    # scrape 成功後：若 metadata 含 user_tags，寫入 DB（與現有值取聯集）
    if result.get('success') and metadata.get('user_tags'):
        try:
            user_tags = metadata['user_tags']
            new_filename = result.get('new_filename', '')
            if new_filename:
                path_uri = to_file_uri(new_filename)
                repo = VideoRepository()
                existing = repo.get_by_path(path_uri)
                existing_user_tags = existing.user_tags if existing else []
                merged = existing_user_tags + [t for t in user_tags if t not in existing_user_tags]
                repo.update_user_tags(path_uri, merged)
        except Exception:
            logger.warning("scrape_single: DB upsert user_tags 失敗，result 仍回傳", exc_info=True)

    return result


class EnrichRequest(BaseModel):
    file_path: str
    number: str
    mode: Literal["refresh_full", "fill_missing", "db_to_sidecar"] = "fill_missing"
    write_nfo: bool = True
    write_cover: bool = True
    write_extrafanart: bool = False
    overwrite_existing: bool = False
    source: Optional[str] = None
    javbus_lang: Optional[str] = None


class BatchEnrichItem(BaseModel):
    file_path: str
    number: str
    source: Optional[str] = None       # per-item override（優先於 batch default）
    javbus_lang: Optional[str] = None  # per-item override


class BatchEnrichRequest(BaseModel):
    items: List[BatchEnrichItem]       # max 20，超過返回 422
    mode: Literal["refresh_full", "fill_missing", "db_to_sidecar"] = "refresh_full"
    source: Optional[str] = None       # batch default（item 未指定時用此值）
    javbus_lang: Optional[str] = None  # batch default
    write_nfo: bool = True
    write_cover: bool = True
    write_extrafanart: bool = False
    overwrite_existing: bool = False


@router.post("/enrich-single")
def enrich_single_endpoint(request: EnrichRequest) -> dict:
    config = load_config()
    search_cfg = config.get("search", {})
    proxy_url = search_cfg.get("proxy_url", "")
    primary_source = search_cfg.get("primary_source", "javbus")

    try:
        result = enrich_single(
            file_path=request.file_path,
            number=request.number,
            mode=request.mode,
            write_nfo=request.write_nfo,
            write_cover=request.write_cover,
            write_extrafanart=request.write_extrafanart,
            overwrite_existing=request.overwrite_existing,
            proxy_url=proxy_url,
            primary_source=primary_source,
            source=request.source,
            javbus_lang=request.javbus_lang,
        )
        from dataclasses import asdict
        return asdict(result)
    except Exception:
        logger.exception("enrich_single_endpoint 失敗")
        return {"success": False, "error": "enrich 處理失敗，請查閱日誌"}


@router.post("/batch-enrich")
async def batch_enrich_endpoint(request: BatchEnrichRequest):
    """批次 enrich — SSE streaming，最多 20 筆，按 file_path 去重"""
    if len(request.items) > 20:
        raise HTTPException(status_code=422, detail="items 上限為 20 筆")

    config = load_config()
    search_cfg = config.get("search", {})
    proxy_url = search_cfg.get("proxy_url", "")
    primary_source = search_cfg.get("primary_source", "javbus")

    # 去重（按 file_path）
    seen_paths: set = set()
    deduped_items = []
    for item in request.items:
        if item.file_path not in seen_paths:
            seen_paths.add(item.file_path)
            deduped_items.append(item)

    total = len(deduped_items)

    async def event_generator():
        success_count = 0
        failed_count = 0
        # scraper cache：只對 refresh_full 生效（100% 需要 scraper data）
        # fill_missing 由 enrich_single 內部判斷是否需要打外站，不 pre-fetch
        # value 為 dict（成功）或 {}（search_jav 回 None，負向 cache）
        scraper_cache: dict = {}

        for idx, item in enumerate(deduped_items, start=1):
            effective_source = item.source or request.source or "auto"
            effective_lang = item.javbus_lang or request.javbus_lang

            # progress 事件
            yield f"data: {json.dumps({'type': 'progress', 'current': idx, 'total': total, 'number': item.number})}\n\n"

            try:
                loop = asyncio.get_running_loop()

                # scraper cache（只對 refresh_full pre-fetch）
                cached_data = None
                if request.mode == "refresh_full":
                    cache_key = (item.number.upper(), effective_source, effective_lang)
                    if cache_key not in scraper_cache:
                        fetched = await loop.run_in_executor(
                            None,
                            lambda n=item.number, es=effective_source, el=effective_lang: search_jav(
                                n,
                                source=es,
                                proxy_url=proxy_url,
                                primary_source=primary_source,
                                javbus_lang=el,
                            ),
                        )
                        # 負向 cache：search_jav 回 None → 存 {}（空 dict falsy）
                        # enrich_single 收到 {} 時 `is None` 為 False（不再搜），
                        # `not scraper_data` 為 True（回錯誤）
                        scraper_cache[cache_key] = fetched if fetched else {}
                    cached_data = scraper_cache[cache_key]

                result = await loop.run_in_executor(
                    None,
                    lambda i=item, sd=cached_data: enrich_single(
                        file_path=i.file_path,
                        number=i.number,
                        mode=request.mode,
                        write_nfo=request.write_nfo,
                        write_cover=request.write_cover,
                        write_extrafanart=request.write_extrafanart,
                        overwrite_existing=request.overwrite_existing,
                        proxy_url=proxy_url,
                        primary_source=primary_source,
                        source=effective_source if effective_source != "auto" else None,
                        javbus_lang=effective_lang,
                        scraper_data=sd,
                    ),
                )
                from dataclasses import asdict
                result_dict = asdict(result)
                if result.success:
                    success_count += 1
                else:
                    failed_count += 1
                yield f"data: {json.dumps({'type': 'result-item', 'number': item.number, 'file_path': item.file_path, **result_dict})}\n\n"
            except Exception:
                logger.exception("batch_enrich item %s 失敗", item.number)
                failed_count += 1
                yield f"data: {json.dumps({'type': 'result-item', 'number': item.number, 'file_path': item.file_path, 'success': False, 'error': 'enrich 處理失敗，請查閱日誌'})}\n\n"

        yield f"data: {json.dumps({'type': 'done', 'summary': {'total': total, 'success': success_count, 'failed': failed_count}})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
