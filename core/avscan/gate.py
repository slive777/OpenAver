"""站方送圖閘（CD-193-2）：同一時刻最多一張在途、兩張之間至少 AVSCAN_MIN_GAP_SECONDS 秒。

閘不碰網路、不認識呼叫者；只回答「現在能不能送」。
"""
import math
import threading
import time

AVSCAN_MIN_GAP_SECONDS = 5
AVSCAN_MAX_PENALTY_SECONDS = 300


class AvscanGate:
    def __init__(self, clock=time.monotonic, min_gap=AVSCAN_MIN_GAP_SECONDS):
        self._clock = clock
        self._min_gap = min_gap
        self._lock = threading.Lock()
        self._in_flight = False
        self._next_allowed = float("-inf")

    def _retry_after(self, now: float, floor: float = 0) -> int:
        return max(1, math.ceil(max(self._next_allowed - now, floor)))

    def try_acquire(self) -> tuple[bool, int]:
        with self._lock:
            now = self._clock()
            if self._in_flight:
                return False, self._retry_after(now, self._min_gap)
            if now < self._next_allowed:
                return False, self._retry_after(now)
            self._in_flight = True
            self._next_allowed = now + self._min_gap
            return True, 0

    def release(self) -> None:
        with self._lock:
            self._in_flight = False

    def penalize(self, seconds: float) -> None:
        seconds = min(seconds, AVSCAN_MAX_PENALTY_SECONDS)
        with self._lock:
            now = self._clock()
            self._next_allowed = max(self._next_allowed, now + seconds, now + self._min_gap)


_GATE = AvscanGate()


def get_gate() -> AvscanGate:
    return _GATE
