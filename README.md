# OpenAver

**現代化的 JAV 影片元數據管理工具 (Modern JAV Metadata Manager)**

OpenAver 是一個基於 Web 技術的桌面應用程式，旨在幫助您輕鬆管理、刮削和生成 JAV 影片的元數據與展示列表。

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)
![Tests](https://img.shields.io/badge/Tests-Passing-brightgreen.svg)

## ✨ 核心功能

### 🔍 Spotlight Search (搜尋)
- **多來源聚合**: 同時搜尋 JavBus, Jav321, JavDB 等多個來源。
- **Gallery Style**: 現代化的 Hero Detail 介面，以大圖和毛玻璃特效呈現影片資訊。
- **智慧搜尋**: 支援番號自動標準化、前綴搜尋、女優搜尋。
- **女優畫廊模式 (Beta)**: 女優搜尋結果 > 10 片時自動切換為 Gallery 瀏覽，顯示女優個人資料 Hero Card。
- **本地檔案搜尋優化**:
  - 拖入檔案自動過濾（副檔名 + 大小）
  - 批次搜尋（20 個一批，並發 2 個）
  - 暫停/繼續功能
  - 我的最愛資料夾一鍵載入

### 📝 Gallery Generator (列表生成)
- **靜態 HTML**: 掃描本地影片資料夾，生成精美的靜態 HTML 索引檔。
- **Mini-Terminal**: 內嵌式終端機視窗，即時顯示掃描與處理進度。
- **NFO 補全**: 自動檢測並補全缺失的 NFO 檔案。

### ⚙️ Settings (設定)
- **Dark Mode**: 全站支援深色模式，並自動同步至生成的 Viewer。
- **Ollama 整合**: 支援使用本地 Ollama 模型翻譯影片標題與簡介。
- **路徑管理**: 靈活設定輸出路徑與檔案命名規則。
- **我的最愛資料夾**: 設定常用資料夾，一鍵載入並自動搜尋。
- **檔案過濾**: 設定最小影片尺寸 (MB)，自動排除過小檔案。

## 🛠️ 技術架構

- **Backend**: FastAPI (Python)
- **Frontend**: Jinja2 + Bootstrap 5 + Custom CSS (Gallery Design System)
- **Desktop**: PyWebView (Windows) / Browser (Linux/macOS)
- **Testing**: Pytest

## 🚀 快速開始

### 前置需求
- Python 3.10+ (原始碼執行)
- Chrome/Edge (用於 PyWebView)
- **Microsoft Edge WebView2 Runtime** (Windows 10/VM 必備)

### 安裝
```bash
# 1. Clone 專案
git clone https://github.com/your-repo/OpenAver.git
cd OpenAver

# 2. 建立虛擬環境
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. 安裝依賴
pip install -r requirements.txt
```

### 啟動
```bash
# 開發模式 (Hot Reload)
uvicorn web.app:app --reload --host 0.0.0.0 --port 8000

# 桌面模式 (Windows)
python windows/launcher.py
```

## ❓ 疑難排解 (Troubleshooting)

### 1. 程式無法啟動 / 閃退 (Windows)
**原因**: Windows 安全機制 (Mark of the Web) 封鎖了從網路下載的執行檔或 DLL。
**解法**:
1. 對下載的 `OpenAver-Windows-x64.zip` 點擊 **右鍵** -> **內容**。
2. 在下方勾選 **「解除封鎖 (Unblock)」**，然後按確定。
3. 重新解壓縮並執行 `OpenAver.bat`。
*或者使用 7-Zip 軟體進行解壓縮，通常可避開此問題。*

### 2. 介面顯示異常 / 空白 / 沒有毛玻璃特效
**原因**: 缺少 WebView2 Runtime 或 GPU 加速支援不足（常見於 Windows 10 或虛擬機）。
**解法**:
請下載並安裝 [Microsoft Edge WebView2 Runtime](https://go.microsoft.com/fwlink/p/?LinkId=2124703)。

## 🧪 執行測試

本專案包含 API 整合測試與核心邏輯單元測試。

```bash
source venv/bin/activate
pytest
```

## 📂 目錄結構

```
OpenAver/
├── web/                # Web GUI (FastAPI)
│   ├── routers/        # API Endpoints (Search, Config, Scraper, AVList)
│   ├── templates/      # HTML Templates (Gallery Style)
│   └── static/         # CSS/JS Assets (Modular JS, Theme CSS)
├── core/               # 核心邏輯
│   ├── scraper.py              # 刮削器 (JavBus/Jav321/JavDB)
│   ├── actress_scraper.py      # 女優爬蟲
│   ├── search_gallery_service.py # Gallery Service
│   ├── gallery_generator.py    # Gallery HTML 生成器
│   ├── organizer.py            # 檔案整理
│   └── path_utils.py           # 跨平台路徑處理
├── tests/              # 測試代碼 (Pytest)
└── windows/            # Windows 啟動器 (PyWebView)
```

## 打包 Windows 應用程式

```bash
# 確保在 venv 環境下執行
source venv/bin/activate
python build.py
```

## License

MIT License
