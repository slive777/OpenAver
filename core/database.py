"""
SQLite 資料庫管理模組。

啟用 WAL mode 提升並發讀寫效能。VideoRepository 負責影片記錄的 CRUD，
AliasRepository 負責新版平坦 group 別名維護。`init_db` 在每次啟動時自動執行
schema migration，無需手動管理資料庫版本。
"""
import sqlite3
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from core.logger import get_logger

logger = get_logger(__name__)


def get_db_path() -> Path:
    """獲取資料庫路徑 (output/openaver.db)"""
    # 使用專案根目錄下的 output 資料夾
    db_dir = Path(__file__).parent.parent / "output"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "openaver.db"


def get_connection(db_path: Path = None) -> sqlite3.Connection:
    """取得資料庫連線，啟用 WAL 模式"""
    if db_path is None:
        db_path = get_db_path()

    conn = sqlite3.connect(str(db_path))
    # 啟用 WAL 模式以提升並發效能
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _migrate_old_aliases(rows: list) -> list:
    """將舊 directional alias rows 跟鏈合併為平坦 groups。

    Args:
        rows: list of (old_name, new_name) tuples from the old actress_aliases table

    Returns:
        list of dicts: [{"primary_name": str, "aliases": list[str]}, ...]
    """
    edges = {old: new for old, new in rows}  # old → new

    visited: set = set()
    groups: dict = {}  # endpoint → [members]

    for start in list(edges.keys()):
        if start in visited:
            continue

        chain: list = []
        node = start
        seen_in_chain: set = set()

        while node in edges:
            if node == edges[node]:
                # 自我指向：A→A，跳過整個 start
                logger.warning("Alias migration: self-reference '%s', skipping", node)
                visited.add(node)
                chain = []  # 清空，不產生 group
                node = None
                break
            if node in seen_in_chain:
                # 循環偵測：以當前 node 為 endpoint，中斷鏈
                logger.warning("Alias migration: cycle detected at '%s', breaking chain", node)
                break
            chain.append(node)
            seen_in_chain.add(node)
            visited.add(node)
            node = edges[node]

        if node is None:
            # 自我指向 — 跳過
            continue

        # node 是 endpoint（鏈的終點）；chain 是路徑上的節點（不含 endpoint）
        aliases = [x for x in chain if x != node]
        if aliases:
            groups.setdefault(node, []).extend(aliases)

    # 去重（匯流時多條鏈可能重複 append 同一名字）
    return [
        {"primary_name": pk, "aliases": list(dict.fromkeys(members))}
        for pk, members in groups.items()
    ]


def init_db(db_path: Path = None) -> None:
    """初始化資料庫 Schema"""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # 創建影片表格
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT UNIQUE NOT NULL,
            number TEXT,
            title TEXT,
            original_title TEXT,
            actresses TEXT,
            maker TEXT,
            director TEXT DEFAULT '',
            series TEXT,
            label TEXT DEFAULT '',
            tags TEXT,
            sample_images TEXT DEFAULT '',
            user_tags TEXT DEFAULT '[]',
            duration INTEGER,
            size_bytes INTEGER,
            cover_path TEXT,
            release_date TEXT,
            mtime REAL,
            nfo_mtime REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 創建索引
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_videos_number ON videos(number)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_videos_path ON videos(path)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_videos_maker ON videos(maker)
    """)

    # 女優別名表 — 偵測舊 schema (old_name 欄位) 並執行跟鏈遷移
    existing_alias_cols = {
        row[1] for row in cursor.execute("PRAGMA table_info(actress_aliases)").fetchall()
    }
    if "old_name" in existing_alias_cols:
        # 舊 schema：執行跟鏈遷移
        logger.info("Detected old actress_aliases schema (old_name column); migrating…")
        rows = cursor.execute(
            "SELECT old_name, new_name FROM actress_aliases"
        ).fetchall()
        groups = _migrate_old_aliases(rows)
        cursor.execute("ALTER TABLE actress_aliases RENAME TO actress_aliases_legacy")
        cursor.execute("""
            CREATE TABLE actress_aliases (
                primary_name  TEXT PRIMARY KEY,
                aliases       TEXT NOT NULL DEFAULT '[]',
                source        TEXT NOT NULL DEFAULT 'manual',
                applied_count INTEGER DEFAULT 0,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        for g in groups:
            cursor.execute(
                """INSERT INTO actress_aliases (primary_name, aliases, source)
                   VALUES (?, ?, 'manual')""",
                (g["primary_name"], json.dumps(g["aliases"], ensure_ascii=False)),
            )
        logger.info("Migration complete: %d groups written to new actress_aliases table", len(groups))
    else:
        # 新 schema 或表不存在：直接 CREATE IF NOT EXISTS
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS actress_aliases (
                primary_name  TEXT PRIMARY KEY,
                aliases       TEXT NOT NULL DEFAULT '[]',
                source        TEXT NOT NULL DEFAULT 'manual',
                applied_count INTEGER DEFAULT 0,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    # Seed data：若新表為空，插入種子資料供既有測試使用
    if cursor.execute("SELECT COUNT(*) FROM actress_aliases").fetchone()[0] == 0:
        # 使用新 schema 格式（平坦 group）插入種子資料
        cursor.execute("""
            INSERT INTO actress_aliases (primary_name, aliases, source) VALUES
            ('坂道みる',  '["miru"]',             'manual'),
            ('新ありな',  '["橋本ありな"]',         'manual'),
            ('河北彩花',  '["河北彩伽"]',           'manual'),
            ('深田えいみ','["天海こころ","心菜りお"]','manual')
        """)

    # 刪除舊 index（新 schema 不需要；IF EXISTS 保證 idempotent）
    cursor.execute("DROP INDEX IF EXISTS idx_actress_aliases_new_name")

    # 創建女優資料表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS actresses (
            name TEXT PRIMARY KEY,
            name_en TEXT,
            birth TEXT,
            height TEXT,
            cup TEXT,
            bust INTEGER,
            waist INTEGER,
            hip INTEGER,
            hometown TEXT,
            hobby TEXT,
            aliases TEXT DEFAULT '[]',
            agency TEXT,
            debut_work TEXT,
            tags TEXT DEFAULT '[]',
            nickname TEXT,
            blog_url TEXT,
            official_url TEXT,
            photo_source TEXT,
            primary_text_source TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Migration: 加入 Phase 37 新欄位
    existing_cols = {row[1] for row in cursor.execute("PRAGMA table_info(videos)").fetchall()}
    if 'director' not in existing_cols:
        cursor.execute("ALTER TABLE videos ADD COLUMN director TEXT DEFAULT ''")
    if 'label' not in existing_cols:
        cursor.execute("ALTER TABLE videos ADD COLUMN label TEXT DEFAULT ''")
    if 'sample_images' not in existing_cols:
        cursor.execute("ALTER TABLE videos ADD COLUMN sample_images TEXT DEFAULT ''")

    # Migration: 加入 Phase 41b user_tags 欄位
    if 'user_tags' not in existing_cols:
        cursor.execute("ALTER TABLE videos ADD COLUMN user_tags TEXT DEFAULT '[]'")

    conn.commit()
    conn.close()


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
        data = dict(zip(columns, row))

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
        self.db_path = db_path or get_db_path()
        self._columns_cache: Optional[List[str]] = None

    def _get_connection(self) -> sqlite3.Connection:
        """取得資料庫連線"""
        return get_connection(self.db_path)

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

            # 取得 id
            cursor.execute("SELECT id FROM videos WHERE path = ?", (video.path,))
            row = cursor.fetchone()
            return row[0] if row else 0
        finally:
            conn.close()

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
            return count
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

        Args:
            actress_name: 女優名稱

        Returns:
            int: 包含該女優的影片數量
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # actresses 欄位是 JSON array，使用 LIKE 查詢
            # 需要處理完全匹配（避免部分匹配，例如 "miru" 匹配到 "miruku"）
            cursor.execute(
                """
                SELECT COUNT(*) FROM videos
                WHERE actresses LIKE ?
                   OR actresses LIKE ?
                   OR actresses LIKE ?
                   OR actresses = ?
                """,
                (
                    f'["{actress_name}",%',      # 開頭
                    f'%, "{actress_name}",%',    # 中間
                    f'%, "{actress_name}"]',     # 結尾
                    f'["{actress_name}"]'        # 唯一
                )
            )
            row = cursor.fetchone()
            return row[0] if row else 0
        finally:
            conn.close()

    def get_videos_by_actress(self, actress_name: str) -> List['Video']:
        """取得包含某女優的所有影片

        Args:
            actress_name: 女優名稱

        Returns:
            List[Video]: 包含該女優的影片列表
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                SELECT * FROM videos
                WHERE actresses LIKE ?
                   OR actresses LIKE ?
                   OR actresses LIKE ?
                   OR actresses = ?
                ORDER BY id
                """,
                (
                    f'["{actress_name}",%',
                    f'%, "{actress_name}",%',
                    f'%, "{actress_name}"]',
                    f'["{actress_name}"]'
                )
            )
            rows = cursor.fetchall()
            return [Video.from_row(row, self._get_columns()) for row in rows]
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

def migrate_json_to_sqlite(json_path: Path, db_path: Path = None,
                           delete_on_success: bool = True) -> dict:
    """遷移 JSON cache 到 SQLite

    Args:
        json_path: JSON 快取檔案路徑
        db_path: SQLite 資料庫路徑（預設為 output/openaver.db）
        delete_on_success: 成功後是否刪除 JSON 檔案

    Returns:
        dict: {'migrated': int, 'skipped': int, 'errors': int}
    """
    from core.gallery_scanner import VideoInfo

    result = {'migrated': 0, 'skipped': 0, 'errors': 0}

    if not Path(json_path).exists():
        return result

    # 確保資料庫已初始化
    if db_path is None:
        db_path = get_db_path()
    init_db(db_path)

    # 讀取 JSON
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        result['errors'] = 1
        return result

    repo = VideoRepository(db_path)
    videos_to_upsert = []

    for path_key, entry in cache_data.items():
        # 跳過 _metadata
        if path_key == '_metadata':
            result['skipped'] += 1
            continue

        try:
            # 取得 info 資料
            info_dict = entry.get('info', {})
            if not info_dict:
                result['skipped'] += 1
                continue

            # 建立 VideoInfo
            video_info = VideoInfo.from_dict(info_dict)

            # 轉換為 Video
            video = Video.from_video_info(video_info)

            # 設定 mtime 和 nfo_mtime（從 cache entry 取得，不是從 info 取得）
            video.mtime = entry.get('mtime', 0.0)
            video.nfo_mtime = entry.get('nfo_mtime', 0.0)

            videos_to_upsert.append(video)
        except Exception as e:
            result['errors'] += 1

    # 批次寫入
    if videos_to_upsert:
        inserted, updated = repo.upsert_batch(videos_to_upsert)
        result['migrated'] = inserted + updated

    # 成功後刪除 JSON
    if delete_on_success and result['errors'] == 0 and result['migrated'] > 0:
        try:
            Path(json_path).unlink()
        except IOError:
            pass

    return result


@dataclass
class AliasRecord:
    """新版女優別名資料模型（平坦 group schema）"""
    primary_name: str = ""
    aliases: List[str] = field(default_factory=list)  # JSON array
    source: str = "manual"  # 'manual' | 'auto'
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """轉為字典（JSON 欄位序列化）"""
        data = asdict(self)
        data["aliases"] = json.dumps(self.aliases, ensure_ascii=False)
        if self.created_at:
            data["created_at"] = self.created_at.isoformat()
        if self.updated_at:
            data["updated_at"] = self.updated_at.isoformat()
        return data

    @classmethod
    def from_row(cls, row: tuple, columns: List[str]) -> "AliasRecord":
        """從資料庫 row 建立"""
        data = dict(zip(columns, row))
        if "aliases" in data and data["aliases"]:
            try:
                data["aliases"] = json.loads(data["aliases"])
            except json.JSONDecodeError:
                data["aliases"] = []
        else:
            data["aliases"] = []
        if "created_at" in data and data["created_at"]:
            if isinstance(data["created_at"], str):
                data["created_at"] = datetime.fromisoformat(data["created_at"])
        if "updated_at" in data and data["updated_at"]:
            if isinstance(data["updated_at"], str):
                data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        return cls(**data)


class AliasRepository:
    """新版女優別名資料存取層（平坦 group schema）"""

    def __init__(self, db_path: Path = None):
        self.db_path = db_path or get_db_path()

    def _get_connection(self) -> sqlite3.Connection:
        """取得資料庫連線"""
        return get_connection(self.db_path)

    def _get_columns(self) -> List[str]:
        """取得欄位名稱列表"""
        return ["primary_name", "aliases", "source", "created_at", "updated_at"]

    # ------------------------------------------------------------------
    # Read methods
    # ------------------------------------------------------------------

    def get_all(self) -> List[AliasRecord]:
        """取得所有別名組，依 primary_name 排序"""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM actress_aliases ORDER BY primary_name"
            )
            rows = cursor.fetchall()
            cols = self._get_columns()
            return [AliasRecord.from_row(row, cols) for row in rows]
        finally:
            conn.close()

    def get_by_primary(self, name: str) -> Optional[AliasRecord]:
        """根據 primary_name 查詢；不存在回傳 None"""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM actress_aliases WHERE primary_name = ?", (name,)
            )
            row = cursor.fetchone()
            if row:
                return AliasRecord.from_row(row, self._get_columns())
            return None
        finally:
            conn.close()

    def find_by_alias(self, alias: str) -> Optional[AliasRecord]:
        """在 aliases JSON 陣列中搜尋；不存在回傳 None"""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                """SELECT aa.* FROM actress_aliases aa, json_each(aa.aliases)
                   WHERE json_each.value = ?""",
                (alias,),
            )
            row = cursor.fetchone()
            if row:
                return AliasRecord.from_row(row, self._get_columns())
            return None
        finally:
            conn.close()

    def resolve(self, name: str) -> set:
        """
        解析名稱：
        - primary hit  → {primary_name} ∪ set(aliases)
        - alias hit    → {primary_name} ∪ set(aliases)
        - miss         → {name}
        """
        record = self.get_by_primary(name)
        if record is None:
            record = self.find_by_alias(name)
        if record is None:
            return {name}
        return {record.primary_name} | set(record.aliases)

    # ------------------------------------------------------------------
    # Write methods — all use BEGIN EXCLUSIVE
    # ------------------------------------------------------------------

    def add(
        self,
        primary_name: str,
        aliases: Optional[List[str]] = None,
        source: str = "manual",
    ) -> AliasRecord:
        """
        新增別名組。

        Raises:
            ValueError: primary_name 已存在（作為 primary 或 alias）
        """
        if aliases is None:
            aliases = []

        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("BEGIN EXCLUSIVE")

            # 全域唯一檢查 primary_name
            ok, msg = self._check_global_uniqueness_cursor(cursor, primary_name)
            if not ok:
                raise ValueError(msg)

            # 全域唯一檢查每個 alias
            for alias in aliases:
                ok, msg = self._check_global_uniqueness_cursor(cursor, alias)
                if not ok:
                    raise ValueError(f"alias '{alias}': {msg}")

            aliases_json = json.dumps(aliases, ensure_ascii=False)
            cursor.execute(
                """INSERT INTO actress_aliases (primary_name, aliases, source)
                   VALUES (?, ?, ?)""",
                (primary_name, aliases_json, source),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        return self.get_by_primary(primary_name)

    def add_alias(self, primary_name: str, alias: str) -> tuple:
        """
        為既有 group 新增一個 alias。

        Returns:
            (True, None)       — 成功
            (False, error_msg) — 衝突
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("BEGIN EXCLUSIVE")

            # 確認 primary 存在
            cursor.execute(
                "SELECT aliases FROM actress_aliases WHERE primary_name = ?",
                (primary_name,),
            )
            row = cursor.fetchone()
            if row is None:
                return False, f"'{primary_name}' 不存在"

            # 全域唯一檢查（排除自己的 group）
            ok, msg = self._check_global_uniqueness_cursor(
                cursor, alias, exclude_primary=primary_name
            )
            if not ok:
                conn.rollback()
                return False, msg

            current = json.loads(row[0]) if row[0] else []
            if alias not in current:
                current.append(alias)
            cursor.execute(
                """UPDATE actress_aliases
                   SET aliases = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE primary_name = ?""",
                (json.dumps(current, ensure_ascii=False), primary_name),
            )
            conn.commit()
            return True, None
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def remove_alias(self, primary_name: str, alias: str) -> bool:
        """
        從 group 中移除一個 alias。

        Returns:
            True  — 成功移除
            False — alias 不存在
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("BEGIN EXCLUSIVE")
            cursor.execute(
                "SELECT aliases FROM actress_aliases WHERE primary_name = ?",
                (primary_name,),
            )
            row = cursor.fetchone()
            if row is None:
                return False
            current = json.loads(row[0]) if row[0] else []
            if alias not in current:
                return False
            current.remove(alias)
            cursor.execute(
                """UPDATE actress_aliases
                   SET aliases = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE primary_name = ?""",
                (json.dumps(current, ensure_ascii=False), primary_name),
            )
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def delete(self, name: str) -> bool:
        """
        刪除 group。name 可為 primary 或 alias（先 resolve 取得 primary）。

        Returns:
            True  — 成功刪除
            False — 不存在
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("BEGIN EXCLUSIVE")

            # 解析 primary_name
            cursor.execute(
                "SELECT primary_name FROM actress_aliases WHERE primary_name = ?",
                (name,),
            )
            row = cursor.fetchone()
            if row is None:
                # 試 alias
                cursor.execute(
                    """SELECT aa.primary_name FROM actress_aliases aa, json_each(aa.aliases)
                       WHERE json_each.value = ?""",
                    (name,),
                )
                row = cursor.fetchone()
            if row is None:
                return False

            primary = row[0]
            cursor.execute(
                "DELETE FROM actress_aliases WHERE primary_name = ?", (primary,)
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def sync_from_favorite(
        self, name: str, aliases: List[str], source: str = "auto"
    ) -> dict:
        """
        從 favorite 同步 alias group（resolve-first，CD-6）。

        Returns:
            {"primary_name": str, "skipped_aliases": list[str]}
        """
        # resolve name → 找到所屬 group (若有)
        resolved = self.resolve(name)
        target_record: Optional[AliasRecord] = None

        if len(resolved) > 1 or (len(resolved) == 1 and name not in resolved):
            # name 解析到某個 group
            primary_in_resolved = next(
                (n for n in resolved if self.get_by_primary(n) is not None), None
            )
            if primary_in_resolved:
                target_record = self.get_by_primary(primary_in_resolved)
        else:
            target_record = self.get_by_primary(name)

        target_primary = target_record.primary_name if target_record else name

        conn = self._get_connection()
        cursor = conn.cursor()
        skipped: List[str] = []
        try:
            cursor.execute("BEGIN EXCLUSIVE")

            # 逐一檢查 incoming aliases
            merged_aliases: List[str] = list(target_record.aliases) if target_record else []
            for alias in aliases:
                if alias == target_primary or alias in merged_aliases:
                    continue
                ok, _ = self._check_global_uniqueness_cursor(
                    cursor, alias, exclude_primary=target_primary
                )
                if not ok:
                    skipped.append(alias)
                else:
                    merged_aliases.append(alias)

            aliases_json = json.dumps(merged_aliases, ensure_ascii=False)
            if target_record is None:
                cursor.execute(
                    """INSERT INTO actress_aliases (primary_name, aliases, source)
                       VALUES (?, ?, ?)""",
                    (target_primary, aliases_json, source),
                )
            else:
                cursor.execute(
                    """UPDATE actress_aliases
                       SET aliases = ?, source = ?, updated_at = CURRENT_TIMESTAMP
                       WHERE primary_name = ?""",
                    (aliases_json, source, target_primary),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        return {"primary_name": target_primary, "skipped_aliases": skipped}

    # ------------------------------------------------------------------
    # Private helper — cursor-based uniqueness check (within transaction)
    # ------------------------------------------------------------------

    def _check_global_uniqueness_cursor(
        self, cursor, name: str, exclude_primary: Optional[str] = None
    ) -> tuple:
        """
        Same as _check_global_uniqueness but uses an existing cursor (within a transaction).
        """
        # Check primary_name
        cursor.execute(
            "SELECT primary_name FROM actress_aliases WHERE primary_name = ?", (name,)
        )
        row = cursor.fetchone()
        if row and row[0] != exclude_primary:
            return False, f"'{name}' 已是 primary_name"

        # Check aliases (json_each)
        cursor.execute(
            """SELECT aa.primary_name FROM actress_aliases aa, json_each(aa.aliases)
               WHERE json_each.value = ?""",
            (name,),
        )
        row = cursor.fetchone()
        if row and row[0] != exclude_primary:
            return False, f"'{name}' 已經是 '{row[0]}' 的別名"

        return True, None


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
        data = dict(zip(columns, row))

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


class ActressRepository:
    """女優資料存取層"""

    def __init__(self, db_path: Path = None):
        self.db_path = db_path or get_db_path()

    def _get_connection(self) -> sqlite3.Connection:
        """取得資料庫連線"""
        return get_connection(self.db_path)

    def _get_columns(self) -> List[str]:
        """取得欄位名稱列表"""
        return [
            'name', 'name_en', 'birth', 'height', 'cup',
            'bust', 'waist', 'hip', 'hometown', 'hobby',
            'aliases', 'agency', 'debut_work', 'tags', 'nickname',
            'blog_url', 'official_url', 'photo_source', 'primary_text_source',
            'created_at', 'updated_at',
        ]

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
            update_parts = [
                f"{col} = excluded.{col}"
                for col in columns
                if col != 'name'
            ]
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
