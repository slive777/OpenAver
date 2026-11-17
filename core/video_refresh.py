"""重新讀取單一影片的現有檔案。"""
from pathlib import Path
from typing import NamedTuple

from core import media_probe, thumbnail_cache
from core.cover_signature import apply_cover_change, cover_changed, read_cover_signature
from core.database import Video
from core.gallery_scanner import VideoScanner
from core.media_probe_force import probe_now
from core.nfo_stat import nfo_mtime_or_none
from core.path_utils import uri_to_local_fs_path
from core.readonly_paths import resolve_owning_output_root
from core.source_reachability import is_path_on_unreachable_source
from core.video_files_info import source_root_unreachable, stat_kind, summarize_media
from core.video_nfo_locate import locate_readonly_nfo


def _refresh_readonly(repo, row, config, path_mappings):
    owning = resolve_owning_output_root(row.path, config)
    try:
        nfo_fs, err = locate_readonly_nfo(row, path_mappings, owning[2])
    except ValueError:
        return {"success": False, "error": "nfo_unreadable"}
    if err:
        return {"success": False, "error": err}
    virtual_fs = str(Path(nfo_fs).with_suffix(".mp4"))
    scanner = VideoScanner(path_mappings=path_mappings, nfo_title_format=config.get('scraper', {}).get('nfo_title_format', '[{num}]{title}'))
    if scanner.parse_nfo(nfo_fs) is None:
        return {"success": False, "error": "nfo_unreadable"}
    video = Video.from_video_info(scanner.scan_file(virtual_fs))
    video.path = row.path  # readonly: restore source row path
    video.size_bytes = row.size_bytes
    video.mtime = row.mtime
    video.nfo_mtime = nfo_mtime_or_none(Path(nfo_fs)) or 0.0
    changed = _commit_refreshed_video(repo, video, config, path_mappings)
    return {"success": True, "status": "ok", "cover_changed": changed,
            "media_status": "skipped", "media": summarize_media(repo.get_media_probe_view(video.path))}


def _commit_refreshed_video(repo, video, config, path_mappings):
    old_sig = repo.get_cover_sig(video.path)
    video.user_tags = []
    repo.upsert(video)
    return sync_cover_and_thumbnail(repo, video.path, video.cover_path, old_sig, config, path_mappings).changed


class CoverThumbResult(NamedTuple):
    changed: bool
    thumb_ok: bool


def sync_cover_and_thumbnail(repo, video_path, cover_uri, old_sig, config, path_mappings) -> CoverThumbResult:
    try:
        cover_fs = uri_to_local_fs_path(cover_uri, path_mappings) if cover_uri else None
    except ValueError:
        cover_fs = None
    new_sig = read_cover_signature(cover_fs) if cover_fs else None
    changed = cover_changed(old_sig, new_sig)
    if changed:
        apply_cover_change(repo, video_path, cover_fs, path_mappings)
    if new_sig is not None:
        repo.set_cover_signature(video_path, *new_sig)
    thumbnail_cache.invalidate(video_path)
    thumb_ok = True
    if config.get('thumbnail_cache_enabled', False) and cover_fs and new_sig is not None:
        thumb_ok = thumbnail_cache.get_or_create(video_path, cover_fs) is not None
    return CoverThumbResult(changed, thumb_ok)


def refresh_one(repo, video, config, path_mappings):
    """重讀一般來源的資訊，保留資料庫中使用者自行維護的資料。"""
    if is_path_on_unreachable_source(video.path, config.get('gallery', {})):
        return {"success": False, "error": "unreachable"}
    if resolve_owning_output_root(video.path, config) is not None:
        return _refresh_readonly(repo, video, config, path_mappings)
    try:
        fs_path = uri_to_local_fs_path(video.path, path_mappings)
    except ValueError:
        return {"success": False, "error": "unreachable"}
    kind, st = stat_kind(fs_path)
    if kind == 'absent' and source_root_unreachable(video.path, config.get('gallery', {})):
        return {"success": False, "error": "unreachable"}
    if kind != 'ok':
        return {"success": False, "error": "not_found" if kind == 'absent' else "unreachable"}
    scanner = VideoScanner(path_mappings=path_mappings, nfo_title_format=config.get('scraper', {}).get('nfo_title_format', '[{num}]{title}'))
    nfo_path = Path(fs_path).with_suffix('.nfo')
    nfo_kind, _ = stat_kind(nfo_path)
    if nfo_kind == 'unreadable' or (nfo_kind == 'ok' and scanner.parse_nfo(str(nfo_path)) is None):
        return {"success": False, "error": "nfo_unreadable"}
    refreshed = Video.from_video_info(scanner.scan_file(fs_path))
    refreshed.path = video.path
    refreshed.mtime = st.st_mtime
    refreshed.size_bytes = st.st_size
    refreshed.nfo_mtime = nfo_mtime_or_none(Path(fs_path).with_suffix('.nfo')) or 0.0
    video = refreshed
    changed = _commit_refreshed_video(repo, video, config, path_mappings)
    if not media_probe.is_available():
        media_status = 'unavailable'
    else:
        media_status = probe_now(repo, video.path, fs_path, st.st_mtime, st.st_size)
    return {"success": True, "status": "ok", "cover_changed": changed,
            "media_status": media_status, "media": summarize_media(repo.get_media_probe_view(video.path))}
