"""
AVList API 路由 - 影片列表生成
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Generator

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse, HTMLResponse, Response, FileResponse

# 加入 core 模組路徑
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.gallery_scanner import VideoScanner, load_cache, save_cache, fast_scan_directory, VIDEO_EXTENSIONS, VideoInfo
from core.gallery_generator import HTMLGenerator
from core.path_utils import normalize_path, to_file_uri
from core.nfo_updater import check_cache_needs_update, update_videos_generator, apply_actress_aliases_generator
from core.database import VideoRepository, Video, init_db, get_db_path, migrate_json_to_sqlite, ActressAliasRepository
from web.routers.config import load_config
from pydantic import BaseModel
from core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/gallery", tags=["gallery"])


def generate_avlist() -> Generator[str, None, None]:
    """產生影片列表（SSE 串流）- 使用 SQLite 儲存"""

    def send(data: dict):
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    try:
        # 載入設定
        config = load_config()
        gallery_config = config.get('gallery', {})

        directories = gallery_config.get('directories', [])
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
            yield send({"type": "error", "message": "未設定掃描資料夾"})
            return

        logger.info(f"[Gallery] 開始生成，目錄數: {len(directories)}")

        # 確保輸出目錄存在
        project_root = Path(__file__).parent.parent.parent
        output_path = project_root / output_dir
        output_path.mkdir(parents=True, exist_ok=True)

        html_path = output_path / output_filename
        cache_path = output_path / output_filename.replace('.html', '_cache.json')
        db_path = get_db_path()

        yield send({"type": "log", "level": "info", "message": f"輸出路徑: {html_path}"})

        # 檢查是否需要遷移 JSON cache 到 SQLite
        if cache_path.exists() and not db_path.exists():
            yield send({"type": "log", "level": "info", "message": "遷移 JSON cache 到 SQLite..."})
            migrate_result = migrate_json_to_sqlite(cache_path, db_path, delete_on_success=True)
            yield send({"type": "log", "level": "info", "message": f"遷移完成: {migrate_result['migrated']} 筆"})

        # 初始化資料庫
        init_db(db_path)
        repo = VideoRepository(db_path)

        yield send({"type": "log", "level": "info", "message": f"資料庫筆數: {repo.count()}"})

        # 初始化掃描器
        scanner = VideoScanner(path_mappings=path_mappings)

        total_dirs = len(directories)
        total_inserted = 0
        total_updated = 0
        total_deleted = 0
        session_added_paths = []  # 追蹤本次新增/變更的影片路徑

        for idx, directory in enumerate(directories, 1):
            logger.info(f"[Gallery] 掃描: {directory}")

            # 轉換路徑格式 (Windows -> WSL)
            try:
                normalized_dir = normalize_path(directory)
            except ValueError as e:
                yield send({"type": "log", "level": "warn", "message": f"路徑轉換失敗: {e}"})
                continue

            yield send({
                "type": "progress",
                "status": f"掃描: {directory}",
                "current": idx,
                "total": total_dirs + 1  # +1 for generating
            })

            if not os.path.exists(normalized_dir):
                yield send({"type": "log", "level": "warn", "message": f"資料夾不存在: {directory}"})
                continue

            try:
                # 快速掃描取得檔案列表
                min_size_bytes = min_size_mb * 1024 * 1024
                all_files = fast_scan_directory(normalized_dir, VIDEO_EXTENSIONS, min_size_bytes)

                if not all_files:
                    yield send({"type": "log", "level": "info", "message": f"{directory}: 沒有影片檔案"})
                    continue

                yield send({"type": "log", "level": "info", "message": f"{directory}: 找到 {len(all_files)} 個檔案"})

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
                normalized_dir_uri = to_file_uri(normalized_dir, path_mappings)
                deleted_paths = [p for p in db_index.keys() if p.startswith(normalized_dir_uri) and p not in current_paths]
                if deleted_paths:
                    deleted_count = repo.delete_by_paths(deleted_paths)
                    total_deleted += deleted_count
                    yield send({"type": "log", "level": "info", "message": f"  清理 {deleted_count} 個已刪除檔案"})

                # 掃描並寫入需要更新的檔案
                videos_to_upsert = []
                cache_hits = len(all_files) - len(needs_scan)
                cache_misses = 0

                for i, file_info in enumerate(needs_scan, 1):
                    video_name = os.path.basename(file_info['path'])
                    yield send({"type": "log", "level": "info", "message": f"  [{i}/{len(needs_scan)}] {video_name}"})

                    try:
                        video_info = scanner.scan_file(file_info['path'], None)
                        video = Video.from_video_info(video_info)
                        video.mtime = file_info['mtime']
                        video.nfo_mtime = file_info.get('nfo_mtime', 0)
                        videos_to_upsert.append(video)
                        session_added_paths.append(video.path)
                        cache_misses += 1
                    except Exception as e:
                        yield send({"type": "log", "level": "warn", "message": f"  [{i}] 錯誤: {e}"})

                # 批次寫入
                if videos_to_upsert:
                    inserted, updated = repo.upsert_batch(videos_to_upsert)
                    total_inserted += inserted
                    total_updated += updated

                logger.info(f"[Gallery] {directory}: {len(all_files)} 個檔案，快取命中 {cache_hits}")

                yield send({
                    "type": "log",
                    "level": "info",
                    "message": f"{directory}: {len(all_files)} 部 (快取: {cache_hits}, 新增/更新: {cache_misses})"
                })
            except Exception as e:
                yield send({"type": "log", "level": "error", "message": f"掃描錯誤: {e}"})

        # 從 SQLite 取得所有影片用於生成 HTML
        all_db_videos = repo.get_all()

        # === 自動套用女優別名 ===
        alias_repo = ActressAliasRepository(db_path)
        aliases = alias_repo.get_all()

        if aliases:
            yield send({"type": "log", "level": "info",
                        "message": f"套用 {len(aliases)} 筆女優別名..."})

            db_updated = False
            for msg in apply_actress_aliases_generator(aliases, repo, alias_repo):
                # 過濾掉中間函數的 done 事件，避免前端誤判為最終結果
                if msg.get('type') == 'done':
                    if msg.get('db_updated', 0) > 0:
                        db_updated = True
                    continue  # 不轉發 done 事件
                yield send(msg)

            # 如果有更新，重新取得影片資料
            if db_updated:
                all_db_videos = repo.get_all()

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
                            'num': video.number or ''
                        }
                    }
            if session_cache:
                session_stats = check_cache_needs_update(session_cache)
                session_update = {
                    "count": session_stats['need_update'],
                    "paths": session_stats['paths']
                }
                if session_update['count'] > 0:
                    yield send({
                        "type": "log",
                        "level": "warn",
                        "message": f"發現 {session_update['count']} 部新增影片資訊不全"
                    })

        yield send({"type": "log", "level": "info", "message": f"資料庫總筆數: {repo.count()}"})

        # 產生 HTML
        yield send({
            "type": "progress",
            "status": "產生網頁...",
            "current": total_dirs,
            "total": total_dirs + 1
        })

        generator = HTMLGenerator()
        generator.generate(
            all_videos,
            str(html_path),
            title="AV List",
            mode=default_mode,
            sort=default_sort,
            order=default_order,
            items_per_page=items_per_page,
            theme=default_theme
        )

        yield send({
            "type": "progress",
            "status": "完成",
            "current": total_dirs + 1,
            "total": total_dirs + 1
        })

        logger.info(f"[Gallery] 完成，新增 {total_inserted}，更新 {total_updated}，刪除 {total_deleted}")

        yield send({
            "type": "done",
            "video_count": len(all_videos),
            "output_path": str(html_path),
            "session_update": session_update,
            "stats": {
                "inserted": total_inserted,
                "updated": total_updated,
                "deleted": total_deleted
            }
        })

    except Exception as e:
        yield send({"type": "error", "message": str(e)})


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
async def get_stats():
    """取得 AVList 統計資訊（從 SQLite 讀取）"""
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
        return {"success": False, "error": str(e)}


@router.get("/update-check")
async def check_update():
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
                    'num': v.number or ''
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
        return {"success": False, "error": str(e)}


def generate_nfo_update() -> Generator[str, None, None]:
    """NFO 更新生成器（SSE 串流）- 使用 SQLite"""

    def send(data: dict):
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    try:
        db_path = get_db_path()

        if not db_path.exists():
            yield send({"type": "error", "message": "資料庫不存在，請先產生列表"})
            return

        repo = VideoRepository(db_path)
        all_videos = repo.get_all()

        if not all_videos:
            yield send({"type": "done", "message": "沒有影片資料", "updated": 0})
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
                    'num': v.number or ''
                }
            }

        # 檢查需要更新的影片
        stats = check_cache_needs_update(cache)
        if stats['need_update'] == 0:
            yield send({"type": "done", "message": "沒有需要更新的影片", "updated": 0})
            return

        paths_to_update = stats['paths']
        yield send({
            "type": "log",
            "level": "info",
            "message": f"執行 NFO 檢查 ({len(paths_to_update)} 部)..."
        })

        # 執行更新
        for msg in update_videos_generator(cache, paths_to_update):
            yield send(msg)

        yield send({
            "type": "done",
            "message": "更新完成，建議重新產生網頁以更新資料庫",
        })

    except Exception as e:
        yield send({"type": "error", "message": str(e)})


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
async def view_list():
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
    except Exception as e:
        return HTMLResponse(
            content=f"<html><body><h1>錯誤</h1><p>{e}</p></body></html>",
            status_code=500
        )


@router.get("/image")
async def get_image(path: str = Query(..., description="圖片路徑")):
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

    if not os.path.exists(local_path):
        return Response(status_code=404, content=f"Not found: {local_path}")

    # 檢測 MIME 類型
    ext = os.path.splitext(local_path)[1].lower()
    mime_types = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.webp': 'image/webp',
        '.bmp': 'image/bmp',
    }
    media_type = mime_types.get(ext, 'application/octet-stream')

    return FileResponse(local_path, media_type=media_type)


# === 女優名稱管理 API ===

class ActressAliasRequest(BaseModel):
    """新增女優別名請求"""
    old_name: str
    new_name: str


@router.get("/actress-aliases")
async def get_actress_aliases():
    """取得所有別名對照"""
    try:
        db_path = get_db_path()
        init_db(db_path)

        alias_repo = ActressAliasRepository(db_path)
        aliases = alias_repo.get_all()

        return {
            "success": True,
            "data": [alias.to_dict() for alias in aliases]
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/actress-aliases")
async def add_actress_alias(request: ActressAliasRequest):
    """新增別名對照"""
    try:
        if not request.old_name or not request.new_name:
            return {"success": False, "error": "名稱不可為空"}

        if request.old_name == request.new_name:
            return {"success": False, "error": "新舊名稱不可相同"}

        db_path = get_db_path()
        init_db(db_path)

        alias_repo = ActressAliasRepository(db_path)
        new_id = alias_repo.add(request.old_name, request.new_name)

        if new_id == -1:
            return {"success": False, "error": "該舊名稱已存在"}

        return {"success": True, "data": {"id": new_id}}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.delete("/actress-aliases/{alias_id}")
async def delete_actress_alias(alias_id: int):
    """刪除別名對照"""
    try:
        db_path = get_db_path()
        init_db(db_path)

        alias_repo = ActressAliasRepository(db_path)
        success = alias_repo.delete(alias_id)

        if not success:
            return {"success": False, "error": "找不到該別名對照"}

        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/actress-stats")
async def get_actress_stats(name: str = Query(..., description="女優名稱")):
    """查詢某名字的片數"""
    try:
        db_path = get_db_path()

        if not db_path.exists():
            return {"success": True, "data": {"count": 0}}

        repo = VideoRepository(db_path)
        count = repo.count_by_actress(name)

        return {"success": True, "data": {"count": count}}
    except Exception as e:
        return {"success": False, "error": str(e)}


def generate_apply_actress_aliases() -> Generator[str, None, None]:
    """套用女優別名生成器（SSE 串流）"""

    def send(data: dict):
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    try:
        db_path = get_db_path()

        if not db_path.exists():
            yield send({"type": "error", "message": "資料庫不存在"})
            return

        init_db(db_path)
        video_repo = VideoRepository(db_path)
        alias_repo = ActressAliasRepository(db_path)

        aliases = alias_repo.get_all()
        if not aliases:
            yield send({"type": "done", "message": "沒有別名對照", "stats": {}})
            return

        yield send({
            "type": "log",
            "level": "info",
            "message": f"開始套用 {len(aliases)} 筆別名對照..."
        })

        # 執行套用
        for msg in apply_actress_aliases_generator(aliases, video_repo, alias_repo):
            yield send(msg)

        yield send({
            "type": "done",
            "message": "套用完成！建議重新產生列表以更新封面。"
        })

    except Exception as e:
        yield send({"type": "error", "message": str(e)})


@router.get("/apply-actress-aliases")
async def apply_actress_aliases():
    """執行批次更新（SSE 串流回傳進度）- 使用 GET 以支援 EventSource"""
    return StreamingResponse(
        generate_apply_actress_aliases(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )
