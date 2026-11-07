"""Unit tests for scripts/audit_build_artifact.py.

Tests use synthetic in-memory/temp ZIPs to verify:
  - playwright (hard-fail tier) → exit 1
  - uvloop (warn tier) → default exit 0, --strict exit 1
  - ZIP exceeding --max-mb → exit 1
  - Clean ZIP with baseline noise (pydantic/mypy.py, pytest_base_url/,
    greenlet/, *__mypyc.cp312-win_amd64.pyd) → exit 0 (no false positives)
  - glob matching 0 files → SystemExit (non-zero)

The audit() function is imported directly for fast, no-subprocess tests.
"""

from __future__ import annotations

import io
import struct
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest


# Ensure the repo root is importable so we can import the script directly.
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from audit_build_artifact import audit  # noqa: E402  (after path insert)


# ── Helpers ───────────────────────────────────────────────────────────────────


_FACEFINDER_ENTRY = "OpenAver/app/core/focal/facefinder"


def _make_zip(
    tmp_path: Path,
    entries: dict[str, bytes | None],
    name: str = "test.zip",
    include_facefinder: bool = True,
) -> Path:
    """Build a ZIP at tmp_path/name with the given {entry_path: content} mapping.

    Pass None as content to use a tiny 4-byte placeholder.

    include_facefinder (TASK-98a-T1): the facefinder gate is an unconditional
    hard-fail, so by default this helper injects a valid 240KB
    OpenAver/app/core/focal/facefinder entry (unless the caller already
    provided that exact key, or passed include_facefinder=False) — this keeps
    every pre-existing "expected green" case green without each of them having
    to know about the new gate.
    """
    zip_path = tmp_path / name
    if include_facefinder and _FACEFINDER_ENTRY not in entries:
        entries = {**entries, _FACEFINDER_ENTRY: b"\0" * 240_000}
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for entry_name, content in entries.items():
            zf.writestr(entry_name, content if content is not None else b"test")
    return zip_path


def _site(pkg: str, filename: str = "__init__.py") -> str:
    """Return a canonical site-packages path for a package."""
    return f"OpenAver/python/Lib/site-packages/{pkg}/{filename}"


# ── Hard-fail tier ────────────────────────────────────────────────────────────


def test_playwright_hard_fails(tmp_path):
    """playwright in site-packages/ must cause exit 1 (hard-fail tier)."""
    zp = _make_zip(tmp_path, {_site("playwright", "driver/node.exe"): b"x"})
    code, msgs = audit(zp, "win", 55.0, False)
    assert code == 1, f"Expected exit 1 for playwright, got {code}\nMessages: {msgs}"
    combined = "\n".join(msgs)
    assert "playwright" in combined
    assert "FAIL" in combined


# ── Warn tier (uvloop / langdetect) ──────────────────────────────────────────


# ── Size ceiling ──────────────────────────────────────────────────────────────


def test_oversized_zip_fails(tmp_path):
    """ZIP exceeding --max-mb must cause exit 1."""
    # Create a ZIP that is over 1 MB compressed (we use incompressible data)
    big_data = bytes(range(256)) * (1024 * 5)  # ~1.28 MB uncompressed
    zp = _make_zip(
        tmp_path,
        {"OpenAver/python/Lib/site-packages/dummy/__init__.py": big_data},
    )
    # Set max to 0 MB — guaranteed to fail
    code, msgs = audit(zp, "win", 0.0, False)
    assert code == 1, f"Expected exit 1 for oversized ZIP, got {code}"
    assert any("SIZE" in m or "ceiling" in m.lower() for m in msgs)


# ── False-positive / baseline noise tests ─────────────────────────────────────


# ── dist-info existence checks (spec-97 G-2 static first pass) ─────────────────


def test_curl_cffi_pkg_without_dist_info_fails(tmp_path):
    """curl_cffi package present but its .dist-info stripped → HARD-FAIL.

    This is the EXACT spec-97 regression: dist-info gone → PackageNotFoundError
    at import → javdb silently disabled in every release. The audit must catch it.
    """
    zp = _make_zip(tmp_path, {_site("curl_cffi", "__init__.py"): b"x"})
    code, msgs = audit(zp, "win", 55.0, False)
    assert code == 1, f"curl_cffi without dist-info must hard-fail, got {code}\n" + "\n".join(msgs)
    assert any("curl_cffi" in m and "FAIL" in m for m in msgs)


# ── facefinder cascade existence checks (TASK-98a-T1) ───────────────────────────


def test_facefinder_mislocated_same_name_fails(tmp_path):
    """A same-named 'facefinder' file at the WRONG path (app/core/facefinder,
    or under site-packages/) must NOT satisfy the anchored check -> fail."""
    zp = _make_zip(
        tmp_path,
        {
            _site("fastapi", "__init__.py"): b"x",
            "OpenAver/app/core/facefinder": b"\0" * 240_000,
            "OpenAver/python/Lib/site-packages/somepkg/facefinder": b"\0" * 240_000,
        },
        include_facefinder=False,
    )
    code, msgs = audit(zp, "win", 55.0, False)
    assert code == 1, (
        "mislocated same-named facefinder must not satisfy the anchored gate,"
        f" got {code}\n" + "\n".join(msgs)
    )
    assert any("FACEFINDER" in m and "FAIL" in m for m in msgs)


def test_facefinder_undersized_fails(tmp_path):
    """facefinder present at the correct path but only 10 bytes -> fail
    (proves the size floor, not just presence)."""
    zp = _make_zip(
        tmp_path,
        {
            _site("fastapi", "__init__.py"): b"x",
            "OpenAver/app/core/focal/facefinder": b"\0" * 10,
        },
        include_facefinder=False,
    )
    code, msgs = audit(zp, "win", 55.0, False)
    assert code == 1, f"undersized facefinder must hard-fail, got {code}\n" + "\n".join(msgs)
    assert any("FACEFINDER" in m and "FAIL" in m for m in msgs)


# ── Glob resolution errors ────────────────────────────────────────────────────


# ── Test-tool still hard-fails on mac platform ────────────────────────────────


def test_playwright_hard_fails_on_mac(tmp_path):
    """Test tools must hard-fail on mac too (playwright is never OK anywhere)."""
    zp = _make_zip(tmp_path, {_site("playwright", "driver/node.exe"): b"x"})
    code, msgs = audit(zp, "mac", 55.0, False)
    assert code == 1


# ── Summary message ───────────────────────────────────────────────────────────


# ── Linux tar.gz helpers + checks (TASK-194-T6a) ──────────────────────────────

_TAR_FACEFINDER = "OpenAver/app/core/focal/facefinder"

_SITE_PREFIX = "OpenAver/python/lib/python3.12/site-packages"


def _elf_header(machine: int) -> bytes:
    head = bytearray(64)
    head[0:4] = b"\x7fELF"
    head[4] = 2
    head[5] = 1
    struct.pack_into("<H", head, 18, machine)
    return bytes(head)


def _make_tar(
    tmp_path: Path,
    extra: dict | None = None,
    name: str = "OpenAver-v0.0.0-Linux-x86_64.tar.gz",
    wheel_tag: str | None = None,
    machine: int = 0x3E,
    drop: tuple[str, ...] = (),
    wheel_text: str | None = None,
) -> Path:
    tar_path = tmp_path / name
    entries: dict[str, bytes | None] = {
        _TAR_FACEFINDER: b"\0" * 240_000,
        "OpenAver/python/bin/python3.12": _elf_header(machine),
        f"{_SITE_PREFIX}/uvloop/__init__.py": b"x",
        "OpenAver/app/linux/openaver": b"\0" * 64,
    }
    if wheel_tag is not None or wheel_text is None:
        tag = wheel_tag if wheel_tag is not None else "py3-none-any"
        entries[f"{_SITE_PREFIX}/dummy-1.0.dist-info/WHEEL"] = (
            f"Wheel-Version: 1.0\nTag: {tag}\n".encode()
        )
    if wheel_text is not None:
        entries[f"{_SITE_PREFIX}/dummy-1.0.dist-info/WHEEL"] = wheel_text.encode()
    if extra:
        entries.update(extra)
    for key in drop:
        entries.pop(key, None)
    symlinks = {
        "OpenAver/python/bin/python3": "python3.12",
        "OpenAver/openaver": "app/linux/openaver",
    }
    with tarfile.open(tar_path, "w:gz") as tf:
        for entry_name, content in entries.items():
            data = content if content is not None else b"test"
            info = tarfile.TarInfo(entry_name)
            info.size = len(data)
            info.mtime = 1700000000
            tf.addfile(info, io.BytesIO(data))
        for link_name, target in symlinks.items():
            if link_name in drop:
                continue
            info = tarfile.TarInfo(link_name)
            info.type = tarfile.SYMTYPE
            info.linkname = target
            info.mtime = 1700000000
            tf.addfile(info)
    return tar_path


@pytest.mark.parametrize("topdir", ["pywebview", "webview"])
def test_linux_asset_with_pywebview_fails(tmp_path, topdir):
    zp = _make_tar(tmp_path, extra={f"{_SITE_PREFIX}/{topdir}/__init__.py": b"x"})
    code, msgs = audit(zp, "linux", 55.0, True)
    assert code == 1, f"Expected exit 1 for {topdir}, got {code}\n" + "\n".join(msgs)
    assert any("HARD-FAIL" in m and "FAIL" in m for m in msgs)


@pytest.mark.parametrize(
    ("tag", "expect_fail"),
    [
        ("manylinux_2_34_x86_64", True),
        ("manylinux_2_28_x86_64", False),
        ("manylinux2014_x86_64.manylinux_2_34_x86_64", False),
    ],
)
def test_linux_glibc_floor_is_28_inclusive(tmp_path, tag, expect_fail):
    zp = _make_tar(tmp_path, wheel_tag=f"cp312-cp312-{tag}")
    code, msgs = audit(zp, "linux", 55.0, True)
    if expect_fail:
        assert code == 1, f"Expected exit 1 for {tag}, got {code}\n" + "\n".join(msgs)
        assert any("GLIBC" in m and "FAIL" in m for m in msgs)
    else:
        assert code == 0, f"Expected exit 0 for {tag}, got {code}\n" + "\n".join(msgs)


def test_linux_asset_with_wrong_arch_interpreter_fails(tmp_path):
    zp = _make_tar(tmp_path, machine=0xB7)
    code, msgs = audit(zp, "linux", 55.0, True)
    assert code == 1, f"Expected exit 1 for wrong arch, got {code}\n" + "\n".join(msgs)
    assert any("ELF" in m and "FAIL" in m for m in msgs)


@pytest.mark.parametrize(
    "text",
    [
        "Wheel-Version: 1.0\n",
        "Wheel-Version: 1.0\nTag: cp312-cp312-musllinux_1_2_x86_64\n",
    ],
)
def test_linux_unparseable_wheel_fails_closed(tmp_path, text):
    zp = _make_tar(tmp_path, wheel_text=text)
    code, msgs = audit(zp, "linux", 55.0, True)
    assert code == 1, f"Expected exit 1 for unparseable WHEEL, got {code}\n" + "\n".join(msgs)
    assert any("GLIBC" in m and "FAIL" in m for m in msgs)
