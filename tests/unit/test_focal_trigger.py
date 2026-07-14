"""
test_focal_trigger.py — TASK-98b-T2 / 99b-T2: maybe_submit_video_focal helper 契約

TDD-lite（注入假 submit_focal / 假 repo / 假 gate，不真跑 pigo、不碰真 DB）：
- gate：有碼 → 不 submit；無碼 → submit
- exists guard：cover None / 檔不在 → 不 submit
- submit 參數：kind=='video'、ratio==0.71、cover_fs、video_path_uri 對齊
- commit lambda：呼叫 update_auto_focal(video_path_uri, focal_str, cover_path_uri)（fp 忽略）
- 防禦：helper 內任何例外都吞掉（不冒泡打斷 scrape/scan）
- 99b-T2 CD-99b-9：cover_path_uri 為 keyword-only 必填，省略即 TypeError（fail-closed）
"""

from unittest.mock import patch, MagicMock

import pytest


# ─── gate：有碼片零成本（不 submit） ────────────────────────────────────────

def test_censored_number_does_not_submit():
    with (
        patch("core.focal_trigger.requires_face_detection", return_value=False),
        patch("core.focal_trigger.submit_focal") as mock_submit,
        patch("core.focal_trigger.os.path.exists", return_value=True),
    ):
        from core.focal_trigger import maybe_submit_video_focal
        maybe_submit_video_focal(
            "SONE-205", "SOD", "file:///x/SONE-205.mp4", "/x/SONE-205.jpg",
            cover_path_uri="file:///x/SONE-205.jpg",
        )

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
        maybe_submit_video_focal(
            "SIRO-1234", "", "file:///x/SIRO-1234.mp4", "/x/SIRO-1234.jpg",
            cover_path_uri="file:///x/SIRO-1234.jpg",
        )

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
        maybe_submit_video_focal(
            "SIRO-1234", "", "file:///x/SIRO-1234.mp4", None,
            cover_path_uri="file:///x/SIRO-1234.jpg",
        )

    mock_submit.assert_not_called()


def test_cover_missing_file_does_not_submit():
    with (
        patch("core.focal_trigger.requires_face_detection", return_value=True),
        patch("core.focal_trigger.submit_focal") as mock_submit,
        patch("core.focal_trigger.os.path.exists", return_value=False),
    ):
        from core.focal_trigger import maybe_submit_video_focal
        maybe_submit_video_focal(
            "SIRO-1234", "", "file:///x/SIRO-1234.mp4", "/x/gone.jpg",
            cover_path_uri="file:///x/gone.jpg",
        )

    mock_submit.assert_not_called()


# ─── commit lambda：綁定 video_path_uri + cover_path_uri，呼叫 update_auto_focal ──

def test_commit_lambda_calls_update_auto_focal_with_uri_and_expected_cover():
    """99b-T2：commit lambda 必須把 cover_path_uri（submit 當下捕獲）一併穿進
    update_auto_focal 的 expected_cover_path 第三參——mutation：把 commit lambda
    改回只傳 (video_path_uri, focal_str) 兩參 → 本測 RED（call args 缺第三參）。"""
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
        maybe_submit_video_focal(
            "SIRO-1234", "", "file:///x/SIRO-1234.mp4", "/x/SIRO-1234.jpg",
            cover_path_uri="file:///x/SIRO-1234.jpg",
        )

        # 模擬 worker dequeue 完成後呼叫 commit(focal_str, fp)
        captured["commit"]("0.5,0.4", ("/x/SIRO-1234.jpg", 123, 456))

    MockRepo.return_value.update_auto_focal.assert_called_once_with(
        "file:///x/SIRO-1234.mp4", "0.5,0.4", "file:///x/SIRO-1234.jpg"
    )


def test_commit_lambda_captures_cover_path_uri_at_submit_time_not_commit_time():
    """CD-99b-9/latest-wins 精神：兩次 submit（不同 cover_path_uri）各自的 commit
    closure 帶各自捕獲的值，互不干擾——即使晚 submit 的先被呼叫，早 submit 的
    commit 仍用它自己當下的 cover_path_uri（非某個共享的最新變數）。"""
    commits = []

    def _capture_submit(kind, id, fs_path, ratio, commit):
        commits.append(commit)

    with (
        patch("core.focal_trigger.requires_face_detection", return_value=True),
        patch("core.focal_trigger.submit_focal", side_effect=_capture_submit),
        patch("core.focal_trigger.os.path.exists", return_value=True),
        patch("core.focal_trigger.VideoRepository") as MockRepo,
    ):
        from core.focal_trigger import maybe_submit_video_focal
        maybe_submit_video_focal(
            "SIRO-1234", "", "file:///x/SIRO-1234.mp4", "/x/A.jpg",
            cover_path_uri="file:///x/A.jpg",
        )
        maybe_submit_video_focal(
            "SIRO-1234", "", "file:///x/SIRO-1234.mp4", "/x/B.jpg",
            cover_path_uri="file:///x/B.jpg",
        )

        assert len(commits) == 2
        commits[0]("0.1,0.1", None)  # 舊 job（A）先 commit
        commits[1]("0.2,0.2", None)  # 新 job（B）後 commit

    calls = MockRepo.return_value.update_auto_focal.call_args_list
    assert calls[0].args == ("file:///x/SIRO-1234.mp4", "0.1,0.1", "file:///x/A.jpg")
    assert calls[1].args == ("file:///x/SIRO-1234.mp4", "0.2,0.2", "file:///x/B.jpg")


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
        maybe_submit_video_focal(
            "SIRO-1234", "", "file:///x/SIRO-1234.mp4", "/x/SIRO-1234.jpg",
            cover_path_uri="file:///x/SIRO-1234.jpg",
        )


def test_maker_none_treated_as_empty():
    """maker=None 不應 crash（helper 內 `maker or ""`）。"""
    with (
        patch("core.focal_trigger.requires_face_detection", return_value=False) as mock_gate,
        patch("core.focal_trigger.submit_focal"),
    ):
        from core.focal_trigger import maybe_submit_video_focal
        maybe_submit_video_focal(
            "SONE-205", None, "file:///x/SONE-205.mp4", "/x/c.jpg",
            cover_path_uri="file:///x/c.jpg",
        )

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
    cover_uri = "file:///scan/SIRO-9999.jpg"
    # 真 tmp DB 建一 row，auto_focal 初始為空。
    VideoRepository(temp_db).upsert_batch([
        Video(path=video_uri, number="SIRO-9999", maker="", cover_path=cover_uri)
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
            "SIRO-9999", "", video_uri, "/scan/SIRO-9999.jpg",
            cover_path_uri=cover_uri, db_path=temp_db,
        )

    # 模擬 worker 完成後回呼 commit(focal_str, fp)
    captured["commit"]("0.5,0.5", None)

    # 斷言：寫入「注入的 tmp DB」，非預設 DB。
    assert VideoRepository(temp_db).get_by_path(video_uri).auto_focal == "0.5,0.5"


# ─── 99b-T2 CD-99b-9: cover_path_uri 為 keyword-only 必填（fail-closed） ────────

def test_cover_path_uri_is_required_keyword_only():
    """省略 cover_path_uri → TypeError（不可靜默用某個預設值）——CD-99b-9 要求必填，
    不留 Optional=None 的 fail-open 門。"""
    from core.focal_trigger import maybe_submit_video_focal

    with pytest.raises(TypeError):
        maybe_submit_video_focal("SIRO-1234", "", "file:///x/SIRO-1234.mp4", "/x/SIRO-1234.jpg")


def test_cover_path_uri_cannot_be_passed_positionally():
    """cover_path_uri 是 keyword-only（`*,` 之後）——位置傳入第 5 個參數必須 TypeError，
    不可被誤當成別的位置參數靜默吃下。"""
    from core.focal_trigger import maybe_submit_video_focal

    with pytest.raises(TypeError):
        maybe_submit_video_focal(
            "SIRO-1234", "", "file:///x/SIRO-1234.mp4", "/x/SIRO-1234.jpg",
            "file:///x/SIRO-1234.jpg",
        )
