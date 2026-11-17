"""Conservative continuity for video files whose extension changed."""
import os
import posixpath
from collections import defaultdict

from core import thumbnail_cache
from core.logger import get_logger
from core.path_utils import is_path_under_dir, to_file_uri, uri_to_local_fs_path

logger = get_logger(__name__)


def match_renamed_videos(deleted_uris, new_uris, exists_fn):
    """Match only unambiguous, missing old files with the same directory and stem."""
    old_groups = defaultdict(list)
    new_groups = defaultdict(list)
    for uri in deleted_uris:
        old_groups[posixpath.splitext(uri)[0]].append(uri)
    for uri in new_uris:
        new_groups[posixpath.splitext(uri)[0]].append(uri)
    matches = []
    for key, olds in old_groups.items():
        news = new_groups.get(key, [])
        if len(olds) != 1 or len(news) != 1:
            continue
        if exists_fn(olds[0]):
            continue
        if posixpath.splitext(olds[0])[1] != posixpath.splitext(news[0])[1]:
            matches.append((olds[0], news[0]))
    return matches


def continue_renamed_videos(repo, db_index, all_files, normalized_dir, path_mappings, skipped_paths):
    """Repath matching rows before the normal incremental and deletion checks."""
    if skipped_paths:
        return set()
    current = {to_file_uri(info['path'], path_mappings) for info in all_files}
    new = [uri for uri in current if uri not in db_index]
    if not new:
        return set()
    dir_uri = to_file_uri(normalized_dir, path_mappings)
    deleted = [uri for uri in db_index if uri not in current and is_path_under_dir(uri, dir_uri)]

    def exists(uri):
        try:
            os.stat(uri_to_local_fs_path(uri, path_mappings))
        except (FileNotFoundError, NotADirectoryError):
            return False
        except OSError:
            return True
        return True

    continued = set()
    for old, new_uri in match_renamed_videos(deleted, new, exists):
        try:
            success = repo.repath_path_only(old, new_uri)
        except Exception:
            logger.exception('接續影片路徑失敗: %s', old)
            continue
        if not success:
            continue
        db_index[new_uri] = db_index.pop(old)
        continued.add(new_uri)
        logger.info('接續影片路徑: %s → %s', old, new_uri)
        try:
            thumbnail_cache.invalidate(old)
        except Exception:
            logger.exception('清除舊影片縮圖失敗: %s', old)
    return continued


def clear_user_tags_for_continued(videos, continued_uris):
    """Keep the database authoritative for tags on continued rows."""
    for video in videos:
        if video.path in continued_uris:
            video.user_tags = []
