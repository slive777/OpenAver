"""Synthetic DSM packages for the SPK artifact audit."""

from __future__ import annotations

import io
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest


AUDITOR = Path(__file__).resolve().parents[2] / "scripts/audit_spk_artifact.py"


def _add_file(archive: tarfile.TarFile, name: str, content: bytes = b"x") -> None:
    info = tarfile.TarInfo(name)
    info.size = len(content)
    archive.addfile(info, io.BytesIO(content))


def _make_spk(
    path: Path,
    archs: tuple[str, ...],
    dist_counts: dict[str, int] | None = None,
    extra: dict[str, bytes] | None = None,
) -> None:
    package_bytes = io.BytesIO()
    with tarfile.open(fileobj=package_bytes, mode="w:gz") as package:
        for arch in archs:
            _add_file(package, f"python-{arch}/bin/python3")
            _add_file(package, f"python-{arch}/bin/python3.12")
            for number in range((dist_counts or {}).get(arch, 5)):
                _add_file(
                    package,
                    f"python-{arch}/lib/python3.12/site-packages/pkg{number}-1.0.dist-info/METADATA",
                )
        for name, content in (extra or {}).items():
            _add_file(package, name, content)
    with tarfile.open(path, mode="w") as spk:
        _add_file(spk, "package.tgz", package_bytes.getvalue())


def _audit(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(AUDITOR), str(path), "--strict", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_audit_spk_artifact_flags_missing_architecture(tmp_path: Path) -> None:
    spk = tmp_path / "missing.spk"
    _make_spk(spk, ("aarch64",))

    result = _audit(spk)

    assert result.returncode != 0
    assert "x86_64" in result.stdout + result.stderr


@pytest.mark.parametrize(
    ("aarch64_count", "x86_64_count", "expected_code"),
    [(2, 5, 1)],
)
def test_audit_spk_artifact_dist_info_ratio_boundary(
    tmp_path: Path,
    aarch64_count: int,
    x86_64_count: int,
    expected_code: int,
) -> None:
    spk = tmp_path / "ratio.spk"
    _make_spk(
        spk,
        ("aarch64", "x86_64"),
        {"aarch64": aarch64_count, "x86_64": x86_64_count},
    )

    result = _audit(spk)

    assert result.returncode == expected_code, result.stdout + result.stderr


@pytest.mark.parametrize("case", ["top_level_dir", "dist_info_only", "clean_pass"])
def test_audit_spk_rich_group_leftovers(tmp_path: Path, case: str) -> None:
    """top_level_dir: four rich-group dirs in x86_64 only -> exit 1, names arch.

    dist_info_only: only the four *.dist-info/METADATA in x86_64 only
    -> exit 1. clean_pass: no leftovers -> exit 0.
    """
    rich_group_dirs = ["rich", "pygments", "markdown_it", "mdurl"]
    rich_group_dists = [
        "rich-14.0.0.dist-info",
        "pygments-2.19.2.dist-info",
        "markdown_it_py-4.0.0.dist-info",
        "mdurl-0.1.2.dist-info",
    ]
    prefix = "python-x86_64/lib/python3.12/site-packages/"
    if case == "top_level_dir":
        extra = {f"{prefix}{pkg}/__init__.py": b"x" for pkg in rich_group_dirs}
    elif case == "dist_info_only":
        extra = {f"{prefix}{dist}/METADATA": b"Metadata-Version: 2.4\n" for dist in rich_group_dists}
    else:
        extra = {}
    spk = tmp_path / f"{case}.spk"
    _make_spk(spk, ("aarch64", "x86_64"), extra=extra)

    result = _audit(spk)

    combined = result.stdout + result.stderr
    if case == "clean_pass":
        assert result.returncode == 0, combined
    else:
        assert result.returncode == 1, f"case={case} must hard-fail\n{combined}"
        assert "x86_64" in combined, f"case={case}: output must name the arch\n{combined}"
        for name in rich_group_dirs:
            assert name in combined, f"case={case}: {name!r} missing\n{combined}"


@pytest.mark.parametrize(("limit", "code"), [("0.001", 1), ("10", 0)], ids=["over", "within"])
def test_audit_spk_size_ceiling(tmp_path: Path, limit: str, code: int) -> None:
    spk = tmp_path / "size.spk"
    _make_spk(spk, ("aarch64", "x86_64"))
    result = _audit(spk, "--max-mb", limit)
    assert result.returncode == code, result.stdout + result.stderr
    if code == 1:
        assert "ceiling" in result.stdout + result.stderr


@pytest.mark.parametrize("case", ["libpython", "tkinter_pkg", "tkinter_ext", "tcl_tk", "pil_finder_ok"])
def test_audit_spk_slim_leftovers(tmp_path: Path, case: str) -> None:
    cases = {
        "libpython": ("aarch64", ["lib/libpython3.12.so.1.0"]),
        "tkinter_pkg": ("x86_64", ["lib/python3.12/tkinter/__init__.py"]),
        "tkinter_ext": ("aarch64", ["lib/python3.12/lib-dynload/_tkinter.so"]),
        "tcl_tk": ("x86_64", ["lib/libtcl9.0.so", "lib/libtk9.0.so"]),
    }
    if case == "pil_finder_ok":
        extra = {f"python-{arch}/lib/python3.12/site-packages/PIL/_tkinter_finder.py": b"x"
                 for arch in ("aarch64", "x86_64")}
    else:
        arch, paths = cases[case]
        extra = {f"python-{arch}/{path}": b"x" for path in paths}
    spk = tmp_path / f"{case}.spk"
    _make_spk(spk, ("aarch64", "x86_64"), extra=extra)
    result = _audit(spk)
    output = result.stdout + result.stderr
    if case == "pil_finder_ok":
        assert result.returncode == 0, output
    else:
        assert result.returncode == 1, output
        failures = "\n".join(line for line in output.splitlines() if "[FAIL]" in line)
        assert arch in failures
        assert ("x86_64" if arch == "aarch64" else "aarch64") not in failures
        for path in paths:
            assert path in failures
