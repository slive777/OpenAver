"""
tests/unit/test_fc_javten_cf_flow.py — TASK-118a-T4
===================================================
鏡射 test_javlibrary_cf_flow.py::TestSearchJavCfSentinelReRaise：
fc-javten 走 explicit 迴圈時，CF 例外必須 bubble（CD-118a-6）。

Patch 打消費端 core.scrapers.fc2_javten.get_cf_transport（BE-TEST-01）。
"""
import pytest
from unittest.mock import MagicMock, patch

from core.cf_transport import CfChallengeRequired, CfTransportUnavailable


def _make_mock_transport(*, navigate_side_effect=None, is_ready=False):
    t = MagicMock()
    if navigate_side_effect is not None:
        t.navigate_and_settle.side_effect = navigate_side_effect
    t.is_ready.return_value = is_ready
    return t


class TestSearchJavFcJavtenCfSentinelReRaise:
    """core/scraper.py explicit 迴圈對 fc-javten CF 例外的 re-raise。"""

    def test_search_jav_fc_javten_bubbles_cf_challenge_required(self):
        """FC2JavtenScraper.search() 拋 CfChallengeRequired → search_jav bubble。"""
        mock_transport = _make_mock_transport(
            navigate_side_effect=CfChallengeRequired("CF challenge detected")
        )
        with patch(
            "core.scrapers.fc2_javten.get_cf_transport",
            return_value=mock_transport,
        ):
            from core.scraper import search_jav
            with pytest.raises(CfChallengeRequired):
                search_jav("FC2-PPV-1234567", source="fc-javten")

    def test_search_jav_fc_javten_bubbles_cf_transport_unavailable(self):
        """get_cf_transport() 為 None → search_jav bubble CfTransportUnavailable。"""
        with patch(
            "core.scrapers.fc2_javten.get_cf_transport",
            return_value=None,
        ):
            from core.scraper import search_jav
            with pytest.raises(CfTransportUnavailable):
                search_jav("FC2-PPV-1234567", source="fc-javten")

    def test_search_jav_fc_javten_other_exception_continues_returns_none(self):
        """普通 RuntimeError → search_jav 回 None（continue，不 bubble）。"""
        mock_transport = _make_mock_transport(
            navigate_side_effect=RuntimeError("network error")
        )
        with patch(
            "core.scrapers.fc2_javten.get_cf_transport",
            return_value=mock_transport,
        ):
            from core.scraper import search_jav
            result = search_jav("FC2-PPV-1234567", source="fc-javten")
            assert result is None, "普通例外應被 continue 吞掉，回 None"


class TestCfSiteOriginsParity:
    """F-1：get_manual_only_sources() 每個 id 都必須在 origin 表裡。"""

    def test_cf_site_origins_covers_all_manual_only_sources(self):
        from core.source_config import get_manual_only_sources
        import web.routers.scraper as scraper_router

        table = getattr(scraper_router, "_CF_SITE_ORIGINS", None)
        assert table is not None, "F-1 違規：web.routers.scraper 缺少 _CF_SITE_ORIGINS"
        missing = [s.id for s in get_manual_only_sources() if s.id not in table]
        assert missing == [], (
            f"F-1 違規：manual_only 來源 {missing} 不在 _CF_SITE_ORIGINS — "
            "新增 CF 來源時必須同步 origin 表，禁止 silent fallback"
        )
        for sid, origin in table.items():
            assert origin, f"_CF_SITE_ORIGINS[{sid!r}] 不可為空"

    def test_per_site_behaviour_tables_cover_all_manual_only_sources(self):
        """transport 的兩張 per-site 行為表也要 parity（pre-merge Stage 2 FINDING 3）。

        兩張表都以 `.get(key, False)` fail-closed，所以漏列**不會拋錯、不會有任何測試轉紅**，
        只會讓那個來源安靜地拿到錯的行為。`_SITE_NAV_RESET` 漏列的症狀就是 118a-T6 剛修掉的那顆：
        使用者查第二次，CF 視窗跳出來停在上一頁不動，90 秒以上，只能關掉 App。

        只驗 key 覆蓋、不驗值——值是各站台的真實差異（javlibrary 有年齡閘、javten 沒有），
        該由加來源的人依站台實況決定，這裡只逼他「必須做出決定」。
        """
        import importlib.util
        from pathlib import Path
        from core.source_config import get_manual_only_sources

        impl_path = Path(__file__).resolve().parents[2] / "windows" / "cf_transport_impl.py"
        spec = importlib.util.spec_from_file_location("cf_transport_impl_parity", impl_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        ids = [s.id for s in get_manual_only_sources()]
        for table_name in ("_SITE_AGE_GATE", "_SITE_NAV_RESET"):
            table = getattr(mod, table_name, None)
            assert table is not None, f"cf_transport_impl 缺少 {table_name}"
            missing = [sid for sid in ids if sid not in table]
            assert missing == [], (
                f"{table_name} 漏列 manual_only 來源 {missing} —— 兩張表都是 fail-closed 的 "
                ".get(key, False)，漏列不會有任何測試轉紅，只會讓那個來源安靜地拿到錯的行為"
            )
