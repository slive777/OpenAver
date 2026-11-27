import pytest

from core.plot_nfo import resolve_plot_pair


@pytest.mark.parametrize("source,translated,expected", [
    ("原文", None, ("原文", "")),
    ("原文", "  ", ("原文", "")),
    ("中文", "中文", ("中文", "")),
    ("中文  第一行\n第二行", "中文 第一行 第二行", ("中文  第一行\n第二行", "")),
    ("原文", "譯文", ("譯文", "原文")),
    ("", "譯文", ("譯文", "")),
    ("a\x07b", "ab", ("ab", "")),
    ("原文", "\x00", ("原文", "")),
    ("\x07", "譯文", ("譯文", "")),
    (None, None, ("", "")),
    (123, 456, ("456", "123")),
])
def test_resolve_plot_pair_truth_table(source, translated, expected):
    assert resolve_plot_pair(source, translated) == expected
