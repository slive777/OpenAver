"""
Scanner API 路由 - 影片列表生成

端點：
- GET  /api/gallery/generate              — 掃描資料夾並產生影片列表（SSE 串流）
- GET  /api/gallery/stats                 — 取得 Scanner 統計資訊（影片總數）
- DELETE /api/gallery/cache               — 清除所有影片快取（清空 SQLite）
- GET  /api/gallery/update-check          — 檢查需要補全 NFO 的影片數量
- GET  /api/gallery/update                — 執行 NFO 補全更新（SSE 串流）
- GET  /api/gallery/view                  — 取得產生的 HTML 列表頁面
- GET  /api/gallery/image                 — 代理圖片請求（解決 file:// 限制）
- GET  /api/gallery/video                 — 代理影片請求，支援 Range 請求（影片 seek）
- GET  /api/gallery/player                — 影片播放頁面（HTML5 player）
- GET  /api/gallery/actress-stats         — 查詢指定女優名稱的片數
- GET  /api/gallery/jellyfin-check        — 檢查多少影片缺少 Jellyfin poster/fanart
- GET  /api/gallery/jellyfin-update       — 批次產生 Jellyfin poster + fanart（SSE 串流）
- GET  /api/gallery/missing-check         — 檢查缺少 NFO/封面的影片清單
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
from urllib.parse import unquote, quote
from pathlib import Path
from typing import Any, Dict, Generator, List

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse, HTMLResponse, Response, FileResponse, JSONResponse

from core.gallery_scanner import VideoScanner, fast_scan_directory, VideoInfo, _run_sample_images_cleanup_pass
from core.video_extensions import get_proxy_extensions, get_video_extensions
from core.gallery_generator import HTMLGenerator
from core.path_utils import to_file_uri, is_path_under_dir, uri_to_fs_path, coerce_to_file_uri
from core.nfo_updater import check_cache_needs_update, update_videos_generator
from core.database import VideoRepository, Video, init_db, get_db_path, migrate_json_to_sqlite
from core.organizer import generate_jellyfin_images, HEADERS as _EMBED_HEADERS
from core.config import load_config, iter_gallery_sources, get_gallery_source_paths
from core.readonly_producer import produce_source, resolve_output_root
from core import thumbnail_cache
from core.scraper import smart_search
from core.source_settings import is_uncensored_mode_effective
from pydantic import BaseModel
from core.logger import get_logger
from web.routers.notifications import emit_notification as _emit_notif

logger = get_logger(__name__)

router = APIRouter(prefix="/api/gallery", tags=["gallery"])

# T3(40c): Jellyfin check TTL 快取（60 秒）
_jellyfin_cache_result: dict | None = None
_jellyfin_cache_time: float = 0

# TASK-73: 白名單目錄 dual-form TTL 快取（key: (raw_dir, frozen_mappings), value: (forms, expire_monotonic)）
_dir_forms_cache: dict = {}
_DIR_FORMS_TTL = 60.0  # 秒


def _safe_realpath(fs_path: str, endpoint_label: str) -> str:
    """TASK-73: realpath-or-normpath helper。
    回傳 FS path（str）：realpath 成功則用 realpath 結果，OSError（FUSE/WinFsp）則降級 normpath。
    只回傳 FS path，不回傳 URI；realpath 只跑一次（serving + 白名單比對共用）。
    """
    try:
        return os.path.realpath(fs_path)
    except OSError as e:
        logger.warning(
            "%s: realpath 失敗（FUSE/WinFsp？），降級為 normpath path=%s err=%s",
            endpoint_label, fs_path, e,
        )
        return os.path.normpath(fs_path)


def _dir_candidate_forms(raw_dir: str, path_mappings: dict) -> tuple:
    """TASK-73: 回傳白名單目錄的候選 file:/// URI tuple（1 或 2 個，已 dedup）。
    normpath_form 永遠存在；realpath_form 在 realpath 成功時加入。
    cache-on-success-only：realpath OSError 時不寫快取（避免 NAS 重連後 false-403 窗口）。
    並發安全：dict 賦值原子，無需鎖（冪等計算）。
    """
    cache_key = (raw_dir, frozenset(path_mappings.items()) if path_mappings else frozenset())
    now = time.monotonic()
    cached = _dir_forms_cache.get(cache_key)
    if cached is not None:
        forms, expire = cached
        if now < expire:
            return forms

    # raw_dir 可能是 FS 路徑或 file:/// URI（DirectoryConfig.path schema：「FS 路徑或
    # URI」）。先過 uri_to_fs_path 統一成 FS 路徑（URI→FS，FS→FS 冪等，path-contract
    # 合規，不手刻 startswith('file:///')）。否則對 URI 直接 os.path.normpath/realpath
    # 會把 file:/// 折成 file:/ 再被 to_file_uri 二次包成 file:///file:/…，image/video
    # 兩條白名單同時誤殺（PR#91 P2-D 同源）。FS 輸入行為不變 → 保留 dual-form + TASK-73
    # 跨格式 casefold。
    fs_dir = uri_to_fs_path(raw_dir)
    normpath_form = to_file_uri(os.path.normpath(fs_dir), path_mappings)
    try:
        realpath_form = to_file_uri(os.path.realpath(fs_dir), path_mappings)
        forms = tuple(dict.fromkeys([normpath_form, realpath_form]))
        # cache-on-success-only
        _dir_forms_cache[cache_key] = (forms, now + _DIR_FORMS_TTL)
    except OSError:
        # FUSE/WinFsp: normpath fallback — 不寫快取，確保 NAS 重連後立即重算
        forms = (normpath_form,)
    return forms


def _image_whitelist_dirs(config: dict) -> List[str]:
    """TASK-88c-T1 / TASK-89a-T2: /api/gallery/image 白名單的候選 raw 目錄清單。

    每個來源 emit `src.path`，並在 `resolve_output_root(src, config)`（CD-89a-7）
    非空時一併 emit——off 風味回傳固定 `output/lib/<name>` 根（讓唯讀 + off 風味
    生成的封面/劇照能經 image proxy 服務，Codex #1 回歸鎖：只改 producer 不改
    白名單會讓 off 封面 404）；jellyfin/emby/kodi 沿用 `source.output_path` 原值。

    純函式、無 IO（`resolve_output_root` 本身無 IO）。空字串仍被過濾——不讓空
    字串進 `_dir_candidate_forms`（避免 `to_file_uri('') = 'file:///'` 根路徑
    把整顆磁碟放進白名單，CWE-allowlist bypass）。get_video 不共用此 helper
    （獨立 call site，spec P1a）。
    """
    gallery_config = config.get('gallery', {})
    dirs: List[str] = []
    for src in iter_gallery_sources(gallery_config):
        dirs.append(src.path)
        resolved = resolve_output_root(src, config)
        if resolved:
            dirs.append(resolved)
    return dirs


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


def _run_readonly_source(src, config, repo, proxy_url, summary, reachable: bool = True) -> Generator[str, None, None]:
    """在 daemon worker thread 跑 produce_source，drain 無界 queue 逐片 yield SSE。

    worker 例外（含 produce_source 迴圈前的 normalize/列檔/DB 拋錯，未被 producer
    內 try 包覆）顯式接手（CD-88c-1 / Codex P1），不靜默吞：box['error'] → 產生器
    emit error SSE + source_errors+1 + 續下一來源。
    """
    q: "queue.Queue" = queue.Queue()  # 無界：worker 永不阻塞於 put，client 斷線 daemon 自然退出
    _SENTINEL = object()
    box: dict = {}

    def _work():
        try:
            box['result'] = produce_source(
                src, config, repo, proxy_url=proxy_url,
                on_progress=q.put,
                should_abort=None,
                reachable=reachable,
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


def generate_avlist() -> Generator[str, None, None]:
    """產生影片列表（SSE 串流）- 使用 SQLite 儲存"""

    try:
        # 載入設定
        config = load_config()
        gallery_config = config.get('gallery', {})

        directories = get_gallery_source_paths(gallery_config)
        output_dir = gallery_config.get('output_dir', 'output')
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

        # 確保輸出目錄存在
        project_root = Path(__file__).parent.parent.parent
        output_path = project_root / output_dir
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
        scanner = VideoScanner(path_mappings=path_mappings)

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
            directory = src.path
            logger.info(f"[Gallery] 掃描: {directory}")

            # TASK-88c-T2: readonly 來源分流（早於 normalize，UNC 主場景不被擋）
            if src.readonly:
                # TASK-89b-T5 / CD-89b-5: 可達性防呆補在 readonly 分流點（:366 的
                # os.path.exists 只在非 readonly 分支執行，readonly 分支需要等義入口
                # 檢查）。src.path 是 config 原始輸入，不套 reverse_path_mapping
                # （比照 :353/:96 既定作法，見 TASK-89b-T5 現況分析 #5）。
                reachable = os.path.exists(uri_to_fs_path(src.path))
                yield from _run_readonly_source(src, config, repo, proxy_url, readonly_summary, reachable)
                continue

            # 轉換路徑格式 (Windows -> WSL)。directory 可能是 FS 路徑或 file:/// URI
            # （DirectoryConfig.path schema）。uri_to_fs_path 對 URI→FS、FS→FS 皆冪等，
            # 取代裸 normalize_path（後者對 URI 原樣通過 → os.path.exists 失敗 → 誤報
            # 「資料夾不存在」，非 readonly 的 URI 來源掃不到）。
            try:
                normalized_dir = uri_to_fs_path(directory)
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

            if not os.path.exists(normalized_dir):
                yield _sse_event({"type": "log", "level": "warn", "message": f"資料夾不存在: {directory}"})
                continue

            try:
                # 快速掃描取得檔案列表
                min_size_bytes = min_size_mb * 1024 * 1024
                video_extensions = get_video_extensions(config)
                # a5 Codex fix: 收集因 OSError/PermissionError 被跳過的路徑
                # （含 Windows 長路徑觸發的 OSError — 這些 entry 根本不會進 all_files）
                skipped_paths: list[str] = []
                all_files = fast_scan_directory(
                    normalized_dir,
                    video_extensions,
                    min_size_bytes,
                    on_skip=lambda p, _e: skipped_paths.append(p),  # noqa: B023 — skipped_paths consumed synchronously within same iteration, not deferred
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
                    elif db_entry[0] != file_info['mtime'] or db_entry[1] != file_info.get('nfo_mtime', 0):
                        # mtime 或 nfo_mtime 變更
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
                        "message": f"  {directory}: {len(skipped_paths)} 個路徑讀取失敗，跳過刪除偵測以免誤刪（詳見 debug.log）"
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

        # 建立「當前設定資料夾」URI 集合，用於過濾 DB 記錄
        # DB 保留所有歷史資料當 cache，但只輸出當前設定的資料夾
        configured_dir_uris = set()
        for p in get_gallery_source_paths(gallery_config):
            try:
                # coerce_to_file_uri：來源 path 可能已是 file:/// URI（含 readonly 剛
                # upsert 的列），已是 URI 就原樣回、FS 才轉，避免 to_file_uri 二次包成
                # file:///file:/// 把 readonly 生成的列全數過濾掉（PR#91 P2-D）。
                configured_dir_uris.add(coerce_to_file_uri(p, path_mappings))
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
                    "paths": session_stats['paths']
                }
                if session_update['count'] > 0:
                    yield _sse_event({
                        "type": "log",
                        "level": "warn",
                        "message": f"發現 {session_update['count']} 部新增影片資訊不全"
                    })

        yield _sse_event({"type": "log", "level": "info", "message": f"資料庫總筆數: {repo.count()}"})

        # §b1 AC#2: sample_images 孤兒清理 pass（Scanner UI 主路徑覆蓋，共用 helper）
        try:
            cleaned = _run_sample_images_cleanup_pass(repo)
            if cleaned > 0:
                yield _sse_event({"type": "log", "level": "info", "message": f"清除 {cleaned} 筆孤兒劇照記錄"})
        except Exception as e:
            logger.warning("sample_images cleanup pass failed: %s: %s", type(e).__name__, e)
            # 失敗不中斷 scan 流程

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


@router.get("/generate")
async def generate():
    """產生影片列表（SSE 串流回傳進度）"""
    return StreamingResponse(
        generate_avlist(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


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


@router.get("/update-check")
def check_update():
    """檢查需要更新的影片數量（從 SQLite 讀取）"""
    try:
        db_path = get_db_path()

        if not db_path.exists():
            return {"success": True, "data": {"need_update": 0}}

        repo = VideoRepository(db_path)
        all_videos = repo.get_all()

        # 建構相容 check_cache_needs_update 的格式
        cache = {}
        for v in all_videos:
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
            elif not has_nfo:
                missing_nfo += 1
            else:
                missing_cover += 1
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

        # 建構相容 check_cache_needs_update 的格式
        cache = {}
        for v in all_videos:
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

        # 執行更新
        for msg in update_videos_generator(cache, paths_to_update):
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
        output_dir = gallery_config.get('output_dir', 'output')
        output_filename = gallery_config.get('output_filename', 'gallery_output.html')

        project_root = Path(__file__).parent.parent.parent
        html_path = project_root / output_dir / output_filename

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


@router.get("/image")
def get_image(path: str = Query(..., description="圖片路徑")):
    """代理圖片請求，解決 file:// 在 iframe 中無法載入的問題"""
    from urllib.parse import unquote
    from core.path_utils import normalize_path

    # URL decode
    path = unquote(path)

    # 使用 path_utils 統一處理路徑轉換
    try:
        local_path = normalize_path(path)
    except ValueError:
        local_path = path  # 無法轉換時使用原路徑

    # 1. 解析 .. 並追蹤 symlink target（realpath）；FUSE/WinFsp OSError 時降級 normpath
    local_path = _safe_realpath(local_path, "get_image")

    # 2. 副檔名白名單（只允許圖片格式）
    ext = os.path.splitext(local_path)[1].lower()
    mime_types = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.webp': 'image/webp',
        '.bmp': 'image/bmp',
    }
    if ext not in mime_types:
        logger.warning("get_image: 拒絕非圖片副檔名請求 ext=%s", ext)
        return Response(status_code=403, content="不允許的檔案類型")

    # 3. 目錄白名單：只允許 gallery.directories 底下的檔案
    config = load_config()
    gallery_config = config.get('gallery', {})
    path_mappings = gallery_config.get('path_mappings', {})

    # TASK-73: 兩端對稱正規化 — request_uri 用 single-form（realpath已做）；
    # dir 端用 dual-form（normpath + realpath 候選），避免 SMB mapped drive 格式不同 403 誤殺
    request_uri = to_file_uri(local_path, path_mappings)
    # TASK-88c-T1: 白名單納入各來源非空 output_path（唯讀 off 風味封面服務）；
    # 複用 _dir_candidate_forms dual-form，不另寫 single-form 比對
    allowed = any(
        is_path_under_dir(request_uri, form)
        for p in _image_whitelist_dirs(config)
        for form in _dir_candidate_forms(p, path_mappings)
    )
    if not allowed:
        logger.warning("get_image: 拒絕白名單外路徑請求 uri=%s", request_uri)
        return Response(status_code=403, content="路徑不在允許的資料夾範圍內")

    # 4. 檔案存在性
    if not os.path.exists(local_path):
        return Response(status_code=404, content="檔案不存在")

    media_type = mime_types[ext]
    return FileResponse(
        local_path,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )


# ── feature/71 T3: 縮圖快取端點 ────────────────────────────────────────────────
# prewarm 單例鎖（背景 daemon thread，fire-and-forget；sync def → 無 event loop）
_prewarm_lock = threading.Lock()
_prewarming = False

# fallback 原圖用副檔名 → mime（thumb 端點不抄 get_image 的安全鏈，用 DB 背書）
_THUMB_FALLBACK_MIME = {
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
    '.bmp': 'image/bmp',
}


def _serve_thumb_file(tf: Path, request: Request) -> Response:
    """serve 一個已存在的 thumb webp：強 ETag + no-cache + If-None-Match → 304。

    本地一次 stat（零 DB / 零 NAS）。CD-4 明令不可用 max-age。

    Codex P2(b)：200 路徑改 read_bytes() 在 handler try 內把整檔讀進記憶體，**不再用
    FileResponse**。FileResponse 會把 stat/open 延到 ASGI send 階段（在 handler try 外），
    若此時 thumb 被並發 invalidate(unlink)，Starlette 內部 stat 失敗會冒成 500。
    在此同步讀 bytes → send 階段已不碰磁碟；read 期間的並發 unlink 會在這裡拋 OSError，
    由呼叫端 get_thumb 既有的 try/except OSError 接住降級 miss 重生（與 M1 一致）。
    """
    etag = f'"{tf.stat().st_mtime_ns}"'
    if request.headers.get("If-None-Match") == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": "no-cache"})
    data = tf.read_bytes()  # 並發 unlink → OSError 上拋給 get_thumb 降級重生
    return Response(
        content=data,
        media_type="image/webp",
        headers={"Cache-Control": "no-cache", "ETag": etag},
    )


@router.get("/thumb")
def get_thumb(request: Request, path: str = Query(..., description="影片路徑 URI")):
    """縮圖 serve（feature/71 T3）：hit 零 DB/NAS、miss 生成、失敗 fallback 原圖。

    sync def → 跑在 Starlette threadpool worker thread。

    P2-A（TASK-71c）：不呼叫 unquote(path)。FastAPI 已自動 decode query string 一次；
    再 unquote 造成 double-decode → 檔名含字面 % 的影片 key 失配 → 404。
    get_image / get_video 的 unquote 是 pre-existing 不同建構鏈，留作 follow-up。
    """
    tf = thumbnail_cache.thumb_file_for(path)

    # hit：零 DB、零 NAS（只一次本地 stat）— 驗收 4.A 核心
    # feature/71 T8 M1（+ Codex P2(b)）：hit 判定（tf.exists()）通過後、_serve_thumb_file
    # 內讀 thumb（stat / read_bytes）期間，thumb 可能被並發 invalidate(unlink) → 拋 OSError
    # （含 FileNotFoundError）。整個 serve 在此 try 內把 bytes 讀完（send 時不再碰磁碟），
    # 拋出時降級 fall through 到下方 miss 重生路徑（DB 有 cover → 重生；無 → 404），不 500。
    if tf.exists():
        try:
            return _serve_thumb_file(tf, request)
        except OSError as e:
            logger.warning("thumb hit 後並發失效，降級重生: path=%s err=%s", path, e)

    # miss：DB 背書取 cover
    db_path = get_db_path()
    if not db_path.exists():
        return Response(status_code=404, content="無快取")

    repo = VideoRepository(db_path)
    video = repo.get_by_path(path)
    if video is None or not video.cover_path:
        return Response(status_code=404, content="無封面")

    # 路徑轉換一步（不疊 normalize_path）；DB 背書取代 realpath 安全鏈
    cover_fs = uri_to_fs_path(video.cover_path)
    if not repo.is_known_cover_path(cover_fs):
        return Response(status_code=404, content="封面不在快取記錄中")

    # P2-B（TASK-71c）：miss 路徑 gate disabled，不重生 WebP。
    # 用戶關閉快取 + clear 後，stale 分頁的 miss 請求不應重建剛清的目錄。
    # disabled → fall through 到下方 fallback 原圖（D6 不破圖）。
    # load_config() 無 lru_cache，每次讀 disk（與 _prewarm_worker:945 同 pattern）。
    # hit 路徑（tf.exists() → _serve_thumb_file）不 gate：已存在直接 serve 是 harmless。
    if not load_config().get("thumbnail_cache_enabled", False):
        # disabled：跳過 generate，fall through 到 fallback 原圖
        pass
    elif thumbnail_cache.generate(cover_fs, tf):
        # Codex P1（round-1 + round-2）：generate 用的 cover_fs 是 miss 進來時的 DB 值。
        # 生成期間若 enrich/rescrape 並發換封面，剛寫的 thumb 可能是 stale。re-read DB 一次
        # （miss 路徑本就碰本地 DB，不違反 D4「serve hit 不碰 NAS」）：
        #   - fresh is None / cover_path 空（並發刪除）→ stale，invalidate 丟棄剛寫 thumb + 404，
        #     不 serve 剛生成的 stale thumb（round-2 P1 補強）。
        #   - cover_path 換了不同 path → invalidate 丟棄 + 把 cover_fs 重指當前封面，
        #     fall through 到下方 P2(a)-guarded fallback serve 當前封面（下次 view lazy 重生）。
        #   - 同路徑原地覆寫競態 → 已由 core per-thumb 鎖（修法 A）關閉，web 不再 stat 比對，
        #     直接 safe-serve（OSError → fall through 重指/fallback，round-2 P2）。
        fresh = repo.get_by_path(path)
        if not fresh or not fresh.cover_path:
            thumbnail_cache.invalidate(path)
            return Response(status_code=404, content="影片已不存在")
        fresh_fs = uri_to_fs_path(fresh.cover_path)
        if fresh_fs != cover_fs:
            thumbnail_cache.invalidate(path)
            cover_fs = fresh_fs
            # fall through 到 fallback：serve 當前封面（cover_fs 已重指）
        else:
            # 同路徑：原地覆寫競態已由 core per-thumb 鎖關閉 → 集中 safe-serve。
            # generate 後 thumb 被並發刪（DB row 刪除 + invalidate）→ OSError，fall through
            # 到 fallback（round-2 P2：此 serve 過去在 try 外，會冒成 500）。
            try:
                return _serve_thumb_file(tf, request)
            except OSError as e:
                logger.warning("thumb miss→generate 後並發失效，降級 fallback: path=%s err=%s", path, e)

    # generate 失敗 → fallback 原圖（D6 不破圖；非 404）
    # Codex P2(a)：fallback 前先確認 cover 原圖存在；不存在（並發刪/搬移）→ 回 404，
    # 讓前端破圖三態接手，而非讓 FileResponse 在 send 階段 stat 失敗冒成 500。
    if not os.path.isfile(cover_fs):
        return Response(status_code=404, content="封面檔不存在")
    ext = os.path.splitext(cover_fs)[1].lower()
    media_type = _THUMB_FALLBACK_MIME.get(ext, "application/octet-stream")
    return FileResponse(
        cover_fs,
        media_type=media_type,
        headers={"Cache-Control": "no-cache"},
    )


def _prewarm_worker():
    """背景預熱 daemon thread：對 DB 全部影片補缺縮圖。

    自包 try/except（不冒泡 → 沒包就靜默死 + flag 卡死）+ finally 清 flag。
    絕不碰 event loop（sync thread 無 running loop）。notification center 跨 thread 安全。
    """
    global _prewarming
    try:
        _emit_notif("info", "notif.thumb_prewarm_start", task_type="thumb_prewarm")
        db_path = get_db_path()
        if not db_path.exists():
            return
        repo = VideoRepository(db_path)
        n = 0
        stopped_disabled = False  # Codex P3：被 disable 中止時跳過 done 通知
        # round-3 P2：snapshot（iter_missing 吃 repo.get_all()）取得後，用戶可能按
        # 「清除所有影片快取」→ clear_cache 跑 repo.clear_all()（清空 DB）+
        # thumbnail_cache.clear_all()（rmtree thumb 目錄）；單筆刪除 / prune 亦同理。
        # clear_all 只是 rmtree，不 fence 後續生成，故 worker 從 stale snapshot 繼續
        # generate 會在已清空目錄重建 orphan webp（DB 空 thumb 在）。
        # surgical fence：逐項用「同一個 repo」re-check get_by_path（reuse，不每筆新建），
        # 只跳過/清理被移除的那部，存活影片照常完成預熱（不像 generation token 會 abort
        # 整個 prewarm，也不需 clear_cache cancel/join 背景 thread 卡住同步請求）。
        # round-4 P2：snapshot 的 cover 只用來「列出待補項」，不用於 generate。enrich /
        # rescrape 可能在 snapshot 後換封面（video 還在但 cover_path 變），故一律從
        # fresh DB 讀「當前」cover 生成（與 get_thumb miss 路徑對稱：fresh re-read +
        # path-change 偵測）；before/after re-check 收 video 消失 / 無 cover / cover 換掉
        # 三種期間變動（≤1 generate-期間-變動窗口，與 get_thumb 同級）。
        for video_uri, _stale_cover_fs in thumbnail_cache.iter_missing(repo.get_all()):
            # Codex P2 race：用戶可在 prewarm 進行中關閉快取（toggle false → save →
            # clear）。worker 每筆重讀 load_config()（無 lru_cache，每次讀 disk）拿前端
            # 剛 PUT 的 false → 立即 break，不再 generate 後續 item（否則在 clear 已
            # rmtree 的目錄重建 orphan webp）。before-check：關閉即停。
            if not load_config().get("thumbnail_cache_enabled", False):
                stopped_disabled = True
                break
            # before-check：影片已從 DB 移除（clear / prune / 單筆刪除）或無 cover → 不生成孤兒
            fresh = repo.get_by_path(video_uri)
            if fresh is None or not fresh.cover_path:
                continue
            cover_fs = uri_to_fs_path(fresh.cover_path)  # 用當前 cover，忽略 stale snapshot
            ok = thumbnail_cache.generate(cover_fs, thumbnail_cache.thumb_file_for(video_uri))
            # after-check：generate 期間影片被清 / cover 又換 / 快取被關閉（≤1 窗口）→
            # 丟棄剛寫的 stale thumb。disabled_after：再讀一次 load_config，若快取已關閉
            # → invalidate 剛生成的 webp + break（關掉 generate-in-flight 的最後殘留窗口）。
            # 正確性依賴前端契約「先 save(false) 才 clear」（config.json 寫 false 早於
            # clear fetch）；若未來改成「先清才存」會破此假設。
            disabled_after = not load_config().get("thumbnail_cache_enabled", False)
            after = repo.get_by_path(video_uri)
            # disabled-after 拉到 ok 判斷外（Codex P3-2）：generate 期間被關閉時，無論這筆
            # 成功或失敗都要停止且不送 done 通知。成功才需 invalidate（清剛寫的殘留 thumb）；
            # 失敗無 thumb 可清。否則「最後一筆 generate 失敗 + 同時關閉」會漏 break → 誤送 done。
            if disabled_after:
                if ok:
                    thumbnail_cache.invalidate(video_uri)
                stopped_disabled = True
                break
            # 既有孤兒處理：generate 成功但影片消失 / 無 cover / cover 換掉 → 丟棄 stale thumb
            if ok and (after is None or not after.cover_path
                       or uri_to_fs_path(after.cover_path) != cover_fs):
                thumbnail_cache.invalidate(video_uri)
                continue
            if ok:
                n += 1
        # Codex P3：若被 disable 中止（用戶「關閉並清除」），跳過「完成 N 張」通知——那些
        # 縮圖已被 clear 刪除 / invalidate，顯示完成數會誤導且與「關閉並清除」UX 打架。
        # disable 流程自身有確認 modal + saveConfig 回饋，無需 done 通知。
        if not stopped_disabled:
            _emit_notif("success", "notif.thumb_prewarm_done",
                        message=f"{n} 張", task_type="thumb_prewarm")
    except Exception:
        logger.exception("縮圖預熱背景任務失敗")
    finally:
        with _prewarm_lock:
            _prewarming = False


@router.post("/thumb/prewarm")
def thumb_prewarm():
    """背景預熱縮圖快取（feature/71 T3）：後端自 gate + 單例鎖，fire-and-forget。

    sync def。前端兩觸發點（toggle-on / scan-done）可無條件 POST，由此 gate。
    """
    global _prewarming
    config = load_config()
    if not config.get("thumbnail_cache_enabled", False):
        return {"status": "disabled"}

    with _prewarm_lock:
        if _prewarming:
            return {"status": "already_running"}
        _prewarming = True

    threading.Thread(target=_prewarm_worker, daemon=True).start()
    return {"status": "started"}


@router.post("/thumb/clear")
def thumb_clear():
    """DB-safe 清空封面縮圖快取（feature/71b T2）。

    僅 rmtree output/thumb/（CD-71b-3）——**絕不碰 videos DB**。前端在
    「關閉縮圖快取 toggle 且存檔成功」後才 fire-and-forget POST 此端點（先存才清）。
    冪等：clear_all() 對缺目錄 no-op。sync def → Starlette threadpool。
    """
    thumbnail_cache.clear_all()
    return {"cleared": True}


@router.get("/video")
def get_video(request: Request, path: str = Query(..., description="影片路徑（file:/// URI 或 FS 路徑）")):
    """代理影片請求，解決瀏覽器無法開啟 file:/// URI 的問題"""
    # URL decode
    path = unquote(path)

    # 1. 轉換為 FS 路徑
    local_path = uri_to_fs_path(path)

    # 2. 解析 .. 並追蹤 symlink target（realpath）；FUSE/WinFsp OSError 時降級 normpath
    local_path = _safe_realpath(local_path, "get_video")

    # 3. 副檔名白名單（用 realpath/normpath 解析後的路徑）
    #    使用 get_proxy_extensions() = user config ∩ SAFE_PROXY_EXTENSIONS
    config = load_config()
    allowed_extensions = get_proxy_extensions(config)
    ext = os.path.splitext(local_path)[1].lower()
    if ext not in allowed_extensions:
        logger.warning("get_video: 拒絕非影片副檔名請求 ext=%s", ext)
        return Response(status_code=403, content="不允許的檔案類型")

    # 4. 目錄白名單：只允許 gallery.directories 底下的檔案
    gallery_config = config.get('gallery', {})
    path_mappings = gallery_config.get('path_mappings', {})

    # TASK-73: 兩端對稱正規化 — request_uri 用 single-form（realpath已做）；
    # dir 端用 dual-form（normpath + realpath 候選），避免 SMB mapped drive 格式不同 403 誤殺
    request_uri = to_file_uri(local_path, path_mappings)
    allowed = any(
        is_path_under_dir(request_uri, form)
        for p in get_gallery_source_paths(gallery_config)
        for form in _dir_candidate_forms(p, path_mappings)
    )
    if not allowed:
        logger.warning("get_video: 拒絕白名單外路徑請求 uri=%s", request_uri)
        return Response(status_code=403, content="路徑不在允許的資料夾範圍內")

    # 5. 檔案存在性
    if not os.path.exists(local_path):
        return Response(status_code=404, content="檔案不存在")

    # 6. MIME 類型映射
    video_mime = {
        '.mp4': 'video/mp4', '.mkv': 'video/x-matroska',
        '.avi': 'video/x-msvideo', '.wmv': 'video/x-ms-wmv',
        '.mov': 'video/quicktime', '.flv': 'video/x-flv',
        '.webm': 'video/webm', '.m4v': 'video/x-m4v',
        '.ts': 'video/mp2t', '.m2ts': 'video/mp2t',
        '.mpg': 'video/mpeg', '.mpeg': 'video/mpeg',
    }
    media_type = video_mime.get(ext, 'application/octet-stream')

    # 7. Range request 支援（影片 seek 必要）
    file_size = os.path.getsize(local_path)
    range_header = request.headers.get("range")

    if range_header:
        import re
        range_match = re.match(r'bytes=(\d+)-(\d*)', range_header)
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2)) if range_match.group(2) else file_size - 1
            end = min(end, file_size - 1)

            # 無效 Range：start 超出檔案大小或 start > end
            if start >= file_size or start > end:
                return Response(
                    status_code=416,
                    headers={"Content-Range": f"bytes */{file_size}"},
                )

            chunk_size = end - start + 1

            def iter_file():
                with open(local_path, 'rb') as f:
                    f.seek(start)
                    remaining = chunk_size
                    while remaining > 0:
                        read_size = min(remaining, 65536)
                        data = f.read(read_size)
                        if not data:
                            break
                        remaining -= len(data)
                        yield data

            return StreamingResponse(
                iter_file(),
                status_code=206,
                media_type=media_type,
                headers={
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Accept-Ranges": "bytes",
                    "Content-Length": str(chunk_size),
                    "Content-Disposition": "inline",
                },
            )

    # 無 Range：完整回傳
    return FileResponse(
        local_path, media_type=media_type,
        headers={
            "Content-Disposition": "inline",
            "Accept-Ranges": "bytes",
        },
    )


@router.get("/player")
async def video_player(path: str = Query(..., description="影片路徑（file:/// URI 或 FS 路徑）")):
    """影片播放頁面 — 用 HTML5 <video> 標籤在新分頁播放"""
    from html import escape as html_escape
    video_url = f"/api/gallery/video?path={quote(path, safe='')}"

    # 從路徑取檔名作為標題（escape 防 XSS）
    filename = path.rsplit('/', 1)[-1].rsplit('\\', 1)[-1]
    if filename.startswith('file:'):
        filename = 'Video Player'
    filename = html_escape(filename)

    # video_url 也做 HTML escape（防禦性，避免 src 屬性注入）
    video_url_safe = html_escape(video_url)

    html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <title>{filename} - OpenAver</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ background: #000; display: flex; align-items: center; justify-content: center; height: 100vh; }}
        video {{ max-width: 100%; max-height: 100vh; }}
    </style>
</head>
<body>
    <video controls autoplay src="{video_url_safe}"></video>
</body>
</html>"""
    return HTMLResponse(content=html)


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

def _cover_base_stem(cover_fs: str) -> str:
    """從封面路徑取得 base stem，移除 -poster / -fanart 後綴避免重複"""
    stem = os.path.splitext(cover_fs)[0]
    for suffix in ('-poster', '-fanart'):
        if stem.endswith(suffix):
            stem = stem[:-len(suffix)]
            break
    return stem


def check_jellyfin_images_needed(repo: VideoRepository) -> dict:
    """檢查 DB 中有多少影片缺少 poster/fanart"""
    videos = repo.get_all()
    need_update = []
    for v in videos:
        if not v.cover_path:
            continue
        cover_fs = uri_to_fs_path(v.cover_path)
        if not os.path.exists(cover_fs):
            continue
        base_stem = _cover_base_stem(cover_fs)
        poster = base_stem + '-poster.jpg'
        fanart = base_stem + '-fanart.jpg'
        if not os.path.exists(poster) or not os.path.exists(fanart):
            need_update.append({
                'cover_path': cover_fs,
                'base_stem': base_stem,
                'number': v.number or '',
            })
    return {'need_update': len(need_update), 'items': need_update}


def generate_jellyfin_images_stream() -> Generator[str, None, None]:
    """SSE 串流：批次為影片產生 poster + fanart"""
    global _jellyfin_cache_result, _jellyfin_cache_time

    try:
        db_path = get_db_path()

        if not db_path.exists():
            yield _sse_event({"type": "error", "message": "資料庫不存在，請先產生列表"})
            return

        repo = VideoRepository(db_path)
        result = check_jellyfin_images_needed(repo)
        items = result['items']
        total = len(items)

        if total == 0:
            _jellyfin_cache_result = None
            _jellyfin_cache_time = 0
            yield _sse_event({"type": "done", "message": "沒有需要補齊的影片", "updated": 0})
            return

        yield _sse_event({"type": "log", "level": "info", "message": f"需補齊 {total} 部影片的圖片..."})

        for i, item in enumerate(items, 1):
            cover = item['cover_path']
            num = item['number']
            stem = item['base_stem']

            yield _sse_event({
                "type": "progress",
                "current": i,
                "total": total,
                "status": f"處理 {num}"
            })

            img_result = generate_jellyfin_images(cover, stem)

            if not img_result['fanart']:
                yield _sse_event({"type": "log", "level": "warn", "message": f"{num} fanart 複製失敗"})

            if img_result['poster']:
                yield _sse_event({"type": "log", "level": "info", "message": f"✓ {num} poster + fanart"})
            else:
                yield _sse_event({"type": "log", "level": "warn", "message": f"{num} poster 裁切失敗"})

        # T3(40c): 清空快取，讓下次 check 反映最新圖片狀態
        _jellyfin_cache_result = None
        _jellyfin_cache_time = 0
        yield _sse_event({"type": "done", "message": f"完成！已補齊 {total} 部影片的圖片"})

    except Exception as e:
        logger.error("產生 Jellyfin 圖片失敗: %s", e)
        yield _sse_event({"type": "error", "message": "產生圖片失敗"})


def _check_jellyfin_needed() -> dict | None:
    """Threadpool helper: get_db_path + check DB existence + open repo + run jellyfin check.

    Returns None if DB does not exist (caller handles as need_update=0 early return).
    Returns the result dict from check_jellyfin_images_needed otherwise.
    """
    db_path = get_db_path()
    if not db_path.exists():
        return None
    repo = VideoRepository(db_path)
    return check_jellyfin_images_needed(repo)


@router.get("/jellyfin-check")
async def jellyfin_image_check():
    """檢查多少影片需要補齊 Jellyfin 圖片"""
    global _jellyfin_cache_result, _jellyfin_cache_time
    try:
        # T3(40c): TTL 快取命中（純記憶體，命中時 zero-threadpool）
        # T4b(66): get_db_path（含 mkdir）+ db_path.exists() + repo 全併入
        # _check_jellyfin_needed helper 移出 loop，故 DB 偵測現在排在 TTL 快取之後。
        # 副作用：DB 在 60s TTL 窗內被刪除時，warm cache 會回舊值而非 0
        # （pathological，無 workflow 觸發）；屬刻意取捨。
        if _jellyfin_cache_result is not None and time.time() - _jellyfin_cache_time < 60:
            return {"success": True, "data": {"need_update": _jellyfin_cache_result['need_update']}}

        result = await asyncio.to_thread(_check_jellyfin_needed)

        if result is None:
            return {"success": True, "data": {"need_update": 0}}

        # T3(40c): 更新快取
        _jellyfin_cache_result = result
        _jellyfin_cache_time = time.time()

        return {"success": True, "data": {"need_update": result['need_update']}}
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


def _embed_cover(img_ref: str) -> str:
    """將圖片 URL/路徑轉為 data URI。失敗時回傳原值。"""
    if not img_ref or img_ref.startswith('data:'):
        return img_ref

    try:
        if img_ref.startswith('file:///'):
            local_path = uri_to_fs_path(img_ref)
            data = Path(local_path).read_bytes()
        elif img_ref.startswith(('http://', 'https://')):
            headers = _EMBED_HEADERS.copy()
            for domain, referer in _REFERER_MAP.items():
                if domain in img_ref:
                    headers['Referer'] = referer
                    break

            resp = requests.get(img_ref, headers=headers, timeout=15)
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
    output_dir = gallery_config.get('output_dir', 'output')
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
                info.img = _embed_cover(info.img)
                if info.img.startswith('data:'):
                    embedded_count += 1
                elif original:  # 有原圖但 embed 失敗
                    embed_failed_count += 1

    # 確保輸出目錄存在
    project_root = Path(__file__).parent.parent.parent
    output_path = project_root / output_dir
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
