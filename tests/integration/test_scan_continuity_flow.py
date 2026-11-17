import os
import sqlite3
import types
from contextlib import ExitStack
from unittest.mock import patch

import pytest

from core.database import VideoRepository, init_db
from core.gallery_scanner import VideoScanner, fast_scan_directory
from core.media_probe import ProbeResult
from core.path_utils import to_file_uri

pytestmark = pytest.mark.usefixtures('isolate_reconcile_db')


def _run_generate(db, directory, out):
    from web.routers.scanner import generate_avlist

    config = {'gallery': {'directories': [{'path': str(directory), 'readonly': False, 'output_path': ''}],
                          'output_dir': str(out), 'output_filename': 'gallery_output.html',
                          'path_mappings': {}, 'min_size_mb': 0, 'default_mode': 'image',
                          'default_sort': 'date', 'default_order': 'descending', 'items_per_page': 90},
              'general': {'theme': 'light'}, 'search': {'proxy_url': ''},
              'scraper': {'video_extensions': ['.mp4', '.mkv'], 'nfo_title_format': '[{num}]{title}'}}
    patches = [
        patch('web.routers.scanner.load_config', return_value=config),
        patch('web.routers.scanner.get_gallery_source_paths', return_value=[str(directory)]),
        patch('web.routers.scanner.get_db_path', return_value=db),
        patch('web.routers.scanner.HTMLGenerator'),
        patch('web.routers.scanner._run_sample_images_cleanup_pass', return_value=0),
        patch('web.routers.scanner.check_cache_needs_update', return_value={'need_update': 0, 'paths': [], 'items': []}),
        patch('web.routers.scanner._emit_notif'),
        patch('core.similar.ranker_cache.SimilarRankerCache'),
        patch('web.routers.scanner._schedule_ai_incremental'),
        patch('web.routers.scanner.maybe_submit_video_focal'),
        patch('web.routers.scanner._schedule_media_probes'),
        patch('web.routers.scanner.iter_gallery_sources', return_value=[types.SimpleNamespace(path=str(directory), readonly=False, output_path='')]),
    ]
    with ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        list(generate_avlist())


def _setup(tmp_path, monkeypatch):
    directory = tmp_path / 'lib'
    directory.mkdir()
    out = tmp_path / 'out'
    out.mkdir()
    db = tmp_path / 'test.db'
    init_db(db)
    monkeypatch.setattr('core.database.connection.get_db_path', lambda: db)
    old = directory / 'ABF-348.mp4'
    old.write_bytes(b'old video')
    os.utime(old, (1700000000, 1700000000))
    (directory / 'ABF-348.jpg').write_bytes(b'cover')
    _run_generate(db, directory, out)
    return directory, out, db, VideoRepository(db), old


def _id(db, uri):
    with sqlite3.connect(db) as conn:
        return conn.execute('SELECT id FROM videos WHERE path = ?', (uri,)).fetchone()[0]


def _replace(old):
    old.unlink()
    new = old.with_suffix('.mkv')
    new.write_bytes(b'new video with different size')
    os.utime(new, (1700000100, 1700000100))
    return new


def test_continuation_keeps_user_data(tmp_path, monkeypatch):
    directory, out, db, repo, old = _setup(tmp_path, monkeypatch)
    old_uri = to_file_uri(str(old))
    assert repo.set_user_rating(old_uri, 5)
    assert repo.update_user_tags(old_uri, ['kept'], ai_tagged=True)
    row = repo.get_by_path(old_uri)
    assert row.cover_path
    assert repo.update_manual_focal(old_uri, '0.4000', expected_cover_path=row.cover_path)
    st = old.stat()
    probe = ProbeResult(status='ok', reason='', width=1920, height=1080, video_format='AVC', duration_ms=1000, hdr_format=None, frame_rate=24.0, overall_bitrate=1000, container='MPEG-4', audio_langs=(), subtitle_langs=(), truncated=False)
    assert repo.update_media_probe(old_uri, probe, st.st_mtime, st.st_size)
    before = repo.get_by_path(old_uri)
    before_id = _id(db, old_uri)
    with sqlite3.connect(db) as conn:
        ai_before = conn.execute('SELECT ai_tagged_at FROM videos WHERE path = ?', (old_uri,)).fetchone()[0]
    assert ai_before is not None
    invalidated = []
    monkeypatch.setattr('core.thumbnail_cache.invalidate', invalidated.append)
    new_uri = to_file_uri(str(_replace(old)))
    _run_generate(db, directory, out)
    after = repo.get_by_path(new_uri)
    assert _id(db, new_uri) == before_id
    assert repo.get_by_path(old_uri) is None
    assert (after.user_rating, after.user_tags, after.auto_focal, after.crop_mode) == (before.user_rating, before.user_tags, before.auto_focal, before.crop_mode)
    assert (before.auto_focal, before.crop_mode) == ('0.4000', 'manual')
    with sqlite3.connect(db) as conn:
        assert conn.execute('SELECT ai_tagged_at FROM videos WHERE path = ?', (new_uri,)).fetchone()[0] == ai_before
    with sqlite3.connect(db) as conn:
        assert conn.execute('SELECT count(*) FROM videos').fetchone()[0] == 1
    assert not repo.get_media_probe_view(new_uri).key_matches
    assert invalidated == [old_uri]


def test_skipped_paths_block_continuation(tmp_path, monkeypatch):
    directory, out, db, repo, old = _setup(tmp_path, monkeypatch)
    old_uri = to_file_uri(str(old))
    old_id = _id(db, old_uri)
    new_uri = to_file_uri(str(_replace(old)))
    def partial(directory, extensions, minimum, on_skip=None):
        result = fast_scan_directory(directory, extensions, minimum)
        on_skip(str(directory), PermissionError('denied'))
        return result
    monkeypatch.setattr('web.routers.scanner.fast_scan_directory', partial)
    _run_generate(db, directory, out)
    assert repo.get_by_path(old_uri) is not None
    assert _id(db, new_uri) != old_id


def test_coexisting_files_not_continued(tmp_path, monkeypatch):
    directory, out, db, repo, old = _setup(tmp_path, monkeypatch)
    old_uri = to_file_uri(str(old))
    assert repo.set_user_rating(old_uri, 5)
    assert repo.update_user_tags(old_uri, ['old'])
    before = repo.get_by_path(old_uri)
    old_id = _id(db, old_uri)
    new = old.with_suffix('.mkv')
    new.write_bytes(b'new video')
    invalidated = []
    monkeypatch.setattr('core.thumbnail_cache.invalidate', invalidated.append)
    _run_generate(db, directory, out)
    new_uri = to_file_uri(str(new))
    assert _id(db, old_uri) == old_id
    assert _id(db, new_uri) != old_id
    assert repo.get_by_path(old_uri).user_tags == before.user_tags
    assert repo.get_by_path(old_uri).user_rating == before.user_rating
    assert repo.get_by_path(new_uri).user_tags != before.user_tags
    assert not invalidated


@pytest.mark.parametrize('tags,concurrent', [(['nfo', 'extra'], False), (['other'], False), ([], False), (['other'], True)])
def test_continued_row_tags_follow_db_not_nfo(tmp_path, monkeypatch, tags, concurrent):
    directory, out, db, repo, old = _setup(tmp_path, monkeypatch)
    old_uri = to_file_uri(str(old))
    assert repo.update_user_tags(old_uri, tags)
    before = repo.get_by_path(old_uri).user_tags
    (directory / 'ABF-348.nfo').write_text('<movie><user_tag>nfo</user_tag></movie>', encoding='utf-8')
    new_uri = to_file_uri(str(_replace(old)))
    if concurrent:
        original = VideoScanner.scan_file
        def scan(self, path, base_path=None):
            info = original(self, path, base_path)
            assert repo.update_user_tags(new_uri, before + ['concurrent'])
            return info
        monkeypatch.setattr(VideoScanner, 'scan_file', scan)
    _run_generate(db, directory, out)
    assert repo.get_by_path(new_uri).user_tags == before + (['concurrent'] if concurrent else [])
