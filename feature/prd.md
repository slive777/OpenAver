# OpenAver - PRD

## 願景

影片元數據管理工具，讓收藏整理變得簡單。

**核心功能**：
1. **Search** - Spotlight 風格搜尋，多來源聚合 (JavBus/JAV321/JavDB/FC2/AVSOX)
2. **Scraper** - 自動刮削元數據，生成 NFO + 封面
3. **Gallery** - 批量更新 NFO，生成 HTML 瀏覽頁面
4. **Settings** - AI 翻譯 (Ollama/Gemini)、輸出格式自訂

---

## 發展歷程

| Phase | 描述 | 版本 |
|-------|------|------|
| 0-7 | 基礎架構、搜尋、刮削、Gallery、打包 | v0.1.x |
| 8-9 | 女優畫廊模式、批次搜尋優化 | |
| 10-15 | 發布準備、測試框架、AI 翻譯增強、macOS 支援 | v0.2.0 |
| 16-18 | Scraper 模組化、Thin Client、SQLite 資料層 | |
| 19-20 | FC2/無碼搜尋、SQLite 路徑修復、SSE Log 優化 | v0.2.1 |
| 21 | 後綴清理（UC/LEAK）+ 整合測試 | v0.2.2 |
| 22 | Gallery 搜尋增強、本地標記複製 | v0.2.3 |
| 23 | Design System（元件庫 + Fluent Design 視覺） | v0.2.4 |

---

## 目錄結構

```
core/                    # 核心模組
├── scrapers/            # 模組化爬蟲
│   ├── base.py          # BaseScraper 抽象類
│   ├── models.py        # Pydantic 資料模型
│   └── [5 scrapers]     # javbus/jav321/javdb/fc2/avsox
├── database.py          # SQLite 資料層 (WAL mode)
├── organizer.py         # 檔案整理（重命名、NFO、封面）
├── nfo_updater.py       # NFO 批量更新
├── path_utils.py        # 跨平台路徑處理
└── translate_service.py # AI 翻譯服務

web/                     # Web 應用
├── app.py               # FastAPI 主程式
├── routers/             # API 路由
│   ├── search.py        # /api/search, /api/parse-filename
│   ├── gallery.py       # /api/avlist/*
│   ├── translate.py     # /api/translate
│   └── config.py        # /api/config
├── templates/           # Jinja2 (search/avlist/settings/help)
└── static/js/pages/     # 模組化 JS (core/ui/file/init)

tests/                   # Pytest 測試套件
windows/                 # Windows/macOS 打包
```

---

## 技術選型

| 項目 | 選擇 | 理由 |
|------|------|------|
| Backend | **FastAPI** | async、高效能、自動 OpenAPI |
| Frontend | **Jinja2 + Bootstrap 5** | SSR + 快速開發 |
| Desktop | **PyWebView** | 原生對話框、拖放支援 |
| Database | **SQLite (WAL)** | 輕量、無需安裝 |
| AI 翻譯 | **Ollama / Gemini** | 本地隱私 / 雲端高品質 |
| Testing | **Pytest** | Python 標準 |

---

## 技術決策

1. **ZIP 打包**（非 exe）- 避免防毒誤判
2. **爬蟲節流** - MAX_WORKERS=2, REQUEST_DELAY=0.3s
3. **封面優先** - JavBus > Jav321 > JavDB（避免浮水印）
4. **路徑格式** - DB 存 `file:///` URI，運行時轉換
5. **前端精簡** - 業務邏輯集中後端，前端只負責 UI
