"""TASK-194-T3: linux/prepare_server.py 行為測試（走 subprocess 真入口）。"""

import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_REL = Path("linux/prepare_server.py")
DEFAULT_REL = Path("web/config.default.json")


@pytest.fixture(scope="module")
def proj(tmp_path_factory):
    dest = tmp_path_factory.mktemp("proj")
    shutil.copytree(
        REPO_ROOT / "core", dest / "core",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    (dest / "web").mkdir(parents=True)
    shutil.copy2(REPO_ROOT / DEFAULT_REL, dest / DEFAULT_REL)
    (dest / "linux").mkdir(parents=True)
    shutil.copy2(REPO_ROOT / SCRIPT_REL, dest / SCRIPT_REL)
    return dest


def _run_script(proj, data_dir, home):
    data_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["OPENAVER_DATA_DIR"] = str(data_dir)
    return subprocess.run(
        [sys.executable, str(proj / SCRIPT_REL)],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_fresh_data_root_is_finalized_before_server_mode_is_written(proj, tmp_path):
    data_dir = tmp_path / "data-fresh"
    first = _run_script(proj, data_dir, tmp_path)
    assert first.returncode == 0, f"stdout={first.stdout!r} stderr={first.stderr!r}"
    assert first.stdout == "", f"stdout must be empty, got {first.stdout!r}"
    layout_path = data_dir / ".layout.json"
    config_path = data_dir / "config.json"
    assert layout_path.is_file(), "fresh run did not finalize data root (.layout.json missing)"
    assert config_path.is_file(), "fresh run did not write config.json"
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    assert cfg["general"]["server_mode"] is True, "server_mode was not set to true"
    default = json.loads((proj / DEFAULT_REL).read_text(encoding="utf-8"))
    for key, value in default.get("general", {}).items():
        if key == "server_mode":
            continue
        assert cfg["general"][key] == value, f"general.{key} diverged from default"
    first_config_bytes = config_path.read_bytes()
    first_layout_bytes = layout_path.read_bytes()
    second = _run_script(proj, data_dir, tmp_path)
    assert second.returncode == 0, f"stdout={second.stdout!r} stderr={second.stderr!r}"
    assert second.stdout == "", f"stdout must be empty, got {second.stdout!r}"
    assert config_path.read_bytes() == first_config_bytes, "second run changed config.json"
    assert layout_path.read_bytes() == first_layout_bytes, "second run changed .layout.json"


def test_existing_settings_survive_only_server_mode_flips(proj, tmp_path):
    data_dir = tmp_path / "data-existing"
    baseline = _run_script(proj, data_dir, tmp_path)
    assert baseline.returncode == 0, f"stdout={baseline.stdout!r} stderr={baseline.stderr!r}"
    config_path = data_dir / "config.json"
    assert config_path.is_file(), "baseline run did not produce config.json"
    before = json.loads(config_path.read_text(encoding="utf-8"))
    before.setdefault("general", {})["server_mode"] = False
    before["general"]["theme"] = "light"
    before["general"]["locale"] = "ja"
    before.setdefault("gallery", {})["directories"] = [
        {"path": "/mnt/media/av", "readonly": True, "output_path": ""}
    ]
    config_path.write_text(
        json.dumps(before, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    rerun = _run_script(proj, data_dir, tmp_path)
    assert rerun.returncode == 0, f"stdout={rerun.stdout!r} stderr={rerun.stderr!r}"
    assert rerun.stdout == "", f"stdout must be empty, got {rerun.stdout!r}"
    after = json.loads(config_path.read_text(encoding="utf-8"))
    expected = copy.deepcopy(before)
    expected["general"]["server_mode"] = True
    assert after == expected, "rerun changed settings other than general.server_mode"
