"""NFO 定位：唯讀來源讀輸出夾那份、一般來源讀影片旁同名 .nfo（187b-T2b / CD-187b-5）。

從 web.routers.showcase 原樣搬出；簽名、回傳 (path, err)、err 碼不變。
"""

from __future__ import annotations

import os
from pathlib import Path

from core.path_utils import is_path_under_dir, uri_to_local_fs_path
from core.readonly_paths import resolve_owning_output_root


def locate_readonly_nfo(video, path_mappings: dict, output_uri: str):
    """唯讀來源：scandir 一次列舉輸出夾的 .nfo（BE-DATA-12：四狀態分開）。回 (path, err)。

    output_dir 必須在目前設定的輸出根（output_uri）底下，否則視為沒有 NFO（不碰舊夾）。
    """
    if not video.output_dir:
        return None, "no_nfo"
    if not output_uri or not is_path_under_dir(video.output_dir, output_uri):
        return None, "no_nfo"
    out_fs = uri_to_local_fs_path(video.output_dir, path_mappings)
    try:
        with os.scandir(out_fs) as it:
            nfo_files = sorted(e.path for e in it if e.name.lower().endswith(".nfo") and e.is_file())
    except FileNotFoundError:
        return None, "no_nfo"
    except OSError:
        return None, "nfo_unreadable"
    if len(nfo_files) > 1:
        return None, "nfo_ambiguous"
    if not nfo_files:
        return None, "no_nfo"
    return nfo_files[0], None


def locate_video_nfo(video, config: dict, path_mappings: dict):
    """回 (nfo_path, err)：唯讀來源取輸出夾那份，一般來源取影片旁同名 .nfo。"""
    owning = resolve_owning_output_root(video.path, config)
    if owning is not None:
        return locate_readonly_nfo(video, path_mappings, owning[2])
    return str(Path(uri_to_local_fs_path(video.path, path_mappings)).with_suffix(".nfo")), None
