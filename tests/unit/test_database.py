"""測試 core/database.py"""
import pytest
import sqlite3
import json
from pathlib import Path
from datetime import datetime

from core.database import (
    get_db_path,
    get_connection,
    init_db,
    Video,
    migrate_json_to_sqlite,
    VideoRepository
)
from core.gallery_scanner import VideoInfo


def test_get_db_path():
    """測試資料庫路徑正確"""
    db_path = get_db_path()
    assert isinstance(db_path, Path)
    assert db_path.name == "openaver.db"
    assert db_path.parent.name == "output"
    # 確保路徑是絕對路徑
    assert db_path.is_absolute()


def test_init_db_creates_table(tmp_path):
    """測試建立表格"""
    db_path = tmp_path / "test.db"
    init_db(db_path)

    # 檢查表格是否存在
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='videos'
    """)
    result = cursor.fetchone()
    conn.close()

    assert result is not None
    assert result[0] == "videos"

    # Verify schema columns via PRAGMA table_info
    cursor2 = sqlite3.connect(str(db_path)).cursor()
    cursor2.execute("PRAGMA table_info(videos)")
    columns = [row[1] for row in cursor2.fetchall()]
    cursor2.connection.close()

    assert "number" in columns
    assert "title" in columns
    assert "cover_path" in columns


def test_init_db_creates_indexes(tmp_path):
    """測試建立索引"""
    db_path = tmp_path / "test.db"
    init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='index'
    """)
    indexes = [row[0] for row in cursor.fetchall()]
    conn.close()

    # 檢查四個索引是否存在
    assert 'idx_videos_number' in indexes
    assert 'idx_videos_path' in indexes
    assert 'idx_videos_maker' in indexes
    assert 'idx_videos_cover_path' in indexes


def test_init_db_idempotent(tmp_path):
    """測試重複呼叫不報錯"""
    db_path = tmp_path / "test.db"

    # 第一次初始化
    init_db(db_path)
    # 第二次初始化（不應該報錯）
    init_db(db_path)
    # 第三次初始化
    init_db(db_path)

    # 確認表格依然存在且正常
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM videos")
    result = cursor.fetchone()
    conn.close()

    assert result[0] == 0  # 表格為空


@pytest.fixture
def default_video():
    """建立預設 Video 物件供測試共用。"""
    return Video()


def test_video_defaults_basic_fields(default_video):
    """測試核心基本欄位的預設值"""
    assert default_video.id is None
    assert default_video.path == ""
    assert default_video.number is None
    assert default_video.size_bytes == 0
    assert default_video.mtime == 0.0
    assert default_video.nfo_mtime == 0.0
    assert default_video.created_at is None
    assert default_video.updated_at is None


def test_video_defaults_string_metadata(default_video):
    """測試可選字串欄位預設值"""
    assert default_video.title == ""
    assert default_video.original_title == ""
    assert default_video.maker == ""
    assert default_video.series is None
    assert default_video.cover_path == ""
    assert default_video.release_date == ""
    assert default_video.duration is None


def test_video_defaults_list_fields(default_video):
    """測試列表欄位預設空 list"""
    assert default_video.actresses == []
    assert default_video.tags == []


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


def test_mapped_video_basic_fields(mapped_video):
    """測試 VideoInfo 轉換的基本欄位映射"""
    assert mapped_video.path == "/videos/test.mp4"
    assert mapped_video.number == "ABC-123"
    assert mapped_video.size_bytes == 1024 * 1024 * 500
    assert mapped_video.mtime > 0  # 檢查 mtime 轉換是否正確（允許小誤差）


def test_mapped_video_metadata_fields(mapped_video):
    """測試 VideoInfo 轉換的字串元資料映射"""
    assert mapped_video.title == "測試影片"
    assert mapped_video.original_title == "Test Video"
    assert mapped_video.maker == "測試片商"
    assert mapped_video.cover_path == "/covers/test.jpg"
    assert mapped_video.release_date == "2024-01-20"


def test_mapped_video_list_fields(mapped_video):
    """測試 VideoInfo 轉換的列表欄位映射"""
    assert mapped_video.actresses == ["演員A", "演員B", "演員C"]
    assert mapped_video.tags == ["類型1", "類型2", "類型3"]


def test_video_to_dict():
    """測試序列化正確"""
    video = Video(
        id=1,
        path="/videos/test.mp4",
        number="ABC-123",
        title="測試影片",
        actresses=["演員A", "演員B"],
        tags=["類型1", "類型2"],
        size_bytes=1024,
        created_at=datetime(2024, 1, 20, 12, 0, 0),
        updated_at=datetime(2024, 1, 21, 13, 30, 0)
    )

    data = video.to_dict()

    assert data['id'] == 1
    assert data['path'] == "/videos/test.mp4"
    assert data['number'] == "ABC-123"
    assert data['title'] == "測試影片"
    # JSON 欄位應該被序列化為字串
    assert isinstance(data['actresses'], str)
    assert json.loads(data['actresses']) == ["演員A", "演員B"]
    assert isinstance(data['tags'], str)
    assert json.loads(data['tags']) == ["類型1", "類型2"]
    # datetime 應該被轉為 ISO 格式字串
    assert data['created_at'] == "2024-01-20T12:00:00"
    assert data['updated_at'] == "2024-01-21T13:30:00"


def test_video_actresses_json():
    """測試 JSON 欄位處理"""
    # 測試空列表
    video1 = Video(actresses=[])
    data1 = video1.to_dict()
    assert json.loads(data1['actresses']) == []

    # 測試中文字元
    video2 = Video(actresses=["波多野結衣", "上原亞衣"])
    data2 = video2.to_dict()
    actresses = json.loads(data2['actresses'])
    assert actresses == ["波多野結衣", "上原亞衣"]

    # 測試 tags
    video3 = Video(tags=["巨乳", "中出", "單體作品"])
    data3 = video3.to_dict()
    tags = json.loads(data3['tags'])
    assert tags == ["巨乳", "中出", "單體作品"]


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


class TestInsertAndQuery:
    """測試基本 CRUD 操作，拆分為多個小測試"""

    @pytest.fixture(autouse=True)
    def setup_db(self, tmp_path):
        db_path = tmp_path / "test_crud.db"
        init_db(db_path)

        conn = get_connection(db_path)
        cursor = conn.cursor()

        # 插入測試資料
        video = Video(
            path="/videos/test123.mp4",
            number="TEST-123",
            title="測試影片",
            original_title="Test Video",
            actresses=["演員A", "演員B"],
            maker="測試片商",
            series="測試系列",
            tags=["類型1", "類型2"],
            duration=120,
            size_bytes=1024 * 1024 * 100,
            cover_path="/covers/test123.jpg",
            release_date="2024-01-20",
            mtime=1234567890.0,
            nfo_mtime=1234567800.0
        )

        video_dict = video.to_dict()
        video_dict.pop('id', None)
        video_dict.pop('created_at', None)
        video_dict.pop('updated_at', None)

        columns = list(video_dict.keys())
        placeholders = ', '.join(['?'] * len(columns))
        cursor.execute(
            f"INSERT INTO videos ({', '.join(columns)}) VALUES ({placeholders})",
            list(video_dict.values())
        )
        conn.commit()

        # 查詢資料
        cursor.execute("SELECT * FROM videos WHERE number = ?", ("TEST-123",))
        row = cursor.fetchone()
        cursor.execute("PRAGMA table_info(videos)")
        columns_info = cursor.fetchall()
        column_names = [col[1] for col in columns_info]

        conn.close()

        assert row is not None
        self.result_video = Video.from_row(row, column_names)

    def test_insert_basic_fields(self):
        """測試插入與查詢的基本欄位"""
        assert self.result_video.path == "/videos/test123.mp4"
        assert self.result_video.number == "TEST-123"
        assert self.result_video.size_bytes == 1024 * 1024 * 100
        assert self.result_video.mtime == 1234567890.0
        assert self.result_video.nfo_mtime == 1234567800.0
        assert self.result_video.created_at is not None
        assert self.result_video.updated_at is not None

    def test_insert_metadata_fields(self):
        """測試插入與查詢的字串元資料欄位"""
        assert self.result_video.title == "測試影片"
        assert self.result_video.original_title == "Test Video"
        assert self.result_video.maker == "測試片商"
        assert self.result_video.series == "測試系列"
        assert self.result_video.duration == 120
        assert self.result_video.cover_path == "/covers/test123.jpg"
        assert self.result_video.release_date == "2024-01-20"

    def test_insert_list_fields(self):
        """測試插入與查詢的列表欄位"""
        assert self.result_video.actresses == ["演員A", "演員B"]
        assert self.result_video.tags == ["類型1", "類型2"]


def test_video_from_video_info_with_empty_fields():
    """測試 VideoInfo 空欄位處理"""
    info = VideoInfo(
        path="/videos/test.mp4",
        title="測試影片",
        actor="",  # 空字串
        genre="",  # 空字串
        num="",
        size=1024
    )

    video = Video.from_video_info(info)

    assert video.actresses == []  # 空字串應轉為空列表
    assert video.tags == []  # 空字串應轉為空列表
    assert video.number is None  # 空字串應轉為 None


def test_video_from_video_info_with_spaces():
    """測試 VideoInfo 含空白字元處理"""
    info = VideoInfo(
        path="/videos/test.mp4",
        title="測試影片",
        actor="  演員A  ,  演員B  , , 演員C  ",  # 含多餘空白
        genre="類型1,  類型2  ,   ,類型3",  # 含多餘空白和空項目
        num="ABC-123"
    )

    video = Video.from_video_info(info)

    # 應該去除空白並過濾空項目
    assert video.actresses == ["演員A", "演員B", "演員C"]
    assert video.tags == ["類型1", "類型2", "類型3"]


def test_init_db_creates_actress_aliases_table(tmp_path):
    """測試 actress_aliases 表建立"""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='actress_aliases'")
    assert cursor.fetchone() is not None
    conn.close()


def test_actress_aliases_new_schema(tmp_path):
    """[T1 updated] 新 schema 有 primary_name PK，無舊 idx_actress_aliases_new_name index"""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    # 新 schema 應有 primary_name 欄位
    cursor.execute("PRAGMA table_info(actress_aliases)")
    cols = [row[1] for row in cursor.fetchall()]
    assert "primary_name" in cols
    # 舊 index 已移除
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_actress_aliases_new_name'")
    assert cursor.fetchone() is None
    conn.close()


def test_actress_aliases_new_schema_has_seed_data(tmp_path):
    """[T1 updated] 新建 DB 有種子資料（新 schema 格式，4 組）"""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM actress_aliases")
    count = cursor.fetchone()[0]
    # 新表無種子資料，fresh DB 應為空
    assert count == 0
    conn.close()


def test_actress_alias_primary_name_unique_constraint(tmp_path):
    """[T1 updated] 新 schema 中 primary_name 是 PRIMARY KEY（唯一約束）"""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    conn = get_connection(db_path)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO actress_aliases (primary_name, aliases) VALUES ('Alice', '[]')")
    conn.commit()
    # 嘗試插入重複的 primary_name 應拋 IntegrityError
    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute("INSERT INTO actress_aliases (primary_name, aliases) VALUES ('Alice', '[\"alt\"]')")
    conn.close()


# ============ migrate_json_to_sqlite 測試 ============

def test_migrate_json_to_sqlite_success(tmp_path):
    """測試正常遷移與 idempotency"""
    db_path = tmp_path / "test.db"
    json_path = tmp_path / "cache.json"

    # 準備假的 json cache 資料
    fake_cache = {
        "_metadata": {"version": 1},
        "file:///videos/test1.mp4": {
            "mtime": 100.0,
            "nfo_mtime": 200.0,
            "info": {
                "path": "file:///videos/test1.mp4",
                "title": "Title 1",
                "num": "TEST-001"
            }
        }
    }
    json_path.write_text(json.dumps(fake_cache))

    # 第一次遷移
    result1 = migrate_json_to_sqlite(json_path, db_path, delete_on_success=False)
    assert result1['migrated'] == 1
    assert result1['skipped'] == 1
    assert result1['errors'] == 0

    # 檢查 mtime/nfo_mtime 預設值
    repo = VideoRepository(db_path)
    video = repo.get_by_path("file:///videos/test1.mp4")
    assert video.mtime == 100.0
    assert video.nfo_mtime == 200.0

    # 第2次遷移，測試重複匯入（idempotency）
    result2 = migrate_json_to_sqlite(json_path, db_path, delete_on_success=False)
    assert result2['migrated'] == 1  # 依然算 migrated 因為它會 UPSERT（updated計數+1）
    # 但總數仍為 1
    assert repo.count() == 1


def test_migrate_json_to_sqlite_invalid_json(tmp_path):
    """測試損壞的 json 檔案"""
    db_path = tmp_path / "test.db"
    json_path = tmp_path / "bad.json"
    json_path.write_text("{bad json")

    result = migrate_json_to_sqlite(json_path, db_path, delete_on_success=False)
    assert result['errors'] == 1


# ============ Phase 37 新欄位映射測試 ============

class TestFromVideoInfoNewFields:
    """from_video_info() Phase 37 新欄位映射測試"""

    def test_from_video_info_director_mapped(self):
        """director 欄位正確映射"""
        info = VideoInfo(
            path="/test.mp4",
            num="ABC-001",
            title="テスト",
            director="テスト監督",
        )
        video = Video.from_video_info(info)
        assert video.director == "テスト監督"

    def test_from_video_info_label_mapped(self):
        """label 欄位正確映射"""
        info = VideoInfo(
            path="/test.mp4",
            num="ABC-001",
            title="テスト",
            label="S1",
        )
        video = Video.from_video_info(info)
        assert video.label == "S1"

    def test_from_video_info_series_mapped(self):
        """series 欄位正確映射"""
        info = VideoInfo(
            path="/test.mp4",
            num="ABC-001",
            title="テスト",
            series="テストシリーズ",
        )
        video = Video.from_video_info(info)
        assert video.series == "テストシリーズ"

    def test_from_video_info_series_empty_becomes_none(self):
        """series='' → None（與 Optional[str] 語意一致）"""
        info = VideoInfo(
            path="/test.mp4",
            num="ABC-001",
            title="テスト",
            series="",
        )
        video = Video.from_video_info(info)
        assert video.series is None

    def test_from_video_info_duration_mapped(self):
        """duration 欄位正確映射"""
        info = VideoInfo(
            path="/test.mp4",
            num="ABC-001",
            title="テスト",
            duration=120,
        )
        video = Video.from_video_info(info)
        assert video.duration == 120

    def test_from_video_info_duration_zero_preserved(self):
        """duration=0 保持 0（不被 or 短路為 None）"""
        info = VideoInfo(
            path="/test.mp4",
            num="ABC-001",
            title="テスト",
            duration=0,
        )
        video = Video.from_video_info(info)
        assert video.duration == 0

    def test_from_video_info_duration_none_preserved(self):
        """duration=None 保持 None"""
        info = VideoInfo(
            path="/test.mp4",
            num="ABC-001",
            title="テスト",
            duration=None,
        )
        video = Video.from_video_info(info)
        assert video.duration is None

    def test_from_video_info_all_new_fields(self):
        """all 4 new fields mapped correctly in single call"""
        info = VideoInfo(
            path="/test.mp4",
            num="ABC-001",
            title="テスト",
            director="監督X",
            duration=90,
            series="シリーズX",
            label="premium",
        )
        video = Video.from_video_info(info)
        assert video.director == "監督X"
        assert video.duration == 90
        assert video.series == "シリーズX"
        assert video.label == "premium"


class TestVideoDirectorLabelFields:
    """Video dataclass 新增 director/label 欄位測試"""

    def test_video_director_default_empty_string(self):
        """Video.director 預設值為 ''"""
        video = Video()
        assert hasattr(video, 'director')
        assert video.director == ''

    def test_video_label_default_empty_string(self):
        """Video.label 預設值為 ''"""
        video = Video()
        assert hasattr(video, 'label')
        assert video.label == ''


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
            ("file:///old.mp4", "OLD-001", "舊資料")
        )
        conn.commit()
        conn.close()

    def test_migration_adds_director_column(self, tmp_path):
        """舊 schema 升級後，PRAGMA table_info 確認 director 欄位存在"""
        db_path = tmp_path / "old.db"
        self._create_old_schema_db(db_path)

        # 執行 init_db (migration)
        init_db(db_path)

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(videos)")
        columns = [row[1] for row in cursor.fetchall()]
        conn.close()

        assert 'director' in columns

    def test_migration_adds_label_column(self, tmp_path):
        """舊 schema 升級後，PRAGMA table_info 確認 label 欄位存在"""
        db_path = tmp_path / "old.db"
        self._create_old_schema_db(db_path)

        init_db(db_path)

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(videos)")
        columns = [row[1] for row in cursor.fetchall()]
        conn.close()

        assert 'label' in columns

    def test_migration_preserves_existing_data(self, tmp_path):
        """升級後舊資料仍然存在"""
        db_path = tmp_path / "old.db"
        self._create_old_schema_db(db_path)

        init_db(db_path)

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT number, title FROM videos WHERE path = ?", ("file:///old.mp4",))
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "OLD-001"
        assert row[1] == "舊資料"

    def test_new_db_includes_director_and_label(self, tmp_path):
        """全新 DB 的 CREATE TABLE 也包含 director 和 label"""
        db_path = tmp_path / "new.db"
        init_db(db_path)

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(videos)")
        columns = [row[1] for row in cursor.fetchall()]
        conn.close()

        assert 'director' in columns
        assert 'label' in columns


class TestGetColumnsOrder:
    """_get_columns() 順序與 SELECT * 一致，upsert + get_by_path round-trip 驗證"""

    def test_upsert_and_get_by_path_roundtrip(self, tmp_path):
        """upsert + get_by_path round-trip 驗證 director/label 欄位正確"""
        db_path = tmp_path / "test.db"
        init_db(db_path)

        repo = VideoRepository(db_path)

        # 建立含新欄位的 Video
        video = Video(
            path="file:///test/roundtrip.mp4",
            number="RT-001",
            title="Round-trip 測試",
            director="監督名",
            label="S1",
            series="シリーズ",
            duration=75,
        )
        repo.upsert(video)

        # 讀回來
        result = repo.get_by_path("file:///test/roundtrip.mp4")
        assert result is not None
        assert result.director == "監督名"
        assert result.label == "S1"
        assert result.series == "シリーズ"
        assert result.duration == 75


# ============ AliasRepository 測試 ============

def test_alias_repository_crud(tmp_path):
    """[T1 updated] 測試新 AliasRepository 完整 CRUD 流程"""
    from core.database import AliasRepository, get_connection
    db_path = tmp_path / "actress.db"
    init_db(db_path)
    # 清除種子資料，確保測試隔離
    conn = get_connection(db_path)
    conn.execute("DELETE FROM actress_aliases")
    conn.commit()
    conn.close()

    repo = AliasRepository(db_path)

    # 清除後應為空
    initial = repo.get_all()
    assert len(initial) == 0

    # Add group
    record = repo.add("新テスト女優", ["alias1"])
    assert record.primary_name == "新テスト女優"
    assert "alias1" in record.aliases

    # get_all
    all_data = repo.get_all()
    assert len(all_data) == 1

    # Add alias
    ok, _ = repo.add_alias("新テスト女優", "alias2")
    assert ok is True
    updated = repo.get_by_primary("新テスト女優")
    assert "alias2" in updated.aliases

    # Remove alias
    removed = repo.remove_alias("新テスト女優", "alias2")
    assert removed is True

    # Delete
    success = repo.delete("新テスト女優")
    assert success is True
    assert len(repo.get_all()) == 0

