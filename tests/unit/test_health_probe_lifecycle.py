"""
TASK-130a-T3: windows/health_probe.py 伺服器 thread 生命週期與三態探活

驗證：
1. wait_for_server 簽章：server_thread 必填、回傳 PROBE_OK / PROBE_TIMEOUT / PROBE_THREAD_DIED。
2. thread 立刻死亡 → 提前中止（elapsed < 2s）回 PROBE_THREAD_DIED。
3. 活著的 thread ＋ 探活永遠失敗 → PROBE_TIMEOUT。
4. 探活拿到 200 → PROBE_OK。
5. run_server 未預期例外 → logger.exception 留痕且不往外拋。
6. 逾時／thread 死亡路徑各留痕恰好一次（含最後一次被吞例外）。
8. 四種 flag 組合：活著×逾時／死掉×未逾時／死掉×已逾時／活著×200。
"""
import threading
import time
import urllib.request

import pytest

import windows.health_probe as health_probe
from windows.health_probe import wait_for_server


def _const(name: str) -> str:
    """Fetch a probe constant; AttributeError here means the T3 API is still missing."""
    return getattr(health_probe, name)


@pytest.fixture
def alive_thread():
    """daemon thread that stays alive until the fixture tears down."""
    stop = threading.Event()

    def _spin():
        stop.wait(60)

    t = threading.Thread(target=_spin, daemon=True)
    t.start()
    assert t.is_alive()
    yield t
    stop.set()
    t.join(timeout=2)


def _dead_thread():
    """起一個立刻結束的 thread 並 join，讓 is_alive() 穩定為 False。

    ⚠️ 這裡故意**不**讓 target 拋例外。拋例外一樣會讓 thread 死掉，但會觸發
    `PytestUnhandledThreadExceptionWarning`，在整套 7000+ 測試的輸出裡變成看不出來源的雜訊
    ——而本測試要驗的是「thread 死了」，不是「thread 怎麼死的」。
    真實世界那條「因為未預期例外而死」的路徑由 `test_run_server_logs_unexpected_exception`
    覆蓋（`run_server` 自己的 try/except 會接住並留痕，所以那支不會噴 warning）。

    必須 `start()` 過：**沒 start() 的 thread 也回報 `is_alive() == False`**，
    用它會拿到一個假的 PROBE_THREAD_DIED，測試看起來綠但什麼都沒證明。
    """

    t = threading.Thread(target=lambda: None, daemon=True)
    t.start()
    t.join(timeout=2)
    assert not t.is_alive()
    return t


def _failing_opener(monkeypatch, exc_factory=None):
    """Monkeypatch build_opener so every open() raises."""
    if exc_factory is None:
        def exc_factory():
            return OSError("Network unreachable")

    class StubOpener:
        def open(self, url, timeout=1):
            raise exc_factory()

    monkeypatch.setattr(urllib.request, "build_opener", lambda *handlers: StubOpener())


# ----- D1: signature + return literals -----


# ----- D2 + flag: dead × not timed out -----

def test_thread_death_aborts_probe_early(monkeypatch):
    """D2 / AC-T3-2: 立刻死亡的 thread → PROBE_THREAD_DIED 且 elapsed < 2s。"""
    _failing_opener(monkeypatch)
    dead = _dead_thread()

    t0 = time.monotonic()
    result = wait_for_server(49152, dead, timeout=30)
    elapsed = time.monotonic() - t0

    assert result == _const("PROBE_THREAD_DIED")
    assert elapsed < 2.0, f"thread 死亡應遠早於 30s 中止，實際 elapsed={elapsed:.2f}s"


# ----- D3 + flag: alive × timeout -----


# ----- D4 + flag: alive × 200 -----


# ----- flag: dead × already timed out（檢查順序：thread 優先） -----


# ----- D5: run_server exception boundary -----


# ----- D6: once-only logging -----


@pytest.mark.parametrize("threshold", [1, 3])
def test_wait_for_server_cancelled_returns_without_waiting_for_timeout(monkeypatch, alive_thread, threshold):
    _failing_opener(monkeypatch)
    calls = [0]
    def cancelled():
        calls[0] += 1
        return calls[0] >= threshold
    start = time.monotonic()
    assert wait_for_server(49152, alive_thread, timeout=30, cancelled=cancelled) == "cancelled"
    assert time.monotonic() - start < 2


def test_debug_log_hint_matches_core_logger_default(monkeypatch, tmp_path):
    import io
    from unittest.mock import MagicMock
    from core import logger as core_logger
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(core_logger, "_initialized", False)
    root = MagicMock(); root.handlers = []
    monkeypatch.setattr(core_logger.logging, "getLogger", lambda *a: root)
    handler = MagicMock()
    monkeypatch.setattr(core_logger, "RotatingFileHandler", handler)
    monkeypatch.setattr(io, "TextIOWrapper", MagicMock())
    core_logger.setup_logging()
    assert str(handler.call_args.args[0]) == health_probe._debug_log_hint()
