"""
test_scraper_live.py - 供應商連通 Smoke Tests

⚠️ 只用於本地手動測試，不進 CI（避免被 ban）

執行方式：
    pytest tests/smoke -v -m smoke

注意：
- 只測文字資料，不抓圖片
- 無法連線時自動 skip，不算失敗
"""

import pytest
from core.scraper import search_jav


@pytest.mark.smoke
class TestScraperLive:
    """各供應商連通測試 - 僅本地手動跑"""

    def test_javbus_connectivity(self):
        """JavBus 連通性測試"""
        result = search_jav("SONE-103", source="javbus")
        if result is None:
            pytest.skip("JavBus 無法連線或無結果")

        assert result.get('number') == 'SONE-103', f"番號不符: {result.get('number')}"
        assert result.get('title'), "標題為空"
        # actors 可能為空，不強制要求

    def test_jav321_connectivity(self):
        """Jav321 連通性測試"""
        result = search_jav("SONE-103", source="jav321")
        if result is None:
            pytest.skip("Jav321 無法連線或無結果")

        assert result.get('number') == 'SONE-103', f"番號不符: {result.get('number')}"
        assert result.get('title'), "標題為空"

    def test_javdb_connectivity(self):
        """JavDB 連通性測試"""
        result = search_jav("SONE-103", source="javdb")
        if result is None:
            pytest.skip("JavDB 無法連線或無結果")

        assert result.get('number') == 'SONE-103', f"番號不符: {result.get('number')}"
        assert result.get('title'), "標題為空"

    def test_auto_source_connectivity(self):
        """自動來源連通性測試（至少一個來源可用）"""
        result = search_jav("MIDV-139", source="auto")
        if result is None:
            pytest.skip("所有來源無法連線")

        # 只要有結果就算通過
        assert result.get('number'), "無番號返回"


@pytest.mark.smoke
class TestActressSearch:
    """女優搜尋連通測試"""

    def test_actress_search_connectivity(self):
        """女優搜尋連通性"""
        from core.scraper import search_actress

        results = search_actress("三上悠亞", limit=5)
        if not results:
            pytest.skip("女優搜尋無法連線或無結果")

        assert len(results) >= 1, "至少應返回 1 個結果"
        assert results[0].get('number'), "結果應包含番號"
