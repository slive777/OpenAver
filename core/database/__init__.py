"""core.database — 永久 re-export facade（spec-87 D0）。

所有呼叫方繼續使用 `from core.database import X`，無需感知子模組。
"""
from .connection import (
    get_db_path,
    get_connection,
    init_db,
    _migrate_old_aliases,
)
from .video import Video, VideoRepository
from .alias import AliasRecord, AliasRepository
from .tag_alias import TagAliasRecord, TagAliasRepository
from .actress import Actress, ActressRepository
from .actress_library import get_library_actresses
from .migrate import migrate_json_to_sqlite, backfill_readonly_nfo_mtime, backfill_readonly_nfo_mtime_once
from .wishlist import WishlistRepository
from .embeddings import EmbeddingRepository
from .notifications import (
    insert_notification,
    mark_notifications_read,
    clear_all_notifications,
    load_recent_notifications,
)
from . import organize_failures
from . import maker_javbus_map

__all__ = [
    "get_db_path",
    "get_connection",
    "init_db",
    "_migrate_old_aliases",
    "Video",
    "VideoRepository",
    "AliasRecord",
    "AliasRepository",
    "TagAliasRecord",
    "TagAliasRepository",
    "Actress",
    "ActressRepository",
    "get_library_actresses",
    "migrate_json_to_sqlite",
    "backfill_readonly_nfo_mtime",
    "backfill_readonly_nfo_mtime_once",
    "WishlistRepository",
    "EmbeddingRepository",
    "insert_notification",
    "mark_notifications_read",
    "clear_all_notifications",
    "load_recent_notifications",
    "organize_failures",
    "maker_javbus_map",
]

