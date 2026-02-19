"""測試 VideoRepository 類別"""
import pytest
import json
from pathlib import Path

from core.database import (
    init_db,
    Video,
    VideoRepository,
    migrate_json_to_sqlite
)


# temp_db fixture 定義於 tests/unit/conftest.py


@pytest.fixture
def sample_video():
    """建立測試用影片"""
    return Video(
        path="file:///C:/Videos/test.mp4",
        number="ABC-123",
        title="測試影片",
        original_title="Test Video",
        actresses=["演員A", "演員B"],
        maker="測試片商",
        series="測試系列",
        tags=["類型1", "類型2"],
        duration=120,
        size_bytes=1024 * 1024 * 100,
        cover_path="file:///C:/Videos/test.jpg",
        release_date="2024-01-20",
        mtime=1234567890.0,
        nfo_mtime=1234567800.0
    )


class TestVideoRepository:
    """VideoRepository 測試"""

    def test_init_with_default_path(self):
        """測試預設路徑初始化"""
        repo = VideoRepository()
        assert repo.db_path.name == "openaver.db"

    def test_init_with_custom_path(self, temp_db):
        """測試自訂路徑初始化"""
        repo = VideoRepository(temp_db)
        assert repo.db_path == temp_db

    def test_upsert_insert(self, temp_db, sample_video):
        """測試 upsert 新增"""
        repo = VideoRepository(temp_db)
        video_id = repo.upsert(sample_video)

        assert video_id > 0
        assert repo.count() == 1

    def test_upsert_update(self, temp_db, sample_video):
        """測試 upsert 更新"""
        repo = VideoRepository(temp_db)

        # 第一次插入
        video_id1 = repo.upsert(sample_video)

        # 修改標題後再次 upsert
        sample_video.title = "修改後的標題"
        video_id2 = repo.upsert(sample_video)

        # id 應該相同
        assert video_id1 == video_id2
        assert repo.count() == 1

        # 驗證標題已更新
        result = repo.get_by_path(sample_video.path)
        assert result.title == "修改後的標題"

    def test_upsert_batch_insert(self, temp_db):
        """測試 upsert_batch 批次新增"""
        repo = VideoRepository(temp_db)

        videos = [
            Video(path="file:///video1.mp4", title="影片1", mtime=100.0),
            Video(path="file:///video2.mp4", title="影片2", mtime=200.0),
            Video(path="file:///video3.mp4", title="影片3", mtime=300.0),
        ]

        inserted, updated = repo.upsert_batch(videos)

        assert inserted == 3
        assert updated == 0
        assert repo.count() == 3

    def test_upsert_batch_mixed(self, temp_db):
        """測試 upsert_batch 混合新增更新"""
        repo = VideoRepository(temp_db)

        # 先插入兩部
        initial_videos = [
            Video(path="file:///video1.mp4", title="影片1", mtime=100.0),
            Video(path="file:///video2.mp4", title="影片2", mtime=200.0),
        ]
        repo.upsert_batch(initial_videos)

        # 批次操作：1 部更新 + 1 部新增
        batch_videos = [
            Video(path="file:///video1.mp4", title="影片1-更新", mtime=150.0),
            Video(path="file:///video3.mp4", title="影片3", mtime=300.0),
        ]
        inserted, updated = repo.upsert_batch(batch_videos)

        assert inserted == 1
        assert updated == 1
        assert repo.count() == 3

    def test_upsert_batch_empty(self, temp_db):
        """測試 upsert_batch 空列表"""
        repo = VideoRepository(temp_db)
        inserted, updated = repo.upsert_batch([])
        assert inserted == 0
        assert updated == 0

    def test_get_by_path_found(self, temp_db, sample_video):
        """測試 get_by_path 找到"""
        repo = VideoRepository(temp_db)
        repo.upsert(sample_video)

        result = repo.get_by_path(sample_video.path)

        assert result is not None
        assert result.path == sample_video.path
        assert result.number == sample_video.number
        assert result.title == sample_video.title
        assert result.actresses == sample_video.actresses
        assert result.tags == sample_video.tags

    def test_get_by_path_not_found(self, temp_db):
        """測試 get_by_path 找不到"""
        repo = VideoRepository(temp_db)
        result = repo.get_by_path("file:///not_exist.mp4")
        assert result is None

    def test_get_all_empty(self, temp_db):
        """測試 get_all 空資料庫"""
        repo = VideoRepository(temp_db)
        result = repo.get_all()
        assert result == []

    def test_get_all_with_data(self, temp_db):
        """測試 get_all 有資料"""
        repo = VideoRepository(temp_db)

        videos = [
            Video(path="file:///video1.mp4", title="影片1", mtime=100.0),
            Video(path="file:///video2.mp4", title="影片2", mtime=200.0),
        ]
        repo.upsert_batch(videos)

        result = repo.get_all()

        assert len(result) == 2
        assert result[0].path == "file:///video1.mp4"
        assert result[1].path == "file:///video2.mp4"

    def test_get_mtime_index(self, temp_db):
        """測試 get_mtime_index"""
        repo = VideoRepository(temp_db)

        videos = [
            Video(path="file:///video1.mp4", mtime=100.5, nfo_mtime=100.0),
            Video(path="file:///video2.mp4", mtime=200.5, nfo_mtime=200.0),
        ]
        repo.upsert_batch(videos)

        index = repo.get_mtime_index()

        assert len(index) == 2
        assert index["file:///video1.mp4"] == (100.5, 100.0)
        assert index["file:///video2.mp4"] == (200.5, 200.0)

    def test_delete_by_paths(self, temp_db):
        """測試 delete_by_paths"""
        repo = VideoRepository(temp_db)

        videos = [
            Video(path="file:///video1.mp4", mtime=100.0),
            Video(path="file:///video2.mp4", mtime=200.0),
            Video(path="file:///video3.mp4", mtime=300.0),
        ]
        repo.upsert_batch(videos)

        deleted = repo.delete_by_paths(["file:///video1.mp4", "file:///video3.mp4"])

        assert deleted == 2
        assert repo.count() == 1
        assert repo.get_by_path("file:///video2.mp4") is not None

    def test_delete_by_paths_empty(self, temp_db):
        """測試 delete_by_paths 空列表"""
        repo = VideoRepository(temp_db)
        deleted = repo.delete_by_paths([])
        assert deleted == 0

    def test_delete_by_paths_not_exist(self, temp_db):
        """測試 delete_by_paths 刪除不存在的路徑"""
        repo = VideoRepository(temp_db)
        deleted = repo.delete_by_paths(["file:///not_exist.mp4"])
        assert deleted == 0

    def test_count_empty(self, temp_db):
        """測試 count 空資料庫"""
        repo = VideoRepository(temp_db)
        assert repo.count() == 0

    def test_count_with_data(self, temp_db):
        """測試 count 有資料"""
        repo = VideoRepository(temp_db)

        videos = [
            Video(path="file:///video1.mp4", mtime=100.0),
            Video(path="file:///video2.mp4", mtime=200.0),
            Video(path="file:///video3.mp4", mtime=300.0),
        ]
        repo.upsert_batch(videos)

        assert repo.count() == 3


    def test_clear_all_empty(self, temp_db):
        """測試 clear_all 空資料庫"""
        repo = VideoRepository(temp_db)
        deleted = repo.clear_all()
        assert deleted == 0
        assert repo.count() == 0

    def test_clear_all_with_data(self, temp_db):
        """測試 clear_all 有資料"""
        repo = VideoRepository(temp_db)
        videos = [
            Video(path="file:///video1.mp4", mtime=100.0),
            Video(path="file:///video2.mp4", mtime=200.0),
            Video(path="file:///video3.mp4", mtime=300.0),
        ]
        repo.upsert_batch(videos)
        assert repo.count() == 3

        deleted = repo.clear_all()
        assert deleted == 3
        assert repo.count() == 0


class TestMigrateJsonToSqlite:
    """migrate_json_to_sqlite 測試"""

    def test_migrate_basic(self, tmp_path):
        """測試基本遷移"""
        db_path = tmp_path / "test.db"
        json_path = tmp_path / "cache.json"

        # 建立 JSON cache
        cache_data = {
            "/path/to/video1.mp4": {
                "mtime": 1234567890.0,
                "nfo_mtime": 1234567800.0,
                "info": {
                    "path": "file:///C:/video1.mp4",
                    "title": "影片1",
                    "originaltitle": "Video 1",
                    "actor": "演員A,演員B",
                    "num": "ABC-001",
                    "maker": "片商1",
                    "date": "2024-01-01",
                    "genre": "類型1,類型2",
                    "size": 1024,
                    "mtime": 133500000000000000,
                    "img": "file:///C:/cover1.jpg"
                }
            },
            "/path/to/video2.mp4": {
                "mtime": 1234567891.0,
                "nfo_mtime": 1234567801.0,
                "info": {
                    "path": "file:///C:/video2.mp4",
                    "title": "影片2",
                    "originaltitle": "",
                    "actor": "",
                    "num": "ABC-002",
                    "maker": "",
                    "date": "",
                    "genre": "",
                    "size": 2048,
                    "mtime": 133500000000000000,
                    "img": ""
                }
            }
        }

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f)

        result = migrate_json_to_sqlite(json_path, db_path, delete_on_success=False)

        assert result['migrated'] == 2
        assert result['skipped'] == 0
        assert result['errors'] == 0

        # 驗證資料庫內容
        repo = VideoRepository(db_path)
        assert repo.count() == 2

        video1 = repo.get_by_path("file:///C:/video1.mp4")
        assert video1 is not None
        assert video1.title == "影片1"
        assert video1.number == "ABC-001"
        assert video1.actresses == ["演員A", "演員B"]
        assert video1.mtime == 1234567890.0
        assert video1.nfo_mtime == 1234567800.0

    def test_migrate_skip_metadata(self, tmp_path):
        """測試遷移時跳過 _metadata"""
        db_path = tmp_path / "test.db"
        json_path = tmp_path / "cache.json"

        cache_data = {
            "_metadata": {
                "last_run": "2026-01-21T00:18:22.552708",
                "last_added": 2
            },
            "/path/to/video.mp4": {
                "mtime": 1234567890.0,
                "nfo_mtime": 0,
                "info": {
                    "path": "file:///C:/video.mp4",
                    "title": "影片",
                    "originaltitle": "",
                    "actor": "",
                    "num": "ABC-001",
                    "maker": "",
                    "date": "",
                    "genre": "",
                    "size": 1024,
                    "mtime": 0,
                    "img": ""
                }
            }
        }

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f)

        result = migrate_json_to_sqlite(json_path, db_path, delete_on_success=False)

        assert result['migrated'] == 1
        assert result['skipped'] == 1  # _metadata 被跳過
        assert result['errors'] == 0

    def test_migrate_delete_on_success(self, tmp_path):
        """測試遷移成功後刪除 JSON"""
        db_path = tmp_path / "test.db"
        json_path = tmp_path / "cache.json"

        cache_data = {
            "/path/to/video.mp4": {
                "mtime": 1234567890.0,
                "nfo_mtime": 0,
                "info": {
                    "path": "file:///C:/video.mp4",
                    "title": "影片",
                    "originaltitle": "",
                    "actor": "",
                    "num": "ABC-001",
                    "maker": "",
                    "date": "",
                    "genre": "",
                    "size": 1024,
                    "mtime": 0,
                    "img": ""
                }
            }
        }

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f)

        result = migrate_json_to_sqlite(json_path, db_path, delete_on_success=True)

        assert result['migrated'] == 1
        assert not json_path.exists()  # JSON 應該被刪除

    def test_migrate_not_delete_when_disabled(self, tmp_path):
        """測試遷移成功但不刪除 JSON"""
        db_path = tmp_path / "test.db"
        json_path = tmp_path / "cache.json"

        cache_data = {
            "/path/to/video.mp4": {
                "mtime": 1234567890.0,
                "nfo_mtime": 0,
                "info": {
                    "path": "file:///C:/video.mp4",
                    "title": "影片",
                    "originaltitle": "",
                    "actor": "",
                    "num": "",
                    "maker": "",
                    "date": "",
                    "genre": "",
                    "size": 1024,
                    "mtime": 0,
                    "img": ""
                }
            }
        }

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f)

        result = migrate_json_to_sqlite(json_path, db_path, delete_on_success=False)

        assert result['migrated'] == 1
        assert json_path.exists()  # JSON 應該保留

    def test_migrate_nonexistent_json(self, tmp_path):
        """測試遷移不存在的 JSON"""
        db_path = tmp_path / "test.db"
        json_path = tmp_path / "not_exist.json"

        result = migrate_json_to_sqlite(json_path, db_path)

        assert result['migrated'] == 0
        assert result['skipped'] == 0
        assert result['errors'] == 0

    def test_migrate_invalid_json(self, tmp_path):
        """測試遷移無效 JSON"""
        db_path = tmp_path / "test.db"
        json_path = tmp_path / "invalid.json"

        with open(json_path, 'w') as f:
            f.write("{ invalid json }")

        result = migrate_json_to_sqlite(json_path, db_path)

        assert result['errors'] == 1

    def test_migrate_empty_info(self, tmp_path):
        """測試遷移空 info 的項目"""
        db_path = tmp_path / "test.db"
        json_path = tmp_path / "cache.json"

        cache_data = {
            "/path/to/video.mp4": {
                "mtime": 1234567890.0,
                "info": {}  # 空 info
            }
        }

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f)

        result = migrate_json_to_sqlite(json_path, db_path, delete_on_success=False)

        assert result['skipped'] == 1
        assert result['migrated'] == 0
