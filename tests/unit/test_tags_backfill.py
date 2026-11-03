"""188c-T4a: 補完全庫 job 核心（鎖／停止／承接／逐部放棄／status／繼續旗標）。

全部走注入的 ``_tag_one`` 接縫，不連任何網路（BE-TEST-43）。thread 一律用等待 helper，
逾時即失敗（BE-TEST-45）；「不准發生」一律量次數（BE-TEST-46）。
時序類測試行數超過產品碼屬預期。
"""
from __future__ import annotations

import threading
import time

import pytest

from core.ai_services import tags_backfill, tags_state
from core.ai_services.tagging import TaggingFailure
from core.database import Video, VideoRepository, init_db
from core.database import connection as db_connection
from core.path_utils import to_file_uri

_REAL_FETCH = tags_backfill._fetch_pending
_REAL_CONSUME = tags_backfill._consume_handoff_locked
_STATUS_KEYS = {
    "running", "job_kind", "done", "skipped", "slow", "waiting", "stop_reason", "outcome",
    "pending", "total", "tagged", "resumable", "unreachable", "last_success_at",
}


class Env:
    def __init__(self, tmp_path, monkeypatch):
        self.tmp = tmp_path
        tmp_path.mkdir(parents=True, exist_ok=True)
        self.db = tmp_path / "lib.db"
        init_db(self.db)
        monkeypatch.setattr(db_connection, "get_db_path", lambda: self.db)
        self.cfg = {"ai_services": {"tags": {"enabled": True}}}
        monkeypatch.setattr(tags_backfill, "load_config", lambda: self.cfg)
        self.vrepo = VideoRepository(self.db)
        self.n = 0
        self.calls: list[str] = []
        self.idents: set[int] = set()
        self.inflight = self.peak = 0
        self.behave = None  # callable(path, nth_call) -> None，可拋例外；回來後視為成功
        self._lock = threading.Lock()
        # T4b：每片第幾次呼叫、每次開始時飛行中數（含自己）
        self.path_counts: dict[str, int] = {}
        self.inflight_at_start: list[tuple[str, int, int]] = []
        monkeypatch.setattr(tags_backfill, "_tag_one", self._fake_tag_one)

    def add_video(self, with_cover: bool = True) -> str:
        self.n += 1
        path = to_file_uri(str(self.tmp / f"v{self.n}.mp4"))
        self.vrepo.upsert(Video(
            path=path, number=f"T-{self.n:03d}", cover_path="cover.jpg" if with_cover else ""))
        return path

    def progress(self) -> tuple[int, int, int]:
        total, pending = self.vrepo.count_ai_tag_progress()
        return total, pending, total - pending

    def start_inflight_of(self, path: str, path_nth: int) -> int:
        for p, n, inf in self.inflight_at_start:
            if p == path and n == path_nth:
                return inf
        raise AssertionError(f"no inflight_at_start for {path!r} nth={path_nth}")

    def _fake_tag_one(self, path: str):
        with self._lock:
            self.calls.append(path)
            nth = len(self.calls)
            path_nth = self.path_counts.get(path, 0) + 1
            self.path_counts[path] = path_nth
            self.inflight += 1
            self.inflight_at_start.append((path, path_nth, self.inflight))
            self.peak = max(self.peak, self.inflight)
            self.idents |= {t.ident for t in _workers()}
        try:
            if self.behave:
                self.behave(path, nth)
            self.vrepo.update_user_tags(path, [], ai_tagged=True)  # 成功像真的一樣落盤
        finally:
            with self._lock:
                self.inflight -= 1


def _reset_state(monkeypatch) -> None:
    """模組級狀態歸零（BE-TEST-38）；也用來模擬「程序重啟」（丟棄記憶體、不起 thread）。"""
    for name, val in (("_JOB_LOCK", threading.Lock()), ("_STATE_LOCK", threading.Lock()),
                      ("_STOP", threading.Event()), ("_rerun", False)):
        monkeypatch.setattr(tags_backfill, name, val)
    for name, val in (
        ("unreachable", False), ("last_success_at", None), ("last_persist_mono", None),
        ("notified", False), ("notification_sink", None),
        ("job", {"kind": None, "done": 0, "skipped": 0, "slow": False, "waiting": False,
                 "stop_reason": None, "outcome": None}),
    ):
        monkeypatch.setattr(tags_state._STATE, name, val)


def _workers() -> list:
    return [t for t in threading.enumerate() if t.name == tags_backfill.THREAD_NAME]


def _join_workers(timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    for t in _workers():
        t.join(max(0.0, deadline - time.monotonic()))
        if t.is_alive():
            pytest.fail("tags-backfill worker did not finish in time")


@pytest.fixture(autouse=True)
def _fresh_state(monkeypatch):
    _reset_state(monkeypatch)
    yield
    tags_backfill.request_stop()
    _join_workers()


@pytest.fixture(autouse=True)
def _no_real_429_wait(monkeypatch):
    """防止任何測試真等 60 秒；行為②自己再 patch 成 30。"""
    from core.ai_services import tags_backfill_policy
    monkeypatch.setattr(tags_backfill_policy, "WAIT_429_S", 0)


@pytest.fixture
def serial_pool(monkeypatch):
    """T4a 四支在 pool=4 下 peak／呼叫數會 race；強制並行上限 1。"""
    from core.ai_services import tags_backfill_policy
    monkeypatch.setattr(tags_backfill_policy, "MAX_CONCURRENCY", 1)


class _SpyStop(threading.Event):
    """覆寫 wait：先標記 entered 再委派，供行為①(b)／②／halt-wake 偵測 429 等待縫。"""

    def __init__(self):
        super().__init__()
        self.entered = threading.Event()
        self.wait_timeouts: list = []
        self.saw_waiting = False

    def wait(self, timeout=None):
        self.wait_timeouts.append(timeout)
        self.saw_waiting = tags_backfill.status()["waiting"] is True
        self.entered.set()
        return super().wait(timeout)


class _RecordingLock:
    """委派真實鎖，記錄每次取鎖的（呼叫 thread 名, 取鎖當下鎖是否已被持有）。"""

    def __init__(self, real, on_attempt=None):
        self.real, self.records, self.on_attempt = real, [], on_attempt

    def __enter__(self):
        name = threading.current_thread().name
        self.records.append((name, self.real.locked()))
        if self.on_attempt:
            self.on_attempt(name)
        self.real.acquire()
        return self

    def __exit__(self, *exc):
        self.real.release()
        return False


def test_scan_handoff_at_boundary_runs_new_video_once_by_same_thread(tmp_path, monkeypatch, serial_pool):
    """R1：更新片庫掃進新片時剛好撞上補標收尾，或同時按了補完全庫 → 新片仍被標、不起兩份、不重複付費。"""
    env = Env(tmp_path, monkeypatch)
    paths = [env.add_video() for _ in range(3)]
    reached, release, first = threading.Event(), threading.Event(), [True]

    def barrier(ctx):  # 停在「已看到待處理＝0、仍持有工作鎖、尚未進收尾」
        result = _REAL_FETCH(ctx)
        if first[0] and not result:
            first[0] = False
            env.idents |= {t.ident for t in _workers()}
            reached.set()
            release.wait(10)
        return result

    monkeypatch.setattr(tags_backfill, "_fetch_pending", barrier)
    assert tags_backfill.start_build() == {"ok": True, "status": "started"}
    try:
        assert reached.wait(10)
        paths.append(env.add_video())
        tags_backfill.schedule_incremental()  # job 還在跑 → 只留承接旗標
        before = env.progress()
        assert tags_backfill.start_build() == {"ok": False, "status": "already_running"}
        assert tags_backfill.start_rebuild() == {"ok": False, "status": "already_running"}
        assert env.progress() == before and before[2] == 3  # I-RESET-LOCK：零寫入、tagged 不變
    finally:
        release.set()
    _join_workers()

    assert sorted(env.calls) == sorted(paths)  # 4 部各恰一次，含承接進來的新片
    assert len(env.idents) == 1 and env.peak == 1
    assert env.progress() == (4, 0, 4)
    assert not tags_backfill._JOB_LOCK.locked()


def test_stop_halts_requests_and_restart_shows_resume_without_thread(tmp_path, monkeypatch, serial_pool):
    """R1：按停止後仍被扣費，或重啟後自己跑起來，或「還有 N 部」與實際對不上。"""
    env = Env(tmp_path, monkeypatch)
    paths = [env.add_video() for _ in range(5)]
    env.add_video(with_cover=False)
    k = 3
    env.behave = lambda path, nth: tags_backfill.request_stop() if nth == k else None

    assert tags_backfill.start_build()["status"] == "started"
    _join_workers()
    st = tags_backfill.status()
    assert set(st) == _STATUS_KEYS
    assert len(env.calls) == k  # 停止之後不再開始新請求
    assert (st["outcome"], st["running"], st["job_kind"]) == ("stopped", False, None)
    assert (st["total"], st["pending"], st["tagged"], st["done"]) == (5, 2, 3, 3)
    assert st["resumable"] is True
    assert tags_state.meta_get(tags_state.META_BACKFILL_OPEN) == "1"

    # 模擬重啟：記憶體歸零、DB 保留；status() 不起 thread、不送請求
    tags_state.meta_set(tags_state.META_LAST_SUCCESS, repr(1700000000.5))
    _reset_state(monkeypatch)
    st = tags_backfill.status()
    assert len(env.calls) == k and _workers() == []
    assert (st["running"], st["resumable"], st["pending"]) == (False, True, 2)
    assert isinstance(st["last_success_at"], float) and st["last_success_at"] == 1700000000.5

    env.behave = None  # 再按「繼續」：只跑剩下的
    assert tags_backfill.start_build()["status"] == "started"
    _join_workers()
    assert sorted(env.calls) == sorted(paths)  # 每部恰一次，沒重算已標的
    assert tags_state.meta_get(tags_state.META_BACKFILL_OPEN) is None
    st = tags_backfill.status()
    assert (st["outcome"], st["pending"], st["resumable"], st["tagged"]) == ("drained", 0, False, 5)

    env.add_video()  # 跑完後掃進新片：按鈕不能寫「繼續」
    st = tags_backfill.status()
    assert (st["pending"], st["resumable"]) == (1, False)


def test_failing_videos_are_skipped_once_each_and_job_still_drains(tmp_path, monkeypatch, serial_pool):
    """R1：有幾部片永遠標不出來 → 補完全庫仍會跑完、不是永遠轉。"""
    env = Env(tmp_path, monkeypatch)
    paths = [env.add_video() for _ in range(4)]

    def behave(path, nth):
        if path == paths[1]:
            raise TaggingFailure("bad_response", detail="bad_json")
        if path == paths[2]:
            raise RuntimeError("boom")

    env.behave = behave
    assert tags_backfill.start_build()["status"] == "started"
    _join_workers()
    assert sorted(env.calls) == sorted(paths)  # 失敗片各只被呼叫 1 次
    st = tags_backfill.status()
    assert (st["outcome"], st["skipped"], st["done"], st["running"]) == ("drained", 2, 2, False)
    assert st["pending"] == 2  # 被放棄的片仍待處理，但不再有「繼續」
    assert tags_state.meta_get(tags_state.META_BACKFILL_OPEN) is None and st["resumable"] is False


def test_scan_arriving_inside_final_check_is_not_lost(tmp_path, monkeypatch, serial_pool):
    """R1：更新片庫恰好撞上補標收尾 → 新進的片沒人跑，要等下次掃描。"""
    env = Env(tmp_path, monkeypatch)
    paths = [env.add_video() for _ in range(2)]
    reached, release = threading.Event(), threading.Event()
    sched_tried, first = threading.Event(), [True]
    lock = _RecordingLock(
        tags_backfill._STATE_LOCK, on_attempt=lambda n: sched_tried.set() if n == "sched" else None)
    monkeypatch.setattr(tags_backfill, "_STATE_LOCK", lock)

    def hook():  # worker 停在 _STATE_LOCK 區段內部（最後檢查）
        if first[0]:
            first[0] = False
            reached.set()
            release.wait(10)
        return _REAL_CONSUME()

    monkeypatch.setattr(tags_backfill, "_consume_handoff_locked", hook)
    sched = threading.Thread(target=tags_backfill.schedule_incremental, name="sched")
    assert tags_backfill.start_build()["status"] == "started"
    try:
        assert reached.wait(10)
        paths.append(env.add_video())  # 此時 worker 已不會再撈，新片只能靠接下來的 sched 被跑
        sched.start()
        assert sched_tried.wait(10)
    finally:
        release.set()
    sched.join(10)
    assert not sched.is_alive()
    _join_workers()

    assert ("sched", True) in lock.records  # 掃描端取鎖當下被擋（鎖正被收尾區段持有）
    assert sorted(env.calls) == sorted(paths)  # 新片恰好一次
    assert env.peak == 1  # 任何時刻最多一份 job 在 _tag_one 內
    assert env.progress() == (3, 0, 3) and not tags_backfill._JOB_LOCK.locked()


# ── T4b：並行／降速／429 等待／halt 通知 ──────────────────────────────────────

def test_concurrency_caps_at_four_and_degrades_to_one_after_429(tmp_path, monkeypatch):
    """服務一限流就還是 4 條硬打，或偶發一波 429 就被誤判額度用完整批停下。"""
    # (a) 全成功、8 部、首 4 次同時卡住 ⇒ peak == 4
    env_a = Env(tmp_path / "a", monkeypatch)
    for _ in range(8):
        env_a.add_video()
    barrier_a = threading.Barrier(4)
    seen_a = [0]

    def behave_a(path, nth):
        with env_a._lock:
            seen_a[0] += 1
            my = seen_a[0]
        if my <= 4:
            barrier_a.wait(timeout=5)

    env_a.behave = behave_a
    assert tags_backfill.start_build()["status"] == "started"
    _join_workers()
    assert env_a.peak == 4 and env_a.peak > 1
    assert tags_backfill.status()["outcome"] == "drained"

    # (b) 一部第一次 429 ⇒ 降速後開始的請求飛行中數 == 1，slow=True
    # 起始 Barrier(4) 確保 A 回 429 前 B/C/D 已在飛（否則 A 太快會在他人領取前就降速）
    _reset_state(monkeypatch)
    env_b = Env(tmp_path / "b", monkeypatch)
    A, B, C, D, E = [env_b.add_video() for _ in range(5)]
    release_b = threading.Event()
    started_post = threading.Event()
    start_b = threading.Barrier(4)
    spy = _SpyStop()
    monkeypatch.setattr(tags_backfill, "_STOP", spy)

    def behave_b(path, nth):
        with env_b._lock:
            attempt = env_b.path_counts[path]
        if path in (A, B, C, D) and attempt == 1:
            start_b.wait(timeout=5)
        if path == A:
            if attempt == 1:
                raise TaggingFailure("unreachable", detail="rate_limited")
            started_post.set()
            return
        if path == B:
            release_b.wait(10)
            return
        if path in (C, D):
            assert spy.entered.wait(10)
            return
        if path == E:
            started_post.set()
            return

    env_b.behave = behave_b
    assert tags_backfill.start_build()["status"] == "started"
    assert spy.entered.wait(10)
    assert not started_post.wait(0.3)  # 降速後、B 仍占名額時不得開始 A#2／E
    release_b.set()
    _join_workers()
    st_b = tags_backfill.status()
    assert st_b["slow"] is True
    assert st_b["outcome"] == "drained"
    assert env_b.start_inflight_of(A, 2) == 1
    assert env_b.start_inflight_of(E, 1) == 1

    # (c) 4 部同時在飛、全部第一次 429 ⇒ 不得 quota、drained、skipped==0
    _reset_state(monkeypatch)
    env_c = Env(tmp_path / "c", monkeypatch)
    for _ in range(4):
        env_c.add_video()
    barrier_c = threading.Barrier(4)

    def behave_c(path, nth):
        with env_c._lock:
            attempt = env_c.path_counts[path]
        if attempt == 1:
            barrier_c.wait(timeout=5)
            raise TaggingFailure("unreachable", detail="rate_limited")

    env_c.behave = behave_c
    assert tags_backfill.start_build()["status"] == "started"
    _join_workers()
    st_c = tags_backfill.status()
    assert st_c["outcome"] == "drained"
    assert st_c["stop_reason"] is None
    assert st_c["skipped"] == 0
    assert st_c["outcome"] != "quota"

    # (d) connection_timeout 降速後的重試必須重走 gate（開始時飛行中數 == 1）
    _reset_state(monkeypatch)
    env_d = Env(tmp_path / "d", monkeypatch)
    A, B, C, D, E = [env_d.add_video() for _ in range(5)]
    release_b = threading.Event()
    started_retry = threading.Event()
    start_d = threading.Barrier(4)
    timed_out = threading.Event()

    def behave_d(path, nth):
        with env_d._lock:
            attempt = env_d.path_counts[path]
        if path in (A, B, C, D) and attempt == 1:
            start_d.wait(timeout=5)
        if path == A:
            if attempt == 1:
                timed_out.set()
                raise TaggingFailure("unreachable", detail="connection_timeout")
            started_retry.set()
            return
        if path == B:
            release_b.wait(10)
            return
        if path in (C, D):
            assert timed_out.wait(10)
            return
        if path == E:
            started_retry.set()
            return

    env_d.behave = behave_d
    assert tags_backfill.start_build()["status"] == "started"
    try:
        assert timed_out.wait(10)
        assert not started_retry.wait(0.3)  # B 仍占名額時 A 重試／E 不得開始
    finally:
        release_b.set()
    _join_workers()
    st_d = tags_backfill.status()
    assert st_d["slow"] is True
    assert st_d["outcome"] == "drained"
    assert env_d.start_inflight_of(A, 2) == 1
    assert env_d.start_inflight_of(E, 1) == 1


def test_stop_interrupts_429_wait_and_never_resends(tmp_path, monkeypatch):
    """按停止卻要等 60 秒才停，或停了之後還對雲端多送一次。"""
    from core.ai_services import tags_backfill_policy
    monkeypatch.setattr(tags_backfill_policy, "WAIT_429_S", 30)
    env = Env(tmp_path, monkeypatch)
    path = env.add_video()
    sink_calls: list = []
    tags_state.set_notification_sink(lambda *a, **k: sink_calls.append((a, k)))

    spy = _SpyStop()
    monkeypatch.setattr(tags_backfill, "_STOP", spy)

    def behave(p, nth):
        raise TaggingFailure("unreachable", detail="rate_limited")

    env.behave = behave
    assert tags_backfill.start_build()["status"] == "started"
    assert spy.entered.wait(10)
    assert tags_backfill.status()["waiting"] is True
    tags_backfill.request_stop()
    _join_workers()
    st = tags_backfill.status()
    assert len(env.calls) == 1
    assert st["outcome"] == "stopped"
    assert st["waiting"] is False
    assert env.progress() == (1, 1, 0)  # 該片仍 pending
    assert path in env.vrepo.list_ai_pending_paths()
    assert tags_state.meta_get(tags_state.META_BACKFILL_OPEN) == "1"
    assert sink_calls == []


@pytest.mark.parametrize("case", ["skip_only", "disabled", "build_halt", "incremental_halt"])
def test_halt_notifies_once_and_skip_or_drain_notifies_none(tmp_path, monkeypatch, case):
    """模型連不上時 4 條各發一則灌爆通知，或失敗卻沒人知道，或自己關掉開關也被通知。"""
    env = Env(tmp_path / case, monkeypatch)
    sink_calls: list = []
    tags_state.set_notification_sink(lambda *a, **k: sink_calls.append((a, k)))

    if case == "skip_only":
        for _ in range(3):
            env.add_video()

        def behave_skip(path, nth):
            raise TaggingFailure("bad_response", detail="bad_json")

        env.behave = behave_skip
        assert tags_backfill.start_build()["status"] == "started"
        _join_workers()
        assert tags_backfill.status()["outcome"] == "drained"
        assert sink_calls == []
        return

    if case == "disabled":
        for _ in range(2):
            env.add_video()

        def behave_dis(path, nth):
            raise TaggingFailure("disabled")

        env.behave = behave_dis
        assert tags_backfill.start_build()["status"] == "started"
        _join_workers()
        st = tags_backfill.status()
        assert st["outcome"] == "disabled"
        assert st["stop_reason"] == "disabled"
        assert sink_calls == []
        return

    # build_halt / incremental_halt：6 部、per-attempt Barrier(4)
    paths = [env.add_video() for _ in range(6)]
    barriers = {1: threading.Barrier(4), 2: threading.Barrier(4)}

    def behave_halt(path, nth):
        with env._lock:
            attempt = env.path_counts[path]
        barriers[attempt].wait(timeout=5)
        raise TaggingFailure("unreachable", detail="connection_failed")

    env.behave = behave_halt
    if case == "incremental_halt":
        tags_backfill.schedule_incremental()
    else:
        assert tags_backfill.start_build()["status"] == "started"
    _join_workers()

    st = tags_backfill.status()
    assert len(env.calls) == 8
    assert all(env.path_counts.get(p, 0) <= 2 for p in paths)
    hit = [p for p in paths if env.path_counts.get(p, 0) > 0]
    assert len(hit) == 4
    assert all(env.path_counts[p] == 2 for p in hit)
    assert env.path_counts.get(paths[4], 0) == 0
    assert env.path_counts.get(paths[5], 0) == 0
    assert st["stop_reason"] == st["outcome"] == "unreachable"
    total, pending, tagged = env.progress()
    assert pending == 6 and tagged == 0
    if case == "build_halt":
        assert st["resumable"] is True
        expected_key = "notif.ai_tags_backfill_stopped"
    else:
        expected_key = "notif.ai_tags_unreachable"
    assert len(sink_calls) == 1
    a, k = sink_calls[0]
    assert a[1] == expected_key
    assert k["task_type"] == "ai_tags"


def test_inflight_failure_after_stop_keeps_stopped_outcome(tmp_path, monkeypatch):
    """停止後才回來的失敗不得覆寫 outcome／stop_reason，也不得 skip／放棄；多 halt 原因時 stop_reason 跟第一個。"""
    # --- 停止後：halt 類與 skip 類都維持 stopped ---
    env = Env(tmp_path / "after_stop", monkeypatch)
    paths = [env.add_video() for _ in range(4)]
    start_b = threading.Barrier(4)
    release = threading.Event()
    all_in = threading.Event()

    def behave(path, nth):
        start_b.wait(timeout=5)
        all_in.set()
        assert release.wait(10)
        if path == paths[0]:
            raise TaggingFailure("disabled")
        if path == paths[1]:
            raise TaggingFailure("not_configured")
        if path == paths[2]:
            raise TaggingFailure("bad_response", detail="bad_json")
        raise RuntimeError("boom")

    env.behave = behave
    assert tags_backfill.start_build()["status"] == "started"
    assert all_in.wait(10)
    tags_backfill.request_stop()
    release.set()
    _join_workers()
    st = tags_backfill.status()
    assert st["outcome"] == "stopped"
    assert st["stop_reason"] is None
    assert st["skipped"] == 0
    assert env.progress() == (4, 4, 0)  # 皆未放棄、仍 pending
    assert sorted(env.vrepo.list_ai_pending_paths()) == sorted(paths)

    # --- 兩種立停原因同時 halt：stop_reason 必須等於第一個 halt（= outcome）---
    _reset_state(monkeypatch)
    env2 = Env(tmp_path / "first_halt", monkeypatch)
    p0 = env2.add_video()
    env2.add_video()
    barrier = threading.Barrier(2)

    def behave2(path, nth):
        barrier.wait(timeout=5)
        if path == p0:
            raise TaggingFailure("disabled")
        raise TaggingFailure("not_configured")

    env2.behave = behave2
    assert tags_backfill.start_build()["status"] == "started"
    _join_workers()
    st2 = tags_backfill.status()
    assert st2["outcome"] in ("disabled", "not_configured")
    assert st2["stop_reason"] == st2["outcome"]


def test_halt_interrupts_429_wait_without_user_stop(tmp_path, monkeypatch):
    """整批 halt 時，其他 worker 的 429 等待不得等滿 60 秒；醒來不重送、waiting 清掉。"""
    from core.ai_services import tags_backfill_policy
    monkeypatch.setattr(tags_backfill_policy, "WAIT_429_S", 30)
    env = Env(tmp_path, monkeypatch)
    A = env.add_video()
    env.add_video()  # B：兩次 connection_failed → halt
    start_b = threading.Barrier(2)
    spy = _SpyStop()
    monkeypatch.setattr(tags_backfill, "_STOP", spy)
    sink_calls: list = []
    tags_state.set_notification_sink(lambda *a, **k: sink_calls.append((a, k)))

    def behave(path, nth):
        with env._lock:
            attempt = env.path_counts[path]
        if attempt == 1:
            start_b.wait(timeout=5)
        if path == A:
            raise TaggingFailure("unreachable", detail="rate_limited")
        # B 等 A 進入 429 冷卻後立刻立停（不走 retry，否則會被共用冷卻擋住而無法 halt）
        assert spy.entered.wait(10)
        raise TaggingFailure("disabled")

    env.behave = behave
    t0 = time.monotonic()
    assert tags_backfill.start_build()["status"] == "started"
    assert spy.entered.wait(10)
    _join_workers()
    elapsed = time.monotonic() - t0
    st = tags_backfill.status()
    assert spy.saw_waiting is True  # 進入 _STOP.wait 當下 waiting 已亮
    assert elapsed < 10  # 被 halt 喚醒，不得拖到 join 逾時／等滿 30 秒
    assert st["waiting"] is False
    assert st["outcome"] == "disabled"
    assert st["stop_reason"] == "disabled"
    assert env.path_counts.get(A, 0) == 1  # 429 等待被打斷後不重送
    assert sink_calls == []  # disabled 不發通知


def test_shared_cooldown_blocks_all_tagging_until_deadline(tmp_path, monkeypatch):
    """I-COOLDOWN：撞 429 後整批進入共用冷卻；冷卻期間不得有任何 _tag_one（新片或重送）。"""
    from core.ai_services import tags_backfill_policy
    monkeypatch.setattr(tags_backfill_policy, "WAIT_429_S", 60)
    clock = [1000.0]
    monkeypatch.setattr(tags_backfill, "_monotonic", lambda: clock[0], raising=False)

    hold = threading.Event()
    entered = threading.Event()

    class _ClockStop(threading.Event):
        def wait(self, timeout=None):
            entered.set()
            while not hold.is_set() and not self.is_set():
                if hold.wait(0.05):
                    break
            if self.is_set() and not hold.is_set():
                return True
            # 模擬等到截止：推進假時鐘後以 timeout 返回（非使用者停止）
            clock[0] += float(timeout or 0)
            return False

    monkeypatch.setattr(tags_backfill, "_STOP", _ClockStop())
    env = Env(tmp_path, monkeypatch)
    A, B, C, D, E = [env.add_video() for _ in range(5)]
    start_b = threading.Barrier(4)
    post_cooldown = threading.Event()

    def behave(path, nth):
        with env._lock:
            attempt = env.path_counts[path]
        if path in (A, B, C, D) and attempt == 1:
            start_b.wait(timeout=5)
        if path == A and attempt == 1:
            raise TaggingFailure("unreachable", detail="rate_limited")
        if path == E or (path == A and attempt == 2):
            post_cooldown.set()

    env.behave = behave
    assert tags_backfill.start_build()["status"] == "started"
    try:
        assert entered.wait(10)
        assert tags_backfill.status()["waiting"] is True
        # 冷卻中：B/C/D 可跑完首輪，但 A 重送與 E 不得開始
        assert not post_cooldown.wait(0.4)
        assert env.path_counts.get(E, 0) == 0
        assert env.path_counts.get(A, 0) == 1
    finally:
        hold.set()
    _join_workers()
    st = tags_backfill.status()
    assert st["outcome"] == "drained"
    assert st["waiting"] is False
    assert st["outcome"] != "quota"
    assert env.path_counts.get(A, 0) == 2
    assert env.path_counts.get(E, 0) == 1


def test_shared_cooldown_survives_sliding_window_rate_limit(tmp_path, monkeypatch):
    """I-COOLDOWN：每窗 15 次的限流下 ≥40 部不得以 quota 停下，應全部標完。

    無共用冷卻時：降速後其他線在等待中繼續領片撞 429 → 連續三次 → quota。
    """
    from core.ai_services import tags_backfill_policy
    WINDOW = 15
    monkeypatch.setattr(tags_backfill_policy, "WAIT_429_S", 60)
    clock = [0.0]
    monkeypatch.setattr(tags_backfill, "_monotonic", lambda: clock[0], raising=False)
    hold = threading.Event()
    entered = threading.Event()
    successes_left = [WINDOW]
    post_degrade_429 = [0]
    piled = threading.Event()
    lock = threading.Lock()

    class _ClockStop(threading.Event):
        def wait(self, timeout=None):
            entered.set()
            # 可被 halt／stop（Event.set）或測試 hold 喚醒
            while not hold.is_set() and not self.is_set():
                if hold.wait(0.05):
                    break
            if self.is_set() and not hold.is_set():
                return True
            with lock:
                successes_left[0] = WINDOW  # 冷卻結束＝新窗口
            clock[0] += float(timeout or 0)
            return False

    monkeypatch.setattr(tags_backfill, "_STOP", _ClockStop())
    env = Env(tmp_path, monkeypatch)
    n = 40
    for _ in range(n):
        env.add_video()

    def behave(path, nth):
        with lock:
            if successes_left[0] > 0:
                successes_left[0] -= 1
                return
            if entered.is_set():
                post_degrade_429[0] += 1
                if post_degrade_429[0] >= 3:
                    piled.set()
        raise TaggingFailure("unreachable", detail="rate_limited")

    env.behave = behave
    assert tags_backfill.start_build()["status"] == "started"
    assert entered.wait(10)
    # 無冷卻時會在等待中繼續領片並堆積 429；有冷卻則 piled 不會亮
    piled.wait(0.5)
    hold.set()
    _join_workers(timeout=30.0)
    st = tags_backfill.status()
    assert st["outcome"] == "drained"
    assert st["outcome"] != "quota"
    assert st["stop_reason"] is None
    assert env.progress() == (n, 0, n)
    assert st["done"] == n
