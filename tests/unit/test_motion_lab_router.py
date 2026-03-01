"""測試 Motion Lab router"""
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from core.database import init_db, Video, VideoRepository


# temp_db fixture 定義於 tests/unit/conftest.py


@pytest.fixture
def populated_db(temp_db):
    """填入 35 筆測試資料（超過 30 筆，用於測試 LIMIT）"""
    repo = VideoRepository(temp_db)
    videos = []
    for i in range(35):
        videos.append(Video(
            path=f"file:///C:/Videos/TEST-{i:03d}.mp4",
            number=f"TEST-{i:03d}",
            title=f"Test Video {i}",
            actresses=[f"Actress {i}"],
            maker="Test Maker",
            release_date="2024-01-01",
            tags=[],
            size_bytes=1024,
            cover_path=f"file:///C:/Videos/TEST-{i:03d}/cover.jpg",
            mtime=1705276800.0 + i,
        ))
    repo.upsert_batch(videos)
    return temp_db


class TestMotionLabDataAPI:
    """測試 /api/motion-lab/data 端點"""

    def test_motion_lab_data_returns_json_structure(self, temp_db, monkeypatch):
        """API 回傳 { success, videos, total }"""
        monkeypatch.setattr("web.routers.motion_lab.get_db_path", lambda: temp_db)

        from web.routers.motion_lab import router
        from fastapi import FastAPI
        test_app = FastAPI()
        test_app.include_router(router)
        client = TestClient(test_app)

        response = client.get("/api/motion-lab/data")
        assert response.status_code == 200

        data = response.json()
        assert "success" in data
        assert "videos" in data
        assert "total" in data
        assert data["success"] is True
        assert isinstance(data["videos"], list)
        assert isinstance(data["total"], int)

    def test_motion_lab_data_returns_at_most_30_videos(self, populated_db, monkeypatch):
        """最多 30 筆（DB 有 35 筆，應只回傳 30 筆）"""
        monkeypatch.setattr("web.routers.motion_lab.get_db_path", lambda: populated_db)

        from web.routers.motion_lab import router
        from fastapi import FastAPI
        test_app = FastAPI()
        test_app.include_router(router)
        client = TestClient(test_app)

        response = client.get("/api/motion-lab/data")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert len(data["videos"]) <= 30
        assert data["total"] <= 30

    def test_motion_lab_data_handles_empty_db(self, temp_db, monkeypatch):
        """DB 空時 videos: []"""
        monkeypatch.setattr("web.routers.motion_lab.get_db_path", lambda: temp_db)

        from web.routers.motion_lab import router
        from fastapi import FastAPI
        test_app = FastAPI()
        test_app.include_router(router)
        client = TestClient(test_app)

        response = client.get("/api/motion-lab/data")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["videos"] == []
        assert data["total"] == 0

    def test_motion_lab_data_cover_url_format(self, populated_db, monkeypatch):
        """cover_url 包含 /api/gallery/image?path="""
        monkeypatch.setattr("web.routers.motion_lab.get_db_path", lambda: populated_db)

        from web.routers.motion_lab import router
        from fastapi import FastAPI
        test_app = FastAPI()
        test_app.include_router(router)
        client = TestClient(test_app)

        response = client.get("/api/motion-lab/data")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert len(data["videos"]) > 0

        # 所有有封面的影片，cover_url 必須包含 /api/gallery/image?path=
        for video in data["videos"]:
            if video["cover_url"]:
                assert video["cover_url"].startswith("/api/gallery/image?path="), \
                    f"cover_url 格式錯誤: {video['cover_url']}"

    def test_motion_lab_data_db_not_exists(self, tmp_path, monkeypatch):
        """DB 不存在時回傳空結果，不拋例外"""
        nonexistent_db = tmp_path / "nonexistent.db"
        monkeypatch.setattr("web.routers.motion_lab.get_db_path", lambda: nonexistent_db)

        from web.routers.motion_lab import router
        from fastapi import FastAPI
        test_app = FastAPI()
        test_app.include_router(router)
        client = TestClient(test_app)

        response = client.get("/api/motion-lab/data")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["videos"] == []
        assert data["total"] == 0
