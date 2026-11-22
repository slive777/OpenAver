"""core.database.tag_blacklist — TagBlacklistRepository（205b-T1）。

`tag_blacklist` 單鍵表：`key`（`name.strip().lower()`，主鍵）＋ `name`（strip 後原字）。
連線慣例照 `core/database/embeddings.py` 檔頭：每次呼叫 `closing(get_connection(db_path))`。
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Optional

from . import connection


class TagBlacklistRepository:
    """`tag_blacklist` 的資料存取層。"""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or connection.get_db_path()

    def get_all(self) -> list[dict]:
        """回 `[{"name", "key", "created_at"}]`，依 `created_at`、`key` 排序。"""
        with closing(connection.get_connection(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT name, key, created_at FROM tag_blacklist ORDER BY created_at, key"
            ).fetchall()
        return [
            {"name": name, "key": key, "created_at": created_at}
            for name, key, created_at in rows
        ]

    def add(self, name: str) -> dict:
        """新增一列；同 `key` 已存在 → `raise ValueError`。回 `{"name", "key"}`。"""
        display = name.strip()
        if not display:
            raise ValueError("黑名單標籤不可為空")
        key = display.lower()
        with closing(connection.get_connection(self.db_path)) as conn:
            try:
                conn.execute(
                    "INSERT INTO tag_blacklist (key, name) VALUES (?, ?)",
                    (key, display),
                )
                conn.commit()
            except sqlite3.IntegrityError as exc:
                conn.rollback()
                raise ValueError(f"'{display}' 已在黑名單") from exc
        return {"name": display, "key": key}

    def remove(self, name: str) -> bool:
        """依 `key` 刪；不存在不報錯（回 False），刪掉回 True。"""
        key = name.strip().lower()
        with closing(connection.get_connection(self.db_path)) as conn:
            cursor = conn.execute("DELETE FROM tag_blacklist WHERE key = ?", (key,))
            conn.commit()
            return cursor.rowcount > 0
