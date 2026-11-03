"""189a-T8：BackfillState 共用容器（節流、兩旗標互不影響）。只用公開方法與公開屬性。"""

from __future__ import annotations

from core.ai_services.backfill_state import BackfillState


def test_persist_due_throttles_to_once_per_minute():
    """每次 AI 回應都想寫「上次成功」→ 一分鐘內只准寫一次，滿一分鐘才再寫。"""
    st = BackfillState(name="x")
    assert st.persist_due(0.0) is True
    assert st.last_persist_mono == 0.0
    assert st.persist_due(59.9) is False
    assert st.last_persist_mono == 0.0
    assert st.persist_due(60.0) is True
    assert st.last_persist_mono == 60.0


def test_hook_and_backfill_notify_flags_are_independent():
    """補完全庫開工不吃掉定時整理這輪的連不上通知（反之亦然）→ 側欄不多不少各一則。"""
    st = BackfillState(name="x")
    assert st.note_hook_failure() is True
    st.job_begin("build", reset_notified=True)
    assert st.note_failure() is True
    assert st.note_hook_failure() is False

    st.new_hook_round()
    assert st.note_failure() is False
    assert st.note_hook_failure() is True

    st.job_begin("build")  # 預設不清補完全庫旗標
    assert st.note_failure() is False
    st.job_begin("build", reset_notified=True)
    assert st.note_failure() is True
