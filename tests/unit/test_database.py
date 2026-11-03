"""測試 core/database.py"""
import pytest
import sqlite3
from pathlib import Path

from core.database import (
    get_connection,
    init_db,
    Video,
    VideoRepository,
)
from core.gallery_scanner import VideoInfo
from core.path_utils import to_file_uri


@pytest.fixture
def mapped_video():
    """準備 VideoInfo 轉換後的 Video 物件供測試"""
    info = VideoInfo(
        path="/videos/test.mp4",
        title="測試影片",
        originaltitle="Test Video",
        actor="演員A, 演員B, 演員C",
        num="ABC-123",
        maker="測試片商",
        date="2024-01-20",
        genre="類型1, 類型2, 類型3",
        size=1024 * 1024 * 500,  # 500MB
        mtime=133500000000000000,  # FileTime 格式
        img="/covers/test.jpg"
    )
    return Video.from_video_info(info)


def test_mapped_video_list_fields(mapped_video):
    """測試 VideoInfo 轉換的列表欄位映射"""
    assert mapped_video.actresses == ["演員A", "演員B", "演員C"]
    assert mapped_video.tags == ["類型1", "類型2", "類型3"]


def test_connection_wal_mode(tmp_path):
    """測試 WAL 模式啟用"""
    db_path = tmp_path / "test_wal.db"
    conn = get_connection(db_path)

    # 檢查 WAL 模式是否啟用
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode")
    result = cursor.fetchone()
    conn.close()

    assert result[0].lower() == "wal"


# ============ migrate_json_to_sqlite 測試 ============


# ============ Phase 37 新欄位映射測試 ============


class TestDbMigration:
    """DB migration 測試：舊 schema 升級後確認新欄位存在"""

    def _create_old_schema_db(self, db_path: Path):
        """建立沒有 director/label 的舊 schema DB"""
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE videos (
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
        # 插入一筆舊資料
        cursor.execute(
            "INSERT INTO videos (path, number, title) VALUES (?, ?, ?)",
            (to_file_uri("/old.mp4"), "OLD-001", "舊資料")
        )
        conn.commit()
        conn.close()

    def test_migration_adds_director_column(self, tmp_path):
        """最舊 schema 升級後，PRAGMA table_info 確認各代新增欄位全數補齊"""
        db_path = tmp_path / "old.db"
        self._create_old_schema_db(db_path)

        # 執行 init_db (migration)
        init_db(db_path)

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(videos)")
        columns = [row[1] for row in cursor.fetchall()]
        conn.close()

        for col in (
            'director', 'label', 'output_dir', 'scrape_attempted_at',
            'auto_focal', 'crop_mode', 'focal_attempted_at', 'user_rating', 'user_tags',
            'ai_tagged_at',
        ):
            assert col in columns, col

    def test_migration_preserves_existing_data(self, tmp_path):
        """升級後舊資料仍然存在"""
        db_path = tmp_path / "old.db"
        self._create_old_schema_db(db_path)

        init_db(db_path)

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT number, title FROM videos WHERE path = ?", (to_file_uri("/old.mp4"),))
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "OLD-001"
        assert row[1] == "舊資料"


class TestScrapeAttemptedAtField:
    """TASK-89b-T1: videos.scrape_attempted_at 欄位 — CREATE TABLE + 加法遷移 + backfill"""

    # 舊 schema 已含 output_dir（89a 早於本 task），唯獨缺 scrape_attempted_at
    _OLD_SCHEMA_SQL = """
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """

    def _create_old_schema_db(self, db_path: Path, rows: list[dict] | None = None):
        """建立沒有 scrape_attempted_at 的舊 schema DB（其餘欄位齊全，含 output_dir）。

        rows: list of {path, cover_path, nfo_mtime, output_dir} — 供 backfill 條件矩陣測試組裝。
        """
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute(self._OLD_SCHEMA_SQL)
        if rows is None:
            rows = [{
                "path": to_file_uri("/old_no_scrape_attempted_at.mp4"),
                "cover_path": "",
                "nfo_mtime": 0.0,
                "output_dir": "",
            }]
        for r in rows:
            cursor.execute(
                """INSERT INTO videos (path, number, title, cover_path, nfo_mtime, output_dir)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (r["path"], r.get("number", "OLD"), r.get("title", "舊資料"),
                 r["cover_path"], r["nfo_mtime"], r["output_dir"])
            )
        conn.commit()
        conn.close()


    def test_backfill_all_empty_stays_zero(self, tmp_path):
        """backfill: cover_path/nfo_mtime/output_dir 三者皆空/0 的純新片維持 0"""
        db_path = tmp_path / "old.db"
        path = to_file_uri("/backfill_untouched.mp4")
        self._create_old_schema_db(db_path, rows=[{
            "path": path, "cover_path": "",
            "nfo_mtime": 0.0, "output_dir": "",
        }])

        init_db(db_path)

        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT scrape_attempted_at FROM videos WHERE path = ?", (path,)
        ).fetchone()
        conn.close()

        assert row[0] == 0

    def test_backfill_output_dir_only_producer_row(self, tmp_path):
        """回歸鎖（Codex Finding-3）：output_dir != '' AND cover_path == '' AND nfo_mtime == 0
        （producer 生成片模擬，天生沒封面/nfo_mtime）升級後 scrape_attempted_at > 0"""
        db_path = tmp_path / "old.db"
        path = to_file_uri("/backfill_output_dir_only.mp4")
        self._create_old_schema_db(db_path, rows=[{
            "path": path, "cover_path": "",
            "nfo_mtime": 0.0, "output_dir": to_file_uri("/produced/OD-999"),
        }])

        init_db(db_path)

        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT scrape_attempted_at FROM videos WHERE path = ?", (path,)
        ).fetchone()
        conn.close()

        assert row[0] > 0


# ============ AliasRepository 測試 ============


# ============ 57b: DROP clip_embedding / clip_model_id 測試 ============

class TestClipColumnDrop:
    """spec-57 §2.6 + plan-57b CD-57b-4：DROP clip_embedding / clip_model_id（idempotent）"""

    def test_drop_clip_embedding_column_legacy_db(self, tmp_path):
        """legacy DB（v0.8.6 schema）：欄位存在，init_db 後被 DROP"""
        db_path = tmp_path / "legacy.db"
        # 模擬 v0.8.6 schema：手動建 table 含 clip 欄位（完整 column set，含 maker 等）
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.execute("""
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
                duration INTEGER,
                size_bytes INTEGER,
                cover_path TEXT,
                release_date TEXT,
                mtime REAL,
                nfo_mtime REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                clip_embedding BLOB DEFAULT NULL,
                clip_model_id TEXT DEFAULT NULL
            )
        """)
        conn.commit()
        conn.close()
        # 用 init_db 觸發 migration
        init_db(db_path)
        # 驗欄位已 DROP
        conn = sqlite3.connect(db_path)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(videos)").fetchall()}
        conn.close()
        assert 'clip_embedding' not in cols
        assert 'clip_model_id' not in cols


# ============ TASK-98a-T4: focal + crop_mode migration（CD-98a-6/-7/-8）============

class TestFocalCropMigration:
    """舊 DB（無 auto_focal/crop_mode/photo_fp_* 欄位）升級後：欄位補齊、既有 row 得預設值、
    仍可透過 get_by_path/get_by_name 正常讀出（Codex P1：actress SELECT * 長度不符 ValueError 守衛）。
    """

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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """

    _OLD_ACTRESSES_SQL = """
        CREATE TABLE actresses (
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
    """

    def _create_old_schema_db(self, db_path: Path):
        """建立沒有 focal/crop_mode/fp 欄位的舊 videos + actresses 表，各插入一筆既有資料。"""
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute(self._OLD_VIDEOS_SQL)
        cursor.execute(self._OLD_ACTRESSES_SQL)
        cursor.execute(
            "INSERT INTO videos (path, number, title) VALUES (?, ?, ?)",
            (to_file_uri("/old_focal_migration.mp4"), "OLD-FOCAL-001", "舊片"),
        )
        cursor.execute(
            "INSERT INTO actresses (name, name_en) VALUES (?, ?)",
            ("舊女優", "Old Actress"),
        )
        conn.commit()
        conn.close()

    def test_migration_adds_focal_and_fp_columns_to_actresses(self, tmp_path):
        """舊 actresses 表升級後 auto_focal/crop_mode/photo_fp_* 五欄存在"""
        db_path = tmp_path / "old_focal.db"
        self._create_old_schema_db(db_path)

        init_db(db_path)

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(actresses)")
        columns = [row[1] for row in cursor.fetchall()]
        conn.close()

        assert "auto_focal" in columns
        assert "crop_mode" in columns
        assert "photo_fp_path" in columns
        assert "photo_fp_mtime_ns" in columns
        assert "photo_fp_size" in columns


# ============ TASK-123-T1: user_rating migration（CD-123-2）============

class TestUserRatingMigration:
    """舊 DB（無 user_rating 欄位）升級後：欄位補齊、既有 row 得預設值 0，migration
    在已有欄位的 DB 上重跑不報錯不遺失既有值。"""

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

    def _create_old_schema_db(self, db_path: Path):
        """建立沒有 user_rating 欄位的舊 videos 表，插入一筆既有資料。"""
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute(self._OLD_VIDEOS_SQL)
        cursor.execute(
            "INSERT INTO videos (path, number, title) VALUES (?, ?, ?)",
            (to_file_uri("/old_user_rating_migration.mp4"), "OLD-UR-001", "舊片"),
        )
        conn.commit()
        conn.close()


    def test_migration_idempotent_preserves_existing_value_on_second_init(self, tmp_path):
        """第二次 init_db() 重跑不重置既有非預設值（PRAGMA existing_cols 已含
        user_rating → if 判斷跳過 ALTER TABLE，不觸碰既有值）。"""
        db_path = tmp_path / "old_user_rating.db"
        self._create_old_schema_db(db_path)

        init_db(db_path)  # 第一次：補齊欄位，預設 0

        repo = VideoRepository(db_path)
        path = to_file_uri("/old_user_rating_migration.mp4")
        assert repo.set_user_rating(path, 1) is True

        init_db(db_path)  # 第二次：column 已存在，應直接跳過

        result = repo.get_by_path(path)
        assert result is not None
        assert result.user_rating == 1


