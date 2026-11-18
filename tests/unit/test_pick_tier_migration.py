"""TASK-201-T1：精選等級升級遷移 oracle（CD-201-2）。

守住兩條行為：
1. 舊 DB 升級 → 原本精選的片全變金；之後改的銀／銅再開程式不被洗回金（冪等）。
2. 全新 DB／無 user_rating 欄的舊 DB：欄位在遷移之後才由 init_db ALTER 建立，
   若不寫標記，第二次啟動會把使用者設的銅升成金。
"""
import sqlite3

import pytest

from core.database import VideoRepository, init_db
from core.path_utils import to_file_uri

_OLD_VIDEOS_SQL = """
    CREATE TABLE videos (
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
        auto_focal TEXT DEFAULT '',
        crop_mode TEXT NOT NULL DEFAULT 'auto',
        focal_attempted_at TIMESTAMP DEFAULT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
"""


def _create_old_schema_db(db_path, ratings):
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute(_OLD_VIDEOS_SQL)
    cursor.execute("ALTER TABLE videos ADD COLUMN user_rating INTEGER NOT NULL DEFAULT 0")
    for i, r in enumerate(ratings):
        cursor.execute(
            "INSERT INTO videos (path, number, title, user_rating) VALUES (?, ?, ?, ?)",
            (to_file_uri(f"/pick_tier_old_{i}.mp4"), f"PICK-{i}", f"舊片{i}", r),
        )
    conn.commit()
    conn.close()


def _ratings_of(db_path):
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("SELECT user_rating FROM videos ORDER BY number").fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def test_upgrade_marks_existing_picks_gold_and_is_idempotent(tmp_path):
    db_path = tmp_path / "pick_tier_upgrade.db"
    _create_old_schema_db(db_path, [0, 1, 1])

    init_db(db_path)
    assert _ratings_of(db_path) == [0, 3, 3]

    repo = VideoRepository(db_path)
    assert repo.set_user_rating(to_file_uri("/pick_tier_old_1.mp4"), 2) is True
    assert repo.set_user_rating(to_file_uri("/pick_tier_old_2.mp4"), 1) is True

    init_db(db_path)
    init_db(db_path)
    assert _ratings_of(db_path) == [0, 2, 1]


@pytest.mark.parametrize("with_old_schema", [False, True])
def test_new_db_second_init_keeps_bronze(tmp_path, with_old_schema):
    db_path = tmp_path / "pick_tier_fresh.db"
    if with_old_schema:
        conn = sqlite3.connect(str(db_path))
        conn.execute(_OLD_VIDEOS_SQL)
        conn.commit()
        conn.close()

    init_db(db_path)

    repo = VideoRepository(db_path)
    path = to_file_uri("/pick_tier_bronze.mp4")
    from core.database import Video
    repo.upsert(Video(path=path, title="新片"))
    assert repo.set_user_rating(path, 1) is True

    init_db(db_path)
    assert repo.get_by_path(path).user_rating == 1
