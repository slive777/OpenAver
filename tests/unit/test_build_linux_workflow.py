"""Structural checks for the Linux build-linux release job."""

from pathlib import Path

import yaml


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/build.yml"


def _linux_job():
    jobs = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]
    assert "build-linux" in jobs
    return jobs["build-linux"]


def test_build_linux_release_upload_covers_both_assets():
    job = _linux_job()
    needs = job["needs"]
    assert "build-synology" in ([needs] if isinstance(needs, str) else needs)
    steps = job["steps"]
    assert any(
        s.get("uses", "").startswith("actions/download-artifact@")
        and s.get("with", {}).get("name") == "OpenAver-Synology"
        for s in steps
    )
    assert any(
        s.get("uses") == "softprops/action-gh-release@v2"
        and s.get("if") == "startsWith(github.ref, 'refs/tags/')"
        and "-Linux-" in s["with"]["files"]
        and ".tar.gz" in s["with"]["files"]
        for s in steps
    )


def test_build_linux_audit_gates_upload_for_both_arches():
    steps = _linux_job()["steps"]
    runs = [s.get("run", "") for s in steps]
    repack = next(i for i, r in enumerate(runs) if "scripts/repack_linux.sh" in r)
    first_publish = next(
        i for i, s in enumerate(steps)
        if s.get("uses", "").startswith(("actions/upload-artifact@", "softprops/action-gh-release@"))
    )
    for arch in ("Linux-x86_64", "Linux-aarch64"):
        audit = next(
            i for i, r in enumerate(runs)
            if "audit_build_artifact.py" in r and arch in r
        )
        for flag in ("--platform linux", "--strict", "--max-mb"):
            assert flag in runs[audit]
        assert repack < audit < first_publish
