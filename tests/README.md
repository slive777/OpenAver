# Testing Guide

JavHelper 使用 `pytest` 作為測試框架。目前的測試套件設計為「輕量級」，專注於核心 API 穩定性與外部服務連通性。

## 前置準備

確保您已在虛擬環境中，並安裝了測試依賴：

```bash
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install pytest httpx
```

## 執行測試

### 執行所有測試
在專案根目錄下執行：

```bash
pytest
```

這將會執行：
1.  **API 測試** (`test_api_config.py`): 驗證設定檔的讀取與寫入，確保不會破壞 `config.json`。
2.  **單元測試** (`test_smoke.py`): 驗證番號提取邏輯。
3.  **煙霧測試** (`test_smoke.py`): 實際連線至 JavDB/JavBus 抓取資料，驗證爬蟲是否可用。

### 只執行特定測試

**只測 API (快速，不連網):**
```bash
pytest tests/test_api_config.py
```

**只測爬蟲 (慢，需連網):**
```bash
pytest -m smoke
```

## 測試結構

- `conftest.py`: 定義全域 Fixtures，包含 `client` (FastAPI TestClient) 和 `temp_config_path` (Mock 設定檔)。
- `test_api_config.py`: 針對 `/api/config` 的整合測試。
- `test_smoke.py`: 針對 `core.scraper` 的邏輯測試與連線測試。

## 注意事項

- **Mock 設定**: 測試過程中會使用臨時設定檔，**不會** 修改您真實的 `config.json`。
- **網路依賴**: `test_smoke.py` 中的 `test_scraper_connection` 會發送真實 HTTP 請求。如果您的網路無法連線至 JavDB/JavBus，此測試可能會失敗或被跳過。
