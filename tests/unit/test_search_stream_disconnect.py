"""TASK-204-T1：串流離開即時收尾（I-A1／I-A2／I-A5／I-A8）。

直接呼叫公開入口 search_stream，不經 TestClient（BE-TEST-54）。
"""
import asyncio
import json
import threading
import time

import pytest

import core.search_cancel as search_cancel
from web.routers import search as search_module


@pytest.fixture(autouse=True)
def _fixed_mode(monkeypatch):
    monkeypatch.setattr(search_module, "_detect_mode", lambda q, resolve=False: "exact")


def _parse(raw: str) -> dict:
    assert raw.startswith("data: ")
    return json.loads(raw[len("data: "):].strip())


async def _open_stream():
    resp = await search_module.search_stream(
        q="AB-12", limit=20, offset=0, maker_key=None, maker=None,
        spellings=None, cursor=None,
    )
    return resp.body_iterator


def _blocking_stub(started, release, holder, captured):
    def stub(q, limit=20, offset=0, status_callback=None, **kwargs):
        holder["thread"] = threading.current_thread()
        if status_callback is not None:
            captured["cb"] = status_callback
        started.set()
        if status_callback is not None:
            status_callback("javbus", "searching")
        release.wait(10)
        return []
    return stub


@pytest.mark.asyncio
@pytest.mark.parametrize("leave", ["cancelled_at_sleep", "aclose_at_yield", "encode_error_break"])
async def test_stream_exit_does_not_block_event_loop(monkeypatch, leave):
    started = threading.Event()
    release = threading.Event()
    holder = {}
    captured = {}
    monkeypatch.setattr(search_module, "smart_search", _blocking_stub(started, release, holder, captured))
    gen = await _open_stream()
    worker = None
    try:
        first = _parse(await anext(gen))
        assert first["type"] == "mode"
        second = _parse(await anext(gen))
        assert second["type"] == "status"
        assert started.is_set()
        worker = holder["thread"]
        assert worker.is_alive()
        if leave == "cancelled_at_sleep":
            task = asyncio.create_task(anext(gen))
            await asyncio.sleep(0.15)
            begin = time.monotonic()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            spent = time.monotonic() - begin
            assert spent < 0.5, f"收尾耗時 {spent:.2f}s ≥0.5s：事件迴圈被舊搜尋工作緒拖住"
        elif leave == "aclose_at_yield":
            begin = time.monotonic()
            await gen.aclose()
            spent = time.monotonic() - begin
            assert spent < 0.5, f"收尾耗時 {spent:.2f}s ≥0.5s：事件迴圈被舊搜尋工作緒拖住"
        else:
            captured["cb"]("javbus", object())
            begin = time.monotonic()
            third = _parse(await anext(gen))
            spent = time.monotonic() - begin
            assert spent < 0.5, f"收尾耗時 {spent:.2f}s ≥0.5s：事件迴圈被舊搜尋工作緒拖住"
            assert third["type"] == "error"
            with pytest.raises(StopAsyncIteration):
                await anext(gen)
            total = time.monotonic() - begin
            assert total < 0.5, f"收尾耗時 {total:.2f}s ≥0.5s：事件迴圈被舊搜尋工作緒拖住"
            assert not release.is_set()
            assert worker.is_alive()
    finally:
        release.set()
        if worker is not None:
            worker.join(timeout=5)
    assert search_cancel.current() is None


@pytest.mark.asyncio
async def test_stream_exit_sets_cancel_flag_for_worker(monkeypatch):
    started = threading.Event()
    release = threading.Event()
    holder = {}

    def stub(q, limit=20, offset=0, status_callback=None, **kwargs):
        holder["event"] = search_cancel.current()
        holder["thread"] = threading.current_thread()
        started.set()
        if status_callback is not None:
            status_callback("javbus", "searching")
        event = holder["event"]
        if event is not None:
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                if event.is_set():
                    holder["saw_set"] = True
                    break
                time.sleep(0.05)
        release.wait(10)
        return []

    monkeypatch.setattr(search_module, "smart_search", stub)
    gen = await _open_stream()
    worker = None
    try:
        first = _parse(await anext(gen))
        assert first["type"] == "mode"
        second = _parse(await anext(gen))
        assert second["type"] == "status"
        assert started.is_set()
        worker = holder["thread"]
        assert worker.is_alive()
        assert holder["event"] is not None, "run_search 未以 search_cancel.bound 綁定旗標"
        begin = time.monotonic()
        await gen.aclose()
        spent = time.monotonic() - begin
        assert spent < 0.5, f"收尾耗時 {spent:.2f}s ≥0.5s：事件迴圈被舊搜尋工作緒拖住"
        deadline = time.monotonic() + 1.0
        while not holder.get("saw_set") and time.monotonic() < deadline:
            await asyncio.sleep(0.05)
        assert holder.get("saw_set") is True, "串流離開後工作緒未在 1 秒內看到旗標"
    finally:
        release.set()
        if worker is not None:
            worker.join(timeout=5)
