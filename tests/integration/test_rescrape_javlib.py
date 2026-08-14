"""
tests/integration/test_rescrape_javlib.py

/api/rescrape/preview (javlibrary 分支) + /api/enrich-single (detail_url 分支)
整合測試（FastAPI TestClient round-trip）。

patch target 一律為使用端：
  - web.routers.scraper.search_javlib_versions
  - web.routers.scraper.fetch_javlib_by_detail_url
  - web.routers.scraper.enrich_single
  - web.routers.scraper.get_cf_transport
（CD-86-12 / gotchas-backend §1）
"""
from unittest.mock import patch, MagicMock
import pytest


# ── helpers ──────────────────────────────────────────────────────────────────

def _ok_enrich_result(**kwargs):
    """建立成功的 EnrichResult（dataclass）作為 mock 回傳值。
    endpoint 用 asdict(result)，必須是真實 dataclass 才能序列化。
    """
    from core.enricher import EnrichResult
    defaults = dict(
        success=True,
        nfo_written=True,
        cover_written=True,
        extrafanart_written=0,
        fields_filled=[],
        source_used="javlibrary",
        error=None,
    )
    defaults.update(kwargs)
    return EnrichResult(**defaults)


# ── /api/rescrape/preview javlibrary 分支 ────────────────────────────────────

class TestRescrapePreviewJavlib:
    def test_preview_javlib_multi_returns_candidates(self, client):
        """
        source=javlibrary，search_javlib_versions 回 2 dict
        → resp 含 "candidates"（len 2），頂層無 "number" key（確認不是單筆 shape）。
        """
        two_dicts = [
            {"number": "MIDV-010", "url": ".../javme3bu7e.html", "title": "新片", "date": "2021-12-07"},
            {"number": "MIDV-010", "url": ".../javlidaori.html", "title": "舊片", "date": "2009-12-01"},
        ]
        with patch('web.routers.scraper.search_javlib_versions', return_value=two_dicts):
            resp = client.post("/api/rescrape/preview", json={
                "number": "MIDV-010", "source": "javlibrary",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "candidates" in data
        assert len(data["candidates"]) == 2
        assert "number" not in data  # 確認非單筆 shape

    def test_preview_javlib_single_backcompat(self, client):
        """
        source=javlibrary，search_javlib_versions 回 1 dict
        → resp 是單筆 shape（含 success + 欄位），無 candidates key（向下相容）。
        """
        one_dict = {"number": "MIDV-010", "url": ".../javme3bu7e.html", "title": "新片"}
        with patch('web.routers.scraper.search_javlib_versions', return_value=[one_dict]):
            resp = client.post("/api/rescrape/preview", json={
                "number": "MIDV-010", "source": "javlibrary",
            })

        data = resp.json()
        assert data["success"] is True
        assert "candidates" not in data
        assert data.get("number") == "MIDV-010"

    def test_preview_javlib_none_notfound(self, client):
        """
        source=javlibrary，search_javlib_versions 回 []
        → {"success": False}。
        """
        with patch('web.routers.scraper.search_javlib_versions', return_value=[]):
            resp = client.post("/api/rescrape/preview", json={
                "number": "MIDV-010", "source": "javlibrary",
            })

        assert resp.json() == {"success": False}

    def test_preview_javlib_cf_needed(self, client):
        """
        source=javlibrary，search_javlib_versions 拋 CfChallengeRequired
        → {"success": False, "cf_needed": True}（沿用既有 CF 流程）。
        """
        from core.cf_transport import CfChallengeRequired

        with patch('web.routers.scraper.search_javlib_versions',
                   side_effect=CfChallengeRequired("test")), \
             patch('web.routers.scraper.get_cf_transport', return_value=None):
            resp = client.post("/api/rescrape/preview", json={
                "number": "MIDV-010", "source": "javlibrary",
            })

        data = resp.json()
        assert data["success"] is False
        assert data.get("cf_needed") is True

    def test_preview_nonjavlib_unchanged(self, client):
        """
        source=dmm → 走原 search_jav_single_source，不進 javlibrary 分支，
        回單筆（回歸守衛）。
        """
        dmm_result = {
            "number": "SONE-205", "title": "DMM 片",
            "_source": "dmm", "_summary": None, "_rating": None,
        }
        with patch('web.routers.scraper.search_jav_single_source', return_value=dmm_result), \
             patch('web.routers.scraper.search_javlib_versions') as mock_jl:
            resp = client.post("/api/rescrape/preview", json={
                "number": "SONE-205", "source": "dmm",
            })

        mock_jl.assert_not_called()  # 確認未觸碰 javlib 分支
        data = resp.json()
        assert data["success"] is True
        assert "candidates" not in data


# ── /api/enrich-single detail_url 分支 ───────────────────────────────────────

class TestEnrichSingleDetailUrl:
    def test_enrich_single_javlib_detail_url(self, client):
        """
        source=javlibrary + detail_url 存在：
          fetch_javlib_by_detail_url 被呼叫
          → to_legacy_dict() 當 scraper_data 傳給 enrich_single
          → enrich_single 收到 scraper_data（非 None）。
        """
        from core.scrapers.models import Video

        fake_video = MagicMock(spec=Video)
        fake_video.to_legacy_dict.return_value = {
            "number": "MIDV-010",
            "url": ".../javme3bu7e.html",
            "title": "新片",
        }
        # P2：detail_url 路徑須補回 to_legacy_dict 省略的 _rating/_summary carrier
        fake_video.rating = 4.5
        fake_video.summary = "簡介內容"

        with patch('web.routers.scraper.fetch_javlib_by_detail_url',
                   return_value=fake_video) as mock_fetch, \
             patch('web.routers.scraper.enrich_single',
                   return_value=_ok_enrich_result()) as mock_enrich:
            resp = client.post("/api/enrich-single", json={
                "file_path": "file:///fake/MIDV-010.mp4",
                "number": "MIDV-010",
                "source": "javlibrary",
                "detail_url": "https://www.javlibrary.com/ja/javme3bu7e.html",
                "mode": "refresh_full",
                "overwrite_existing": True,
            })

        mock_fetch.assert_called_once_with(
            "https://www.javlibrary.com/ja/javme3bu7e.html", "MIDV-010"
        )
        call_kwargs = mock_enrich.call_args.kwargs
        scraper_data = call_kwargs.get("scraper_data")
        # scraper_data 為選定版本 to_legacy_dict() + 補回的內部 NFO carrier
        assert scraper_data is not None
        assert scraper_data["number"] == "MIDV-010"
        # P2 mutation guard：_rating/_summary carrier 須補回且值取自 video（否則 NFO 評分掉）
        assert scraper_data["_rating"] == 4.5
        assert scraper_data["_summary"] == "簡介內容"

    def test_enrich_single_rejects_non_javlibrary_detail_url(self, client):
        """
        P3 SSRF guard：source=javlibrary 但 detail_url 非 javlibrary origin
        （內網 metadata endpoint / 任意外站 / prefix 繞過）→ success False，
        且 fetch_javlib_by_detail_url 完全不被呼叫。
        """
        malicious_urls = [
            "http://169.254.169.254/latest/meta-data/",
            "https://evil.com/x.html",
            "https://www.javlibrary.com.evil.com/ja/x.html",  # prefix 繞過
            "http://www.javlibrary.com/ja/x.html",            # scheme 不符
        ]
        for bad_url in malicious_urls:
            with patch('web.routers.scraper.fetch_javlib_by_detail_url') as mock_fetch, \
                 patch('web.routers.scraper.enrich_single',
                       return_value=_ok_enrich_result()) as mock_enrich:
                resp = client.post("/api/enrich-single", json={
                    "file_path": "file:///fake/MIDV-010.mp4",
                    "number": "MIDV-010",
                    "source": "javlibrary",
                    "detail_url": bad_url,
                    "mode": "refresh_full",
                    "overwrite_existing": True,
                })
                assert resp.status_code == 200
                assert resp.json()["success"] is False, f"應拒絕 {bad_url}"
                mock_fetch.assert_not_called()  # 惡意 URL 絕不進 fetch
                mock_enrich.assert_not_called()

    def test_enrich_single_accepts_valid_javlibrary_detail_url(self, client):
        """
        P3：合法 javlibrary origin 的 detail_url → 正常進 fetch（origin guard 不誤殺）。
        """
        from core.scrapers.models import Video

        fake_video = MagicMock(spec=Video)
        fake_video.to_legacy_dict.return_value = {"number": "MIDV-010", "title": "新片"}
        fake_video.rating = 3.0
        fake_video.summary = ""

        with patch('web.routers.scraper.fetch_javlib_by_detail_url',
                   return_value=fake_video) as mock_fetch, \
             patch('web.routers.scraper.enrich_single',
                   return_value=_ok_enrich_result()):
            resp = client.post("/api/enrich-single", json={
                "file_path": "file:///fake/MIDV-010.mp4",
                "number": "MIDV-010",
                "source": "javlibrary",
                "detail_url": "https://www.javlibrary.com/ja/?v=javme3bu7e",
                "mode": "refresh_full",
                "overwrite_existing": True,
            })

        assert resp.json()["success"] is True
        mock_fetch.assert_called_once()

    def test_enrich_single_no_detail_url_unchanged(self, client):
        """
        source=javlibrary 但無 detail_url → scraper_data=None，
        enrich_single 自行重搜（現況行為不回歸）。
        fetch_javlib_by_detail_url 不應被呼叫。
        """
        with patch('web.routers.scraper.fetch_javlib_by_detail_url') as mock_fetch, \
             patch('web.routers.scraper.enrich_single',
                   return_value=_ok_enrich_result()) as mock_enrich:
            resp = client.post("/api/enrich-single", json={
                "file_path": "file:///fake/MIDV-010.mp4",
                "number": "MIDV-010",
                "source": "javlibrary",
                "mode": "refresh_full",
                "overwrite_existing": True,
            })

        mock_fetch.assert_not_called()
        call_kwargs = mock_enrich.call_args.kwargs
        assert call_kwargs.get("scraper_data") is None  # 無預餵，enrich_single 自行重搜


# ── TASK-118a-T4：fc-javten CF 接線（preview / enrich-single / readonly） ──

class TestRescrapePreviewFcJavtenCf:
    def test_preview_fc_javten_cf_needed_carries_cf_source(self, client):
        """CD-118a-7：fc-javten 觸發 CF → cf_needed + cf_source='fc-javten'，begin_solve 用 JAVTEN_ORIGIN。"""
        from core.cf_transport import CfChallengeRequired
        from core.scrapers.fc2_javten import JAVTEN_ORIGIN

        mock_t = MagicMock()
        with patch(
            'web.routers.scraper.search_jav_single_source',
            side_effect=CfChallengeRequired("test"),
        ), patch('web.routers.scraper.get_cf_transport', return_value=mock_t):
            resp = client.post("/api/rescrape/preview", json={
                "number": "FC2-PPV-1234567", "source": "fc-javten",
            })

        data = resp.json()
        assert resp.status_code == 200
        assert data["success"] is False
        assert data.get("cf_needed") is True
        assert data.get("cf_source") == "fc-javten"
        mock_t.begin_solve.assert_called_once_with(JAVTEN_ORIGIN, "fc-javten")

    def test_unknown_cf_source_does_not_begin_solve_or_fallback(self, client):
        """F-1：origin 表查不到 → 不 begin_solve、不 silent fallback 到 javlibrary。"""
        from core.cf_transport import CfChallengeRequired

        mock_t = MagicMock()
        with patch(
            'web.routers.scraper.search_jav_single_source',
            side_effect=CfChallengeRequired("test"),
        ), patch('web.routers.scraper.get_cf_transport', return_value=mock_t):
            resp = client.post("/api/rescrape/preview", json={
                "number": "SONE-205", "source": "javbus",
            })

        data = resp.json()
        assert resp.status_code == 200
        assert data["success"] is False
        assert data.get("cf_needed") is not True
        assert "cf_source" not in data or data.get("cf_source") is None
        mock_t.begin_solve.assert_not_called()

    def test_preview_fc_javten_transport_unavailable_returns_cf_unavailable(self, client):
        """AC-2.5：dev／區網選 fc-javten → {success:false, cf_unavailable:true}。

        鏡射 test_api_cf_endpoints.test_cf_transport_unavailable_returns_cf_unavailable，
        但走 search_jav_single_source 分支（不是 javlibrary 的 search_javlib_versions）。
        patch 使用端 web.routers.scraper.search_jav_single_source，side_effect 轉發
        真實函式：transport=None 時 FC2JavtenScraper.search 必須拋 CfTransportUnavailable。
        可證偽：search() 若改成 return None，使用者會拿到「查無此片」而非「僅限桌面版」。
        """
        from core.scraper import search_jav_single_source as _real_single

        with patch(
            'web.routers.scraper.search_jav_single_source',
            side_effect=_real_single,
        ), patch(
            'core.scrapers.fc2_javten.get_cf_transport',
            return_value=None,
        ):
            resp = client.post("/api/rescrape/preview", json={
                "number": "FC2-PPV-1234567", "source": "fc-javten",
            })

        data = resp.json()
        assert resp.status_code == 200
        assert data.get("success") is False
        assert data.get("cf_unavailable") is True


class TestEnrichSingleFcJavtenCf:
    def test_enrich_single_fc_javten_cf_needed(self, client):
        """CD-118a-16：confirm 抓取被 CF 擋 → {success:false, cf_needed, cf_source}，不是籠統失敗。"""
        from core.cf_transport import CfChallengeRequired
        from core.scrapers.fc2_javten import JAVTEN_ORIGIN

        mock_t = MagicMock()
        with patch('web.routers.scraper.resolve_owning_output_root', return_value=None), \
             patch('web.routers.scraper.enrich_single',
                   side_effect=CfChallengeRequired("test")), \
             patch('web.routers.scraper.get_cf_transport', return_value=mock_t):
            resp = client.post("/api/enrich-single", json={
                "file_path": "file:///fake/FC2-PPV-1234567.mp4",
                "number": "FC2-PPV-1234567",
                "source": "fc-javten",
                "mode": "refresh_full",
                "overwrite_existing": True,
            })

        data = resp.json()
        assert resp.status_code == 200
        assert data["success"] is False
        assert data.get("cf_needed") is True
        assert data.get("cf_source") == "fc-javten"
        assert data.get("error") != "enrich 處理失敗，請查閱日誌"
        mock_t.begin_solve.assert_called_once_with(JAVTEN_ORIGIN, "fc-javten")

    def test_enrich_single_readonly_fc_javten_cf_needed_full_shape(self, client):
        """CD-118a-16 + F-0：readonly 路徑回完整 EnrichResult ＋ additive cf_needed/cf_source。"""
        from core.cf_transport import CfChallengeRequired
        from core.enrich_contract import EnrichResult
        from core.scrapers.fc2_javten import JAVTEN_ORIGIN

        mock_source = MagicMock()
        mock_source.path = "/tmp/ro_src"
        mock_t = MagicMock()
        with patch(
            'web.routers.scraper.resolve_owning_output_root',
            return_value=(mock_source, "/out/ro", "file:///out/ro"),
        ), patch(
            'web.routers.scraper.enrich_one_readonly',
            side_effect=CfChallengeRequired("test"),
        ), patch('web.routers.scraper.get_cf_transport', return_value=mock_t):
            resp = client.post("/api/enrich-single", json={
                "file_path": "file:///tmp/ro_src/FC2-PPV-1234567.mp4",
                "number": "FC2-PPV-1234567",
                "source": "fc-javten",
                "readonly_action": "rescrape",
                "write_nfo": True,
            })

        data = resp.json()
        assert resp.status_code == 200
        expected_fields = {f.name for f in EnrichResult.__dataclass_fields__.values()}
        assert expected_fields <= set(data.keys()), (
            f"F-0 違規：readonly CF 回應缺少 EnrichResult 欄位 {expected_fields - set(data.keys())}"
        )
        assert data["success"] is False
        assert data["nfo_written"] is False
        assert data["cover_written"] is False
        assert data["extrafanart_written"] == 0
        assert data["fields_filled"] == []
        assert data["source_used"] == ""
        assert data.get("cf_needed") is True
        assert data.get("cf_source") == "fc-javten"
        mock_t.begin_solve.assert_called_once_with(JAVTEN_ORIGIN, "fc-javten")


# ── capabilities 全檔守衛 ─────────────────────────────────────────────────────

def test_detail_url_not_in_capabilities():
    """
    CD-86-10 capabilities 全檔守衛：
    "detail_url" 字串在整個 web/routers/capabilities.py 完全不出現。
    EnrichRequest 新增 detail_url 後不可洩露到 capabilities JSON（任何 capability）。
    """
    import pathlib
    src = pathlib.Path("web/routers/capabilities.py").read_text(encoding="utf-8")
    assert "detail_url" not in src, (
        "detail_url 不可揭露給 AI agent（CD-86-10 / spec AC9）"
    )
