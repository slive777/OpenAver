"""core.database.embeddings — 圖片相似向量表與索引中繼（186-T4a，CD-186-9）。

一部片一列（``video_embeddings.video_id`` 主鍵）；``app_meta`` 四個鍵記「現在用哪個
模型建的索引」與是否建完。``dim == 0`` 且 ``vec == b''`` ＝封面讀不到、試過了。
讀取一律 JOIN videos（孤兒列不清；id 因 AUTOINCREMENT 不重用）。

連線慣例同 BE-DATA-01：每次呼叫 ``closing(get_connection(db_path))``，不加鎖。
``db_path`` 在建構當下定死（工作 thread 用同一個 repository，不延遲解析）。
"""
from __future__ import annotations

import struct
import time
from array import array
from contextlib import closing
from pathlib import Path
from typing import Optional

from . import connection

META_MODEL = "ai.similar.index_model"
META_DIM = "ai.similar.index_dim"
META_COMPLETE = "ai.similar.index_complete"
META_LAST_SUCCESS = "ai.similar.last_success_at"

_PENDING_FROM = """
    FROM videos v
    LEFT JOIN video_embeddings e ON e.video_id = v.id
    WHERE v.cover_path != ''
      AND (e.video_id IS NULL
               OR e.model != ? OR (e.dim != ? AND e.dim != 0) OR e.cover_path != v.cover_path)
"""


def pack_vector(vec) -> bytes:
    """float 序列 → little-endian float32 bytes（呼叫端負責已 L2 正規化）。"""
    return struct.pack("<%df" % len(vec), *vec)


def unpack_vector(blob: bytes) -> array:
    """little-endian float32 bytes → ``array('f')``。"""
    n = len(blob) // 4
    return array("f", struct.unpack("<%df" % n, blob))


def _key(model: Optional[str], dim: Optional[int]) -> tuple[str, int]:
    # 索引未建立時 (None, None) → 沒有任何列符合 → 全部待處理。
    return (model or "", -1 if dim is None else int(dim))


class EmbeddingRepository:
    """``video_embeddings`` 與 ``ai.similar.*`` 中繼的存取層。"""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or connection.get_db_path()

    # ── app_meta ────────────────────────────────────────────────────────────

    def get_index_state(self) -> dict:
        """回 ``{model, dim, complete, last_success_at}``；未設的鍵為 None。"""
        with closing(connection.get_connection(self.db_path)) as conn:
            rows = dict(conn.execute(
                "SELECT key, value FROM app_meta WHERE key IN (?, ?, ?, ?)",
                (META_MODEL, META_DIM, META_COMPLETE, META_LAST_SUCCESS),
            ).fetchall())
        dim = rows.get(META_DIM)
        last = rows.get(META_LAST_SUCCESS)
        return {
            "model": rows.get(META_MODEL),
            "dim": int(dim) if dim not in (None, "") else None,
            "complete": rows.get(META_COMPLETE),
            "last_success_at": float(last) if last not in (None, "") else None,
        }

    def begin_index(self, model: str, dim: int) -> bool:
        """通過一致性測試後定模型。換成新的 (model, dim) 時三鍵同一個 transaction 寫入
        （含 ``complete='0'``，不出現「新模型＋舊 '1'」）。回 True＝換了模型；相同＝False。"""
        with closing(connection.get_connection(self.db_path)) as conn:
            cur = dict(conn.execute(
                "SELECT key, value FROM app_meta WHERE key IN (?, ?)",
                (META_MODEL, META_DIM),
            ).fetchall())
            if cur.get(META_MODEL) == model and cur.get(META_DIM) == str(int(dim)):
                return False
            conn.executemany(
                "INSERT OR REPLACE INTO app_meta (key, value) VALUES (?, ?)",
                [(META_MODEL, model), (META_DIM, str(int(dim))), (META_COMPLETE, "0")],
            )
            conn.commit()
        return True

    def reset_index(self, model: str, dim: int) -> int:
        """使用者要求「刪除並重建」：刪光全部向量列並定模型、``complete='0'``，同一個
        transaction（不出現「列已刪、complete 仍 '1'」）。回刪除列數。"""
        with closing(connection.get_connection(self.db_path)) as conn:
            n = conn.execute("DELETE FROM video_embeddings").rowcount
            conn.executemany(
                "INSERT OR REPLACE INTO app_meta (key, value) VALUES (?, ?)",
                [(META_MODEL, model), (META_DIM, str(int(dim))), (META_COMPLETE, "0")],
            )
            conn.commit()
        return n

    def mark_complete(self) -> None:
        with closing(connection.get_connection(self.db_path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO app_meta (key, value) VALUES (?, '1')",
                (META_COMPLETE,),
            )
            conn.commit()

    # ── rows ────────────────────────────────────────────────────────────────

    def write_vector(self, video_id: int, model: str, dim: int, vec: bytes,
                     cover_path: str) -> None:
        """寫（覆寫）一列，並在同一個 transaction 記 ``last_success_at``。"""
        now = time.time()
        with closing(connection.get_connection(self.db_path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO video_embeddings "
                "(video_id, model, dim, vec, cover_path, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (video_id, model, int(dim), vec, cover_path, now),
            )
            conn.execute(
                "INSERT OR REPLACE INTO app_meta (key, value) VALUES (?, ?)",
                (META_LAST_SUCCESS, repr(now)),
            )
            conn.commit()

    def write_unreadable(self, video_id: int, model: str, cover_path: str) -> None:
        """封面讀不到、試過了：``dim=0``、``vec=b''``（不算待處理、不進融合）。"""
        with closing(connection.get_connection(self.db_path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO video_embeddings "
                "(video_id, model, dim, vec, cover_path, updated_at) VALUES (?, ?, 0, ?, ?, ?)",
                (video_id, model, b"", cover_path, time.time()),
            )
            conn.commit()

    def clear_unreadable(self, model: str) -> int:
        """刪掉該模型下 ``dim=0``（封面讀不到、試過了）的列，讓它們回到待處理。
        只給使用者發起的建立工作用（每次工作重試一次）；回刪除列數。"""
        with closing(connection.get_connection(self.db_path)) as conn:
            n = conn.execute(
                "DELETE FROM video_embeddings WHERE model = ? AND dim = 0", (model,)
            ).rowcount
            conn.commit()
        return n

    def get_row(self, video_id: int) -> Optional[dict]:
        with closing(connection.get_connection(self.db_path)) as conn:
            row = conn.execute(
                "SELECT model, dim, vec, cover_path FROM video_embeddings WHERE video_id = ?",
                (video_id,),
            ).fetchone()
        if row is None:
            return None
        return {"model": row[0], "dim": row[1], "vec": row[2], "cover_path": row[3]}

    def load_valid_vectors(self, model: str, dim: int) -> list[tuple[int, str, array]]:
        """一次載入全部有效向量列（CD-186-13）：JOIN videos；
        ``model== ∧ dim== ∧ dim>0 ∧ cover_path`` 相符。回 ``(video_id, number, array('f'))``。"""
        with closing(connection.get_connection(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT v.id, v.number, e.vec FROM videos v "
                "JOIN video_embeddings e ON e.video_id = v.id "
                "WHERE e.model = ? AND e.dim = ? AND e.dim > 0 "
                "AND e.cover_path = v.cover_path AND v.cover_path != ''",
                (model, int(dim)),
            ).fetchall()
        return [(r[0], r[1] or "", unpack_vector(r[2])) for r in rows]

    # ── pending / counts ────────────────────────────────────────────────────

    def pending(self, model: Optional[str], dim: Optional[int]) -> list[tuple[int, str]]:
        """待處理清單，只取 ``(video_id, cover_path)``（I11）。"""
        with closing(connection.get_connection(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT v.id, v.cover_path" + _PENDING_FROM + " ORDER BY v.id",
                _key(model, dim),
            ).fetchall()
        return [(r[0], r[1]) for r in rows]

    def counts(self, model: Optional[str], dim: Optional[int]) -> dict:
        """``{indexed, total, pending, unreadable}``（定義見 CD-186-9；
        ``unreadable``＝封面讀不到、試過了的列數：model 相符、dim=0、cover_path 相符）。"""
        m, d = _key(model, dim)
        with closing(connection.get_connection(self.db_path)) as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM videos WHERE cover_path != ''"
            ).fetchone()[0]
            indexed = conn.execute(
                "SELECT COUNT(*) FROM videos v JOIN video_embeddings e ON e.video_id = v.id "
                "WHERE v.cover_path != '' AND e.model = ? AND e.dim = ? "
                "AND e.cover_path = v.cover_path",
                (m, d),
            ).fetchone()[0]
            unreadable = conn.execute(
                "SELECT COUNT(*) FROM videos v JOIN video_embeddings e ON e.video_id = v.id "
                "WHERE v.cover_path != '' AND e.model = ? AND e.dim = 0 "
                "AND e.cover_path = v.cover_path",
                (m,),
            ).fetchone()[0]
            pending = conn.execute(
                "SELECT COUNT(*)" + _PENDING_FROM, (m, d)
            ).fetchone()[0]
        return {"indexed": indexed, "total": total, "pending": pending, "unreadable": unreadable}

