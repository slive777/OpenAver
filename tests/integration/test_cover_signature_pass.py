import os

import pytest

from core import thumbnail_cache
from core.cover_signature_pass import run_cover_signature_pass
from core.database import VideoRepository, init_db
from core.database.video import Video
from core.path_utils import to_file_uri

pytestmark = pytest.mark.usefixtures('isolate_reconcile_db')


@pytest.fixture
def library(tmp_path, monkeypatch, mocker):
    db = tmp_path / 'test.db'
    init_db(db)
    monkeypatch.setattr('core.database.connection.get_db_path', lambda: db)
    mocker.patch('core.thumbnail_cache._thumb_dir', return_value=tmp_path / 'thumbs')
    mocker.patch('core.focal_trigger.maybe_submit_video_focal')
    repo = VideoRepository(db)
    directory = tmp_path / 'library'
    directory.mkdir()
    config = {'gallery': {'directories': [{'path': str(directory), 'readonly': False, 'output_path': ''}], 'path_mappings': {}}}

    def add(name, mode='auto', signature='different', folder=directory):
        cover = folder / f'{name}.jpg'
        cover.write_bytes(b'cover')
        uri = to_file_uri(str(folder / f'{name}.mp4'))
        cover_uri = to_file_uri(str(cover))
        repo.upsert(Video(path=uri, cover_path=cover_uri, number=name))
        repo.update_auto_focal(uri, '0.3000', cover_uri)
        if mode == 'manual':
            repo.update_manual_focal(uri, '0.4000', expected_cover_path=cover_uri)
        st = cover.stat()
        live = (st.st_mtime_ns, st.st_size)
        if signature != 'null':
            repo.set_cover_signature(uri, *(live if signature == 'same' else (live[0] - 1, live[1])))
        thumb = thumbnail_cache.thumb_file_for(uri)
        thumb.parent.mkdir(parents=True, exist_ok=True)
        thumb.write_bytes(b'x')
        return uri, cover, thumb, live

    return repo, config, add


def focal(repo, uri):
    video = repo.get_by_path(uri)
    return video.crop_mode, video.auto_focal, video.focal_attempted_at


@pytest.mark.parametrize('case', ['null', 'same', 'auto', 'manual', 'permission'])
def test_signature_pass_decision_table(library, monkeypatch, case):
    repo, config, add = library
    uri, cover, thumb, live = add('ABF-348', mode='manual' if case == 'manual' else 'auto', signature=case if case in ('null', 'same') else 'different')
    before, old_sig = focal(repo, uri), repo.get_cover_sig(uri)
    if case == 'permission':
        original = os.stat
        def stat(path, *args, **kwargs):
            if os.fspath(path) == str(cover):
                raise PermissionError('denied')
            return original(path, *args, **kwargs)
        monkeypatch.setattr(os, 'stat', stat)
        other, _, _, other_live = add('ABF-349', signature='null')
    stats = run_cover_signature_pass(repo, config, {})
    if case == 'permission':
        assert repo.get_cover_sig(other) == other_live
    assert repo.get_cover_sig(uri) == (old_sig if case == 'permission' else live)
    assert thumb.exists() == (case in ('null', 'same', 'permission'))
    assert focal(repo, uri) == (('auto', '', None) if case == 'auto' else before)
    assert stats.changed == (1 if case in ('auto', 'manual') else 0)


def test_unreachable_source_not_stat(library, tmp_path, monkeypatch):
    repo, config, add = library
    offline = tmp_path / 'offline'
    offline.mkdir()
    config['gallery']['directories'].append({'path': str(offline), 'readonly': False, 'output_path': ''})
    uri, cover, thumb, _ = add('ABF-348', folder=offline)
    other, _, other_thumb, live = add('ABF-349')
    old = repo.get_cover_sig(uri)
    monkeypatch.setattr('core.source_reachability._snapshot', {str(offline): 'unreachable'})
    original = os.stat
    calls = []
    def stat(path, *args, **kwargs):
        if os.fspath(path) == str(cover):
            calls.append(path)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(os, 'stat', stat)
    run_cover_signature_pass(repo, config, {})
    assert calls == []
    assert repo.get_cover_sig(uri) == old and thumb.exists()
    assert repo.get_cover_sig(other) == live and not other_thumb.exists()


def test_abort_stops_pass(library):
    repo, config, add = library
    first, _, first_thumb, live = add('ABF-348', signature='null')
    second, _, second_thumb, _ = add('ABF-349')
    old = repo.get_cover_sig(second)
    calls = iter([False, True])
    run_cover_signature_pass(repo, config, {}, should_abort=lambda: next(calls))
    assert repo.get_cover_sig(first) == live and first_thumb.exists()
    assert repo.get_cover_sig(second) == old and second_thumb.exists()


def test_scan_tail_runs_cover_pass_and_logs(library, mocker):
    from web.routers import scanner
    repo, config, add = library
    uri, _, thumb, live = add('ABF-348')
    mocker.patch('web.routers.scanner._run_sample_images_cleanup_pass', return_value=0)
    events = list(scanner._post_scan_cleanup_and_plot_backfill(repo, config, {}, lambda: False))
    assert any('封面檢查：' in event for event in events)
    assert repo.get_cover_sig(uri) == live and not thumb.exists()
