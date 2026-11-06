"""
Gallery media 路由 - 圖片／影片代理服務（TASK-150a-T1 自 web/routers/scanner.py 搬出）

端點：
- GET  /api/gallery/image                 — 代理圖片請求（解決 file:// 限制）
- GET  /api/gallery/video                 — 代理影片請求，支援 Range 請求（影片 seek）
- GET  /api/gallery/player                — 影片播放頁面（HTML5 player）
"""

import json
import os
import time
from pathlib import Path
from typing import List
from urllib.parse import quote, unquote

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response, FileResponse, HTMLResponse, StreamingResponse

from core.path_utils import to_file_uri, is_path_under_dir, uri_to_fs_path, uri_to_local_fs_path
from core.config import load_config, iter_gallery_sources, get_gallery_source_paths
from core.database import get_db_path, VideoRepository
from core.multipart_group import resolve_group
from core.video_extensions import get_proxy_extensions
from core.readonly_paths import resolve_output_root
from core import thumbnail_cache
from core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/gallery", tags=["gallery"])

# TASK-73: 白名單目錄 dual-form TTL 快取（key: (raw_dir, frozen_mappings), value: (forms, expire_monotonic)）
_dir_forms_cache: dict = {}
_DIR_FORMS_TTL = 60.0  # 秒


def safe_realpath(fs_path: str, endpoint_label: str) -> str:
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
    fs_dir = uri_to_fs_path(raw_dir)  # uri-no-reverse: native config path (DirectoryConfig.path), no DB-mapped namespace
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

    # 0. 字面式早退（PR#178 R2 缺陷C）：在任何 realpath 之前，用純字面（lexical）URI
    # 判斷來源是否已知斷線。safe_realpath 與 _dir_candidate_forms 都會對位在斷線來源上
    # 的路徑呼叫 os.path.realpath()（跑在 sync def 的 threadpool worker），滿頁封面請求
    # 會在走到下方既有 fast-fail 之前就先一張一張卡在遠端逾時——這裡把判斷挪到任何遠端
    # IO 之前，不呼叫 realpath / safe_realpath / _dir_candidate_forms / os.path.exists。
    # config/gallery_config/path_mappings 從原本「3. 目錄白名單」段落整段上移到這裡
    # （不多呼叫一次 load_config()，下方該段落改用這裡算好的變數）。
    config = load_config()
    gallery_config = config.get('gallery', {})
    path_mappings = gallery_config.get('path_mappings', {})

    from core.source_reachability import is_path_on_unreachable_source
    lexical_uri = to_file_uri(os.path.normpath(local_path), path_mappings)
    if is_path_on_unreachable_source(lexical_uri, gallery_config):
        return Response(status_code=404, content="來源目前無法存取")

    # 1. 解析 .. 並追蹤 symlink target（realpath）；FUSE/WinFsp OSError 時降級 normpath
    local_path = safe_realpath(local_path, "get_image")

    # 2. 副檔名白名單（只允許圖片格式）
    ext = os.path.splitext(local_path)[1].lower()
    mime_types = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.webp': 'image/webp',
        '.bmp': 'image/bmp',
        '.tbn': 'image/jpeg',  # Kodi ecosystem: JPEG with a .tbn suffix
    }
    if ext not in mime_types:
        logger.warning("get_image: 拒絕非圖片副檔名請求 ext=%s", ext)
        return Response(status_code=403, content="不允許的檔案類型")

    # 3. 目錄白名單：只允許 gallery.directories 底下的檔案
    # config / gallery_config / path_mappings 已於上方「0. 字面式早退」段落算好（不重複
    # 呼叫 load_config()）。

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

    # 來源可達性已在上方「0. 字面式早退」判過（PR#178 R2）。這裡不再判第二次：
    # 兩處用的是同一組來源前綴，只差 normpath vs realpath 形式，對非 symlink 路徑
    # 完全等價 —— 留著第二道會變成沒有任何測試守得住的死碼（mutation M5 SURVIVED），
    # 而「守不住的守衛」比沒有守衛更糟（它會讓全綠變成假的）。
    # 放棄的涵蓋範圍：realpath 之後才落進斷線來源的 symlink（那種情況 realpath 本身
    # 就已經先付過遠端成本，第二道也救不了牆），行為等同本 branch 之前。

    # 4. 檔案存在性
    if not os.path.exists(local_path):
        return Response(status_code=404, content="檔案不存在")

    media_type = mime_types[ext]
    return FileResponse(
        local_path,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/video")
def get_video(request: Request, path: str = Query(..., description="影片路徑（file:/// URI 或 FS 路徑）")):
    """代理影片請求，解決瀏覽器無法開啟 file:/// URI 的問題"""
    # URL decode
    path = unquote(path)

    # TASK-91-T2b #12：config/gallery_config/path_mappings 搬到 local_path 計算之前，
    # 讓 uri_to_local_fs_path 取用得到 path_mappings（原本晚於 local_path 賦值，會 NameError）。
    config = load_config()
    gallery_config = config.get('gallery', {})
    path_mappings = gallery_config.get('path_mappings', {})

    # 1. 轉換為 FS 路徑（WSL+UNC path_mappings 環境下反解成真正能 open() 的本機路徑）
    local_path = uri_to_local_fs_path(path, path_mappings)

    # 2. 解析 .. 並追蹤 symlink target（realpath）；FUSE/WinFsp OSError 時降級 normpath
    local_path = safe_realpath(local_path, "get_video")

    # 3. 副檔名白名單（用 realpath/normpath 解析後的路徑）
    #    使用 get_proxy_extensions() = user config ∩ SAFE_PROXY_EXTENSIONS
    allowed_extensions = get_proxy_extensions(config)
    ext = os.path.splitext(local_path)[1].lower()
    if ext not in allowed_extensions:
        logger.warning("get_video: 拒絕非影片副檔名請求 ext=%s", ext)
        return Response(status_code=403, content="不允許的檔案類型")

    # 4. 目錄白名單：只允許 gallery.directories 底下的檔案
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


def _render_player_html(
    *,
    html_lang_safe: str,
    filename: str,
    src: str,
    hint_text_network: str,
    hint_text_format: str,
    extra_style: str = '',
    video_open_attrs: str = '',
    video_data_attrs: str = '',
    extra_body: str = '',
    extra_script: str = '',
) -> str:
    """播放頁 HTML（單檔與分集共用同一份骨架）。

    feature/122 T5 originally 為分集分支抄了一份完整的頁面骨架，只差一條 CSS、
    兩個 video 屬性、一個 div 和一個 script tag——那份重複會在下次改播放頁樣式
    或 error hint 時靜默漂移（/simplify reuse 條目）。骨架收成一處，差異走參數。

    所有插入點都由呼叫端**先 escape 過**才傳進來（`html_escape(..., quote=True)`），
    本函式只做字串組裝、不做 escape，維持與原本兩份 f-string 逐位元組相同的輸出。
    """
    return f"""<!DOCTYPE html>
<html lang="{html_lang_safe}">
<head>
    <meta charset="UTF-8">
    <title>{filename} - OpenAver</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ background: #000; display: flex; align-items: center; justify-content: center; height: 100vh; }}
        video {{ max-width: 100%; max-height: 100vh; }}
        #video-error-hint-network, #video-error-hint-format {{ color: #fff; padding: 1.5rem; text-align: center; max-width: 32rem; line-height: 1.6; }}{extra_style}
    </style>
</head>
<body>
    <video {video_open_attrs}controls autoplay src="{src}"{video_data_attrs} onerror="this.style.display='none';var c=this.error?this.error.code:0;document.getElementById((c===3||c===4)?'video-error-hint-format':'video-error-hint-network').style.display='flex'"></video>{extra_body}
    <div id="video-error-hint-network" style="display:none">{hint_text_network}</div>
    <div id="video-error-hint-format" style="display:none">{hint_text_format}</div>{extra_script}
</body>
</html>"""


@router.get("/player")
def video_player(path: str = Query(..., description="影片路徑（file:/// URI 或 FS 路徑）")):
    """影片播放頁面 — 用 HTML5 <video> 標籤在新分頁播放"""
    from html import escape as html_escape
    from core.i18n import SUPPORTED_LOCALES, t as i18n_t

    video_url = f"/api/gallery/video?path={quote(path, safe='')}"

    # 從路徑取檔名作為標題（escape 防 XSS）
    filename = path.rsplit('/', 1)[-1].rsplit('\\', 1)[-1]
    if filename.startswith('file:'):
        filename = 'Video Player'
    filename = html_escape(filename)

    # video_url 也做 HTML escape（防禦性，避免 src 屬性注入）
    video_url_safe = html_escape(video_url)

    config = load_config()
    locale = (config.get('general') or {}).get('locale') or ''
    # 本端點唯一的 locale 正規化點，lang 屬性與提示文字都吃它
    html_lang = locale if isinstance(locale, str) and locale in SUPPORTED_LOCALES else "zh-TW"
    html_lang_safe = html_escape(html_lang)
    hint_text_network = html_escape(i18n_t('showcase.video.player_unavailable', locale=html_lang))
    hint_text_format = html_escape(i18n_t('showcase.video.player_unavailable_format', locale=html_lang))

    gallery_config = config.get('gallery', {})
    path_mappings = gallery_config.get('path_mappings', {})

    group = None
    try:
        db_path = get_db_path()
        if db_path.exists():
            repo = VideoRepository(db_path)
            v = repo.get_by_path(path)
            if v is not None:
                group = resolve_group(repo, path, path_mappings, folder_source_uri=v.path)
    except Exception:
        logger.warning("video_player: 分組查詢失敗，退回單檔播放", exc_info=True)
        group = None

    if group is not None and len(group.members) > 1:
        parts_urls = [f"/api/gallery/video?path={quote(m.path, safe='')}" for m in group.members]
        data_parts_json = html_escape(json.dumps(parts_urls), quote=True)
        part_label_template = html_escape(i18n_t('showcase.video.part_progress', locale=html_lang), quote=True)
        first_src = html_escape(parts_urls[0])
        return HTMLResponse(content=_render_player_html(
            html_lang_safe=html_lang_safe,
            filename=filename,
            src=first_src,
            hint_text_network=hint_text_network,
            hint_text_format=hint_text_format,
            extra_style=(
                "\n        #oa-player-progress { position: fixed; top: 1rem; left: 1rem;"
                " z-index: 1; pointer-events: none; color: #fff; font: 14px/1.4 sans-serif; }"
            ),
            video_open_attrs='id="oa-player" ',
            video_data_attrs=(
                f' data-parts="{data_parts_json}"'
                f' data-part-label-template="{part_label_template}"'
            ),
            extra_body='\n    <div id="oa-player-progress"></div>',
            extra_script='\n    <script type="module" src="/static/js/pages/player.js"></script>',
        ))

    return HTMLResponse(content=_render_player_html(
        html_lang_safe=html_lang_safe,
        filename=filename,
        src=video_url_safe,
        hint_text_network=hint_text_network,
        hint_text_format=hint_text_format,
    ))


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
    # TASK-91-T2b #9：is_known_cover_path 內部用「不帶 path_mappings 的 to_file_uri」
    # 跟 DB 存的 mapped-namespace URI 字面比對（round-trip 契約），若改餵反解後的本機
    # 路徑進去，to_file_uri 落 fallback 分支產生四斜線怪字串、永遠比對不到 → 誤判
    # 「封面不在快取記錄中」（本 task 發現的卡片未涵蓋 gap，見 report）。
    # 修法：DB 背書比對維持用裸 uri_to_fs_path（與改動前行為等價，零回歸）；
    # 反解只用在「即將真的碰磁碟」的 cover_fs（generate/fallback FileResponse/os.path.isfile）。
    gallery_config = load_config().get('gallery', {})
    path_mappings = gallery_config.get('path_mappings', {})
    cover_fs_for_db = uri_to_fs_path(video.cover_path)  # uri-no-reverse: DB round-trip comparison-only (is_known_cover_path), real disk path uses uri_to_local_fs_path below  # db-ns-ok: _for_db, sourced from existing DB URI (uri_to_fs_path, not reverse-mapped), round-trips to mapped namespace
    if not repo.is_known_cover_path(cover_fs_for_db):
        return Response(status_code=404, content="封面不在快取記錄中")
    cover_fs = uri_to_local_fs_path(video.cover_path, path_mappings)

    from core.source_reachability import is_path_on_unreachable_source
    cover_uri = to_file_uri(cover_fs, path_mappings)
    if is_path_on_unreachable_source(cover_uri, gallery_config):
        return Response(status_code=404, content="來源目前無法存取")

    # P2-B（TASK-71c）：miss 路徑 gate disabled，不重生 WebP。
    # 用戶關閉快取 + clear 後，stale 分頁的 miss 請求不應重建剛清的目錄。
    # disabled → fall through 到下方 fallback 原圖（D6 不破圖）。
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
        # TASK-91-T2b #10：同函式同一個 path_mappings（上方 #9 已算好）
        fresh_fs = uri_to_local_fs_path(fresh.cover_path, path_mappings)
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


@router.post("/thumb/clear")
def thumb_clear():
    """DB-safe 清空封面縮圖快取（feature/71b T2）。

    僅 rmtree output/thumb/（CD-71b-3）——**絕不碰 videos DB**。前端在
    「關閉縮圖快取 toggle 且存檔成功」後才 fire-and-forget POST 此端點（先存才清）。
    冪等：clear_all() 對缺目錄 no-op。sync def → Starlette threadpool。
    """
    thumbnail_cache.clear_all()
    return {"cleared": True}
