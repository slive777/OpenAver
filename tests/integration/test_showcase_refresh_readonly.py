import hashlib
import os
from pathlib import Path
from unittest.mock import MagicMock
import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from core.database import VideoRepository, init_db
from core.path_utils import to_file_uri, uri_to_local_fs_path
from core import readonly_paths, readonly_producer

pytestmark = pytest.mark.usefixtures('isolate_reconcile_db')


def _download(url, save_path, referer=''):
    Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    Path(save_path).write_bytes(('image:' + url).encode())
    return True


def _jellyfin(cover_fs, base_stem, **kwargs):
    Path(base_stem + '-poster.jpg').write_bytes(b'poster')
    fanart = Path(base_stem + '-fanart.jpg')
    if str(fanart) != cover_fs:
        fanart.write_bytes(b'fanart')
    return {'poster': True, 'fanart': True}


def _env(tmp_path, monkeypatch, mocker, layout='jellyfin'):
    source = tmp_path / 'source'
    source.mkdir()
    video = source / 'TEST-001-C.mp4'
    video.write_bytes(b'video bytes')
    db = tmp_path / 'test.db'
    init_db(db)
    repo = VideoRepository(db)
    output = tmp_path / 'output' if layout == 'jellyfin' else db.parent / 'lib' / readonly_paths._derive_source_name(str(source))
    output.mkdir(parents=True)
    scraper = {'external_manager': layout, 'filename_format': '{num} {title}',
               'nfo_title_format': '[{num}]{title}', 'folder_layers': [], 'folder_format': '',
               'max_filename_length': 60, 'max_title_length': 50, 'suffix_keywords': [],
               'download_sample_images': True}
    config = {'gallery': {'directories': [{'path': str(source), 'readonly': True, 'output_path': str(output)}],
                          'path_mappings': {}}, 'scraper': scraper}
    meta = {'number': 'TEST-001', 'title': 'Test Movie Title', 'cover': 'https://example.com/cover.jpg',
            'actors': ['Actress A', 'Actress B'], 'tags': ['tag1', 'tag2'], 'date': '2024-01-01',
            'maker': 'Test Maker', 'director': 'Test Director', 'series': 'Test Series',
            'label': 'Test Label', 'sample_images': ['https://example.com/1.jpg', 'https://example.com/2.jpg'],
            'duration': 120, '_summary': 'Test summary', '_rating': 8.5, 'url': 'https://example.com/video'}
    monkeypatch.setattr('core.readonly_assets.download_image', _download)
    monkeypatch.setattr('core.readonly_assets.generate_jellyfin_images', _jellyfin)
    monkeypatch.setattr('web.routers.showcase_files.get_db_path', lambda: db)
    monkeypatch.setattr('web.routers.showcase_files.load_config', lambda: config)
    monkeypatch.setattr('core.readonly_paths.get_db_path', lambda: db)
    monkeypatch.setattr('core.thumbnail_cache.get_db_path', lambda: db)
    monkeypatch.setattr('core.database.connection.get_db_path', lambda: db)
    mocker.patch('core.focal_trigger.schedule_focal_after_cover_write')
    mocker.patch('core.media_probe.is_available', return_value=True)
    probe = mocker.patch('core.video_refresh.probe_now', side_effect=AssertionError('unexpected probe'))
    st = video.stat()
    file_info = {'path': str(video), 'size': st.st_size, 'mtime': st.st_mtime}
    args = dict(file_info=file_info, meta=meta, cover_strategy=('download', meta['cover']),
                output_root=str(output), output_uri=to_file_uri(str(output)), allocated_this_run=set(), path_mappings={})
    movie_dir, _ = readonly_producer._produce_one(repo, MagicMock(), scraper, assets_mode='full', existing=None, **args)
    uri = to_file_uri(str(video))
    assert repo.get_by_path(uri) is not None
    readonly_producer._produce_one(repo, MagicMock(), scraper, assets_mode='samples_only', existing=repo.get_by_path(uri), **args)
    nfo, = Path(movie_dir).glob('*.nfo')
    assert nfo.stem != video.stem
    from web.app import app
    return TestClient(app), repo, uri, source, output, nfo, config, probe


def _snapshot(root):
    return {str(p.relative_to(root)): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
            for p in root.rglob('*') if p.is_file()}


def _post(client, uri):
    response = client.post('/api/showcase/video/refresh', json={'path': uri})
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize('layout', ['off', 'jellyfin'])
def test_readonly_refresh_is_idempotent(tmp_path, monkeypatch, mocker, layout):
    client, repo, uri, _, _, _, _, probe = _env(tmp_path, monkeypatch, mocker, layout)
    before = repo.get_by_path(uri)
    result = _post(client, uri)
    assert result['success'] is True
    after = repo.get_by_path(uri)
    for field in ('title', 'original_title', 'actresses', 'maker', 'tags', 'series', 'label',
                  'release_date', 'cover_path', 'sample_images', 'has_plot', 'number', 'director',
                  'duration', 'nfo_mtime', 'size_bytes', 'mtime', 'output_dir', 'scrape_attempted_at', 'id'):
        assert getattr(after, field) == getattr(before, field), field
    assert len(repo.get_all()) == 1
    assert result['media_status'] == 'skipped'
    probe.assert_not_called()


def test_readonly_refresh_follows_output_edits_and_writes_nothing(tmp_path, monkeypatch, mocker):
    client, repo, uri, source, output, nfo, _, probe = _env(tmp_path, monkeypatch, mocker)
    submit = mocker.patch('core.media_probe_trigger.maybe_submit_media_probe', side_effect=AssertionError('unexpected probe submission'))
    repo.update_user_tags(uri, ['mine'], ai_tagged=True)
    repo.set_user_rating(uri, 1)
    before = repo.get_by_path(uri)
    ai_before = repo.get_ai_tagged_at(uri)
    cover = Path(uri_to_local_fs_path(before.cover_path, {}))
    st = cover.stat()
    repo.set_cover_signature(uri, st.st_mtime_ns, st.st_size)
    tree = ET.parse(nfo)
    title = tree.find('title')
    title.text += 'X'
    tree.write(nfo, encoding='utf-8', xml_declaration=True)
    cover.write_bytes(b'new cover bytes')
    os.utime(cover, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
    sample = nfo.parent / 'extrafanart' / 'fanart3.jpg'
    sample.write_bytes(b'new sample')
    snapshots = _snapshot(source), _snapshot(output)
    result = _post(client, uri)
    assert result['success'] is True and result['cover_changed'] is True
    assert result['media_status'] == 'skipped'
    after = repo.get_by_path(uri)
    assert after.title == before.title + 'X'
    assert to_file_uri(str(sample)) in after.sample_images
    for field in ('id', 'user_rating', 'cover_path', 'output_dir', 'size_bytes', 'mtime', 'scrape_attempted_at'):
        assert getattr(after, field) == getattr(before, field), field
    assert repo.get_ai_tagged_at(uri) == ai_before
    assert len(repo.get_all()) == 1
    assert (_snapshot(source), _snapshot(output)) == snapshots
    probe.assert_not_called()
    submit.assert_not_called()


@pytest.mark.parametrize('case', ['no_nfo', 'outside', 'nfo_ambiguous', 'nfo_unreadable'])
def test_readonly_refresh_without_usable_nfo_changes_nothing(tmp_path, monkeypatch, mocker, case):
    client, repo, uri, source, output, nfo, config, _ = _env(tmp_path, monkeypatch, mocker)
    if case == 'no_nfo':
        nfo.unlink()
    elif case == 'outside':
        config['gallery']['directories'][0]['output_path'] = str(tmp_path / 'other')
    elif case == 'nfo_ambiguous':
        (nfo.parent / 'alias.nfo').write_bytes(nfo.read_bytes())
    else:
        nfo.write_text('<movie><title>broken')
    before = repo.get_all()
    snapshots = _snapshot(source), _snapshot(output)
    result = _post(client, uri)
    assert result == {'success': False, 'error': 'no_nfo' if case == 'outside' else case}
    assert repo.get_all() == before
    assert (_snapshot(source), _snapshot(output)) == snapshots


@pytest.mark.parametrize('db_tags,nfo_tag', [(['db-only'], 'nfo-only'), ([], 'other-nfo')])
def test_readonly_refresh_tags_follow_db_not_nfo(tmp_path, monkeypatch, mocker, db_tags, nfo_tag):
    client, repo, uri, _, _, nfo, _, _ = _env(tmp_path, monkeypatch, mocker)
    repo.update_user_tags(uri, db_tags)
    tree = ET.parse(nfo)
    ET.SubElement(tree.getroot(), 'user_tag').text = nfo_tag
    tree.write(nfo, encoding='utf-8', xml_declaration=True)
    assert _post(client, uri)['success'] is True
    assert repo.get_by_path(uri).user_tags == db_tags
