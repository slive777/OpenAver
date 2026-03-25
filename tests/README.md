# Testing Guide

OpenAver 使用 `pytest` 作為測試框架。測試套件分為四層：單元測試、整合測試、煙霧測試、E2E 測試。

## 前置準備

```bash
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install pytest pytest-asyncio pytest-mock httpx
```

## 目錄結構

```
tests/
├── conftest.py              # 全域 Fixtures
├── test_frontend_lint.py    # 前端靜態檔案 lint 測試
│
├── unit/                    # 單元測試（不需網路）
│   ├── conftest.py
│   ├── test_actress_alias_api.py
│   ├── test_database.py
│   ├── test_gallery_scanner.py
│   ├── test_local_status_api.py
│   ├── test_motion_lab_router.py
│   ├── test_organizer.py
│   ├── test_path_utils.py
│   ├── test_scanner_sqlite.py
│   ├── test_scraper_callbacks.py
│   ├── test_scraper_parser.py
│   ├── test_scraper_partial.py
│   ├── test_scraper_validators.py
│   ├── test_showcase_api.py
│   ├── test_translate_service.py
│   ├── test_utils_extended.py
│   ├── test_video_extensions.py
│   └── test_video_repository.py
│
├── integration/             # 整合測試（使用 Mock）
│   ├── conftest.py
│   ├── test_actress_profile.py
│   ├── test_api_config.py
│   ├── test_api_config_endpoints.py
│   ├── test_api_filename.py
│   ├── test_api_gallery.py
│   ├── test_api_scanner.py
│   ├── test_api_search.py
│   ├── test_api_translate.py
│   └── test_new_scrapers.py
│
├── smoke/                   # 煙霧測試（需網路/服務）
│   ├── conftest.py
│   ├── test_batch_api.py
│   ├── test_gemini_safety_settings.py
│   ├── test_javbus_smoke.py
│   ├── test_scraper_live.py
│   ├── test_scrapers.py
│   ├── test_translate_gemini_manual.py
│   └── test_translate_live.py
│
├── e2e/                     # 瀏覽器端對端測試（需真實瀏覽器 + 網路）
│   ├── __init__.py
│   ├── conftest.py          # Session-scoped FastAPI server（port 8001）
│   └── test_search_e2e.py   # 搜尋頁完整流程（Detail 新欄位 / Sample Lightbox / 方向鍵導航）
│
├── fixtures/                # Mock 測試資料
│   └── responses/
│       ├── javbus/SONE-103.json
│       └── javdb/actress_search.json
│
├── mock_data/               # Mock JSON 資料
│   └── mikami_profile.json
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

# 單元 + 整合（CI 標準）
pytest tests/ -v --ignore=tests/smoke --ignore=tests/e2e -m "not smoke and not e2e"
```

### E2E 測試（需 Playwright + 網路）

```bash
# E2E 測試（需先安裝 Playwright + Chromium，需網路 + JavBus 可連）
source venv/bin/activate && pip install pytest-playwright && playwright install chromium
pytest tests/e2e/ -v -m e2e
```

### 完整測試（需網路）

```bash
# 所有測試（含 smoke）
pytest tests/ -v

# 只跑煙霧測試（爬蟲連通）
pytest -m smoke -v
```

### 特定測試

```bash
# 番號解析測試
pytest tests/unit/test_scraper_parser.py -v

# 路徑轉換測試
pytest tests/unit/test_path_utils.py -v

# 翻譯服務測試
pytest tests/unit/test_translate_service.py -v

# Config API 測試
pytest tests/integration/test_api_config.py -v

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
| `test_scraper_validators.py` | 爬蟲資料驗證邏輯 |
| `test_scraper_partial.py` | 爬蟲部分結果處理 |
| `test_database.py` | 資料庫操作 |
| `test_organizer.py` | 檔案整理邏輯 |
| `test_video_repository.py` | 影片資料存取層 |

### 整合測試 (`integration/`)

使用 Mock 測試 API 端點：

| 檔案 | 測試內容 |
|------|----------|
| `test_api_search.py` | 搜尋 API、模式切換、分頁 |
| `test_api_gallery.py` | 圖片代理、Gallery 統計 |
| `test_api_config.py` | Config API 整合測試 |
| `test_api_scanner.py` | 掃描 API 測試 |
| `test_api_translate.py` | 翻譯 API 測試 |
| `test_actress_profile.py` | 女優資料 scraper 測試 |
| `test_new_scrapers.py` | 新增爬蟲模組測試 |

### 煙霧測試 (`smoke/`)

實際連線外部服務：

| 檔案 | 測試內容 | 前提條件 |
|------|----------|----------|
| `test_scraper_live.py` | 爬蟲連通性 | 網路 |
| `test_scrapers.py` | 6 個爬蟲模組測試 | 網路 |
| `test_javbus_smoke.py` | JavBus scraper 連通 + 欄位驗證 | 網路 + JavBus 可連 |
| `test_translate_live.py` | Ollama 翻譯 | Ollama 服務 |
| `test_batch_api.py` | 批次翻譯 API | FastAPI + Ollama |
| `test_gemini_safety_settings.py` | Gemini 安全設定 | Gemini API Key |

### E2E 測試 (`e2e/`)

需要真實瀏覽器（Playwright Chromium）+ 真實網路連線：

| 檔案 | 測試內容 | 前提條件 |
|------|----------|----------|
| `test_search_e2e.py` | Detail 新欄位顯示、Sample Lightbox 互動、方向鍵導航 | 網路 + JavBus + Playwright Chromium |

無網路 / JavBus 無回應時自動 SKIP（不 FAIL）。

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
