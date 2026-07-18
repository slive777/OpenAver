"""
Showcase API 路由 - 影片展示資料端點

端點：
- GET /api/showcase/videos        — 取得所有影片資料（供 Showcase 頁面客戶端渲染）
- GET /api/showcase/video?path=   — 取得單筆影片資料（供 T3 enrich 後刷新卡片）
"""

import os
from urllib.parse import quote

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.database import VideoRepository, get_db_path, init_db
from core.path_utils import is_path_under_dir, uri_to_local_fs_path, coerce_to_file_uri
from core.logger import get_logger
from core.config import load_config, get_gallery_source_paths
from core.readonly_source import is_path_readonly, readonly_source_prefixes, writable_source_prefixes
from core.focal import detect_focal, format_focal, parse_focal
from core import thumbnail_cache

logger = get_logger(__name__)

router = APIRouter(prefix="/api/showcase", tags=["showcase"])


class DetectFocalRequest(BaseModel):
    """POST /video/detect-focal body：path（DB key，Codex P0 絕不當檔案路徑開啟）。"""
    path: str


class ManualFocalRequest(BaseModel):
    """POST /video/save-focal body：path（DB key）+ focal（'x.xxxx,y.xxxx' 格式字串）+
    expected_cover_path（Codex PR#107 第二輪 P2：使用者開遮罩當下觀察到的
    row.cover_path，DB-key file:/// URI 或空字串；必填、不可省略——見
    VideoRepository.update_manual_focal 的 cover compare-and-store 說明）。"""
    path: str
    focal: str
    expected_cover_path: str


def _serialize_video(v, path_mappings: dict, enabled: bool = False, readonly_prefixes: list = None, writable_prefixes: list = None) -> dict:
    """將 Video ORM 物件序列化為前端 JSON dict（列表端點與單筆端點共用）。

    feature/71 T4：thumbnail_cache_enabled 開關決定 cover_url 走 thumb / image 分支。
    - enabled  → cover_url 指向 T3 /api/gallery/thumb?path=<quote(v.path)>（thumb key = video path）
    - disabled → 維持現狀 /api/gallery/image?path=<quote(uri_to_local_fs_path(v.cover_path, path_mappings))>（字節不變）
    cover_full_url 恆原圖（不受 flag 影響），供 T6 燈箱 blur-up 上層淡入用。
    """
    cover_url = ""
    cover_full_url = ""
    if v.cover_path:
        original_url = f"/api/gallery/image?path={quote(uri_to_local_fs_path(v.cover_path, path_mappings), safe='')}"
        cover_full_url = original_url
        if enabled:
            cover_url = f"/api/gallery/thumb?path={quote(v.path, safe='')}"
        else:
            cover_url = original_url

    sample_urls = []
    for img_uri in (v.sample_images or []):
        local_path = uri_to_local_fs_path(img_uri, path_mappings)
        sample_urls.append(f"/api/gallery/image?path={quote(local_path, safe='')}")

    return {
        "path": v.path,                                          # file:/// URI（開啟影片用）
        "title": v.title,
        "original_title": v.original_title,
        "actresses": ','.join(v.actresses) if v.actresses else '',  # 逗號分隔字串
        "number": v.number or '',
        "maker": v.maker,
        "release_date": v.release_date,
        "tags": ','.join(v.tags) if v.tags else '',              # 逗號分隔字串
        "size": v.size_bytes,
        "cover_url": cover_url,                                  # enabled→thumb / disabled→image
        "cover_full_url": cover_full_url,                        # 恆原圖 /api/gallery/image?path=...（T6 燈箱）
        "mtime": int(v.mtime) if v.mtime else 0,                 # Unix timestamp 整數
        "director": v.director or '',
        "duration": v.duration,                                  # Optional[int]，None 時前端 x-show 隱藏
        "series": v.series or '',
        "label": v.label or '',
        "sample_images": sample_urls,
        "user_tags": v.user_tags or [],              # list[str]，空時回空 list
        "has_cover": bool(v.cover_path),             # DB 初判（不做 IO）
        "has_nfo": (v.nfo_mtime or 0) > 0,          # 對齊 41a nfo_mtime 寫入契約，防禦 NULL
        "is_readonly_source": is_path_readonly(     # 後端算：片落唯讀前綴下且不落可寫前綴→True（前端不判路徑）
            # uri-no-reverse: coerce_to_file_uri forward URI build, D2 complement
            coerce_to_file_uri(v.path, path_mappings), readonly_prefixes or [], writable_prefixes or []
        ),
        "auto_focal": v.auto_focal,                  # canonical "x,y" 4dp 字串或 ''（98b：前端 focalObjectPosition 消費）
        "crop_mode": v.crop_mode,                    # 'auto' | 'default'（98b：default 退 baseline 右裁）
    }


def _get_configured_dirs(config: dict) -> tuple[set, dict]:
    """從 config 取出 configured_dir_uris 與 path_mappings（列表與單筆端點共用）"""
    gallery_config = config.get('gallery', {})
    path_mappings = gallery_config.get('path_mappings', {})

    configured_dir_uris: set = set()
    for p in get_gallery_source_paths(gallery_config):
        try:
            # coerce_to_file_uri：來源 path 可能已是 file:/// URI（DirectoryConfig.path
            # schema「FS 路徑或 URI」）。已是 URI 就原樣回，避免 to_file_uri 二次包成
            # file:///file:/// 把 readonly 來源的列從 Showcase 過濾掉（PR#91 P2-D 同源）。
            configured_dir_uris.add(coerce_to_file_uri(p, path_mappings))  # uri-no-reverse: coerce_to_file_uri forward URI build, D2 complement
        except ValueError:
            continue

    return configured_dir_uris, path_mappings


@router.get("/videos")
def get_videos():
    """取得所有影片資料（用於 Showcase 頁面客戶端渲染）"""
    try:
        db_path = get_db_path()

        # 空庫情境：資料庫檔案不存在
        if not db_path.exists():
            return JSONResponse({
                "success": True,
                "videos": [],
                "total": 0
            })

        init_db(db_path)  # 確保 schema 存在（防止半毀損 DB）
        repo = VideoRepository(db_path)

        # 只取「當前設定資料夾」底下的記錄（DB 保留全部當 cache）
        config = load_config()
        configured_dir_uris, path_mappings = _get_configured_dirs(config)
        # 唯讀來源前綴集：每 request 算一次（迴圈外），逐片只跑純比對（避免 N+1 config 解析，CD-90b-9）
        readonly_prefixes = readonly_source_prefixes(config.get('gallery', {}), path_mappings)
        writable_prefixes = writable_source_prefixes(config.get('gallery', {}), path_mappings)

        all_videos = [v for v in repo.get_all()
                      if any(is_path_under_dir(v.path, uri) for uri in configured_dir_uris)]

        thumb_enabled = config.get('thumbnail_cache_enabled', False)
        videos_json = [_serialize_video(v, path_mappings, thumb_enabled, readonly_prefixes, writable_prefixes)
                       for v in all_videos]

        return JSONResponse({
            "success": True,
            "videos": videos_json,
            "total": len(videos_json)
        })

    except Exception as e:
        logger.error("取得影片資料失敗: %s", e)
        return JSONResponse({
            "success": False,
            "error": "取得影片資料失敗",
            "videos": [],
            "total": 0
        }, status_code=500)


@router.get("/video")
def get_video(path: str = Query(..., description="file:/// URI")):
    """取得單筆影片資料（用於 T3 refreshVideoData enrich 後刷新卡片）"""
    try:
        db_path = get_db_path()
        if not db_path.exists():
            return JSONResponse({"success": False, "error": "video not found"}, status_code=404)

        init_db(db_path)
        repo = VideoRepository(db_path)

        config = load_config()
        configured_dir_uris, path_mappings = _get_configured_dirs(config)
        readonly_prefixes = readonly_source_prefixes(config.get('gallery', {}), path_mappings)
        writable_prefixes = writable_source_prefixes(config.get('gallery', {}), path_mappings)

        if not any(is_path_under_dir(path, uri) for uri in configured_dir_uris):
            return JSONResponse({"success": False, "error": "video not found"}, status_code=404)

        v = repo.get_by_path(path)
        if v is None:
            return JSONResponse({"success": False, "error": "video not found"}, status_code=404)

        thumb_enabled = config.get('thumbnail_cache_enabled', False)
        return JSONResponse({"success": True,
                             "video": _serialize_video(v, path_mappings, thumb_enabled, readonly_prefixes, writable_prefixes)})

    except Exception as e:
        logger.error("取得單筆影片失敗: %s", e)
        return JSONResponse({"success": False, "error": "取得影片資料失敗"}, status_code=500)


@router.delete("/video")
def delete_video(path: str = Query(..., description="file:/// URI")):
    """從收藏移除單筆影片（71-T7，CD-10 / §1.6）。

    只刪 DB row（repo.delete_by_paths，DB-only）+ 砍衍生縮圖 WebP
    （thumbnail_cache.invalidate）。**絕不 unlink 影片檔或原始封面檔。**

    刻意「無 scope guard」：issue #57 要刪的正是已移出 gallery 設定資料夾的
    stale DB row，那些 path 依定義不在任何 configured dir 下，scope guard 會
    擋掉正當用例。未知 path → delete_by_paths rowcount=0，安全 no-op。

    `def`（非 async）→ Starlette threadpool，body 內 DB / unlink 在 worker thread。
    不進 capabilities（D9）。
    """
    db_path = get_db_path()
    if not db_path.exists():
        return JSONResponse({"deleted": 0})

    init_db(db_path)
    repo = VideoRepository(db_path)

    n = repo.delete_by_paths([path])
    thumbnail_cache.invalidate(path)

    return JSONResponse({"deleted": n})


@router.post("/video/detect-focal")
def detect_video_focal(req: DetectFocalRequest):
    """使用者主動 force-detect 封面焦點預覽（98b-T4 CD-98b-7 / Codex P0；99a-T1a 改純預覽-only）。

    **安全不變式：body `path` 一律當 DB key，絕不當檔案路徑開啟。** 偵測目標是
    `row.cover_path` 反解的封面 fs（非 body path 的影片 URI）。
    - 非 DB path → 404（不開任何檔）。
    - configured-dir scope 外 → 拒（scope 外 force-detect 無意義）。
    - **不寫 DB**（99a-T1a）：純預覽供前端遮罩顯示，唯讀來源亦放行（D4/CD-7——
      偵測本身不寫入，不需要可寫權限）。要存入需另呼叫 `POST /video/save-focal` mutator。
    - row.cover_path 空或檔案不存在 → 固定字串（不崩）。
    - 無臉 → format_focal(None) = '' 回傳（不存）。

    回應（row 找到、in-scope 之後的所有分支：成功偵測 / 封面檔缺失）皆帶
    `cover_path`（row 當下的 DB-key `cover_path`，Codex PR#107 第二輪 P2）：
    前端拿這個值原樣存為 mask session 的 `expected_cover_path`，之後
    `POST /video/save-focal` 存檔時原樣帶回，讓 `update_manual_focal` 的
    compare-and-store 守衛比對「使用者觀察當下」與「存檔當下」的封面是否一致，
    擋掉 rescan/rescrape 換封面卻把舊座標存成新封面 manual 值的 race。
    `def`（非 async）→ threadpool；detect_focal 同步 ~2.2s。**不進 capabilities（不揭露）。**
    """
    try:
        db_path = get_db_path()
        if not db_path.exists():
            return JSONResponse({"success": False, "error": "找不到影片"}, status_code=404)

        init_db(db_path)
        repo = VideoRepository(db_path)

        row = repo.get_by_path(req.path)
        if row is None:
            return JSONResponse({"success": False, "error": "找不到影片"}, status_code=404)

        config = load_config()
        configured_dir_uris, path_mappings = _get_configured_dirs(config)

        in_scope = any(is_path_under_dir(row.path, uri) for uri in configured_dir_uris)
        if not in_scope:
            return JSONResponse({"success": False, "error": "此影片不在收藏範圍，無法偵測焦點"}, status_code=403)

        # ★ Codex P0：取 row.cover_path（非 body path）反解封面 fs
        cover_fs = uri_to_local_fs_path(row.cover_path, path_mappings) if row.cover_path else ''
        if not row.cover_path or not os.path.isfile(cover_fs):
            return JSONResponse({"success": False, "error": "找不到封面檔案",
                                 "cover_path": row.cover_path}, status_code=400)

        focal = detect_focal(cover_fs, 0.71)     # 同步；無臉 → None
        auto_focal = format_focal(focal)          # None → ''，純預覽不寫 DB
        return JSONResponse({"success": True, "auto_focal": auto_focal, "cover_path": row.cover_path})

    except Exception as e:
        logger.error("偵測焦點失敗: %s", e)
        return JSONResponse({"success": False, "error": "偵測焦點失敗"}, status_code=500)


@router.post("/video/save-focal")
def set_manual_focal(req: ManualFocalRequest):
    """使用者手動存入焦點座標（99a-T1a，CD-2 / spec §3.9-2）。

    body {path, focal}；focal 非合法 "x.xxxx,y.xxxx"（[0,1]x[0,1]，含空字串）格式
    → 400 固定字串，**不碰 DB**（格式驗證先於 scope 檢查，非法輸入不需要多一次
    DB round-trip）。格式合法才進 scope guard：path 不存在 DB → 404；path 不在
    任何 configured dir 下 → 403，DB 皆不變。**不判 readonly**（D4/CD-7：唯讀不擋
    手動存，與 `/detect-focal` 現行為一致——mutator 從一開始就不含 readonly 邏輯）。
    正規化後存（`format_focal(parse_focal(...))`），與 `/detect-focal` 存
    `format_focal(focal)` 的既有慣例一致。原子單一 UPDATE 同時寫 auto_focal +
    crop_mode='manual'（`VideoRepository.update_manual_focal`）。

    body 另帶必填 `expected_cover_path`（Codex PR#107 第二輪 P2）：使用者開遮罩當下
    觀察到的 `cover_path`，原樣帶回與存檔當下的 `row.cover_path` 比對——不符（rescan/
    rescrape 期間換了封面）→ 409，DB 不變，前端應提示使用者重新開啟裁切工具。
    `def`（非 async）→ Starlette threadpool。**不進 capabilities（不揭露）。**
    """
    parsed = parse_focal(req.focal)
    if parsed is None:
        return JSONResponse({"success": False, "error": "無效的焦點座標格式"}, status_code=400)

    try:
        db_path = get_db_path()
        if not db_path.exists():
            return JSONResponse({"success": False, "error": "找不到影片"}, status_code=404)

        init_db(db_path)
        repo = VideoRepository(db_path)

        row = repo.get_by_path(req.path)
        if row is None:
            return JSONResponse({"success": False, "error": "找不到影片"}, status_code=404)

        config = load_config()
        configured_dir_uris, _path_mappings = _get_configured_dirs(config)

        in_scope = any(is_path_under_dir(row.path, uri) for uri in configured_dir_uris)
        if not in_scope:
            return JSONResponse({"success": False, "error": "此影片不在收藏範圍，無法存入焦點"}, status_code=403)

        normalized = format_focal(parsed)
        written = repo.update_manual_focal(req.path, normalized, req.expected_cover_path)
        if not written:
            return JSONResponse(
                {"success": False, "error": "封面已變更，請重新開啟裁切工具再試一次"},
                status_code=409,
            )
        return JSONResponse({"success": True, "auto_focal": normalized})

    except Exception as e:
        logger.error("存入手動焦點失敗: %s", e)
        return JSONResponse({"success": False, "error": "存入手動焦點失敗"}, status_code=500)
