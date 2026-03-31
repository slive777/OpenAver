"""
test_api_collection_sql.py — POST /api/collection/sql 端點整合測試

使用 FastAPI TestClient + tmp_path 真實 SQLite DB。
"""

import sqlite3
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, call
from fastapi.testclient import TestClient

from core.database import init_db


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path):
    """建立臨時測試資料庫，插入少量測試資料"""
    db_path = tmp_path / "test_collection.db"
    init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")

    # 插入測試影片
    conn.execute("""
        INSERT INTO videos (path, number, title, actresses, maker, tags, duration, size_bytes)
        VALUES
        ('file:///test/SONE-205.mp4', 'SONE-205', 'Test Title 1',
         '["明日花キララ"]', 'Sony', '["巨乳"]', 7200, 4000000000),
        ('file:///test/ABW-001.mp4', 'ABW-001', 'Test Title 2',
         '["葵つかさ","橋本ありな"]', 'ABC', '["女教師"]', 6000, 3500000000),
        ('file:///test/FC2-PPV-1234567.mp4', 'FC2-PPV-1234567', 'Test Title 3',
         '[]', 'FC2', '[]', 3600, 1000000000)
    """)

    # 插入測試別名
    conn.execute("""
        INSERT OR IGNORE INTO actress_aliases (old_name, new_name)
        VALUES ('橋本ありな', '新ありな')
    """)

    conn.commit()
    conn.close()

    return db_path


@pytest.fixture
def client(tmp_db, monkeypatch):
    """TestClient，monkeypatch get_db_path 指向 tmp DB"""
    monkeypatch.setattr("web.routers.collection.get_db_path", lambda: tmp_db)

    from web.app import app
    return TestClient(app)


# ── Happy Path ────────────────────────────────────────────────────────────────

class TestHappyPath:
    def test_count_all_videos(self, client):
        """SELECT COUNT(*) → success=True，count=1，columns=['total']"""
        resp = client.post("/api/collection/sql", json={
            "sql": "SELECT COUNT(*) as total FROM videos"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["columns"] == ["total"]
        assert len(data["rows"]) == 1
        assert data["rows"][0][0] == 3  # 3 筆測試資料
        assert data["count"] == 1

    def test_select_number_title(self, client):
        """SELECT number, title → columns 含 number, title，rows 為二維陣列"""
        resp = client.post("/api/collection/sql", json={
            "sql": "SELECT number, title FROM videos ORDER BY id LIMIT 3"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "number" in data["columns"]
        assert "title" in data["columns"]
        assert isinstance(data["rows"], list)
        assert all(isinstance(r, list) for r in data["rows"])
        assert data["count"] == 3

    def test_tvf_json_each_query(self, client):
        """json_each TVF 查詢正確執行"""
        resp = client.post("/api/collection/sql", json={
            "sql": "SELECT value FROM videos, json_each(videos.actresses) LIMIT 5"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "value" in data["columns"]
        # 明日花キララ + 葵つかさ + 橋本ありな = 3 個女優（videos 3 有空陣列）
        assert data["count"] >= 2

    def test_actress_aliases_query(self, client):
        """SELECT FROM actress_aliases → 正確回傳別名資料"""
        resp = client.post("/api/collection/sql", json={
            "sql": "SELECT old_name, new_name FROM actress_aliases WHERE old_name='橋本ありな'"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["count"] >= 1
        assert "old_name" in data["columns"]
        assert "new_name" in data["columns"]

    def test_limit_restricts_rows(self, client):
        """limit=2 → 最多回傳 2 筆"""
        resp = client.post("/api/collection/sql", json={
            "sql": "SELECT * FROM videos",
            "limit": 2
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["count"] <= 2

    def test_response_structure_success(self, client):
        """成功回應含 success, columns, rows, count 四個欄位"""
        resp = client.post("/api/collection/sql", json={
            "sql": "SELECT id FROM videos LIMIT 1"
        })
        data = resp.json()
        assert "success" in data
        assert "columns" in data
        assert "rows" in data
        assert "count" in data


# ── Security Reject Cases ─────────────────────────────────────────────────────

class TestSecurityRejects:
    def test_insert_rejected_400(self, client):
        """INSERT → 400，error 含 '只允許 SELECT'"""
        resp = client.post("/api/collection/sql", json={
            "sql": "INSERT INTO videos (path) VALUES ('x')"
        })
        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False
        assert "只允許 SELECT" in data["error"]

    def test_delete_rejected_400(self, client):
        """DELETE → 400"""
        resp = client.post("/api/collection/sql", json={
            "sql": "DELETE FROM videos"
        })
        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False

    def test_semicolon_rejected_400(self, client):
        """含 ; → 400"""
        resp = client.post("/api/collection/sql", json={
            "sql": "SELECT * FROM videos; DROP TABLE videos"
        })
        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False
        assert "不合法" in data["error"]

    def test_unknown_table_rejected_400(self, client):
        """未在白名單的表 → 400"""
        resp = client.post("/api/collection/sql", json={
            "sql": "SELECT * FROM secret_table"
        })
        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False
        assert "不允許的資料表" in data["error"]

    def test_sqlite_master_rejected_400(self, client):
        """sqlite_master → 400"""
        resp = client.post("/api/collection/sql", json={
            "sql": "SELECT * FROM sqlite_master"
        })
        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False

    def test_pragma_in_select_rejected_400(self, client):
        """含 PRAGMA 關鍵字 → 400"""
        resp = client.post("/api/collection/sql", json={
            "sql": "SELECT * FROM videos PRAGMA journal_mode"
        })
        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False

    def test_load_extension_rejected_400(self, client):
        """load_extension → 400"""
        resp = client.post("/api/collection/sql", json={
            "sql": "SELECT load_extension('/evil.so')"
        })
        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False

    def test_error_response_has_all_fields(self, client):
        """error 回應也含 columns=[], rows=[], count=0"""
        resp = client.post("/api/collection/sql", json={
            "sql": "DELETE FROM videos"
        })
        data = resp.json()
        assert data["columns"] == []
        assert data["rows"] == []
        assert data["count"] == 0

    def test_comma_join_disallowed_table_rejected_400(self, client):
        """逗號 JOIN 含非白名單表 → 400（F1 修正）"""
        resp = client.post("/api/collection/sql", json={
            "sql": "SELECT * FROM videos, evil_table"
        })
        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False
        assert "不允許的資料表" in data["error"]


# ── DB 不存在 ─────────────────────────────────────────────────────────────────

class TestDbNotExist:
    def test_db_not_exist_returns_200_with_error(self, tmp_path, monkeypatch):
        """DB 檔案不存在 → HTTP 200，success=False，error 含 '資料庫尚未初始化'"""
        non_existent = tmp_path / "no_such.db"
        monkeypatch.setattr("web.routers.collection.get_db_path", lambda: non_existent)

        from web.app import app
        test_client = TestClient(app)

        resp = test_client.post("/api/collection/sql", json={
            "sql": "SELECT * FROM videos"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "資料庫尚未初始化" in data["error"]


# ── Limit Capping ─────────────────────────────────────────────────────────────

class TestLimitCapping:
    def test_limit_over_500_returns_422(self, client):
        """limit=999 → Pydantic le=500 拒絕，HTTP 422（F3 修正）"""
        resp = client.post("/api/collection/sql", json={
            "sql": "SELECT * FROM videos",
            "limit": 999
        })
        assert resp.status_code == 422

    def test_limit_zero_returns_422(self, client):
        """limit=0 → Pydantic ge=1 拒絕，HTTP 422（F3 修正）"""
        resp = client.post("/api/collection/sql", json={
            "sql": "SELECT * FROM videos",
            "limit": 0
        })
        assert resp.status_code == 422

    def test_limit_negative_returns_422(self, client):
        """limit=-1 → Pydantic ge=1 拒絕，HTTP 422（F3 修正）"""
        resp = client.post("/api/collection/sql", json={
            "sql": "SELECT * FROM videos",
            "limit": -1
        })
        assert resp.status_code == 422

    def test_limit_500_succeeds(self, client):
        """limit=500 → 合法上限，成功回傳"""
        resp = client.post("/api/collection/sql", json={
            "sql": "SELECT * FROM videos",
            "limit": 500
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["count"] <= 500

    def test_missing_sql_returns_422(self, client):
        """sql 欄位缺失 → Pydantic 422"""
        resp = client.post("/api/collection/sql", json={
            "limit": 10
        })
        assert resp.status_code == 422

    def test_empty_sql_returns_422(self, client):
        """空字串 sql → Pydantic min_length=1 拒絕，HTTP 422（F6 修正）"""
        resp = client.post("/api/collection/sql", json={
            "sql": ""
        })
        assert resp.status_code == 422


# ── Security Layer 8：PRAGMA 設定驗證（BC28 / BC33）────────────────────────────

class TestLayer8Pragmas:
    """BC28 / BC33 — 驗證 SQLite 連線的 PRAGMA 設定被正確套用（F4 修正）"""

    def _make_mock_conn_with_pragma_tracking(self):
        """
        建立 MagicMock connection，追蹤所有 execute 呼叫的 SQL 語句。
        回傳 (mock_conn, executed_stmts_list)。
        """
        executed_stmts = []
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("total",)]
        mock_cursor.fetchmany.return_value = [[1]]

        def track_execute(stmt, *args, **kwargs):
            executed_stmts.append(stmt.strip())
            return mock_cursor

        mock_conn.execute.side_effect = track_execute
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.close = MagicMock()
        return mock_conn, executed_stmts

    def test_bc28_query_only_pragma_is_set(self, tmp_db, monkeypatch):
        """BC28：驗證 PRAGMA query_only = ON 的 execute 被呼叫（F4 修正）"""
        monkeypatch.setattr("web.routers.collection.get_db_path", lambda: tmp_db)

        mock_conn, executed_stmts = self._make_mock_conn_with_pragma_tracking()

        with patch("sqlite3.connect", return_value=mock_conn):
            from web.app import app
            test_client = TestClient(app)
            resp = test_client.post("/api/collection/sql", json={
                "sql": "SELECT COUNT(*) as total FROM videos"
            })

        assert resp.status_code == 200
        assert resp.json()["success"] is True
        # 確認 PRAGMA query_only = ON 被呼叫
        query_only_calls = [s for s in executed_stmts if "query_only" in s.lower()]
        assert query_only_calls, (
            f"PRAGMA query_only = ON 未被設定；執行的語句: {executed_stmts}"
        )
        assert any("ON" in s.upper() for s in query_only_calls), (
            f"query_only 值不是 ON：{query_only_calls}"
        )

    def test_bc28_query_only_blocks_writes_at_sqlite_layer(self, tmp_db):
        """BC28：query_only = ON 在 SQLite 層實際阻擋寫入（真實 DB 驗證）"""
        conn = sqlite3.connect(f"file:{tmp_db}?mode=ro", uri=True)
        conn.execute("PRAGMA query_only = ON")

        # 嘗試寫入 → 應拋出 OperationalError（SQLite 層阻擋）
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("INSERT INTO videos (path, number) VALUES ('x', 'y')")

        conn.close()

    def test_bc33_busy_timeout_pragma_is_set(self, tmp_db, monkeypatch):
        """BC33：驗證 PRAGMA busy_timeout = 5000 的 execute 被呼叫（F4 修正）"""
        monkeypatch.setattr("web.routers.collection.get_db_path", lambda: tmp_db)

        mock_conn, executed_stmts = self._make_mock_conn_with_pragma_tracking()

        with patch("sqlite3.connect", return_value=mock_conn):
            from web.app import app
            test_client = TestClient(app)
            resp = test_client.post("/api/collection/sql", json={
                "sql": "SELECT COUNT(*) as total FROM videos"
            })

        assert resp.status_code == 200
        # 確認 PRAGMA busy_timeout = 5000 被呼叫
        busy_timeout_calls = [s for s in executed_stmts if "busy_timeout" in s.lower()]
        assert busy_timeout_calls, (
            f"PRAGMA busy_timeout = 5000 未被設定；執行的語句: {executed_stmts}"
        )
        assert "5000" in busy_timeout_calls[0], (
            f"busy_timeout 值不是 5000：{busy_timeout_calls[0]}"
        )
