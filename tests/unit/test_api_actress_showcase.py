"""
Unit tests for GET /api/actresses list + POST /api/actresses/{name}/rescrape
Phase 44a T1 — TDD-lite
"""
import pytest
from pathlib import Path
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
    monkeypatch.setattr("core.database.connection.get_db_path", lambda: db_with_actresses)
    monkeypatch.setattr("web.routers.actress.init_db", lambda: None)
    # patch get_local_photo_path to return None (no photo files in test)
    monkeypatch.setattr("web.routers.actress.get_local_photo_path", lambda name: None)
    from web.app import app
    return TestClient(app), db_with_actresses


# ---------------------------------------------------------------------------
# GET /api/actresses — list endpoint
# ---------------------------------------------------------------------------

class TestActressListEndpoint:


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
            assert isinstance(actress_data["recent_score"], (int, float))
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


# ---------------------------------------------------------------------------
# Backward compatibility: _actress_to_response default video_count
# ---------------------------------------------------------------------------

