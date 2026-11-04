"""AI 補跑狀態的共用容器（189a-T8，CD-189a-11①／-12）。

標籤／相似／人臉三份記憶體觀察值逐字相同的部分收在這裡：``app_meta`` 讀寫、60 秒節流、
連不上旗標、通知 sink 與去重旗標、job 計數。實例只活在三個 ``*_state`` 模組（各一個
``_STATE``）；本模組不持有任何可變單例。

``meta_get``／``meta_set``／``meta_delete`` 是無狀態模組函式，不放進類別：各 ``*_state``
以模組全域薄函式包它，測試才攔得住（BE-TEST-29）。只 import ``core.*``（BE-LINT-09）。
"""

from __future__ import annotations

import threading
from contextlib import closing
from typing import Callable, Optional

from core.database import connection
from core.logger import get_logger

logger = get_logger(__name__)

PERSIST_INTERVAL_S = 60.0


def _default_new_job(kind: Optional[str] = None) -> dict:
    return {"kind": kind, "done": 0, "outcome": None}


# ── app_meta（無狀態）────────────────────────────────────────────────────────

def meta_get(key: str) -> Optional[str]:
    """Read one ``app_meta`` value (None if absent)."""
    with closing(connection.get_connection()) as conn:
        row = conn.execute("SELECT value FROM app_meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def meta_set(key: str, value: str) -> None:
    """Upsert one ``app_meta`` value."""
    with closing(connection.get_connection()) as conn:
        conn.execute("INSERT OR REPLACE INTO app_meta (key, value) VALUES (?, ?)", (key, value))
        conn.commit()


def meta_delete(key: str) -> None:
    """Delete one ``app_meta`` value (no-op if absent)."""
    with closing(connection.get_connection()) as conn:
        conn.execute("DELETE FROM app_meta WHERE key = ?", (key,))
        conn.commit()


class BackfillState:
    """一個 AI 功能的記憶體觀察值。欄位公開（測試與各 ``*_state`` 直接讀寫）。"""

    def __init__(
        self,
        *,
        name: str,
        task_type: Optional[str] = None,
        new_job: Optional[Callable[[Optional[str]], dict]] = None,
    ) -> None:
        self.name = name
        self.task_type = task_type
        self._new_job = new_job or _default_new_job
        self.lock = threading.Lock()
        self.unreachable: bool = False
        self.last_success_at: Optional[float] = None
        self.job: dict = self._new_job(None)
        self.notified: bool = False
        self.hook_notified: bool = False  # 入庫後掛勾專用；與補完全庫的 ``notified`` 互不影響
        self.last_persist_mono: Optional[float] = None
        self.notification_sink: Optional[Callable[..., None]] = None

    # ── 通知 ─────────────────────────────────────────────────────────────────

    def set_sink(self, fn: Callable[..., None]) -> None:
        self.notification_sink = fn

    def emit(self, key: str) -> None:
        """透過已註冊的 sink 發側欄通知（sink 為 None 時 no-op；sink 例外只記 log）。"""
        sink = self.notification_sink
        if sink is None:
            return
        try:
            sink("warn", key, task_type=self.task_type)
        except Exception:
            logger.exception("[%s] notification sink failed", self.name)

    def note_failure(self) -> bool:
        """補完全庫旗標：每個 job 第一次回 True。"""
        with self.lock:
            if self.notified:
                return False
            self.notified = True
            return True

    def reset_notified(self) -> None:
        with self.lock:
            self.notified = False

    def note_hook_failure(self) -> bool:
        """入庫後掛勾旗標：每輪第一次回 True；不碰 ``notified``。"""
        with self.lock:
            if self.hook_notified:
                return False
            self.hook_notified = True
            return True

    def new_hook_round(self) -> None:
        with self.lock:
            self.hook_notified = False

    # ── 持久化節流 ───────────────────────────────────────────────────────────

    def persist_due(self, now_mono: float) -> bool:
        """60 秒節流（第一次恆 True）。呼叫端須已持 ``self.lock``；這裡不取鎖。"""
        last = self.last_persist_mono
        if last is None or (now_mono - last) >= PERSIST_INTERVAL_S:
            self.last_persist_mono = now_mono
            return True
        return False

    # ── job 進度（每次呼叫當下讀 ``self.job``，測試會整包替換）──────────────────

    def job_begin(self, kind: str, *, reset_notified: bool = False) -> None:
        with self.lock:
            self.job = self._new_job(kind)
            if reset_notified:
                self.notified = False

    def job_progress(self) -> None:
        with self.lock:
            self.job["done"] += 1

    def job_end(self, outcome: str) -> None:
        with self.lock:
            self.job["outcome"] = outcome
