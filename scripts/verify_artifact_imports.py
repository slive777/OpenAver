#!/usr/bin/env python3
"""Verify a packaged OpenAver artifact can import every bundled top-level package.

Runs ON the artifact's OWN interpreter (Windows embedded ``python.exe`` /
macOS ``python/bin/python3``), so it MUST be stdlib-only and layout-agnostic
(Windows ``Lib/site-packages`` vs macOS ``lib/pythonX.Y/site-packages``).

Why this guard exists (spec-97 G-2):
    ``build.py``/``build_macos.py`` used to strip every ``*.dist-info`` to save
    ~0.5 MB. ``curl_cffi.__init__`` reads its own metadata at import time
    (``importlib.metadata.metadata("curl_cffi")``); with dist-info gone that
    raised ``PackageNotFoundError`` (an ``ImportError`` subclass), which
    ``core/scrapers/javdb.py`` swallowed via ``except ImportError`` — silently
    disabling javdb in EVERY released Windows/macOS build. Dev-venv tests never
    caught it because the venv keeps its dist-info. This sweep imports every
    bundled package using the SHIPPED interpreter, so such breakage fails the
    build (wired into CI as a release gate — see build.yml verify jobs).

Usage:
    <artifact>/python/python.exe scripts/verify_artifact_imports.py [--skip pkg ...] [--strict]

Exit codes:
    0 — every discovered top-level package imported cleanly.
    1 — at least one import failed (list printed), OR no site-packages was found
        on sys.path (guards against a false-green run on the wrong interpreter),
        OR ``--strict`` and pymediainfo's native library failed ``can_parse()``.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

# Directory / file names that are not importable top-level packages.
_SKIP_DIRS = {"__pycache__", "bin", "Scripts"}
_SKIP_SUFFIXES = (".dist-info", ".data")
_EXT_SUFFIXES = (".pyd", ".so")

# 每一項都必須回答：「它不在的話，哪個使用者可見功能會靜默死掉？」
# 判準見 plan-120d.md CD-120d-11——不是「這個模組很重要」。
# ctypes 沒被列進 sweep 就完全沒人驗——既有 sweep 只掃 site-packages
# 的頂層套件，stdlib 一個都不碰。
_STDLIB_SWEEP = [
    "ctypes",  # 缺 ctypes 時 windows/standalone.py 的
               # WebView2 提示彈窗（_win_message_box）與剪貼簿寫入整段炸開，
               # 被 _ensure_webview2_runtime() 的 except Exception 吞掉、
               # sys.exit(0)——使用者雙擊 OpenAver.bat 後畫面上什麼都不會
               # 出現（pythonw.exe 無 console），只有 debug.log 一行
               # warning。這正是 Bug B 的整支修復會失效的那個洞。
]


def _site_packages_dirs() -> list[Path]:
    """Return every ``site-packages`` directory on this interpreter's sys.path.

    Layout-agnostic: we do not hardcode ``Lib/`` vs ``lib/pythonX.Y/`` — we trust
    the shipped interpreter's own resolved sys.path (the artifact ``._pth`` /
    site config puts its site-packages there).
    """
    seen: set[Path] = set()
    dirs: list[Path] = []
    for entry in sys.path:
        if not entry:
            continue
        p = Path(entry)
        if p.name == "site-packages" and p.is_dir():
            rp = p.resolve()
            if rp not in seen:
                seen.add(rp)
                dirs.append(p)
    return dirs


def _top_level_modules(sp_dir: Path) -> tuple[list[str], list[str]]:
    """Collect importable top-level module names inside one site-packages dir.

    Returns (names, skipped) where ``skipped`` lists non-identifier entries
    (namespace dirs, hyphenated names) recorded for transparency.
    """
    names: set[str] = set()
    skipped: list[str] = []
    for entry in sorted(sp_dir.iterdir()):
        name = entry.name
        if name in _SKIP_DIRS or name.endswith(_SKIP_SUFFIXES):
            continue
        if entry.is_dir():
            if (entry / "__init__.py").is_file():
                mod = name
            else:
                continue  # namespace pkg / data dir — not counted
        elif name.endswith(_EXT_SUFFIXES):
            mod = name.split(".")[0]  # _cffi_backend.cp312-win_amd64.pyd -> _cffi_backend
        elif name.endswith(".py"):
            if name == "__init__.py":
                continue
            mod = entry.stem
        else:
            continue
        if not mod.isidentifier():
            skipped.append(name)
            continue
        names.add(mod)
    return sorted(names), skipped


def _import_sweep(names: list[str]) -> list[tuple[str, str, str]]:
    """Try importing each name; return (name, exc_type, exc_msg) for failures.

    Shared by both the site-packages sweep and the stdlib sweep so there is
    exactly one fail-collection code path feeding main()'s final exit code.
    """
    fails: list[tuple[str, str, str]] = []
    for name in names:
        try:
            importlib.import_module(name)
        except BaseException as exc:  # noqa: BLE001 — a sweep must catch everything
            fails.append((name, type(exc).__name__, str(exc)))
    return fails


def _probe_ctypes_windll_user32() -> tuple[str, str, str] | None:
    """Windows-only probe of ctypes.windll.user32 (CD-120d-11).

    1. ``windll`` 這個屬性只在 ``os.name == "nt"`` 下才存在——同時是
       「這確實是 Windows 直譯器」的斷言；
    2. 它會真的走一次 ``LibraryLoader → WinDLL → LoadLibrary`` 把一個真實
       DLL 載進來，而 ``import ctypes`` 本身不走這條路徑。
    邊際偵測價值小但非零：``import ctypes`` 成功卻 ``windll.user32`` 失敗
    ＝ 系統壞了、不是 build 壞了。
    """
    if sys.platform != "win32":
        print("SKIP  ctypes.windll.user32 (non-Windows, contract is Windows-only)")
        return None
    import ctypes

    try:
        ctypes.windll.user32  # noqa: B018 — attribute access is the probe itself
    except Exception as exc:
        return ("ctypes.windll.user32", type(exc).__name__, str(exc))
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import every bundled top-level package using the artifact's own interpreter.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--skip",
        action="append",
        default=[],
        metavar="PKG",
        help="Top-level module name to skip (repeatable). Use only for a "
        "documented platform-specific special case; prints a SKIP line.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Also require pymediainfo.MediaInfo.can_parse() (build/CI only). "
        "Without this flag a missing native library prints [WARN] and exits 0.",
    )
    args = parser.parse_args(argv)
    skip = set(args.skip)

    print(f"[INFO] interpreter: {sys.executable}")
    sp_dirs = _site_packages_dirs()
    if not sp_dirs:
        print(
            "[FAIL] no site-packages directory found on sys.path — "
            "is this the artifact's own interpreter? (false-green guard)",
            file=sys.stderr,
        )
        return 1

    modules: set[str] = set()
    for sp in sp_dirs:
        print(f"[INFO] site-packages: {sp}")
        names, skipped = _top_level_modules(sp)
        modules.update(names)
        for s in skipped:
            print(f"SKIP  {s} (not an import name)")

    names_to_import: list[str] = []
    for mod in sorted(modules):
        if mod in skip:
            print(f"SKIP  {mod} (--skip)")
            continue
        names_to_import.append(mod)
    fails = _import_sweep(names_to_import)

    scanned = len(modules) - len(skip & modules)
    print(f"TOTAL {scanned} FAILS {len(fails)}")
    for mod, exc_type, msg in fails:
        print(f"FAIL  {mod}: {exc_type}: {msg}")

    stdlib_fails = _import_sweep(list(_STDLIB_SWEEP))
    stdlib_failed_names = {name for name, _, _ in stdlib_fails}
    if "ctypes" not in stdlib_failed_names:
        probe_fail = _probe_ctypes_windll_user32()
        if probe_fail is not None:
            stdlib_fails.append(probe_fail)
    print(f"[STDLIB] TOTAL {len(_STDLIB_SWEEP)} FAILS {len(stdlib_fails)}")
    for mod, exc_type, msg in stdlib_fails:
        print(f"FAIL[stdlib]  {mod}: {exc_type}: {msg}")
    fails.extend(stdlib_fails)

    if scanned == 0:
        # A real artifact bundles ~50 packages; zero attempted imports means the
        # sweep found a site-packages dir but nothing importable in it (e.g. a
        # build that stripped every package). Never a legitimate GREEN.
        print(
            "[FAIL] 0 packages attempted — site-packages present but empty of "
            "importable modules (false-green guard)",
            file=sys.stderr,
        )
        return 1

    if fails:
        return 1

    # pymediainfo：import 成功不代表原生庫載得起來（BE-BUILD-03）。
    # import 放函式內 + try/except，維持本腳本 stdlib-only 預設路徑。
    try:
        from pymediainfo import MediaInfo as _MediaInfo
    except ImportError as exc:
        print(f"FAIL  pymediainfo: ImportError: {exc}")
        return 1
    if not _MediaInfo.can_parse():
        msg = "pymediainfo.MediaInfo.can_parse() is False — native libmediainfo unavailable"
        if args.strict:
            print(f"FAIL  {msg}")
            return 1
        print(f"[WARN] {msg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
