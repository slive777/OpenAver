"""TASK-107-P1-T2: lifespan 啟動更新檢查 orchestration 單元測試。

測試入口＝直接 `await web.app._startup_update_check()`，patch 四個 use-site 依賴：
  - `web.app.check_update`（AsyncMock）
  - `web.app.emit_notification`（Mock）
  - `web.app.load_config`（回 raw dict）
  - `web.app._is_windows_desktop` / `web.app._is_mac_desktop`（回 bool）

pytest.ini asyncio_mode = auto → async def test_* 無需 @pytest.mark.asyncio 裝飾。

繞開背景 task 競態（AC-A6 lifespan 不 await 其完成）：把 orchestration 收成
module-level async 函式後可直接 await、確定性斷言 emit 有無與參數。
"""

from unittest.mock import AsyncMock, Mock, patch

import web.app as webapp


def _patches(*, check_update_result=None, check_update_exc=None,
             config=None, is_win=True, is_mac=False):
    """回傳 (check_update_mock, emit_mock) 並套用 patch 的 context manager helper。

    以 ExitStack 風格手動組合較繁瑣，這裡改用一個 patch 集合的 contextmanager。
    """
    cu = AsyncMock()
    if check_update_exc is not None:
        cu.side_effect = check_update_exc
    else:
        cu.return_value = check_update_result
    emit = Mock()
    load = Mock(return_value=config if config is not None else {"general": {"auto_check_update": True}})
    return cu, emit, load, is_win, is_mac


def _apply(cu, emit, load, is_win, is_mac):
    return [
        patch.object(webapp, "check_update", cu),
        patch.object(webapp, "emit_notification", emit),
        patch.object(webapp, "load_config", load),
        patch.object(webapp, "_is_windows_desktop", Mock(return_value=is_win)),
        patch.object(webapp, "_is_mac_desktop", Mock(return_value=is_mac)),
    ]


async def _run(cu, emit, load, is_win, is_mac):
    ctxs = _apply(cu, emit, load, is_win, is_mac)
    for c in ctxs:
        c.start()
    try:
        await webapp._startup_update_check()
    finally:
        for c in ctxs:
            c.stop()


async def test_has_update_emits_once():
    """桌面 + flag on + 有新版 → emit 恰一次，args=("info","notif.update_available")、message="v9.9.9"。"""
    cu, emit, load, is_win, is_mac = _patches(
        check_update_result={
            "success": True, "has_update": True,
            "current_version": "1.0.0", "latest_version": "9.9.9",
            "download_url": "https://example.com",
        }
    )
    await _run(cu, emit, load, is_win, is_mac)
    cu.assert_awaited_once()
    emit.assert_called_once_with("info", "notif.update_available", message="v9.9.9")


async def test_up_to_date_no_emit():
    """桌面 + flag on + 已最新（has_update False）→ 無 emit。"""
    cu, emit, load, is_win, is_mac = _patches(
        check_update_result={
            "success": True, "has_update": False,
            "current_version": "9.9.9", "latest_version": "9.9.9",
        }
    )
    await _run(cu, emit, load, is_win, is_mac)
    cu.assert_awaited_once()
    emit.assert_not_called()


async def test_404_no_latest_version_no_emit():
    """404 分支（has_update False、無 latest_version）→ 無 emit、不 KeyError。"""
    cu, emit, load, is_win, is_mac = _patches(
        check_update_result={"success": True, "has_update": False, "current_version": "1.0.0"}
    )
    await _run(cu, emit, load, is_win, is_mac)
    cu.assert_awaited_once()
    emit.assert_not_called()


async def test_flag_off_check_update_not_called():
    """開關關（auto_check_update False）→ check_update 未被呼叫、無 emit。"""
    cu, emit, load, is_win, is_mac = _patches(
        check_update_result={"success": True, "has_update": True, "latest_version": "9.9.9"},
        config={"general": {"auto_check_update": False}},
    )
    await _run(cu, emit, load, is_win, is_mac)
    cu.assert_not_awaited()
    cu.assert_not_called()
    emit.assert_not_called()


async def test_non_desktop_check_update_not_called():
    """非桌面（両 is_desktop False）→ check_update 未被呼叫、無 emit。"""
    cu, emit, load, is_win, is_mac = _patches(
        check_update_result={"success": True, "has_update": True, "latest_version": "9.9.9"},
        is_win=False, is_mac=False,
    )
    await _run(cu, emit, load, is_win, is_mac)
    cu.assert_not_awaited()
    cu.assert_not_called()
    emit.assert_not_called()


async def test_check_update_raises_does_not_propagate():
    """check_update 拋例外 → _startup_update_check 不外拋（正常返回）、無 emit。"""
    cu, emit, load, is_win, is_mac = _patches(check_update_exc=RuntimeError("boom"))
    # 不應拋出 —— 若外拋，await 這行會 raise，測試 fail。
    await _run(cu, emit, load, is_win, is_mac)
    emit.assert_not_called()


async def test_error_dict_no_emit():
    """check_update 回 error dict（success False）→ 不 emit、不 crash。"""
    cu, emit, load, is_win, is_mac = _patches(
        check_update_result={"success": False, "error": "連線逾時"}
    )
    await _run(cu, emit, load, is_win, is_mac)
    cu.assert_awaited_once()
    emit.assert_not_called()


async def test_missing_flag_key_defaults_true():
    """config general 缺 auto_check_update → .get(..., True) 落預設 True → 桌面下照常查。"""
    cu, emit, load, is_win, is_mac = _patches(
        check_update_result={"success": True, "has_update": True, "latest_version": "9.9.9"},
        config={},
    )
    await _run(cu, emit, load, is_win, is_mac)
    cu.assert_awaited_once()
    emit.assert_called_once_with("info", "notif.update_available", message="v9.9.9")
