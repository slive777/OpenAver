"""Repath preserves the user's row and does not modify source files."""
import asyncio
import hashlib
import os
import sqlite3
from unittest.mock import Mock

import pytest
import httpx

from core import thumbnail_cache
from core.database import Video, VideoRepository, init_db
from core.gallery_scanner import VideoScanner, fast_scan_directory
from core.media_probe import ProbeResult
from core.path_utils import to_file_uri

pytestmark = pytest.mark.usefixtures('isolate_reconcile_db')


def _uri(path):
    return to_file_uri(str(path), {})


def _rows(db):
    with sqlite3.connect(db) as conn:
        return conn.execute('SELECT * FROM videos ORDER BY path').fetchall()


def _snapshot(root):
    return {str(p.relative_to(root)): (hashlib.sha256(p.read_bytes()).hexdigest(),
                                      p.lstat().st_mtime_ns, p.is_symlink())
            for p in root.rglob('*') if p.is_file()}


@pytest.fixture
def env(tmp_path, monkeypatch):
    lib = tmp_path / 'lib'
    ro = tmp_path / 'readonly'
    lib.mkdir()
    ro.mkdir()
    old = lib / 'ABF-348.mp4'
    new = lib / 'ABF-348.mkv'
    old.write_bytes(b'old')
    new.write_bytes(b'new video data')
    os.utime(old, (1700000000, 1700000000))
    os.utime(new, (1700000100, 1700000100))
    (lib / 'ABF-348.jpg').write_bytes(b'cover')
    (lib / 'ABF-348.nfo').write_text('<movie><title>title</title><user_tag>a</user_tag><user_tag>b</user_tag></movie>')
    db = tmp_path / 'video.db'
    init_db(db)
    repo = VideoRepository(db)
    video = Video.from_video_info(VideoScanner(path_mappings={}).scan_file(str(old)))
    video.mtime = old.stat().st_mtime
    repo.upsert(video)
    uri = _uri(old)
    repo.set_user_rating(uri, 5)
    repo.update_user_tags(uri, ['b', 'c'], ai_tagged=True)
    row = repo.get_by_path(uri)
    assert repo.update_manual_focal(uri, '0.4000', expected_cover_path=row.cover_path)
    st = old.stat()
    probe = ProbeResult('ok', '', 1920, 1080, 'AVC', 1000, None, 24.0, 1000, 'MPEG-4', (), (), False)
    assert repo.update_media_probe(uri, probe, st.st_mtime, st.st_size)
    config = {'gallery': {'directories': [{'path': str(lib), 'readonly': False},
                                          {'path': str(ro), 'readonly': True}],
                          'path_mappings': {}, 'min_size_mb': 0}}
    monkeypatch.setattr('web.routers.showcase_files.get_db_path', lambda: db)
    monkeypatch.setattr('web.routers.showcase_files.load_config', lambda: config)
    monkeypatch.setattr('core.thumbnail_cache._thumb_dir', lambda: tmp_path / 'thumb')
    monkeypatch.setattr('core.video_repath.maybe_submit_media_probe', Mock())
    monkeypatch.setattr('core.video_repath.schedule_focal_after_cover_write', Mock())
    from fastapi import FastAPI
    from web.routers.showcase_files import router
    app = FastAPI()
    app.include_router(router)

    async def inline_threadpool(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr('starlette.routing.run_in_threadpool', inline_threadpool)
    monkeypatch.setattr('fastapi.routing.run_in_threadpool', inline_threadpool)
    return dict(client=app, repo=repo, db=db, lib=lib, ro=ro, old=old,
                new=new, uri=uri, config=config, monkeypatch=monkeypatch)


def _post(env, new, old=None, confirm=False):
    async def request():
        transport = httpx.ASGITransport(app=env['client'], client=('127.0.0.1', 50000))
        async with httpx.AsyncClient(transport=transport, base_url='http://test') as client:
            return await client.post('/api/showcase/video/repath', json={
                'path': old or env['uri'], 'new_path': str(new), 'confirm_name_change': confirm})
    return asyncio.run(request())


@pytest.mark.parametrize('case,code', [
    ('readonly', 'readonly'), ('unchanged', 'unchanged'), ('text', 'not_video'),
    ('missing', 'not_found'), ('outside', 'out_of_library'), ('ro_target', 'out_of_library'),
    ('collision', 'already_in_library'), ('name', 'confirm_required'),
    ('small', 'not_scannable'), ('system', 'not_scannable'), ('symlink', 'not_scannable'),
    ('nfo', 'not_scannable'), ('symlink_dir', 'not_scannable'),
    ('exception', 'repath_failed'),
])
def test_repath_error_codes(env, tmp_path, case, code):
    lib, ro, repo = env['lib'], env['ro'], env['repo']
    target, old = env['new'], env['uri']
    if case == 'readonly':
        p = ro / 'old.mp4'; p.write_bytes(b'ro'); old = _uri(p)
        repo.upsert(Video(path=old, number='RO-001', title='ro'))
    elif case == 'unchanged': target = env['old']
    elif case == 'text': target = lib / 'x.txt'; target.write_bytes(b'x')
    elif case == 'missing': target = lib / 'missing.mkv'
    elif case == 'outside': target = tmp_path / 'outside.mkv'; target.write_bytes(b'x')
    elif case == 'ro_target': target = ro / 'target.mkv'; target.write_bytes(b'x')
    elif case == 'collision': repo.upsert(Video(path=_uri(target), number='X', title='x'))
    elif case == 'name': target = lib / 'OTHER.mkv'; target.write_bytes(b'x')
    elif case == 'small': env['config']['gallery']['min_size_mb'] = 1
    elif case == 'system':
        folder = lib / '@eaDir'; folder.mkdir(); target = folder / 'ABF-348.mkv'; target.write_bytes(b'x')
    elif case == 'symlink': target = lib / 'link.mkv'; target.symlink_to(env['new'])
    elif case == 'symlink_dir':
        folder = lib / 'linked'; folder.symlink_to(lib, target_is_directory=True); target = folder / env['new'].name
    elif case == 'exception':
        env['monkeypatch'].setattr('core.video_repath.repath_video', Mock(side_effect=RuntimeError('test')))
    elif case == 'nfo':
        env['config']['scraper'] = {'video_extensions': ['.nfo']}; target = lib / 'ABF-348.nfo'
    thumb = thumbnail_cache.thumb_file_for(old)
    thumb.parent.mkdir(parents=True, exist_ok=True)
    thumb.write_bytes(b'cached thumbnail')
    before = (_rows(env['db']), _snapshot(lib), _snapshot(ro), _snapshot(thumb.parent))
    response = _post(env, target, old)
    assert response.status_code == (500 if case == 'exception' else 200)
    assert response.json() == {'success': False, 'error': code}
    assert (_rows(env['db']), _snapshot(lib), _snapshot(ro), _snapshot(thumb.parent)) == before
    from core import video_repath
    video_repath.maybe_submit_media_probe.assert_not_called()
    video_repath.schedule_focal_after_cover_write.assert_not_called()


@pytest.mark.parametrize('tags', [['b', 'c'], []])
def test_repath_keeps_user_data(env, monkeypatch, tags):
    repo, uri = env['repo'], env['uri']
    repo.update_user_tags(uri, tags, ai_tagged=True)
    before = repo.get_by_path(uri)
    with sqlite3.connect(env['db']) as conn:
        identity = conn.execute('SELECT id, ai_tagged_at FROM videos WHERE path=?', (uri,)).fetchone()
        count = conn.execute('SELECT count(*) FROM videos').fetchone()[0]
    thumb = thumbnail_cache.thumb_file_for(uri)
    thumb.parent.mkdir(parents=True); thumb.write_bytes(b'thumb')
    submit = Mock(); focal = Mock()
    monkeypatch.setattr('core.video_repath.maybe_submit_media_probe', submit)
    monkeypatch.setattr('core.video_repath.schedule_focal_after_cover_write', focal)
    response = _post(env, env['new'])
    assert response.json()['success'] is True
    new_uri = _uri(env['new'])
    row = repo.get_by_path(new_uri)
    assert repo.get_by_path(uri) is None
    with sqlite3.connect(env['db']) as conn:
        assert conn.execute('SELECT id, ai_tagged_at FROM videos WHERE path=?', (new_uri,)).fetchone() == identity
        assert conn.execute('SELECT count(*) FROM videos').fetchone()[0] == count
    assert row.user_rating == before.user_rating == 5
    assert row.user_tags == tags
    assert (row.crop_mode, row.auto_focal) == (before.crop_mode, before.auto_focal)
    assert row.size_bytes == env['new'].stat().st_size
    assert row.mtime == env['new'].stat().st_mtime
    assert not thumb.exists()
    assert not repo.get_media_probe_view(new_uri).key_matches
    cover_stat = (env['lib'] / 'ABF-348.jpg').stat()
    assert repo.get_cover_sig(new_uri) == (cover_stat.st_mtime_ns, cover_stat.st_size)
    submit.assert_called_once(); assert submit.call_args.args[0] == new_uri
    focal.assert_not_called()


def test_repath_stored_uri_equals_scanner_uri(env, monkeypatch):
    monkeypatch.setattr('core.video_repath.maybe_submit_media_probe', Mock())
    assert _post(env, env['new']).json()['success']
    info = next(x for x in fast_scan_directory(str(env['lib']), {'.mp4', '.mkv'}, 0)
                if x['path'] == str(env['new']))
    uri = _uri(info['path'])
    assert env['repo'].get_by_path(uri).path == uri
    assert env['repo'].get_mtime_index()[uri] == (info['mtime'], info['nfo_mtime'], info['sample_image_count'], info['size'])


def test_repath_name_change_needs_confirm(env, monkeypatch):
    target = env['lib'] / 'OTHER-001.mkv'; target.write_bytes(b'new')
    monkeypatch.setattr('core.video_repath.maybe_submit_media_probe', Mock())
    before = env['repo'].get_by_path(env['uri'])
    with sqlite3.connect(env['db']) as conn:
        old_id = conn.execute('SELECT id FROM videos WHERE path=?', (env['uri'],)).fetchone()[0]
    assert _post(env, target).json()['error'] == 'confirm_required'
    response = _post(env, target, confirm=True).json()
    assert response['success'] and response['name_changed']
    row = env['repo'].get_by_path(_uri(target))
    assert not row.cover_path and not row.nfo_mtime
    with sqlite3.connect(env['db']) as conn:
        assert conn.execute('SELECT id FROM videos WHERE path=?', (_uri(target),)).fetchone()[0] == old_id
    assert row.user_rating == before.user_rating and row.user_tags == before.user_tags


def test_repath_touches_no_files(env, monkeypatch):
    monkeypatch.setattr('core.video_repath.maybe_submit_media_probe', Mock())
    before = (_snapshot(env['lib']), _snapshot(env['ro']))
    assert _post(env, env['new']).json()['success']
    assert (_snapshot(env['lib']), _snapshot(env['ro'])) == before
