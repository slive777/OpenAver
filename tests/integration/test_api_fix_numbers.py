"""
test_api_fix_numbers.py — Integration tests for:
  POST /api/collection/fix-numbers/preview
  POST /api/collection/fix-numbers/apply

Uses FastAPI TestClient + tmp_path real SQLite DB.
"""

import sqlite3
import pytest
from fastapi.testclient import TestClient

from core.database import init_db


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path):
    """空 videos 表（只建 schema）"""
    db_path = tmp_path / "test_fix_numbers.db"
    init_db(db_path)
    return db_path


@pytest.fixture
def client(tmp_db, monkeypatch):
    """TestClient，monkeypatch get_db_path → tmp_db"""
    monkeypatch.setattr("web.routers.collection.get_db_path", lambda: tmp_db)
    from web.app import app
    return TestClient(app)


def _insert_videos(db_path, rows):
    """Helper: 批次插入測試影片資料"""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executemany(
        """INSERT INTO videos
           (path, number, title, actresses, maker, tags, director, label,
            original_title, cover_path, release_date, nfo_mtime)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()
    conn.close()


# ── I1: preview happy path ────────────────────────────────────────────────────

class TestPreviewHappyPath:
    """I1: 插入 3 筆 corrupted number，preview 應回傳正確的 old/new_number 和 rule"""

    def test_preview_returns_affected_list(self, tmp_db, monkeypatch):
        rows = [
            # digit_prefix × 2
            ("file:///test/1.mp4", "7IPZ-154",  "Title 1", "[]", "Maker", "[]", "", "", "", None, "2024-01-01", 0.0),
            ("file:///test/2.mp4", "3ABW-001",  "Title 2", "[]", "Maker", "[]", "", "", "", None, "2024-01-01", 0.0),
            # TK_prefix × 1
            ("file:///test/3.mp4", "TKSONE-205","Title 3", "[]", "Maker", "[]", "", "", "", None, "2024-01-01", 0.0),
            # 正常番號（不應出現）
            ("file:///test/4.mp4", "MIDE-001",  "Title 4", "[]", "Maker", "[]", "", "", "", None, "2024-01-01", 0.0),
        ]
        _insert_videos(tmp_db, rows)

        monkeypatch.setattr("web.routers.collection.get_db_path", lambda: tmp_db)
        from web.app import app
        test_client = TestClient(app)

        resp = test_client.post(
            "/api/collection/fix-numbers/preview",
            json={"rules": []},
        )
        assert resp.status_code == 200
        data = resp.json()

        # total = 3 筆 corrupted
        assert data["total"] == 3
        assert len(data["affected"]) == 3

        # rules_applied 含全部 4 條
        assert set(data["rules_applied"]) == {"digit_prefix", "TK_prefix", "K9_prefix", "R_prefix"}

        # 驗證每筆結構
        for item in data["affected"]:
            assert "id" in item
            assert "old_number" in item
            assert "new_number" in item
            assert "rule" in item
            assert "path" in item

        # 驗證修正內容
        affected_by_old = {item["old_number"]: item for item in data["affected"]}
        assert "7IPZ-154" in affected_by_old
        assert affected_by_old["7IPZ-154"]["new_number"] == "IPZ-154"
        assert affected_by_old["7IPZ-154"]["rule"] == "digit_prefix"

        assert "3ABW-001" in affected_by_old
        assert affected_by_old["3ABW-001"]["new_number"] == "ABW-001"

        assert "TKSONE-205" in affected_by_old
        assert affected_by_old["TKSONE-205"]["new_number"] == "SONE-205"
        assert affected_by_old["TKSONE-205"]["rule"] == "TK_prefix"

        # 正常番號不出現
        numbers_in_affected = {item["old_number"] for item in data["affected"]}
        assert "MIDE-001" not in numbers_in_affected


# ── I2: apply success ─────────────────────────────────────────────────────────

class TestApplySuccess:
    """I2: apply 傳入 preview 回傳的 ids，驗證 DB number 欄位正確更新"""

    def test_apply_updates_db_numbers(self, tmp_db, monkeypatch):
        rows = [
            ("file:///test/1.mp4", "7IPZ-154",  "Title 1", "[]", "Maker", "[]", "", "", "", None, "2024-01-01", 0.0),
            ("file:///test/2.mp4", "3ABW-001",  "Title 2", "[]", "Maker", "[]", "", "", "", None, "2024-01-01", 0.0),
            ("file:///test/3.mp4", "TKSONE-205","Title 3", "[]", "Maker", "[]", "", "", "", None, "2024-01-01", 0.0),
        ]
        _insert_videos(tmp_db, rows)

        monkeypatch.setattr("web.routers.collection.get_db_path", lambda: tmp_db)
        from web.app import app
        test_client = TestClient(app)

        # Step 1: preview 取得 ids
        preview_resp = test_client.post(
            "/api/collection/fix-numbers/preview",
            json={"rules": []},
        )
        assert preview_resp.status_code == 200
        preview_data = preview_resp.json()
        ids = [item["id"] for item in preview_data["affected"]]
        assert len(ids) == 3

        # Step 2: apply
        apply_resp = test_client.post(
            "/api/collection/fix-numbers/apply",
            json={"ids": ids},
        )
        assert apply_resp.status_code == 200
        apply_data = apply_resp.json()
        assert apply_data["updated"] == 3
        assert apply_data["failed"] == 0

        # Step 3: 驗證 DB number 已更新
        conn = sqlite3.connect(str(tmp_db))
        rows_result = conn.execute("SELECT number FROM videos ORDER BY id").fetchall()
        conn.close()
        numbers = [r[0] for r in rows_result]
        assert "IPZ-154" in numbers
        assert "ABW-001" in numbers
        assert "SONE-205" in numbers
        # 舊番號不應存在
        assert "7IPZ-154" not in numbers
        assert "3ABW-001" not in numbers
        assert "TKSONE-205" not in numbers


# ── I3: apply 跳過不再符合規則的 ID ──────────────────────────────────────────

class TestApplySkipsAlreadyFixed:
    """I3: 手動先更新 DB 使番號變為正常，apply 傳入該 ID → updated=0, failed=1"""

    def test_apply_skips_already_fixed_id(self, tmp_db, monkeypatch):
        rows = [
            ("file:///test/1.mp4", "7IPZ-154", "Title 1", "[]", "Maker", "[]", "", "", "", None, "2024-01-01", 0.0),
        ]
        _insert_videos(tmp_db, rows)

        # 手動先把番號更新為正常番號（模擬 preview 到 apply 之間被修正）
        conn = sqlite3.connect(str(tmp_db))
        conn.execute("UPDATE videos SET number = 'IPZ-154' WHERE path = 'file:///test/1.mp4'")
        conn.commit()
        video_id = conn.execute("SELECT id FROM videos WHERE path = 'file:///test/1.mp4'").fetchone()[0]
        conn.close()

        monkeypatch.setattr("web.routers.collection.get_db_path", lambda: tmp_db)
        from web.app import app
        test_client = TestClient(app)

        # apply 傳入該 ID
        apply_resp = test_client.post(
            "/api/collection/fix-numbers/apply",
            json={"ids": [video_id]},
        )
        assert apply_resp.status_code == 200
        apply_data = apply_resp.json()
        assert apply_data["updated"] == 0
        assert apply_data["failed"] == 1

        # 確認 DB 番號仍是修正後的正常番號（不被覆蓋）
        conn = sqlite3.connect(str(tmp_db))
        number = conn.execute("SELECT number FROM videos WHERE id = ?", (video_id,)).fetchone()[0]
        conn.close()
        assert number == "IPZ-154"
