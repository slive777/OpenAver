import hashlib
import os
import sqlite3
import threading

import pytest

from core.database import Video, VideoRepository, init_db
from core.gallery_scanner import VideoScanner
from core.nfo_field_edit import apply_edit, read_edit_view
from core.path_utils import to_file_uri
from core.user_tags_write import hold_nfo_write

pytestmark = pytest.mark.usefixtures('isolate_reconcile_db')


@pytest.fixture(autouse=True)
def _mapping(monkeypatch):
    monkeypatch.setattr('core.gallery_scanner.load_name_mapping', lambda: {'ムーディーズ': 'Moodyz'})
    monkeypatch.setattr('core.gallery_scanner.load_prefix_mapping', lambda: {'MIAA': 'Moodyz'})


def _env(tmp_path):
    folder = tmp_path / 'source'
    folder.mkdir()
    mp4 = folder / 'MIAA-456-C.mp4'
    mp4.write_bytes(b'video')
    nfo = mp4.with_suffix('.nfo')
    nfo.write_text('<movie><title>Old</title><num>MIAA-456</num><studio>Old</studio><plot>Old plot</plot><tag>4K</tag></movie>')
    os.chmod(nfo, 0o644)
    os.utime(nfo, ns=(1700000000000000000, 1700000000000000000))
    db = tmp_path / 'db.sqlite'
    init_db(db)
    repo = VideoRepository(db)
    video = Video.from_video_info(VideoScanner().scan_file(str(mp4)))
    video.nfo_mtime = nfo.stat().st_mtime
    repo.upsert(video)
    config = {'gallery': {'directories': [{'path': str(folder), 'readonly': False, 'output_path': ''}], 'path_mappings': {}}, 'scraper': {'nfo_title_format': '[{num}]{title}'}}
    return repo, to_file_uri(str(mp4)), mp4, nfo, config


def _snapshot(path):
    return {str(p.relative_to(path)): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns) for p in path.rglob('*') if p.is_file()}


def _edit(repo, uri, config, field, payload):
    return apply_edit(repo, repo.get_by_path(uri), field, payload, config, {})


@pytest.mark.parametrize(('field', 'payload'), [
    ('title', {'value': 'New title'}), ('original_title', {'value': 'Original'}),
    ('actresses', {'value': ['A', 'B']}), ('maker', {'value': 'Custom maker'}),
    ('series', {'value': 'Series'}), ('release_date', {'value': '2023-01-02'}),
    ('plot', {'value': 'New plot'}), ('plot_translation', {'value': 'Translation'}),
    ('tags', {'add': ['New tag'], 'remove': []}),
])
def test_edit_reads_back_as_scanned(tmp_path, field, payload):
    repo, uri, mp4, nfo, config = _env(tmp_path)
    result = _edit(repo, uri, config, field, payload)
    assert result['success'] and result['nfo_updated']
    row = repo.get_by_path(uri)
    scanned = Video.from_video_info(VideoScanner().scan_file(str(mp4)))
    for key in ('title', 'original_title', 'actresses', 'maker', 'release_date', 'series', 'tags', 'has_plot'):
        assert getattr(row, key) == getattr(scanned, key), key
    if field not in ('tags', 'plot', 'plot_translation'):
        assert result['values'][field] == (getattr(scanned, field) or ('' if field == 'series' else getattr(scanned, field)))
    if field == 'tags':
        assert 'New tag' in [t['text'] for t in result['tags']]
    if field in ('plot', 'plot_translation'):
        assert result['values'][field] == payload['value']
    if os.name == 'posix':
        assert nfo.stat().st_mode & 0o777 == 0o644
    os.utime(nfo, ns=(1700000000000000000, 1700000000000000000))
    before = (nfo.read_bytes(), nfo.stat().st_mtime_ns)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(repo, 'update_nfo_fields', lambda *a: pytest.fail('unexpected DB update'))
        assert _edit(repo, uri, config, field, payload)['unchanged']
    assert (nfo.read_bytes(), nfo.stat().st_mtime_ns) == before
    dbfield = {'plot': 'has_plot', 'plot_translation': 'has_plot'}.get(field, field)
    wrong = {'actresses': ['wrong'], 'tags': ['wrong'], 'has_plot': False}.get(dbfield, 'wrong')
    assert repo.update_nfo_fields(uri, {dbfield: wrong}, row.nfo_mtime)
    assert _edit(repo, uri, config, field, payload)['unchanged']
    assert (nfo.read_bytes(), nfo.stat().st_mtime_ns) == before
    assert getattr(repo.get_by_path(uri), dbfield) == getattr(scanned, dbfield)


def test_nfo_write_failure_leaves_everything_untouched(tmp_path, monkeypatch):
    repo, uri, mp4, nfo, config = _env(tmp_path)
    before, row = _snapshot(mp4.parent), repo.get_by_path(uri)
    with monkeypatch.context() as patch:
        patch.setattr('core.atomic_write.os.replace', lambda *a: (_ for _ in ()).throw(PermissionError()))
        assert _edit(repo, uri, config, 'series', {'value': 'New'}) == {'success': False, 'error': 'nfo_write_failed'}
    assert _snapshot(mp4.parent) == before
    assert repo.get_by_path(uri) == row


@pytest.mark.parametrize('error', [sqlite3.OperationalError, RuntimeError])
def test_db_failure_rolls_nfo_back(tmp_path, monkeypatch, error):
    repo, uri, _, nfo, config = _env(tmp_path)
    before, row = nfo.read_bytes(), repo.get_by_path(uri)
    monkeypatch.setattr(repo, 'update_nfo_fields', lambda *a: (_ for _ in ()).throw(error()))
    assert _edit(repo, uri, config, 'series', {'value': 'New'}) == {'success': False, 'error': 'db_write_failed'}
    assert nfo.read_bytes() == before
    assert repo.get_by_path(uri) == row


def test_readonly_source_zero_write(tmp_path):
    repo, uri, mp4, source_nfo, config = _env(tmp_path)
    output = tmp_path / 'output'
    movie = output / 'movie'
    movie.mkdir(parents=True)
    nfo = movie / 'X.nfo'
    nfo.write_bytes(source_nfo.read_bytes())
    config['gallery']['directories'][0].update(readonly=True, output_path=str(output))
    config['scraper']['external_manager'] = 'jellyfin'
    row = repo.get_by_path(uri)
    row.output_dir = to_file_uri(str(movie))
    repo.upsert(row)
    before = _snapshot(mp4.parent)
    assert _edit(repo, uri, config, 'maker', {'value': 'Custom'})['success']
    assert _snapshot(mp4.parent) == before
    assert b'Custom' in nfo.read_bytes()
    nfo.unlink()
    assert _edit(repo, uri, config, 'maker', {'value': 'Custom'})['error'] == 'readonly_no_nfo'
    nfo.write_bytes(source_nfo.read_bytes())
    other = movie / 'Y.nfo'
    other.write_bytes(nfo.read_bytes())
    assert _edit(repo, uri, config, 'maker', {'value': 'Custom'})['error'] == 'nfo_ambiguous'
    other.unlink()
    if os.name != 'nt':
        nfo.unlink()
        nfo.symlink_to(source_nfo)
        before = _snapshot(mp4.parent)
        assert _edit(repo, uri, config, 'maker', {'value': 'Custom'})['error'] == 'nfo_link_outside'
        assert nfo.is_symlink() and _snapshot(mp4.parent) == before



def test_concurrent_edits_do_not_lose_updates(tmp_path):
    repo, uri, _, nfo, config = _env(tmp_path)
    barrier = threading.Barrier(2)
    results = []
    def worker(field, value):
        barrier.wait(timeout=10)
        with hold_nfo_write():
            results.append(_edit(repo, uri, config, field, {'value': value}))
    threads = [threading.Thread(target=worker, args=('maker', 'Custom')), threading.Thread(target=worker, args=('series', 'Series'))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
        assert not thread.is_alive()
    assert len(results) == 2 and all(r['success'] for r in results)
    assert b'Custom' in nfo.read_bytes() and b'Series' in nfo.read_bytes()


def test_blocked_cases_write_nothing(tmp_path, monkeypatch):
    repo, uri, mp4, nfo, config = _env(tmp_path)
    view = read_edit_view(repo, repo.get_by_path(uri), config, {})
    assert view['state'] == 'ok' and view['values']['title'] == repo.get_by_path(uri).title
    assert view['values']['plot'] == 'Old plot'
    assert {'text': '中文字幕', 'from_filename': True} in view['tags']
    assert all(t['text'] != '4K' for t in view['tags'])
    if os.name != 'nt':
        target = mp4.parent / 'target.xml'
        nfo.rename(target)
        nfo.symlink_to(target)
        assert _edit(repo, uri, config, 'series', {'value': 'Linked'})['success']
        assert nfo.is_symlink() and b'Linked' in target.read_bytes()
    nfo.unlink()
    row = repo.get_by_path(uri)
    row.nfo_mtime = 0
    repo.upsert(row)
    for reason in ('no_nfo', 'borrowed', 'unreachable'):
        if reason == 'borrowed':
            other = mp4.with_name('MIAA-456.mp4')
            other.write_bytes(b'video')
            other.with_suffix('.nfo').write_text('<movie><title>Other</title><num>MIAA-456</num></movie>')
            sibling = Video.from_video_info(VideoScanner().scan_file(str(other)))
            sibling.nfo_mtime = other.with_suffix('.nfo').stat().st_mtime
            repo.upsert(sibling)

        if reason == 'unreachable':
            monkeypatch.setattr('core.nfo_field_edit.is_path_on_unreachable_source', lambda *a: True)
        before, row = _snapshot(mp4.parent), repo.get_by_path(uri)
        assert read_edit_view(repo, row, config, {})['reason'] == reason
        assert _edit(repo, uri, config, 'series', {'value': 'New'})['error'] == reason
        assert _snapshot(mp4.parent) == before and repo.get_by_path(uri) == row
