# [lint-guard: pytest-justified] ①「schema 名稱都在文件」要 import Python 常數集合（schema.TOP_KEYS 等），
# eslint／stylelint／scripts/*.mjs 讀不到 Python 常數；②「範例 YAML 能載入」要呼叫 Python loader（schema.load_text）。
"""docs/custom-sources.md 的文件契約：schema 名稱不漏、範例區塊都能載入。"""
import re
from pathlib import Path

import pytest
import yaml

from core.custom_source import errors, schema

DOC_PATH = Path(__file__).resolve().parents[2] / "docs" / "custom-sources.md"

# schema.py 以字面驗證這三個子鍵、沒有常數可 import（T7 不得改 schema.py），故在此寫死
_RESULTS_AND_NOT_FOUND_KEYS = frozenset({"css", "keep_if_contains", "body_contains"})
# schema.py 未公開此集合，與 schema 模板白名單（_URL_VARS_SUFFIX）同步
_PLACEHOLDERS = frozenset({"{number}", "{number_lower}", "{number_digits}", "{suffix}"})

_MARKER = "<!-- example -->"
_EXAMPLE_RE = re.compile(r"<!-- example -->[ \t]*\n(?:[ \t]*\n)*```yaml\n(.*?)\n```", re.DOTALL)


def _doc_text():
    return DOC_PATH.read_text(encoding="utf-8")


def _example_blocks():
    return _EXAMPLE_RE.findall(_doc_text())


def _all_names():
    names = set()
    for group in (
        schema.TOP_KEYS, schema.STEP_KEYS, schema.FIELD_NAMES, schema.FIELD_KEYS,
        schema.TRANSFORMS, schema.CASE_KEYS, schema.CASE_STATUSES, schema.EXPECT_SUFFIXES,
        errors.LOAD_REASONS, errors.SCRAPE_ERROR_REASONS,
        _RESULTS_AND_NOT_FOUND_KEYS, _PLACEHOLDERS,
    ):
        names |= set(group)
    return names


def test_schema_names_all_documented():
    text = _doc_text()
    missing = sorted(n for n in _all_names() if f"`{n}`" not in text)
    assert not missing, f"文件缺少以行內程式碼出現的名稱：{missing}"


def test_example_markers_not_dangling():
    count = _doc_text().count(_MARKER)
    assert count == len(_example_blocks()), (
        f"<!-- example --> 出現 {count} 次，但後面緊接 yaml 區塊的只有 {len(_example_blocks())} 個"
    )


def _load_blocks():
    specs = []
    for i, block in enumerate(_example_blocks(), 1):
        data = yaml.safe_load(block)
        stem = data.get("id") if isinstance(data, dict) else None
        try:
            specs.append(schema.load_text(block, stem))
        except errors.LoadError as exc:
            pytest.fail(f"範例區塊 #{i} 載入被拒：reason={exc.reason} field_path={exc.field_path}")
    return specs


def test_example_blocks_all_load():
    assert _load_blocks() is not None


def test_example_blocks_cover_both_shapes():
    specs = _load_blocks()
    assert len(specs) >= 2, f"範例區塊只有 {len(specs)} 份"
    shapes = sorted({len(s.steps) for s in specs})
    assert shapes == [1, 2], f"範例須含單段式與兩段式各一，實際 steps 長度：{shapes}"


# ---------------------------------------------------------------------------
# 165-T11：「## 13. 上傳、驗收與狀態」與程式對帳（只掃新章，各子節以標題逐字定位）
# ---------------------------------------------------------------------------
import ast  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
_CHAPTER_HEADING = "## 13. 上傳、驗收與狀態"
_PATH_RE = re.compile(r"/api/custom[^\s'\"`),，|]*")
_FIRST_CELL_CODE_RE = re.compile(r"^\|\s*`([^`]+)`\s*\|")


def _chapter13():
    text = _doc_text()
    idx = text.find("\n" + _CHAPTER_HEADING)
    if idx < 0:
        pytest.fail(f"docs 找不到章節標題 {_CHAPTER_HEADING!r}")
    return text[idx + 1:]


def _subsection(title):
    chapter = _chapter13()
    heading = f"### {title}"
    lines = chapter.split("\n")
    start = None
    for i, line in enumerate(lines):
        if line.strip() == heading:
            start = i + 1
            break
    if start is None:
        pytest.fail(f"§13 找不到子節標題 {heading!r}")
    body = []
    for line in lines[start:]:
        if line.startswith("### ") or line.startswith("## "):
            break
        body.append(line)
    return "\n".join(body)


def _table_first_cells(section):
    cells = set()
    for line in section.split("\n"):
        m = _FIRST_CELL_CODE_RE.match(line)
        if m:
            cells.add(m.group(1))
    return cells


def _norm_doc_path(path):
    parts = path.split("/")  # ['', 'api', 'custom-sources', X, ...]
    if len(parts) >= 4 and parts[3] not in ("applicable", "{id}"):
        parts[3] = "{id}"
    return "/".join(parts)


def _router_paths():
    import web.routers.custom_sources as mod

    return {r.path.replace("{source_id}", "{id}") for r in mod.router.routes}


def _service_error_codes():
    codes = set()
    for rel in ("core/custom_source/service.py", "web/routers/custom_sources.py"):
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "ServiceError"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                codes.add(node.args[0].value)
    return codes


def _derive_status_literals():
    tree = ast.parse((ROOT / "core/custom_source/state.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "derive_status":
            return {
                n.value.value
                for n in ast.walk(node)
                if isinstance(n, ast.Return)
                and isinstance(n.value, ast.Constant)
                and isinstance(n.value.value, str)
            }
    pytest.fail("找不到 derive_status")


def test_docs_endpoints_match_router():
    section = _subsection("端點")
    extracted = {_norm_doc_path(p) for p in _PATH_RE.findall(section)}
    assert extracted, "§13 端點子節沒擷取到任何 /api/custom 路徑"
    routes = _router_paths()
    assert extracted <= routes, f"docs 出現路由不存在的路徑：{sorted(extracted - routes)}"
    required = {"/api/custom-sources", "/api/custom-sources/{id}/verify", "/api/custom-sources/{id}"}
    assert required <= extracted, f"docs 漏了 AI 端點：{sorted(required - extracted)}"


def test_docs_error_codes_cover_service():
    documented = _table_first_cells(_subsection("錯誤碼"))
    expected = _service_error_codes()
    assert expected, "ast 沒掃到任何 ServiceError 字面"
    assert documented, "§13 錯誤碼表沒擷取到任何 code"
    assert expected <= documented, f"錯誤碼表漏列：{sorted(expected - documented)}"


def test_docs_states_match_state_py():
    from core.custom_source import state

    documented = _table_first_cells(_subsection("狀態"))
    expected = _derive_status_literals() | set(state.STATUSES)
    assert documented, "§13 狀態表沒擷取到任何狀態"
    assert documented == expected, f"狀態表與 state.py 不符：docs={sorted(documented)} code={sorted(expected)}"


def test_docs_gate_reasons_match_gate():
    from core.custom_source import gate

    documented = _table_first_cells(_subsection("使用 custom:<id> 的條件"))
    assert documented, "§13 gate reason 表沒擷取到任何 reason"
    assert documented == set(gate.REASONS), (
        f"gate reason 表與 gate.REASONS 不符：docs={sorted(documented)} code={sorted(gate.REASONS)}"
    )
