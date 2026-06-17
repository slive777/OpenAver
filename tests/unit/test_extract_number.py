"""
TestExtractNumber — extract_number 和 normalize_number 單元測試
（搬自 tests/integration/test_new_scrapers.py TestExtractNumber）

純邏輯測試，不需 mock
"""
from core.scrapers.utils import extract_number
from core.scrapers.d2pass import D2PassScraper


class TestExtractNumber:
    """extract_number 和 normalize_number 單元測試"""

    def test_extract_number_underscore_3digit(self):
        """底線格式 3-digit suffix 正確提取"""
        result = extract_number("120415_201.mp4")
        assert result == "120415_201"

    def test_extract_number_underscore_2digit(self):
        """底線格式 2-digit suffix 正確提取"""
        result = extract_number("082912_01.mp4")
        assert result == "082912_01"

    def test_normalize_number_preserves_underscore(self):
        """D2PassScraper.normalize_number 不破壞底線格式番號"""
        scraper = D2PassScraper()
        result = scraper.normalize_number("120415_201")
        assert result == "120415_201"

    def test_extract_number_hyphen_2digit(self):
        """hyphen 格式 2-digit suffix 正確提取（T6b regex 修正）"""
        result = extract_number("041417-41.mp4")
        assert result == "041417-41"

    # --- TASK-73a-T2: 單字母 + 4 位無碼番號（Tokyo Hot）---

    def test_extract_single_letter_tokyo_hot_full_filename(self):
        """用戶 bug 本體：[無碼]n0762 Tokyo Hot n0762.mp4 → N0762（大寫無 hyphen）"""
        result = extract_number("[無碼]n0762 Tokyo Hot n0762.mp4")
        assert result == "N0762"

    def test_extract_single_letter_k0150(self):
        """k0150.mp4 → K0150（單字母 + 4 位，不插 hyphen）"""
        assert extract_number("k0150.mp4") == "K0150"

    def test_extract_single_letter_c0050(self):
        """c0050.mp4 → C0050（單字母 + 4 位，不插 hyphen）"""
        assert extract_number("c0050.mp4") == "C0050"

    # --- TASK-73a-T2: 回歸守衛（單字母 pattern 不得污染既有行為）---

    def test_regression_multiletter_no_hyphen_still_inserts(self):
        """SONE205.mp4 → SONE-205（多字母走 index 6，照舊插 hyphen）"""
        assert extract_number("SONE205.mp4") == "SONE-205"

    def test_regression_hyphen_format_unchanged(self):
        """ABC-123.mp4 → ABC-123（帶 hyphen 不變）"""
        assert extract_number("ABC-123.mp4") == "ABC-123"

    def test_regression_date_format_unchanged(self):
        """041417-413.mp4 → 041417-413（日期型不變）"""
        assert extract_number("041417-413.mp4") == "041417-413"

    def test_regression_fc2_unchanged(self):
        """FC2-PPV-1234567.mp4 → FC2-PPV-1234567（不變）"""
        assert extract_number("FC2-PPV-1234567.mp4") == "FC2-PPV-1234567"

    def test_regression_t28_unchanged(self):
        """T28-103.mp4 → T28-103（混合格式不變）"""
        assert extract_number("T28-103.mp4") == "T28-103"

    def test_regression_no_false_extract_4digit_year(self):
        """random_movie_2024.mp4 不誤抽（4 位數字前非緊鄰單字母，_ 隔開）"""
        assert extract_number("random_movie_2024.mp4") is None

    def test_regression_no_false_extract_s1_underscore(self):
        """S1_2024.mp4 不誤抽成 S2024（底線隔開單字母與數字）"""
        result = extract_number("S1_2024.mp4")
        assert result != "S2024"

    # --- TASK-73a-T2 bugfix: right-side digit boundary (no truncation) ---

    def test_no_truncate_5digit_n12345(self):
        """n12345.mp4 不應截斷為 N1234（單字母 + 5 位 → 不是 Tokyo Hot，應回 None）"""
        result = extract_number("n12345.mp4")
        # 5-digit after single letter is NOT Tokyo Hot (spec: exactly 4 digits)
        # Earlier patterns don't match either, so result must NOT be N1234
        assert result != "N1234"
        assert result is None

    def test_no_truncate_5digit_n07620(self):
        """n07620.mp4 不應截斷為 N0762（單字母 + 5 位 → 不是 Tokyo Hot，應回 None）"""
        result = extract_number("n07620.mp4")
        assert result != "N0762"
        assert result is None
