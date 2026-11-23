"""CD-166-1: lifespan 到 yield 的耗時不含任何 NAS／區網／外網 I/O 的等待。

案 (a)：metatube 關閉、DB 有唯讀列、NAS 路徑丟包（回填那一側）。
案 (b)：DB 零列、metatube 開啟、list_providers 丟包（重連那一側）。
兩案各自只擋一個違例，紅燈才分辨得出是誰造成。
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import pathlib
import socket
import threading
import time
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import core.database.connection as db_conn
import core.source_reachability as sr
from core.database.connection import init_db
from core.database.video import Video, VideoRepository
from core.metatube.state import metatube_state
from core.path_utils import to_file_uri
from web.app import app, lifespan

BLACKHOLE = "/srv/blackhole-nas"
MAX_READY_SECONDS = 2.0


@pytest.fixture(autouse=True)
def _reset_singletons():
    """metatube state 與 app.state 的兩個背景 task 屬性是進程單例，前後都清。"""
    def _clean():
        metatube_state.disconnect()
        for name in ("nfo_backfill_task", "metatube_reconnect_task"):
            with contextlib.suppress(AttributeError, KeyError):
                delattr(app.state, name)
    _clean()
    yield
    _clean()


@pytest.fixture
def base_env(tmp_path, monkeypatch, temp_config_path):
    """tmp DB ＋ tmp config ＋ 與本不變式無關的鄰居 mock。"""
    db_path = tmp_path / "t.db"
    init_db(db_path)
    monkeypatch.setattr(db_conn, "get_db_path", lambda: db_path)
    monkeypatch.setattr("core.access_auth.get_db_path", lambda: tmp_path / "access.db")
    monkeypatch.setattr("web.app.init_db", lambda *a, **kw: None)
    monkeypatch.setattr("web.app.ensure_schema", lambda *a, **kw: None)
    monkeypatch.setattr("web.app.start_notification_persistence", lambda *a, **kw: None)
    monkeypatch.setattr("web.app._startup_update_check", AsyncMock())
    monkeypatch.setattr("web.app._periodic_update_check_loop", AsyncMock())
    monkeypatch.setattr("web.app.auto_organize_loop", AsyncMock())
    with sr._lock:
        sr._snapshot, sr._snapshot_at, sr._in_flight = {}, sr._NEVER, False
        sr._pending_exists.clear()
        sr._reprobe_task = None
    return db_path, temp_config_path


def _write_cfg(cfg_path, *, metatube=None, directories=None):
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    if metatube is not None:
        cfg["metatube"] = metatube
    if directories is not None:
        cfg.setdefault("gallery", {})["directories"] = directories
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")


def _seed_rows(db_path):
    repo = VideoRepository(db_path)
    for i in range(40):
        for kind, od in (("ro", "/mnt/out"), ("gen", "")):
            cover = to_file_uri(f"{BLACKHOLE}/{kind}/V-{i:03d}.jpg", {})
            repo.upsert(Video(path=to_file_uri(f"{BLACKHOLE}/{kind}/V-{i:03d}.mp4", {}),
                              number=f"V-{i:03d}", title="t", cover_path=cover,
                              output_dir=od, nfo_mtime=0.0))


def _skip_backfill(monkeypatch):
    # raising=False：改前 web.app 尚無此名字，RED 才會紅在斷言而非 AttributeError。
    monkeypatch.setattr("web.app.backfill_readonly_nfo_mtime_once",
                        lambda *a, **kw: None, raising=False)


def _blackhole_exists(monkeypatch, gate, seen=None):
    real_exists = pathlib.Path.exists

    def fake_exists(self, *a, **kw):
        if str(self).startswith(BLACKHOLE):
            if seen is not None:
                seen["backfill"] = threading.current_thread()
                seen["backfill_ev"].set()
            gate.wait(0.25)
            return False
        return real_exists(self, *a, **kw)

    monkeypatch.setattr(pathlib.Path, "exists", fake_exists)


def _blackhole_metatube(monkeypatch, gate, seen=None):
    from web.routers.settings_metatube import MetatubeError

    def fake_list_providers(self):
        if seen is not None:
            seen["reconnect"] = threading.current_thread()
            seen["reconnect_ev"].set()
        gate.wait(10)
        raise MetatubeError("blackhole")

    def fake_create_connection(*a, **kw):
        gate.wait(10)
        raise TimeoutError("blackhole")

    monkeypatch.setattr("web.routers.settings_metatube.MetatubeHttpClient.list_providers",
                        fake_list_providers)
    monkeypatch.setattr(socket, "create_connection", fake_create_connection)


async def _measure_ready(gate, injected=None):
    t0 = time.perf_counter()
    cm = lifespan(app)
    try:
        await asyncio.wait_for(cm.__aenter__(), timeout=5)
        elapsed = time.perf_counter() - t0
        if injected is not None:
            # yield 之後、離場取消背景 task 之前，確認注入點真的被進入過（不能空過）。
            assert await asyncio.to_thread(injected.wait, 5), "blackhole injection never reached"
        return elapsed
    finally:
        gate.set()
        with contextlib.suppress(BaseException):
            await cm.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_lifespan_ready_case_a_backfill(base_env, monkeypatch):
    db_path, cfg_path = base_env
    _write_cfg(cfg_path, metatube={"enabled": False, "url": "", "token": ""})
    _seed_rows(db_path)
    gate = threading.Event()
    seen = {"backfill_ev": threading.Event()}
    _blackhole_exists(monkeypatch, gate, seen)
    elapsed = await _measure_ready(gate, injected=seen["backfill_ev"])
    assert elapsed <= MAX_READY_SECONDS, f"lifespan took {elapsed:.2f}s to reach yield"


@pytest.mark.asyncio
async def test_lifespan_ready_case_b_metatube(base_env, monkeypatch):
    _, cfg_path = base_env
    _write_cfg(cfg_path, metatube={"enabled": True, "url": "http://8.8.8.8:8080", "token": "t"})
    _skip_backfill(monkeypatch)
    gate = threading.Event()
    _blackhole_metatube(monkeypatch, gate)
    elapsed = await _measure_ready(gate)
    assert elapsed <= MAX_READY_SECONDS, f"lifespan took {elapsed:.2f}s to reach yield"


async def _await_reconnect_task():
    task = getattr(app.state, "metatube_reconnect_task", None)
    assert task is not None, "app.state.metatube_reconnect_task is missing"
    _done, pending = await asyncio.wait({task}, timeout=5)
    assert not pending, "metatube_reconnect_task did not finish within 5s"


def test_startup_reconnect_success_reflected_in_status(base_env, monkeypatch):
    """§4.4 特徵測試：重連成功 → /status connected 且 providers 與 mock 一致。"""
    _, cfg_path = base_env
    _write_cfg(cfg_path, metatube={"enabled": True, "url": "http://8.8.8.8:8080", "token": "t"})
    _skip_backfill(monkeypatch)
    providers = {"SOD": "http://mt:8080", "KIN8": "http://mt:8080"}
    monkeypatch.setattr("web.routers.settings_metatube.MetatubeHttpClient.list_providers",
                        lambda self: providers)
    probed = threading.Event()
    monkeypatch.setattr("web.app._fire_probe", lambda *a, **kw: probed.set())
    with TestClient(app) as client:
        assert probed.wait(5), "_fire_probe was never called"
        data = client.get("/api/settings/metatube/status").json()
    assert data["connected"] is True
    assert sorted(p["id"] for p in data["providers"]) == sorted(f"metatube:{n}" for n in providers)


@pytest.mark.asyncio
async def test_lifespan_primes_and_migrates_before_any_background_work(
    base_env, monkeypatch
):
    """TASK-206a-T3 (f)：prime／migrate 先於 writer 與各背景協程入口。"""
    import web.app as web_app

    order = []
    monkeypatch.setattr("web.app.init_db", lambda *a, **kw: None)
    monkeypatch.setattr("web.app.seed_builtin_aliases", lambda *a, **kw: None)
    monkeypatch.setattr(
        "web.app.media_probe.log_unavailable_once", lambda *a, **kw: None
    )
    monkeypatch.setattr(
        web_app, "prime_secret_store", lambda *a, **kw: order.append("prime"), raising=False
    )
    monkeypatch.setattr(
        web_app, "migrate_config_secrets", lambda *a, **kw: order.append("migrate"), raising=False
    )
    monkeypatch.setattr(
        web_app,
        "start_notification_persistence",
        lambda *a, **kw: order.append("writer"),
    )
    monkeypatch.setattr(
        "web.app.source_reachability.schedule_reprobe_if_stale", AsyncMock()
    )

    real_create_task = asyncio.create_task

    def _spy_create_task(coro, **kwargs):
        name = getattr(coro, "__name__", type(coro).__name__)
        order.append(f"task:{name}")
        coro.close()
        fut = real_create_task(asyncio.sleep(0))
        return fut

    monkeypatch.setattr(asyncio, "create_task", _spy_create_task)
    cm = lifespan(app)
    try:
        await asyncio.wait_for(cm.__aenter__(), timeout=5)
    finally:
        with contextlib.suppress(BaseException):
            await cm.__aexit__(None, None, None)
    assert order.index("prime") < order.index("migrate")
    background = [e for e in order if e == "writer" or e.startswith("task:")]
    assert background, "no background work observed"
    assert order.index("migrate") < min(order.index(e) for e in background)


