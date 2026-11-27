import json
import queue
import threading
import time

import pytest
from PIL import Image

import core.config as config
from core.ai_services.faces import Box, FacesResult
from core.ai_services import faces_detect
from core.focal import subprocess_runner


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'CONFIG_PATH', tmp_path / 'config.json')
    monkeypatch.setattr(config, 'CONFIG_DEFAULT_PATH', tmp_path / 'default.json')
    monkeypatch.setattr(subprocess_runner, '_breaker_streak', 0)
    monkeypatch.setattr(subprocess_runner, '_cover_waiting', 0, raising=False)
    monkeypatch.setattr(subprocess_runner, '_last_cover_release_mono', None, raising=False)
    monkeypatch.setattr(subprocess_runner, '_slot_lock', threading.Lock())


class FakeProcess:
    def __init__(self, result=None):
        self.stdout = self
        self.stderr = None
        self.lines = queue.Queue()
        self.lines.put('READY\n')
        if result is not None:
            self.lines.put(json.dumps(result) + '\n')

    def readline(self):
        return self.lines.get()

    def kill(self):
        self.lines.put('')

    def wait(self):
        return 0


def test_actress_pigo_timeouts_never_disable_cover_focal():
    from core.focal import face_runner
    from core.version import VERSION
    config.save_config({'focal_device': {'disabled': False, 'consecutive_timeout_count': 0,
                                       'judged_at_version': VERSION, 'set_by_user': False}})
    before = config.load_config()['focal_device']
    streak = subprocess_runner._breaker_streak
    calls = []
    def spawn(path):
        calls.append(path)
        return FakeProcess()
    for _ in range(2):
        assert face_runner.run_face_boxes('x', timeout_s=0.02, pre_spawn_check=lambda: False,
                                          spawn_fn=spawn) == ('ABANDONED', 'detect_timeout')
    assert len(calls) == 2
    assert config.load_config()['focal_device'] == before
    assert subprocess_runner._breaker_streak == streak


def test_child_faces_payload_keeps_row_col_order(tmp_path):
    from core.focal import _detect_faces_child as child, face_runner
    assert child.faces_payload([(200, 50, 40, 3.0)], 0.5, 400, 800) == [[0.5, 0.25, 80.0, 3.0]]
    path = tmp_path / 'exif.jpg'
    img = Image.new('RGB', (120, 60))
    exif = img.getexif()
    exif[274] = 6
    img.save(path, exif=exif)
    payload = child.build_payload(str(path))
    assert payload['size'] == [60, 120]
    calls = []
    def spawn(path):
        calls.append(path)
        return FakeProcess(payload)
    assert face_runner.run_face_boxes('x', pre_spawn_check=lambda: False, spawn_fn=spawn) == (
        'FOUND', payload['faces'], (60, 120))
    assert len(calls) == 1


@pytest.mark.parametrize('case', ['order_A_C_B', 'no_acquire_while_cover_waiting',
    'quiet_window_after_cover_release', 'endpoint_enabled_while_waiting',
    'probe_failure_fail_closed', 'cover_wait_bound'])
def test_cover_has_priority_over_actress_pigo(monkeypatch, case):
    from core.focal import face_runner
    monkeypatch.setattr(face_runner, '_POLL_INTERVAL_S', 0.01)
    monkeypatch.setattr(face_runner, 'COVER_QUIET_S', 0.05)
    monkeypatch.setattr(subprocess_runner, '_try_external', lambda *args: (None, None))
    release = threading.Event()
    started = threading.Event()
    order = []
    threads = []
    def face_spawn(path):
        order.append(path)
        started.set()
        proc = FakeProcess({'faces': [], 'size': [1, 1]})
        if path == 'A':
            proc.lines = queue.Queue()
            proc.lines.put('READY\n')
            def finish():
                release.wait(2)
                proc.lines.put(json.dumps({'faces': [], 'size': [1, 1]}) + '\n')
            threading.Thread(target=finish, daemon=True).start()
        return proc
    def face(path='B', check=lambda: False, spawn=face_spawn):
        return face_runner.run_face_boxes(path, timeout_s=0.1, pre_spawn_check=check, spawn_fn=spawn)
    def cover():
        def spawn(path, ratio):
            order.append('C')
            return FakeProcess({'focal': None})
        subprocess_runner.run_detection('C', 1.5, job_key='c', timeout_s=1, spawn_fn=spawn)
    def start(fn):
        t = threading.Thread(target=fn, daemon=True)
        threads.append(t)
        t.start()
    try:
        if case in ('order_A_C_B', 'cover_wait_bound'):
            start(lambda: face('A'))
            assert started.wait(1)
            start(cover)
            deadline = time.monotonic() + 1
            while subprocess_runner.cover_waiting() == 0 and time.monotonic() < deadline:
                threading.Event().wait(0.001)
            assert subprocess_runner.cover_waiting() == 1
            if case == 'order_A_C_B':
                start(face)
                release.set()
            else:
                threads[1].join(1.2)
                assert not threads[1].is_alive()
            for t in threads:
                t.join(2)
            assert order == (['A', 'C', 'B'] if case == 'order_A_C_B' else ['A', 'C'])
        elif case == 'no_acquire_while_cover_waiting':
            class CountingLock:
                def __init__(self):
                    self.lock = threading.Lock()
                    self.calls = []
                def acquire(self, *args, **kwargs):
                    self.calls.append((args, kwargs))
                    return self.lock.acquire(*args, **kwargs)
                def release(self):
                    self.lock.release()
            lock = CountingLock()
            observed = threading.Event()
            flag = threading.Event()
            def waiting():
                observed.set()
                return 0 if flag.is_set() else 1
            monkeypatch.setattr(subprocess_runner, '_slot_lock', lock)
            monkeypatch.setattr(subprocess_runner, 'cover_waiting', waiting)
            start(face)
            assert observed.wait(1)
            assert lock.calls == []
            flag.set()
            threads[0].join(2)
            assert len(lock.calls) == 1
        elif case == 'quiet_window_after_cover_release':
            monkeypatch.setattr(face_runner, 'COVER_QUIET_S', 2.0)
            cover()
            assert subprocess_runner.cover_quiet_for() < face_runner.COVER_QUIET_S
            start(face)
            assert not started.wait(0.02)
            monkeypatch.setattr(face_runner, 'COVER_QUIET_S', 0.0)
            threads[0].join(2)
            assert order == ['C', 'B']
        else:
            def probe():
                if case == 'probe_failure_fail_closed':
                    raise RuntimeError('probe')
                return {'ai_services': {'faces': {'enabled': True, 'url': 'http://x'}}}
            monkeypatch.setattr(face_runner, 'load_config', probe)
            if case == 'endpoint_enabled_while_waiting':
                monkeypatch.setattr(face_runner, 'active_in', lambda cfg: True)
            assert face_runner.run_face_boxes('B', spawn_fn=face_spawn) == ('ABANDONED', 'skipped_disabled')
            assert order == []
            assert subprocess_runner._slot_lock.acquire(blocking=False)
            subprocess_runner._slot_lock.release()
    finally:
        release.set()
        if case == 'no_acquire_while_cover_waiting':
            flag.set()
        for t in threads:
            t.join(2)
            assert not t.is_alive()


@pytest.mark.parametrize('score,kind', [(0.9, 'FOUND'), (0.0, 'NO_FACE')], ids=['found', 'no_face_with_boxes'])
def test_external_result_carries_boxes_for_found_and_no_face(score, kind):
    boxes = [Box(0.2, 0.2, 0.3, 0.4, score)]
    result = faces_detect._to_external_result(FacesResult(boxes=boxes, model='m'), 100, 100, 1.5, 'warmup')
    assert result.kind == kind
    assert result.boxes == tuple(boxes)
