import hashlib
import os
import threading

import pytest

from core.database import Video, VideoRepository, init_db
from core.gallery_scanner import VideoScanner
from core.nfo_field_edit import ERROR_CODES
from core.path_utils import to_file_uri
from core.user_tags_write import hold_nfo_write
from core.version_group import resolve_work

pytestmark = pytest.mark.usefixtures('isolate_reconcile_db')
GET = '/api/showcase/video/edit-data'
POST = '/api/showcase/video/edit-field'


@pytest.fixture(autouse=True)
def _mapping(monkeypatch):
    monkeypatch.setattr('core.gallery_scanner.load_name_mapping', lambda: {'ムーディーズ': 'Moodyz'})
    monkeypatch.setattr('core.gallery_scanner.load_prefix_mapping', lambda: {'MIAA': 'Moodyz'})


def _add_video(repo, folder, name, title='Old', studio='Old', tags=('4K', 'Mine')):
    mp4 = folder / name
    mp4.write_bytes(b'video')
    nfo = mp4.with_suffix('.nfo')
    tag_xml = ''.join(f'<tag>{tag}</tag>' for tag in tags)
    nfo.write_text(f'<movie><title>{title}</title><num>MIAA-456</num><studio>{studio}</studio><plot>Old plot</plot>{tag_xml}</movie>')
    os.utime(nfo, ns=(1700000000000000000, 1700000000000000000))
    video = Video.from_video_info(VideoScanner().scan_file(str(mp4)))
    video.nfo_mtime = nfo.stat().st_mtime
    repo.upsert(video)
    return to_file_uri(str(mp4)), mp4, nfo


@pytest.fixture
def env(tmp_path, monkeypatch):
    folder = tmp_path / 'source'
    folder.mkdir()
    db = tmp_path / 'db.sqlite'
    init_db(db)
    repo = VideoRepository(db)
    uri, mp4, nfo = _add_video(repo, folder, 'MIAA-456-C.mp4')
    config = {'gallery': {'directories': [{'path': str(folder), 'readonly': False, 'output_path': ''}], 'path_mappings': {}}, 'scraper': {'nfo_title_format': '[{num}]{title}'}}
    monkeypatch.setattr('web.routers.showcase_files.get_db_path', lambda: db)
    monkeypatch.setattr('web.routers.showcase_files.load_config', lambda: config)
    monkeypatch.setattr('core.readonly_paths.get_db_path', lambda: db)
    monkeypatch.setattr('core.database.connection.get_db_path', lambda: db)
    return repo, uri, mp4, nfo, config


def _snapshot(path):
    return {str(p.relative_to(path)): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns) for p in path.rglob('*') if p.is_file()}


def _file_state(path):
    return hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns


def test_get_edit_data_ok_shape(client, env):
    repo, uri, _, nfo, _ = env
    row, before = repo.get_by_path(uri), _file_state(nfo)
    assert 'Mine' in row.tags and '中文字幕' in row.tags
    assert row.maker == 'Moodyz'
    response = client.get(GET, params={'path': uri})
    body = response.json()
    assert response.status_code == 200 and body['success']
    assert (body['state'], body['reason'], body['readonly']) == ('ok', None, False)
    for key in ('title', 'original_title', 'actresses', 'maker', 'series', 'release_date'):
        assert body['values'][key] == (getattr(row, key) or ('' if key == 'series' else getattr(row, key)))
    assert body['values']['maker'] == 'Moodyz' and body['values']['plot'] == 'Old plot'
    assert {'text': '中文字幕', 'from_filename': True} in body['tags']
    assert {'text': 'Mine', 'from_filename': False} in body['tags']
    assert all(tag['text'] != '4K' for tag in body['tags'])
    assert _file_state(nfo) == before and repo.get_by_path(uri) == row


@pytest.mark.parametrize('reason', ['borrowed', 'no_nfo', 'unreachable', 'readonly_no_nfo', 'nfo_ambiguous'])
def test_blocked_cases_http(client, env, tmp_path, monkeypatch, reason):
    repo, uri, mp4, nfo, config = env
    if reason in ('borrowed', 'no_nfo', 'unreachable'):
        nfo.unlink()
        row = repo.get_by_path(uri)
        row.nfo_mtime = 0
        repo.upsert(row)
    if reason == 'borrowed':
        _add_video(repo, mp4.parent, 'MIAA-456.mp4')
    if reason == 'unreachable':
        monkeypatch.setattr('core.nfo_field_edit.is_path_on_unreachable_source', lambda *a, **k: True)
    if reason.startswith('readonly') or reason == 'nfo_ambiguous':
        output = tmp_path / 'output'
        movie = output / 'movie'
        movie.mkdir(parents=True)
        config['gallery']['directories'][0].update(readonly=True, output_path=str(output))
        config['scraper']['external_manager'] = 'jellyfin'
        row = repo.get_by_path(uri)
        row.output_dir = to_file_uri(str(movie))
        repo.upsert(row)
        if reason == 'nfo_ambiguous':
            (movie / 'X.nfo').write_bytes(nfo.read_bytes())
            (movie / 'Y.nfo').write_bytes(nfo.read_bytes())
    before, row = _snapshot(mp4.parent), repo.get_by_path(uri)
    output_before = _snapshot(movie) if reason in ('readonly_no_nfo', 'nfo_ambiguous') else None
    response = client.get(GET, params={'path': uri})
    view = response.json()
    assert response.status_code == 200 and view['state'] == 'blocked' and view['reason'] == reason
    assert 'values' not in view and 'tags' not in view
    response = client.post(POST, json={'path': uri, 'field': 'series', 'value': 'New'})
    assert response.status_code == 200 and response.json() == {'success': False, 'error': reason}
    assert _snapshot(mp4.parent) == before and repo.get_by_path(uri) == row
    if output_before is not None:
        assert _snapshot(movie) == output_before


@pytest.mark.parametrize('case', ['number', 'unknown', 'missing_row', 'out_of_scope', 'no_db', 'bad_uri', 'invalid_value'])
def test_edit_field_errors_are_http_200_and_write_nothing(client, env, tmp_path, monkeypatch, case):
    repo, uri, _, nfo, config = env
    before, row = _file_state(nfo), repo.get_by_path(uri)
    request = {'path': uri, 'field': 'series', 'value': 'New'}
    expected = 'not_found'
    if case in ('number', 'unknown'):
        request['field'] = 'number' if case == 'number' else 'unknown'
        expected = 'invalid_field'
    elif case == 'missing_row':
        request['path'] = to_file_uri(str(tmp_path / 'missing.mp4'))
    elif case == 'out_of_scope':
        config['gallery']['directories'][0]['path'] = str(tmp_path / 'elsewhere')
    elif case == 'no_db':
        monkeypatch.setattr('web.routers.showcase_files.get_db_path', lambda: tmp_path / 'missing.db')
    elif case == 'bad_uri':
        def raiser(*args, **kwargs):
            raise ValueError('bad URI')
        monkeypatch.setattr('core.nfo_field_edit.uri_to_local_fs_path', raiser)
        response = client.get(GET, params={'path': uri})
        assert response.status_code == 200 and response.json() == {'success': False, 'error': 'invalid_path'}
        expected = 'invalid_path'
    elif case == 'invalid_value':
        request.update(field='maker', value=123)
        expected = 'invalid_value'
    response = client.post(POST, json=request)
    body = response.json()
    assert response.status_code == 200 and body['success'] is False
    assert body['error'] == expected and body['error'] in ERROR_CODES
    assert _file_state(nfo) == before and repo.get_by_path(uri) == row


def test_multi_version_edit_touches_only_requested_version(client, env):
    repo, uri, mp4, nfo, _ = env
    other, other_mp4, other_nfo = _add_video(repo, mp4.parent, 'MIAA-456.mp4', title='Other', studio='Other')
    assert len(resolve_work(repo, uri, {}).versions) == 2
    row_a, row_b = repo.get_by_path(uri), repo.get_by_path(other)
    assert row_a.title != row_b.title
    # Preserve distinct maker values despite the prefix mapping.
    assert repo.update_nfo_fields(other, {'maker': 'Other maker'}, row_b.nfo_mtime)
    row_b = repo.get_by_path(other)
    assert row_a.maker != row_b.maker
    before_a, before_b = _file_state(nfo), _file_state(other_nfo)
    bytes_b = other_nfo.read_bytes()
    response = client.post(POST, json={'path': uri, 'field': 'maker', 'value': 'Custom'})
    assert response.status_code == 200 and response.json()['success']
    assert repo.get_by_path(uri).maker == 'Custom' and _file_state(nfo) != before_a
    assert b'Custom' in nfo.read_bytes()
    assert other_nfo.read_bytes() == bytes_b and _file_state(other_nfo) == before_b
    assert repo.get_by_path(other) == row_b
    # GET reads the NFO itself: the other version's NFO maker, not its (DB-only) 'Other maker'.
    nfo_maker = VideoScanner().scan_file(str(other_mp4)).maker
    assert nfo_maker != row_b.maker
    assert client.get(GET, params={'path': other}).json()['values']['maker'] == nfo_maker


def test_tags_net_effect_and_batch_atomic(client, env):
    repo, uri, mp4, nfo, _ = env
    nfo.write_text('<movie><title>Old</title><num>MIAA-456</num><tag>4K</tag><tag>Keep</tag><tag>Drop</tag></movie>')
    os.utime(nfo, ns=(1700000000000000000, 1700000000000000000))
    video = Video.from_video_info(VideoScanner().scan_file(str(mp4)))
    video.nfo_mtime = nfo.stat().st_mtime
    repo.upsert(video)
    assert {'4K', 'Keep', 'Drop'} <= set(repo.get_by_path(uri).tags)
    req = {'path': uri, 'field': 'tags', 'add': ['Both', 'New'], 'remove': ['Both', 'Drop']}
    assert client.post(POST, json=req).json()['success']
    tags = set(VideoScanner().scan_file(str(mp4)).genre.split(','))
    assert 'Both' not in tags and 'New' in tags and 'Drop' not in tags and 'Keep' in tags and '4K' in tags
    before = _file_state(nfo)
    assert client.post(POST, json=req).json()['unchanged'] is True
    assert _file_state(nfo) == before
    for add, error in [(['a,b'], 'tag_invalid'), (['4K'], 'tag_hidden')]:
        row = repo.get_by_path(uri)
        response = client.post(POST, json={'path': uri, 'field': 'tags', 'add': add, 'remove': ['Keep']})
        assert response.status_code == 200 and response.json() == {'success': False, 'error': error}
        assert _file_state(nfo) == before and repo.get_by_path(uri) == row
        assert 'Keep' in VideoScanner().scan_file(str(mp4)).genre.split(',')


def test_endpoint_holds_lock_and_rereads_row(client, env, monkeypatch):
    repo, uri, _, nfo, _ = env
    before, before_bytes = _file_state(nfo), nfo.read_bytes()
    event, results = threading.Event(), []
    original = VideoRepository.get_by_path
    def wrapped(self, path):
        result = original(self, path)
        if threading.current_thread() is not threading.main_thread() and path == uri:
            event.set()
        return result
    monkeypatch.setattr(VideoRepository, 'get_by_path', wrapped)
    req_thread = threading.Thread(target=lambda: results.append(client.post(POST, json={'path': uri, 'field': 'series', 'value': 'Locked'})))
    try:
        with hold_nfo_write():
            req_thread.start()
            assert event.wait(timeout=10)
            req_thread.join(timeout=0.5)
            assert req_thread.is_alive() and nfo.read_bytes() == before_bytes
            repo.delete_by_paths([uri])
    finally:
        if req_thread.ident is not None:
            req_thread.join(timeout=10)
    assert not req_thread.is_alive()
    assert len(results) == 1 and results[0].status_code == 200
    assert results[0].json() == {'success': False, 'error': 'not_found'}
    assert _file_state(nfo) == before


@pytest.fixture
def capabilities_auth_db(tmp_path, monkeypatch):
    import core.access_auth as access_auth

    db_path = tmp_path / 'access.db'
    monkeypatch.setattr('core.access_auth.get_db_path', lambda: db_path)
    access_auth.ensure_schema()
    access_auth.reset_state_for_tests()
    yield db_path
    access_auth.reset_state_for_tests()


def test_video_edit_field_example_drives_endpoint(client, env, capabilities_auth_db):
    import json
    import shlex
    import xml.etree.ElementTree as ET

    from core.gallery_scanner import MANUAL_MAKER_TAG

    repo, uri, _, nfo, _ = env
    tools = {t['name']: t for t in client.get('/api/capabilities').json()['tools']}
    tool = tools['video_edit_field']
    example = shlex.split(tool['example'])
    assert tool['method'] == 'POST' and example[-1].endswith(tool['path'])
    body = json.loads(example[example.index('-d') + 1])
    before = repo.get_by_path(uri)
    assert body['value'] == 'S1' and body['value'] != before.maker
    before_xml = ET.parse(nfo).getroot()
    body['path'] = uri
    response = client.post(tool['path'], json=body)
    result = response.json()
    assert response.status_code == 200 and result['success'] is True
    assert result['unchanged'] is False and result['values'] == {'maker': 'S1'}
    after_xml = ET.parse(nfo).getroot()
    ignored = {'studio', MANUAL_MAKER_TAG}
    assert [(e.tag, e.text) for e in before_xml.iter() if e.tag not in ignored] == [
        (e.tag, e.text) for e in after_xml.iter() if e.tag not in ignored
    ]
    after = repo.get_by_path(uri)
    assert after.maker == 'S1'
    for field in ('title', 'actresses', 'series', 'release_date', 'tags'):
        assert getattr(after, field) == getattr(before, field)


def test_get_edit_data_reads_externally_edited_nfo_and_noop_save_keeps_it(client, env):
    repo, uri, _, nfo, _ = env
    db_row = repo.get_by_path(uri)
    nfo.write_text('<movie><title>Ext title</title><num>MIAA-456</num><studio>ExtMaker</studio><openaver_manual_maker>1</openaver_manual_maker>'
                   '<set><name>Ext series</name></set><plot>Old plot</plot><tag>Mine</tag><tag>ExtTag</tag></movie>')
    assert repo.get_by_path(uri) == db_row and db_row.maker != 'ExtMaker'
    body = client.get(GET, params={'path': uri}).json()
    assert body['state'] == 'ok'
    assert body['values']['maker'] == 'ExtMaker'
    assert body['values']['title'] == 'Ext title'
    assert body['values']['series'] == 'Ext series'
    assert isinstance(body['values']['actresses'], list)
    assert 'ExtTag' in [tag['text'] for tag in body['tags']]
    # Press the check mark without changing anything: the externally edited value must survive.
    post = client.post(POST, json={'path': uri, 'field': 'maker', 'value': body['values']['maker']}).json()
    assert post['success'] is True
    assert '<studio>ExtMaker</studio>' in nfo.read_text()
    assert repo.get_by_path(uri).maker == 'ExtMaker'
