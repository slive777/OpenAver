"""tests/unit/test_scraper_utils.py — spec-48a §a2 字幕 pattern helper 測試

- TestStripSubtitleMarkers：驗證 strip_subtitle_markers() 剝除行為
- TestCheckSubtitleNoRegression：守護 check_subtitle() 重構為常數後行為不變
"""
import pytest


class TestStripSubtitleMarkers:
    @pytest.mark.parametrize("input_name, expected_chinese_remains", [
        ("[中字] ABC-123", False),          # bracket 前綴剝除後無中文
        ("ABC-123 [中字]", False),          # bracket 後綴剝除後無中文
        ("ABC-123【中文字幕】", False),
        ("ABC-123-C", False),              # -C 後綴剝除
        ("ABC-123_c extra", False),        # _c 後綴剝除
        ("ABC-123 正妹の中文版", True),     # 真中文片名保留
        ("ABC-123 [中字] 正妹の中文版", True),  # 剝字幕後仍有真片名
        ("ABC-123", False),                # 無任何中文
    ])
    def test_strip_leaves_correct_content(self, input_name, expected_chinese_remains):
        from core.scrapers.utils import strip_subtitle_markers, has_chinese
        result = strip_subtitle_markers(input_name)
        assert has_chinese(result) == expected_chinese_remains

    # ── 詞根邊界 exact-string 斷言（守護「幕後」「字幕員」等複合詞不被誤剝）────────

    @pytest.mark.parametrize("input_name, expected_exact", [
        # 「幕後」包含「幕」字，但不是字幕標記，應完整保留
        ("ABC-123 幕後花絮", "ABC-123 幕後花絮"),
        # 「字幕員」包含「字幕」子串，但是真片名複合詞，應完整保留
        ("字幕員特典", "字幕員特典"),
        # bracket 形式應完整剝除，保留外部內容（strip 後）
        ("ABC-123 [中字]", "ABC-123"),
        ("【中文字幕】ABC-123", "ABC-123"),
        # 純文字形式帶分隔符的字幕標記應剝除
        # 注意：剝除後中間留雙空格是刻意的（函式只 strip 頭尾，不 collapse 中間）
        # 若實作多加一次 re.sub(r'\s+', ' ', name) 會造成此 case 失敗 → 故意測
        ("ABC-123 中字 extra", "ABC-123  extra"),   # 字幕詞兩側有空格
        # 真中文片名含「字幕」子串的複合詞不被剝除
        ("日本字幕員訪談", "日本字幕員訪談"),
        # -C 後綴剝除後不影響其他內容
        ("ABC-123-C", "ABC-123"),
    ])
    def test_strip_exact_string(self, input_name, expected_exact):
        """exact-string 斷言：確認剝除後的字串與預期完全一致（而非只驗布林值）"""
        from core.scrapers.utils import strip_subtitle_markers
        result = strip_subtitle_markers(input_name)
        assert result == expected_exact, (
            f"strip_subtitle_markers({input_name!r}) = {result!r}，期望 {expected_exact!r}"
        )

    def test_strip_empty(self):
        from core.scrapers.utils import strip_subtitle_markers
        assert strip_subtitle_markers("") == ""
        assert strip_subtitle_markers(None) is None


class TestCheckSubtitleNoRegression:
    """確認 check_subtitle 重構為常數後行為不變"""
    @pytest.mark.parametrize("filename, expected", [
        ("ABC-123-C.mp4", True),
        ("[中文字幕] ABC-123.mp4", True),
        ("ABC-123_C extra.mp4", True),
        ("ABC-123.mp4", False),
        ("ABC-123-CD1.mp4", False),    # -CD 不是字幕標記
        ("ABC-123中字.mp4", True),
    ])
    def test_check_subtitle(self, filename, expected):
        from core.scrapers.utils import check_subtitle
        assert check_subtitle(filename) == expected
