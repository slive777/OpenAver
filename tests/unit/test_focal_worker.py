"""test_focal_worker.py - core/focal/worker.py 單元測試 (TASK-98a-T5 DoD 1-6)

全測試用假 detector + 假 commit + 可控 fingerprint 注入（不真跑 pigo / 不碰 DB），
且一律用 `_process_one()` 同步驅動 worker loop 的一步（免與真背景 thread 賽跑，
deterministic）。每個 test 都 `FocalWorker()` 自己 new 一個 instance，絕不碰
module-level 單例 `_worker` / `submit_focal`。
"""
import threading

from core.focal.detector import format_focal
from core.focal.worker import FocalWorker, _fingerprint


def _make_fp_store(initial):
    """dict 型可控 fingerprint：test 直接改 dict 內容模擬「換圖」。"""
    store = dict(initial)

    def fp_fn(fs_path):
        return store.get(fs_path)

    return store, fp_fn


class TestLatestWinsRace:
    """DoD 1 — Codex P1: A 在途換圖 submit(B)，A 被丟棄、B 確實 commit（非只驗 A 不覆蓋 B）。"""

    def test_a_dropped_on_stale_fp_b_committed(self):
        path = "/fake/v.jpg"
        store, fp_fn = _make_fp_store({path: ("fp_v1",)})
        committed = []

        def commit(focal_str, fp):
            committed.append(focal_str)

        w = FocalWorker(fingerprint_fn=fp_fn, auto_start=False)

        def fake_detect(fs_path, ratio, work_width):
            if ratio == 1.0:
                # side effect of A's (slow) detection: image gets swapped
                # mid-flight AND a fresh submit(B) for the SAME key lands.
                store[fs_path] = ("fp_v2",)
                w.submit("video", "v", fs_path, 2.0, commit)
                return (0.1, 0.1)  # A's coords -- must be dropped
            return (0.9, 0.9)  # B's coords -- must be committed

        w._detect = fake_detect

        w.submit("video", "v", path, 1.0, commit)
        w._process_one()  # processes A: start_fp != end_fp -> dropped
        assert committed == [], "A's stale result must not be committed"

        # Guard: if re-enqueue were broken, the queue would be empty here and
        # the next _process_one() would BLOCK forever (no pytest-timeout in
        # repo). Assert first so a regression fails cleanly instead of hanging.
        assert not w._queue.empty(), "B must have been re-queued (latest-wins)"
        w._process_one()  # processes B (re-queued by A's side effect)
        assert committed == [format_focal((0.9, 0.9))], (
            "B's focal must be committed -- proves B wasn't deduped away"
        )


class TestDequeueFingerprint:
    """DoD 2 — Codex P2: fp 在 dequeue（job 啟動）取樣，不是 submit 取樣。"""

    def test_swap_while_queued_still_recomputes_current_image(self):
        path = "/fake/v.jpg"
        store, fp_fn = _make_fp_store({path: ("fp1",)})
        committed = []

        def commit(focal_str, fp):
            committed.append((focal_str, fp))

        def fake_detect(fs_path, ratio, work_width):
            return (0.5, 0.5)

        w = FocalWorker(detect_fn=fake_detect, fingerprint_fn=fp_fn, auto_start=False)
        w.submit("video", "v", path, 1.0, commit)

        # swap BEFORE processing (queued period, not submit-time)
        store[path] = ("fp2",)

        w._process_one()

        # dequeue takes start_fp == "fp2" (current at dequeue), detect
        # doesn't change it further -> end_fp == start_fp -> commits the
        # CURRENT image's focal, not a stale-drop of the submit-time fp.
        assert committed == [(format_focal((0.5, 0.5)), ("fp2",))]


class TestNoFaceStillCommits:
    """DoD 3 — detect() -> None still commits '' (both commit styles)."""

    def test_video_style_and_actress_style_both_receive_empty_string(self):
        video_path = "/fake/v.jpg"
        actress_path = "/fake/a.jpg"
        store, fp_fn = _make_fp_store({
            video_path: ("fpv",),
            actress_path: ("fpa",),
        })

        def fake_detect(fs_path, ratio, work_width):
            return None

        video_committed = []
        actress_committed = []

        def video_commit(focal_str, fp):
            video_committed.append(focal_str)  # fp ignored (video-style)

        def actress_commit(focal_str, fp):
            actress_committed.append((focal_str, fp))  # fp used (actress-style)

        w = FocalWorker(detect_fn=fake_detect, fingerprint_fn=fp_fn, auto_start=False)

        w.submit("video", "v1", video_path, 1.0, video_commit)
        w._process_one()
        w.submit("actress", "a1", actress_path, 1.0, actress_commit)
        w._process_one()

        assert video_committed == ['']
        assert actress_committed == [('', ("fpa",))]


class TestCommitDispatch:
    """DoD 4 — worker calls whatever commit callback it's given, unchanged
    args, proving it's repo-agnostic (doesn't hardcode video vs actress)."""

    def test_each_commit_style_invoked_with_right_args(self):
        video_path = "/fake/v.jpg"
        actress_path = "/fake/a.jpg"
        store, fp_fn = _make_fp_store({
            video_path: ("fpv",),
            actress_path: ("fpa",),
        })

        def fake_detect(fs_path, ratio, work_width):
            return (0.3, 0.7)

        recorder = []

        def video_commit(focal_str, fp):
            recorder.append(("video", focal_str))

        def actress_commit(focal_str, fp):
            recorder.append(("actress", focal_str, fp))

        w = FocalWorker(detect_fn=fake_detect, fingerprint_fn=fp_fn, auto_start=False)

        w.submit("video", "v1", video_path, 1.0, video_commit)
        w._process_one()
        w.submit("actress", "a1", actress_path, 1.0, actress_commit)
        w._process_one()

        expected = format_focal((0.3, 0.7))
        assert recorder == [
            ("video", expected),
            ("actress", expected, ("fpa",)),
        ]


class TestStackedSubmit:
    """DoD 5 — same key submitted 3x rapidly: queue/pending don't grow,
    final commit is the LAST submitted job's result."""

    def test_same_key_triple_submit_commits_last_only(self):
        path = "/fake/v.jpg"
        store, fp_fn = _make_fp_store({path: ("fp1",)})

        def fake_detect(fs_path, ratio, work_width):
            return (ratio, ratio)  # encode which submit "won" via ratio

        committed = []

        def commit(focal_str, fp):
            committed.append(focal_str)

        w = FocalWorker(detect_fn=fake_detect, fingerprint_fn=fp_fn, auto_start=False)

        w.submit("video", "v", path, 0.1, commit)
        w.submit("video", "v", path, 0.2, commit)
        w.submit("video", "v", path, 0.3, commit)

        assert w._queue.qsize() == 1, "same-key resubmit must not grow the queue"
        assert len(w._pending) == 1, "pending must hold only the latest snapshot"

        w._process_one()
        assert committed == [format_focal((0.3, 0.3))]


class TestExceptionIsolation:
    """DoD 6 — a single job's detect() exception is swallowed; the loop
    (via repeated _process_one calls) keeps working afterward."""

    def test_exception_does_not_prevent_next_job(self):
        path1 = "/fake/v1.jpg"
        path2 = "/fake/v2.jpg"
        store, fp_fn = _make_fp_store({path1: ("fp1",), path2: ("fp2",)})
        calls = {"n": 0}

        def fake_detect(fs_path, ratio, work_width):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("boom")
            return (0.5, 0.5)

        committed = []

        def commit(focal_str, fp):
            committed.append(focal_str)

        w = FocalWorker(detect_fn=fake_detect, fingerprint_fn=fp_fn, auto_start=False)

        w.submit("video", "v1", path1, 1.0, commit)
        w._process_one()  # raises internally -> must be swallowed
        assert committed == []
        assert w._inflight == set(), "inflight must be discarded even on exception"

        w.submit("video", "v2", path2, 1.0, commit)
        w._process_one()  # thread/loop must still work after the exception
        assert committed == [format_focal((0.5, 0.5))]


class TestLazyStart:
    """submit() lazily starts the single daemon thread."""

    def test_first_submit_starts_daemon_thread(self):
        def fake_detect(fs_path, ratio, work_width):
            return None

        def fp_fn(fs_path):
            return ("fp",)

        w = FocalWorker(detect_fn=fake_detect, fingerprint_fn=fp_fn)
        assert w._thread is None

        done = threading.Event()

        def commit(focal_str, fp):
            done.set()

        w.submit("video", "v", "/fake/v.jpg", 1.0, commit)

        assert w._thread is not None
        assert w._thread.daemon is True
        assert done.wait(timeout=2.0), "daemon thread must process the job"


class TestFingerprint:
    """_fingerprint(): real-file smoke (nanosecond mtime + size; OSError -> None)."""

    def test_real_file_returns_path_mtime_ns_size(self, tmp_path):
        f = tmp_path / "img.jpg"
        f.write_bytes(b"hello")
        fp = _fingerprint(str(f))
        assert fp is not None
        fs_path, mtime_ns, size = fp
        assert fs_path == str(f)
        assert size == 5
        assert isinstance(mtime_ns, int)

    def test_missing_file_returns_none(self):
        assert _fingerprint("/nonexistent/path/does-not-exist.jpg") is None
