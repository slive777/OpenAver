import asyncio
import copy

from fastapi import APIRouter, Request

from core.access_auth import load_snapshot, snapshot
from core.version import __version__
from core.logger import get_logger
from core.source_config import get_source_enum

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["capabilities"])


_TOOLS: list[dict] = [
    {
        "name": "search",
        "description": "搜尋單一番號或女優，回傳 metadata + 封面 URL。不修改資料庫",
        "side_effect": False,
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
                    "description": "搜尋模式；source 只在 exact 時有效",
                },
                "source": {
                    "type": "string",
                    "enum": get_source_enum(include_auto=False),
                    "description": "指定來源必須搭配精確模式（mode=exact），其他模式帶了會被拒絕",
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
        "description": "一次搜尋多個番號，適合文章解析後批量查詢。不修改資料庫",
        "side_effect": False,
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
        "description": "新片整理：搜尋 metadata → 下載封面 → 生成 NFO → 重命名搬移。帶 metadata 時直接採用你給的那份，不重查來源。不帶 metadata 時：number 是完整番號格式 → 問第一家有結果的來源、整包拿，不跨站合併（與搜尋頁整理、定時整理同一套規則）；number 不是完整番號格式（打錯、傳成標題或女優名）→ 退回逐站精確查詢並跨站合併欄位，也就是今天的既有行為（無碼模式開啟時例外：改問無碼來源白名單、命中第一家即回，與定時整理一致）。想要多來源聚合，自己對每個來源各查一次 /api/search、組好 metadata 再傳進來。",
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
        "description": "批量查詢番號是否已在本地收藏。不修改資料庫",
        "side_effect": False,
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
        "description": "從檔名提取番號和字幕偵測。不修改資料庫",
        "side_effect": False,
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
        "description": "舊片原地補完：補齊 NFO/封面/劇照，不搬移不改名。refresh_full 搭配 overwrite_existing=true 才覆蓋既有 NFO/封面；若只想更新 DB 不覆蓋檔案，用 overwrite_existing=false（預設）。overwrite_existing=true 時必須先讓用戶確認。劇照只補缺的：extrafanart 資料夾裡已經存在的圖一律不會被覆蓋，overwrite_existing 對劇照不適用。metadata 帶番號與 DB 既有值不符會被拒絕，除非帶 allow_number_change=true；分集片（-cd1/-cd2）要逐段各自呼叫本端點，一次只吃一個 file_path",
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
                "metadata": {
                    "type": "object",
                    "description": (
                        "AI 已審核/改寫過的刮削結果，逐欄位落地（整包取代，不是補缺）。"
                        "只在 mode=refresh_full 時生效，其餘模式會被拒絕。"
                        "允許欄位：title/original_title/actors/maker/director/series/label/tags/date/duration/"
                        "cover/preview_cover_url/preview_sample_images/url/sample_images/_summary/_rating。"
                        "換封面須顯式帶 write_cover=true（本欄位存在時，write_cover 預設改為 false）。"
                        "_summary／_rating 存不存在，看你手上那筆結果字典本身的 key，不要用搜尋模式名稱猜："
                        "凡是經過 core.scraper.search_jav 組出來的結果，兩個 key 一定都在（值可能是空字串"
                        "或 None，但 key 存在）——精確番號搜尋、partial／prefix 局部搜尋、javbus 關鍵字/女優"
                        "模糊搜尋都經過它。不經過它、直接用 to_legacy_dict() 組裝的結果就完全不會有這兩個"
                        "key（目前已知：DMM 關鍵字搜尋、javlibrary 多版本清單、jav321 關鍵字 fallback）。"
                        "拿到後可整包送 scrape_single（零驗證）；但 enrich_single 有嚴格白名單，未知欄位會 400。"
                        "這部片目前 NFO 裡的值仍然讀不到（DB 不收這兩欄）；未帶時後端沿用既有 NFO 這條規則不變。"
                        "⚠️ _rating 是 0-5 刻度（不是 Jellyfin 那種 0-10），後端會自動 ×2 存進 NFO；"
                        "送 8.0 會寫出 16.0，不是你以為的『10 分制打 8 分』。"
                        "⚠️ original_title 送空字串會被拒絕（400）——這一欄沒有受支援的清空途徑，"
                        "只能換成另一個非空值。其餘文字欄位送空字串是合法的，意思是「這一欄我要它空的」。"
                        "⚠️ **這是整包取代：你沒送的白名單欄位會被寫成空**（女優、標籤、片商、系列、"
                        "發售日…），不是「維持原值」。要只改一欄，就得把其餘欄位連同原值一起送回來"
                        "（例外只有三個：original_title 拒絕空字串、_summary 與 _rating 未帶時沿用既有 NFO）。"
                        "⚠️ duration 的單位是**分鐘**（與讀取端回的 duration 同一刻度），不是秒。"
                        "⚠️ source 不是可落地欄位，但若要帶必須是字串、且不可為 \"db\" 或 \"nfo\"（400）"
                        "——那兩個是後端內部保留值，不要拿來標示「這份資料來自你的資料庫」。"
                        "帶了就原樣回顯在 source_used，省略則回顯 \"scraper\"。"
                    ),
                },
                "write_nfo": {"type": "boolean", "default": True},
                "write_cover": {
                    "type": "boolean",
                    "default": True,
                    "description": "預設是否換封面。這個預設值只在不帶 metadata 時成立；帶 metadata 時預設改為 false（CD-135-4）——要換封面必須顯式傳 true。",
                },
                "write_extrafanart": {"type": "boolean", "default": False},
                "allow_number_change": {
                    "type": "boolean",
                    "default": False,
                    "description": (
                        "允許把這個檔案的番號改成與資料庫既有值不同的號。預設 false：番號不符一律 400，"
                        "避免把別部片的資料寫到這部片上。只有在你確定要改號（例如原本認錯番號）時才傳 true。"
                    ),
                },
                "overwrite_existing": {
                    "type": "boolean",
                    "default": False,
                    "description": "是否覆蓋既有 NFO/封面檔案（refresh_full 時才有意義；預設 false 只補缺欄位不覆蓋）",
                },
                "source": {
                    "type": "string",
                    "enum": get_source_enum(include_auto=True),
                    "default": "auto",
                    "description": "刮削來源（**預設值就是 auto**——不指定就會自動把每個欄位各自取第一個有值的來源、拼成一份，不是「整包用第一家的資料」；指定單一來源時才是整包用那家的；部分地區 dmm 需要日本 IP（設定頁 Proxy 欄或日本 VPN））",
                },
                "javbus_lang": {
                    "type": "string",
                    "enum": ["zh-tw", "ja", "en"],
                    "description": "JavBus 語系（覆蓋 config 設定；source=auto 或 source=javbus 時生效）",
                },
                "preserve_title": {
                    "type": "boolean",
                    "default": False,
                    "description": "true 時保留這部片目前的標題，不用新刮到的標題取代；新刮到的番號與原片不同時仍改用新標題。只影響標題，其他欄位照常更新。",
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
        "name": "video_rescrape_with_source",
        "description": (
            "進階重刮：以指定來源覆蓋既有封面 / NFO，不可逆。"
            "mode=refresh_full 重刮覆蓋（rescrape 主用）/ fill_missing 補缺。"
            "重刮覆蓋請設 overwrite_existing=true（refresh_full 配 overwrite_existing=false "
            "在不會寫出任何 sidecar 的設定下後端會擋下，只更新 DB 會造成磁碟分裂）。"
            "source 可為停用來源或 metatube:{provider}。"
        ),
        "method": "POST",
        "path": "/api/enrich-single",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "影片檔案路徑"},
                "number": {"type": "string", "description": "番號（可與檔名解析不同，重刮用此值查詢）"},
                "source": {
                    "type": "string",
                    "enum": get_source_enum(include_auto=True),
                    "default": "auto",
                    "description": "重刮來源（明確選源整包贏；可為停用來源 / metatube:{provider}；auto=多源合併）",
                },
                "mode": {
                    "type": "string",
                    "enum": ["refresh_full", "fill_missing"],
                    "default": "refresh_full",
                    "description": "refresh_full=重刮覆蓋 / fill_missing=補缺",
                },
                "overwrite_existing": {
                    "type": "boolean",
                    "default": True,
                    "description": "是否覆蓋既有 NFO/封面。重刮覆蓋請設 true；refresh_full+false 不會寫出任何 sidecar 時後端 400",
                },
                "write_nfo": {"type": "boolean", "default": True},
                "write_cover": {"type": "boolean", "default": True},
                "preserve_title": {
                    "type": "boolean",
                    "default": False,
                    "description": "true 時保留這部片目前的標題，不用新刮到的標題取代；新刮到的番號與原片不同時仍改用新標題。只影響標題，其他欄位照常更新。",
                },
            },
            "required": ["file_path", "number", "source", "mode", "overwrite_existing"],
        },
        "output_schema": {
            "success": "boolean",
            "nfo_written": "boolean — 是否寫入 NFO",
            "cover_written": "boolean — 是否寫入封面",
            "fields_filled": "[string] — fill_missing 模式下本次補上的欄位名（無缺漏則為空）；refresh_full 不回報覆蓋欄位，固定為空陣列",
            "source_used": "string — 實際使用的來源",
            "reason": "string — hit|no_cover|not_found|error",
        },
        "side_effect": True,
        "confirmation_required": True,
        "idempotent": False,
        "retry_safe": False,
        "cost_hint": "refresh_full 會打外部網站重抓",
        "_example_template": (
            "curl -X POST -H 'Content-Type: application/json' "
            "-d '{{\"file_path\":\"/library/SONE-205/SONE-205.mp4\",\"number\":\"SONE-205\","
            "\"source\":\"javdb\",\"mode\":\"refresh_full\",\"overwrite_existing\":true}}' "
            "{base}/api/enrich-single"
        ),
    },
    {
        "name": "fetch_samples",
        "description": "自動下載影片對應番號的劇照（sample images）到本機 extrafanart 資料夾，並更新 DB sample_images 欄位。僅下載劇照，不改 NFO / 封面 / 其他欄位。既有的劇照不會被取代——只補缺的那幾張；要整組換掉請由用戶自行刪除 extrafanart 資料夾後再執行。若影片所在資料夾有多於 1 個影片會拒絕執行（避免污染）。",
        "method": "POST",
        "path": "/api/scraper/fetch-samples",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "影片檔案路徑（file:/// URI 或原生 FS 路徑）"},
                "number": {"type": "string", "description": "番號"},
            },
            "required": ["file_path", "number"],
        },
        "output_schema": {
            "success": "boolean",
            "nfo_written": "boolean — 固定 false（此端點不寫 NFO）",
            "cover_written": "boolean — 固定 false（此端點不寫封面）",
            "extrafanart_written": "integer — 本次成功下載的劇照數；0 也可能代表「本來就齊全、沒有缺的要補」，不必然是失敗",
            "fields_filled": "[string] — 本次補齊的欄位名",
            "source_used": "string — 使用的來源",
            "error": "string|null — 錯誤訊息；multi_video_folder=資料夾有多片，拒絕執行",
            "count": "integer — multi_video_folder 時，資料夾內的影片數",
        },
        "side_effect": True,
        "confirmation_required": True,
        "idempotent": True,
        "retry_safe": True,
        "cost_hint": "會打外部網站抓劇照，並寫入本機磁碟與 DB",
        "_example_template": "curl -X POST -H 'Content-Type: application/json' -d '{{\"file_path\":\"file:///library/SONE-205/SONE-205.mp4\",\"number\":\"SONE-205\"}}' {base}/api/scraper/fetch-samples",
    },
    {
        "name": "batch_enrich",
        "description": "批次補完：一次提交最多 20 筆舊片，逐筆補齊 NFO/封面/DB。結果以 SSE streaming 逐筆回傳。注意：此操作會覆寫 NFO 和封面檔案，使用 overwrite_existing=true 時不可逆，必須先讓用戶確認。劇照不在此列：既有的 extrafanart 圖一律不會被覆蓋，overwrite_existing 對劇照不適用，只補缺的那幾張。",
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
                                "enum": get_source_enum(include_auto=True),
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
                    "enum": get_source_enum(include_auto=True),
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
            "result_item": "{type: 'result-item', number, file_path, success, nfo_written, cover_written, source_used, reason, error?}（reason: hit|no_cover|not_found|error；唯讀來源片改道 output_dir 產生、成功項回 nfo_written/cover_written 及 reason（hit/no_cover，與非唯讀項同語意）、不再回 readonly 拒絕）",
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
                "user_rating": "INTEGER — 精選標記（1=精選 / 0=未精選；只由 POST /api/user-rating 寫入）",
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
        "description": "代理下載遠端圖片 — 解決 Cloudflare / 防盜鏈問題。搜尋結果的 cover 和 sample_images URL 是遠端直連，AI agent 直接 curl 會被擋。必須透過此端點下載。URL 必須屬於 SSRF 白名單域名（scraper 圖片來源 javbus / dmm / javdb / jav321 等，以及女優圖片 cdn.jsdelivr.net / upload.wikimedia.org / graphis.ne.jp / faws.xcity.jp），外部圖床一律須為 https。另：若使用者目前**已連線** metatube，該台伺服器的圖片端點（path 必須以 /v1/images/ 開頭）亦放行，scheme 依其設定的 base_url（LAN 自架可能是 http）；未連線時該放行即消失。非白名單 host、非法 path、或跟隨 redirect 的來源一律回 403/404。",
        "method": "GET",
        "path": "/api/proxy-image",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "遠端圖片 URL（從搜尋結果的 cover 或 sample_images 欄位取得；須為 https 白名單域名）"},
            },
            "required": ["url"],
        },
        "output_schema": "binary — 圖片二進位資料（Content-Type: image/jpeg）。非白名單 URL 回 403；外部下載失敗回 404 空回應。",
        "side_effect": False,
        "retry_safe": True,
        "_example_template": "curl -o cover.jpg '{base}/api/proxy-image?url=https://pics.dmm.co.jp/digital/video/ssis00221/ssis00221pl.jpg'",
    },
    {
        "name": "user_tags",
        "description": (
            "管理用戶自訂標籤（評分、書籤、分類等）。存入 DB + NFO <user_tag> 元素，不被 scraper refresh 覆蓋。"
            "唯讀來源的片寫的是輸出夾那份 NFO（原始資料夾零寫入）；該片還沒產出輸出夾時，"
            "標籤仍會存進 DB，但回傳 readonly_no_output=true 表示這次沒有任何 NFO 被更新。"
        ),
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
            "readonly_no_output": "boolean — 唯讀來源的片，這次沒有任何 NFO 被更新時為 true（標籤已存進 DB，但媒體伺服器讀到的 NFO 沒變：可能是還沒產出輸出夾、或那份 NFO 讀不到／壞掉）。一般片恆為 false",
        },
        "side_effect": True,
        "confirmation_required": False,
        "retry_safe": True,
        "also_see": "GET /api/user-tags?file_path=... — 查詢現有 user_tags（見 get_user_tags tool）",
        "_example_template": "curl -X POST -H 'Content-Type: application/json' -d '{{\"file_path\":\"file:///C:/AVtest/SONE-205/SONE-205.mp4\",\"add\":[\"★5\",\"足\"]}}' {base}/api/user-tags",
    },
    {
        "name": "user_rating",
        "description": (
            "批次或單筆冪等設定「精選」狀態（picked: true/false）。"
            "⚠️ side effect：一次呼叫可改動多部影片的精選狀態，批次取消無一鍵復原。"
            "精選是獨立欄位（user_rating），不是 user_tags 裡的 ★ 標籤——兩者互不影響、不會互相覆蓋。"
            "分集片（-cd1/-cd2 等）自動解析到代表段，效果套用到整組。"
        ),
        "method": "POST",
        "path": "/api/user-rating",
        "input_schema": {
            "type": "object",
            "properties": {
                "paths": {"type": "array", "items": {"type": "string"}, "description": "批次影片路徑清單（file:/// URI），與 file_path 二擇一，最多 500 筆"},
                "file_path": {"type": "string", "description": "單筆影片路徑（file:/// URI），與 paths 二擇一"},
                "picked": {"type": "boolean", "description": "目標精選狀態，true=設為精選，false=取消精選"},
            },
            "required": ["picked"],
        },
        "output_schema": {
            "success": "boolean",
            "picked": "boolean — 本次設定的目標狀態",
            "results": "[{path, ok, reason?}] — 逐路徑回報，與輸入 1:1 對應；reason 目前只有 not_found",
            "changed": "integer — 成功命中的影片組數（分集片去重後計數）。注意：本來就已是目標狀態的片也算命中，不代表這麼多片的星真的變了",
        },
        "side_effect": True,
        "confirmation_required": True,
        "retry_safe": True,
        "also_see": "GET /api/showcase/videos — 查詢影片目前的 user_rating 欄位",
        "_example_template": "curl -X POST -H 'Content-Type: application/json' -d '{{\"file_path\":\"file:///C:/AVtest/SONE-205/SONE-205.mp4\",\"picked\":true}}' {base}/api/user-rating",
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
            "列出當前 Showcase 設定資料夾下「所有」影片，每筆含 23 欄位 enrich 過的完整 metadata。"
            " ⚠️ **分集片（`-cd1`/`-part2`…）一組只回一筆**（feature/122）：同資料夾同主幹的各段"
            "合併成單一 item，`path` 是**段號最小的那一段**（通常是 cd1，但不保證 cd1 存在）、"
            "`size` 是各段加總、`part_tokens` 列出段別。"
            "因此 `total` 是**分組數不是檔案數**，做全庫盤點時不要當成檔案總數。"
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
                "description": "影片清單；每筆 item 為 23 欄位 dict（分集片一組一筆）",
                "item_fields": {
                    "path": "string — file:/// URI（DB key 格式，可作為 showcase_video 查詢輸入）",
                    "title": "string",
                    "original_title": "string",
                    "number": "string — 番號（可能為空字串）",
                    "actresses": "string — ⚠️ 逗號分隔字串，**不是** array（例：'女優A,女優B'）",
                    "maker": "string",
                    "release_date": "string — YYYY-MM-DD（可能為空字串）",
                    "tags": "string — ⚠️ 逗號分隔字串，**不是** array",
                    "size": "integer — 檔案 bytes；分集片為各段加總",
                    "cover_url": "string — 後端代理 URL（/api/gallery/image?path=...），可直接 <img> 顯示",
                    "cover_full_url": "string — 恆為原圖代理 URL（不受縮圖快取開關影響）",
                    "mtime": "integer — Unix timestamp（秒）",
                    "director": "string",
                    "duration": "integer | null — 分鐘；null 時前端隱藏",
                    "series": "string",
                    "label": "string",
                    "sample_images": "array[string] — 劇照 gallery image URLs（真正的 array）",
                    "user_tags": "array[string] — 用戶自訂標籤（真正的 array，可空）",
                    "has_cover": "boolean — DB 初判 cover_path 非空（不做 IO 檢查）",
                    "has_nfo": "boolean — nfo_mtime > 0（41a 寫入契約）",
                    "auto_focal": "string — 封面焦點 'x,y'（4 位小數）或空字串",
                    "crop_mode": "string — 'auto'（依 auto_focal 裁切）| 'default'（右裁 baseline）",
                    "part_tokens": (
                        "array[string] — 分集段別字面（例 ['cd1', 'cd2']，依段號升冪）；"
                        "單檔片為空陣列。非空即代表本筆是多個實體檔案的合併呈現。"
                    ),
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
                "object — 23 欄位 dict，schema 同 showcase_videos.videos.item_fields"
                "（path/title/original_title/number/actresses[csv⚠️]/maker/release_date/tags[csv⚠️]/"
                "size/cover_url/cover_full_url/mtime/director/duration/series/label/"
                "sample_images[array]/user_tags[array]/has_cover/has_nfo/auto_focal/crop_mode/"
                "part_tokens[array]）。注意 actresses 和 tags"
                "是逗號分隔字串，其餘標記為 array 的欄位才是真正的 array。"
                " 查詢分集片的任一段，回的都是該組的合併結果（`part_tokens` 非空）。"
            ),
        },
        "side_effect": False,
        "retry_safe": True,
        "_example_template": "curl '{base}/api/showcase/video?path=file:///C:/AVtest/SONE-205/SONE-205.mp4'",
    },
    {
        "name": "jellyfin_check",
        "description": (
            "檢查本地收藏中有多少影片缺少外部媒體管理器 poster/fanart 圖片，回傳待更新數量。"
            " update 操作（批次產生圖片）為 SSE 串流，不適合 AI 直接呼叫，需透過 UI 操作。"
            " 注意：設定中 external_manager 為 off（或任何非 jellyfin/emby/kodi 的值）時，"
            "一律回傳 0，代表「此模式下功能已關閉」，不代表「圖片已經補齊」，請勿因此回報"
            "使用者已無待處理項目。"
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
            "data": "{need_update: integer, items: [{cover_path, base_stem, number, maker, path}]} — 缺少外部媒體管理器圖片的影片數量及清單",
        },
        "side_effect": False,
        "confirmation_required": False,
        "retry_safe": True,
        "_example_template": "curl '{base}/api/gallery/jellyfin-check'",
    },
    {
        "name": "favorite_actress",
        "description": (
            "收藏女優：從本地快取或即時爬取女優資料並存入 DB + 下載照片到本地。"
            "寫入 DB + 下載照片到 output/Gfriends/。"
            "批次收藏多位女優時應序列呼叫或最多併發 2，不得無限制平行 POST"
            "（爬蟲/下載壓力限制，與前端手動連點的節流是同一個不變式）。"
            "四來源都刮不到資料時，若片庫裡已有這位女優的片（NFO 已標名字），"
            "會改建一張只有名字的本地卡，並用該片封面右側裁一張照片當頭像"
            "（best-effort，裁不到也照樣建卡）；片庫裡沒有她的片仍回 404。"
        ),
        "method": "POST",
        "path": "/api/actresses/favorite",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "女優名（日文）"},
                "makers": {"type": "array", "items": {"type": "string"}, "description": "片商名列表（可選，提升 gfriends 照片查詢精準度）"},
            },
            "required": ["name"],
        },
        "output_schema": {
            "success": "boolean",
            "actress": "Actress — 完整女優資料（含本地 photo_url）",
            "photo_downloaded": "boolean — 照片是否成功下載",
        },
        "side_effect": True,
        "confirmation_required": True,
        "idempotent": False,
        "retry_safe": False,
        "_example_template": "curl -X POST -H 'Content-Type: application/json' -d '{{\"name\":\"三上悠亜\"}}' {base}/api/actresses/favorite",
    },
    {
        "name": "list_actresses",
        "description": "列出所有已收藏女優，每筆含 video_count（本地收藏片數）、created_at（收藏時間）、照片 URL 等完整資料。適合 AI 查看用戶收藏總覽或依條件篩選女優。",
        "method": "GET",
        "path": "/api/actresses",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "output_schema": {
            "success": "boolean",
            "actresses": "Actress[] — 完整女優資料陣列，每筆含 name/photo_url/video_count/created_at/is_favorite 等欄位",
            "total": "integer — 收藏女優總數",
        },
        "side_effect": False,
        "confirmation_required": False,
        "idempotent": True,
        "retry_safe": True,
        "_example_template": "curl '{base}/api/actresses'",
    },
    {
        "name": "list_library_actresses",
        "description": (
            "列出本地影片庫（videos 表的 actresses 欄位）中出現過的全部女優，"
            "依別名 group 聚合（同一人的不同別名合併為一筆）。"
            "每筆含 primary_name（正式名）、names（該 group 全部名字，含別名，"
            "供比對/搜尋用）、video_count（本地片數，同一片掛多別名只算一次）、"
            "is_favorite（是否已收藏）。"
            "與 favorite_actress 差異：本端點涵蓋庫內*出現過*的所有名字（不論是否收藏），"
            "list_actresses 只回傳*已收藏*的女優。"
            "適合 AI 用 video_count 篩選候選名單（例如「片數超過 20 的都收藏」），"
            "篩出清單後逐一呼叫 favorite_actress（見該條目的併發限制）。不修改資料庫。"
        ),
        "method": "GET",
        "path": "/api/actresses/library",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "output_schema": {
            "success": "boolean",
            "actresses": (
                "LibraryActressItem[] — 每筆 {primary_name: string, "
                "names: string[]（primary + 別名，供比對用）, "
                "video_count: integer（DISTINCT 片數）, is_favorite: boolean}"
            ),
            "total": "integer — group 總數",
        },
        "side_effect": False,
        "retry_safe": True,
        "_example_template": "curl '{base}/api/actresses/library'",
    },
    {
        "name": "get_actress",
        "description": "查詢單一收藏女優資料（含本地照片 URL）。不修改資料庫",
        "side_effect": False,
        "method": "GET",
        "path": "/api/actresses/{name}",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "女優名（URL path parameter）"},
            },
            "required": ["name"],
        },
        "output_schema": {
            "actress": "Actress",
            "is_favorite": "boolean — 固定 true（此端點只回傳已收藏女優）",
        },
        "retry_safe": True,
        "_example_template": "curl '{base}/api/actresses/%E4%B8%89%E4%B8%8A%E6%82%A0%E4%BA%9C'",
    },
    {
        "name": "unfavorite_actress",
        "description": "取消收藏女優（從 DB 刪除 + 刪除本地照片）",
        "method": "DELETE",
        "path": "/api/actresses/{name}",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "女優名（URL path parameter）"},
            },
            "required": ["name"],
        },
        "output_schema": {
            "success": "boolean",
        },
        "side_effect": True,
        "confirmation_required": True,
        "idempotent": True,
        "retry_safe": True,
        "_example_template": "curl -X DELETE '{base}/api/actresses/%E4%B8%89%E4%B8%8A%E6%82%A0%E4%BA%9C'",
    },
    {
        "name": "alias_crud_read",
        "description": (
            "列出所有別名組或查詢單一別名組。"
            " GET /api/actress-aliases 回傳所有 group（primary_name + aliases list）；"
            " GET /api/actress-aliases/{name} 可用 primary_name 或 alias 查詢所屬 group。"
            " 適合 AI 查看目前別名設定或確認某個名字是否已被收錄。"
        ),
        "method": "GET",
        "path": "/api/actress-aliases",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "女優名（URL path parameter，可為 primary_name 或 alias）。省略時列出所有 group。",
                },
            },
            "required": [],
        },
        "output_schema": {
            "success": "boolean",
            "groups": "AliasGroup[] — 列表時回傳；每筆含 primary_name/aliases/source/created_at/updated_at",
            "total": "integer — 群組總數（列表時）",
            "group": "AliasGroup — 單筆查詢時回傳",
        },
        "side_effect": False,
        "confirmation_required": False,
        "retry_safe": True,
        "_example_template": "curl '{base}/api/actress-aliases'",
    },
    {
        "name": "alias_crud_write",
        "description": (
            "別名 CRUD 寫入操作（建立 group、新增 alias、刪除 group、刪除 alias）。"
            " ⚠️ 刪除整個 group 不可逆，必須先讓用戶確認再執行。"
            " POST /api/actress-aliases 建立新 group；"
            " POST /api/actress-aliases/{name}/alias 新增單一 alias；"
            " DELETE /api/actress-aliases/{name} 刪除整個 group（name 可為 primary 或 alias）；"
            " DELETE /api/actress-aliases/{name}/alias/{alias} 移除單一 alias。"
        ),
        "method": "POST",
        "path": "/api/actress-aliases",
        "input_schema": {
            "type": "object",
            "properties": {
                "primary_name": {
                    "type": "string",
                    "description": "主要名稱（必填，建立 group 時使用）",
                },
                "aliases": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "別名清單（可選，省略等同空 list）",
                },
                "alias": {
                    "type": "string",
                    "description": "單一別名（新增或刪除 alias 時使用）",
                },
            },
            "required": [],
        },
        "output_schema": {
            "success": "boolean",
            "group": "AliasGroup — 建立或新增 alias 成功後的最新 group 資料",
            "error": "string — 衝突或找不到時的錯誤訊息",
        },
        "side_effect": True,
        "confirmation_required": True,
        "retry_safe": False,
        "_example_template": (
            "curl -X POST -H 'Content-Type: application/json'"
            " -d '{{\"primary_name\":\"橋本ありな\",\"aliases\":[\"新ありな\"]}}'"
            " {base}/api/actress-aliases"
        ),
    },
    {
        "name": "alias_search_online",
        "description": (
            "呼叫 scraper orchestrator 搜尋女優，從 profile 提取建議別名列表。"
            " 只查詢不寫入，適合 AI 先取得建議再讓用戶確認是否要呼叫 alias_crud_write 寫入。"
            " 若 scraper 超時回 504；查無此女優回 suggested_aliases=[]。"
        ),
        "method": "POST",
        "path": "/api/actress-aliases/search-online",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "女優名（日文）"},
            },
            "required": ["name"],
        },
        "output_schema": {
            "success": "boolean",
            "name": "string — 查詢名稱",
            "suggested_aliases": "string[] — 建議別名清單（可空 list）",
            "message": "string — 查無時說明訊息（可選）",
        },
        "side_effect": False,
        "confirmation_required": False,
        "retry_safe": True,
        "_example_template": (
            "curl -X POST -H 'Content-Type: application/json'"
            " -d '{{\"name\":\"橋本ありな\"}}'"
            " {base}/api/actress-aliases/search-online"
        ),
    },
    {
        "name": "list_actress_photo_candidates",
        "description": (
            "串流回傳女優候選照片列表（SSE）。"
            "從 4 個雲端來源（graphis/gfriends/wiki/xcity）並行抓取，"
            "加上本機影片封面 crop，最多 6 張。"
            "每張照片準備好立即 push，前端即時展示。不修改資料庫。"
        ),
        "side_effect": False,
        "method": "GET",
        "path": "/api/actresses/{name}/photo-candidates",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "女優名稱（URL path parameter，需 URL encode）",
                },
                "attempt": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "重抓輪替序號：0/省略=主名；N=依 alias 穩定排序輪替，無 alias 時任意 N 行為同 0",
                },
            },
            "required": ["name"],
        },
        "output_schema": {
            "candidates": "SSE stream — event: candidate（重複 N 次）+ event: done",
            "candidate_data": '{"source": str, "thumb_url": str, "full_url": str, "video_path"?: str}',
            "done_data": '{"total": int}',
        },
        "_example_template": "curl -N '{base}/api/actresses/%E4%B8%89%E4%B8%8A%E6%82%A0%E4%BA%9C/photo-candidates'",
    },
    {
        "name": "set_actress_photo",
        "description": (
            "替換女優本機照片。接受雲端 URL（graphis/gfriends/wiki/xcity）或本機影片封面 crop（local_crop）。"
            "⚠️ side effect：覆蓋本機照片檔案（先 glob 刪除舊副檔名再寫入新圖）。"
            "可逆 — 隨時可再換；但舊檔案無備份。"
            "執行前必須先確認用戶選擇的來源與 URL。"
            "身分守衛：name 若是某位已收藏女優的別名，一律回 400 並告知正確名字，"
            "不會靜默把照片寫進別名自己的孤兒資料列。"
        ),
        "method": "POST",
        "path": "/api/actresses/{name}/photo",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "女優名稱（URL path parameter，需 URL encode）"},
                "source": {
                    "type": "string",
                    "enum": ["graphis", "gfriends", "wiki", "xcity", "local_crop"],
                    "description": "照片來源識別碼",
                },
                "url": {"type": "string", "description": "雲端照片 URL（source 為雲端來源時必填）"},
                "video_path": {"type": "string", "description": "影片 file:/// URI（source=local_crop 時必填）"},
                "crop_spec": {"type": "string", "description": "裁切規格，預設 v1（source=local_crop 時適用）"},
            },
            "required": ["name", "source"],
        },
        "output_schema": {
            "photo_url": "string — 新照片路徑，含 ?v={mtime_ns}-{size} cache-bust query",
            "photo_source": "string — 實際使用的來源識別碼（與 request 的 source 相同）",
            "auto_focal": "string — 固定為空字串（換照片不跑自動偵測，不寫入焦點）",
            "crop_mode": "string — 固定為 \"auto\"",
        },
        "side_effect": True,
        "confirmation_required": True,
        "idempotent": False,
        "retry_safe": False,
        "_example_template": (
            "curl -X POST '{base}/api/actresses/%E4%B8%89%E4%B8%8A%E6%82%A0%E4%BA%9C/photo' "
            "-H 'Content-Type: application/json' "
            "-d '{{\"source\": \"graphis\", \"url\": \"https://example.com/photo.jpg\"}}'"
        ),
    },
    {
        "name": "get_notifications",
        "description": "查詢 OpenAver 最近發生的事件通知（最多 10 筆），包含掃描開始/完成/失敗、批次補完等事件。可用來確認後台任務是否成功執行。只讀，不修改任何資料。",
        "method": "GET",
        "path": "/api/notifications",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "output_schema": {
            "items": "[Notification] — 通知列表，最多 10 筆，最新的排前面；每筆含 id/timestamp/level/title_key/message/task_type/is_read",
            "unread_count": "integer — 未讀通知數量",
            "highest_unread_level": "string | null — 未讀中最高嚴重度（info/success/warn/error），無未讀時為 null",
        },
        "side_effect": False,
        "confirmation_required": False,
        "retry_safe": True,
        "_example_template": "curl '{base}/api/notifications'",
    },
    {
        "name": "mark_notifications_read",
        "description": "把所有通知標記為已讀。無破壞性：不刪除任何通知，只更新已讀記錄。下次查詢時 unread_count 會變 0。",
        "method": "POST",
        "path": "/api/notifications/read",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "output_schema": {
            "ok": "boolean",
            "marked_count": "integer — 本次標記為已讀的通知數量",
        },
        "side_effect": True,
        "confirmation_required": False,
        "retry_safe": True,
        "_example_template": "curl -X POST '{base}/api/notifications/read'",
    },
    {
        "name": "clear_notifications",
        "description": "清空所有通知記錄（包含已讀和未讀）。此操作不可逆，清空後記錄永久消失（重啟前）。AI 呼叫前必須向用戶確認。",
        "method": "DELETE",
        "path": "/api/notifications",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "output_schema": {
            "ok": "boolean",
            "cleared_count": "integer — 刪除的通知筆數",
        },
        "side_effect": True,
        "confirmation_required": True,
        "idempotent": True,
        "retry_safe": True,
        "_example_template": "curl -X DELETE '{base}/api/notifications'",
    },
    {
        "name": "similar_covers_by_number",
        "description": "規則式相似度排序：基於 tag IDF-weighted Jaccard + 系列 / 片商 / 年份多訊號 + MMR diversity；給定番號回傳 12 部探索星空候選。不修改資料庫。",
        "side_effect": False,
        "method": "GET",
        "path": "/api/similar-covers/by-number/{number}",
        "input_schema": {
            "type": "object",
            "properties": {
                "number": {"type": "string", "description": "番號（大小寫不敏感）"},
                "limit": {
                    "type": "integer", "default": 12, "minimum": 1, "maximum": 50,
                    "description": "回傳筆數",
                },
            },
            "required": ["number"],
        },
        "output_schema": {
            "model_id": "string — ranker 版本識別（固定 'rule-based:v1'，非 ML model id）",
            "query_video": "{video_id, number, title, cover_url}",
            "results": "[{video_id, number, title, cover_url, cosine_score, penalty_applied, actresses}]",
        },
        "retry_safe": True,
        "_example_template": "curl '{base}/api/similar-covers/by-number/SONE-205'",
    },
    {
        "name": "similar_covers",
        "description": "同 similar_covers_by_number，但用 DB 內部 video_id 查詢。一般 AI agent 用 by-number 即可，本端點為內部識別保留。",
        "side_effect": False,
        "method": "GET",
        "path": "/api/similar-covers/{video_id}",
        "input_schema": {
            "type": "object",
            "properties": {
                "video_id": {"type": "integer"},
                "limit": {"type": "integer", "default": 12, "minimum": 1, "maximum": 50},
            },
            "required": ["video_id"],
        },
        "output_schema": {
            "model_id": "string — ranker 版本識別（固定 'rule-based:v1'，非 ML model id）",
            "query_video": "{video_id, number, title, cover_url}",
            "results": "[{video_id, number, title, cover_url, cosine_score, penalty_applied, actresses}]",
        },
        "retry_safe": True,
        "_example_template": "curl '{base}/api/similar-covers/123'",
    },
    {
        "name": "tag_alias_crud_read",
        "description": (
            "列出所有 tag 別名組或查詢單一 group。"
            " GET /api/tag-aliases 回傳全部 group（primary_name + aliases list）；"
            " GET /api/tag-aliases/{name} 可用 primary_name 或 alias 查詢所屬 group。"
            " 適合 AI 查看目前 tag alias 設定或確認某個 tag 是否已被收錄。"
        ),
        "method": "GET",
        "path": "/api/tag-aliases",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "tag 名稱（URL path parameter，可為 primary_name 或 alias）。省略時列出所有 group。",
                },
            },
            "required": [],
        },
        "output_schema": {
            "success": "boolean",
            "groups": "TagAliasGroup[] — 列表時回傳；每筆含 primary_name/aliases/source/created_at/updated_at",
            "total": "integer — 群組總數（列表時）",
            "group": "TagAliasGroup — 單筆查詢時回傳",
        },
        "side_effect": False,
        "confirmation_required": False,
        "retry_safe": True,
        "_example_template": "curl '{base}/api/tag-aliases'",
    },
    {
        "name": "tag_alias_crud_write",
        "description": (
            "Tag 別名 CRUD 寫入（建立 group、新增 alias、刪除 group、刪除 alias）。"
            " ⚠️ 刪除整個 group 不可逆，必須先讓用戶確認再執行。"
            " POST /api/tag-aliases 建立新 group；"
            " POST /api/tag-aliases/{name}/alias 新增單一 alias；"
            " DELETE /api/tag-aliases/{name} 刪除整個 group（name 可為 primary 或 alias）；"
            " DELETE /api/tag-aliases/{name}/alias/{alias} 移除單一 alias。"
            " tag alias 影響 Showcase 過濾展開與 SimilarRanker canonicalize，寫入後立即生效（cache 自動清除）。"
        ),
        "method": "POST",
        "path": "/api/tag-aliases",
        "input_schema": {
            "type": "object",
            "properties": {
                "primary_name": {
                    "type": "string",
                    "description": "主要 tag 名稱（必填，建立 group 時使用）",
                },
                "aliases": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "別名清單（可選，省略等同空 list）",
                },
                "alias": {
                    "type": "string",
                    "description": "單一別名（新增或刪除 alias 時使用）",
                },
            },
            "required": [],
        },
        "output_schema": {
            "success": "boolean",
            "group": "TagAliasGroup — 建立或新增 alias 成功後的最新 group 資料",
            "error": "string — 衝突或找不到時的錯誤訊息",
        },
        "side_effect": True,
        "confirmation_required": True,
        "retry_safe": False,
        "_example_template": (
            "curl -X POST -H 'Content-Type: application/json'"
            " -d '{{\"primary_name\":\"巨乳\",\"aliases\":[\"Big Tits\",\"おっぱい\"]}}'"
            " {base}/api/tag-aliases"
        ),
    },
    {
        "name": "tags_top",
        "description": (
            "列出 NFO tag 頻次排序（前 N 名），適合 AI 用 LLM 判斷跨語言同義詞候選後"
            " 呼叫 tag_alias_crud_write 建立 alias group。"
            " min_count=2（預設）過濾噪音單次 tag；total_unique_tags 不受 min_count 影響。"
            " 不含 user_tags（user_tags 為獨立欄位）。"
        ),
        "method": "GET",
        "path": "/api/tags/top",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "default": 100,
                    "minimum": 1,
                    "maximum": 500,
                    "description": "回傳筆數上限（預設 100，最大 500）",
                },
                "min_count": {
                    "type": "integer",
                    "default": 2,
                    "minimum": 1,
                    "description": "最低出現次數過濾（預設 2，過濾噪音；設 1 看全集合）",
                },
            },
            "required": [],
        },
        "output_schema": {
            "success": "boolean",
            "items": "[{tag: string, count: integer}] — 依 count 降序排列",
            "total_unique_tags": "integer — 全庫 unique tag 數（不受 min_count 影響）",
            "applied_min_count": "integer — 本次查詢使用的 min_count 值",
        },
        "side_effect": False,
        "confirmation_required": False,
        "retry_safe": True,
        "_example_template": "curl '{base}/api/tags/top?limit=50&min_count=2'",
    },
    {
        "name": "scraper_sources_list",
        "description": (
            "查詢使用者目前啟用、會用於自動搜尋（auto 模式實際 fan-out）的來源清單，"
            "協助 AI 判斷目前哪些來源 active。total_enabled 為已揭露的來源數。"
            "不揭露：停用（enabled=false）、Parts Bin（未 promote 的 metatube）、"
            "Manual-Only、BETA 來源都不會出現；也不揭露 metatube URL / token。"
            "不修改任何資料"
        ),
        "side_effect": False,
        "confirmation_required": False,
        "method": "GET",
        "path": "/api/scraper-sources",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "output_schema": {
            "sources": "array — 每筆 {id: string, display_name: string, type: string, enabled: boolean, order: integer, is_censored: boolean}，依 order 升冪",
            "total_enabled": "integer — 已揭露（實際會 fan-out）的啟用來源數",
        },
        "retry_safe": True,
        "_example_template": "curl '{base}/api/scraper-sources'",
    },
    {
        "name": "preview_actress_sources",
        "description": (
            "查詢女優的四個資料來源（xcity/wiki/graphis/gfriends），"
            "每個來源的結果分開回傳，不合併、不挑贏家，讓 AI 自己比對後決定"
            "要用哪個值。身分判斷優先於「查詢名字自己有沒有資料列」：若查詢的"
            "名字是某位已收藏女優的別名，一律先判定為別名（alias_of 會一併出現，"
            "值為正確的女優名），current 改回那位正確女優（primary）的資料——"
            "即使查詢的名字自己也意外存在一筆資料列（孤兒列），這條規則仍然"
            "優先，current 不會是那筆孤兒列的資料。只有查詢的名字不是任何已收藏"
            "女優的別名時，才退回看它自己：本身已收藏則 current 是它自己的資料，"
            "否則 current 為 null。各來源資料仍以查詢的名字（原字面）抓取，不受"
            "alias_of 影響。照片候選看本端點回應的 photo_candidates 欄位（不論"
            "是否已收藏都有效，未收藏的女優沒有獨立的照片候選端點可用）。"
            "完全不寫入：不收藏、不存檔、不下載照片。"
            "下一步：把預覽結果對照、自己上網補查後，呼叫 submit_actress 交回"
            "審過的版本。"
        ),
        "method": "POST",
        "path": "/api/actresses/preview",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "女優名（日文）"},
            },
            "required": ["name"],
        },
        "output_schema": {
            "name": "string — 查詢的女優名",
            "sources": (
                "{xcity, wiki, graphis, gfriends} — 各來源各自的原始欄位 dict，"
                "查無/下架/例外時該來源為 null，彼此獨立不合併"
            ),
            "current": (
                "Actress|null — 查詢名字已收藏時是它自己的資料；查詢名字是某已收藏"
                "女優的別名時（見 alias_of）改回那位正確女優（primary）的資料；"
                "兩者皆非則為 null"
            ),
            "photo_candidates": "[{source, url}] — 各來源可選照片，皆無照片時為空陣列",
            "alias_of": "string（可選）— 只有查詢名字是某已收藏女優的別名時才出現，值為正確的女優名；此時 current 已改回這位正確女優的資料",
        },
        "side_effect": False,
        "confirmation_required": False,
        "retry_safe": True,
        "_example_template": (
            "curl -X POST '{base}/api/actresses/preview' "
            "-H 'Content-Type: application/json' "
            "-d '{{\"name\": \"三上悠亜\"}}'"
        ),
    },
    {
        "name": "submit_actress",
        "description": (
            "提交審過的女優資料，寫入片庫。⚠️ 會覆蓋該女優既有的對應欄位"
            "（沒帶的欄位不動、帶空值會清空該欄位）；若同時提交 photo，會覆蓋"
            "現有照片並重設對焦位置；若這位女優尚未收藏，會直接建立收藏"
            "（不會走自動抓取，寫進去的就是提交的內容）。"
            "tags 等清單型欄位是整份取代，不是加一個/刪一個——要新增/刪除"
            "先呼叫 preview_actress_sources 或既有查詢端點讀現值，在清單上改，"
            "再整份交回。"
            "不可寫的內部欄位（帶了就 400，不靜默忽略）："
            "photo_source / primary_text_source / auto_focal / crop_mode / "
            "photo_fp_path / photo_fp_mtime_ns / photo_fp_size / aliases / "
            "name / created_at / updated_at。"
            "別名不在這條流程裡——要新增/刪除別名，走既有的 "
            "POST /api/actress-aliases/{name}/alias。"
            "身分守衛：提交的名字若是某位已收藏女優的別名，一律擋下並告知"
            "正確名字，不會靜默轉向到別人身上。"
            "photo.source 只能是 graphis/gfriends/wiki/xcity/local_crop 五選一。"
            "graphis/gfriends/wiki/xcity（雲端來源）：photo.url 必填，且必須是該"
            "來源既有白名單允許的 host，不合法會 400；若圖片來自這四個網站以外，"
            "請改用 upload_actress_photo 端點自行下載後上傳，不要嘗試把任意網址"
            "塞進 photo.url（會被拒絕）。local_crop：photo.video_path 必填"
            "（該片必須已經在你的片庫裡，file:/// URI），photo.crop_spec 選填"
            "（預設 \"v1\"），此分支不使用 photo.url。"
            "提交前的欄位驗證失敗一律回 400，body 為 {\"detail\": \"<單一錯誤訊息字串>\"}"
            "（保留欄位/未知欄位/型別或範圍錯誤/別名擋下時 detail 會點名正確名字），此時片庫零寫入；"
            "照片處理階段文字欄位（及新建立的收藏）是否還原採保守語義，僅限以下五種"
            "「確定尚未觸碰任何照片檔案」的驗證失敗才會還原：不支援的照片來源、缺少"
            "照片網址、照片網址不合法（皆 400）、local_crop 缺少影片路徑（400）、"
            "找不到對應的影片或封面（404）——原照片的對焦設定仍可能已被清除、需要"
            "重新調整。除此之外的照片失敗——下載失敗、裁切失敗、寫檔失敗、"
            "photo_source 持久化失敗、照片路徑重新解析失敗，或任何未預期例外——"
            "一律回 500 且**不會還原**：這些失敗都發生在文字欄位成功寫入之後，"
            "本次提交的文字已保留生效；只有照片是否真的換成功狀態不明，請以"
            "GET /api/actresses/photo/{name} 確認實際圖片後，再決定是否只重送"
            "photo 欄位補一次照片，不要重送整份文字。文字欄位另可看"
            "GET /api/actresses/{name} 核對（此時女優資料裡的照片來源欄位可能"
            "仍是舊值，不代表照片檔案本身沒換）。以上照片相關錯誤"
            "body 皆為 {\"error\": ...}。另外，照片安裝成功後、伺服器重新讀取最新"
            "資料準備回應這一步若失敗，回 500 {\"detail\": \"操作失敗\"}（文字與照片皆"
            "不還原，因為安裝本身已經成功，只是回應組裝失敗）；成功時回 {\"success\": "
            "true, \"actress\": <完整女優資料，與 GET /api/actresses/{name} 相同形狀>}。"
        ),
        "method": "POST",
        "path": "/api/actresses/{name}",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "女優名稱（URL path parameter，需 URL encode，前後空白會自動去除）。若是既有收藏女優的別名會被 400 擋下，不會靜默轉向"},
                "name_en": {"type": "string", "description": "英文名；沒帶=不動，帶空字串=清空"},
                "birth": {"type": "string", "description": "生日，需符合 YYYY-MM-DD 且是合法曆法日期；沒帶=不動，空字串=清空"},
                "height": {"type": "string", "description": "身高，請傳字串，例如 \"158cm\" 或 \"158\"，正規化為 \"{n}cm\"，需落在 100~220"},
                "cup": {"type": "string", "description": "罩杯，單一大寫字母（如 \"D\"），不支援雙字母記法"},
                "hometown": {"type": "string", "description": "出身地"},
                "hobby": {"type": "string", "description": "興趣"},
                "agency": {"type": "string", "description": "所屬事務所"},
                "debut_work": {"type": "string", "description": "出道作品"},
                "nickname": {"type": "string", "description": "暱稱"},
                "blog_url": {"type": "string", "description": "部落格網址"},
                "official_url": {"type": "string", "description": "官方網站網址"},
                "bust": {"type": "integer", "description": "胸圍 cm，也接受數字字串如 \"83\"，需落在 50~150"},
                "waist": {"type": "integer", "description": "腰圍 cm，也接受數字字串，需落在 40~120"},
                "hip": {"type": "integer", "description": "臀圍 cm，也接受數字字串，需落在 50~150"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "標籤，整份取代（不是加一個/刪一個）"},
                "photo": {
                    "type": "object",
                    "description": (
                        "不帶此欄位或帶 null=照片與對焦位置都不動。帶了非 null 物件才換照片，"
                        "對焦依既有換照片規則處理。source 為雲端來源時 url 必填且需過白名單；"
                        "source 為 local_crop 時 video_path 必填、不使用 url；"
                        "白名單外的圖片改用 upload_actress_photo。"
                    ),
                    "properties": {
                        "source": {
                            "type": "string",
                            "enum": ["graphis", "gfriends", "wiki", "xcity", "local_crop"],
                        },
                        "url": {"type": "string", "description": "source 為 graphis/gfriends/wiki/xcity 時必填，且必須是該來源既有白名單允許的 host；source=local_crop 時不使用"},
                        "video_path": {"type": "string", "description": "source=local_crop 時必填，該影片必須已存在於你的片庫裡（file:/// URI）"},
                        "crop_spec": {"type": "string", "description": "source=local_crop 時可選，預設 \"v1\""},
                    },
                },
            },
            "required": ["name"],
        },
        "output_schema": {
            "success": "boolean",
            "actress": "Actress — 與 GET /api/actresses/{name} 相同的完整女優資料（primary_text_source 已被伺服器覆寫為 \"ai\"）",
        },
        "side_effect": True,
        "confirmation_required": True,
        "idempotent": False,
        "retry_safe": False,
        "_example_template": (
            "curl -X POST '{base}/api/actresses/%E4%B8%89%E4%B8%8A%E6%82%A0%E4%BA%9C' "
            "-H 'Content-Type: application/json' "
            "-d '{{\"height\": \"158cm\"}}'"
        ),
    },
    {
        "name": "upload_actress_photo",
        "description": (
            "上傳任意來源的圖片檔案取代女優照片（multipart，非 URL）。"
            "⚠️ 會覆蓋現有照片並重設對焦位置，不可復原（舊檔無備份）。"
            "AI 從 graphis/gfriends/wiki/xcity 白名單以外的網站找到想要的照片時，"
            "走這條路：自己下載該圖片的 bytes，再用本端點以 multipart/form-data "
            "上傳，不要嘗試把該網址交給 submit_actress/set_actress_photo 的 url "
            "欄位（會被白名單拒絕）。上限：檔案 10MB、像素 50M；格式需為 "
            "JPEG/PNG/WEBP/GIF 之一。這位女優必須已經收藏（先呼叫 submit_actress "
            "或既有收藏功能），未收藏會回 404，本端點不會替你自動建立收藏；"
            "若這個名字是某位已收藏女優的別名，一律回 400 並告知正確名字，不會"
            "靜默轉向到別人身上。"
        ),
        "method": "POST",
        "path": "/api/actresses/{name}/photo/upload",
        "input_schema": {
            "type": "object",
            "description": "multipart/form-data body（非 JSON），欄位如下",
            "properties": {
                "name": {"type": "string", "description": "女優名稱（URL path parameter，需 URL encode）"},
                "file": {"type": "string", "format": "binary", "description": "圖片檔案（multipart form field，JPEG/PNG/WEBP/GIF，≤10MB，≤50M 像素）"},
            },
            "required": ["name", "file"],
        },
        "output_schema": {
            "photo_url": "string — 新照片路徑，含 ?v={mtime_ns}-{size} cache-bust query",
            "photo_source": "string — 固定為 \"upload\"",
            "auto_focal": "string — 固定為空字串（上傳不跑自動偵測，不寫入焦點）",
            "crop_mode": "string — 固定為 \"auto\"",
        },
        "side_effect": True,
        "confirmation_required": True,
        "idempotent": False,
        "retry_safe": False,
        "_example_template": (
            "curl -X POST '{base}/api/actresses/%E4%B8%89%E4%B8%8A%E6%82%A0%E4%BA%9C/photo/upload' "
            "-F 'file=@photo.jpg'"
        ),
    },
]


def _build_tools(base: str, curl_auth: str = "") -> list[dict]:
    """CD-114b-8: `curl_auth` is inserted right after the literal `curl `
    prefix of every tool's rendered example. All 39 `_example_template`
    values are confirmed to start with `curl ` (TASK-114b-T5 verification) —
    if `curl_auth` is non-empty, `"curl "` becomes
    `'curl -H "Authorization: Bearer $OPENAVER_TOKEN" '` and the rest of the
    template follows unchanged (`curl -X POST ...` becomes
    `curl -H "..." -X POST ...` — still valid curl syntax, flag order does
    not matter to curl).

    If a future `_example_template` does NOT start with `curl ` (e.g. a
    40th tool that is not curl-shaped), this function deliberately leaves
    it untouched rather than raising: a hard assertion here would 500 the
    whole capabilities endpoint for every caller over one tool missing a
    prefix. The gap is instead caught by the property test in
    tests/integration/test_capabilities_auth.py, which walks the full
    response and names the offending tool by its `name` field.
    """
    tools = []
    for t in _TOOLS:
        tool = copy.deepcopy(t)
        template = tool.pop("_example_template", "")
        example = template.format(base=base)
        if curl_auth and example.startswith("curl "):
            example = "curl " + curl_auth + example[len("curl "):]
        tool["example"] = example
        tools.append(tool)
    return tools


def _capabilities_auth_fields(
    base: str, auth_enabled: bool
) -> tuple[str, object, dict]:
    """CD-114b-8 pure string fields derived from auth_enabled.

    Extracted so get_capabilities stays under py_function_size_lint's 200-line
    cap (card inlined this block and would push the handler to 236 lines).
    Zero I/O — caller must resolve auth_enabled via snapshot()/load_snapshot
    on the route handler itself so BE-ASYNC-01 still covers load_snapshot.
    """
    # CD-114b-8: single variable, applied right after the literal "curl "
    # prefix at every directly-executable curl call site. Trailing space is
    # deliberate — it separates the header flag from whatever curl flag
    # follows "curl " at each call site.
    curl_auth = '-H "Authorization: Bearer $OPENAVER_TOKEN" ' if auth_enabled else ""

    network_auth: object = "none"
    if auth_enabled:
        network_auth = {
            "type": "bearer",
            "header": "Authorization: Bearer <token>",
            "note": "token 請在本機（loopback）開啟 Help 頁（/help）取得；GET /api/health 不需要認證",
        }

    ps_headers = ' -Headers @{Authorization = "Bearer $OPENAVER_TOKEN"}' if auth_enabled else ""

    agent_instructions = {
        "fetch_method": "curl",
        "fetch_note": "必須走 shell HTTP 工具（POSIX 用 curl，Windows 用 curl.exe 或 Invoke-RestMethod）存取此服務。禁止使用瀏覽器 fetch()、AI 內建的 WebFetch / web_search 等 HTTP 工具，因其常經由外部 proxy 或沙箱網路，無法可靠連到 localhost / LAN。",
        "example": f"curl -s {curl_auth}{base}/api/capabilities",
        "shell_compat": {
            "preferred": {
                "posix": "curl",
                "windows": "curl.exe",
            },
            "alternative_windows": (
                f"Invoke-RestMethod -Uri '{base}/api/batch-search' -Method POST"
                f" -ContentType 'application/json'{ps_headers} -Body '{{\"numbers\":[\"SONE-205\"]}}'"
            ),
            "windows_gotcha": "PowerShell 內 curl 是 Invoke-WebRequest 的 alias，建議顯式呼叫 curl.exe；POST JSON body 引號易與 PS 字串規則打架，改用 Invoke-RestMethod -Body 較穩。",
            "forbidden": ["fetch()", "WebFetch", "web_search"],
            "forbidden_reason": "Browser-sandbox or external-proxy routing cannot reliably reach localhost or LAN services.",
        },
    }
    if auth_enabled:
        agent_instructions["token_setup"] = (
            "token 請先設成環境變數再執行上面的指令 —— "
            "POSIX（bash/zsh）：export OPENAVER_TOKEN=\"<token>\"； "
            "PowerShell：$env:OPENAVER_TOKEN = \"<token>\"； "
            "<token> 請在本機（loopback）開啟 Help 頁（/help）取得。"
        )
    return curl_auth, network_auth, agent_instructions


def _build_image_display(curl_auth: str) -> dict:
    """`GET /api/capabilities` 的 image_display 區塊。

    從 `get_capabilities()` 抽出來的原因是函式規模棘輪（`scripts/py_function_size_lint.py`，
    上限 200 行）——加了 metatube preview_* 的食譜之後剛好推爆。抽法照該檔既有的
    `_build_tools(base, curl_auth)` 模式，內容逐字元不變。
    """
    return {
        "description": "如何在對話流程中向用戶展示搜尋結果的封面 / 劇照圖片",
        "problem": "搜尋結果的 cover 和 sample_images 是遠端 URL。AI agent 直接 curl 遠端 URL 會被 Cloudflare / 防盜鏈擋掉（回傳 HTML 而非圖片）。",
        "solution": "透過 /api/proxy-image 下載圖片到本地，再依 agent 形態用本地絕對路徑嵌入。",
        "steps": [
            "1. 搜尋取得 cover / sample_images URL",
            "1b. 若同筆結果有 preview_cover_url / preview_sample_images（metatube 來源），"
            "改用 preview_cover_url || cover、preview_sample_images[i] || sample_images[i]",
            f"2. curl {curl_auth}-o <local_path> '<base_url>/api/proxy-image?url=<remote_url>' 下載到本地",
            "3. 依 agent 形態嵌入（見 agents 區塊）：對話氣泡內嵌 / artifact 面板 / 純路徑文字",
        ],
        "rules": [
            "禁止直接 curl 遠端圖片 URL — 一定會被擋",
            "一律透過 /api/proxy-image 代理下載",
            "metatube 來源優先用 preview_* 欄位：/api/proxy-image 的網域白名單只收錄常見圖床，"
            "metatube 接的冷門 provider 圖床不在名單內會回 403。preview_* 走使用者自己的 "
            "metatube 伺服器（在動態白名單內），是同一張圖的可達副本。空字串代表該格沒有代理，"
            "退回原始網址即可（用 || 不要用 ??）",
            "下載到本地後用絕對路徑顯示（不要用遠端 URL 嵌入）",
        ],
        "agents": {
            "codex_app": {
                "description": "Codex App（OpenAI 桌面應用）— 對話氣泡可直接內嵌圖片",
                "mechanism": "inline_markdown",
                "temp_dir": "C:/Codex/tmp/openaver-images/",
                "display_format": "![SONE-205 cover](C:/Codex/tmp/openaver-images/SONE-205-cover.jpg)",
                "naming": "<number>-cover.jpg 或 <number>-sample-<N>.jpg",
                "note": "路徑不可含空格。OpenAver 的番號與檔名不含空格，可安全使用。",
            },
            "antigravity": {
                "description": "Google Antigravity 2.0（桌面 app）— 對話氣泡不渲染圖片，必須透過右側 artifact 面板（Markdown 富文本）嵌入",
                "mechanism": "artifact_markdown",
                "artifact_dir_hint": "<appDataDir>/brain/<conversation-id>/  例：C:/Users/<user>/.gemini/antigravity/brain/<conv-id>/。實際路徑請從 runtime 取得當前對話的 artifact 目錄，不要寫死 conv-id",
                "display_format": "![SONE-205 cover](<artifact_dir>/SONE-205-cover.jpg)",
                "rules": [
                    "圖片下載到 artifact 目錄內（或其子目錄）才能被 artifact 引用",
                    "Markdown 路徑用絕對路徑 + 正斜線（Windows 也用 / 不用 \\）",
                    "用 ![]() 不能用 []()，前綴 ! 才會渲染為圖片",
                    "圖片不在對話氣泡顯示，而是右側 artifact 面板",
                ],
                "carousel_syntax": "多張圖可用 carousel 區塊：````carousel 開頭 + 每張 ![](path) 之間用 <!-- slide --> 分隔 + ```` 結尾（實測可用，官方文件未列）",
            },
            "terminal_cli": {
                "description": "終端機型 agent（Claude Code / Codex CLI / Gemini CLI 等）— 終端不渲染圖片",
                "mechanism": "path_text",
                "display_format": "下載完成後在訊息中提供絕對路徑供用戶手動開啟（檔案總管 / Preview / Quick Look 等）",
                "note": "若 agent host 環境支援開檔指令，可主動呼叫 open / xdg-open / start 等",
            },
        },
    }


@router.get("/capabilities")
async def get_capabilities(request: Request):
    base = str(request.base_url).rstrip("/")

    # CD-114b-5 / CD-114b-8: zero-I/O read of the auth snapshot on the hot
    # path (BE-ASYNC-01); only fall back to the blocking loader when the
    # in-process cache has never been warmed (cold start). `load_snapshot`
    # must stay in tests/integration/test_async_offload_guard.py's
    # `BLOCKING_FUNC_NAMES` so a future regression that calls it bare
    # (outside `asyncio.to_thread`) is caught by that guard.
    auth_snap = snapshot()
    if auth_snap is None:
        auth_snap = await asyncio.to_thread(load_snapshot)
    curl_auth, network_auth, agent_instructions = _capabilities_auth_fields(
        base, auth_snap.enabled
    )

    return {
        "schema_version": "v1",
        "name": "OpenAver",
        "version": __version__,
        "base_url": base,
        "description": "影片元數據管理工具 — 搜尋、刮削、整理、瀏覽",
        "skill_setup": {
            "description": "將以下內容加入你的 AI 自訂指令 / Skill / System Prompt，讓 AI 學會使用 OpenAver",
            "template": f"你可以使用 OpenAver 影片元數據管理工具。使用前先 GET {base}/api/capabilities 查看可用操作和使用範例。",
            "hint": f"建議將此服務註冊為 AI skill（如 SKILL.md），存入 `curl -s {curl_auth}{base}/api/capabilities` 指令，後續啟動自動發現。",
        },
        "quick_check": {
            "description": "確認服務是否運行中",
            "method": "GET",
            "path": "/api/health",
        },
        "network": {
            "scope": "lan",
            "auth": network_auth,
            "note": "本地/區網服務，不上公網",
        },
        "agent_instructions": agent_instructions,
        "image_display": _build_image_display(curl_auth),
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
        "tools": _build_tools(base, curl_auth),
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
                    "2. 若 URL 是 ptt.cc → curl -b 'over18=1' 取得 HTML → 從 div#main-content 解析內文（PTT 年齡驗證是 client-side JS，加 cookie 即可繞過）",
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
                    # 第三個「性質測試看不到」的格子（前兩個是 PowerShell 與
                    # image_display.steps[1]）：字串以步驟編號 "2. " 開頭，
                    # `.startswith("curl ")` 的過濾器掃不到它，但它照樣是一行
                    # agent 會直接照抄執行的指令——漏掉就是一次 401。
                    f"2. curl {curl_auth}-o /tmp/SONE-205-cover.jpg '<base_url>/api/proxy-image?url=<cover_url>' 下載到本地",
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
            {
                "scenario": "逐欄位選來源 + AI 改寫後提交",
                "description": "查兩個來源、挑欄位、翻譯標題，交回審過的結果（不是把查到的原樣送回，是組合＋改寫後的版本）",
                "steps": [
                    "1. GET /api/search?q=SONE-205&mode=exact&source=dmm 取得 dmm 版（封面/文字）",
                    "2. GET /api/search?q=SONE-205&mode=exact&source=javdb 取得 javdb 版（文字）",
                    "3. AI 自己決定：封面用 dmm 的 url，標題翻成中文，其餘文字用 javdb 的——組出一份新的 metadata dict（不是直接轉傳步驟 1/2 的原始回應）",
                    "4. POST /api/enrich-single {file_path, number, mode: 'refresh_full', overwrite_existing: true, metadata: {...}, write_cover: true}",
                ],
                "confirmation_rule": "本流程掛在免確認條目上，AI 可在無人值守排程中執行；分集片要逐段各自提交，對每一段各自重複步驟 3-4",
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
