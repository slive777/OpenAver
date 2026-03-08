"""
寫於 tests/unit/test_scraper_validators.py
涵蓋 is_number_format, is_partial_number, is_prefix_only 的單元測試

注意：測試按照 CURRENT prod code 行為撰寫：
- is_number_format: regex ``^[a-zA-Z]+-?\\d{3,}$`` (先清除 -UC/-UNCEN 等後綴)
- is_partial_number: regex ``^([a-zA-Z]+)-?(\\d{1,2})$``
- is_prefix_only: regex ``^[A-Z]{2,6}$``
- 三者都沒有 null guard (.strip() on None raises AttributeError)
"""
import pytest
from core.scraper import is_number_format, is_partial_number, is_prefix_only


class TestIsNumberFormat:
    def test_standard_format(self):
        assert is_number_format("ABP-001") is True
        assert is_number_format("SNIS-123") is True

    def test_mixed_case(self):
        assert is_number_format("abp-001") is True
        assert is_number_format("AbP-001") is True

    def test_no_dash(self):
        """Letters followed by 3+ digits without dash"""
        assert is_number_format("ABP001") is True

    def test_with_uc_suffix(self):
        """UC/UNCEN suffixes are stripped before matching"""
        assert is_number_format("SONE-103-UC") is True

    def test_multi_dash_rejected(self):
        """Multi-dash formats like FC2-PPV-1234567 don't match simple regex"""
        assert is_number_format("FC2-PPV-1234567") is False

    def test_digit_in_prefix_rejected(self):
        """Prefix must be pure letters; T28 has a digit"""
        assert is_number_format("T28-001") is False

    def test_number_prefix_rejected(self):
        """Prefix starting with digit rejected"""
        assert is_number_format("259LUXU-001") is False

    def test_underscore_in_number_rejected(self):
        """Underscore in number portion doesn't match"""
        assert is_number_format("1Pondo-123456_789") is False

    def test_invalid_formats(self):
        assert is_number_format("hello") is False
        assert is_number_format("12345") is False
        assert is_number_format("") is False
        assert is_number_format("ABP-") is False
        assert is_number_format("-001") is False

    def test_too_few_digits(self):
        """Less than 3 digits rejected"""
        assert is_number_format("ABP-01") is False
        assert is_number_format("ABP-1") is False

    def test_none_raises(self):
        """None input raises AttributeError (no null guard)"""
        with pytest.raises(AttributeError):
            is_number_format(None)


class TestIsPartialNumber:
    def test_valid_partial(self):
        assert is_partial_number("SNIS-1") is True
        assert is_partial_number("ABP12") is True  # no dash, 1-2 digits

    def test_no_digits_rejected(self):
        """ABP- has no digits, doesn't match regex"""
        assert is_partial_number("ABP-") is False

    def test_multi_segment_rejected(self):
        """FC2-PPV- doesn't match simple letter-digit partial pattern"""
        assert is_partial_number("FC2-PPV-") is False

    def test_complete_number_rejected(self):
        """3+ digits = complete number, not partial"""
        assert is_partial_number("ABP-001") is False

    def test_invalid_partial(self):
        assert is_partial_number("hello") is False
        assert is_partial_number("12345") is False
        assert is_partial_number("") is False

    def test_none_raises(self):
        """None input raises AttributeError (no null guard)"""
        with pytest.raises(AttributeError):
            is_partial_number(None)


class TestIsPrefixOnly:
    def test_valid_prefix(self):
        assert is_prefix_only("ABP") is True
        assert is_prefix_only("SNIS") is True
        assert is_prefix_only("ABCDEF") is True  # 6 chars = max

    def test_digit_in_prefix_rejected(self):
        """FC2 contains digit '2', doesn't match ^[A-Z]{2,6}$"""
        assert is_prefix_only("FC2") is False

    def test_too_short(self):
        """Single letter is too short (min 2)"""
        assert is_prefix_only("A") is False

    def test_too_long(self):
        """7+ letters is too long (max 6)"""
        assert is_prefix_only("ABCDEFG") is False

    def test_lowercase_converted(self):
        """Input is uppercased before matching, so lowercase works"""
        assert is_prefix_only("abp") is True
        assert is_prefix_only("snis") is True

    def test_invalid_prefix(self):
        assert is_prefix_only("ABP-001") is False
        assert is_prefix_only("ABP-") is False
        assert is_prefix_only("123") is False
        assert is_prefix_only("") is False

    def test_none_raises(self):
        """None input raises AttributeError (no null guard)"""
        with pytest.raises(AttributeError):
            is_prefix_only(None)
