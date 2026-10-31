"""187a-T3a: external faces re-arm isolation (I-C oracle ②)."""

from __future__ import annotations

from unittest.mock import patch

import core.config as core_config
from core.config import load_config, mutate_config, save_config
from core.version import VERSION


def _patch_config_paths(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
    monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")
    return config_path


def _seed_focal_device_disabled() -> None:
    save_config(
        {
            "focal_device": {
                "disabled": True,
                "consecutive_timeout_count": 2,
                "judged_at_version": VERSION,
                "set_by_user": False,
            }
        }
    )


def test_external_enabled_rearms_and_closing_restores_focal_device(tmp_path, monkeypatch):
    """Local disabled + VERSION match; faces on → re-arm; faces off → same focal_device."""
    from core.focal import device_state
    from core.focal_trigger import maybe_submit_video_focal

    _patch_config_paths(tmp_path, monkeypatch)
    _seed_focal_device_disabled()

    cover = tmp_path / "cover.jpg"
    cover.write_bytes(b"x")

    def _enable_faces(cfg: dict) -> None:
        cfg.setdefault("ai_services", {})["faces"] = {
            "enabled": True,
            "url": "http://faces.test",
            "api_key": "",
            "model": "",
        }

    mutate_config(_enable_faces)

    assert device_state.is_disabled() is False

    with patch("core.focal_trigger.submit_focal") as mock_submit:
        maybe_submit_video_focal(
            "SIRO-1234",
            "",
            "file:///x/SIRO-1234.mp4",
            str(cover),
            cover_path_uri="file:///x/SIRO-1234.jpg",
        )
    mock_submit.assert_called_once()

    before = dict(load_config()["focal_device"])

    def _disable_faces(cfg: dict) -> None:
        cfg["ai_services"]["faces"]["enabled"] = False

    mutate_config(_disable_faces)

    assert device_state.is_disabled() is True
    assert dict(load_config()["focal_device"]) == before

    with patch("core.focal_trigger.submit_focal") as mock_submit:
        maybe_submit_video_focal(
            "SIRO-1234",
            "",
            "file:///x/SIRO-1234.mp4",
            str(cover),
            cover_path_uri="file:///x/SIRO-1234.jpg",
        )
    mock_submit.assert_not_called()


# ---------------------------------------------------------------------------
# 187a-T3b: run_detection external branch (I-A / I-B / fallback probe)
# ---------------------------------------------------------------------------

import json  # noqa: E402

import pytest  # noqa: E402

from core.ai_services.faces_detect import ExternalResult  # noqa: E402
from core.focal import device_state, subprocess_runner  # noqa: E402
from tests.unit.test_focal_subprocess_runner import FakeProcess  # noqa: E402


def _spawn(focal, counter):
    def spawn_fn(fs_path, ratio):
        counter.append(1)
        p = FakeProcess()
        p.stdout.feed_line("READY")
        if focal != "hang":
            p.stdout.feed_line(json.dumps({"focal": list(focal)}))
        return p
    return spawn_fn


def _run(spawn_fn, **kw):
    return subprocess_runner.run_detection(
        "/x.jpg", 0.71, job_key="j", timeout_s=0.05, spawn_fn=spawn_fn,
        pre_spawn_check=device_state.is_disabled, on_outcome=device_state.record_outcome,
        **kw,
    )


@pytest.fixture
def _ext(tmp_path, monkeypatch):
    from core.ai_services import faces_detect, faces_state
    _patch_config_paths(tmp_path, monkeypatch)
    sink: list = []
    monkeypatch.setattr(device_state, "_notification_sink", lambda *a, **k: sink.append(a))
    monkeypatch.setattr(faces_state, "_notification_sink", lambda *a, **k: sink.append(a))
    monkeypatch.setattr(subprocess_runner, "_local_disabled_probe", device_state.local_is_disabled)

    def set_ext(result, seen=None):
        def fake(fs_path, ratio, profile="background"):
            if seen is not None:
                seen.append(subprocess_runner._slot_lock.locked())
            return result
        monkeypatch.setattr(faces_detect, "detect", fake)
    return set_ext, sink


def test_external_failures_never_touch_focal_device(_ext):
    set_ext, sink = _ext
    failed = ExternalResult(kind="FAILED", failure="external_timeout")
    # local disabled: 4 external failures never spawn nor change config
    _seed_focal_device_disabled()
    before, spawned = dict(load_config()["focal_device"]), []
    set_ext(failed)
    for _ in range(4):
        out = _run(_spawn((0.8, 0.7), spawned))
        assert out.reason == "skipped_disabled"
    assert spawned == [] and dict(load_config()["focal_device"]) == before and sink == []
    # local usable: control (external off) vs external-fail fallback, local detect_timeout x2
    fresh = {"focal_device": {"disabled": False, "consecutive_timeout_count": 0,
                              "judged_at_version": VERSION, "set_by_user": False}}
    save_config(fresh)
    set_ext(None)
    ctl_spawn = []
    for _ in range(2):
        _run(_spawn("hang", ctl_spawn))
    control = dict(load_config()["focal_device"])
    save_config(fresh)
    set_ext(failed)
    exp_spawn = []
    for _ in range(2):
        _run(_spawn("hang", exp_spawn))
    assert dict(load_config()["focal_device"]) == control
    assert len(exp_spawn) == len(ctl_spawn)


def test_fallback_respects_local_disabled_probe(_ext, monkeypatch):
    set_ext, _ = _ext
    set_ext(ExternalResult(kind="FAILED", failure="external_unreachable"))
    seen, spawned = [], []
    monkeypatch.setattr(subprocess_runner, "_local_disabled_probe", lambda: True)
    out = subprocess_runner.run_detection(
        "/x.jpg", 0.71, job_key="j", timeout_s=0.05, spawn_fn=_spawn((0.8, 0.7), spawned),
        on_outcome=seen.append,
    )
    assert (out.kind, out.reason, out.external_failure) == (
        "ABANDONED", "skipped_disabled", "external_unreachable")
    assert spawned == [] and seen == []

    def boom():
        raise RuntimeError("probe")
    monkeypatch.setattr(subprocess_runner, "_local_disabled_probe", boom)
    out = subprocess_runner.run_detection(
        "/x.jpg", 0.71, job_key="j", timeout_s=1.0, spawn_fn=_spawn((0.8, 0.7), spawned))
    assert out.kind == "FOUND" and out.focal == (0.8, 0.7) and len(spawned) == 1
    assert out.external_failure == "external_unreachable"


@pytest.mark.parametrize("res", [
    ExternalResult(kind="FOUND", focal=(0.2, 0.3), model="m1"),
    ExternalResult(kind="NO_FACE", model="m1"),
])
def test_external_success_never_spawns_nor_records(_ext, res):
    set_ext, _ = _ext
    held, spawned, seen = [], [], []
    set_ext(res, held)
    out = subprocess_runner.run_detection(
        "/x.jpg", 0.71, job_key="j", timeout_s=0.05, spawn_fn=_spawn((0.8, 0.7), spawned),
        on_outcome=seen.append,
    )
    assert (out.kind, out.focal, out.model) == (res.kind, res.focal, "m1")
    assert spawned == [] and seen == [] and held == [False]
