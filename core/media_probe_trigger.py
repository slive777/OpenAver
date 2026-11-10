"""core.media_probe_trigger — 入庫後條件式排探針（TASK-198a-T2a，CD-198a-5）。

本 task 只備好 helper，不接任何入庫路徑（T2b）。
任何例外吞掉記 log（比照 focal_trigger 安全退化）；不吞 BaseException。
"""
from __future__ import annotations

from core import media_probe
from core.database.video import VideoRepository
from core.logger import get_logger
from core.media_probe_worker import submit_media_probe
from core.path_utils import uri_to_local_fs_path
from core.readonly_source import is_path_readonly

logger = get_logger(__name__)


def maybe_submit_media_probe(
    video_uri,
    *,
    db_path=None,
    readonly_prefixes=None,
    writable_prefixes=None,
    path_mappings=None,
):
    """可用性閘 → 讀列 → 唯讀判定 → I4 key 比對 → submit。

    prefix／path_mappings 為 None 時自己 load_config()。
    入庫時唯讀列一律不讀（不看 include_readonly）。
    """
    try:
        if not media_probe.is_available():
            return
        if readonly_prefixes is None or writable_prefixes is None or path_mappings is None:
            from core.config import load_config
            from core.readonly_source import (
                readonly_source_prefixes,
                writable_source_prefixes,
            )

            gallery = load_config().get("gallery", {}) or {}
            mappings = gallery.get("path_mappings", {}) or {}
            if path_mappings is None:
                path_mappings = mappings
            if readonly_prefixes is None:
                readonly_prefixes = readonly_source_prefixes(gallery, path_mappings)
            if writable_prefixes is None:
                writable_prefixes = writable_source_prefixes(gallery, path_mappings)

        repo = VideoRepository(db_path)
        view = repo.get_media_probe_view(video_uri)
        if view is None:
            return
        if is_path_readonly(video_uri, readonly_prefixes or [], writable_prefixes or []):
            return
        if view.key_matches:
            return
        fs_path = uri_to_local_fs_path(video_uri, path_mappings or {})
        submit_media_probe(
            video_uri,
            fs_path,
            view.mtime,
            view.size_bytes,
            db_path=db_path,
        )
    except Exception:
        logger.exception(
            "maybe_submit_media_probe 排程失敗（不影響呼叫端流程）: %s", video_uri
        )
