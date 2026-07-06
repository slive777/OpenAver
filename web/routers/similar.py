"""
web/routers/similar.py
GET /api/similar-covers 端點（57b-T2）。

兩個端點：
- GET /api/similar-covers/by-number/{number}  ← 必須在前（防路由衝突）
- GET /api/similar-covers/{video_id}

v0.8.7 rule-based ranker 取代 v0.8.6 CLIP embedding。
API response shape 完全不變（CD-57b-5）。
"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query

from core.config import load_config
from core.database import VideoRepository
from core.logger import get_logger
from core.path_utils import uri_to_local_fs_path
from core.similar.ranker_cache import SimilarRankerCache

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["similar"])


def _build_cover_url(video, enabled: bool = False, path_mappings: dict = None) -> str:
    """組封面 url（feature/71 T4）。

    - enabled  → /api/gallery/thumb?path=<quote(video.path)>（thumb key = video path，非 cover）。
    - disabled → 維持現狀 /api/gallery/image?path=<quote(uri_to_local_fs_path(video.cover_path, path_mappings))>（字節不變）。
    邊界：video.cover_path 為空字串 / None → 回傳空字串（enabled/disabled 皆然，無 cover 不發 thumb url）。
    """
    if not video.cover_path:
        return ""
    if enabled:
        return f"/api/gallery/thumb?path={quote(video.path, safe='')}"
    local_path = uri_to_local_fs_path(video.cover_path, path_mappings)
    return f"/api/gallery/image?path={quote(local_path, safe='')}"


def _build_cover_full_url(video, path_mappings: dict = None) -> str:
    """組封面原圖 url（71c）。

    恆原圖（不受 thumbnail_cache_enabled 影響），鏡像 showcase._serialize_video 中 cover_full_url 的邏輯。
    供 燈箱 blur-up .lb-full overlay 使用；similar slip-through 路徑不帶此欄會讓 .lb-full 卡 opacity:0。
    """
    if not video.cover_path:
        return ""
    local_path = uri_to_local_fs_path(video.cover_path, path_mappings)
    return f"/api/gallery/image?path={quote(local_path, safe='')}"


def _compute_similar_covers(video_id: int, limit: int) -> dict:
    """核心業務邏輯：根據 video_id 取 target，呼叫 ranker 取得相似影片，組裝 response。

    Args:
        video_id: 目標影片 id
        limit: 回傳結果數量上限

    Returns:
        符合 v0.8.6 response shape 的 dict

    Raises:
        HTTPException 404: target 不存在
    """
    repo = VideoRepository()
    target = repo.get_by_id(video_id)
    if target is None:
        raise HTTPException(status_code=404, detail="找不到影片")

    ranker = SimilarRankerCache.get()
    results_videos = ranker.rank(target, top_k=limit)

    # feature/71 T4：讀一次 thumbnail_cache flag，套用於 query_video + 每個 result
    config = load_config()
    gallery_config = config.get('gallery', {})
    path_mappings = gallery_config.get('path_mappings', {})
    enabled = config.get('thumbnail_cache_enabled', False)

    return {
        "video_id": video_id,
        "model_id": "rule-based:v1",
        "query_video": {
            "video_id": target.id,
            "number": target.number,
            "title": target.title,
            "cover_url": _build_cover_url(target, enabled, path_mappings),
        },
        "results": [
            {
                "video_id": v.id,
                "number": v.number,
                "title": v.title,
                "cover_path": v.cover_path,
                "cover_url": _build_cover_url(v, enabled, path_mappings),
                "cover_full_url": _build_cover_full_url(v, path_mappings),  # 71c：恆原圖，供燈箱 blur-up .lb-full overlay
                "cosine_score": ranker._score(target, v),
                "penalty_applied": False,  # rule-based 無 penalty 概念，保留 key 為 fixture 相容
                "actresses": v.actresses if isinstance(v.actresses, list) else [],
            }
            for v in results_videos
        ],
    }


# by-number 端點必須在 {video_id} 之前定義（防 FastAPI 路由衝突）
@router.get("/similar-covers/by-number/{number}")
def get_similar_covers_by_number(
    number: str,
    limit: int = Query(default=12, ge=1, le=50),
) -> dict:
    """GET /api/similar-covers/by-number/{number}

    根據番號查詢相似影片。番號大小寫不敏感。

    Returns:
        200: v0.8.6 response shape
        404: 查無番號
    """
    repo = VideoRepository()
    video = repo.get_by_number(number)
    if video is None:
        raise HTTPException(status_code=404, detail="找不到影片")
    return _compute_similar_covers(video.id, limit)


@router.get("/similar-covers/{video_id}")
def get_similar_covers_by_id(
    video_id: int,
    limit: int = Query(default=12, ge=1, le=50),
) -> dict:
    """GET /api/similar-covers/{video_id}

    根據影片 id 查詢相似影片。

    Returns:
        200: v0.8.6 response shape
        404: 查無 video_id
    """
    return _compute_similar_covers(video_id, limit)


@router.get("/similar/warmup")
def warmup_similar_ranker() -> dict:
    """GET /api/similar/warmup — 57e hotfix。

    Showcase 頁 mount 時 fire-and-forget 呼叫；觸發 SimilarRankerCache 首次 lazy build，
    讓用戶之後點 magic icon 時不再吃 cold-start 延遲（6000-video DB 上 50-150ms）。
    與 magic icon 首次點擊 race 配合（client 端 openSimilarMode 序列化修法）：
    warm-up 命中 → A 的 await 變 ~10ms invisible；warm-up 來不及 → A 仍正確（只是慢）。
    """
    SimilarRankerCache.get()
    return {"ok": True}
