"""Behavior of the shared Linux Python slimming entry point."""

import os
from pathlib import Path
import subprocess


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/slim_linux_python.sh"
DELETE = {
    "lib/libpython3.12.so", "lib/libpython3.12.so.1.0", "lib/libpython3.so",
    "lib/libtcl9.so", "lib/tcl9.0", "lib/tcl9.0/init.tcl", "lib/tk9.0",
    "lib/tk9.0/init.tcl", "lib/itcl4", "lib/itcl4/init.tcl", "lib/thread2",
    "lib/thread2/init.tcl", "lib/python3.12/tkinter", "lib/python3.12/tkinter/__init__.py",
    "lib/python3.12/lib-dynload/_tkinter.so", "lib/python3.12/ensurepip",
    "lib/python3.12/ensurepip/__init__.py", "lib/python3.12/idlelib",
    "lib/python3.12/idlelib/__init__.py", "lib/python3.12/site-packages/pip",
    "lib/python3.12/site-packages/pip/__init__.py", "include", "include/python.h",
    "share/terminfo", "share/terminfo/entry", "bin/pip", "bin/pip3", "bin/pip3.12",
    "bin/idle3", "bin/idle3.12",
}
KEEP_FILES = {
    "bin/python3.12", "bin/2to3", "bin/pydoc3", "bin/python3.12-config",
    "bin/python3-config", "lib/pkgconfig/python.pc", "share/man/python.1",
    "lib/python3.12/unittest/__init__.py", "lib/python3.12/lib2to3/__init__.py",
    "lib/python3.12/test/__init__.py", "lib/python3.12/turtledemo/__init__.py",
    "lib/python3.12/config-3.12/Makefile",
    "lib/python3.12/site-packages/pip-26.2.1.dist-info/METADATA",
    "lib/python3.12/site-packages/curl_cffi-0.0.0.dist-info/METADATA",
    "lib/python3.12/site-packages/curl_cffi/_wrapper.abi3.so",
    "lib/python3.12/site-packages/pillow.libs/libjpeg.so.6",
}


def _tree(root):
    links = {"lib/libpython3.12.so": "libpython3.12.so.1.0", "bin/idle3": "missing-idle"}
    for name in (DELETE | KEEP_FILES) - links.keys():
        path = root / name
        if any(other.startswith(name + "/") for other in DELETE | KEEP_FILES):
            path.mkdir(parents=True, exist_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
    for name, target in links.items():
        (root / name).symlink_to(target)


def _paths(root):
    return {str((Path(base) / name).relative_to(root))
            for base, dirs, files in os.walk(root, followlinks=False)
            for name in dirs + files if os.path.lexists(Path(base) / name)}


def _run(root, tmp_path):
    stub = tmp_path / "strip-stub"
    stub.write_text('#!/bin/sh\nfor arg do\n  case "$arg" in -*) ;; *) printf "%s\\n" "$arg" >> "$LOG" ;; esac\ndone\n')
    stub.chmod(0o755)
    log = tmp_path / (root.name + ".log")
    result = subprocess.run(["bash", str(SCRIPT), str(root), str(stub)],
                            env={**os.environ, "LOG": str(log)}, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return {str(Path(line).relative_to(root)) for line in log.read_text().splitlines()}


def test_slim_removes_only_listed_paths(tmp_path):
    root = tmp_path / "python"
    _tree(root)
    before = _paths(root)
    expected_strip = {p for p in before if p.startswith("lib/") and not (root / p).is_symlink()
                      and (p.endswith(".so") or ".so." in Path(p).name) and (root / p).is_file()}
    stripped = _run(root, tmp_path)
    after = _paths(root)
    assert before - after == DELETE
    assert KEEP_FILES <= after
    assert {p for p in before if ".dist-info" in p} <= after
    assert stripped == expected_strip
    assert stripped and "lib/python3.12/site-packages/curl_cffi/_wrapper.abi3.so" in stripped
    assert "lib/python3.12/site-packages/pillow.libs/libjpeg.so.6" in stripped
    assert "bin/python3.12" not in stripped
    _run(root, tmp_path)
    assert _paths(root) == after


def test_slim_same_result_for_both_arch_dirs(tmp_path):
    results = []
    for name in ("python-x86_64", "python-aarch64"):
        root = tmp_path / name
        _tree(root)
        before = _paths(root)
        stripped = _run(root, tmp_path)
        results.append((before - _paths(root), stripped))
    assert results[0] == results[1]
    assert results[0][0] and results[0][1]
