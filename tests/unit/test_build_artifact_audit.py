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
import sys
import zipfile
from pathlib import Path

import pytest

# Ensure the repo root is importable so we can import the script directly.
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from audit_build_artifact import audit, _resolve_zip  # noqa: E402  (after path insert)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_zip(tmp_path: Path, entries: dict[str, bytes | None], name: str = "test.zip") -> Path:
    """Build a ZIP at tmp_path/name with the given {entry_path: content} mapping.

    Pass None as content to use a tiny 4-byte placeholder.
    """
    zip_path = tmp_path / name
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


def test_mypy_hard_fails(tmp_path):
    """mypy in site-packages/ must cause exit 1 (hard-fail tier)."""
    zp = _make_zip(tmp_path, {_site("mypy", "__init__.py"): b"x"})
    code, msgs = audit(zp, "win", 55.0, False)
    assert code == 1
    assert any("mypy" in m and "FAIL" in m for m in msgs)


def test_pytest_hard_fails(tmp_path):
    """pytest in site-packages/ must cause exit 1 (hard-fail tier)."""
    zp = _make_zip(tmp_path, {_site("pytest", "__init__.py"): b"x"})
    code, msgs = audit(zp, "win", 55.0, False)
    assert code == 1


def test_ruff_hard_fails(tmp_path):
    """ruff in site-packages/ must cause exit 1 (hard-fail tier)."""
    zp = _make_zip(tmp_path, {_site("ruff", "__main__.py"): b"x"})
    code, msgs = audit(zp, "win", 55.0, False)
    assert code == 1


# ── Warn tier (uvloop / langdetect) ──────────────────────────────────────────


def test_uvloop_default_warns_exits_0_on_win(tmp_path):
    """uvloop on win default mode → exit 0 (warn only, not release-blocking)."""
    zp = _make_zip(tmp_path, {_site("uvloop", "loop.cpython-312-x86_64-linux-gnu.so"): b"x"})
    code, msgs = audit(zp, "win", 55.0, False)
    assert code == 0, f"Expected exit 0 for uvloop default, got {code}\nMessages: {msgs}"
    combined = "\n".join(msgs)
    assert "WARN" in combined or "warn" in combined.lower()


def test_uvloop_strict_exits_1_on_win(tmp_path):
    """uvloop on win with --strict → exit 1."""
    zp = _make_zip(tmp_path, {_site("uvloop", "loop.cpython-312-x86_64-linux-gnu.so"): b"x"})
    code, msgs = audit(zp, "win", 55.0, True)
    assert code == 1, f"Expected exit 1 for uvloop --strict, got {code}\nMessages: {msgs}"


def test_uvloop_allowed_on_mac_default(tmp_path):
    """uvloop is a valid macOS runtime dep — must NOT be flagged on mac."""
    zp = _make_zip(tmp_path, {_site("uvloop", "__init__.py"): b"x"})
    code, msgs = audit(zp, "mac", 55.0, False)
    assert code == 0, f"uvloop must be allowed on mac (default), got {code}\nMessages: {msgs}"
    combined = "\n".join(msgs)
    # Should not even warn about uvloop on mac — no mention at all
    assert "uvloop" not in combined, f"uvloop must not be flagged on mac, got: {combined}"


def test_uvloop_allowed_on_mac_strict(tmp_path):
    """uvloop is a valid macOS runtime dep — must NOT be flagged even with --strict on mac."""
    zp = _make_zip(tmp_path, {_site("uvloop", "__init__.py"): b"x"})
    code, msgs = audit(zp, "mac", 55.0, True)
    assert code == 0, f"uvloop must be allowed on mac --strict, got {code}\nMessages: {msgs}"


def test_langdetect_default_warns_exits_0(tmp_path):
    """langdetect on win default mode → exit 0 (warn only)."""
    zp = _make_zip(tmp_path, {_site("langdetect", "__init__.py"): b"x"})
    code, msgs = audit(zp, "win", 55.0, False)
    assert code == 0


def test_langdetect_strict_exits_1(tmp_path):
    """langdetect on win --strict → exit 1."""
    zp = _make_zip(tmp_path, {_site("langdetect", "__init__.py"): b"x"})
    code, msgs = audit(zp, "win", 55.0, True)
    assert code == 1


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


def test_exactly_at_ceiling_passes(tmp_path):
    """ZIP at exactly max_mb must pass (we use <= semantics)."""
    zp = _make_zip(tmp_path, {"OpenAver/file.txt": b"hello"})
    compressed_mb = zp.stat().st_size / (1024 * 1024)
    # Set max exactly to the compressed size (rounded up a tiny bit)
    code, msgs = audit(zp, "win", compressed_mb + 0.001, False)
    assert code == 0, f"ZIP at/below ceiling must pass: {msgs}"


# ── False-positive / baseline noise tests ─────────────────────────────────────


def test_clean_zip_with_baseline_noise_passes(tmp_path):
    """Clean ZIP containing only runtime packages and baseline noise must exit 0.

    Noise items that must NOT trigger false positives:
      - pydantic/mypy.py          (legit pydantic file, not mypy package)
      - pytest_base_url/__init__.py  (acceptable 3KB transitive)
      - greenlet/__init__.py      (runtime, must not be flagged)
      - somemod__mypyc.cp312-win_amd64.pyd  (compiled runtime, not mypy)
    """
    entries = {
        # Real runtime packages
        _site("fastapi", "__init__.py"): b"x",
        _site("uvicorn", "__init__.py"): b"x",
        _site("pydantic", "__init__.py"): b"x",
        _site("starlette", "__init__.py"): b"x",
        _site("httptools", "__init__.py"): b"x",
        _site("watchfiles", "__init__.py"): b"x",
        _site("greenlet", "__init__.py"): b"x",
        _site("anyio", "__init__.py"): b"x",
        # Baseline noise — must NOT be false-positived
        "OpenAver/python/Lib/site-packages/pydantic/mypy.py": b"x",  # NOT mypy pkg
        "OpenAver/python/Lib/site-packages/pytest_base_url/__init__.py": b"x",  # tiny transitive
        # mypyc compiled runtime module (not the mypy package)
        "OpenAver/python/Lib/site-packages/somemod__mypyc.cp312-win_amd64.pyd": b"x",
    }
    zp = _make_zip(tmp_path, entries)
    code, msgs = audit(zp, "win", 55.0, False)
    assert code == 0, f"Clean baseline ZIP must pass.\nMessages:\n" + "\n".join(msgs)


def test_pydantic_mypy_file_not_flagged(tmp_path):
    """pydantic/mypy.py is a file INSIDE pydantic, not the mypy package.
    It must NOT trigger the mypy ban."""
    entries = {
        "OpenAver/python/Lib/site-packages/pydantic/mypy.py": b"x",
        "OpenAver/python/Lib/site-packages/pydantic/__init__.py": b"x",
    }
    zp = _make_zip(tmp_path, entries)
    code, msgs = audit(zp, "win", 55.0, False)
    assert code == 0, (
        "pydantic/mypy.py must not trigger mypy ban (it's a pydantic file).\n"
        + "\n".join(msgs)
    )


def test_greenlet_not_flagged(tmp_path):
    """greenlet is a runtime dep and must never be flagged."""
    entries = {_site("greenlet", "__init__.py"): b"x"}
    zp = _make_zip(tmp_path, entries)
    code, msgs = audit(zp, "win", 55.0, True)  # even with --strict
    assert code == 0, f"greenlet must not be flagged:\n" + "\n".join(msgs)


def test_mypyc_pyd_at_root_not_flagged(tmp_path):
    """A *__mypyc.cp312-win_amd64.pyd file at site-packages ROOT (not in a
    mypy/ subdirectory) represents a compiled runtime extension, not the mypy
    package. It must not trigger the ban."""
    # This file sits directly in site-packages/ with a mypyc-compiled name
    entries = {
        "OpenAver/python/Lib/site-packages/pydantic_core__mypyc.cp312-win_amd64.pyd": b"x",
        _site("pydantic_core", "__init__.py"): b"x",
    }
    zp = _make_zip(tmp_path, entries)
    code, msgs = audit(zp, "win", 55.0, False)
    assert code == 0, (
        "mypyc-compiled .pyd at site-packages root must not trigger mypy ban.\n"
        + "\n".join(msgs)
    )


def test_pytest_base_url_not_flagged(tmp_path):
    """pytest_base_url (acceptable pre-existing 3KB transitive) must not trip the audit."""
    entries = {
        "OpenAver/python/Lib/site-packages/pytest_base_url/__init__.py": b"x",
    }
    zp = _make_zip(tmp_path, entries)
    code, msgs = audit(zp, "win", 55.0, False)
    assert code == 0, (
        "pytest_base_url must not be flagged (it's not in the hard-fail list).\n"
        + "\n".join(msgs)
    )


# ── Glob resolution errors ────────────────────────────────────────────────────


def test_glob_no_match_exits_nonzero(tmp_path):
    """Glob pattern matching 0 files must raise SystemExit with non-zero code."""
    pattern = str(tmp_path / "nonexistent_*.zip")
    with pytest.raises(SystemExit) as exc_info:
        _resolve_zip(pattern)
    assert exc_info.value.code != 0


def test_glob_multiple_matches_exits_nonzero(tmp_path):
    """Glob pattern matching >1 file must raise SystemExit with non-zero code."""
    _make_zip(tmp_path, {"a.txt": b"x"}, name="foo-Windows-x64.zip")
    _make_zip(tmp_path, {"b.txt": b"x"}, name="bar-Windows-x64.zip")
    pattern = str(tmp_path / "*-Windows-*.zip")
    with pytest.raises(SystemExit) as exc_info:
        _resolve_zip(pattern)
    assert exc_info.value.code != 0


# ── Test-tool still hard-fails on mac platform ────────────────────────────────


def test_playwright_hard_fails_on_mac(tmp_path):
    """Test tools must hard-fail on mac too (playwright is never OK anywhere)."""
    zp = _make_zip(tmp_path, {_site("playwright", "driver/node.exe"): b"x"})
    code, msgs = audit(zp, "mac", 55.0, False)
    assert code == 1


# ── Summary message ───────────────────────────────────────────────────────────


def test_summary_line_present_on_pass(tmp_path):
    """Audit result must always include a RESULT/summary line on pass."""
    zp = _make_zip(tmp_path, {_site("fastapi", "__init__.py"): b"x"})
    code, msgs = audit(zp, "win", 55.0, False)
    assert any("RESULT" in m or "PASSED" in m for m in msgs)


def test_summary_line_present_on_fail(tmp_path):
    """Audit result must always include a RESULT/summary line on fail."""
    zp = _make_zip(tmp_path, {_site("playwright", "driver/node.exe"): b"x"})
    code, msgs = audit(zp, "win", 55.0, False)
    assert any("RESULT" in m or "FAILED" in m for m in msgs)
