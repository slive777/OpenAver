"""
collection.py — POST /api/collection/sql read-only SQL 查詢端點 + /api/user-tags CRUD

提供 AI agent 對本地收藏資料庫執行任意 read-only SQL 查詢。
12 層安全防護確保查詢不可能修改資料或探測 DB 結構。

同時提供 user_tags_router（prefix=/api）實作 POST/GET /api/user-tags。
"""

import json
import re
import sqlite3
from pathlib import Path
from typing import Any, List, Literal, Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.config import load_config
from core.database import Video, VideoRepository, get_connection, get_db_path
from core.logger import get_logger
from core.nfo_updater import update_nfo_user_tags
from core.path_utils import CURRENT_ENV, to_file_uri, uri_to_fs_path
from core.scraper import extract_number, is_number_format

logger = get_logger(__name__)

router = APIRouter(prefix="/api/collection", tags=["collection"])

# 允許的表名白名單
ALLOWED_TABLES = {"videos", "actress_aliases"}

# ── Analysis 常數 ─────────────────────────────────────────────────────────────

CORRUPTION_RULES = [
    {"name": "digit_prefix", "pattern": r"^(\d+)([A-Z]{2,}-\d+)$",  "fix_group": 2},
    {"name": "TK_prefix",    "pattern": r"^TK([A-Z]{2,}-\d+)$",     "fix_group": 1},
    {"name": "K9_prefix",    "pattern": r"^K9([A-Z]{2,}-\d+)$",     "fix_group": 1},
    {"name": "R_prefix",     "pattern": r"^R-([A-Z]{2,}-\d+)$",     "fix_group": 1},
]

WESTERN_PATH_PATTERNS = ["西洋", "《03》", "《05》"]

_AVAILABLE_GROUPS = [
    "no_nfo", "corrupted_numbers", "japanese_tags",
    "missing_core", "missing_secondary",
]


# ── Analysis 輔助函數 ─────────────────────────────────────────────────────────

def _is_western(path: str) -> bool:
    """依路徑中的關鍵字判斷是否為西洋片"""
    return any(p in path for p in WESTERN_PATH_PATTERNS)


def _is_corrupted_number(number) -> bool:
    """判斷番號是否符合任一 corruption pattern（None-safe）"""
    if number is None:
        return False
    upper = number.upper()
    return any(re.match(rule["pattern"], upper) for rule in CORRUPTION_RULES)


def _get_fixed_number(number) -> Optional[str]:
    """
    遍歷 CORRUPTION_RULES，找第一個 match，回傳 fix_group 對應的 capture group。
    不 match → 回傳 None。供 preview 和 apply 共用。
    """
    if number is None:
        return None
    upper = number.upper()
    for rule in CORRUPTION_RULES:
        m = re.match(rule["pattern"], upper)
        if m:
            return m.group(rule["fix_group"])
    return None


def _has_japanese_tags(tags_json) -> bool:
    """判斷 tags JSON 字串中是否含有假名字元（None-safe，非法 JSON 返回 False）"""
    if not tags_json:
        return False
    try:
        tags = json.loads(tags_json)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(tags, list):
        return False
    return any(
        bool(re.search(r"[\u3040-\u30ff]", tag))
        for tag in tags
        if isinstance(tag, str)
    )


# ── Request / Response Model ──────────────────────────────────────────────────

class SqlRequest(BaseModel):
    sql: str = Field(..., min_length=1)
    limit: int = Field(default=500, ge=1, le=500)


class AnalysisGroupRequest(BaseModel):
    group: Literal[
        "no_nfo", "corrupted_numbers", "japanese_tags",
        "missing_core", "missing_secondary"
    ]
    limit: int = Field(default=50, ge=1, le=200)
    exclude_western: bool = True


class FixNumbersPreviewRequest(BaseModel):
    rules: List[str] = []


class FixNumbersApplyRequest(BaseModel):
    ids: List[int]


# ── SQL 驗證邏輯（可獨立測試）────────────────────────────────────────────────

def _strip_string_literals(sql: str) -> str:
    """移除單引號字串內容（含 '' 轉義），保留結構"""
    return re.sub(r"'(?:''|[^'])*'", "''", sql)


def validate_sql(sql: str) -> Optional[str]:
    """
    驗證 SQL 字串是否符合安全規範（層 1–7）。

    Returns:
        None  — 通過所有檢查
        str   — 錯誤訊息（應回傳給 client）
    """
    # 層 1：只允許 SELECT 開頭
    if not sql.strip().upper().startswith("SELECT"):
        return "只允許 SELECT 語句"

    # 層 2：禁止 ; （多語句攻擊）
    if ";" in sql:
        return "SQL 語句不合法"

    # 層 3：禁止 PRAGMA（case-insensitive）
    if re.search(r"\bPRAGMA\b", sql, re.IGNORECASE):
        return "SQL 語句不合法"

    # 層 4：禁止 ATTACH / DETACH
    if re.search(r"\b(ATTACH|DETACH)\b", sql, re.IGNORECASE):
        return "SQL 語句不合法"

    # 層 5：禁止 sqlite_master / sqlite_schema
    if re.search(r"\bsqlite_(master|schema)\b", sql, re.IGNORECASE):
        return "SQL 語句不合法"

    # 層 6：禁止 load_extension
    if re.search(r"\bload_extension\b", sql, re.IGNORECASE):
        return "SQL 語句不合法"

    # 層 6.5：禁止引號包裹的識別符（防繞過表白名單）
    sql_no_strings = _strip_string_literals(sql)
    if re.search(r'"[^"]+"|`[^`]+`|\[[^\]]+\]', sql_no_strings):
        return "SQL 語句不合法"

    # 層 7：表白名單
    # 提取所有表名：FROM/JOIN 後的第一個識別符，以及 FROM 子句中逗號分隔的後續表名。
    # 逗號掃描從每個 FROM 關鍵字位置往後進行，避免誤抓 SELECT 欄位列表中的逗號。
    identifiers: list = []
    for m in re.finditer(r"\b(FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)", sql, re.IGNORECASE):
        keyword = m.group(1).upper()
        identifiers.append(m.group(2))

        if keyword == "FROM":
            # 掃描 FROM 子句中逗號分隔的後續表名（跳過可選 alias）
            pos = m.end()
            while True:
                comma_match = re.match(
                    r"\s*(?:[a-zA-Z_][a-zA-Z0-9_]*)?\s*,\s*([a-zA-Z_][a-zA-Z0-9_]*)",
                    sql[pos:],
                    re.IGNORECASE,
                )
                if not comma_match:
                    break
                identifiers.append(comma_match.group(1))
                pos += comma_match.end()

    for ident in identifiers:
        # 判斷識別符後是否緊跟 `(`（含可能的空格）→ TVF，略過
        if re.search(r"\b" + re.escape(ident) + r"\s*\(", sql, re.IGNORECASE):
            continue  # TVF，略過
        # 否則必須在白名單
        if ident.lower() not in ALLOWED_TABLES:
            return "查詢包含不允許的資料表"

    return None  # 全部通過


# ── 端點實作 ──────────────────────────────────────────────────────────────────

@router.post("/sql")
def collection_sql(request: SqlRequest) -> dict:
    """
    執行 read-only SQL 查詢。

    12 層安全防護：
    - 層 1–7：字串層級 pre-check（validate_sql）
    - 層 8：read-only connection（mode=ro + PRAGMA query_only + busy_timeout）
    - 層 9：結果限制 min(limit, 500)
    - 層 10：timeout 由 busy_timeout PRAGMA 控制
    - 層 11：columns 從 cursor.description 提取
    - 層 12：錯誤細節遮蔽（不暴露 sqlite 原始訊息）
    """
    _ERR_EMPTY = {"success": False, "error": "", "columns": [], "rows": [], "count": 0}

    def _err(msg: str) -> dict:
        return {**_ERR_EMPTY, "error": msg}

    # 層 1–7：字串層級驗證（回傳 HTTP 400）
    validation_error = validate_sql(request.sql)
    if validation_error is not None:
        return JSONResponse(
            status_code=400,
            content=_err(validation_error),
        )

    # 層 8：確認 DB 存在
    db_path = get_db_path()
    if not db_path.exists():
        return _err("資料庫尚未初始化")

    # 層 9：結果限制
    effective_limit = min(request.limit, 500)

    conn = None
    try:
        # 層 8：read-only connection
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.execute("PRAGMA query_only = ON")    # belt-and-suspenders
        conn.execute("PRAGMA busy_timeout = 5000")  # 5 秒 timeout

        cursor = conn.cursor()
        cursor.execute(request.sql)

        # 層 11：columns 從 cursor.description 提取
        columns: List[str] = [desc[0] for desc in cursor.description]

        # 層 9：fetchmany 限制筆數
        rows: List[List[Any]] = [list(row) for row in cursor.fetchmany(effective_limit)]

        return {
            "success": True,
            "columns": columns,
            "rows": rows,
            "count": len(rows),
        }

    except sqlite3.OperationalError as e:
        # 層 12：含 database is locked（timeout）+ 語法錯誤等
        logger.warning("[collection/sql] SQL 執行失敗: %s", e)
        return _err("SQL 執行失敗，請確認語法")

    except sqlite3.DatabaseError as e:
        logger.warning("[collection/sql] DB 錯誤: %s", e)
        return _err("SQL 執行失敗，請確認語法")

    except Exception as e:
        logger.error("[collection/sql] 非預期錯誤: %s", e)
        return _err("內部錯誤，請稍後再試")

    finally:
        if conn:
            conn.close()


# ── GET /api/collection/analysis ─────────────────────────────────────────────

@router.get("/analysis")
def collection_analysis() -> dict:
    """
    收藏庫 metadata 健康度診斷。

    回傳各欄位缺失數、空陣列數、異常番號、日文 tag 統計、NFO 狀態以及可用的 group 名稱。
    """
    db_path = get_db_path()
    if not db_path.exists():
        return {"success": False, "error": "資料庫尚未初始化"}

    conn = None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.execute("PRAGMA query_only = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        cur = conn.cursor()

        # 總筆數
        total_videos = cur.execute("SELECT COUNT(*) FROM videos").fetchone()[0]

        # missing_fields（NULL 或空字串）
        def _count_missing(col: str) -> int:
            return cur.execute(
                f"SELECT COUNT(*) FROM videos WHERE {col} IS NULL OR {col} = ''"
            ).fetchone()[0]

        missing_fields = {
            "title":          _count_missing("title"),
            "actresses":      _count_missing("actresses"),   # 只計 NULL/''，不含 '[]'
            "maker":          _count_missing("maker"),
            "tags":           _count_missing("tags"),
            "release_date":   _count_missing("release_date"),
            "cover_path":     _count_missing("cover_path"),
            "director":       _count_missing("director"),
            "label":          _count_missing("label"),
            "original_title": _count_missing("original_title"),
        }

        # empty_array_fields：LENGTH < 3（'[]' 長度為 2）
        def _count_empty_array(col: str) -> int:
            return cur.execute(
                f"SELECT COUNT(*) FROM videos WHERE COALESCE(LENGTH({col}), 0) < 3"
            ).fetchone()[0]

        empty_array_fields = {
            "actresses": _count_empty_array("actresses"),
            "tags":      _count_empty_array("tags"),
        }

        # corrupted_numbers：從 DB 全取 number，Python 端比對
        all_numbers = [
            row[0] for row in cur.execute("SELECT number FROM videos").fetchall()
        ]
        pattern_counts = {rule["name"]: 0 for rule in CORRUPTION_RULES}
        for num in all_numbers:
            if num is None:
                continue
            upper = num.upper()
            for rule in CORRUPTION_RULES:
                if re.match(rule["pattern"], upper):
                    pattern_counts[rule["name"]] += 1
        corrupted_total = sum(pattern_counts.values())
        corrupted_numbers = {
            "total": corrupted_total,
            "patterns": [
                {"name": rule["name"], "count": pattern_counts[rule["name"]]}
                for rule in CORRUPTION_RULES
            ],
        }

        # japanese_tags：從 DB 全取 tags，Python 端比對
        all_tags = [
            row[0] for row in cur.execute("SELECT tags FROM videos").fetchall()
        ]
        japanese_total = sum(1 for t in all_tags if _has_japanese_tags(t))
        japanese_tags = {"total": japanese_total}

        # nfo_status
        has_nfo = cur.execute(
            "SELECT COUNT(*) FROM videos WHERE nfo_mtime IS NOT NULL AND nfo_mtime > 0"
        ).fetchone()[0]
        missing_nfo = cur.execute(
            "SELECT COUNT(*) FROM videos WHERE nfo_mtime IS NULL OR nfo_mtime = 0"
        ).fetchone()[0]
        nfo_status = {"has_nfo": has_nfo, "missing_nfo": missing_nfo}

        return {
            "total_videos":      total_videos,
            "missing_fields":    missing_fields,
            "empty_array_fields": empty_array_fields,
            "corrupted_numbers": corrupted_numbers,
            "japanese_tags":     japanese_tags,
            "nfo_status":        nfo_status,
            "available_groups":  _AVAILABLE_GROUPS,
        }

    except Exception as e:
        logger.error("[collection/analysis] 非預期錯誤: %s", e)
        return {"success": False, "error": "內部錯誤，請稍後再試"}

    finally:
        if conn:
            conn.close()


# ── POST /api/collection/analysis/groups ─────────────────────────────────────

@router.post("/analysis/groups")
def collection_analysis_groups(request: AnalysisGroupRequest) -> dict:
    """
    依問題類型取得待修復影片清單（drill-down）。

    永遠從頭取 limit 筆，批次修復後再呼叫取下一批，直到 items 為空。
    """
    db_path = get_db_path()
    if not db_path.exists():
        return {"success": False, "error": "資料庫尚未初始化"}

    group = request.group
    limit = request.limit
    exclude_western = request.exclude_western

    conn = None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.execute("PRAGMA query_only = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        cur = conn.cursor()

        def _row_to_item(row) -> dict:
            id_, number, file_path, title, maker = row
            return {
                "id":        id_,
                "number":    number,
                "file_path": file_path,
                "title":     title,
                "maker":     maker,
            }

        items: List[dict] = []
        total = 0

        if group == "no_nfo":
            # SQL: nfo_mtime IS NULL OR nfo_mtime = 0
            # Python: is_number_format(number) 為 True
            rows = cur.execute(
                """SELECT id, number, path, title, maker FROM videos
                   WHERE nfo_mtime IS NULL OR nfo_mtime = 0""",
            ).fetchall()
            for row in rows:
                item = _row_to_item(row)
                if item["number"] and is_number_format(item["number"]):
                    if exclude_western and _is_western(item["file_path"] or ""):
                        continue
                    total += 1
                    if len(items) < limit:
                        items.append(item)

        elif group == "corrupted_numbers":
            rows = cur.execute(
                "SELECT id, number, path, title, maker FROM videos",
            ).fetchall()
            for row in rows:
                item = _row_to_item(row)
                if _is_corrupted_number(item["number"]):
                    if exclude_western and _is_western(item["file_path"] or ""):
                        continue
                    total += 1
                    if len(items) < limit:
                        items.append(item)

        elif group == "japanese_tags":
            rows = cur.execute(
                "SELECT id, number, path, title, maker, tags FROM videos",
            ).fetchall()
            for row in rows:
                id_, number, file_path, title, maker, tags = row
                if _has_japanese_tags(tags):
                    if exclude_western and _is_western(file_path or ""):
                        continue
                    total += 1
                    if len(items) < limit:
                        items.append({
                            "id":        id_,
                            "number":    number,
                            "file_path": file_path,
                            "title":     title,
                            "maker":     maker,
                        })

        elif group == "missing_core":
            rows = cur.execute(
                """SELECT id, number, path, title, maker FROM videos
                   WHERE (actresses IS NULL OR actresses = '' OR LENGTH(actresses) < 3)
                      OR (tags IS NULL OR tags = '' OR LENGTH(tags) < 3)
                      OR (release_date IS NULL OR release_date = '')""",
            ).fetchall()
            for row in rows:
                item = _row_to_item(row)
                if exclude_western and _is_western(item["file_path"] or ""):
                    continue
                total += 1
                if len(items) < limit:
                    items.append(item)

        elif group == "missing_secondary":
            rows = cur.execute(
                """SELECT id, number, path, title, maker FROM videos
                   WHERE (director IS NULL OR director = '')
                      OR (label IS NULL OR label = '')
                      OR (original_title IS NULL OR original_title = '')""",
            ).fetchall()
            for row in rows:
                item = _row_to_item(row)
                if exclude_western and _is_western(item["file_path"] or ""):
                    continue
                total += 1
                if len(items) < limit:
                    items.append(item)

        return {
            "group":           group,
            "total":           total,
            "limit":           limit,
            "exclude_western": exclude_western,
            "items":           items,
        }

    except Exception as e:
        logger.error("[collection/analysis/groups] 非預期錯誤: %s", e)
        return {"success": False, "error": "內部錯誤，請稍後再試"}

    finally:
        if conn:
            conn.close()


# ── POST /api/collection/fix-numbers/preview ─────────────────────────────────

@router.post("/fix-numbers/preview")
def fix_numbers_preview(request: FixNumbersPreviewRequest) -> dict:
    """
    預覽哪些番號符合 corruption 修正規則（read-only）。

    - rules 為空 → 套用全部 4 條規則
    - rules 含無效名稱 → HTTP 400
    - 回傳 {rules_applied, affected, total}
    """
    valid_names = {rule["name"] for rule in CORRUPTION_RULES}

    # 驗證 rules 名稱
    if request.rules:
        invalid = [r for r in request.rules if r not in valid_names]
        if invalid:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": f"無效的規則名稱：{invalid}。有效名稱：{sorted(valid_names)}",
                },
            )

    rules_to_apply = (
        CORRUPTION_RULES
        if not request.rules
        else [r for r in CORRUPTION_RULES if r["name"] in request.rules]
    )
    rules_applied = [r["name"] for r in rules_to_apply]

    db_path = get_db_path()
    if not db_path.exists():
        return {"success": False, "error": "資料庫尚未初始化"}

    conn = None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.execute("PRAGMA query_only = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        cur = conn.cursor()

        rows = cur.execute("SELECT id, number, path FROM videos").fetchall()

        affected = []
        for id_, number, path in rows:
            if number is None:
                continue
            upper = number.upper()
            for rule in rules_to_apply:
                m = re.match(rule["pattern"], upper)
                if m:
                    new_number = m.group(rule["fix_group"])
                    affected.append({
                        "id":         id_,
                        "old_number": number,
                        "new_number": new_number,
                        "rule":       rule["name"],
                        "path":       path,
                    })
                    break  # 取第一條符合的規則

        return {
            "rules_applied": rules_applied,
            "affected":      affected,
            "total":         len(affected),
        }

    except Exception as e:
        logger.error("[collection/fix-numbers/preview] 非預期錯誤: %s", e)
        return {"success": False, "error": "內部錯誤，請稍後再試"}

    finally:
        if conn:
            conn.close()


# ── POST /api/collection/fix-numbers/apply ───────────────────────────────────

@router.post("/fix-numbers/apply")
def fix_numbers_apply(request: FixNumbersApplyRequest) -> dict:
    """
    執行番號修正：對指定 ID 清單逐一重新驗證後執行 UPDATE。

    - ids 為空 → 直接回傳 {updated: 0, failed: 0}
    - 每個 ID 重新從 DB 讀取 number，仍符合規則才 UPDATE，否則計入 failed
    - 回傳 {updated, failed}
    """
    if not request.ids:
        return {"updated": 0, "failed": 0}

    db_path = get_db_path()
    if not db_path.exists():
        return {"success": False, "error": "資料庫尚未初始化"}

    updated = 0
    failed = 0
    conn = None
    try:
        conn = get_connection(db_path)
        cur = conn.cursor()

        for vid_id in request.ids:
            # 重新從 DB 讀取當前番號（防禦性驗證）
            row = cur.execute("SELECT number FROM videos WHERE id = ?", (vid_id,)).fetchone()
            if row is None:
                # ID 不存在
                failed += 1
                continue

            current_number = row[0]
            if not _is_corrupted_number(current_number):
                # 番號已不符合規則（被其他途徑修正，或原本就正常）
                failed += 1
                continue

            new_number = _get_fixed_number(current_number)
            if new_number is None:
                # 理論上不會到這裡（_is_corrupted_number 已確認），但防禦
                failed += 1
                continue

            cur.execute(
                "UPDATE videos SET number = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (new_number, vid_id),
            )
            updated += 1

        conn.commit()
        return {"updated": updated, "failed": failed}

    except Exception as e:
        logger.error("[collection/fix-numbers/apply] 非預期錯誤: %s", e)
        if conn:
            conn.rollback()
        return {"success": False, "error": "內部錯誤，請稍後再試"}

    finally:
        if conn:
            conn.close()


# ── /api/user-tags router ─────────────────────────────────────────────────────


def _resolve_user_tag_paths(input_path: str) -> tuple[str, str]:
    """同時取得 (canonical_uri, local_fs_path)。

    user_tags 端點需要兩個不同 view 的相同檔案：
    - **canonical_uri**: 透過 forward path_mappings 產生 DB key（與 scanner.py 一致）
    - **local_fs_path**: 當前環境**可實際存取**的 FS 路徑（用於 is_file/NFO read-write）

    這兩個 view 在 WSL 部署 + 自訂 path_mappings 的場景必須分開：
    - DB 存的是 UNC URI（forward map：/home/user/nas → //NAS-SERVER/share）
    - 但 WSL 程序實際開檔得用 /home/user/nas/... 這個 mount path
    - uri_to_fs_path() 不知道 path_mappings 反向映射，所以單獨用它無法取得本地路徑

    Returns:
        (canonical_uri, local_fs_path) — 任一為空字串時表示無效輸入
    """
    if not input_path:
        return ("", "")

    config = load_config()
    path_mappings = config.get("gallery", {}).get("path_mappings", {}) or {}

    try:
        fs_normalized = uri_to_fs_path(input_path)
    except Exception:
        return ("", "")

    canonical_uri = to_file_uri(fs_normalized, path_mappings)

    # local_fs_path：
    # - native path 輸入 → 直接用 fs_normalized（已 normalize 為當前 env 形式）
    # - URI 輸入 + WSL + 有 mappings → 反向映射 UNC → /home/user/nas/...
    # - 其他 → fs_normalized
    local_fs_path = fs_normalized
    if input_path.startswith("file://") and CURRENT_ENV == "wsl" and path_mappings:
        # 反向映射：fs_normalized 可能是 //NAS-SERVER/share/... 或 \\NAS-SERVER\share\...
        for local_prefix, win_prefix in path_mappings.items():
            win_fwd = win_prefix.replace("\\", "/")
            win_bs = win_prefix.replace("/", "\\")
            if fs_normalized.startswith(win_fwd):
                local_fs_path = local_prefix + fs_normalized[len(win_fwd):]
                break
            if fs_normalized.startswith(win_bs):
                local_fs_path = local_prefix + fs_normalized[len(win_bs):].replace("\\", "/")
                break

    return (canonical_uri, local_fs_path)


def _normalize_to_uri(p: str) -> str:
    """Backward-compat: 只取 canonical URI（不需要 local FS path 的呼叫端用）。"""
    canonical, _ = _resolve_user_tag_paths(p)
    return canonical


user_tags_router = APIRouter(prefix="/api", tags=["user-tags"])


class UserTagsRequest(BaseModel):
    file_path: str                # file:/// URI 格式（DB key）
    add: List[str] = Field(default_factory=list)
    remove: List[str] = Field(default_factory=list)


@user_tags_router.post("/user-tags")
def post_user_tags(request: UserTagsRequest) -> dict:
    """
    新增 / 移除 user tags。

    資料流：
    1. get_by_path(file_path) 查 DB
    2. 不存在 → 自動建立 stub 紀錄（從檔名解析 number），用於 Search 拖入但未掃描的檔案
    3. 合併 add / 移除 remove（去重，remove 優先）
    4. update_user_tags(file_path, merged) 更新 DB
    5. 重寫 NFO（失敗不阻擋回傳）
    6. 回傳 {success: true, user_tags: [...], nfo_updated: bool}
    """
    db_path = get_db_path()
    repo = VideoRepository(db_path)

    # 0. 解析路徑 — 同時取得 canonical URI（DB key）+ local FS path（filesystem 操作）
    if not request.file_path:
        return {"success": False, "error": "file_path 不可為空"}
    file_path, local_fs_path = _resolve_user_tag_paths(request.file_path)
    if not file_path:
        return {"success": False, "error": "file_path 格式無效"}

    # 1. 查 DB；不存在則自動建立 stub 紀錄
    video = repo.get_by_path(file_path)
    if video is None:
        if not local_fs_path or not Path(local_fs_path).is_file():
            return {"success": False, "error": "檔案不存在"}

        filename = Path(local_fs_path).name
        try:
            mtime = Path(local_fs_path).stat().st_mtime
            size_bytes = Path(local_fs_path).stat().st_size
        except Exception:
            mtime = 0.0
            size_bytes = 0

        stub = Video(
            path=file_path,
            number=extract_number(filename) or "",
            title=Path(local_fs_path).stem,
            mtime=mtime,
            size_bytes=size_bytes,
        )
        try:
            repo.upsert(stub)
        except Exception as e:
            logger.warning("[user-tags] 建立 stub 紀錄失敗: %s", e)
            return {"success": False, "error": "建立 DB 紀錄失敗"}

        video = repo.get_by_path(file_path)
        if video is None:
            return {"success": False, "error": "建立 DB 紀錄失敗"}

    # 2. 去重合併（remove 優先）
    existing = list(video.user_tags)
    # add：先加不重複的，同時對 add 本身去重
    seen_add = set()
    unique_add = []
    for t in request.add:
        if t not in seen_add:
            seen_add.add(t)
            unique_add.append(t)
    after_add = existing + [t for t in unique_add if t not in existing]
    # remove：移除指定 tags
    merged_tags = [t for t in after_add if t not in request.remove]

    # 3. 更新 DB
    updated = repo.update_user_tags(file_path, merged_tags)
    if not updated:
        return {"success": False, "error": "DB 更新失敗"}

    # 4. Surgical NFO update — 用 local_fs_path（WSL mapped mount 場景下與 DB key 不同）
    nfo_updated = False
    try:
        nfo_path = str(Path(local_fs_path).with_suffix(".nfo"))
        nfo_updated = update_nfo_user_tags(nfo_path, merged_tags)
    except Exception as e:
        logger.warning("[user-tags] NFO 寫入失敗（忽略）: %s", e)

    return {"success": True, "user_tags": merged_tags, "nfo_updated": nfo_updated}


@user_tags_router.get("/user-tags")
def get_user_tags(file_path: str = Query(...)) -> dict:
    """
    查詢指定 file_path 的現有 user_tags。

    接受 file:/// URI 或 native FS 路徑（自動正規化）。
    不存在時回傳 {user_tags: [], file_path: "..."}（HTTP 200）。
    """
    db_path = get_db_path()
    repo = VideoRepository(db_path)

    normalized = _normalize_to_uri(file_path)
    video = repo.get_by_path(normalized)
    if video is None:
        return {"user_tags": [], "file_path": normalized}

    return {"user_tags": video.user_tags, "file_path": normalized}
