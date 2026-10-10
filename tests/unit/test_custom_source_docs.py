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
