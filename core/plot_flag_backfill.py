"""has_plot 一次性回填 pass（187b-T2b / CD-187b-3）。

候選＝has_plot IS NULL AND nfo_mtime > 0；locate → read_plot_flag：
True/False＝已確認寫入；None 或 locate 任一 err＝維持 NULL（BE-DATA-11）。
NFO 路徑不存在（外接碟／NAS 離線）→ 視為未知、維持 NULL；不呼叫
read_plot_flag（其「不存在＝False」語意留給掃描／補完路徑）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from core.logger import get_logger
from core.plot_nfo import read_plot_flag
from core.video_nfo_locate import locate_video_nfo

logger = get_logger(__name__)


def run_plot_flag_backfill_pass(
    repo,
    config: dict,
    path_mappings: dict = None,
    should_abort: Optional[Callable[[], bool]] = None,
) -> int:
    """掃描舊庫一次補齊 has_plot。回傳已確認寫入列數。

    should_abort：每列讀 NFO 前查一次；abort 時停止讀取、已確認的照寫。
    """
    if path_mappings is None:
        path_mappings = {}
    candidates = repo.get_plot_unknown_rows()
    confirmed = []
    for video in candidates:
        if should_abort is not None and should_abort():
            break
        nfo_path, err = locate_video_nfo(video, config, path_mappings)
        if err is not None or nfo_path is None:
            continue
        # 離線／路徑暫時不可達：不存在 ≠ 已確認沒有（CD-187b-3）
        if not Path(nfo_path).exists():
            continue
        flag = read_plot_flag(nfo_path)
        if flag is None:
            continue
        confirmed.append((video.path, flag))
    if not confirmed:
        return 0
    return repo.set_has_plot_bulk(confirmed)
