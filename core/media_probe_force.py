"""core.media_probe_force — 不經背景 worker 的同步探針。

probe_now(repo, video_uri, fs_path, expected_mtime, expected_size, timeout=20)：
整段工作在自己開的 daemon 執行緒（name='media-probe-force'）內做，主呼叫端
join(timeout)，逾時回 'timeout'（執行緒繼續跑）。執行緒內未預期例外 →
logger.exception、結果 'unreadable'。

回傳 ∈ ok|failed|unreadable|stale|changed|skipped|timeout。
unreadable／stale／changed／skipped 時 DB 位元不變；timeout 時回應當下 DB 不變。
與背景 worker 之間不保證誰後寫（compare-and-store 擋掉 key 已變的舊寫入）。
"""
from __future__ import annotations

import os
import threading

from core import media_probe
from core.logger import get_logger
from core.video_extensions import ZERO_SIZE_EXTENSIONS

logger = get_logger(__name__)


def probe_now(repo, video_uri, fs_path, expected_mtime, expected_size, timeout=20) -> str:
    """同步讀一次這個檔並回報這一次的結果。"""

    def _probe():
        if os.path.splitext(fs_path)[1].lower() in ZERO_SIZE_EXTENSIONS:
            return "skipped"
        try:
            start_stat = os.stat(fs_path)
        except (OSError, ValueError):
            return "unreadable"
        if (
            expected_mtime is None
            or expected_size is None
            or start_stat.st_size != expected_size
            or abs(start_stat.st_mtime - expected_mtime) > 1.0
        ):
            return "changed"
        result = media_probe.probe_file(fs_path)
        if result.status == "unreadable":
            return "unreadable"
        try:
            end_stat = os.stat(fs_path)
        except (OSError, ValueError):
            return "unreadable"
        if (end_stat.st_mtime_ns, end_stat.st_size) != (start_stat.st_mtime_ns, start_stat.st_size):
            return "unreadable"
        written = repo.update_media_probe(video_uri, result, expected_mtime, expected_size)
        if not written:
            return "stale"
        return "ok" if result.status == "ok" else "failed"

    outcome: dict = {}

    def _work():
        try:
            outcome["result"] = _probe()
        except Exception:
            logger.exception("media probe force failed for %s", video_uri)
            outcome["result"] = "unreadable"

    thread = threading.Thread(target=_work, daemon=True, name="media-probe-force")
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        return "timeout"
    return outcome.get("result", "unreadable")
