import hashlib
import os

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from core import thumbnail_cache
from core.database import Video, VideoRepository, init_db
from core.media_probe import ProbeResult
from core.path_utils import to_file_uri
from core.video_files_info import summarize_media

pytestmark = pytest.mark.usefixtures('isolate_reconcile_db')


def _probe(status='ok', width=1920):
    return ProbeResult(status=status, reason='', width=width if status == 'ok' else None,
                       height=1080 if status == 'ok' else None, video_format='HEVC' if status == 'ok' else None,
                       duration_ms=1000 if status == 'ok' else None, hdr_format=None, frame_rate=None,
                       overall_bitrate=None, container=None, audio_langs=(), subtitle_langs=(), truncated=False)


def _env(tmp_path, monkeypatch, mocker, layout='cover'):
    folder = tmp_path / 'library'
    folder.mkdir()
    video = folder / 'ABF-348.mp4'
    video.write_bytes(b'old video')
    video.with_suffix('.nfo').write_text('<movie><title>Old</title><num>ABF-348</num><user_tag>nfo</user_tag></movie>')
    names = {'cover': ['ABF-348.jpg'], 'both': ['ABF-348-fanart.jpg', 'ABF-348-poster.jpg'], 'poster': ['ABF-348-poster.jpg']}[layout]
    for i, name in enumerate(names):
        Image.new('RGB', (200, 120), (30 + i * 100, 40, 50)).save(folder / name)
    cover = folder / names[0]
    db = tmp_path / 'test.db'
    init_db(db)
    repo = VideoRepository(db)
    uri = to_file_uri(str(video))
    st = video.stat()
    repo.upsert(Video(path=uri, number='ABF-348', title='Old', cover_path=to_file_uri(str(cover)), mtime=st.st_mtime, size_bytes=st.st_size))
    config = {'gallery': {'directories': [{'path': str(folder), 'readonly': False, 'output_path': ''}], 'path_mappings': {}}, 'scraper': {'nfo_title_format': '[{num}]{title}'}}
    monkeypatch.setattr('web.routers.showcase_files.get_db_path', lambda: db)
    monkeypatch.setattr('web.routers.showcase_files.load_config', lambda: config)
    monkeypatch.setattr('core.readonly_paths.get_db_path', lambda: db)
    mocker.patch('core.thumbnail_cache._thumb_dir', return_value=tmp_path / 'thumbs')
    mocker.patch('core.media_probe.is_available', return_value=False)
    from web.app import app
    return TestClient(app), repo, uri, video, cover, config


def _snapshot(folder):
    return {str(p.relative_to(folder)): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
            for p in folder.rglob('*') if p.is_file()}


@pytest.mark.parametrize('layout', ['cover', 'both', 'poster', 'root_gone', 'missing'])
def test_refresh_writes_nothing_to_disk(tmp_path, monkeypatch, mocker, layout):
    client, _, uri, video, _, _ = _env(tmp_path, monkeypatch, mocker, 'cover' if layout in ('root_gone', 'missing') else layout)
    snapshot_root = video.parent
    if layout == 'root_gone':
        video.parent.rename(tmp_path / 'disconnected')
        monkeypatch.setattr('core.source_reachability._snapshot', {str(video.parent): 'ok'})
        snapshot_root = tmp_path
    elif layout == 'missing':
        video.unlink()
    before = _snapshot(snapshot_root)
    response = client.post('/api/showcase/video/refresh', json={'path': uri})
    assert response.status_code == 200
    if layout in ('root_gone', 'missing'):
        assert response.json() == {'success': False, 'error': 'unreachable' if layout == 'root_gone' else 'not_found'}
    else:
        assert response.json()['success'] is True
    assert _snapshot(snapshot_root) == before


def test_refresh_rereads_nfo_keeps_user_data(tmp_path, monkeypatch, mocker):
    client, repo, uri, video, cover, config = _env(tmp_path, monkeypatch, mocker)
    config['thumbnail_cache_enabled'] = True
    assert repo.update_user_tags(uri, ['mine'], ai_tagged=True)
    assert repo.set_user_rating(uri, 1)
    before = repo.get_by_path(uri)
    ai_before = repo.get_ai_tagged_at(uri)
    st = cover.stat()
    assert repo.set_cover_signature(uri, st.st_mtime_ns, st.st_size)
    video.with_suffix('.nfo').write_text('<movie><title>New</title><num>ABF-348</num></movie>')
    sample = video.parent / 'extrafanart'
    sample.mkdir()
    (sample / 'one.jpg').write_bytes(b'sample')
    Image.new('RGB', (200, 120), (200, 10, 50)).save(cover)
    os.utime(cover, ns=(st.st_atime_ns, st.st_mtime_ns + 1000000000))
    response = client.post('/api/showcase/video/refresh', json={'path': uri})
    assert response.status_code == 200 and response.json()['cover_changed'] is True
    after = repo.get_by_path(uri)
    assert (after.id, after.user_rating, after.user_tags) == (before.id, before.user_rating, before.user_tags)
    assert repo.get_ai_tagged_at(uri) == ai_before
    assert len(repo.get_all()) == 1
    assert after.title == 'New' and after.sample_images == [to_file_uri(str(sample / 'one.jpg'))]
    thumb = thumbnail_cache.thumb_file_for(uri)
    actual = thumb.read_bytes()
    thumbnail_cache.invalidate(uri)
    expected = thumbnail_cache.get_or_create(uri, str(cover)).read_bytes()
    assert actual == expected


@pytest.mark.parametrize('case', ['same', 'unreadable', 'replaced'])
def test_refresh_probe_forced_same_source(tmp_path, monkeypatch, mocker, case):
    client, repo, uri, video, _, _ = _env(tmp_path, monkeypatch, mocker)
    st = video.stat()
    assert repo.update_media_probe(uri, _probe(width=1280), st.st_mtime, st.st_size)
    before = summarize_media(repo.get_media_probe_view(uri))
    if case == 'replaced':
        video.write_bytes(b'a different and much longer video file')
    mocker.patch('core.media_probe.is_available', return_value=True)
    mocker.patch('core.media_probe.probe_file', return_value=_probe('unreadable') if case == 'unreadable' else _probe(width=1920))
    response = client.post('/api/showcase/video/refresh', json={'path': uri})
    assert response.status_code == 200
    body = response.json()
    assert body['success'] is True
    if case == 'unreadable':
        assert body['media_status'] == 'unreadable' and body['media'] == before
    else:
        assert body['media_status'] == 'ok' and body['media']['width'] == 1920
        assert body['media']['size'] == video.stat().st_size
