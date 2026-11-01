"""
Showcase API 路由 - 影片展示資料端點

端點：
- GET /api/showcase/videos        — 取得所有影片資料（供 Showcase 頁面客戶端渲染）
- GET /api/showcase/video?path=   — 取得單筆影片資料（供 T3 enrich 後刷新卡片）
"""

import os
import uuid
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from core.database import VideoRepository, get_db_path, init_db
from core.database.version_tracker import (
    compute_db_fingerprint,
    compute_etag,
    get_showcase_revision,
)
from core.path_utils import (
    is_path_under_dir,
    uri_to_local_fs_path,
)
from core.logger import get_logger
from core.platform_info import DSM_PERMISSION_HINT, is_synology
from core.config import load_config, get_gallery_source_paths, get_configured_gallery_dirs
from core.scrapers.utils import has_japanese
from core.nfo_stat import nfo_mtime_or_none
from core.nfo_title_format import build_display_title
from core.title_writeback import (
    NfoNotFoundError, NfoParseError, rewrite_nfo_titles, strip_illegal_xml_chars,
)
from core.video_nfo_locate import locate_readonly_nfo, locate_video_nfo
from core.focal import device_state, format_focal, parse_focal
from core.focal.subprocess_runner import run_detection
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


class TitleWritebackRequest(BaseModel):
    """POST /video/title body：file_path（DB key）+ title（新標題）+ original_title 三態
    （None＝沿用；""＝清空；非空＝設定）。"""
    file_path: str
    title: str
    original_title: Optional[str] = None


def _needs_translate(title, original_title, nfo_mtime) -> bool:
    """標題是假名、沒有原文、且有 NFO（nfo_mtime > 0）才算待翻譯（列表與寫回回應共用）。"""
    return bool((not original_title) and has_japanese(title or '') and (nfo_mtime or 0) > 0)


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
        "needs_translate": _needs_translate(v.title, v.original_title, v.nfo_mtime),  # 無條件輸出（FE-ALPINE-06）
        "auto_focal": v.auto_focal,                  # canonical "x,y" 4dp 字串或 ''（98b：前端 focalObjectPosition 消費）
        "crop_mode": v.crop_mode,                    # 'auto' | 'default'（98b：default 退 baseline 右裁）
        "has_plot": v.has_plot is True,              # 187b：後端不輸出三態（NULL→false；FE-ALPINE-06）
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


def _etag_matches(if_none_match: str, etag: str) -> bool:
    """比對 `If-None-Match` 語意（抄 Starlette `StaticFiles.is_not_modified()` 的比對方式，
    不 import 該函式本身——它綁定 `FileResponse` 用的 `Headers` 型別，這裡是手寫 JSON 端點）。

    依逗號拆多值、去除頭尾空白與 `W/` 弱驗證前綴，逐一比對是否等於 `etag`。
    """
    if not if_none_match:
        return False
    return etag in [tag.strip().removeprefix("W/") for tag in if_none_match.split(",")]


@router.get("/videos")
def get_videos(request: Request):
    """取得所有影片資料（用於 Showcase 頁面客戶端渲染）。

    帶 ETag（CD-145a-8/11/12）：涵蓋 DB 內部寫入 revision、DB/-wal 檔案指紋（涵蓋外部
    抽換或還原備份）、無機密設定投影（來源資料夾／path_mappings／縮圖開關）三項，
    加上開機隨機值一起 HMAC（`core.database.version_tracker.compute_etag`）。命中
    `If-None-Match` 時在序列化之前短路回 304，資料真的沒變時不用重新序列化整份清單、
    不用把整包 JSON 再傳一次。
    """
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

        # 只取「當前設定資料夾」底下的記錄（DB 保留全部當 cache）
        config = load_config()
        gallery_config = config.get('gallery', {})
        configured_dir_uris, path_mappings = get_configured_gallery_dirs(config)
        thumb_enabled = config.get('thumbnail_cache_enabled', False)

        projection = {
            "directories": sorted(get_gallery_source_paths(gallery_config)),
            "path_mappings": path_mappings,
            "thumbnail_cache_enabled": thumb_enabled,
        }
        etag = compute_etag(get_showcase_revision(), compute_db_fingerprint(db_path), projection)

        if _etag_matches(request.headers.get("if-none-match"), etag):
            return Response(status_code=304, headers={"ETag": etag, "Cache-Control": "no-cache"})

        repo = VideoRepository(db_path)
        all_videos = [v for v in repo.get_all()
                      if any(is_path_under_dir(v.path, uri) for uri in configured_dir_uris)]

        # feature/122 CD-122-1：分組在序列化層收斂，前端拿到的 videos 陣列已是
        # 合併後的一筆一組（多一個 part_tokens 欄位）。單檔片的 group 只有自己
        # 一個 member，_serialize_group() 輸出與改動前逐鍵逐值相同（AC-4）。
        groups = group_rows(all_videos, fs_path_of=lambda v: uri_to_local_fs_path(v.path, path_mappings))

        videos_json = [_serialize_group(g, path_mappings, thumb_enabled)
                       for g in groups]

        resp = JSONResponse({
            "success": True,
            "videos": videos_json,
            "total": len(videos_json)
        })
        resp.headers["ETag"] = etag
        resp.headers["Cache-Control"] = "no-cache"
        return resp

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
        configured_dir_uris, path_mappings = get_configured_gallery_dirs(config)

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
        _, path_mappings = get_configured_gallery_dirs(config)
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


_MANUAL_DETECT_TIMEOUT_S = 5.0  # D2/D9: 前景與背景共用同一個 5 秒定義（CD-152d-1），不是批次上限外的安全網
_MANUAL_DETECT_WALL_BUDGET_S = 5.0
_manual_detect_executor = ThreadPoolExecutor(max_workers=1)


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
    成功分支另帶 ``reason``（CD-152d-4b 五值：``""`` / ``device_disabled`` /
    ``too_slow_auto_disabled`` / ``too_slow`` / ``failed``），供前端區分提示。
    `def`（非 async）→ threadpool。使用者回應有 5 秒 wall budget（`_MANUAL_DETECT_WALL_BUDGET_S`，
    逾時回 ``still_detecting``：背景那輪還在跑，這裡不記帳——它之後照既有規則記；
    等待時間含排隊與子程序啟動，不能當成「偵測本身太慢」停用）；以下描述的是**背景執行緒**的時間，不是 HTTP 回應會等多久：
    有計時預算的只有兩段：`_MANUAL_DETECT_TIMEOUT_S = 5.0`（偵測階段本身）＋ 最長 10 秒的子程序
    啟動逾時（`_STARTUP_TIMEOUT_S`，寫死在 `core/focal/subprocess_runner.py`，不受本端點傳入的
    `timeout_s` 影響），兩者相加 15 秒是**名義預算**。總 wall time 另外包含兩段**沒有 timeout**
    的等待：取全域 `_slot_lock`（`subprocess_runner.py` 裸 acquire）與 kill 之後的 `child.wait()`
    （已接受的 residual，見 CHANGELOG「封面放在 NAS／網路磁碟上而中途斷線」那條）。
    ⚠️ 停用狀態已於上方端點層短路，不會走到這裡，所以「關掉之後直接進手動」不受鎖排隊影響。
    **不進 capabilities（不揭露）。**
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
        configured_dir_uris, path_mappings = get_configured_gallery_dirs(config)

        in_scope = any(is_path_under_dir(row.path, uri) for uri in configured_dir_uris)
        if not in_scope:
            return JSONResponse({"success": False, "error": "此影片不在收藏範圍，無法偵測焦點"}, status_code=403)

        # ★ Codex P0：取 row.cover_path（非 body path）反解封面 fs
        cover_fs = uri_to_local_fs_path(row.cover_path, path_mappings) if row.cover_path else ''
        if not row.cover_path or not os.path.isfile(cover_fs):
            return JSONResponse({"success": False, "error": "找不到封面檔案",
                                 "cover_path": row.cover_path}, status_code=400)

        # 152d-T-D8：停用時在這裡就回，不要進 run_detection ——
        # pre_spawn_check 跑在全域 _slot_lock 裡面（subprocess_runner.py:298→309），
        # 進去等於排隊，而文案承諾的是「直接進手動拖曳」。斷路器的兩處檢查又都排在
        # pre_spawn_check 之前，已停用 + 斷路器已開會回 circuit_open → 前端跳「偵測失敗」。
        # 重用上面那份 config 快照（同一個 request 內取的，BE-CONFIG-05 的新鮮度要求成立）。
        # runner 內的 pre_spawn_check 保留不動，封住「這裡判完之後才被關掉」的窄競態。
        # 152d-T-D9：fail-open，鏡射 runner 內 pre_spawn_check 的既有契約
        # （subprocess_runner.py:309-315）。「config 查詢失敗」與「這台機器算不算得動人臉」
        # 是兩回事——查不到不可以當成停用，更不可以讓整個請求失敗。
        try:
            _focal_disabled = device_state.is_disabled_in(config)
        except Exception:
            logger.warning("focal 停用查詢失敗，fail-open 繼續偵測", exc_info=True)
            _focal_disabled = False
        if _focal_disabled:
            return JSONResponse({
                "success": True,
                "auto_focal": "",
                "cover_path": row.cover_path,
                "reason": "device_disabled",
            })

        decision = {}

        def _on_outcome(o):
            decision["just_disabled"] = device_state.record_manual_outcome(o)

        future = _manual_detect_executor.submit(
            run_detection,
            cover_fs, 0.71, job_key=str(uuid.uuid4()), timeout_s=_MANUAL_DETECT_TIMEOUT_S,
            pre_spawn_check=device_state.is_disabled, on_outcome=_on_outcome,
            external_profile="manual",
        )
        try:
            outcome = future.result(timeout=_MANUAL_DETECT_WALL_BUDGET_S)
        except TimeoutError:
            return JSONResponse({
                "success": True, "auto_focal": "", "cover_path": row.cover_path, "reason": "still_detecting",
            })
        focal = outcome.focal if outcome.kind == "FOUND" else None
        auto_focal = format_focal(focal)          # None → ''，純預覽不寫 DB
        reason = device_state.classify_manual_reason(
            outcome, decision.get("just_disabled", False),
        )
        return JSONResponse({
            "success": True,
            "auto_focal": auto_focal,
            "cover_path": row.cover_path,
            "reason": reason,
        })

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
        configured_dir_uris, _path_mappings = get_configured_gallery_dirs(config)

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


_TITLE_ERROR_MESSAGES = {
    "not_found": "找不到影片",
    "title_empty": "標題不可為空",
    "no_nfo": "找不到 NFO",
    "nfo_ambiguous": "輸出夾有多份 NFO，無法判斷要改哪一份",
    "nfo_unreadable": "NFO 無法讀取或解析",
    "nfo_write_failed": "NFO 寫入失敗",
    "db_write_failed": "資料庫寫入失敗（NFO 已更新，請再試一次）",
    "invalid_path": "檔案路徑格式無效",
}


def _title_fail(code: str) -> dict:
    """寫回失敗一律 HTTP 200 ＋ {success:false, error:<code>, message}。"""
    return {"success": False, "error": code, "message": _TITLE_ERROR_MESSAGES[code]}


def _new_original_title(req, video) -> str:
    """original_title 三態：None＝沿用（現值也空就搬目前標題本體）；""＝清空；非空＝設定。"""
    if req.original_title is not None:
        return req.original_title
    return video.original_title or video.title


def _locate_readonly_nfo(video, path_mappings: dict, output_uri: str):
    return locate_readonly_nfo(video, path_mappings, output_uri)


def _locate_title_nfo(video, config: dict, path_mappings: dict):
    return locate_video_nfo(video, config, path_mappings)


def _write_title_nfo(nfo_path: str, video, body: str, new_original: str, fmt: str) -> Optional[str]:
    """改寫 NFO 標題元素；成功回 None，失敗回錯誤碼（NFO 先、DB 後，無回滾）。"""
    try:
        rewrite_nfo_titles(
            nfo_path, number=video.number or '', title_body=body, original_title=new_original,
            actors=video.actresses, maker=video.maker, date=video.release_date,
            nfo_title_format=fmt,
        )
    except NfoNotFoundError:
        return "no_nfo"
    except NfoParseError:
        return "nfo_unreadable"
    except Exception as e:
        logger.error("[title-writeback] NFO 寫入失敗: %s", e)
        return "nfo_write_failed"
    return None


def _apply_title_writeback(repo, video, req, config: dict, path_mappings: dict) -> dict:
    fmt = config.get("scraper", {}).get("nfo_title_format", '[{num}]{title}')
    _display, body = build_display_title(
        video.number or '', strip_illegal_xml_chars(req.title).strip(), '',
        video.actresses, video.maker, video.release_date, fmt,
    )
    if not body:
        return _title_fail("title_empty")
    new_original = strip_illegal_xml_chars(_new_original_title(req, video))

    nfo_path, loc_err = _locate_title_nfo(video, config, path_mappings)
    if nfo_path is None:
        return _title_fail(loc_err)
    nfo_err = _write_title_nfo(nfo_path, video, body, new_original, fmt)
    if nfo_err is not None:
        return _title_fail(nfo_err)

    # 取實際寫入那份 NFO 的 mtime；取不到沿用舊值（下次掃描最多多讀一次）
    new_mtime = nfo_mtime_or_none(Path(nfo_path))
    if new_mtime is None:
        new_mtime = video.nfo_mtime
    try:
        written = repo.update_titles(video.path, body, new_original, new_mtime)
    except Exception as e:
        logger.error("[title-writeback] DB 寫入失敗: %s", e)
        return _title_fail("db_write_failed")
    if not written:
        return _title_fail("not_found")
    return {"success": True, "title": body, "original_title": new_original,
            "needs_translate": _needs_translate(body, new_original, new_mtime),
            "nfo_updated": True}


@router.post("/video/title")
def write_video_title(req: TitleWritebackRequest):
    """燈箱翻譯／復原：NFO 標題與 DB 同步改寫（先 NFO、後 DB；沒有任何回滾）。

    失敗一律 HTTP 200 ＋ {success:false, error:<code>}。`def`（非 async）→ threadpool。
    端點內不呼叫翻譯；唯讀來源只改輸出夾那份 NFO，來源零寫入。
    """
    try:
        db_path = get_db_path()
        if not db_path.exists():
            return _title_fail("not_found")
        init_db(db_path)
        repo = VideoRepository(db_path)
        video = repo.get_by_path(req.file_path)
        if video is None:
            return _title_fail("not_found")
        config = load_config()
        configured_dir_uris, path_mappings = get_configured_gallery_dirs(config)
        if not any(is_path_under_dir(video.path, uri) for uri in configured_dir_uris):
            return _title_fail("not_found")
        return _apply_title_writeback(repo, video, req, config, path_mappings)
    except ValueError:
        return _title_fail("invalid_path")
    except Exception as e:
        logger.error("[title-writeback] 未預期錯誤: %s", e)
        return _title_fail("nfo_write_failed")


@router.get("/source-status")
async def get_source_status():
    from core.source_reachability import (
        get_snapshot,
        schedule_reprobe_if_stale,
        unc_host,
        wait_for_first_probe,
    )

    await schedule_reprobe_if_stale()
    await wait_for_first_probe()
    snapshot = get_snapshot()
    out = []
    seen_displays = set()
    for path, status in snapshot.items():
        if status not in ("unreachable", "no_permission"):
            continue
        host = unc_host(path)
        display = host if host else path
        # spec F3：同一主機底下多個來源合成一個名字。去重在端點做（CD-6：顯示名由端點算、
        # 前端不做字串處理），否則 footer 會列出兩次同一台 NAS，「N 個位置」也會多算。
        if display in seen_displays:
            continue
        seen_displays.add(display)
        out.append({"path": path, "display": display, "status": status,
                    "reason": status,
                    "dsm_hint": DSM_PERMISSION_HINT if status == "no_permission" and is_synology() else None})
    return out
