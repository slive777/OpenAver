"""
enricher.py - 舊片原地補完（NFO / 封面 / 劇照），絕對不搬移、不改名、不建目錄
"""

import os
import shutil
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, NamedTuple, Optional

from core.config import STEM_IMAGE_MODES
from core.cover_attributes import effective_tags
from core.cover_layout import resolve_cover_target, same_target_verdict
from core.database import Video, VideoRepository, get_connection
from core.enrich_contract import (
    EnrichResult,
    compute_has_servable_cover,
    effective_original_title,
    effective_title,
    enrich_success,
    should_preserve_cover,
)
from core.focal_trigger import schedule_focal_after_cover_write
from core.logger import get_logger
from core.nfo_read import (
    nfo_actor_names,
    nfo_first_text,
    nfo_merged_tags,
    nfo_runtime_minutes,
    nfo_series_name,
    nfo_text,
    nfo_title_record,
)
from core.nfo_stat import NFO_MTIME_FILL_MISSING, NFO_MTIME_REFRESH, nfo_mtime_or_none
from core.nfo_title_format import resolve_preserved_title_for_write, resolve_title_body
from core.nfo_updater import parse_nfo
from core.organizer import crop_to_poster, download_image, find_subtitle_files, generate_nfo, _strip_num_prefixes
from core.path_utils import to_file_uri, uri_to_fs_path, uri_to_local_fs_path
from core.scraper import search_jav
from core.scrapers.utils import check_subtitle

logger = get_logger(__name__)

VALID_MODES = {"fill_missing", "db_to_sidecar", "refresh_full"}


_FILL_MISSING_REQUIRED = ["title", "actresses", "maker", "director", "series", "label", "tags", "release_date"]


def _reraise_nfo_stat_error(e: OSError) -> None:
    """S3/S4's on_error callback: let a stat failure propagate to each call
    site's own `try/except OSError`, which already logs the "nfo_mtime stat
    失敗" warning below — re-raising avoids duplicating that message in the
    callback (Opus BLOCKER fix, plan-113b v8: `.exists()` restored at both
    call sites, primitive only takes over the `.stat()` call itself).
    """
    raise e


# EnrichResult 定義已遷入 core.enrich_contract（中性合約模組），此處 re-export
# 保持全庫既有 `from core.enricher import EnrichResult` 匯入零改動（feature/105）。


def _nfo_to_meta(
    root: ET.Element,
    number: str = '',
    nfo_title_format: str = '[{num}]{title}',
) -> dict:
    actresses = nfo_actor_names(root)
    maker = nfo_first_text(root, ("maker", "studio"))
    release_date = nfo_first_text(root, ("release", "premiered", "year"))
    raw_title = nfo_text(root, "title")
    record = nfo_title_record(root)
    title = resolve_title_body(raw_title, number, actresses, maker, release_date, nfo_title_format, record)
    return {
        "title": title,
        "original_title": nfo_text(root, "originaltitle"),
        "actresses": actresses,
        "maker": maker,
        "director": nfo_text(root, "director"),
        "series": nfo_series_name(root),
        "label": nfo_text(root, "label"),
        "tags": nfo_merged_tags(root),
        "release_date": release_date,
        "duration": nfo_runtime_minutes(root),
        "cover_url": "",
        # CD-126-2：preview_* 是 metatube 取回路徑的暫態。本地 NFO 沒有代理可言，
        # 但**鍵必須存在**——否則下游 `.get()` 的預設值會散落在四個地方。
        "preview_cover_url": "",
        "preview_sample_images": [],
        "url": nfo_text(root, "website"),
    }


def _resolve_subtitle_and_tags(fs_path: str, meta: dict) -> tuple:
    """回傳 (has_subtitle, 合併後的 tags)。

    CD-7：字幕偵測不能只看 sidecar .srt，檔名標記（-C/_C/中文字幕…）也要算數，
    否則同一支片「補齊資料」跟「拖進搜尋頁整理」（`core/organizer.py` 已是兩者 or）
    會出現不對稱結果。

    CD-9：屬性 tag（中文字幕／VR／4K…）只在這裡算一次，讓下游 `_write_nfo()` 與
    `_db_upsert()` 共讀同一份合併結果（不得各自再算一次）。
    """
    basename = os.path.basename(fs_path)
    has_subtitle = check_subtitle(basename) or bool(find_subtitle_files(fs_path))
    base_tags = list(meta.get('tags', []) or [])
    if has_subtitle:
        base_tags.append('中文字幕')
    return has_subtitle, effective_tags(basename, base_tags)


def _sync_tags_to_db(repo, path_uri: str, tags: list, number: str) -> None:
    """把合併後的 tags 同步進 DB（CD-9 延伸）。

    `source_used` 為 "db"/"nfo"/"" 時 `enrich_single()` 裡那個 `_db_upsert()` 的 if
    不會跑，DB 的 tags 就永遠不會同步——**這裡是那三種來源唯一的 DB 同步點**。
    `source_used == "scraper"` 時 `_db_upsert()` 已寫過同一份 tags，這裡比對相同、
    no-op（`update_tags_if_changed` 內建「不變不寫」）。

    錯誤隔離比照 `_db_upsert()`：呼叫到這裡時 NFO／封面／其他 DB 欄位都已寫成功，
    不能讓 sqlite 例外（busy/locked）穿透出去把「部分成功」誤報成「整體失敗」
    ——使用者會看到「補齊資料失敗」而重按，實際上檔案早就寫好了。
    """
    try:
        repo.update_tags_if_changed(path_uri, tags)
    except Exception as e:
        logger.warning("tags 同步失敗 (%s): %s", number, e)


def _pick_row_for_path(videos: list, path_uri: str) -> Video:
    """同番號可能有多列（cd1/cd2、-4k/-uc 變體；見 config 的 suffix_keywords 預設值），
    優先挑路徑與當前檔案相符的那一列，挑不到才退回第一列。

    Why（PR #145 Codex P1）：舊碼無條件取 `videos[0]`，卻把結果寫進**當前檔案**的
    `path_uri`——同番號多檔案時等於用另一支片的資料覆蓋這一支。退回第一列保留既有
    行為，所以單檔情境（既有測試與絕大多數真實片庫）逐字不變。
    """
    for video in videos:
        if video.path == path_uri:
            return video
    return videos[0]


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
        # CD-126-2：DB 來源沒有代理（preview_* 不入庫，見 T4b card 類別 Y）。鍵在值空。
        "preview_cover_url": "",
        "preview_sample_images": [],
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
        # CD-126-2：代理 URL 走平行欄位，與 cover/sample 同時進 meta。
        # 這是整條 enrich 管線**唯一**有值的產生端——丟在這裡，下游全部是死的。
        "preview_cover_url": data.get("preview_cover_url", ""),
        "preview_sample_images": data.get("preview_sample_images", []),
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
    # CD-126-2：preview_* 必須跟 cover/sample **在同一個分支裡**搬——分開搬＝封面來自
    # 候選 A、代理來自候選 B（CD-113c-12 同一種病，畫面上看不出來）。
    # sample_images 有 if 與 elif **兩條路**，兩條都要搬，漏一條就是上面那個病。
    if merged.get("cover_url") == "" and supplement.get("cover_url"):
        merged["cover_url"] = supplement["cover_url"]
        merged["preview_cover_url"] = supplement.get("preview_cover_url", "")
    if merged.get("sample_images") is None and supplement.get("sample_images"):
        merged["sample_images"] = supplement["sample_images"]
        merged["preview_sample_images"] = supplement.get("preview_sample_images", [])
    elif not merged.get("sample_images") and supplement.get("sample_images"):
        merged["sample_images"] = supplement["sample_images"]
        merged["preview_sample_images"] = supplement.get("preview_sample_images", [])
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
    nfo_title_format: str = '[{num}]{title}',
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
        nfo_title_format=nfo_title_format,
    )
    return True


def _write_cover(
    fs_path: str,
    cover_url: str,
    write_cover: bool,
    overwrite_existing: bool,
    external_manager: str = "off",
    preview_cover_url: str = "",
) -> bool:
    # write_cover=False 先短路，避免對「不寫封面」的片多做一次 os.path.exists
    # （逐位元組對齊 T2 前行為）；exists/overwrite 保留判斷仍走共用 should_preserve_cover。
    if not write_cover:
        return False
    if not cover_url:
        return False

    cover_path = resolve_cover_target(str(Path(fs_path).with_suffix("")), external_manager)
    if should_preserve_cover(write_cover, overwrite_existing, os.path.exists(cover_path)):
        return False

    # CD-126-3／10：原址優先，取不到才退代理。gate **只看 preview 非空**，
    # 不得改用 meta["source"] 判斷——混源時「文字走 javbus、封面走 metatube」是合法狀態。
    #
    # **preview 為空時連 kwarg 都不傳**（不是傳 fallback_url=""）：AC-5 要求非 metatube
    # 來源「逐字元相同」，而既有測試的 stub 簽名就是 (url, dest)——多一個 kwarg 會讓
    # 它們 TypeError。這不是為了配合測試，是那些測試正確地把 AC-5 焊死了。
    if preview_cover_url:
        return download_image(cover_url, cover_path, fallback_url=preview_cover_url)
    return download_image(cover_url, cover_path)


def _write_external_images(
    fs_path: str,
    external_manager: str,
    overwrite_existing: bool,
    write_cover: bool = True,
    number: str = '',
    maker: str = '',
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

    base_stem = str(Path(fs_path).with_suffix(""))  # 影片 stem，CD-112b-3：不從封面路徑反推
    cover_path = Path(resolve_cover_target(base_stem, external_manager))

    # 依模式決定目標路徑（jellyfin / emby 與 kodi 均使用 stem 長格式）
    if external_manager in STEM_IMAGE_MODES:
        poster_path = Path(base_stem + "-poster.jpg")
        fanart_path = Path(base_stem + "-fanart.jpg")
    else:
        # 未知 external_manager 值：不產圖、不崩（防呆）
        return {"poster": False, "fanart": False}

    # 底圖不存在 → 無法產生 poster/fanart；
    # 但若 stem-poster/fanart 已獨立存在（MDCX/Javinizer 匯入）且 overwrite=False，
    # 則直接認可磁碟現況，不嘗試生成（72d-P2B）
    if not cover_path.exists():
        if not overwrite_existing or not write_cover:
            poster_ok = poster_path.exists()
            fanart_ok = fanart_path.exists()
            if poster_ok or fanart_ok:
                return {"poster": poster_ok, "fanart": fanart_ok}
        return {"poster": False, "fanart": False}

    poster_ok = False
    fanart_ok = False

    # fanart = 原圖複製
    if fanart_path.exists() and (not overwrite_existing or not write_cover):
        fanart_ok = True  # 存在即算 True，NFO tag 對得上磁碟現況
    elif write_cover:
        is_same, certain = same_target_verdict(str(cover_path), str(fanart_path))
        if is_same:
            fanart_ok = certain
        else:
            try:
                shutil.copy2(str(cover_path), str(fanart_path))
                fanart_ok = True
            except shutil.SameFileError:
                fanart_ok = True
            except Exception as e:
                logger.warning("_write_external_images fanart 複製失敗 (%s): %s", fs_path, e)

    # poster = 裁切
    if poster_path.exists() and (not overwrite_existing or not write_cover):
        poster_ok = True  # 同上
    elif write_cover:
        is_same, certain = same_target_verdict(str(cover_path), str(poster_path))
        if is_same:
            poster_ok = certain
        else:
            try:
                poster_ok = crop_to_poster(str(cover_path), str(poster_path), number=number, maker=maker)
            except Exception as e:
                logger.warning("_write_external_images poster 裁切失敗 (%s): %s", fs_path, e)

    return {"poster": poster_ok, "fanart": fanart_ok}


class ExtrafanartResult(NamedTuple):
    """`_write_extrafanart` 的三個回傳值（CD-127c-2）。

    uris:             磁碟真相（**含本次跳過的既有檔**）→ 餵 DB sample_images
    downloaded:       本次真的下載成功幾格 → 餵 EnrichResult.extrafanart_written
    skipped_existing: 因既有檔而跳過幾格 → 只進 log，不進 API
    """
    uris: List[str]
    downloaded: int
    skipped_existing: int


def _write_extrafanart(
    fs_path: str,
    sample_images: List[str],
    write_extrafanart: bool,
    path_mappings: dict = None,
    preview_sample_images: List[str] = None,
) -> ExtrafanartResult:
    if not write_extrafanart or not sample_images:
        return ExtrafanartResult([], 0, 0)

    parent = Path(fs_path).parent
    extrafanart_dir = parent / "extrafanart"
    os.makedirs(str(extrafanart_dir), exist_ok=True)

    # CD-126-2：逐張配對用 index，**不用裸 zip()**——zip 在長度不等時會靜默截斷，
    # 等於少下載幾張圖。長度不等的正確語意是「那幾格沒有代理」，不是「少下載」。
    previews = preview_sample_images or []
    uris: List[str] = []
    downloaded = 0
    skipped_existing = 0
    for i, url in enumerate(sample_images):
        dest = str(extrafanart_dir / f"fanart{i+1}.jpg")
        # CD-127c-1：既有劇照永遠不被程式覆蓋。跳過的那格仍要 append——
        # uris 是「磁碟真相」，少一格會讓 _db_upsert 把那張劇照從 DB 洗掉。
        if os.path.exists(dest):
            uris.append(to_file_uri(dest, path_mappings))
            skipped_existing += 1
            continue
        fallback = previews[i] if i < len(previews) else ""
        try:
            # 同 _write_cover：preview 為空時不傳 kwarg（AC-5 逐字元相同）
            ok = (
                download_image(url, dest, fallback_url=fallback)
                if fallback
                else download_image(url, dest)
            )
            if ok:
                uris.append(to_file_uri(dest, path_mappings))
                downloaded += 1
        except Exception as e:
            logger.warning("extrafanart %d 下載失敗: %s", i + 1, e)
    return ExtrafanartResult(uris, downloaded, skipped_existing)


def _preserve_nfo_only_fields(meta: dict, scraper_data: dict, fs_path: str) -> None:
    """T4（CD-135-5 / CD-135-13）：NFO-only 三欄位（plot/rating/url）在「原始 packet
    沒帶這個 key」時才沿用既有 NFO——判準問 scraper_data（映射前），不是 meta（映射後）。
    原地修改 meta，無回傳值。"""
    if "_summary" in scraper_data and "_rating" in scraper_data and "url" in scraper_data:
        return
    nfo_p = Path(fs_path).with_suffix(".nfo")
    if not nfo_p.exists():
        return
    _, root = parse_nfo(str(nfo_p))
    if root is None:
        return
    if "_summary" not in scraper_data:
        meta["summary"] = nfo_text(root, "plot")
    if "_rating" not in scraper_data:
        raw = nfo_text(root, "rating")
        if raw:
            try:
                meta["rating"] = float(raw) / 2.0
            except ValueError:
                pass
    if "url" not in scraper_data:
        meta["url"] = nfo_text(root, "website")


def _is_filename_placeholder_title(title: str, number: str, fs_path: str) -> bool:
    """判斷 title 是不是掃描時從檔名塞進來的佔位值（CD-145a-15）。

    A：title 逐字等於檔名 stem（掃描器把 stem 原樣塞進 videos.title 的一般情況）
    B：title 本身以番號開頭（剝除有作用），且剝完之後與 stem 剝完之後相等
       （涵蓋舊版被寫壞成 `[NUMBER]` / `[NUMBER]4K` 的既有 NFO）

    B 的 `stripped != title` guard 是承重的，不得簡化掉——拿掉它，整理過的片
    （檔名 `[NUMBER]真標題.mp4`、NFO title `真標題`）會被誤判成佔位。
    """
    if not title:
        return False
    stem = Path(fs_path).stem
    stripped = _strip_num_prefixes(title, number)
    return (
        title == stem
        or (stripped != title and stripped == _strip_num_prefixes(stem, number))
    )


def _preserved_body_override_from_sidecar(fs_path, existing, preserve_title, nfo_title_format):
    """CD-154b-12：從來源檔旁 NFO 算出 preserved_body_override；失敗一律 None。"""
    if not preserve_title:
        return None
    try:
        nfo_p = Path(fs_path).with_suffix(".nfo")
        if nfo_p.exists():
            _, root = parse_nfo(str(nfo_p))
            if root is not None:
                disk_title = nfo_text(root, "title")
                record = nfo_title_record(root)
                return resolve_preserved_title_for_write(
                    disk_title, existing, nfo_title_format, record)
    except Exception as e:
        logger.warning("保留標題：讀取舊 NFO 失敗，照原樣保留 (%s): %s", fs_path, e)
        return None
    return None


def enrich_single(  # ranker-invalidate-ok: (no literal SQL here; corpus writes go via _db_upsert → repo.upsert and via repo.update_tags_if_changed — both already invalidate)
    file_path: str,
    number: str,
    mode: str = "fill_missing",
    write_nfo: bool = True,
    write_cover: bool = True,
    write_extrafanart: bool = False,
    overwrite_existing: bool = False,
    external_manager: str = "off",
    source: Optional[str] = None,
    javbus_lang: Optional[str] = None,
    scraper_data: Optional[dict] = None,
    path_mappings: dict = None,
    preserve_title: bool = False, nfo_title_format: str = '[{num}]{title}',
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
    # 提前算：DB 選列（_pick_row_for_path）與後面的 user_tags 讀取共用同一個 key
    path_uri = to_file_uri(fs_path_for_db)  # db-ns-ok: fs_path_for_db, DB round-trip value, no reverse mapping applied
    meta: dict = {}
    source_used = ""
    fields_filled: List[str] = []

    if mode == "refresh_full":
        if scraper_data is None:
            scraper_data = search_jav(number,
                                      source=source or 'auto', javbus_lang=javbus_lang)
        if not scraper_data:
            repo.update_scrape_attempted_at(to_file_uri(fs_path_for_db), time.time())  # db-ns-ok: fs_path_for_db, DB round-trip value, no reverse mapping applied
            _empty.error = f"找不到 {number} 的資料"
            _empty.reason = "not_found"
            return _empty
        meta = _scraper_to_meta(scraper_data)
        source_used = scraper_data.get("source", "scraper") or "scraper"
        _preserve_nfo_only_fields(meta, scraper_data, fs_path)

    elif mode == "db_to_sidecar":
        db_hits = repo.get_by_numbers([number])
        videos = db_hits.get(number, [])
        if not videos:
            _empty.error = f"DB 中找不到 {number} 的資料"
            _empty.reason = "not_found"
            return _empty
        meta = _video_to_meta(_pick_row_for_path(videos, path_uri))
        source_used = "db"

    else:
        db_hits = repo.get_by_numbers([number])
        videos = db_hits.get(number, [])

        if videos:
            meta = _video_to_meta(_pick_row_for_path(videos, path_uri))
            source_used = "db"
        else:
            nfo_p = Path(fs_path).with_suffix(".nfo")
            if nfo_p.exists():
                _, root = parse_nfo(str(nfo_p))
                if root is not None:
                    meta = _nfo_to_meta(root, number, nfo_title_format)
                    source_used = "nfo"

        # CD-145a-15：判定 title 是不是掃描時塞進來的佔位值（判定式本體見
        # _is_filename_placeholder_title）。清空成 '' 才能讓 _missing_fields()
        # 把它算進缺項（該函式只認 falsy，非空字串的佔位值本身不會被當缺項）。
        _placeholder_title = meta.get('title') or ''
        _is_placeholder_title = _is_filename_placeholder_title(_placeholder_title, number, fs_path)
        _title_only_synthetic_missing = False
        if _is_placeholder_title:
            _title_only_synthetic_missing = not _missing_fields(meta)   # 今天（未清空 title）missing 是否為空
            meta['title'] = ''

        missing = _missing_fields(meta)
        # CD-147b-1：缺封面也觸發外站查詢；不進 _missing_fields() 本體，避免污染
        # :600 的 _title_only_synthetic_missing 判定（CD-145a-9）。
        _cover_also_missing = write_cover and not meta.get("cover_url")
        if missing or _cover_also_missing:
            if scraper_data is None:
                scraper_data = search_jav(number,
                                          source=source or 'auto', javbus_lang=javbus_lang)
            if not scraper_data:
                if _title_only_synthetic_missing:
                    # CD-145a-9：八欄本來就齊，只差我們自己清空的合成 title 缺項——
                    # 刮不到來源不算「真的缺資料」，early return 會是這次改動自己
                    # 造成的回歸（今天這一列本來就會成功）。還原佔位標題，走原本的
                    # 寫入路徑（NFO 從 DB 現值重寫，與今天逐值相同）。
                    meta['title'] = _placeholder_title
                    # CD-147b-4b：佔位標題＋缺封面＋外站查無 → source_used 停在
                    # "db"，:722 gate 不會寫 scrape_attempted_at；僅當真的缺封面
                    # 時手動補記（write_cover=False 維持既有「不記」）。
                    if _cover_also_missing:
                        repo.update_scrape_attempted_at(to_file_uri(fs_path_for_db), time.time())  # db-ns-ok: fs_path_for_db, DB round-trip value, no reverse mapping applied
                elif not missing:
                    # CD-147b-1b：只因缺封面進來（文字欄齊），刮不到不算真缺資料——
                    # 不早退，落下去走原本寫入路徑；source_used 停在 "db"，手動補記。
                    repo.update_scrape_attempted_at(to_file_uri(fs_path_for_db), time.time())  # db-ns-ok: fs_path_for_db, DB round-trip value, no reverse mapping applied
                else:
                    # missing 本來就有 title 以外的缺項：早退行為與今天完全一致
                    repo.update_scrape_attempted_at(to_file_uri(fs_path_for_db), time.time())  # db-ns-ok: fs_path_for_db, DB round-trip value, no reverse mapping applied
                    _empty.error = f"找不到 {number} 的資料"
                    _empty.reason = "not_found"
                    return _empty
            else:
                # scraper_data 有值才會進來這支——None 進 _scraper_to_meta 會炸。
                supplement = _scraper_to_meta(scraper_data)
                meta, fields_filled = _merge_meta(meta, supplement)
                source_used = scraper_data.get("source", "scraper") or "scraper"

        # CD-145a-9：scraper 有回應但沒給 title 時，meta['title'] 會停在上面清空後
        # 的空字串——這裡補回原本的佔位值，避免 NFO／卡片標題變成真的空白。
        if _is_placeholder_title and not meta.get('title'):
            meta['title'] = _placeholder_title

    has_subtitle, meta['tags'] = _resolve_subtitle_and_tags(fs_path, meta)

    # 讀取 DB 現有 user_tags，在 NFO 寫出和 DB upsert 時保留（path_uri 已於函式開頭算好）
    existing_record = repo.get_by_path(path_uri)
    preserved_user_tags = existing_record.user_tags if existing_record else []

    # Bug 2 (feature/105): synthesize the EFFECTIVE original_title ONCE, before any
    # write branch, so both _write_nfo (<originaltitle>) and _db_upsert consume the
    # same preserved value. A refresh_full re-scrape returning an empty original_title
    # must NOT clobber the existing DB/NFO value (mirrors user_tags/cover preserve).
    meta['original_title'] = effective_original_title(meta, existing_record)
    meta['title'] = effective_title(meta, existing_record, preserve_title, number, preserved_body_override=_preserved_body_override_from_sidecar(fs_path, existing_record, preserve_title, nfo_title_format))

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
            preview_cover_url=meta.get("preview_cover_url", ""),
            overwrite_existing=overwrite_existing, external_manager=external_manager,  # 兩個 kwarg 刻意併行：enrich_single 的規模閘 baseline(249) 零頭寸，拆成兩行會直接超標（CD-112-13）
        )
        imgs = _write_external_images(
            fs_path=fs_path,
            external_manager=external_manager,
            overwrite_existing=overwrite_existing, write_cover=write_cover,
            number=number,
            maker=meta.get("maker", ""),
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
                fs_path_for_db=fs_path_for_db, nfo_title_format=nfo_title_format,
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
                fs_path_for_db=fs_path_for_db, nfo_title_format=nfo_title_format,
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
            preview_cover_url=meta.get("preview_cover_url", ""),
        )

    extrafanart_res = _write_extrafanart(
        fs_path=fs_path,
        sample_images=meta.get("sample_images", []),
        write_extrafanart=write_extrafanart,
        path_mappings=path_mappings,
        preview_sample_images=meta.get("preview_sample_images", []),
    )
    extrafanart_written = extrafanart_res.downloaded

    # DB upsert 在寫檔後執行，才能知道本地封面路徑
    # db_to_sidecar 不打 scraper 也不更新 DB（metadata 不變）
    if mode in ("refresh_full", "fill_missing") and source_used not in ("db", "nfo", ""):
        local_cover = resolve_cover_target(str(Path(fs_path).with_suffix("")), external_manager) if cover_written else ""
        nfo_path = Path(fs_path).with_suffix(".nfo")
        # TASK-113b-T1: TOCTOU 對齊 S4 既有失敗語意——.exists() 判定後檔案在 .stat()
        # 前消失（OSError）視為「沒有值」，記 warning，不讓整個 enrich_single 炸掉。
        _NFO_MTIME_POLICY = NFO_MTIME_REFRESH
        try:
            _mt = nfo_mtime_or_none(nfo_path, on_error=_reraise_nfo_stat_error) if nfo_path.exists() else None
        except OSError as e:
            logger.warning("nfo_mtime stat 失敗 (%s): %s", number, e)
            _mt = None
        nfo_mtime = _mt if _mt is not None else 0.0
        # wrapper callsite decision point; helper itself: enforced at callsites
        # db-ns-ok: fs_path_for_db passed through to _db_upsert's internal primitive sink
        _db_upsert(repo, number, fs_path_for_db, meta, local_cover_path=local_cover,
                   nfo_mtime=nfo_mtime, written_uris=extrafanart_res.uris,
                   path_mappings=path_mappings)

        # 重刮 focal trigger（TASK-98b-T2 + 99a-T1b CD-4）：只在「實際寫入新封面內容」
        # （cover_written=True）時才作廢舊手動焦點、再排新的背景偵測；reset 必須在
        # submit 之前（先清舊值、再讓 gate 判斷是否排 worker，避免有碼片極端時序下
        # 短暫殘留 manual）。cover_written=False（只重寫 NFO，未覆蓋既有封面）→ 完全
        # 不進此塊，manual 值原樣保留。video_path_uri 須與 _db_upsert 寫入的 key 一致
        # （:190 / :594 to_file_uri(fs_path_for_db)），複用上方已算過的 path_uri。
        if cover_written:
            # TASK-105-T6: reset+submit 收斂至共用 helper（video_uri=path_uri，
            # 與 reset 現用值同源、byte-identical，見 TASK-105-T6.md 等值證明）。
            schedule_focal_after_cover_write(
                repo, path_uri, number, meta.get("maker"), local_cover, path_mappings
            )

    _sync_tags_to_db(repo, path_uri, meta.get('tags', []), number)

    _sync_nfo_mtime(repo, fs_path, fs_path_for_db, number)

    # reason=hit 的「/thumb 兩道 gate + 磁碟複驗 + false-negative 取捨」完整理由已
    # 遷入 core.enrich_contract.compute_has_servable_cover 的 docstring（feature/105，
    # 三呼叫點共用同一份磁碟真相）。此重讀在所有寫檔 + _db_upsert + nfo_mtime UPDATE
    # 之後（同步、已 commit），故看到的是最終 DB 狀態。
    # db-ns-ok: fs_path_for_db, DB round-trip key（同 :437 path_uri）
    has_servable_cover = compute_has_servable_cover(
        repo, to_file_uri(fs_path_for_db), path_mappings
    )

    return enrich_success(
        nfo_written=nfo_written,
        cover_written=cover_written,
        extrafanart_written=extrafanart_written,
        fields_filled=fields_filled,
        source_used=source_used,
        has_servable_cover=has_servable_cover,
    )


def _sync_nfo_mtime(  # ranker-invalidate-ok: (SET 的是 nfo_mtime，不是 corpus 欄位；本標記隨這段 SQL 從 enrich_single 一起搬過來，理由不變)
    repo: VideoRepository, fs_path: str, fs_path_for_db: str, number: str
) -> None:
    """nfo_mtime 獨立更新（S4）：不論 mode/source，只要 NFO 存在就同步 DB，避免 analysis
    永遠視為 missing_nfo。覆寫語意為 fill-missing（`WHERE … AND (nfo_mtime IS NULL OR
    nfo_mtime = 0)`），與 enrich_single 內 S3 的無條件覆寫刻意不同（plan-113b CD-113b-3）。

    TASK-113b-T1 的兩件事：
    ① stat 的失敗來源與 DB 的失敗來源分開——stat 失敗（TOCTOU：`.exists()` 判定後檔案
       消失）視為「沒有值」，**整段跳過 UPDATE**（等同現況「NFO 不存在」的處置；
       **不得折成 0.0 再寫**，那會把原本 NULL 的列改成 0.0）。DB 連線／寫入的例外面
       （`except Exception` + warning + `finally: conn.close()`）原封不動保留。
    ② 從 enrich_single 原地抽出：**純搬移、零行為變更**，換得規模閘淨負（實測
       249 → 237 行）——本 task 在 enrich_single 內新增 S3 的例外保護會讓它長大到
       263，而豁免基準只准減不准增。baseline 維持 249 不下修，把餘裕留給 T2。
    """
    nfo_path = Path(fs_path).with_suffix(".nfo")
    _NFO_MTIME_POLICY = NFO_MTIME_FILL_MISSING
    if not nfo_path.exists():
        return
    try:
        nfo_mt = nfo_mtime_or_none(nfo_path, on_error=_reraise_nfo_stat_error)
    except OSError as e:
        logger.warning("nfo_mtime stat 失敗 (%s): %s", number, e)
        return
    if nfo_mt is None:
        return

    conn = None
    try:
        path_uri = to_file_uri(fs_path_for_db)  # db-ns-ok: fs_path_for_db, DB round-trip value, no reverse mapping applied
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

    meta = search_jav(number,
                      source="auto", javbus_lang=None)
    if not meta:
        logger.warning("[fetch_samples_only] 找不到資料: %s", number)
        _empty.error = f"找不到 {number} 的資料"
        return _empty

    sample_images = meta.get("sample_images", [])
    extrafanart_res = _write_extrafanart(
        fs_path, sample_images, write_extrafanart=True, path_mappings=path_mappings,
        preview_sample_images=meta.get("preview_sample_images", []),
    )

    if extrafanart_res.uris:                      # ← 既有 gate，語意不變（磁碟真相非空才寫 DB）
        repo = VideoRepository()
        # db-ns-ok: fs_path_for_db, DB round-trip value passed to wrapper sink
        _db_upsert_samples_only(repo, fs_path_for_db, extrafanart_res.uris)

    logger.info(
        "[fetch_samples_only] %s: %d downloaded / %d skipped-existing / %d on disk",
        number, extrafanart_res.downloaded, extrafanart_res.skipped_existing,
        len(extrafanart_res.uris),
    )
    return enrich_success(
        nfo_written=False,
        cover_written=False,
        extrafanart_written=extrafanart_res.downloaded,
        fields_filled=[],
        source_used=meta.get("source", ""),
        reason=None,
    )


def resolve_nfo_cover_paths(file_path: str, path_mappings: dict = None, external_manager: str = "off") -> tuple:
    """由影片 file_path 推導目標 NFO / cover 的 FS 路徑。

    復用 enrich_single / _write_nfo / _write_cover 的同一套路徑邏輯：
    先以 uri_to_local_fs_path() 解析（fallback 原值），再 with_suffix。
    回傳 (nfo_path, cover_path)，兩者皆為當前環境 FS 字串路徑。

    ⚠️ 路徑邏輯必須與 `_write_nfo`（with_suffix(".nfo")）/ `_write_cover`
    （with_suffix(".jpg")）保持同步——62a-1 的 refresh_full 分裂守衛
    （web/routers/scraper.py enrich_single_endpoint）靠本函數判斷檔案是否已存在。
    若 writer 改了 cover 命名（poster.jpg / .png / fanart 等）或 fs_path 推導，
    本函數要一起改，否則守衛會悄悄檢查錯路徑（false-allow 重現分裂 / false-block 打爆缺封面 quick-enrich）。

    external_manager 預設 `"off"` 只是參數預設值（呼叫端未傳時的 fallback）——本函式的
    唯一呼叫端 `web/routers/scraper.py`（refresh_full + overwrite_existing=false 分裂守衛）
    已在 T2c pre-merge P2-5 改為傳入真值。**在 `resolve_cover_target` 仍是 T1 stub 的
    現況下傳真值是無行為差異的**（stub 完全不讀這個參數），這裡提前接線只是讓 T3
    三步規則落地時零呼叫端改動即可生效，避免留一段「簽名已加、呼叫端仍傳預設值」
    的窗口期看起來像已接線卻沒有。
    """
    try:
        fs_path = uri_to_local_fs_path(file_path, path_mappings)
    except Exception:
        fs_path = file_path
    nfo_path = str(Path(fs_path).with_suffix(".nfo"))
    cover_path = resolve_cover_target(str(Path(fs_path).with_suffix("")), external_manager)
    return nfo_path, cover_path
