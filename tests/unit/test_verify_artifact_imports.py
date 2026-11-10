"""Unit tests for scripts/verify_artifact_imports.py (TASK-120d-T3).

The script itself is stdlib-only (runs on the artifact interpreter). These
tests import it the same way test_build_artifact_audit.py imports its script.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

import verify_artifact_imports as vai  # noqa: E402


def _patch_usable_site_packages(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make main() see a site-packages dir with one always-importable name.

    ``json`` is stdlib, so the site-packages sweep succeeds without touching
    a real venv package (keeps these tests independent of third-party health).
    """
    monkeypatch.setattr(vai, "_site_packages_dirs", lambda: [Path("/fake/site-packages")])
    monkeypatch.setattr(vai, "_top_level_modules", lambda _sp: (["json"], []))


# ── DoD 1: ctypes is on the list ─────────────────────────────────────────────


def test_stdlib_sweep_contains_ctypes():
    """_STDLIB_SWEEP must list ctypes (CD-120d-11 / 修訂 1)."""
    assert "ctypes" in vai._STDLIB_SWEEP


# ── DoD 2: fail-closed sweep helper + main() exit 1 ──────────────────────────


def test_main_stdlib_import_failure_exits_1(monkeypatch, capsys):
    """stdlib 失敗必須讓 exit code 變 1，且 stdout 印模組名與例外原文."""
    _patch_usable_site_packages(monkeypatch)
    missing = "__does_not_exist_xyz__"
    monkeypatch.setattr(vai, "_STDLIB_SWEEP", [missing])
    rc = vai.main([])
    assert rc == 1
    out = capsys.readouterr().out
    assert missing in out
    assert "FAIL[stdlib]" in out


# ── DoD 1 / C: Windows windll.user32 probe ───────────────────────────────────


def test_windll_user32_probe_failure_enters_fails(monkeypatch, capsys):
    """win32 + windll.user32 存取拋例外 → 結果進 fails、main() 回 1."""
    _patch_usable_site_packages(monkeypatch)

    class _BoomWindll:
        @property
        def user32(self):
            raise OSError("simulated LoadLibrary failure")

    import ctypes

    monkeypatch.setattr(vai.sys, "platform", "win32")
    monkeypatch.setattr(ctypes, "windll", _BoomWindll(), raising=False)
    rc = vai.main([])
    assert rc == 1
    out = capsys.readouterr().out
    assert "ctypes.windll.user32" in out
    assert "simulated LoadLibrary failure" in out


# ── DoD 4: missing site-packages still early-returns before stdlib ───────────


def test_main_missing_site_packages_exits_before_stdlib_sweep(monkeypatch, capsys):
    """找不到 site-packages 必須在到達 stdlib sweep 之前以 1 提早退出."""
    sweep_calls: list[list[str]] = []

    def _record(names: list[str]) -> list[tuple[str, str, str]]:
        sweep_calls.append(list(names))
        return []

    monkeypatch.setattr(vai, "_site_packages_dirs", lambda: [])
    monkeypatch.setattr(vai, "_import_sweep", _record)
    rc = vai.main([])
    assert rc == 1
    assert sweep_calls == []
    err = capsys.readouterr().err
    assert "no site-packages" in err


# ── DoD 4 sibling: 0 packages attempted still exit 1 ─────────────────────────


# ── DoD 7: each listed module has a Chinese silent-death comment ─────────────


def _docstring_constants(tree: ast.AST) -> set[ast.Constant]:
    """Constant nodes that are Module / Function / Class docstrings."""
    found: set[ast.Constant] = set()
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            continue
        if not node.body:
            continue
        first = node.body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            found.add(first.value)
    return found


def _code_string_literal_nodes(src: str) -> list[ast.Constant]:
    tree = ast.parse(src)
    docs = _docstring_constants(tree)
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node not in docs
    ]


def _code_string_literals(src: str) -> list[str]:
    """All str constants in src EXCLUDING docstrings (comments never exist in AST)."""
    return [node.value for node in _code_string_literal_nodes(src)]


def _sys_exit_calls(src: str) -> list[int]:
    """Line numbers of real sys.exit(...) Call nodes (prose can never match)."""
    hits: list[int] = []
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "exit"
            and isinstance(func.value, ast.Name)
            and func.value.id == "sys"
        ):
            hits.append(node.lineno)
    return hits


def _stdlib_sweep_assign(src: str) -> ast.Assign:
    tree = ast.parse(src)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(t, ast.Name) and t.id == "_STDLIB_SWEEP" for t in node.targets):
            return node
    raise AssertionError("_STDLIB_SWEEP assignment not found")


def _layout_literal_hits(src: str) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for node in _code_string_literal_nodes(src):
        value = node.value
        if "Lib/site-packages" in value or re.search(r"lib/python\d", value):
            hits.append((node.lineno, value))
    return hits


# ── F4: helpers must ignore prose and still catch real code ──────────────────

_DOC_ONLY_SRC = '''\
"""Module docs.

Historically shipped under lib/python3.13/site-packages before the layout-agnostic rewrite.
"""

def helper():
    """Earlier drafts called sys.exit(1) directly."""
    return 0

# lib/python3.12/site-packages was the old layout
'''

_DOC_PLUS_CODE_SRC = _DOC_ONLY_SRC + '''
from pathlib import Path
import sys
P = Path("Lib/site-packages")
sys.exit(2)
'''


# ── TASK-198a-T1: pymediainfo can_parse warn / --strict ──────────────────────


@pytest.mark.parametrize(
    'strict,expected_rc,needle',
    [
        (False, 0, '[WARN]'),
        (True, 1, 'can_parse'),
    ],
)
def test_pymediainfo_can_parse_warn_or_strict(monkeypatch, capsys, strict, expected_rc, needle):
    """can_parse 為假：無旗標 WARN+exit 0；--strict FAIL+exit 1（CD-198a-1）。"""
    _patch_usable_site_packages(monkeypatch)
    import pymediainfo

    monkeypatch.setattr(
        pymediainfo.MediaInfo,
        'can_parse',
        classmethod(lambda c, library_file=None: False),
    )
    argv = ['--strict'] if strict else []
    rc = vai.main(argv)
    assert rc == expected_rc
    out = capsys.readouterr().out
    assert needle in out


