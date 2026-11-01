"""Showcase plot API — GET/POST /api/showcase/video/plot（TASK-187b-T4，CD-187b-6）。

讀寫 NFO 的 <plot>／<originalplot>；先 NFO 後 DB、無回滾；唯讀來源只寫輸出夾。
驗證前置沿用 write_video_title，抽成本檔 _load_gallery_video（不重構標題端點）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from core.config import load_config, get_configured_gallery_dirs
from core.database import VideoRepository, get_db_path, init_db
from core.logger import get_logger
from core.nfo_stat import nfo_mtime_or_none
from core.path_utils import is_path_under_dir
from core.plot_writeback import (
    PlotEmptyError,
    read_nfo_plots,
    rewrite_nfo_plot,
)
from core.title_writeback import (
    NfoNotFoundError,
    NfoParseError,
    strip_illegal_xml_chars,
)
from core.video_nfo_locate import locate_video_nfo

logger = get_logger(__name__)

router = APIRouter(prefix="/api/showcase", tags=["showcase"])


class PlotWritebackRequest(BaseModel):
    """POST /video/plot body：file_path（DB key）+ plot + original_plot 三態
    （None＝沿用；""＝清空；非空＝設定）。"""
    file_path: str
    plot: str
    original_plot: Optional[str] = None


_PLOT_ERROR_MESSAGES = {
    "not_found": "找不到影片",
    "plot_empty": "簡介不可為空",
    "no_nfo": "找不到 NFO",
    "nfo_ambiguous": "輸出夾有多份 NFO，無法判斷要改哪一份",
    "nfo_unreadable": "NFO 無法讀取或解析",
    "nfo_write_failed": "NFO 寫入失敗",
    "db_write_failed": "資料庫寫入失敗（NFO 已更新，請再試一次）",
    "invalid_path": "檔案路徑格式無效",
}


def _plot_fail(code: str) -> dict:
    """讀寫失敗一律 HTTP 200 ＋ {success:false, error:<code>, message}。"""
    return {"success": False, "error": code, "message": _PLOT_ERROR_MESSAGES[code]}


def _norm(text: str) -> str:
    """空白正規化：用於 unchanged 判定（CD-187b-6.6）。"""
    return " ".join(text.split())


def _load_gallery_video(file_path: str):
    """DB 存在、get_by_path、圖庫目錄檢查；成功回 (repo, video, config, path_mappings)，
    失敗回 (None, fail_dict, None, None)。"""
    db_path = get_db_path()
    if not db_path.exists():
        return None, _plot_fail("not_found"), None, None
    init_db(db_path)
    repo = VideoRepository(db_path)
    video = repo.get_by_path(file_path)
    if video is None:
        return None, _plot_fail("not_found"), None, None
    config = load_config()
    configured_dir_uris, path_mappings = get_configured_gallery_dirs(config)
    if not any(is_path_under_dir(video.path, uri) for uri in configured_dir_uris):
        return None, _plot_fail("not_found"), None, None
    return repo, video, config, path_mappings


def _resolve_target_original(req_original, cur_plot: str, cur_original: str, new_plot: str) -> str:
    """解算寫入用的 original_plot 最終值（字串；""＝清除）。

    None＝沿用；現值也空且 plot 有變 → 把目前 <plot> 搬進 <originalplot>。
    plot 正規化後未變時不搬，避免中文簡介被捏造 originalplot（CD 問題①）。
    """
    if req_original is not None:
        return req_original
    if _norm(new_plot) == _norm(cur_plot):
        return cur_original
    return cur_original if cur_original else cur_plot


def _read_plots_from_disk(nfo_path: str) -> tuple:
    """讀現值；成功回 (plot, original, None)，失敗回 (None, None, fail_dict)。"""
    try:
        plot, original = read_nfo_plots(nfo_path)
    except NfoNotFoundError:
        return None, None, _plot_fail("no_nfo")
    except FileNotFoundError:
        return None, None, _plot_fail("no_nfo")
    except NfoParseError:
        return None, None, _plot_fail("nfo_unreadable")
    except Exception as e:
        logger.error("[plot] NFO 讀取失敗: %s", e)
        return None, None, _plot_fail("nfo_unreadable")
    return plot, original, None


@router.get("/video/plot")
def get_video_plot(file_path: str = Query(...)):
    """燈箱開簡介：讀 NFO 的 <plot>／<originalplot>（點開當下才讀，無快取）。"""
    try:
        repo, video_or_fail, config, path_mappings = _load_gallery_video(file_path)
        if repo is None:
            return video_or_fail
        video = video_or_fail

        nfo_path, loc_err = locate_video_nfo(video, config, path_mappings)
        if nfo_path is None:
            return _plot_fail(loc_err)
        # 一般來源 locate 只組路徑、不檢查存在
        if not Path(nfo_path).exists():
            return _plot_fail("no_nfo")

        plot, original, err = _read_plots_from_disk(nfo_path)
        if err is not None:
            return err
        if not plot:
            return _plot_fail("plot_empty")
        return {
            "success": True,
            "plot": plot,
            "original_plot": original,
            "has_original": bool(original),
        }
    except ValueError:
        return _plot_fail("invalid_path")
    except Exception as e:
        logger.error("[plot] GET 未預期錯誤: %s", e)
        return _plot_fail("nfo_unreadable")


@router.post("/video/plot")
def write_video_plot(req: PlotWritebackRequest):
    """燈箱翻譯／復原：NFO <plot>／<originalplot> 與 DB has_plot 同步改寫。

    相等判定在任何寫入之前完成（CD-187b-6.6）；先 NFO 後 DB、無回滾。
    """
    try:
        repo, video_or_fail, config, path_mappings = _load_gallery_video(req.file_path)
        if repo is None:
            return video_or_fail
        video = video_or_fail

        nfo_path, loc_err = locate_video_nfo(video, config, path_mappings)
        if nfo_path is None:
            return _plot_fail(loc_err)
        if not Path(nfo_path).exists():
            return _plot_fail("no_nfo")

        cur_plot, cur_original, err = _read_plots_from_disk(nfo_path)
        if err is not None:
            return err
        if not cur_plot:
            return _plot_fail("plot_empty")

        new_plot = strip_illegal_xml_chars(req.plot)
        if not new_plot.strip():
            return _plot_fail("plot_empty")

        req_original = (
            strip_illegal_xml_chars(req.original_plot)
            if req.original_plot is not None
            else None
        )
        target_original = _resolve_target_original(
            req_original, cur_plot, cur_original, new_plot,
        )

        # 不變式：最終 plot＋originalplot 正規化後皆等於現值 → 零寫入
        if (
            _norm(new_plot) == _norm(cur_plot)
            and _norm(target_original) == _norm(cur_original)
        ):
            return {
                "success": True,
                "plot": cur_plot,
                "original_plot": cur_original,
                "has_original": bool(cur_original),
                "unchanged": True,
            }

        # new_original 傳給 helper：""＝清除；否則設定（已解算，不再傳 None）
        try:
            rewrite_nfo_plot(
                nfo_path, new_plot=new_plot, new_original=target_original,
            )
        except NfoNotFoundError:
            return _plot_fail("no_nfo")
        except PlotEmptyError:
            return _plot_fail("plot_empty")
        except NfoParseError:
            return _plot_fail("nfo_unreadable")
        except Exception as e:
            logger.error("[plot] NFO 寫入失敗: %s", e)
            return _plot_fail("nfo_write_failed")

        new_mtime = nfo_mtime_or_none(Path(nfo_path))
        if new_mtime is None:
            new_mtime = video.nfo_mtime
        try:
            written = repo.update_plot_flag(video.path, True, new_mtime)
        except Exception as e:
            logger.error("[plot] DB 寫入失敗: %s", e)
            return _plot_fail("db_write_failed")
        if not written:
            return _plot_fail("not_found")

        return {
            "success": True,
            "plot": new_plot,
            "original_plot": target_original,
            "has_original": bool(target_original),
            "unchanged": False,
        }
    except ValueError:
        return _plot_fail("invalid_path")
    except Exception as e:
        logger.error("[plot] POST 未預期錯誤: %s", e)
        return _plot_fail("nfo_write_failed")
