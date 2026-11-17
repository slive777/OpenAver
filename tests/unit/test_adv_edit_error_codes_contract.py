# [lint-guard: pytest-justified] 跨 Python／JS 兩檔的契約，lint 不能表達
import re
from pathlib import Path

import pytest

from core.nfo_field_edit import ERROR_CODES


@pytest.mark.xfail(strict=True, raises=AssertionError, reason='等 T6a')
def test_error_codes_match_frontend_table():
    root = next(p for p in Path(__file__).resolve().parents if (p / 'web').is_dir())
    js = root / 'web/static/js/pages/showcase/adv-edit-data-logic.js'
    contents = js.read_text() if js.exists() else ''
    match = re.search(r'ADV_EDIT_DATA_ERROR_KEYS\s*=\s*\{(.*?)\n\};', contents, re.S)
    assert match, 'ADV_EDIT_DATA_ERROR_KEYS 尚未落地（等 T6a）'
    keys = set(re.findall(r'^\s*([a-z_]+)\s*:', match.group(1), re.M))
    assert keys == set(ERROR_CODES)
