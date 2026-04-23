"""
enricher.py - 舊片原地補完（NFO / 封面 / 劇照），絕對不搬移、不改名、不建目錄
"""

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from core.database import Video, VideoRepository, get_connection
from core.logger import get_logger
from core.nfo_updater import parse_nfo
from core.organizer import download_image, find_subtitle_files, generate_nfo
from core.path_utils import to_file_uri, uri_to_fs_path
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
    return merged, filled


def _write_nfo(
    fs_path: str,
    number: str,
    meta: dict,
    write_nfo: bool,
    overwrite_existing: bool,
    has_subtitle: bool,
    user_tags: List[str] = None,
) -> bool:
    if not write_nfo:
        return False

    nfo_path = str(Path(fs_path).with_suffix(".nfo"))

    if os.path.exists(nfo_path) and not overwrite_existing:
        return False

    # 若未傳入 user_tags，從 DB 讀取現有值（確保不被覆蓋）
    if user_tags is None:
        repo = VideoRepository()
        path_uri = to_file_uri(fs_path)
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


def _write_extrafanart(
    fs_path: str,
    sample_images: List[str],
    write_extrafanart: bool,
) -> int:
    if not write_extrafanart or not sample_images:
        return 0

    parent = Path(fs_path).parent
    extrafanart_dir = parent / "extrafanart"
    os.makedirs(str(extrafanart_dir), exist_ok=True)

    count = 0
    for i, url in enumerate(sample_images):
        dest = str(extrafanart_dir / f"fanart{i+1}.jpg")
        try:
            if download_image(url, dest):
                count += 1
        except Exception as e:
            logger.warning("extrafanart %d 下載失敗: %s", i + 1, e)
    return count


def enrich_single(
    file_path: str,
    number: str,
    mode: str = "fill_missing",
    write_nfo: bool = True,
    write_cover: bool = True,
    write_extrafanart: bool = False,
    overwrite_existing: bool = False,
    proxy_url: str = "",
    primary_source: str = "javbus",
    source: Optional[str] = None,
    javbus_lang: Optional[str] = None,
    scraper_data: Optional[dict] = None,
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
        return _empty

    if mode not in VALID_MODES:
        _empty.error = f"不支援的 mode: {mode}（合法值：fill_missing, db_to_sidecar, refresh_full）"
        return _empty

    try:
        fs_path = uri_to_fs_path(file_path)
    except Exception:
        fs_path = file_path

    if not os.path.exists(fs_path):
        _empty.error = "檔案不存在"
        return _empty

    repo = VideoRepository()
    meta: dict = {}
    source_used = ""
    fields_filled: List[str] = []

    if mode == "refresh_full":
        if scraper_data is None:
            scraper_data = search_jav(number, proxy_url=proxy_url, primary_source=primary_source,
                                      source=source or 'auto', javbus_lang=javbus_lang)
        if not scraper_data:
            _empty.error = f"找不到 {number} 的資料"
            return _empty
        meta = _scraper_to_meta(scraper_data)
        source_used = scraper_data.get("source", "scraper") or "scraper"

    elif mode == "db_to_sidecar":
        db_hits = repo.get_by_numbers([number])
        videos = db_hits.get(number, [])
        if not videos:
            _empty.error = f"DB 中找不到 {number} 的資料"
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
                scraper_data = search_jav(number, proxy_url=proxy_url, primary_source=primary_source,
                                          source=source or 'auto', javbus_lang=javbus_lang)
            if not scraper_data:
                _empty.error = f"找不到 {number} 的資料"
                return _empty
            supplement = _scraper_to_meta(scraper_data)
            meta, fields_filled = _merge_meta(meta, supplement)
            source_used = scraper_data.get("source", "scraper") or "scraper"

    has_subtitle = bool(find_subtitle_files(fs_path))

    # 讀取 DB 現有 user_tags，在 NFO 寫出和 DB upsert 時保留
    path_uri = to_file_uri(fs_path)
    existing_record = repo.get_by_path(path_uri)
    preserved_user_tags = existing_record.user_tags if existing_record else []

    nfo_written = False
    try:
        nfo_written = _write_nfo(
            fs_path=fs_path,
            number=number,
            meta=meta,
            write_nfo=write_nfo,
            overwrite_existing=overwrite_existing,
            has_subtitle=has_subtitle,
            user_tags=preserved_user_tags,
        )
    except PermissionError:
        _empty.error = "NFO 寫入失敗，請確認目錄寫入權限"
        return _empty

    cover_url = meta.get("cover_url", "")
    cover_written = _write_cover(
        fs_path=fs_path,
        cover_url=cover_url,
        write_cover=write_cover,
        overwrite_existing=overwrite_existing,
    )

    extrafanart_written = _write_extrafanart(
        fs_path=fs_path,
        sample_images=meta.get("sample_images", []),
        write_extrafanart=write_extrafanart,
    )

    # DB upsert 在寫檔後執行，才能知道本地封面路徑
    # db_to_sidecar 不打 scraper 也不更新 DB（metadata 不變）
    if mode in ("refresh_full", "fill_missing") and source_used not in ("db", "nfo", ""):
        local_cover = str(Path(fs_path).with_suffix(".jpg")) if cover_written else ""
        nfo_path = Path(fs_path).with_suffix(".nfo")
        nfo_mtime = nfo_path.stat().st_mtime if nfo_path.exists() else 0.0
        _db_upsert(repo, number, fs_path, meta, local_cover_path=local_cover,
                   nfo_mtime=nfo_mtime, extrafanart_written=extrafanart_written)

    # nfo_mtime 獨立更新：不論 mode/source，只要 NFO 存在就同步 DB
    # 避免 analysis 永遠視為 missing_nfo
    nfo_path = Path(fs_path).with_suffix(".nfo")
    if nfo_path.exists():
        conn = None
        try:
            path_uri = to_file_uri(fs_path)
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

    return EnrichResult(
        success=True,
        nfo_written=nfo_written,
        cover_written=cover_written,
        extrafanart_written=extrafanart_written,
        fields_filled=fields_filled,
        source_used=source_used,
        error=None,
    )


def _db_upsert(
    repo: VideoRepository, number: str, fs_path: str, meta: dict,
    local_cover_path: str = "",
    nfo_mtime: float = 0.0,
    extrafanart_written: int = 0,
) -> None:
    """更新 DB 記錄。fs_path 必須是已解析的 FS 路徑（非 file:/// URI）。"""
    try:
        path_uri = to_file_uri(fs_path)

        # 讀取現有記錄以保留 cover_path 和 user_tags
        existing = repo.get_by_path(path_uri)

        # cover_path 只存本地 file:/// URI
        # 若有本地封面路徑則轉 URI；否則保留 DB 既有值（透過傳空字串讓 upsert 不覆蓋）
        cover_uri = ""
        if local_cover_path and os.path.exists(local_cover_path):
            cover_uri = to_file_uri(local_cover_path)
        elif existing and existing.cover_path:
            cover_uri = existing.cover_path

        # 保留 DB 既有 user_tags（不被 scraper 覆蓋）
        preserved_user_tags = existing.user_tags if existing else []

        # §b1: 只有磁碟真寫出 extrafanart 檔案才更新 DB sample_images；
        # 否則保留現有值（等同 no-op），避免遠端 URL 污染 DB
        if extrafanart_written > 0:
            sample_imgs = meta.get("sample_images", [])
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
        )
        repo.upsert(video)
    except Exception as e:
        logger.warning("DB upsert 失敗: %s", e)


def _db_upsert_samples_only(repo: VideoRepository, fs_path: str, sample_images: list) -> None:
    """只更新 DB 的 sample_images 欄位（不觸碰其他欄位）。"""
    path_uri = to_file_uri(fs_path)
    repo.update_sample_images(path_uri, sample_images)


def fetch_samples_only(
    file_path: str,
    number: str,
    proxy_url: str = "",
    primary_source: str = "javbus",
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
        fs_path = uri_to_fs_path(file_path)
    except Exception:
        fs_path = file_path

    if not os.path.exists(fs_path):
        logger.warning("[fetch_samples_only] 檔案不存在: %s", fs_path)
        _empty.error = "檔案不存在"
        return _empty

    meta = search_jav(number, proxy_url=proxy_url, primary_source=primary_source,
                      source="auto", javbus_lang=None)
    if not meta:
        logger.warning("[fetch_samples_only] 找不到資料: %s", number)
        _empty.error = f"找不到 {number} 的資料"
        return _empty

    sample_images = meta.get("sample_images", [])
    count = _write_extrafanart(fs_path, sample_images, write_extrafanart=True)

    if count > 0:
        repo = VideoRepository()
        _db_upsert_samples_only(repo, fs_path, sample_images)

    logger.info("[fetch_samples_only] %s: %d samples downloaded", number, count)
    return EnrichResult(
        success=True,
        nfo_written=False,
        cover_written=False,
        extrafanart_written=count,
        fields_filled=[],
        source_used=meta.get("source", ""),
        error=None,
    )
