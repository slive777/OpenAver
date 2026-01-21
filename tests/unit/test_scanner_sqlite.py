"""測試 Scanner SQLite 整合"""
import pytest
import tempfile
import os
from pathlib import Path

from core.gallery_scanner import VideoScanner
from core.database import init_db, VideoRepository


@pytest.fixture
def temp_db():
    """建立臨時資料庫"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        init_db(db_path)
        yield db_path


@pytest.fixture
def temp_video_dir():
    """建立臨時影片目錄"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def create_video_file(dir_path: Path, name: str, size: int = 1024 * 1024) -> Path:
    """建立測試影片檔案"""
    video_path = dir_path / name
    with open(video_path, 'wb') as f:
        f.write(b'0' * size)
    return video_path


def create_nfo_file(video_path: Path, title: str = "測試影片", num: str = "ABC-123",
                    actor: str = "演員A", maker: str = "片商") -> Path:
    """建立測試 NFO 檔案"""
    nfo_path = video_path.with_suffix('.nfo')
    nfo_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<movie>
    <title>{title}</title>
    <num>{num}</num>
    <maker>{maker}</maker>
    <actor><name>{actor}</name></actor>
</movie>
"""
    with open(nfo_path, 'w', encoding='utf-8') as f:
        f.write(nfo_content)
    return nfo_path


class TestScanToSqlite:
    """scan_to_sqlite 測試"""

    def test_scan_empty_directory(self, temp_db, temp_video_dir):
        """測試掃描空目錄"""
        scanner = VideoScanner()
        result = scanner.scan_to_sqlite(str(temp_video_dir), temp_db)

        assert result['inserted'] == 0
        assert result['updated'] == 0
        assert result['deleted'] == 0
        assert result['total'] == 0

    def test_scan_single_video(self, temp_db, temp_video_dir):
        """測試掃描單一影片"""
        video_path = create_video_file(temp_video_dir, "test.mp4")
        create_nfo_file(video_path, title="測試影片", num="ABC-001")

        scanner = VideoScanner()
        result = scanner.scan_to_sqlite(str(temp_video_dir), temp_db)

        assert result['inserted'] == 1
        assert result['updated'] == 0
        assert result['deleted'] == 0
        assert result['total'] == 1

        # 驗證資料庫內容
        repo = VideoRepository(temp_db)
        videos = repo.get_all()
        assert len(videos) == 1
        assert videos[0].title == "測試影片"
        assert videos[0].number == "ABC-001"

    def test_scan_multiple_videos(self, temp_db, temp_video_dir):
        """測試掃描多部影片"""
        for i in range(3):
            video_path = create_video_file(temp_video_dir, f"video{i}.mp4")
            create_nfo_file(video_path, title=f"影片{i}", num=f"ABC-{i:03d}")

        scanner = VideoScanner()
        result = scanner.scan_to_sqlite(str(temp_video_dir), temp_db)

        assert result['inserted'] == 3
        assert result['total'] == 3

    def test_scan_incremental_no_changes(self, temp_db, temp_video_dir):
        """測試增量掃描（無變更）"""
        video_path = create_video_file(temp_video_dir, "test.mp4")
        create_nfo_file(video_path, title="測試影片")

        scanner = VideoScanner()

        # 第一次掃描
        result1 = scanner.scan_to_sqlite(str(temp_video_dir), temp_db)
        assert result1['inserted'] == 1

        # 第二次掃描（無變更）
        result2 = scanner.scan_to_sqlite(str(temp_video_dir), temp_db)
        assert result2['inserted'] == 0
        assert result2['updated'] == 0
        assert result2['deleted'] == 0
        assert result2['total'] == 1

    def test_scan_incremental_new_file(self, temp_db, temp_video_dir):
        """測試增量掃描（新增檔案）"""
        video1 = create_video_file(temp_video_dir, "video1.mp4")
        create_nfo_file(video1, title="影片1")

        scanner = VideoScanner()

        # 第一次掃描
        result1 = scanner.scan_to_sqlite(str(temp_video_dir), temp_db)
        assert result1['inserted'] == 1
        assert result1['total'] == 1

        # 新增檔案
        video2 = create_video_file(temp_video_dir, "video2.mp4")
        create_nfo_file(video2, title="影片2")

        # 第二次掃描
        result2 = scanner.scan_to_sqlite(str(temp_video_dir), temp_db)
        assert result2['inserted'] == 1
        assert result2['updated'] == 0
        assert result2['total'] == 2

    def test_scan_incremental_deleted_file(self, temp_db, temp_video_dir):
        """測試增量掃描（刪除檔案）"""
        video1 = create_video_file(temp_video_dir, "video1.mp4")
        create_nfo_file(video1, title="影片1")
        video2 = create_video_file(temp_video_dir, "video2.mp4")
        create_nfo_file(video2, title="影片2")

        scanner = VideoScanner()

        # 第一次掃描
        result1 = scanner.scan_to_sqlite(str(temp_video_dir), temp_db)
        assert result1['inserted'] == 2
        assert result1['total'] == 2

        # 刪除檔案
        video1.unlink()
        video1.with_suffix('.nfo').unlink()

        # 第二次掃描
        result2 = scanner.scan_to_sqlite(str(temp_video_dir), temp_db)
        assert result2['deleted'] == 1
        assert result2['total'] == 1

    def test_scan_incremental_mtime_changed(self, temp_db, temp_video_dir):
        """測試增量掃描（檔案修改時間變更）"""
        import time

        video_path = create_video_file(temp_video_dir, "test.mp4")
        create_nfo_file(video_path, title="原始標題")

        scanner = VideoScanner()

        # 第一次掃描
        result1 = scanner.scan_to_sqlite(str(temp_video_dir), temp_db)
        assert result1['inserted'] == 1

        # 等待一小段時間確保 mtime 不同
        time.sleep(0.1)

        # 修改檔案（觸發 mtime 變更）
        with open(video_path, 'ab') as f:
            f.write(b'1')

        # 第二次掃描
        result2 = scanner.scan_to_sqlite(str(temp_video_dir), temp_db)
        assert result2['updated'] == 1
        assert result2['inserted'] == 0

    def test_scan_incremental_nfo_mtime_changed(self, temp_db, temp_video_dir):
        """測試增量掃描（NFO 修改時間變更）"""
        import time

        video_path = create_video_file(temp_video_dir, "test.mp4")
        nfo_path = create_nfo_file(video_path, title="原始標題")

        scanner = VideoScanner()

        # 第一次掃描
        result1 = scanner.scan_to_sqlite(str(temp_video_dir), temp_db)
        assert result1['inserted'] == 1

        # 等待確保 mtime 不同
        time.sleep(0.1)

        # 修改 NFO（觸發 nfo_mtime 變更）
        create_nfo_file(video_path, title="修改後標題")

        # 第二次掃描
        result2 = scanner.scan_to_sqlite(str(temp_video_dir), temp_db)
        assert result2['updated'] == 1

        # 驗證標題已更新
        repo = VideoRepository(temp_db)
        video = repo.get_all()[0]
        assert video.title == "修改後標題"

    def test_scan_nonexistent_directory(self, temp_db):
        """測試掃描不存在的目錄"""
        scanner = VideoScanner()

        with pytest.raises(ValueError, match="資料夾不存在"):
            scanner.scan_to_sqlite("/nonexistent/path", temp_db)

    def test_scan_min_size_filter(self, temp_db, temp_video_dir):
        """測試最小檔案大小過濾"""
        # 建立小檔案（100 bytes）
        create_video_file(temp_video_dir, "small.mp4", size=100)
        # 建立大檔案（2 MB）
        create_video_file(temp_video_dir, "large.mp4", size=2 * 1024 * 1024)

        scanner = VideoScanner()
        result = scanner.scan_to_sqlite(str(temp_video_dir), temp_db, min_size_mb=1)

        # 只有大檔案被掃描
        assert result['inserted'] == 1
        assert result['total'] == 1

    def test_scan_with_progress_callback(self, temp_db, temp_video_dir):
        """測試進度回調"""
        for i in range(3):
            create_video_file(temp_video_dir, f"video{i}.mp4")

        progress_calls = []

        def progress_callback(current, total, filename):
            progress_calls.append((current, total, filename))

        scanner = VideoScanner()
        scanner.scan_to_sqlite(str(temp_video_dir), temp_db, progress_callback=progress_callback)

        assert len(progress_calls) == 3
        # 驗證 current 遞增
        for i, (current, total, _) in enumerate(progress_calls, 1):
            assert current == i
            assert total == 3

    def test_scan_subdirectories(self, temp_db, temp_video_dir):
        """測試掃描子目錄"""
        # 在子目錄建立影片
        subdir = temp_video_dir / "subdir"
        subdir.mkdir()
        create_video_file(subdir, "video1.mp4")
        create_video_file(temp_video_dir, "video2.mp4")

        scanner = VideoScanner()
        result = scanner.scan_to_sqlite(str(temp_video_dir), temp_db)

        # 兩部影片都應該被掃描
        assert result['inserted'] == 2
        assert result['total'] == 2

    def test_scan_video_extensions(self, temp_db, temp_video_dir):
        """測試不同影片副檔名"""
        # 建立不同副檔名的檔案
        create_video_file(temp_video_dir, "video.mp4")
        create_video_file(temp_video_dir, "video.mkv")
        create_video_file(temp_video_dir, "video.avi")
        create_video_file(temp_video_dir, "document.txt")  # 不是影片

        scanner = VideoScanner()
        result = scanner.scan_to_sqlite(str(temp_video_dir), temp_db)

        # 只有影片檔案被掃描
        assert result['inserted'] == 3
        assert result['total'] == 3

    def test_scan_default_db_path(self, temp_video_dir):
        """測試預設資料庫路徑"""
        create_video_file(temp_video_dir, "test.mp4")

        scanner = VideoScanner()
        # 使用預設路徑（不傳入 db_path）
        # 這會使用 output/openaver.db
        result = scanner.scan_to_sqlite(str(temp_video_dir))

        assert result['inserted'] == 1

        # 清理：刪除預設資料庫中的測試資料
        from core.database import get_db_path
        repo = VideoRepository(get_db_path())
        repo.delete_by_paths([v.path for v in repo.get_all() if str(temp_video_dir) in v.path])


class TestScanToSqliteIntegration:
    """scan_to_sqlite 整合測試"""

    def test_full_workflow(self, temp_db, temp_video_dir):
        """測試完整工作流程"""
        scanner = VideoScanner()
        repo = VideoRepository(temp_db)

        # 1. 初始掃描
        video1 = create_video_file(temp_video_dir, "video1.mp4")
        create_nfo_file(video1, title="影片1", num="ABC-001", actor="演員A")

        result1 = scanner.scan_to_sqlite(str(temp_video_dir), temp_db)
        assert result1['inserted'] == 1

        # 2. 新增檔案
        video2 = create_video_file(temp_video_dir, "video2.mp4")
        create_nfo_file(video2, title="影片2", num="ABC-002", actor="演員B")

        result2 = scanner.scan_to_sqlite(str(temp_video_dir), temp_db)
        assert result2['inserted'] == 1
        assert result2['total'] == 2

        # 3. 刪除檔案
        video1.unlink()
        video1.with_suffix('.nfo').unlink()

        result3 = scanner.scan_to_sqlite(str(temp_video_dir), temp_db)
        assert result3['deleted'] == 1
        assert result3['total'] == 1

        # 4. 驗證最終狀態
        videos = repo.get_all()
        assert len(videos) == 1
        assert videos[0].title == "影片2"
        assert videos[0].number == "ABC-002"
