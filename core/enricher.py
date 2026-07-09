"""
enricher.py - 舊片原地補完（NFO / 封面 / 劇照），絕對不搬移、不改名、不建目錄
"""

import os
import shutil
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from core.config import _STEM_IMAGE_MODES
from core.database import Video, VideoRepository, get_connection
from core.logger import get_logger
from core.nfo_updater import parse_nfo
from core.organizer import crop_to_poster, download_image, find_subtitle_files, generate_nfo
from core.path_utils import to_file_uri, uri_to_fs_path, uri_to_local_fs_path
from core.scraper import search_jav

logger = get_logger(__name__)

VALID_MODES = {"fill_missing", "db_to_sidecar", "refresh_full"}


_FILL_MISSING_REQUIRED = ["title", "actresses", "maker", "director", "series", "label", "tags", "release_date"]


@dataclass
class EnrichResult:
    success: bool
    nfo_written: bool
    cover_written: bool
    extrafanart_written: int
    fields_filled: List[str]
    source_used: str
    error: Optional[str]
    reason: Optional[str] = None


def _nfo_to_meta(root: ET.Element) -> dict:
    def _text(tag: str) -> str:
        elem = root.find(tag)
        return (elem.text or "").strip() if elem is not None else ""

    actors = [
        (n.text or "").strip()
        for a in root.findall("actor")
        for n in [a.find("name")]
        if n is not None and n.text
    ]
    tags = [(e.text or "").strip() for e in root.findall("tag") if e.text]
    set_elem = root.find("set")
    series = ""
    if set_elem is not None:
        n_elem = set_elem.find("name")
        series = (n_elem.text or "").strip() if n_elem is not None else ""

    runtime_text = _text("runtime")
    duration = int(runtime_text) if runtime_text.isdigit() else None

    return {
        "title": _text("title"),
        "original_title": _text("originaltitle"),
        "actresses": actors,
        "maker": _text("studio"),
        "director": _text("director"),
        "series": series,
        "label": _text("label"),
        "tags": tags,
        "release_date": _text("premiered"),
        "duration": duration,
        "cover_url": "",
        "url": _text("website"),
    }


def _video_to_meta(video: Video) -> dict:
    return {
        "title": video.title,
        "original_title": video.original_title,
        "actresses": video.actresses or [],
        "maker": video.maker,
        "director": video.director,
        "series": video.series or "",
        "label": video.label,
        "tags": video.tags or [],
        "release_date": video.release_date,
        "duration": video.duration,
        "cover_url": video.cover_path,
        "url": "",
        "sample_images": video.sample_images or [],
    }


def _scraper_to_meta(data: dict) -> dict:
    return {
        "title": data.get("title", ""),
        "original_title": data.get("original_title", ""),
        "actresses": data.get("actors", []),
        "maker": data.get("maker", ""),
        "director": data.get("director", ""),
        "series": data.get("series", ""),
        "label": data.get("label", ""),
        "tags": data.get("tags", []),
        "release_date": data.get("date", ""),
        "duration": data.get("duration"),
        "cover_url": data.get("cover", ""),
        "url": data.get("url", ""),
        "sample_images": data.get("sample_images", []),
        # 63c-5（CD-63c-5）：唯一 summary/rating 流入 meta 的 crossing point。
        # _ 前綴 carrier（search_jav 注入）在此去前綴轉 canonical key，流入 NFO writer。
        "summary": data.get("_summary", ""),
        "rating": data.get("_rating"),
    }


def _missing_fields(meta: dict) -> List[str]:
    missing = []
    if not meta.get("title"):
        missing.append("title")
    if not meta.get("actresses"):
        missing.append("actresses")
    if not meta.get("maker"):
        missing.append("maker")
    if not meta.get("director"):
        missing.append("director")
    if not meta.get("series"):
        missing.append("series")
    if not meta.get("label"):
        missing.append("label")
    if not meta.get("tags"):
        missing.append("tags")
    if not meta.get("release_date"):
        missing.append("release_date")
    return missing


def _merge_meta(base: dict, supplement: dict) -> tuple:
    """合併 base + supplement，回傳 (merged, fields_filled)"""
    merged = dict(base)
    filled = []
    for key in _FILL_MISSING_REQUIRED:
        if not merged.get(key) and supplement.get(key):
            merged[key] = supplement[key]
            filled.append(key)
    if merged.get("cover_url") == "" and supplement.get("cover_url"):
        merged["cover_url"] = supplement["cover_url"]
    if merged.get("sample_images") is None and supplement.get("sample_images"):
        merged["sample_images"] = supplement["sample_images"]
    elif not merged.get("sample_images") and supplement.get("sample_images"):
        merged["sample_images"] = supplement["sample_images"]
    # 63c-5：summary/rating 從 supplement（scraper meta）透傳。base 通常是 DB/NFO meta
    # 無此欄（intentionally NOT carried），fill-if-empty 語意：base 有值不覆蓋。
    if not merged.get("summary") and supplement.get("summary"):
        merged["summary"] = supplement["summary"]
    if merged.get("rating") is None and supplement.get("rating") is not None:
        merged["rating"] = supplement["rating"]
    return merged, filled


def _write_nfo(
    fs_path: str,
    number: str,
    meta: dict,
    write_nfo: bool,
    overwrite_existing: bool,
    has_subtitle: bool,
    user_tags: List[str] = None,
    external_manager: str = "off",
    has_poster: bool = False,
    has_fanart: bool = False,
    fs_path_for_db: str = None,
) -> bool:
    if not write_nfo:
        return False

    nfo_path = str(Path(fs_path).with_suffix(".nfo"))

    if os.path.exists(nfo_path) and not overwrite_existing:
        return False

    # 若未傳入 user_tags，從 DB 讀取現有值（確保不被覆蓋）
    if user_tags is None:
        repo = VideoRepository()
        # TASK-91b-T1 `_for_db` 式 — fs_path_for_db 來自 caller（enrich_single 已在其內
        # 算好、DB 命名空間值）；None-fallback 用 fs_path 僅供 legacy 直呼（未傳
        # fs_path_for_db）相容，production 恆傳，accepted residual。
        # db-ns-ok: fs_path_for_db is DB round-trip value, no reverse mapping applied
        path_uri = to_file_uri(fs_path_for_db if fs_path_for_db is not None else fs_path)
        existing = repo.get_by_path(path_uri)
        user_tags = existing.user_tags if existing else []

    generate_nfo(
        number=number,
        title=meta.get("title", ""),
        original_title=meta.get("original_title", ""),
        actors=meta.get("actresses", []),
        tags=meta.get("tags", []),
        date=meta.get("release_date", ""),
        maker=meta.get("maker", ""),
        url=meta.get("url", ""),
        has_subtitle=has_subtitle,
        output_path=nfo_path,
        director=meta.get("director", ""),
        duration=meta.get("duration"),
        series=meta.get("series", ""),
        label=meta.get("label", ""),
        user_tags=user_tags,
        # 63c-5：canonical key（無 _ 前綴，已於 _scraper_to_meta crossing 去前綴）。
        # DB/NFO base meta 無此欄 → default 空 plot / 無 rating tag。
        summary=meta.get("summary", ""),
        rating=meta.get("rating"),
        # 72b-T6：外部媒體管理器模式 F3 欄位 + poster/fanart tag 切換。
        # off 模式：三者皆用 default，generate_nfo 行為 byte-identical。
        external_manager=external_manager,
        has_poster=has_poster,
        has_fanart=has_fanart,
    )
    return True


def _write_cover(
    fs_path: str,
    cover_url: str,
    write_cover: bool,
    overwrite_existing: bool,
) -> bool:
    if not write_cover:
        return False
    if not cover_url:
        return False

    cover_path = str(Path(fs_path).with_suffix(".jpg"))
    if os.path.exists(cover_path) and not overwrite_existing:
        return False

    return download_image(cover_url, cover_path)


def _write_external_images(
    fs_path: str,
    external_manager: str,
    overwrite_existing: bool,
) -> dict:
    """外部媒體管理器模式下產生 poster / fanart 圖（72b-T6 CD-7 方案 A）。

    回傳 {"poster": bool, "fanart": bool}，反映最終磁碟存在狀態，
    供 enrich_single 算 has_poster/has_fanart 傳 _write_nfo。

    gate 規則：以 cover_path.exists()（磁碟真相）為準，不以 cover_written 為準，
    避免 _write_cover skip-but-exists 邊界（.jpg 存在 + overwrite=False）喪失外部圖。

    jellyfin / emby 與 kodi 均使用 stem 長格式（{stem}-poster.jpg / {stem}-fanart.jpg），
    Kodi 在所有資料夾 layout 下均識別此命名。
    """
    # off 或未知模式：直接 no-op（防呆）
    if external_manager == "off":
        return {"poster": False, "fanart": False}

    cover_path = Path(fs_path).with_suffix(".jpg")
    stem = str(cover_path.with_suffix(""))  # 去副檔名的完整路徑前綴

    # 依模式決定目標路徑（jellyfin / emby 與 kodi 均使用 stem 長格式）
    if external_manager in _STEM_IMAGE_MODES:
        poster_path = Path(stem + "-poster.jpg")
        fanart_path = Path(stem + "-fanart.jpg")
    else:
        # 未知 external_manager 值：不產圖、不崩（防呆）
        return {"poster": False, "fanart": False}

    # 底圖不存在 → 無法產生 poster/fanart；
    # 但若 stem-poster/fanart 已獨立存在（MDCX/Javinizer 匯入）且 overwrite=False，
    # 則直接認可磁碟現況，不嘗試生成（72d-P2B）
    if not cover_path.exists():
        if not overwrite_existing:
            poster_ok = poster_path.exists()
            fanart_ok = fanart_path.exists()
            if poster_ok or fanart_ok:
                return {"poster": poster_ok, "fanart": fanart_ok}
        return {"poster": False, "fanart": False}

    poster_ok = False
    fanart_ok = False

    # fanart = 原圖複製
    if fanart_path.exists() and not overwrite_existing:
        fanart_ok = True  # 存在即算 True，NFO tag 對得上磁碟現況
    else:
        try:
            shutil.copy2(str(cover_path), str(fanart_path))
            fanart_ok = True
        except Exception as e:
            logger.warning("_write_external_images fanart 複製失敗 (%s): %s", fs_path, e)

    # poster = 裁切
    if poster_path.exists() and not overwrite_existing:
        poster_ok = True  # 同上
    else:
        try:
            poster_ok = crop_to_poster(str(cover_path), str(poster_path))
        except Exception as e:
            logger.warning("_write_external_images poster 裁切失敗 (%s): %s", fs_path, e)

    return {"poster": poster_ok, "fanart": fanart_ok}


def _write_extrafanart(
    fs_path: str,
    sample_images: List[str],
    write_extrafanart: bool,
    path_mappings: dict = None,
) -> List[str]:
    if not write_extrafanart or not sample_images:
        return []

    parent = Path(fs_path).parent
    extrafanart_dir = parent / "extrafanart"
    os.makedirs(str(extrafanart_dir), exist_ok=True)

    written_uris: List[str] = []
    for i, url in enumerate(sample_images):
        dest = str(extrafanart_dir / f"fanart{i+1}.jpg")
        try:
            if download_image(url, dest):
                written_uris.append(to_file_uri(dest, path_mappings))
        except Exception as e:
            logger.warning("extrafanart %d 下載失敗: %s", i + 1, e)
    return written_uris


def enrich_single(  # ranker-invalidate-ok: (only updates nfo_mtime, not a corpus field; corpus writes go via _db_upsert → repo.upsert which already has invalidate)
    file_path: str,
    number: str,
    mode: str = "fill_missing",
    write_nfo: bool = True,
    write_cover: bool = True,
    write_extrafanart: bool = False,
    overwrite_existing: bool = False,
    external_manager: str = "off",
    proxy_url: str = "",
    source: Optional[str] = None,
    javbus_lang: Optional[str] = None,
    scraper_data: Optional[dict] = None,
    path_mappings: dict = None,
) -> EnrichResult:
    _empty = EnrichResult(
        success=False,
        nfo_written=False,
        cover_written=False,
        extrafanart_written=0,
        fields_filled=[],
        source_used="",
        error=None,
    )

    if not number:
        _empty.error = "缺少番號"
        _empty.reason = "error"
        return _empty

    if mode not in VALID_MODES:
        _empty.error = f"不支援的 mode: {mode}（合法值：fill_missing, db_to_sidecar, refresh_full）"
        _empty.reason = "error"
        return _empty

    try:
        fs_path = uri_to_local_fs_path(file_path, path_mappings)
    except Exception:
        fs_path = file_path
    fs_path_for_db = uri_to_fs_path(file_path)  # uri-no-reverse: DB key must stay in DB's stored namespace; disk I/O uses fs_path

    if not os.path.exists(fs_path):
        _empty.error = "檔案不存在"
        _empty.reason = "error"
        return _empty

    repo = VideoRepository()
    meta: dict = {}
    source_used = ""
    fields_filled: List[str] = []

    if mode == "refresh_full":
        if scraper_data is None:
            scraper_data = search_jav(number, proxy_url=proxy_url,
                                      source=source or 'auto', javbus_lang=javbus_lang)
        if not scraper_data:
            repo.update_scrape_attempted_at(to_file_uri(fs_path_for_db), time.time())  # db-ns-ok: fs_path_for_db, DB round-trip value, no reverse mapping applied
            _empty.error = f"找不到 {number} 的資料"
            _empty.reason = "not_found"
            return _empty
        meta = _scraper_to_meta(scraper_data)
        source_used = scraper_data.get("source", "scraper") or "scraper"

    elif mode == "db_to_sidecar":
        db_hits = repo.get_by_numbers([number])
        videos = db_hits.get(number, [])
        if not videos:
            _empty.error = f"DB 中找不到 {number} 的資料"
            _empty.reason = "not_found"
            return _empty
        meta = _video_to_meta(videos[0])
        source_used = "db"

    else:
        db_hits = repo.get_by_numbers([number])
        videos = db_hits.get(number, [])

        if videos:
            meta = _video_to_meta(videos[0])
            source_used = "db"
        else:
            nfo_p = Path(fs_path).with_suffix(".nfo")
            if nfo_p.exists():
                _, root = parse_nfo(str(nfo_p))
                if root is not None:
                    meta = _nfo_to_meta(root)
                    source_used = "nfo"

        missing = _missing_fields(meta)
        if missing:
            if scraper_data is None:
                scraper_data = search_jav(number, proxy_url=proxy_url,
                                          source=source or 'auto', javbus_lang=javbus_lang)
            if not scraper_data:
                repo.update_scrape_attempted_at(to_file_uri(fs_path_for_db), time.time())  # db-ns-ok: fs_path_for_db, DB round-trip value, no reverse mapping applied
                _empty.error = f"找不到 {number} 的資料"
                _empty.reason = "not_found"
                return _empty
            supplement = _scraper_to_meta(scraper_data)
            meta, fields_filled = _merge_meta(meta, supplement)
            source_used = scraper_data.get("source", "scraper") or "scraper"

    has_subtitle = bool(find_subtitle_files(fs_path))

    # 讀取 DB 現有 user_tags，在 NFO 寫出和 DB upsert 時保留
    path_uri = to_file_uri(fs_path_for_db)  # db-ns-ok: fs_path_for_db, DB round-trip value, no reverse mapping applied
    existing_record = repo.get_by_path(path_uri)
    preserved_user_tags = existing_record.user_tags if existing_record else []

    cover_url = meta.get("cover_url", "")

    nfo_written = False
    cover_written = False

    if external_manager != "off":
        # 72b-T6 外部媒體管理器寫序：cover → external images → NFO
        # NFO 必須在圖片後寫入，才能取得 has_poster/has_fanart 真值。
        # jellyfin / emby 與 kodi 均使用 stem 長格式（無 per-folder 切換邏輯）。
        cover_written = _write_cover(
            fs_path=fs_path,
            cover_url=cover_url,
            write_cover=write_cover,
            overwrite_existing=overwrite_existing,
        )
        imgs = _write_external_images(
            fs_path=fs_path,
            external_manager=external_manager,
            overwrite_existing=overwrite_existing,
        )
        try:
            nfo_written = _write_nfo(
                fs_path=fs_path,
                number=number,
                meta=meta,
                write_nfo=write_nfo,
                overwrite_existing=overwrite_existing,
                has_subtitle=has_subtitle,
                user_tags=preserved_user_tags,
                external_manager=external_manager,
                has_poster=imgs["poster"],
                has_fanart=imgs["fanart"],
                fs_path_for_db=fs_path_for_db,
            )
        except PermissionError:
            _empty.error = "NFO 寫入失敗，請確認目錄寫入權限"
            _empty.reason = "error"
            return _empty
    else:
        # off 模式：維持原寫序（NFO 先、cover 後），行為 byte-identical
        try:
            nfo_written = _write_nfo(
                fs_path=fs_path,
                number=number,
                meta=meta,
                write_nfo=write_nfo,
                overwrite_existing=overwrite_existing,
                has_subtitle=has_subtitle,
                user_tags=preserved_user_tags,
                fs_path_for_db=fs_path_for_db,
            )
        except PermissionError:
            _empty.error = "NFO 寫入失敗，請確認目錄寫入權限"
            _empty.reason = "error"
            return _empty

        cover_written = _write_cover(
            fs_path=fs_path,
            cover_url=cover_url,
            write_cover=write_cover,
            overwrite_existing=overwrite_existing,
        )

    written_uris = _write_extrafanart(
        fs_path=fs_path,
        sample_images=meta.get("sample_images", []),
        write_extrafanart=write_extrafanart,
        path_mappings=path_mappings,
    )
    extrafanart_written = len(written_uris)

    # DB upsert 在寫檔後執行，才能知道本地封面路徑
    # db_to_sidecar 不打 scraper 也不更新 DB（metadata 不變）
    if mode in ("refresh_full", "fill_missing") and source_used not in ("db", "nfo", ""):
        local_cover = str(Path(fs_path).with_suffix(".jpg")) if cover_written else ""
        nfo_path = Path(fs_path).with_suffix(".nfo")
        nfo_mtime = nfo_path.stat().st_mtime if nfo_path.exists() else 0.0
        # wrapper callsite decision point; helper itself: enforced at callsites
        # db-ns-ok: fs_path_for_db passed through to _db_upsert's internal primitive sink
        _db_upsert(repo, number, fs_path_for_db, meta, local_cover_path=local_cover,
                   nfo_mtime=nfo_mtime, written_uris=written_uris, path_mappings=path_mappings)

    # nfo_mtime 獨立更新：不論 mode/source，只要 NFO 存在就同步 DB
    # 避免 analysis 永遠視為 missing_nfo
    nfo_path = Path(fs_path).with_suffix(".nfo")
    if nfo_path.exists():
        conn = None
        try:
            path_uri = to_file_uri(fs_path_for_db)  # db-ns-ok: fs_path_for_db, DB round-trip value, no reverse mapping applied
            nfo_mt = nfo_path.stat().st_mtime
            conn = get_connection(repo.db_path)
            conn.execute(
                "UPDATE videos SET nfo_mtime = ? WHERE path = ? AND (nfo_mtime IS NULL OR nfo_mtime = 0)",
                (nfo_mt, path_uri),
            )
            conn.commit()
        except Exception as e:
            logger.warning("nfo_mtime 更新失敗 (%s): %s", number, e)
        finally:
            if conn:
                conn.close()

    # reason=hit 必須是「前端 /thumb 真的服務得到」。/thumb（scanner.py get_thumb）
    # 有兩道 gate，兩道都過才服務得到，reason=hit 必須同時鏡射：
    #   gate 1（scanner.py:1276-1277）：DB cover_path 非空，否則 404。
    #   gate 2（scanner.py:1290/1300/1332-1333）：cache miss 或 disabled 時要讀
    #     實體封面檔（uri_to_local_fs_path 反解後 generate / fallback FileResponse），
    #     檔不在 → 404。（cache hit 於 :1263 直接 serve WebP 不碰實體檔，見下方 false-negative）
    # 故不能只查 DB cover_path 非空（只鏡射 gate 1，Codex PR #98 P2）：DB 有記
    # cover_path、但該實體封面檔已被刪/移／path_mapping 失效解不到時，/thumb 於
    # cache miss/disabled 會 404 → 飛入破圖，卻誤計 hit。
    # 亦不能用磁碟 sidecar 真相（Path(fs_path).with_suffix('.jpg')）判：磁碟有 .jpg
    # 但 DB cover_path 空（散落 sidecar 未入 DB／db·nfo-sourced 命中跳過 :514
    # _db_upsert）會漏 gate 1（Codex P1，v0.11.9）。故重讀 DB 最終 cover_path，
    # 並用 /thumb 同一組解析（uri_to_local_fs_path + 同 path_mappings）確認實體檔存在。
    # 此重讀在所有寫檔 + _db_upsert + nfo_mtime UPDATE 之後（同步、已 commit），
    # 故看到的是最終 DB 狀態。
    # 已知並接受的 false-negative（安全方向）：cache hit（stale WebP 已快取）但實體
    # 封面檔已刪時，/thumb 仍能從快取 serve（:1263），此處卻判 no_cover。代價是「服務
    # 得到的封面不飛入」（不破圖）；反向 false-positive（判 hit 卻 404 破圖）代價更高，
    # 故偏保守。
    # db-ns-ok: fs_path_for_db, DB round-trip key（同 :437 path_uri）
    final_row = repo.get_by_path(to_file_uri(fs_path_for_db))
    cover_uri = final_row.cover_path if final_row else ''
    has_servable_cover = bool(cover_uri) and os.path.exists(
        uri_to_local_fs_path(cover_uri, path_mappings)
    )

    return EnrichResult(
        success=True,
        nfo_written=nfo_written,
        cover_written=cover_written,
        extrafanart_written=extrafanart_written,
        fields_filled=fields_filled,
        source_used=source_used,
        error=None,
        reason=("hit" if has_servable_cover else "no_cover"),
    )


def _db_upsert(
    repo: VideoRepository, number: str, fs_path: str, meta: dict,
    local_cover_path: str = "",
    nfo_mtime: float = 0.0,
    written_uris: List[str] = None,
    path_mappings: dict = None,
) -> None:
    """更新 DB 記錄。fs_path 為 DB key 專用（不做反解），必須是「DB 儲存命名空間」的 FS 路徑。

    db-ns-ok: enforced at callsites — 本體內 to_file_uri(fs_path) primitive sink 命名空間
    正確性委派給呼叫端保證（TASK-91b-T1 wrapper sink 登記，callsite 各自標記）。
    """
    try:
        path_uri = to_file_uri(fs_path)

        # 讀取現有記錄以保留 cover_path 和 user_tags
        existing = repo.get_by_path(path_uri)

        # cover_path 只存本地 file:/// URI
        # 若有本地封面路徑則轉 URI；否則保留 DB 既有值（透過傳空字串讓 upsert 不覆蓋）
        cover_uri = ""
        if local_cover_path and os.path.exists(local_cover_path):
            cover_uri = to_file_uri(local_cover_path, path_mappings)
        elif existing and existing.cover_path:
            cover_uri = existing.cover_path

        # 保留 DB 既有 user_tags（不被 scraper 覆蓋）
        preserved_user_tags = existing.user_tags if existing else []

        # TASK-89a-T5 (CD-89a-5 / Codex C2): 保留 DB 既有 output_dir（enricher 從不
        # 自己生成 output_dir，純粹讀出既有值原樣塞回，作為 T1 DB CASE-WHEN 之上的
        # defense-in-depth，避免補完/重刮把 producer 寫入的 output_dir 洗掉）
        preserved_output_dir = existing.output_dir if existing else ''

        # §b1 / Codex P1: 只有磁碟真寫出 extrafanart 檔案才更新 DB sample_images；
        # 使用 written_uris（local file:/// URIs），不寫 scraper 遠端 URL
        if written_uris:
            sample_imgs = written_uris
        else:
            sample_imgs = existing.sample_images if existing else []

        video = Video(
            path=path_uri,
            number=number,
            title=meta.get("title", ""),
            original_title=meta.get("original_title", ""),
            actresses=meta.get("actresses", []),
            maker=meta.get("maker", ""),
            director=meta.get("director", ""),
            series=meta.get("series") or None,
            label=meta.get("label", ""),
            tags=meta.get("tags", []),
            user_tags=preserved_user_tags,
            sample_images=sample_imgs,
            duration=meta.get("duration"),
            cover_path=cover_uri,
            release_date=meta.get("release_date", ""),
            nfo_mtime=nfo_mtime,
            output_dir=preserved_output_dir,
            scrape_attempted_at=time.time(),
        )
        repo.upsert(video)
    except Exception as e:
        logger.warning("DB upsert 失敗: %s", e)


def _db_upsert_samples_only(repo: VideoRepository, fs_path: str, sample_images: list) -> None:
    """只更新 DB 的 sample_images 欄位（不觸碰其他欄位）。fs_path 為 DB key 專用（不做反解）。

    db-ns-ok: enforced at callsites — 本體內 to_file_uri(fs_path) primitive sink 命名空間
    正確性委派給呼叫端保證（TASK-91b-T1 wrapper sink 登記，callsite 各自標記）。
    """
    path_uri = to_file_uri(fs_path)
    repo.update_sample_images(path_uri, sample_images)


def fetch_samples_only(
    file_path: str,
    number: str,
    proxy_url: str = "",
    path_mappings: dict = None,
) -> EnrichResult:
    """只補抓劇照：呼叫 scraper → 下載 extrafanart → 更新 DB sample_images。
    不寫 NFO / cover / 其他欄位。
    """
    _empty = EnrichResult(
        success=False,
        nfo_written=False,
        cover_written=False,
        extrafanart_written=0,
        fields_filled=[],
        source_used="",
        error=None,
    )

    try:
        fs_path = uri_to_local_fs_path(file_path, path_mappings)
    except Exception:
        fs_path = file_path
    fs_path_for_db = uri_to_fs_path(file_path)  # uri-no-reverse: DB key must stay in DB's stored namespace; disk I/O uses fs_path

    if not os.path.exists(fs_path):
        logger.warning("[fetch_samples_only] 檔案不存在: %s", fs_path)
        _empty.error = "檔案不存在"
        return _empty

    meta = search_jav(number, proxy_url=proxy_url,
                      source="auto", javbus_lang=None)
    if not meta:
        logger.warning("[fetch_samples_only] 找不到資料: %s", number)
        _empty.error = f"找不到 {number} 的資料"
        return _empty

    sample_images = meta.get("sample_images", [])
    written_uris = _write_extrafanart(fs_path, sample_images, write_extrafanart=True, path_mappings=path_mappings)

    if written_uris:
        repo = VideoRepository()
        # db-ns-ok: fs_path_for_db, DB round-trip value passed to wrapper sink
        _db_upsert_samples_only(repo, fs_path_for_db, written_uris)

    logger.info("[fetch_samples_only] %s: %d samples downloaded", number, len(written_uris))
    return EnrichResult(
        success=True,
        nfo_written=False,
        cover_written=False,
        extrafanart_written=len(written_uris),
        fields_filled=[],
        source_used=meta.get("source", ""),
        error=None,
    )


def resolve_nfo_cover_paths(file_path: str, path_mappings: dict = None) -> tuple:
    """由影片 file_path 推導目標 NFO / cover 的 FS 路徑。

    復用 enrich_single / _write_nfo / _write_cover 的同一套路徑邏輯：
    先以 uri_to_local_fs_path() 解析（fallback 原值），再 with_suffix。
    回傳 (nfo_path, cover_path)，兩者皆為當前環境 FS 字串路徑。

    ⚠️ 路徑邏輯必須與 `_write_nfo`（with_suffix(".nfo")）/ `_write_cover`
    （with_suffix(".jpg")）保持同步——62a-1 的 refresh_full 分裂守衛
    （web/routers/scraper.py enrich_single_endpoint）靠本函數判斷檔案是否已存在。
    若 writer 改了 cover 命名（poster.jpg / .png / fanart 等）或 fs_path 推導，
    本函數要一起改，否則守衛會悄悄檢查錯路徑（false-allow 重現分裂 / false-block 打爆缺封面 quick-enrich）。
    """
    try:
        fs_path = uri_to_local_fs_path(file_path, path_mappings)
    except Exception:
        fs_path = file_path
    nfo_path = str(Path(fs_path).with_suffix(".nfo"))
    cover_path = str(Path(fs_path).with_suffix(".jpg"))
    return nfo_path, cover_path
