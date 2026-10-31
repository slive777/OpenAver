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
