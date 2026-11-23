"""tests/unit/test_translation_judge.py — core/translation_judge.is_bad_translation 判定表（TASK-205c-T1）。"""
import pytest

from core.translation_judge import is_bad_translation


@pytest.mark.parametrize(
    "source,translated,expect_bad",
    [
        ("夢中になる最高の女。-男性主體の無避妊中出しセックス- 八掛うみ",
         "為我著迷的最棒女人。-以男性為主體的無避孕內射性交- 八掛うみ", False),
        ("これはテスト", "這是テスト", False),
        ("これはテスト", "這是測試", False),
        ("美しい人妻の秘密", "美麗人妻的秘密", False),
        ("美人妻教師", " 美人妻教師 ", True),
        ("これはテスト", "這是\n測試", True),
        ("あいうえお", "測" * 46, True),
        ("これはテスト", "抱歉，我無法翻譯這個標題", True),
        ("これはテスト", "I can’t translate this", True),
        ("これはテスト", "", True),
    ],
    ids=[
        "kana_retained_long_title_good",
        "kana_retained_short_flipped_good",
        "normal_good_short",
        "normal_good_other",
        "same_after_strip_bad",
        "newline_bad",
        "too_long_bad",
        "refusal_zh_bad",
        "refusal_en_curly_apostrophe_bad",
        "empty_bad",
    ],
)
def test_is_bad_translation_table(source, translated, expect_bad):
    assert is_bad_translation(source, translated) is expect_bad
