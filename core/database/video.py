"""core.database.video — Video 資料模型與 VideoRepository（spec-87 子模組）。"""
import sqlite3
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from core.logger import get_logger

from . import connection

logger = get_logger(__name__)


@dataclass
class Video:
    """影片資料模型"""
    id: Optional[int] = None
    path: str = ""
    number: Optional[str] = None
    title: str = ""
    original_title: str = ""
    actresses: List[str] = field(default_factory=list)  # JSON
    maker: str = ""
    director: str = ""
    series: Optional[str] = None
    label: str = ""
    tags: List[str] = field(default_factory=list)  # JSON
    user_tags: List[str] = field(default_factory=list)  # JSON - 用戶自訂標籤
    sample_images: List[str] = field(default_factory=list)  # JSON
    duration: Optional[int] = None
    size_bytes: int = 0
    cover_path: str = ""
    release_date: str = ""
    mtime: float = 0.0
    nfo_mtime: float = 0.0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_video_info(cls, info) -> 'Video':
        """從 gallery_scanner.VideoInfo 轉換"""
        # info.actor 是逗號分隔字串 → list
        actresses = [a.strip() for a in info.actor.split(',') if a.strip()] if info.actor else []
        # info.genre 是逗號分隔字串 → list
        tags = [g.strip() for g in info.genre.split(',') if g.strip()] if info.genre else []

        # 將 FileTime (Windows) 轉回 Unix timestamp
        # FileTime 是從 1601-01-01 開始的 100ns 單位
        # scanner 中: int(stat.st_mtime * 10000000 + 116444736000000000)
        # 反向轉換: (filetime - 116444736000000000) / 10000000
        mtime_unix = 0.0
        if info.mtime > 0:
            try:
                mtime_unix = (info.mtime - 116444736000000000) / 10000000.0
            except (ValueError, OverflowError):
                mtime_unix = 0.0

        return cls(
            path=info.path,
            number=info.num or None,
            title=info.title,
            original_title=info.originaltitle,
            actresses=actresses,
            maker=info.maker,
            director=info.director or '',
            series=info.series or None,
            label=info.label or '',
            tags=tags,
            user_tags=info.user_tags or [],
            sample_images=info.sample_images or [],
            duration=info.duration,
            size_bytes=info.size,
            cover_path=info.img,
            release_date=info.date,
            mtime=mtime_unix,
            nfo_mtime=0.0  # VideoInfo 沒有直接的 nfo_mtime
        )

    def to_dict(self) -> dict:
        """轉為字典（JSON 欄位序列化）"""
        data = asdict(self)
        # 序列化 JSON 欄位
        data['actresses'] = json.dumps(self.actresses, ensure_ascii=False)
        data['tags'] = json.dumps(self.tags, ensure_ascii=False)
        data['user_tags'] = json.dumps(self.user_tags, ensure_ascii=False)
        data['sample_images'] = json.dumps(self.sample_images, ensure_ascii=False)
        # 序列化 datetime
        if self.created_at:
            data['created_at'] = self.created_at.isoformat()
        if self.updated_at:
            data['updated_at'] = self.updated_at.isoformat()
        return data

    @classmethod
    def from_row(cls, row: tuple, columns: List[str]) -> 'Video':
        """從資料庫 row 建立"""
        data = dict(zip(columns, row, strict=True))

        # 反序列化 JSON 欄位
        if 'actresses' in data and data['actresses']:
            try:
                data['actresses'] = json.loads(data['actresses'])
            except json.JSONDecodeError:
                data['actresses'] = []
        else:
            data['actresses'] = []

        if 'tags' in data and data['tags']:
            try:
                data['tags'] = json.loads(data['tags'])
            except json.JSONDecodeError:
                data['tags'] = []
        else:
            data['tags'] = []

        if 'user_tags' in data and data['user_tags']:
            try:
                data['user_tags'] = json.loads(data['user_tags'])
            except json.JSONDecodeError:
                data['user_tags'] = []
        else:
            data['user_tags'] = []

        if 'sample_images' in data and data['sample_images']:
            try:
                data['sample_images'] = json.loads(data['sample_images'])
            except json.JSONDecodeError:
                data['sample_images'] = []
        else:
            data['sample_images'] = []

        # 反序列化 datetime
        if 'created_at' in data and data['created_at']:
            if isinstance(data['created_at'], str):
                data['created_at'] = datetime.fromisoformat(data['created_at'])

        if 'updated_at' in data and data['updated_at']:
            if isinstance(data['updated_at'], str):
                data['updated_at'] = datetime.fromisoformat(data['updated_at'])

        return cls(**data)


class VideoRepository:
    """影片資料存取層"""

    def __init__(self, db_path: Path = None):
        self.db_path = db_path or connection.get_db_path()
        self._columns_cache: Optional[List[str]] = None

    def _get_connection(self) -> sqlite3.Connection:
        """取得資料庫連線"""
        return connection.get_connection(self.db_path)

    def _get_columns(self) -> List[str]:
        """取得欄位名稱列表（動態從 PRAGMA table_info 取得，確保與 SELECT * 順序一致）"""
        if self._columns_cache is None:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(videos)")
                self._columns_cache = [row[1] for row in cursor.fetchall()]
            finally:
                conn.close()
        return self._columns_cache

    def upsert(self, video: Video) -> int:
        """新增或更新影片（根據 path 判斷）

        Returns:
            int: 影片 id
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            video_dict = video.to_dict()
            # 移除自動欄位
            video_dict.pop('id', None)
            video_dict.pop('created_at', None)
            video_dict.pop('updated_at', None)

            columns = list(video_dict.keys())
            placeholders = ', '.join(['?'] * len(columns))
            update_parts = []
            for col in columns:
                if col == 'path':
                    continue
                elif col == 'user_tags':
                    # user_tags = '[]' 時視同「不更新」，保留 DB 現有值
                    update_parts.append(
                        "user_tags = CASE WHEN excluded.user_tags = '[]' THEN videos.user_tags ELSE excluded.user_tags END"
                    )
                else:
                    update_parts.append(f"{col} = excluded.{col}")
            update_clause = ', '.join(update_parts)

            sql = f"""
                INSERT INTO videos ({', '.join(columns)})
                VALUES ({placeholders})
                ON CONFLICT(path) DO UPDATE SET
                    {update_clause},
                    updated_at = CURRENT_TIMESTAMP
            """

            cursor.execute(sql, list(video_dict.values()))
            conn.commit()

            # invalidate ranker cache（寫成功才 invalidate；commit 失敗跳過）
            try:
                from core.similar.ranker_cache import SimilarRankerCache
                SimilarRankerCache.invalidate()
            except Exception:
                logger.exception("SimilarRankerCache invalidate failed (non-fatal)")

            # 取得 id
            cursor.execute("SELECT id FROM videos WHERE path = ?", (video.path,))
            row = cursor.fetchone()
            return row[0] if row else 0
        finally:
            conn.close()

    # ── B1 helper ─────────────────────────────────────────────────────────────

    @staticmethod
    def _union_tags(a: list, b: list) -> list:
        """去重保序的 tag 聯集。b 為空時回傳 a。"""
        if not b:
            return list(a)
        seen = list(a)
        for t in b:
            if t not in seen:
                seen.append(t)
        return seen

    def repath(self, old_uri: str | None, new_uri: str, video: Video) -> None:
        """將 DB 中 old_uri 那筆重新對應到 new_uri，保留 id / created_at。

        四分支：
        1. self-no-op : old_uri is None 或 old_uri == new_uri → upsert(video)
        2. 正常 UPDATE : old 在 DB、new 不在 → UPDATE SET path=new_uri + metadata
        3. 碰撞 delete-merge : new 已有一筆 → DELETE old + INSERT...ON CONFLICT
        4. old-not-in-DB : 兩者皆不在 → upsert(video)

        Connection pattern 鏡射 update_user_tags（database.py:840-860），
        禁用 context manager（gotchas-backend）。
        """
        # ── 分支 1：self-no-op ─────────────────────────────────────────────
        if old_uri is None or old_uri == new_uri:
            self.upsert(video)
            return

        # 讀取 old / new 是否存在
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT 1 FROM videos WHERE path = ?", (old_uri,))
            old_exists = cursor.fetchone() is not None
            cursor.execute("SELECT 1 FROM videos WHERE path = ?", (new_uri,))
            new_exists = cursor.fetchone() is not None
        finally:
            conn.close()

        # ── 分支 4：old-not-in-DB ─────────────────────────────────────────
        if not old_exists and not new_exists:
            self.upsert(video)
            return

        # ── 分支 2：正常 UPDATE（old 在 DB、new 不在 DB）────────────────────
        if old_exists and not new_exists:
            old_row = self.get_by_path(old_uri)
            merged_tags = self._union_tags(
                old_row.user_tags if old_row else [],
                video.user_tags,
            )

            # 動態建 SET 子句（鏡射 upsert 的 column list 邏輯）
            video_dict = video.to_dict()
            video_dict.pop('id', None)
            video_dict.pop('created_at', None)
            video_dict.pop('updated_at', None)
            video_dict.pop('path', None)   # path 會另外指定

            set_parts = []
            set_values = []
            for col, val in video_dict.items():
                if col == 'user_tags':
                    continue  # handled separately
                set_parts.append(f"{col} = ?")
                set_values.append(val)

            # user_tags（Python-side union，JSON 序列化）
            set_parts.append("user_tags = ?")
            set_values.append(json.dumps(merged_tags, ensure_ascii=False))

            # path + updated_at
            set_parts.append("path = ?")
            set_values.append(new_uri)
            set_parts.append("updated_at = CURRENT_TIMESTAMP")

            sql = f"UPDATE videos SET {', '.join(set_parts)} WHERE path = ?"
            set_values.append(old_uri)

            conn = self._get_connection()
            cursor = conn.cursor()
            try:
                cursor.execute(sql, set_values)
                conn.commit()
                rowcount = cursor.rowcount  # 讀在 close() 之前
            finally:
                conn.close()

            if rowcount == 0:
                # old row 在 existence check 後被並行刪除 → 退化為 upsert
                # upsert 自帶 invalidate，不再額外呼叫（避免 double invalidate）
                self.upsert(video)
                return

            # ranker invalidate（不繼承 upsert，必須顯式呼叫）
            try:
                from core.similar.ranker_cache import SimilarRankerCache
                SimilarRankerCache.invalidate()
            except Exception:
                logger.exception("SimilarRankerCache invalidate failed (non-fatal)")
            return

        # ── 分支 3：碰撞 delete-merge（new 已有一筆）──────────────────────────
        old_row = self.get_by_path(old_uri) if old_exists else None
        new_row = self.get_by_path(new_uri)

        # 三方 tag 聯集
        tags_a = old_row.user_tags if old_row else []
        tags_b = new_row.user_tags if new_row else []
        tags_c = video.user_tags
        merged_tags = self._union_tags(self._union_tags(tags_a, tags_b), tags_c)

        # created_at 取較早
        old_ca = old_row.created_at if old_row else None
        new_ca = new_row.created_at if new_row else None
        if old_ca and new_ca:
            earliest_ca = min(str(old_ca), str(new_ca))
        elif old_ca:
            earliest_ca = str(old_ca)
        elif new_ca:
            earliest_ca = str(new_ca)
        else:
            earliest_ca = None

        # 動態建 INSERT 欄位 / upsert update_clause（鏡射 upsert）
        video_dict = video.to_dict()
        video_dict.pop('id', None)
        video_dict.pop('created_at', None)
        video_dict.pop('updated_at', None)

        columns = list(video_dict.keys())
        values = list(video_dict.values())

        # 強制覆蓋 path + user_tags
        for i, col in enumerate(columns):
            if col == 'path':
                values[i] = new_uri
            elif col == 'user_tags':
                values[i] = json.dumps(merged_tags, ensure_ascii=False)

        # 顯式帶入 created_at
        if earliest_ca:
            columns.append('created_at')
            values.append(earliest_ca)

        placeholders = ', '.join(['?'] * len(columns))

        update_parts = []
        for col in columns:
            if col == 'path':
                continue
            elif col == 'created_at':
                # 碰撞分支：強制寫入較早的 created_at（DO UPDATE 也要更新）
                update_parts.append("created_at = excluded.created_at")
            elif col == 'user_tags':
                update_parts.append(
                    "user_tags = CASE WHEN excluded.user_tags = '[]' "
                    "THEN videos.user_tags ELSE excluded.user_tags END"
                )
            else:
                update_parts.append(f"{col} = excluded.{col}")
        update_parts.append("updated_at = CURRENT_TIMESTAMP")
        update_clause = ', '.join(update_parts)

        insert_sql = (
            f"INSERT INTO videos ({', '.join(columns)}) VALUES ({placeholders})\n"
            f"ON CONFLICT(path) DO UPDATE SET {update_clause}"
        )

        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            if old_exists:
                cursor.execute("DELETE FROM videos WHERE path = ?", (old_uri,))
            cursor.execute(insert_sql, values)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        # ranker invalidate
        try:
            from core.similar.ranker_cache import SimilarRankerCache
            SimilarRankerCache.invalidate()
        except Exception:
            logger.exception("SimilarRankerCache invalidate failed (non-fatal)")

    def repath_path_only(self, old_uri: str, new_uri: str) -> bool:
        """scan-fail 保卡專用：只更新 path，不觸碰其他欄位。

        Contract:
        - old_uri 空或 old_uri == new_uri → return False（no-op）
        - new_uri 已有 row → 不 UPDATE（避免 UNIQUE 碰撞）→ return False
        - 否則 UPDATE path + updated_at WHERE path=old_uri；commit；
          invalidate ranker cache（non-fatal）；rowcount > 0 → True else False
        """
        if not old_uri or old_uri == new_uri:
            return False

        # 碰撞預檢：new_uri 已有 row → 放棄（讓 prune 自癒）
        if self.get_by_path(new_uri) is not None:
            return False

        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE videos SET path = ?, updated_at = CURRENT_TIMESTAMP WHERE path = ?",
                (new_uri, old_uri),
            )
            conn.commit()
            rowcount = cursor.rowcount  # 讀在 close() 之前
        finally:
            conn.close()

        try:
            from core.similar.ranker_cache import SimilarRankerCache
            SimilarRankerCache.invalidate()
        except Exception:
            logger.exception("SimilarRankerCache invalidate failed (non-fatal)")

        return rowcount > 0

    def upsert_batch(self, videos: List[Video]) -> tuple:
        """批次新增或更新

        Returns:
            Tuple[int, int]: (inserted, updated)
        """
        if not videos:
            return (0, 0)

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # 先取得現有 path 列表
            paths = [v.path for v in videos]
            placeholders = ', '.join(['?'] * len(paths))
            cursor.execute(f"SELECT path FROM videos WHERE path IN ({placeholders})", paths)
            existing_paths = {row[0] for row in cursor.fetchall()}

            inserted = 0
            updated = 0

            for video in videos:
                video_dict = video.to_dict()
                video_dict.pop('id', None)
                video_dict.pop('created_at', None)
                video_dict.pop('updated_at', None)

                columns = list(video_dict.keys())
                placeholders_sql = ', '.join(['?'] * len(columns))
                update_parts = []
                for col in columns:
                    if col == 'path':
                        continue
                    elif col == 'user_tags':
                        # user_tags = '[]' 時視同「不更新」，保留 DB 現有值
                        update_parts.append(
                            "user_tags = CASE WHEN excluded.user_tags = '[]' THEN videos.user_tags ELSE excluded.user_tags END"
                        )
                    else:
                        update_parts.append(f"{col} = excluded.{col}")
                update_clause = ', '.join(update_parts)

                sql = f"""
                    INSERT INTO videos ({', '.join(columns)})
                    VALUES ({placeholders_sql})
                    ON CONFLICT(path) DO UPDATE SET
                        {update_clause},
                        updated_at = CURRENT_TIMESTAMP
                """

                cursor.execute(sql, list(video_dict.values()))

                if video.path in existing_paths:
                    updated += 1
                else:
                    inserted += 1

            conn.commit()

            # invalidate ranker cache（寫成功才 invalidate；commit 失敗跳過）
            try:
                from core.similar.ranker_cache import SimilarRankerCache
                SimilarRankerCache.invalidate()
            except Exception:
                logger.exception("SimilarRankerCache invalidate failed (non-fatal)")

            return (inserted, updated)
        finally:
            conn.close()

    def get_by_path(self, path: str) -> Optional[Video]:
        """根據 path 查詢"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM videos WHERE path = ?", (path,))
            row = cursor.fetchone()
            if row:
                return Video.from_row(row, self._get_columns())
            return None
        finally:
            conn.close()

    def get_all(self) -> List[Video]:
        """取得所有影片"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM videos ORDER BY id")
            rows = cursor.fetchall()
            return [Video.from_row(row, self._get_columns()) for row in rows]
        finally:
            conn.close()

    def get_mtime_index(self) -> dict:
        """取得 {path: (mtime, nfo_mtime)} 索引，用於增量比對"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT path, mtime, nfo_mtime FROM videos")
            rows = cursor.fetchall()
            return {row[0]: (row[1], row[2]) for row in rows}
        finally:
            conn.close()

    def get_cover_index(self) -> dict:
        """取得 {path: cover_path} 索引，供唯讀 producer 增量比對（feature/88）。

        Additive read-only method; does NOT change get_mtime_index() shape (CD-88b-2).
        cover_path may be '' or None for rows without a cover — callers must handle both.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT path, cover_path FROM videos")
            rows = cursor.fetchall()
            return {row[0]: row[1] for row in rows}
        finally:
            conn.close()

    def delete_by_paths(self, paths: List[str]) -> int:
        """批次刪除

        Returns:
            int: 刪除數量
        """
        if not paths:
            return 0

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            placeholders = ', '.join(['?'] * len(paths))
            cursor.execute(f"DELETE FROM videos WHERE path IN ({placeholders})", paths)
            deleted_count = cursor.rowcount
            conn.commit()

            # invalidate ranker cache（寫成功才 invalidate；commit 失敗跳過）
            try:
                from core.similar.ranker_cache import SimilarRankerCache
                SimilarRankerCache.invalidate()
            except Exception:
                logger.exception("SimilarRankerCache invalidate failed (non-fatal)")

            return deleted_count
        finally:
            conn.close()

    def count(self) -> int:
        """取得總數"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT COUNT(*) FROM videos")
            row = cursor.fetchone()
            return row[0] if row else 0
        finally:
            conn.close()

    def clear_all(self) -> int:
        """清除所有影片快取

        Returns:
            int: 刪除數量
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT COUNT(*) FROM videos")
            count = cursor.fetchone()[0]
            cursor.execute("DELETE FROM videos")
            conn.commit()

            # invalidate ranker cache（寫成功才 invalidate；commit 失敗跳過）
            try:
                from core.similar.ranker_cache import SimilarRankerCache
                SimilarRankerCache.invalidate()
            except Exception:
                logger.exception("SimilarRankerCache invalidate failed (non-fatal)")

            return count
        finally:
            conn.close()

    def get_by_id(self, video_id: int) -> Optional[Video]:
        """根據整數 id 查詢單筆影片（供 T6 主端點使用）。

        Returns:
            Video 若找到，None 若 id 不存在
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM videos WHERE id = ?", (video_id,))
            row = cursor.fetchone()
            if row:
                return Video.from_row(row, self._get_columns())
            return None
        finally:
            conn.close()

    def get_by_ids(self, video_ids: list[int]) -> dict[int, Video]:
        """批次查詢多筆影片（避免 N+1 — codex P2 fix）。

        相似搜尋一次需取所有候選影片資訊（套 diversity penalty 用），
        個別 get_by_id 在 2000+ 候選時 → 2000 SQL round-trip。

        Returns:
            {video_id: Video} dict（缺失 id 不在 result 內）；空 list 回 {}。
        """
        if not video_ids:
            return {}
        placeholders = ",".join("?" * len(video_ids))
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                f"SELECT * FROM videos WHERE id IN ({placeholders})",
                tuple(video_ids),
            )
            cols = self._get_columns()
            return {
                row[cols.index("id")]: Video.from_row(row, cols)
                for row in cursor.fetchall()
            }
        finally:
            conn.close()

    def get_by_number(self, number: str) -> Optional[Video]:
        """根據番號查詢單筆影片，大小寫不敏感（供 by-number 端點使用）。

        Returns:
            Video 若找到，None 若番號不存在
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM videos WHERE UPPER(number) = UPPER(?) LIMIT 1",
                (number,)
            )
            row = cursor.fetchone()
            if row:
                return Video.from_row(row, self._get_columns())
            return None
        finally:
            conn.close()

    def get_by_numbers(self, numbers: List[str]) -> dict:
        """根據番號批次查詢（大小寫不敏感）

        Args:
            numbers: 番號列表 (e.g., ["SONE-205", "ABW-001"])

        Returns:
            dict: {番號: [Video, ...]} - 同番號可能有多個檔案
                  番號 key 使用原始輸入的大小寫形式
        """
        if not numbers:
            return {}

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # 建立大寫番號 → 原始輸入的映射
            upper_to_original = {n.upper(): n for n in numbers}
            upper_numbers = list(upper_to_original.keys())

            # 使用 UPPER() 進行大小寫不敏感比對
            placeholders = ', '.join(['?'] * len(upper_numbers))
            cursor.execute(
                f"SELECT * FROM videos WHERE UPPER(number) IN ({placeholders})",
                upper_numbers
            )
            rows = cursor.fetchall()

            # 建立結果字典（使用原始輸入的 key）
            result = {}
            for row in rows:
                video = Video.from_row(row, self._get_columns())
                if video.number:
                    # 找到原始輸入的 key
                    original_key = upper_to_original.get(video.number.upper())
                    if original_key:
                        if original_key not in result:
                            result[original_key] = []
                        result[original_key].append(video)

            return result
        finally:
            conn.close()

    def count_by_actress(self, actress_name: str) -> int:
        """查詢某女優名字的片數

        Uses json_each to expand the actresses JSON array and match exactly,
        replacing the previous 4-LIKE-OR pattern to prevent prefix/suffix false matches.

        Args:
            actress_name: 女優名稱

        Returns:
            int: 包含該女優的影片數量
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """SELECT COUNT(DISTINCT videos.rowid) FROM videos, json_each(videos.actresses)
                   WHERE json_valid(videos.actresses) AND json_each.value = ?""",
                (actress_name,)
            )
            row = cursor.fetchone()
            return row[0] if row else 0
        except sqlite3.OperationalError:
            logger.exception(
                "count_by_actress json_each failed for %r (returning 0)",
                actress_name
            )
            return 0
        finally:
            conn.close()

    def get_videos_by_actress(self, actress_name: str) -> List['Video']:
        """取得包含某女優的所有影片

        Uses json_each to expand the actresses JSON array and match exactly,
        replacing the previous 4-LIKE-OR pattern to prevent prefix/suffix false matches.

        Args:
            actress_name: 女優名稱

        Returns:
            List[Video]: 包含該女優的影片列表
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """SELECT DISTINCT videos.* FROM videos, json_each(videos.actresses)
                   WHERE json_valid(videos.actresses) AND json_each.value = ?
                   ORDER BY videos.id""",
                (actress_name,)
            )
            rows = cursor.fetchall()
            return [Video.from_row(row, self._get_columns()) for row in rows]
        except sqlite3.OperationalError:
            logger.exception(
                "get_videos_by_actress json_each failed for %r (returning [])",
                actress_name
            )
            return []
        finally:
            conn.close()

    def get_videos_by_actress_names(self, names: list) -> List['Video']:
        """多名 OR 查詢（用於 alias 展開後的本地封面候選）

        Uses json_each with IN (placeholders) and SELECT DISTINCT to match any of the
        given names exactly, replacing the previous per-name UNION-of-LIKE pattern.
        DISTINCT prevents duplicate rows when a video's actresses list contains
        multiple names from the query set.

        Args:
            names: 女優名稱 list（alias 展開後的所有名稱）

        Returns:
            List[Video]: 包含任一名稱的影片列表（去重）
        """
        if not names:
            return []

        placeholders = ",".join("?" * len(names))
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                f"""SELECT DISTINCT videos.* FROM videos, json_each(videos.actresses)
                   WHERE json_valid(videos.actresses) AND json_each.value IN ({placeholders})
                   ORDER BY videos.id""",
                tuple(names)
            )
            rows = cursor.fetchall()
            return [Video.from_row(row, self._get_columns()) for row in rows]
        except sqlite3.OperationalError:
            logger.exception(
                "get_videos_by_actress_names json_each failed for %d names (returning [])",
                len(names)
            )
            return []
        finally:
            conn.close()

    def update_user_tags(self, path: str, user_tags: List[str]) -> bool:
        """安全更新 user_tags 欄位（不碰其他欄位）

        Args:
            path: 影片路徑（DB key，file:/// URI 格式）
            user_tags: 新的 user_tags 列表

        Returns:
            bool: 是否成功更新
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE videos SET user_tags = ?, updated_at = CURRENT_TIMESTAMP WHERE path = ?",
                (json.dumps(user_tags, ensure_ascii=False), path)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def update_sample_images(self, path: str, sample_images: List[str]) -> bool:
        """只更新 sample_images 欄位（§b1 scanner cleanup + §b3 fetch-samples 使用）"""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE videos SET sample_images = ?, updated_at = CURRENT_TIMESTAMP WHERE path = ?",
                (json.dumps(sample_images, ensure_ascii=False), path),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def count_videos_in_folder(self, folder_uri_prefix: str) -> int:
        """計算「直接在此目錄下」的影片數（不含子目錄）。
        folder_uri_prefix 必須以 '/' 結尾，例如 'file:///A/'。
        """
        assert folder_uri_prefix.endswith('/'), "prefix 必須以 '/' 結尾"
        # Python 側先 escape LIKE wildcards，順序：\ → % → _
        # ESCAPE '\\' 子句只定義 escape 字元，不會自動處理參數
        escaped = (folder_uri_prefix
                   .replace('\\', '\\\\')
                   .replace('%', '\\%')
                   .replace('_', '\\_'))
        conn = self._get_connection()
        try:
            row = conn.execute(
                """
                SELECT COUNT(*) FROM videos
                WHERE path LIKE ? ESCAPE '\\'
                  AND path NOT LIKE ? ESCAPE '\\'
                """,
                (escaped + '%', escaped + '%/%'),
            ).fetchone()
            return row[0] if row else 0
        finally:
            conn.close()

    def is_known_cover_path(self, fs_path: str) -> bool:
        """
        驗證 fs_path 是否為 DB 中某個 video 的 cover_path（防任意檔案讀取）。

        DB 主要存 file:/// URI（gallery_scanner / enricher 寫入），但 legacy migrate 路徑
        可能保留裸 FS 路徑（migrate_json_to_sqlite 未正規化）。為保留相容性，同時查兩種 key。
        走 idx_videos_cover_path index（O(log N)）。
        """
        from core.path_utils import to_file_uri
        if not fs_path:
            return False
        try:
            uri = to_file_uri(fs_path)
        except Exception:
            uri = None
        conn = self._get_connection()
        try:
            if uri is not None:
                row = conn.execute(
                    "SELECT 1 FROM videos WHERE cover_path IN (?, ?) LIMIT 1",
                    (uri, fs_path)
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT 1 FROM videos WHERE cover_path = ? LIMIT 1",
                    (fs_path,)
                ).fetchone()
        finally:
            conn.close()
        return row is not None
