"""Unit tests for TASK-195-T2: disk_label truth table + recheck throttle window."""

from __future__ import annotations

import asyncio
import contextlib
from unittest.mock import AsyncMock, patch

import pytest

from core.config import DirectoryConfig


def _reset_sr_module(sr) -> None:
    with sr._lock:
        sr._snapshot = {}
        sr._snapshot_at = sr._NEVER
        sr._in_flight = False
        sr._pending_exists.clear()
        sr._reprobe_task = None


@pytest.fixture
def sr():
    import core.source_reachability as mod

    _reset_sr_module(mod)
    yield mod
    task = mod._reprobe_task
    if task is not None and not task.done():
        task.cancel()
        with contextlib.suppress(Exception):
            asyncio.get_event_loop().run_until_complete(task)
    _reset_sr_module(mod)


@pytest.mark.parametrize(
    ("native", "expected"),
    [
        ("D:\\電影", "D:"),
        ("d:/FC2", "D:"),
        ("/Volumes/USB4T/電影", "USB4T"),
        ("\\\\NAS\\x", None),
        ("/mnt/nas", None),
    ],
)
def test_disk_label_truth_table(sr, native, expected) -> None:
    assert sr.disk_label(native) == expected


@pytest.mark.asyncio
async def test_recheck_throttle_window(sr) -> None:
    try:
        now = [1000.0]
        sources = [DirectoryConfig(path="/mnt/usb-a")]
        probe = AsyncMock(return_value="unreachable")
        with (
            patch.object(sr, "_now", new=lambda: now[0]),
            patch.object(sr, "load_config", return_value={"gallery": {}}),
            patch.object(sr, "iter_gallery_sources", return_value=sources),
            patch.object(sr, "_probe_one", probe),
        ):
            await sr.schedule_reprobe_if_stale()
            assert sr._in_flight is True
            await sr.wait_for_inflight_probe()
            assert probe.await_count == 1

            now[0] = 1003.0
            await sr.schedule_reprobe_if_stale(max_age=10.0)
            assert sr._in_flight is False
            await sr.wait_for_inflight_probe()
            assert probe.await_count == 1

            now[0] = 1011.0
            await sr.schedule_reprobe_if_stale(max_age=10.0)
            assert sr._in_flight is True
            await sr.wait_for_inflight_probe()
            assert probe.await_count == 2

            now[0] = 1022.0
            await asyncio.gather(
                sr.schedule_reprobe_if_stale(max_age=10.0),
                sr.schedule_reprobe_if_stale(max_age=10.0),
            )
            assert sr._in_flight is True
            await sr.wait_for_inflight_probe()
            assert probe.await_count == 3
    finally:
        _reset_sr_module(sr)
