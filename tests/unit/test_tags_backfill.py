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

    def _fake_tag_one(self, path: str):
        with self._lock:
            self.calls.append(path)
            nth = len(self.calls)
            self.inflight += 1
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
        ("unreachable", False), ("last_success_at", None), ("_last_persist_mono", None),
        ("notified", False), ("_notification_sink", None),
        ("job", {"kind": None, "done": 0, "skipped": 0, "slow": False, "waiting": False,
                 "stop_reason": None, "outcome": None}),
    ):
        monkeypatch.setattr(tags_state, name, val)


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


def test_scan_handoff_at_boundary_runs_new_video_once_by_same_thread(tmp_path, monkeypatch):
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


def test_stop_halts_requests_and_restart_shows_resume_without_thread(tmp_path, monkeypatch):
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


def test_failing_videos_are_skipped_once_each_and_job_still_drains(tmp_path, monkeypatch):
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


def test_scan_arriving_inside_final_check_is_not_lost(tmp_path, monkeypatch):
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
