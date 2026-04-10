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


# ============ has_cover / has_nfo Tests ============

class TestShowcaseHasCoverHasNfo:
    """測試 GET /api/showcase/videos 包含 has_cover / has_nfo 欄位（T2）"""

    @pytest.fixture
    def cover_nfo_setup(self, tmp_path):
        """建立含 4 種 has_cover×has_nfo 組合的臨時 DB"""
        video_dir = tmp_path / "videos"
        video_dir.mkdir()

        # 建立假封面 URI（不需要真實檔案，DB 初判不做 IO）
        cover_uri = to_file_uri(str(tmp_path / "cover.jpg"), {})

        uris = {
            "v_ff": to_file_uri(str(video_dir / "v_ff.mp4"), {}),  # cover=False, nfo=False
            "v_tf": to_file_uri(str(video_dir / "v_tf.mp4"), {}),  # cover=True,  nfo=False
            "v_ft": to_file_uri(str(video_dir / "v_ft.mp4"), {}),  # cover=False, nfo=True
            "v_tt": to_file_uri(str(video_dir / "v_tt.mp4"), {}),  # cover=True,  nfo=True
        }

        db_path = tmp_path / "cover_nfo_test.db"
        init_db(db_path)
        repo = VideoRepository(db_path)
        repo.upsert_batch([
            Video(path=uris["v_ff"], title="FF", cover_path="",        nfo_mtime=0.0),
            Video(path=uris["v_tf"], title="TF", cover_path=cover_uri, nfo_mtime=0.0),
            Video(path=uris["v_ft"], title="FT", cover_path="",        nfo_mtime=1700000000.0),
            Video(path=uris["v_tt"], title="TT", cover_path=cover_uri, nfo_mtime=1700000000.0),
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

        return {"db_path": db_path, "uris": uris, "config": config}

    def test_has_cover_and_has_nfo_fields_present(self, client, cover_nfo_setup, mocker):
        """每個 video 物件必須包含 has_cover 與 has_nfo 欄位"""
        mocker.patch("web.routers.showcase.get_db_path", return_value=cover_nfo_setup["db_path"])
        mocker.patch("web.routers.showcase.load_config", return_value=cover_nfo_setup["config"])

        response = client.get("/api/showcase/videos")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        for video in data["videos"]:
            assert "has_cover" in video, f"has_cover 欄位缺失：{video.get('path')}"
            assert "has_nfo" in video, f"has_nfo 欄位缺失：{video.get('path')}"
            assert isinstance(video["has_cover"], bool)
            assert isinstance(video["has_nfo"], bool)

    def test_has_cover_false_when_cover_path_empty(self, client, cover_nfo_setup, mocker):
        """cover_path 為空字串時 has_cover 應為 False"""
        mocker.patch("web.routers.showcase.get_db_path", return_value=cover_nfo_setup["db_path"])
        mocker.patch("web.routers.showcase.load_config", return_value=cover_nfo_setup["config"])

        response = client.get("/api/showcase/videos")
        data = response.json()

        v_ff = next(v for v in data["videos"] if v["path"] == cover_nfo_setup["uris"]["v_ff"])
        assert v_ff["has_cover"] is False
        assert v_ff["has_nfo"] is False

    def test_has_cover_true_when_cover_path_set(self, client, cover_nfo_setup, mocker):
        """cover_path 非空時 has_cover 應為 True"""
        mocker.patch("web.routers.showcase.get_db_path", return_value=cover_nfo_setup["db_path"])
        mocker.patch("web.routers.showcase.load_config", return_value=cover_nfo_setup["config"])

        response = client.get("/api/showcase/videos")
        data = response.json()

        v_tf = next(v for v in data["videos"] if v["path"] == cover_nfo_setup["uris"]["v_tf"])
        assert v_tf["has_cover"] is True
        assert v_tf["has_nfo"] is False

    def test_has_nfo_true_when_nfo_mtime_positive(self, client, cover_nfo_setup, mocker):
        """nfo_mtime > 0 時 has_nfo 應為 True"""
        mocker.patch("web.routers.showcase.get_db_path", return_value=cover_nfo_setup["db_path"])
        mocker.patch("web.routers.showcase.load_config", return_value=cover_nfo_setup["config"])

        response = client.get("/api/showcase/videos")
        data = response.json()

        v_ft = next(v for v in data["videos"] if v["path"] == cover_nfo_setup["uris"]["v_ft"])
        assert v_ft["has_cover"] is False
        assert v_ft["has_nfo"] is True

        v_tt = next(v for v in data["videos"] if v["path"] == cover_nfo_setup["uris"]["v_tt"])
        assert v_tt["has_cover"] is True
        assert v_tt["has_nfo"] is True


# ============ Single Video Endpoint Tests ============

class TestShowcaseVideoSingle:
    """測試 GET /api/showcase/video?path= 單筆查詢端點（T2）"""

    @pytest.fixture
    def single_setup(self, tmp_path):
        """建立含 1 筆有封面＋NFO 影片的臨時 DB"""
        video_dir = tmp_path / "videos"
        video_dir.mkdir()

        cover_uri = to_file_uri(str(tmp_path / "cover.jpg"), {})
        vid_uri = to_file_uri(str(video_dir / "video.mp4"), {})

        db_path = tmp_path / "single_test.db"
        init_db(db_path)
        repo = VideoRepository(db_path)
        repo.upsert_batch([
            Video(
                path=vid_uri,
                number="ABC-001",
                title="Single Test Video",
                actresses=["Actress A"],
                maker="Test Maker",
                release_date="2024-06-01",
                tags=["HD"],
                user_tags=["★5"],
                size_bytes=2147483648,
                mtime=1700000000.0,
                cover_path=cover_uri,
                nfo_mtime=1700000001.0,
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

        return {"db_path": db_path, "vid_uri": vid_uri, "video_dir": video_dir, "config": config}

    def test_happy_path_returns_video(self, client, single_setup, mocker):
        """正常情況：回傳 200 + video dict 欄位完整"""
        mocker.patch("web.routers.showcase.get_db_path", return_value=single_setup["db_path"])
        mocker.patch("web.routers.showcase.load_config", return_value=single_setup["config"])

        response = client.get(f"/api/showcase/video?path={single_setup['vid_uri']}")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert "video" in data

        video = data["video"]
        assert video["path"] == single_setup["vid_uri"]
        assert video["number"] == "ABC-001"
        assert video["has_cover"] is True
        assert video["has_nfo"] is True
        assert isinstance(video["user_tags"], list)
        # 確認所有必要欄位存在
        for field in ("path", "title", "number", "cover_url", "has_cover", "has_nfo",
                      "user_tags", "tags", "actresses", "size", "mtime"):
            assert field in video, f"欄位 {field} 缺失"

    def test_nonexistent_path_returns_404(self, client, single_setup, mocker):
        """DB 中不存在的 path → 404"""
        mocker.patch("web.routers.showcase.get_db_path", return_value=single_setup["db_path"])
        mocker.patch("web.routers.showcase.load_config", return_value=single_setup["config"])

        # 用 to_file_uri 產生 configured directory 下的合法 URI（避免手刻 URI 拼接）
        # 確保真的測到「path 在 dir 下但 DB 沒記錄」分支，而非被 dir filter 先擋
        ghost_uri = to_file_uri(str(single_setup["video_dir"] / "ghost.mp4"), {})

        response = client.get(f"/api/showcase/video?path={ghost_uri}")
        assert response.status_code == 404
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "video not found"

    def test_path_not_in_configured_dir_returns_404(self, client, single_setup, mocker, tmp_path):
        """path 不在 configured directory → 404（不洩漏目錄資訊）"""
        mocker.patch("web.routers.showcase.get_db_path", return_value=single_setup["db_path"])
        mocker.patch("web.routers.showcase.load_config", return_value=single_setup["config"])

        # 建構一個合法 URI 但在不同目錄
        other_dir = tmp_path / "other_dir"
        other_dir.mkdir()
        other_uri = to_file_uri(str(other_dir / "other.mp4"), {})

        response = client.get(f"/api/showcase/video?path={other_uri}")
        assert response.status_code == 404
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "video not found"

    def test_missing_path_param_returns_422(self, client, single_setup, mocker):
        """path query param 缺失 → FastAPI 回 422"""
        mocker.patch("web.routers.showcase.get_db_path", return_value=single_setup["db_path"])
        mocker.patch("web.routers.showcase.load_config", return_value=single_setup["config"])

        response = client.get("/api/showcase/video")
        assert response.status_code == 422

    def test_serializer_consistency_list_vs_single(self, client, single_setup, mocker):
        """列表查詢與單筆查詢同一影片，has_cover / has_nfo / cover_url / path 完全相等"""
        mocker.patch("web.routers.showcase.get_db_path", return_value=single_setup["db_path"])
        mocker.patch("web.routers.showcase.load_config", return_value=single_setup["config"])

        list_resp = client.get("/api/showcase/videos")
        assert list_resp.status_code == 200
        list_video = list_resp.json()["videos"][0]

        single_resp = client.get(f"/api/showcase/video?path={single_setup['vid_uri']}")
        assert single_resp.status_code == 200
        single_video = single_resp.json()["video"]

        for field in ("path", "has_cover", "has_nfo", "cover_url", "number", "user_tags"):
            assert list_video[field] == single_video[field], (
                f"serializer 不一致欄位 {field}: list={list_video[field]!r} single={single_video[field]!r}"
            )
