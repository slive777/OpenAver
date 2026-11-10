"""TASK-198a-T2a — worker／trigger／backfill：I1 oracle-1／-3、I6、I7。"""
from __future__ import annotations

import threading

import pytest

from core.database import Video, VideoRepository
from core.database import connection as db_connection
from core.media_probe import ProbeResult
from core.media_probe_worker import MediaProbeWorker
from core.path_utils import to_file_uri


def _ok(*, width=3840, height=2160, video_format="HEVC", duration_ms=7_200_000) -> ProbeResult:
    return ProbeResult(
        status="ok",
        reason="",
        width=width,
        height=height,
        video_format=video_format,
        duration_ms=duration_ms,
        hdr_format=None,
        frame_rate=23.976,
        overall_bitrate=12_000_000,
        container="MPEG-4",
        audio_langs=("ja",),
        subtitle_langs=(),
        truncated=False,
    )


def _unreadable() -> ProbeResult:
    return ProbeResult(
        status="unreadable",
        reason="io error",
        width=None,
        height=None,
        video_format=None,
        duration_ms=None,
        hdr_format=None,
        frame_rate=None,
        overall_bitrate=None,
        container=None,
        audio_langs=(),
        subtitle_langs=(),
        truncated=False,
    )


@pytest.fixture(autouse=True)
def _fresh_backfill_state(monkeypatch, temp_db):
    """重置 backfill 模組狀態；預設 DB → temp_db（G1／meta_get）。"""
    import core.media_probe_backfill as backfill
    import core.media_probe_worker as worker_mod

    monkeypatch.setattr(db_connection, "get_db_path", lambda: temp_db)
    # directories 含 /media，讓 I6 backfill 的 /media/bf_*.mp4 落在設定資料夾內
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
    # 換掉單例，避免跨測污染
    fresh = MediaProbeWorker(auto_start=False)
    monkeypatch.setattr(worker_mod, "_worker", fresh)
    yield
    backfill._reset_for_tests()
    # 清 queue（BE-TEST-51）
    w = worker_mod.get_worker()
    while True:
        try:
            w._queue.get_nowait()
            w._queue.task_done()
        except Exception:
            break


# ── I1 oracle-1 ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("mode", ["mid_process_resubmit", "queued_double_submit"])
def test_resubmit_latest_wins(temp_db, mode):
    """I1 oracle-1：最後一次 submit 的探針結果勝出。"""
    repo = VideoRepository(temp_db)
    path = to_file_uri("/media/latest_wins.mp4")
    fs = "/media/latest_wins.mp4"
    mtime_old, size = 100.0, 1000
    mtime_new = 200.0
    repo.upsert(Video(path=path, title="片", mtime=mtime_old, size_bytes=size))

    calls = {"n": 0}
    results = [
        _ok(height=2160, width=3840),
        _ok(height=1080, width=1920),
    ]

    def probe_fn(fs_path):
        idx = calls["n"]
        calls["n"] += 1
        if mode == "mid_process_resubmit" and idx == 0:
            # 讀檔中途改寫 DB 列並再 submit（第一次 2160、第二次 1080）
            VideoRepository(temp_db).upsert(
                Video(path=path, title="片", mtime=mtime_new, size_bytes=size)
            )
            w.submit(path, fs, mtime_new, size, db_path=temp_db)
            return results[0]
        # mid 第二次呼叫、或 queued（只探針一次＝第二次 submit 的值）
        return results[1]

    def stat_fn(fs_path):
        return (1_000_000_000, size)

    w = MediaProbeWorker(probe_fn=probe_fn, stat_fn=stat_fn, auto_start=False)

    if mode == "queued_double_submit":
        # 排隊中連 submit 兩次；第二次 expected_mtime／探針回值都不同
        w.submit(path, fs, mtime_old, size, db_path=temp_db)
        VideoRepository(temp_db).upsert(
            Video(path=path, title="片", mtime=mtime_new, size_bytes=size)
        )
        w.submit(path, fs, mtime_new, size, db_path=temp_db)
        assert not w._queue.empty(), "第二次 submit 必須仍在佇列（latest-wins）"
        w._process_one()
    else:
        w.submit(path, fs, mtime_old, size, db_path=temp_db)
        assert not w._queue.empty()
        w._process_one()
        # 中途 resubmit 應已重新入列
        assert not w._queue.empty(), "resubmit 必須重新入列"
        w._process_one()

    view = VideoRepository(temp_db).get_media_probe_view(path)
    assert view is not None
    assert view.media_height == 1080
    assert view.media_probe_mtime == mtime_new


# ── I1 oracle-3 ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "scenario",
    ["stat_changed", "unreadable", "stat_none"],
)
def test_no_write_on_stat_change_or_unreadable(temp_db, scenario, monkeypatch):
    """I1 oracle-3：讀前讀後 stat 不同／unreadable／讀前 stat 失敗 → 零寫入。"""
    repo = VideoRepository(temp_db)
    path = to_file_uri(f"/media/nowrite_{scenario}.mp4")
    fs = f"/media/nowrite_{scenario}.mp4"
    mtime, size = 10.0, 100
    repo.upsert(Video(path=path, title="片", mtime=mtime, size_bytes=size))
    assert repo.update_media_probe(path, _ok(height=720, width=1280), mtime, size) is True
    before = repo.get_media_probe_view(path)
    assert before is not None and before.media_height == 720

    write_calls = []
    real_update = VideoRepository.update_media_probe

    def tracking_update(self, *a, **k):
        write_calls.append((a, k))
        return real_update(self, *a, **k)

    monkeypatch.setattr(VideoRepository, "update_media_probe", tracking_update)

    stats = {"n": 0}

    def probe_fn(fs_path):
        if scenario == "unreadable":
            return _unreadable()
        return _ok(height=2160, width=3840)

    def stat_fn(fs_path):
        if scenario == "stat_none":
            return None
        stats["n"] += 1
        if scenario == "stat_changed":
            # 讀前 ns1、讀後 ns2
            return (1_000_000_000 if stats["n"] == 1 else 2_000_000_000, size)
        return (1_000_000_000, size)

    w = MediaProbeWorker(probe_fn=probe_fn, stat_fn=stat_fn, auto_start=False)
    w.submit(path, fs, mtime, size, db_path=temp_db)
    assert not w._queue.empty()
    w._process_one()

    assert write_calls == [], f"update_media_probe 不得被呼叫：{write_calls}"
    after = VideoRepository(temp_db).get_media_probe_view(path)
    assert after is not None
    assert after.media_height == before.media_height
    assert after.media_probe_mtime == before.media_probe_mtime
    assert after.media_probe_status == before.media_probe_status


# ── I6 ───────────────────────────────────────────────────────────────────────


def test_backfill_progress_converges(temp_db, monkeypatch):
    """I6：快照 3 列、處理第 2 列前對同 path 再 submit → done == total == 3。"""
    import time

    import core.media_probe_backfill as backfill
    import core.media_probe_worker as worker_mod

    repo = VideoRepository(temp_db)
    paths = []
    for i in range(3):
        p = to_file_uri(f"/media/bf_{i}.mp4")
        repo.upsert(Video(path=p, title=f"片{i}", mtime=float(i + 1), size_bytes=100 + i))
        paths.append(p)

    hold_path = paths[1]
    resubmitted = {"done": False}
    seen_done = []

    def probe_fn(fs_path):
        return _ok(height=1080, width=1920)

    def stat_fn(fs_path):
        return (1_000_000_000, 100)

    w = MediaProbeWorker(probe_fn=probe_fn, stat_fn=stat_fn, auto_start=False)
    monkeypatch.setattr(worker_mod, "_worker", w)

    def probe_resubmit(fs_path):
        with w._lock:
            inflight = set(w._inflight)
        if hold_path in inflight and not resubmitted["done"]:
            resubmitted["done"] = True
            view = VideoRepository(temp_db).get_media_probe_view(hold_path)
            w.submit(
                hold_path,
                hold_path,
                view.mtime,
                view.size_bytes,
                db_path=temp_db,
            )
        return probe_fn(fs_path)

    w._probe = probe_resubmit

    result = backfill.start()
    assert result["ok"] is True
    assert result["status"] == "started"

    end = time.monotonic() + 5.0
    while time.monotonic() < end:
        st = backfill.status()
        seen_done.append(st["job"]["done"])
        if (
            st["job"]["total"] >= 3
            and st["job"]["done"] == st["job"]["total"]
            and not st["job"]["running"]
        ):
            break
        if not w._queue.empty():
            w._process_one()
        else:
            for t in threading.enumerate():
                if t.name == backfill.THREAD_NAME and t.is_alive():
                    t.join(0.05)

    st = backfill.status()
    assert st["job"]["total"] == 3
    assert st["job"]["done"] == 3
    assert st["job"]["running"] is False
    # done 單調不減、不超過 total
    assert seen_done == sorted(seen_done)
    assert all(0 <= d <= 3 for d in seen_done)
    assert resubmitted["done"] is True


# ── I7 ───────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "case",
    [
        "pending_default",
        "pending_include_ro",
        "trigger_skips_ro",
        "pending_outside_configured",
        "pending_excludes_strm",
        "trigger_skips_strm",
    ],
)
def test_readonly_rows_never_read(temp_db, monkeypatch, case):
    """I7：唯讀／設定外／.strm 不進 pending；trigger 永不 submit 唯讀與 .strm。"""
    import core.media_probe_backfill as backfill
    import core.media_probe_trigger as trigger
    import core.media_probe_worker as worker_mod

    ro_prefix = to_file_uri("/nas/ro")
    wr_prefix = to_file_uri("/nas/rw")
    ro_path = to_file_uri("/nas/ro/a.mp4")
    wr_path = to_file_uri("/nas/rw/b.mp4")
    outside_path = to_file_uri("/other/removed/c.mp4")
    strm_path = to_file_uri("/nas/rw/d.strm")

    repo = VideoRepository(temp_db)
    repo.upsert(Video(path=ro_path, title="唯讀", mtime=1.0, size_bytes=10))
    repo.upsert(Video(path=wr_path, title="可寫", mtime=2.0, size_bytes=20))
    repo.upsert(Video(path=outside_path, title="已移除來源", mtime=3.0, size_bytes=30))
    repo.upsert(Video(path=strm_path, title="串流指標", mtime=4.0, size_bytes=40))

    submitted = []

    def track_submit(path_uri, fs_path, expected_mtime, expected_size, db_path=None):
        submitted.append(path_uri)

    monkeypatch.setattr(worker_mod, "submit_media_probe", track_submit)
    # trigger 模組內的綁定名也要換（from-import）
    monkeypatch.setattr(trigger, "submit_media_probe", track_submit)

    ro_prefixes = [ro_prefix]
    wr_prefixes = [wr_prefix]
    configured = {ro_prefix, wr_prefix}

    if case == "pending_default":
        pending = repo.list_media_probe_pending(
            include_readonly=False,
            readonly_prefixes=ro_prefixes,
            writable_prefixes=wr_prefixes,
            configured_dir_uris=configured,
        )
        got = {p for p, _m, _s in pending}
        assert got == {wr_path}

    elif case == "pending_include_ro":
        pending = repo.list_media_probe_pending(
            include_readonly=True,
            readonly_prefixes=ro_prefixes,
            writable_prefixes=wr_prefixes,
            configured_dir_uris=configured,
        )
        got = {p for p, _m, _s in pending}
        assert ro_path in got
        assert wr_path in got

    elif case == "pending_outside_configured":
        pending = repo.list_media_probe_pending(
            include_readonly=True,
            readonly_prefixes=ro_prefixes,
            writable_prefixes=wr_prefixes,
            configured_dir_uris=configured,
        )
        got = {p for p, _m, _s in pending}
        assert outside_path not in got
        assert wr_path in got

    elif case == "pending_excludes_strm":
        pending = repo.list_media_probe_pending(
            include_readonly=True,
            readonly_prefixes=ro_prefixes,
            writable_prefixes=wr_prefixes,
            configured_dir_uris=configured,
        )
        got = {p for p, _m, _s in pending}
        assert strm_path not in got
        assert wr_path in got

    elif case == "trigger_skips_strm":
        trigger.maybe_submit_media_probe(
            strm_path,
            db_path=temp_db,
            readonly_prefixes=ro_prefixes,
            writable_prefixes=wr_prefixes,
            path_mappings={},
        )
        assert submitted == []

    else:
        # trigger 在 include_readonly=True 設定下仍不 submit 唯讀
        backfill.set_include_readonly(True)
        assert backfill.get_include_readonly() is True
        trigger.maybe_submit_media_probe(
            ro_path,
            db_path=temp_db,
            readonly_prefixes=ro_prefixes,
            writable_prefixes=wr_prefixes,
            path_mappings={},
        )
        assert submitted == []