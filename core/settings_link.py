"""
Settings Link — 最愛資料夾與 Scanner directories 連動邏輯

純函式模組，無 web router 依賴。
"""
from __future__ import annotations

from core.logger import get_logger
from core.path_utils import (
    expand_env_vars,
    is_path_under_dir,
    normalize_path,
    to_file_uri,
    uri_to_fs_path,
)

logger = get_logger(__name__)


def find_matched_directory(
    favorite: str,
    directories: list,
    path_mappings: dict | None = None,
) -> str | None:
    """
    判斷 favorite 路徑是否在某個 Scanner directory 範圍內。

    Args:
        favorite: 最愛資料夾路徑（可含環境變數 / 波浪號）
        directories: Scanner 追蹤的資料夾清單（來自 config.gallery.directories）
        path_mappings: 路徑映射表（WSL 環境用，傳給 to_file_uri，CD-58-B1-3a）

    Returns:
        命中的 directory（精確相等或子目錄）；未命中或例外時回 None
    """
    if not favorite or not favorite.strip():
        return None

    if not directories:
        return None

    # favorite 端：expand → normalize → to_file_uri
    try:
        fav_expanded = expand_env_vars(favorite)
    except ValueError as e:
        logger.warning("expand_env_vars 拋 ValueError，favorite=%r: %s", favorite, e)
        return None

    fav_normalized = normalize_path(fav_expanded)
    fav_uri = to_file_uri(fav_normalized, path_mappings)

    # directories 端：uri_to_fs_path → to_file_uri（不 expand，CD-58-B1-3b）
    # directory 可能是 FS 路徑或 file:/// URI（DirectoryConfig.path schema「FS 路徑或
    # URI」）。uri_to_fs_path 對 URI→FS、FS→FS 皆冪等，取代裸 normalize_path（後者對
    # URI 原樣通過 → to_file_uri 二次包成 file:///file:/// → 永不命中）(PR#91 同源)。
    for directory in directories:
        try:
            d_normalized = uri_to_fs_path(directory)  # uri-no-reverse: native config path (DirectoryConfig.path), no DB-mapped namespace
            d_uri = to_file_uri(d_normalized, path_mappings)
        except (ValueError, Exception) as e:
            logger.warning("跳過無效 directory=%r: %s", directory, e)
            continue

        if fav_uri == d_uri or is_path_under_dir(fav_uri, d_uri):
            return directory

    return None
