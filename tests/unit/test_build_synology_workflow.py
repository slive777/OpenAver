"""Structural checks for the Synology build and release workflow."""

from pathlib import Path

import yaml


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/build.yml"


def _synology_steps():
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return workflow["jobs"]["build-synology"]["steps"]


def test_build_synology_job_exists():
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert "build-synology" in workflow["jobs"]


def test_build_synology_calls_packaging_script():
    assert any("synology/build_spk.sh" in step.get("run", "") for step in _synology_steps())


def test_build_synology_audits_strictly():
    assert any(
        "python scripts/audit_spk_artifact.py" in step.get("run", "")
        and "--strict" in step["run"]
        and "--max-mb" in step["run"]
        for step in _synology_steps()
    )


def test_release_asset_name_has_no_build_number():
    copy_commands = [
        line.strip()
        for step in _synology_steps()
        for line in step.get("run", "").splitlines()
        if line.strip().startswith("cp synology/out/OpenAver-")
    ]
    assert copy_commands == [
        "cp synology/out/OpenAver-${{ steps.ver.outputs.spk_version }}-fat.spk "
        "OpenAver-v${{ steps.ver.outputs.app_version }}-Synology-beta.spk"
    ]


def test_release_upload_is_tag_only():
    assert any(
        step.get("uses") == "softprops/action-gh-release@v2"
        and step.get("if") == "startsWith(github.ref, 'refs/tags/')"
        for step in _synology_steps()
    )
