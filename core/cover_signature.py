"""core.cover_signature — 封面簽章網址版本記號（200b-T2 CD-200b-4）。"""


def cover_version_suffix(sig) -> str:
    """有簽章回 ``&v=<mtime_ns>-<size>``；None／半缺回 ``""``。"""
    if sig is None:
        return ""
    mtime_ns, size = sig
    if mtime_ns is None or size is None:
        return ""
    return f"&v={mtime_ns}-{size}"


def cover_changed(db_sig, live_sig) -> bool:
    return db_sig is not None and live_sig is not None and db_sig != live_sig


def read_cover_signature(cover_fs):
    """讀不到封面時保留未知狀態。"""
    import os

    try:
        st = os.stat(cover_fs)
    except OSError:
        return None
    return st.st_mtime_ns, st.st_size


def apply_cover_change(repo, video_uri, cover_fs, path_mappings) -> None:
    """失效縮圖，僅重設自動裁切。"""
    from core import thumbnail_cache
    from core.focal_trigger import schedule_focal_after_cover_write

    thumbnail_cache.invalidate(video_uri)
    video = repo.get_by_path(video_uri)
    if video is None:
        return
    if video.crop_mode == 'auto':
        schedule_focal_after_cover_write(
            repo, video_uri, video.number, video.maker, cover_fs, path_mappings,
        )
