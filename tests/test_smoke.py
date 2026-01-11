import pytest
from core.scraper import extract_number, search_jav, normalize_number

# 單元測試：番號提取邏輯
@pytest.mark.parametrize("filename,expected", [
    ("SONE-103.mp4", "SONE-103"),
    ("fc2-ppv-123456.mkv", "FC2-PPV-123456"),
    ("[IPZZ-001] Title.avi", "IPZZ-001"),
    ("ipzz001.mp4", "IPZZ-001"), # 不帶橫線
    ("abc-123.mp4", "ABC-123"),
])
def test_extract_number(filename, expected):
    assert extract_number(filename) == expected

# 單元測試：番號標準化
def test_normalize_number():
    assert normalize_number("sone103") == "SONE-103"
    assert normalize_number("SONE-103") == "SONE-103"
    assert normalize_number("ipzz-01") == "IPZZ-01"

# 煙霧測試：真實網路請求
# 警告：此測試依賴外部網路和目標網站狀態
@pytest.mark.smoke
def test_scraper_connection():
    """
    測試爬蟲連通性
    抓取一個非常舊且穩定的番號，確認不是 None
    """
    # 這裡我們只測試 'auto' 模式，讓它自己去試 JavBus 或 Jav321
    # 選擇一個常見番號
    result = search_jav("SONE-103")
    
    # 如果網路不通或網站掛了，這裡可能會 None，但在 CI 中通常會預期失敗或 Skip
    # 這裡我們做一個軟性斷言
    if result is None:
        pytest.skip("Scraper returned None, possibly network issue or site blocked")
    
    assert result['number'] == 'SONE-103'
    assert result['title'] is not None
    assert len(result['actors']) > 0
