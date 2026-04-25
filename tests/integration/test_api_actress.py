"""
test_api_actress.py — 女優 API 整合測試

使用 FastAPI TestClient + 真實 SQLite DB（tmp_path）。
外部依賴（orchestrator + requests）全部 mock。
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient
from core.database import init_db


# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

MOCK_PROFILE = {
    "name": "三上悠亜",
    "name_en": "Yua Mikami",
    "text": {
        "birth": "1993-08-16",
        "height": "158cm",
        "cup": "E",
        "bust": "88",
        "waist": "58",
        "hip": "85",
        "hometown": "東京都",
        "hobby": "ゲーム",
        "aliases": ["鬼頭桃菜"],
        "agency": None,
        "debut_work": None,
        "tags": ["美少女", "巨乳"],
        "nickname": None,
        "blog_url": "https://example.com",
        "official_url": None,
    },
    "photo_url": "https://example.com/photo.jpg",
    "photo_source": "gfriends",
    "img": "https://example.com/photo.jpg",
    "primary_text_source": "minnano",
}

ACTRESS_NAME = "三上悠亜"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path):
    """建立臨時測試資料庫（空 DB，無預置資料）"""
    db_path = tmp_path / "test_actress.db"
    init_db(db_path)
    return db_path


@pytest.fixture
def client(tmp_db, monkeypatch):
    """TestClient，monkeypatch get_db_path 指向 tmp DB，mock 外部依賴"""
    # actress router 從 core.database 匯入 ActressRepository / init_db，
    # 兩者都透過 core.database.get_db_path() 取得路徑，因此 patch core 層
    monkeypatch.setattr("core.database.get_db_path", lambda: tmp_db)

    from web.app import app
    return TestClient(app)


# ---------------------------------------------------------------------------
# T1: POST /api/actresses/favorite — 成功收藏
# ---------------------------------------------------------------------------

class TestAddFavorite:
    """POST /api/actresses/favorite 測試"""

    def test_add_favorite_success(self, client):
        """mock orchestrator 回 profile → 200，DB 存入，photo_downloaded 有值"""
        with patch("web.routers.actress.get_cached_profile", return_value=None), \
             patch("web.routers.actress.get_actress_profile") as mock_get_profile, \
             patch("web.routers.actress.download_actress_photo", return_value=True), \
             patch("web.routers.actress.get_local_photo_path", return_value=None):

            from core.scrapers.actress.orchestrator import ProfileResult
            mock_get_profile.return_value = ProfileResult(data=MOCK_PROFILE, timed_out=False)

            resp = client.post("/api/actresses/favorite", json={"name": ACTRESS_NAME})

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["photo_downloaded"] is True
        actress = data["actress"]
        assert actress["name"] == ACTRESS_NAME
        assert actress["name_en"] == "Yua Mikami"
        assert actress["birth"] == "1993-08-16"
        assert actress["cup"] == "E"

    def test_add_favorite_uses_cache_hit(self, client):
        """cache hit → 不呼叫 get_actress_profile，直接存入 DB"""
        with patch("web.routers.actress.get_cached_profile", return_value=MOCK_PROFILE), \
             patch("web.routers.actress.get_actress_profile") as mock_get_profile, \
             patch("web.routers.actress.download_actress_photo", return_value=True), \
             patch("web.routers.actress.get_local_photo_path", return_value=None):

            resp = client.post("/api/actresses/favorite", json={"name": ACTRESS_NAME})

        assert resp.status_code == 200
        mock_get_profile.assert_not_called()

    def test_add_favorite_duplicate_returns_409(self, client):
        """同名再 POST → 409"""
        # 先收藏一次
        with patch("web.routers.actress.get_cached_profile", return_value=MOCK_PROFILE), \
             patch("web.routers.actress.get_actress_profile"), \
             patch("web.routers.actress.download_actress_photo", return_value=True), \
             patch("web.routers.actress.get_local_photo_path", return_value=None):
            client.post("/api/actresses/favorite", json={"name": ACTRESS_NAME})

        # 第二次 POST → 409
        with patch("web.routers.actress.get_local_photo_path", return_value=None):
            resp = client.post("/api/actresses/favorite", json={"name": ACTRESS_NAME})

        assert resp.status_code == 409
        data = resp.json()
        assert data["error"] == "already_exists"
        assert "actress" in data

    def test_add_favorite_not_found_returns_404(self, client):
        """orchestrator 回 data=None, timed_out=False → 404"""
        with patch("web.routers.actress.get_cached_profile", return_value=None), \
             patch("web.routers.actress.get_actress_profile") as mock_get_profile:

            from core.scrapers.actress.orchestrator import ProfileResult
            mock_get_profile.return_value = ProfileResult(data=None, timed_out=False)

            resp = client.post("/api/actresses/favorite", json={"name": "不存在女優XYZ"})

        assert resp.status_code == 404
        data = resp.json()
        assert data["error"] == "not_found"

    def test_add_favorite_timeout_returns_504(self, client):
        """orchestrator 超時 → 504"""
        with patch("web.routers.actress.get_cached_profile", return_value=None), \
             patch("web.routers.actress.get_actress_profile") as mock_get_profile:

            from core.scrapers.actress.orchestrator import ProfileResult
            mock_get_profile.return_value = ProfileResult(data=None, timed_out=True)

            resp = client.post("/api/actresses/favorite", json={"name": "タイムアウト女優"})

        assert resp.status_code == 504
        data = resp.json()
        assert data["error"] == "timeout"

    def test_add_favorite_empty_name_returns_422(self, client):
        """空名稱 → 422"""
        resp = client.post("/api/actresses/favorite", json={"name": ""})
        assert resp.status_code == 422

    def test_add_favorite_returns_real_video_count(self, client):
        """成功收藏後，回應 actress.video_count 應為真實值（非硬編碼 0）"""
        with patch("web.routers.actress.get_cached_profile", return_value=None), \
             patch("web.routers.actress.get_actress_profile") as mock_get_profile, \
             patch("web.routers.actress.download_actress_photo", return_value=True), \
             patch("web.routers.actress.get_local_photo_path", return_value=None), \
             patch("core.database.ActressRepository.count_videos_for_actress_names", return_value=5), \
             patch("core.database.AliasRepository.resolve", return_value={ACTRESS_NAME}):

            from core.scrapers.actress.orchestrator import ProfileResult
            mock_get_profile.return_value = ProfileResult(data=MOCK_PROFILE, timed_out=False)

            resp = client.post("/api/actresses/favorite", json={"name": ACTRESS_NAME})

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["actress"]["video_count"] == 5


# ---------------------------------------------------------------------------
# T2: GET /api/actresses/{name} — 查詢已收藏女優
# ---------------------------------------------------------------------------

class TestGetActress:
    """GET /api/actresses/{name} 測試"""

    def test_get_actress_success(self, client):
        """已收藏女優 → 200，is_favorite: True"""
        # 先收藏
        with patch("web.routers.actress.get_cached_profile", return_value=MOCK_PROFILE), \
             patch("web.routers.actress.get_actress_profile"), \
             patch("web.routers.actress.download_actress_photo", return_value=True), \
             patch("web.routers.actress.get_local_photo_path", return_value=None):
            client.post("/api/actresses/favorite", json={"name": ACTRESS_NAME})

        # 查詢
        with patch("web.routers.actress.get_local_photo_path", return_value=None):
            resp = client.get(f"/api/actresses/{ACTRESS_NAME}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["is_favorite"] is True
        actress = data["actress"]
        assert actress["name"] == ACTRESS_NAME

    def test_get_actress_not_found_returns_404(self, client):
        """不存在的女優 → 404"""
        resp = client.get("/api/actresses/不存在女優XYZ")

        assert resp.status_code == 404
        data = resp.json()
        assert data["error"] == "not_found"


# ---------------------------------------------------------------------------
# T3: DELETE /api/actresses/{name} — 刪除已收藏女優
# ---------------------------------------------------------------------------

class TestDeleteActress:
    """DELETE /api/actresses/{name} 測試"""

    def test_delete_actress_success(self, client):
        """已收藏女優刪除 → 200，DB 刪除"""
        # 先收藏
        with patch("web.routers.actress.get_cached_profile", return_value=MOCK_PROFILE), \
             patch("web.routers.actress.get_actress_profile"), \
             patch("web.routers.actress.download_actress_photo", return_value=True), \
             patch("web.routers.actress.get_local_photo_path", return_value=None):
            client.post("/api/actresses/favorite", json={"name": ACTRESS_NAME})

        # 刪除
        with patch("web.routers.actress.delete_local_photo", return_value=True):
            resp = client.delete(f"/api/actresses/{ACTRESS_NAME}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

        # 確認 DB 已刪除
        resp2 = client.get(f"/api/actresses/{ACTRESS_NAME}")
        assert resp2.status_code == 404

    def test_delete_actress_not_found_returns_404(self, client):
        """刪除不存在的女優 → 404"""
        resp = client.delete("/api/actresses/不存在女優XYZ")

        assert resp.status_code == 404
        data = resp.json()
        assert data["error"] == "not_found"


# ---------------------------------------------------------------------------
# T4: GET /api/actresses/photo/{name} — 本地照片 binary response
# ---------------------------------------------------------------------------

class TestGetActressPhoto:
    """GET /api/actresses/photo/{name} 測試"""

    def test_get_photo_success(self, client, tmp_path):
        """有本地檔案 → 200 + binary content"""
        # 建立假照片檔案
        fake_photo = tmp_path / "photo.jpg"
        fake_photo.write_bytes(b"\xff\xd8\xff\xe0fake_jpeg_content")

        with patch("web.routers.actress.get_local_photo_path", return_value=fake_photo):
            resp = client.get(f"/api/actresses/photo/{ACTRESS_NAME}")

        assert resp.status_code == 200
        assert resp.content == b"\xff\xd8\xff\xe0fake_jpeg_content"
        assert "image/jpeg" in resp.headers["content-type"]

    def test_get_photo_not_found_returns_404(self, client):
        """無本地照片 → 404"""
        with patch("web.routers.actress.get_local_photo_path", return_value=None):
            resp = client.get(f"/api/actresses/photo/{ACTRESS_NAME}")

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# T5: GET /api/actresses/{name}/photo-candidates — SSE 候選照片串流 (T2 新增)
# ---------------------------------------------------------------------------

def _parse_sse_events(text: str) -> list[dict]:
    """解析 SSE 文字為 event list，每筆 {"event": str, "data": dict}"""
    events = []
    current_event = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("event:"):
            current_event["event"] = line[len("event:"):].strip()
        elif line.startswith("data:"):
            import json as _json
            current_event["data"] = _json.loads(line[len("data:"):].strip())
        elif line == "" and current_event:
            events.append(current_event)
            current_event = {}
    if current_event:
        events.append(current_event)
    return events


class TestPhotoCandidates:
    """GET /api/actresses/{name}/photo-candidates 測試"""

    def _save_actress(self, client):
        """Helper: 收藏 ACTRESS_NAME（photo_source='gfriends'，來自 MOCK_PROFILE）"""
        with patch("web.routers.actress.get_cached_profile", return_value=MOCK_PROFILE), \
             patch("web.routers.actress.get_actress_profile"), \
             patch("web.routers.actress.download_actress_photo", return_value=True), \
             patch("web.routers.actress.get_local_photo_path", return_value=None):
            client.post("/api/actresses/favorite", json={"name": ACTRESS_NAME})

    def _save_actress_with_source(self, client, photo_source):
        """Helper: 收藏 ACTRESS_NAME，指定 photo_source"""
        profile = {**MOCK_PROFILE, "photo_source": photo_source}
        with patch("web.routers.actress.get_cached_profile", return_value=profile), \
             patch("web.routers.actress.get_actress_profile"), \
             patch("web.routers.actress.download_actress_photo", return_value=True), \
             patch("web.routers.actress.get_local_photo_path", return_value=None):
            client.post("/api/actresses/favorite", json={"name": ACTRESS_NAME})

    def test_photo_candidates_actress_not_found(self, client):
        """actress 不在 DB → 404 JSONResponse"""
        resp = client.get("/api/actresses/不存在女優XYZ/photo-candidates")
        assert resp.status_code == 404
        data = resp.json()
        assert data["error"] == "not_found"

    def test_photo_candidates_sse_happy_path(self, client):
        """actress 存在，雲端 mock 回 URL → SSE stream 含 candidate + done events"""
        self._save_actress(client)

        def mock_fetch(name, source):
            return f"https://example.com/{source}/photo.jpg"

        with patch("web.routers.actress._fetch_single_source", side_effect=mock_fetch), \
             patch("web.routers.actress._get_random_videos_with_covers", return_value=[]):
            resp = client.get(f"/api/actresses/{ACTRESS_NAME}/photo-candidates")

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")

        events = _parse_sse_events(resp.text)
        event_names = [e["event"] for e in events]
        assert "done" in event_names

        candidates = [e for e in events if e["event"] == "candidate"]
        # 雲端 mock 成功（gfriends 被過濾，因 photo_source=gfriends），最多 3 來源
        assert len(candidates) <= 3
        for c in candidates:
            assert "source" in c["data"]
            assert "thumb_url" in c["data"]
            assert "full_url" in c["data"]

        # done event 含 total
        done_events = [e for e in events if e["event"] == "done"]
        assert len(done_events) == 1
        assert "total" in done_events[0]["data"]

    def test_photo_candidates_cloud_fail_local_fallback(self, client):
        """雲端全失敗 + 本機有影片 → SSE 仍回 local_crop candidates + done"""
        self._save_actress(client)

        # 建立假 Video
        from unittest.mock import MagicMock as MM
        fake_video = MM()
        fake_video.cover_path = "/fake/cover.jpg"
        fake_video.path = "/fake/video.mp4"

        with patch("web.routers.actress._fetch_single_source", return_value=None), \
             patch("web.routers.actress._get_random_videos_with_covers", return_value=[fake_video]), \
             patch("web.routers.actress.to_file_uri", return_value="file:///fake/video.mp4"):
            resp = client.get(f"/api/actresses/{ACTRESS_NAME}/photo-candidates")

        assert resp.status_code == 200
        events = _parse_sse_events(resp.text)

        candidates = [e for e in events if e["event"] == "candidate"]
        assert len(candidates) == 1
        assert candidates[0]["data"]["source"] == "local_crop"
        assert "thumb_url" in candidates[0]["data"]

        done_events = [e for e in events if e["event"] == "done"]
        assert done_events[0]["data"]["total"] == 1

    def test_photo_candidates_total_zero_when_all_fail(self, client):
        """雲端全失敗 + 本機無影片 → done: {total: 0}"""
        self._save_actress(client)

        with patch("web.routers.actress._fetch_single_source", return_value=None), \
             patch("web.routers.actress._get_random_videos_with_covers", return_value=[]):
            resp = client.get(f"/api/actresses/{ACTRESS_NAME}/photo-candidates")

        assert resp.status_code == 200
        events = _parse_sse_events(resp.text)
        done_events = [e for e in events if e["event"] == "done"]
        assert done_events[0]["data"]["total"] == 0

    def test_photo_candidates_photo_source_none_tries_all_four(self, client):
        """photo_source=None（legacy）時 4 來源全部嘗試"""
        # 先收藏，photo_source 設為 None
        with patch("web.routers.actress.get_cached_profile", return_value={**MOCK_PROFILE, "photo_source": None}), \
             patch("web.routers.actress.get_actress_profile"), \
             patch("web.routers.actress.download_actress_photo", return_value=True), \
             patch("web.routers.actress.get_local_photo_path", return_value=None):
            client.post("/api/actresses/favorite", json={"name": ACTRESS_NAME})

        called_sources = []

        def mock_fetch(name, source):
            called_sources.append(source)
            return None

        with patch("web.routers.actress._fetch_single_source", side_effect=mock_fetch), \
             patch("web.routers.actress._get_random_videos_with_covers", return_value=[]):
            client.get(f"/api/actresses/{ACTRESS_NAME}/photo-candidates")

        # 4 來源全部嘗試
        assert set(called_sources) == {"graphis", "gfriends", "wiki", "minnano"}

    def test_photo_candidates_excludes_current_source(self, client):
        """photo_source='gfriends' 時 gfriends 不會被呼叫，剩 3 來源並行"""
        self._save_actress(client)  # photo_source='gfriends'（MOCK_PROFILE 預設）

        called_sources = []

        def mock_fetch(name, source):
            called_sources.append(source)
            return None

        with patch("web.routers.actress._fetch_single_source", side_effect=mock_fetch), \
             patch("web.routers.actress._get_random_videos_with_covers", return_value=[]):
            resp = client.get(f"/api/actresses/{ACTRESS_NAME}/photo-candidates")

        assert resp.status_code == 200
        assert "gfriends" not in called_sources
        assert set(called_sources) == {"graphis", "wiki", "minnano"}

    def test_photo_candidates_local_crop_tries_all_four(self, client):
        """photo_source='local_crop' 時 4 雲端來源全試"""
        self._save_actress_with_source(client, "local_crop")

        called_sources = []

        def mock_fetch(name, source):
            called_sources.append(source)
            return None

        with patch("web.routers.actress._fetch_single_source", side_effect=mock_fetch), \
             patch("web.routers.actress._get_random_videos_with_covers", return_value=[]):
            client.get(f"/api/actresses/{ACTRESS_NAME}/photo-candidates")

        assert set(called_sources) == {"graphis", "gfriends", "wiki", "minnano"}


# ---------------------------------------------------------------------------
# T6: GET /api/actresses/actress-crop — on-demand crop endpoint (T2 新增)
# ---------------------------------------------------------------------------

class TestActressCrop:
    """GET /api/actresses/actress-crop 測試"""

    def test_actress_crop_success(self, client):
        """crop_video_cover 回 bytes → 200 image/jpeg"""
        fake_jpeg = b"\xff\xd8\xff\xe0FAKE_JPEG"

        with patch("web.routers.actress.crop_video_cover", return_value=fake_jpeg):
            resp = client.get("/api/actresses/actress-crop?path=/fake/cover.jpg&spec=v1")

        assert resp.status_code == 200
        assert "image/jpeg" in resp.headers.get("content-type", "")
        assert resp.content == fake_jpeg

    def test_actress_crop_not_found(self, client):
        """crop_video_cover 回 None → 404"""
        with patch("web.routers.actress.crop_video_cover", return_value=None):
            resp = client.get("/api/actresses/actress-crop?path=/nonexistent/cover.jpg&spec=v1")

        assert resp.status_code == 404

    def test_actress_crop_missing_path_returns_422(self, client):
        """缺少 path 參數 → FastAPI 自動 422"""
        resp = client.get("/api/actresses/actress-crop")
        assert resp.status_code == 422
