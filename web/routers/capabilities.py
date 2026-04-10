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
        "description": "舊片原地補完：補齊 NFO/封面/劇照，不搬移不改名。refresh_full 搭配 overwrite_existing=true 才覆蓋既有 NFO/封面；若只想更新 DB 不覆蓋檔案，用 overwrite_existing=false（預設）。overwrite_existing=true 時必須先讓用戶確認",
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
                    "description": "fill_missing=只補缺的 / db_to_sidecar=從DB重建不打外站 / refresh_full=強制重抓（搭配 overwrite_existing=true 才覆蓋既有 NFO/封面）",
                },
                "write_nfo": {"type": "boolean", "default": True},
                "write_cover": {"type": "boolean", "default": True},
                "write_extrafanart": {"type": "boolean", "default": False},
                "overwrite_existing": {
                    "type": "boolean",
                    "default": False,
                    "description": "是否覆蓋既有 NFO/封面檔案（refresh_full 時才有意義；預設 false 只補缺欄位不覆蓋）",
                },
                "source": {
                    "type": "string",
                    "enum": ["auto", "javbus", "dmm", "jav321", "javdb", "fc2", "avsox", "d2pass", "heyzo"],
                    "default": "auto",
                    "description": "刮削來源（auto=自動多源合併；指定單一來源時只打該站；dmm 需要 proxy 才能使用）",
                },
                "javbus_lang": {
                    "type": "string",
                    "enum": ["zh-tw", "ja", "en"],
                    "description": "JavBus 語系（覆蓋 config 設定；source=auto 或 source=javbus 時生效）",
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
        "name": "batch_enrich",
        "description": "批次補完：一次提交最多 20 筆舊片，逐筆補齊 NFO/封面/DB。結果以 SSE streaming 逐筆回傳。注意：此操作會覆寫 NFO 和封面檔案，使用 overwrite_existing=true 時不可逆，必須先讓用戶確認。",
        "method": "POST",
        "path": "/api/batch-enrich",
        "input_schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "maxItems": 20,
                    "items": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string", "description": "影片檔案路徑"},
                            "number": {"type": "string", "description": "番號"},
                            "source": {
                                "type": "string",
                                "enum": ["auto", "javbus", "dmm", "jav321", "javdb", "fc2", "avsox", "d2pass", "heyzo"],
                                "description": "per-item 刮削來源覆蓋（優先於 batch 預設）",
                            },
                            "javbus_lang": {
                                "type": "string",
                                "enum": ["zh-tw", "ja", "en"],
                                "description": "per-item JavBus 語系覆蓋",
                            },
                        },
                        "required": ["file_path", "number"],
                    },
                    "description": "要補完的影片清單（最多 20 筆，按 file_path 去重）",
                },
                "mode": {
                    "type": "string",
                    "enum": ["fill_missing", "db_to_sidecar", "refresh_full"],
                    "default": "refresh_full",
                    "description": "補完模式（套用到全部 items）",
                },
                "source": {
                    "type": "string",
                    "enum": ["auto", "javbus", "dmm", "jav321", "javdb", "fc2", "avsox", "d2pass", "heyzo"],
                    "default": "auto",
                    "description": "batch 預設刮削來源（item.source 未指定時使用）",
                },
                "javbus_lang": {
                    "type": "string",
                    "enum": ["zh-tw", "ja", "en"],
                    "description": "batch 預設 JavBus 語系",
                },
                "write_nfo": {"type": "boolean", "default": True},
                "write_cover": {"type": "boolean", "default": True},
                "write_extrafanart": {"type": "boolean", "default": False},
                "overwrite_existing": {
                    "type": "boolean",
                    "default": False,
                    "description": "是否覆蓋既有 NFO/封面（不可逆，必須先讓用戶確認）",
                },
            },
            "required": ["items"],
        },
        "output_schema": {
            "streaming": "text/event-stream — SSE 格式逐筆推送",
            "progress": "{type: 'progress', current, total, number}",
            "result_item": "{type: 'result-item', number, file_path, success, nfo_written, cover_written, source_used, error?}",
            "done": "{type: 'done', summary: {total, success, failed}}",
        },
        "side_effect": True,
        "confirmation_required": True,
        "idempotent": False,
        "retry_safe": False,
        "cost_hint": "每筆 item 觸發外部網站搜尋",
        "_example_template": "curl -N -X POST -H 'Content-Type: application/json' -d '{{\"items\":[{{\"file_path\":\"/video/IPZ-154.mp4\",\"number\":\"IPZ-154\"}}],\"mode\":\"refresh_full\"}}' {base}/api/batch-enrich",
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
                "user_tags": "TEXT — 用戶自訂標籤 JSON array",
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
    {
        "name": "collection_analysis",
        "description": "收藏庫 metadata 健康度診斷 — 統計各欄位缺失數、空陣列、異常番號、日文 tag、NFO 狀態。AI agent 批次補完前先呼叫此端點了解規模",
        "method": "GET",
        "path": "/api/collection/analysis",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "output_schema": {
            "total_videos": "integer — 收藏總筆數",
            "missing_fields": "{title, actresses, maker, tags, release_date, cover_path, director, label, original_title} — 各欄位 NULL/空字串筆數",
            "empty_array_fields": "{actresses, tags} — JSON 空陣列（'[]'）筆數",
            "corrupted_numbers": "{total: integer, patterns: [{name, count}]} — 異常番號統計（digit_prefix/TK_prefix/K9_prefix/R_prefix）",
            "japanese_tags": "{total: integer} — tags 含假名字元的筆數",
            "nfo_status": "{has_nfo: integer, missing_nfo: integer} — NFO 狀態統計",
            "available_groups": "[string] — 可用的 group 名稱（傳給 /api/collection/analysis/groups）",
        },
        "side_effect": False,
        "confirmation_required": False,
        "retry_safe": True,
        "_example_template": "curl '{base}/api/collection/analysis'",
    },
    {
        "name": "collection_analysis_groups",
        "description": "依問題類型取得待修復影片清單（drill-down）。group 可選：no_nfo / corrupted_numbers / japanese_tags / missing_core / missing_secondary。永遠從頭取 limit 筆，批次修復後再呼叫取下一批，直到 items 為空",
        "method": "POST",
        "path": "/api/collection/analysis/groups",
        "input_schema": {
            "type": "object",
            "properties": {
                "group": {
                    "type": "string",
                    "enum": [
                        "no_nfo", "corrupted_numbers", "japanese_tags",
                        "missing_core", "missing_secondary"
                    ],
                    "description": "問題類型群組",
                },
                "limit": {
                    "type": "integer",
                    "default": 50,
                    "maximum": 200,
                    "description": "回傳筆數上限（1–200）",
                },
                "exclude_western": {
                    "type": "boolean",
                    "default": True,
                    "description": "是否過濾掉西洋片（路徑含「西洋」/「《03》」/「《05》」）",
                },
            },
            "required": ["group"],
        },
        "output_schema": {
            "group": "string — 請求的 group 名稱",
            "total": "integer — 符合條件的總筆數（含 exclude_western 過濾後）",
            "limit": "integer — 請求的 limit",
            "exclude_western": "boolean — 是否已過濾西洋片",
            "items": "[{id, number, file_path, title, maker}] — 待修復影片清單",
        },
        "side_effect": False,
        "confirmation_required": False,
        "retry_safe": True,
        "_example_template": "curl -X POST -H 'Content-Type: application/json' -d '{{\"group\":\"no_nfo\",\"limit\":50}}' {base}/api/collection/analysis/groups",
    },
    {
        "name": "fix_numbers_preview",
        "description": "預覽收藏庫中符合異常番號修正規則的影片清單。支援 4 種規則：digit_prefix（開頭多餘數字）、TK_prefix、K9_prefix、R_prefix。不修改任何資料，回傳待修正清單供 fix_numbers_apply 使用",
        "method": "POST",
        "path": "/api/collection/fix-numbers/preview",
        "input_schema": {
            "type": "object",
            "properties": {
                "rules": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["digit_prefix", "TK_prefix", "K9_prefix", "R_prefix"],
                    },
                    "description": "要套用的規則名稱（空陣列或省略 = 全部 4 條規則）",
                },
            },
            "required": [],
        },
        "output_schema": {
            "rules_applied": "[string] — 實際套用的規則名稱",
            "affected": "[{id, old_number, new_number, rule, path}] — 待修正影片清單",
            "total": "integer — 符合條件的總筆數",
        },
        "side_effect": False,
        "confirmation_required": False,
        "retry_safe": True,
        "_example_template": "curl -X POST -H 'Content-Type: application/json' -d '{{\"rules\":[]}}' {base}/api/collection/fix-numbers/preview",
    },
    {
        "name": "fix_numbers_apply",
        "description": "執行番號修正：將 fix_numbers_preview 回傳的異常番號永久更新到 DB。**此操作直接修改 DB 的 number 欄位，不可逆。必須先呼叫 preview 確認範圍，並讓用戶確認後再執行。** apply 內部會重新驗證每個 ID，已被其他途徑修正的番號不會被覆蓋",
        "method": "POST",
        "path": "/api/collection/fix-numbers/apply",
        "input_schema": {
            "type": "object",
            "properties": {
                "ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "要修正的影片 ID 清單（從 fix_numbers_preview 的 affected[].id 取得）",
                },
            },
            "required": ["ids"],
        },
        "output_schema": {
            "updated": "integer — 成功更新的筆數",
            "failed": "integer — 跳過或失敗的筆數（ID 不存在、或番號已不符合規則）",
        },
        "side_effect": True,
        "confirmation_required": True,
        "idempotent": False,
        "retry_safe": False,
        "_example_template": "curl -X POST -H 'Content-Type: application/json' -d '{{\"ids\":[42,55,78]}}' {base}/api/collection/fix-numbers/apply",
    },
    {
        "name": "proxy_image",
        "description": "代理下載遠端圖片 — 解決 Cloudflare / 防盜鏈問題。搜尋結果的 cover 和 sample_images URL 是遠端直連，AI agent 直接 curl 會被擋。必須透過此端點下載。",
        "method": "GET",
        "path": "/api/proxy-image",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "遠端圖片 URL（從搜尋結果的 cover 或 sample_images 欄位取得）"},
            },
            "required": ["url"],
        },
        "output_schema": "binary — 圖片二進位資料（Content-Type: image/jpeg）。失敗時回傳 404 空回應。",
        "side_effect": False,
        "retry_safe": True,
        "_example_template": "curl -o cover.jpg '{base}/api/proxy-image?url=https://pics.dmm.co.jp/digital/video/ssis00221/ssis00221pl.jpg'",
    },
    {
        "name": "user_tags",
        "description": "管理用戶自訂標籤（評分、書籤、分類等）。存入 DB + NFO <user_tag> 元素，不被 scraper refresh 覆蓋",
        "method": "POST",
        "path": "/api/user-tags",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "影片路徑（DB key，file:/// URI 格式）"},
                "add": {"type": "array", "items": {"type": "string"}, "description": "要新增的 tags（可省略）"},
                "remove": {"type": "array", "items": {"type": "string"}, "description": "要移除的 tags（可省略）"},
            },
            "required": ["file_path"],
        },
        "output_schema": {
            "success": "boolean",
            "user_tags": "[string] — 更新後的完整 user_tags 清單",
            "nfo_updated": "boolean — NFO 是否同步更新",
        },
        "side_effect": True,
        "confirmation_required": False,
        "retry_safe": True,
        "also_see": "GET /api/user-tags?file_path=... — 查詢現有 user_tags（見 get_user_tags tool）",
        "_example_template": "curl -X POST -H 'Content-Type: application/json' -d '{{\"file_path\":\"file:///C:/AVtest/SONE-205/SONE-205.mp4\",\"add\":[\"★5\",\"足\"]}}' {base}/api/user-tags",
    },
    {
        "name": "get_user_tags",
        "description": (
            "查詢指定影片的現有 user_tags（user_tags POST 的對等讀取端點）。"
            "接受 file:/// URI 或 native FS 路徑（自動正規化）。影片不存在於 DB 時回 200 + 空清單。"
        ),
        "method": "GET",
        "path": "/api/user-tags",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "影片路徑（file:/// URI 或 native FS path）"},
            },
            "required": ["file_path"],
        },
        "output_schema": {
            "user_tags": "[string] — 現有 user_tags 清單（空時回 []）",
            "file_path": "string — 正規化後的 file:/// URI",
        },
        "side_effect": False,
        "retry_safe": True,
        "_example_template": "curl '{base}/api/user-tags?file_path=file:///C:/AVtest/SONE-205/SONE-205.mp4'",
    },
    {
        "name": "showcase_videos",
        "description": (
            "列出當前 Showcase 設定資料夾下「所有」影片，每筆含 19 欄位 enrich 過的完整 metadata。"
            " ⚠️ 高 token 成本：回整個 configured directory（可能數百到數千筆）一次回完，無分頁。"
            " Routing 規則（依優先級）："
            " (1) 已知具體 path → 用 `showcase_video`（單筆，省 token）；"
            " (2) 只需 ID/path 篩選、統計、條件查詢 → 用 `collection_sql`（自訂 SELECT）"
            " 或 `collection_analysis`（預設 5 種診斷分組）；"
            " (3) 僅在「真的需要全庫概觀」時才用本 tool（例如 diagnose 缺資料的影片總覽、"
            " 批次操作前的全量探索）。"
        ),
        "method": "GET",
        "path": "/api/showcase/videos",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "output_schema": {
            "success": "boolean",
            "total": "integer — videos 陣列長度",
            "videos": {
                "type": "array",
                "description": "影片清單；每筆 item 為 19 欄位 dict",
                "item_fields": {
                    "path": "string — file:/// URI（DB key 格式，可作為 showcase_video 查詢輸入）",
                    "title": "string",
                    "original_title": "string",
                    "number": "string — 番號（可能為空字串）",
                    "actresses": "string — ⚠️ 逗號分隔字串，**不是** array（例：'女優A,女優B'）",
                    "maker": "string",
                    "release_date": "string — YYYY-MM-DD（可能為空字串）",
                    "tags": "string — ⚠️ 逗號分隔字串，**不是** array",
                    "size": "integer — 檔案 bytes",
                    "cover_url": "string — 後端代理 URL（/api/gallery/image?path=...），可直接 <img> 顯示",
                    "mtime": "integer — Unix timestamp（秒）",
                    "director": "string",
                    "duration": "integer | null — 秒；null 時前端隱藏",
                    "series": "string",
                    "label": "string",
                    "sample_images": "array[string] — 劇照 gallery image URLs（真正的 array）",
                    "user_tags": "array[string] — 用戶自訂標籤（真正的 array，可空）",
                    "has_cover": "boolean — DB 初判 cover_path 非空（不做 IO 檢查）",
                    "has_nfo": "boolean — nfo_mtime > 0（41a 寫入契約）",
                },
            },
        },
        "side_effect": False,
        "retry_safe": True,
        "_example_template": "curl '{base}/api/showcase/videos'",
    },
    {
        "name": "showcase_video",
        "description": (
            "By-path 單筆查詢 Showcase 影片資料（showcase_videos 的單筆版本）。"
            " 比 `collection_sql WHERE path=...` 更省 prompt token，且回傳 schema 已 enrich"
            "（cover_url、has_cover、has_nfo 已預先計算）。"
            " 適合：(a) 前端 enrich-single / scrape-single 後刷新單張卡片；"
            " (b) AI 從 collection_sql 結果拿到 path 後取單筆完整 metadata。"
            " 影片不在 configured directory 或 DB 內回 404。"
        ),
        "method": "GET",
        "path": "/api/showcase/video",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "影片 file:/// URI（DB key 格式）"},
            },
            "required": ["path"],
        },
        "output_schema": {
            "success": "boolean",
            "video": (
                "object — 19 欄位 dict，schema 同 showcase_videos.videos.item_fields"
                "（path/title/original_title/number/actresses[csv⚠️]/maker/release_date/tags[csv⚠️]/"
                "size/cover_url/mtime/director/duration/series/label/sample_images[array]/"
                "user_tags[array]/has_cover/has_nfo）。注意 actresses 和 tags 是逗號分隔字串，"
                "其餘標記為 array 的欄位才是真正的 array。"
            ),
        },
        "side_effect": False,
        "retry_safe": True,
        "_example_template": "curl '{base}/api/showcase/video?path=file:///C:/AVtest/SONE-205/SONE-205.mp4'",
    },
    {
        "name": "jellyfin_check",
        "description": (
            "檢查本地收藏中有多少影片缺少 Jellyfin poster/fanart 圖片，回傳待更新數量。"
            " update 操作（批次產生圖片）為 SSE 串流，不適合 AI 直接呼叫，需透過 UI 操作。"
        ),
        "method": "GET",
        "path": "/api/gallery/jellyfin-check",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "output_schema": {
            "success": "boolean",
            "data": "{need_update: integer} — 缺少 Jellyfin 圖片的影片數量",
        },
        "side_effect": False,
        "confirmation_required": False,
        "retry_safe": True,
        "_example_template": "curl '{base}/api/gallery/jellyfin-check'",
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
        "image_display": {
            "description": "如何在對話中顯示搜尋結果的封面 / 劇照圖片",
            "problem": "搜尋結果的 cover 和 sample_images 是遠端 URL。AI agent 直接 curl 遠端 URL 會被 Cloudflare / 防盜鏈擋掉（回傳 HTML 而非圖片）。",
            "solution": "透過 /api/proxy-image 下載圖片到本地，再用本地絕對路徑嵌入回覆。",
            "steps": [
                "1. 搜尋取得 cover / sample_images URL",
                "2. curl -o <local_path> '<base_url>/api/proxy-image?url=<remote_url>' 下載到本地",
                "3. 用 Markdown 圖片語法嵌入回覆：![番號 封面](<local_absolute_path>)",
            ],
            "rules": [
                "禁止直接 curl 遠端圖片 URL — 一定會被擋",
                "一律透過 /api/proxy-image 代理下載",
                "下載到本地後用絕對路徑顯示（不要用遠端 URL 嵌入）",
            ],
            "codex_app": {
                "description": "Codex App（OpenAI 桌面應用）專用指引 — 目前唯一支援對話內嵌圖片的 GUI agent",
                "temp_dir": "C:/Codex/tmp/openaver-images/",
                "display_format": "![SONE-205 cover](C:/Codex/tmp/openaver-images/SONE-205-cover.jpg)",
                "naming": "<number>-cover.jpg 或 <number>-sample-<N>.jpg",
                "note": "路徑不可含空格。OpenAver 的番號與檔名不含空格，可安全使用。",
            },
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
                "scenario": "顯示封面圖片（對話內嵌入）",
                "description": "用戶要求看某部片的封面或劇照，AI 在回覆中直接顯示圖片",
                "steps": [
                    "1. GET /api/search?q=SONE-205 → 取得 cover URL",
                    "2. curl -o /tmp/SONE-205-cover.jpg '<base_url>/api/proxy-image?url=<cover_url>' 下載到本地",
                    "3. 回覆中嵌入 ![SONE-205 封面](/tmp/SONE-205-cover.jpg)",
                ],
                "confirmation_rule": "純查詢 + 下載圖片，不需確認",
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
