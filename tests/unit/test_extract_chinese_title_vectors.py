"""extract_chinese_title（Python）與前端 extractChineseTitle（JS）共用向量（205c-T3）。

預期值由 node 實跑 file.js 的 extractChineseTitle 產出；前端為權威。
同一份檔由 node --test 另讀一次
（web/static/js/pages/search/__tests__/extract-chinese-title-vectors.test.mjs）。

向量是取樣，只證明這些類別一致，不證明所有輸入一致。
"""
import json
from pathlib import Path

import pytest

from core.organizer import extract_chinese_title

_VECTOR_FILE = Path(__file__).resolve().parent.parent / "data" / "extract_chinese_title_vectors.json"
_VECTORS = json.loads(_VECTOR_FILE.read_text(encoding="utf-8"))["vectors"]


@pytest.mark.parametrize("vec", _VECTORS, ids=[repr(v["filename"]) for v in _VECTORS])
def test_extract_chinese_title_matches_frontend_vectors(vec):
    assert extract_chinese_title(vec["filename"], vec["number"], vec["actors"]) == vec["expected"]
