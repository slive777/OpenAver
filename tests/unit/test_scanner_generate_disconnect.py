"""TASK-90b-T2: `/api/gallery/generate` 斷線偵測 cancel_event 生命週期單元測試。

spec-90 §90b(ii) + plan-90b.md CD-90b-5（已定案：方案 A，輪詢 task，見
plan-90b.md 記錄的 starlette==1.3.1 spike 實測結論）。

本檔**不**跑真 uvicorn（spike 已用真 uvicorn 驗證過斷線偵測可靠性，見
`feature/90-mediaserver-strm/TASK-90b-T2.md` 的「Spike 結果」段落）；這裡只
用 monkeypatch 假 `Request.is_disconnected` 驗證 `generate()` handler 建立的
`cancel_event` / watcher task 生命週期：
    1. 斷線路徑：cancel_event 在合理時間內被設置。
    2. 正常完成路徑：cancel_event 全程不被誤設，且 watcher task 正確被
       cancel + await（不留孤兒 task），對齊 CD-90b-5 追加 P2。

T2 範圍只到「cancel_event 建立 + 被正確設置」，尚未串進 generate_avlist（T3
才做），故本檔不驗證 generate_avlist 迴圈行為。
"""

import asyncio
import threading

import pytest

from web.routers.scanner import generate


class _FakeRequest:
    """假 Request，只提供 `generate()` handler 需要的 `is_disconnected()`。"""

    def __init__(self, disconnect_after: int | None):
        """`disconnect_after`：第幾次呼叫 `is_disconnected()` 起回傳 True。
        `None` 表示永遠回傳 False（模擬 client 全程未斷線）。
        """
        self._disconnect_after = disconnect_after
        self.call_count = 0

    async def is_disconnected(self) -> bool:
        self.call_count += 1
        if self._disconnect_after is None:
            return False
        return self.call_count >= self._disconnect_after


@pytest.mark.asyncio
async def test_cancel_event_set_on_disconnect():
    """斷線路徑：watcher task 應在合理時間內偵測到並 set cancel_event。"""
    fake_request = _FakeRequest(disconnect_after=1)

    response = await generate(fake_request)

    # cancel_event 必須是 threading.Event（非 asyncio.Event）——T3 要讓背景
    # daemon thread 跨 thread 讀取，誤用 asyncio.Event 是 blocker-class 錯誤。
    assert isinstance(response.cancel_event, threading.Event)

    # 輪詢間隔為 0.5s（見 scanner.py _DISCONNECT_POLL_INTERVAL_SEC）；
    # 給足 3 個輪詢週期的餘裕，避免測試在慢機器上 flaky。
    for _ in range(30):
        if response.cancel_event.is_set():
            break
        await asyncio.sleep(0.05)

    assert response.cancel_event.is_set() is True

    # 模擬 Starlette 於 response 傳輸結束後執行 BackgroundTask 收尾。
    await response.background()

    assert response.watcher_task.done() is True
    assert response.watcher_task.cancelled() is False  # 已經正常 return，非被 cancel 中斷


@pytest.mark.asyncio
async def test_cancel_event_not_set_when_no_disconnect():
    """正常完成路徑：全程未斷線時 cancel_event 不得被誤設，且 watcher task
    在 BackgroundTask 收尾後應被正確 cancel + await，無 dangling task。
    """
    fake_request = _FakeRequest(disconnect_after=None)

    response = await generate(fake_request)

    # 短暫等待，讓 watcher task 至少跑過一次輪詢迴圈（確認它真的活著在跑，
    # 而非一建立就意外结束）。
    await asyncio.sleep(0.1)
    assert response.cancel_event.is_set() is False
    assert response.watcher_task.done() is False

    # 模擬「串流正常跑完」：Starlette 呼叫 BackgroundTask 收尾。
    await response.background()

    # 正常完成路徑：cancel_event 全程不被誤設（驗收條件 2：零回歸）。
    assert response.cancel_event.is_set() is False
    # watcher task 必須已被 cancel + await，不留孤兒 task。
    assert response.watcher_task.done() is True
    assert response.watcher_task.cancelled() is True


@pytest.mark.asyncio
async def test_multiple_requests_have_independent_cancel_events():
    """多個並發 `/generate` 請求：cancel_event/watcher_task 各自獨立，不共享
    module-level 狀態（card 邊界條件：per-request 區域變數，非 global）。
    """
    request_a = _FakeRequest(disconnect_after=1)
    request_b = _FakeRequest(disconnect_after=None)

    response_a = await generate(request_a)
    response_b = await generate(request_b)

    assert response_a.cancel_event is not response_b.cancel_event
    assert response_a.watcher_task is not response_b.watcher_task

    for _ in range(30):
        if response_a.cancel_event.is_set():
            break
        await asyncio.sleep(0.05)

    assert response_a.cancel_event.is_set() is True
    assert response_b.cancel_event.is_set() is False

    await response_a.background()
    await response_b.background()

    assert response_a.watcher_task.done() is True
    assert response_b.watcher_task.done() is True
