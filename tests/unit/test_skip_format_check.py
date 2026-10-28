"""TASK-183-T1：進階搜尋 javdb 照原樣查（skip_format_check 旗標）— 三條守住的行為。

零網路：JavDBScraper 的兩條資料通道、jav321 的 post_html 一律 stub。
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from core.scraper import search_jav, search_jav_single_source
from core.scrapers.javdb import JavDBScraper

pytestmark = pytest.mark.usefixtures("isolate_reconcile_db")


def test_search_jav_skip_format_check_gates_by_source(monkeypatch):
    api_calls = []  # (number, scraper 實際收到的旗標)
    monkeypatch.setattr(
        JavDBScraper, "search_via_api",
        lambda self, n: api_calls.append((n, getattr(self, "skip_format_check", None))),
    )
    monkeypatch.setattr(JavDBScraper, "search_via_html", lambda self, n: None)
    monkeypatch.setattr("core.scraper.get_enabled_source_ids", lambda **kw: ["javdb"])
    state = MagicMock()
    state.is_connected = False
    state.routing_availability_map.return_value = {}
    monkeypatch.setattr("core.scraper.metatube_state", state)

    # 進得去：javdb + True（search_jav 與 single_source 兩個入口）
    assert search_jav("MKD-S85", source="javdb", skip_format_check=True) is None
    assert search_jav_single_source("MKD-S85", "javdb", skip_format_check=True) is None
    assert api_calls == [("MKD-S85", True), ("MKD-S85", True)]

    # 仍被擋：旗標預設 False
    api_calls.clear()
    assert search_jav("MKD-S85", source="javdb") is None
    assert api_calls == []

    # 反向格：auto + True 不放寬（MKD-S85 進不去；標準番號建出的 scraper 旗標為 False）
    assert search_jav("MKD-S85", source="auto", skip_format_check=True) is None
    assert api_calls == []
    assert search_jav("SONE-205", source="auto", skip_format_check=True) is None
    assert api_calls == [("SONE-205", False)]

    # 反向格：jav321 + True 不放寬（SONE 不得進 scraper 的 POST）
    with patch("core.scrapers.jav321.post_html") as post:
        assert search_jav("SONE", source="jav321", skip_format_check=True) is None
    post.assert_not_called()


def test_enrich_single_refresh_full_passes_skip_format_check_to_search_jav(tmp_path):
    from web.app import app

    video = tmp_path / "XXX-AV-20433.mp4"
    video.write_bytes(b"x")
    body = {
        "file_path": str(video), "number": "XXX-AV-20433", "mode": "refresh_full",
        "overwrite_existing": True, "source": "javdb",
    }
    cfg = {"search": {"proxy_url": ""}, "gallery": {}, "scraper": {}}
    seen = []
    with (
        patch("web.routers.scraper.load_config", return_value=cfg),
        patch("core.enricher.VideoRepository"),
        patch("core.enricher.search_jav", side_effect=lambda *a, **kw: seen.append(kw) or None),
    ):
        client = TestClient(app)
        client.post("/api/enrich-single", json={**body, "skip_format_check": True})
        client.post("/api/enrich-single", json=body)

    assert [kw.get("skip_format_check") for kw in seen] == [True, False]


@pytest.mark.parametrize("action,expect", [("rescrape", True), ("ingest", None)])
def test_resolve_ingest_plan_rescrape_branch_receives_skip_format_check(tmp_path, action, expect):
    from core.readonly_producer import resolve_ingest_plan

    video = tmp_path / "SRC-001.mp4"
    video.write_bytes(b"FAKE")
    with (
        patch("core.readonly_producer.search_jav_single_source", return_value=None) as single,
        patch("core.readonly_producer.search_jav", return_value=None),
        patch("core.readonly_producer.VideoScanner"),
    ):
        resolve_ingest_plan(
            str(video), "SRC-001", {}, action=action, source="javdb", skip_format_check=True,
        )

    assert single.call_args.kwargs.get("skip_format_check") is expect
