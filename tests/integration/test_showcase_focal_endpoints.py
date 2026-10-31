"""
test_showcase_focal_endpoints.py — 98b-T4 / 99a-T1a 兩個 POST endpoint（TDD-lite）

- POST /api/showcase/video/detect-focal {path}   — 純預覽，**不寫 DB**（99a T1a）
- POST /api/showcase/video/save-focal {path, focal}   — 原子 mutator，存 auto_focal +
  crop_mode='manual'（99a T1a，取代已刪除的 /crop-mode）

**detect_focal 一律 mock（spy），絕不真跑 pigo。** 核心回歸鎖（Codex P0）：
detect_focal 收到的永遠是 row.cover_path 反解的封面 fs（.jpg），
絕非 body path（影片 .mp4 URI）。mutation「改回開 body path」必 RED。

`/api/showcase/video/crop-mode` 端點已於 99a-T1a 移除（見本檔
`TestCropModeRouteRemoved` 回歸鎖）。
"""

import pytest
from core.database import init_db, VideoRepository, Video
from core.focal import device_state
from core.focal.subprocess_runner import RunnerOutcome
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


# ============ crop-mode route removed（99a-T1a 回歸鎖）============


# ============ detect-focal ============

class TestDetectFocalEndpoint:
    def test_detects_cover_fs_not_body_path(self, client, focal_endpoint_setup, mocker):
        """Codex P0 回歸鎖：detect_focal 收到 row.cover_path 反解的封面 fs（.jpg），
        絕非 body path（.mp4）。mutation『改回開 body path』必 RED。"""
        _patch_db_and_config(mocker, focal_endpoint_setup)
        spy = mocker.patch("web.routers.showcase.run_detection", return_value=RunnerOutcome(kind="FOUND", focal=(0.42, 0.5)))

        resp = client.post("/api/showcase/video/detect-focal",
                           json={"path": focal_endpoint_setup["video_uri"]})
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert resp.json()["auto_focal"] == "0.4200,0.5000"
        # Codex PR#107 第二輪 P2：回應帶 row 當下的 cover_path（DB-key URI），供前端
        # 存為 mask session 的 expected_cover_path token，之後原樣帶回 /video/save-focal。
        assert resp.json()["cover_path"] == focal_endpoint_setup["cover_uri"]

        spy.assert_called_once()
        called_path = spy.call_args.args[0]
        # ★ 不變式：偵測的是封面 fs，不是 body 的 .mp4 URI/path
        assert called_path == focal_endpoint_setup["cover_fs"]
        assert called_path.endswith(".jpg")
        assert not called_path.endswith(".mp4")
        assert "SONE-001.mp4" not in called_path


    def test_manual_detect_wall_budget_returns_too_slow_without_real_wait(
        self, client, focal_endpoint_setup, mocker,
    ):
        _patch_db_and_config(mocker, focal_endpoint_setup)

        class TimeoutFuture:
            def __init__(self):
                self.timeout = None

            def result(self, timeout=None):
                self.timeout = timeout
                raise TimeoutError()

        class TimeoutExecutor:
            def __init__(self):
                self.future = TimeoutFuture()
                self.submitted = False

            def submit(self, fn, *args, **kwargs):
                self.submitted = True
                return self.future

        fake_executor = TimeoutExecutor()
        mocker.patch("web.routers.showcase._manual_detect_executor", fake_executor, create=True)
        mocker.patch(
            "web.routers.showcase.run_detection",
            return_value=RunnerOutcome(kind="FOUND", focal=(0.42, 0.5)),
        )
        record = mocker.patch.object(device_state, "record_manual_outcome")

        resp = client.post("/api/showcase/video/detect-focal",
                           json={"path": focal_endpoint_setup["video_uri"]})
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert resp.json()["auto_focal"] == ""
        assert resp.json()["cover_path"] == focal_endpoint_setup["cover_uri"]
        assert resp.json()["reason"] == "still_detecting"
        assert fake_executor.submitted
        from web.routers import showcase
        assert fake_executor.future.timeout == showcase._MANUAL_DETECT_WALL_BUDGET_S == 5.0
        record.assert_not_called()


    def test_disabled_short_circuits_before_runner_lock(self, client, focal_endpoint_setup, mocker):
        """關掉自動對焦後，點裁切工具不得進 run_detection 全域鎖排隊。

        端點層用 is_disabled_in(config) 短路；本測試餵真的 focal_device config。

        stub 刻意回一個**看得出來的** focal（0.99）而不是拋例外：拋例外會被端點的
        `except Exception` 收成 500，紅字只剩 `assert 500 == 200`——那跟「端點因為
        別的原因炸了」長得一模一樣，診斷力是零。回可辨識值的話，短路一旦被拿掉，
        紅字直接是 `assert '0.9900,0.9900' == ''`，一眼看得出偵測真的跑了。
        `assert_not_called()` 再補上「一次都不准呼叫」這個不變式本身。
        """
        # 選 set_by_user=True：使用者關掉對焦與版本無關，is_disabled_in 直接讀 disabled，
        # 不依賴 judged_at_version == VERSION（避免 lazy-reset 把測試讀成「未停用」）。
        disabled_config = {
            **focal_endpoint_setup["config"],
            "focal_device": {
                "disabled": True,
                "set_by_user": True,
                "judged_at_version": "",
                "consecutive_timeout_count": 0,
            },
        }
        _patch_db_and_config(mocker, focal_endpoint_setup, config=disabled_config)
        spy = mocker.patch(
            "web.routers.showcase.run_detection",
            return_value=RunnerOutcome(kind="FOUND", focal=(0.99, 0.99)),
        )

        resp = client.post("/api/showcase/video/detect-focal",
                           json={"path": focal_endpoint_setup["video_uri"]})
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["auto_focal"] == "", "短路被拿掉了：偵測真的跑了並回了座標"
        assert body["reason"] == "device_disabled"
        assert body["cover_path"] == focal_endpoint_setup["cover_uri"]
        spy.assert_not_called()


    def test_reason_empty_on_found(self, client, focal_endpoint_setup, mocker):
        """reason 值域：正常 FOUND → ''。"""
        _patch_db_and_config(mocker, focal_endpoint_setup)
        mocker.patch(
            "web.routers.showcase.run_detection",
            return_value=RunnerOutcome(kind="FOUND", focal=(0.42, 0.5)),
        )
        resp = client.post("/api/showcase/video/detect-focal",
                           json={"path": focal_endpoint_setup["video_uri"]})
        assert resp.status_code == 200
        assert resp.json()["reason"] == ""


    @pytest.mark.parametrize("abandoned_reason", ["crashed"])
    def test_reason_failed_for_non_timeout_abandoned(
        self, client, focal_endpoint_setup, mocker, abandoned_reason,
    ):
        """reason 值域：startup_timeout／crashed／circuit_open → 'failed'（不得變 too_slow*）。"""
        _patch_db_and_config(mocker, focal_endpoint_setup)
        mocker.patch(
            "web.routers.showcase.run_detection",
            return_value=RunnerOutcome(kind="ABANDONED", reason=abandoned_reason),
        )
        resp = client.post("/api/showcase/video/detect-focal",
                           json={"path": focal_endpoint_setup["video_uri"]})
        assert resp.status_code == 200
        assert resp.json()["reason"] == "failed"
        assert resp.json()["reason"] not in ("too_slow", "too_slow_auto_disabled")


    def test_manual_timeout_does_not_call_notification_sink(
        self, client, focal_endpoint_setup, mocker, tmp_path, monkeypatch,
    ):
        """前景轉態不呼叫 notification sink——拋例外的 sink 全程未被呼叫，端點仍 200。"""
        import core.config as core_config
        from core.config import save_config
        from core.focal import device_state
        from core.version import VERSION

        _patch_db_and_config(mocker, focal_endpoint_setup)
        config_path = tmp_path / "config.json"
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")
        save_config({
            "focal_device": {
                "disabled": False,
                "consecutive_timeout_count": 0,
                "judged_at_version": VERSION,
                "set_by_user": False,
            }
        })

        calls = []

        def _boom_sink(*args, **kwargs):
            calls.append((args, kwargs))
            raise RuntimeError("sink must not be called on manual path")

        monkeypatch.setattr(device_state, "_notification_sink", _boom_sink)

        def fake_run(
            fs_path, ratio, *, job_key, timeout_s, pre_spawn_check=None, on_outcome=None,
            external_profile=None,
        ):
            outcome = RunnerOutcome(kind="ABANDONED", reason="detect_timeout")
            if on_outcome is not None:
                on_outcome(outcome)
            return outcome

        mocker.patch("web.routers.showcase.run_detection", side_effect=fake_run)
        resp = client.post("/api/showcase/video/detect-focal",
                           json={"path": focal_endpoint_setup["video_uri"]})
        assert resp.status_code == 200
        assert resp.json()["reason"] == "too_slow_auto_disabled"
        assert calls == []
        assert device_state.is_disabled() is True


    def test_interleaved_set_by_user_yields_too_slow_not_auto_disabled(
        self, client, focal_endpoint_setup, mocker, tmp_path, monkeypatch,
    ):
        """交錯 oracle：偵測期間 set_by_user 變 True → reason=too_slow，設定仍開著。"""
        import core.config as core_config
        from core.config import save_config
        from core.focal import device_state
        from core.version import VERSION

        _patch_db_and_config(mocker, focal_endpoint_setup)
        config_path = tmp_path / "config.json"
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")
        save_config({
            "focal_device": {
                "disabled": False,
                "consecutive_timeout_count": 0,
                "judged_at_version": VERSION,
                "set_by_user": False,
            }
        })

        def fake_run(
            fs_path, ratio, *, job_key, timeout_s, pre_spawn_check=None, on_outcome=None,
            external_profile=None,
        ):
            # 模擬：入口讀到 set_by_user=false，偵測中途使用者在設定頁打開
            device_state.set_disabled_by_user(False)
            outcome = RunnerOutcome(kind="ABANDONED", reason="detect_timeout")
            if on_outcome is not None:
                on_outcome(outcome)
            return outcome

        mocker.patch("web.routers.showcase.run_detection", side_effect=fake_run)
        resp = client.post("/api/showcase/video/detect-focal",
                           json={"path": focal_endpoint_setup["video_uri"]})
        assert resp.status_code == 200
        assert resp.json()["reason"] == "too_slow"
        assert device_state.is_disabled() is False


# ============ /video/save-focal mutator（99a-T1a）============

class TestManualFocalEndpoint:
    def test_valid_focal_atomic_write(self, client, focal_endpoint_setup, mocker):
        """成功後 auto_focal 與 crop_mode='manual' 同時反映在 DB（單一 UPDATE 原子寫）。
        expected_cover_path 對上目前 row.cover_path（fixture 的 cover_uri）→ 正常寫入。"""
        _patch_db_and_config(mocker, focal_endpoint_setup)
        resp = client.post("/api/showcase/video/save-focal",
                           json={"path": focal_endpoint_setup["video_uri"], "focal": "0.3,0.6",
                                 "expected_cover_path": focal_endpoint_setup["cover_uri"]})
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        repo = VideoRepository(focal_endpoint_setup["db_path"])
        result = repo.get_by_path(focal_endpoint_setup["video_uri"])
        assert result.auto_focal == "0.3000,0.6000"   # 正規化（format_focal(parse_focal(...))）
        assert result.crop_mode == "manual"


    def test_cover_path_mismatch_409_db_unchanged(self, client, focal_endpoint_setup, mocker):
        """核心回歸鎖（Codex PR#107 第二輪 P2）：expected_cover_path 與目前 row.cover_path
        不符（使用者開遮罩期間封面被 rescan/rescrape 換掉）→ 409、DB 完全不變（不寫
        auto_focal、不蓋 crop_mode='manual'）。mutation：把
        `VideoRepository.update_manual_focal` 呼叫改用真正的目前 cover_path（而非
        request 帶來的 expected 值）會讓這條 RED（守衛被繞過，寫入成功）。"""
        _patch_db_and_config(mocker, focal_endpoint_setup)
        stale_cover = to_file_uri(focal_endpoint_setup["video_dir"] + "/old-cover.jpg", {})
        before = VideoRepository(focal_endpoint_setup["db_path"]).get_by_path(
            focal_endpoint_setup["video_uri"])

        resp = client.post("/api/showcase/video/save-focal",
                           json={"path": focal_endpoint_setup["video_uri"], "focal": "0.3,0.6",
                                 "expected_cover_path": stale_cover})
        assert resp.status_code == 409
        assert resp.json()["success"] is False
        assert resp.json()["error"]

        after = VideoRepository(focal_endpoint_setup["db_path"]).get_by_path(
            focal_endpoint_setup["video_uri"])
        assert after.auto_focal == before.auto_focal
        assert after.crop_mode == before.crop_mode
        assert after.crop_mode != "manual"


    def test_invalid_focal_format_400_db_untouched(self, client, focal_endpoint_setup, mocker):
        """非法 focal 格式 → 400 固定字串、DB 完全不碰（連 get_by_path 都不需呼叫，
        格式驗證在 scope 檢查之前）。"""
        _patch_db_and_config(mocker, focal_endpoint_setup)
        spy = mocker.patch("web.routers.showcase.VideoRepository.get_by_path")
        resp = client.post("/api/showcase/video/save-focal",
                           json={"path": focal_endpoint_setup["video_uri"], "focal": "abc",
                                 "expected_cover_path": focal_endpoint_setup["cover_uri"]})
        assert resp.status_code == 400
        assert resp.json()["success"] is False
        assert resp.json()["error"]
        spy.assert_not_called()


    def test_out_of_scope_403_db_unchanged(self, client, focal_endpoint_setup, mocker, tmp_path):
        """path 存在但 out-of-scope（不在任何 configured dir 下）→ 403、DB 不變。

        mutation 驗證（Codex P1-1）：拔掉 scope guard 後 out-of-scope 也能寫入
        → 必須變 RED。"""
        other_dir = tmp_path / "elsewhere"
        other_dir.mkdir()
        oos_config = {
            "gallery": {
                "directories": [{"path": str(other_dir), "readonly": False, "output_path": ""}],
                "path_mappings": {},
            },
        }
        _patch_db_and_config(mocker, focal_endpoint_setup, config=oos_config)
        before = VideoRepository(focal_endpoint_setup["db_path"]).get_by_path(
            focal_endpoint_setup["video_uri"])
        resp = client.post("/api/showcase/video/save-focal",
                           json={"path": focal_endpoint_setup["video_uri"], "focal": "0.3,0.6",
                                 "expected_cover_path": focal_endpoint_setup["cover_uri"]})
        assert resp.status_code == 403
        assert resp.json()["success"] is False
        after = VideoRepository(focal_endpoint_setup["db_path"]).get_by_path(
            focal_endpoint_setup["video_uri"])
        assert after.auto_focal == before.auto_focal
        assert after.crop_mode == before.crop_mode

    def test_readonly_source_in_scope_allowed_write(self, client, focal_endpoint_setup, mocker):
        """path 存在、in-scope、來源標記 readonly → 仍放行寫入（D4/CD-7，刻意與 98b
        舊行為分歧：唯讀不擋手動存）。"""
        ro_config = {
            "gallery": {
                "directories": [{"path": focal_endpoint_setup["video_dir"],
                                 "readonly": True, "output_path": ""}],
                "path_mappings": {},
            },
        }
        _patch_db_and_config(mocker, focal_endpoint_setup, config=ro_config)
        resp = client.post("/api/showcase/video/save-focal",
                           json={"path": focal_endpoint_setup["video_uri"], "focal": "0.3,0.6",
                                 "expected_cover_path": focal_endpoint_setup["cover_uri"]})
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        repo = VideoRepository(focal_endpoint_setup["db_path"])
        result = repo.get_by_path(focal_endpoint_setup["video_uri"])
        assert result.auto_focal == "0.3000,0.6000"
        assert result.crop_mode == "manual"
