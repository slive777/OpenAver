"""core.database.actress — Actress 資料模型與 ActressRepository（spec-87 子模組）。"""
import sqlite3
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from . import connection


@dataclass
class Actress:
    """女優資料模型"""
    name: str = ""
    name_en: Optional[str] = None
    birth: Optional[str] = None
    height: Optional[str] = None
    cup: Optional[str] = None
    bust: Optional[int] = None
    waist: Optional[int] = None
    hip: Optional[int] = None
    hometown: Optional[str] = None
    hobby: Optional[str] = None
    aliases: List[str] = field(default_factory=list)  # JSON
    agency: Optional[str] = None
    debut_work: Optional[str] = None
    tags: List[str] = field(default_factory=list)  # JSON
    nickname: Optional[str] = None
    blog_url: Optional[str] = None
    official_url: Optional[str] = None
    photo_source: Optional[str] = None
    primary_text_source: Optional[str] = None
    auto_focal: str = ''
    crop_mode: str = 'auto'
    # Photo fingerprint (98d stat-on-load). Defaults MATCH the SQL column
    # defaults ('' / 0 / 0) so a fresh save() and an ALTER-migrated row share
    # ONE canonical "unset" sentinel — 98d compares (path, mtime_ns, size)
    # and must not juggle None-vs-''/0 by row provenance.
    # 98a 預留、spec-100 不使用：這三欄供 98a 規劃的 stat-on-load 背景 focal
    # 演算法使用（未落地）。spec-100 的手動焦點
    # 走 update_manual_focal，不寫這三欄（女優無背景 writer，CD-3）。保留欄位
    # 不刪除，供未來背景 focal worker 落地時使用。
    photo_fp_path: str = ''
    photo_fp_mtime_ns: int = 0
    photo_fp_size: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """轉為字典（JSON 欄位序列化）"""
        data = asdict(self)
        data['aliases'] = json.dumps(self.aliases, ensure_ascii=False)
        data['tags'] = json.dumps(self.tags, ensure_ascii=False)
        if self.created_at:
            data['created_at'] = self.created_at.isoformat()
        if self.updated_at:
            data['updated_at'] = self.updated_at.isoformat()
        return data

    @classmethod
    def from_row(cls, row: tuple, columns: List[str]) -> 'Actress':
        """從資料庫 row 建立"""
        data = dict(zip(columns, row, strict=True))

        if 'aliases' in data and data['aliases']:
            try:
                data['aliases'] = json.loads(data['aliases'])
            except json.JSONDecodeError:
                data['aliases'] = []
        else:
            data['aliases'] = []

        if 'tags' in data and data['tags']:
            try:
                data['tags'] = json.loads(data['tags'])
            except json.JSONDecodeError:
                data['tags'] = []
        else:
            data['tags'] = []

        if 'created_at' in data and data['created_at']:
            if isinstance(data['created_at'], str):
                data['created_at'] = datetime.fromisoformat(data['created_at'])

        if 'updated_at' in data and data['updated_at']:
            if isinstance(data['updated_at'], str):
                data['updated_at'] = datetime.fromisoformat(data['updated_at'])

        return cls(**data)


# save() ON CONFLICT 排除集合（CD-98a-6）：name 是 PK、恆不進 update_parts；
# auto_focal/crop_mode/photo_fp_* 五欄只由專用 mutator 改寫，save() 衝突時一律保留
# DB 既有值（比照 video.py 的 _FOCAL_PRESERVE）。現行 writer：clear_focal /
# update_manual_focal（spec-100，auto_focal + crop_mode）。98a 曾預留
# update_crop_mode/update_focal_result 供未落地的背景 focal worker 使用，
# spec-100 未採用，已於 103-T1 隨同刪除。
_ACTRESS_FOCAL_PRESERVE = frozenset({
    'name', 'auto_focal', 'crop_mode',
    'photo_fp_path', 'photo_fp_mtime_ns', 'photo_fp_size',
})


class ActressRepository:
    """女優資料存取層"""

    def __init__(self, db_path: Path = None):
        self.db_path = db_path or connection.get_db_path()
        self._columns_cache: Optional[List[str]] = None

    def _get_connection(self) -> sqlite3.Connection:
        """取得資料庫連線"""
        return connection.get_connection(self.db_path)

    def _get_columns(self) -> List[str]:
        """取得欄位名稱列表（動態從 PRAGMA table_info 取得，確保與 SELECT * 順序一致，
        鏡射 VideoRepository._get_columns；CD-98a-8——手寫清單在 ALTER 加欄後會與
        SELECT * 長度不符，from_row 的 zip(strict=True) 直接 ValueError）"""
        if self._columns_cache is None:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(actresses)")
                self._columns_cache = [row[1] for row in cursor.fetchall()]
            finally:
                conn.close()
        return self._columns_cache

    def save(self, actress: Actress) -> None:
        """新增或更新女優（根據 name 判斷）"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            actress_dict = actress.to_dict()
            actress_dict.pop('created_at', None)
            actress_dict.pop('updated_at', None)

            columns = list(actress_dict.keys())
            placeholders = ', '.join(['?'] * len(columns))
            # preserve-on-conflict（CD-98a-6）：name 是 PK 恆排除；focal + photo fingerprint
            # 五欄只由專用 mutator 改寫（現行＝clear_focal / update_manual_focal），save() 衝突時保留
            update_parts = []
            for col in columns:
                if col in _ACTRESS_FOCAL_PRESERVE:
                    continue
                update_parts.append(f"{col} = excluded.{col}")
            update_clause = ', '.join(update_parts)

            sql = f"""
                INSERT INTO actresses ({', '.join(columns)})
                VALUES ({placeholders})
                ON CONFLICT(name) DO UPDATE SET
                    {update_clause},
                    updated_at = CURRENT_TIMESTAMP
            """

            cursor.execute(sql, list(actress_dict.values()))
            conn.commit()
        finally:
            conn.close()

    def clear_focal(self, name: str) -> bool:
        """原子清空手動焦點（CD-98a-6 mutator，spec-100 T3 換圖時呼叫）。

        單一 UPDATE 一次寫完 auto_focal='' + crop_mode='auto'，換圖作廢舊焦點。

        Args:
            name: 女優名稱（DB key）

        Returns:
            bool: 是否成功更新（name 不存在 → False，不拋例外、不新建 row）
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE actresses SET auto_focal = '', crop_mode = 'auto', "
                "updated_at = CURRENT_TIMESTAMP WHERE name = ?",
                (name,)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def update_manual_focal(self, name: str, focal: str) -> bool:
        """原子寫入使用者手動焦點（CD-98a-6 mutator，spec-100 T4 使用者按確認存入時呼叫）。

        單一 UPDATE 一次寫完 auto_focal=focal + crop_mode='manual'。

        刻意不吃 expected_fp / expected_cover_path 之類的 compare-and-store token
        （對照 video.py 的 update_manual_focal(path, focal, expected_cover_path)）——
        CD-3：女優 focal 沒有背景 writer 會與此方法交錯寫入，不需要 compare token 防
        race，`WHERE name = ?` 已足夠。不要為了「補齊對稱」加上這個參數。

        格式驗證（parse_focal）不在此層——呼叫端（T4 focal 端點）負責，此方法是啞的
        原子寫入器，傳什麼字串就存什麼字串（含空字串，見 task card 邊界條件）。

        Args:
            name: 女優名稱（DB key）
            focal: 新的 auto_focal 值（canonical "x,y" 4dp 字串，或呼叫端傳入的任意字串）

        Returns:
            bool: 是否成功更新（name 不存在 → False，不拋例外、不新建 row）
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE actresses SET auto_focal = ?, crop_mode = 'manual', "
                "updated_at = CURRENT_TIMESTAMP WHERE name = ?",
                (focal, name)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def get_by_name(self, name: str) -> Optional[Actress]:
        """根據 name 查詢"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM actresses WHERE name = ?", (name,))
            row = cursor.fetchone()
            if row:
                return Actress.from_row(row, self._get_columns())
            return None
        finally:
            conn.close()

    def delete_by_name(self, name: str) -> bool:
        """刪除女優資料

        Returns:
            bool: 是否成功刪除（不存在則回 False）
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("DELETE FROM actresses WHERE name = ?", (name,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def get_all(self) -> List[Actress]:
        """取得所有女優"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM actresses ORDER BY name")
            rows = cursor.fetchall()
            return [Actress.from_row(row, self._get_columns()) for row in rows]
        finally:
            conn.close()

    def exists(self, name: str) -> bool:
        """檢查女優是否存在"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT COUNT(*) FROM actresses WHERE name = ?", (name,))
            row = cursor.fetchone()
            return bool(row and row[0] > 0)
        finally:
            conn.close()

    def count_videos_for_actress_names(self, names: set) -> int:
        """Count videos where any actress name in `names` appears in the actresses JSON array.

        Uses COUNT(DISTINCT videos.rowid) to avoid double-counting a video that
        lists multiple aliases of the same actress.
        """
        if not names:
            return 0
        placeholders = ",".join("?" * len(names))
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                f"""SELECT COUNT(DISTINCT videos.rowid) FROM videos, json_each(videos.actresses)
                   WHERE json_valid(videos.actresses) AND json_each.value IN ({placeholders})""",
                tuple(names),
            )
            return cursor.fetchone()[0]
        except sqlite3.OperationalError:
            return 0
        finally:
            conn.close()

    def count_videos_for_actress(self, name: str) -> int:
        """Count videos featuring this actress (backward-compatible single-name wrapper)."""
        return self.count_videos_for_actress_names({name})
