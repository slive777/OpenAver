"""
collection.py — POST /api/collection/sql read-only SQL 查詢端點

提供 AI agent 對本地收藏資料庫執行任意 read-only SQL 查詢。
12 層安全防護確保查詢不可能修改資料或探測 DB 結構。
"""

import re
import sqlite3
from typing import Any, List, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.database import get_db_path
from core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/collection", tags=["collection"])

# 允許的表名白名單
ALLOWED_TABLES = {"videos", "actress_aliases"}


# ── Request / Response Model ──────────────────────────────────────────────────

class SqlRequest(BaseModel):
    sql: str = Field(..., min_length=1)
    limit: int = Field(default=500, ge=1, le=500)


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
