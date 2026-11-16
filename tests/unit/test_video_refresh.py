import os
import sqlite3

import pytest

from core import thumbnail_cache
from core.cover_signature_pass import run_cover_signature_pass
from core.database import Video, VideoRepository, init_db
from core.gallery_scanner import VideoScanner
from core.path_utils import to_file_uri

pytestmark = pytest.mark.usefixtures('isolate_reconcile_db')


def _library(root, monkeypatch):
    root.mkdir()
    folder = root / 'library'
    folder.mkdir()
    mp4 = folder / 'ABF-348.mp4'
    mp4.write_bytes(b'video')
    cover = folder / 'ABF-348.jpg'
    cover.write_bytes(b'old cover')
    os.utime(cover, ns=(1700000000000000000, 1700000000000000000))
    mp4.with_suffix('.nfo').write_text('<movie><title>Title</title><num>ABF-348</num><user_tag>nfo</user_tag></movie>')
    db = root / 'db.sqlite'
    init_db(db)
    repo = VideoRepository(db)
    uri, cover_uri = to_file_uri(str(mp4)), to_file_uri(str(cover))
    repo.upsert(Video(path=uri, number='ABF-348', cover_path=cover_uri))
    config = {'gallery': {'directories': [{'path': str(folder), 'readonly': False, 'output_path': ''}], 'path_mappings': {}}, 'scraper': {'nfo_title_format': '[{num}]{title}'}}
    return repo, uri, cover, mp4, config


def _rows(repo):
    with sqlite3.connect(repo.db_path) as conn:
        return conn.execute('SELECT * FROM videos').fetchall()


@pytest.mark.parametrize('case', ['auto_changed', 'manual_changed', 'unchanged', 'sig_null'])
def test_cover_change_same_rule_both_exits(tmp_path, monkeypatch, mocker, case):
    from core.video_refresh import refresh_one

    mocker.patch('core.thumbnail_cache._thumb_dir', return_value=tmp_path / 'thumbs')
    spy = mocker.patch('core.focal_trigger.maybe_submit_video_focal')
    mocker.patch('core.media_probe.is_available', return_value=False)
    outcomes = []
    for index in range(2):
        repo, uri, cover, _, config = _library(tmp_path / str(index), monkeypatch)
        cover_uri = to_file_uri(str(cover))
        assert repo.update_auto_focal(uri, '0.3000', cover_uri)
        if case == 'manual_changed':
            assert repo.update_manual_focal(uri, '0.4000', expected_cover_path=cover_uri)
        with sqlite3.connect(repo.db_path) as conn:
            conn.execute("UPDATE videos SET focal_attempted_at = ? WHERE path = ?", ('2020-01-01 00:00:00', uri))
        before = repo.get_by_path(uri)
        if case != 'sig_null':
            st = cover.stat()
            assert repo.set_cover_signature(uri, st.st_mtime_ns, st.st_size)
        thumb = thumbnail_cache.thumb_file_for(uri)
        thumb.parent.mkdir(parents=True, exist_ok=True)
        thumb.write_bytes(b'old thumb')
        changed = case in ('auto_changed', 'manual_changed')
        if changed:
            st = cover.stat()
            cover.write_bytes(b'new and different cover')
            os.utime(cover, ns=(st.st_atime_ns, st.st_mtime_ns + 1000000000))
        live = cover.stat()
        spy.reset_mock()
        if index == 0:
            run_cover_signature_pass(repo, config, {})
        else:
            result = refresh_one(repo, repo.get_by_path(uri), config, {})
            assert result['cover_changed'] is changed
        row = repo.get_by_path(uri)
        focal = (row.crop_mode, row.auto_focal, row.focal_attempted_at)
        expected = ('auto', '', None) if case == 'auto_changed' else (before.crop_mode, before.auto_focal, before.focal_attempted_at)
        assert focal == expected
        assert repo.get_cover_sig(uri) == (live.st_mtime_ns, live.st_size)
        assert spy.call_count == (1 if case == 'auto_changed' else 0)
        if case == 'auto_changed':
            spy.assert_called_once_with(row.number, row.maker, uri, str(cover), cover_path_uri=cover_uri)
        assert thumb.exists() == (index == 0 and not changed)
        outcomes.append((focal, repo.get_cover_sig(uri), spy.call_count))
    assert outcomes[0] == outcomes[1]


@pytest.mark.parametrize('case', ['not_found', 'unreachable', 'nfo_unreadable'])
def test_refresh_not_found_or_unreachable_changes_nothing(tmp_path, monkeypatch, mocker, case):
    from core.video_refresh import refresh_one

    repo, uri, cover, mp4, config = _library(tmp_path / 'one', monkeypatch)
    mocker.patch('core.thumbnail_cache._thumb_dir', return_value=tmp_path / 'thumbs')
    thumb = thumbnail_cache.thumb_file_for(uri)
    thumb.parent.mkdir(parents=True, exist_ok=True)
    thumb.write_bytes(b'thumb')
    row, before = repo.get_by_path(uri), _rows(repo)
    if case == 'not_found':
        mp4.unlink()
    elif case == 'unreachable':
        monkeypatch.setattr('core.source_reachability._snapshot', {str(mp4.parent): 'unreachable'})
    else:
        mp4.with_suffix('.nfo').write_text('<movie><title>broken')
    original = os.stat
    calls = []
    def counted(path, *args, **kwargs):
        if os.fspath(path) in (str(mp4), str(cover)):
            calls.append(path)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(os, 'stat', counted)
    assert refresh_one(repo, row, config, {}) == {'success': False, 'error': case}
    if case == 'unreachable':
        assert calls == []
    assert _rows(repo) == before
    assert thumb.exists()


@pytest.mark.parametrize('case', ['extra', 'deleted', 'empty', 'concurrent'])
def test_refresh_tags_follow_db_not_nfo(tmp_path, monkeypatch, mocker, case):
    from core.video_refresh import refresh_one

    repo, uri, _, _, config = _library(tmp_path / 'one', monkeypatch)
    tags = {'extra': ['nfo', 'extra'], 'deleted': ['kept'], 'empty': [], 'concurrent': ['initial']}[case]
    assert repo.update_user_tags(uri, tags)
    before = repo.get_by_path(uri).user_tags
    if case == 'concurrent':
        original = VideoScanner.scan_file
        def scan(self, *args, **kwargs):
            info = original(self, *args, **kwargs)
            assert repo.update_user_tags(uri, ['initial', 'concurrent-added'])
            return info
        monkeypatch.setattr(VideoScanner, 'scan_file', scan)
    mocker.patch('core.media_probe.is_available', return_value=False)
    assert refresh_one(repo, repo.get_by_path(uri), config, {})['success']
    assert repo.get_by_path(uri).user_tags == (['initial', 'concurrent-added'] if case == 'concurrent' else before)
