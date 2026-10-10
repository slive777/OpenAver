"""TASK-163a-T5 — 重刮預覽／指定來源搜尋回報 access_error。

假回應只驗接線；2026-10-09 實測台灣直連活站回 200，沒有可重現的真封鎖回應。
假回應放在 HTTP 邊界（requests.Session.post），不 patch search_jav_single_source，
讓 explicit 分支的 re-raise 真的被走到。
"""
from unittest.mock import MagicMock, patch

import pytest
import requests

import core.scraper as scraper_mod
from core.scrapers.errors import SourceBlocked
from core.scrapers.models import Video


@pytest.fixture(autouse=True)
def _isolated(temp_config_path, monkeypatch):
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(k, raising=False)
    import core.scrapers.dmm as dmm_module

    monkeypatch.setattr(dmm_module, "rate_limit", lambda *a, **kw: None)


def _resp(status=200, data=None):
    r = MagicMock()
    r.status_code = status
    r.json = lambda: data if data is not None else {"data": {"ppvContent": None, "legacySearchPPV": None}}
    return r


# (名稱, post 的行為, 預期 access_error)
CASES = [
    ("403", {"return_value": _resp(403)}, "refused"),
    ("500", {"return_value": _resp(500)}, "refused"),
    ("conn", {"side_effect": requests.ConnectionError("x")}, "unreachable"),
    ("200-empty", {"return_value": _resp(200)}, None),
]


@pytest.mark.parametrize("name,post_kw,expected", CASES, ids=[c[0] for c in CASES])
def test_rescrape_preview_access_error_by_response_kind(client, name, post_kw, expected):
    with patch.object(requests.Session, "post", **post_kw):
        r = client.post("/api/rescrape/preview", json={"number": "SONE-205", "source": "dmm"})
    body = r.json()
    assert r.status_code == 200
    assert body["success"] is False
    if expected is None:
        assert "access_error" not in body
    else:
        assert body["access_error"] == expected
        assert body["source"] == "dmm"


@pytest.mark.parametrize("name,post_kw,expected", CASES, ids=[c[0] for c in CASES])
def test_api_search_exact_source_access_error_by_response_kind(client, name, post_kw, expected):
    with patch.object(requests.Session, "post", **post_kw):
        r = client.get("/api/search", params={"q": "SONE-205", "mode": "exact", "source": "dmm"})
    body = r.json()
    assert body["success"] is False
    assert body["data"] == [] and body["total"] == 0 and body["mode"] == "exact"
    if expected is None:
        assert "access_error" not in body
    else:
        assert body["access_error"] == expected
        assert body["source"] == "dmm"
        assert "DMM" in body["error"]
        assert ("拒絕連線" if expected == "refused" else "連不到") in body["error"]


def test_access_error_advice_only_for_jp_ip_sources(client):
    """DMM 被拒附日本 IP 建議句；JavDB 被拒同樣 refused 但不附。"""
    with patch.object(requests.Session, "post", return_value=_resp(403)):
        dmm = client.get("/api/search", params={"q": "SONE-205", "mode": "exact", "source": "dmm"}).json()
    assert "日本 IP" in dmm["error"]

    class _Blocked:
        def search(self, number):
            raise SourceBlocked("JavDB: HTTP 403")

    with patch("core.scraper.JavDBScraper", lambda *a, **k: _Blocked()):
        jd = client.get("/api/search", params={"q": "SONE-205", "mode": "exact", "source": "javdb"}).json()
        rp = client.post("/api/rescrape/preview", json={"number": "SONE-205", "source": "javdb"}).json()
    assert jd["access_error"] == "refused" and jd["source"] == "javdb"
    assert "日本 IP" not in jd["error"]
    assert rp["access_error"] == "refused" and rp["source"] == "javdb"


def test_default_search_jav_still_swallows_access_errors():
    with patch.object(requests.Session, "post", return_value=_resp(403)):
        assert scraper_mod.search_jav("SONE-205", source="dmm") is None
        assert scraper_mod.search_jav_single_source("SONE-205", "dmm") is None


def test_auto_search_dmm_refused_other_sources_still_return(monkeypatch):
    class _Blocked:
        def search(self, number):
            raise SourceBlocked("DMM: HTTP 403")

    class _Bus:
        def search(self, number):
            return Video(number="SONE-205", title="t", source="javbus")

    monkeypatch.setattr(scraper_mod, "get_enabled_source_ids", lambda availability_map=None: ["dmm", "javbus"])
    monkeypatch.setattr(scraper_mod, "DMMScraper", lambda *a, **k: _Blocked())
    monkeypatch.setattr(scraper_mod, "JavBusScraper", lambda *a, **k: _Bus())
    result = scraper_mod.search_jav("SONE-205", source="auto")
    assert result is not None and result["_source"] == "javbus"
