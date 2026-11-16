"""Validate and update a video path without moving source files."""
import os
import posixpath
import stat
import unicodedata
from pathlib import Path

from core import thumbnail_cache
from core.cover_signature import read_cover_signature
from core.database import Video
from core.focal_trigger import schedule_focal_after_cover_write
from core.gallery_scanner import VideoScanner, is_nas_system_dir_name, is_scannable_video
from core.logger import get_logger
from core.media_probe_trigger import maybe_submit_media_probe
from core.nfo_stat import nfo_mtime_or_none
from core.path_utils import coerce_to_file_uri, is_path_under_dir, uri_to_local_fs_path
from core.readonly_source import is_path_readonly, readonly_source_prefixes, writable_source_prefixes
from core.video_extensions import get_video_extensions

logger = get_logger(__name__)


def _same(a, b):
    return is_path_under_dir(a, b) and is_path_under_dir(b, a)


def _owner(uri, sources):
    matches = [source for source in sources if is_path_under_dir(uri, source)]
    return max(matches, key=lambda source: len(source.split('/')), default=None)


def _source_base(source):
    stripped = source.rstrip('/')
    return source[:-1] if stripped == 'file:' else stripped


def scan_form_uri(new_uri, source_uris, listdir):
    """Use the scanner's source spelling and the filesystem's component spelling."""
    source = _owner(new_uri, source_uris)
    if source is None:
        return None
    source_parts = _source_base(source).split('/')
    rest = new_uri.split('/')[len(source_parts):]
    canonical = _source_base(source)
    # Windows-style equality differs from POSIX equality in the shared helper.
    windows = _same(source, source.swapcase()) and source != source.swapcase()
    for part in rest:
        names = listdir(canonical)
        if names is None:
            return None
        if part in names:
            chosen = part
        elif windows:
            key = unicodedata.normalize('NFC', part).casefold()
            matches = [name for name in names if unicodedata.normalize('NFC', name).casefold() == key]
            if len(matches) != 1:
                return None
            chosen = matches[0]
        else:
            return None
        canonical += '/' + chosen
    return canonical


def _listdir(uri, mappings):
    try:
        return os.listdir(uri_to_local_fs_path(uri, mappings))
    except (OSError, ValueError):
        return None


def _scannable(uri, root, mappings, file_stat, extensions, min_size):
    ext = posixpath.splitext(uri)[1].lower()
    if not is_scannable_video(ext, file_stat.st_size, extensions, min_size):
        return False
    parts = uri.split('/')
    root_parts = _source_base(root).split('/')
    current = _source_base(root)
    try:
        for part in parts[len(root_parts):-1]:
            if is_nas_system_dir_name(part):
                return False
            current += '/' + part
            if not stat.S_ISDIR(os.lstat(uri_to_local_fs_path(current, mappings)).st_mode):
                return False
        return stat.S_ISREG(os.lstat(uri_to_local_fs_path(uri, mappings)).st_mode)
    except (OSError, ValueError):
        return False


def _fail(code):
    return {'success': False, 'error': code}


def _finish(repo, row, video, new_uri, mappings):
    for uri in (row.path, new_uri):
        try:
            thumbnail_cache.invalidate(uri)
        except Exception:
            logger.exception('清除縮圖失敗')
    if video.cover_path:
        try:
            cover_fs = uri_to_local_fs_path(video.cover_path, mappings)
            sig = read_cover_signature(cover_fs)
            if sig is not None:
                repo.set_cover_signature(new_uri, *sig)
        except Exception:
            logger.exception('更新封面簽章失敗')
        if video.cover_path != row.cover_path:
            try:
                cover_fs = uri_to_local_fs_path(video.cover_path, mappings)
                schedule_focal_after_cover_write(repo, new_uri, video.number, video.maker, cover_fs, mappings)
            except Exception:
                logger.exception('排程焦點失敗')
    try:
        maybe_submit_media_probe(new_uri, db_path=repo.db_path, path_mappings=mappings)
    except Exception:
        logger.exception('排程媒體探針失敗')


def repath_video(repo, row, typed, confirm_name_change, config, path_mappings):
    gallery = config.get('gallery', {})
    ro_prefixes = readonly_source_prefixes(gallery, path_mappings)
    wr_prefixes = writable_source_prefixes(gallery, path_mappings)
    if is_path_readonly(row.path, ro_prefixes, wr_prefixes):
        return _fail("readonly")
    typed = typed.strip()
    if not typed:
        return _fail('not_found')
    try:
        new_uri = coerce_to_file_uri(typed, path_mappings)
    except (OSError, ValueError):
        return _fail('not_found')
    if _same(row.path, new_uri):
        return _fail('unchanged')
    extensions = get_video_extensions(config)
    if posixpath.splitext(new_uri)[1].lower() not in extensions:
        return _fail('not_video')
    try:
        fs_path = uri_to_local_fs_path(new_uri, path_mappings)
        file_stat = os.stat(fs_path)
        if not stat.S_ISREG(file_stat.st_mode):
            return _fail('not_found')
    except (OSError, ValueError):
        return _fail('not_found')
    root = _owner(new_uri, wr_prefixes)
    if root is None or is_path_readonly(new_uri, ro_prefixes, wr_prefixes):
        return _fail('out_of_library')
    new_uri = scan_form_uri(new_uri, wr_prefixes, lambda uri: _listdir(uri, path_mappings))
    if new_uri is None:
        return _fail('not_found')
    root = _owner(new_uri, wr_prefixes)
    minimum = int(gallery.get('min_size_mb', 0)) * 1024 * 1024
    if not _scannable(new_uri, root, path_mappings, file_stat, extensions, minimum):
        return _fail('not_scannable')
    if repo.get_by_path(new_uri) or any(_same(new_uri, uri) for uri in repo.get_mtime_index()):
        return _fail('already_in_library')
    name_changed = posixpath.splitext(posixpath.basename(row.path))[0] != posixpath.splitext(posixpath.basename(new_uri))[0]
    if name_changed and not confirm_name_change:
        return _fail('confirm_required')
    fs_path = uri_to_local_fs_path(new_uri, path_mappings)
    scanner = VideoScanner(path_mappings=path_mappings, nfo_title_format=config.get('scraper', {}).get('nfo_title_format', '[{num}]{title}'))
    video = Video.from_video_info(scanner.scan_file(fs_path))
    video.mtime = file_stat.st_mtime
    video.nfo_mtime = nfo_mtime_or_none(Path(fs_path).with_suffix('.nfo')) or 0
    video.path = new_uri
    video.user_tags = []
    repo.repath(row.path, new_uri, video)
    _finish(repo, row, video, new_uri, path_mappings)
    return {'success': True, 'path': new_uri, 'name_changed': name_changed}
