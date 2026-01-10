# JavHelper Web GUI - PRD

## 目標
將 JavHelper 的 4 個功能整合成一個 Web-based GUI：
1. **JAV Search** - EverAver 風格的搜尋介面（用 JavBus/Jav321）
2. **JAV Scraper** - jav_scraper.py 的 GUI 版
3. **NFO Updater** - nfo_updater.py 的 GUI 版
4. **AVList Generator** - avlist.py 的 GUI 版

---

## 階段 0：環境準備（前置工作）

### 0.1 Git 初始化
```bash
cd /home/peace/JavHelper
git init
```

### 0.2 建立 .gitignore
```gitignore
# Python
__pycache__/
*.pyc
*.pyo
.env
venv/

# Cache
avlist_cache.json
file_mapping.json
*.tmp

# Archives (舊檔案備份)
archives/

# IDE
.vscode/
.idea/

# Output
*.html
failure_report.txt

# Windows
*.exe
Thumbs.db
Zone.Identifier
```

### 0.3 檔案結構重組
**現有檔案移到 `archives/`：**
```bash
mkdir -p archives
mv jav_scraper.py archives/
mv nfo_updater.py archives/
mv avlist_py/ archives/
mv avlist/ archives/          # 舊的反編譯資料
mv "EverAver Renamer v1.5.1.7/" archives/
mv GUI計劃.md archives/
```

**保留在根目錄：**
- `maker_mapping.json` - 共用資料
- `README.md` - 更新為新版說明

### 0.4 新目錄結構
```
JavHelper/
├── .gitignore
├── README.md                 # 更新為新版
├── prd.md                    # 本文件
├── requirements.txt          # Python 依賴
├── maker_mapping.json        # 共用資料（保留）
│
├── web/                      # FastAPI Web GUI
│   ├── app.py                # 主程式入口
│   ├── config.json           # 統一設定檔
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── search.py         # 搜尋 API
│   │   ├── scraper.py        # 刮削 API
│   │   ├── updater.py        # 更新 API
│   │   ├── avlist.py         # 列表生成 API
│   │   └── config.py         # 設定 API
│   ├── templates/
│   │   ├── base.html
│   │   ├── search.html
│   │   ├── scraper.html
│   │   ├── updater.html
│   │   ├── avlist.html
│   │   └── settings.html
│   └── static/
│       ├── css/
│       └── js/
│
├── core/                     # 共用模組
│   ├── __init__.py
│   ├── scraper.py            # 刮削邏輯（JavBus/Jav321/DMM）
│   ├── updater.py            # NFO 更新邏輯
│   ├── avlist.py             # 列表生成邏輯
│   ├── maker.py              # Maker 映射管理
│   ├── number_utils.py       # 番號處理
│   ├── nfo_utils.py          # NFO 讀寫
│   └── translator.py         # Ollama 翻譯
│
└── archives/                 # 舊檔案備份（gitignore）
    ├── jav_scraper.py
    ├── nfo_updater.py
    ├── avlist_py/
    └── ...
```

### 0.5 開發環境設置
```bash
# 建立虛擬環境（可選，也可用 conda）
python3 -m venv venv
source venv/bin/activate

# 安裝依賴
pip install fastapi uvicorn jinja2 python-multipart
pip install requests beautifulsoup4 lxml
pip install jvav  # JavBus API
```

### 0.6 開發/測試流程
```bash
# WSL 端啟動 server（hot reload）
cd /home/peace/JavHelper
uvicorn web.app:app --reload --host 0.0.0.0 --port 8000

# Windows 瀏覽器開啟
# http://localhost:8000
```

### 0.7 初始 Commit
```bash
git add .
git commit -m "Initial commit: project restructure for Web GUI"
```

---

## 技術選型

| 項目 | 選擇 | 理由 |
|------|------|------|
| 後端框架 | **FastAPI** | 原生 async、WebSocket 支援、自動 API 文件 |
| 模板引擎 | **Jinja2** | FastAPI 內建支援 |
| 前端 UI | **Bootstrap 5** | 快速開發、響應式、不需要 Node.js |
| **桌面 GUI** | **PyWebView** | 唯一支援的使用方式，提供原生檔案對話框和拖放功能 |
| 進度更新 | **WebSocket** | 即時推送 scraper/updater 進度 |
| LLM 翻譯 | **Ollama HTTP API** | 可選功能，用戶自行安裝 |
| 打包 | **zip + 嵌入式 Python** | 避免 exe 被誤判病毒 |

> **注意**: 本專案僅支援透過 PyWebView 桌面應用程式使用。直接用瀏覽器開啟雖然可以顯示介面，但檔案選擇、拖放等核心功能將無法使用，且不提供維護。

## 架構設計

```
JavHelper/
├── web/                          # Web GUI
│   ├── app.py                    # FastAPI 主程式
│   ├── routers/
│   │   ├── search.py             # /api/search - 搜尋 API
│   │   ├── scraper.py            # /api/scraper - 刮削 API
│   │   ├── updater.py            # /api/updater - 更新 API
│   │   ├── avlist.py             # /api/avlist - 列表生成 API
│   │   └── config.py             # /api/config - 設定 API
│   ├── templates/
│   │   ├── base.html             # 基礎模板（側邊欄 + 內容區）
│   │   ├── search.html           # 搜尋頁面
│   │   ├── scraper.html          # 刮削器頁面
│   │   ├── updater.html          # 更新器頁面
│   │   ├── avlist.html           # 列表生成頁面
│   │   └── settings.html         # 設定頁面
│   ├── static/
│   │   ├── css/
│   │   └── js/
│   │       └── websocket.js      # WebSocket 進度處理
│   └── config.json               # GUI 統一設定檔
│
├── core/                         # 共用模組（重構自現有腳本）
│   ├── scraper.py                # 刮削器（從 jav_scraper.py 提取）
│   ├── updater.py                # 更新器（從 nfo_updater.py 提取）
│   ├── maker.py                  # Maker 映射管理
│   ├── number_utils.py           # 番號處理工具
│   ├── nfo_utils.py              # NFO 讀寫工具
│   └── translator.py             # 翻譯器（支援 Ollama）
│
└── maker_mapping.json            # 共用
```

## 統一設定檔 (web/config.json)

```json
{
  "paths": {
    "input_folder": "/mnt/c/Users/peace/Downloads/JAV_input",
    "output_folder": "/mnt/c/Users/peace/Downloads/JAV_output",
    "failed_folder": "/mnt/c/Users/peace/Downloads/JAV_failed",
    "nas_folder": "/home/peace/admin_special_HD"
  },
  "scraper": {
    "sources": ["javbus", "jav321", "dmm", "avsox"],
    "enable_translate": true
  },
  "translator": {
    "provider": "ollama",
    "ollama_url": "http://localhost:11434",
    "ollama_model": "qwen2.5:7b"
  },
  "avlist": {
    "directories": ["/home/peace/usbshare2"],
    "path_mapping": {
      "/home/peace/usbshare2": "\\\\DiskStation\\usbshare2"
    }
  }
}
```

## 實作階段

### 階段 1：基礎框架 + 搜尋功能（優先）
**目標：快速看到效果，最像 EverAver 的部分**

- [ ] 建立 FastAPI 專案結構 (`web/app.py`)
- [ ] 設計 base.html 模板（側邊欄導航 + Bootstrap 5）
- [ ] 從 jav_scraper.py 提取 `scrape_javbus()` / `scrape_jav321()` 到 `core/scraper.py`
- [ ] 實作 `/api/search` 搜尋 API（番號搜尋）
- [ ] 搜尋頁面 UI：
  - 輸入框 + 搜尋按鈕
  - 結果卡片（封面、番號、演員、日期）
  - 點擊卡片顯示詳細資訊
- [ ] 設定頁面基礎 UI（刮削來源選擇）

### 階段 2：設定管理 + JAV Scraper GUI
- [ ] 實作 `/api/config` 設定讀寫
- [ ] 統一設定檔 `web/config.json`
- [ ] 重構 jav_scraper.py → `core/scraper.py`（類別化，支援 callback）
- [ ] 實作 WebSocket `/ws/progress` 進度推送
- [ ] 刮削器頁面 UI：
  - 資料夾選擇（輸入/輸出/失敗）
  - 選項勾選（翻譯、封面）
  - 進度條 + 日誌輸出
  - 開始/暫停/取消按鈕

### 階段 3：NFO Updater GUI
- [ ] 重構 nfo_updater.py → `core/updater.py`
- [ ] 5 階段進度顯示（掃描→標籤→片商→翻譯→寫回）
- [ ] 更新器頁面 UI
- [ ] 斷點續傳支援

### 階段 4：AVList GUI
- [ ] 整合現有 avlist_py（直接調用）
- [ ] 列表生成頁面 UI：
  - 資料夾列表管理
  - 路徑映射設定
  - 顯示選項
- [ ] 生成後預覽 / 下載 HTML

### 階段 5：Ollama 翻譯整合（可選功能）
- [ ] 實作 `core/translator.py`（Ollama HTTP API）
- [ ] 自動偵測 Ollama 是否可用（`localhost:11434/api/tags`）
- [ ] 設定頁面：Ollama URL、模型選擇、啟用/關閉
- [ ] 整合到 Scraper 和 Updater

### 階段 6：打包發布
- [ ] 建立 start.bat 啟動腳本
- [ ] 測試嵌入式 Python 打包
- [ ] GitHub Actions 自動打包 zip
- [ ] 撰寫安裝說明

## 頁面設計

### 搜尋頁面 (search.html)
```
┌─────────────────────────────────────────────────┐
│ [搜尋框: SONE-001____________] [搜尋]           │
│                                                 │
│ ┌─────────┐ ┌─────────┐ ┌─────────┐            │
│ │ 封面圖  │ │ 封面圖  │ │ 封面圖  │            │
│ │         │ │         │ │         │            │
│ ├─────────┤ ├─────────┤ ├─────────┤            │
│ │SONE-001 │ │SONE-002 │ │SONE-003 │            │
│ │演員名   │ │演員名   │ │演員名   │            │
│ │2024-01  │ │2024-02  │ │2024-03  │            │
│ └─────────┘ └─────────┘ └─────────┘            │
└─────────────────────────────────────────────────┘
```

### 刮削器頁面 (scraper.html)
```
┌─────────────────────────────────────────────────┐
│ 輸入資料夾: [/mnt/c/.../JAV_input    ] [瀏覽]   │
│ 輸出資料夾: [/mnt/c/.../JAV_output   ] [瀏覽]   │
│                                                 │
│ ☑ 啟用翻譯  ☑ 下載封面  ☐ 跳過已處理            │
│                                                 │
│ [▶ 開始處理]  [⏸ 暫停]  [⏹ 取消]               │
│                                                 │
│ 進度: ████████████░░░░░░░░ 12/20 (60%)          │
│                                                 │
│ ┌─ 處理日誌 ─────────────────────────────────┐ │
│ │ [1/20] 處理: SONE-001.mp4                  │ │
│ │   [+] JAVBUS 成功                          │ │
│ │   [+] 翻譯: 新人出道...                    │ │
│ │   [+] 完成                                 │ │
│ │ [2/20] 處理: MIDE-002.mp4                  │ │
│ └────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

## 啟動方式

### 開發模式

**1. 啟動後端服務 (WSL)**
```bash
cd /home/peace/JavHelper
source venv/bin/activate
uvicorn web.app:app --reload --host 0.0.0.0 --port 8000
```

**2. 啟動桌面應用 (Windows PowerShell)**
```powershell
cd C:\path\to\JavHelper\windows
python launcher.py
```

### 發布版 (start.bat)
```bat
@echo off
cd /d "%~dp0"
start "" python\python.exe -m uvicorn web.app:app --host 127.0.0.1 --port 8000
timeout /t 2 >nul
python\python.exe windows\launcher.py
```
