"""
Scraper API 路由 - 單檔刮削

端點：
- POST /api/scrape-single  — 單一影片刮削（搜尋元數據、建資料夾、重命名、下載封面、產生 NFO）
- POST /api/batch-enrich   — 批次原地補完（SSE streaming）
"""

import asyncio
import json
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Literal, Optional

from core.database import VideoRepository
from core.db_inflow import try_inflow_upsert
from core.enricher import enrich_single, fetch_samples_only, resolve_nfo_cover_paths
from core.organizer import organize_file
from core.path_utils import to_file_uri, uri_to_fs_path
from core.scraper import search_jav, search_jav_single_source, strip_internal_nfo_keys
from core.source_config import validate_source_id
from core.logger import get_logger
from core.config import load_config
from web.routers.notifications import emit_notification as _emit_notif

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

    # in-flow upsert：整理成功後條件式寫入 DB（只在 Scanner 追蹤目錄內才執行）
    db_sync_status = "not_linked"
    if result.get("success"):
        target_file = result.get("new_filename")
        if target_file:
            db_sync_status = try_inflow_upsert(target_file)
        else:
            logger.warning("scrape_single: organize_file 回傳缺 new_filename，skip in-flow upsert")

    return {**result, "db_sync_status": db_sync_status}


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


class RescrapePreviewRequest(BaseModel):
    number: str
    source: str = "auto"


@router.post("/rescrape/preview")
def rescrape_preview_endpoint(request: RescrapePreviewRequest) -> dict:
    """重刮預覽（CD-62-3）：只搜不寫，復用 B1 搜尋路徑。

    - source=auto → search_jav（走 merger）。
    - 具體來源 → search_jav_single_source（明確選源繞 merger，CD-62-6）。
    回傳成功 dict + success:True；not-found（None）→ 200 {success:False}。
    不下載 cover（cover 是遠端 URL，原樣回前端，無 SSRF 面）。
    """
    config = load_config()
    search_cfg = config.get("search", {})
    proxy_url = search_cfg.get("proxy_url", "")

    try:
        if request.source == "auto":
            result = search_jav(
                request.number,
                source="auto",
                proxy_url=proxy_url,
            )
        else:
            result = search_jav_single_source(
                request.number, request.source, proxy_url
            )

        if result is None:
            return {"success": False}
        return {"success": True, **strip_internal_nfo_keys(result)}
    except Exception:
        logger.exception("rescrape_preview_endpoint 失敗")
        return {"success": False, "error": "預覽搜尋失敗，請查閱日誌"}


@router.post("/enrich-single")
def enrich_single_endpoint(request: EnrichRequest) -> dict:
    config = load_config()
    search_cfg = config.get("search", {})
    proxy_url = search_cfg.get("proxy_url", "")

    # CD-62-4 分裂陷阱智慧防呆：refresh_full + overwrite=false 時，若這組設定不會寫出任何
    # sidecar（NFO/cover）卻仍 _db_upsert，就是純分裂。一個 sidecar「會寫」需 write 旗標開 + 檔案缺
    # （此分支 overwrite 已為 false，既有檔不覆寫）。兩者皆不會寫 → 擋；任一會寫則放行（quick-enrich
    # 缺封面零回歸）。涵蓋 write_nfo/write_cover 皆 false 的純 DB-only 路徑（Codex P1）。
    # write_extrafanart 刻意排除：_write_extrafanart 無 overwrite gate 且只在 scraper 回
    # sample_images 才寫；若 scraper 無 samples → 零磁碟寫出但 _db_upsert 照跑 = 分裂，
    # 故不得計入「保證會寫 sidecar」；補劇照請用 /api/scraper/fetch-samples（Codex PR#47 round-2 P2）。
    # 在 try 之前 raise，避免被下方 except Exception 吞成籠統 200。
    if request.mode == "refresh_full" and not request.overwrite_existing:
        nfo_path, cover_path = resolve_nfo_cover_paths(request.file_path)
        will_write_nfo = request.write_nfo and not os.path.exists(nfo_path)
        will_write_cover = request.write_cover and not os.path.exists(cover_path)
        if not will_write_nfo and not will_write_cover:
            raise HTTPException(
                status_code=400,
                detail="refresh_full + overwrite_existing=false 在此設定下不會寫出任何 NFO/封面，只會更新 DB 造成與磁碟分裂；請開 overwrite_existing、確保 NFO/封面有實際寫入，或補劇照請改用 /api/scraper/fetch-samples",
            )

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
            source=request.source,
            javbus_lang=request.javbus_lang,
        )
        from dataclasses import asdict
        return asdict(result)
    except Exception:
        logger.exception("enrich_single_endpoint 失敗")
        return {"success": False, "error": "enrich 處理失敗，請查閱日誌"}


class FetchSamplesRequest(BaseModel):
    file_path: str
    number: str


@router.post("/scraper/fetch-samples")
def fetch_samples_endpoint(req: FetchSamplesRequest) -> dict:
    config = load_config()
    search_cfg = config.get("search", {})
    proxy_url = search_cfg.get("proxy_url", "")

    folder_uri_prefix = to_file_uri(os.path.dirname(uri_to_fs_path(req.file_path))) + "/"
    repo = VideoRepository()
    count = repo.count_videos_in_folder(folder_uri_prefix)
    if count > 1:
        return {"success": False, "error": "multi_video_folder", "count": count, "extrafanart_written": 0}

    try:
        result = fetch_samples_only(
            file_path=req.file_path,
            number=req.number,
            proxy_url=proxy_url,
        )
        from dataclasses import asdict
        return asdict(result)
    except Exception:
        logger.exception("fetch_samples_endpoint 失敗")
        return {"success": False, "error": "fetch_samples 處理失敗，請查閱日誌"}


@router.post("/batch-enrich")
async def batch_enrich_endpoint(request: BatchEnrichRequest):
    """批次 enrich — SSE streaming，最多 20 筆，按 file_path 去重"""
    if len(request.items) > 20:
        raise HTTPException(status_code=422, detail="items 上限為 20 筆")

    config = await asyncio.to_thread(load_config)
    search_cfg = config.get("search", {})
    proxy_url = search_cfg.get("proxy_url", "")

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
        # 53b-T3: 補完開始通知
        _emit_notif(
            "info", "notif.batch_enrich_started",
            message=f"共 {total} 部",
            task_type="batch_enrich",
        )
        # scraper cache：只對 refresh_full 生效（100% 需要 scraper data）
        # fill_missing 由 enrich_single 內部判斷是否需要打外站，不 pre-fetch
        # value 為 dict（成功）或 {}（search_jav 回 None，負向 cache）
        scraper_cache: dict = {}

        try:
            for idx, item in enumerate(deduped_items, start=1):
                effective_source = item.source or request.source or "auto"
                # 未知 / 非法 source guard：不靜默轉成無效 cache_key，退回 'auto'（最小驚訝）。
                if effective_source != "auto" and not validate_source_id(effective_source):
                    logger.warning(
                        "batch_enrich: 未知 source %r（number=%s），退回 'auto'",
                        effective_source, item.number,
                    )
                    effective_source = "auto"
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
            # 53b-T3: 補完完成通知
            if failed_count > 0:
                _emit_notif(
                    "warn", "notif.batch_enrich_done_with_errors",
                    message=f"補完 {success_count} 部，{failed_count} 部失敗",
                    task_type="batch_enrich",
                )
            else:
                _emit_notif(
                    "success", "notif.batch_enrich_done",
                    message=f"補完 {success_count} 部",
                    task_type="batch_enrich",
                )
        except Exception:
            logger.exception("[notif] batch_enrich 失敗")
            _emit_notif(
                "error", "notif.batch_enrich_failed",
                message="批次補完中斷，請查閱日誌",
                task_type="batch_enrich",
            )
            raise

    return StreamingResponse(event_generator(), media_type="text/event-stream")
