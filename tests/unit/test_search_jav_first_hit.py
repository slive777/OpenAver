"""search_jav(first_hit=True) 契約 — TASK-197-T2 I-1／I-2／I-3。

輸入只是我們自組的 card dict／字串；patch 打使用端 binding。
不得以捏造站方 HTML／JSON 為輸入。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from core.scraper import search_jav


def _make_exact_card(**overrides):
    """每次現造新 dict，避免 pop('_mode')／setdefault 污染後續 row。"""
    card = {
        "number": "ABC-123",
        "title": "FIRST",
        "actors": ["女優A"],
        "cover": "https://example.com/c.jpg",
        "date": "2024-01-01",
        "maker": "SOD",
        "director": "監督",
        "series": "系列",
        "label": "LABEL",
        "tags": ["タグ1", "タグ2"],
        "sample_images": [],
        "duration": 120,
        "url": "https://example.com/ABC-123",
        "source": "dmm",
        "_mode": "exact",
    }
    card.update(overrides)
    return card


def _fanout_recorder(calls):
    def _rec(*_a, **_kw):
        calls.append(True)
        return []

    return _rec


@pytest.mark.parametrize(
    "with_original_title",
    [False, True],
    ids=["no_original_title_key", "keeps_existing_original_title"],
)
def test_first_hit_exact_returns_card_without_fanout(with_original_title):
    """I-1：適用且 exact → 回 card（無 _mode、補／保留 original_title），不進 fan-out。"""
    overrides = {}
    if with_original_title:
        overrides["original_title"] = "X"
    # 不含 original_title 鍵＝真實 card；有鍵則 setdefault 不得覆蓋
    stub_card = _make_exact_card(**overrides)
    fanout_calls: list = []
    smart_calls: list = []

    def _smart(*_a, **_kw):
        smart_calls.append(True)
        return [stub_card]

    with (
        patch("core.scraper.smart_search", side_effect=_smart),
        patch("core.scraper.get_enabled_source_ids", side_effect=_fanout_recorder(fanout_calls)),
        patch("core.scraper.is_uncensored_mode_effective", return_value=False),
        patch("core.scraper.load_config", return_value={}),
    ):
        result = search_jav("ABC-123", first_hit=True)

    assert result is not None
    assert "_mode" not in result
    if with_original_title:
        assert result["original_title"] == "X"
    else:
        assert result["original_title"] == "FIRST"
    assert result["title"] == "FIRST"
    assert len(fanout_calls) == 0
    assert len(smart_calls) == 1


def test_first_hit_not_found_does_not_fall_back():
    """I-2：適用但 smart_search 回 [] → None，不進 fan-out。"""
    fanout_calls: list = []
    smart_calls: list = []

    def _smart(*_a, **_kw):
        smart_calls.append(True)
        return []

    with (
        patch("core.scraper.smart_search", side_effect=_smart),
        patch("core.scraper.get_enabled_source_ids", side_effect=_fanout_recorder(fanout_calls)),
        patch("core.scraper.is_uncensored_mode_effective", return_value=False),
        patch("core.scraper.load_config", return_value={}),
    ):
        result = search_jav("ABC-123", first_hit=True)

    assert result is None
    assert len(fanout_calls) == 0
    assert len(smart_calls) == 1


@pytest.mark.parametrize(
    "number,smart_results,javbus_lang,expect_smart_max",
    [
        # (a) 非番號格式且非無碼 → 不呼叫 smart_search，走 fan-out
        ("SSIS-001-C", None, None, 0),
        # (b) 第一筆 _mode=partial → 不採用，走 fan-out
        #     expect_smart_max=None：實作前後 smart 呼叫次數不同（實作前 0、後 1），
        #     鑑別力靠「不回 partial card」＋ recorder ≥1（_mode 守衛不佔 mutation）
        ("ABC-123", "partial", None, None),
        # (c) javbus_lang 有值 → 不進首擊，走 fan-out
        ("ABC-123", None, "ja", 0),
    ],
    ids=["non_number_format", "partial_first_result", "javbus_lang_given"],
)
def test_first_hit_falls_through_when_not_trustworthy(
    number, smart_results, javbus_lang, expect_smart_max,
):
    """I-3：不適用／不可信 → 逐字走既有 auto fan-out（recorder ≥1）。"""
    fanout_calls: list = []
    smart_calls: list = []

    def _smart(*_a, **_kw):
        smart_calls.append(True)
        if smart_results == "partial":
            return [_make_exact_card(_mode="partial", title="PARTIAL")]
        return []

    with (
        patch("core.scraper.smart_search", side_effect=_smart),
        patch("core.scraper.get_enabled_source_ids", side_effect=_fanout_recorder(fanout_calls)),
        patch("core.scraper.is_uncensored_mode_effective", return_value=False),
        patch("core.scraper.load_config", return_value={}),
    ):
        # fall-through 會進 auto fan-out；recorder 回 [] → search_jav 最終 None
        result = search_jav(number, first_hit=True, javbus_lang=javbus_lang)

    # 不得採信 partial／不適用結果（若誤採用會回 card 且 fan-out=0）
    assert result is None or result.get("title") != "PARTIAL"
    assert len(fanout_calls) >= 1
    if expect_smart_max is not None:
        assert len(smart_calls) == expect_smart_max
