"""test_focal_worker.py - core/focal/worker.py 單元測試 (TASK-98a-T5 DoD 1-6)

全測試用假 detector + 假 commit + 可控 fingerprint 注入（不真跑 pigo / 不碰 DB），
且一律用 `_process_one()` 同步驅動 worker loop 的一步（免與真背景 thread 賽跑，
deterministic）。每個 test 都 `FocalWorker()` 自己 new 一個 instance，絕不碰
module-level 單例 `_worker` / `submit_focal`。
"""

import types

from core.focal.detector import format_focal
from core.focal.subprocess_runner import RunnerOutcome
from core.focal.worker import FocalWorker


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
                return RunnerOutcome(kind="FOUND", focal=(0.1, 0.1))  # A's coords -- must be dropped
            return RunnerOutcome(kind="FOUND", focal=(0.9, 0.9))  # B's coords -- must be committed

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
            return RunnerOutcome(kind="NO_FACE")

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
            return RunnerOutcome(kind="FOUND", focal=(0.5, 0.5))

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


class TestAbandonedSkipsCommit:
    """TASK-152b-T2 — ABANDONED must not call job.commit; FOUND/NO_FACE still do."""

    def test_abandoned_result_never_commits(self):
        path = "/fake/v.jpg"
        store, fp_fn = _make_fp_store({path: ("fp1",)})
        committed = []

        def commit(focal_str, fp):
            committed.append((focal_str, fp))

        def fake_detect(fs_path, ratio, work_width):
            return RunnerOutcome(kind="ABANDONED", reason="detect_timeout")

        w = FocalWorker(detect_fn=fake_detect, fingerprint_fn=fp_fn, auto_start=False)
        w.submit("video", "v", path, 1.0, commit)
        w._process_one()

        assert committed == []

    def test_found_still_commits_exactly_once(self):
        path = "/fake/v.jpg"
        store, fp_fn = _make_fp_store({path: ("fp1",)})
        committed = []

        def commit(focal_str, fp):
            committed.append((focal_str, fp))

        def fake_detect(fs_path, ratio, work_width):
            return RunnerOutcome(kind="FOUND", focal=(0.4, 0.6))

        w = FocalWorker(detect_fn=fake_detect, fingerprint_fn=fp_fn, auto_start=False)
        w.submit("video", "v", path, 1.0, commit)
        w._process_one()

        assert committed == [(format_focal((0.4, 0.6)), ("fp1",))]


class TestCommitModelPassthrough:
    """187a-T2：outcome 帶 model 才走三參數 commit；本機兩參數簽名不受影響。"""

    def test_commit_passes_model_only_when_outcome_has_model(self):
        path = "/fake/model.jpg"
        store, fp_fn = _make_fp_store({path: ("fp1",)})
        two_arg_calls = []
        three_arg_calls = []

        def commit_two(focal_str, fp):
            two_arg_calls.append((focal_str, fp))

        def commit_three(focal_str, fp, model):
            three_arg_calls.append((focal_str, fp, model))

        def detect_local(fs_path, ratio, work_width):
            return RunnerOutcome(kind="FOUND", focal=(0.5, 0.4))

        def detect_remote(fs_path, ratio, work_width):
            return types.SimpleNamespace(
                kind="FOUND", focal=(0.5, 0.4), reason=None, model="X",
            )

        w = FocalWorker(detect_fn=detect_local, fingerprint_fn=fp_fn, auto_start=False)
        w.submit("video", "v-local", path, 1.0, commit_two)
        w._process_one()
        assert two_arg_calls == [(format_focal((0.5, 0.4)), ("fp1",))]
        assert three_arg_calls == []

        w2 = FocalWorker(detect_fn=detect_remote, fingerprint_fn=fp_fn, auto_start=False)
        w2.submit("video", "v-remote", path, 1.0, commit_three)
        w2._process_one()
        assert three_arg_calls == [(format_focal((0.5, 0.4)), ("fp1",), "X")]

