import threading
from unittest.mock import Mock

import pytest
from PIL import Image

from core.ai_services import actress_faces
from core.ai_services.faces_detect import ExternalResult
from core.database import Actress, ActressRepository, init_db
from core.focal.face_judge import judge_endpoint

_REAL_KICK = actress_faces.kick
BOXES = ((0.2, 0.2, 0.5, 0.25),)


@pytest.fixture(autouse=True)
def setup_faces(tmp_path, monkeypatch):
    db = tmp_path / 'test.db'
    init_db(db)
    repo = ActressRepository(db)
    cfg = {'ai_services': {'faces': {'enabled': True, 'url': 'http://x'}},
           'focal_device': {'disabled': False, 'set_by_user': True}}
    fps, avatars, target = {}, [], ['m1']
    monkeypatch.setattr(actress_faces, '_repo', lambda: repo)
    monkeypatch.setattr(actress_faces, 'load_config', lambda: cfg)
    monkeypatch.setattr(actress_faces, '_target_model', lambda: target[0])
    monkeypatch.setattr(actress_faces, 'current_photo_fp', lambda name: fps.get(name))
    monkeypatch.setattr(actress_faces.actress_avatar, 'get_or_create', lambda row, path: avatars.append((row, path)))
    monkeypatch.setattr(actress_faces, 'kick', _REAL_KICK)
    monkeypatch.setattr(actress_faces, '_dirty', False)
    monkeypatch.setattr(actress_faces, '_running', False)
    monkeypatch.setattr(actress_faces, '_thread', None)
    def add(name, source='', orientation=1):
        path = tmp_path / (name + '.jpg')
        exif = Image.Exif()
        exif[274] = orientation
        Image.new('RGB', (300, 200)).save(path, exif=exif)
        stat = path.stat()
        fps[name] = (str(path), stat.st_mtime_ns, stat.st_size)
        repo.save(Actress(name=name, photo_source=source))
    return repo, cfg, fps, avatars, target, add


@pytest.mark.parametrize('case', ['endpoint_down_stops_round', 'switch_off_no_detection',
    'endpoint_ignores_local_switch', 'endpoint_without_model_string', 'endpoint_uses_upright_size',
    'pigo_when_endpoint_off_switch_open', 'pigo_skips_local_crop', 'same_result_not_redetected',
    'pigo_result_upgraded_by_endpoint', 'target_model_changed_recomputes',
    'fingerprint_changed_recomputes', 'pigo_abandoned_then_endpoint_next'])
def test_source_decision_table(case, setup_faces, monkeypatch):
    repo, cfg, fps, avatars, target, add = setup_faces
    add('A', 'local_crop' if case == 'pigo_skips_local_crop' else '', 6 if case == 'endpoint_uses_upright_size' else 1)
    if case in ('endpoint_down_stops_round', 'switch_off_no_detection', 'pigo_abandoned_then_endpoint_next'):
        add('B')
    endpoint = cfg['ai_services']['faces']
    if case in ('switch_off_no_detection', 'pigo_when_endpoint_off_switch_open', 'pigo_skips_local_crop', 'pigo_abandoned_then_endpoint_next'):
        endpoint['enabled'] = False
    if case in ('switch_off_no_detection', 'endpoint_ignores_local_switch'):
        cfg['focal_device']['disabled'] = True
    result = ExternalResult('FOUND', model=None if case == 'endpoint_without_model_string' else 'm1', boxes=BOXES)
    if case == 'endpoint_down_stops_round':
        result = ExternalResult('FAILED', failure='external_unreachable')
    detect = Mock(return_value=result)
    runner = Mock(return_value=('FOUND', [], (400, 400)))
    if case == 'pigo_abandoned_then_endpoint_next':
        def switch(*args, **kwargs):
            endpoint['enabled'] = True
            return ('ABANDONED', 'skipped_disabled')
        runner.side_effect = switch
    monkeypatch.setattr(actress_faces.faces_detect, 'detect', detect)
    monkeypatch.setattr(actress_faces.face_runner, 'run_face_boxes', runner)
    if case in ('pigo_result_upgraded_by_endpoint', 'target_model_changed_recomputes', 'fingerprint_changed_recomputes'):
        model = 'local-pigo' if case == 'pigo_result_upgraded_by_endpoint' else 'm0' if case == 'target_model_changed_recomputes' else 'm1'
        fp = fps['A'] if case != 'fingerprint_changed_recomputes' else (fps['A'][0], 0, 0)
        repo.update_face_result('A', 'found', 'old', model, *fp)
    if case == 'same_result_not_redetected':
        for name, status in zip(('A', 'B', 'C', 'D'), ('found', 'none', 'unsure', 'multi'), strict=True):
            if name != 'A':
                add(name)
            repo.update_face_result(name, status, 'box', 'm1', *fps[name])
        before = [repo.get_by_name(n) for n in 'ABCD']
        actress_faces.sweep()
        assert detect.call_count == 0 and runner.call_count == 0
        assert [repo.get_by_name(n) for n in 'ABCD'] == before
        endpoint['enabled'] = False
        for name in 'ABCD':
            repo.update_face_result(name, repo.get_by_name(name).face_status, 'box', 'local-pigo', *fps[name])
        before = [repo.get_by_name(n) for n in 'ABCD']
        actress_faces.sweep()
        assert detect.call_count == 0 and runner.call_count == 0
        assert [repo.get_by_name(n) for n in 'ABCD'] == before
        return
    actress_faces.sweep()
    row = repo.get_by_name('A')
    if case == 'endpoint_down_stops_round':
        assert detect.call_count == 1 and runner.call_count == 0
        assert row.face_status == repo.get_by_name('B').face_status == ''
    elif case == 'switch_off_no_detection':
        assert detect.call_count == runner.call_count == 0
        assert row.face_status == repo.get_by_name('B').face_status == ''
    elif case == 'pigo_abandoned_then_endpoint_next':
        assert runner.call_count == detect.call_count == 1
        assert row.face_status == '' and repo.get_by_name('B').face_status == 'found'
    elif case in ('pigo_when_endpoint_off_switch_open', 'pigo_skips_local_crop'):
        assert detect.call_count == 0 and runner.call_count == (0 if case == 'pigo_skips_local_crop' else 1)
        assert (row.face_status, row.face_model) == ('unsure' if case == 'pigo_skips_local_crop' else 'none', 'local-pigo')
        assert (row.photo_fp_path, row.photo_fp_mtime_ns, row.photo_fp_size) == fps['A']
    else:
        assert detect.call_count == 1 and runner.call_count == 0
        assert row.face_status == 'found' and row.face_model == ('external' if case == 'endpoint_without_model_string' else 'm1')
        if case == 'endpoint_ignores_local_switch':
            assert detect.call_args.kwargs == {'profile': 'background', 'notify': False}
            assert len(avatars) == 1 and avatars[0][0].face_status == 'found' and avatars[0][0].face_box == row.face_box
        if case == 'endpoint_uses_upright_size':
            assert row.face_box == judge_endpoint(BOXES, 200, 300).box
            assert row.face_box != judge_endpoint(BOXES, 300, 200).box
        if case == 'endpoint_without_model_string':
            target[0] = None
            actress_faces.sweep()
            assert detect.call_count == 1


def test_result_dropped_when_photo_changes_mid_detect(setup_faces, monkeypatch):
    repo, cfg, fps, avatars, target, add = setup_faces
    add('A')
    old = fps['A']
    new = (old[0], old[1] + 1, old[2])
    def detect_once(*args, **kwargs):
        fps['A'] = new
        return ExternalResult('FOUND', model='m1', boxes=BOXES)
    detect = Mock(side_effect=detect_once)
    monkeypatch.setattr(actress_faces.faces_detect, 'detect', detect)
    actress_faces.sweep()
    assert repo.get_by_name('A').face_status == '' and avatars == [] and detect.call_count == 1
    actress_faces.sweep()
    row = repo.get_by_name('A')
    assert detect.call_count == 2 and len(avatars) == 1
    assert (row.photo_fp_path, row.photo_fp_mtime_ns, row.photo_fp_size) == new


@pytest.mark.parametrize('reason', [pytest.param('detect_timeout', id='detect_timeout'),
    pytest.param('crashed', id='crash_stops_round'), pytest.param('startup_timeout', id='crash_stops_round')])
def test_pigo_timeout_is_remembered_but_crash_is_not(reason, setup_faces, monkeypatch):
    repo, cfg, fps, avatars, target, add = setup_faces
    add('A'); add('B')
    cfg['ai_services']['faces']['enabled'] = False
    runner = Mock(side_effect=[('ABANDONED', reason), ('FOUND', [], (400, 400))])
    monkeypatch.setattr(actress_faces.face_runner, 'run_face_boxes', runner)
    actress_faces.sweep()
    if reason == 'detect_timeout':
        assert runner.call_count == 2
        assert (repo.get_by_name('A').face_status, repo.get_by_name('A').face_model) == ('unsure', 'local-pigo')
        assert repo.get_by_name('B').face_status == 'none'
        actress_faces.sweep()
        assert runner.call_count == 2
    else:
        assert runner.call_count == 1 and repo.get_by_name('A').face_status == repo.get_by_name('B').face_status == ''


@pytest.mark.parametrize('case', ['kick_during_sweep', 'kick_then_raise', 'raise_then_later_kick', 'kick_does_no_io'])
def test_kick_never_loses_a_wakeup(case, setup_faces, monkeypatch):
    started, release = threading.Event(), threading.Event()
    calls = []
    def fake_sweep():
        calls.append(1)
        if len(calls) == 1:
            started.set()
            assert release.wait(5)
            if case in ('kick_then_raise', 'raise_then_later_kick'):
                raise RuntimeError('test')
    fake = Mock(side_effect=fake_sweep)
    monkeypatch.setattr(actress_faces, 'sweep', fake)
    config = Mock(side_effect=RuntimeError('unexpected'))
    if case == 'kick_does_no_io':
        monkeypatch.setattr(actress_faces, 'load_config', config)
    try:
        actress_faces.kick()
        assert started.wait(5)
        first = actress_faces._thread
        if case in ('kick_during_sweep', 'kick_then_raise'):
            actress_faces.kick()
        release.set()
        first.join(timeout=5)
        assert not first.is_alive() and actress_faces._running is False
        if case == 'raise_then_later_kick':
            actress_faces.kick()
            second = actress_faces._thread
            second.join(timeout=5)
            assert not second.is_alive() and actress_faces._running is False
        assert fake.call_count == (1 if case == 'kick_does_no_io' else 2)
        assert config.call_count == 0
    finally:
        release.set()
        if actress_faces._thread is not None:
            actress_faces._thread.join(timeout=5)


@pytest.mark.parametrize('case', ['endpoint_result_survives_endpoint_off', 'pigo_result_survives_endpoint_unreachable'])
def test_existing_result_is_never_downgraded(case, setup_faces, monkeypatch):
    repo, cfg, fps, avatars, target, add = setup_faces
    add('A')
    model = 'm0' if case == 'endpoint_result_survives_endpoint_off' else 'local-pigo'
    repo.update_face_result('A', 'found', 'box', model, *fps['A'])
    before = repo.get_by_name('A')
    if model == 'm0':
        cfg['ai_services']['faces']['enabled'] = False
    detect = Mock(return_value=ExternalResult('FAILED'))
    runner = Mock(return_value=('FOUND', [], (400, 400)))
    monkeypatch.setattr(actress_faces.faces_detect, 'detect', detect)
    monkeypatch.setattr(actress_faces.face_runner, 'run_face_boxes', runner)
    actress_faces.sweep()
    assert repo.get_by_name('A') == before
    assert runner.call_count == 0 and detect.call_count == (0 if model == 'm0' else 1)


def test_truncated_photo_does_not_stop_pigo_sweep(setup_faces, monkeypatch):
    repo, cfg, fps, avatars, target, add = setup_faces
    add('A')
    add('B')
    cfg['ai_services']['faces']['enabled'] = False
    runner = Mock(side_effect=[('ABANDONED', 'unreadable'), ('FOUND', [], (400, 400))])
    monkeypatch.setattr(actress_faces.face_runner, 'run_face_boxes', runner)

    actress_faces.sweep()

    assert runner.call_count == 2
    assert [call.args[0] for call in runner.call_args_list] == [fps['A'][0], fps['B'][0]]
    assert repo.get_by_name('A').face_status == ''
    assert repo.get_by_name('B').face_status == 'none'
