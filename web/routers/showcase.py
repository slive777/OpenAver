"""
Showcase API 路由 - 影片展示資料端點

端點：
- GET /api/showcase/videos        — 取得所有影片資料（供 Showcase 頁面客戶端渲染）
- GET /api/showcase/video?path=   — 取得單筆影片資料（供 T3 enrich 後刷新卡片）
"""

import io
import os
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from PIL import Image

from core.database import VideoRepository, get_db_path, init_db
from core.path_utils import (
    is_path_under_dir,
    uri_to_local_fs_path,
    coerce_to_file_uri,
)
from core.logger import get_logger
from core.config import load_config, get_gallery_source_paths
from core.focal import detect_focal, format_focal, parse_focal
from core import thumbnail_cache
from core.multipart_group import group_rows, resolve_group

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


class RotateCoverRequest(BaseModel):
    """POST /video/rotate body：path（DB key）+ angle（順時針 90/180/270）+
    expected_cover_path（cover compare-and-store，防旋轉期間封面被 rescan/rescrape
    換掉——同 save-focal 的 PR#107 P2 模式）。"""
    path: str
    angle: int
    expected_cover_path: str


def _serialize_video(v, path_mappings: dict, enabled: bool = False) -> dict:
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
        "cover_path": v.cover_path,                              # file:/// URI（快捷旋轉 expected_cover_path / x-show gate 用，125-T1）
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
        "user_rating": v.user_rating or 0,            # 精選標記（spec-123）；無條件輸出，未精選為 0（FE-ALPINE-06）
        "has_cover": bool(v.cover_path),             # DB 初判（不做 IO）
        "has_nfo": (v.nfo_mtime or 0) > 0,          # 對齊 41a nfo_mtime 寫入契約，防禦 NULL
        "auto_focal": v.auto_focal,                  # canonical "x,y" 4dp 字串或 ''（98b：前端 focalObjectPosition 消費）
        "crop_mode": v.crop_mode,                    # 'auto' | 'default'（98b：default 退 baseline 右裁）
    }


def _serialize_group(group, path_mappings: dict, enabled: bool = False) -> dict:
    """將 VideoGroup 序列化為前端 JSON dict（feature/122，CD-122-4）。

    以 `group.members[0]`（part-1，group_rows 已依 part_number 升冪排序）的
    `_serialize_video()` 結果為基底，只在**真的多段時**覆寫 `size`（各段 size_bytes 加總，`or 0`
    是必要防禦——`Video.from_row()` 對 DB NULL 不做防禦，size_bytes 可能是 None）
    與新增 `part_tokens`。其餘欄位（含 `duration`）逐字取 part-1，不做欄位級 merge。
    單檔片：members==[v]、part_tokens==[]，輸出與今天 `_serialize_video(v, ...)`
    逐鍵逐值相同，只多 `part_tokens: []` 一個新鍵（AC-4）。
    """
    base = _serialize_video(group.members[0], path_mappings, enabled)
    # 單檔片不碰 size：`_serialize_video()` 原樣傳 `v.size_bytes`（DB NULL → None），
    # 套 `or 0` 會把 None 變 0，違反 AC-4「單檔片逐位元組不變」的字面契約。
    # 只有真的多段時才加總，`or 0` 的 NULL 防禦留在那條路上（T2 review P3）。
    if len(group.members) > 1:
        base['size'] = sum(m.size_bytes or 0 for m in group.members)
    base['part_tokens'] = group.part_tokens
    return base


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

        all_videos = [v for v in repo.get_all()
                      if any(is_path_under_dir(v.path, uri) for uri in configured_dir_uris)]

        # feature/122 CD-122-1：分組在序列化層收斂，前端拿到的 videos 陣列已是
        # 合併後的一筆一組（多一個 part_tokens 欄位）。單檔片的 group 只有自己
        # 一個 member，_serialize_group() 輸出與改動前逐鍵逐值相同（AC-4）。
        groups = group_rows(all_videos, fs_path_of=lambda v: uri_to_local_fs_path(v.path, path_mappings))

        thumb_enabled = config.get('thumbnail_cache_enabled', False)
        videos_json = [_serialize_group(g, path_mappings, thumb_enabled)
                       for g in groups]

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

        if not any(is_path_under_dir(path, uri) for uri in configured_dir_uris):
            return JSONResponse({"success": False, "error": "video not found"}, status_code=404)

        v = repo.get_by_path(path)
        if v is None:
            return JSONResponse({"success": False, "error": "video not found"}, status_code=404)

        thumb_enabled = config.get('thumbnail_cache_enabled', False)

        # feature/122：用查到列的 v.path（而非使用者傳入的原始 path 字面，更可靠）
        # 算同資料夾候選列，反解該 path 所屬的組。找不到組（極端狀況：part-1 被
        # 刪但 part-2 還在、或路徑不再是任何組的代表）→ fail-safe 退回單檔序列化，
        # 不 500（CD-122-6）。
        group = resolve_group(repo, path, path_mappings, folder_source_uri=v.path)
        if group is None:
            return JSONResponse({"success": True,
                                 "video": _serialize_video(v, path_mappings, thumb_enabled)})

        return JSONResponse({"success": True,
                             "video": _serialize_group(group, path_mappings, thumb_enabled)})

    except Exception as e:
        logger.error("取得單筆影片失敗: %s", e)
        return JSONResponse({"success": False, "error": "取得影片資料失敗"}, status_code=500)


@router.delete("/video")
def delete_video(path: str = Query(..., description="file:/// URI")):
    """從收藏移除影片（71-T7，CD-10 / §1.6；feature/122 T4 改整組刪除）。

    只刪 DB row（repo.delete_by_paths，DB-only）+ 砍衍生縮圖 WebP
    （thumbnail_cache.invalidate）。**絕不 unlink 影片檔或原始封面檔。**

    刻意「無 scope guard」：issue #57 要刪的正是已移出 gallery 設定資料夾的
    stale DB row，那些 path 依定義不在任何 configured dir 下，scope guard 會
    擋掉正當用例。未知 path → delete_by_paths rowcount=0，安全 no-op。

    feature/122：合併卡刪除時反解同組全部成員，一次刪除整組 DB 列，並對
    每一個 member 呼叫 thumbnail_cache.invalidate。`deleted` 為本次刪除的列數。
    反解失敗（找不到組、或載入設定時拋例外）→ fail-safe 退回單路徑刪除，不 500。
    注意 try 只包住「反解組」那一段，**不包實際刪除**——DB 真的壞掉仍會照常
    拋出 500，不會偽裝成刪除成功。（路徑運算本身不拋：uri_to_fs_path 對畸形
    輸入是原樣回傳，那條路走的是「反解不到組 → 退回單筆」而非例外。）

    `def`（非 async）→ Starlette threadpool，body 內 DB / unlink 在 worker thread。
    不進 capabilities（D9）。
    """
    db_path = get_db_path()
    if not db_path.exists():
        return JSONResponse({"deleted": 0})

    init_db(db_path)
    repo = VideoRepository(db_path)

    group = None
    try:
        config = load_config()
        _, path_mappings = _get_configured_dirs(config)
        group = resolve_group(repo, path, path_mappings)
    except Exception:
        logger.warning("delete_video: 分組反解失敗，退回單路徑刪除", exc_info=True)
        group = None

    if group is None:
        n = repo.delete_by_paths([path])
        thumbnail_cache.invalidate(path)
    else:
        member_paths = [m.path for m in group.members]
        n = repo.delete_by_paths(member_paths)
        for m in group.members:
            thumbnail_cache.invalidate(m.path)

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


@router.post("/video/rotate")
def rotate_video_cover(req: RotateCoverRequest):
    """快捷旋轉封面（順時針 90/180/270），物理寫回磁碟 jpg（Plex 直讀），
    並重置 focal（座標基於舊方向失效，reset_focal_to_auto 後背景 worker 會重新偵測）。

    流程與 save-focal 同構：path（DB key）解析 → scope guard → cover compare-and-store
    （expected_cover_path 防旋轉期間封面被換）→ 旋轉寫回 → reset_focal_to_auto。
    注意：**物理改圖不可逆**（覆蓋原封面），前端應以 toast/確認交付可逆性提示。
    """
    if req.angle not in (90, 180, 270):
        return JSONResponse({"success": False, "error": "旋轉角度僅支援 90/180/270"}, status_code=400)

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
            return JSONResponse({"success": False, "error": "此影片不在收藏範圍，無法旋轉封面"}, status_code=403)

        # cover compare-and-store：封面被 rescan/rescrape 換掉 → 拒絕（舊封面座標/尺寸失效）
        if row.cover_path != req.expected_cover_path:
            return JSONResponse(
                {"success": False, "error": "封面已變更，請重新開啟再試一次"},
                status_code=409,
            )
        if not row.cover_path:
            return JSONResponse({"success": False, "error": "此影片沒有封面可旋轉"}, status_code=400)

        from core.organizer import rotate_cover

        cover_fs = uri_to_local_fs_path(row.cover_path, {})
        ok, new_size = rotate_cover(cover_fs, req.angle)
        if not ok:
            return JSONResponse({"success": False, "error": "封面旋轉失敗"}, status_code=500)

        # 旋轉後 focal 座標失效 → 重置（清空 + crop_mode='auto' + focal_attempted_at=NULL，
        # 背景 worker 會重新偵測新封面）
        repo.reset_focal_to_auto(req.path)

        # 縮圖快取失效（舊方向縮圖）
        try:
            thumbnail_cache.invalidate(req.path)
        except Exception:
            pass

        return JSONResponse({"success": True, "size": list(new_size)})

    except Exception as e:
        logger.error("旋轉封面失敗: %s", e)
        return JSONResponse({"success": False, "error": "旋轉封面失敗"}, status_code=500)


# ---- 封面手动替换（125-T2：仿女优换照，裁切预览界面内，保存覆盖原封面）----
_UPLOAD_MAX_BYTES = 15 * 1024 * 1024
_UPLOAD_MAX_PIXELS = 60_000_000


@router.post("/video/replace-cover")
def replace_video_cover(
    path: str = Form(...),
    expected_cover_path: str = Form(''),
    file: UploadFile = File(...),
):
    """手动替换影片封面（multipart：path（DB key）+ file 图片）。

    写入目标 = 现有 cover_path 指向的磁盘文件（{stem}.jpg，覆盖原封面——
    Plex 直读同名 jpg）；图片统一转 JPEG 写盘。成功后重置 focal（新图坐标
    失效，背景 worker 重测）+ 缩略图失效。
    """
    try:
        data = file.file.read()
    except Exception:
        return JSONResponse({"success": False, "error": "讀取上傳失敗"}, status_code=400)
    if len(data) > _UPLOAD_MAX_BYTES:
        return JSONResponse({"success": False, "error": "圖片太大（上限 15MB）"}, status_code=413)
    try:
        img = Image.open(io.BytesIO(data))
        w, h = img.size
        if w * h > _UPLOAD_MAX_PIXELS:
            return JSONResponse({"success": False, "error": "圖片像素過大"}, status_code=413)
        img.verify()
    except Exception:
        return JSONResponse({"success": False, "error": "不支援的圖片格式"}, status_code=415)

    try:
        db_path = get_db_path()
        if not db_path.exists():
            return JSONResponse({"success": False, "error": "找不到影片"}, status_code=404)
        init_db(db_path)
        repo = VideoRepository(db_path)

        row = repo.get_by_path(path)
        if row is None:
            return JSONResponse({"success": False, "error": "找不到影片"}, status_code=404)

        config = load_config()
        configured_dir_uris, path_mappings = _get_configured_dirs(config)
        in_scope = any(is_path_under_dir(row.path, uri) for uri in configured_dir_uris)
        if not in_scope:
            return JSONResponse({"success": False, "error": "此影片不在收藏範圍，無法替換封面"}, status_code=403)

        # cover compare-and-store（同 save-focal/rotate）：封面被 rescan/rescrape 換掉 → 拒絕。
        # 空 cover_path（無封面影片）時 expected 亦為空，跳過比對（見下方「無封面→創建」分支）。
        if row.cover_path and row.cover_path != expected_cover_path:
            return JSONResponse(
                {"success": False, "error": "封面已變更，請重新開啟再試一次"},
                status_code=409,
            )

        if row.cover_path:
            cover_fs = uri_to_local_fs_path(row.cover_path, path_mappings)
        else:
            # 無封面 → 以影片路徑推導封面目標（resolve_cover_target：同名 .jpg 優先，
            # 與刮削產出同一規則，Plex 直讀同名 jpg）。寫盤後更新 DB cover_path。
            from core.cover_layout import resolve_cover_target
            video_fs = uri_to_local_fs_path(row.path, path_mappings)
            if not video_fs or not os.path.isfile(video_fs):
                return JSONResponse({"success": False, "error": "找不到影片檔案"}, status_code=404)
            cover_fs = resolve_cover_target(str(Path(video_fs).with_suffix('')), 'off')
            cover_dir = os.path.dirname(cover_fs)
            if cover_dir and not os.path.isdir(cover_dir):
                return JSONResponse({"success": False, "error": "封面目錄不存在"}, status_code=400)
        with Image.open(io.BytesIO(data)) as src:
            rgb = ImageOps.exif_transpose(src).convert("RGB")
            rgb.save(cover_fs, "JPEG", quality=95)

        if not row.cover_path:
            # 建立新封面：以 file:/// URI 寫入 DB cover_path（與刮削產出同一形狀）
            repo.update_cover_path(path, coerce_to_file_uri(cover_fs, path_mappings))
        repo.reset_focal_to_auto(path)
        try:
            thumbnail_cache.invalidate(path)
        except Exception:
            pass

        return JSONResponse({"success": True, "size": [rgb.size[0], rgb.size[1]]})
    except Exception as e:
        logger.error("替換封面失敗: %s", e)
        return JSONResponse({"success": False, "error": "替換封面失敗"}, status_code=500)
