"""
AVList API 路由 - 影片列表生成
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Generator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

# 加入 core 模組路徑
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.avlist_scanner import VideoScanner, load_cache, save_cache, fast_scan_directory, VIDEO_EXTENSIONS, VideoInfo
from core.avlist_generator import HTMLGenerator
from core.path_utils import normalize_path
from web.routers.config import load_config

router = APIRouter(prefix="/api/avlist", tags=["avlist"])


def generate_avlist() -> Generator[str, None, None]:
    """產生影片列表（SSE 串流）"""

    def send(data: dict):
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    try:
        # 載入設定
        config = load_config()
        avlist_config = config.get('avlist', {})

        directories = avlist_config.get('directories', [])
        output_dir = avlist_config.get('output_dir', 'output')
        output_filename = avlist_config.get('output_filename', 'avlist_output.html')
        path_mappings = avlist_config.get('path_mappings', {})
        min_size_kb = avlist_config.get('min_size_kb', 0)

        # 預設顯示設定
        default_mode = avlist_config.get('default_mode', 'image')
        default_sort = avlist_config.get('default_sort', 'date')
        default_order = avlist_config.get('default_order', 'descending')
        items_per_page = avlist_config.get('items_per_page', 90)

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

        # 初始化掃描器
        scanner = VideoScanner(path_mappings=path_mappings)

        all_videos = []
        total_dirs = len(directories)
        total_added = 0  # 追蹤本次新增數量

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
                min_size_bytes = min_size_kb * 1024
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

        # 儲存 metadata
        cache['_metadata'] = {
            'last_run': datetime.now().isoformat(),
            'last_added': total_added,
            'last_total': len(all_videos)
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
            items_per_page=items_per_page
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
            "output_path": str(html_path)
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
        avlist_config = config.get('avlist', {})
        output_dir = avlist_config.get('output_dir', 'output')
        output_filename = avlist_config.get('output_filename', 'avlist_output.html')

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
