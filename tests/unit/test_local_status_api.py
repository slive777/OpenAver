"""測試 /api/search/local-status API"""
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
    # 設定 VideoRepository 使用臨時資料庫
    def mock_get_db_path():
        return temp_db

    monkeypatch.setattr("core.database.get_db_path", mock_get_db_path)
    monkeypatch.setattr("web.routers.search.get_db_path", mock_get_db_path)

    from web.app import app
    return TestClient(app)


@pytest.fixture
def populated_db(temp_db):
    """預先填入測試資料的資料庫"""
    repo = VideoRepository(temp_db)

    # 插入測試資料
    videos = [
        Video(
            path="/mnt/media/SONE-205.mp4",
            number="SONE-205",
            title="Test Video 1",
            mtime=100.0
        ),
        Video(
            path="/mnt/media/SONE-205-uncensored.mp4",
            number="SONE-205",
            title="Test Video 1 (Uncensored)",
            mtime=101.0
        ),
        Video(
            path="/mnt/media/ABW-001.mp4",
            number="ABW-001",
            title="Test Video 2",
            mtime=200.0
        ),
        Video(
            path="/mnt/media/fc2-ppv-1234567.mp4",
            number="FC2-PPV-1234567",
            title="FC2 Video",
            mtime=300.0
        ),
    ]
    repo.upsert_batch(videos)
    return temp_db


class TestLocalStatusAPI:
    """測試 /api/search/local-status API"""

    def test_single_number_exists(self, client, populated_db, monkeypatch):
        """測試查詢存在的單一番號"""
        def mock_get_db_path():
            return populated_db
        monkeypatch.setattr("web.routers.search.get_db_path", mock_get_db_path)

        response = client.get("/api/search/local-status?numbers=SONE-205")
        assert response.status_code == 200

        data = response.json()
        assert "SONE-205" in data
        assert data["SONE-205"]["exists"] is True
        assert data["SONE-205"]["count"] == 2
        assert len(data["SONE-205"]["paths"]) == 2

    def test_single_number_not_exists(self, client, populated_db, monkeypatch):
        """測試查詢不存在的單一番號"""
        def mock_get_db_path():
            return populated_db
        monkeypatch.setattr("web.routers.search.get_db_path", mock_get_db_path)

        response = client.get("/api/search/local-status?numbers=XYZ-999")
        assert response.status_code == 200

        data = response.json()
        assert "XYZ-999" in data
        assert data["XYZ-999"]["exists"] is False

    def test_multiple_numbers_mixed(self, client, populated_db, monkeypatch):
        """測試查詢多個番號（混合存在/不存在）"""
        def mock_get_db_path():
            return populated_db
        monkeypatch.setattr("web.routers.search.get_db_path", mock_get_db_path)

        response = client.get("/api/search/local-status?numbers=SONE-205,ABW-001,XYZ-999")
        assert response.status_code == 200

        data = response.json()
        assert data["SONE-205"]["exists"] is True
        assert data["ABW-001"]["exists"] is True
        assert data["XYZ-999"]["exists"] is False

    def test_case_insensitive_lowercase(self, client, populated_db, monkeypatch):
        """測試大小寫不敏感 - 小寫查詢"""
        def mock_get_db_path():
            return populated_db
        monkeypatch.setattr("web.routers.search.get_db_path", mock_get_db_path)

        response = client.get("/api/search/local-status?numbers=sone-205")
        assert response.status_code == 200

        data = response.json()
        assert "sone-205" in data
        assert data["sone-205"]["exists"] is True
        assert data["sone-205"]["count"] == 2

    def test_case_insensitive_mixed(self, client, populated_db, monkeypatch):
        """測試大小寫不敏感 - 混合大小寫查詢"""
        def mock_get_db_path():
            return populated_db
        monkeypatch.setattr("web.routers.search.get_db_path", mock_get_db_path)

        response = client.get("/api/search/local-status?numbers=SoNe-205,abw-001")
        assert response.status_code == 200

        data = response.json()
        assert data["SoNe-205"]["exists"] is True
        assert data["abw-001"]["exists"] is True

    def test_empty_numbers(self, client, temp_db, monkeypatch):
        """測試空番號列表"""
        def mock_get_db_path():
            return temp_db
        monkeypatch.setattr("web.routers.search.get_db_path", mock_get_db_path)

        response = client.get("/api/search/local-status?numbers=")
        assert response.status_code == 200

        data = response.json()
        assert data == {}

    def test_whitespace_handling(self, client, populated_db, monkeypatch):
        """測試空白處理"""
        def mock_get_db_path():
            return populated_db
        monkeypatch.setattr("web.routers.search.get_db_path", mock_get_db_path)

        response = client.get("/api/search/local-status?numbers= SONE-205 , ABW-001 ")
        assert response.status_code == 200

        data = response.json()
        assert data["SONE-205"]["exists"] is True
        assert data["ABW-001"]["exists"] is True

    def test_limit_100_numbers(self, client, temp_db, monkeypatch):
        """測試限制單次查詢最多 100 個番號"""
        def mock_get_db_path():
            return temp_db
        monkeypatch.setattr("web.routers.search.get_db_path", mock_get_db_path)

        # 產生 150 個番號
        numbers = [f"TEST-{i:03d}" for i in range(150)]
        numbers_str = ",".join(numbers)

        response = client.get(f"/api/search/local-status?numbers={numbers_str}")
        assert response.status_code == 200

        data = response.json()
        # 應該只回傳前 100 個
        assert len(data) == 100

    def test_fc2_number(self, client, populated_db, monkeypatch):
        """測試 FC2 番號查詢"""
        def mock_get_db_path():
            return populated_db
        monkeypatch.setattr("web.routers.search.get_db_path", mock_get_db_path)

        response = client.get("/api/search/local-status?numbers=FC2-PPV-1234567")
        assert response.status_code == 200

        data = response.json()
        assert data["FC2-PPV-1234567"]["exists"] is True
        assert data["FC2-PPV-1234567"]["count"] == 1

    def test_same_number_multiple_files(self, client, populated_db, monkeypatch):
        """測試同番號多檔案正確計數"""
        def mock_get_db_path():
            return populated_db
        monkeypatch.setattr("web.routers.search.get_db_path", mock_get_db_path)

        response = client.get("/api/search/local-status?numbers=SONE-205")
        assert response.status_code == 200

        data = response.json()
        assert data["SONE-205"]["exists"] is True
        assert data["SONE-205"]["count"] == 2
        assert "/mnt/media/SONE-205.mp4" in data["SONE-205"]["paths"]
        assert "/mnt/media/SONE-205-uncensored.mp4" in data["SONE-205"]["paths"]


class TestVideoRepositoryGetByNumbers:
    """測試 VideoRepository.get_by_numbers() 方法"""

    def test_get_by_numbers_empty(self, temp_db):
        """測試空番號列表"""
        repo = VideoRepository(temp_db)
        result = repo.get_by_numbers([])
        assert result == {}

    def test_get_by_numbers_not_found(self, temp_db):
        """測試查詢不存在的番號"""
        repo = VideoRepository(temp_db)
        result = repo.get_by_numbers(["XYZ-999"])
        assert result == {}

    def test_get_by_numbers_found(self, temp_db):
        """測試查詢存在的番號"""
        repo = VideoRepository(temp_db)

        video = Video(
            path="/mnt/media/SONE-205.mp4",
            number="SONE-205",
            title="Test Video",
            mtime=100.0
        )
        repo.upsert(video)

        result = repo.get_by_numbers(["SONE-205"])
        assert "SONE-205" in result
        assert len(result["SONE-205"]) == 1
        assert result["SONE-205"][0].path == "/mnt/media/SONE-205.mp4"

    def test_get_by_numbers_case_insensitive(self, temp_db):
        """測試大小寫不敏感"""
        repo = VideoRepository(temp_db)

        video = Video(
            path="/mnt/media/SONE-205.mp4",
            number="SONE-205",
            title="Test Video",
            mtime=100.0
        )
        repo.upsert(video)

        # 小寫查詢
        result = repo.get_by_numbers(["sone-205"])
        assert "sone-205" in result
        assert len(result["sone-205"]) == 1

    def test_get_by_numbers_multiple(self, temp_db):
        """測試多番號查詢"""
        repo = VideoRepository(temp_db)

        videos = [
            Video(path="/mnt/media/SONE-205.mp4", number="SONE-205", mtime=100.0),
            Video(path="/mnt/media/ABW-001.mp4", number="ABW-001", mtime=200.0),
        ]
        repo.upsert_batch(videos)

        result = repo.get_by_numbers(["SONE-205", "ABW-001"])
        assert len(result) == 2
        assert "SONE-205" in result
        assert "ABW-001" in result

    def test_get_by_numbers_same_number_multiple_files(self, temp_db):
        """測試同番號多檔案"""
        repo = VideoRepository(temp_db)

        videos = [
            Video(path="/mnt/media/SONE-205.mp4", number="SONE-205", mtime=100.0),
            Video(path="/mnt/media/SONE-205-uncensored.mp4", number="SONE-205", mtime=101.0),
        ]
        repo.upsert_batch(videos)

        result = repo.get_by_numbers(["SONE-205"])
        assert len(result["SONE-205"]) == 2
