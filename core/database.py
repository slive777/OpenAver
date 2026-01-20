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
