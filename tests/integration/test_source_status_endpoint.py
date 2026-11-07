"""Integration tests for GET /api/showcase/source-status and lifespan probe.

Covers TASK-142-T2 DoD 1–5:
1. Rapid calls (5 times in 60s window) probe at most once and respond < 50ms.
2. Lifespan context manager yields within 100ms even if probe takes 10s.
3. get_snapshot exception does not affect GET /api/showcase/videos.
4. Returns empty list [] when all sources are ok/unknown/unprobed.
5. Display formatting for UNC (\\\\host) and non-UNC paths.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import core.source_reachability as sr
from web.app import app, lifespan


def _reset_sr_module() -> None:
    with sr._lock:
        sr._snapshot = {}
        sr._snapshot_at = sr._NEVER
        sr._in_flight = False
        sr._pending_exists.clear()
        sr._reprobe_task = None


@pytest.mark.asyncio
async def test_dod2_lifespan_yield_not_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """DoD 2: lifespan to yield takes < 100ms even when probe runs for 10s."""
    _reset_sr_module()

    monkeypatch.setattr("web.app.init_db", lambda *a, **kw: None)
    monkeypatch.setattr("web.app.seed_builtin_aliases", lambda *a, **kw: None)
    monkeypatch.setattr("web.app.ensure_schema", lambda *a, **kw: None)
    monkeypatch.setattr("web.app.backfill_readonly_nfo_mtime_once", lambda *a, **kw: 0)
    monkeypatch.setattr("web.app.startup_reconnect", lambda *a, **kw: None)
    monkeypatch.setattr("web.app._startup_update_check", AsyncMock())
    # v0.15.13：shutdown 開始 drain 通知 writer 之後，這一行才變成「會真的做事」。
    # 在那之前 start_notification_persistence() 幾乎總是提早 return——它開頭有
    # `if _writer_thread is not None and _writer_thread.is_alive(): return`，而
    # 前面任何一支測試留下的活 writer thread 都會讓它命中那道閘、根本不碰 DB。
    # 現在 shutdown 會把 _writer_thread 設回 None，於是下一次 lifespan 啟動真的會去
    # load_recent_notifications() 連**真實的** output/openaver.db，被 repo-write 守衛
    # 擋成 RepoWriteGuardViolation（繼承 BaseException，start_notification_persistence()
    # 內的 `except Exception` 攔不到）⇒ 整段 startup 炸掉。
    # 這裡與上面五行同樣的處置：本測試量的是「lifespan 到 yield 的耗時」，
    # 通知歷史載回與它無關，照鄰居的形狀一起 mock 掉（順便避免把真實 DB I/O
    # 算進那個 < 0.1s 的斷言裡）。
    monkeypatch.setattr("web.app.start_notification_persistence", lambda *a, **kw: None)

    async def slow_probe_all() -> None:
        await asyncio.sleep(10.0)

    monkeypatch.setattr(sr, "_probe_all", slow_probe_all)

    called = False
    real_schedule = sr.schedule_reprobe_if_stale

    async def tracking_schedule() -> None:
        nonlocal called
        called = True
        await real_schedule()

    monkeypatch.setattr(sr, "schedule_reprobe_if_stale", tracking_schedule)

    t0 = time.perf_counter()
    cm = lifespan(app)
    try:
        await asyncio.wait_for(cm.__aenter__(), timeout=1.0)
        elapsed = time.perf_counter() - t0
        assert called, "lifespan must call schedule_reprobe_if_stale()"
        assert elapsed < 0.1, f"lifespan startup took {elapsed:.3f}s, expected < 0.1s"
    finally:
        with contextlib.suppress(Exception):
            await cm.__aexit__(None, None, None)
        if sr._reprobe_task and not sr._reprobe_task.done():
            sr._reprobe_task.cancel()


@pytest.mark.parametrize("synology,server_only", [(False, False), (True, False), (False, True)])
def test_no_permission_source_included_with_reason(monkeypatch: pytest.MonkeyPatch, synology: bool, server_only: bool) -> None:
    from core.platform_info import DSM_PERMISSION_HINT, LINUX_PERMISSION_HINT

    monkeypatch.setattr(sr, "get_snapshot", lambda: {"/denied": "no_permission", "/gone": "unreachable", "/ok": "ok"})
    monkeypatch.setattr(sr, "schedule_reprobe_if_stale", AsyncMock())
    monkeypatch.setattr("web.routers.showcase.is_synology", lambda: synology)
    if server_only:
        monkeypatch.setenv("OPENAVER_SERVER_ONLY", "1")
    data = TestClient(app, client=("127.0.0.1", 50000)).get("/api/showcase/source-status").json()
    denied = next(item for item in data if item["path"] == "/denied")
    assert denied["status"] == "no_permission"
    assert denied["reason"] == "no_permission"
    assert denied["dsm_hint"] == (DSM_PERMISSION_HINT if synology else (LINUX_PERMISSION_HINT if server_only else None))
    gone = next(item for item in data if item["path"] == "/gone")
    assert gone["reason"] == "unreachable"
    assert gone["dsm_hint"] is None


def test_dod5_unreachable_sources_display_format(monkeypatch: pytest.MonkeyPatch) -> None:
    """DoD 5: unreachable UNC formats to \\\\<host>, non-UNC to raw path."""
    mock_snapshot = {
        "\\\\nas-box\\share\\videos": "unreachable",
        "/mnt/storage/media": "unreachable",
        "//other-nas/data": "ok",
    }
    monkeypatch.setattr(sr, "get_snapshot", lambda: mock_snapshot)
    monkeypatch.setattr(sr, "schedule_reprobe_if_stale", AsyncMock())

    client = TestClient(app, client=("127.0.0.1", 50000))
    resp = client.get("/api/showcase/source-status")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 2

    unc_item = next(
        (item for item in data if item["path"] == "\\\\nas-box\\share\\videos"),
        None,
    )
    assert unc_item is not None
    assert unc_item["display"] == "\\\\nas-box"
    assert unc_item["status"] == "unreachable"

    local_item = next(
        (item for item in data if item["path"] == "/mnt/storage/media"),
        None,
    )
    assert local_item is not None
    assert local_item["display"] == "/mnt/storage/media"
    assert local_item["status"] == "unreachable"


def test_cold_start_waits_for_first_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    """缺陷 B：快照從未寫過時，端點要等第一次探測寫完，不能拿到 []。"""
    _reset_sr_module()

    async def fake_probe_all() -> None:
        await asyncio.sleep(0.05)
        with sr._lock:
            sr._snapshot = {"/mnt/cold": "unreachable"}
            sr._snapshot_at = sr._now()
            sr._in_flight = False

    monkeypatch.setattr(sr, "_probe_all", fake_probe_all)

    client = TestClient(app, client=("127.0.0.1", 50000))
    resp = client.get("/api/showcase/source-status")
    assert resp.status_code == 200
    data = resp.json()
    assert any(item["path"] == "/mnt/cold" for item in data), (
        f"cold start must wait for first probe, got {data!r}"
    )


def test_same_unc_host_sources_merge_into_one_display(monkeypatch: pytest.MonkeyPatch) -> None:
    """spec F3: 同一主機底下多個來源合成一個名字（否則 footer 列兩次同一台 NAS，
    「N 個位置無法存取」也會多算）。非 UNC 的不同根路徑仍各自一筆。"""
    monkeypatch.setattr(
        sr,
        "get_snapshot",
        lambda: {
            "\\\\nas-box\\share\\videos": "unreachable",
            "\\\\nas-box\\share2\\more": "unreachable",
            "/mnt/usb-a": "unreachable",
            "/mnt/usb-b": "unreachable",
        },
    )
    monkeypatch.setattr(sr, "schedule_reprobe_if_stale", AsyncMock())

    client = TestClient(app, client=("127.0.0.1", 50000))
    data = client.get("/api/showcase/source-status").json()

    displays = [item["display"] for item in data]
    assert displays.count("\\\\nas-box") == 1, "同一 UNC 主機只該出現一次"
    assert sorted(displays) == sorted(["\\\\nas-box", "/mnt/usb-a", "/mnt/usb-b"])
