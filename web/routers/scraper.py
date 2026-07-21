"""
Scraper API 路由 - 單檔刮削

端點：
- POST /api/scrape-single  — 單一影片刮削（搜尋元數據、建資料夾、重命名、下載封面、產生 NFO）
- POST /api/batch-enrich   — 批次原地補完（SSE streaming）
"""

import asyncio
import json
import os
from dataclasses import asdict
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Literal, Optional

from core.database import VideoRepository
from core.db_inflow import try_inflow_upsert
from core.focal_trigger import maybe_submit_video_focal, schedule_focal_after_cover_write
from core.enricher import enrich_single, fetch_samples_only, resolve_nfo_cover_paths
from core.enrich_contract import apply_cover_preserve, compute_has_servable_cover, cover_uri_is_servable, enrich_success
from core.organizer import organize_file
from core.path_utils import to_file_uri, uri_to_fs_path, uri_to_local_fs_path, coerce_to_file_uri
from core.scraper import (
    search_jav, search_jav_single_source, strip_internal_nfo_keys,
    search_javlib_versions, fetch_javlib_by_detail_url, internal_nfo_carriers,
)
from core.source_config import validate_source_id
from core.cf_transport import get_cf_transport, CfChallengeRequired, CfTransportUnavailable
from core.scrapers.javlibrary import JAVLIBRARY_ORIGIN
from core.logger import get_logger
from core.config import load_config
from core.readonly_source import is_path_readonly, readonly_source_prefixes, writable_source_prefixes
from core.readonly_producer import (
    resolve_owning_output_root, resolve_ingest_plan, _produce_one,
    _readonly_stub_not_found, _readonly_enrich_failure,
)
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


# 唯讀來源 guard 的錯誤訊息（單一真理來源；sync helper 與 batch async loop 共用）。
_READONLY_SOURCE_ERROR_MSG = (
    "此來源路徑為唯讀（readonly），無法搬移或重新命名檔案。"
    "請改用掃描頁『產生』生成本地媒體庫，或確認你對此路徑有寫入權限。"
)

# P2 review round 3 (FIX#4)：readonly 來源 + mode='db_to_sidecar' 的拒絕訊息（單一
# 真理來源；enrich-single 與 batch 的 _do_readonly 共用）。db_to_sidecar 意指「把 DB
# 現有 metadata 寫回來源 sidecar NFO、不刮網」——唯讀來源零寫入牆下，來源 sidecar 本來
# 就不可寫；output_dir 的 NFO 又是產生流程自動管理，故此 mode 對唯讀來源無意義。
_READONLY_DB_TO_SIDECAR_ERROR_MSG = (
    "唯讀來源不支援 db_to_sidecar（產物 NFO 由產生流程自動管理，來源零寫入）"
)

# P1 revert + reject (round-3 review 2026-07-21，owner-confirmed)：Codex PR#113
# round-3 threaded a write_nfo=false skip-NFO gate into the readonly produce
# path — that was a P1 data-loss (a title-changing rescrape with
# write_nfo=False skipped writing the new NFO while stale-cleanup still
# unlinked the old one, losing the NFO while the DB kept a stale nfo_mtime
# claiming it exists). Readonly produce is HOLISTIC — a library entry always
# has an NFO — so write_nfo=false is rejected here exactly like
# db_to_sidecar above (both are granular flags the holistic produce model
# doesn't support), instead of threading a skip flag down into
# _produce_one/_write_movie_assets.
_READONLY_NO_NFO_ERROR_MSG = (
    "唯讀來源產生一律含 NFO（holistic 產物），不支援 write_nfo=false"
)


def _readonly_source_error(file_path: str) -> Optional[dict]:
    """唯讀來源 guard：只依 file_path 判斷所屬來源是否唯讀（readonly）。

    P3 grok-review（pre-merge 2026-07-21）：TASK-104-T3 之後，`enrich-single`／
    `fetch-samples`／`batch-enrich` 的唯讀項已不再走「拒絕」——改道 `_produce_one`
    落 output_dir（見 `resolve_owning_output_root`/`resolve_ingest_plan`）。本
    helper 現僅供 **`scrape-single`** 使用，該端點語意是「搬移/改名來源檔案」，
    唯讀來源本就無法安全支援，維持一律拒絕、不寫任何 sidecar。

    是 → 回既有錯誤形狀 plain dict（scrape-single 不搬檔、不刮削、不寫任何 sidecar）；
    否則回 None。兩端一律用 UNC-tolerant coerce_to_file_uri，不做原生路徑正規化
    （Codex P2：對 UNC 在 WSL/Linux 會拋 ValueError，而 UNC 正是 readonly 主場景）。
    coerce_to_file_uri 對「已是 DB canonical file:/// URI」原樣回、對 FS path 才轉，
    避免 to_file_uri 雙重包成 file:///file:/// 繞過 guard（Codex P1）。helper 自己讀
    config（每次呼叫重判，安全側）。

    ⚠️ 本 helper 內含 load_config()（阻塞 I/O），僅可用於 sync 端點（threadpool）；async
    路由（如 batch_enrich）須改為「入口一次載入 config → readonly_source_prefixes 算一次
    → 逐項 is_path_readonly 純比對」，勿在 event loop 上裸呼叫本 helper（async-offload 守衛）。
    """
    _gallery_config = load_config().get('gallery', {})
    _path_mappings = _gallery_config.get('path_mappings', {})
    _prefixes = readonly_source_prefixes(_gallery_config, _path_mappings)
    _writable = writable_source_prefixes(_gallery_config, _path_mappings)
    # uri-no-reverse: coerce_to_file_uri forward URI build, D2 complement
    if is_path_readonly(coerce_to_file_uri(file_path, _path_mappings), _prefixes, _writable):
        return {"success": False, "error": _READONLY_SOURCE_ERROR_MSG}
    return None


# Codex PR#113 P4 one-pass alignment (2026-07-21): readonly ingest/rescrape
# writes the whole meta wholesale (no _merge_meta partial-diff concept the
# way non-readonly enrich_single has), so there is no equivalent "fields the
# scrape supplemented" diff to report. Listing the non-empty top-level
# metadata keys is a reasonable "what got written" summary for the
# fields_filled slot of the EnrichResult shape.
_READONLY_FIELDS_FILLED_KEYS = ('title', 'actors', 'tags', 'date', 'maker', 'director', 'series', 'label')


def _readonly_fields_filled(meta: dict) -> List[str]:
    return [k for k in _READONLY_FIELDS_FILLED_KEYS if meta.get(k)]


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
    # 必須在 extract_number / search_jav / organize_file 之前（Codex P1）。
    _err = _readonly_source_error(file_path)
    if _err:
        return _err

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
    path_mappings = config.get('gallery', {}).get('path_mappings', {})

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
                # TASK-91b-T1（axis-B 子形狀 ii，forward-map 式）：new_filename 是
                # organize_file 產出的裸本機路徑，需帶 path_mappings 落 mapped DB
                # 命名空間，否則 get_by_path miss、既有 user_tags 靜默遺失。
                path_uri = to_file_uri(new_filename, path_mappings)
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

        # 首刮 focal trigger（TASK-98b-T2 / 99b-T2 read-back 重構）：只在 file 在
        # Scanner 追蹤夾（有 DB row）才排——非 synced 無 row，submit 也 silent-miss。
        # 重建 to_file_uri(target_file, path_mappings) 必等於 db_inflow 寫入的
        # video.path（禁 normalize 疊加）。
        #
        # ⚠️ 99b-T2 CD-99b-4：不可用 result['cover_path']（scraper 分析用的封面）
        # 當分析檔 + expected URI——db_inflow.try_inflow_upsert 內部呼叫
        # VideoScanner().scan_file() 在磁碟上重新偵測封面/sidecar，external-manager
        # 模式下可能選到不同的 poster/fanart 檔，與 result['cover_path'] 不同源
        # （db_inflow.py 全檔 grep cover 零命中）。改為 read-back 權威 `row.cover_path`
        # ——分析檔與 expected URI 同源，免除任何推導證明，且順手修正「焦點對 A
        # 算、render 卻裁 B」的既有隱性錯誤。
        #
        # ⚠️ 致命細節 1：必須自建 focal_repo，不可重用上面 :186 的 `repo`——那個
        # 綁在 `if result.get('success') and metadata.get('user_tags'):` 分支內，
        # 無 user_tags 的正常刮削路徑走到此處 `repo` 未綁定，誤用會 UnboundLocalError。
        # ⚠️ 致命細節 2：`VideoRepository()`/`get_by_path()`/`uri_to_local_fs_path()`
        # 都在 maybe_submit_video_focal 內部 try/except 的保護邊界外，此區塊必須
        # 自帶 try/except，否則任何例外會把已成功的刮削請求打成 500（CD-99b-7）。
        if target_file and db_sync_status == "synced":
            try:
                focal_repo = VideoRepository()
                row = focal_repo.get_by_path(to_file_uri(target_file, path_mappings))
                if row and row.cover_path:  # row is None 或 cover_path='' → 不排、不炸
                    cover_fs = uri_to_local_fs_path(row.cover_path, path_mappings)
                    maybe_submit_video_focal(
                        number,
                        metadata.get("maker") if isinstance(metadata, dict) else "",
                        row.path,
                        cover_fs,
                        cover_path_uri=row.cover_path,
                    )
            except Exception:
                logger.warning("scrape_single: 首刮 focal 排程失敗（不影響整理結果）", exc_info=True)

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
    # TASK-104-T3 (CD-104-5): readonly-source intent — 'ingest' (放大鏡, local-first)
    # or 'rescrape' (gear, always-remote). MUST stay optional: existing non-readonly
    # / batch / integration callers never send it and must not 422 (Codex P1-2).
    # Non-readonly files ignore this field entirely (byte-identical); a readonly
    # file with it omitted defaults to 'ingest' (safe default — never force a
    # remote overwrite without an explicit gear action).
    readonly_action: Optional[Literal['rescrape', 'ingest']] = None


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


def _javlib_candidate_scraper_data(request: "EnrichRequest"):
    """Fetch a javlibrary detail_url candidate for the readonly gear-rescrape
    branch (TASK-104-T3). Reuses the exact SSRF guard + CfChallengeRequired/
    CfTransportUnavailable handling as `enrich_single_endpoint`'s own (non-
    readonly) detail_url block below — deliberately NOT shared/called from
    there, to keep that inline block byte-identical (zero risk to
    tests/integration/test_rescrape_javlib.py's existing coverage, which is
    outside this task's file allowlist).

    Returns `(scraper_data, error_response)`: on any guard-trip/failure,
    `error_response` is the exact structured dict the endpoint must return
    verbatim (never raise — CD-104-10 lifecycle symmetry); on success
    `scraper_data` is the `to_legacy_dict()` + `internal_nfo_carriers()` merge
    and `error_response` is None.
    """
    if not _is_javlibrary_url(request.detail_url):
        logger.warning("enrich_single: 拒絕非法 detail_url origin")
        return None, {"success": False, "error": "detail_url 來源不合法"}
    try:
        video = fetch_javlib_by_detail_url(request.detail_url, request.number)
    except CfChallengeRequired:
        t = get_cf_transport()
        if t:
            try:
                t.begin_solve(JAVLIBRARY_ORIGIN, 'javlibrary')
            except Exception:
                logger.exception("enrich_single: begin_solve 失敗，回 cf_unavailable")
                return None, {"success": False, "cf_unavailable": True}
        return None, {"success": False, "cf_needed": True}
    except CfTransportUnavailable:
        return None, {"success": False, "cf_unavailable": True}
    if video is None:
        return None, {"success": False, "error": "javlibrary 無法取得指定版本資料"}
    # to_legacy_dict 省略 _summary/_rating 內部 carrier；補回以對齊既有 javlibrary
    # 重刮的 NFO 輸出（search_jav 走 internal_nfo_carriers 注入同組，PR #89 Codex P2）
    scraper_data = video.to_legacy_dict()
    scraper_data.update(internal_nfo_carriers(video))
    return scraper_data, None


@router.post("/enrich-single")
def enrich_single_endpoint(request: EnrichRequest) -> dict:
    config = load_config()
    search_cfg = config.get("search", {})
    proxy_url = search_cfg.get("proxy_url", "")
    # TASK-91-T3：讀取端 path_mappings，供 resolve_nfo_cover_paths / uri_to_local_fs_path /
    # enrich_single 共用一次算好的同一組值（避免重複 .get() chain）。
    path_mappings = config.get("gallery", {}).get("path_mappings", {})

    # TASK-104-T3 (CD-104-5)：唯讀來源片不再一律拒絕——改道 output_dir。
    # resolve_owning_output_root 依 canonical URI 找最內層唯讀來源（尊重 writable
    # override）；None → 非唯讀，落到下方既有 400-guard + enrich_single 路徑
    # （byte-identical，零改動）。找到 → 早 return，絕不 fall-through 到 400-guard
    # （resolve_nfo_cover_paths 對唯讀路徑推 source-adjacent 路徑沒有意義，CD-104-10）。
    canonical = coerce_to_file_uri(request.file_path, path_mappings)  # uri-no-reverse: coerce_to_file_uri forward URI build, D2 complement
    owning = resolve_owning_output_root(canonical, config)
    if owning is not None:
        source, output_root, output_uri = owning
        # Codex PR#113 one-pass alignment (2026-07-21): readonly branch now returns
        # the ACTUAL EnrichResult dataclass shape (asdict'd) on every path — success
        # AND failure — so the frontend badge/fly-in UI keyed off nfo_written/
        # cover_written/fields_filled/source_used/reason gets the same contract
        # whether the file came from a writable or readonly source (closes the
        # whole class of partial-shape divergences Codex peeled off one at a time).
        # P2 review round 3 (FIX#4): mode='db_to_sidecar' means "write current DB
        # metadata to the SOURCE sidecar NFO, no scrape" — for a readonly source
        # the source sidecar cannot be written at all (zero-write wall), and the
        # output_dir NFO is auto-managed by the produce flow (resolve_ingest_plan/
        # _produce_one), so this mode has no meaningful readonly behaviour. Reject
        # early — before resolve_ingest_plan/_produce_one — with a clean, full-shape
        # EnrichResult rather than silently doing a full ingest/rescrape instead
        # (this branch otherwise ignores request.mode entirely).
        if request.mode == 'db_to_sidecar':
            return asdict(_readonly_enrich_failure(_READONLY_DB_TO_SIDECAR_ERROR_MSG, 'error'))
        # P1 revert + reject (round-3 review 2026-07-21): readonly produce is
        # holistic (a library entry always has an NFO) — write_nfo=false is
        # rejected the same way db_to_sidecar is above, rather than threading
        # a skip-NFO flag down into resolve_ingest_plan/_produce_one (see
        # _READONLY_NO_NFO_ERROR_MSG). The frontend never sends
        # write_nfo=false, so this is zero UI impact.
        if not request.write_nfo:
            return asdict(_readonly_enrich_failure(_READONLY_NO_NFO_ERROR_MSG, 'error'))
        if not output_root:
            return asdict(_readonly_enrich_failure("未設定媒體庫輸出路徑", "error"))
        try:
            action = request.readonly_action or 'ingest'
            scraper_data = None
            if action == 'rescrape' and request.source == 'javlibrary' and request.detail_url:
                scraper_data, _cand_err = _javlib_candidate_scraper_data(request)
                if _cand_err:
                    return _cand_err
            fs_path = uri_to_local_fs_path(request.file_path, path_mappings)
            meta, cover_strategy = resolve_ingest_plan(
                fs_path, request.number, config.get("scraper", {}),
                action=action, proxy_url=proxy_url, scraper_data=scraper_data, source=request.source,
                javbus_lang=request.javbus_lang,
            )
            if not meta:
                # FIX P2-A / FIX#4 (P2 parity closeout): mirror non-readonly
                # core.enricher.py:391/429's not-found bookkeeping — mark
                # scrape_attempted_at so this file isn't rescanned/rescraped
                # forever. TRAP: update_scrape_attempted_at is a bare
                # UPDATE...WHERE path=? that silently no-ops without a row —
                # insert_if_ignore MUST run first to create the stub row
                # (mirrors bulk readonly_producer.py:1559-1561 byte-for-byte).
                # reason='not_found' (not 'error') matches the batch sibling
                # (:1003) and non-readonly enricher.py:393/431.
                repo = VideoRepository()
                _readonly_stub_not_found(repo, canonical, request.number, fs_path)
                return asdict(_readonly_enrich_failure("找不到可用的番號資料", "not_found"))
            repo = VideoRepository()
            existing = repo.get_by_path(canonical)
            # Codex PR#113 P2#3（round 2，owner-confirmed 全面對齊；round 6 修正）：
            # readonly enrich 對齊非唯讀 core.enricher._write_cover 的 skip 語意
            # （os.path.exists(cover) and not overwrite_existing）——fill_missing
            # （放大鏡在「已有封面、缺 NFO」的片上點，見 state-lightbox.js:1634-1650）
            # 或 write_cover=false 時只補 NFO，絕不動既有封面（output_dir 的封面檔與
            # DB cover_path 皆保留）。refresh_full（gear 一律送 mode='refresh_full'
            # +overwrite_existing=true，見 state-rescrape.js:404/408；或放大鏡在無
            # 封面片上點）不受此擋，維持既有「一律寫」行為。
            # round 6 fix（Codex PR#113 round-6，P2，found in 2 readonly branches）：
            # had_cover 只看 DB `existing.cover_path` 不夠——DB row 可能殘留、輸出
            # 封面檔已被刪除或路徑對應後在磁碟上不存在，這樣仍會誤判「已有封面」
            # 而跳過重建，留下一張壞掉/消失的圖。改為額外要求檔案實際存在於磁碟，
            # 與 _write_cover 的 os.path.exists(cover_path) 判斷真正一致。
            had_cover = cover_uri_is_servable(
                existing.cover_path if existing else "", path_mappings
            )
            cover_strategy = apply_cover_preserve(
                cover_strategy, request.write_cover, request.overwrite_existing, had_cover
            )
            file_info = {
                "path": fs_path,
                "size": existing.size_bytes if existing else os.path.getsize(fs_path),
                "mtime": existing.mtime if existing else os.path.getmtime(fs_path),
            }
            # _produce_one now returns (movie_dir, assets). NFO is always written
            # (P1 revert, round-3 review 2026-07-21 — write_nfo=false is rejected
            # above, before this point is ever reached). cover_written reflects
            # whether the cover step actually produced a file (cover_strategy=
            # ('none',) or a failed copy/download both leave assets['cover_fs'] == '').
            _, assets = _produce_one(
                repo, source, config.get("scraper", {}), file_info=file_info,
                meta=meta, cover_strategy=cover_strategy, assets_mode='full',
                existing=existing, output_root=output_root, output_uri=output_uri,
                allocated_this_run=set(), path_mappings=path_mappings,
            )
            thumbnail_cache.invalidate(canonical)
            cover_written = bool(assets.get('cover_fs'))
            # Bug 1 fix (feature/105): `reason` must reflect whether a SERVABLE
            # cover exists — DB has cover_path AND the physical file is on disk —
            # not just whether the DB row has a cover_path. _produce_one已同步
            # upsert（寫檔+_db_upsert）於上，故此處重讀 DB 最終 cover_path + 磁碟
            # 複驗，與 core.enricher.enrich_single 共用同一個 compute_has_servable_cover
            # 原子（消除唯讀漏磁碟複驗的破圖 false-positive）。key=canonical，與
            # 上方 existing = repo.get_by_path(canonical) 及 _produce_one 的 upsert
            # key 同一命名空間。
            has_servable_cover = compute_has_servable_cover(repo, canonical, path_mappings)
            # Codex PR#113 P2#4（round 2）：對齊 core.enricher.enrich_single:528-547
            # ——只在「本次實際寫入新封面內容」時才作廢舊手動焦點、再排新的背景偵測。
            # preserve_cover=True 時 cover_strategy=('none',) 不產出檔案，
            # assets['cover_fs'] 恆為空 → cover_written 恆 False，此塊不進、既有
            # manual 焦點原樣保留（與 enricher 的 cover_written 閘門語意一致）。
            if cover_written:
                try:
                    focal_repo = VideoRepository()  # 致命細節 1：不可重用上面的 repo 變數
                    # TASK-105-T6: reset+submit 收斂至共用 helper。
                    schedule_focal_after_cover_write(
                        focal_repo, canonical, meta['number'], meta.get('maker'),
                        assets['cover_fs'], path_mappings,
                    )
                except Exception:
                    logger.warning("readonly enrich focal 排程失敗（不影響改道結果）", exc_info=True)
            return asdict(enrich_success(
                # NFO is always written on a successful readonly produce (P1
                # revert, round-3 review 2026-07-21) — write_nfo=false never
                # reaches here (rejected above).
                nfo_written=True,
                cover_written=cover_written,
                extrafanart_written=len(assets.get('sample_fs', [])),
                fields_filled=_readonly_fields_filled(meta),
                source_used=meta.get('source', ''),
                has_servable_cover=has_servable_cover,
            ))
        except Exception:
            logger.exception("enrich_single_endpoint readonly 改道失敗")
            return asdict(_readonly_enrich_failure("enrich 處理失敗，請查閱日誌", "error"))

    # CD-62-4 分裂陷阱智慧防呆：refresh_full + overwrite=false 時，若這組設定不會寫出任何
    # sidecar（NFO/cover）卻仍 _db_upsert，就是純分裂。一個 sidecar「會寫」需 write 旗標開 + 檔案缺
    # （此分支 overwrite 已為 false，既有檔不覆寫）。兩者皆不會寫 → 擋；任一會寫則放行（quick-enrich
    # 缺封面零回歸）。涵蓋 write_nfo/write_cover 皆 false 的純 DB-only 路徑（Codex P1）。
    # write_extrafanart 刻意排除：_write_extrafanart 無 overwrite gate 且只在 scraper 回
    # sample_images 才寫；若 scraper 無 samples → 零磁碟寫出但 _db_upsert 照跑 = 分裂，
    # 故不得計入「保證會寫 sidecar」；補劇照請用 /api/scraper/fetch-samples（Codex PR#47 round-2 P2）。
    # 在 try 之前 raise，避免被下方 except Exception 吞成籠統 200。
    if request.mode == "refresh_full" and not request.overwrite_existing:
        nfo_path, cover_path = resolve_nfo_cover_paths(request.file_path, path_mappings)
        will_write_nfo = request.write_nfo and not os.path.exists(nfo_path)
        will_write_cover = request.write_cover and not os.path.exists(cover_path)
        # 72d-P2A：外部圖寫出機會也是合法的寫出路徑（72b-T6 加入 external_manager 後守衛未同步）
        external_manager = config.get("scraper", {}).get("external_manager", "off")
        if external_manager != "off":
            stem = os.path.splitext(uri_to_local_fs_path(request.file_path, path_mappings))[0]
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
            path_mappings=path_mappings,
        )
        # feature/71 T8: 換封面成功 → 失效舊縮圖（下次 lazy/prewarm 重生，CD-9 / spec 2.A.7）。
        # request.file_path 已是 DB 的 file:/// URI（前端送 currentLightboxVideo.path /
        # missing-check items / rescrape，皆 DB v.path）。縮圖 canonical key = v.path 原字串
        # hash（generate/serve/prewarm 同源），故 invalidate 必須用同一 URI 原值——用冪等
        # coerce_to_file_uri（已是 URI 就原樣回），不可再套 to_file_uri 造成 file:///file:///
        # double-encode 砍錯 hash（PR #60 Codex P2）。
        if result.success:
            thumbnail_cache.invalidate(coerce_to_file_uri(request.file_path))  # uri-no-reverse: coerce_to_file_uri forward URI build, D2 complement
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
    # TASK-91-T3：站台5 outer to_file_uri 補傳 path_mappings（inner uri_to_fs_path 維持不變，
    # 見 TASK-91-T3.md 站台5 inner/outer 分析結論）。
    path_mappings = config.get("gallery", {}).get("path_mappings", {})

    # TASK-104-T3 (CD-104-5)：唯讀來源片改道 output_dir，僅補劇照（samples_only）。
    # 不走 resolve_ingest_plan——它會強制清空 sample_images（ingest/rescrape 皆不含
    # 劇照），故直接用 search_jav 取劇照 URL 列表。None → 非唯讀，落到下方既有
    # multi-video guard + fetch_samples_only 路徑（byte-identical）。
    canonical = coerce_to_file_uri(req.file_path, path_mappings)  # uri-no-reverse: coerce_to_file_uri forward URI build, D2 complement
    owning = resolve_owning_output_root(canonical, config)
    if owning is not None:
        source, output_root, output_uri = owning
        # Codex PR#113 one-pass alignment (2026-07-21): mirror core.enricher.
        # fetch_samples_only's own EnrichResult field-for-field — nfo_written/
        # cover_written are always False here (samples-only never touches NFO or
        # cover), fields_filled is always [] (no metadata merge happens).
        if not output_root:
            return asdict(_readonly_enrich_failure("未設定媒體庫輸出路徑", "error"))
        try:
            meta = search_jav(req.number, source="auto", proxy_url=proxy_url)
            # P2 review round 3 (FIX#2/FIX#3): mirror core.enricher.fetch_samples_only
            # field-for-field. That function NEVER sets `reason` (EnrichResult's
            # dataclass default, None, on every path — success, file-not-found,
            # meta-not-found alike) and distinguishes a TOTAL search failure
            # (search_jav found nothing at all, enricher.py:715-718 → success=False
            # + error) from "found metadata but it has no sample_images to
            # download" (not an error — meta.get("sample_images", []) just
            # defaults to [], nothing to write, success=True/extrafanart_written=0).
            # The old `not meta or not meta.get(...)` conflated both into one
            # success=True branch, silently swallowing total search failures.
            if not meta:
                return asdict(_readonly_enrich_failure(f"找不到 {req.number} 的資料"))
            if not meta.get("sample_images"):
                return asdict(enrich_success(
                    nfo_written=False, cover_written=False,
                    extrafanart_written=0, fields_filled=[],
                    source_used=meta.get('source', ''),
                    reason=None,
                ))
            fs_path = uri_to_local_fs_path(req.file_path, path_mappings)
            repo = VideoRepository()
            existing = repo.get_by_path(canonical)
            file_info = {
                "path": fs_path,
                "size": existing.size_bytes if existing else os.path.getsize(fs_path),
                "mtime": existing.mtime if existing else os.path.getmtime(fs_path),
            }
            # P2 review (2026-07-21): report the ACTUALLY-downloaded count, not the
            # requested one — `len(meta["sample_images"])` used to be returned
            # verbatim regardless of how many downloads actually succeeded, so a
            # partial/total download failure still reported full success.
            # `assets['sample_fs']` (from _produce_one's new (movie_dir, assets)
            # return) only contains the files `_write_movie_assets` actually wrote
            # — the same source `_upsert_db` uses to (conditionally) update
            # sample_images, so this count and the DB state can never disagree.
            _, assets = _produce_one(
                repo, source, config.get("scraper", {}), file_info=file_info,
                meta=meta, cover_strategy=('none',), assets_mode='samples_only',
                existing=existing, output_root=output_root, output_uri=output_uri,
                allocated_this_run=set(), path_mappings=path_mappings,
            )
            written = len(assets.get('sample_fs', []))
            return asdict(enrich_success(
                nfo_written=False, cover_written=False,
                extrafanart_written=written, fields_filled=[],
                source_used=meta.get('source', ''),
                reason=None,
            ))
        except Exception:
            logger.exception("fetch_samples_endpoint readonly 改道失敗")
            # fetch_samples_only never sets reason='error' either (it has no
            # top-level exception boundary of its own — stays the dataclass
            # default None on every path), so this router-level catch-all
            # matches with reason=None too (FIX#2 field-for-field parity).
            return asdict(_readonly_enrich_failure("fetch_samples 處理失敗，請查閱日誌"))

    # uri-no-reverse: comparison-only (DB LIKE prefix), inner kept bare per TASK-91-T3 inner/outer analysis
    folder_uri_prefix = to_file_uri(os.path.dirname(uri_to_fs_path(req.file_path)), path_mappings) + "/"
    repo = VideoRepository()
    count = repo.count_videos_in_folder(folder_uri_prefix)
    if count > 1:
        return {"success": False, "error": "multi_video_folder", "count": count, "extrafanart_written": 0}

    try:
        result = fetch_samples_only(
            file_path=req.file_path,
            number=req.number,
            proxy_url=proxy_url,
            path_mappings=path_mappings,
        )
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

    # 90c-T1 唯讀 guard（async-safe）：config 已於上方 to_thread 載入，這裡從既載入的
    # config 算一次唯讀前綴集（純比對、無 I/O），逐項用 is_path_readonly 純比對——不可在
    # async event loop 上裸呼叫含 load_config 的 _readonly_source_error（async-offload 守衛）。
    _ro_gallery = config.get("gallery", {})
    _ro_mappings = _ro_gallery.get("path_mappings", {})
    _ro_prefixes = readonly_source_prefixes(_ro_gallery, _ro_mappings)
    _ro_writable = writable_source_prefixes(_ro_gallery, _ro_mappings)

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

                # TASK-104-T3 (CD-104-5)：唯讀項不再拒絕，改道 output_dir（action 固定
                # 'ingest'——batch 語意是補缺、非撞號選版；撞號選版走單片 enrich-single
                # gear rescrape，見 CD-104-5 P1-b）。混合批中可寫項照常 enrich，整批不中斷
                # （spec-90 §90b(iii) 驗收 2）。`_produce_one`/`resolve_ingest_plan` 是阻塞
                # I/O（寫檔、可能刮網）→ 須比照既有 :557-574 offload 慣例包進
                # run_in_executor，不可在 event loop 上裸呼叫（async-offload 守衛）。
                # item/canonical 用預設參數綁定，避免 for-loop 變數 late-binding
                # （同既有 :559 lambda 慣例）。
                # uri-no-reverse: coerce_to_file_uri forward URI build, D2 complement
                canonical = coerce_to_file_uri(item.file_path, _ro_mappings)
                if is_path_readonly(canonical, _ro_prefixes, _ro_writable):
                    def _do_readonly(itm=item, uri=canonical, es=effective_source, el=effective_lang):
                        # P2 review round 3 (FIX#4): same db_to_sidecar rejection as
                        # enrich_single_endpoint's readonly branch (see that branch's
                        # comment) — placed before resolve_owning_output_root so it
                        # short-circuits regardless of output_dir configuration.
                        # BatchEnrichRequest has no per-item mode override, so this
                        # is checked once against the whole-batch `request.mode`.
                        if request.mode == 'db_to_sidecar':
                            return ('db_to_sidecar', _READONLY_DB_TO_SIDECAR_ERROR_MSG)
                        # P1 revert + reject (round-3 review 2026-07-21): same
                        # write_nfo=false rejection as enrich_single_endpoint's
                        # readonly branch (see _READONLY_NO_NFO_ERROR_MSG) — readonly
                        # produce is holistic, no per-item override exists.
                        if not request.write_nfo:
                            return ('no_nfo', _READONLY_NO_NFO_ERROR_MSG)
                        owning = resolve_owning_output_root(uri, config)
                        if owning is None:
                            return ('skip', None)  # 理論不達（上面 is_path_readonly 已判真）
                        ro_source, out_root, out_uri = owning
                        if not out_root:
                            return ('error', "未設定媒體庫輸出路徑")
                        fs_path = uri_to_local_fs_path(itm.file_path, _ro_mappings)
                        # P2 fix (round-3 review 2026-07-21): thread the caller's own
                        # effective_source/effective_lang into the ingest scrape-
                        # fallback instead of leaving resolve_ingest_plan's source/
                        # javbus_lang at their None defaults (which silently forced
                        # every no-valid-NFO batch item through source="auto").
                        meta, cs = resolve_ingest_plan(
                            fs_path, itm.number, config.get("scraper", {}),
                            action='ingest', proxy_url=proxy_url, source=es, javbus_lang=el,
                        )
                        if not meta:
                            # FIX P2-A (P2 parity closeout): same not-found
                            # bookkeeping as enrich_single_endpoint's readonly
                            # branch (see that branch's comment for the
                            # insert_if_ignore-before-update_scrape_attempted_at
                            # trap). This branch already canonicalizes 'no_scrape'
                            # → reason='not_found' below (:1003) — no change there.
                            stub_repo = VideoRepository()
                            _readonly_stub_not_found(stub_repo, uri, itm.number, fs_path)
                            return ('no_scrape', "找不到可用的番號資料")
                        repo = VideoRepository()
                        existing = repo.get_by_path(uri)
                        # Codex PR#113 P2#3（round 2，owner-confirmed 全面對齊；round 6
                        # 修正）：batch readonly 對齊 enrich_single_endpoint 同一段
                        # cover-preserve gate（見該處註解，含 round-6 fix 說明）。
                        # BatchEnrichRequest 沒有 per-item mode/write_cover/
                        # overwrite_existing 覆寫欄位（BatchEnrichItem 只帶 file_path/
                        # number/source/javbus_lang），一律用整批 request 的值。
                        had_cover = cover_uri_is_servable(
                            existing.cover_path if existing else "", _ro_mappings
                        )
                        cs = apply_cover_preserve(
                            cs, request.write_cover, request.overwrite_existing, had_cover
                        )
                        file_info = {
                            "path": fs_path,
                            "size": existing.size_bytes if existing else os.path.getsize(fs_path),
                            "mtime": existing.mtime if existing else os.path.getmtime(fs_path),
                        }
                        try:
                            # _produce_one now returns (movie_dir, assets) — payload
                            # (P3 review 2026-07-21) carries assets back out of the
                            # executor so the 'ok' branch below can surface the full
                            # EnrichResult shape (Codex PR#113 one-pass alignment) on
                            # the result-item, same as the non-readonly EnrichResult
                            # shape the frontend (state-batch.js) already keys its
                            # badge/fly-in animation off of. NFO is always written
                            # (P1 revert, round-3 review 2026-07-21 — write_nfo=false
                            # is rejected above, before this point is ever reached).
                            _, assets = _produce_one(
                                repo, ro_source, config.get("scraper", {}), file_info=file_info, meta=meta,
                                cover_strategy=cs, assets_mode='full', existing=existing,
                                output_root=out_root, output_uri=out_uri,
                                allocated_this_run=set(), path_mappings=_ro_mappings,
                            )
                        except Exception:
                            logger.exception("batch_enrich readonly item %s 失敗", itm.number)
                            return ('error', "生成失敗")
                        # Codex PR#113 P2#4（round 2）：對齊 enrich-single / core.enricher
                        # ——只在本次「實際寫入新封面內容」時才 reset+re-submit focal。留在
                        # executor 執行緒內完成（run_in_executor 已離開 event loop）——
                        # reset_focal_to_auto 是阻塞 DB 寫、maybe_submit_video_focal 內部
                        # 亦有阻塞 DB 讀，不可搬回外層 async 裸呼叫（async-offload 守衛）。
                        if assets.get('cover_fs'):
                            try:
                                focal_repo = VideoRepository()  # 致命細節 1：不可重用上面的 repo
                                # TASK-105-T6: reset+submit 收斂至共用 helper。
                                schedule_focal_after_cover_write(
                                    focal_repo, uri, meta['number'], meta.get('maker'),
                                    assets['cover_fs'], _ro_mappings,
                                )
                            except Exception:
                                logger.warning(
                                    "batch_enrich readonly item %s focal 排程失敗（不影響結果）",
                                    itm.number, exc_info=True,
                                )
                        # Bug 1 fix (feature/105): has_servable_cover MUST re-read
                        # the final DB row + disk-verify (shared compute_has_servable_cover
                        # atom, same as core.enricher.enrich_single). The DB read
                        # (repo.get_by_path) is a BLOCKING sqlite call — it MUST stay
                        # inside this executor closure (already off the event loop);
                        # doing it in the async 'ok' branch below would block the loop.
                        # _produce_one already upserted synchronously above, so this
                        # reads the produced/preserved cover_path. key=uri (=canonical),
                        # same namespace as existing = repo.get_by_path(uri) and
                        # _produce_one's upsert key. Carried out via payload since
                        # `repo`/`existing` are local to this closure.
                        has_servable_cover = compute_has_servable_cover(repo, uri, _ro_mappings)
                        return ('ok', (assets, meta, has_servable_cover))

                    try:
                        loop = asyncio.get_running_loop()
                        status, payload = await loop.run_in_executor(None, _do_readonly)
                        if status == 'ok':
                            success_count += 1
                            # PR#114 P2: 縮圖失效是 best-effort cleanup（檔案 unlink 可拋
                            # OSError）——比照上方 focal 排程各自 try/except 吞掉，不可讓其
                            # 失敗被外層 except 捕獲，否則同一成功項會 success+failed 雙記
                            # 且被誤報成失敗（done 匯總 success+failed > total）。
                            try:
                                thumbnail_cache.invalidate(canonical)
                            except Exception:
                                logger.warning(
                                    "batch_enrich item %s 縮圖失效失敗（不影響結果）",
                                    item.number, exc_info=True,
                                )
                            # nfo_written=True unconditionally: assets_mode='full' reaching
                            # here means _write_movie_assets ran to completion (it raises
                            # otherwise, caught above as 'error'), and the NFO write is
                            # always attempted now (P1 revert, round-3 review 2026-07-21 —
                            # write_nfo=false is rejected above, before this point).
                            # has_servable_cover was computed INSIDE the executor closure
                            # (compute_has_servable_cover: final DB re-read + disk verify,
                            # Bug 1 fix feature/105) and carried out via payload — the DB
                            # read is blocking and must not run in this async context.
                            # reason mirrors non-readonly EnrichResult semantics
                            # (core/enricher.py) so state-batch.js _resolveCardStatus
                            # doesn't fall back to its success-implies-'hit' default —
                            # an NFO-only ingest (no servable cover) reports 'no_cover',
                            # so the frontend never builds a /api/gallery/thumb URL for a
                            # cover that isn't servable.
                            assets, item_meta, has_servable_cover = payload or ({}, {}, False)
                            cover_written = bool(assets.get('cover_fs'))
                            result_item = {
                                'type': 'result-item', 'number': item.number, 'file_path': item.file_path,
                                **asdict(enrich_success(
                                    nfo_written=True,
                                    cover_written=cover_written,
                                    extrafanart_written=len(assets.get('sample_fs', [])),
                                    fields_filled=_readonly_fields_filled(item_meta),
                                    source_used=item_meta.get('source', ''),
                                    has_servable_cover=has_servable_cover,
                                )),
                            }
                            yield f"data: {json.dumps(result_item)}\n\n"
                        else:
                            failed_count += 1
                            # P2 review round 3 (FIX#5): canonicalize `reason` — only
                            # 'hit'/'no_cover'/'not_found'/'error' are ever emitted, never
                            # a raw internal status string. 'no_scrape' → 'not_found'
                            # (mirrors core.enricher's own not_found reason value for the
                            # same "couldn't find any data" condition — Codex PR#113
                            # one-pass alignment); every other non-'ok' status ('error',
                            # 'db_to_sidecar' [FIX#4], and the theoretically-unreachable
                            # 'skip') collapses to 'error' — previously `reason = status`
                            # would have leaked 'skip' verbatim if that dead path were
                            # ever somehow hit.
                            reason = 'not_found' if status == 'no_scrape' else 'error'
                            result_item = {
                                'type': 'result-item', 'number': item.number, 'file_path': item.file_path,
                                **asdict(_readonly_enrich_failure(payload or '生成失敗', reason)),
                            }
                            yield f"data: {json.dumps(result_item)}\n\n"
                    except Exception:
                        # TASK-105-T9（BUG，PR#113 round 8 Codex thread `Sn2qv`）：唯讀分支
                        # 補齊與可寫路徑（:1045 對應 except）同層的 per-item 隔離。narrow
                        # try（:889，護 _produce_one）與 focal try（:914）之外的任何
                        # in-executor 例外（如 resolve_ingest_plan）改前會經 await（原
                        # :941）重拋、直上批次層 try（:803）→ raise → 整批 SSE 崩潰。此
                        # except 把該唯讀項隔離成一筆失敗結果項，同批其他項照常完成。
                        # except Exception（非 BaseException）：asyncio.CancelledError
                        # 需正確上傳，不得被吞成假失敗項。
                        logger.exception("batch_enrich readonly item %s 失敗", item.number)
                        failed_count += 1
                        result_item = {
                            'type': 'result-item', 'number': item.number, 'file_path': item.file_path,
                            **asdict(_readonly_enrich_failure("enrich 處理失敗，請查閱日誌", 'error')),
                        }
                        yield f"data: {json.dumps(result_item)}\n\n"
                    continue

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
                            path_mappings=_ro_mappings,
                        ),
                    )
                    result_dict = asdict(result)
                    if result.success:
                        success_count += 1
                        # feature/71 T8: 換封面成功 → 失效舊縮圖（廉價同步 unlink，不需 offload）。
                        # item.file_path 已是 DB file:/// URI → 冪等 coerce，不可 double-encode
                        # （同 enrich-single，PR #60 Codex P2）。
                        # PR#114 P2: unlink 可拋 OSError → best-effort try/except 吞掉，避免被
                        # 外層 except 捕獲導致同一成功項 success+failed 雙記 + 誤報失敗。
                        try:
                            thumbnail_cache.invalidate(coerce_to_file_uri(item.file_path))  # uri-no-reverse: coerce_to_file_uri forward URI build, D2 complement
                        except Exception:
                            logger.warning(
                                "batch_enrich item %s 縮圖失效失敗（不影響結果）",
                                item.number, exc_info=True,
                            )
                    else:
                        failed_count += 1
                    yield f"data: {json.dumps({'type': 'result-item', 'number': item.number, 'file_path': item.file_path, **result_dict})}\n\n"
                except Exception:
                    logger.exception("batch_enrich item %s 失敗", item.number)
                    failed_count += 1
                    yield f"data: {json.dumps({'type': 'result-item', 'number': item.number, 'file_path': item.file_path, 'success': False, 'error': 'enrich 處理失敗，請查閱日誌', 'reason': 'error'})}\n\n"

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
