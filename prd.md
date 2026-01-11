# OpenAver Web GUI - PRD

## 目標
將 OpenAver 的 4 個功能整合成一個 Web-based GUI，並提供現代化的使用者體驗 (Gallery Style)：
1. **JAV Search** - 全新 Spotlight 風格搜尋介面
2. **JAV Scraper** - 自動化刮削影片元數據 + 生成 NFO
3. **NFO Updater** - 批量更新現有 NFO 檔案
4. **AVList Generator** - 生成精美的 HTML 影片列表

---

## 專案狀態 (Project Status)

| 階段 | 描述 | 狀態 |
|------|------|------|
| **Phase 0** | 環境準備與架構重組 | ✅ [Done] |
| **Phase 1** | 基礎框架 + 搜尋功能 | ✅ [Done] |
| **Phase 2** | UI 重構 (Gallery Design System) | ✅ [Done] |
| **Phase 3** | AVList 與 Settings 優化 | ✅ [Done] |
| **Phase 4** | 測試基礎設施 (Infrastructure) | ✅ [Done] |

---

## 目錄結構
```
OpenAver/
├── web/                          # Web GUI
│   ├── app.py                    # FastAPI 主程式
│   ├── routers/                  # API 路由 (Search, Config, Scraper, AVList)
│   ├── templates/                # Jinja2 模板
│   │   ├── search.html           # 搜尋 (Spotlight UI)
│   │   ├── avlist.html           # 列表生成 (Gallery UI + Mini Terminal)
│   │   └── settings.html         # 設定 (Modern Card UI)
│   ├── static/
│   │   ├── css/                  # Theme.css (Dark Mode, Variables)
│   │   └── js/                   # 模組化 JS
│   └── config.json               # 統一設定檔
│
├── core/                         # 核心模組
│   ├── scraper.py                # 刮削器 (JavBus/Jav321/DMM)
│   ├── avlist_generator.py       # HTML 生成器
│   └── ...
│
├── tests/                        # 測試套件
│   ├── conftest.py               # Fixtures
│   ├── test_api_config.py        # API 整合測試
│   └── test_smoke.py             # 爬蟲煙霧測試
│
└── windows/                      # Windows 啟動器
    └── launcher.py               # PyWebView 啟動腳本
```

## 功能規劃詳情

### 階段 1：基礎框架 + 搜尋功能 [Done]
- 實作 FastAPI 後端與 Jinja2 模板。
- 整合 `core/scraper.py` 支援 JavBus/Jav321/DMM 多來源搜尋。
- 實作番號自動標準化與模糊搜尋。

### 階段 2：UI 重構 (Gallery Design System) [Done]
- **Design System**: 建立 `theme.css`，定義全站變數 (Colors, Radius, Shadows, Dark Mode)。
- **Search UI**:
    - **Spotlight Input**: 膠囊狀搜尋框，置中聚焦。
    - **Hero Detail**: 搜尋結果以大圖呈現，無邊框設計，強調視覺衝擊。
    - **Glassmorphism**: 廣泛使用毛玻璃特效。

### 階段 3：AVList 與 Settings 優化 [Done]
- **AVList Generator**:
    - **Gallery List**: 資料夾列表改為 Chip/Row 樣式。
    - **Mini Terminal**: 內嵌式滾動日誌視窗，提供即時回饋但不佔空間。
    - **Feature Restore**: 補回「複製路徑」與「NFO 補全」功能。
- **Settings Page**:
    - **Modern Cards**: 移除 Bootstrap 原生邊框，使用大圓角卡片。
    - **Feature Complete**: 支援 AVList 輸出路徑設定、Ollama 翻譯設定。
- **Viewer Theme Sync**: 讓靜態生成的 HTML Viewer 能夠跟隨 Web App 的 Light/Dark 設定。

### 階段 4：測試基礎設施 [Done]
- 引入 `pytest` 測試框架。
- 建立 `tests/` 目錄結構。
- 實作 Settings API 的整合測試與 Scraper 的煙霧測試。
- 確保核心功能在重構後的穩定性。

## 技術選型

| 項目 | 選擇 | 理由 |
|------|------|------|
| 後端框架 | **FastAPI** | 原生 async、效能優異 |
| 模板引擎 | **Jinja2** | 靈活的服務端渲染 |
| 前端 UI | **Bootstrap 5 + Custom CSS** | 快速開發 + 客製化 Gallery Style |
| **桌面 GUI** | **PyWebView** | 提供原生檔案對話框和拖放功能 |
| 測試框架 | **Pytest** | Python 標準測試工具 |
| LLM 翻譯 | **Ollama** | 本地隱私翻譯 |

## 開發指南

### 啟動開發伺服器
```bash
source venv/bin/activate
uvicorn web.app:app --reload --host 0.0.0.0 --port 8000
```

### 執行測試
```bash
source venv/bin/activate
pytest
```