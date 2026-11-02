"""
tests/unit/test_similar_invalidate_completeness.py
AST lint test — 確保所有 raw SQL mutation 函式都有 SimilarRankerCache.invalidate() 呼叫
spec-57 §3 Phase 57b DoD R2/R8 / plan-57b.md §2 T6 lines 694-729
"""
import ast
import re
from pathlib import Path

import pytest

EXCLUDE_PREFIXES = ("core/clip/", "core/similar/", "tests/", "archive/")

# 三種觸發 SQL pattern（corpus 欄位 raw mutation）
_SQL_PATTERNS = [
    re.compile(
        r"UPDATE\s+videos\s+SET[^;]*\b(number|tags|actresses|maker|series|release_date|duration|user_tags)\b",
        re.DOTALL | re.IGNORECASE,
    ),
    re.compile(r"DELETE\s+FROM\s+videos\b", re.DOTALL | re.IGNORECASE),
    re.compile(r"INSERT\s+INTO\s+videos\b", re.DOTALL | re.IGNORECASE),
]

INVALIDATE_OK_MARKER = "# ranker-invalidate-ok"


def _has_invalidate_call(funcdef_node: ast.FunctionDef) -> bool:
    """AST walk 整個 function scope（含 nested def），找 SimilarRankerCache.invalidate() 呼叫。"""
    for node in ast.walk(funcdef_node):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "invalidate":
            # 確認 receiver 是 SimilarRankerCache（Name 或 Attribute）
            if isinstance(func.value, ast.Name) and func.value.id == "SimilarRankerCache":
                return True
            if isinstance(func.value, ast.Attribute) and func.value.attr == "SimilarRankerCache":
                return True
    return False


def _get_source_segment(source: str, node: ast.FunctionDef) -> str:
    """取得 function 的原始碼段（用於 noqa 檢查）。"""
    lines = source.splitlines()
    start = node.lineno - 1
    end = node.end_lineno
    return "\n".join(lines[start:end])


def _scan_file(path: Path) -> list[str]:
    """掃描單一 .py 檔，回傳 violation 描述 list。"""
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        seg = _get_source_segment(source, node)

        # 白名單豁免（委派給已自帶 invalidate 的路徑）
        if INVALIDATE_OK_MARKER in seg:
            continue

        # 是否有觸發 SQL pattern
        has_sql = any(pat.search(seg) for pat in _SQL_PATTERNS)
        if not has_sql:
            continue

        # 有 SQL mutation → 必須有 invalidate
        if not _has_invalidate_call(node):
            violations.append(
                f"{path}:{node.lineno}: function `{node.name}` has raw SQL mutation on videos "
                f"but no SimilarRankerCache.invalidate() call. "
                f"Fix: add invalidate after conn.commit() per plan-57b CD-57b-3 pattern."
            )

    return violations


def test_all_raw_sql_mutations_have_invalidate():
    """所有對 videos 表做 raw SQL mutation 的函式必須呼叫 SimilarRankerCache.invalidate()。

    例外：函式內含 '# ranker-invalidate-ok' 註解（委派給已自帶 invalidate 的路徑）。
    """
    root = Path(".")
    violations = []

    for pattern in ("core/**/*.py", "web/routers/**/*.py"):
        for path in sorted(root.glob(pattern)):
            rel = path.as_posix()
            if any(rel.startswith(p) for p in EXCLUDE_PREFIXES):
                continue
            violations.extend(_scan_file(path))

    assert not violations, (
        f"Found {len(violations)} function(s) with raw SQL mutation but no invalidate:\n"
        + "\n".join(violations)
    )
