"""187a-T4a: faces_recompute 全庫重算工作本體（I-D…I-J）。

假端點接縫＝patch ``core.ai_services.faces._new_client``（BE-TEST-43）。
thread 一律用等待 helper，逾時即失敗（BE-TEST-45）；「不准發生」一律量次數。
"""
from __future__ import annotations

import json
import threading
import time
from contextlib import closing

import httpx
import pytest
from PIL import Image

from core.ai_services import faces, faces_detect, faces_state, samples
from core.database import Video, VideoRepository, init_db
from core.database import connection as db_connection
from core.path_utils import to_file_uri

# 無碼番號（gate 命中）；有碼番號（gate 不命中）
_UNCEN = "FC2-1000001"
_CENSORED = "SSIS-001"
_STAMP = "2020-01-01 00:00:00"
_DETECT_RATIO = 0.71


class FakeEndpoint:
    """mode: normal | down | http_5xx | contract。換 model＝改 ``model``／box 偏置。"""

    def __init__(self):
        self.mode = "normal"
        self.model = "model-A"
        self.bias = "left"  # left → 偏左 box；right → 偏右
        self.covers = 0
        self.samples = 0
        self.inflight = 0
        self.peak = 0
        self.on_cover = None  # callable(n)：第 n 次封面請求回應前呼叫
        self._lock = threading.Lock()
        self._sample_uri = samples.get_faces_sample_input()

    def _box(self) -> list[float]:
        if self.bias == "right":
            return [0.7, 0.2, 0.2, 0.2]
        if self.bias == "center":
            return [0.4, 0.2, 0.2, 0.2]  # center (0.5, 0.3) — 過一致性測試
        return [0.1, 0.2, 0.2, 0.2]

    def handler(self, request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        uri = payload["input"]
        is_sample = uri == self._sample_uri
        with self._lock:
            self.inflight += 1
            self.peak = max(self.peak, self.inflight)
            if is_sample:
                self.samples += 1
            else:
                self.covers += 1
                n = self.covers
        try:
            if not is_sample and self.on_cover is not None:
                self.on_cover(n)
            if self.mode == "down":
                raise httpx.ConnectError("down", request=request)
            if self.mode == "http_5xx":
                return httpx.Response(503, json={"error": "cold"})
            if self.mode == "contract":
                # faces 非 list → EndpointError(contract)／ExternalResult.failure=external_contract
                return httpx.Response(200, json={"faces": {}, "model": self.model})
            # 一致性測試用 center；封面重算用 bias
            box = [0.4, 0.2, 0.2, 0.2] if is_sample else self._box()
            return httpx.Response(
                200,
                json={"faces": [{"box": box, "score": 0.9}], "model": self.model},
            )
        finally:
            with self._lock:
                self.inflight -= 1

    @property
    def requests(self) -> int:
        return self.covers + self.samples


class Env:
    def __init__(self, tmp_path, monkeypatch, name: str):
        self.tmp = tmp_path / name
        self.tmp.mkdir()
        self.db = self.tmp / "lib.db"
        init_db(self.db)
        self.n = 0
        self.vrepo = VideoRepository(self.db)
        self.fake = FakeEndpoint()
        self.cfg = {
            "ai_services": {
                "faces": {
                    "enabled": True,
                    "url": "http://faces.test",
                    "api_key": "",
                    "model": "",
                }
            },
            "gallery": {"path_mappings": {}},
        }
        monkeypatch.setattr(db_connection, "get_db_path", lambda: self.db)
        # 各模組 `from core.config import load_config` 是各自綁定——逐一 patch
        monkeypatch.setattr("core.config.load_config", lambda: self.cfg)
        monkeypatch.setattr(faces_detect, "load_config", lambda: self.cfg)
        from core.ai_services import faces_recompute as _fr

        monkeypatch.setattr(_fr, "load_config", lambda: self.cfg)
        monkeypatch.setattr(
            faces,
            "_new_client",
            lambda timeout=None: httpx.Client(
                transport=httpx.MockTransport(self.fake.handler),
                timeout=timeout,
            ),
        )

    def add_video(
        self,
        *,
        number: str = _UNCEN,
        maker: str = "",
        crop_mode: str = "auto",
        auto_focal: str = "0.1111,0.2222",
        focal_model: str = "old-model",
        with_cover: bool = True,
        stamp: str = _STAMP,
    ) -> str:
        self.n += 1
        cover = ""
        if with_cover:
            f = self.tmp / f"c{self.n}.jpg"
            Image.new(
                "RGB",
                (64, 64),
                (self.n * 37 % 256, self.n * 91 % 256, self.n * 53 % 256),
            ).save(f)
            cover = to_file_uri(str(f))
        path = to_file_uri(str(self.tmp / f"v{self.n}.mp4"))
        self.vrepo.upsert(
            Video(path=path, number=number, maker=maker, cover_path=cover)
        )
        with closing(db_connection.get_connection(self.db)) as conn:
            conn.execute(
                "UPDATE videos SET auto_focal=?, crop_mode=?, focal_model=?, "
                "focal_attempted_at=?, created_at=?, updated_at=? WHERE path=?",
                (auto_focal, crop_mode, focal_model, stamp, stamp, stamp, path),
            )
            conn.commit()
        return path

    def row(self, path: str) -> tuple:
        with closing(db_connection.get_connection(self.db)) as conn:
            return conn.execute("SELECT * FROM videos WHERE path=?", (path,)).fetchone()

    def rows_matching(self, where: str, args=()) -> list:
        with closing(db_connection.get_connection(self.db)) as conn:
            return conn.execute(
                f"SELECT * FROM videos WHERE {where}", args
            ).fetchall()

    def count(self, where: str = "1=1", args=()) -> int:
        with closing(db_connection.get_connection(self.db)) as conn:
            return conn.execute(
                f"SELECT COUNT(*) FROM videos WHERE {where}", args
            ).fetchone()[0]

    def unlink_cover(self, path: str) -> None:
        with closing(db_connection.get_connection(self.db)) as conn:
            cover = conn.execute(
                "SELECT cover_path FROM videos WHERE path=?", (path,)
            ).fetchone()[0]
        from core.path_utils import uri_to_local_fs_path
        import os

        fs = uri_to_local_fs_path(cover, {})
        if os.path.exists(fs):
            os.unlink(fs)


def _reset_state(monkeypatch) -> None:
    """模組級狀態歸零（BE-TEST-38）；也用來模擬程序重啟。"""
    from core.ai_services import faces_recompute

    for name, val in (
        ("_JOB_LOCK", threading.Lock()),
        ("_STATE_LOCK", threading.Lock()),
        ("_STOP", threading.Event()),
        ("_unreadable", 0),
        ("_stopped_reason", None),
        ("_stopped_kind", None),
        ("_stopped_check", None),
    ):
        monkeypatch.setattr(faces_recompute, name, val)
    for name, val in (
        ("observed_model", None),
        ("degraded", False),
        ("last_error_kind", None),
        ("last_error_check", None),
        ("notified", False),
        ("last_success_at", None),
        ("job", {"kind": None, "done": 0, "outcome": None}),
        ("_last_persist_mono", None),
        ("_notification_sink", None),
    ):
        monkeypatch.setattr(faces_state, name, val)


def _workers() -> list:
    from core.ai_services import faces_recompute

    return [t for t in threading.enumerate() if t.name == faces_recompute.THREAD_NAME]


def _join_workers(timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    for t in _workers():
        t.join(max(0.0, deadline - time.monotonic()))
        if t.is_alive():
            pytest.fail("faces-recompute worker did not finish in time")


@pytest.fixture(autouse=True)
def _fresh_state(monkeypatch):
    # faces_recompute 可能尚未存在 → 測試檔 import 時先 RED
    from core.ai_services import faces_recompute  # noqa: F401

    _reset_state(monkeypatch)
    yield
    faces_recompute = __import__(
        "core.ai_services.faces_recompute", fromlist=["request_stop"]
    )
    faces_recompute.request_stop()
    _join_workers()


def _ensure_and_join(model: str = "model-A"):
    from core.ai_services import faces_recompute

    started = faces_recompute.ensure(model)
    _join_workers()
    return started


# ── (a) I-G 手動永不碰 ──────────────────────────────────────────────────────


def test_manual_focal_never_touched_by_recompute_or_rebuild(tmp_path, monkeypatch):
    """I-G：5 manual（含 auto_focal 非空、gate 命中）＋10 auto；重算＋刪除並重新對焦後
    manual 列 SELECT * 前後逐位元相等。"""
    from core.ai_services import faces_recompute

    env = Env(tmp_path, monkeypatch, "ig")
    manuals = [
        env.add_video(
            number=f"FC2-{1000001 + i}",
            crop_mode="manual",
            auto_focal=f"0.{i+1:04d},0.5000",
            focal_model="hand-kept",
        )
        for i in range(5)
    ]
    for i in range(10):
        env.add_video(
            number=f"FC2-{2000001 + i}",
            crop_mode="auto",
            auto_focal=f"0.3{i:03d},0.4000",
            focal_model="old-model",
        )

    before = {p: env.row(p) for p in manuals}
    assert all(before.values())

    env.fake.model = "model-A"
    env.fake.bias = "left"
    assert _ensure_and_join("model-A") is True
    after_recompute = {p: env.row(p) for p in manuals}
    assert after_recompute == before

    # 刪除並重新對焦：假端點先過一致性（sample → center box）
    env.fake.bias = "left"
    env.fake.model = "model-A"
    res = faces_recompute.start_rebuild()
    assert res.get("ok") is True
    _join_workers()
    after_rebuild = {p: env.row(p) for p in manuals}
    assert after_rebuild == before


# ── (b) I-H＋I-D＋I-E 停止／繼續／重啟／單一工作 ─────────────────────────────


def test_stop_resume_and_restart_do_not_redo_or_autostart(tmp_path, monkeypatch):
    """I-H／I-D／I-E：停在 k → 已寫＝k±1；繼續不重算；重啟零請求；並行 ≤1。"""
    from core.ai_services import faces_recompute

    env = Env(tmp_path, monkeypatch, "ih")
    m, k = 6, 3
    for i in range(m):
        env.add_video(
            number=f"FC2-{3000001 + i}",
            auto_focal="0.1000,0.2000",
            focal_model="old",
        )

    ensure_calls = {"n": 0}
    real_ensure = faces_recompute.ensure

    def spy_ensure(model, kind="model_change"):
        ensure_calls["n"] += 1
        return real_ensure(model, kind=kind)

    monkeypatch.setattr(faces_recompute, "ensure", spy_ensure)

    env.fake.model = "model-A"
    env.fake.on_cover = (
        lambda n: faces_recompute.request_stop() if n == k else None
    )
    assert faces_recompute.ensure("model-A") is True
    _join_workers()
    done = env.count("focal_model = ?", ("model-A",))
    assert done in (k, k + 1)  # 最多再完成當下一張
    assert env.fake.peak <= 1

    # 進行中再 ensure／resume 不另起 thread（再跑一輪，中途呼叫）
    env.fake.on_cover = None
    entered, release = threading.Event(), threading.Event()

    def hold(n):
        if n == 1:
            entered.set()
            release.wait(10)
            # 工作進行中呼叫
            assert faces_recompute.ensure("model-A") is False
            r = faces_recompute.resume()
            assert r["started"] is False and r["reason"] == "already_running"
            assert len(_workers()) <= 1

    # 先把剩餘清掉以便下一輪測並行；這裡用 resume 繼續
    before_req = env.fake.covers
    remaining = m - done
    env.fake.covers = 0
    env.fake.on_cover = None
    res = faces_recompute.resume()
    assert res["started"] is True
    _join_workers()
    assert env.fake.covers == remaining
    assert env.count("focal_model = ?", ("model-A",)) == m
    assert env.fake.peak <= 1

    # 重啟：歸零模組狀態 → 零 thread、零新請求、pending 反映 DB
    env.fake.covers = 0
    before_ensure = ensure_calls["n"]
    _reset_state(monkeypatch)
    st = faces_recompute.status()
    assert (st["running"], st["pending"]) == (False, 0)  # 全部已是 target
    assert env.fake.covers == 0 and not _workers()
    assert ensure_calls["n"] == before_ensure  # 重啟路徑不呼叫 ensure

    # 再種待處理，驗重啟後不自動開工
    for i in range(3):
        env.add_video(
            number=f"FC2-{4000001 + i}",
            auto_focal="0.1000,0.2000",
            focal_model="old",
        )
    # 設 target 但不 ensure（模擬「重啟時 app_meta 已有 target」）
    faces_state.meta_set("ai.faces.target_model", "model-A")
    _reset_state(monkeypatch)
    # 重啟後 target 仍在 DB，但 thread 不起
    faces_state.meta_set("ai.faces.target_model", "model-A")
    before_req = env.fake.covers
    before_ensure = ensure_calls["n"]
    st = faces_recompute.status()
    assert st["running"] is False
    assert st["pending"] == 3
    assert env.fake.covers == before_req and not _workers()
    assert ensure_calls["n"] == before_ensure

    # 並行請求 ≤1（進行中 hold）
    env.fake.covers = 0
    env.fake.on_cover = hold
    assert faces_recompute.ensure("model-A") is True
    assert entered.wait(10)
    release.set()
    _join_workers()
    assert env.fake.peak <= 1


# ── (c) I-I＋I-J＋I-F 錯誤即停／讀不到／有碼零請求／模型相符 ─────────────────


def test_endpoint_error_stops_keeps_written_and_unreadable_skips(tmp_path, monkeypatch):
    """I-I／I-J／I-F：FAILED 即停、已寫保留、sink 零呼叫；讀不到 K+1；有碼零請求。"""
    from core.ai_services import faces_recompute

    env = Env(tmp_path, monkeypatch, "ii")
    sink_calls: list = []
    faces_state.set_notification_sink(lambda *a, **k: sink_calls.append((a, k)))

    # 先種讀不到的（path 較早）→ ORDER BY path 時先遇到 K+1，再算可讀的
    bad = env.add_video(number="FC2-5000010", focal_model="old")
    env.unlink_cover(bad)
    good = [
        env.add_video(number=f"FC2-{5000001 + i}", focal_model="old")
        for i in range(4)
    ]
    censored = [
        env.add_video(number=f"SSIS-{100 + i}", focal_model="old") for i in range(2)
    ]
    env.add_video(
        number="FC2-5000099",
        crop_mode="manual",
        auto_focal="0.9000,0.9000",
        focal_model="hand",
    )

    # 第 2 張封面請求斷線（第 1 張已寫）→ 已寫保留、未寫 focal_model 不變
    env.fake.model = "model-A"
    env.fake.bias = "left"

    def fail_at(n):
        if n == 2:
            env.fake.mode = "down"

    env.fake.on_cover = fail_at
    assert faces_recompute.ensure("model-A") is True
    _join_workers()

    st = faces_recompute.status()
    assert st["running"] is False
    assert st["stopped_reason"] == "unreachable"
    assert st["kind"] == "unreachable"
    assert sink_calls == []
    assert st["unreadable"] >= 1
    # 錯誤即停：第 2 張封面失敗後不再打剩餘封面（mutation：拔掉 stop 會打滿 4 張）
    assert env.fake.covers <= 3, env.fake.covers
    with closing(db_connection.get_connection(env.db)) as conn:
        written_paths = {
            r[0]
            for r in conn.execute(
                "SELECT path FROM videos WHERE focal_model = ?", ("model-A",)
            )
        }
        assert len(written_paths) >= 1
        assert bad not in written_paths
        assert (
            conn.execute(
                "SELECT focal_model FROM videos WHERE path=?", (bad,)
            ).fetchone()[0]
            == "old"
        )
        for p in good:
            fm = conn.execute(
                "SELECT focal_model FROM videos WHERE path=?", (p,)
            ).fetchone()[0]
            if p in written_paths:
                assert fm == "model-A"
            else:
                assert fm == "old"
        for p in censored:
            assert (
                conn.execute(
                    "SELECT focal_model FROM videos WHERE path=?", (p,)
                ).fetchone()[0]
                == "old"
            )

    # 契約不符 → stopped_reason=contract；sink 仍零
    _reset_state(monkeypatch)
    faces_state.set_notification_sink(lambda *a, **k: sink_calls.append((a, k)))
    sink_calls.clear()
    env2 = Env(tmp_path, monkeypatch, "ii_c")
    for i in range(3):
        env2.add_video(number=f"FC2-{6000001 + i}", focal_model="old")
    env2.fake.model = "model-A"
    env2.fake.on_cover = lambda n: setattr(env2.fake, "mode", "contract") if n == 1 else None
    # 第 1 張先成功再改 contract：讓 n==1 時改 mode 會影響「當下」這張
    # 改為：第 1 張就 contract
    env2.fake.mode = "contract"
    env2.fake.on_cover = None
    assert faces_recompute.ensure("model-A") is True
    _join_workers()
    st2 = faces_recompute.status()
    assert st2["stopped_reason"] == "contract"
    assert st2["kind"] == "contract"
    assert sink_calls == []

    # 模型 A→B：每列 focal_model 與焦點值與其產出者相符；有碼零請求
    _reset_state(monkeypatch)
    env3 = Env(tmp_path, monkeypatch, "ii_f")
    paths = [
        env3.add_video(number=f"FC2-{7000001 + i}", focal_model="old") for i in range(4)
    ]
    env3.add_video(number="SSIS-200", focal_model="old")  # 有碼
    env3.fake.model = "model-A"
    env3.fake.bias = "left"
    producers: dict[str, str] = {}

    def switch(n):
        # 記錄目前 model 為即將寫入的產出者；第 2 張後切 B
        if n == 2:
            env3.fake.model = "model-B"
            env3.fake.bias = "right"
            faces_recompute.ensure("model-B")  # 只更新 target，不另起 thread

    env3.fake.on_cover = switch
    assert faces_recompute.ensure("model-A") is True
    _join_workers()
    # 可能因 target 中途變 B 再跑一 pass；最終每列 focal_model ∈ {A,B}
    with closing(db_connection.get_connection(env3.db)) as conn:
        for p in paths:
            fm, af = conn.execute(
                "SELECT focal_model, auto_focal FROM videos WHERE path=?", (p,)
            ).fetchone()
            assert fm in ("model-A", "model-B")
            if fm == "model-A":
                assert af.startswith("0.2")  # 偏左
            else:
                assert af.startswith("0.8")  # 偏右
        # 有碼未動
        assert (
            conn.execute(
                "SELECT focal_model FROM videos WHERE number='SSIS-200'"
            ).fetchone()[0]
            == "old"
        )
    # 有碼片零請求：封面請求只來自 4 部無碼（A→B 可能重跑已寫 A 的列 → ≥4）
    assert env3.fake.covers >= 4
    # 有碼 SSIS-200 從未進候選 → 請求數不會無界膨脹到把有碼也算進去的程度
    assert env3.fake.covers <= 8  # 最多 A pass 4 + B pass 4


# ── (d) 刪除並重新對焦：先測後刪 ─────────────────────────────────────────────


def test_rebuild_test_failed_keeps_all_auto_focal(tmp_path, monkeypatch):
    """端點契約不符 → 一筆都不刪；改回正常 → 清空並重算；進行中 → already_running。"""
    from core.ai_services import faces_recompute

    env = Env(tmp_path, monkeypatch, "rb")
    for i in range(4):
        env.add_video(
            number=f"FC2-{8000001 + i}",
            auto_focal=f"0.5{i:03d},0.4000",
            focal_model="old-model",
        )
    before_count = env.count("auto_focal != ''")
    assert before_count == 4

    # 契約不符（empty faces → no_face）
    env.fake.mode = "contract"
    env.fake.model = "model-A"
    res = faces_recompute.start_rebuild()
    assert res["ok"] is False
    assert res["reason"] == "test_failed"
    assert res.get("kind") == "contract"
    assert env.count("auto_focal != ''") == before_count
    assert not _workers()

    # 改回正常 → 清空並開始重算
    env.fake.mode = "normal"
    env.fake.bias = "left"
    res = faces_recompute.start_rebuild()
    assert res["ok"] is True
    _join_workers()
    assert env.count("focal_model = ?", ("model-A",)) == 4
    # 重算後 auto_focal 非空（有臉）
    assert env.count("auto_focal != ''") == 4

    # 工作進行中 → already_running，一筆不動
    env2 = Env(tmp_path, monkeypatch, "rb2")
    for i in range(3):
        env2.add_video(number=f"FC2-{9000001 + i}", focal_model="old")
    entered, release = threading.Event(), threading.Event()

    def hold(n):
        if n == 1:
            entered.set()
            release.wait(10)

    env2.fake.model = "model-A"
    env2.fake.on_cover = hold
    assert faces_recompute.ensure("model-A") is True
    assert entered.wait(10)
    before = env2.count("auto_focal != ''")
    res = faces_recompute.start_rebuild()
    assert res["ok"] is False and res["reason"] == "already_running"
    assert env2.count("auto_focal != ''") == before
    release.set()
    _join_workers()
