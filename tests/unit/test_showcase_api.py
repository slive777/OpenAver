"""測試 Showcase API"""
import pytest
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient

from core.database import init_db, Video, VideoRepository


@pytest.fixture
def temp_db():
    """建立臨時資料庫"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        init_db(db_path)
        yield db_path


@pytest.fixture
def client(temp_db, monkeypatch):
    """建立測試客戶端，使用臨時資料庫"""
    def mock_get_db_path():
        return temp_db

    monkeypatch.setattr("core.database.get_db_path", mock_get_db_path)
    monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

    from web.app import app
    return TestClient(app)


@pytest.fixture
def populated_db(temp_db):
    """預先填入測試資料的資料庫"""
    repo = VideoRepository(temp_db)

    # 插入測試影片資料
    videos = [
        Video(
            path="file:///mnt/media/SONE-205.mp4",
            number="SONE-205",
            title="Test Video 1",
            original_title="テストビデオ1",
            actresses=["坂道みる", "深田えいみ"],
            maker="S1 NO.1 STYLE",
            release_date="2024-01-15",
            tags=["単体作品", "ハイビジョン", "独占配信"],
            size_bytes=3145728000,
            cover_path="file:///mnt/media/SONE-205/poster.jpg",
            mtime=1705276800.0  # 2024-01-15 00:00:00 UTC
        ),
        Video(
            path="file:///C:/Videos/ABW-001.mp4",
            number="ABW-001",
            title="Test Video 2",
            original_title="",
            actresses=["新ありな"],
            maker="Prestige",
            release_date="2024-02-01",
            tags=["スレンダー"],
            size_bytes=2147483648,
            cover_path="file:///C:/Videos/ABW-001/cover.jpg",
            mtime=1706745600.0  # 2024-02-01 00:00:00 UTC
        ),
        Video(
            path="file:///D:/AV/FC2-001.mp4",
            number="FC2-PPV-001",
            title="Test Video 3 - No Cover",
            original_title="",
            actresses=[],  # 空陣列測試
            maker="",
            release_date="",
            tags=[],  # 空陣列測試
            size_bytes=0,
            cover_path="",  # 無封面測試
            mtime=0.0  # 零時間測試
        ),
    ]
    repo.upsert_batch(videos)
    return temp_db


# === API 端點測試 ===

class TestShowcaseVideosAPI:
    """測試 /api/showcase/videos 端點"""

    def test_get_videos_empty_db(self, client, temp_db, monkeypatch):
        """測試空資料庫回傳正確格式"""
        def mock_get_db_path():
            return temp_db
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        response = client.get("/api/showcase/videos")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["videos"] == []
        assert data["total"] == 0

    def test_get_videos_db_not_exists(self, client, tmp_path, monkeypatch):
        """測試資料庫檔案不存在時不報錯"""
        nonexistent_db = tmp_path / "nonexistent.db"

        def mock_get_db_path():
            return nonexistent_db
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        response = client.get("/api/showcase/videos")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["videos"] == []
        assert data["total"] == 0

    def test_get_videos_with_data(self, client, populated_db, monkeypatch):
        """測試有資料時回傳完整欄位"""
        def mock_get_db_path():
            return populated_db
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        response = client.get("/api/showcase/videos")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["total"] == 3
        assert len(data["videos"]) == 3

        # 驗證第一筆資料欄位完整性
        video1 = data["videos"][0]
        assert "path" in video1
        assert "title" in video1
        assert "original_title" in video1
        assert "actresses" in video1
        assert "number" in video1
        assert "maker" in video1
        assert "release_date" in video1
        assert "tags" in video1
        assert "size" in video1
        assert "cover_url" in video1
        assert "mtime" in video1

    def test_cover_url_conversion_unix_path(self, client, populated_db, monkeypatch):
        """測試 cover_url 正確轉換（Unix 路徑）"""
        def mock_get_db_path():
            return populated_db
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        response = client.get("/api/showcase/videos")
        data = response.json()

        # 第一筆：file:///mnt/media/SONE-205/poster.jpg
        # 預期：/api/gallery/image?path=mnt%2Fmedia%2FSONE-205%2Fposter.jpg
        video1 = data["videos"][0]
        assert video1["cover_url"].startswith("/api/gallery/image?path=")
        assert "mnt" in video1["cover_url"]
        assert "SONE-205" in video1["cover_url"]
        # URL encoded，路徑分隔符 / 會變成 %2F
        assert "%2F" in video1["cover_url"]

    def test_cover_url_conversion_windows_path(self, client, populated_db, monkeypatch):
        """測試 cover_url 正確轉換（Windows 路徑）"""
        def mock_get_db_path():
            return populated_db
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        response = client.get("/api/showcase/videos")
        data = response.json()

        # 第二筆：file:///C:/Videos/ABW-001/cover.jpg
        # 預期：/api/gallery/image?path=C%3A%2FVideos%2FABW-001%2Fcover.jpg
        video2 = data["videos"][1]
        assert video2["cover_url"].startswith("/api/gallery/image?path=")
        # C: 會被編碼為 C%3A
        assert "C%3A" in video2["cover_url"]
        assert "ABW-001" in video2["cover_url"]

    def test_cover_url_empty_when_no_cover(self, client, populated_db, monkeypatch):
        """測試無封面圖時 cover_url 為空字串"""
        def mock_get_db_path():
            return populated_db
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        response = client.get("/api/showcase/videos")
        data = response.json()

        # 第三筆：無封面
        video3 = data["videos"][2]
        assert video3["cover_url"] == ""

    def test_actresses_comma_separated_string(self, client, populated_db, monkeypatch):
        """測試 actresses 正確轉為逗號分隔字串"""
        def mock_get_db_path():
            return populated_db
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        response = client.get("/api/showcase/videos")
        data = response.json()

        # 第一筆：多位女優
        video1 = data["videos"][0]
        assert isinstance(video1["actresses"], str)
        assert video1["actresses"] == "坂道みる,深田えいみ"

        # 第二筆：單一女優
        video2 = data["videos"][1]
        assert video2["actresses"] == "新ありな"

        # 第三筆：空陣列 → 空字串
        video3 = data["videos"][2]
        assert video3["actresses"] == ""

    def test_tags_comma_separated_string(self, client, populated_db, monkeypatch):
        """測試 tags 正確轉為逗號分隔字串"""
        def mock_get_db_path():
            return populated_db
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        response = client.get("/api/showcase/videos")
        data = response.json()

        # 第一筆：多個標籤
        video1 = data["videos"][0]
        assert isinstance(video1["tags"], str)
        assert video1["tags"] == "単体作品,ハイビジョン,独占配信"

        # 第三筆：空陣列 → 空字串
        video3 = data["videos"][2]
        assert video3["tags"] == ""

    def test_mtime_is_integer(self, client, populated_db, monkeypatch):
        """測試 mtime 為整數（不是浮點數）"""
        def mock_get_db_path():
            return populated_db
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        response = client.get("/api/showcase/videos")
        data = response.json()

        # 第一筆：有 mtime
        video1 = data["videos"][0]
        assert isinstance(video1["mtime"], int)
        assert video1["mtime"] == 1705276800  # 浮點數 1705276800.0 → 整數 1705276800

        # 第三筆：零時間
        video3 = data["videos"][2]
        assert video3["mtime"] == 0
        assert isinstance(video3["mtime"], int)

    def test_empty_fields_handling(self, client, populated_db, monkeypatch):
        """測試空值欄位處理正確"""
        def mock_get_db_path():
            return populated_db
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        response = client.get("/api/showcase/videos")
        data = response.json()

        # 第三筆：多個空值欄位
        video3 = data["videos"][2]
        assert video3["number"] == "FC2-PPV-001"  # number 有值
        assert video3["original_title"] == ""  # 空字串
        assert video3["maker"] == ""  # 空字串
        assert video3["release_date"] == ""  # 空字串
        assert video3["actresses"] == ""  # 空陣列 → 空字串
        assert video3["tags"] == ""  # 空陣列 → 空字串
        assert video3["size"] == 0  # 零值
        assert video3["cover_url"] == ""  # 無封面
        assert video3["mtime"] == 0  # 零時間

    def test_response_structure(self, client, populated_db, monkeypatch):
        """測試回應結構完整性"""
        def mock_get_db_path():
            return populated_db
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        response = client.get("/api/showcase/videos")
        assert response.status_code == 200

        data = response.json()
        # 必須包含三個頂層欄位
        assert "success" in data
        assert "videos" in data
        assert "total" in data

        # videos 必須是陣列
        assert isinstance(data["videos"], list)
        # total 必須是整數且等於陣列長度
        assert isinstance(data["total"], int)
        assert data["total"] == len(data["videos"])

    def test_video_path_format(self, client, populated_db, monkeypatch):
        """測試 path 欄位保持 file:/// URI 格式"""
        def mock_get_db_path():
            return populated_db
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        response = client.get("/api/showcase/videos")
        data = response.json()

        # 所有 path 都應該保持 file:/// 格式（開啟影片用）
        for video in data["videos"]:
            assert video["path"].startswith("file:///")
