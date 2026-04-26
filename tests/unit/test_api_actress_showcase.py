"""
Unit tests for GET /api/actresses list + POST /api/actresses/{name}/rescrape
Phase 44a T1 — TDD-lite
"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from core.database import init_db, Actress, ActressRepository, Video, VideoRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_with_actresses(tmp_path: Path):
    """建立含女優資料的臨時 DB，回傳 db_path"""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return db_path


@pytest.fixture
def client_with_db(monkeypatch, db_with_actresses):
    """TestClient with monkeypatched DB path，actress router 用"""
    monkeypatch.setattr("core.database.get_db_path", lambda: db_with_actresses)
    monkeypatch.setattr("web.routers.actress.init_db", lambda: None)
    # patch get_local_photo_path to return None (no photo files in test)
    monkeypatch.setattr("web.routers.actress.get_local_photo_path", lambda name: None)
    from web.app import app
    return TestClient(app), db_with_actresses


# ---------------------------------------------------------------------------
# GET /api/actresses — list endpoint
# ---------------------------------------------------------------------------

class TestActressListEndpoint:

    def test_list_empty(self, client_with_db):
        """空 DB → {"actresses": [], "total": 0}"""
        client, db_path = client_with_db
        response = client.get("/api/actresses")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["actresses"] == []
        assert data["total"] == 0

    def test_list_with_actresses(self, client_with_db):
        """儲存 2 位女優 → 回傳兩筆，含所有欄位 + video_count + created_at"""
        client, db_path = client_with_db
        repo = ActressRepository(db_path)
        repo.save(Actress(name="三上悠亜", name_en="Yua Mikami", height="163cm"))
        repo.save(Actress(name="明日花キララ", name_en="Kirara Asuka"))

        response = client.get("/api/actresses")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["total"] == 2
        assert len(data["actresses"]) == 2

        names = {a["name"] for a in data["actresses"]}
        assert "三上悠亜" in names
        assert "明日花キララ" in names

        # 每筆應含 video_count + created_at + is_favorite
        for actress_data in data["actresses"]:
            assert "video_count" in actress_data
            assert "created_at" in actress_data
            assert isinstance(actress_data["video_count"], int)
            assert actress_data["is_favorite"] is True

    def test_list_video_count_exact_match(self, client_with_db):
        """video_count 使用 json_each 精確比對，不誤匹子字串"""
        client, db_path = client_with_db
        repo = ActressRepository(db_path)
        repo.save(Actress(name="miru"))
        # "miruku" 不應算入 "miru" 的 video_count
        repo.save(Actress(name="miruku"))

        video_repo = VideoRepository(db_path)
        video_repo.upsert_batch([
            Video(
                path="/test/video1.mp4",
                number="TEST-001",
                actresses=["miru"],
                mtime=100.0,
            ),
            Video(
                path="/test/video2.mp4",
                number="TEST-002",
                actresses=["miruku"],
                mtime=200.0,
            ),
        ])

        response = client.get("/api/actresses")
        assert response.status_code == 200
        data = response.json()
        actresses_map = {a["name"]: a for a in data["actresses"]}

        assert actresses_map["miru"]["video_count"] == 1
        assert actresses_map["miruku"]["video_count"] == 1

    def test_list_video_count_dirty_data(self, client_with_db):
        """actresses 欄位為無效 JSON 時，video_count 回傳 0（不炸）"""
        client, db_path = client_with_db
        repo = ActressRepository(db_path)
        repo.save(Actress(name="女優A"))

        # 直接插入 dirty data（actresses 為無效 JSON）
        import sqlite3
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                "INSERT INTO videos (path, number, actresses, mtime) VALUES (?, ?, ?, ?)",
                ("/test/dirty.mp4", "DIRTY-001", "NOT_VALID_JSON", 100.0)
            )

        # 不應 crash，video_count 應為 0
        response = client.get("/api/actresses")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        actress_data = data["actresses"][0]
        assert actress_data["video_count"] == 0

    def test_list_video_count_no_videos(self, client_with_db):
        """videos 表為空 → video_count = 0"""
        client, db_path = client_with_db
        repo = ActressRepository(db_path)
        repo.save(Actress(name="孤獨女優"))

        response = client.get("/api/actresses")
        assert response.status_code == 200
        data = response.json()
        assert data["actresses"][0]["video_count"] == 0


# ---------------------------------------------------------------------------
# Backward compatibility: _actress_to_response default video_count
# ---------------------------------------------------------------------------

class TestActressToResponseBackwardCompatibility:

    def test_actress_to_response_default_video_count(self, monkeypatch):
        """現有呼叫端不傳 video_count → 預設 0，不影響現有行為"""
        monkeypatch.setattr("web.routers.actress.get_local_photo_path", lambda name: None)

        from web.routers.actress import _actress_to_response
        actress = Actress(name="測試女優", name_en="Test Actress")

        # 不傳 video_count，應使用預設值 0
        result = _actress_to_response(actress)
        assert result["video_count"] == 0
        assert result["name"] == "測試女優"

        # 傳 video_count，應正確反映
        result_with_count = _actress_to_response(actress, video_count=5)
        assert result_with_count["video_count"] == 5

        # created_at 應在回傳 dict 中
        assert "created_at" in result
        assert result["created_at"] is None  # Actress() 預設 created_at=None
