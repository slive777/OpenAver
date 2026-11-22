"""tests/unit/test_needs_translate.py — core/title_writeback.needs_translate 判準真值表（TASK-205c-T2）。

判準：has_japanese(原始標題) 且 nfo_mtime>0，且（原文標準化後為空 or 標題標準化後 == 原文標準化後）。
標準化＝strip → _strip_num_prefixes(s, number) → strip（兩邊都做，不做大小寫／全半形正規化）。
"""
import pytest

from core.title_writeback import needs_translate


@pytest.mark.parametrize(
    "title,original,nfo_mtime,number,expected",
    [
        ("為我著迷的最棒女人-八掛うみ", "夢中になる最高の女-八掛うみ", 1.0, "", False),
        ("これはテスト", "これはテスト", 1.0, "", True),
        ("これはテスト", "  これはテスト  ", 1.0, "", True),
        ("タイトル", "STARS-701 タイトル", 1.0, "STARS-701", True),
        ("これはテスト", "", 1.0, "", True),
        ("これはテスト", None, 1.0, "", True),
        ("これはテスト", "これはテスト", 0, "", False),
        ("中文標題", "中文標題", 1.0, "", False),
        ("[STARS-701]タイトル", "タイトル", 1.0, "STARS-701", True),
    ],
    ids=[
        "translated_differs_no_rerun",
        "same_title_and_original_needs_translate",
        "same_after_strip_needs_translate",
        "original_with_number_prefix_needs_translate",
        "original_empty_needs_translate",
        "original_none_needs_translate",
        "nfo_zero_never_needs_translate",
        "no_kana_never_needs_translate",
        "title_with_number_prefix_needs_translate",
    ],
)
def test_needs_translate_truth_table(title, original, nfo_mtime, number, expected):
    assert needs_translate(title, original, nfo_mtime, number=number) is expected
