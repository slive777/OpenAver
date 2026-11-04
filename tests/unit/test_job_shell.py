"""JobShell 鎖殼（189a-T9a）：承接旗標的最小單執行緒走一遍。"""
from core.ai_services.job_shell import JobShell


def test_handoff_flag_left_while_job_runs_then_consumed_once():
    shell = JobShell()

    with shell.state_lock:
        assert shell.schedule_handoff() is True  # 沒有 job 在跑 → 自己開
        shell.begin_locked()
    assert shell.is_running()
    assert shell.rerun is False

    with shell.state_lock:
        assert shell.schedule_handoff() is False  # 有 job 在跑 → 留旗標
    assert shell.rerun is True

    with shell.state_lock:
        assert shell.consume_handoff_locked() is True
        assert shell.consume_handoff_locked() is False  # 只消化一次

    with shell.state_lock:
        shell.rerun = True
        shell.release_locked()
    assert not shell.is_running()
    assert shell.rerun is False

    with shell.state_lock:
        assert shell.schedule_handoff() is True
        shell.begin_locked()
        assert shell.rerun is False
        shell.rerun = True
    shell.request_stop()
    assert shell.rerun is False
    assert shell.stop.is_set()
    assert shell.is_running()
