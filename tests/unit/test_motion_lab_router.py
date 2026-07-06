"""測試 Motion Lab router"""
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from core.database import init_db, Video, VideoRepository
from core.path_utils import to_file_uri


# temp_db fixture 定義於 tests/unit/conftest.py

@pytest.fixture
def populated_db(make_populated_db):
    videos = []
    for i in range(35):
        videos.append(Video(
            path=to_file_uri(f"C:/Videos/TEST-{i:03d}.mp4"),
            number=f"TEST-{i:03d}",
            title=f"Test Video {i}",
            actresses=[f"Actress {i}"],
            maker="Test Maker",
            release_date="2024-01-01",
            tags=[],
            size_bytes=1024,
            cover_path=to_file_uri(f"C:/Videos/TEST-{i:03d}/cover.jpg"),
            mtime=1705276800.0 + i,
        ))
    return make_populated_db(videos)


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
        assert len(data["videos"]) == 30  # 35 筆 DB，限制 30 筆

        # 所有有封面的影片，cover_url 必須包含 /api/gallery/image?path=
        for video in data["videos"]:
            if video["cover_url"]:
                assert video["cover_url"].startswith("/api/gallery/image?path="), \
                    f"cover_url 格式錯誤: {video['cover_url']}"

    def test_motion_lab_data_cover_url_reverse_maps_wsl_unc(self, tmp_path, monkeypatch):
        """TASK-91-T2a #5: cover_url 在 WSL + UNC path_mappings 下必須反解為
        本機路徑，而不是留下裸 uri_to_fs_path() 產生的映射端 UNC 字串
        （get_image 端沒有第二次反解機會）。"""
        import core.path_utils as path_utils
        from core.database import Video

        monkeypatch.setattr(path_utils, "CURRENT_ENV", "wsl")

        db_path = tmp_path / "wsl_unc.db"
        init_db(db_path)
        repo = VideoRepository(db_path)
        video = Video(
            path="file://///NAS/share/video.mp4",
            number="TEST-001",
            title="WSL UNC Video",
            cover_path="file://///NAS/share/cover.jpg",
        )
        repo.upsert(video)

        monkeypatch.setattr("web.routers.motion_lab.get_db_path", lambda: db_path)
        monkeypatch.setattr(
            "web.routers.motion_lab.load_config",
            lambda: {"gallery": {"path_mappings": {"/home/user/nas": "//NAS/share"}}},
        )

        from web.routers.motion_lab import router
        from fastapi import FastAPI
        test_app = FastAPI()
        test_app.include_router(router)
        client = TestClient(test_app)

        response = client.get("/api/motion-lab/data")
        assert response.status_code == 200
        data = response.json()
        from urllib.parse import unquote
        cover_url = unquote(data["videos"][0]["cover_url"])
        assert "/home/user/nas/cover.jpg" in cover_url, (
            f"cover_url 應反解為本機路徑，實際: {cover_url}"
        )
        assert "//NAS/share/cover.jpg" not in cover_url, (
            f"cover_url 不應殘留裸 UNC 映射端字串，實際: {cover_url}"
        )

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
