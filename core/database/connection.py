"""core.database.connection — DB 路徑、連線與 schema 初始化（spec-87 子模組）。

get_db_path / get_connection / init_db / _migrate_old_aliases 同住於此。
"""
import sqlite3
import json
import time
from pathlib import Path

from core.logger import get_logger

logger = get_logger(__name__)


def get_db_path() -> Path:
    """獲取資料庫路徑 (output/openaver.db)"""
    # 使用專案根目錄下的 output 資料夾
    # __file__ = core/database/connection.py → 上溯三層才是 repo 根（87a 拆檔後
    # 本檔比原 core/database.py 深一層；三 .parent 還原 repo-root/output 預設位置）
    db_dir = Path(__file__).parent.parent.parent / "output"
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
            output_dir TEXT DEFAULT '',
            duration INTEGER,
            size_bytes INTEGER,
            cover_path TEXT,
            release_date TEXT,
            mtime REAL,
            nfo_mtime REAL,
            scrape_attempted_at REAL DEFAULT 0,
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
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_videos_cover_path ON videos(cover_path)
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
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    # 刪除舊 index（新 schema 不需要；IF EXISTS 保證 idempotent）
    cursor.execute("DROP INDEX IF EXISTS idx_actress_aliases_new_name")

    # 創建 tag 別名資料表（完全鏡射 actress_aliases schema，CD-58-3）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tag_aliases (
            primary_name  TEXT PRIMARY KEY,
            aliases       TEXT NOT NULL DEFAULT '[]',
            source        TEXT NOT NULL DEFAULT 'manual',
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

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

    # Migration: 加入 89a output_dir 欄位
    if 'output_dir' not in existing_cols:
        cursor.execute("ALTER TABLE videos ADD COLUMN output_dir TEXT DEFAULT ''")

    # Migration: 加入 89b scrape_attempted_at 欄位 + 一次性 backfill
    if 'scrape_attempted_at' not in existing_cols:
        cursor.execute("ALTER TABLE videos ADD COLUMN scrape_attempted_at REAL DEFAULT 0")
        cursor.execute(
            """UPDATE videos SET scrape_attempted_at = ?
               WHERE scrape_attempted_at = 0
               AND (cover_path != '' OR nfo_mtime > 0 OR output_dir != '')""",
            (time.time(),)
        )

    # Migration: 57b — 移除 v0.8.6 視覺搜尋欄位（idempotent；clean install 不爆）
    # DROP INDEX 必先於 DROP COLUMN（SQLite 不允許 drop 被 index 引用的 column）
    cursor.execute("DROP INDEX IF EXISTS idx_videos_clip_model_id")  # IF EXISTS 本身 idempotent  # 57d 連帶刪
    if 'clip_embedding' in existing_cols:  # 57d 連帶刪
        cursor.execute("ALTER TABLE videos DROP COLUMN clip_embedding")  # 57d 連帶刪
        existing_cols.discard('clip_embedding')  # 57d 連帶刪
    if 'clip_model_id' in existing_cols:  # 57d 連帶刪
        cursor.execute("ALTER TABLE videos DROP COLUMN clip_model_id")  # 57d 連帶刪
        existing_cols.discard('clip_model_id')  # 57d 連帶刪

    conn.commit()
    conn.close()
