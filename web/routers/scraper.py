"""
Scraper API 路由 - 單檔刮削

端點：
- POST /api/scrape-single  — 單一影片刮削（搜尋元數據、建資料夾、重命名、下載封面、產生 NFO）
- POST /api/batch-enrich   — 批次原地補完（SSE streaming）
"""

import asyncio
import json
import os
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Literal, Optional

from core.database import VideoRepository
from core.db_inflow import try_inflow_upsert
from core.enricher import enrich_single, fetch_samples_only, resolve_nfo_cover_paths
from core.organizer import organize_file
from core.path_utils import to_file_uri, uri_to_fs_path, coerce_to_file_uri, is_path_under_dir
from core.scraper import (
    search_jav, search_jav_single_source, strip_internal_nfo_keys,
    search_javlib_versions, fetch_javlib_by_detail_url, internal_nfo_carriers,
)
from core.source_config import validate_source_id
from core.cf_transport import get_cf_transport, CfChallengeRequired, CfTransportUnavailable
from core.scrapers.javlibrary import JAVLIBRARY_ORIGIN
from core.logger import get_logger
from core.config import load_config, iter_gallery_sources
from core import thumbnail_cache
from web.routers.notifications import emit_notification as _emit_notif

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["scraper"])

# SSRF 防護：confirm 階段的 detail_url 來自 client（不可信），會被丟給 CF transport
# （standalone 真瀏覽器 fetch）。限定 scheme+netloc 精確等於 javlibrary origin，
# 擋掉 169.254.169.254 / evil.com / www.javlibrary.com.evil.com 之類 prefix 繞過
# （netloc 精確比對，非 startswith 字串）。preview candidates 的 url 是後端自產（可信），
# 不在此驗證面（PR #89 Codex P3）。
_JAVLIB_ORIGIN_PARSED = urlparse(JAVLIBRARY_ORIGIN)


def _is_javlibrary_url(url: str) -> bool:
    try:
        p = urlparse(url)
    except (ValueError, TypeError):
        return False
    # netloc 大小寫不敏感（RFC 3986 host）：lower 後比對，避免大寫合法 URL 被誤拒；
    # scheme urlparse 已 lower。安全方向不變（netloc 仍精確等於 javlibrary host）。
    return (
        p.scheme == _JAVLIB_ORIGIN_PARSED.scheme
        and p.netloc.lower() == _JAVLIB_ORIGIN_PARSED.netloc.lower()
    )


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

    # U7 readonly guard：只依 file_path 判斷所屬來源是否唯讀（readonly）。
    # 是 → 不搬檔、不刮削、不解析番號，回既有錯誤形狀 plain dict。
    # 必須在 extract_number / search_jav / organize_file 之前（Codex P1）；
    # 兩端一律用 UNC-tolerant to_file_uri，不做原生路徑正規化（Codex P2：對 UNC 在
    # WSL/Linux 會拋 ValueError，而 UNC 正是 readonly 主場景）。
    _gallery_config = load_config().get('gallery', {})
    _path_mappings = _gallery_config.get('path_mappings', {})
    # coerce_to_file_uri：file_path 可能已是 DB canonical file:/// URI（鄰近寫入路徑
    # 傳的就是 URI），直接 to_file_uri 會雙重包成 file:///file:/// 導致 guard 被繞過
    # （Codex P1）。coerce 對「已是 URI」原樣回、對 FS path 才轉，兩端對稱處理。
    _file_uri = coerce_to_file_uri(file_path, _path_mappings)
    for _s in iter_gallery_sources(_gallery_config):
        if not _s.readonly or not _s.path:
            continue
        if is_path_under_dir(_file_uri, coerce_to_file_uri(_s.path, _path_mappings)):
            return {
                "success": False,
                "error": "此來源路徑為唯讀（readonly），無法搬移或重新命名檔案。"
                         "請改用掃描頁『產生』生成本地媒體庫，或確認你對此路徑有寫入權限。",
            }

    # 如果沒有提供番號，嘗試從檔名提取
    if not number:
        from core.scraper import extract_number
        number = extract_number(file_path)

    if not number:
        return {
            "success": False,
            "error": "無法識別番號，請手動輸入"
        }

    # 載入設定（需在 search_jav 之前，以便傳入 proxy_url）
    config = load_config()
    scraper_config = config.get('scraper', {})
    _proxy_url = config.get('search', {}).get('proxy_url', '')

    # 優先使用前端傳來的 metadata
    if request.metadata:
        metadata = request.metadata
        metadata['number'] = number
    else:
        # 沒有 metadata 才重新搜尋
        metadata = search_jav(number, proxy_url=_proxy_url)
        if not metadata:
            return {
                "success": False,
                "error": f"找不到 {number} 的資料"
            }
        metadata['number'] = number

    logger.debug(f"[scraper] cover URL: {metadata.get('cover', 'NO COVER')}")

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
            # 72d-P2C：cd2/part2 外部模式下 organizer F2 skip NFO，scan_file 無 NFO 可讀
            # → 傳 scraped_metadata 讓 db_inflow overlay scraped fields，cd2 row 與 cd1 一致。
            # 非 multipart（skipped_nfo_multipart 不存在或 False）一律傳 None（byte-identical）。
            _multipart_meta = metadata if result.get("skipped_nfo_multipart") else None
            db_sync_status = try_inflow_upsert(
                target_file,
                old_file_path=file_path,
                scraped_metadata=_multipart_meta,
            )
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
    detail_url: Optional[str] = None


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
        if request.source == 'javlibrary':
            versions = search_javlib_versions(request.number)  # Cf* 例外由外層 except 接
            if not versions:
                return {"success": False}
            if len(versions) == 1:
                return {"success": True, **strip_internal_nfo_keys(versions[0])}
            return {"success": True, "candidates": [strip_internal_nfo_keys(v) for v in versions]}
        elif request.source == "auto":
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
    except CfChallengeRequired:
        t = get_cf_transport()
        if t:
            try:
                t.begin_solve(JAVLIBRARY_ORIGIN, 'javlibrary')  # 非阻塞
            except Exception:
                logger.exception("rescrape_preview: begin_solve 失敗，回 cf_unavailable")
                return {"success": False, "cf_unavailable": True}
        return {"success": False, "cf_needed": True}
    except CfTransportUnavailable:
        return {"success": False, "cf_unavailable": True}
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
        # 72d-P2A：外部圖寫出機會也是合法的寫出路徑（72b-T6 加入 external_manager 後守衛未同步）
        external_manager = config.get("scraper", {}).get("external_manager", "off")
        if external_manager != "off":
            stem = os.path.splitext(uri_to_fs_path(request.file_path))[0]
            poster_path = stem + "-poster.jpg"
            fanart_path = stem + "-fanart.jpg"
            # 底圖存在 + 至少一張外部圖缺 → _write_external_images 有寫出機會
            cover_exists_on_disk = os.path.exists(cover_path)
            will_write_external = cover_exists_on_disk and (
                not os.path.exists(poster_path) or not os.path.exists(fanart_path)
            )
        else:
            will_write_external = False
        if not will_write_nfo and not will_write_cover and not will_write_external:
            raise HTTPException(
                status_code=400,
                detail="refresh_full + overwrite_existing=false 在此設定下不會寫出任何 NFO/封面，只會更新 DB 造成與磁碟分裂；請開 overwrite_existing、確保 NFO/封面有實際寫入，或補劇照請改用 /api/scraper/fetch-samples",
            )

    try:
        scraper_data = None
        if request.source == 'javlibrary' and request.detail_url:
            # SSRF guard：拒絕非 javlibrary origin 的 detail_url（不 fetch、不洩 URL）
            if not _is_javlibrary_url(request.detail_url):
                logger.warning("enrich_single: 拒絕非法 detail_url origin")
                return {"success": False, "error": "detail_url 來源不合法"}
            try:
                video = fetch_javlib_by_detail_url(request.detail_url, request.number)
            except CfChallengeRequired:
                t = get_cf_transport()
                if t:
                    try:
                        t.begin_solve(JAVLIBRARY_ORIGIN, 'javlibrary')
                    except Exception:
                        logger.exception("enrich_single: begin_solve 失敗，回 cf_unavailable")
                        return {"success": False, "cf_unavailable": True}
                return {"success": False, "cf_needed": True}
            except CfTransportUnavailable:
                return {"success": False, "cf_unavailable": True}
            if video is None:
                return {"success": False, "error": "javlibrary 無法取得指定版本資料"}
            # to_legacy_dict 省略 _summary/_rating 內部 carrier；補回以對齊既有 javlibrary
            # 重刮的 NFO 輸出（search_jav 走 internal_nfo_carriers 注入同組，PR #89 Codex P2）
            scraper_data = video.to_legacy_dict()
            scraper_data.update(internal_nfo_carriers(video))
        result = enrich_single(
            file_path=request.file_path,
            number=request.number,
            mode=request.mode,
            write_nfo=request.write_nfo,
            write_cover=request.write_cover,
            write_extrafanart=request.write_extrafanart,
            overwrite_existing=request.overwrite_existing,
            external_manager=config.get("scraper", {}).get("external_manager", "off"),
            proxy_url=proxy_url,
            source=request.source,
            javbus_lang=request.javbus_lang,
            scraper_data=scraper_data,
        )
        # feature/71 T8: 換封面成功 → 失效舊縮圖（下次 lazy/prewarm 重生，CD-9 / spec 2.A.7）。
        # request.file_path 已是 DB 的 file:/// URI（前端送 currentLightboxVideo.path /
        # missing-check items / rescrape，皆 DB v.path）。縮圖 canonical key = v.path 原字串
        # hash（generate/serve/prewarm 同源），故 invalidate 必須用同一 URI 原值——用冪等
        # coerce_to_file_uri（已是 URI 就原樣回），不可再套 to_file_uri 造成 file:///file:///
        # double-encode 砍錯 hash（PR #60 Codex P2）。
        if result.success:
            thumbnail_cache.invalidate(coerce_to_file_uri(request.file_path))
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
                        lambda i=item, sd=cached_data, es=effective_source, el=effective_lang: enrich_single(
                            file_path=i.file_path,
                            number=i.number,
                            mode=request.mode,
                            write_nfo=request.write_nfo,
                            write_cover=request.write_cover,
                            write_extrafanart=request.write_extrafanart,
                            overwrite_existing=request.overwrite_existing,
                            external_manager=config.get("scraper", {}).get("external_manager", "off"),
                            proxy_url=proxy_url,
                            source=es if es != "auto" else None,
                            javbus_lang=el,
                            scraper_data=sd,
                        ),
                    )
                    from dataclasses import asdict
                    result_dict = asdict(result)
                    if result.success:
                        success_count += 1
                        # feature/71 T8: 換封面成功 → 失效舊縮圖（廉價同步 unlink，不需 offload）。
                        # item.file_path 已是 DB file:/// URI → 冪等 coerce，不可 double-encode
                        # （同 enrich-single，PR #60 Codex P2）。
                        thumbnail_cache.invalidate(coerce_to_file_uri(item.file_path))
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
