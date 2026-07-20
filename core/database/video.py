"""core.database.video — Video 資料模型與 VideoRepository（spec-87 子模組）。"""
import sqlite3
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, List, Tuple
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
    output_dir: str = ''
    release_date: str = ""
    mtime: float = 0.0
    nfo_mtime: float = 0.0
    scrape_attempted_at: float = 0.0
    auto_focal: str = ''
    crop_mode: str = 'auto'
    focal_attempted_at: Optional[str] = None  # NULL=從未偵測過；非 NULL=偵測跑過（Codex PR#105 P2）
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


# preserve-on-conflict 欄位集合（CD-98a-6）：比照 path — 首次 INSERT 帶 dataclass 預設值，
# 衝突/repath 走下方 4 個 builder 時不無條件覆蓋。focal 只由專用 update_auto_focal/
# update_manual_focal/reset_focal_to_auto mutator 改寫（update_crop_mode 已於 99a-T7
# retire，production 已無獨立呼叫端）；掃描/重刮的 builder 一律不直接寫入 dataclass 預設值。
#
# 三欄位行為不對稱（Codex PR#105 P2b 修正）：
# - crop_mode：純使用者裁切模式偏好，與封面無關，無條件保留 DB 既有值。
# - auto_focal / focal_attempted_at：是「針對某張封面」算出的結果，若 incoming（本次
#   掃描）cover_path 與 DB 既有 cover_path 相同（metadata-only 衝突）→ 保留既有值；
#   若 cover_path 不同（用戶換封面 / NFO・sidecar 選了不同封面）→ 重置為未偵測
#   （auto_focal='' + focal_attempted_at=NULL），否則舊封面的 stale 焦點結果會讓新
#   封面永遠不被 get_empty_focal_candidates 重新排入偵測，除非手動 force-detect。
_FOCAL_PRESERVE = frozenset({'auto_focal', 'crop_mode', 'focal_attempted_at'})

# ON CONFLICT DO UPDATE 用的條件式 CASE 片段（cover_path 相同才保留舊值，否則重置）。
# videos.<col> 在 upsert 語境中指衝突前既有的 row 值；excluded.<col> 指本次 INSERT 的
# incoming 值——鏡射既有 user_tags/output_dir CASE-WHEN 寫法（見下方 3 個 builder）。
_FOCAL_AUTO_FOCAL_CASE_SQL = (
    "auto_focal = CASE WHEN excluded.cover_path = videos.cover_path "
    "THEN videos.auto_focal ELSE '' END"
)
_FOCAL_ATTEMPTED_AT_CASE_SQL = (
    "focal_attempted_at = CASE WHEN excluded.cover_path = videos.cover_path "
    "THEN videos.focal_attempted_at ELSE NULL END"
)
# crop_mode 版（99a-T1b CD-10）：同封面一律保留（manual/auto/default 皆不動）；
# 換封面時 manual 座標已對新內容失效 → 降回 'auto'（讓 empty-focal gate 能重掃）；
# auto/legacy default 換封面不受影響（只有 auto_focal/focal_attempted_at 被清）。
_FOCAL_CROP_MODE_CASE_SQL = (
    "crop_mode = CASE WHEN excluded.cover_path = videos.cover_path THEN videos.crop_mode "
    "WHEN videos.crop_mode = 'manual' THEN 'auto' ELSE videos.crop_mode END"
)


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
                elif col in _FOCAL_PRESERVE:
                    if col == 'crop_mode':
                        # 同封面保留；換封面時 manual 座標已失效 → 降回 auto（CD-10/99a-T1b）
                        update_parts.append(_FOCAL_CROP_MODE_CASE_SQL)
                    elif col == 'auto_focal':
                        # cover_path 相同 → 保留；換封面 → 重置為未偵測（Codex PR#105 P2b）
                        update_parts.append(_FOCAL_AUTO_FOCAL_CASE_SQL)
                    elif col == 'focal_attempted_at':
                        update_parts.append(_FOCAL_ATTEMPTED_AT_CASE_SQL)
                elif col == 'user_tags':
                    # user_tags = '[]' 時視同「不更新」，保留 DB 現有值
                    update_parts.append(
                        "user_tags = CASE WHEN excluded.user_tags = '[]' THEN videos.user_tags ELSE excluded.user_tags END"
                    )
                elif col == 'output_dir':
                    # output_dir = '' 時視同「不更新」，保留 DB 現有值（TASK-89a-T1）
                    update_parts.append(
                        "output_dir = CASE WHEN excluded.output_dir = '' THEN videos.output_dir ELSE excluded.output_dir END"
                    )
                elif col == 'scrape_attempted_at':
                    # scrape_attempted_at = 0 時視同「不更新」，保留 DB 現有值（P2 修正，須與 output_dir 對稱）
                    update_parts.append(
                        "scrape_attempted_at = CASE WHEN excluded.scrape_attempted_at = 0 THEN videos.scrape_attempted_at ELSE excluded.scrape_attempted_at END"
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

    def insert_if_ignore(self, video: Video) -> bool:
        """新增影片，path 已存在時不覆蓋任何既有欄位（TASK-89b-T1）。

        鏡射 upsert() 的動態欄位建構，但改用 ON CONFLICT(path) DO NOTHING——
        不建 update_parts / DO UPDATE 分支。實際插入新 row 時（rowcount>0）比照
        upsert() 呼叫 SimilarRankerCache.invalidate()：placeholder row 目前雖不含
        排序特徵欄位、不影響 IDF/相似訊號，但保持「每次 INSERT INTO videos 都 invalidate」
        的 spec-57b 完整性不變式（避免日後 placeholder 補欄位時漏 invalidate 成隱性 stale）。

        Returns:
            bool: True 表示實際插入新 row；False 表示 path 已存在、未動任何欄位。
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            video_dict = video.to_dict()
            video_dict.pop('id', None)
            video_dict.pop('created_at', None)
            video_dict.pop('updated_at', None)

            columns = list(video_dict.keys())
            placeholders = ', '.join(['?'] * len(columns))

            sql = f"""
                INSERT INTO videos ({', '.join(columns)})
                VALUES ({placeholders})
                ON CONFLICT(path) DO NOTHING
            """

            cursor.execute(sql, list(video_dict.values()))
            conn.commit()

            inserted = cursor.rowcount > 0
            if inserted:
                # invalidate ranker cache（實際插入才 invalidate；DO NOTHING 命中則跳過）
                try:
                    from core.similar.ranker_cache import SimilarRankerCache
                    SimilarRankerCache.invalidate()
                except Exception:
                    logger.exception("SimilarRankerCache invalidate failed (non-fatal)")

            return inserted
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

            # cover_path 是否變動決定 auto_focal/focal_attempted_at 保留或重置
            # （Codex PR#105 P2b）。old_row 為 None 屬既有存在檢查後被並行刪除的極端
            # race（見上方 merged_tags 同一 old_row 用法），安全預設視為「封面已變」
            # 一併重置，不留可能對應舊封面的 stale 值。
            cover_unchanged = old_row is not None and video.cover_path == old_row.cover_path

            set_parts = []
            set_values = []
            for col, val in video_dict.items():
                if col == 'user_tags':
                    continue  # handled separately
                elif col == 'crop_mode':
                    if cover_unchanged:
                        continue  # 裁切模式偏好與封面無關，同封面一律保留 DB 既有值（CD-98a-6）
                    if old_row and old_row.crop_mode == 'manual':
                        # 換封面：manual 座標對新內容已失效 → 降回 auto（CD-10/99a-T1b）
                        set_parts.append("crop_mode = ?")
                        set_values.append('auto')
                    continue  # 防 fall-through 到底部通用 append 重複 SET（Codex PR#105 P2c 教訓）
                elif col == 'auto_focal':
                    if cover_unchanged:
                        continue  # 保留 DB 既有值
                    set_parts.append("auto_focal = ?")
                    set_values.append('')
                    continue  # 已排入 reset，勿 fall through 到底部通用 append（重複 SET→SQLite 取最右＝incoming stale 值蓋掉 reset，Codex PR#105 P2c）
                elif col == 'focal_attempted_at':
                    if cover_unchanged:
                        continue  # 保留 DB 既有值
                    set_parts.append("focal_attempted_at = ?")
                    set_values.append(None)
                    continue  # 同上：勿 fall through 重複 append 蓋掉 reset（Codex PR#105 P2c）
                elif col == 'output_dir' and not val:
                    # incoming output_dir 空 → 保留既有值（不寫入），與 upsert() CASE-WHEN 對稱
                    continue
                elif col == 'scrape_attempted_at' and not val:
                    # incoming scrape_attempted_at 為 0 → 保留既有值（不寫入），與 upsert() CASE-WHEN 對稱
                    continue
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
            elif col in _FOCAL_PRESERVE:
                if col == 'crop_mode':
                    # 同封面保留；換封面時 manual 座標已失效 → 降回 auto（CD-10/99a-T1b）
                    update_parts.append(_FOCAL_CROP_MODE_CASE_SQL)
                elif col == 'auto_focal':
                    # cover_path 相同 → 保留；換封面 → 重置為未偵測（Codex PR#105 P2b）
                    update_parts.append(_FOCAL_AUTO_FOCAL_CASE_SQL)
                elif col == 'focal_attempted_at':
                    update_parts.append(_FOCAL_ATTEMPTED_AT_CASE_SQL)
            elif col == 'created_at':
                # 碰撞分支：強制寫入較早的 created_at（DO UPDATE 也要更新）
                update_parts.append("created_at = excluded.created_at")
            elif col == 'user_tags':
                update_parts.append(
                    "user_tags = CASE WHEN excluded.user_tags = '[]' "
                    "THEN videos.user_tags ELSE excluded.user_tags END"
                )
            elif col == 'output_dir':
                # output_dir = '' 時視同「不更新」，保留 DB 現有值（與 upsert() 對稱，Codex P2 修正）
                update_parts.append(
                    "output_dir = CASE WHEN excluded.output_dir = '' "
                    "THEN videos.output_dir ELSE excluded.output_dir END"
                )
            elif col == 'scrape_attempted_at':
                # scrape_attempted_at = 0 時視同「不更新」，保留 DB 現有值（與 upsert() 對稱，Codex P2 修正）
                update_parts.append(
                    "scrape_attempted_at = CASE WHEN excluded.scrape_attempted_at = 0 "
                    "THEN videos.scrape_attempted_at ELSE excluded.scrape_attempted_at END"
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
                    elif col in _FOCAL_PRESERVE:
                        if col == 'crop_mode':
                            # 同封面保留；換封面時 manual 座標已失效 → 降回 auto（CD-10/99a-T1b）
                            update_parts.append(_FOCAL_CROP_MODE_CASE_SQL)
                        elif col == 'auto_focal':
                            # cover_path 相同 → 保留；換封面 → 重置為未偵測（Codex PR#105 P2b）
                            update_parts.append(_FOCAL_AUTO_FOCAL_CASE_SQL)
                        elif col == 'focal_attempted_at':
                            update_parts.append(_FOCAL_ATTEMPTED_AT_CASE_SQL)
                    elif col == 'user_tags':
                        # user_tags = '[]' 時視同「不更新」，保留 DB 現有值
                        update_parts.append(
                            "user_tags = CASE WHEN excluded.user_tags = '[]' THEN videos.user_tags ELSE excluded.user_tags END"
                        )
                    elif col == 'output_dir':
                        # output_dir = '' 時視同「不更新」，保留 DB 現有值（TASK-89a-T1，須與 upsert() 對稱）
                        update_parts.append(
                            "output_dir = CASE WHEN excluded.output_dir = '' THEN videos.output_dir ELSE excluded.output_dir END"
                        )
                    elif col == 'scrape_attempted_at':
                        # scrape_attempted_at = 0 時視同「不更新」，保留 DB 現有值（P2 修正，須與 upsert() 對稱）
                        update_parts.append(
                            "scrape_attempted_at = CASE WHEN excluded.scrape_attempted_at = 0 THEN videos.scrape_attempted_at ELSE excluded.scrape_attempted_at END"
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

    def get_focal_crop_map(self, paths: List[str]) -> dict:
        """批次讀 {path: (auto_focal, crop_mode)}（Codex PR#105 P2 修復用，避免 N+1）。

        用途：similar-covers 端點的 SimilarRankerCache 回傳快取 Video 物件，其
        auto_focal/crop_mode 可能因 update_auto_focal()/update_manual_focal()/
        reset_focal_to_auto() 寫入而 stale（這些 mutator 刻意不 invalidate 整個
        ranker cache——焦點/裁切模式是純顯示欄位、不影響排序特徵，若比照
        upsert/delete invalidate 代價不對稱）。
        呼叫端可用此 map 對 ranker 結果做 fresh 覆蓋，讓 ranker 快取仍可命中。

        單條 `SELECT path, auto_focal, crop_mode FROM videos WHERE path IN (...)`，超過
        SQLite 變數上限時分批。空 paths 直接回 {}（不查詢）。鏡射 get_empty_focal_candidates 連線 pattern。

        Args:
            paths: 影片 path（DB key，file:/// URI 格式）列表

        Returns:
            dict[str, tuple[str, str]]: {path: (auto_focal, crop_mode)}；未在 DB 的 path
            不會出現在結果中。
        """
        if not paths:
            return {}

        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            result: dict = {}
            chunk_size = 900  # 保守低於 SQLite 999 變數上限
            for i in range(0, len(paths), chunk_size):
                chunk = paths[i:i + chunk_size]
                placeholders = ', '.join(['?'] * len(chunk))
                cursor.execute(
                    f"SELECT path, auto_focal, crop_mode FROM videos WHERE path IN ({placeholders})",
                    chunk,
                )
                for row in cursor.fetchall():
                    result[row[0]] = (row[1], row[2])
            return result
        finally:
            conn.close()

    def get_empty_focal_candidates(self, paths: List[str]) -> List[Tuple[str, Optional[str], str, str]]:
        """批次讀「本次掃描 in-scope 但 auto_focal 仍空、且從未偵測過」的候選列
        （Codex PR#105 P2 修復；no-face re-enqueue 修復同號 P2）。

        舊版掃描 focal trigger 只迴圈 videos_to_upsert（= needs_scan，新檔/mtime 或
        NFO 變動的檔），既有、未變動、auto_focal='' 的列永遠不會被送偵測——「重掃
        一次自動補焦既有庫」實際上是假的（見 CHANGELOG 0.12.0 已知限制承諾）。改
        由呼叫端傳入本次掃描 in-scope 的完整 DB-key URI 集合（與 upsert 同一套
        to_file_uri(path, path_mappings) 推導，不在此另建 URI）查詢，一次補齊。

        偵測到「無臉」時 auto_focal 也存 format_focal(None) == ''，與「從未偵測過」
        無法用 auto_focal 單一欄位區分——若只篩 auto_focal 空，無臉封面會被每次重掃
        無限重排、worker 白忙。因此額外要求 focal_attempted_at IS NULL（update_auto_focal
        蓋章過的列一律排除，不論找到臉或無臉）。

        單條 `SELECT path, number, maker, cover_path FROM videos WHERE path IN (...)
        AND (auto_focal IS NULL OR auto_focal = '') AND focal_attempted_at IS NULL`，
        超過 SQLite 變數上限時分批。空 paths 直接回 []（不查詢）。gate
        （requires_face_detection）仍在 Python 側逐列判（番號/廠牌邏輯不搬 SQL），
        此處只做欄位篩選。鏡射 get_focal_crop_map 連線 pattern。

        Args:
            paths: 本次掃描 in-scope 的 path（DB key，file:/// URI 格式）列表。

        Returns:
            list[tuple[str, str|None, str, str]]: [(path, number, maker, cover_path), ...]；
            未在 DB 的 path、auto_focal 非空的 path、或已偵測過（focal_attempted_at 非
            NULL，含無臉結果）的 path 都不會出現在結果中。
        """
        if not paths:
            return []

        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            result: List[Tuple[str, Optional[str], str, str]] = []
            chunk_size = 900  # 保守低於 SQLite 999 變數上限
            for i in range(0, len(paths), chunk_size):
                chunk = paths[i:i + chunk_size]
                placeholders = ', '.join(['?'] * len(chunk))
                cursor.execute(
                    f"""SELECT path, number, maker, cover_path FROM videos
                        WHERE path IN ({placeholders})
                        AND (auto_focal IS NULL OR auto_focal = '')
                        AND focal_attempted_at IS NULL""",
                    chunk,
                )
                result.extend(cursor.fetchall())
            return result
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

    def get_attempted_index(self) -> dict:
        """取得 {path: scrape_attempted_at} 索引，供 T3 `_should_skip` 冷啟動判斷用（TASK-89b-T1）。

        Additive read-only method，鏡射 get_mtime_index() shape。SELECT 不加 WHERE，
        含 scrape_attempted_at == 0 的 row（不過濾）——呼叫端用 `.get(path, 0) > 0`
        統一判斷「從未試過」（key 不存在或值為 0 皆視為未試過）。
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT path, scrape_attempted_at FROM videos")
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

    def update_scrape_attempted_at(self, path: str, ts: float) -> bool:
        """安全更新 scrape_attempted_at 欄位（不碰其他欄位）（TASK-89b-T1）。

        鏡射 update_user_tags() 的單欄安全更新範本。ts 由呼叫端（T2 producer/enricher）
        傳入 time.time()，本方法不自行取時間（保持純寫入語意，供單元測試可控時間值）。

        Args:
            path: 影片路徑（DB key，file:/// URI 格式）
            ts: 新的 scrape_attempted_at 值（Unix float 時間戳）

        Returns:
            bool: 是否成功更新（path 不存在 → False，不拋例外、不新建 row）
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE videos SET scrape_attempted_at = ?, updated_at = CURRENT_TIMESTAMP WHERE path = ?",
                (ts, path)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def update_auto_focal(self, path: str, focal: str, expected_cover_path: str) -> bool:
        """安全更新 auto_focal 欄位（不碰其他欄位，CD-98a-6 mutator，鏡射 update_user_tags）。

        同時蓋章 focal_attempted_at = CURRENT_TIMESTAMP（單條 UPDATE 原子寫，Codex PR#105
        P2 修復）：背景 worker 與 force-detect endpoint 都經此方法 commit 偵測結果——不論
        找到臉（focal='x,y'）或無臉（focal=''），都代表「偵測跑過了」，須排除於後續
        get_empty_focal_candidates 的重掃 backfill 之外，否則無臉封面每次重掃都被當
        「沒偵測過」無限重排。

        `AND crop_mode != 'manual'`（CD-9/99a-T1b）：本方法現為 update_auto_focal
        唯一 production caller（core/focal_trigger.py 的 worker commit lambda）——
        擋掉 in-flight stale worker（開跑後使用者才手存 manual）commit 時偷換剛存的
        手動座標。manual row 被擋下時 rowcount 為 0，focal_attempted_at 不蓋章，但
        安全：manual row 的 auto_focal 恆非空字串，天然被 get_empty_focal_candidates
        的 `auto_focal = ''` 篩選排除，不會被誤重排。

        `AND cover_path = ?`（99b-T2 CD-99b-3/4/5/9，換封面 compare-and-store）：
        row 若在 in-flight worker 分析當下之後又被換了封面（scanner upsert / 重刮 /
        repath 落既有 row），舊 job commit 時 `expected_cover_path` 對不上目前
        `cover_path` → rowcount 0，不寫入 stale 焦點、不蓋 focal_attempted_at 章。
        `expected_cover_path` 為必填、不可傳 `None`——`cover_path=''` 是真實存在的
        合法值（封面下載失敗時 `_db_upsert` 會寫 `''`），必須由呼叫端顯式帶入「被
        分析的那張封面」的 DB-key URI，不可省略。

        Args:
            path: 影片路徑（DB key，file:/// URI 格式）
            focal: 新的 auto_focal 值（背景 focal 演算法算出的座標字串，如 '0.5,0.4'，
                無臉時為 format_focal(None) == ''）
            expected_cover_path: 被分析的那張封面的 DB-key `cover_path`（file:/// URI
                或空字串）。必須與呼叫端分析封面時使用的值同源（CD-99b-4），不可用
                反解後的 FS path。

        Returns:
            bool: 是否成功更新（path 不存在、crop_mode='manual'、或 cover_path 已不
                符 expected_cover_path → False，不拋例外、不新建 row）
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE videos SET auto_focal = ?, focal_attempted_at = CURRENT_TIMESTAMP, "
                "updated_at = CURRENT_TIMESTAMP WHERE path = ? AND crop_mode != 'manual' "
                "AND cover_path = ?",
                (focal, path, expected_cover_path)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def update_manual_focal(self, path: str, focal: str, expected_cover_path: str) -> bool:
        """原子寫入使用者手動指定的焦點座標（99a-T1a mutator，CD-2；99b Codex P2
        補 cover_path compare-and-store，鏡射 update_auto_focal 的 99b-T2 修法）。

        同一 UPDATE 內把 crop_mode 蓋為 'manual'，代表「使用者手動存過」——與
        update_auto_focal（背景/預覽偵測寫入，不動 crop_mode）語意分離。刻意不碰
        focal_attempted_at：手動存入的 auto_focal 恆非空字串（mutator 呼叫方已用
        parse_focal 擋掉空字串/非法輸入），get_empty_focal_candidates 的
        `auto_focal = ''` 篩選天然排除 manual row，不需要額外蓋章。

        `AND cover_path = ?`（Codex PR#107 第二輪 P2）：使用者開遮罩觀察的是某張
        封面，若期間 rescan/rescrape 換了封面（row.cover_path 變了），這支 UPDATE
        必須拒絕把舊封面算出的座標蓋進新封面、且標成 manual——一旦寫入，
        update_auto_focal 的 `AND crop_mode != 'manual'` 守衛會永久擋住背景 worker
        重新分析新封面，`get_empty_focal_candidates` 的 `auto_focal = ''` 篩選也
        因 row 已有非空值而永不重排，新封面座標會卡死。expected_cover_path 為
        必填、不可傳 None——`cover_path=''` 是真實存在的合法值（封面下載失敗時
        `_db_upsert` 會寫 `''`），把 None 解釋成「比對空字串」會命中錯的 row。

        Args:
            path: 影片路徑（DB key，file:/// URI 格式）
            focal: 正規化後的焦點座標字串（如 '0.5000,0.4000'）
            expected_cover_path: 使用者編輯遮罩當下觀察到的 `cover_path`（DB-key
                file:/// URI 或空字串），必須是 server 端當時回傳給前端的原始值，
                不可用反解後的 FS path（namespace 對不上會讓 UPDATE 恆命中 0 列）。

        Returns:
            bool: 是否成功更新（path 不存在、或 cover_path 已不符
                expected_cover_path → False，不拋例外、不新建 row）
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE videos SET auto_focal = ?, crop_mode = 'manual', "
                "updated_at = CURRENT_TIMESTAMP WHERE path = ? AND cover_path = ?",
                (focal, path, expected_cover_path)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def reset_focal_to_auto(self, path: str) -> bool:
        """作廢手動焦點、降回未偵測狀態（99a-T1b mutator，CD-4）。

        單一 UPDATE 原子清空 auto_focal、降回 crop_mode='auto'、且把
        focal_attempted_at 清 NULL（比照 upsert() 的 _FOCAL_ATTEMPTED_AT_CASE_SQL：
        換封面視同「從未偵測過」，Codex review 補修）。呼叫端（enricher 重刮流程）
        於確認 cover_written=True（實際寫入新封面內容）時呼叫，且必須在排入新的
        背景 focal 偵測（maybe_submit_video_focal）之前——先清舊值、再讓 gate
        判斷是否排 worker，避免有碼片在極端時序下短暫殘留 manual。

        若不清 focal_attempted_at：worker 若在 submit 後失敗/未 commit（未呼叫
        update_auto_focal 蓋章），row 停在 auto_focal='' + focal_attempted_at 仍是
        舊封面留下的非 NULL 值——get_empty_focal_candidates 的
        `auto_focal='' AND focal_attempted_at IS NULL` gate 會判定「已偵測過」而
        永遠跳過，新封面就再也不會被排入偵測（除非手動 force-detect）。

        Args:
            path: 影片路徑（DB key，file:/// URI 格式）

        Returns:
            bool: 是否成功更新（path 不存在 → False，不拋例外、不新建 row）
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE videos SET auto_focal = '', crop_mode = 'auto', "
                "focal_attempted_at = NULL, "
                "updated_at = CURRENT_TIMESTAMP WHERE path = ?",
                (path,)
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

    def is_output_dir_taken(self, output_dir: str, exclude_path: str) -> bool:
        """查詢 output_dir 是否已被別筆 source_uri（videos.path）佔用（TASK-89a-T1）。

        供 T3 判斷候選輸出夾是否需要 increment 另尋。純 SELECT，唯讀 connection
        pattern（鏡射 is_known_cover_path() / get_by_path()），不需 commit。

        Args:
            output_dir: 候選輸出夾（file:/// URI）。呼叫端須保證候選為非空路徑
                （一般 enrich/scan row 的 output_dir 恆為 ''，若誤傳空字串會匹配
                到大量一般 row，本 method 不做防呆）。
            exclude_path: 排除的 source_uri（自己那筆的 videos.path），避免跟自己比對
                （CD-89a-3「讀存原地覆蓋」情境：候選 = 自己既有值時不應誤判為佔用）。

        Returns:
            True 表示已被別筆佔用；False 表示可用（含無人持有 / 只被自己持有兩種情況）。
        """
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT 1 FROM videos WHERE output_dir = ? AND path != ? LIMIT 1",
                (output_dir, exclude_path)
            ).fetchone()
        finally:
            conn.close()
        return row is not None
