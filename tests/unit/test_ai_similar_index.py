"""186-T4a: 圖片相似索引工作核心（建立／停止／繼續／換模型／增量／承接）。

假端點接縫＝patch ``core.ai_services.embeddings._new_client``（BE-TEST-29），
一個 handler 切四種模式（正常／錯維度／換 model／斷線）。thread 一律用等待 helper，
逾時即失敗（BE-TEST-45）；「不准發生」一律量次數（BE-TEST-46）。
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from contextlib import closing

import httpx
import pytest
from PIL import Image

from core.ai_services import embeddings, samples, similar_index, similar_state
from core.database import EmbeddingRepository, Video, VideoRepository, init_db
from core.database import connection as db_connection
from core.database.embeddings import pack_vector
from core.path_utils import to_file_uri

_REAL_FETCH = similar_index._fetch_pending


def _vec(seed: str, dim: int) -> list[float]:
    out: list[float] = []
    i = 0
    while len(out) < dim:
        out += [b - 127.5 for b in hashlib.sha256(f"{seed}|{i}".encode()).digest()]
        i += 1
    return out[:dim]


class FakeEndpoint:
    """mode: normal | bad_dim | down。換 model＝改 ``model``／``dim``。"""

    def __init__(self):
        self.mode, self.model, self.dim = "normal", "model-X", 128
        self.salt = ""  # 底層模型換了但名稱沒變：改 salt 就得到不同向量
        self.covers = self.samples = self.inflight = self.peak = 0
        self.on_cover = None  # callable(n)：每個封面請求在回應前於 handler 內呼叫
        self._lock = threading.Lock()
        self._sample_uris = set(samples.get_sample_inputs())

    def handler(self, request: httpx.Request) -> httpx.Response:
        uri = json.loads(request.content)["input"][0]
        is_cover = uri not in self._sample_uris
        with self._lock:
            self.inflight += 1
            self.peak = max(self.peak, self.inflight)
            if is_cover:
                self.covers += 1
            else:
                self.samples += 1
            n = self.covers
        try:
            if is_cover and self.on_cover:
                self.on_cover(n)
            if self.mode == "down":
                raise httpx.ConnectError("down", request=request)
            dim = 64 if self.mode == "bad_dim" else self.dim
            body = {"model": self.model, "data": [{"embedding": _vec(uri + self.salt, dim)}]}
            return httpx.Response(200, json=body)
        finally:
            with self._lock:
                self.inflight -= 1

    @property
    def requests(self) -> int:
        return self.covers + self.samples


class Env:
    def __init__(self, tmp_path, monkeypatch, name):
        self.tmp = tmp_path / name
        self.tmp.mkdir()
        self.db = self.tmp / "lib.db"
        init_db(self.db)
        self.n = 0
        self.covers: dict[int, str] = {}
        self.vrepo = VideoRepository(self.db)
        self.fake = FakeEndpoint()
        self.cfg = {
            "ai_services": {"image_similar": {
                "enabled": True, "url": "http://embed.test", "api_key": "", "model": "m"}},
            "gallery": {"path_mappings": {}},
        }
        monkeypatch.setattr(db_connection, "get_db_path", lambda: self.db)
        monkeypatch.setattr(similar_index, "load_config", lambda: self.cfg)
        monkeypatch.setattr(embeddings, "_new_client", lambda timeout=None: httpx.Client(
            transport=httpx.MockTransport(self.fake.handler), timeout=timeout))
        self.repo = EmbeddingRepository(self.db)

    def add_video(self, with_cover: bool = True) -> int:
        self.n += 1
        cover = ""
        if with_cover:
            f = self.tmp / f"c{self.n}.jpg"
            Image.new("RGB", (64, 64), (self.n * 37 % 256, self.n * 91 % 256, self.n * 53 % 256)).save(f)
            cover = to_file_uri(str(f))
        vid = self.vrepo.upsert(Video(
            path=to_file_uri(str(self.tmp / f"v{self.n}.mp4")), number=f"T-{self.n:03d}",
            cover_path=cover))
        self.covers[vid] = cover
        return vid

    def restore_cover(self, n: int) -> None:
        Image.new("RGB", (64, 64), (n * 37 % 256, n * 91 % 256, n * 53 % 256)).save(self.tmp / f"c{n}.jpg")

    def stamp(self, video_id: int) -> float:
        with closing(db_connection.get_connection(self.db)) as conn:
            return conn.execute(
                "SELECT updated_at FROM video_embeddings WHERE video_id = ?", (video_id,)).fetchone()[0]

    def rows(self, where: str = "1=1") -> int:
        with closing(db_connection.get_connection(self.db)) as conn:
            return conn.execute(f"SELECT COUNT(*) FROM video_embeddings WHERE {where}").fetchone()[0]

    def models(self) -> set:
        with closing(db_connection.get_connection(self.db)) as conn:
            return {r[0] for r in conn.execute(
                "SELECT DISTINCT model FROM video_embeddings WHERE dim > 0")}

    def complete(self):
        return self.repo.get_index_state()["complete"]

    def gate(self) -> bool:
        return similar_state.fusion_gate_open(self.cfg, self.db)


def _reset_state(monkeypatch) -> None:
    """模組級狀態歸零（BE-TEST-38）；也用來模擬「程序重啟」（丟棄記憶體、不起 thread）。"""
    for name, val in (("_JOB_LOCK", threading.Lock()), ("_STATE_LOCK", threading.Lock()),
                      ("_STOP", threading.Event()), ("_rerun", False),
                      ("_notification_sink", None)):
        monkeypatch.setattr(similar_index, name, val)
    for name, val in (("observed_model", None), ("observed_dim", None), ("unreachable", False),
                      ("last_error_kind", None), ("last_error_check", None),
                      ("job", {"kind": None, "done": 0, "outcome": None})):
        monkeypatch.setattr(similar_state, name, val)


def _workers() -> list:
    return [t for t in threading.enumerate() if t.name == similar_index.THREAD_NAME]


def _join_workers(timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    for t in _workers():
        t.join(max(0.0, deadline - time.monotonic()))
        if t.is_alive():
            pytest.fail("similar-index worker did not finish in time")


@pytest.fixture(autouse=True)
def _fresh_state(monkeypatch):
    _reset_state(monkeypatch)
    yield
    similar_index.request_stop()
    _join_workers()


def _build_and_join() -> dict:
    res = similar_index.start_build()
    _join_workers()
    return res


def _stop_at(env: Env, k: int) -> None:
    env.fake.on_cover = lambda n: similar_index.request_stop() if n == k else None


def _check_pending_predicate(env: Env) -> None:
    ids = {k: env.add_video() for k in ("none", "other_model", "other_dim", "new_cover", "tried", "done")}
    env.add_video(with_cover=False)
    env.repo.begin_index("m1", 128)
    vec = pack_vector(_vec("x", 128))
    c = env.covers
    env.repo.write_vector(ids["other_model"], "old", 128, vec, c[ids["other_model"]])
    env.repo.write_vector(ids["other_dim"], "m1", 256, vec, c[ids["other_dim"]])
    env.repo.write_vector(ids["new_cover"], "m1", 128, vec, "file:///old-cover.jpg")
    env.repo.write_unreadable(ids["tried"], "m1", c[ids["tried"]])
    env.repo.write_vector(ids["done"], "m1", 128, vec, c[ids["done"]])
    pending = {vid for vid, _ in env.repo.pending("m1", 128)}
    assert pending == {ids[k] for k in ("none", "other_model", "other_dim", "new_cover")}
    assert env.repo.counts("m1", 128) == {"indexed": 1, "total": 6, "pending": 4, "unreadable": 1}


def test_pending_and_resume(tmp_path, monkeypatch):
    """R1：使用者停下再按繼續 → 不重算已算的；重啟後不自己續跑。"""
    _check_pending_predicate(Env(tmp_path, monkeypatch, "pred"))

    env = Env(tmp_path, monkeypatch, "resume")
    m, k = 6, 3
    vids = [env.add_video() for _ in range(m)]
    unreadable, still_bad = 5, 6  # 停止點 k 之後兩部封面檔不見 → I7：寫 dim=0 列、工作繼續
    for n in (unreadable, still_bad):
        (env.tmp / f"c{n}.jpg").unlink()
    _stop_at(env, k)
    assert _build_and_join()["status"] == "started"
    assert env.rows() == k

    _reset_state(monkeypatch)  # 模擬重啟：丟棄記憶體，不起 thread
    before = env.fake.requests
    st = similar_index.status()
    assert (st["running"], st["pending"], st["complete"]) == (False, m - k, False)
    assert env.fake.requests == before and not _workers()

    env.fake.covers, env.fake.on_cover = 0, None
    assert _build_and_join()["status"] == "started"
    assert env.fake.covers == m - k - 2  # 讀不到的兩部沒送請求
    assert (env.rows(), env.complete()) == (m, "1")
    assert env.repo.get_row(vids[unreadable - 1])["dim"] == 0
    st = similar_index.status()
    assert (st["pending"], st["unreadable"], st["indexed"]) == (0, 2, m - 2)

    env.restore_cover(unreadable)  # NAS 接回：再按建立 → 讀不到的各重試一次，不迴圈
    env.fake.covers, stamp = 0, env.stamp(vids[still_bad - 1])
    _build_and_join()
    assert env.fake.covers == 1  # 只有放回封面的那部送請求；仍讀不到的重試也不送
    assert env.stamp(vids[still_bad - 1]) > stamp  # 但它確實被重試過（重寫 dim=0 列）
    assert env.repo.get_row(vids[unreadable - 1])["dim"] > 0
    st = similar_index.status()
    assert (st["pending"], st["unreadable"], st["complete"]) == (0, 1, True)
    env.fake.covers = 0
    _build_and_join()  # 仍讀不到的每次工作只重試一次、不迴圈：零請求、unreadable 仍 1、pending 0
    st = similar_index.status()
    assert (env.fake.covers, st["unreadable"], st["pending"]) == (0, 1, 0)


def test_single_job(tmp_path, monkeypatch):
    """R1：建索引中又掃描 → 不得同時兩份工作打端點。"""
    env = Env(tmp_path, monkeypatch, "single")
    for _ in range(4):
        env.add_video()
    entered, release = threading.Event(), threading.Event()

    def hook(n):
        if n == 1:
            entered.set()
            release.wait(10)

    env.fake.on_cover = hook
    try:
        assert similar_index.start_build()["status"] == "started"
        assert entered.wait(10)
        samples_before = env.fake.samples
        assert similar_index.start_build()["status"] == "already_running"
        similar_index.schedule_incremental()
        assert len(_workers()) == 1
    finally:
        release.set()
    _join_workers()
    assert env.fake.peak <= 1
    assert env.fake.samples == samples_before  # 第二次 start_build 沒跑一致性測試
    assert similar_index.status()["pending"] == 0


def test_model_change_no_mixing(tmp_path, monkeypatch):
    """R1：換模型後星空混用兩種模型，或重建到一半就用半套向量。"""
    env = Env(tmp_path, monkeypatch, "model")
    for _ in range(5):
        env.add_video()

    env.fake.mode = "bad_dim"  # I2：錯維度 → 測試不過，零列、index_model 不變
    res = similar_index.start_build()
    assert (res["status"], res["kind"], res["check"]) == ("test_failed", "contract", "dim_range")
    assert env.rows() == 0 and env.repo.get_index_state()["model"] is None and not _workers()

    env.fake.mode = "normal"  # I3：X 建完 → 改 Y 重建
    _build_and_join()
    assert (env.models(), env.complete(), env.gate()) == ({"model-X"}, "1", True)
    env.fake.model, env.fake.dim, env.fake.covers = "model-Y", 192, 0
    _stop_at(env, 2)
    _build_and_join()
    assert (env.complete(), env.gate()) == ("0", False)  # I12：重建途中停止
    env.fake.on_cover = None
    _build_and_join()
    assert (env.models(), env.complete(), env.gate()) == ({"model-Y"}, "1", True)

    env.fake.model = "model-Z"  # I8：端點又換了模型，掃描不得混寫
    env.add_video()
    rows_before = env.rows()
    similar_index.schedule_incremental()
    _join_workers()
    assert env.rows() == rows_before and env.models() == {"model-Y"}
    assert similar_index.status()["model_changed"] is True and env.gate() is False


def test_unreachable_stops_and_notifies_once(tmp_path, monkeypatch):
    """R1：端點斷線時使用者以為新片有被算；停止後一次掃描卻讓 OpenAver 自己補完整批。"""
    env = Env(tmp_path, monkeypatch, "down")
    for _ in range(2):
        env.add_video()
    calls: list = []
    similar_index.set_notification_sink(lambda *a, **kw: calls.append((a, kw)))
    _build_and_join()
    for _ in range(3):
        env.add_video()
    base = env.rows()
    env.fake.covers = 0
    env.fake.on_cover = lambda n: setattr(env.fake, "mode", "down") if n == 2 else None
    similar_index.schedule_incremental()
    _join_workers()
    assert env.rows() == base + 1  # 已寫的保留
    assert calls == [(("warn", "notif.ai_similar_unreachable"), {"task_type": "ai_similar"})]
    st = similar_index.status()
    assert (st["unreachable"], st["kind"], st["pending"]) == (True, "unreachable", 2)

    def assert_noop(e: Env) -> None:  # I9／I10：條件不成立 → 零請求、不起 thread、待處理保留
        e.fake.mode, e.fake.on_cover = "normal", None
        before = e.fake.requests
        similar_index.schedule_incremental()
        assert not _workers() and e.fake.requests == before
        assert similar_index.status()["pending"] > 0

    env.cfg["ai_services"]["image_similar"]["enabled"] = False
    assert_noop(env)
    fresh = Env(tmp_path, monkeypatch, "fresh")  # index_model 未設
    for _ in range(4):
        fresh.add_video()
    assert_noop(fresh)
    _stop_at(fresh, 2)  # 停止後 index_complete=='0'
    _build_and_join()
    assert fresh.complete() == "0"
    assert_noop(fresh)
    assert len(calls) == 1


def _install_barrier(monkeypatch):
    """讓工作停在「已觀察到待處理＝0、仍持有工作鎖」的邊界（只攔第一次）。"""
    reached, release, first = threading.Event(), threading.Event(), [True]

    def wrapper(ctx):
        result = _REAL_FETCH(ctx)
        if first[0]:
            first[0] = False
            reached.set()
            release.wait(10)
        return result

    monkeypatch.setattr(similar_index, "_fetch_pending", wrapper)
    return reached, release


def _queue_handoff_at_boundary(env: Env, monkeypatch, then=None) -> None:
    """已建完 → 增量停在邊界 → 此時進一部新片並排隊承接 →（可選 then）→ 放行並等結束。"""
    _build_and_join()
    reached, release = _install_barrier(monkeypatch)
    env.fake.covers = 0
    try:
        similar_index.schedule_incremental()
        assert reached.wait(10)
        env.add_video()
        similar_index.schedule_incremental()
        if then:
            then()
    finally:
        release.set()
    _join_workers()


def test_scan_handoff(tmp_path, monkeypatch):
    """R1：新片一直沒有向量；或使用者按停止後 OpenAver 又自己對端點送請求。"""
    a = Env(tmp_path, monkeypatch, "during")  # I5：建立中進新片
    for _ in range(4):
        a.add_video()
    added = []
    a.fake.on_cover = lambda n: added.append(a.add_video()) if n == 2 else None
    _build_and_join()
    st = similar_index.status()
    assert (st["pending"], st["total"], a.fake.covers, a.complete()) == (0, 5, 5, "1")

    b = Env(tmp_path, monkeypatch, "boundary")  # I13：邊界插入＋排隊 → 恰算一次
    for _ in range(3):
        b.add_video()
    _queue_handoff_at_boundary(b, monkeypatch)
    assert (b.fake.covers, similar_index.status()["pending"], b.complete()) == (1, 0, "1")

    c = Env(tmp_path, monkeypatch, "stop")  # I13 豁免：排隊後按停止 → 零新請求、不自行重開
    for _ in range(3):
        c.add_video()
    _queue_handoff_at_boundary(c, monkeypatch, then=similar_index.request_stop)
    st = similar_index.status()
    assert (c.fake.covers, st["pending"], st["running"]) == (0, 1, False)
    _reset_state(monkeypatch)  # 模擬重啟：仍零請求
    st = similar_index.status()
    assert (c.fake.covers, st["pending"], st["running"]) == (0, 1, False) and not _workers()
    _build_and_join()  # 「繼續」後才歸 0
    assert (c.fake.covers, similar_index.status()["pending"]) == (1, 0)


def _vec_bytes(env: Env) -> dict:
    with closing(db_connection.get_connection(env.db)) as conn:
        return {r[0]: bytes(r[1]) for r in conn.execute("SELECT video_id, vec FROM video_embeddings")}


def _snapshot(env: Env) -> tuple:
    with closing(db_connection.get_connection(env.db)) as conn:
        rows = conn.execute(
            "SELECT video_id, model, dim, vec, cover_path FROM video_embeddings ORDER BY video_id"
        ).fetchall()
    return [tuple(r) for r in rows], env.repo.get_index_state()


def test_rebuild_refused_while_running(tmp_path, monkeypatch):
    """R1：建立進行中按刪除並重建 → 向量被刪光、兩份工作同時打端點。"""
    env = Env(tmp_path, monkeypatch, "rb_run")
    for _ in range(4):
        env.add_video()
    entered, release = threading.Event(), threading.Event()

    def hook(n):
        if n == 2:
            entered.set()
            release.wait(10)

    env.fake.on_cover = hook
    try:
        assert similar_index.start_build()["status"] == "started"
        assert entered.wait(10)
        rows, samples_before = env.rows(), env.fake.samples
        assert similar_index.start_rebuild()["status"] == "already_running"
        assert env.rows() == rows == 1
        assert env.fake.samples == samples_before  # 沒跑第二次一致性測試
        assert len(_workers()) == 1
    finally:
        release.set()
    _join_workers()
    assert env.fake.peak <= 1 and env.rows() == 4


def test_rebuild_test_failed_keeps_everything(tmp_path, monkeypatch):
    """R2：端點壞了還按重建 → 好端端的向量白白被刪、之後也建不回來。"""
    env = Env(tmp_path, monkeypatch, "rb_fail")
    for _ in range(3):
        env.add_video()
    _build_and_join()
    before = _snapshot(env)
    assert len(before[0]) == 3 and before[1]["complete"] == "1"
    env.fake.mode = "bad_dim"
    res = similar_index.start_rebuild()
    assert (res["status"], res["kind"], res["check"]) == ("test_failed", "contract", "dim_range")
    assert _snapshot(env) == before and not _workers()


def test_rebuild_deletes_then_recomputes_all(tmp_path, monkeypatch):
    """R3：按重建卻瞬間完成、向量其實沒換 → 使用者以為換好了，星空仍用舊模型的向量。"""
    env = Env(tmp_path, monkeypatch, "rb_all")
    m = 5
    for _ in range(m):
        env.add_video()
    _build_and_join()
    old = _vec_bytes(env)
    assert len(old) == m
    env.fake.salt, env.fake.covers = "-new", 0  # 同 model／同 dim，底層模型換了
    assert similar_index.start_rebuild()["status"] == "started"
    _join_workers()
    new = _vec_bytes(env)
    assert env.fake.covers == m  # 每一張封面都重送了
    assert set(new) == set(old) and all(new[k] != old[k] for k in old)
    assert (env.rows(), env.complete()) == (m, "1")


def test_rebuild_gate_closed_until_complete(tmp_path, monkeypatch):
    """R4：重建到一半（含停止）星空就用半套新向量 → 同一批片的結果隨進度忽好忽壞。"""
    env = Env(tmp_path, monkeypatch, "rb_gate")
    for _ in range(4):
        env.add_video()
    _build_and_join()
    assert env.gate() is True
    env.fake.salt, env.fake.covers = "-new", 0
    entered, release = threading.Event(), threading.Event()

    def hook(n):
        if n == 2:
            entered.set()
            release.wait(10)

    env.fake.on_cover = hook
    try:
        assert similar_index.start_rebuild()["status"] == "started"
        assert entered.wait(10)
        assert (env.gate(), env.complete()) == (False, "0") and env.rows() < 4
        similar_index.request_stop()
    finally:
        release.set()
    _join_workers()
    assert (env.gate(), env.complete()) == (False, "0")
    env.fake.on_cover = None
    _build_and_join()
    assert (env.gate(), env.complete(), env.rows()) == (True, "1", 4)


def test_rebuild_result_single_model_and_fresh_cache(tmp_path, monkeypatch):
    """R5：重建完成後星空查詢仍拿刪除前的向量矩陣 → 等於沒重建。"""
    env = Env(tmp_path, monkeypatch, "rb_cache")
    for _ in range(3):
        env.add_video()
    _build_and_join()
    vid = next(iter(env.covers))
    old = _vec_bytes(env)[vid]
    similar_state.fusion_vectors(env.cfg, env.db)  # 暖 cache：載入舊向量
    env.fake.salt = "-new"
    assert similar_index.start_rebuild()["status"] == "started"
    _join_workers()
    new = _vec_bytes(env)[vid]
    assert new != old
    with closing(db_connection.get_connection(env.db)) as conn:
        assert [tuple(r) for r in conn.execute(
            "SELECT DISTINCT model, dim FROM video_embeddings WHERE dim > 0")] == [("model-X", 128)]
    vectors = similar_state.fusion_vectors(env.cfg, env.db)
    assert vectors is not None
    got = pack_vector(list(vectors[vid]))
    assert got == new and got != old
