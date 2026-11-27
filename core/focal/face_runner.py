"""Run actress face detection in the shared, cover-priority slot."""
import json
import math
import os
import queue
import subprocess
import sys
import time
from pathlib import Path

from core.ai_services.faces_config import active_in
from core.config import load_config
from core.focal import device_state, subprocess_runner
from core.logger import get_logger

logger = get_logger(__name__)
_ACTRESS_DETECT_TIMEOUT_S = 15.0
COVER_QUIET_S = 2.0
_POLL_INTERVAL_S = 0.5


def _default_spawn(fs_path):
    import core.focal as focal_pkg
    root = Path(focal_pkg.__file__).resolve().parents[2]
    kwargs = dict(args=[sys.executable, '-u', '-m', 'core.focal._detect_faces_child', fs_path],
                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(root),
                  env={**os.environ, 'PYTHONPATH': str(root)}, text=True, encoding='utf-8')
    if sys.platform == 'win32':
        kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
    return subprocess.Popen(**kwargs)


def actress_pre_spawn_check():
    try:
        cfg = load_config()
        return active_in(cfg) or device_state.is_disabled_in(cfg)
    except Exception:
        logger.exception('actress face configuration probe failed')
        return True


def _acquire_slot():
    while True:
        if subprocess_runner.cover_waiting() == 0 and subprocess_runner.cover_quiet_for() >= COVER_QUIET_S:
            lock = subprocess_runner._slot_lock
            if lock.acquire(blocking=False):
                return lock
        time.sleep(_POLL_INTERVAL_S)


def _parse_faces_line(line):
    try:
        data = json.loads(line)
        faces, size = data['faces'], data['size']
        if not isinstance(faces, list) or not isinstance(size, list) or len(size) != 2:
            return None
        if any(type(v) is not int or v <= 0 for v in size):
            return None
        if any(not isinstance(f, list) or len(f) != 4 or
               any(type(v) not in (int, float) or not math.isfinite(v) for v in f)
               for f in faces):
            return None
        return ('FOUND', faces, tuple(size))
    except (ValueError, TypeError, KeyError):
        return None


def _read_faces_result(child, timeout_s):
    events = queue.Queue()
    subprocess_runner._start_reader(child.stdout, events)
    subprocess_runner._start_stderr_drain(getattr(child, 'stderr', None))
    event = subprocess_runner._queue_get(events, subprocess_runner._STARTUP_TIMEOUT_S)
    if event is subprocess_runner._TIMEOUT:
        return ('ABANDONED', 'startup_timeout')
    if event[0] != 'line' or event[1] != 'READY':
        return ('ABANDONED', 'crashed')
    event = subprocess_runner._queue_get(events, timeout_s)
    if event is subprocess_runner._TIMEOUT:
        return ("ABANDONED", "detect_timeout")
    if event[0] != 'line':
        return ('ABANDONED', 'crashed')
    return _parse_faces_line(event[1]) or ('ABANDONED', 'crashed')


def run_face_boxes(fs_path, *, timeout_s=_ACTRESS_DETECT_TIMEOUT_S, pre_spawn_check=None,
                   spawn_fn=_default_spawn):
    lock = _acquire_slot()
    child = None
    abandoned = True
    try:
        try:
            skip = (pre_spawn_check or actress_pre_spawn_check)()
        except Exception:
            logger.exception('actress face pre-spawn check failed')
            skip = True
        if skip:
            return ('ABANDONED', 'skipped_disabled')
        try:
            child = spawn_fn(fs_path)
        except OSError:
            logger.exception('actress face spawn failed')
            return ('ABANDONED', 'crashed')
        result = _read_faces_result(child, timeout_s)
        abandoned = result[0] == 'ABANDONED'
        return result
    finally:
        if child is not None:
            if abandoned:
                subprocess_runner._safe_kill(child)
            try:
                child.wait()
            except Exception:
                logger.exception('actress face child wait failed')
        lock.release()
