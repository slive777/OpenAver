# Testing Guide

OpenAver 使用 `pytest` 作為測試框架。測試套件分為三層：單元測試、整合測試、煙霧測試。

## 前置準備

```bash
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install pytest pytest-asyncio pytest-mock httpx
```

## 目錄結構

```
tests/
├── conftest.py              # 全域 Fixtures
├── test_api_config.py       # Config API 整合測試
├── test_smoke.py            # 基本煙霧測試（番號提取、爬蟲連通）
├── test_scrapers.py         # 6 個爬蟲模組測試（Phase 16）
│
├── unit/                    # 單元測試（不需網路）
│   ├── test_scraper_parser.py    # 番號解析測試
│   ├── test_path_utils.py        # 跨平台路徑轉換測試
│   └── test_translate_service.py # 翻譯服務抽象層測試
│
├── integration/             # 整合測試（使用 Mock）
│   ├── test_api_search.py        # 搜尋 API 測試
│   └── test_api_gallery.py       # Gallery API 測試
│
├── smoke/                   # 煙霧測試（需網路/服務）
│   ├── test_scraper_live.py      # 6 個爬蟲連通測試
│   ├── test_translate_live.py    # Ollama 翻譯連通測試
│   ├── test_batch_api.py         # 批次翻譯 API 測試
│   ├── test_gemini_safety_settings.py  # Gemini 安全設定測試
│   └── test_translate_gemini_manual.py # Gemini 手動測試
│
├── fixtures/                # Mock 測試資料
│   └── responses/
│       ├── javbus/SONE-103.json
│       └── javdb/actress_search.json
│
└── samples/                 # 番號解析測試樣本
    ├── basic/               # 基本格式 (SONE-103.mp4)
    ├── real_world/          # 真實世界格式
    ├── special_format/      # 特殊片商格式
    └── expected_results.json
```

## 執行測試

### 快速測試（CI 適用，不需網路）

```bash
# 所有單元測試
pytest tests/unit/ -v

# 整合測試（使用 Mock）
pytest tests/integration/ -v

# 基本煙霧測試
pytest tests/test_smoke.py tests/test_scrapers.py -v
```

### 完整測試（需網路）

```bash
# 所有測試
pytest

# 只跑煙霧測試（爬蟲連通）
pytest -m smoke -v
```

### 特定測試

```bash
# Config API 測試
pytest tests/test_api_config.py -v

# 番號解析測試
pytest tests/unit/test_scraper_parser.py -v

# 路徑轉換測試
pytest tests/unit/test_path_utils.py -v

# 翻譯服務測試
pytest tests/unit/test_translate_service.py -v

# 6 個爬蟲模組測試
pytest tests/test_scrapers.py -v

# 爬蟲連通測試（需網路）
pytest tests/smoke/test_scraper_live.py -v -m smoke
```

## 測試分類

### 單元測試 (`unit/`)

不需要網路，測試純邏輯：

| 檔案 | 測試內容 |
|------|----------|
| `test_scraper_parser.py` | `extract_number()`, `normalize_number()` |
| `test_path_utils.py` | 跨平台路徑轉換 (WSL/Windows/Linux/Mac) |
| `test_translate_service.py` | 翻譯服務工廠、配置處理 |

### 整合測試 (`integration/`)

使用 Mock 測試 API 端點：

| 檔案 | 測試內容 |
|------|----------|
| `test_api_search.py` | 搜尋 API、模式切換、分頁 |
| `test_api_gallery.py` | 圖片代理、Gallery 統計 |

### 煙霧測試 (`smoke/`)

實際連線外部服務：

| 檔案 | 測試內容 | 前提條件 |
|------|----------|----------|
| `test_scraper_live.py` | 6 個爬蟲連通性 | 網路 |
| `test_translate_live.py` | Ollama 翻譯 | Ollama 服務 |
| `test_batch_api.py` | 批次翻譯 API | FastAPI + Ollama |
| `test_gemini_safety_settings.py` | Gemini 安全設定 | Gemini API Key |

### 爬蟲模組測試 (`test_scrapers.py`)

Phase 16 新增的 6 個爬蟲模組測試：

| 爬蟲 | 測試內容 | 備註 |
|------|----------|------|
| JavBusScraper | 番號搜尋、正規化 | 需 jvav 套件 |
| JAV321Scraper | 番號搜尋、關鍵字搜尋 | |
| JavDBScraper | 番號搜尋、封面來源 | 需 curl_cffi |
| DMMScraper | 番號解析、前綴轉換、快取 | 需日本 VPN |
| FC2Scraper | FC2 番號正規化、搜尋 | |
| AVSOXScraper | 無碼番號搜尋 | |

## Fixtures

### conftest.py

```python
@pytest.fixture
def client():
    """FastAPI TestClient"""

@pytest.fixture
def temp_config_path(tmp_path, monkeypatch):
    """Mock config.json（不修改真實配置）"""

@pytest.fixture
def mock_wsl_env(monkeypatch):
    """模擬 WSL 環境"""

@pytest.fixture
def mock_windows_env(monkeypatch):
    """模擬 Windows 環境"""
```

## 注意事項

- **Mock 設定**: 測試使用臨時配置檔，**不會**修改真實 `config.json`
- **網路依賴**: 煙霧測試依賴外部網路，失敗時會自動 skip
- **DMM 測試**: 需要日本 VPN，預設標記為 skip
- **翻譯測試**: 需要 Ollama 或 Gemini 服務運行中
- **CI 建議**: 只跑 `unit/` 和 `integration/`，避免被網站 ban

## 手動測試腳本

```bash
# Gemini 安全設定測試
python tests/smoke/test_gemini_safety_settings.py

# Gemini 配置遷移測試
python tests/smoke/test_translate_gemini_manual.py

# 批次翻譯 API 測試（需先啟動服務）
python tests/smoke/test_batch_api.py
```
