"""
Settings Link Router — /api/settings/favorite-scanner-link

提供最愛資料夾與 Scanner directories 的即時連動狀態查詢。
favorite 從 query param 取得（input 即時值），不讀 config 存檔的 favorite_folder。
directories / path_mappings 仍從 config 讀（CD-58-B1-4）。
"""
from fastapi import APIRouter, Query
from core.config import load_config
from core.logger import get_logger
from core.settings_link import find_matched_directory

logger = get_logger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings-link"])


@router.get("/favorite-scanner-link")
def get_favorite_scanner_link(
    favorite: str = Query(default="", description="最愛資料夾路徑（input 即時值）"),
) -> dict:
    """
    查詢最愛資料夾是否在某個 Scanner directory 範圍內。

    Response:
        {"linked": bool, "matched_directory": str | null}
    """
    # favorite 空字串 → 直接回未連動，不做 path 比對
    if not favorite or not favorite.strip():
        return {"linked": False, "matched_directory": None}

    config = load_config()
    gallery_config = config.get("gallery", {}) if isinstance(config, dict) else getattr(config, "gallery", {})

    # 從 config 讀 directories / path_mappings（不接受前端傳入）
    if isinstance(gallery_config, dict):
        directories = gallery_config.get("directories", [])
        path_mappings = gallery_config.get("path_mappings", {})
    else:
        directories = getattr(gallery_config, "directories", [])
        path_mappings = getattr(gallery_config, "path_mappings", {})

    matched = find_matched_directory(
        favorite=favorite,
        directories=directories,
        path_mappings=path_mappings or None,
    )

    return {
        "linked": matched is not None,
        "matched_directory": matched,
    }
