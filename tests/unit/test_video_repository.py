"""測試 VideoRepository 類別"""
import pytest
import json
from unittest.mock import patch

from core.database import (
    Video,
    VideoRepository,
    migrate_json_to_sqlite
)
from core.path_utils import to_file_uri


# temp_db fixture 定義於 tests/unit/conftest.py


@pytest.fixture
def sample_video():
    """建立測試用影片"""
    return Video(
        path=to_file_uri("C:/Videos/test.mp4"),
        number="ABC-123",
        title="測試影片",
        original_title="Test Video",
        actresses=["演員A", "演員B"],
        maker="測試片商",
        series="測試系列",
        tags=["類型1", "類型2"],
        duration=120,
        size_bytes=1024 * 1024 * 100,
        cover_path=to_file_uri("C:/Videos/test.jpg"),
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
            Video(path=to_file_uri("/video1.mp4"), title="影片1", mtime=100.0),
            Video(path=to_file_uri("/video2.mp4"), title="影片2", mtime=200.0),
            Video(path=to_file_uri("/video3.mp4"), title="影片3", mtime=300.0),
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
            Video(path=to_file_uri("/video1.mp4"), title="影片1", mtime=100.0),
            Video(path=to_file_uri("/video2.mp4"), title="影片2", mtime=200.0),
        ]
        repo.upsert_batch(initial_videos)

        # 批次操作：1 部更新 + 1 部新增
        batch_videos = [
            Video(path=to_file_uri("/video1.mp4"), title="影片1-更新", mtime=150.0),
            Video(path=to_file_uri("/video3.mp4"), title="影片3", mtime=300.0),
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
        result = repo.get_by_path(to_file_uri("/not_exist.mp4"))
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
            Video(path=to_file_uri("/video1.mp4"), title="影片1", mtime=100.0),
            Video(path=to_file_uri("/video2.mp4"), title="影片2", mtime=200.0),
        ]
        repo.upsert_batch(videos)

        result = repo.get_all()

        assert len(result) == 2
        assert result[0].path == to_file_uri("/video1.mp4")
        assert result[1].path == to_file_uri("/video2.mp4")

    def test_get_mtime_index(self, temp_db):
        """測試 get_mtime_index"""
        repo = VideoRepository(temp_db)

        videos = [
            Video(path=to_file_uri("/video1.mp4"), mtime=100.5, nfo_mtime=100.0),
            Video(path=to_file_uri("/video2.mp4"), mtime=200.5, nfo_mtime=200.0),
        ]
        repo.upsert_batch(videos)

        index = repo.get_mtime_index()

        assert len(index) == 2
        assert index[to_file_uri("/video1.mp4")] == (100.5, 100.0)
        assert index[to_file_uri("/video2.mp4")] == (200.5, 200.0)

    def test_delete_by_paths(self, temp_db):
        """測試 delete_by_paths"""
        repo = VideoRepository(temp_db)

        videos = [
            Video(path=to_file_uri("/video1.mp4"), mtime=100.0),
            Video(path=to_file_uri("/video2.mp4"), mtime=200.0),
            Video(path=to_file_uri("/video3.mp4"), mtime=300.0),
        ]
        repo.upsert_batch(videos)

        deleted = repo.delete_by_paths([to_file_uri("/video1.mp4"), to_file_uri("/video3.mp4")])

        assert deleted == 2
        assert repo.count() == 1
        assert repo.get_by_path(to_file_uri("/video2.mp4")) is not None

    def test_delete_by_paths_empty(self, temp_db):
        """測試 delete_by_paths 空列表"""
        repo = VideoRepository(temp_db)
        deleted = repo.delete_by_paths([])
        assert deleted == 0

    def test_delete_by_paths_not_exist(self, temp_db):
        """測試 delete_by_paths 刪除不存在的路徑"""
        repo = VideoRepository(temp_db)
        deleted = repo.delete_by_paths([to_file_uri("/not_exist.mp4")])
        assert deleted == 0

    def test_count_empty(self, temp_db):
        """測試 count 空資料庫"""
        repo = VideoRepository(temp_db)
        assert repo.count() == 0

    def test_count_with_data(self, temp_db):
        """測試 count 有資料"""
        repo = VideoRepository(temp_db)

        videos = [
            Video(path=to_file_uri("/video1.mp4"), mtime=100.0),
            Video(path=to_file_uri("/video2.mp4"), mtime=200.0),
            Video(path=to_file_uri("/video3.mp4"), mtime=300.0),
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
            Video(path=to_file_uri("/video1.mp4"), mtime=100.0),
            Video(path=to_file_uri("/video2.mp4"), mtime=200.0),
            Video(path=to_file_uri("/video3.mp4"), mtime=300.0),
        ]
        repo.upsert_batch(videos)
        assert repo.count() == 3

        deleted = repo.clear_all()
        assert deleted == 3
        assert repo.count() == 0


class TestOutputDirProtectionAndOccupancy:
    """TASK-89a-T1: upsert/upsert_batch output_dir 對稱保護 + 佔用查詢 helper"""

    def test_upsert_preserves_output_dir_on_empty_incoming(self, temp_db):
        """upsert 傳空 output_dir（且 DB 已有非空既有值）→ 既有值不被覆寫"""
        repo = VideoRepository(temp_db)
        path = to_file_uri("/video1.mp4")

        v1 = Video(path=path, title="影片1", output_dir=to_file_uri("/produced/ABC-001"))
        repo.upsert(v1)

        v2 = Video(path=path, title="影片1-rescan", output_dir="")
        repo.upsert(v2)

        result = repo.get_by_path(path)
        assert result is not None
        assert result.output_dir == to_file_uri("/produced/ABC-001")

    def test_upsert_overwrites_output_dir_on_nonempty_incoming(self, temp_db):
        """upsert 傳非空 output_dir → 正常寫入/覆寫"""
        repo = VideoRepository(temp_db)
        path = to_file_uri("/video1.mp4")

        v1 = Video(path=path, title="影片1", output_dir=to_file_uri("/produced/ABC-001"))
        repo.upsert(v1)

        v2 = Video(path=path, title="影片1", output_dir=to_file_uri("/produced/ABC-001-v2"))
        repo.upsert(v2)

        result = repo.get_by_path(path)
        assert result is not None
        assert result.output_dir == to_file_uri("/produced/ABC-001-v2")

    def test_upsert_insert_writes_output_dir_directly(self, temp_db):
        """首次 insert（無既有 row）：INSERT 直接寫入 incoming output_dir 值"""
        repo = VideoRepository(temp_db)
        path = to_file_uri("/video1.mp4")

        v = Video(path=path, title="影片1", output_dir=to_file_uri("/produced/ABC-001"))
        repo.upsert(v)

        result = repo.get_by_path(path)
        assert result is not None
        assert result.output_dir == to_file_uri("/produced/ABC-001")

    def test_upsert_batch_preserves_output_dir_on_empty_incoming(self, temp_db):
        """upsert_batch 傳空 output_dir（且 DB 已有非空既有值）→ 既有值不被覆寫
        （與 upsert 對稱測試，Codex C2 回歸鎖：獨立斷言，不假設 upsert_batch 與 upsert 行為一致）"""
        repo = VideoRepository(temp_db)
        path = to_file_uri("/video1.mp4")

        repo.upsert_batch([
            Video(path=path, title="影片1", output_dir=to_file_uri("/produced/ABC-001")),
        ])

        repo.upsert_batch([
            Video(path=path, title="影片1-rescan", output_dir=""),
        ])

        result = repo.get_by_path(path)
        assert result is not None
        assert result.output_dir == to_file_uri("/produced/ABC-001")

    def test_upsert_batch_overwrites_output_dir_on_nonempty_incoming(self, temp_db):
        """upsert_batch 傳非空 output_dir → 正常寫入"""
        repo = VideoRepository(temp_db)
        path = to_file_uri("/video1.mp4")

        repo.upsert_batch([
            Video(path=path, title="影片1", output_dir=to_file_uri("/produced/ABC-001")),
        ])
        repo.upsert_batch([
            Video(path=path, title="影片1", output_dir=to_file_uri("/produced/ABC-001-v2")),
        ])

        result = repo.get_by_path(path)
        assert result is not None
        assert result.output_dir == to_file_uri("/produced/ABC-001-v2")

    def test_is_output_dir_taken_true_when_held_by_other_row(self, temp_db):
        """候選 output_dir 被別筆 path（source_uri）佔用 → True"""
        repo = VideoRepository(temp_db)
        taken_dir = to_file_uri("/produced/ABC-001")

        repo.upsert(Video(path=to_file_uri("/video1.mp4"), title="影片1", output_dir=taken_dir))

        assert repo.is_output_dir_taken(taken_dir, to_file_uri("/video2.mp4")) is True

    def test_is_output_dir_taken_false_when_held_only_by_self(self, temp_db):
        """候選 output_dir 只被自己（exclude_path 對應那筆）持有 → False（原地覆蓋不誤判）"""
        repo = VideoRepository(temp_db)
        own_dir = to_file_uri("/produced/ABC-001")
        own_path = to_file_uri("/video1.mp4")

        repo.upsert(Video(path=own_path, title="影片1", output_dir=own_dir))

        assert repo.is_output_dir_taken(own_dir, own_path) is False

    def test_is_output_dir_taken_false_when_unheld(self, temp_db):
        """候選 output_dir 無人持有 → False"""
        repo = VideoRepository(temp_db)
        assert repo.is_output_dir_taken(
            to_file_uri("/produced/NEW-001"), to_file_uri("/video1.mp4")
        ) is False


class TestScrapeAttemptedAtUpsertProtection:
    """P2 修正：scrape_attempted_at 缺 empty→preserve 保護，與 output_dir 不對稱。
    補對稱 CASE-WHEN（採「保留」語意）：incoming=0 時保留 DB 既有值，避免資料夾重掃
    （Video.from_video_info() 預設 scrape_attempted_at=0.0）洗掉 enricher 標記的 tried 時間戳。"""

    def test_upsert_preserves_scrape_attempted_at_on_zero_incoming(self, temp_db):
        """upsert 傳 scrape_attempted_at=0（且 DB 已有 >0 既有值）→ 既有值不被覆寫"""
        repo = VideoRepository(temp_db)
        path = to_file_uri("/video1.mp4")

        v1 = Video(path=path, title="影片1", scrape_attempted_at=1717171717.0)
        repo.upsert(v1)

        v2 = Video(path=path, title="影片1-rescan", scrape_attempted_at=0.0)
        repo.upsert(v2)

        result = repo.get_by_path(path)
        assert result is not None
        assert result.scrape_attempted_at == 1717171717.0

    def test_upsert_overwrites_scrape_attempted_at_on_nonzero_incoming(self, temp_db):
        """upsert 傳 scrape_attempted_at>0 → 正常寫入/覆寫"""
        repo = VideoRepository(temp_db)
        path = to_file_uri("/video1.mp4")

        v1 = Video(path=path, title="影片1", scrape_attempted_at=1717171717.0)
        repo.upsert(v1)

        v2 = Video(path=path, title="影片1", scrape_attempted_at=1717181818.0)
        repo.upsert(v2)

        result = repo.get_by_path(path)
        assert result is not None
        assert result.scrape_attempted_at == 1717181818.0

    def test_upsert_batch_preserves_scrape_attempted_at_on_zero_incoming(self, temp_db):
        """upsert_batch 傳 scrape_attempted_at=0（且 DB 已有 >0 既有值）→ 既有值不被覆寫
        （與 upsert 對稱測試，回歸鎖：獨立斷言，不假設 upsert_batch 與 upsert 行為一致）"""
        repo = VideoRepository(temp_db)
        path = to_file_uri("/video1.mp4")

        repo.upsert_batch([
            Video(path=path, title="影片1", scrape_attempted_at=1717171717.0),
        ])

        repo.upsert_batch([
            Video(path=path, title="影片1-rescan", scrape_attempted_at=0.0),
        ])

        result = repo.get_by_path(path)
        assert result is not None
        assert result.scrape_attempted_at == 1717171717.0

    def test_upsert_batch_overwrites_scrape_attempted_at_on_nonzero_incoming(self, temp_db):
        """upsert_batch 傳 scrape_attempted_at>0 → 正常寫入"""
        repo = VideoRepository(temp_db)
        path = to_file_uri("/video1.mp4")

        repo.upsert_batch([
            Video(path=path, title="影片1", scrape_attempted_at=1717171717.0),
        ])
        repo.upsert_batch([
            Video(path=path, title="影片1", scrape_attempted_at=1717181818.0),
        ])

        result = repo.get_by_path(path)
        assert result is not None
        assert result.scrape_attempted_at == 1717181818.0

    def test_upsert_insert_writes_scrape_attempted_at_zero_directly(self, temp_db):
        """首次 insert（無既有 row）傳 scrape_attempted_at=0 → 直接寫 0（happy path）"""
        repo = VideoRepository(temp_db)
        path = to_file_uri("/video1.mp4")

        v = Video(path=path, title="影片1", scrape_attempted_at=0.0)
        repo.upsert(v)

        result = repo.get_by_path(path)
        assert result is not None
        assert result.scrape_attempted_at == 0.0


class TestScrapeAttemptedAtRepositoryMethods:
    """TASK-89b-T1: update_scrape_attempted_at / get_attempted_index / insert_if_ignore"""

    # ── update_scrape_attempted_at ──────────────────────────────────────────

    def test_update_scrape_attempted_at_updates_only_that_field(self, temp_db):
        """只改 scrape_attempted_at 與 updated_at，其餘欄位不變"""
        repo = VideoRepository(temp_db)
        path = to_file_uri("/video1.mp4")
        repo.upsert(Video(
            path=path, title="影片1", cover_path=to_file_uri("/out/v1.jpg"),
            user_tags=["tagA"], output_dir=to_file_uri("/produced/ABC-001"),
        ))

        ok = repo.update_scrape_attempted_at(path, 1717171717.0)

        assert ok is True
        result = repo.get_by_path(path)
        assert result.scrape_attempted_at == 1717171717.0
        assert result.cover_path == to_file_uri("/out/v1.jpg")
        assert result.user_tags == ["tagA"]
        assert result.output_dir == to_file_uri("/produced/ABC-001")

    def test_update_scrape_attempted_at_path_not_exist_returns_false(self, temp_db):
        """path 不存在 → 回傳 False，不拋例外、不新建 row"""
        repo = VideoRepository(temp_db)
        ok = repo.update_scrape_attempted_at(to_file_uri("/nope.mp4"), 123.0)

        assert ok is False
        assert repo.count() == 0

    # ── get_attempted_index ──────────────────────────────────────────────────

    def test_get_attempted_index_empty(self, temp_db):
        """空表回傳 {}"""
        repo = VideoRepository(temp_db)
        assert repo.get_attempted_index() == {}

    def test_get_attempted_index_includes_zero_value_rows(self, temp_db):
        """含 scrape_attempted_at == 0 的 row（不過濾）"""
        repo = VideoRepository(temp_db)
        repo.upsert_batch([
            Video(path=to_file_uri("/video1.mp4"), scrape_attempted_at=0.0),
            Video(path=to_file_uri("/video2.mp4"), scrape_attempted_at=999.0),
        ])

        index = repo.get_attempted_index()

        assert len(index) == 2
        assert index[to_file_uri("/video1.mp4")] == 0.0
        assert index[to_file_uri("/video2.mp4")] == 999.0

    # ── insert_if_ignore ──────────────────────────────────────────────────────

    def test_insert_if_ignore_new_path_inserts_and_returns_true(self, temp_db):
        """path 不存在 → 新建一筆並回傳 True"""
        repo = VideoRepository(temp_db)
        video = Video(path=to_file_uri("/new.mp4"), number="NEW-001", title="新片")

        ok = repo.insert_if_ignore(video)

        assert ok is True
        result = repo.get_by_path(to_file_uri("/new.mp4"))
        assert result is not None
        assert result.number == "NEW-001"

    def test_insert_if_ignore_existing_path_does_not_overwrite_returns_false(self, temp_db):
        """path 已存在 → 不覆蓋任何既有欄位（含 cover_path/user_tags/output_dir）並回傳 False"""
        repo = VideoRepository(temp_db)
        path = to_file_uri("/video1.mp4")
        repo.upsert(Video(
            path=path, title="既有影片", cover_path=to_file_uri("/out/v1.jpg"),
            user_tags=["existing_tag"], output_dir=to_file_uri("/produced/EXIST-001"),
        ))

        conflicting = Video(
            path=path, title="嘗試覆蓋", cover_path=to_file_uri("/out/OTHER.jpg"),
            user_tags=["new_tag"], output_dir=to_file_uri("/produced/OTHER-999"),
        )
        ok = repo.insert_if_ignore(conflicting)

        assert ok is False
        result = repo.get_by_path(path)
        assert result.title == "既有影片"
        assert result.cover_path == to_file_uri("/out/v1.jpg")
        assert result.user_tags == ["existing_tag"]
        assert result.output_dir == to_file_uri("/produced/EXIST-001")

    def test_insert_if_ignore_invalidates_only_on_actual_insert(self, temp_db, monkeypatch):
        """實際插入才 invalidate（rowcount>0）；ON CONFLICT DO NOTHING 命中則不 invalidate。

        比照 upsert() 維持「每次 INSERT INTO videos 都 invalidate」的 spec-57b 完整性不變式
        （89b-T1 follow-up：guard 測試 test_all_raw_sql_mutations_have_invalidate 要求）。
        """
        from core.similar.ranker_cache import SimilarRankerCache

        calls = []
        monkeypatch.setattr(SimilarRankerCache, "invalidate", classmethod(lambda cls: calls.append(1)))

        repo = VideoRepository(temp_db)
        path = to_file_uri("/new2.mp4")

        # 首次插入 → 實際新增 row → invalidate 一次
        assert repo.insert_if_ignore(Video(path=path, title="新片2")) is True
        assert calls == [1]

        # 再次插入同 path → DO NOTHING（rowcount==0）→ 不再 invalidate
        assert repo.insert_if_ignore(Video(path=path, title="新片2")) is False
        assert calls == [1]


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
                    "path": to_file_uri("C:/video1.mp4"),
                    "title": "影片1",
                    "originaltitle": "Video 1",
                    "actor": "演員A,演員B",
                    "num": "ABC-001",
                    "maker": "片商1",
                    "date": "2024-01-01",
                    "genre": "類型1,類型2",
                    "size": 1024,
                    "mtime": 133500000000000000,
                    "img": to_file_uri("C:/cover1.jpg")
                }
            },
            "/path/to/video2.mp4": {
                "mtime": 1234567891.0,
                "nfo_mtime": 1234567801.0,
                "info": {
                    "path": to_file_uri("C:/video2.mp4"),
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

        video1 = repo.get_by_path(to_file_uri("C:/video1.mp4"))
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
                    "path": to_file_uri("C:/video.mp4"),
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
                    "path": to_file_uri("C:/video.mp4"),
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
                    "path": to_file_uri("C:/video.mp4"),
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


class TestNfoMtimeRepathAuthoritative:
    """TASK-showcase-nfo-mtime: repath 各分支 nfo_mtime 權威值寫穿驗證（含 anti-stale 反向案）。

    Codex High 裁決（見 feature/97-javdb-packaging-fix/showcase-nfo-mtime-inflow/
    TASK-showcase-nfo-mtime.md「方案取捨」）：nfo_mtime=0 是「已確認無 NFO」的合法值，
    與 output_dir=''/scrape_attempted_at=0 的「無資訊、保留舊值」語意不同 —— DB 層
    不加 0-guard，plain overwrite（照傳入值寫，包含 0）即為正確行為。本測試組
    分別覆蓋 upsert / 正常 UPDATE / 碰撞 merge 三分支，並含 anti-stale 探針
    （證明「若誤加 0-guard」會被這裡的斷言抓到）。
    """

    # ── upsert 分支（old_uri None，或 old 不在 DB → 委派 upsert）──────────────

    def test_repath_upsert_branch_writes_positive_nfo_mtime(self, temp_db):
        """old_uri=None → 委派 upsert；incoming nfo_mtime>0 應照寫。"""
        repo = VideoRepository(temp_db)
        new_uri = to_file_uri("/video_upsert_pos.mp4")
        video = Video(path=new_uri, title="新片", nfo_mtime=555.0)

        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.repath(None, new_uri, video)

        row = repo.get_by_path(new_uri)
        assert row is not None
        assert row.nfo_mtime == 555.0

    def test_repath_upsert_branch_writes_zero_nfo_mtime(self, temp_db):
        """old_uri=None → 委派 upsert；incoming nfo_mtime=0（無 NFO）應照寫 0，非保留守衛。"""
        repo = VideoRepository(temp_db)
        new_uri = to_file_uri("/video_upsert_zero.mp4")
        video = Video(path=new_uri, title="新片", nfo_mtime=0.0)

        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.repath(None, new_uri, video)

        row = repo.get_by_path(new_uri)
        assert row is not None
        assert row.nfo_mtime == 0.0

    def test_upsert_on_conflict_anti_stale_zero_overwrites_existing(self, temp_db):
        """upsert() ON CONFLICT(path) DO UPDATE 分支 anti-stale 探針（負向 DoD 守衛）：
        同一 path 已有 nfo_mtime>0 的 row，再次 upsert 帶 incoming nfo_mtime=0
        （確認無 NFO）→ DB 必須被覆蓋為 0，不得保留舊正值。

        此分支正是 upsert() 已對 output_dir/scrape_attempted_at 掛 CASE-WHEN-0 守衛之處，
        是未來最可能被誤加 nfo_mtime 0-guard 的位置。既有「upsert branch」測試只走
        INSERT（new_uri 不預存），從不觸發 ON CONFLICT UPDATE，故補此案堵住守衛缺口。
        MUTATION：若在 upsert() ON CONFLICT 加 nfo_mtime CASE-WHEN-0 守衛，本測試必 RED。"""
        repo = VideoRepository(temp_db)
        path = to_file_uri("/video_upsert_conflict_zero.mp4")

        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.upsert(Video(path=path, title="舊片", nfo_mtime=888.0))
        # 確認前置：ON CONFLICT 分支需 path 已存在且 nfo_mtime>0
        pre = repo.get_by_path(path)
        assert pre is not None and pre.nfo_mtime == 888.0

        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.upsert(Video(path=path, title="新掃描-無NFO", nfo_mtime=0.0))

        row = repo.get_by_path(path)
        assert row is not None
        assert row.nfo_mtime == 0.0, (
            f"upsert ON CONFLICT 分支：incoming nfo_mtime=0 應覆蓋舊正值 888.0，"
            f"不得殘留，實際: {row.nfo_mtime!r}"
        )

    def test_repath_old_not_in_db_branch_writes_authoritative_nfo_mtime(self, temp_db):
        """old_uri 不在 DB（純 search 無前置 Scanner）→ 委派 upsert；nfo_mtime 照傳入值寫。"""
        repo = VideoRepository(temp_db)
        old_uri = to_file_uri("/nonexistent_old_nfo.mp4")
        new_uri = to_file_uri("/video_old_not_in_db.mp4")
        video = Video(path=new_uri, title="新片", nfo_mtime=777.0)

        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.repath(old_uri, new_uri, video)

        row = repo.get_by_path(new_uri)
        assert row is not None
        assert row.nfo_mtime == 777.0

    # ── 正常 UPDATE 分支（old 在 DB、new 不在）──────────────────────────────

    def test_repath_normal_update_writes_new_positive_nfo_mtime(self, temp_db):
        """pre-existing row nfo_mtime>0；repath 傳入新的正值 → row 更新為新值。"""
        repo = VideoRepository(temp_db)
        old_uri = to_file_uri("/old_normal_pos.mp4")
        new_uri = to_file_uri("/new_normal_pos.mp4")

        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.upsert(Video(path=old_uri, title="舊片", nfo_mtime=100.0))

        new_video = Video(path=new_uri, title="新片", nfo_mtime=200.0)
        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.repath(old_uri, new_uri, new_video)

        row = repo.get_by_path(new_uri)
        assert row is not None
        assert row.nfo_mtime == 200.0

    def test_repath_normal_update_anti_stale_zero_incoming_does_not_retain_old_value(self, temp_db):
        """anti-stale 反向案（Codex 指定探針）：pre-existing row nfo_mtime>0；
        repath 到新路徑且 incoming nfo_mtime=0（新路徑確實無 NFO）→ 結果必須為 0，
        不得殘留舊 mtime 假稱 has_nfo=true。這正是揭穿「0-guard」矛盾方案的斷言：
        若 production 錯誤加上『incoming=0 時保留既有值』的 CASE-WHEN 守衛，
        本測試會 RED（見 mutation check）。"""
        repo = VideoRepository(temp_db)
        old_uri = to_file_uri("/old_anti_stale.mp4")
        new_uri = to_file_uri("/new_anti_stale.mp4")

        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.upsert(Video(path=old_uri, title="舊片", nfo_mtime=999.0))

        new_video = Video(path=new_uri, title="新片-無NFO", nfo_mtime=0.0)
        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.repath(old_uri, new_uri, new_video)

        row = repo.get_by_path(new_uri)
        assert row is not None
        assert row.nfo_mtime == 0.0, (
            f"anti-stale: 新路徑無 NFO 時 nfo_mtime 必須為 0，不得殘留舊值 999.0，"
            f"實際: {row.nfo_mtime!r}"
        )

    # ── 碰撞 delete-merge 分支（new 已存在）──────────────────────────────────

    def test_repath_collision_merge_incoming_wins_positive(self, temp_db):
        """碰撞 merge：incoming nfo_mtime 為權威值，覆蓋 new_row 既有值。"""
        repo = VideoRepository(temp_db)
        old_uri = to_file_uri("/old_collision_pos.mp4")
        new_uri = to_file_uri("/new_collision_pos.mp4")

        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.upsert(Video(path=old_uri, title="舊片", nfo_mtime=111.0))
            repo.upsert(Video(path=new_uri, title="既有新路徑片", nfo_mtime=222.0))

        collision_video = Video(path=new_uri, title="掃描新值", nfo_mtime=333.0)
        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.repath(old_uri, new_uri, collision_video)

        row = repo.get_by_path(new_uri)
        assert row is not None
        assert row.nfo_mtime == 333.0

    def test_repath_collision_merge_incoming_wins_zero(self, temp_db):
        """碰撞 merge：incoming nfo_mtime=0（確認無 NFO）同樣照寫，覆蓋既有正值。
        0 是合法權威值、非「未提供」，anti-stale 精神延伸到碰撞分支。"""
        repo = VideoRepository(temp_db)
        old_uri = to_file_uri("/old_collision_zero.mp4")
        new_uri = to_file_uri("/new_collision_zero.mp4")

        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.upsert(Video(path=old_uri, title="舊片", nfo_mtime=444.0))
            repo.upsert(Video(path=new_uri, title="既有新路徑片", nfo_mtime=555.0))

        collision_video = Video(path=new_uri, title="掃描新值-無NFO", nfo_mtime=0.0)
        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.repath(old_uri, new_uri, collision_video)

        row = repo.get_by_path(new_uri)
        assert row is not None
        assert row.nfo_mtime == 0.0, (
            f"碰撞 merge 分支 nfo_mtime=0 應照寫（合法權威值），實際: {row.nfo_mtime!r}"
        )


# ============ TASK-98a-T4: focal + crop_mode preserve-on-conflict（CD-98a-6）============

class TestFocalPreserveOnConflict:
    """crop_mode/auto_focal 四路 builder preserve-on-conflict 回歸鎖——這是本 milestone
    最貴的一條（Codex P1）：漏任一 builder＝掃描/重刮把背景算的 focal 與使用者的
    crop_mode 選擇清回 dataclass 預設值。四路皆須：先用 mutator 寫非預設值，再走
    對應 builder 寫一筆「看似新掃描」的 Video（focal 欄位是 dataclass 預設），
    讀回後 focal 欄位須維持 mutator 寫的值，不被覆蓋。
    """

    def test_upsert_preserves_focal_on_conflict(self, temp_db):
        """upsert() ON CONFLICT 分支：重掃描/重刮不覆蓋既有 crop_mode/auto_focal/
        focal_attempted_at（Codex PR#105 P2 no-face re-enqueue 修復：漏 preserve 會讓
        重掃的 upsert 把 focal_attempted_at 洗回 NULL，無臉列又被重排）"""
        repo = VideoRepository(temp_db)
        path = to_file_uri("/focal_upsert.mp4")
        repo.upsert(Video(path=path, title="舊片"))
        assert repo.update_crop_mode(path, 'default') is True
        assert repo.update_auto_focal(path, '0.5,0.4') is True

        repo.upsert(Video(path=path, title="重掃描新片"))

        result = repo.get_by_path(path)
        assert result is not None
        assert result.crop_mode == 'default'
        assert result.auto_focal == '0.5,0.4'
        assert result.focal_attempted_at is not None

    def test_upsert_batch_preserves_focal_on_conflict(self, temp_db):
        """upsert_batch() ON CONFLICT 分支（Scanner 增量掃描主路徑，漏此等於沒修）。
        含 focal_attempted_at（Codex PR#105 P2）——mutation：把 focal_attempted_at 移出
        _FOCAL_PRESERVE 會讓這條 RED（洗回 NULL）。"""
        repo = VideoRepository(temp_db)
        path = to_file_uri("/focal_upsert_batch.mp4")
        repo.upsert(Video(path=path, title="舊片"))
        assert repo.update_crop_mode(path, 'default') is True
        assert repo.update_auto_focal(path, '0.5,0.4') is True

        repo.upsert_batch([Video(path=path, title="重掃描新片")])

        result = repo.get_by_path(path)
        assert result is not None
        assert result.crop_mode == 'default'
        assert result.auto_focal == '0.5,0.4'
        assert result.focal_attempted_at is not None

    def test_repath_normal_update_preserves_focal(self, temp_db):
        """repath() 分支 2（正常 UPDATE，old 在 DB、new 不在）：SET 子句不含 focal"""
        repo = VideoRepository(temp_db)
        old_uri = to_file_uri("/focal_repath_old.mp4")
        new_uri = to_file_uri("/focal_repath_new.mp4")

        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.upsert(Video(path=old_uri, title="舊片"))
        assert repo.update_crop_mode(old_uri, 'default') is True
        assert repo.update_auto_focal(old_uri, '0.5,0.4') is True

        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.repath(old_uri, new_uri, Video(path=new_uri, title="重掃描新片"))

        result = repo.get_by_path(new_uri)
        assert result is not None
        assert result.crop_mode == 'default'
        assert result.auto_focal == '0.5,0.4'
        assert result.focal_attempted_at is not None

    def test_repath_collision_merge_preserves_focal(self, temp_db):
        """repath() 分支 3（碰撞 delete-merge，new 已有一筆）：DO UPDATE 跳過 focal 欄位"""
        repo = VideoRepository(temp_db)
        old_uri = to_file_uri("/focal_collision_old.mp4")
        new_uri = to_file_uri("/focal_collision_new.mp4")

        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.upsert(Video(path=old_uri, title="舊片"))
            repo.upsert(Video(path=new_uri, title="既有新路徑片"))
        assert repo.update_crop_mode(new_uri, 'default') is True
        assert repo.update_auto_focal(new_uri, '0.5,0.4') is True

        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.repath(old_uri, new_uri, Video(path=new_uri, title="重掃描新片"))

        result = repo.get_by_path(new_uri)
        assert result is not None
        assert result.crop_mode == 'default'
        assert result.auto_focal == '0.5,0.4'
        assert result.focal_attempted_at is not None

    # ── Codex PR#105 P2b：cover_path 換了必須重置 focal 偵測態 ───────────────

    def test_upsert_preserves_focal_when_cover_path_unchanged(self, temp_db):
        """metadata-only 衝突：incoming cover_path 與 DB 既有值相同（非空、非巧合的
        default '' == ''）→ 仍保留既有 focal 結果。鎖住「同封面保留」這一半的條件式
        邏輯，不只靠 preserves_focal_on_conflict 系列測試的 default 空字串巧合過。"""
        repo = VideoRepository(temp_db)
        path = to_file_uri("/focal_same_cover_upsert.mp4")
        cover = to_file_uri("/focal_same_cover_upsert.jpg")

        repo.upsert(Video(path=path, title="舊片", cover_path=cover))
        assert repo.update_crop_mode(path, 'default') is True
        assert repo.update_auto_focal(path, '0.5,0.4') is True

        repo.upsert(Video(path=path, title="重掃描-metadata only", cover_path=cover))

        result = repo.get_by_path(path)
        assert result is not None
        assert result.cover_path == cover
        assert result.crop_mode == 'default'
        assert result.auto_focal == '0.5,0.4'
        assert result.focal_attempted_at is not None

    def test_upsert_resets_focal_when_cover_path_changes(self, temp_db):
        """Codex PR#105 P2b 核心回歸：cover_path 換了（用戶換封面/NFO・sidecar 選了不同
        封面），舊 focal 偵測結果是針對舊封面算的、已 stale，須重置為未偵測（auto_focal=''
        + focal_attempted_at=NULL），否則新封面永遠不會被 get_empty_focal_candidates
        重新排入偵測，除非手動 force-detect。crop_mode 是裁切模式偏好、與封面無關，
        換封面不應重置——mutation：把條件化拿掉（回到無條件 continue）會讓這條 RED
        （focal_attempted_at 仍非 NULL）。"""
        repo = VideoRepository(temp_db)
        path = to_file_uri("/focal_cover_change_upsert.mp4")
        old_cover = to_file_uri("/focal_cover_change_upsert_old.jpg")
        new_cover = to_file_uri("/focal_cover_change_upsert_new.jpg")

        repo.upsert(Video(path=path, title="舊片", cover_path=old_cover))
        assert repo.update_crop_mode(path, 'default') is True
        assert repo.update_auto_focal(path, '') is True  # 無臉試過（format_focal(None) == ''）

        repo.upsert(Video(path=path, title="換封面重掃", cover_path=new_cover))

        result = repo.get_by_path(path)
        assert result is not None
        assert result.cover_path == new_cover
        assert result.auto_focal == ''
        assert result.focal_attempted_at is None, (
            "封面換了，focal_attempted_at 必須重置為 NULL，否則 get_empty_focal_candidates "
            "永遠不會對新封面重新排入偵測"
        )
        assert result.crop_mode == 'default', "crop_mode 是裁切模式偏好，與封面無關，換封面不應重置"

    def test_upsert_batch_resets_focal_when_cover_path_changes(self, temp_db):
        """upsert_batch() ON CONFLICT 分支同鏡射（Scanner 增量掃描主路徑，漏此等於沒修）。"""
        repo = VideoRepository(temp_db)
        path = to_file_uri("/focal_cover_change_batch.mp4")
        old_cover = to_file_uri("/focal_cover_change_batch_old.jpg")
        new_cover = to_file_uri("/focal_cover_change_batch_new.jpg")

        repo.upsert(Video(path=path, title="舊片", cover_path=old_cover))
        assert repo.update_crop_mode(path, 'default') is True
        assert repo.update_auto_focal(path, '0.5,0.4') is True

        repo.upsert_batch([Video(path=path, title="換封面重掃", cover_path=new_cover)])

        result = repo.get_by_path(path)
        assert result is not None
        assert result.cover_path == new_cover
        assert result.auto_focal == ''
        assert result.focal_attempted_at is None
        assert result.crop_mode == 'default'

    def test_repath_normal_update_resets_focal_when_cover_path_changes(self, temp_db):
        """repath() 分支 2（正常 UPDATE，old 在 DB、new 不在）：Python-side cover_path
        比對（無 excluded. 可用，走 old_row.cover_path vs incoming video.cover_path）。"""
        repo = VideoRepository(temp_db)
        old_uri = to_file_uri("/focal_repath_cover_change_old.mp4")
        new_uri = to_file_uri("/focal_repath_cover_change_new.mp4")
        old_cover = to_file_uri("/focal_repath_cover_change_old.jpg")
        new_cover = to_file_uri("/focal_repath_cover_change_new.jpg")

        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.upsert(Video(path=old_uri, title="舊片", cover_path=old_cover))
        assert repo.update_crop_mode(old_uri, 'default') is True
        assert repo.update_auto_focal(old_uri, '0.5,0.4') is True

        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.repath(
                old_uri, new_uri,
                # incoming 帶 non-default focal（Codex PR#105 P2c）：若 reset branch 漏 continue、
                # fall through 到底部通用 append，會用這裡的 stale 值蓋掉 reset（SQLite 取最右 SET）。
                # 用預設 ''/None 會與 reset 值巧合相同、測不出 missing-continue，故刻意餵非預設值。
                Video(path=new_uri, title="換封面重掃", cover_path=new_cover,
                      auto_focal='0.9,0.9', focal_attempted_at='2020-01-01 00:00:00'),
            )

        result = repo.get_by_path(new_uri)
        assert result is not None
        assert result.cover_path == new_cover
        assert result.auto_focal == ''
        assert result.focal_attempted_at is None
        assert result.crop_mode == 'default'

    def test_repath_collision_merge_resets_focal_when_cover_path_changes(self, temp_db):
        """repath() 分支 3（碰撞 delete-merge，new 已有一筆）：比對 incoming cover_path
        （excluded.cover_path）vs 既存 new_uri 那筆的 cover_path（videos.cover_path）。"""
        repo = VideoRepository(temp_db)
        old_uri = to_file_uri("/focal_collision_cover_change_old.mp4")
        new_uri = to_file_uri("/focal_collision_cover_change_new.mp4")
        existing_cover = to_file_uri("/focal_collision_cover_change_existing.jpg")
        incoming_cover = to_file_uri("/focal_collision_cover_change_incoming.jpg")

        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.upsert(Video(path=old_uri, title="舊片"))
            repo.upsert(Video(path=new_uri, title="既有新路徑片", cover_path=existing_cover))
        assert repo.update_crop_mode(new_uri, 'default') is True
        assert repo.update_auto_focal(new_uri, '0.5,0.4') is True

        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.repath(
                old_uri, new_uri,
                Video(path=new_uri, title="換封面重掃", cover_path=incoming_cover),
            )

        result = repo.get_by_path(new_uri)
        assert result is not None
        assert result.cover_path == incoming_cover
        assert result.auto_focal == ''
        assert result.focal_attempted_at is None
        assert result.crop_mode == 'default'

    def test_insert_writes_dataclass_focal_defaults(self, temp_db):
        """INSERT（新 path，非衝突）：focal 欄位照寫 dataclass 預設值（''/'auto'/None），
        鏡像操作對稱驗證（CD-98a-6 語意驗證段落）"""
        repo = VideoRepository(temp_db)
        path = to_file_uri("/focal_insert_defaults.mp4")

        repo.upsert(Video(path=path, title="新片"))

        result = repo.get_by_path(path)
        assert result is not None
        assert result.crop_mode == 'auto'
        assert result.auto_focal == ''
        assert result.focal_attempted_at is None


class TestFocalMutators:
    """VideoRepository.update_auto_focal / update_crop_mode round-trip（CD-98a-6 mutator）"""

    def test_update_auto_focal_roundtrip(self, temp_db):
        repo = VideoRepository(temp_db)
        path = to_file_uri("/focal_mutator_auto_focal.mp4")
        repo.upsert(Video(path=path, title="片"))

        assert repo.update_auto_focal(path, '0.3,0.6') is True

        result = repo.get_by_path(path)
        assert result is not None
        assert result.auto_focal == '0.3,0.6'

    def test_update_auto_focal_missing_path_returns_false(self, temp_db):
        repo = VideoRepository(temp_db)
        assert repo.update_auto_focal(to_file_uri("/focal_mutator_nonexistent.mp4"), '0.3,0.6') is False

    def test_update_auto_focal_stamps_focal_attempted_at_with_coords(self, temp_db):
        """有臉存座標時，focal_attempted_at 同一 UPDATE 一起蓋章非 NULL（Codex PR#105 P2）"""
        repo = VideoRepository(temp_db)
        path = to_file_uri("/focal_mutator_attempted_coords.mp4")
        repo.upsert(Video(path=path, title="片"))
        assert repo.get_by_path(path).focal_attempted_at is None

        assert repo.update_auto_focal(path, '0.3,0.6') is True

        result = repo.get_by_path(path)
        assert result.auto_focal == '0.3,0.6'
        assert result.focal_attempted_at is not None

    def test_update_auto_focal_stamps_focal_attempted_at_on_no_face(self, temp_db):
        """無臉存 ''（format_focal(None)）時，focal_attempted_at 仍蓋章非 NULL——這是
        Codex PR#105 P2 修的核心：無臉結果也要記「試過了」，否則重掃無限重排。"""
        repo = VideoRepository(temp_db)
        path = to_file_uri("/focal_mutator_attempted_no_face.mp4")
        repo.upsert(Video(path=path, title="片"))
        assert repo.get_by_path(path).focal_attempted_at is None

        assert repo.update_auto_focal(path, '') is True

        result = repo.get_by_path(path)
        assert result.auto_focal == ''
        assert result.focal_attempted_at is not None

    def test_update_crop_mode_roundtrip(self, temp_db):
        repo = VideoRepository(temp_db)
        path = to_file_uri("/focal_mutator_crop_mode.mp4")
        repo.upsert(Video(path=path, title="片"))

        assert repo.update_crop_mode(path, 'default') is True

        result = repo.get_by_path(path)
        assert result is not None
        assert result.crop_mode == 'default'

    def test_update_crop_mode_missing_path_returns_false(self, temp_db):
        repo = VideoRepository(temp_db)
        assert repo.update_crop_mode(to_file_uri("/focal_mutator_nonexistent2.mp4"), 'default') is False


class TestGetEmptyFocalCandidates:
    """VideoRepository.get_empty_focal_candidates（Codex PR#105 P2 scan-backfill 修復用）。

    掃描 focal trigger 改用此方法涵蓋「本次掃描 in-scope 但 auto_focal 仍空」的所有
    列（不只 upsert batch），此處直接驗證 SQL 篩選正確性：只回空 auto_focal 且
    path 在 in-scope 集合內的列。
    """

    def test_empty_paths_returns_empty_list(self, temp_db):
        repo = VideoRepository(temp_db)
        assert repo.get_empty_focal_candidates([]) == []

    def test_returns_only_empty_focal_rows_within_scope(self, temp_db):
        repo = VideoRepository(temp_db)
        p_empty = to_file_uri("/empty_focal_candidates_empty.mp4")
        p_filled = to_file_uri("/empty_focal_candidates_filled.mp4")
        p_out_of_scope = to_file_uri("/empty_focal_candidates_out_of_scope.mp4")

        repo.upsert(Video(path=p_empty, number="SIRO-1111", maker="", cover_path="cover1"))
        repo.upsert(Video(path=p_filled, number="SIRO-2222", maker="", cover_path="cover2"))
        repo.update_auto_focal(p_filled, "0.5,0.5")
        # 不在本次掃描 in-scope 集合的列（即使 auto_focal 也是空）不該被查到
        repo.upsert(Video(path=p_out_of_scope, number="SIRO-3333", maker="", cover_path="cover3"))

        result = repo.get_empty_focal_candidates([p_empty, p_filled])

        assert result == [(p_empty, "SIRO-1111", "", "cover1")]

    def test_missing_path_not_in_result(self, temp_db):
        repo = VideoRepository(temp_db)
        assert repo.get_empty_focal_candidates([to_file_uri("/no_such_video.mp4")]) == []

    def test_no_face_result_excluded_from_candidates(self, temp_db):
        """Codex PR#105 P2 核心回歸鎖：auto_focal='' 但 focal_attempted_at 已蓋章
        （偵測跑過、legitimately 無臉）→ 不應再被當「未偵測」回傳，否則每次重掃
        都對同一張無臉封面無限重跑昂貴偵測。"""
        repo = VideoRepository(temp_db)
        p_no_face = to_file_uri("/empty_focal_candidates_no_face.mp4")
        p_never_tried = to_file_uri("/empty_focal_candidates_never_tried.mp4")

        repo.upsert(Video(path=p_no_face, number="SIRO-4444", maker="", cover_path="cover4"))
        repo.upsert(Video(path=p_never_tried, number="SIRO-5555", maker="", cover_path="cover5"))
        # 模擬偵測跑過、legitimately 找不到臉：auto_focal 仍空，但蓋 focal_attempted_at 章
        repo.update_auto_focal(p_no_face, "")

        result = repo.get_empty_focal_candidates([p_no_face, p_never_tried])

        assert result == [(p_never_tried, "SIRO-5555", "", "cover5")]
