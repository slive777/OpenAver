"""DoD 6：不補零第二試／搜尋 API 兩條補償路徑的真連線驗證（TASK-134b-T10）.

三筆各鎖不同路徑（見 TASK-134b-T10 佐證表 C）：
  MIDD-357 / KAWD-067 → 不補零第二試
  NWF-237             → 搜尋 API（queryWord "NWF 237" → 3nwf237）

需日本線路。外部不可達時 skip；HTTP 通了但回空 → fail（與 D8 同形）。
CI 排除（--ignore=tests/smoke / -m "not smoke"）。
"""
import pytest

from core.scrapers.dmm import DMMScraper

pytestmark = pytest.mark.smoke

# (番號, 期望 makerContentId) — 期望值由主 session 2026-08-29 實測，不得自行更動
RESCUE_CASES = (
    ("MIDD-357", "MIDD-357"),
    ("KAWD-067", "KAWD-067"),
    ("NWF-237", "NWF-237"),
)


@pytest.mark.smoke
@pytest.mark.parametrize("number,expected_number", RESCUE_CASES)
def test_dmm_rescues_second_try_or_search_api(number, expected_number):
    """對補零算不出、但 DMM 確實收錄的番號，真實 search() 應救回正確片。"""
    scraper = DMMScraper()

    try:
        result = scraper.search(number)
    except Exception as e:
        pytest.skip(f"DMM 連線失敗（{type(e).__name__}: {e}）")

    if result is None:
        pytest.fail(
            f"DMM 救回失敗或回空（番號={number}；"
            "HTTP 已通但查無結果——不是環境未就緒）"
        )

    assert result.number == expected_number
