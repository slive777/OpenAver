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
from core.path_utils import normalize_path
from core.nfo_updater import check_cache_needs_update, update_videos_generator
from web.routers.config import load_config

router = APIRouter(prefix="/api/gallery", tags=["gallery"])


def generate_avlist() -> Generator[str, None, None]:
    """產生影片列表（SSE 串流）"""

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

        # 確保輸出目錄存在
        project_root = Path(__file__).parent.parent.parent
        output_path = project_root / output_dir
        output_path.mkdir(parents=True, exist_ok=True)

        html_path = output_path / output_filename
        cache_path = output_path / output_filename.replace('.html', '_cache.json')

        yield send({"type": "log", "level": "info", "message": f"輸出路徑: {html_path}"})

        # 載入快取
        cache = load_cache(str(cache_path))
        # 移除舊的 metadata（不計入快取數量）
        old_metadata = cache.pop('_metadata', {})
        yield send({"type": "log", "level": "info", "message": f"載入快取: {len(cache)} 筆"})

        # 清理不在掃描清單內的快取
        normalized_dirs = []
        for d in directories:
            try:
                normalized_dirs.append(normalize_path(d))
            except ValueError:
                pass

        if normalized_dirs:
            keys_to_remove = []
            for key in cache.keys():
                # 檢查此快取項目是否屬於任一掃描目錄
                in_scan_list = any(key.startswith(nd) for nd in normalized_dirs)
                if not in_scan_list:
                    keys_to_remove.append(key)

            if keys_to_remove:
                for k in keys_to_remove:
                    del cache[k]
                yield send({"type": "log", "level": "info", "message": f"清理舊快取: {len(keys_to_remove)} 筆"})

        # 初始化掃描器
        scanner = VideoScanner(path_mappings=path_mappings)

        all_videos = []
        total_dirs = len(directories)
        total_added = 0  # 追蹤本次新增數量
        session_added_paths = []  # 追蹤本次新增/變更的影片路徑

        for idx, directory in enumerate(directories, 1):
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

                # 逐一處理檔案
                videos = []
                cache_hits = 0
                cache_misses = 0
                current_paths = set()

                for i, file_info in enumerate(all_files, 1):
                    path_key = file_info['path']
                    file_mtime = file_info['mtime']
                    nfo_mtime = file_info.get('nfo_mtime', 0)
                    current_paths.add(path_key)
                    video_name = os.path.basename(path_key)

                    # 檢查緩存
                    cached = cache.get(path_key)
                    cache_valid = (cached and
                                   cached.get('mtime') == file_mtime and
                                   cached.get('nfo_mtime', 0) == nfo_mtime)

                    if cache_valid:
                        info = VideoInfo.from_dict(cached['info'])
                        videos.append(info)
                        cache_hits += 1
                    else:
                        # 回報處理進度（只有非快取命中才顯示）
                        yield send({"type": "log", "level": "info", "message": f"  [{i}] {video_name}"})
                        try:
                            info = scanner.scan_file(path_key, None)
                            videos.append(info)
                            cache_misses += 1
                            cache[path_key] = {
                                'mtime': file_mtime,
                                'nfo_mtime': nfo_mtime,
                                'info': info.to_dict()
                            }
                            # 追蹤本次新增/變更的路徑
                            session_added_paths.append(path_key)
                        except Exception as e:
                            yield send({"type": "log", "level": "warn", "message": f"  [{i}] 錯誤: {e}"})

                # 清理已刪除檔案的緩存
                deleted_keys = [k for k in list(cache.keys()) if k.startswith(normalized_dir) and k not in current_paths]
                for k in deleted_keys:
                    del cache[k]

                all_videos.extend(videos)
                total_added += cache_misses
                yield send({
                    "type": "log",
                    "level": "info",
                    "message": f"{directory}: {len(videos)} 部 (快取: {cache_hits}, 新增: {cache_misses})"
                })
            except Exception as e:
                yield send({"type": "log", "level": "error", "message": f"掃描錯誤: {e}"})

        # 檢查本次新增影片是否需要 NFO 補全
        session_update = {"count": 0, "paths": []}
        if session_added_paths:
            # 建立只包含本次新增影片的 session_cache
            session_cache = {path: cache[path] for path in session_added_paths if path in cache}
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

        # 儲存 metadata（包含 session_update 供 NFO 更新使用）
        cache['_metadata'] = {
            'last_run': datetime.now().isoformat(),
            'last_added': total_added,
            'last_total': len(all_videos),
            'last_session_update': session_update
        }

        # 儲存快取
        save_cache(str(cache_path), cache)
        yield send({"type": "log", "level": "info", "message": f"儲存快取: {len(cache) - 1} 筆"})

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

        yield send({
            "type": "done",
            "video_count": len(all_videos),
            "output_path": str(html_path),
            "session_update": session_update
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
    """取得 AVList 統計資訊（從快取檔案讀取）"""
    try:
        config = load_config()
        gallery_config = config.get('gallery', {})
        output_dir = gallery_config.get('output_dir', 'output')
        output_filename = gallery_config.get('output_filename', 'gallery_output.html')

        project_root = Path(__file__).parent.parent.parent
        cache_path = project_root / output_dir / output_filename.replace('.html', '_cache.json')

        if not cache_path.exists():
            return {"success": True, "data": {"total": 0, "last_run": None, "last_added": None}}

        cache = load_cache(str(cache_path))

        # 讀取 metadata（如果有的話）
        metadata = cache.pop('_metadata', {})

        return {
            "success": True,
            "data": {
                "total": len(cache),
                "last_run": metadata.get('last_run'),
                "last_added": metadata.get('last_added'),
                "last_total": metadata.get('last_total')
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/update-check")
async def check_update():
    """檢查需要更新的影片數量"""
    try:
        config = load_config()
        gallery_config = config.get('gallery', {})
        output_dir = gallery_config.get('output_dir', 'output')
        output_filename = gallery_config.get('output_filename', 'gallery_output.html')

        project_root = Path(__file__).parent.parent.parent
        cache_path = project_root / output_dir / output_filename.replace('.html', '_cache.json')

        if not cache_path.exists():
            return {"success": True, "data": {"need_update": 0}}

        cache = load_cache(str(cache_path))
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
    """NFO 更新生成器（SSE 串流）"""

    def send(data: dict):
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    try:
        config = load_config()
        gallery_config = config.get('gallery', {})
        output_dir = gallery_config.get('output_dir', 'output')
        output_filename = gallery_config.get('output_filename', 'gallery_output.html')

        project_root = Path(__file__).parent.parent.parent
        cache_path = project_root / output_dir / output_filename.replace('.html', '_cache.json')

        if not cache_path.exists():
            yield send({"type": "error", "message": "快取檔案不存在，請先產生列表"})
            return

        cache = load_cache(str(cache_path))
        
        # 讀取 session 更新資料
        metadata = cache.get('_metadata', {})
        session_update = metadata.get('last_session_update', {})
        
        paths_to_update = []
        
        # 優先：使用本次 session 的更新清單
        if session_update and session_update.get('count', 0) > 0:
            paths_to_update = session_update['paths']
            yield send({
                "type": "log",
                "level": "info",
                "message": f"執行本次新增影片的 NFO 更新 ({len(paths_to_update)} 部)..."
            })
        else:
            # 備用：完整掃描整個快取
            stats = check_cache_needs_update(cache)
            if stats['need_update'] == 0:
                yield send({"type": "done", "message": "沒有需要更新的影片", "updated": 0})
                return
            paths_to_update = stats['paths']
            yield send({
                "type": "log",
                "level": "info",
                "message": f"執行完整 NFO 檢查 ({len(paths_to_update)} 部)..."
            })

        # 執行更新
        for msg in update_videos_generator(cache, paths_to_update):
            yield send(msg)

        # 更新完成後清除 session_update，避免重複更新
        if '_metadata' in cache and 'last_session_update' in cache['_metadata']:
            cache['_metadata']['last_session_update'] = {"count": 0, "paths": []}
            save_cache(str(cache_path), cache)

        yield send({
            "type": "done",
            "message": "更新完成，建議重新產生網頁以更新快取",
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
    import re

    # URL decode
    path = unquote(path)

    # 轉換為本地路徑
    # Windows 路徑 C:/Users/... 需要轉換為 WSL 路徑 /mnt/c/Users/...
    if re.match(r'^[A-Za-z]:/', path) or re.match(r'^[A-Za-z]:\\\\', path):
        # Windows 絕對路徑，轉換為 WSL 格式
        drive = path[0].lower()
        rest = path[2:].replace('\\', '/')
        if rest.startswith('/'):
            rest = rest[1:]
        local_path = f'/mnt/{drive}/{rest}'
    elif path.startswith('/mnt/'):
        # 已經是 WSL 路徑
        local_path = path
    else:
        # 其他格式，嘗試直接使用
        local_path = path

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
