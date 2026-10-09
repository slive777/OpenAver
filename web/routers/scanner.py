"""
Scanner API 路由 - 影片列表生成

端點：
- GET  /api/gallery/generate              — 掃描資料夾並產生影片列表（SSE 串流）
- GET  /api/gallery/stats                 — 取得 Scanner 統計資訊（影片總數）
- DELETE /api/gallery/cache               — 清除所有影片快取（清空 SQLite）
- GET  /api/gallery/update-check          — 檢查需要補全 NFO 的影片數量
- GET  /api/gallery/update                — 執行 NFO 補全更新（SSE 串流）
- GET  /api/gallery/view                  — 取得產生的 HTML 列表頁面
- GET  /api/gallery/actress-stats         — 查詢指定女優名稱的片數
- GET  /api/gallery/jellyfin-check        — 檢查多少影片缺少 Jellyfin poster/fanart
- GET  /api/gallery/jellyfin-update       — 批次產生 Jellyfin poster + fanart（SSE 串流）
- GET  /api/gallery/missing-check         — 檢查缺少 NFO/封面的影片清單
- GET  /api/gallery/browse-dir            — 列舉資料夾目錄與影片檔案清單
"""

import asyncio
import base64
import json
import os
import queue
import sys
import threading
import time
import requests
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse, HTMLResponse, JSONResponse
from starlette.background import BackgroundTask

from core.gallery_scanner import VideoScanner, fast_scan_directory, VideoInfo, _run_sample_images_cleanup_pass, is_nas_system_dir_name  # noqa: PLC2701 — scanner 的 rescan 端點需要在特定時機主動觸發 gallery_scanner 內部的樣本圖清理 pass（該 pass 平常只在 scanner 自身流程內被呼叫），避免把整段清理邏輯複製一份到 router 層
from core.cover_layout import cover_base_stem
from core.video_extensions import get_video_extensions
from core.gallery_generator import HTMLGenerator
from core.path_utils import to_file_uri, is_path_under_dir, uri_to_fs_path, coerce_to_file_uri, uri_to_local_fs_path
from core.nfo_updater import check_cache_needs_update, update_videos_generator
from core.database import VideoRepository, Video, init_db, get_db_path, migrate_json_to_sqlite
from core.focal import requires_face_detection
from core.focal_trigger import maybe_submit_video_focal
from core.organizer import generate_jellyfin_images, HEADERS as _EMBED_HEADERS
from core.config import load_config, iter_gallery_sources, get_gallery_source_paths, STEM_IMAGE_MODES
from core.data_root import resolve_gallery_output_path
from core.readonly_producer import produce_source
from web.routers.gallery_media import safe_realpath
from core.readonly_source import is_path_readonly, readonly_source_prefixes, writable_source_prefixes
from core.generate_state import try_mark_generate_active, mark_generate_done
from core import thumbnail_cache
from core.scraper import smart_search
from core.source_settings import is_uncensored_mode_effective
from pydantic import BaseModel
from core.logger import get_logger
from core.platform_info import DSM_PERMISSION_HINT, is_synology
from core.proxy_policy import proxy_kwargs
from web.routers.notifications import emit_notification as _emit_notif
from core.wishlist_reconcile import reconcile_wishlist, format_wishlist_removed_message

logger = get_logger(__name__)

router = APIRouter(prefix="/api/gallery", tags=["gallery"])

# T3(40c): Jellyfin check TTL 快取（60 秒）
_jellyfin_cache_result: dict | None = None
_jellyfin_cache_time: float = 0


def _sse_event(data: dict) -> str:
    """將 dict 編碼為 SSE 格式的單條 message。"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _collect_long_paths(
    all_files: List[Dict[str, Any]],
    threshold: int = 260,
) -> List[str]:
    """a5: 從 fast_scan_directory 結果收集超過 threshold 的 path（純函數）。

    呼叫端負責 platform gate（sys.platform == 'win32'）。
    此 helper 不檢查平台，方便單元測試。
    """
    return [f['path'] for f in all_files if len(f['path']) > threshold]


def _emit_long_path_warnings(logger_, long_paths: List[str]) -> None:
    """a5: 把長路徑清單寫到 debug.log（空 list 時不輸出）。"""
    if not long_paths:
        return
    logger_.warning(f"[a5] 發現 {len(long_paths)} 個路徑超過 260 字元：")
    for p in long_paths:
        logger_.warning(f"  {p}")


# ---------------------------------------------------------------------------
# TASK-88c-T2: readonly 來源分流 + SSE thread/queue 橋接 + 四數摘要
# ---------------------------------------------------------------------------

def _outcome_to_sse(o) -> dict:
    """把 ProduceOutcome 轉一條 SSE log 行 dict（純函式）。

    error 已是固定 "生成失敗"（producer 已 sanitize，:462）→ 直接轉發，
    不再塞 server-side 細節。failed → warn，其餘 info。
    """
    label = {
        "created": "✓ 生成",
        "skipped": "略過",
        "no_scrape": "刮不到",
        "failed": "✗ 失敗",
    }.get(o.status, o.status)
    msg = f"  {label}: {o.number or o.source_uri}"
    if o.status == "failed" and o.error:
        msg += f"（{o.error}）"
    return {"type": "log", "level": "warn" if o.status == "failed" else "info", "message": msg}


def _accumulate_readonly(summary: dict, result) -> None:
    """跨來源累計四數 + no_output/unreachable/partial/pruned（純函式，CD-88c-3 / TASK-89b-T6）。

    no_output_path → 只 no_output+1；unreachable → 只 unreachable+1（Finding-2 修復，
    須插在通用 aborted_reason 分支之前，否則會被通用分支吃掉）；其他非空 aborted_reason
    （not_readonly 防呆）→ 記 log 不計數；正常 → sources+1 並累加
    created/skipped/no_scrape/failed/pruned，skipped_paths 非空另計 partial+1。
    """
    if result.aborted_reason == "no_output_path":
        summary["no_output"] += 1
        return
    if result.aborted_reason == "unreachable":
        summary["unreachable"] += 1
        return
    if result.aborted_reason:
        logger.info("唯讀來源略過（%s）: %s", result.aborted_reason, result.source_path)
        return
    summary["sources"] += 1
    summary["created"] += result.created
    summary["skipped"] += result.skipped
    summary["no_scrape"] += result.no_scrape
    summary["failed"] += result.failed
    summary["pruned"] += result.pruned
    if result.skipped_paths:
        summary["partial"] += 1


def _yield_source_summary(result) -> Generator[str, None, None]:
    """該來源小結（產生器）。

    no_output_path → 「請先設定輸出夾」提示（Acceptance #11）。
    unreachable → 「來源無法連線」warn 提示（TASK-89b-T6，Finding-2 修復）。
    正常小結後，skipped_paths 非空時追加「已略過刪除偵測」warn（比照非 readonly
    分支 :428-433 文案風格）。
    """
    if result.aborted_reason == "no_output_path":
        yield _sse_event({
            "type": "log", "level": "warn",
            "message": f"  {result.source_path}: 請先設定輸出夾，已略過",
        })
    elif result.aborted_reason == "unreachable":
        yield _sse_event({
            "type": "log", "level": "warn",
            "message": f"  {result.source_path}: 來源無法連線，已略過",
        })
    elif not result.aborted_reason:
        yield _sse_event({
            "type": "log", "level": "info",
            "message": (
                f"  {result.source_path}: 新增 {result.created}／略過 {result.skipped}"
                f"／刮不到 {result.no_scrape}／失敗 {result.failed}"
            ),
        })
        if result.skipped_paths:
            yield _sse_event({
                "type": "log", "level": "warn",
                "message": f"  {result.source_path}: {len(result.skipped_paths)} 個路徑讀取失敗，已略過刪除偵測",
            })


def _run_readonly_source(src, config, repo, proxy_url, summary, reachable: bool = True, should_abort: Optional[Callable[[], bool]] = None, strm_mappings_getter: Optional[Callable[[], dict]] = None) -> Generator[str, None, None]:
    """在 daemon worker thread 跑 produce_source，drain 無界 queue 逐片 yield SSE。

    worker 例外（含 produce_source 迴圈前的 normalize/列檔/DB 拋錯，未被 producer
    內 try 包覆）顯式接手（CD-88c-1 / Codex P1），不靜默吞：box['error'] → 產生器
    emit error SSE + source_errors+1 + 續下一來源。

    strm_mappings_getter（PR #93 五審四次 P2, option C）：注入 produce_source，讓 media-server
    模式每片重讀 fresh strm 映射，封死斷線尾巴那片用凍結舊映射落檔的殘留。
    """
    q: "queue.Queue" = queue.Queue()  # 無界：worker 永不阻塞於 put，client 斷線 daemon 自然退出
    _SENTINEL = object()
    box: dict = {}

    def _work():
        try:
            box['result'] = produce_source(
                src, config, repo, proxy_url=proxy_url,
                on_progress=q.put,
                should_abort=should_abort,
                reachable=reachable,
                strm_mappings_getter=strm_mappings_getter,
            )
        except Exception:
            logger.exception("唯讀生成來源失敗: %s", src.path)
            box['error'] = True
        finally:
            q.put(_SENTINEL)

    t = threading.Thread(target=_work, daemon=True)
    t.start()
    yield _sse_event({"type": "log", "level": "info", "message": f"唯讀生成: {src.path}"})
    while True:
        item = q.get()
        if item is _SENTINEL:
            break
        yield _sse_event(_outcome_to_sse(item))
    t.join()
    if box.get('error'):
        summary["source_errors"] += 1
        yield _sse_event({
            "type": "log", "level": "error",
            "message": f"  {src.path}: 生成失敗（來源無法存取或設定錯誤）",
        })
        return
    result = box.get('result')
    if result is not None:
        _accumulate_readonly(summary, result)
        yield from _yield_source_summary(result)


def _permission_denied_warning(directory: str) -> str:
    """權限不足時共用的掃描警告（Synology 附 DSM 指引）。"""
    warning = f"  {directory}: 沒有權限讀取，跳過刪除偵測以免誤刪"
    if is_synology():
        warning += f"；{DSM_PERMISSION_HINT}"
    return warning


def _scan_root_skip_message(directory: str, normalized_dir: str) -> Optional[str]:
    """根目錄不可存取時回傳警告；可存取時回傳 None。"""
    try:
        os.stat(normalized_dir)
    except (FileNotFoundError, NotADirectoryError):
        return f"資料夾不存在: {directory}"
    except PermissionError:
        return _permission_denied_warning(directory)
    except (OSError, ValueError):  # 與 os.path.exists 一致：畸形路徑也只跳過這個來源
        return f"資料夾不存在: {directory}"
    return None


def _skipped_scan_warning(directory: str, root: str, skipped_paths: dict[str, OSError]) -> str:
    """掃描有路徑被跳過時的 SSE 警告：根目錄本身沒權限 → 講「沒有權限」（Synology 附 DSM 指引）；其餘維持泛用句（159-T10a）"""
    if isinstance(skipped_paths.get(root), PermissionError):
        return _permission_denied_warning(directory)
    return f"  {directory}: {len(skipped_paths)} 個路徑讀取失敗，跳過刪除偵測以免誤刪（詳見 debug.log）"


def generate_avlist(should_abort: Optional[Callable[[], bool]] = None) -> Generator[str, None, None]:  # noqa: C901 — avlist SSE 生成主流程；109 已判定為「列 backlog、現在別搬」（60–100 處測試 patch target 焊死該函式，拆分成本由測試面而非邏輯面決定）
    """產生影片列表（SSE 串流）- 使用 SQLite 儲存"""

    try:
        # 載入設定
        config = load_config()
        gallery_config = config.get('gallery', {})

        directories = get_gallery_source_paths(gallery_config)
        output_dir = gallery_config.get('output_dir', '') or ''
        output_filename = gallery_config.get('output_filename', 'gallery_output.html')
        path_mappings = gallery_config.get('path_mappings', {})
        min_size_mb = gallery_config.get('min_size_mb', 0)

        # 預設顯示設定
        default_mode = gallery_config.get('default_mode', 'image')
        default_sort = gallery_config.get('default_sort', 'date')
        default_order = gallery_config.get('default_order', 'descending')
        items_per_page = gallery_config.get('items_per_page', 90)

        # 取得全域主題設定
        default_theme = config.get('general', {}).get('theme', 'light')

        if not directories:
            yield _sse_event({"type": "error", "message": "未設定掃描資料夾"})
            return

        # 53b-T3: 確認 directories 有值才 emit 掃描開始通知
        _emit_notif("info", "notif.scanner_started", task_type="scanner_generate")
        logger.info(f"[Gallery] 開始生成，目錄數: {len(directories)}")

        # 確保輸出目錄存在（空值 → 資料根；相對／絕對值依 resolve_gallery_output_path）
        output_path = resolve_gallery_output_path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        html_path = output_path / output_filename
        cache_path = output_path / output_filename.replace('.html', '_cache.json')
        db_path = get_db_path()

        yield _sse_event({"type": "log", "level": "info", "message": f"輸出路徑: {html_path}"})

        # 檢查是否需要遷移 JSON cache 到 SQLite
        if cache_path.exists() and not db_path.exists():
            yield _sse_event({"type": "log", "level": "info", "message": "遷移 JSON cache 到 SQLite..."})
            migrate_result = migrate_json_to_sqlite(cache_path, db_path, delete_on_success=True)
            yield _sse_event({"type": "log", "level": "info", "message": f"遷移完成: {migrate_result['migrated']} 筆"})

        # 初始化資料庫
        init_db(db_path)
        repo = VideoRepository(db_path)

        yield _sse_event({"type": "log", "level": "info", "message": f"資料庫筆數: {repo.count()}"})

        # 初始化掃描器
        scanner = VideoScanner(path_mappings=path_mappings, nfo_title_format=config.get('scraper', {}).get('nfo_title_format', '[{num}]{title}'))

        total_dirs = len(directories)
        total_inserted = 0
        total_updated = 0
        total_deleted = 0
        scan_error_count = 0
        session_added_paths = []  # 追蹤本次新增/變更的影片路徑
        long_paths: list[str] = []  # a5: Windows 長路徑收集（只在 win32 填充）

        # TASK-88c-T2: readonly 來源生成摘要（跨來源累計，迴圈前初始化避免清零）
        proxy_url = config.get('search', {}).get('proxy_url', '')
        readonly_summary = {
            "created": 0, "skipped": 0, "no_scrape": 0, "failed": 0,
            "no_output": 0, "sources": 0, "source_errors": 0,
            "unreachable": 0, "partial": 0, "pruned": 0,
        }

        for idx, src in enumerate(iter_gallery_sources(gallery_config), 1):
            # TASK-90b-T4: 逐來源中止檢查（每個來源處理之前），比照唯讀分支
            # T3 既有語意「這一個單位做完，下一個開始前停」。should_abort 可能
            # 為 None（向後相容），先短路判斷。
            if should_abort and should_abort():
                break

            directory = src.path
            logger.info(f"[Gallery] 掃描: {directory}")

            # TASK-88c-T2: readonly 來源分流（早於 normalize，UNC 主場景不被擋）
            if src.readonly:
                # TASK-89b-T5 / CD-89b-5: 可達性防呆補在 readonly 分流點（:366 的
                # os.path.exists 只在非 readonly 分支執行，readonly 分支需要等義入口
                # 檢查）。src.path 是 config 原始輸入，不套 reverse_path_mapping
                # （比照 :353/:96 既定作法，見 TASK-89b-T5 現況分析 #5）。
                reachable = os.path.exists(uri_to_fs_path(src.path))  # uri-no-reverse: native config path (src.path), no DB-mapped namespace
                # PR #93 五審四次 P2 (option C)：注入 fresh strm 映射 getter。config 是 :303
                # 一次載入的凍結快照；load_config() 無 lru_cache、每次讀 disk，故 getter 拿到
                # 的是「當下磁碟上的」映射 → 斷線尾巴那片也用當前映射。
                yield from _run_readonly_source(
                    src, config, repo, proxy_url, readonly_summary, reachable,
                    should_abort=should_abort,
                    strm_mappings_getter=lambda: load_config().get('scraper', {}).get('strm_path_mappings', {}),
                )
                continue

            # 轉換路徑格式 (Windows -> WSL)。directory 可能是 FS 路徑或 file:/// URI
            # （DirectoryConfig.path schema）。uri_to_fs_path 對 URI→FS、FS→FS 皆冪等，
            # 取代裸 normalize_path（後者對 URI 原樣通過 → os.path.exists 失敗 → 誤報
            # 「資料夾不存在」，非 readonly 的 URI 來源掃不到）。
            try:
                normalized_dir = uri_to_fs_path(directory)  # uri-no-reverse: native config path (DirectoryConfig.path), no DB-mapped namespace
            except ValueError:
                logger.exception("路徑轉換失敗: %s", directory)
                yield _sse_event({"type": "log", "level": "warn", "message": "路徑轉換失敗"})
                continue

            yield _sse_event({
                "type": "progress",
                "status": f"掃描: {directory}",
                "current": idx,
                "total": total_dirs + 1  # +1 for generating
            })
            skip_message = _scan_root_skip_message(directory, normalized_dir)
            if skip_message is not None:
                yield _sse_event({"type": "log", "level": "warn", "message": skip_message})
                continue

            try:
                # 快速掃描取得檔案列表
                min_size_bytes = min_size_mb * 1024 * 1024
                video_extensions = get_video_extensions(config)
                # a5 Codex fix: 收集因 OSError/PermissionError 被跳過的路徑
                # （含 Windows 長路徑觸發的 OSError — 這些 entry 根本不會進 all_files）
                skipped_paths: dict[str, OSError] = {}  # path → 例外（159-T10a：分辨「沒有權限」）
                all_files = fast_scan_directory(
                    normalized_dir,
                    video_extensions,
                    min_size_bytes,
                    on_skip=lambda p, e: skipped_paths.__setitem__(p, e),  # noqa: B023 — callback consumed synchronously within same iteration, not deferred
                )

                if not all_files and not skipped_paths:
                    yield _sse_event({"type": "log", "level": "info", "message": f"{directory}: 沒有影片檔案"})
                    continue

                # a5: Windows 長路徑警告（gate 在呼叫端，不在 helper）
                if sys.platform == 'win32':
                    long_paths.extend(_collect_long_paths(all_files))
                    # 把因長度而失敗的 skipped 路徑也納入警告（filter >260 過濾非長路徑失敗）
                    long_paths.extend(p for p in skipped_paths if len(p) > 260)

                yield _sse_event({"type": "log", "level": "info", "message": f"{directory}: 找到 {len(all_files)} 個檔案"})

                # 取得現有 mtime 索引
                db_index = repo.get_mtime_index()

                # 比對決定需要處理的檔案
                needs_scan = []
                current_paths = set()

                for file_info in all_files:
                    path = file_info['path']
                    file_uri = to_file_uri(path, path_mappings)
                    current_paths.add(file_uri)

                    db_entry = db_index.get(file_uri)
                    if db_entry is None:
                        # 新檔案
                        needs_scan.append(file_info)
                    elif db_entry[0] != file_info['mtime'] or db_entry[1] != file_info.get('nfo_mtime', 0) or db_entry[2] != file_info.get('sample_image_count', 0):
                        # mtime、nfo_mtime 或劇照張數變更（TASK-118b-T9：db_entry[2] 為 get_mtime_index() 哨兵值時代表壞資料，恆不等於真實張數 → 同樣觸發重掃，fail-safe）
                        needs_scan.append(file_info)

                # 清理已刪除的檔案（限定在此目錄下）
                # a5 Codex fix: scan 不完整時（skipped_paths 非空）跳過 deletion 偵測
                # current_paths 只含本次成功掃到的檔案；若有路徑因 OSError/PermissionError
                # 被跳過，current_paths 就不是本目錄完整集合，用它做 diff 會把「原本存在
                # 但這次沒掃到（因失敗）」的 DB 紀錄誤判為已刪除並清掉。
                # partial scan 只做 insert/update，不能 infer 刪除。
                if skipped_paths:
                    yield _sse_event({
                        "type": "log",
                        "level": "warn",
                        "message": _skipped_scan_warning(directory, normalized_dir, skipped_paths)
                    })
                else:
                    normalized_dir_uri = to_file_uri(normalized_dir, path_mappings)
                    deleted_paths = [p for p in db_index.keys() if is_path_under_dir(p, normalized_dir_uri) and p not in current_paths]
                    if deleted_paths:
                        deleted_count = repo.delete_by_paths(deleted_paths)
                        # feature/71 T8: prune 連動失效縮圖。deleted_paths 已是 DB URI
                        # （db_index.keys()）→ 原樣傳入、不過 to_file_uri、不疊轉換（plan §0.1）。
                        for p in deleted_paths:
                            thumbnail_cache.invalidate(p)
                        total_deleted += deleted_count
                        yield _sse_event({"type": "log", "level": "info", "message": f"  清理 {deleted_count} 個已刪除檔案"})

                # 掃描並寫入需要更新的檔案
                videos_to_upsert = []
                cache_hits = len(all_files) - len(needs_scan)
                cache_misses = 0

                for i, file_info in enumerate(needs_scan, 1):
                    # TASK-90b-T4: 逐檔中止檢查（每檔處理之前）。單一資料夾內
                    # 檔案量大時，逐來源層檢查粒度太粗，需要在此內層迴圈頂端
                    # 再插一次，讓中止在「下一個可偵測的時間點」生效（不中斷
                    # 正在進行中的單一 scan_file() 呼叫）。
                    if should_abort and should_abort():
                        break

                    video_name = os.path.basename(file_info['path'])
                    yield _sse_event({"type": "log", "level": "info", "message": f"  [{i}/{len(needs_scan)}] {video_name}"})

                    try:
                        video_info = scanner.scan_file(file_info['path'], None)
                        video = Video.from_video_info(video_info)
                        video.mtime = file_info['mtime']
                        video.nfo_mtime = file_info.get('nfo_mtime', 0)
                        videos_to_upsert.append(video)
                        session_added_paths.append(video.path)
                        cache_misses += 1
                    except Exception:
                        logger.exception("掃描檔案失敗: %s", file_info.get('path', ''))
                        yield _sse_event({"type": "log", "level": "warn", "message": f"  [{i}] 掃描發生錯誤，已跳過"})
                        scan_error_count += 1

                # 批次寫入
                if videos_to_upsert:
                    inserted, updated = repo.upsert_batch(videos_to_upsert)
                    total_inserted += inserted
                    total_updated += updated

                # 掃描 focal trigger（TASK-98b-T2 / Codex PR#105 P2）：涵蓋本次掃描
                # in-scope 的所有空焦點無碼片，不只 upsert batch（needs_scan）——既有、
                # 未變動、auto_focal='' 的列（不在 videos_to_upsert 內）也要補，否則
                # 「重掃一次自動補焦既有庫」形同虛設。current_paths 是本目錄本次掃到
                # 的完整 DB-key URI 集合（:457-458 同一套 to_file_uri(path,
                # path_mappings) 推導），bulk 查詢，不另建 URI、不 N+1。
                #
                # TASK-99b-T1（CD-99b-8 sibling 併修）：fresh 查一次 should_abort()——
                # 中途取消時本段之前無任何中止檢查，若不擋，取消後仍會把整目錄的空
                # 焦點候選塞進單執行緒 FIFO worker（每 job ~3s），與
                # readonly_producer.produce_source 的同型洞同批修。只 gate 這段
                # focal pass，不影響上面的 upsert 與下面的完成通知。
                if current_paths and not (should_abort and should_abort()):
                    focal_candidates = repo.get_empty_focal_candidates(list(current_paths))
                    for c_path, c_number, c_maker, c_cover_path in focal_candidates:
                        # Codex P1（CD-99b-8 二次修）：:539 入口 gate 只擋「取消已在
                        # 迴圈開始前發生」；候選數可達數千、每圈一次 os.path.exists，
                        # 迴圈本身可能跑到秒級，取消也可能落在迴圈中途。此處每圈
                        # fresh 查一次，與入口 gate 防同一種傷害、只是取消落點不同。
                        if should_abort and should_abort():
                            break
                        if requires_face_detection(c_number, c_maker):
                            cover_fs = uri_to_local_fs_path(c_cover_path, path_mappings)
                            maybe_submit_video_focal(c_number, c_maker, c_path, cover_fs, db_path=repo.db_path, cover_path_uri=c_cover_path)

                logger.info(f"[Gallery] {directory}: {len(all_files)} 個檔案，快取命中 {cache_hits}")

                yield _sse_event({
                    "type": "log",
                    "level": "info",
                    "message": f"{directory}: {len(all_files)} 部 (快取: {cache_hits}, 新增/更新: {cache_misses})"
                })
            except Exception:
                logger.exception("掃描資料夾失敗: %s", directory)
                scan_error_count += 1
                yield _sse_event({"type": "log", "level": "error", "message": "掃描發生錯誤，已跳過此資料夾"})

        # TASK-90b-T4 / PR#90b Codex P1: 尾段每個外顯副作用（HTML 檔、完成通知、
        # done event）之前各自 fresh 查一次 should_abort()，而非迴圈結束時單次
        # snapshot。單次 snapshot 會漏掉「迴圈已結束、尾段進行中才斷線」的 race：
        # HTMLGenerator.generate() 期間 client 才斷線時，snapshot 仍為 False，後面
        # 的完成通知與 done event 仍照跑 → 對已中止的掃描誤報 success。改為每個
        # 外顯副作用前重新查詢，把 tail-race 窗口收斂到單一 event.is_set() 呼叫。
        def _is_aborted() -> bool:
            return bool(should_abort and should_abort())

        # 建立「當前設定資料夾」URI 集合，用於過濾 DB 記錄
        # DB 保留所有歷史資料當 cache，但只輸出當前設定的資料夾
        configured_dir_uris = set()
        for p in get_gallery_source_paths(gallery_config):
            try:
                # coerce_to_file_uri：來源 path 可能已是 file:/// URI（含 readonly 剛
                # upsert 的列），已是 URI 就原樣回、FS 才轉，避免 to_file_uri 二次包成
                # file:///file:/// 把 readonly 生成的列全數過濾掉（PR#91 P2-D）。
                configured_dir_uris.add(coerce_to_file_uri(p, path_mappings))  # uri-no-reverse: coerce_to_file_uri forward URI build, D2 complement
            except ValueError:
                continue

        # 從 SQLite 取得影片，只保留當前設定資料夾底下的記錄
        all_db_videos = [v for v in repo.get_all()
                         if any(is_path_under_dir(v.path, uri) for uri in configured_dir_uris)]

        # 轉換為 VideoInfo 格式供 HTMLGenerator 使用
        all_videos = []
        for v in all_db_videos:
            info = VideoInfo(
                path=v.path,
                title=v.title,
                originaltitle=v.original_title,
                actor=','.join(v.actresses) if v.actresses else '',
                num=v.number or '',
                maker=v.maker,
                date=v.release_date,
                genre=','.join(v.tags) if v.tags else '',
                size=v.size_bytes,
                mtime=int(v.mtime * 10000000 + 116444736000000000) if v.mtime else 0,
                img=v.cover_path
            )
            all_videos.append(info)

        # 檢查本次新增影片是否需要 NFO 補全（建構相容的 cache 格式）
        session_update = {"count": 0, "paths": []}
        if session_added_paths:
            # 建立只包含本次新增影片的 session_cache（相容 check_cache_needs_update 格式）
            session_cache = {}
            for path in session_added_paths:
                video = repo.get_by_path(path)
                if video:
                    session_cache[path] = {
                        'nfo_mtime': video.nfo_mtime,
                        'info': {
                            'title': video.title,
                            'date': video.release_date,
                            'actor': ','.join(video.actresses) if video.actresses else '',
                            'genre': ','.join(video.tags) if video.tags else '',
                            'maker': video.maker,
                            'num': video.number or '',
                            'director': video.director or '',
                            'duration': video.duration,
                            'series': video.series or '',
                            'label': video.label or '',
                        }
                    }
            if session_cache:
                session_stats = check_cache_needs_update(session_cache)
                session_update = {
                    "count": session_stats['need_update'],
                    "paths": session_stats['paths'],
                    "items": session_stats['items'],
                }
                if session_update['count'] > 0:
                    yield _sse_event({
                        "type": "log",
                        "level": "warn",
                        "message": f"發現 {session_update['count']} 部新增影片資訊不全"
                    })

        yield _sse_event({"type": "log", "level": "info", "message": f"資料庫總筆數: {repo.count()}"})

        # TASK-90b-T4: abort 時跳過 orphan 清理（全庫 pass，非本次掃描範圍新增
        # 的成本，abort 時執行拿不到「這次掃描結果更完整」的好處，純屬多做一次
        # 不必要的全庫查詢，見決策表）
        if not _is_aborted():
            # §b1 AC#2: sample_images 孤兒清理 pass（Scanner UI 主路徑覆蓋，共用 helper）
            try:
                cleaned = _run_sample_images_cleanup_pass(repo, path_mappings)
                if cleaned > 0:
                    yield _sse_event({"type": "log", "level": "info", "message": f"清除 {cleaned} 筆孤兒劇照記錄"})
            except Exception as e:
                logger.warning("sample_images cleanup pass failed: %s: %s", type(e).__name__, e)
                # 失敗不中斷 scan 流程

        # TASK-90b-T4: abort 時跳過 HTML 產生（成本隨影片數線性成長，是浪費工的
        # 主源；client 已斷線不會有人看這份輸出，見決策表）與對應的「完成」
        # progress event（HTML 都不產生了，沒有對應的真實進度可回報）
        if not _is_aborted():
            # 產生 HTML
            yield _sse_event({
                "type": "progress",
                "status": "產生網頁...",
                "current": total_dirs,
                "total": total_dirs + 1
            })

            generator = HTMLGenerator()
            generator.generate(
                all_videos,
                str(html_path),
                title="OpenAver Scanner",
                mode=default_mode,
                sort=default_sort,
                order=default_order,
                items_per_page=items_per_page,
                theme=default_theme
            )

            yield _sse_event({
                "type": "progress",
                "status": "完成",
                "current": total_dirs + 1,
                "total": total_dirs + 1
            })

        logger.info(f"[Gallery] 完成，新增 {total_inserted}，更新 {total_updated}，刪除 {total_deleted}")

        # TASK-88c-T2: readonly 生成摘要 log 行（僅有 readonly 活動時輸出）
        # TASK-89b-T6: unreachable/partial 納入活躍度判斷，否則全 unreachable 的
        # run 這行 log 完全不輸出，debug.log 事後排錯看不到這次唯讀掃描發生過什麼。
        if (readonly_summary["sources"] > 0 or readonly_summary["no_output"] > 0
                or readonly_summary["source_errors"] > 0 or readonly_summary["unreachable"] > 0
                or readonly_summary["partial"] > 0):
            logger.info(
                "唯讀生成完成: 新增 %d／略過 %d／刮不到 %d／失敗 %d／清除 %d"
                "（%d 個來源；%d 個未設輸出夾；%d 個來源錯誤；%d 個來源無法連線；%d 個來源部分讀取失敗）",
                readonly_summary["created"], readonly_summary["skipped"],
                readonly_summary["no_scrape"], readonly_summary["failed"], readonly_summary["pruned"],
                readonly_summary["sources"], readonly_summary["no_output"],
                readonly_summary["source_errors"], readonly_summary["unreachable"],
                readonly_summary["partial"],
            )

        # a5: 寫長路徑清單到 debug.log（helper 內部判斷空 list）
        _emit_long_path_warnings(logger, long_paths)

        # T3(40c) Codex fix: generate 後清空 jellyfin check 快取
        global _jellyfin_cache_result, _jellyfin_cache_time
        _jellyfin_cache_result = None
        _jellyfin_cache_time = 0

        # 53b-T3 / 88c-P2: 掃描完成通知
        # scan_error_count（一般掃描逐檔失敗）與 readonly source_errors（唯讀來源
        # 迴圈前整源拋錯）皆須讓完成通知走 warn，不可純 success（Codex P2：來源級
        # 失敗原本只增 source_errors，完成通知沒納入 → 仍報成功，誤導）。
        # 個別影片失敗（readonly failed，例如 NFO 寫入失敗）同樣須讓完成通知走
        # warn（PR#91 ②）。no_scrape 是「線上查無 metadata」的正常情況，不計入。
        # TASK-89b-T6（Codex Finding-2）：no_output/unreachable/partial 三者原本
        # 被 _accumulate_readonly/_yield_source_summary 安靜吸收，完成通知未讀
        # 它們 → 使用者看到 success，違反 spec §89b.3.3「警告並略過，不誤報成功」。
        # TASK-90b-T4 / PR#90b Codex P1+P2: abort 時不發 success/warn 完成通知（對
        # 已中止的掃描回報「完成」是明確誤報），但**必須**發一筆中性 terminal 通知
        # 與函式開頭無條件 emit 的 scanner_started 配對。通知中心是 append-only 的
        # 全域 deque（web/routers/notifications.py），不依 task_type 撤回或配對，只發
        # started 不發 terminal，會在通知抽屜永久殘留一筆看似未完成的「掃描開始」，
        # 使用者每中止一次就累積一筆錯的狀態（Codex P2）。此處 fresh 再查一次
        # should_abort()（Codex P1：涵蓋 HTML 產生期間才斷線的 tail-race）。
        _aborted = _is_aborted()

        try:
            _wl_removed = reconcile_wishlist()
        except Exception:
            logger.exception("wishlist 對帳失敗（掃描完成收尾）")
            _emit_notif("warn", "notif.wishlist_reconcile_failed", task_type="wishlist_reconcile")
            _wl_removed = []
        if _wl_removed:
            _emit_notif(
                "info", "notif.wishlist_auto_removed",
                message=format_wishlist_removed_message(_wl_removed),
                task_type="wishlist_reconcile",
            )

        if _aborted:
            _emit_notif(
                "info", "notif.scanner_cancelled",
                task_type="scanner_generate",
            )
        else:
            _source_errors = readonly_summary["source_errors"]
            _readonly_failed = readonly_summary["failed"]
            _readonly_no_output = readonly_summary["no_output"]
            _readonly_unreachable = readonly_summary["unreachable"]
            _readonly_partial = readonly_summary["partial"]
            if (scan_error_count > 0 or _source_errors > 0 or _readonly_failed > 0
                    or _readonly_no_output > 0 or _readonly_unreachable > 0 or _readonly_partial > 0):
                _err_parts = []
                if scan_error_count > 0:
                    _err_parts.append(f"{scan_error_count} 部失敗")
                if _source_errors > 0:
                    _err_parts.append(f"{_source_errors} 個來源失敗")
                if _readonly_failed > 0:
                    _err_parts.append(f"{_readonly_failed} 部失敗")
                if _readonly_no_output > 0:
                    _err_parts.append(f"{_readonly_no_output} 個來源未設輸出夾")
                if _readonly_unreachable > 0:
                    _err_parts.append(f"{_readonly_unreachable} 個來源無法連線")
                if _readonly_partial > 0:
                    _err_parts.append(f"{_readonly_partial} 個來源部分讀取失敗")
                _emit_notif(
                    "warn", "notif.scanner_done_with_errors",
                    message=f"完成 {len(all_videos)} 部，" + "、".join(_err_parts),
                    task_type="scanner_generate",
                )
            else:
                _emit_notif(
                    "success", "notif.scanner_done",
                    message=f"完成 {len(all_videos)} 部",
                    task_type="scanner_generate",
                )

            # TASK-90b-T4: abort 時跳過 done event——client 已斷線收不到，且
            # payload 的 output_path/video_count 語意上宣稱「已完成產生」，
            # HTML 根本沒產生會與實際狀態矛盾，見決策表。
            yield _sse_event({
                "type": "done",
                "video_count": len(all_videos),
                "output_path": str(html_path),
                "session_update": session_update,
                "long_paths": long_paths,  # a5
                "stats": {
                    "inserted": total_inserted,
                    "updated": total_updated,
                    "deleted": total_deleted
                },
                "readonly_stats": readonly_summary  # TASK-88c-T2: 加法式新欄位
            })

    except Exception as e:
        logger.error("產生影片列表失敗: %s", e)
        # T3(40c) Codex fix: exception 路徑也清空快取（DB 可能已被修改）
        # global 已在 try 區塊宣告，此處直接賦值即可
        _jellyfin_cache_result = None
        _jellyfin_cache_time = 0
        # 53b-T3: 掃描失敗通知（不洩漏 str(e) 到前端）
        _emit_notif(
            "error", "notif.scanner_failed",
            message="掃描中斷，請查閱日誌",
            task_type="scanner_generate",
        )
        yield _sse_event({"type": "error", "message": "產生影片列表失敗"})


# TASK-90b-T2: 斷線偵測輪詢間隔（秒）。定案依據見 plan-90b.md CD-90b-5/6：
# spike 實測顯示 Starlette（釘版 starlette==1.3.1）對同步 generator 直接丟給
# StreamingResponse 時，client 斷線僅停止再呼叫 next()，並不會主動對 generator
# 呼叫 .close()（GeneratorExit 備案在此版本上不會被觸發，等 GC 亦不可靠、觀測
# 不到 timely 觸發）；故採方案 A：獨立 asyncio task 主動輪詢
# `request.is_disconnected()`，非搶 iterate_in_threadpool 的同一組 receive
# channel（該輪詢與 StreamingResponse 內部行為互不干擾，spike 已驗證）。
_DISCONNECT_POLL_INTERVAL_SEC = 0.5


@router.get("/generate")
async def generate(request: Request):
    """產生影片列表（SSE 串流回傳進度）

    TASK-90b-T2：加入斷線偵測機制。`cancel_event`（`threading.Event`，非
    `asyncio.Event`——T3 要讓背景 daemon thread 安全讀取）在偵測到 client
    斷線時被設置；本 task 尚未把它串進 `generate_avlist`/`produce_source`
    （那是 T3），此處只負責建立 + 正確設置 + 生命週期收尾。
    """
    cancel_event = threading.Event()
    # Finding 2 + PR #93 P1 雙向互斥：以 cancel_event 為唯一 token 登記「產生進行中」，
    # 讓設定頁切換媒體伺服器模式在 generate 仍跑時被擋。try_mark_generate_active 同時檢查
    # 反方向——若設定頁正在切換模式（purge 窗口中），回 False → 拒絕開始產生，避免背景
    # producer 讀到舊唯讀來源、把剛被 purge 的卡 _upsert 補回（切模式後殭屍卡）。
    if not try_mark_generate_active(cancel_event):
        async def _refuse_switching():
            yield f"data: {json.dumps({'type': 'error', 'message': '設定切換中，請稍後再產生列表。'})}\n\n"
        return StreamingResponse(
            _refuse_switching(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    async def _watch_disconnect() -> None:
        try:
            while not cancel_event.is_set():
                if await request.is_disconnected():
                    cancel_event.set()
                    return
                await asyncio.sleep(_DISCONNECT_POLL_INTERVAL_SEC)
        except asyncio.CancelledError:
            # 正常完成路徑：外層 BackgroundTask 收尾時會 cancel 這個 task，
            # 屬預期流程，非錯誤。
            raise
        finally:
            # 兩條路徑皆會走到：斷線 → watcher return → finally；正常完成 →
            # _cleanup_watcher cancel → CancelledError → finally。故此處清 token
            # 可靠涵蓋 normal + disconnect，不會讓「產生中」旗標永久卡住（切換被永久擋）。
            mark_generate_done(cancel_event)

    watcher_task = asyncio.create_task(_watch_disconnect())

    async def _cleanup_watcher() -> None:
        # BackgroundTask：涵蓋「正常完成」路徑——Starlette 於 response 正常
        # 傳輸結束後 await 本 background，cancel 仍在輪詢的 watcher task，不留
        # 孤兒（CD-90b-5 追加 P2）。⚠️ 斷線路徑不靠這裡：starlette 1.3.1 在
        # send() 拋 OSError→ClientDisconnect 時會在 await background 之前就
        # 往上拋，本 background 不會被執行；但斷線路徑的 watcher 已自行偵測到
        # 斷線並 return（task 自然結束），故兩條路徑皆無 dangling task。
        # 正常完成路徑一定走到這裡：即使 watcher task 還沒真正跑過就被 cancel
        # （其 finally 因而不執行），這裡也保證清掉「產生中」token（idempotent），
        # 不讓正常完成後旗標殘留把 mode-switch 永久擋住。斷線路徑靠 watcher finally。
        mark_generate_done(cancel_event)
        watcher_task.cancel()
        try:
            await watcher_task
        except asyncio.CancelledError:
            pass

    response = StreamingResponse(
        generate_avlist(should_abort=cancel_event.is_set),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )
    response.background = BackgroundTask(_cleanup_watcher)
    # 測試用掛鉤（不影響 production 行為）：讓
    # tests/unit/test_scanner_generate_disconnect.py 可在不跑真 uvicorn 的
    # 情況下觀察 cancel_event / watcher_task 狀態。
    response.cancel_event = cancel_event
    response.watcher_task = watcher_task
    return response


@router.get("/stats")
def get_stats():
    """取得 Scanner 統計資訊（從 SQLite 讀取）"""
    try:
        db_path = get_db_path()

        if not db_path.exists():
            return {"success": True, "data": {"total": 0, "last_run": None, "last_added": None}}

        repo = VideoRepository(db_path)
        total = repo.count()

        return {
            "success": True,
            "data": {
                "total": total,
                "last_run": None,  # SQLite 版本不追蹤 last_run
                "last_added": None,  # SQLite 版本不追蹤 last_added
                "last_total": total
            }
        }
    except Exception as e:
        logger.error("取得統計資訊失敗: %s", e)
        return {"success": False, "error": "取得統計資訊失敗"}


@router.delete("/cache")
def clear_cache():  # ranker-invalidate-ok: (DELETE FROM videos only in docstring; actual deletion delegates to repo.clear_all() which already calls SimilarRankerCache.invalidate())
    """清除所有影片快取（DELETE FROM videos）"""
    try:
        db_path = get_db_path()

        if not db_path.exists():
            return {"success": True, "deleted": 0}

        repo = VideoRepository(db_path)
        deleted = repo.clear_all()
        # feature/71 T8: 清空整個縮圖快取目錄（CD-11 / spec 2.A.9）
        thumbnail_cache.clear_all()
        # T3(40c): 清空 jellyfin check 快取
        global _jellyfin_cache_result, _jellyfin_cache_time
        _jellyfin_cache_result = None
        _jellyfin_cache_time = 0
        return {"success": True, "deleted": deleted}
    except Exception as e:
        logger.error("清除快取失敗: %s", e)
        return {"success": False, "error": "清除快取失敗"}


def _build_nfo_update_cache(all_videos, config) -> tuple:
    """建構 `check_cache_needs_update` 相容的 cache，**並濾掉唯讀來源的列**。

    唯讀零寫入（spec-143 不變式：唯讀 ＝ 一般掃描 ＋ 產物落輸出夾）：
    `update_videos_generator` 寫的是**來源影片旁**的 sidecar NFO
    （`core/nfo_updater.py` 的 `get_nfo_path_from_video` ＝ 影片路徑 `.with_suffix('.nfo')`），
    對唯讀來源就是寫回使用者叫我們別碰的那個資料夾——而唯讀列的 `nfo_mtime` 指的是
    **輸出夾**那份的 mtime、恆 > 0，不濾掉一定會入選。

    判準與 `web/routers/scraper.py` 的批次入口同一套：config 算一次前綴集、逐項純比對、零 I/O。
    **`/update-check` 與 `/update` 共用本 helper**——兩邊各抄一份唯讀判定必然漂移，
    而漂移的形狀是「按鈕說要更新 N 部、實際只更新 M 部」。

    回傳 ``(cache, skipped_readonly, path_mappings)``。
    """
    gallery_config = config.get('gallery', {})
    path_mappings = gallery_config.get('path_mappings', {})
    ro_prefixes = readonly_source_prefixes(gallery_config, path_mappings)
    writable_prefixes = writable_source_prefixes(gallery_config, path_mappings)

    cache = {}
    skipped_readonly = 0
    for v in all_videos:
        if ro_prefixes and is_path_readonly(
            coerce_to_file_uri(v.path, path_mappings), ro_prefixes, writable_prefixes
        ):
            skipped_readonly += 1
            continue
        cache[v.path] = {
            'nfo_mtime': v.nfo_mtime,
            'info': {
                'title': v.title,
                'date': v.release_date,
                'actor': ','.join(v.actresses) if v.actresses else '',
                'genre': ','.join(v.tags) if v.tags else '',
                'maker': v.maker,
                'num': v.number or '',
                'director': v.director or '',
                'duration': v.duration,
                'series': v.series or '',
                'label': v.label or '',
            }
        }
    return cache, skipped_readonly, path_mappings


@router.get("/update-check")
def check_update():
    """檢查需要更新的影片數量（從 SQLite 讀取）"""
    try:
        db_path = get_db_path()

        if not db_path.exists():
            return {"success": True, "data": {"need_update": 0}}

        repo = VideoRepository(db_path)
        all_videos = repo.get_all()

        cache, _skipped_readonly, _path_mappings = _build_nfo_update_cache(all_videos, load_config())

        stats = check_cache_needs_update(cache)

        # 不要返回 paths 列表（太大）
        return {
            "success": True,
            "data": {
                "need_update": stats['need_update'],
                "details": {
                    "no_title": stats['no_title'],
                    "no_date": stats['no_date'],
                    "no_actor": stats['no_actor'],
                    "no_genre": stats['no_genre'],
                    "no_maker": stats['no_maker'],
                }
            }
        }
    except Exception as e:
        logger.error("檢查更新數量失敗: %s", e)
        return {"success": False, "error": "檢查更新數量失敗"}


@router.get("/missing-check")
def check_missing():
    """T10: 檢查 DB 中缺少 NFO 或封面的影片數量與清單"""
    try:
        db_path = get_db_path()

        if not db_path.exists():
            return {"success": True, "data": {"missing_both": 0, "missing_nfo": 0,
                                               "missing_cover": 0, "total_missing": 0, "items": []}}

        repo = VideoRepository(db_path)
        all_videos = repo.get_all()

        missing_both = 0
        missing_nfo = 0
        missing_cover = 0
        items = []

        for v in all_videos:
            has_nfo = (v.nfo_mtime or 0) > 0
            has_cover = bool(v.cover_path)
            produced = bool(v.output_dir)
            tried = (v.scrape_attempted_at or 0) > 0
            if produced or tried:
                continue
            if has_nfo and has_cover:
                continue
            if not v.number:  # skip videos without number (cannot enrich)
                continue
            item = {"file_path": v.path, "number": v.number}
            if not has_nfo and not has_cover:
                missing_both += 1
                item["category"] = "both"
            elif not has_nfo:
                missing_nfo += 1
                item["category"] = "nfo"
            else:
                missing_cover += 1
                item["category"] = "cover"
            items.append(item)

        total_missing = missing_both + missing_nfo + missing_cover

        # 永遠回傳完整 items 清單；大批量的 confirm gate 由前端處理
        return {
            "success": True,
            "data": {
                "missing_both": missing_both,
                "missing_nfo": missing_nfo,
                "missing_cover": missing_cover,
                "total_missing": total_missing,
                "items": items,
            }
        }
    except Exception as e:
        logger.error("檢查缺失 NFO/封面失敗: %s", e)
        return {"success": False, "error": "檢查缺失 NFO/封面失敗"}


def generate_nfo_update() -> Generator[str, None, None]:
    """NFO 更新生成器（SSE 串流）- 使用 SQLite"""

    try:
        db_path = get_db_path()

        if not db_path.exists():
            yield _sse_event({"type": "error", "message": "資料庫不存在，請先產生列表"})
            return

        repo = VideoRepository(db_path)
        all_videos = repo.get_all()

        if not all_videos:
            yield _sse_event({"type": "done", "message": "沒有影片資料", "updated": 0})
            return

        cache, skipped_readonly, path_mappings = _build_nfo_update_cache(all_videos, load_config())
        if skipped_readonly:
            yield _sse_event({
                "type": "log",
                "level": "info",
                "message": f"略過 {skipped_readonly} 部唯讀來源影片（不寫回來源資料夾）"
            })

        # 檢查需要更新的影片
        stats = check_cache_needs_update(cache)
        if stats['need_update'] == 0:
            yield _sse_event({"type": "done", "message": "沒有需要更新的影片", "updated": 0})
            return

        paths_to_update = stats['paths']
        yield _sse_event({
            "type": "log",
            "level": "info",
            "message": f"執行 NFO 檢查 ({len(paths_to_update)} 部)..."
        })

        # 執行更新（path_mappings 沿用 _build_nfo_update_cache 算好的那份，不重讀 config）
        for msg in update_videos_generator(cache, paths_to_update, path_mappings):
            yield _sse_event(msg)

        yield _sse_event({
            "type": "done",
            "message": "更新完成，建議重新產生網頁以更新資料庫",
        })

    except Exception as e:
        logger.error("NFO 更新失敗: %s", e)
        yield _sse_event({"type": "error", "message": "NFO 更新失敗"})


@router.get("/update")
async def run_update():
    """執行 NFO 更新（SSE 串流回傳進度）"""
    return StreamingResponse(
        generate_nfo_update(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.get("/view")
def view_list():
    """取得產生的 HTML 列表檔案（修改圖片路徑為 API 代理）"""
    try:
        config = load_config()
        gallery_config = config.get('gallery', {})
        output_dir = gallery_config.get('output_dir', '') or ''
        output_filename = gallery_config.get('output_filename', 'gallery_output.html')

        html_path = resolve_gallery_output_path(output_dir) / output_filename

        if not html_path.exists():
            return HTMLResponse(
                content="<html><body><h1>列表尚未產生</h1><p>請先到「列表生成」頁面產生列表。</p></body></html>",
                status_code=404
            )

        with open(html_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 將 file:/// 圖片路徑替換為 API 代理路徑（只替換圖片，不替換影片）
        # file:///C:/path/to/image.jpg -> /api/gallery/image?path=C:/path/to/image.jpg
        import re
        from urllib.parse import quote

        # 圖片副檔名
        image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp')

        def replace_file_url(match):
            file_path = match.group(1)
            # 只替換圖片路徑
            if file_path.lower().endswith(image_extensions):
                encoded_path = quote(file_path, safe='')
                return f'/api/gallery/image?path={encoded_path}'
            # 非圖片保持原樣
            return match.group(0)

        # 匹配 file:/// 後面直到引號的所有字元（包含空格和中文）
        content = re.sub(r'file:///([^"\'<>]+?)(?=["\'])', replace_file_url, content)

        return HTMLResponse(content=content)
    except Exception:
        logger.exception("view_list 讀取失敗")
        return HTMLResponse(
            content="<html><body><h1>錯誤</h1><p>列表載入失敗，請重試。</p></body></html>",
            status_code=500
        )


@router.get("/actress-stats")
def get_actress_stats(name: str = Query(..., description="女優名稱")):
    """查詢某名字的片數"""
    try:
        db_path = get_db_path()

        if not db_path.exists():
            return {"success": True, "data": {"count": 0}}

        repo = VideoRepository(db_path)
        count = repo.count_by_actress(name)

        return {"success": True, "data": {"count": count}}
    except Exception as e:
        logger.error("查詢女優片數失敗: %s", e)
        return {"success": False, "error": "查詢女優片數失敗"}


# === Jellyfin 圖片批次補齊 ===

def check_jellyfin_images_needed(repo: VideoRepository, path_mappings: dict = None) -> dict:
    """檢查 DB 中有多少影片缺少 poster/fanart"""
    videos = repo.get_all()
    need_update = []
    for v in videos:
        if not v.cover_path:
            continue
        cover_fs = uri_to_local_fs_path(v.cover_path, path_mappings)
        if not os.path.exists(cover_fs):
            continue
        base_stem = cover_base_stem(cover_fs)
        poster = base_stem + '-poster.jpg'
        fanart = base_stem + '-fanart.jpg'
        if not os.path.exists(poster) or not os.path.exists(fanart):
            need_update.append({
                'cover_path': cover_fs,
                'base_stem': base_stem,
                'number': v.number or '',
                'maker': v.maker or '',
                'path': v.path,
            })
    return {'need_update': len(need_update), 'items': need_update}


def generate_jellyfin_images_stream() -> Generator[str, None, None]:
    """SSE 串流：批次為影片產生 poster + fanart"""
    global _jellyfin_cache_result, _jellyfin_cache_time

    try:
        # Codex PR#123 P2：gate 必須排在 get_db_path() 之前——get_db_path() 內部會
        # mkdir 建立 output/ 資料夾（core/database/connection.py:15-22），是有副作用
        # 的磁碟操作。若先呼叫 get_db_path() 再判斷 gate，會導致「external_manager=
        # off 且資料庫不存在」（全新安裝／還沒產生過列表）這個情境下：gate 根本走
        # 不到，先建了 output/ 資料夾、又回傳 error 而非 spec-111 AC8 承諾的
        # done + updated:0（off 時零寫入），且與 _check_jellyfin_needed() 的順序
        # 不對稱。config 只讀一次，下面 path_mappings 沿用同一個 config。
        config = load_config()
        external_manager = config.get('scraper', {}).get('external_manager', 'off')
        if external_manager not in STEM_IMAGE_MODES:
            _jellyfin_cache_result = None
            _jellyfin_cache_time = 0
            yield _sse_event({"type": "done", "message": "沒有需要補齊的影片", "updated": 0})
            return

        db_path = get_db_path()

        if not db_path.exists():
            yield _sse_event({"type": "error", "message": "資料庫不存在，請先產生列表"})
            return

        repo = VideoRepository(db_path)
        path_mappings = config.get('gallery', {}).get('path_mappings', {})
        result = check_jellyfin_images_needed(repo, path_mappings)
        items = result['items']
        total = len(items)

        if total == 0:
            _jellyfin_cache_result = None
            _jellyfin_cache_time = 0
            yield _sse_event({"type": "done", "message": "沒有需要補齊的影片", "updated": 0})
            return

        yield _sse_event({"type": "log", "level": "info", "message": f"需補齊 {total} 部影片的圖片..."})

        completed = 0
        for i, item in enumerate(items, 1):
            # Codex PR#122 P2-b：開頭 gate 一次不夠——批次跑到一半使用者可能把
            # external_manager 切成 off（或非白名單），剩餘項目仍會繼續產生
            # poster/fanart，違反 AC8 的 TOCTOU 洞。每筆重讀成本可忽略（產一張圖
            # 含人臉偵測＋裁切＋寫檔，遠比讀一次 config 貴），故逐筆重讀而非只在
            # 進入迴圈前讀一次。命中就中止，沿用既有 done 事件形狀回報已完成筆數。
            current_config = load_config()
            current_external_manager = current_config.get('scraper', {}).get('external_manager', 'off')
            if current_external_manager not in STEM_IMAGE_MODES:
                break

            cover = item['cover_path']
            num = item['number']
            stem = item['base_stem']

            yield _sse_event({
                "type": "progress",
                "current": i,
                "total": total,
                "status": f"處理 {num}"
            })

            img_result = generate_jellyfin_images(
                cover, stem, number=item['number'], maker=item['maker']
            )

            if not img_result['fanart']:
                yield _sse_event({"type": "log", "level": "warn", "message": f"{num} fanart 複製失敗"})

            if img_result['poster']:
                yield _sse_event({"type": "log", "level": "info", "message": f"✓ {num} poster + fanart"})
            else:
                yield _sse_event({"type": "log", "level": "warn", "message": f"{num} poster 裁切失敗"})

            completed += 1

        # T3(40c): 清空快取，讓下次 check 反映最新圖片狀態
        _jellyfin_cache_result = None
        _jellyfin_cache_time = 0
        yield _sse_event({
            "type": "done",
            "message": f"完成！已補齊 {completed} 部影片的圖片",
            "updated": completed,
        })

    except Exception as e:
        logger.error("產生 Jellyfin 圖片失敗: %s", e)
        yield _sse_event({"type": "error", "message": "產生圖片失敗"})


def _check_jellyfin_needed() -> dict | None:
    """Threadpool helper: gate → TTL 快取命中 → get_db_path + check DB existence +
    open repo + run jellyfin check.

    spec-111 CD-111-2 gate：external_manager 不在 STEM_IMAGE_MODES 白名單（含 off）時，
    直接回傳零項，不產生 -poster/-fanart（fail-closed 正向白名單，不用 != 'off'）。

    Codex PR#122 P2-a：gate **必須**排在 TTL 快取讀取之前——快取只是「省重算」的
    優化，不能繞過「off 時回零項」的產品邊界。時序漏洞（修前）：media-server 模式
    呼叫一次把快取寫成正數 → 60 秒內把設定切成 off → 再呼叫 → 舊實作在 async body
    先查快取命中直接回傳，根本不會進到這支 gate，回傳舊的非零值，違反 AC8。
    現在快取讀寫也併入本 helper（threadpool 內執行），async 端不再碰快取狀態。

    Returns None if DB does not exist (caller handles as need_update=0 early return).
    Returns the result dict (from cache or freshly computed) otherwise.
    """
    global _jellyfin_cache_result, _jellyfin_cache_time

    config = load_config()
    external_manager = config.get('scraper', {}).get('external_manager', 'off')
    if external_manager not in STEM_IMAGE_MODES:
        return {'need_update': 0, 'items': []}

    # T3(40c): TTL 快取命中（gate 通過之後才查，見上方 docstring）
    if _jellyfin_cache_result is not None and time.time() - _jellyfin_cache_time < 60:
        return _jellyfin_cache_result

    db_path = get_db_path()
    if not db_path.exists():
        return None
    repo = VideoRepository(db_path)
    path_mappings = config.get('gallery', {}).get('path_mappings', {})
    result = check_jellyfin_images_needed(repo, path_mappings)

    # T3(40c): 更新快取
    _jellyfin_cache_result = result
    _jellyfin_cache_time = time.time()

    return result


@router.get("/jellyfin-check")
async def jellyfin_image_check():
    """檢查多少影片需要補齊 Jellyfin 圖片"""
    try:
        result = await asyncio.to_thread(_check_jellyfin_needed)

        if result is None:
            return {"success": True, "data": {"need_update": 0, "items": []}}

        return {"success": True, "data": {"need_update": result['need_update'], "items": result['items']}}
    except Exception as e:
        logger.error("檢查 Jellyfin 圖片狀態失敗: %s", e)
        return {"success": False, "error": "檢查圖片狀態失敗"}


@router.get("/jellyfin-update")
async def jellyfin_image_update():
    """批次產生 poster + fanart（SSE 串流回傳進度）"""
    return StreamingResponse(
        generate_jellyfin_images_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


_MIME_MAP = {
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.webp': 'image/webp',
}


_REFERER_MAP = {
    'javbus.com': 'https://www.javbus.com/',
    'dmm.co.jp': 'https://www.dmm.co.jp/',
    'jav321.com': 'https://www.jav321.com/',
}

_MIN_IMAGE_SIZE = 1000  # bytes — 小於此視為無效（防空白/錯誤頁）


def _embed_cover(img_ref: str, path_mappings: dict = None) -> str:
    """將圖片 URL/路徑轉為 data URI。失敗時回傳原值。"""
    if not img_ref or img_ref.startswith('data:'):
        return img_ref

    try:
        if img_ref.startswith('file:///'):
            local_path = uri_to_local_fs_path(img_ref, path_mappings)
            data = Path(local_path).read_bytes()
        elif img_ref.startswith(('http://', 'https://')):
            headers = _EMBED_HEADERS.copy()
            for domain, referer in _REFERER_MAP.items():
                if domain in img_ref:
                    headers['Referer'] = referer
                    break

            resp = requests.get(img_ref, headers=headers, timeout=15, **proxy_kwargs('image', url=img_ref))
            if resp.status_code != 200:
                logger.warning('封面嵌入失敗 [HTTP %s] %s', resp.status_code, img_ref[:100])
                return img_ref
            if len(resp.content) < _MIN_IMAGE_SIZE:
                logger.warning('封面嵌入失敗 [內容過小 %d bytes] %s', len(resp.content), img_ref[:100])
                return img_ref
            data = resp.content
        else:
            return img_ref

        # MIME: HTTP 時優先用 Content-Type，其他 fallback 副檔名
        mime = 'image/jpeg'
        if img_ref.startswith(('http://', 'https://')):
            ct = resp.headers.get('Content-Type', '')
            if ct.startswith('image/'):
                mime = ct.split(';')[0].strip()
        if mime == 'image/jpeg':
            ext = Path(img_ref.split('?')[0]).suffix.lower()
            mime = _MIME_MAP.get(ext, 'image/jpeg')

        b64 = base64.b64encode(data).decode('ascii')
        return f'data:{mime};base64,{b64}'
    except Exception as e:
        logger.warning('封面嵌入失敗 [%s] %s', type(e).__name__, img_ref[:100])
        return img_ref


class GenerateFromIdsRequest(BaseModel):
    numbers: List[str]
    title: str = "Custom Gallery"
    mode: str = "image"
    sort: str = "date"
    embed_covers: bool = True


_VALID_MODES = {"image", "detail", "text"}
_VALID_SORTS = {"date", "num", "title"}


@router.post("/generate-from-ids", summary="番號列表產生自訂 Gallery HTML")
def generate_from_ids(body: GenerateFromIdsRequest):
    """
    根據番號列表產生自訂 Gallery HTML 頁面。

    - DB 有資料的番號直接組裝；DB 沒有的即時 scrape。
    - 輸出路徑：output/gallery_custom_{timestamp}.html

    回傳：
    ```json
    {
      "success": true,
      "html_path": "/abs/path/to/gallery_custom_20260331_120000.html",
      "video_count": 12,
      "missing": ["FAKE-999"]
    }
    ```
    """
    numbers = [n.strip() for n in body.numbers if isinstance(n, str) and n.strip()]

    if not numbers:
        return JSONResponse(status_code=400, content={"success": False, "error": "numbers 不可為空"})

    if len(numbers) > 100:
        return JSONResponse(status_code=422, content={"success": False, "error": "最多支援 100 筆"})

    if body.mode not in _VALID_MODES:
        return JSONResponse(status_code=422, content={
            "success": False,
            "error": f"mode 必須是 {sorted(_VALID_MODES)} 之一"
        })

    if body.sort not in _VALID_SORTS:
        return JSONResponse(status_code=422, content={
            "success": False,
            "error": f"sort 必須是 {sorted(_VALID_SORTS)} 之一"
        })

    config = load_config()
    gallery_config = config.get('gallery', {})
    output_dir = gallery_config.get('output_dir', '') or ''
    theme = config.get('general', {}).get('theme', 'light')
    proxy_url = config.get('search', {}).get('proxy_url', '')

    # 查 DB
    try:
        db_path = get_db_path()
        repo = VideoRepository(db_path)
        db_results = repo.get_by_numbers(numbers)
    except Exception as e:
        logger.error('generate_from_ids: DB 查詢失敗: %s', e)
        return JSONResponse(status_code=500, content={"success": False, "error": "資料庫查詢失敗"})

    all_videos: List[VideoInfo] = []
    missing: List[str] = []

    for num in numbers:
        db_videos = db_results.get(num)
        if db_videos:
            v = db_videos[0]
            info = VideoInfo(
                path=v.path,
                title=v.title or '',
                originaltitle=v.original_title or '',
                actor=','.join(v.actresses) if v.actresses else '',
                num=v.number or num,
                maker=v.maker or '',
                date=v.release_date or '',
                genre=','.join(v.tags) if v.tags else '',
                size=v.size_bytes or 0,
                mtime=int(v.mtime * 10000000 + 116444736000000000) if v.mtime else 0,
                img=v.cover_path or ''
            )
            all_videos.append(info)
        else:
            # DB miss → 即時 scrape
            try:
                scrape_results = smart_search(num, limit=1, uncensored_mode=is_uncensored_mode_effective(config), proxy_url=proxy_url)
            except Exception as e:
                logger.error('generate_from_ids: scrape %s failed: %s', num, e)
                scrape_results = []

            if scrape_results:
                r = scrape_results[0]
                info = VideoInfo(
                    path='',
                    title=r.get('title', ''),
                    originaltitle=r.get('original_title', ''),
                    actor=','.join(r.get('actors', [])) if isinstance(r.get('actors'), list) else r.get('actors', ''),
                    num=r.get('number', num),
                    maker=r.get('maker', ''),
                    date=r.get('date', ''),
                    genre=','.join(r.get('tags', [])) if isinstance(r.get('tags'), list) else '',
                    size=0,
                    mtime=0,
                    img=r.get('cover', '') or r.get('cover_url', '')
                )
                all_videos.append(info)
            else:
                missing.append(num)

    # 封面嵌入（embed_covers=True 時將 img 轉為 data URI）
    embedded_count = 0
    embed_failed_count = 0
    if body.embed_covers:
        for info in all_videos:
            if info.img:
                original = info.img
                info.img = _embed_cover(info.img, gallery_config.get('path_mappings', {}))
                if info.img.startswith('data:'):
                    embedded_count += 1
                elif original:  # 有原圖但 embed 失敗
                    embed_failed_count += 1

    # 確保輸出目錄存在（空值 → 資料根；相對／絕對值依 resolve_gallery_output_path）
    output_path = resolve_gallery_output_path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    html_filename = f'gallery_custom_{timestamp}.html'
    html_path = output_path / html_filename

    try:
        generator = HTMLGenerator()
        generator.generate(
            all_videos,
            str(html_path),
            title=body.title,
            mode=body.mode,
            sort=body.sort,
            theme=theme,
        )
    except Exception as e:
        logger.error('generate_from_ids: HTML 產生失敗: %s', e)
        return JSONResponse(status_code=500, content={"success": False, "error": "HTML 產生失敗"})

    result = {
        "success": True,
        "html_path": str(html_path),
        "video_count": len(all_videos),
        "missing": missing,
    }
    if body.embed_covers:
        result["embedded_count"] = embedded_count
        result["embed_failed_count"] = embed_failed_count
    return result


def _is_windows() -> bool:
    return os.name == 'nt'


def _path_flavour():
    from pathlib import PurePosixPath, PureWindowsPath
    return PureWindowsPath if _is_windows() else PurePosixPath


def _compute_parent(path: str) -> Optional[str]:
    if not path:
        return None
    flavour = _path_flavour()
    p = flavour(path)
    if p.parent == p:
        return "" if _is_windows() else None
    return str(p.parent)


def _list_windows_drives() -> list[str]:
    try:
        if hasattr(os, "listdrives"):
            return list(os.listdrives())
    except (AttributeError, OSError):
        pass
    import string
    return [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]


def _browse_start_dir(config: dict) -> str:
    gallery_cfg = config.get('gallery') or {}
    sources = iter_gallery_sources(gallery_cfg)
    if sources:
        path_mappings = gallery_cfg.get('path_mappings', {})
        fs = uri_to_local_fs_path(sources[0].path, path_mappings)
        parent = str(Path(fs).parent)
        resolved = safe_realpath(parent, 'browse-dir')
        # isdir 為真還不夠：目錄存在但列不出來（traverse-only 權限、NAS 掛著但權限壞掉）
        # 會讓「第一次開彈窗」直接吃 403，而使用者沒有任何畫面可以導去別處自救。
        # 起點決議不得回 4xx —— 探一次 scandir，列不動就退回平台根。
        if os.path.isdir(resolved):
            try:
                with os.scandir(resolved):
                    pass
                return resolved
            except OSError:
                logger.warning("browse-dir: 起點列舉失敗，退回平台根 path=%s", resolved)
    return "" if _is_windows() else "/"


@router.get("/browse-dir")
def browse_dir(path: Optional[str] = Query(None), expand: Optional[str] = Query(None)):
    config = load_config()
    # path 省略 → 起點決議。空字串在兩個平台語意不同：Windows 的 "" 是虛擬磁碟機清單
    # 節點（從 C:\ 按上一層會走到這裡，必須保留），POSIX 沒有這個節點，"" 等同省略。
    if path is None or (path == "" and not _is_windows()):
        current_path = _browse_start_dir(config)
    else:
        current_path = path

    if current_path == "" and _is_windows():
        drives = _list_windows_drives()
        entries = [{"name": d, "path": d} for d in drives]
        entries.sort(key=lambda e: (e["name"].casefold(), e["name"]))
        result = {
            "current_path": "",
            "parent_path": None,
            "entries": entries,
        }
        if expand == "videos":
            result["files"] = []
        return result

    resolved_path = safe_realpath(current_path, "browse-dir")
    if not os.path.exists(resolved_path):
        return JSONResponse(status_code=404, content={"success": False, "error": "not_found"})
    if not os.path.isdir(resolved_path):
        return JSONResponse(status_code=400, content={"success": False, "error": "not_a_directory"})

    entries = []
    video_files = []
    video_exts = get_video_extensions(config) if expand == "videos" else set()

    try:
        with os.scandir(resolved_path) as it:
            for entry in it:
                try:
                    if entry.is_dir():
                        if is_nas_system_dir_name(entry.name):
                            continue
                        entries.append({"name": entry.name, "path": entry.path})
                    elif expand == "videos" and entry.is_file():
                        ext = os.path.splitext(entry.name)[1].lower()
                        if ext in video_exts:
                            video_files.append(entry.path)
                except OSError:
                    continue
    except (PermissionError, OSError):
        return JSONResponse(status_code=403, content={"success": False, "error": "permission_denied"})

    entries.sort(key=lambda e: (e["name"].casefold(), e["name"]))
    if expand == "videos":
        video_files.sort(key=lambda p: (os.path.basename(p).casefold(), p))

    parent_path = _compute_parent(resolved_path)
    result = {
        "current_path": resolved_path,
        "parent_path": parent_path,
        "entries": entries,
    }
    if expand == "videos":
        result["files"] = video_files
    return result
