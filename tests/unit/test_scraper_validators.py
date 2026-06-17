"""
寫於 tests/unit/test_scraper_validators.py
涵蓋 is_number_format, is_partial_number, is_prefix_only 的單元測試

注意：測試按照 CURRENT prod code 行為撰寫：
- is_number_format: regex ``^[a-zA-Z]+-?\\d{3,}$`` (先清除 -UC/-UNCEN 等後綴)
- is_partial_number: regex ``^([a-zA-Z]+)-?(\\d{1,2})$``
- is_prefix_only: regex ``^[A-Z]{2,6}$``
- 三者都沒有 null guard (.strip() on None raises AttributeError)
"""
from unittest.mock import patch

import pytest

import core.scraper as scraper_mod
from core.scraper import (
    is_number_format,
    is_partial_number,
    is_prefix_only,
    search_jav,
)


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


# ============ search_jav source routing (TASK-61a-3) ============

# Scraper classes patched in core.scraper that may get constructed by search_jav.
# Construction must be cheap & must NOT hit the network; we patch them with
# spies recording instantiation and stub .search() so nothing real runs.
_SCRAPER_ATTRS = [
    'DMMScraper', 'JavBusScraper', 'JAV321Scraper', 'JavDBScraper',
    'D2PassScraper', 'HEYZOScraper', 'FC2Scraper', 'AVSOXScraper',
]

# id -> scraper class attr name in core.scraper
_ID_TO_ATTR = {
    'dmm': 'DMMScraper',
    'javbus': 'JavBusScraper',
    'jav321': 'JAV321Scraper',
    'javdb': 'JavDBScraper',
    'd2pass': 'D2PassScraper',
    'heyzo': 'HEYZOScraper',
    'fc2': 'FC2Scraper',
    'avsox': 'AVSOXScraper',
}


def _install_scraper_spies(monkeypatch):
    """Replace each Scraper class on core.scraper with a spy.

    Returns a dict {attr_name: list_of_calls}. Each spy:
    - records its construction (args/kwargs ignored for the count),
    - returns an object whose .search() returns None (no result, no network).
    """
    constructed: dict[str, int] = {attr: 0 for attr in _SCRAPER_ATTRS}

    def make_spy(attr_name):
        def factory(*args, **kwargs):
            constructed[attr_name] += 1

            class _Stub:
                def search(self, number):
                    return None

            return _Stub()

        return factory

    for attr in _SCRAPER_ATTRS:
        monkeypatch.setattr(scraper_mod, attr, make_spy(attr))

    # normalize_number() constructs a real JavBusScraper at module scope (unrelated
    # to routing). Stub it to identity so the spies don't break it and no network runs.
    monkeypatch.setattr(scraper_mod, 'normalize_number', lambda n: n)

    return constructed


class TestValidateSourceIntegration:
    """validate_source_id wiring: known ids + 'auto' accepted; unknown -> None."""

    def test_unknown_source_returns_none_no_raise(self, monkeypatch):
        # Should not raise; should short-circuit to None before constructing scrapers.
        _install_scraper_spies(monkeypatch)
        result = search_jav("ABP-001", source="not-a-real-source")
        assert result is None

    def test_auto_is_accepted(self, monkeypatch):
        # 'auto' must pass validation; with empty enabled list -> no results -> None.
        _install_scraper_spies(monkeypatch)
        monkeypatch.setattr(scraper_mod, 'get_enabled_source_ids', lambda availability_map=None: [])
        result = search_jav("ABP-001", source="auto")
        assert result is None

    def test_known_explicit_source_accepted(self, monkeypatch):
        # 'javbus' must pass validation and construct exactly JavBusScraper.
        constructed = _install_scraper_spies(monkeypatch)
        result = search_jav("ABP-001", source="javbus")
        assert result is None  # stub .search returns None
        assert constructed['JavBusScraper'] == 1
        # No other scrapers constructed for an explicit single source.
        for attr in _SCRAPER_ATTRS:
            if attr != 'JavBusScraper':
                assert constructed[attr] == 0


class TestAutoFanOutReadsEnabledIds:
    """auto path fans out over get_enabled_source_ids()."""

    def test_auto_only_constructs_enabled_subset(self, monkeypatch):
        constructed = _install_scraper_spies(monkeypatch)
        monkeypatch.setattr(
            scraper_mod, 'get_enabled_source_ids', lambda availability_map=None: ['javbus', 'javdb']
        )
        search_jav("ABP-001", source="auto")
        assert constructed['JavBusScraper'] == 1
        assert constructed['JavDBScraper'] == 1
        # Everything else (incl. DMM) must not be constructed.
        for attr in _SCRAPER_ATTRS:
            if attr not in ('JavBusScraper', 'JavDBScraper'):
                assert constructed[attr] == 0

    def test_auto_empty_enabled_list_returns_none(self, monkeypatch):
        constructed = _install_scraper_spies(monkeypatch)
        monkeypatch.setattr(scraper_mod, 'get_enabled_source_ids', lambda availability_map=None: [])
        result = search_jav("ABP-001", source="auto")
        assert result is None
        assert all(v == 0 for v in constructed.values())


class TestDmmProxyGuard:
    """DMM proxy guard preserved across the refactor."""

    def test_auto_dmm_enabled_but_no_proxy_not_constructed(self, monkeypatch):
        # 'dmm' is in the enabled list but no proxy -> DMM must NOT be constructed.
        constructed = _install_scraper_spies(monkeypatch)
        monkeypatch.setattr(
            scraper_mod, 'get_enabled_source_ids', lambda availability_map=None: ['dmm', 'javbus']
        )
        search_jav("ABP-001", source="auto", proxy_url="")
        assert constructed['DMMScraper'] == 0
        assert constructed['JavBusScraper'] == 1

    def test_auto_dmm_with_proxy_constructed(self, monkeypatch):
        # Proxy configured -> DMM included in the fan-out.
        constructed = _install_scraper_spies(monkeypatch)
        monkeypatch.setattr(
            scraper_mod, 'get_enabled_source_ids', lambda availability_map=None: ['dmm', 'javbus']
        )
        search_jav("ABP-001", source="auto", proxy_url="http://127.0.0.1:8080")
        assert constructed['DMMScraper'] == 1
        assert constructed['JavBusScraper'] == 1

    def test_explicit_dmm_no_proxy_not_constructed(self, monkeypatch):
        constructed = _install_scraper_spies(monkeypatch)
        result = search_jav("ABP-001", source="dmm", proxy_url="")
        assert result is None
        assert constructed['DMMScraper'] == 0

    def test_explicit_dmm_with_proxy_constructed(self, monkeypatch):
        constructed = _install_scraper_spies(monkeypatch)
        search_jav("ABP-001", source="dmm", proxy_url="http://127.0.0.1:8080")
        assert constructed['DMMScraper'] == 1


# ============ TASK-73a-T1: 入口 gate + search_jav 整合 ============

class TestTokyoHotGate:
    """is_number_format 入口 gate 守衛：n0762 / N0762 必須通過"""

    def test_is_number_format_n0762_lowercase(self):
        """n0762 通過入口 gate（契約守衛）"""
        assert is_number_format('n0762') is True

    def test_is_number_format_N0762_uppercase(self):
        """N0762 通過入口 gate（契約守衛）"""
        assert is_number_format('N0762') is True


class TestTokyoHotSearchJavIntegration:
    """search_jav('n0762', source='javbus') 傳進 scraper 的番號必須是 N0762（不是 N-0762）"""

    def test_search_jav_n0762_passes_N0762_to_scraper(self, monkeypatch):
        """n0762 normalize 後以 N0762 傳入 scraper.search()"""
        received_numbers = []

        # Subclass the REAL JavBusScraper so the inherited (real) normalize_number
        # runs through the production module-level wrapper
        # (scraper.py:78 → JavBusScraper().normalize_number()); only .search() is
        # overridden to capture. No normalize_number patching → the full real
        # normalize path is exercised, not a stand-in wrapper.
        from core.scrapers import JavBusScraper as _RealJavBusScraper

        class _CapturingJavBusScraper(_RealJavBusScraper):
            def search(self, number):
                received_numbers.append(number)
                return None

        # Patch the USE-SITE binding in core.scraper (same pattern as existing tests).
        monkeypatch.setattr(scraper_mod, 'JavBusScraper', _CapturingJavBusScraper)

        search_jav('n0762', source='javbus')

        # scraper must have been called exactly once with N0762 (not N-0762)
        assert len(received_numbers) == 1, f"expected 1 call, got {received_numbers}"
        assert received_numbers[0] == 'N0762', (
            f"expected 'N0762' but scraper received {received_numbers[0]!r}"
        )
