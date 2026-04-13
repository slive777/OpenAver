"""
Unit tests for GET /api/actresses list + POST /api/actresses/{name}/rescrape
Phase 44a T1 — TDD-lite
"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from core.database import init_db, Actress, ActressRepository, Video, VideoRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_with_actresses(tmp_path: Path):
    """建立含女優資料的臨時 DB，回傳 db_path"""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    return db_path


@pytest.fixture
def client_with_db(monkeypatch, db_with_actresses):
    """TestClient with monkeypatched DB path，actress router 用"""
    monkeypatch.setattr("core.database.get_db_path", lambda: db_with_actresses)
    monkeypatch.setattr("web.routers.actress.init_db", lambda: None)
    # patch get_local_photo_path to return None (no photo files in test)
    monkeypatch.setattr("web.routers.actress.get_local_photo_path", lambda name: None)
    from web.app import app
    return TestClient(app), db_with_actresses


# ---------------------------------------------------------------------------
# GET /api/actresses — list endpoint
# ---------------------------------------------------------------------------

class TestActressListEndpoint:

    def test_list_empty(self, client_with_db):
        """空 DB → {"actresses": [], "total": 0}"""
        client, db_path = client_with_db
        response = client.get("/api/actresses")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["actresses"] == []
        assert data["total"] == 0

    def test_list_with_actresses(self, client_with_db):
        """儲存 2 位女優 → 回傳兩筆，含所有欄位 + video_count + created_at"""
        client, db_path = client_with_db
        repo = ActressRepository(db_path)
        repo.save(Actress(name="三上悠亜", name_en="Yua Mikami", height="163cm"))
        repo.save(Actress(name="明日花キララ", name_en="Kirara Asuka"))

        response = client.get("/api/actresses")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["total"] == 2
        assert len(data["actresses"]) == 2

        names = {a["name"] for a in data["actresses"]}
        assert "三上悠亜" in names
        assert "明日花キララ" in names

        # 每筆應含 video_count + created_at + is_favorite
        for actress_data in data["actresses"]:
            assert "video_count" in actress_data
            assert "created_at" in actress_data
            assert isinstance(actress_data["video_count"], int)
            assert actress_data["is_favorite"] is True

    def test_list_video_count_exact_match(self, client_with_db):
        """video_count 使用 json_each 精確比對，不誤匹子字串"""
        client, db_path = client_with_db
        repo = ActressRepository(db_path)
        repo.save(Actress(name="miru"))
        # "miruku" 不應算入 "miru" 的 video_count
        repo.save(Actress(name="miruku"))

        video_repo = VideoRepository(db_path)
        video_repo.upsert_batch([
            Video(
                path="/test/video1.mp4",
                number="TEST-001",
                actresses=["miru"],
                mtime=100.0,
            ),
            Video(
                path="/test/video2.mp4",
                number="TEST-002",
                actresses=["miruku"],
                mtime=200.0,
            ),
        ])

        response = client.get("/api/actresses")
        assert response.status_code == 200
        data = response.json()
        actresses_map = {a["name"]: a for a in data["actresses"]}

        assert actresses_map["miru"]["video_count"] == 1
        assert actresses_map["miruku"]["video_count"] == 1

    def test_list_video_count_dirty_data(self, client_with_db):
        """actresses 欄位為無效 JSON 時，video_count 回傳 0（不炸）"""
        client, db_path = client_with_db
        repo = ActressRepository(db_path)
        repo.save(Actress(name="女優A"))

        # 直接插入 dirty data（actresses 為無效 JSON）
        import sqlite3
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                "INSERT INTO videos (path, number, actresses, mtime) VALUES (?, ?, ?, ?)",
                ("/test/dirty.mp4", "DIRTY-001", "NOT_VALID_JSON", 100.0)
            )

        # 不應 crash，video_count 應為 0
        response = client.get("/api/actresses")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        actress_data = data["actresses"][0]
        assert actress_data["video_count"] == 0

    def test_list_video_count_no_videos(self, client_with_db):
        """videos 表為空 → video_count = 0"""
        client, db_path = client_with_db
        repo = ActressRepository(db_path)
        repo.save(Actress(name="孤獨女優"))

        response = client.get("/api/actresses")
        assert response.status_code == 200
        data = response.json()
        assert data["actresses"][0]["video_count"] == 0


# ---------------------------------------------------------------------------
# POST /api/actresses/{name}/rescrape
# ---------------------------------------------------------------------------

class TestActressRescrapeEndpoint:

    def _make_profile(self, name="三上悠亜"):
        """Helper: 建立模擬 profile dict"""
        return {
            "name": name,
            "name_en": "Yua Mikami",
            "photo_url": "https://example.com/photo.jpg",
            "photo_source": "minnano",
            "primary_text_source": "minnano",
            "text": {
                "birth": "1993-11-16",
                "height": "163cm",
                "cup": "F",
                "aliases": [],
                "tags": [],
            }
        }

    def test_rescrape_success(self, client_with_db, monkeypatch):
        """orchestrator 回傳 profile → 200，actress 資料刷新"""
        client, db_path = client_with_db
        from core.scrapers.actress.orchestrator import ProfileResult

        profile = self._make_profile("三上悠亜")
        mock_result = ProfileResult(data=profile, timed_out=False)

        with patch("web.routers.actress.get_actress_profile", return_value=mock_result), \
             patch("web.routers.actress.download_actress_photo", return_value=True):
            response = client.post("/api/actresses/三上悠亜/rescrape")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["actress"]["name"] == "三上悠亜"
        assert data["photo_downloaded"] is True

        # 驗證 DB 有存入
        repo = ActressRepository(db_path)
        saved = repo.get_by_name("三上悠亜")
        assert saved is not None
        assert saved.height == "163cm"

    def test_rescrape_timeout(self, client_with_db):
        """orchestrator 回傳 timed_out=True → 504"""
        client, db_path = client_with_db
        from core.scrapers.actress.orchestrator import ProfileResult

        mock_result = ProfileResult(data=None, timed_out=True)

        with patch("web.routers.actress.get_actress_profile", return_value=mock_result):
            response = client.post("/api/actresses/三上悠亜/rescrape")

        assert response.status_code == 504
        data = response.json()
        assert data["error"] == "timeout"

    def test_rescrape_not_found(self, client_with_db):
        """orchestrator 回傳 data=None（非 timeout）→ 404"""
        client, db_path = client_with_db
        from core.scrapers.actress.orchestrator import ProfileResult

        mock_result = ProfileResult(data=None, timed_out=False)

        with patch("web.routers.actress.get_actress_profile", return_value=mock_result):
            response = client.post("/api/actresses/不存在的人/rescrape")

        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "not_found"

    def test_rescrape_new_name(self, client_with_db, monkeypatch):
        """name 不在 DB，scrape 成功 → 200（允許，新增 entry）"""
        client, db_path = client_with_db
        from core.scrapers.actress.orchestrator import ProfileResult

        profile = self._make_profile("新人女優")
        mock_result = ProfileResult(data=profile, timed_out=False)

        # 確認 DB 中沒有這個名字
        repo = ActressRepository(db_path)
        assert repo.exists("新人女優") is False

        with patch("web.routers.actress.get_actress_profile", return_value=mock_result), \
             patch("web.routers.actress.download_actress_photo", return_value=False):
            response = client.post("/api/actresses/新人女優/rescrape")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # 應已儲存到 DB
        saved = repo.get_by_name("新人女優")
        assert saved is not None

    def test_rescrape_returns_real_video_count(self, client_with_db):
        """rescrape 成功後，回應 actress.video_count 應為真實值（非硬編碼 0）"""
        client, db_path = client_with_db
        from core.scrapers.actress.orchestrator import ProfileResult

        profile = self._make_profile("三上悠亜")
        mock_result = ProfileResult(data=profile, timed_out=False)

        with patch("web.routers.actress.get_actress_profile", return_value=mock_result), \
             patch("web.routers.actress.download_actress_photo", return_value=True), \
             patch("core.database.ActressRepository.count_videos_for_actress_names", return_value=5), \
             patch("core.database.AliasRepository.resolve", return_value={"三上悠亜"}):
            response = client.post("/api/actresses/三上悠亜/rescrape")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["actress"]["video_count"] == 5


# ---------------------------------------------------------------------------
# Backward compatibility: _actress_to_response default video_count
# ---------------------------------------------------------------------------

class TestActressToResponseBackwardCompatibility:

    def test_actress_to_response_default_video_count(self, monkeypatch):
        """現有呼叫端不傳 video_count → 預設 0，不影響現有行為"""
        monkeypatch.setattr("web.routers.actress.get_local_photo_path", lambda name: None)

        from web.routers.actress import _actress_to_response
        actress = Actress(name="測試女優", name_en="Test Actress")

        # 不傳 video_count，應使用預設值 0
        result = _actress_to_response(actress)
        assert result["video_count"] == 0
        assert result["name"] == "測試女優"

        # 傳 video_count，應正確反映
        result_with_count = _actress_to_response(actress, video_count=5)
        assert result_with_count["video_count"] == 5

        # created_at 應在回傳 dict 中
        assert "created_at" in result
        assert result["created_at"] is None  # Actress() 預設 created_at=None
