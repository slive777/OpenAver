<p align="center">
  <img src="docs/logo.svg" alt="OpenAver Logo" width="200">
</p>

<h1 align="center">OpenAver</h1>

<p align="center">
  <strong>現代化的 JAV 影片元數據管理工具 (Modern JAV Metadata Manager)</strong>
</p>

OpenAver 是一個基於 Web 技術的桌面應用程式，旨在幫助您輕鬆管理、刮削和生成 JAV 影片的元數據與展示列表。

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)
![Tests](https://github.com/slive777/OpenAver/actions/workflows/test.yml/badge.svg)
![GitHub Release](https://img.shields.io/github/v/release/slive777/OpenAver)

## 📸 截圖預覽

![Home](docs/screenshots/home.jpg)

<details>
<summary>更多截圖</summary>

<div style="display: flex; gap: 20px; margin: 20px 0;">
  <div flex="1">
    <img src="docs/screenshots/demo.gif" width="100%" alt="Search Demo">
  </div>
  <div flex="1">
    <img src="docs/screenshots/demo2.gif" width="100%" alt="Showcase Demo">
  </div>
</div>

| 搜尋結果 | Showcase Grid | Showcase 詳細 |
|----------|---------------|---------------|
| ![Search](docs/screenshots/search-detail.png) | ![Grid](docs/screenshots/showcase-grid.png) | ![Detail](docs/screenshots/showcase-detail.png) |

</details>

## ⚠️ 免責聲明

本專案僅供個人學習研究使用，請使用者遵守：
- 尊重網站服務條款
- 合理控制請求頻率
- 不用於商業目的

使用本專案造成的任何後果由使用者自行承擔。

## 🔒 隱私聲明

OpenAver 是純本地應用程式：
- ✅ 不蒐集使用者資料
- ✅ 不上傳檔案資訊到遠端伺服器
- ✅ 所有操作在您的電腦本地執行
- ⚠️ 網路請求僅用於刮削公開影片元數據

---

## ✨ 核心功能

### 🔍 Spotlight Search (搜尋)
- **多來源聚合**: 同時搜尋 JavBus, Jav321, JavDB, DMM, D2Pass, HEYZO 等多個來源。
- **Gallery Style**: 現代化的 Hero Detail 介面，以大圖和毛玻璃特效呈現影片資訊。
- **智慧搜尋**: 支援番號自動標準化、前綴搜尋、女優搜尋。
- **版本標記**: 自動偵測 UC/LEAK/4K 等後綴，`{suffix}` 格式變數支援。
- **女優畫廊模式 (Beta)**: 女優搜尋結果 > 10 片時自動切換為 Gallery 瀏覽，顯示女優個人資料 Hero Card。
- **本地檔案搜尋優化**:
  - 拖入檔案自動過濾（副檔名 + 大小）
  - 批次搜尋（20 個一批，並發 2 個）
  - 暫停/繼續功能 + 批次翻譯
  - 我的最愛資料夾一鍵載入
  - 開啟資料夾（系統檔案管理員整合）

### 📝 Scanner (掃描與列表生成)
- **靜態 HTML**: 掃描本地影片資料夾，生成精美的靜態 HTML 索引檔。
- **Mini-Terminal**: 內嵌式終端機視窗，即時顯示掃描與處理進度。
- **NFO 補全**: 自動檢測並補全缺失的 NFO 檔案。
- **Jellyfin 圖片模式**: 自動生成 poster/thumb/fanart 供 Jellyfin 使用。
- **快取管理**: 一鍵清除掃描快取，支援兩步確認。

### ⚙️ Settings (設定)
- **Dark Mode**: 全站支援深色模式，並自動同步至生成的 Viewer。
- **翻譯服務**: 支援 Ollama（本地）和 Gemini（Google）兩種翻譯提供商。
- **路徑管理**: 靈活設定輸出路徑與檔案命名規則，支援 `{suffix}` 格式變數。
- **我的最愛資料夾**: 設定常用資料夾，一鍵載入並自動搜尋。
- **檔案過濾**: 設定最小影片尺寸 (MB)，自動排除過小檔案。

### 🌐 翻譯功能

OpenAver 支援兩種翻譯提供商：

| 提供商 | 特點 | 速度 |
|--------|------|------|
| **Ollama（本地）** | 免費、無 API 限制、需本地 GPU | ~0.5 秒/片 |
| **Gemini（Google）** | 雲端 API、免費額度 15 RPM | ~0.1 秒/片 |

**⚠️ Gemini API Key 安全提示**

- API Key 以明文存儲在 `web/config.json`
- **請勿將 config.json 分享給他人或上傳至公開位置**
- 如需撤銷：前往 [Google AI Studio](https://aistudio.google.com/apikey) 重新生成

## 🛠️ 技術架構

- **Backend**: FastAPI (Python 3.10+)
- **Frontend**: Jinja2 + DaisyUI + Tailwind CSS + Alpine.js 3.x + GSAP 3.14+ + Fluent Design 2
- **Animation**: GSAP (Showcase/Search pages) + Motion Adapter (reduced-motion support)
- **Desktop**: PyWebView (Windows/macOS)
- **Database**: SQLite (WAL mode)
- **Testing**: Pytest (803+ tests)

## 📥 安裝

### 推薦方式：一行安裝（自動處理所有平台配置）

**macOS**:
```bash
curl -fsSL https://raw.githubusercontent.com/slive777/OpenAver/main/install.sh | bash
```

**Windows** (PowerShell):
```powershell
irm https://raw.githubusercontent.com/slive777/OpenAver/main/install.ps1 | iex
```

安裝指令會自動：
- 偵測系統架構並下載最新版本
- 移除 macOS 隔離標記（無需手動 `xattr` 指令）
- 解除 Windows 下載安全限制（無需手動 Unblock）
- 建立桌面快捷方式（Windows）
- 保留設定與日誌檔案（升級時）

### 備用方式：手動下載 ZIP

如果網路環境無法執行指令（公司代理等），可從 [GitHub Releases](https://github.com/slive777/OpenAver/releases/latest) 手動下載：

| 平台 | 檔案 |
|------|------|
| **Windows x64** | `OpenAver-vX.X.X-Windows-x64.zip` |
| **macOS arm64** | `OpenAver-vX.X.X-macOS-arm64.zip` |

**⚠️ 手動 ZIP 安裝** — 需額外步驟解除平台安全限制，見下方「疑難排解 (ZIP 安裝)」。

> ℹ️ macOS 版本僅支援 Apple Silicon (M1/M2/M3/M4)。

---

## 🚀 快速開始（原始碼）

### 前置需求
- Python 3.10+ (原始碼執行)
- Chrome/Edge (用於 PyWebView)
- **Microsoft Edge WebView2 Runtime** (Windows 10/VM 必備)

### 安裝
```bash
# 1. Clone 專案
git clone https://github.com/slive777/OpenAver.git
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

## ❓ 疑難排解

> 💡 如果您使用上方推薦的 **curl 一行安裝**，以下步驟通常不需要。疑難排解僅適用於手動 ZIP 安裝。

### ZIP 安裝專用

#### 1. Windows 程式無法啟動 / 閃退

**原因**: Windows 安全機制 (Mark of the Web) 封鎖了從網路下載的執行檔或 DLL。

**解法**:
1. 對下載的 `OpenAver-Windows-x64.zip` 點擊 **右鍵** -> **內容**
2. 在下方勾選 **「解除封鎖 (Unblock)」**，然後按確定
3. 重新解壓縮並執行 `OpenAver.bat`

*或者使用 7-Zip 軟體進行解壓縮，通常可避開此問題。*

**程式啟動後的使用**:
- **OpenAver.bat** - 正常啟動（顯示啟動提示，無詳細日誌）
- **OpenAver_Debug.bat** - 調試版本（顯示控制台，輸出詳細日誌）

**遇到問題時，請執行 OpenAver_Debug.bat**：
1. 雙擊 `OpenAver_Debug.bat` 啟動程式
2. 控制台會顯示詳細的錯誤訊息
3. 同時日誌檔案保存在：`%USERPROFILE%\OpenAver\logs\debug.log`
4. 將控制台輸出或日誌內容附加到 [GitHub Issue](https://github.com/slive777/OpenAver/issues) 中報告

#### 2. macOS 無法開啟 / 安全性警告

**原因**: macOS Gatekeeper 阻擋未簽名的應用程式。

**完整安裝步驟** (複製貼上執行):

**[步驟 1]** 下載 ZIP
- Safari 會自動解壓縮，檔案在「下載項目」資料夾

**[步驟 2]** 開啟終端機
- 按 ⌘ + 空白鍵 開啟 Spotlight
- 輸入 Terminal 並按 Enter

**[步驟 3]** 進入資料夾（複製貼上以下指令）
```bash
cd ~/Downloads/OpenAver
```

**[步驟 4]** 解除安全封鎖（必做）
```bash
xattr -dr com.apple.quarantine .
```

**[步驟 5]** 啟動程式
```bash
./OpenAver.command
```

💡 設定完成後，之後可直接雙擊 `OpenAver.command` 執行。

**程式啟動後的使用**:
- **OpenAver.command** - 正常啟動（無日誌輸出，後台執行）
- **OpenAver_Debug.command** - 調試版本（在終端機顯示詳細日誌）

**遇到問題時，請執行 OpenAver_Debug.command**：
1. 雙擊 `OpenAver_Debug.command`（或在 Terminal 執行 `./OpenAver_Debug.command`）
2. 終端機會顯示詳細的日誌輸出
3. 日誌檔案同時保存在：`~/OpenAver/logs/debug.log`
4. 將日誌內容附加到 [GitHub Issue](https://github.com/slive777/OpenAver/issues) 中報告

### 所有安裝方式均適用

#### 介面顯示異常 / 空白 / 沒有毛玻璃特效

**原因**: 缺少 WebView2 Runtime 或 GPU 加速支援不足（常見於 Windows 10 或虛擬機）。

**解法**: 請下載並安裝 [Microsoft Edge WebView2 Runtime](https://go.microsoft.com/fwlink/p/?LinkId=2124703)。

## 💬 社群

加入 [Telegram 群組](https://t.me/+J-U2l96gv0FjZTBl) 與其他使用者交流討論！

---

## 🐛 回報問題

遇到問題或發現 Bug？請透過以下管道回報，幫助我們改進：

### 📌 一般問題 / 功能建議
→ [GitHub Issues](https://github.com/slive777/OpenAver/issues)
- 適用於開發者查詢、功能討論
- 問題與解決方案留檔可供他人參考

**回報格式**：
- 問題描述（發生什麼錯誤？）
- 重現步驟（如何觸發這個問題？）
- 您的環境（OS 版本、是否使用打包版）
- 日誌檔案（如果有）

### 🔒 NSFW / 隱私敏感問題
→ [Telegram 群組](https://t.me/+J-U2l96gv0FjZTBl)
- 私密頻道，支援直接上傳敏感截圖 / 影片
- 適合不便公開的內容

### 取得日誌檔案（Windows 打包版）
1. 執行 `OpenAver_Debug.bat`
2. 重現問題
3. 日誌位置：`%USERPROFILE%\OpenAver\logs\debug.log`
4. 將日誌檔案附加到 GitHub Issue 或 Telegram

---

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
│   ├── routers/        # API Endpoints (Search, Config, Scraper, Scanner)
│   ├── templates/      # HTML Templates (DaisyUI + Fluent Design 2)
│   └── static/         # CSS/JS Assets (Modular JS, Theme CSS)
├── core/               # 核心邏輯
│   ├── scrapers/               # 模組化爬蟲 (JavBus/JavDB/Jav321/FC2/AVSOX/DMM/D2Pass/HEYZO)
│   ├── database.py             # SQLite 資料層 (WAL mode)
│   ├── organizer.py            # 檔案整理 + fallback 空值防護
│   ├── path_utils.py           # 跨平台路徑處理 (file:// URI)
│   └── translate_service.py    # AI 翻譯 (Ollama/Gemini)
├── tests/              # 測試代碼 (Pytest)
└── windows/            # Windows 啟動器 (PyWebView)
```

## 打包 Windows 應用程式

```bash
# 確保在 venv 環境下執行
source venv/bin/activate
python build.py
```

## 🙏 致謝 (Acknowledgements)

OpenAver 使用並感謝以下開源專案：

- **[jvav](https://github.com/akynazh/jvav)** - JAV 元數據刮削工具庫，提供 JavBus/JavDB/JavLib 等多來源支援
- **[FastAPI](https://fastapi.tiangolo.com/)** - 現代化的 Python Web 框架
- **[PyWebView](https://pywebview.flowrl.com/)** - 輕量級的跨平台桌面應用框架
- **[DaisyUI](https://daisyui.com/)** - Tailwind CSS 元件庫
- **[Tailwind CSS](https://tailwindcss.com/)** - Utility-first CSS 框架
- **[Alpine.js](https://alpinejs.dev/)** - 輕量級 JavaScript 框架

特別感謝所有為這些專案做出貢獻的開發者們。

## License

MIT License
