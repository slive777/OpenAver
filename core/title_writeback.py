"""title_writeback.py — 就地改寫 NFO 的標題相關元素（TASK-172-T1，CD-172-4）。

只改 <title>／<originaltitle>／（已存在才同步的）<sorttitle>／<openaver_title_record>，
其餘元素原樣保留。顯示標題計算全部委派 core.nfo_title_format.build_display_title。
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from typing import Optional

from core.logger import get_logger
from core.nfo_read import nfo_first_text
from core.nfo_stat import nfo_mtime_or_none
from core.nfo_title_format import build_display_title
from core.nfo_updater import set_element_text
from core.nfo_utils import sanitize_nfo_bytes
from core.organizer import _strip_illegal_xml_chars
from core.scrapers.utils import has_japanese
from core.video_nfo_locate import locate_video_nfo

logger = get_logger(__name__)

# 公開別名：路由層寫 DB 前用同一支淨化函式（NFO 與 DB 同值）
strip_illegal_xml_chars = _strip_illegal_xml_chars

_DEFAULT_FORMAT = '[{num}]{title}'


class NfoNotFoundError(Exception):
    """NFO 檔案不存在。"""


class NfoParseError(Exception):
    """NFO 內容無法解析成 XML（sanitize 後仍失敗）。"""


def rewrite_nfo_titles(
    nfo_path,
    *,
    number,
    title_body,
    original_title,
    actors,
    maker,
    date,
    nfo_title_format,
) -> bytes:
    """改寫 NFO 的標題元素並回傳寫出的 bytes。

    NFO 不存在 → NfoNotFoundError；XML 無法解析 → NfoParseError（檔案不動）；
    讀／寫的 OSError 不包裝、原樣往外拋。
    """
    path = Path(nfo_path)
    if not path.exists():
        raise NfoNotFoundError(str(nfo_path))

    # sink 淨化（NFO-CTRL-01）：先淨化、後算顯示標題（與 generate_nfo 同序）
    number = _strip_illegal_xml_chars(number)
    title_body = _strip_illegal_xml_chars(title_body)
    original_title = _strip_illegal_xml_chars(original_title)
    maker = _strip_illegal_xml_chars(maker)
    date = _strip_illegal_xml_chars(date)
    actors = [_strip_illegal_xml_chars(a) for a in (actors or [])]

    raw = path.read_bytes()
    raw = sanitize_nfo_bytes(raw)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        raise NfoParseError(str(e)) from e

    display_title, body = build_display_title(
        number, title_body, original_title, actors, maker, date, nfo_title_format,
    )

    if number and not nfo_first_text(root, ("num", "id")):
        set_element_text(root, "num", number, after_tag="title")
    set_element_text(root, "title", display_title, after_tag="num")
    set_element_text(root, "originaltitle", original_title, after_tag="title")
    if root.find("sorttitle") is not None:
        root.find("sorttitle").text = display_title

    for old in list(root.findall("openaver_title_record")):
        root.remove(old)
    if nfo_title_format != _DEFAULT_FORMAT:
        rec = ET.SubElement(root, "openaver_title_record")
        ET.SubElement(rec, "written").text = display_title
        ET.SubElement(rec, "body").text = body

    out = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    path.write_bytes(out)
    return out


def needs_translate(title, original_title, nfo_mtime) -> bool:
    """標題是假名、沒有原文、且有 NFO（nfo_mtime > 0）才算待翻譯（列表與寫回回應共用）。"""
    return bool((not original_title) and has_japanese(title or '') and (nfo_mtime or 0) > 0)


def _new_original_title(original_title: Optional[str], video) -> str:
    """original_title 三態：None＝沿用（現值也空就搬目前標題本體）；""＝清空；非空＝設定。"""
    if original_title is not None:
        return original_title
    return video.original_title or video.title


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


def apply_title_writeback(repo, video, title, original_title, config: dict, path_mappings: dict) -> dict:
    """翻譯／復原寫回本體：NFO 先、DB 後、無回滾。失敗回 {success: False, error: <code>}。

    original_title 三態：None＝沿用；""＝清空；非空＝設定。
    不取 user_tags_write._LOCK（非可重入；呼叫端需要互斥時自己 with hold_nfo_write()）。
    """
    fmt = config.get("scraper", {}).get("nfo_title_format", _DEFAULT_FORMAT)
    _display, body = build_display_title(
        video.number or '', strip_illegal_xml_chars(title).strip(), '',
        video.actresses, video.maker, video.release_date, fmt,
    )
    if not body:
        return {"success": False, "error": "title_empty"}
    new_original = strip_illegal_xml_chars(_new_original_title(original_title, video))

    nfo_path, loc_err = locate_video_nfo(video, config, path_mappings)
    if nfo_path is None:
        return {"success": False, "error": loc_err}
    nfo_err = _write_title_nfo(nfo_path, video, body, new_original, fmt)
    if nfo_err is not None:
        return {"success": False, "error": nfo_err}

    # 取實際寫入那份 NFO 的 mtime；取不到沿用舊值（下次掃描最多多讀一次）
    new_mtime = nfo_mtime_or_none(Path(nfo_path))
    if new_mtime is None:
        new_mtime = video.nfo_mtime
    try:
        written = repo.update_titles(video.path, body, new_original, new_mtime)
    except Exception as e:
        logger.error("[title-writeback] DB 寫入失敗: %s", e)
        return {"success": False, "error": "db_write_failed"}
    if not written:
        return {"success": False, "error": "not_found"}
    return {"success": True, "title": body, "original_title": new_original,
            "needs_translate": needs_translate(body, new_original, new_mtime),
            "nfo_updated": True}
