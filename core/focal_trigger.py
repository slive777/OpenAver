"""core.focal_trigger — 共用 focal 自動 trigger 接線（TASK-98b-T2）。

四個 cover 落盤點（首刮 in-flow save、重刮/enrich、掃描入庫兩實作）皆呼叫
`maybe_submit_video_focal`，讓無碼片背景算出 `auto_focal`；有碼片零成本。

放 `core/`（非 `core/focal/`）避免 focal 純 infra 包（worker/detector/gate）耦合 DB：
本 helper 綁 `VideoRepository`，屬 application-glue，不屬 infra。

安全退化：helper 全程「靜默不排」＝安全退化（無 focal → render 退 baseline 右裁）；
任何失敗都吞掉、不改 scrape/enrich/scan 的既有回傳形狀與成功語意。
"""
import os

from core.database import VideoRepository
from core.focal import requires_face_detection, submit_focal
from core.logger import get_logger

logger = get_logger(__name__)

# 偵測 ratio 一律 0.71（CD-98b-1）。Python 側目前無 `POSTER_CROP_RATIO` 常數
# 可 import——它僅存於 JS（web/static/js/shared/constellation/animations.js）
# 與 CSS var `--poster-crop-ratio`，後端無 SSOT，故在此落一個 named module 常數，
# 不散寫裸 0.71。
_DETECT_RATIO = 0.71


def maybe_submit_video_focal(number, maker, video_path_uri, cover_fs_path, *, cover_path_uri: str, db_path=None):
    """條件式排入背景 focal 偵測（無碼片才排）。

    Args:
        number: canonical `videos.number`（gate 判無碼用，不自加番號判斷）。
        maker: canonical `videos.maker`（gate whitelist 用；None 視同 ""）。
        video_path_uri: DB row key（file:/// URI）——commit 以此 WHERE key 寫
            `auto_focal`。必須等於 DB 實際 row 的 `path` 欄，否則 silent-miss。
        cover_fs_path: 已反解的本機封面 fs 路徑（worker 直接開檔，不做反解）。
        cover_path_uri: 被分析的這張封面在 DB 的 `cover_path`（DB-key，file:///
            URI 或空字串，99b-T2 CD-99b-4/5/9）。keyword-only 必填、無預設值——
            commit 時穿進 `update_auto_focal` 的 `expected_cover_path`，讓 worker
            commit 前確認 row 仍指著這張封面（换封面 race 鎖）。呼叫端必須顯式
            傳入與分析封面同源的值，不可用反解後的 FS path，也不可省略。
        db_path: commit 寫回的目標 DB。None＝預設 DB（`VideoRepository(None)` 退回
            `get_db_path()`，scraper/enricher 走此）。掃描端傳入自訂/tmp `db_path`，
            否則背景 commit 會寫到預設 DB → 非預設 DB 掃描 silent-miss。

    背景 submit 失敗由 98a worker 內部 logger.exception 吞；此處再包一層防禦，
    確保「排 job 這動作本身」的任何例外都不冒泡打斷呼叫端流程。
    """
    try:
        if not requires_face_detection(number, maker or ""):
            return  # 有碼片零成本
        if not cover_fs_path or not os.path.exists(cover_fs_path):
            return  # 無封面檔不排空 job
        # fp 忽略（video 無 fingerprint 欄）；commit 綁 video_path_uri 當 WHERE key、
        # cover_path_uri 在此刻（submit 當下）被 closure 捕獲當 expected_cover_path、
        # db_path 當目標 DB。
        commit = lambda focal_str, fp: VideoRepository(db_path).update_auto_focal(video_path_uri, focal_str, cover_path_uri)  # noqa: E731
        submit_focal("video", video_path_uri, cover_fs_path, _DETECT_RATIO, commit)
    except Exception:
        logger.exception("maybe_submit_video_focal 排程失敗（不影響呼叫端流程）: %s", video_path_uri)
        return
