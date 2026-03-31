import copy

from fastapi import APIRouter, Request

from core.version import __version__
from core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["capabilities"])


_TOOLS: list[dict] = [
    {
        "name": "search",
        "description": "搜尋單一番號或女優，回傳 metadata + 封面 URL",
        "method": "GET",
        "path": "/api/search",
        "input_schema": {
            "type": "object",
            "properties": {
                "q": {"type": "string", "description": "番號、女優名、或關鍵字"},
                "mode": {
                    "type": "string",
                    "enum": ["auto", "exact", "partial", "prefix", "actress", "keyword", "uncensored"],
                    "default": "auto",
                    "description": "搜尋模式",
                },
                "source": {
                    "type": "string",
                    "enum": ["javbus", "jav321", "javdb", "fc2", "avsox", "dmm"],
                    "description": "指定來源（可選）",
                },
                "since": {
                    "type": "string",
                    "format": "date",
                    "description": "只回傳此日期之後的結果（YYYY-MM-DD，可選）",
                },
                "discovery": {
                    "type": "boolean",
                    "default": False,
                    "description": "true=只回傳番號+標題清單（秒回），跳過詳情抓取。適合 actress/prefix 模式先探索再用 batch-search 精準抓取",
                },
            },
            "required": ["q"],
        },
        "output_schema": {
            "success": "boolean",
            "data": "[Video] — 搜尋結果陣列。discovery=false 時含完整欄位；discovery=true 時只有 number + title",
            "total": "integer — 結果總數",
            "mode": "string — 實際使用的搜尋模式",
            "discovery": "boolean — 是否為探索模式（僅 discovery=true 時出現）",
        },
        "retry_safe": True,
        "_example_template": "curl '{base}/api/search?q=SONE-205'",
    },
    {
        "name": "batch_search",
        "description": "一次搜尋多個番號，適合文章解析後批量查詢",
        "method": "POST",
        "path": "/api/batch-search",
        "input_schema": {
            "type": "object",
            "properties": {
                "numbers": {"type": "array", "items": {"type": "string"}, "description": "番號陣列"},
                "include_covers": {"type": "boolean", "default": True, "description": "是否包含封面 URL"},
            },
            "required": ["numbers"],
        },
        "output_schema": {
            "results": "{number: Video} — 以番號為 key 的搜尋結果 map",
            "summary": "{total, found, not_found} — 統計摘要",
        },
        "retry_safe": True,
        "rate_limit_hint": "硬限 50 筆（伺服器端截斷），建議一次不超過 20 筆",
        "cost_hint": "每筆觸發外部網站搜尋，受節流限制",
        "_example_template": "curl -X POST -H 'Content-Type: application/json' -d '{{\"numbers\":[\"FC2-PPV-1854491\",\"SONE-205\"]}}' {base}/api/batch-search",
    },
    {
        "name": "scrape_single",
        "description": "新片整理：搜尋 metadata → 下載封面 → 生成 NFO → 重命名搬移",
        "method": "POST",
        "path": "/api/scrape-single",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "影片檔案路徑"},
                "number": {"type": "string", "description": "番號（可選，不給會從檔名提取）"},
                "metadata": {"type": "object", "description": "預先取得的 metadata（可選，跳過搜尋）"},
            },
            "required": ["file_path"],
        },
        "output_schema": {
            "success": "boolean",
            "new_folder": "string — 新目錄路徑",
            "new_filename": "string — 新檔名",
            "cover_path": "string — 封面圖路徑",
            "nfo_path": "string — NFO 檔路徑",
        },
        "side_effect": True,
        "confirmation_required": True,
        "idempotent": False,
        "retry_safe": False,
        "_example_template": "curl -X POST -H 'Content-Type: application/json' -d '{{\"file_path\":\"/downloads/SONE-205.mp4\"}}' {base}/api/scrape-single",
    },
    {
        "name": "generate_gallery",
        "description": "從番號列表生成圖文並茂的 HTML 頁面",
        "method": "POST",
        "path": "/api/gallery/generate-from-ids",
        "input_schema": {
            "type": "object",
            "properties": {
                "numbers": {"type": "array", "items": {"type": "string"}, "description": "番號陣列"},
                "title": {"type": "string", "description": "頁面標題"},
                "mode": {"type": "string", "enum": ["image", "detail", "text"], "default": "image"},
                "sort": {"type": "string", "enum": ["date", "num", "title"], "default": "date"},
                "embed_covers": {"type": "boolean", "default": True, "description": "嵌入封面圖片為 base64（預設 True，適合分享用途）"},
            },
            "required": ["numbers"],
        },
        "output_schema": {
            "success": "boolean",
            "html_path": "string — 生成的 HTML 檔案路徑",
            "video_count": "integer — 成功收錄的影片數",
            "missing": "[string] — 未找到的番號陣列",
            "embedded_count": "integer — 成功嵌入封面數（僅 embed_covers=true 時出現）",
            "embed_failed_count": "integer — 嵌入失敗封面數（僅 embed_covers=true 時出現）",
        },
        "side_effect": True,
        "confirmation_required": False,
        "idempotent": True,
        "retry_safe": True,
        "_example_template": "curl -X POST -H 'Content-Type: application/json' -d '{{\"numbers\":[\"FC2-PPV-1854491\",\"FC2-PPV-2471432\"],\"title\":\"PTT 精選\"}}' {base}/api/gallery/generate-from-ids",
    },
    {
        "name": "local_status",
        "description": "批量查詢番號是否已在本地收藏",
        "method": "GET",
        "path": "/api/search/local-status",
        "input_schema": {
            "type": "object",
            "properties": {
                "numbers": {"type": "string", "description": "逗號分隔的番號列表"},
            },
            "required": ["numbers"],
        },
        "output_schema": {
            "<number>": "{exists: boolean, count: integer, paths: [string]} — 以番號為 key",
        },
        "retry_safe": True,
        "_example_template": "curl '{base}/api/search/local-status?numbers=SONE-205,ABW-001'",
    },
    {
        "name": "parse_filename",
        "description": "從檔名提取番號和字幕偵測",
        "method": "POST",
        "path": "/api/parse-filename",
        "input_schema": {
            "type": "object",
            "properties": {
                "filenames": {"type": "array", "items": {"type": "string"}, "description": "檔名陣列"},
            },
            "required": ["filenames"],
        },
        "output_schema": {
            "results": "[{filename: string, number: string|null, has_subtitle: boolean}] — 解析結果陣列",
        },
        "retry_safe": True,
        "_example_template": "curl -X POST -H 'Content-Type: application/json' -d '{{\"filenames\":[\"SONE-205-C.mp4\",\"FC2-1234567.mp4\"]}}' {base}/api/parse-filename",
    },
    {
        "name": "enrich_single",
        "description": "舊片原地補完：補齊 NFO/封面/劇照，不搬移不改名。overwrite_existing=true 時必須先讓用戶確認",
        "method": "POST",
        "path": "/api/enrich-single",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "影片檔案路徑"},
                "number": {"type": "string", "description": "番號（可選）"},
                "mode": {
                    "type": "string",
                    "enum": ["fill_missing", "db_to_sidecar", "refresh_full"],
                    "default": "fill_missing",
                    "description": "fill_missing=只補缺的 / db_to_sidecar=從DB重建不打外站 / refresh_full=強制重抓",
                },
                "write_nfo": {"type": "boolean", "default": True},
                "write_cover": {"type": "boolean", "default": True},
                "write_extrafanart": {"type": "boolean", "default": False},
                "overwrite_existing": {
                    "type": "boolean",
                    "default": False,
                    "description": "是否覆蓋既有檔案",
                },
            },
            "required": ["file_path", "number"],
        },
        "output_schema": {
            "success": "boolean",
            "nfo_written": "boolean — 是否寫入 NFO",
            "cover_written": "boolean — 是否寫入封面",
            "fields_filled": "[string] — 本次補齊的欄位名",
            "source_used": "string — 使用的來源（javbus/dmm/db 等）",
        },
        "side_effect": True,
        "confirmation_required": False,
        "idempotent": True,
        "retry_safe": True,
        "cost_hint": "fill_missing/refresh_full 會打外部網站；db_to_sidecar 純本地",
        "_example_template": "curl -X POST -H 'Content-Type: application/json' -d '{{\"file_path\":\"/library/SONE-205/SONE-205.mp4\",\"number\":\"SONE-205\",\"mode\":\"fill_missing\"}}' {base}/api/enrich-single",
    },
    {
        "name": "collection_sql",
        "description": "Read-only SQL 查詢收藏資料庫，可自由組合 SELECT/JOIN/GROUP BY/WHERE",
        "method": "POST",
        "path": "/api/collection/sql",
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "SELECT 語句（僅允許 SELECT）"},
                "limit": {
                    "type": "integer",
                    "default": 500,
                    "maximum": 500,
                    "description": "回傳筆數上限",
                },
            },
            "required": ["sql"],
        },
        "output_schema": {
            "success": "boolean",
            "columns": "[string] — 欄位名陣列",
            "rows": "[[any]] — 二維結果陣列",
            "count": "integer — 回傳筆數",
        },
        "retry_safe": True,
        "database_schema": {
            "videos": {
                "id": "INTEGER PRIMARY KEY",
                "path": "TEXT UNIQUE — 影片檔案路徑",
                "number": "TEXT — 番號 (e.g. SONE-205)",
                "title": "TEXT — 翻譯後標題",
                "original_title": "TEXT — 原始日文標題",
                "actresses": "TEXT — 女優名 JSON array (e.g. '[\"明日花キララ\"]')",
                "maker": "TEXT — 片商",
                "director": "TEXT — 導演",
                "series": "TEXT — 系列",
                "label": "TEXT — 廠牌",
                "tags": "TEXT — 標籤 JSON array",
                "sample_images": "TEXT — 劇照 JSON array",
                "duration": "INTEGER — 片長（分鐘）",
                "size_bytes": "INTEGER — 檔案大小",
                "cover_path": "TEXT — 封面圖路徑",
                "release_date": "TEXT — 發行日 YYYY-MM-DD",
                "mtime": "REAL — 影片檔案 mtime (Unix timestamp)",
                "nfo_mtime": "REAL — NFO 檔案 mtime (Unix timestamp)",
                "created_at": "TIMESTAMP",
                "updated_at": "TIMESTAMP",
            },
        },
        "sql_examples": [
            "SELECT COUNT(*) as total FROM videos",
            "SELECT maker, COUNT(*) as cnt FROM videos GROUP BY maker ORDER BY cnt DESC LIMIT 10",
            "SELECT * FROM videos WHERE title IS NULL OR cover_path IS NULL LIMIT 50",
            "SELECT * FROM videos WHERE actresses LIKE '%明日花%' AND release_date > '2025-01-01'",
            "SELECT maker, COUNT(*) FROM videos WHERE release_date > '2025-01-01' GROUP BY maker ORDER BY COUNT(*) DESC",
            "SELECT strftime('%Y', release_date) as year, COUNT(*) FROM videos GROUP BY year ORDER BY year DESC",
        ],
        "note": "actresses 和 tags 是 JSON 字串，用 LIKE '%name%' 或 json_each() 查詢",
        "_example_template": "curl -X POST -H 'Content-Type: application/json' -d '{{\"sql\":\"SELECT COUNT(*) as total FROM videos\"}}' {base}/api/collection/sql",
    },
]


def _build_tools(base: str) -> list[dict]:
    tools = []
    for t in _TOOLS:
        tool = copy.deepcopy(t)
        template = tool.pop("_example_template", "")
        tool["example"] = template.format(base=base)
        tools.append(tool)
    return tools


@router.get("/capabilities")
async def get_capabilities(request: Request):
    base = str(request.base_url).rstrip("/")

    return {
        "schema_version": "v1",
        "name": "OpenAver",
        "version": __version__,
        "base_url": base,
        "description": "影片元數據管理工具 — 搜尋、刮削、整理、瀏覽",
        "skill_setup": {
            "description": "將以下內容加入你的 AI 自訂指令 / Skill / System Prompt，讓 AI 學會使用 OpenAver",
            "template": f"你可以使用 OpenAver 影片元數據管理工具。使用前先 GET {base}/api/capabilities 查看可用操作和使用範例。",
            "hint": f"建議將此服務註冊為 AI skill（如 SKILL.md），存入 `curl -s {base}/api/capabilities` 指令，後續啟動自動發現。",
        },
        "quick_check": {
            "description": "確認服務是否運行中",
            "method": "GET",
            "path": "/api/health",
        },
        "network": {
            "scope": "lan",
            "auth": "none",
            "note": "本地/區網服務，不上公網",
        },
        "agent_instructions": {
            "fetch_method": "curl",
            "fetch_note": "必須使用 curl（shell 指令）存取此服務。禁止使用瀏覽器 fetch()、AI 內建的 WebFetch / web_search 等 HTTP 工具 — 這些工具走外部 proxy 或沙箱網路，無法連到 LAN IP。正確做法：用 Bash tool 執行 curl 指令。",
            "example": f"curl -s {base}/api/capabilities",
        },
        "error_format": {
            "structure": {"success": False, "error": "string — 錯誤描述"},
            "http_codes": {
                "400": "參數錯誤（不該重試）",
                "404": "資源不存在（不該重試）",
                "422": "輸入驗證失敗（不該重試）",
                "500": "伺服器錯誤（可重試）",
            },
            "retry_hint": "5xx 可重試，間隔 2 秒，最多 3 次。4xx 不重試，檢查參數。",
        },
        "tools": _build_tools(base),
        "examples": [
            {
                "scenario": "新下載影片整理",
                "description": "剛下載一批檔案，搜尋 metadata + 封面 + NFO + 整理命名",
                "steps": [
                    "1. POST /api/parse-filename 從檔名批量提取番號",
                    "2. POST /api/batch-search 批量取得 metadata",
                    "3. 逐個 POST /api/scrape-single 整理（會搬移+改名+建目錄）",
                ],
                "confirmation_rule": "scrape-single 會搬移檔案，建議先列出計畫讓用戶確認",
            },
            {
                "scenario": "下載前查本地是否已有",
                "description": "用戶貼一串番號，先檢查是否已收藏，避免重複下載",
                "steps": [
                    "1. GET /api/search/local-status?numbers=SONE-205,ABW-001,...",
                ],
                "confirmation_rule": "純查詢，不需確認",
            },
            {
                "scenario": "論壇文章擷取 — URL 或純文字皆可",
                "description": "用戶提供論壇 URL 或直接貼文章內文，AI 抓取內容並提取番號/女優名",
                "steps": [
                    "1. 判斷輸入：URL → 嘗試抓取頁面內容；純文字 → 直接解析",
                    "2. 若 URL 是 ptt.cc → HTTP GET 取得 HTML → 解析內文",
                    "3. 若 URL 是其他論壇 → 回覆用戶「此論壇無法直接抓取，請複製文章內文貼上」",
                    "4. 從內容提取番號（如 'fc2 793288 半外半中' → FC2-PPV-793288）",
                    "5. POST /api/batch-search 批量取得 metadata + 封面 URL",
                ],
                "confirmation_rule": "純查詢，不需確認",
            },
            {
                "scenario": "追蹤女優新片",
                "description": "定期查詢喜歡的女優是否有新作品，比對本地已收藏片單",
                "steps": [
                    "1. GET /api/search?q=明日花キララ&mode=actress&since=2026-03-01&discovery=true → 秒回番號清單",
                    "2. 比對 GET /api/search/local-status 過濾掉已有的",
                    "3. POST /api/batch-search 只抓新片的完整 metadata",
                    "4. 回報新片清單給用戶",
                ],
                "confirmation_rule": "純查詢，不需確認",
            },
            {
                "scenario": "舊片批量補完（NFO / 封面 / 缺欄位）",
                "description": "已在資料庫中的影片，原地補齊缺少的 metadata。嚴格不搬移、不改名、不改目錄結構",
                "steps": [
                    "1. POST /api/collection/sql → SELECT path, number FROM videos WHERE title IS NULL OR cover_path IS NULL",
                    "2. 逐個 POST /api/enrich-single（mode: fill_missing）原地補齊",
                    "3. POST /api/collection/sql → 確認完整度提升",
                ],
                "confirmation_rule": "enrich-single 不搬檔不改名，但會寫入 NFO/封面。建議先告知用戶將補齊的數量",
            },
            {
                "scenario": "換封面來源（JavBus 浮水印 → DMM 高清）",
                "description": "用 DMM 高清封面覆蓋現有 JavBus 浮水印封面",
                "steps": [
                    "1. POST /api/collection/sql → 找出目標影片",
                    "2. POST /api/enrich-single（mode: refresh_full, write_cover: true, overwrite_existing: true）",
                ],
                "confirmation_rule": "overwrite_existing: true 會覆蓋既有封面，必須讓用戶確認",
            },
            {
                "scenario": "DB 有資料但 NFO 檔不見了",
                "description": "從 DB 現有資料重建 NFO sidecar 檔，不打外站",
                "steps": [
                    "1. POST /api/collection/sql → 找目標影片",
                    "2. POST /api/enrich-single（mode: db_to_sidecar）從 DB 重建 NFO",
                ],
                "confirmation_rule": "db_to_sidecar 純本地操作，不打外站。會寫入 NFO 檔",
            },
            {
                "scenario": "收藏統計",
                "description": "快速統計收藏的片商分布、年份分布、女優作品數",
                "steps": [
                    "1. POST /api/collection/sql → SELECT maker, COUNT(*) as cnt FROM videos GROUP BY maker ORDER BY cnt DESC LIMIT 10",
                    "2. POST /api/collection/sql → SELECT strftime('%Y', release_date) as year, COUNT(*) FROM videos GROUP BY year ORDER BY year DESC",
                ],
                "confirmation_rule": "純查詢，不需確認",
            },
        ],
        "integration_notes": {
            "automation": "可搭配 qBittorrent Web API 實現下載→整理自動化",
            "notification": "搭配 LINE Notify / Telegram Bot 實現新片通知",
            "scheduling": "搭配 cron 或 AI agent 排程定期查詢",
            "docker": "支援 Docker 部署，base_url 隨部署環境變動",
        },
        "notes": [
            "所有搜尋遵守節流規則（MAX_WORKERS=2, REQUEST_DELAY=0.3s）",
            "有 side_effect 標記的端點會修改檔案系統",
            "batch-search 建議一次不超過 20 筆，避免觸發來源網站封鎖",
            "base_url 會依實際部署環境動態生成",
        ],
    }
