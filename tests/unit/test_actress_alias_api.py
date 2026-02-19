"""測試女優名稱管理 API"""
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from core.database import init_db, Video, VideoRepository, ActressAliasRepository, ActressAlias


# temp_db fixture 定義於 tests/unit/conftest.py


@pytest.fixture
def client(temp_db, monkeypatch):
    """建立測試客戶端，使用臨時資料庫"""
    def mock_get_db_path():
        return temp_db

    monkeypatch.setattr("core.database.get_db_path", mock_get_db_path)
    monkeypatch.setattr("web.routers.scanner.get_db_path", mock_get_db_path)

    from web.app import app
    return TestClient(app)


@pytest.fixture
def populated_db(temp_db):
    """預先填入測試資料的資料庫"""
    repo = VideoRepository(temp_db)

    # 插入測試影片資料
    videos = [
        Video(
            path="/mnt/media/SONE-205.mp4",
            number="SONE-205",
            title="Test Video 1",
            actresses=["miru", "other actress"],
            mtime=100.0
        ),
        Video(
            path="/mnt/media/SONE-206.mp4",
            number="SONE-206",
            title="Test Video 2",
            actresses=["miru"],
            mtime=200.0
        ),
        Video(
            path="/mnt/media/ABW-001.mp4",
            number="ABW-001",
            title="Test Video 3",
            actresses=["other actress"],
            mtime=300.0
        ),
    ]
    repo.upsert_batch(videos)
    return temp_db


# === ActressAliasRepository 測試 ===

class TestActressAliasRepository:
    """測試 ActressAliasRepository"""

    def test_get_all_empty(self, temp_db):
        """測試空資料庫取得別名（但有種子資料）"""
        repo = ActressAliasRepository(temp_db)
        aliases = repo.get_all()
        # init_db 會插入種子資料
        assert len(aliases) >= 3

    def test_add_alias(self, temp_db):
        """測試新增別名"""
        repo = ActressAliasRepository(temp_db)
        new_id = repo.add("test_old", "test_new")
        assert new_id > 0

        aliases = repo.get_all()
        found = [a for a in aliases if a.old_name == "test_old"]
        assert len(found) == 1
        assert found[0].new_name == "test_new"
        assert found[0].applied_count == 0

    def test_add_duplicate_old_name(self, temp_db):
        """測試新增重複的舊名稱"""
        repo = ActressAliasRepository(temp_db)
        repo.add("duplicate", "new1")
        # 再次新增同一個 old_name 應該失敗
        new_id = repo.add("duplicate", "new2")
        assert new_id == -1

    def test_delete_alias(self, temp_db):
        """測試刪除別名"""
        repo = ActressAliasRepository(temp_db)
        new_id = repo.add("to_delete", "new_name")
        assert new_id > 0

        success = repo.delete(new_id)
        assert success is True

        aliases = repo.get_all()
        found = [a for a in aliases if a.old_name == "to_delete"]
        assert len(found) == 0

    def test_delete_nonexistent(self, temp_db):
        """測試刪除不存在的別名"""
        repo = ActressAliasRepository(temp_db)
        success = repo.delete(99999)
        assert success is False

    def test_increment_applied_count(self, temp_db):
        """測試增加套用次數"""
        repo = ActressAliasRepository(temp_db)
        new_id = repo.add("count_test", "new_name")

        repo.increment_applied_count(new_id, 5)

        aliases = repo.get_all()
        found = [a for a in aliases if a.id == new_id]
        assert len(found) == 1
        assert found[0].applied_count == 5

        # 再增加
        repo.increment_applied_count(new_id, 3)
        aliases = repo.get_all()
        found = [a for a in aliases if a.id == new_id]
        assert found[0].applied_count == 8


# === VideoRepository 女優相關方法測試 ===

class TestVideoRepositoryActressMethods:
    """測試 VideoRepository 女優相關方法"""

    def test_count_by_actress_found(self, populated_db):
        """測試查詢存在的女優片數"""
        repo = VideoRepository(populated_db)
        count = repo.count_by_actress("miru")
        assert count == 2

    def test_count_by_actress_not_found(self, populated_db):
        """測試查詢不存在的女優片數"""
        repo = VideoRepository(populated_db)
        count = repo.count_by_actress("nonexistent")
        assert count == 0

    def test_get_videos_by_actress_found(self, populated_db):
        """測試取得包含某女優的影片"""
        repo = VideoRepository(populated_db)
        videos = repo.get_videos_by_actress("miru")
        assert len(videos) == 2
        numbers = [v.number for v in videos]
        assert "SONE-205" in numbers
        assert "SONE-206" in numbers

    def test_get_videos_by_actress_not_found(self, populated_db):
        """測試取得不存在女優的影片"""
        repo = VideoRepository(populated_db)
        videos = repo.get_videos_by_actress("nonexistent")
        assert len(videos) == 0

    def test_update_actress_name(self, populated_db):
        """測試更新影片女優名稱"""
        repo = VideoRepository(populated_db)

        # 取得影片 ID
        videos = repo.get_videos_by_actress("miru")
        video_id = videos[0].id

        # 更新名稱
        success = repo.update_actress_name(video_id, "miru", "坂道みる")
        assert success is True

        # 驗證
        updated_video = repo.get_by_path(videos[0].path)
        assert "坂道みる" in updated_video.actresses
        assert "miru" not in updated_video.actresses

    def test_update_actress_name_not_found(self, populated_db):
        """測試更新不存在的女優名稱"""
        repo = VideoRepository(populated_db)

        # 取得影片 ID
        videos = repo.get_videos_by_actress("miru")
        video_id = videos[0].id

        # 嘗試更新不存在的名稱
        success = repo.update_actress_name(video_id, "nonexistent", "new_name")
        assert success is False


# === API 端點測試 ===

class TestActressAliasAPI:
    """測試女優別名 API 端點"""

    def test_get_actress_aliases(self, client, temp_db, monkeypatch):
        """測試取得所有別名"""
        def mock_get_db_path():
            return temp_db
        monkeypatch.setattr("web.routers.scanner.get_db_path", mock_get_db_path)

        response = client.get("/api/gallery/actress-aliases")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        # 有種子資料
        assert len(data["data"]) >= 3

    def test_add_actress_alias(self, client, temp_db, monkeypatch):
        """測試新增別名"""
        def mock_get_db_path():
            return temp_db
        monkeypatch.setattr("web.routers.scanner.get_db_path", mock_get_db_path)

        response = client.post(
            "/api/gallery/actress-aliases",
            json={"old_name": "api_test_old", "new_name": "api_test_new"}
        )
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["data"]["id"] > 0

    def test_add_actress_alias_empty_name(self, client, temp_db, monkeypatch):
        """測試新增空名稱"""
        def mock_get_db_path():
            return temp_db
        monkeypatch.setattr("web.routers.scanner.get_db_path", mock_get_db_path)

        response = client.post(
            "/api/gallery/actress-aliases",
            json={"old_name": "", "new_name": "new"}
        )
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is False
        assert "空" in data["error"]

    def test_add_actress_alias_same_name(self, client, temp_db, monkeypatch):
        """測試新增相同名稱"""
        def mock_get_db_path():
            return temp_db
        monkeypatch.setattr("web.routers.scanner.get_db_path", mock_get_db_path)

        response = client.post(
            "/api/gallery/actress-aliases",
            json={"old_name": "same", "new_name": "same"}
        )
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is False
        assert "相同" in data["error"]

    def test_add_actress_alias_duplicate(self, client, temp_db, monkeypatch):
        """測試新增重複的舊名稱"""
        def mock_get_db_path():
            return temp_db
        monkeypatch.setattr("web.routers.scanner.get_db_path", mock_get_db_path)

        # 第一次新增
        client.post(
            "/api/gallery/actress-aliases",
            json={"old_name": "dup", "new_name": "new1"}
        )

        # 第二次重複新增
        response = client.post(
            "/api/gallery/actress-aliases",
            json={"old_name": "dup", "new_name": "new2"}
        )
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is False
        assert "已存在" in data["error"]

    def test_delete_actress_alias(self, client, temp_db, monkeypatch):
        """測試刪除別名"""
        def mock_get_db_path():
            return temp_db
        monkeypatch.setattr("web.routers.scanner.get_db_path", mock_get_db_path)

        # 先新增
        response = client.post(
            "/api/gallery/actress-aliases",
            json={"old_name": "to_delete_api", "new_name": "new"}
        )
        alias_id = response.json()["data"]["id"]

        # 刪除
        response = client.delete(f"/api/gallery/actress-aliases/{alias_id}")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True

    def test_delete_actress_alias_not_found(self, client, temp_db, monkeypatch):
        """測試刪除不存在的別名"""
        def mock_get_db_path():
            return temp_db
        monkeypatch.setattr("web.routers.scanner.get_db_path", mock_get_db_path)

        response = client.delete("/api/gallery/actress-aliases/99999")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is False
        assert "找不到" in data["error"]

    def test_get_actress_stats(self, client, populated_db, monkeypatch):
        """測試查詢女優片數"""
        def mock_get_db_path():
            return populated_db
        monkeypatch.setattr("web.routers.scanner.get_db_path", mock_get_db_path)

        response = client.get("/api/gallery/actress-stats?name=miru")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["data"]["count"] == 2

    def test_get_actress_stats_not_found(self, client, populated_db, monkeypatch):
        """測試查詢不存在的女優片數"""
        def mock_get_db_path():
            return populated_db
        monkeypatch.setattr("web.routers.scanner.get_db_path", mock_get_db_path)

        response = client.get("/api/gallery/actress-stats?name=nonexistent")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["data"]["count"] == 0


# === NFO 更新函數測試 ===

class TestNfoUpdaterActressFunctions:
    """測試 NFO 女優替換函數"""

    def test_replace_actress_in_nfo(self, tmp_path):
        """測試替換 NFO 中的女優名稱"""
        from core.nfo_updater import replace_actress_in_nfo

        # 建立測試 NFO
        nfo_content = """<?xml version="1.0" encoding="utf-8"?>
<movie>
  <title>Test Movie</title>
  <actor>
    <name>miru</name>
  </actor>
  <actor>
    <name>other actress</name>
  </actor>
</movie>
"""
        nfo_path = tmp_path / "test.nfo"
        nfo_path.write_text(nfo_content, encoding='utf-8')

        # 執行替換
        updated, msg = replace_actress_in_nfo(str(nfo_path), "miru", "坂道みる")

        assert updated is True
        assert "已替換" in msg

        # 驗證
        content = nfo_path.read_text(encoding='utf-8')
        assert "坂道みる" in content
        assert ">miru<" not in content
        assert "other actress" in content  # 其他演員不變

    def test_replace_actress_in_nfo_not_found(self, tmp_path):
        """測試替換不存在的女優名稱"""
        from core.nfo_updater import replace_actress_in_nfo

        nfo_content = """<?xml version="1.0" encoding="utf-8"?>
<movie>
  <title>Test Movie</title>
  <actor>
    <name>other actress</name>
  </actor>
</movie>
"""
        nfo_path = tmp_path / "test.nfo"
        nfo_path.write_text(nfo_content, encoding='utf-8')

        updated, msg = replace_actress_in_nfo(str(nfo_path), "miru", "坂道みる")

        assert updated is False
        assert "未找到" in msg

    def test_replace_actress_in_nfo_invalid_file(self, tmp_path):
        """測試處理無效 NFO 檔案"""
        from core.nfo_updater import replace_actress_in_nfo

        nfo_path = tmp_path / "invalid.nfo"
        nfo_path.write_text("invalid xml content", encoding='utf-8')

        updated, msg = replace_actress_in_nfo(str(nfo_path), "old", "new")

        assert updated is False
        assert "無法解析" in msg
