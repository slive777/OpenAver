"""
test_api_showcase.py — Showcase API 整合測試

測試 GET /api/showcase/videos 端點行為，
包含 user_tags 欄位補充（T4）。
"""

import pytest
from pathlib import Path
from core.database import init_db, VideoRepository, Video
from core.path_utils import to_file_uri


# ============ Fixtures ============

@pytest.fixture
def showcase_setup(tmp_path):
    """
    建立含測試資料的臨時 DB（含 user_tags）。
    回傳 dict：{db_path, vid1_uri, vid2_uri, config}
    """
    video_dir = tmp_path / "videos"
    video_dir.mkdir()

    vid1_uri = to_file_uri(str(video_dir / "video1.mp4"), {})
    vid2_uri = to_file_uri(str(video_dir / "video2.mp4"), {})

    db_path = tmp_path / "showcase_test.db"
    init_db(db_path)
    repo = VideoRepository(db_path)
    repo.upsert_batch([
        Video(
            path=vid1_uri,
            number="SONE-001",
            title="Test Video With Tags",
            actresses=["Test Actress"],
            maker="Test Maker",
            release_date="2024-01-01",
            tags=["高畫質", "單體作品"],
            user_tags=["★5", "足"],
            size_bytes=1073741824,
            mtime=1700000000.0,
        ),
        Video(
            path=vid2_uri,
            number="SONE-002",
            title="Test Video No User Tags",
            actresses=[],
            maker="",
            release_date="",
            tags=[],
            user_tags=[],
            size_bytes=0,
            mtime=0.0,
        ),
    ])

    config = {
        "gallery": {
            "directories": [str(video_dir)],
            "path_mappings": {},
            "min_size_mb": 0,
            "thumbnail_width": 400,
        },
        "scraper": {"video_extensions": [".mp4"], "image_extensions": [".jpg"]},
        "database": {"path": ":memory:"},
        "translate": {"provider": "ollama", "ollama_model": "llama3"},
    }

    return {
        "db_path": db_path,
        "vid1_uri": vid1_uri,
        "vid2_uri": vid2_uri,
        "config": config,
    }


# ============ Tests ============

class TestShowcaseVideosUserTags:
    """測試 GET /api/showcase/videos 包含 user_tags 欄位（T4）"""

    def test_response_contains_user_tags_field(self, client, showcase_setup, mocker):
        """每個 video 物件必須包含 user_tags 欄位"""
        mocker.patch("web.routers.showcase.get_db_path", return_value=showcase_setup["db_path"])
        mocker.patch("web.routers.showcase.load_config", return_value=showcase_setup["config"])

        response = client.get("/api/showcase/videos")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["videos"]) == 2

        for video in data["videos"]:
            assert "user_tags" in video, f"user_tags 欄位缺失：{video.get('path')}"
            assert isinstance(video["user_tags"], list), "user_tags 應為 list"

    def test_user_tags_values_preserved(self, client, showcase_setup, mocker):
        """user_tags 值應與 DB 一致"""
        mocker.patch("web.routers.showcase.get_db_path", return_value=showcase_setup["db_path"])
        mocker.patch("web.routers.showcase.load_config", return_value=showcase_setup["config"])

        response = client.get("/api/showcase/videos")
        data = response.json()

        # 找到有 user_tags 的影片
        video_with_tags = next(
            v for v in data["videos"] if v["path"] == showcase_setup["vid1_uri"]
        )
        assert video_with_tags["user_tags"] == ["★5", "足"]

    def test_empty_user_tags_returns_empty_list(self, client, showcase_setup, mocker):
        """無 user_tags 時應回傳空 list（不是 null）"""
        mocker.patch("web.routers.showcase.get_db_path", return_value=showcase_setup["db_path"])
        mocker.patch("web.routers.showcase.load_config", return_value=showcase_setup["config"])

        response = client.get("/api/showcase/videos")
        data = response.json()

        video_no_tags = next(
            v for v in data["videos"] if v["path"] == showcase_setup["vid2_uri"]
        )
        assert video_no_tags["user_tags"] == []
