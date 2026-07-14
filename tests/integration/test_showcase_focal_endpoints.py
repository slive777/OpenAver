"""
test_showcase_focal_endpoints.py — 98b-T4 兩個 POST endpoint（TDD-lite）

- POST /api/showcase/video/crop-mode  {path, mode}
- POST /api/showcase/video/detect-focal {path}

**detect_focal 一律 mock（spy），絕不真跑 pigo。** 核心回歸鎖（Codex P0）：
detect_focal 收到的永遠是 row.cover_path 反解的封面 fs（.jpg），
絕非 body path（影片 .mp4 URI）。mutation「改回開 body path」必 RED。
"""

import pytest
from core.database import init_db, VideoRepository, Video
from core.path_utils import to_file_uri


@pytest.fixture
def focal_endpoint_setup(tmp_path):
    """臨時 DB：一片有真實封面 .jpg（供 os.path.isfile 通過），一片封面檔缺。

    回傳 dict：db_path / video_uri / cover_uri / cover_fs / video_no_cover_uri /
    config（configured dir = video_dir，非唯讀）。
    """
    video_dir = tmp_path / "videos"
    video_dir.mkdir()

    # 真實封面檔（內容不重要——detect_focal 被 mock，不會真讀）
    cover_file = video_dir / "SONE-001-cover.jpg"
    cover_file.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg")

    video_uri = to_file_uri(str(video_dir / "SONE-001.mp4"), {})
    cover_uri = to_file_uri(str(cover_file), {})
    cover_fs = str(cover_file)

    video_no_cover_uri = to_file_uri(str(video_dir / "NOCOVER-001.mp4"), {})
    missing_cover_uri = to_file_uri(str(video_dir / "does-not-exist.jpg"), {})

    db_path = tmp_path / "focal_endpoints.db"
    init_db(db_path)
    repo = VideoRepository(db_path)
    repo.upsert_batch([
        Video(
            path=video_uri,
            number="SONE-001",
            title="With Cover",
            cover_path=cover_uri,
            crop_mode="default",
            auto_focal="",
        ),
        Video(
            path=video_no_cover_uri,
            number="NOCOVER-001",
            title="Cover File Missing",
            cover_path=missing_cover_uri,   # DB 有值但檔案不存在
            crop_mode="default",
            auto_focal="",
        ),
    ])

    config = {
        "gallery": {
            "directories": [{"path": str(video_dir), "readonly": False, "output_path": ""}],
            "path_mappings": {},
        },
    }

    return {
        "db_path": db_path,
        "video_uri": video_uri,
        "cover_uri": cover_uri,
        "cover_fs": cover_fs,
        "video_no_cover_uri": video_no_cover_uri,
        "video_dir": str(video_dir),
        "config": config,
    }


def _patch_db_and_config(mocker, setup, config=None):
    mocker.patch("web.routers.showcase.get_db_path", return_value=setup["db_path"])
    mocker.patch("web.routers.showcase.load_config", return_value=config or setup["config"])


# ============ crop-mode ============

class TestCropModeEndpoint:
    def test_valid_mode_updates_db(self, client, focal_endpoint_setup, mocker):
        _patch_db_and_config(mocker, focal_endpoint_setup)
        spy = mocker.patch(
            "web.routers.showcase.VideoRepository.update_crop_mode",
            return_value=True,
        )
        resp = client.post("/api/showcase/video/crop-mode",
                           json={"path": focal_endpoint_setup["video_uri"], "mode": "auto"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        spy.assert_called_once_with(focal_endpoint_setup["video_uri"], "auto")

    def test_valid_mode_persists(self, client, focal_endpoint_setup, mocker):
        """整合：真的寫進 DB（不 mock repo），crop_mode 由 default → auto。"""
        _patch_db_and_config(mocker, focal_endpoint_setup)
        resp = client.post("/api/showcase/video/crop-mode",
                           json={"path": focal_endpoint_setup["video_uri"], "mode": "auto"})
        assert resp.status_code == 200
        repo = VideoRepository(focal_endpoint_setup["db_path"])
        assert repo.get_by_path(focal_endpoint_setup["video_uri"]).crop_mode == "auto"

    def test_invalid_mode_rejected_repo_untouched(self, client, focal_endpoint_setup, mocker):
        _patch_db_and_config(mocker, focal_endpoint_setup)
        spy = mocker.patch(
            "web.routers.showcase.VideoRepository.update_crop_mode",
            return_value=True,
        )
        resp = client.post("/api/showcase/video/crop-mode",
                           json={"path": focal_endpoint_setup["video_uri"], "mode": "foo"})
        assert resp.status_code == 400
        assert resp.json()["success"] is False
        assert resp.json()["error"]   # 固定中文字串（非空）
        spy.assert_not_called()


# ============ detect-focal ============

class TestDetectFocalEndpoint:
    def test_detects_cover_fs_not_body_path(self, client, focal_endpoint_setup, mocker):
        """Codex P0 回歸鎖：detect_focal 收到 row.cover_path 反解的封面 fs（.jpg），
        絕非 body path（.mp4）。mutation『改回開 body path』必 RED。"""
        _patch_db_and_config(mocker, focal_endpoint_setup)
        spy = mocker.patch("web.routers.showcase.detect_focal", return_value=(0.42, 0.5))

        resp = client.post("/api/showcase/video/detect-focal",
                           json={"path": focal_endpoint_setup["video_uri"]})
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert resp.json()["auto_focal"] == "0.4200,0.5000"

        spy.assert_called_once()
        called_path = spy.call_args.args[0]
        # ★ 不變式：偵測的是封面 fs，不是 body 的 .mp4 URI/path
        assert called_path == focal_endpoint_setup["cover_fs"]
        assert called_path.endswith(".jpg")
        assert not called_path.endswith(".mp4")
        assert "SONE-001.mp4" not in called_path

    def test_detect_persists_auto_focal(self, client, focal_endpoint_setup, mocker):
        _patch_db_and_config(mocker, focal_endpoint_setup)
        mocker.patch("web.routers.showcase.detect_focal", return_value=(0.42, 0.5))
        client.post("/api/showcase/video/detect-focal",
                    json={"path": focal_endpoint_setup["video_uri"]})
        repo = VideoRepository(focal_endpoint_setup["db_path"])
        assert repo.get_by_path(focal_endpoint_setup["video_uri"]).auto_focal == "0.4200,0.5000"

    def test_non_db_path_404_no_detect(self, client, focal_endpoint_setup, mocker):
        _patch_db_and_config(mocker, focal_endpoint_setup)
        spy = mocker.patch("web.routers.showcase.detect_focal", return_value=(0.4, 0.5))
        bogus = to_file_uri(focal_endpoint_setup["video_dir"] + "/not-in-db.mp4", {})
        resp = client.post("/api/showcase/video/detect-focal", json={"path": bogus})
        assert resp.status_code == 404
        assert resp.json()["success"] is False
        spy.assert_not_called()

    def test_readonly_source_rejected(self, client, focal_endpoint_setup, mocker):
        """來源標 readonly → 拒（唯讀無法寫回，force-detect 無意義）。"""
        ro_config = {
            "gallery": {
                "directories": [{"path": focal_endpoint_setup["video_dir"],
                                 "readonly": True, "output_path": ""}],
                "path_mappings": {},
            },
        }
        _patch_db_and_config(mocker, focal_endpoint_setup, config=ro_config)
        spy = mocker.patch("web.routers.showcase.detect_focal", return_value=(0.4, 0.5))
        resp = client.post("/api/showcase/video/detect-focal",
                           json={"path": focal_endpoint_setup["video_uri"]})
        assert resp.status_code == 403
        assert resp.json()["success"] is False
        spy.assert_not_called()

    def test_out_of_scope_rejected(self, client, focal_endpoint_setup, mocker, tmp_path):
        """configured dir 不含影片所在夾 → scope 外 → 拒。"""
        other_dir = tmp_path / "elsewhere"
        other_dir.mkdir()
        oos_config = {
            "gallery": {
                "directories": [{"path": str(other_dir), "readonly": False, "output_path": ""}],
                "path_mappings": {},
            },
        }
        _patch_db_and_config(mocker, focal_endpoint_setup, config=oos_config)
        spy = mocker.patch("web.routers.showcase.detect_focal", return_value=(0.4, 0.5))
        resp = client.post("/api/showcase/video/detect-focal",
                           json={"path": focal_endpoint_setup["video_uri"]})
        assert resp.status_code == 403
        spy.assert_not_called()

    def test_cover_file_missing_fixed_string_no_crash(self, client, focal_endpoint_setup, mocker):
        """DB 有 cover_path 但檔案不存在 → 固定字串、不崩、不呼 detect_focal。"""
        _patch_db_and_config(mocker, focal_endpoint_setup)
        spy = mocker.patch("web.routers.showcase.detect_focal", return_value=(0.4, 0.5))
        resp = client.post("/api/showcase/video/detect-focal",
                           json={"path": focal_endpoint_setup["video_no_cover_uri"]})
        assert resp.status_code == 400
        assert resp.json()["success"] is False
        assert resp.json()["error"]
        spy.assert_not_called()

    def test_no_face_saves_empty_string(self, client, focal_endpoint_setup, mocker):
        """detect_focal 回 None（無臉）→ auto_focal='' 存回、不崩。"""
        _patch_db_and_config(mocker, focal_endpoint_setup)
        mocker.patch("web.routers.showcase.detect_focal", return_value=None)
        resp = client.post("/api/showcase/video/detect-focal",
                           json={"path": focal_endpoint_setup["video_uri"]})
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert resp.json()["auto_focal"] == ""
        repo = VideoRepository(focal_endpoint_setup["db_path"])
        assert repo.get_by_path(focal_endpoint_setup["video_uri"]).auto_focal == ""
