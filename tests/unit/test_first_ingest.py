"""tests/unit/test_first_ingest.py — core/first_ingest 判定表（TASK-205c-T5）。"""
import pytest

from core.first_ingest import (
    is_first_ingest_readonly,
    is_first_ingest_sidecar,
    pick_title,
)

SITE = "SITE-TITLE-PLACEHOLDER"


@pytest.mark.parametrize(
    "meta_source,existing_nfo_mtime,expected",
    [
        ("scraper", 0, True),
        ("nfo", 0, False),
        ("scraper", None, True),
        ("scraper", 1700000000.0, False),
    ],
    ids=[
        "scraper_no_nfo_first",
        "nfo_source_not_first",
        "scraper_none_mtime_first",
        "scraper_existing_nfo_not_first",
    ],
)
def test_is_first_ingest_readonly_table(meta_source, existing_nfo_mtime, expected):
    assert is_first_ingest_readonly(meta_source, existing_nfo_mtime) is expected


@pytest.mark.parametrize(
    "nfo_existed,source_used,title_from_site,expected",
    [
        (False, "scraper", True, True),
        (True, "scraper", True, False),
        (False, "db", True, False),
        (False, "scraper", False, False),
    ],
    ids=[
        "no_nfo_scraper_site_first",
        "nfo_existed_not_first",
        "db_source_not_first",
        "no_site_title_not_first",
    ],
)
def test_is_first_ingest_sidecar_table(nfo_existed, source_used, title_from_site, expected):
    assert is_first_ingest_sidecar(nfo_existed, source_used, title_from_site) is expected


@pytest.mark.parametrize(
    "filename,number,maker,expected_title,expected_original",
    [
        (
            "ABF-343 中文字幕 我沉迷於的最棒女人-以男性為中心的無避孕內射性行為 八掛海 - Hayav AV Streaming.mp4",
            "ABF-343",
            "",
            "我沉迷於的最棒女人-以男性為中心的無避孕內射性行為",
            SITE,
        ),
        ("STARS-701.mp4", "STARS-701", "", SITE, ""),
        ("ABC-123 洗脳啓発まいんどふぁっかー.mp4", "ABC-123", "", SITE, ""),
        ("STARS-701 中文片名 2025-01-02.mp4", "STARS-701", "", SITE, ""),
        ("[ABC-123]標題.mp4", "ABC-123", "", "標題", SITE),
        ("ABC-123 中文標題 SOD.mp4", "ABC-123", "SOD", SITE, ""),
    ],
    ids=[
        "cn_filename_wins",
        "bare_number_falls_back",
        "kana_filename_falls_back",
        "date_junk_falls_back",
        "bracket_prefix_stripped",
        "maker_residue_junk_falls_back",
    ],
)
def test_pick_title_table(filename, number, maker, expected_title, expected_original):
    assert (
        pick_title(SITE, filename, number, [], maker, {"suffix_keywords": []})
        == (expected_title, expected_original)
    )
