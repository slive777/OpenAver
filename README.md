# JavHelper

JAV 影片元數據管理工具 - Web GUI 版本

## 功能

1. **JAV Search** - 搜尋影片資訊（番號、演員、封面）
2. **JAV Scraper** - 刮削影片元數據 + 生成 NFO
3. **NFO Updater** - 批量更新現有 NFO 檔案
4. **AVList Generator** - 生成 HTML 影片列表

## 技術架構

- **後端**: FastAPI + Python (WSL)
- **前端**: Jinja2 + Bootstrap 5
- **GUI**: PyWebView (Windows 桌面應用)
- **翻譯**: Ollama（可選）

## 安裝

```bash
# 建立虛擬環境
python3 -m venv venv

# 啟動虛擬環境
source venv/bin/activate

# 安裝依賴
pip install -r requirements.txt
```

## 啟動

```bash
# 啟動虛擬環境（如果尚未啟動）
source venv/bin/activate

# 啟動伺服器
uvicorn web.app:app --reload --host 0.0.0.0 --port 8000
```

### 方式一：瀏覽器
瀏覽器開啟 http://localhost:8000

### 方式二：PyWebView（推薦）
```powershell
# Windows PowerShell
pip install pywebview
python windows/launcher.py
```

## 目錄結構

```
JavHelper/
├── web/                # Web GUI (FastAPI)
│   ├── app.py          # 主程式
│   ├── routers/        # API 路由
│   ├── templates/      # HTML 模板
│   └── static/         # CSS/JS
├── core/               # 核心模組
├── windows/            # Windows 啟動器
│   └── launcher.py     # PyWebView 啟動腳本
├── maker_mapping.json  # 片商映射
├── requirements.txt    # Python 依賴
└── prd.md              # 產品規劃文件
```

## 開發中

詳細規劃請參考 [prd.md](prd.md)

## License

MIT
