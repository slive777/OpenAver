"""測試 VideoRepository 類別"""
import pytest
import json

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
