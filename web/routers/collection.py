"""
collection.py — POST /api/collection/sql read-only SQL 查詢端點

提供 AI agent 對本地收藏資料庫執行任意 read-only SQL 查詢。
12 層安全防護確保查詢不可能修改資料或探測 DB 結構。
"""

import json
import re
import sqlite3
from typing import Any, List, Literal, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.database import get_connection, get_db_path
from core.logger import get_logger
from core.scraper import is_number_format

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
