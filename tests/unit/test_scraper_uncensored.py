"""63c-4: _get_uncensored_sources staged promotion（US4 / CD-63c-8）。

驗 metatube 無碼 provider 依番號類型 prepend 到 builtin 前；無 metatube → 純 builtin（B1 一致）。
patch get_enabled_source_ids（使用端 core.scraper）模擬「enabled + available」的來源集，
隔離 staging 過濾邏輯（availability gate 本身由 get_enabled_source_ids 自己的測試覆蓋）。
"""
import pytest

from core import scraper


def _patch_enabled(monkeypatch, sids):
    """模擬 get_enabled_source_ids 回傳（已含 enabled + available + order gate）。"""
    monkeypatch.setattr(
        scraper, "get_enabled_source_ids",
        lambda availability_map=None: list(sids),
    )
    monkeypatch.setattr(scraper.metatube_state, "availability_map", lambda: {})


# ─── HEYZO 分支 ───

def test_heyzo_metatube_available_prepended(monkeypatch):
    _patch_enabled(monkeypatch, ["metatube:HEYZO"])
    assert scraper._get_uncensored_sources("HEYZO-3333") == ["metatube:HEYZO", "heyzo", "avsox"]


def test_heyzo_metatube_unavailable_builtin_only(monkeypatch):
    # unavailable → get_enabled_source_ids 已 gate 排除 → 模擬回空 metatube
    _patch_enabled(monkeypatch, [])
    assert scraper._get_uncensored_sources("HEYZO-3333") == ["heyzo", "avsox"]


def test_heyzo_no_metatube_enabled_b1_behavior(monkeypatch):
    _patch_enabled(monkeypatch, ["javbus", "heyzo"])  # builtin enabled，無 metatube
    assert scraper._get_uncensored_sources("HEYZO-3333") == ["heyzo", "avsox"]


# ─── FC2 分支 ───

def test_fc2_metatube_three_providers_order_preserved(monkeypatch):
    _patch_enabled(monkeypatch, ["metatube:FC2", "metatube:fc2hub"])
    assert scraper._get_uncensored_sources("FC2-PPV-3333") == [
        "metatube:FC2", "metatube:fc2hub", "fc2", "avsox",
    ]


def test_fc2_only_fc2_capable_metatube_picked(monkeypatch):
    # HEYZO enabled 但非 FC2 系 → FC2 番號不該選它
    _patch_enabled(monkeypatch, ["metatube:HEYZO"])
    assert scraper._get_uncensored_sources("FC2-PPV-3333") == ["fc2", "avsox"]


def test_fc2ppvdb_picked(monkeypatch):
    _patch_enabled(monkeypatch, ["metatube:FC2PPVDB"])
    assert scraper._get_uncensored_sources("fc2-123") == ["metatube:FC2PPVDB", "fc2", "avsox"]


# ─── 日期型分支 ───

def test_date_type_caribbeancom_prepended(monkeypatch):
    _patch_enabled(monkeypatch, ["metatube:Caribbeancom"])
    result = scraper._get_uncensored_sources("020125-001")
    assert result == ["metatube:Caribbeancom", "d2pass", "heyzo", "fc2", "avsox"]


def test_date_type_excludes_fc2_and_heyzo_metatube(monkeypatch):
    # HEYZO / FC2 系 metatube 不屬日期型 → 日期番號不選它們，只選 Caribbeancom
    _patch_enabled(monkeypatch, ["metatube:HEYZO", "metatube:FC2", "metatube:Caribbeancom"])
    result = scraper._get_uncensored_sources("020125-001")
    assert result == ["metatube:Caribbeancom", "d2pass", "heyzo", "fc2", "avsox"]


def test_date_type_no_metatube_b1_behavior(monkeypatch):
    _patch_enabled(monkeypatch, [])
    assert scraper._get_uncensored_sources("020125-001") == ["d2pass", "heyzo", "fc2", "avsox"]


def test_date_type_multiple_date_providers_order(monkeypatch):
    _patch_enabled(monkeypatch, ["metatube:1Pondo", "metatube:10musume"])
    result = scraper._get_uncensored_sources("020125_001")
    assert result == ["metatube:1Pondo", "metatube:10musume", "d2pass", "heyzo", "fc2", "avsox"]


# ─── 常數正確性 ───

def test_date_uncensored_constant_excludes_branch_providers():
    from core.scrapers.utils import METATUBE_DATE_UNCENSORED, METATUBE_UNCENSORED
    # 日期型 = 全無碼 去掉 fc2/heyzo 分支各自處理的 4 個
    assert METATUBE_DATE_UNCENSORED == METATUBE_UNCENSORED - {"HEYZO", "FC2", "FC2PPVDB", "fc2hub"}
    assert len(METATUBE_DATE_UNCENSORED) == 11
