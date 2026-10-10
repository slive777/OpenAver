"""DoD 6 / F2：步驟 3 真連線救回表算不出來的片（TASK-134a-T4）.

需日本線路（legacySearchPPV）。外部不可達時 skip，不是 fail。
CI 排除（--ignore=tests/smoke / -m "not smoke"）。
"""
import pytest

from core.scrapers.dmm import DMMScraper

pytestmark = pytest.mark.smoke

# NWF 系列（ワンズファクトリー）真實 cid 帶數字前綴（3nwf237）；不在出貨表與收割名單中。
# 空 hints 下 _convert_with_hints → "nwf00237"，第一試必然失敗（DMM 查無此 cid），
# 只能靠搜尋 API 那一步救回。若未來 refresh 收錄 nwf 前綴，下面的前提自檢會報錯。
RESCUE_NUMBER = "NWF-237"


@pytest.mark.smoke
def test_dmm_step3_rescues_number_not_convertible_by_hints():
    """對 hints 算不出正確 cid、但 DMM 確實收錄的番號，真實 search() 應救回。"""
    scraper = DMMScraper()

    # 防衛：出貨表算不出正確 cid（nwf 不在表裡），只能靠搜尋 API 那一步救回。
    #
    # ⚠️ 2026-08-29 branch review P3：原本寫的是 `assert converted != "3nwf237"`，
    # 那條**恆真**——`_convert_with_hints` 預設 `zfill=True`，`"237".zfill(5)`
    # 永遠是 `"00237"`，回傳值不可能等於 `3nwf237`。於是 docstring 宣稱的
    # 「refresh 收錄 nwf 後前提崩壞會報錯」根本不會發生：那時這支會改由
    # 「不補零第二試」通過而**看起來還是綠的**，搜尋 API 救援路徑就此失去
    # 它唯一的真連線守衛（見 gotchas-backend.md `BE-TEST-23`）。
    # 直接斷言真正的前提：nwf 不在表裡。
    prefix_map = scraper._prefix_map()
    assert prefix_map, "出貨表讀不到 ⇒ 下一條斷言會空轉（同 BE-TEST-23 的防恆真）"
    assert "nwf" not in prefix_map, (
        "測試前提崩壞：nwf 已被收進出貨表，這支不再測得到搜尋 API 救援路徑"
    )

    try:
        result = scraper.search(RESCUE_NUMBER)
    except Exception as e:
        pytest.skip(f"DMM 連線失敗（{type(e).__name__}: {e}）")

    if result is None:
        pytest.fail(
            f"DMM 步驟 3 救回失敗或回空（番號={RESCUE_NUMBER}；"
            "HTTP 已通但查無結果——不是環境未就緒）"
        )

    assert result is not None
