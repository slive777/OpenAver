"""
test_focal_trigger.py — TASK-98b-T2: maybe_submit_video_focal helper 契約

TDD-lite（注入假 submit_focal / 假 repo / 假 gate，不真跑 pigo、不碰真 DB）：
- gate：有碼 → 不 submit；無碼 → submit
- exists guard：cover None / 檔不在 → 不 submit
- submit 參數：kind=='video'、ratio==0.71、cover_fs、video_path_uri 對齊
- commit lambda：呼叫 update_auto_focal(video_path_uri, focal_str)（fp 忽略）
- 防禦：helper 內任何例外都吞掉（不冒泡打斷 scrape/scan）
"""

from unittest.mock import patch, MagicMock


# ─── gate：有碼片零成本（不 submit） ────────────────────────────────────────

def test_censored_number_does_not_submit():
    with (
        patch("core.focal_trigger.requires_face_detection", return_value=False),
        patch("core.focal_trigger.submit_focal") as mock_submit,
        patch("core.focal_trigger.os.path.exists", return_value=True),
    ):
        from core.focal_trigger import maybe_submit_video_focal
        maybe_submit_video_focal("SONE-205", "SOD", "file:///x/SONE-205.mp4", "/x/SONE-205.jpg")

    mock_submit.assert_not_called()


# ─── gate：無碼片 → submit（參數契約） ──────────────────────────────────────

def test_uncensored_number_submits_with_correct_args():
    with (
        patch("core.focal_trigger.requires_face_detection", return_value=True),
        patch("core.focal_trigger.submit_focal") as mock_submit,
        patch("core.focal_trigger.os.path.exists", return_value=True),
        patch("core.focal_trigger.VideoRepository"),
    ):
        from core.focal_trigger import maybe_submit_video_focal, _DETECT_RATIO
        maybe_submit_video_focal("SIRO-1234", "", "file:///x/SIRO-1234.mp4", "/x/SIRO-1234.jpg")

    mock_submit.assert_called_once()
    args, kwargs = mock_submit.call_args
    # submit_focal(kind, id, fs_path, ratio, commit)
    assert args[0] == "video"
    assert args[1] == "file:///x/SIRO-1234.mp4"
    assert args[2] == "/x/SIRO-1234.jpg"
    assert args[3] == _DETECT_RATIO
    assert _DETECT_RATIO == 0.71


# ─── exists guard：cover None / 檔不在 → 不 submit ──────────────────────────

def test_cover_none_does_not_submit():
    with (
        patch("core.focal_trigger.requires_face_detection", return_value=True),
        patch("core.focal_trigger.submit_focal") as mock_submit,
    ):
        from core.focal_trigger import maybe_submit_video_focal
        maybe_submit_video_focal("SIRO-1234", "", "file:///x/SIRO-1234.mp4", None)

    mock_submit.assert_not_called()


def test_cover_missing_file_does_not_submit():
    with (
        patch("core.focal_trigger.requires_face_detection", return_value=True),
        patch("core.focal_trigger.submit_focal") as mock_submit,
        patch("core.focal_trigger.os.path.exists", return_value=False),
    ):
        from core.focal_trigger import maybe_submit_video_focal
        maybe_submit_video_focal("SIRO-1234", "", "file:///x/SIRO-1234.mp4", "/x/gone.jpg")

    mock_submit.assert_not_called()


# ─── commit lambda：綁定 video_path_uri，呼叫 update_auto_focal ──────────────

def test_commit_lambda_calls_update_auto_focal_with_uri():
    captured = {}

    def _capture_submit(kind, id, fs_path, ratio, commit):
        captured["commit"] = commit

    with (
        patch("core.focal_trigger.requires_face_detection", return_value=True),
        patch("core.focal_trigger.submit_focal", side_effect=_capture_submit),
        patch("core.focal_trigger.os.path.exists", return_value=True),
        patch("core.focal_trigger.VideoRepository") as MockRepo,
    ):
        from core.focal_trigger import maybe_submit_video_focal
        maybe_submit_video_focal("SIRO-1234", "", "file:///x/SIRO-1234.mp4", "/x/SIRO-1234.jpg")

        # 模擬 worker dequeue 完成後呼叫 commit(focal_str, fp)
        captured["commit"]("0.5,0.4", ("/x/SIRO-1234.jpg", 123, 456))

    MockRepo.return_value.update_auto_focal.assert_called_once_with(
        "file:///x/SIRO-1234.mp4", "0.5,0.4"
    )


# ─── 防禦：submit 拋例外也不冒泡（scrape/scan 不被打斷） ─────────────────────

def test_submit_failure_never_raises():
    with (
        patch("core.focal_trigger.requires_face_detection", return_value=True),
        patch("core.focal_trigger.submit_focal", side_effect=RuntimeError("boom")),
        patch("core.focal_trigger.os.path.exists", return_value=True),
        patch("core.focal_trigger.VideoRepository"),
    ):
        from core.focal_trigger import maybe_submit_video_focal
        # 不應拋出
        maybe_submit_video_focal("SIRO-1234", "", "file:///x/SIRO-1234.mp4", "/x/SIRO-1234.jpg")


def test_maker_none_treated_as_empty():
    """maker=None 不應 crash（helper 內 `maker or ""`）。"""
    with (
        patch("core.focal_trigger.requires_face_detection", return_value=False) as mock_gate,
        patch("core.focal_trigger.submit_focal"),
    ):
        from core.focal_trigger import maybe_submit_video_focal
        maybe_submit_video_focal("SONE-205", None, "file:///x/SONE-205.mp4", "/x/c.jpg")

    # gate 收到的 maker 為 "" 而非 None
    mock_gate.assert_called_once_with("SONE-205", "")


# ─── TASK-98b-T7: commit 寫入「注入的 db_path」而非預設 DB（P2 silent-miss 修） ──

def test_commit_writes_to_injected_db_path(temp_db):
    """注入非預設 db_path → 背景 commit 對該 DB 寫 auto_focal（真跑 commit 對真 tmp DB）。

    mutation 鎖：把 helper 的 commit 改回無參數 `VideoRepository()` → 寫到預設 DB、
    tmp DB row 的 auto_focal 不變 → 本測試 RED。
    """
    from core.database import VideoRepository, Video

    video_uri = "file:///scan/SIRO-9999.mp4"
    # 真 tmp DB 建一 row，auto_focal 初始為空。
    VideoRepository(temp_db).upsert_batch([
        Video(path=video_uri, number="SIRO-9999", maker="", cover_path="file:///scan/SIRO-9999.jpg")
    ])
    assert VideoRepository(temp_db).get_by_path(video_uri).auto_focal == ""

    captured = {}

    def _capture_submit(kind, id, fs_path, ratio, commit):
        captured["commit"] = commit  # 捕捉 commit callback，不真跑 pigo

    with (
        patch("core.focal_trigger.requires_face_detection", return_value=True),
        patch("core.focal_trigger.submit_focal", side_effect=_capture_submit),
        patch("core.focal_trigger.os.path.exists", return_value=True),
    ):
        from core.focal_trigger import maybe_submit_video_focal
        maybe_submit_video_focal(
            "SIRO-9999", "", video_uri, "/scan/SIRO-9999.jpg", db_path=temp_db
        )

    # 模擬 worker 完成後回呼 commit(focal_str, fp)
    captured["commit"]("0.5,0.5", None)

    # 斷言：寫入「注入的 tmp DB」，非預設 DB。
    assert VideoRepository(temp_db).get_by_path(video_uri).auto_focal == "0.5,0.5"
