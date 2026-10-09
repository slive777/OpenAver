"""TASK-134a-T6 — 步驟 3 回空時 debug.log 留痕（spec-134 F5 / CD-134-7）。"""
import logging

import pytest

import core.scrapers.dmm as dmm_module
from core.scrapers.dmm import DMMScraper
from core.proxy_policy import ProxySettings
from core.scrapers.models import ScraperConfig, Video

LOG_SNIPPET = "搜尋 API 查無結果"


@pytest.fixture
def dmm_scraper(monkeypatch):
    monkeypatch.setattr(dmm_module, "_shipped_table_cache", {})
    monkeypatch.setattr(dmm_module, "rate_limit", lambda *a, **kw: None)
    return DMMScraper(ScraperConfig(proxy_settings=ProxySettings(url="http://test-proxy:8080")))


def test_step3_miss_logs_debug_with_number(dmm_scraper, caplog, monkeypatch):
    """DoD 1：discovered_cid 為 None → caplog 抓到一行 DEBUG，內容含番號。"""

# ⚠️ 本檔的函式名與 docstring 裡的「步驟 N」沿用 T12 **之前**的編號
#    （當時：1 查快取／2 前綴轉換／3 搜尋 API／4 手貼 cid）。
#    T12 刪掉逐番號快取後 search() 只剩三步，搜尋 API 現在是**步驟 2**。
#    測試邏輯本身沒有受影響（斷言的是機制不是編號）；不批次改名是為了
#    避免一次為零使用者價值的重命名產生大 diff——見 TASK-134b-T12 的已接受 residual。
    monkeypatch.setattr(dmm_scraper, "_convert_with_hints", lambda number: "")
    monkeypatch.setattr(dmm_scraper, "_search_content_id", lambda number: None)

    with caplog.at_level(logging.DEBUG, logger=dmm_module.logger.name):
        result = dmm_scraper.search("ZZZZ-999")

    assert result is None
    debug_records = [r for r in caplog.records if r.levelno == logging.DEBUG]
    assert any(
        LOG_SNIPPET in r.getMessage() and "ZZZZ-999" in r.getMessage()
        for r in debug_records
    )


def test_step3_hit_no_log(dmm_scraper, caplog, monkeypatch):
    """DoD 2 正向鎖：步驟 3 命中（discovered_cid 有值且 _fetch_by_id 成功）→ 不誤觸發。"""
    video = Video(number="ZZZZ-999", title="t", source="dmm")
    monkeypatch.setattr(dmm_scraper, "_convert_with_hints", lambda number: "")
    monkeypatch.setattr(dmm_scraper, "_search_content_id", lambda number: "zzzz00999")
    monkeypatch.setattr(
        dmm_scraper,
        "_fetch_by_id",
        lambda cid: video if cid == "zzzz00999" else None,
    )

    with caplog.at_level(logging.DEBUG, logger=dmm_module.logger.name):
        result = dmm_scraper.search("ZZZZ-999")

    assert result is not None
    assert not any(LOG_SNIPPET in r.getMessage() for r in caplog.records)


def test_step2_hit_step3_not_reached_no_log(dmm_scraper, caplog, monkeypatch):
    """DoD 3：步驟 2 已成功 → 步驟 3 完全不執行 → 不誤導印步驟 3 失敗訊息。"""
    video = Video(number="ZZZZ-999", title="t", source="dmm")
    step3_called = {"value": False}

    def _search_content_id_spy(number):
        step3_called["value"] = True
        return None

    monkeypatch.setattr(dmm_scraper, "_convert_with_hints", lambda number: "zzzz00999")
    monkeypatch.setattr(
        dmm_scraper,
        "_fetch_by_id",
        lambda cid: video if cid == "zzzz00999" else None,
    )
    monkeypatch.setattr(dmm_scraper, "_search_content_id", _search_content_id_spy)

    with caplog.at_level(logging.DEBUG, logger=dmm_module.logger.name):
        result = dmm_scraper.search("ZZZZ-999")

    assert result is not None
    assert step3_called["value"] is False
    assert not any(LOG_SNIPPET in r.getMessage() for r in caplog.records)


def test_step3_cid_found_but_fetch_fails_no_log(dmm_scraper, caplog, monkeypatch):
    """DoD 4（A18 範圍縮小）：discovered_cid 有值但 _fetch_by_id 回 None → 不印。"""
    monkeypatch.setattr(dmm_scraper, "_convert_with_hints", lambda number: "")
    monkeypatch.setattr(dmm_scraper, "_search_content_id", lambda number: "zzzz00999")
    monkeypatch.setattr(dmm_scraper, "_fetch_by_id", lambda cid: None)

    with caplog.at_level(logging.DEBUG, logger=dmm_module.logger.name):
        result = dmm_scraper.search("ZZZZ-999")

    assert result is None
    assert not any(LOG_SNIPPET in r.getMessage() for r in caplog.records)


# ── Codex review 追加（P3-1）────────────────────────────────────────────────


def test_raw_cid_input_does_not_log_step3(dmm_scraper, caplog, monkeypatch):
    """完整 cid 輸入 → _search_content_id 發請求前就 return None → 不得留痕。

    這條路接著被步驟 4 救回來（搜尋其實成功），若仍印「可能是地區限制」，
    之後拿 debug.log 排錯的人會被誤導去查 VPN。
    """
    video = Video(number="ID-057", title="t", source="dmm")
    monkeypatch.setattr(
        dmm_scraper,
        "_fetch_by_id",
        lambda cid: video if cid == "h_113id00057" else None,
    )

    with caplog.at_level(logging.DEBUG, logger=dmm_module.logger.name):
        result = dmm_scraper.search("h_113id00057")

    assert result is not None
    assert not any(LOG_SNIPPET in r.getMessage() for r in caplog.records)


def test_raw_cid_input_that_also_fails_still_does_not_log(
    dmm_scraper, caplog, monkeypatch
):
    """反向鎖：步驟 4 也失敗時同樣不得留痕——判準是『番號可不可解析』，
    不是『最後有沒有找到』。避免用 result is not None 之類的假條件過關。"""
    monkeypatch.setattr(dmm_scraper, "_fetch_by_id", lambda cid: None)

    with caplog.at_level(logging.DEBUG, logger=dmm_module.logger.name):
        result = dmm_scraper.search("h_113id00057")

    assert result is None
    assert not any(LOG_SNIPPET in r.getMessage() for r in caplog.records)
