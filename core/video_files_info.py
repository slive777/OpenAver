"""core.video_files_info — GET /api/showcase/video/files 的回應組裝（TASK-200b-T5）。

全程純讀：只做 os.stat，不寫資料庫、不產縮圖、不寫任何磁碟檔。
"""
from __future__ import annotations

import os
import stat
from urllib.parse import quote

from core import thumbnail_cache
from core.config import STEM_IMAGE_MODES, normalize_external_manager
from core.cover_layout import COVER_EXT, cover_base_stem
from core.cover_signature import (
    cover_changed,
    cover_version_suffix,
    read_cover_signature,
)
from core.logger import get_logger
from core.media_probe import resolution_tier, video_codec_label
from core.path_utils import is_path_under_dir, normalize_path, to_file_uri, uri_to_local_fs_path
from core.readonly_paths import resolve_owning_output_root
from core.source_reachability import (
    _scandir_probe, is_path_on_unreachable_source, owning_source_index,
    source_keys_and_prefixes,
)
from core.video_nfo_locate import locate_video_nfo

logger = get_logger(__name__)


def stat_kind(path: str):
    """stat 一次：回 (kind, st)。kind ∈ ok／absent／unreadable。

    只有 FileNotFoundError／NotADirectoryError 算 absent，其餘 OSError
    （含 PermissionError）與 ValueError（路徑含 NUL）算 unreadable。
    """
    try:
        st = os.stat(path)
    except (FileNotFoundError, NotADirectoryError):
        return "absent", None
    except (OSError, ValueError) as e:
        logger.warning("stat 讀不到: %s: %s", path, e)
        return "unreadable", None
    return "ok", st


def source_root_unreachable(video_path, gallery_config):
    keys, prefixes = source_keys_and_prefixes(gallery_config)
    index = owning_source_index(video_path, prefixes)
    return index is not None and _scandir_probe(keys[index]) is not False


def thumb_is_stale(*, mode, db_sig, live_sig, thumb_mtime_ns) -> bool:
    """牆上縮圖是否比封面舊（純函式，CD-200b-5）。"""
    if mode != "cache":
        return False
    if thumb_mtime_ns is None:
        return False
    if live_sig is None:
        return False
    if db_sig is not None:
        return cover_changed(db_sig, live_sig)
    return thumb_mtime_ns < live_sig[0]


def poster_regen_verdict(*, external_mode_on, has_cover_file, cover_fs, video_fs, readonly):
    """海報能不能重新產生（純函式，零 I/O；T6 的 poster-regenerate 沿用）。"""
    if not external_mode_on:
        return False, None
    if not has_cover_file:
        return False, "no_cover"
    if readonly:
        return True, None
    cover_stem = os.path.basename(cover_base_stem(cover_fs))
    video_stem = os.path.basename(os.path.splitext(video_fs)[0])
    cover_dir = to_file_uri(normalize_path(os.path.normpath(os.path.dirname(cover_fs))))
    video_dir = to_file_uri(normalize_path(os.path.normpath(os.path.dirname(video_fs))))
    same_dir = is_path_under_dir(cover_dir, video_dir) and is_path_under_dir(video_dir, cover_dir)
    if cover_stem != video_stem or not same_dir:
        return False, "generic_cover_name"
    return True, None


def summarize_media(view) -> dict:
    """探針視圖 → media 回應段；非 ok 時其餘欄恆 None。"""
    blank = {
        "status": "none", "tier": None, "width": None, "height": None,
        "codec": None, "duration_ms": None, "size": None,
    }
    if view is None:
        return blank
    if view.is_ok_current:
        return {
            "status": "ok",
            "tier": resolution_tier(view.media_width, view.media_height),
            "width": view.media_width,
            "height": view.media_height,
            "codec": video_codec_label(view.media_video_format) or None,
            "duration_ms": view.media_duration_ms,
            "size": view.size_bytes,
        }
    if view.media_probe_status == "failed" and view.key_matches:
        failed = dict(blank)
        failed["status"] = "failed"
        return failed
    return blank


def _cover_section(video, *, config, path_mappings) -> dict:
    if not video.cover_path:
        return {"exists": False, "url": ""}
    try:
        cover_fs = uri_to_local_fs_path(video.cover_path, path_mappings)
    except ValueError:
        return {"exists": False, "url": ""}
    kind, st = stat_kind(cover_fs)
    if kind != "ok" or not stat.S_ISREG(st.st_mode):
        return {"exists": False, "url": ""}
    version = cover_version_suffix(read_cover_signature(cover_fs))
    return {
        "exists": True,
        "url": f"/api/gallery/image?path={quote(cover_fs, safe='')}{version}",
    }


def _thumb_section(video, *, config, path_mappings, db_sig, cover_live_sig) -> dict:
    if not config.get("thumbnail_cache_enabled", False):
        cover = _cover_section(video, config=config, path_mappings=path_mappings)
        return {
            "mode": "cover", "exists": cover["exists"],
            "url": cover["url"], "stale": False,
        }
    thumb_fs = thumbnail_cache.thumb_file_for(video.path)
    kind, st = stat_kind(str(thumb_fs))
    if kind != "ok":
        return {"mode": "cache", "exists": False, "url": "", "stale": False}
    thumb_mtime_ns = st.st_mtime_ns
    return {
        "mode": "cache",
        "exists": True,
        "url": f"/api/gallery/thumb?path={quote(video.path, safe='')}&v={thumb_mtime_ns}",
        "stale": thumb_is_stale(
            mode="cache", db_sig=db_sig, live_sig=cover_live_sig,
            thumb_mtime_ns=thumb_mtime_ns,
        ),
    }


def _poster_section(video, *, config, path_mappings, external_mode_on, readonly, cover_info) -> dict:
    if not external_mode_on:
        can_regen, blocked = poster_regen_verdict(
            external_mode_on=False, has_cover_file=False,
            cover_fs="", video_fs="", readonly=readonly,
        )
        return {
            "visible": False, "exists": False, "url": "",
            "can_regen": can_regen, "regen_blocked": blocked,
        }
    has_cover = cover_info["exists"]
    try:
        cover_fs = uri_to_local_fs_path(video.cover_path, path_mappings)
    except ValueError:
        cover_fs = ""
    try:
        video_fs = uri_to_local_fs_path(video.path, path_mappings)
    except ValueError:
        video_fs = ""
    can_regen, blocked = poster_regen_verdict(
        external_mode_on=True, has_cover_file=has_cover,
        cover_fs=cover_fs, video_fs=video_fs, readonly=readonly,
    )
    if blocked == "generic_cover_name":
        return {
            "visible": True, "exists": None, "url": "",
            "can_regen": can_regen, "regen_blocked": blocked,
        }
    if not has_cover:
        return {
            "visible": True, "exists": False, "url": "",
            "can_regen": can_regen, "regen_blocked": blocked,
        }
    poster_fs = cover_base_stem(cover_fs) + "-poster" + COVER_EXT
    kind, st = stat_kind(poster_fs)
    exists = kind == "ok" and stat.S_ISREG(st.st_mode)
    if not exists:
        return {
            "visible": True, "exists": False, "url": "",
            "can_regen": can_regen, "regen_blocked": blocked,
        }
    version = cover_version_suffix(read_cover_signature(poster_fs))
    return {
        "visible": True,
        "exists": True,
        "url": f"/api/gallery/image?path={quote(poster_fs, safe='')}{version}",
        "can_regen": can_regen,
        "regen_blocked": blocked,
    }


def _nfo_section(video, *, config, path_mappings) -> dict:
    try:
        nfo_path, _err = locate_video_nfo(video, config, path_mappings)
    except (OSError, ValueError):
        return {"name": ""}
    if nfo_path is None:
        return {"name": ""}
    try:
        video_fs = uri_to_local_fs_path(video.path, path_mappings)
    except ValueError:
        return {"name": ""}
    if resolve_owning_output_root(video.path, config) is not None:
        return {"name": os.path.basename(nfo_path)}
    if os.path.dirname(nfo_path) != os.path.dirname(video_fs):
        return {"name": ""}
    kind, _st = stat_kind(nfo_path)
    if kind != "ok":
        return {"name": ""}
    return {"name": os.path.basename(nfo_path)}


def _neutral_response(*, readonly, external_mode_on, media, folders, mode) -> dict:
    return {
        "state": "unreachable",
        "readonly": readonly,
        "external_mode_on": external_mode_on,
        "nfo": {"name": ""},
        "cover": {"exists": False, "url": ""},
        "poster": {
            "visible": external_mode_on, "exists": False, "url": "",
            "can_regen": False, "regen_blocked": None,
        },
        "thumb": {"mode": mode, "exists": False, "url": "", "stale": False},
        "media": media,
        "folders": folders,
    }


def build_files_info(video, *, repo, config, path_mappings) -> dict:
    """組 GET /api/showcase/video/files 回應本體（不含 success）。"""
    readonly = resolve_owning_output_root(video.path, config) is not None
    external_mode_on = normalize_external_manager(
        config.get("scraper", {}).get("external_manager", "off"),
    ) in STEM_IMAGE_MODES
    view = repo.get_media_probe_view(video.path)
    media = summarize_media(view)
    folders = {
        "source": video.path,
        "output": video.output_dir if readonly else "",
    }
    mode = "cache" if config.get("thumbnail_cache_enabled", False) else "cover"
    if is_path_on_unreachable_source(video.path, config.get('gallery', {})):
        return _neutral_response(
            readonly=readonly, external_mode_on=external_mode_on,
            media=media, folders=folders, mode=mode,
        )
    try:
        video_fs = uri_to_local_fs_path(video.path, path_mappings)
    except ValueError:
        video_fs = ""
    kind, _st = stat_kind(video_fs) if video_fs else ("unreadable", None)
    if kind == "ok":
        state = "ok"
    elif kind == "absent":
        state = "unreachable" if source_root_unreachable(video.path, config.get("gallery", {})) else "missing"
    else:
        state = "unreachable"
    if state == "unreachable":
        return _neutral_response(
            readonly=readonly, external_mode_on=external_mode_on,
            media=media, folders=folders, mode=mode,
        )
    try:
        cover_fs = uri_to_local_fs_path(video.cover_path, path_mappings)
    except ValueError:
        cover_fs = ""
    cover_live_sig = read_cover_signature(cover_fs) if cover_fs else None
    db_sig = repo.get_cover_sig(video.path)
    cover_info = _cover_section(video, config=config, path_mappings=path_mappings)
    thumb_info = _thumb_section(
        video, config=config, path_mappings=path_mappings,
        db_sig=db_sig, cover_live_sig=cover_live_sig,
    )
    poster_info = _poster_section(
        video, config=config, path_mappings=path_mappings,
        external_mode_on=external_mode_on, readonly=readonly,
        cover_info=cover_info,
    )
    nfo_info = _nfo_section(video, config=config, path_mappings=path_mappings)
    return {
        "state": state,
        "readonly": readonly,
        "external_mode_on": external_mode_on,
        "nfo": nfo_info,
        "cover": cover_info,
        "poster": poster_info,
        "thumb": thumb_info,
        "media": media,
        "folders": folders,
    }
