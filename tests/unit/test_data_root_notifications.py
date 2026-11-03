"""TASK-153b-T4: data-root bootstrap notifications via lifespan consume-once."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

import core.data_layout as data_layout_module
import web.app as webapp
from core.data_layout import BootstrapResult


@pytest.fixture(autouse=True)
def _reset_bootstrap_notification_state(monkeypatch):
    monkeypatch.setattr(data_layout_module, "_bootstrap_notification_recorded", False)
    monkeypatch.setattr(data_layout_module, "_pending_bootstrap_result", None)


def _recording_bootstrap(status: str, root: Path):
    def _fake():
        result = BootstrapResult(status=status, root=root)
        data_layout_module._record_first_bootstrap_result(result)
        return result

    return _fake


def _run_lifespan_with_bootstrap(monkeypatch, fake_bootstrap, emit: Mock):
    """Drive real lifespan via TestClient; silence DB / update-check side effects."""

    async def _noop_loop():
        while True:
            await asyncio.sleep(3600)

    monkeypatch.setattr(webapp, "bootstrap_data_layout", fake_bootstrap)
    monkeypatch.setattr(webapp, "emit_notification", emit)
    monkeypatch.setattr(webapp, "init_db", Mock())
    monkeypatch.setattr(webapp, "seed_builtin_aliases", Mock())
    monkeypatch.setattr(webapp, "start_notification_persistence", Mock())
    monkeypatch.setattr(webapp, "stop_notification_persistence", Mock())
    monkeypatch.setattr(webapp, "ensure_schema", Mock())
    monkeypatch.setattr(webapp, "backfill_readonly_nfo_mtime_once", Mock(return_value=0))
    monkeypatch.setattr(webapp, "startup_reconnect", Mock(return_value=None))
    monkeypatch.setattr(webapp, "check_update", AsyncMock(return_value={"has_update": False}))
    monkeypatch.setattr(
        webapp,
        "load_config",
        Mock(return_value={"gallery": {}, "general": {}, "search": {}}),
    )
    monkeypatch.setattr(webapp, "_is_windows_desktop", Mock(return_value=False))
    monkeypatch.setattr(webapp, "_is_mac_desktop", Mock(return_value=False))
    monkeypatch.setattr(webapp, "auto_organize_loop", _noop_loop)
    # CodeRabbit（153b PR #202）：web/app.py 用 `await
    # source_reachability.schedule_reprobe_if_stale()`；同步 Mock() 會讓 await
    # 對它拋 TypeError（被 lifespan 的 broad except 吞掉，靜默通過但完全沒驗到
    # 排程行為）。AsyncMock 才是正確匹配 async 呼叫契約的替身。
    monkeypatch.setattr(
        webapp.source_reachability,
        "schedule_reprobe_if_stale",
        AsyncMock(return_value=None),
        raising=False,
    )

    with TestClient(webapp.app):
        pass


def test_lifespan_consumes_reset_access_auth_marker_once(monkeypatch):
    consume = Mock()
    monkeypatch.setattr(webapp, "consume_reset_access_auth_marker", consume, raising=False)
    _run_lifespan_with_bootstrap(
        monkeypatch,
        _recording_bootstrap("already_complete", Path("/tmp/openaver-data-root-reset-fixture")),
        Mock(),
    )
    consume.assert_called_once_with()


def test_recovered_existing_emits_warn_with_required_literals(monkeypatch):
    root = Path("/tmp/openaver-data-root-recovered-fixture")
    emit = Mock()
    _run_lifespan_with_bootstrap(
        monkeypatch, _recording_bootstrap("recovered_existing", root), emit
    )

    data_root_calls = [
        c for c in emit.call_args_list if c.args and c.args[1] == "notif.data_root_recovered"
    ]
    assert len(data_root_calls) == 1
    assert data_root_calls[0].args[0] == "warn"
    assert data_root_calls[0].kwargs.get("message") == str(root)

    zh = (Path(__file__).resolve().parents[2] / "locales" / "zh_TW.json").read_text(
        encoding="utf-8"
    )
    for needle in ("來源設定", "跨機器路徑映射", "外部服務設定", "介面偏好"):
        assert needle in zh


class _OsExitProxy:
    """web.app 模組命名空間專用 os 代理：只覆寫 _exit，其餘轉發真實 os。

    不 monkeypatch 全域 os._exit，避免污染同 process 其他測試。
    """

    def __init__(self, real_os, exit_impl):
        object.__setattr__(self, "_real_os", real_os)
        object.__setattr__(self, "_exit_impl", exit_impl)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_real_os"), name)

    def _exit(self, code):
        return object.__getattribute__(self, "_exit_impl")(code)


async def test_lifespan_bootstrap_oserror_writes_stderr_and_exits_78(monkeypatch, capsys):
    """O2：lifespan gate 必須攔 OSError（I/O 原樣上拋），走固定 stderr + os._exit(78)。"""
    init_db = Mock()
    monkeypatch.setattr(
        webapp, "bootstrap_data_layout", Mock(side_effect=OSError("disk full"))
    )
    monkeypatch.setattr(webapp, "init_db", init_db)

    exit_calls: list[int] = []

    def fake_exit(code):
        exit_calls.append(code)
        raise SystemExit(code)

    monkeypatch.setattr(webapp, "os", _OsExitProxy(webapp.os, fake_exit))

    with pytest.raises(SystemExit) as ei:
        async with webapp.lifespan(webapp.app):
            pass

    assert ei.value.code == webapp.LIFESPAN_BOOTSTRAP_EXIT_CODE
    assert exit_calls == [webapp.LIFESPAN_BOOTSTRAP_EXIT_CODE]
    captured = capsys.readouterr()
    assert webapp._LIFESPAN_BOOTSTRAP_STDERR in captured.err
    init_db.assert_not_called()
