"""tests/unit/test_focal_device_state.py — INV-152c-1 / INV-152c-2 / INV-152c-3

裝置級停用判定（feature/152c TASK-4）。每支測試把 CONFIG_PATH 指到各自的
tmp_path，走真檔案 I/O，不 mock load_config / save_config / mutate_config。
"""

from __future__ import annotations


import pytest

import core.config as core_config
from core.config import load_config, save_config
from core.focal.subprocess_runner import RunnerOutcome


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _patch_config_paths(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
    monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")
    return config_path


def _seed_focal_device(
    *,
    disabled: bool = False,
    consecutive_timeout_count: int = 0,
    judged_at_version: str = "",
    set_by_user: bool = False,
) -> None:
    save_config(
        {
            "focal_device": {
                "disabled": disabled,
                "consecutive_timeout_count": consecutive_timeout_count,
                "judged_at_version": judged_at_version,
                "set_by_user": set_by_user,
            }
        }
    )


def _read_focal_device() -> dict:
    return load_config()["focal_device"]


def _abandoned(reason: str) -> RunnerOutcome:
    return RunnerOutcome(kind="ABANDONED", reason=reason)


def _found(x: float = 0.5, y: float = 0.5) -> RunnerOutcome:
    return RunnerOutcome(kind="FOUND", focal=(x, y))


# ---------------------------------------------------------------------------
# INV-152c-1 — 只有 detect_timeout 遞增；FOUND 歸零計數但不解除 disabled
# ---------------------------------------------------------------------------


class TestInv152c1Classification:
    def test_startup_timeout_noop_then_two_detect_timeout_disables_then_found_zeros_count(
        self, tmp_path, monkeypatch
    ):
        """INV-152c-1 主流程（DoD）。"""
        from core.focal import device_state
        from core.version import VERSION

        _patch_config_paths(tmp_path, monkeypatch)
        _seed_focal_device(judged_at_version=VERSION)

        assert device_state.record_outcome(_abandoned("startup_timeout")) is False
        assert device_state.record_outcome(_abandoned("startup_timeout")) is False
        fd = _read_focal_device()
        assert fd["consecutive_timeout_count"] == 0
        assert fd["disabled"] is False

        assert device_state.record_outcome(_abandoned("detect_timeout")) is False
        just = device_state.record_outcome(_abandoned("detect_timeout"))
        assert just is True
        fd = _read_focal_device()
        assert fd["consecutive_timeout_count"] == 2
        assert fd["disabled"] is True

        assert device_state.record_outcome(_found()) is False
        fd = _read_focal_device()
        assert fd["consecutive_timeout_count"] == 0
        assert fd["disabled"] is True

    @pytest.mark.parametrize(
        "reason",
        ["crashed", ],
    )
    def test_abandoned_noop_reasons_leave_state_unchanged(
        self, tmp_path, monkeypatch, reason
    ):
        """INV-152c-1 no-op 覆蓋（DoD）：各自獨立連續呼叫後計數與 disabled 不變。"""
        from core.focal import device_state
        from core.version import VERSION

        _patch_config_paths(tmp_path, monkeypatch)
        _seed_focal_device(
            disabled=False,
            consecutive_timeout_count=1,
            judged_at_version=VERSION,
        )

        assert device_state.record_outcome(_abandoned(reason)) is False
        assert device_state.record_outcome(_abandoned(reason)) is False
        fd = _read_focal_device()
        assert fd["consecutive_timeout_count"] == 1
        assert fd["disabled"] is False


# ---------------------------------------------------------------------------
# INV-152c-2 — lazy reset（讀路徑立即失真、寫路徑先重置再套用）
# ---------------------------------------------------------------------------


class TestInv152c2LazyReset:
    def test_version_mismatch_read_false_write_resets_then_applies(
        self, tmp_path, monkeypatch
    ):
        """INV-152c-2 主流程（DoD）。"""
        from core.focal import device_state

        _patch_config_paths(tmp_path, monkeypatch)
        monkeypatch.setattr(device_state, "VERSION", "0.16.4")
        _seed_focal_device(
            disabled=True,
            consecutive_timeout_count=2,
            judged_at_version="0.16.3",
        )

        assert device_state.is_disabled() is False

        assert device_state.record_outcome(_abandoned("detect_timeout")) is False
        fd = _read_focal_device()
        assert fd["consecutive_timeout_count"] == 1
        assert fd["disabled"] is False
        assert fd["judged_at_version"] == "0.16.4"

        just = device_state.record_outcome(_abandoned("detect_timeout"))
        assert just is True
        fd = _read_focal_device()
        assert fd["consecutive_timeout_count"] == 2
        assert fd["disabled"] is True
        assert fd["judged_at_version"] == "0.16.4"
        assert device_state.is_disabled() is True


# ---------------------------------------------------------------------------
# record_outcome 不得吞 mutate_config 例外（設計決策硬性要求第 2 條）
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# INV-152c-3 — record_outcome mutator 遵守 mutate_config 契約（真檔案 I/O + 真 thread）
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# T10 — F6 通知埠：只在 disabled false→true 的那一刻經 sink 發一則
# (CD-152b-15 / CD-152c-20)
# ---------------------------------------------------------------------------


class TestNotificationSinkTransition:
    def test_sink_called_once_on_transition_not_on_first_timeout(
        self, tmp_path, monkeypatch
    ):
        """DoD：連續兩次超時湊滿 → sink 恰好被呼叫一次，且發生在第二次那一輪。"""
        from core.focal import device_state
        from core.version import VERSION

        _patch_config_paths(tmp_path, monkeypatch)
        _seed_focal_device(judged_at_version=VERSION)
        calls: list[tuple] = []
        monkeypatch.setattr(
            device_state, "_notification_sink",
            lambda *args, **kwargs: calls.append((args, kwargs)),
        )

        assert device_state.record_outcome(_abandoned("detect_timeout")) is False
        assert calls == []  # 第一次超時：還沒轉態，不發

        assert device_state.record_outcome(_abandoned("detect_timeout")) is True
        assert calls == [(("warn", "notif.focal_auto_disabled"), {})]


# ---------------------------------------------------------------------------
# feature/152d TASK-D1 — set_by_user：使用者的決定不被系統覆寫
# ---------------------------------------------------------------------------


class TestSetByUser:

    def test_set_by_user_true_blocks_auto_disable(self, tmp_path, monkeypatch):
        """set_by_user=True 時，連續 2 次 detect_timeout 不會把 disabled 翻成 True。"""
        from core.focal import device_state
        from core.version import VERSION

        _patch_config_paths(tmp_path, monkeypatch)
        _seed_focal_device(
            disabled=False,
            consecutive_timeout_count=0,
            judged_at_version=VERSION,
            set_by_user=True,
        )

        assert device_state.record_outcome(_abandoned("detect_timeout")) is False
        assert device_state.record_outcome(_abandoned("detect_timeout")) is False
        fd = _read_focal_device()
        assert fd["disabled"] is False
        assert fd["set_by_user"] is True
        assert fd["consecutive_timeout_count"] == 2
        assert device_state.is_disabled() is False

    def test_set_by_user_true_survives_version_bump(self, tmp_path, monkeypatch):
        """set_by_user=True 時，版本升級不會把 disabled／set_by_user 重置回系統管理中。"""
        from core.focal import device_state

        _patch_config_paths(tmp_path, monkeypatch)
        monkeypatch.setattr(device_state, "VERSION", "0.16.4")
        _seed_focal_device(
            disabled=True,
            consecutive_timeout_count=2,
            judged_at_version="0.16.3",
            set_by_user=True,
        )

        # 讀路徑：與版本無關，直接回 disabled
        assert device_state.is_disabled() is True

        # 寫路徑：整段 lazy reset 跳過；disabled／set_by_user 都不被打回
        assert device_state.record_outcome(_abandoned("detect_timeout")) is False
        fd = _read_focal_device()
        assert fd["disabled"] is True
        assert fd["set_by_user"] is True
        assert fd["consecutive_timeout_count"] == 3  # 未 reset，繼續累積
        assert fd["judged_at_version"] == "0.16.4"
        assert device_state.is_disabled() is True


# ---------------------------------------------------------------------------
# feature/152d TASK-D2 — record_manual_outcome：前景單次逾時判定、不發 sink
# ---------------------------------------------------------------------------


class TestRecordManualOutcome:

    def test_record_manual_outcome_single_timeout_disables(self, tmp_path, monkeypatch):
        """前景單次 detect_timeout 就翻 disabled（不必累積到背景的 2 次門檻）。"""
        from core.focal import device_state
        from core.version import VERSION

        _patch_config_paths(tmp_path, monkeypatch)
        _seed_focal_device(
            disabled=False,
            consecutive_timeout_count=0,
            judged_at_version=VERSION,
        )

        just = device_state.record_manual_outcome(_abandoned("detect_timeout"))
        assert just is True
        fd = _read_focal_device()
        assert fd["disabled"] is True
        assert fd["consecutive_timeout_count"] == 0  # count_timeouts=False：不碰 streak
        assert fd["judged_at_version"] == VERSION
        assert device_state.is_disabled() is True


# ---------------------------------------------------------------------------
# classify_manual_reason — table (187a-T3a adds endpoint_down)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kind,reason,external_failure,just_disabled,expected",
    [
        ("FOUND", None, "external_unreachable", False, "endpoint_down"),
        ("ABANDONED", "skipped_disabled", "external_unreachable", False, "endpoint_down"),
        ("ABANDONED", "skipped_disabled", None, False, "device_disabled"),
    ],
)
def test_classify_manual_reason_table(
    kind, reason, external_failure, just_disabled, expected
):
    """FOUND/NO_FACE or ABANDONED(skipped_disabled)+external_failure → endpoint_down."""
    from types import SimpleNamespace

    from core.focal import device_state

    outcome = SimpleNamespace(
        kind=kind, reason=reason, external_failure=external_failure
    )
    assert device_state.classify_manual_reason(outcome, just_disabled) == expected

