"""
TDD-lite: strip_number_prefix 邊界條件測試
對應 TASK-T2fix2 的 11 個邊界條件 + 2 個錯誤處理 case
"""
import pytest
from core.scrapers.utils import strip_number_prefix


# ===========================================================
# 11 個邊界條件
# ===========================================================

def test_basic_dash_prefix():
    """Case 1: 有 dash 番號 + 空格分隔"""
    assert strip_number_prefix("START-424 市役所の窓口勤務の...", "START-424") == "市役所の窓口勤務の..."


def test_embedded_newline():
    """Case 2: 番號後接換行符（JavDB 常見）"""
    assert strip_number_prefix("START-424\n市役所の窓口勤務の...", "START-424") == "市役所の窓口勤務の..."


def test_no_dash_in_title():
    """Case 3: 頁面顯示無 dash 形式（START424），number 仍有 dash"""
    assert strip_number_prefix("START424 市役所の窓口勤務の...", "START-424") == "市役所の窓口勤務の..."


def test_case_insensitive():
    """Case 4: number 小寫，title 大寫番號"""
    assert strip_number_prefix("START-424 市役所の窓口勤務の...", "start-424") == "市役所の窓口勤務の..."


def test_no_prefix_unchanged():
    """Case 5: 片名本身不含番號前綴，不應誤刪"""
    assert strip_number_prefix("市役所の窓口勤務の...", "SONE-001") == "市役所の窓口勤務の..."


def test_multi_dash_number():
    """Case 6: FC2-PPV 多段 dash 番號"""
    assert strip_number_prefix("FC2-PPV-1234567 タイトル", "FC2-PPV-1234567") == "タイトル"


def test_alphanumeric_mixed_prefix():
    """Case 7: 英數混合番號 T28-103"""
    assert strip_number_prefix("T28-103 タイトル", "T28-103") == "タイトル"


def test_leading_trailing_spaces():
    """Case 8: title 開頭有額外空格"""
    assert strip_number_prefix("  START-424  市役所の窓口勤務の...", "START-424") == "市役所の窓口勤務の..."


def test_title_is_only_number():
    """Case 9: title 整個就是番號，剝除後應回傳空字串（不是 None）"""
    result = strip_number_prefix("START-424", "START-424")
    assert result == ""
    assert isinstance(result, str)


def test_empty_title():
    """Case 10: 空字串 title"""
    assert strip_number_prefix("", "START-424") == ""


def test_no_space_between_number_and_title():
    """Case 11: 番號與片名之間無空格"""
    assert strip_number_prefix("CAWD-123市役所の窓口勤務の...", "CAWD-123") == "市役所の窓口勤務の..."


# ===========================================================
# 錯誤處理 case
# ===========================================================

def test_none_title_returns_empty_string():
    """錯誤處理: title 為 None 應回傳空字串，不拋例外"""
    result = strip_number_prefix(None, "START-424")  # type: ignore[arg-type]
    assert result == ""
    assert isinstance(result, str)


def test_empty_number_returns_title_unchanged():
    """錯誤處理: number 為空字串時，直接回傳原始 title"""
    assert strip_number_prefix("START-424 片名", "") == "START-424 片名"


# ===========================================================
# 番號邊界保護（Codex review 補充）
# ===========================================================

def test_longer_number_not_truncated():
    """較長番號共前綴：ABP-123 不應誤砍 ABP-1234 的 title"""
    assert strip_number_prefix("ABP-1234 タイトル", "ABP-123") == "ABP-1234 タイトル"


def test_longer_number_no_dash_not_truncated():
    """無 dash 形式同理：ABP123 不應誤砍 ABP1234"""
    assert strip_number_prefix("ABP1234 タイトル", "ABP-123") == "ABP1234 タイトル"


def test_number_suffix_digit_protected():
    """IPZZ-03 不應誤砍 IPZZ-030 的 title"""
    assert strip_number_prefix("IPZZ-030 title", "IPZZ-03") == "IPZZ-030 title"
