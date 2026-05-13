"""
DB In-flow Upsert Helper

Search 頁整理完成後，條件式將影片寫入 DB（in-flow upsert）。
僅在檔案路徑落在 Scanner 追蹤目錄範圍內時執行。
"""
from __future__ import annotations

from core.config import load_config
from core.database import Video, VideoRepository
from core.gallery_scanner import VideoScanner
from core.logger import get_logger
from core.settings_link import find_matched_directory

logger = get_logger(__name__)


def try_inflow_upsert(target_file_path: str) -> str:
    """
    條件式 in-flow upsert。

    Args:
        target_file_path: 整理後影片的完整 FS 路徑字串（非 file:// URI）

    Returns:
        "synced"     — 成功寫入 DB
        "not_linked" — 不在 Scanner directories 範圍內（靜默 skip）
        "failed"     — 發生例外（整理本身不受影響）
    """
    try:
        config = load_config()
        gallery_cfg = config.get("gallery", {})
        directories: list = gallery_cfg.get("directories", [])
        path_mappings: dict | None = gallery_cfg.get("path_mappings") or None

        # 步驟 1：確認檔案在 Scanner 追蹤範圍內
        matched = find_matched_directory(target_file_path, directories, path_mappings)
        if matched is None:
            logger.debug(
                "try_inflow_upsert: %r 不在任何 Scanner directory，skip",
                target_file_path,
            )
            return "not_linked"

        # 步驟 2：掃描影片資訊（傳 path_mappings → canonical path 與 Scanner 一致）
        scanner = VideoScanner(path_mappings=path_mappings)
        video_info = scanner.scan_file(target_file_path)

        if not video_info:
            logger.debug(
                "try_inflow_upsert: scan_file 回空值，%r skip",
                target_file_path,
            )
            return "not_linked"

        # 步驟 3：upsert 到 DB
        repo = VideoRepository()
        video = Video.from_video_info(video_info)
        repo.upsert(video)

        logger.info(
            "try_inflow_upsert: %r 已寫入 DB（matched dir=%r）",
            target_file_path,
            matched,
        )
        return "synced"

    except Exception:
        logger.exception(
            "try_inflow_upsert: %r 發生例外，DB 寫入失敗（整理結果不受影響）",
            target_file_path,
        )
        return "failed"
