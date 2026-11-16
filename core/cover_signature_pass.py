"""更新片庫時比較封面簽章，保留手動裁切。"""

import time
from typing import NamedTuple

from core.config import get_configured_gallery_dirs
from core.cover_signature import apply_cover_change, cover_changed, read_cover_signature
from core.logger import get_logger
from core.path_utils import is_path_under_dir, uri_to_local_fs_path
from core.source_reachability import is_path_on_unreachable_source

logger = get_logger(__name__)


class CoverPassStats(NamedTuple):
    checked: int
    changed: int
    seconds: float


def run_cover_signature_pass(repo, config, path_mappings, should_abort=None) -> CoverPassStats:
    started = time.monotonic()
    configured_dir_uris, _ = get_configured_gallery_dirs(config)
    sig_map = repo.get_cover_sig_map()
    checked = changed = 0
    pending = []
    for video in repo.get_all():
        if should_abort is not None and should_abort():
            break
        if not video.cover_path or not any(is_path_under_dir(video.path, uri) for uri in configured_dir_uris):
            continue
        if is_path_on_unreachable_source(video.path, config.get('gallery', {})):
            continue
        try:
            cover_fs = uri_to_local_fs_path(video.cover_path, path_mappings)
        except ValueError:
            continue
        live = read_cover_signature(cover_fs)
        if live is None:
            continue
        checked += 1
        db_sig = sig_map.get(video.path)
        if cover_changed(db_sig, live):
            try:
                apply_cover_change(repo, video.path, cover_fs, path_mappings)
                repo.set_cover_signature(video.path, *live)
                changed += 1
            except Exception:
                logger.exception('封面變更處理失敗: %s', video.path)
        elif db_sig is None:
            pending.append((video.path, *live))
    if pending:
        repo.set_cover_signatures(pending)
    return CoverPassStats(checked, changed, time.monotonic() - started)
