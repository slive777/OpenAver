"""
test_collection_sql.py — SQL 驗證邏輯 unit tests（全 mock，不碰 FS）

覆蓋 TASK-T5 的 41 個邊界條件。
"""

import pytest
from unittest.mock import patch, MagicMock
import re


# ── 匯入待測模組 ─────────────────────────────────────────────────────────────

def _get_validate():
    """延遲 import，讓 RED 階段的 import 錯誤只在測試函數中爆"""
    from web.routers.collection import validate_sql
    return validate_sql


def _get_router_module():
    from web.routers import collection
    return collection


# ── 層 1：SELECT 開頭 ─────────────────────────────────────────────────────────

class TestLayer1SelectOnly:
    def test_insert_rejected(self):
        validate = _get_validate()
        err = validate("INSERT INTO videos VALUES (...)")
        assert err is not None
        assert "只允許 SELECT" in err

    def test_update_rejected(self):
        validate = _get_validate()
        err = validate("UPDATE videos SET title='x'")
        assert err is not None
        assert "只允許 SELECT" in err

    def test_delete_rejected(self):
        validate = _get_validate()
        err = validate("DELETE FROM videos")
        assert err is not None
        assert "只允許 SELECT" in err

    def test_drop_rejected(self):
        validate = _get_validate()
        err = validate("DROP TABLE videos")
        assert err is not None
        assert "只允許 SELECT" in err

    def test_create_rejected(self):
        validate = _get_validate()
        err = validate("CREATE TABLE x AS SELECT 1")
        assert err is not None
        assert "只允許 SELECT" in err

    def test_with_cte_non_select_rejected(self):
        """WITH cte AS (SELECT ...) DELETE ... — CTE 包裝非 SELECT"""
        validate = _get_validate()
        err = validate("WITH cte AS (SELECT * FROM videos) DELETE FROM videos")
        assert err is not None
        assert "只允許 SELECT" in err

    def test_leading_whitespace_lowercase_select_allowed(self):
        """前置空白 + 小寫 select → 合法"""
        validate = _get_validate()
        # 會在層 7 因缺少白名單表而可能失敗，但層 1 應通過
        err = validate("  select * from videos")
        # 層 1 本身應通過；若回傳 error，不應是 "只允許 SELECT"
        if err is not None:
            assert "只允許 SELECT" not in err


# ── 層 2：禁止 ; ──────────────────────────────────────────────────────────────

class TestLayer2NoSemicolon:
    def test_semicolon_mid_rejected(self):
        validate = _get_validate()
        err = validate("SELECT * FROM videos; DROP TABLE videos")
        assert err is not None
        assert "不合法" in err

    def test_trailing_semicolon_rejected(self):
        validate = _get_validate()
        err = validate("SELECT * FROM videos;")
        assert err is not None
        assert "不合法" in err


# ── 層 3：PRAGMA 禁止 ─────────────────────────────────────────────────────────

class TestLayer3NoPragma:
    def test_pragma_uppercase_rejected(self):
        validate = _get_validate()
        err = validate("SELECT * FROM videos PRAGMA journal_mode")
        assert err is not None
        assert "不合法" in err

    def test_pragma_lowercase_rejected(self):
        validate = _get_validate()
        err = validate("pragma table_info(videos)")
        assert err is not None
        assert "只允許 SELECT" in err or "不合法" in err


# ── 層 4：ATTACH / DETACH 禁止 ───────────────────────────────────────────────

class TestLayer4NoAttachDetach:
    def test_attach_rejected(self):
        validate = _get_validate()
        err = validate("SELECT 1; ATTACH DATABASE '/etc/passwd' AS pw")
        # 層 2 (;) 會先擋住，但也測試到了
        assert err is not None

    def test_attach_without_semicolon_rejected(self):
        validate = _get_validate()
        # 讓層 4 觸發而非層 2
        err = validate("SELECT ATTACH DATABASE '/etc/passwd' AS pw FROM videos")
        assert err is not None
        assert "不合法" in err

    def test_detach_rejected(self):
        validate = _get_validate()
        err = validate("SELECT DETACH pw FROM videos")
        assert err is not None
        assert "不合法" in err


# ── 層 5：sqlite_master / sqlite_schema 禁止 ─────────────────────────────────

class TestLayer5NoSqliteMaster:
    def test_sqlite_master_rejected(self):
        validate = _get_validate()
        err = validate("SELECT * FROM sqlite_master")
        assert err is not None
        assert "不合法" in err

    def test_sqlite_schema_rejected(self):
        validate = _get_validate()
        err = validate("SELECT * FROM sqlite_schema WHERE type='table'")
        assert err is not None
        assert "不合法" in err


# ── 層 6：load_extension 禁止 ─────────────────────────────────────────────────

class TestLayer6NoLoadExtension:
    def test_load_extension_lowercase_rejected(self):
        validate = _get_validate()
        err = validate("SELECT load_extension('/usr/lib/evil.so')")
        assert err is not None
        assert "不合法" in err

    def test_load_extension_uppercase_rejected(self):
        validate = _get_validate()
        err = validate("SELECT LOAD_EXTENSION('/x')")
        assert err is not None
        assert "不合法" in err


# ── 層 7：表白名單 ────────────────────────────────────────────────────────────

class TestLayer7TableWhitelist:
    def test_videos_allowed(self):
        validate = _get_validate()
        err = validate("SELECT * FROM videos")
        assert err is None

    def test_actress_aliases_allowed(self):
        validate = _get_validate()
        err = validate("SELECT * FROM actress_aliases")
        assert err is None

    def test_unknown_table_rejected(self):
        validate = _get_validate()
        err = validate("SELECT * FROM users")
        assert err is not None
        assert "不允許的資料表" in err

    def test_join_unknown_table_rejected(self):
        validate = _get_validate()
        err = validate("SELECT v.* FROM videos v JOIN users u ON v.id = u.id")
        assert err is not None
        assert "不允許的資料表" in err

    def test_json_each_tvf_allowed(self):
        """json_each 是 TVF，應略過不視為表名"""
        validate = _get_validate()
        err = validate("SELECT value FROM videos, json_each(videos.actresses)")
        assert err is None

    def test_from_json_each_tvf_allowed(self):
        """FROM json_each(...) 形式"""
        validate = _get_validate()
        err = validate("SELECT value FROM json_each(videos.actresses)")
        assert err is None

    def test_cross_join_json_tree_allowed(self):
        """CROSS JOIN json_tree(...) 形式"""
        validate = _get_validate()
        err = validate("SELECT * FROM videos v CROSS JOIN json_tree(v.tags)")
        assert err is None

    def test_subquery_allowed(self):
        """子查詢無額外表名"""
        validate = _get_validate()
        err = validate("SELECT * FROM (SELECT * FROM videos)")
        assert err is None

    def test_subquery_bad_table_rejected(self):
        """子查詢含非白名單表"""
        validate = _get_validate()
        err = validate("SELECT * FROM (SELECT * FROM evil)")
        assert err is not None
        assert "不允許的資料表" in err

    def test_comma_join_disallowed_table_rejected(self):
        """逗號 JOIN 的第二個表名不在白名單 → 拒絕（F1 修正）"""
        validate = _get_validate()
        err = validate("SELECT * FROM videos, evil_table")
        assert err is not None
        assert "不允許的資料表" in err

    def test_comma_join_allowed_tables_passes(self):
        """逗號 JOIN 兩個白名單表 → 通過"""
        validate = _get_validate()
        err = validate("SELECT v.*, a.new_name FROM videos v, actress_aliases a")
        assert err is None

    def test_comma_join_tvf_passes(self):
        """逗號 JOIN TVF（json_each）→ 通過（TVF 略過）"""
        validate = _get_validate()
        err = validate("SELECT value FROM videos, json_each(videos.actresses) LIMIT 5")
        assert err is None


# ── 層 6.5：引號包裹識別符 ────────────────────────────────────────────────────

class TestQuotedIdentifiers:
    def test_double_quoted_table_rejected(self):
        """雙引號包裹的表名 → 拒絕（防繞過白名單）"""
        validate = _get_validate()
        err = validate('SELECT * FROM "sqlite_sequence"')
        assert err is not None
        assert "不合法" in err

    def test_backtick_quoted_table_rejected(self):
        """反引號包裹的表名 → 拒絕"""
        validate = _get_validate()
        err = validate("SELECT * FROM `secret_table`")
        assert err is not None
        assert "不合法" in err

    def test_bracket_quoted_table_rejected(self):
        """方括號包裹的表名 → 拒絕"""
        validate = _get_validate()
        err = validate("SELECT * FROM [videos]")
        assert err is not None
        assert "不合法" in err

    def test_single_quoted_string_still_works(self):
        """單引號字串值（WHERE LIKE）→ 不受影響"""
        validate = _get_validate()
        err = validate("SELECT * FROM videos WHERE actresses LIKE '%明日花%'")
        assert err is None


# ── 層 8：DB 不存在 ───────────────────────────────────────────────────────────

class TestLayer8DbNotExist:
    def test_db_not_exist_returns_error(self, tmp_path):
        """DB 檔案不存在 → 回傳 '資料庫尚未初始化'"""
        from web.routers.collection import collection_sql, SqlRequest

        non_existent = tmp_path / "no_such.db"
        req = SqlRequest(sql="SELECT * FROM videos")

        with patch("web.routers.collection.get_db_path", return_value=non_existent):
            result = collection_sql(req)

        assert result["success"] is False
        assert "資料庫尚未初始化" in result["error"]
        assert result["columns"] == []
        assert result["rows"] == []
        assert result["count"] == 0


# ── 層 9：結果限制 ────────────────────────────────────────────────────────────

class TestLayer9Limit:
    def _make_mock_conn(self, rows, columns=None):
        """建立 mock sqlite3 connection，回傳指定 rows"""
        conn = MagicMock()
        cursor = MagicMock()
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)
        cursor.description = [(c,) for c in (columns or ["id"])]
        cursor.fetchmany.return_value = rows[:500]  # simulate fetchmany
        conn.execute.return_value = cursor
        conn.cursor.return_value = cursor
        return conn, cursor

    def test_limit_100_respected(self, tmp_path):
        """limit=100 → effective_limit=100"""
        from web.routers.collection import collection_sql, SqlRequest
        from core.database import init_db

        db_path = tmp_path / "test.db"
        init_db(db_path)

        import sqlite3
        conn_real = sqlite3.connect(str(db_path))
        conn_real.close()

        req = SqlRequest(sql="SELECT * FROM videos", limit=100)

        called_with_limit = []

        def mock_connect(uri_str, uri=False):
            conn = MagicMock()
            cursor = MagicMock()
            cursor.description = [("id",)]
            cursor.fetchmany.side_effect = lambda n: (called_with_limit.append(n), [])[1]
            conn.execute.return_value = cursor
            conn.cursor.return_value = cursor
            conn.close = MagicMock()
            return conn

        with patch("web.routers.collection.get_db_path", return_value=db_path):
            with patch("sqlite3.connect", side_effect=mock_connect):
                result = collection_sql(req)

        assert called_with_limit and called_with_limit[-1] == 100

    def test_limit_999_rejected_by_pydantic(self):
        """limit=999 → Pydantic ValidationError（le=500）"""
        from pydantic import ValidationError
        from web.routers.collection import SqlRequest

        with pytest.raises(ValidationError):
            SqlRequest(sql="SELECT * FROM videos", limit=999)

    def test_limit_500_is_max_allowed(self, tmp_path):
        """limit=500 → 合法，fetchmany 以 500 呼叫"""
        from web.routers.collection import collection_sql, SqlRequest
        from core.database import init_db

        db_path = tmp_path / "test.db"
        init_db(db_path)

        req = SqlRequest(sql="SELECT * FROM videos", limit=500)

        called_with_limit = []

        def mock_connect(uri_str, uri=False):
            conn = MagicMock()
            cursor = MagicMock()
            cursor.description = [("id",)]
            cursor.fetchmany.side_effect = lambda n: (called_with_limit.append(n), [])[1]
            conn.execute.return_value = cursor
            conn.cursor.return_value = cursor
            conn.close = MagicMock()
            return conn

        with patch("web.routers.collection.get_db_path", return_value=db_path):
            with patch("sqlite3.connect", side_effect=mock_connect):
                result = collection_sql(req)

        assert called_with_limit and called_with_limit[-1] == 500

    def test_default_limit_is_500(self, tmp_path):
        """未提供 limit → 預設 500"""
        from web.routers.collection import SqlRequest
        req = SqlRequest(sql="SELECT * FROM videos")
        assert req.limit == 500

    def test_count_matches_actual_rows(self, tmp_path):
        """查詢結果少於 limit → count 準確"""
        from web.routers.collection import collection_sql, SqlRequest
        from core.database import init_db

        db_path = tmp_path / "test.db"
        init_db(db_path)

        req = SqlRequest(sql="SELECT COUNT(*) as total FROM videos")

        with patch("web.routers.collection.get_db_path", return_value=db_path):
            result = collection_sql(req)

        assert result["success"] is True
        assert result["count"] == len(result["rows"])


# ── 層 11–12：錯誤訊息固定化 ──────────────────────────────────────────────────

class TestLayer11_12ErrorShielding:
    def test_syntax_error_fixed_message(self, tmp_path):
        """SQL 語法錯誤 → success=False，error 是固定字串"""
        from web.routers.collection import collection_sql, SqlRequest
        from core.database import init_db

        db_path = tmp_path / "test.db"
        init_db(db_path)

        req = SqlRequest(sql="SELECT * FORM videos")  # 故意拼錯

        with patch("web.routers.collection.get_db_path", return_value=db_path):
            result = collection_sql(req)

        assert result["success"] is False
        assert "SQL 執行失敗" in result["error"]
        # 不應含 sqlite 原始訊息
        assert "FORM" not in result["error"]

    def test_unexpected_exception_fixed_message(self, tmp_path):
        """非預期例外 → success=False，error 含 '內部錯誤'"""
        from web.routers.collection import collection_sql, SqlRequest
        from core.database import init_db

        db_path = tmp_path / "test.db"
        init_db(db_path)

        req = SqlRequest(sql="SELECT * FROM videos")

        def mock_connect(*args, **kwargs):
            raise RuntimeError("kaboom internal error")

        with patch("web.routers.collection.get_db_path", return_value=db_path):
            with patch("sqlite3.connect", side_effect=mock_connect):
                result = collection_sql(req)

        assert result["success"] is False
        assert "內部錯誤" in result["error"]
        assert "kaboom" not in result["error"]


# ── 輸入驗證 ──────────────────────────────────────────────────────────────────

class TestInputValidation:
    def test_empty_sql_rejected(self):
        """空字串 → 拒絕（層 1 或 Pydantic）"""
        validate = _get_validate()
        err = validate("")
        assert err is not None

    def test_null_sql_pydantic_422(self):
        """sql=None → Pydantic 報錯"""
        from pydantic import ValidationError
        from web.routers.collection import SqlRequest
        with pytest.raises(ValidationError):
            SqlRequest(sql=None)

    def test_missing_sql_pydantic_422(self):
        """sql 欄位缺失 → Pydantic 報錯"""
        from pydantic import ValidationError
        from web.routers.collection import SqlRequest
        with pytest.raises(ValidationError):
            SqlRequest()

    def test_empty_sql_pydantic_422(self):
        """空字串 sql → Pydantic ValidationError（min_length=1，F6 修正）"""
        from pydantic import ValidationError
        from web.routers.collection import SqlRequest
        with pytest.raises(ValidationError):
            SqlRequest(sql="")

    def test_limit_zero_pydantic_422(self):
        """limit=0 → Pydantic ValidationError（ge=1，F3 修正）"""
        from pydantic import ValidationError
        from web.routers.collection import SqlRequest
        with pytest.raises(ValidationError):
            SqlRequest(sql="SELECT * FROM videos", limit=0)

    def test_limit_negative_pydantic_422(self):
        """limit=-1 → Pydantic ValidationError（ge=1，F3 修正）"""
        from pydantic import ValidationError
        from web.routers.collection import SqlRequest
        with pytest.raises(ValidationError):
            SqlRequest(sql="SELECT * FROM videos", limit=-1)


# ── Happy Path（validate_sql 邏輯層面）──────────────────────────────────────

class TestHappyPathValidation:
    def test_select_count_passes_validation(self):
        validate = _get_validate()
        err = validate("SELECT COUNT(*) as total FROM videos")
        assert err is None

    def test_select_columns_passes_validation(self):
        validate = _get_validate()
        err = validate("SELECT number, title FROM videos LIMIT 3")
        assert err is None

    def test_tvf_query_passes_validation(self):
        validate = _get_validate()
        err = validate("SELECT value FROM videos, json_each(videos.actresses) LIMIT 5")
        assert err is None

    def test_actress_aliases_query_passes_validation(self):
        validate = _get_validate()
        err = validate("SELECT old_name, new_name FROM actress_aliases")
        assert err is None
