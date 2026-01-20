"""SQLite 資料庫管理模組"""
import sqlite3
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, List
from datetime import datetime


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
            series TEXT,
            tags TEXT,
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

    # 創建女優別名表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS actress_aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            old_name TEXT NOT NULL UNIQUE,
            new_name TEXT NOT NULL,
            applied_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 創建索引
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_actress_aliases_new_name ON actress_aliases(new_name)
    """)

    # 插入種子資料
    cursor.execute("""
        INSERT OR IGNORE INTO actress_aliases (old_name, new_name) VALUES
        ('miru', '坂道みる'),
        ('橋本ありな', '新ありな'),
        ('河北彩伽', '河北彩花')
    """)

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
    series: Optional[str] = None
    tags: List[str] = field(default_factory=list)  # JSON
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
            series=None,  # VideoInfo 沒有 series 欄位
            tags=tags,
            duration=None,  # VideoInfo 沒有 duration 欄位
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

    def _get_connection(self) -> sqlite3.Connection:
        """取得資料庫連線"""
        return get_connection(self.db_path)

    def _get_columns(self) -> List[str]:
        """取得欄位名稱列表"""
        return [
            'id', 'path', 'number', 'title', 'original_title',
            'actresses', 'maker', 'series', 'tags', 'duration',
            'size_bytes', 'cover_path', 'release_date', 'mtime', 'nfo_mtime',
            'created_at', 'updated_at'
        ]

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
            update_clause = ', '.join([f"{col} = excluded.{col}" for col in columns if col != 'path'])

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
                update_clause = ', '.join([f"{col} = excluded.{col}" for col in columns if col != 'path'])

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
class ActressAlias:
    """女優別名對照"""
    id: Optional[int] = None
    old_name: str = ""
    new_name: str = ""
    applied_count: int = 0
    created_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """轉為字典"""
        data = asdict(self)
        if self.created_at:
            data['created_at'] = self.created_at.isoformat()
        return data

    @classmethod
    def from_row(cls, row: tuple, columns: List[str]) -> 'ActressAlias':
        """從資料庫 row 建立"""
        data = dict(zip(columns, row))
        if 'created_at' in data and data['created_at']:
            if isinstance(data['created_at'], str):
                data['created_at'] = datetime.fromisoformat(data['created_at'])
        return cls(**data)
