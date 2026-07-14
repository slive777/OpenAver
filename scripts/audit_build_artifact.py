"""Build artifact auditor — assert Windows/macOS release ZIPs are clean.

Usage:
    python scripts/audit_build_artifact.py <zip-glob> --platform win|mac [--max-mb N] [--strict]

Exit codes:
    0  — all checks passed (may still print WARN lines for warn-tier packages)
    1  — hard-fail (forbidden test/dev tool found, or ZIP too large)

Matching strategy (CRITICAL — avoids false positives):
    We look for a TOP-LEVEL site-packages/<pkg>/ directory, e.g.:
        OpenAver/python/Lib/site-packages/playwright/...
    We do NOT substring-match raw filenames, so the following baseline noise
    items are intentionally NOT flagged:
        - pydantic/mypy.py          (legit pydantic file, not mypy package)
        - pytest_base_url/          (3 KB transitive, acceptable in baseline)
        - anyio                     (runtime)
        - *__mypyc.cp312-win_amd64.pyd  (compiled runtime module, not mypy)
        - greenlet                  (runtime, never flagged)

Size ceiling (--max-mb, default 55):
    Compressed ZIP size must be <= max_mb.
    Why 55 (not 90):
        - Current baseline (containing uvloop) is ~46 MB compressed.
        - mypy regression was ~58 MB; playwright regression was ~84 MB.
        - 55 MB sits between baseline (46 MB) and the smallest regression
          (mypy 58 MB), catching BOTH regressions while never tripping the
          clean baseline. 90 MB would let playwright (84 MB) slip through.
    After T2 lands (uvloop removed) the ceiling will be tightened to ~48 MB
    in the same follow-up commit that flips uvloop to hard-fail.

Ban-list tiers:
    HARD-FAIL (always non-zero exit, both platforms):
        playwright, mypy, mypyc, pytest, _pytest, ruff, pyee, coverage, twine
    WARN tier (default: WARN only, exit 0; --strict: hard-fail):
        uvloop, langdetect
    Note: uvloop is a VALID runtime dep on macOS — it is excluded from the
    mac ban-list entirely (not even WARN).

Sync point with TASK-80-BUILD-T2:
    T2 adjusts which packages are runtime deps; if it removes uvloop from the
    Windows release, flip uvloop to HARD_FAIL here (same follow-up commit).

dist-info existence check (spec-97 G-2, added in feature/97):
    Two HARD-FAIL checks (both platforms, see _dist_info_check):
      (a) curl_cffi package present ⟹ curl_cffi-*.dist-info/METADATA present.
          The exact spec-97 root cause: build.py used to strip every .dist-info,
          so curl_cffi raised PackageNotFoundError at import → javdb silently
          disabled in every released build. dev-venv tests never caught it.
      (b) At >= 20 top-level packages, dist-info dirs must be >= 50% of packages
          (blanket-strip sanity net; loose ratio, gated so small ZIPs don't trip).
    This static ZIP scan is the CHEAP first pass; it does NOT replace the real
    runtime import sweep (scripts/verify_artifact_imports.py, run on the shipped
    interpreter) — "files present" ≠ "imports clean".

macOS ceiling (spec-97 CD-97-6):
    macOS gets its FIRST audit in feature/97 with --max-mb 60 (not 48): the mac
    ZIP baseline is ~49 MB (v0.10.11 release asset; uvloop is a valid macOS
    runtime dep). 60 = baseline + dist-info (~50) with ~10 MB legit headroom,
    still catching mypy-class (~62) and playwright-class regressions. Windows
    stays at 48 (dist-info adds only ~0.5 MB compressed, ZIP ~35 MB).

facefinder cascade existence check (TASK-98a-T1, added in feature/98):
    ONE HARD-FAIL check (both platforms, see _facefinder_check), unconditional
    and positive (unlike curl_cffi's conditional check): app/core/focal/facefinder
    must always be present and >= 200,000 uncompressed bytes (real cascade is
    239,632 bytes). Both build scripts recursively copy core/ into the artifact,
    so the cascade is never legitimately absent — a missing/truncated cascade
    means detect_focal() silently returns None forever in the released build
    (dev-only blind spot: the feature/97 import sweep never imports core.focal,
    and the lazy classifier singleton only opens the cascade on first real use).
    The match is anchored to the exact release path so a same-named file
    elsewhere (app/core/facefinder, site-packages/x/facefinder) does not
    satisfy the check.
"""

from __future__ import annotations

import argparse
import glob
import re
import sys
import zipfile
from pathlib import Path

# Matches site-packages/curl_cffi-<ver>.dist-info/METADATA anywhere in the ZIP.
_CURL_CFFI_METADATA_RE = re.compile(r"site-packages/curl_cffi-[^/]+\.dist-info/METADATA$")

# Matches the packaged focal-crop cascade at its EXACT anchored release path
# (feature/98 TASK-98a-T1). Anchored to app/core/focal/facefinder so a
# same-named file elsewhere (app/core/facefinder, site-packages/x/facefinder)
# does NOT satisfy the check.
_FACEFINDER_RE = re.compile(r"(^|/)app/core/focal/facefinder$")

# Real cascade is 239,632 bytes; guard against an empty/truncated stand-in.
_FACEFINDER_MIN_BYTES = 200_000

# Top-level scale at/above which the dist-info ratio sanity net engages. Real
# artifacts bundle ~50 packages; synthetic test ZIPs stay well below this.
_DIST_INFO_SCALE_GATE = 20


# ── Ban-list definition ──────────────────────────────────────────────────────

# Packages that must NEVER appear in a release ZIP (test/dev tools).
# Match on site-packages/<pkg>/ top-level directory prefix.
HARD_FAIL_PKGS: frozenset[str] = frozenset(
    [
        "playwright",
        "mypy",
        "mypyc",
        "pytest",
        "_pytest",
        "ruff",
        "pyee",
        "coverage",
        "twine",
    ]
)

# Packages that should not be in the ZIP but whose presence is not
# release-blocking until explicitly enabled via --strict.
# IMPORTANT: uvloop is a valid macOS runtime dep — it is excluded from
# WARN_PKGS when platform == "mac" (see _get_warn_pkgs()).
WARN_PKGS_ALL_PLATFORMS: frozenset[str] = frozenset(["uvloop", "langdetect"])

# Packages that are VALID on macOS — do not warn/fail for them.
MAC_RUNTIME_ALLOWLIST: frozenset[str] = frozenset(["uvloop"])


def _get_warn_pkgs(platform: str) -> frozenset[str]:
    """Return the warn-tier set for the given platform."""
    if platform == "mac":
        return WARN_PKGS_ALL_PLATFORMS - MAC_RUNTIME_ALLOWLIST
    return WARN_PKGS_ALL_PLATFORMS


# ── Core audit logic (importable) ────────────────────────────────────────────


def _site_packages_top_dirs(zf: zipfile.ZipFile) -> set[str]:
    """Extract the set of top-level package directory names inside any
    site-packages/ path within the ZIP.

    A name is included only when it appears as an IMMEDIATE child directory
    of site-packages/, e.g.:
        .../site-packages/playwright/   → "playwright"
        .../site-packages/pydantic/mypy.py → NOT matched (pydantic, not mypy)
        .../site-packages/pytest_base_url/__init__.py → "pytest_base_url"

    We do NOT do substring matching on raw file paths.
    """
    top_dirs: set[str] = set()
    for entry in zf.infolist():
        name = entry.filename
        # Find the site-packages/ segment
        idx = name.find("site-packages/")
        if idx == -1:
            continue
        after = name[idx + len("site-packages/"):]
        if not after:
            continue
        # Grab the first path component after site-packages/
        pkg = after.split("/")[0]
        if pkg:
            top_dirs.add(pkg)
    return top_dirs


def _dist_info_check(zf: zipfile.ZipFile, top_dirs: set[str]) -> list[str]:
    """Return HARD-FAIL messages for missing .dist-info metadata (spec-97 G-2).

    Two platform-agnostic checks — both hard-fail (never warn-tier):

    (a) curl_cffi named check (conditional on the package shipping): if the
        curl_cffi PACKAGE dir is present but no curl_cffi-*.dist-info/METADATA
        exists, that is the EXACT spec-97 regression — curl_cffi reads its own
        metadata at import, so a stripped dist-info raises PackageNotFoundError,
        silently disabling the javdb scraper in every release.

    (b) Scale sanity net: at real-artifact scale (>= _DIST_INFO_SCALE_GATE
        top-level package dirs), the dist-info dir count must be >= half the
        package count. Catches a future blanket dist-info strip. A loose 50%
        ratio avoids brittle coupling to exact transitive-dependency counts;
        the gate keeps small synthetic ZIPs from tripping it.
    """
    messages: list[str] = []
    dist_info_dirs = {n for n in top_dirs if n.endswith(".dist-info")}
    packages = {n for n in top_dirs if not n.endswith((".dist-info", ".data"))}

    # (a) curl_cffi — the named root cause.
    if "curl_cffi" in packages:
        has_metadata = any(_CURL_CFFI_METADATA_RE.search(n) for n in zf.namelist())
        if not has_metadata:
            messages.append(
                "[FAIL] DIST-INFO: curl_cffi package present but its"
                " *.dist-info/METADATA is missing — this is the exact spec-97"
                " regression (curl_cffi raises PackageNotFoundError at import,"
                " silently disabling javdb). The build must NOT strip .dist-info."
            )

    # (b) Blanket-strip sanity net (only at real-artifact scale).
    if len(packages) >= _DIST_INFO_SCALE_GATE and len(dist_info_dirs) < len(packages) / 2:
        messages.append(
            f"[FAIL] DIST-INFO: only {len(dist_info_dirs)} .dist-info dirs for"
            f" {len(packages)} top-level packages (< 50%) — looks like a blanket"
            f" .dist-info strip regression (spec-97). Keep dist-info in the build."
        )

    return messages


def _facefinder_check(zf: zipfile.ZipFile) -> list[str]:
    """Return HARD-FAIL messages for a missing/undersized focal-crop cascade
    (TASK-98a-T1, feature/98).

    Unlike the curl_cffi dist-info check, this tier is POSITIVE and
    UNCONDITIONAL: app/core/focal/facefinder must always be present and
    >= _FACEFINDER_MIN_BYTES uncompressed, on every platform. Both
    build.py and build_macos.py recursively copy core/ into the artifact,
    so the cascade is never expected to be legitimately absent — a missing
    or truncated cascade means detect_focal() will silently return None
    forever in the released build (a dev-only blind spot: the feature/97
    import sweep never imports core.focal, and the lazy classifier
    singleton only opens the cascade on the first real detect_focal call).
    """
    messages: list[str] = []
    match = next((n for n in zf.namelist() if _FACEFINDER_RE.search(n)), None)
    if match is None:
        messages.append(
            "[FAIL] FACEFINDER: app/core/focal/facefinder not found in the"
            " ZIP — the focal-crop cascade is missing from the release"
            " artifact. detect_focal() will silently return None forever"
            " (cascade open() raises, caught and logged, callers fall back"
            " to right-crop) — this is a release-blocking regression, not"
            " a soft failure."
        )
        return messages

    size = zf.getinfo(match).file_size
    if size < _FACEFINDER_MIN_BYTES:
        messages.append(
            f"[FAIL] FACEFINDER: app/core/focal/facefinder is only {size}"
            f" bytes (< {_FACEFINDER_MIN_BYTES} minimum; real cascade is"
            f" 239,632 bytes) — looks empty or truncated."
        )
    return messages


def audit(
    zip_path: str | Path,
    platform: str,
    max_mb: float,
    strict: bool,
) -> tuple[int, list[str]]:
    """Audit a single ZIP file.

    Returns (exit_code, messages).
    exit_code 0 = pass (may include WARN lines).
    exit_code 1 = hard-fail.

    Raises FileNotFoundError if zip_path does not exist.
    """
    zip_path = Path(zip_path)
    messages: list[str] = []
    failed = False

    # ── Size check ────────────────────────────────────────────────────────────
    compressed_mb = zip_path.stat().st_size / (1024 * 1024)
    messages.append(
        f"[SIZE] Compressed ZIP size: {compressed_mb:.1f} MB"
        f" (ceiling: {max_mb} MB, uses <= semantics)"
    )
    if compressed_mb > max_mb:
        messages.append(
            f"[FAIL] ZIP exceeds size ceiling:"
            f" {compressed_mb:.1f} MB > {max_mb} MB"
        )
        failed = True
    else:
        messages.append(
            f"[OK  ] Size within ceiling ({compressed_mb:.1f} MB <= {max_mb} MB)"
        )

    # ── Package scan ──────────────────────────────────────────────────────────
    warn_pkgs = _get_warn_pkgs(platform)

    with zipfile.ZipFile(zip_path) as zf:
        top_dirs = _site_packages_top_dirs(zf)
        dist_info_msgs = _dist_info_check(zf, top_dirs)
        facefinder_msgs = _facefinder_check(zf)

    messages.append(
        f"[INFO] Scanned {zip_path.name} — platform={platform},"
        f" strict={strict}, found {len(top_dirs)} top-level site-packages dirs"
    )

    # ── dist-info existence (spec-97 G-2 static first pass; both platforms) ────
    if dist_info_msgs:
        messages.extend(dist_info_msgs)
        failed = True

    # ── facefinder cascade existence (TASK-98a-T1; both platforms) ─────────────
    if facefinder_msgs:
        messages.extend(facefinder_msgs)
        failed = True

    # Hard-fail tier
    for pkg in sorted(HARD_FAIL_PKGS):
        if pkg in top_dirs:
            messages.append(
                f"[FAIL] HARD-FAIL: forbidden package '{pkg}' found in"
                f" site-packages/ — test/dev tool must not be in release ZIP"
            )
            failed = True

    # Warn tier
    for pkg in sorted(warn_pkgs):
        if pkg in top_dirs:
            if strict:
                messages.append(
                    f"[FAIL] STRICT: warn-tier package '{pkg}' found in"
                    f" site-packages/ — hard-fail because --strict is active"
                    f" (T2 will remove this package entirely)"
                )
                failed = True
            else:
                messages.append(
                    f"\033[33m[WARN] warn-tier package '{pkg}' found in"
                    f" site-packages/ — not release-blocking yet"
                    f" (will hard-fail after T2 lands)\033[0m"
                )

    # Summary
    if failed:
        messages.append(
            f"[RESULT] FAILED — {zip_path.name} did not pass artifact audit."
        )
    else:
        messages.append(
            f"[RESULT] PASSED — {zip_path.name} is clean (exit 0)."
        )

    return (1 if failed else 0, messages)


# ── CLI entry point ───────────────────────────────────────────────────────────


def _resolve_zip(pattern: str) -> Path:
    """Resolve a glob pattern to exactly one ZIP path, or raise SystemExit."""
    matches = glob.glob(pattern)
    if len(matches) == 0:
        print(f"[ERROR] No ZIP files matched glob pattern: {pattern!r}", file=sys.stderr)
        sys.exit(1)
    if len(matches) > 1:
        print(
            f"[ERROR] Glob pattern {pattern!r} matched {len(matches)} files;"
            f" expected exactly 1:\n  " + "\n  ".join(matches),
            file=sys.stderr,
        )
        sys.exit(1)
    return Path(matches[0])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit a release ZIP for forbidden packages and size.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "zip_glob",
        metavar="<zip-glob>",
        help="Glob pattern for the ZIP file (must match exactly 1 file).",
    )
    parser.add_argument(
        "--platform",
        choices=["win", "mac"],
        required=True,
        help="Target platform: win or mac. Affects uvloop warn/allowlist.",
    )
    parser.add_argument(
        "--max-mb",
        type=float,
        default=55.0,
        metavar="N",
        help=(
            "Maximum compressed ZIP size in MB (default: 55). "
            "Why 55: baseline ~46 MB; mypy regression ~58 MB; playwright ~84 MB. "
            "55 catches both regressions without tripping the clean baseline."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help=(
            "Treat warn-tier packages (uvloop, langdetect) as hard-fail. "
            "Enable this after T2 lands (uvloop removed from Windows build)."
        ),
    )
    args = parser.parse_args(argv)

    zip_path = _resolve_zip(args.zip_glob)
    exit_code, messages = audit(zip_path, args.platform, args.max_mb, args.strict)
    for msg in messages:
        print(msg)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
