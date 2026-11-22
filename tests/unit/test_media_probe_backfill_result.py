"""TASK-a205-T1 — job 計數／ETA／結束可見性（I-J1／I-J2／I-J3）。"""
from __future__ import annotations

import threading
import time

import pytest

from core.ai_services.job_shell import JobShell
from core.database import Video, VideoRepository
from core.database import connection as db_connection
from core.media_probe import ProbeResult
from core.media_probe_worker import MediaProbeWorker
from core.path_utils import to_file_uri


def _ok() -> ProbeResult:
    return ProbeResult(
        status="ok", reason="", width=1920, height=1080,
        video_format="AVC", duration_ms=60_000, hdr_format=None,
        frame_rate=None, overall_bitrate=None, container=None,
        audio_langs=(), subtitle_langs=(), truncated=False,
    )


def _no_video() -> ProbeResult:
    return ProbeResult(
        status="no_video", reason="x", width=None, height=None,
        video_format=None, duration_ms=None, hdr_format=None,
        frame_rate=None, overall_bitrate=None, container=None,
        audio_langs=(), subtitle_langs=(), truncated=False,
    )


@pytest.fixture(autouse=True)
def _fresh_backfill_state(monkeypatch, temp_db):
    import core.media_probe_backfill as backfill
    import core.media_probe_worker as worker_mod

    monkeypatch.setattr(db_connection, "get_db_path", lambda: temp_db)
    monkeypatch.setattr(
        "core.config.load_config",
        lambda: {
            "gallery": {
                "directories": [{"path": "/media", "readonly": False, "output_path": ""}],
                "path_mappings": {},
            }
        },
    )
    backfill._reset_for_tests()
    fresh = MediaProbeWorker(auto_start=False)
    monkeypatch.setattr(worker_mod, "_worker", fresh)
    yield
    backfill._reset_for_tests()
    w = worker_mod.get_worker()
    while True:
        try:
            w._queue.get_nowait()
            w._queue.task_done()
        except Exception:
            break


def _drive_to_finish(backfill, w, timeout_s=5.0):
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        st = backfill.status()
        if st["job"]["total"] >= 1 and st["job"]["done"] == st["job"]["total"] and not st["job"]["running"]:
            break
        if not w._queue.empty():
            w._process_one()
        else:
            for t in threading.enumerate():
                if t.name == backfill.THREAD_NAME and t.is_alive():
                    t.join(0.05)


def test_job_counts_reconcile_to_total(temp_db):
    import core.media_probe_backfill as backfill
    import core.media_probe_worker as worker_mod

    repo = VideoRepository(temp_db)
    paths = []
    for i in range(4):
        p = to_file_uri(f"/media/j1_{i}.mp4")
        repo.upsert(Video(path=p, title=f"片{i}", mtime=float(i + 1), size_bytes=100 + i))
        paths.append(p)

    hold_path = paths[3]
    resubmitted = {"done": False}
    w = worker_mod.get_worker()

    def probe_fn(fs_path):
        if "j1_3" in fs_path:
            with w._lock:
                inflight = set(w._inflight)
            if hold_path in inflight and not resubmitted["done"]:
                resubmitted["done"] = True
                repo.upsert(Video(path=hold_path, title="片3", mtime=999.0, size_bytes=999))
                w.submit(hold_path, hold_path, 4.0, 103, db_path=temp_db)
        if "j1_1" in fs_path:
            return _no_video()
        return _ok()

    def stat_fn(fs_path):
        if "j1_2" in fs_path:
            return None
        return (1_000_000_000, 100)

    w._probe = probe_fn
    w._stat = stat_fn

    result = backfill.start()
    assert result["ok"] is True
    _drive_to_finish(backfill, w)

    st = backfill.status()
    assert st["job"]["total"] == 4
    assert st["job"]["done"] == 4
    assert st["job"]["running"] is False
    assert resubmitted["done"] is True
    last = st["job"]["last_result"]
    assert last is not None
    assert last["total"] == 4
    assert last["read"] + last["failed"] + last["unreachable"] == last["total"] == 4
    assert (last["read"], last["failed"], last["unreachable"]) == (1, 1, 2)


def test_eta_needs_min_samples_then_averages(monkeypatch):
    import core.media_probe_backfill as backfill

    backfill._job_done = 29
    backfill._job_total = 100
    backfill._started_at = 1000.0
    monkeypatch.setattr(backfill, "_now", lambda: 1030.0)
    acquired = backfill._SHELL.job_lock.acquire(blocking=False)
    assert acquired is True
    try:
        st = backfill.status()
        assert st["job"]["elapsed_s"] == pytest.approx(30.0)
        assert st["job"]["eta_s"] is None
    finally:
        backfill._SHELL.job_lock.release()

    backfill._job_done = 30
    backfill._job_total = 130
    backfill._started_at = 1000.0
    monkeypatch.setattr(backfill, "_now", lambda: 1030.0)
    acquired = backfill._SHELL.job_lock.acquire(blocking=False)
    assert acquired is True
    try:
        st = backfill.status()
        assert st["job"]["elapsed_s"] == pytest.approx(30.0)
        assert st["job"]["eta_s"] == pytest.approx(100.0)
    finally:
        backfill._SHELL.job_lock.release()


def test_last_result_ready_before_lock_release(temp_db, monkeypatch):
    import core.media_probe_backfill as backfill

    orig_unbound = JobShell.release_locked
    calls = {"n": 0, "seen": "unset"}

    def fake_release(*args, **kwargs):
        calls["n"] += 1
        calls["seen"] = backfill.status()["job"]["last_result"]
        return orig_unbound(backfill._SHELL, *args, **kwargs)

    monkeypatch.setattr(backfill._SHELL, "release_locked", fake_release)

    import core.media_probe_worker as worker_mod

    repo = VideoRepository(temp_db)
    p = to_file_uri("/media/j3_0.mp4")
    repo.upsert(Video(path=p, title="片", mtime=1.0, size_bytes=100))

    w = worker_mod.get_worker()
    w._probe = lambda fs_path: _ok()
    w._stat = lambda fs_path: (1_000_000_000, 100)

    result = backfill.start()
    assert result["ok"] is True
    _drive_to_finish(backfill, w)

    assert calls["n"] >= 1
    assert calls["seen"] is not None
    assert backfill.status()["job"]["last_result"] is not None


def test_status_completion_snapshot_has_result(monkeypatch):
    import core.media_probe_backfill as backfill

    assert backfill._SHELL.job_lock.acquire(blocking=False)
    original_is_running = backfill._SHELL.is_running

    def finish_before_running_read():
        monkeypatch.setattr(backfill._SHELL, "is_running", original_is_running)
        backfill._record_last_result()
        backfill._SHELL.release_locked()
        return original_is_running()

    monkeypatch.setattr(backfill._SHELL, "is_running", finish_before_running_read)
    job = backfill.status()["job"]
    assert job["running"] or job["last_result"] is not None

    backfill._reset_for_tests()
    assert backfill._SHELL.job_lock.acquire(blocking=False)
    calls = 0

    def pending_during_completion(self, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            backfill._record_last_result()
            backfill._SHELL.release_locked()
            return [object()]
        return []

    monkeypatch.setattr(VideoRepository, "list_media_probe_pending", pending_during_completion)
    st = backfill.status()
    assert st["job"]["running"] or (st["pending"] == 0 and st["readonly_pending"] == 0)
