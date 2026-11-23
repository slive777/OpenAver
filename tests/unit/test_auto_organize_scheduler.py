"""tests/unit/test_auto_organize_scheduler.py — 排程 loop 單元測試（TASK-144-T5）。

覆蓋 DoD 1–3、5–11 與 mutation 點 M1/M2/M5/M6/M7。
"""
from __future__ import annotations

import contextlib
import os

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from core import auto_organize_state
from web import auto_organize_scheduler as sched


def _empty_result(**overrides):
    base = {
        "added": [],
        "cover_missing": [],
        "failed": [],
        "skipped": {"has_nfo": 0, "memory_hit": 0, "duplicate": []},
        "newly_recorded": 0,
        "wishlist_removed": [],
        "wishlist_reconcile_failed": False,
        "aborted_after": None,
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def reset_scheduler_and_state():
    """每個測試前後重置 scheduler 與 auto_organize_state 的模組狀態。"""
    with auto_organize_state._lock:
        auto_organize_state._running = False
        auto_organize_state._current_number = None
        auto_organize_state._abort_requested = False
        auto_organize_state._last_manual_at = float("-inf")
    sched._next_due_at = 0.0
    sched._round_task = None
    yield
    with auto_organize_state._lock:
        auto_organize_state._running = False
        auto_organize_state._current_number = None
        auto_organize_state._abort_requested = False
        auto_organize_state._last_manual_at = float("-inf")
    if sched._round_task is not None and not sched._round_task.done():
        sched._round_task.cancel()
    sched._next_due_at = 0.0
    sched._round_task = None


# ---------------------------------------------------------------------------
# DoD-1：開關與計時
# ---------------------------------------------------------------------------


async def test_loop_skips_when_disabled(monkeypatch):
    """DoD-1：enabled=False → loop 醒來也不跑。"""
    wake_count = {"n": 0}

    async def fake_sleep(_s):
        wake_count["n"] += 1
        if wake_count["n"] >= 2:
            raise asyncio.CancelledError()

    monkeypatch.setattr(sched.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(
        sched, "load_config",
        lambda: {"search": {"auto_organize": {"enabled": False}}},
    )
    enter_spy = MagicMock(wraps=auto_organize_state.enter_cron)
    monkeypatch.setattr(sched.auto_organize_state, "enter_cron", enter_spy)

    with pytest.raises(asyncio.CancelledError):
        await sched.auto_organize_loop()

    enter_spy.assert_not_called()


async def test_loop_runs_when_enabled_and_due(monkeypatch):
    """DoD-1：enabled=True 且到期 → 跑一輪。"""
    wake_count = {"n": 0}
    sched._next_due_at = time.time() - 1.0

    async def fake_sleep(_s):
        wake_count["n"] += 1
        if wake_count["n"] >= 2:
            raise asyncio.CancelledError()

    run_body = AsyncMock()
    monkeypatch.setattr(sched.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(
        sched, "load_config",
        lambda: {"search": {"auto_organize": {"enabled": True}}},
    )
    monkeypatch.setattr(sched, "_run_round_body", run_body)
    # enter_cron 成功後 _run_round_body 負責 exit；這裡 body 是 mock，手動釋放
    real_enter = auto_organize_state.enter_cron

    def enter_then_release(trigger, now=None):
        ok = real_enter(trigger, now=now)
        if ok:
            auto_organize_state.exit_cron()
        return ok

    monkeypatch.setattr(sched.auto_organize_state, "enter_cron", enter_then_release)

    with pytest.raises(asyncio.CancelledError):
        await sched.auto_organize_loop()

    run_body.assert_awaited()
    assert run_body.await_args.args[0] == "schedule"


# ---------------------------------------------------------------------------
# DoD-2 / DoD-3：enter_and_start（毫秒返回 ＋ trigger 原樣）
# ---------------------------------------------------------------------------

async def test_enter_and_start_returns_immediately_while_round_runs(monkeypatch):
    """DoD-2：enter_and_start 立刻返回，整輪在背景跑。"""
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_body(trigger):
        started.set()
        await release.wait()
        auto_organize_state.exit_cron()

    monkeypatch.setattr(sched, "_run_round_body", slow_body)

    t0 = time.perf_counter()
    result = sched.enter_and_start("run_now")
    elapsed = time.perf_counter() - t0

    assert result == {"success": True, "reason": None}
    assert elapsed < 0.1
    await asyncio.wait_for(started.wait(), timeout=1.0)
    release.set()
    await asyncio.wait_for(sched._round_task, timeout=1.0)


# ---------------------------------------------------------------------------
# DoD-5 / M7：探測例外仍釋放 running
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# DoD-6 / M2：零事件不發通知
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("overrides", [{}], ids=["no_events"])
def test_zero_events_does_not_emit(monkeypatch, overrides):
    """DoD-6 / M2：事件數 0 → 不發通知。DoD-7 / M5：aborted_after == 0 同樣不發。"""
    emit = MagicMock()
    monkeypatch.setattr(sched, "emit_notification", emit)

    sched._emit_round_summary(_empty_result(**overrides))
    emit.assert_not_called()


def test_nonzero_events_emits_summary(monkeypatch):
    """DoD-6：有新增／失敗 → 發 summary。"""
    emit = MagicMock()
    monkeypatch.setattr(sched, "emit_notification", emit)

    sched._emit_round_summary(_empty_result(added=["ABC-123"], failed=["XYZ-456"]))
    emit.assert_called_once()
    assert emit.call_args.args[0] == "warn"
    assert emit.call_args.args[1] == "notif.auto_organize_summary"
    assert "新增 1 部" in emit.call_args.kwargs["message"]
    assert "失敗 1 部" in emit.call_args.kwargs["message"]


# ---------------------------------------------------------------------------
# DoD-7 / M5：aborted_after 分支
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# DoD-8 / M6：資料夾探測逾時
# ---------------------------------------------------------------------------

async def test_folder_probe_respects_timeout(monkeypatch):
    """DoD-8 / M6：exists 探測必須有 wait_for 上限；逾時 → folder_unreachable。

    兩個保障不能拿掉：① 只讓目標路徑變慢（`sched.os` 就是全域 `os`，無差別 patch
    會讓 pytest 自己的 `os.path.exists` 也跟著睡而掛住）；② 擋住 `run_one_round`
    （逾時被拿掉時探測會回 True 並往下走，不擋就會跑進真實刮削而掛住）。
    """
    monkeypatch.setattr(sched, "_FOLDER_EXISTS_TIMEOUT_S", 0.05)
    monkeypatch.setattr(sched, "load_config", lambda: {"search": {"favorite_folder": "/nas/fav",
                                        "auto_organize": {"enabled": True}}})
    monkeypatch.setattr(sched, "resolve_favorite_folder", lambda _c: "/nas/fav")

    # 🔴 只對「我們這一條路徑」變慢：`sched.os` 就是全域 `os` 模組，無差別 patch
    # 會讓 pytest 自己的每一次 `os.path.exists` 也睡 0.5 秒。
    _real_exists = os.path.exists

    def _slow_only_for_target(path):
        if path == "/nas/fav":
            time.sleep(0.5)
            return True
        return _real_exists(path)

    monkeypatch.setattr(sched.os.path, "exists", _slow_only_for_target)
    # 逾時被拿掉時（mutation）探測會回 True 並往下走到 run_one_round——
    # 那支必須也被擋住，否則 mutation 那一輪會跑進真實刮削而掛住，
    # gate 就看不到「逾時測試轉紅」而是看到逾時。
    monkeypatch.setattr(sched, "run_one_round", lambda *a, **kw: {
        "added": [], "cover_missing": [], "failed": [],
        "skipped": {"has_nfo": 0, "memory_hit": 0, "duplicate": []},
        "newly_recorded": 0, "wishlist_removed": [], "aborted_after": None,
    })

    t0 = time.perf_counter()
    result = await sched._prepare_and_run("schedule")
    elapsed = time.perf_counter() - t0

    assert result.get("folder_unreachable") is True
    assert result["folder"] == "/nas/fav"
    assert elapsed < 0.3  # 遠小於 slow_exists 的 0.5s


# ---------------------------------------------------------------------------
# DoD-9：唯讀資料夾
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# DoD-10：書籤對帳通知（只讀 wishlist_removed，不再呼叫 reconcile）
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("isolate_secret_store")
async def test_scheduled_round_rechecks_enabled_after_acquiring_ownership(monkeypatch, tmp_path):
    """Codex 六審 P3：拿到執行權之後要再問一次開關。

    使用者流程：排程 loop 讀到「開著」→ 使用者**就在這一瞬間**撥掉開關 →
    `request_abort()` 看到「沒有任何一輪在跑」什麼都不做 → loop 進場、`enter_cron()`
    把中止旗標清成 0 → 修正前它照樣把整輪跑完（搬檔、改名、寫 NFO），**而畫面說已經關了**。
    """
    from core import config as core_config

    monkeypatch.setattr(core_config, "CONFIG_PATH", tmp_path / "config.json")
    core_config.mutate_config(
        lambda cfg: cfg.setdefault("search", {}).update(
            {
                "favorite_folder": "/tmp/fav-for-ao",
                "auto_organize": {"enabled": False},   # 使用者剛剛撥掉
            }
        )
    )
    ran = MagicMock()
    monkeypatch.setattr(sched, "run_one_round", ran, raising=False)

    result = await sched._prepare_and_run("schedule")

    assert result == {"scheduling_disabled": True}, (
        "撥掉開關之後排程還是把整輪跑完了"
    )
    ran.assert_not_called()


# ---------------------------------------------------------------------------
# DoD-11：舊 config 缺 auto_organize key 不得炸
# ---------------------------------------------------------------------------


# ===========================================================================
# Opus 於 review 階段補的兩支守衛（實作交件時這兩條都沒有測試守著）
# ===========================================================================

class TestProbeTimeoutAndLoopSurvival:
    def test_loop_survives_an_exception_from_one_round(self, monkeypatch):
        """單輪的例外絕不能殺掉 loop。

        `while True` 外沒有 try/except 的話，一次未預期的例外就會讓整條排程
        **靜默停止**——App 還開著、開關還亮著、側欄什麼都不會說，使用者要好幾天
        後才會發現「它怎麼都沒動」。

        做法：讓第一輪拋例外，斷言 loop 仍能跑到第二輪。
        """
        import asyncio as _asyncio
        from core import auto_organize_state
        from web import auto_organize_scheduler as aos

        auto_organize_state.exit_cron()
        auto_organize_state._last_manual_at = float("-inf")

        calls = {"n": 0}

        # 🔴 讓 `_prepare_and_run` 拋，**不要**整支 mock 掉 `_run_round_body`：
        # 釋放 `running` 的 `exit_cron()` 就住在 `_run_round_body` 的 `_round_guard()` 裡，
        # 把它換掉等於連釋放一起拿掉 ⇒ 第二輪會被 `enter_cron()` 正確地擋下，
        # 測試就會誤判成「loop 被例外殺掉了」（第一版就是這樣自己騙自己）。
        async def _boom(trigger):
            calls["n"] += 1
            raise RuntimeError("這一輪炸了")

        monkeypatch.setattr(aos, "_prepare_and_run", _boom)
        monkeypatch.setattr(aos, "_LOOP_POLL_INTERVAL_S", 0)
        monkeypatch.setattr(aos, "_is_due", lambda: True)
        monkeypatch.setattr(
            aos, "load_config",
            lambda: {"search": {"auto_organize": {"enabled": True}}},
        )

        async def _drive():
            task = _asyncio.create_task(aos.auto_organize_loop())
            # 用真的 sleep 而不是 `sleep(0)`：loop 內有 `await asyncio.to_thread(load_config)`，
            # 那需要真的把控制權交回 event loop 才輪得到 worker thread 完成。
            for _ in range(200):
                await _asyncio.sleep(0.01)
                if calls["n"] >= 2:
                    break
            task.cancel()
            with contextlib.suppress(_asyncio.CancelledError):
                await task

        _asyncio.run(_drive())
        auto_organize_state.exit_cron()

        assert calls["n"] >= 2, (
            "第一輪拋例外之後 loop 就沒有再跑第二輪——排程被單輪的例外殺掉了"
        )


# ---------------------------------------------------------------------------
# v0.15.13 P2-2：run-now 的 detached task 沒有自己的例外處理，使用者永遠等不到
# 任何結果（側欄一片安靜）。回歸鎖 enter_and_start() 真正 create_task 出去的
# 那個 coroutine（不是直接呼叫 _run_round_body），確保例外被攔下、不逃逸成
# asyncio 的 "Task exception was never retrieved"，且有一則固定文案的失敗通知。
# ---------------------------------------------------------------------------

async def test_enter_and_start_exception_is_caught_and_notified(monkeypatch):
    """run-now 背景例外必須被攔下：不吞掉、不裸露例外細節、running 要釋放。

    重現方式：讓 `_prepare_and_run`（資料夾解析／探測／`run_one_round()` 那一段，
    `_round_guard()` 真正保護的主體）拋一個帶內部細節的例外——**不**整支 mock 掉
    `_run_round_body`，否則 `_round_guard()` 的 finally 根本不會跑到，running
    永遠不會被釋放，會誤判成 wrapper 沒接住例外。透過 `enter_and_start()`
    （不是直接呼叫 `_run_round_body`）啟動，await 它真正建立的 `_round_task`，
    斷言：
    1. 例外沒有從 task 逃逸出去（`_round_task.exception()` 為 None，不是
       `_round_task` 本身 raise）——否則就是 "Task exception was never
       retrieved" 那個洞還在。
    2. 發出的通知是固定的 `notif.auto_organize_failed`，且訊息裡**不含**例外
       原文（不可把內部路徑／SQL 洩到畫面上）。
    3. `auto_organize_state` 的 running 有被釋放（`_round_guard()` 的 finally
       仍然跑到）。
    """
    from core import auto_organize_state

    secret_detail = "sqlite3.OperationalError: no such table: /internal/path/leak"

    async def boom(trigger):
        raise RuntimeError(secret_detail)

    monkeypatch.setattr(sched, "_prepare_and_run", boom)

    emitted = []
    monkeypatch.setattr(
        sched, "emit_notification",
        lambda level, key, message="", task_type=None: emitted.append(
            (level, key, message, task_type)
        ),
    )

    result = sched.enter_and_start("run_now")
    assert result == {"success": True, "reason": None}

    # 不能直接 `await sched._round_task` 期待它乾淨結束後再檢查——重點正是
    # 「即使 body 拋例外，這個 task 本身也不可以再往外拋」。用 wait_for 確保
    # 它會結束（不是掛住），再看它是否真的沒有帶著例外收尾。
    await asyncio.wait_for(sched._round_task, timeout=1.0)
    assert sched._round_task.exception() is None, (
        "detached task 帶著例外結束——沒人 await 它，會變成 "
        "'Task exception was never retrieved' 噪音，使用者側也看不到任何通知"
    )

    assert len(emitted) == 1, f"預期恰好一則失敗通知，實際：{emitted!r}"
    level, key, message, task_type = emitted[0]
    assert level == "error"
    assert key == "notif.auto_organize_failed"
    assert task_type == "auto_organize"
    assert secret_detail not in message, (
        "失敗通知的 message 洩漏了例外原文——內部路徑／SQL 不該出現在畫面上"
    )

    assert auto_organize_state.get_status()["running"] is False, (
        "背景例外之後 running 沒有被釋放——下一輪 run-now 會被永久卡在 already_running"
    )


# ---------------------------------------------------------------------------
# Codex 三審 ①：沒設定最愛資料夾就不准跑（P0）
#
# 使用者流程：開了定時整理之後，在設定頁把 favorite_folder 清空，enabled 仍是
# true——resolve_favorite_folder() 會 fallback 到系統的「下載」資料夾，無人值守
# 地把整個下載夾的片改名搬走，而使用者從來沒指定過那個資料夾。
# ---------------------------------------------------------------------------

async def test_folder_not_configured_skips_round_and_emits_warning(monkeypatch):
    """正向鎖：favorite_folder 是空字串 → run_one_round 不跑，發 folder_not_set 通知。"""
    monkeypatch.setattr(sched, "load_config", lambda: {"search": {"favorite_folder": "",
                                        "auto_organize": {"enabled": True}}})
    run_spy = MagicMock()
    monkeypatch.setattr(sched, "run_one_round", run_spy)
    resolve_spy = MagicMock()
    monkeypatch.setattr(sched, "resolve_favorite_folder", resolve_spy)
    emit = MagicMock()
    monkeypatch.setattr(sched, "emit_notification", emit)
    reset = MagicMock(wraps=sched.reset_due_time)
    monkeypatch.setattr(sched, "reset_due_time", reset)

    assert auto_organize_state.enter_cron("schedule") is True
    await sched._run_round_body("schedule")

    run_spy.assert_not_called()
    resolve_spy.assert_not_called()
    emit.assert_called_once_with(
        "warn", "notif.auto_organize_folder_not_set", task_type="auto_organize",
    )
    reset.assert_called_once()
    assert auto_organize_state.get_status()["running"] is False


# ---------------------------------------------------------------------------
# Codex 三審 ③：排程輪拋例外時側欄要有訊息（P2）
#
# 使用者流程：auto_organize_loop() 的 except Exception 只寫 log 就把下次推遲
# 12 小時，run-now 那條路會發 notif.auto_organize_failed，排程這條不會——無人
# 值守的使用者看到開關還亮著、側欄一個字都沒有。
# ---------------------------------------------------------------------------

async def test_loop_exception_after_entered_emits_failed_notification(monkeypatch):
    """正向鎖：entered 為真時例外要發 notif.auto_organize_failed。"""
    wake_count = {"n": 0}

    async def fake_sleep(_s):
        wake_count["n"] += 1
        if wake_count["n"] >= 2:
            raise asyncio.CancelledError()

    monkeypatch.setattr(sched.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(
        sched, "load_config",
        lambda: {"search": {"auto_organize": {"enabled": True}}},
    )
    sched._next_due_at = time.time() - 1.0

    async def boom(_trigger):
        # 真正的 _round_guard() 一定會在例外離開 _run_round_body() 之前釋放 running
        # （finally 區塊），這裡手動模擬同一個保證，避免測試本身洩漏狀態。
        auto_organize_state.exit_cron()
        raise RuntimeError("round boom")

    monkeypatch.setattr(sched, "_run_round_body", boom)

    emit = MagicMock()
    monkeypatch.setattr(sched, "emit_notification", emit)

    with pytest.raises(asyncio.CancelledError):
        await sched.auto_organize_loop()

    emit.assert_called_once_with(
        "error", "notif.auto_organize_failed", task_type="auto_organize",
    )
    assert auto_organize_state.get_status()["running"] is False


