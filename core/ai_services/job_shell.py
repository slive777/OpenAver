"""背景補跑 job 的共用鎖殼（189a-T9a，CD-189a-11②／-12）。

一個 ``JobShell`` 實例收攏「工作鎖／狀態短鎖／停止旗標／承接旗標／起 thread」。本模組不 import
任何功能模組、不放模組層單例；實例只活在各功能模組（``_SHELL = JobShell()``）。

所有屬性與方法每次呼叫**當下**讀 ``self.<屬性>``，不快取、不存任何功能模組的函式（回呼由
呼叫端現場建立並傳入），所以測試 ``setattr`` 換掉 ``state_lock``／``stop``／``job_lock``／
``rerun`` 後下一次呼叫立即生效。「持 state_lock」＝呼叫端已在 ``with <shell>.state_lock:`` 內，
殼內不再取；對 ``state_lock`` 只用 ``with``。
"""
from __future__ import annotations

import threading
from typing import Callable, Optional


class JobShell:
    def __init__(self) -> None:
        self.job_lock = threading.Lock()
        self.state_lock = threading.Lock()
        self.stop = threading.Event()
        self.rerun = False

    def try_acquire(self) -> bool:
        """持 state_lock。不阻塞取工作鎖。"""
        return self.job_lock.acquire(blocking=False)

    def schedule_handoff(self) -> bool:
        """持 state_lock。取得工作鎖回 True（呼叫端自己開 job）；否則留承接旗標回 False。"""
        if self.try_acquire():
            return True
        self.rerun = True
        return False

    def begin_locked(self) -> None:
        """持 state_lock 且已取得 job_lock。"""
        self.stop.clear()
        self.rerun = False

    def consume_handoff_locked(self) -> bool:
        """持 state_lock。承接旗標為真 → 清掉並回 True。"""
        if self.rerun:
            self.rerun = False
            return True
        return False

    def release_locked(self, before_release: Optional[Callable[[], None]] = None) -> None:
        """持 state_lock 且持 job_lock。順序固定：清承接 → before_release → 放工作鎖。"""
        self.rerun = False
        if before_release is not None:
            before_release()
        self.job_lock.release()

    def release_unlaunched(self, before_release: Optional[Callable[[], None]] = None) -> None:
        with self.state_lock:
            self.release_locked(before_release)

    def abort_acquire(self) -> None:
        """持 state_lock。取得工作鎖後、不開工時直接放掉（不碰承接旗標）。"""
        self.job_lock.release()

    def request_stop(self) -> None:
        with self.state_lock:
            self.stop.set()
            self.rerun = False

    def is_running(self) -> bool:
        return self.job_lock.locked()

    def start_thread(self, target: Callable[..., None], args: tuple = (), *,
                     name: str, on_failure: Callable[[], None]) -> None:
        """不持 state_lock 呼叫。``start()`` 失敗 → 先 ``on_failure()`` 再原樣外拋。"""
        t = threading.Thread(target=target, args=args, name=name, daemon=True)
        try:
            t.start()
        except BaseException:
            on_failure()
            raise
