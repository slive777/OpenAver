"""
test_api_actress.py — 女優 API 整合測試

使用 FastAPI TestClient + 真實 SQLite DB（tmp_path）。
外部依賴（orchestrator + requests）全部 mock。
"""

import time

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient
from core.database import init_db
from core.path_utils import to_file_uri


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
    # 兩者都透過 core.database.connection.get_db_path() 取得路徑，因此 patch core 層
    monkeypatch.setattr("core.database.connection.get_db_path", lambda: tmp_db)

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
# TASK-100a-T1: _actress_to_response 序列化契約（auto_focal / crop_mode，spec-100）
# ---------------------------------------------------------------------------

class TestActressFocalSerialization:
    """GET /api/actresses/{name} 應吐出 auto_focal / crop_mode，且值真的來自 DB"""

    def test_get_actress_includes_focal_fields_default(self, client):
        """新收藏女優未經 mutator 寫入 → response 含 auto_focal='' / crop_mode='auto'"""
        with patch("web.routers.actress.get_cached_profile", return_value=MOCK_PROFILE), \
             patch("web.routers.actress.get_actress_profile"), \
             patch("web.routers.actress.download_actress_photo", return_value=True), \
             patch("web.routers.actress.get_local_photo_path", return_value=None):
            client.post("/api/actresses/favorite", json={"name": ACTRESS_NAME})

        with patch("web.routers.actress.get_local_photo_path", return_value=None):
            resp = client.get(f"/api/actresses/{ACTRESS_NAME}")

        assert resp.status_code == 200
        actress = resp.json()["actress"]
        assert actress["auto_focal"] == ""
        assert actress["crop_mode"] == "auto"

    def test_get_actress_reflects_manual_focal_value(self, client, tmp_db):
        """update_manual_focal 塞非預設值後 GET → response 反映該值
        （只斷言 key 存在會被「硬編 ''」的實作騙過，這裡驗證值真的來自 DB）"""
        with patch("web.routers.actress.get_cached_profile", return_value=MOCK_PROFILE), \
             patch("web.routers.actress.get_actress_profile"), \
             patch("web.routers.actress.download_actress_photo", return_value=True), \
             patch("web.routers.actress.get_local_photo_path", return_value=None):
            client.post("/api/actresses/favorite", json={"name": ACTRESS_NAME})

        from core.database import ActressRepository
        repo = ActressRepository(tmp_db)
        assert repo.update_manual_focal(ACTRESS_NAME, "0.6,0.3") is True

        with patch("web.routers.actress.get_local_photo_path", return_value=None):
            resp = client.get(f"/api/actresses/{ACTRESS_NAME}")

        assert resp.status_code == 200
        actress = resp.json()["actress"]
        assert actress["auto_focal"] == "0.6,0.3"
        assert actress["crop_mode"] == "manual"


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
             patch("web.routers.actress.to_file_uri", return_value=to_file_uri("/fake/video.mp4")):
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

        with patch("web.routers.actress.crop_video_cover", return_value=fake_jpeg), \
             patch("web.routers.actress.VideoRepository") as mock_repo_cls:
            mock_repo_cls.return_value.is_known_cover_path.return_value = True
            resp = client.get("/api/actresses/actress-crop?path=/fake/cover.jpg&spec=v1")

        assert resp.status_code == 200
        assert "image/jpeg" in resp.headers.get("content-type", "")
        assert resp.content == fake_jpeg

    def test_actress_crop_not_found(self, client):
        """crop_video_cover 回 None → 404"""
        with patch("web.routers.actress.crop_video_cover", return_value=None), \
             patch("web.routers.actress.VideoRepository") as mock_repo_cls:
            mock_repo_cls.return_value.is_known_cover_path.return_value = True
            resp = client.get("/api/actresses/actress-crop?path=/nonexistent/cover.jpg&spec=v1")

        assert resp.status_code == 404

    def test_actress_crop_missing_path_returns_422(self, client):
        """缺少 path 參數 → FastAPI 自動 422"""
        resp = client.get("/api/actresses/actress-crop")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# T7: POST /api/actresses/{name}/photo — 設定女優照片 (T3 新增)
# ---------------------------------------------------------------------------

class TestSetActressPhoto:
    """POST /api/actresses/{name}/photo 測試"""

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

    def _save_video_with_cover(self, tmp_path):
        """Helper: 在 DB 中儲存一筆含 cover_path 的 Video，回傳 (video_path, cover_path)"""
        from core.database import VideoRepository, Video
        video_path = str(tmp_path / "test_video.mp4")
        cover_path = str(tmp_path / "cover.jpg")
        # 建立假 cover 檔案
        Path(cover_path).write_bytes(b"\xff\xd8\xff\xe0fake_cover")
        video = Video(
            path=video_path,
            title="Test Video",
            actresses=[ACTRESS_NAME],
            cover_path=cover_path,
        )
        repo = VideoRepository()
        repo.upsert(video)
        return video_path, cover_path

    # ---- 雲端 happy path ----

    def test_set_actress_photo_cloud_success(self, client):
        """POST /photo source=graphis + url，mock 下載成功，回 200 + photo_url 含 ?t="""
        self._save_actress(client)

        with patch("web.routers.actress.download_actress_photo", return_value=True):
            resp = client.post(
                f"/api/actresses/{ACTRESS_NAME}/photo",
                json={"source": "graphis", "url": "https://example.com/photo.jpg"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "photo_url" in data
        assert "?t=" in data["photo_url"]
        assert data["photo_source"] == "graphis"

    # ---- local_crop happy path ----

    def test_set_actress_photo_local_crop_success(self, client, tmp_db, tmp_path):
        """POST /photo source=local_crop + video_path，mock crop 成功，回 200 + photo_source='local_crop'"""
        self._save_actress(client)
        video_path, cover_path = self._save_video_with_cover(tmp_path)
        video_uri = f"file://{video_path}"
        fake_jpeg = b"\xff\xd8\xff\xe0FAKE_CROP_JPEG"

        gfriends = tmp_path / "gfriends"
        gfriends.mkdir()
        with patch("web.routers.actress.crop_video_cover", return_value=fake_jpeg), \
             patch("web.routers.actress.GFRIENDS_DIR", gfriends):
            resp = client.post(
                f"/api/actresses/{ACTRESS_NAME}/photo",
                json={"source": "local_crop", "video_path": video_uri},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["photo_source"] == "local_crop"
        assert "?t=" in data["photo_url"]
        # file was actually written
        written = list(gfriends.glob("*.jpg"))
        assert len(written) == 1
        assert written[0].read_bytes() == fake_jpeg

    # ---- 錯誤處理 ----

    def test_set_actress_photo_actress_not_found(self, client):
        """actress 不在 DB 時回 404 not_found"""
        resp = client.post(
            "/api/actresses/不存在女優XYZ/photo",
            json={"source": "graphis", "url": "https://example.com/photo.jpg"},
        )
        assert resp.status_code == 404
        assert resp.json()["error"] == "not_found"

    def test_set_actress_photo_unknown_source(self, client):
        """source='unknown_xyz' 回 400 unknown_source"""
        self._save_actress(client)
        resp = client.post(
            f"/api/actresses/{ACTRESS_NAME}/photo",
            json={"source": "unknown_xyz", "url": "https://example.com/photo.jpg"},
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "unknown_source"

    def test_set_actress_photo_cloud_missing_url(self, client):
        """雲端 source 缺 url 回 400 url_required"""
        self._save_actress(client)
        resp = client.post(
            f"/api/actresses/{ACTRESS_NAME}/photo",
            json={"source": "graphis"},
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "url_required"

    def test_set_actress_photo_local_crop_missing_video_path(self, client):
        """local_crop 缺 video_path 回 400 video_path_required"""
        self._save_actress(client)
        resp = client.post(
            f"/api/actresses/{ACTRESS_NAME}/photo",
            json={"source": "local_crop"},
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "video_path_required"

    def test_set_actress_photo_local_crop_video_not_found(self, client, tmp_path):
        """video_path 對應影片不在 DB 回 404 video_or_cover_not_found"""
        self._save_actress(client)
        resp = client.post(
            f"/api/actresses/{ACTRESS_NAME}/photo",
            json={"source": "local_crop", "video_path": to_file_uri("/tmp/nonexistent_video.mp4")},
        )
        assert resp.status_code == 404
        assert resp.json()["error"] == "video_or_cover_not_found"

    def test_set_actress_photo_local_crop_no_cover(self, client, tmp_db, tmp_path):
        """video 在 DB 但 cover_path 為空 → 404 video_or_cover_not_found"""
        self._save_actress(client)
        # 儲存 Video 但沒有 cover_path
        from core.database import VideoRepository, Video
        video_path = str(tmp_path / "no_cover_video.mp4")
        video = Video(
            path=video_path,
            title="No Cover Video",
            actresses=[ACTRESS_NAME],
            cover_path="",  # 空
        )
        VideoRepository().upsert(video)
        video_uri = f"file://{video_path}"

        resp = client.post(
            f"/api/actresses/{ACTRESS_NAME}/photo",
            json={"source": "local_crop", "video_path": video_uri},
        )
        assert resp.status_code == 404
        assert resp.json()["error"] == "video_or_cover_not_found"

    def test_set_actress_photo_local_crop_failed(self, client, tmp_db, tmp_path):
        """crop_video_cover 回 None 時回 500 crop_failed"""
        self._save_actress(client)
        video_path, cover_path = self._save_video_with_cover(tmp_path)
        video_uri = f"file://{video_path}"

        with patch("web.routers.actress.crop_video_cover", return_value=None):
            resp = client.post(
                f"/api/actresses/{ACTRESS_NAME}/photo",
                json={"source": "local_crop", "video_path": video_uri},
            )

        assert resp.status_code == 500
        assert resp.json()["error"] == "crop_failed"

    def test_set_actress_photo_download_failed(self, client):
        """download_actress_photo 回 False 時回 500 download_failed"""
        self._save_actress(client)

        with patch("web.routers.actress.download_actress_photo", return_value=False):
            resp = client.post(
                f"/api/actresses/{ACTRESS_NAME}/photo",
                json={"source": "gfriends", "url": "https://example.com/photo.jpg"},
            )

        assert resp.status_code == 500
        assert resp.json()["error"] == "download_failed"

    # ---- DB 更新驗證 ----

    def test_set_actress_photo_updates_db_photo_source(self, client):
        """成功後 DB actress.photo_source 更新為 req.source"""
        self._save_actress(client)  # photo_source='gfriends' 初始

        with patch("web.routers.actress.download_actress_photo", return_value=True), \
             patch("web.routers.actress.get_local_photo_path", return_value=None):
            resp = client.post(
                f"/api/actresses/{ACTRESS_NAME}/photo",
                json={"source": "graphis", "url": "https://example.com/new_photo.jpg"},
            )

        assert resp.status_code == 200

        # Re-fetch actress from DB to verify photo_source updated
        with patch("web.routers.actress.get_local_photo_path", return_value=None):
            get_resp = client.get(f"/api/actresses/{ACTRESS_NAME}")

        assert get_resp.status_code == 200
        actress_data = get_resp.json()["actress"]
        assert actress_data["photo_source"] == "graphis"

    # ---- cache-bust 驗證 ----

    def test_set_actress_photo_response_has_cache_bust(self, client):
        """回應 photo_url 含 ?t= 整數 timestamp"""
        self._save_actress(client)

        with patch("web.routers.actress.download_actress_photo", return_value=True):
            resp = client.post(
                f"/api/actresses/{ACTRESS_NAME}/photo",
                json={"source": "minnano", "url": "https://example.com/photo.jpg"},
            )

        assert resp.status_code == 200
        photo_url = resp.json()["photo_url"]
        assert "?t=" in photo_url
        # Extract timestamp and verify it's an integer
        t_part = photo_url.split("?t=")[1]
        assert t_part.isdigit(), f"timestamp should be integer, got: {t_part}"

    # ---- 5a: 連續換圖整合測試 ----

    def test_set_actress_photo_continuous_changes(self, client):
        """連續換圖 cloud → local_crop → cloud，每次正確覆蓋 photo_source"""
        self._save_actress(client)  # 初始 photo_source='gfriends'

        # 1st: source=graphis with mock download True → photo_source='graphis'
        with patch("web.routers.actress.download_actress_photo", return_value=True), \
             patch("web.routers.actress.get_local_photo_path", return_value=None):
            resp1 = client.post(
                f"/api/actresses/{ACTRESS_NAME}/photo",
                json={"source": "graphis", "url": "https://example.com/photo1.jpg"},
            )
        assert resp1.status_code == 200
        assert resp1.json()["photo_source"] == "graphis"

        # Verify DB via GET
        with patch("web.routers.actress.get_local_photo_path", return_value=None):
            get1 = client.get(f"/api/actresses/{ACTRESS_NAME}")
        assert get1.json()["actress"]["photo_source"] == "graphis"

        # 2nd: source=local_crop with mock crop → photo_source='local_crop'
        fake_jpeg = b"\xff\xd8\xff\xe0FAKE_CROP"
        # Use FS path video in DB (existing helper stores FS paths)
        from core.database import VideoRepository, Video
        import tempfile, os
        with tempfile.TemporaryDirectory() as td:
            cover_path = os.path.join(td, "cover.jpg")
            video_path = os.path.join(td, "video.mp4")
            Path(cover_path).write_bytes(b"\xff\xd8\xff\xe0fake_cover")
            vid = Video(
                path=video_path,
                title="Continuous Test Video",
                actresses=[ACTRESS_NAME],
                cover_path=cover_path,
            )
            VideoRepository().upsert(vid)
            video_uri = f"file://{video_path}"

            gfriends = Path(td) / "gfriends"
            gfriends.mkdir()
            with patch("web.routers.actress.crop_video_cover", return_value=fake_jpeg), \
                 patch("web.routers.actress.GFRIENDS_DIR", gfriends):
                resp2 = client.post(
                    f"/api/actresses/{ACTRESS_NAME}/photo",
                    json={"source": "local_crop", "video_path": video_uri},
                )
            assert resp2.status_code == 200
            assert resp2.json()["photo_source"] == "local_crop"

        # Verify DB via GET
        with patch("web.routers.actress.get_local_photo_path", return_value=None):
            get2 = client.get(f"/api/actresses/{ACTRESS_NAME}")
        assert get2.json()["actress"]["photo_source"] == "local_crop"

        # 3rd: source=gfriends → photo_source='gfriends'
        with patch("web.routers.actress.download_actress_photo", return_value=True), \
             patch("web.routers.actress.get_local_photo_path", return_value=None):
            resp3 = client.post(
                f"/api/actresses/{ACTRESS_NAME}/photo",
                json={"source": "gfriends", "url": "https://example.com/photo3.jpg"},
            )
        assert resp3.status_code == 200
        assert resp3.json()["photo_source"] == "gfriends"

        # Verify DB via GET
        with patch("web.routers.actress.get_local_photo_path", return_value=None):
            get3 = client.get(f"/api/actresses/{ACTRESS_NAME}")
        assert get3.json()["actress"]["photo_source"] == "gfriends"

    # ---- Fix 3: actress-crop 路徑驗證 ----

    def test_actress_crop_rejects_unknown_path(self, client):
        """actress-crop endpoint：任意路徑（不在 DB cover_path 中）→ 403"""
        with patch("web.routers.actress.VideoRepository") as mock_repo_cls:
            mock_repo = mock_repo_cls.return_value
            mock_repo.is_known_cover_path.return_value = False
            resp = client.get("/api/actresses/actress-crop?path=/evil/path.jpg&spec=v1")
        assert resp.status_code == 403

    def test_actress_crop_accepts_known_video_cover_path(self, client, tmp_path):
        """actress-crop endpoint：DB 中已知 cover_path → 200"""
        fake_jpeg = b"\xff\xd8\xff\xe0FAKE_JPEG"
        with patch("web.routers.actress.VideoRepository") as mock_repo_cls, \
             patch("web.routers.actress.crop_video_cover", return_value=fake_jpeg):
            mock_repo = mock_repo_cls.return_value
            mock_repo.is_known_cover_path.return_value = True
            resp = client.get("/api/actresses/actress-crop?path=/known/cover.jpg&spec=v1")
        assert resp.status_code == 200
        assert resp.content == fake_jpeg

    def test_actress_crop_accepts_uri_input(self, client, tmp_path):
        """actress-crop endpoint：path 帶 file:/// URI 可正確處理（idempotent）"""
        fake_jpeg = b"\xff\xd8\xff\xe0URI_JPEG"
        with patch("web.routers.actress.VideoRepository") as mock_repo_cls, \
             patch("web.routers.actress.crop_video_cover", return_value=fake_jpeg):
            mock_repo = mock_repo_cls.return_value
            mock_repo.is_known_cover_path.return_value = True
            # 傳 file:/// URI，endpoint 應正確轉為 FS path 再查 DB
            resp = client.get("/api/actresses/actress-crop?path=file:///known/cover.jpg&spec=v1")
        assert resp.status_code == 200
        assert resp.content == fake_jpeg

    # ---- 5b: Production-realistic — DB 存 file:/// URI，local_crop 仍能匹配 ----

    def _save_video_with_uri_path(self, tmp_path):
        """Helper: 在 DB 中儲存一筆含 file:/// URI cover_path 的 Video（模擬 production scanner）"""
        from core.database import VideoRepository, Video
        video_path = str(tmp_path / "uri_test_video.mp4")
        cover_path = str(tmp_path / "uri_cover.jpg")
        # 建立假 cover 檔案
        Path(cover_path).write_bytes(b"\xff\xd8\xff\xe0fake_uri_cover")
        # 模擬 scanner 用 to_file_uri 寫入（file:/// URI）
        from core.path_utils import to_file_uri
        video_uri = to_file_uri(video_path)
        cover_uri = to_file_uri(cover_path)
        video = Video(
            path=video_uri,       # DB 存 file:/// URI（production 格式）
            title="URI Test Video",
            actresses=[ACTRESS_NAME],
            cover_path=cover_uri,  # DB 存 file:/// URI（production 格式）
        )
        repo = VideoRepository()
        repo.upsert(video)
        return video_uri, cover_uri, video_path, cover_path

    def test_set_actress_photo_local_crop_matches_uri_in_db(self, client, tmp_db, tmp_path):
        """模擬 production：DB 存 file:/// URI，request 傳 file:/// URI，比對成功"""
        self._save_actress(client)
        video_uri, cover_uri, video_path, cover_path = self._save_video_with_uri_path(tmp_path)
        fake_jpeg = b"\xff\xd8\xff\xe0FAKE_URI_CROP"

        gfriends = tmp_path / "gfriends"
        gfriends.mkdir()
        with patch("web.routers.actress.crop_video_cover", return_value=fake_jpeg), \
             patch("web.routers.actress.GFRIENDS_DIR", gfriends):
            resp = client.post(
                f"/api/actresses/{ACTRESS_NAME}/photo",
                json={"source": "local_crop", "video_path": video_uri},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["photo_source"] == "local_crop"
        assert "?t=" in data["photo_url"]


# ---------------------------------------------------------------------------
# T2 (TASK-100a-T2): POST /api/actresses/{name}/photo/upload — 女優照片上傳
# ---------------------------------------------------------------------------

_ACTRESS_PHOTO_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "actress_photos"

# CD-8/CD-9 固定中文錯誤文案（測試與實作各自獨立宣告字面值，不共用常數，
# 避免「改常數同時改測試」讓 mutation 測試失去意義）
_ERR_TOO_LARGE = "圖片太大（檔案上限 10MB、尺寸上限 50M 像素）"
_ERR_UNSUPPORTED_FORMAT = "不支援的圖片格式"
_ERR_NOT_FOUND = "查無此女優"
_ERR_UPLOAD_FAILED = "上傳照片失敗，請稍後再試"


class TestUploadActressPhoto:
    """POST /api/actresses/{name}/photo/upload 測試（TASK-100a-T2）"""

    def _save_actress(self, client):
        """Helper: 收藏 ACTRESS_NAME（初始 photo_source='gfriends'，比照 TestSetActressPhoto）"""
        with patch("web.routers.actress.get_cached_profile", return_value=MOCK_PROFILE), \
             patch("web.routers.actress.get_actress_profile"), \
             patch("web.routers.actress.download_actress_photo", return_value=True), \
             patch("web.routers.actress.get_local_photo_path", return_value=None):
            client.post("/api/actresses/favorite", json={"name": ACTRESS_NAME})

    @staticmethod
    def _make_image_bytes(fmt: str, size=(100, 100), color=(200, 50, 50)) -> bytes:
        from io import BytesIO
        from PIL import Image
        buf = BytesIO()
        Image.new("RGB", size, color).save(buf, format=fmt)
        return buf.getvalue()

    def _make_jpeg_bytes(self, size=(100, 100), color=(200, 50, 50)) -> bytes:
        return self._make_image_bytes("JPEG", size=size, color=color)

    def _make_png_bytes(self, size=(100, 100), color=(10, 200, 10)) -> bytes:
        return self._make_image_bytes("PNG", size=size, color=color)

    def _make_webp_bytes(self, size=(100, 100), color=(10, 10, 200)) -> bytes:
        return self._make_image_bytes("WEBP", size=size, color=color)

    def _make_oversized_pixel_jpeg_bytes(self) -> bytes:
        """8000x7000 純色 JPEG，w*h=56,000,000 > 50,000,000 CD-9 門檻，磁碟體積很小。"""
        return self._make_jpeg_bytes(size=(8000, 7000), color=(1, 1, 1))

    # ---- DoD① 完整原圖 byte-for-byte ----

    def test_upload_photo_byte_for_byte_original(self, client, tmp_path):
        """上傳 fixture 原始 bytes → 磁碟檔案與原始 bytes 完全相等（非重編碼）"""
        self._save_actress(client)
        original = (_ACTRESS_PHOTO_FIXTURES_DIR / "narrow_face_top.jpg").read_bytes()

        gfriends = tmp_path / "gfriends"
        with patch("web.routers.actress.GFRIENDS_DIR", gfriends), \
             patch("core.actress_photo.GFRIENDS_DIR", gfriends):
            resp = client.post(
                f"/api/actresses/{ACTRESS_NAME}/photo/upload",
                files={"file": ("narrow_face_top.jpg", original, "image/jpeg")},
            )

        assert resp.status_code == 200
        written = list(gfriends.glob("*.jpg"))
        assert len(written) == 1
        assert written[0].read_bytes() == original

    # ---- DoD② PNG/WebP → 存對應副檔名 + GET 回正確 MIME ----

    def test_upload_photo_png_stores_png_ext_and_correct_mime(self, client, tmp_path):
        self._save_actress(client)
        png_bytes = self._make_png_bytes()

        gfriends = tmp_path / "gfriends"
        with patch("web.routers.actress.GFRIENDS_DIR", gfriends), \
             patch("core.actress_photo.GFRIENDS_DIR", gfriends):
            resp = client.post(
                f"/api/actresses/{ACTRESS_NAME}/photo/upload",
                files={"file": ("photo.png", png_bytes, "image/png")},
            )
            assert resp.status_code == 200
            written = list(gfriends.glob("*.png"))
            assert len(written) == 1
            assert list(gfriends.glob("*.jpg")) == []

            get_resp = client.get(f"/api/actresses/photo/{ACTRESS_NAME}")
        assert get_resp.status_code == 200
        assert get_resp.headers["content-type"] == "image/png"

    def test_upload_photo_webp_stores_webp_ext_and_correct_mime(self, client, tmp_path):
        self._save_actress(client)
        webp_bytes = self._make_webp_bytes()

        gfriends = tmp_path / "gfriends"
        with patch("web.routers.actress.GFRIENDS_DIR", gfriends), \
             patch("core.actress_photo.GFRIENDS_DIR", gfriends):
            resp = client.post(
                f"/api/actresses/{ACTRESS_NAME}/photo/upload",
                files={"file": ("photo.webp", webp_bytes, "image/webp")},
            )
            assert resp.status_code == 200
            written = list(gfriends.glob("*.webp"))
            assert len(written) == 1
            assert list(gfriends.glob("*.jpg")) == []

            get_resp = client.get(f"/api/actresses/photo/{ACTRESS_NAME}")
        assert get_resp.status_code == 200
        assert get_resp.headers["content-type"] == "image/webp"

    # ---- DoD③ 上傳後 DB auto_focal 為空 ----

    def test_upload_photo_clears_auto_focal_and_crop_mode(self, client, tmp_db, tmp_path):
        """上傳前先手動存一個焦點，上傳後 DB auto_focal/crop_mode 必須被清空回 auto"""
        self._save_actress(client)
        from core.database import ActressRepository
        ActressRepository(tmp_db).update_manual_focal(ACTRESS_NAME, "0.3000,0.4000")

        gfriends = tmp_path / "gfriends"
        with patch("web.routers.actress.GFRIENDS_DIR", gfriends), \
             patch("core.actress_photo.GFRIENDS_DIR", gfriends):
            resp = client.post(
                f"/api/actresses/{ACTRESS_NAME}/photo/upload",
                files={"file": ("photo.jpg", self._make_jpeg_bytes(), "image/jpeg")},
            )

        assert resp.status_code == 200
        actress = ActressRepository(tmp_db).get_by_name(ACTRESS_NAME)
        assert actress.auto_focal == ""
        assert actress.crop_mode == "auto"

    # ---- DoD④ >10MB → 413 ----

    def test_upload_photo_too_large_413(self, client):
        self._save_actress(client)
        huge = b"\x00" * (10 * 1024 * 1024 + 1)
        resp = client.post(
            f"/api/actresses/{ACTRESS_NAME}/photo/upload",
            files={"file": ("huge.jpg", huge, "image/jpeg")},
        )
        assert resp.status_code == 413
        assert resp.json() == {"error": _ERR_TOO_LARGE}

    def test_upload_photo_size_none_falls_back_to_len_check(self, client, tmp_db, tmp_path):
        """file.size is None（模擬解析器未設置 .size）→ 讀取後仍用 len(data) 正確擋下 413"""
        self._save_actress(client)
        import asyncio
        from web.routers.actress import upload_actress_photo
        import json as _json

        class _FakeFile:
            size = None
            content_type = "image/jpeg"
            filename = "huge.jpg"

            async def read(self):
                return b"\x00" * (10 * 1024 * 1024 + 1)

        gfriends = tmp_path / "gfriends"
        with patch("web.routers.actress.GFRIENDS_DIR", gfriends), \
             patch("core.actress_photo.GFRIENDS_DIR", gfriends):
            resp = asyncio.run(upload_actress_photo(ACTRESS_NAME, _FakeFile()))

        assert resp.status_code == 413
        assert _json.loads(resp.body) == {"error": _ERR_TOO_LARGE}

    # ---- DoD⑤ 假 Content-Type → 415（兩子案例） ----

    def test_upload_photo_content_type_not_whitelisted_415(self, client):
        """Content-Type 不在白名單（application/pdf）→ 415，且在 Image.open() 之前就攔下"""
        self._save_actress(client)
        with patch("web.routers.actress.Image") as mock_image:
            resp = client.post(
                f"/api/actresses/{ACTRESS_NAME}/photo/upload",
                files={"file": ("fake.jpg", b"%PDF-1.4 fake pdf content", "application/pdf")},
            )
            mock_image.open.assert_not_called()

        assert resp.status_code == 415
        assert resp.json() == {"error": _ERR_UNSUPPORTED_FORMAT}

    def test_upload_photo_fake_content_type_non_image_bytes_415(self, client):
        """Content-Type 謊稱 image/jpeg 但 bytes 是純文字 → Image.open() 拋例外 → 415"""
        self._save_actress(client)
        resp = client.post(
            f"/api/actresses/{ACTRESS_NAME}/photo/upload",
            files={"file": ("fake.jpg", b"this is not an image, just plain text data" * 20, "image/jpeg")},
        )
        assert resp.status_code == 415
        assert resp.json() == {"error": _ERR_UNSUPPORTED_FORMAT}

    # ---- DoD⑥ 高壓縮大尺寸圖 → 413，且下游未被呼叫 ----

    def test_upload_photo_oversized_pixels_413_downstream_not_called(self, client):
        self._save_actress(client)
        oversized = self._make_oversized_pixel_jpeg_bytes()

        with patch("web.routers.actress._write_actress_photo") as mock_write, \
             patch("web.routers.actress.clear_focal") as mock_clear, \
             patch("web.routers.actress.ActressRepository.save") as mock_save:
            resp = client.post(
                f"/api/actresses/{ACTRESS_NAME}/photo/upload",
                files={"file": ("huge_pixels.jpg", oversized, "image/jpeg")},
            )
            mock_write.assert_not_called()
            mock_clear.assert_not_called()
            mock_save.assert_not_called()

        assert resp.status_code == 413
        assert resp.json() == {"error": _ERR_TOO_LARGE}

    # ---- DoD⑦ 重載後 photo_source 仍是 upload ----

    def test_upload_photo_persists_photo_source_upload(self, client, tmp_db, tmp_path):
        self._save_actress(client)  # 初始 photo_source='gfriends'
        gfriends = tmp_path / "gfriends"
        with patch("web.routers.actress.GFRIENDS_DIR", gfriends), \
             patch("core.actress_photo.GFRIENDS_DIR", gfriends):
            resp = client.post(
                f"/api/actresses/{ACTRESS_NAME}/photo/upload",
                files={"file": ("photo.jpg", self._make_jpeg_bytes(), "image/jpeg")},
            )
        assert resp.status_code == 200

        from core.database import ActressRepository
        fresh_repo = ActressRepository(tmp_db)  # 新實例，模擬重新載入
        actress = fresh_repo.get_by_name(ACTRESS_NAME)
        assert actress.photo_source == "upload"

    # ---- DoD⑧ 🔴 CD-4 排序鎖 ----

    def test_upload_photo_clear_focal_failure_blocks_write_500(self, client, tmp_db, tmp_path):
        """clear_focal 回 False → 500，_write_actress_photo 未被呼叫，舊圖/舊焦點完全不變"""
        self._save_actress(client)
        from core.database import ActressRepository
        from core.organizer import sanitize_filename
        repo = ActressRepository(tmp_db)
        repo.update_manual_focal(ACTRESS_NAME, "0.2500,0.7500")

        gfriends = tmp_path / "gfriends"
        gfriends.mkdir()
        safe = sanitize_filename(ACTRESS_NAME)
        old_photo = gfriends / f"{safe}.jpg"
        old_bytes = b"\xff\xd8\xff\xe0OLD_PHOTO_BYTES"
        old_photo.write_bytes(old_bytes)

        with patch("web.routers.actress.GFRIENDS_DIR", gfriends), \
             patch("web.routers.actress.clear_focal", return_value=False), \
             patch("web.routers.actress._write_actress_photo") as mock_write:
            resp = client.post(
                f"/api/actresses/{ACTRESS_NAME}/photo/upload",
                files={"file": ("photo.jpg", self._make_jpeg_bytes(), "image/jpeg")},
            )
            mock_write.assert_not_called()

        assert resp.status_code == 500
        assert resp.json() == {"error": _ERR_UPLOAD_FAILED}
        # 檔案完全不變
        assert old_photo.read_bytes() == old_bytes
        assert list(gfriends.glob(f"{safe}.*")) == [old_photo]
        # DB 完全不變（仍是上傳前的舊值，不是空值）
        fresh_actress = ActressRepository(tmp_db).get_by_name(ACTRESS_NAME)
        assert fresh_actress.auto_focal == "0.2500,0.7500"
        assert fresh_actress.crop_mode == "manual"
        assert fresh_actress.photo_source == "gfriends"  # 仍是上傳前的來源，未被改成 upload

    def test_upload_photo_clear_focal_exception_blocks_write_500(self, client, tmp_db, tmp_path):
        """clear_focal 拋例外 → 同樣視為失敗 → 500，_write_actress_photo 未被呼叫"""
        self._save_actress(client)
        gfriends = tmp_path / "gfriends"
        with patch("web.routers.actress.GFRIENDS_DIR", gfriends), \
             patch("web.routers.actress.clear_focal", side_effect=RuntimeError("db locked")), \
             patch("web.routers.actress._write_actress_photo") as mock_write:
            resp = client.post(
                f"/api/actresses/{ACTRESS_NAME}/photo/upload",
                files={"file": ("photo.jpg", self._make_jpeg_bytes(), "image/jpeg")},
            )
            mock_write.assert_not_called()

        assert resp.status_code == 500
        assert resp.json() == {"error": _ERR_UPLOAD_FAILED}

    # ---- DoD⑨ 錯誤 body 固定中文、無 str(e) ----

    def test_upload_photo_error_bodies_fixed_chinese_no_exception_leak(self, client):
        self._save_actress(client)

        # 404
        resp404 = client.post(
            "/api/actresses/不存在女優ABC/photo/upload",
            files={"file": ("photo.jpg", self._make_jpeg_bytes(), "image/jpeg")},
        )
        assert resp404.status_code == 404
        assert resp404.json() == {"error": _ERR_NOT_FOUND}

        # 413
        huge = b"\x00" * (10 * 1024 * 1024 + 1)
        resp413 = client.post(
            f"/api/actresses/{ACTRESS_NAME}/photo/upload",
            files={"file": ("huge.jpg", huge, "image/jpeg")},
        )
        assert resp413.json() == {"error": _ERR_TOO_LARGE}

        # 415
        resp415 = client.post(
            f"/api/actresses/{ACTRESS_NAME}/photo/upload",
            files={"file": ("fake.jpg", b"not an image" * 50, "image/jpeg")},
        )
        assert resp415.json() == {"error": _ERR_UNSUPPORTED_FORMAT}

        # 500 — 注入含敏感細節（假造檔案系統路徑）的例外，確認不外洩
        with patch("web.routers.actress.clear_focal",
                    side_effect=RuntimeError("boom at /secret/fs/path/leak.db")):
            resp500 = client.post(
                f"/api/actresses/{ACTRESS_NAME}/photo/upload",
                files={"file": ("photo.jpg", self._make_jpeg_bytes(), "image/jpeg")},
            )
        assert resp500.status_code == 500
        body500 = resp500.json()
        assert body500 == {"error": _ERR_UPLOAD_FAILED}

        for r in (resp404, resp413, resp415, resp500):
            assert set(r.json().keys()) == {"error"}  # 🔴 Opus 裁決：無 "success" 鍵
            assert "Traceback" not in r.text
            assert "RuntimeError" not in r.text
            assert "/secret/fs/path" not in r.text
            assert "boom" not in r.text

    # ---- DoD⑩ 同秒兩次上傳 → ?v= 不同 ----

    def test_upload_photo_v_param_differs_on_identical_rapid_uploads(self, client, tmp_path):
        """DoD⑩：同秒兩次上傳 → ?v= 不同。

        🔴 刻意上傳**完全相同的 bytes**（review finding）：本測試原本餵兩張**不同尺寸**
        的圖，`?v={mtime_ns}-{size}` 的 **size 分量就獨自保證了不同** → 即使實作退回
        秒級 `int(time.time())`，測試照樣綠，等於沒鎖到 CD-11。相同 bytes → size 恆等
        → 只剩 mtime_ns 能區分，這才是 CD-11 的本體。

        sleep 10ms 的理由（實測，非猜測）：本機 ext4 的 mtime 時間戳粒度約 **3.7ms**，
        兩次寫入若落在同一格會拿到**完全相同的 mtime_ns**（實測連寫 6 次差 0ns）。
        production 不受影響——兩次真實上傳中間隔著 HTTP 解析／PIL 驗證／兩次 DB
        commit／檔案寫入，遠超 4ms。10ms 遠小於 1 秒，「同秒」的前提不變。
        """
        self._save_actress(client)
        same_bytes = self._make_jpeg_bytes(size=(100, 100))
        gfriends = tmp_path / "gfriends"
        with patch("web.routers.actress.GFRIENDS_DIR", gfriends), \
             patch("core.actress_photo.GFRIENDS_DIR", gfriends):
            resp1 = client.post(
                f"/api/actresses/{ACTRESS_NAME}/photo/upload",
                files={"file": ("photo.jpg", same_bytes, "image/jpeg")},
            )
            time.sleep(0.01)
            resp2 = client.post(
                f"/api/actresses/{ACTRESS_NAME}/photo/upload",
                files={"file": ("photo.jpg", same_bytes, "image/jpeg")},
            )

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        v1 = resp1.json()["photo_url"].split("?v=")[1]
        v2 = resp2.json()["photo_url"].split("?v=")[1]
        assert v1 != v2, "同 size 的兩次上傳 ?v= 相同 → mtime_ns 分量沒有生效"

        # 結構鎖（零 flake，不受秒邊界影響）：mtime_ns 量級 ~1.7e18，秒級
        # int(time.time()) 是 ~1.7e9——差 9 個數量級。退回秒級此條必紅。
        assert int(v1.split("-")[0]) > 10**18, "?v= 的第一個分量不是奈秒級 mtime_ns"

    # ---- 回應 body 完整契約（成功路徑，無 "success" 鍵） ----

    def test_upload_photo_response_body_contract(self, client, tmp_path):
        self._save_actress(client)
        gfriends = tmp_path / "gfriends"
        with patch("web.routers.actress.GFRIENDS_DIR", gfriends), \
             patch("core.actress_photo.GFRIENDS_DIR", gfriends):
            resp = client.post(
                f"/api/actresses/{ACTRESS_NAME}/photo/upload",
                files={"file": ("photo.jpg", self._make_jpeg_bytes(), "image/jpeg")},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert set(data.keys()) == {"photo_url", "photo_source", "auto_focal", "crop_mode"}
        assert data["photo_source"] == "upload"
        assert data["auto_focal"] == ""
        assert data["crop_mode"] == "auto"
        assert "?v=" in data["photo_url"]

    # ---- CD-13 補充：不揭露 capabilities ----

    def test_upload_endpoint_not_registered_in_capabilities(self):
        capabilities_src = Path("web/routers/capabilities.py").read_text(encoding="utf-8")
        assert "photo/upload" not in capabilities_src

    # ---- 🔴 spec §3.3 失敗矩陣：寫檔失敗 → 舊圖必須原封不動 ----

    def test_upload_photo_write_failure_keeps_old_photo(self, client, tmp_path):
        """spec-100 §3.3 失敗矩陣宣稱「寫檔失敗 → **舊圖** + 已清焦點 → 置中裁（輕微退化）」。

        🔴 這條就是那句話的證明（review finding）：`_write_actress_photo` 原本先
        `glob` 刪光 `{safe}.*` 才寫入 → 寫檔失敗時舊照片**已經被刪掉了**，使用者的
        照片直接消失，而不是文件宣稱的「舊圖還在、只是退回置中」。CD-4 pre-invalidate
        的整個賣點（「最壞情況從污染變成退回置中」）建立在這句話上——所以它必須為真。

        改法＝清舊檔移到 `os.replace` 成功之後（dest 本身除外）。
        mutation：把清舊檔移回寫入之前 → 本測試必紅。
        """
        from core.organizer import sanitize_filename

        self._save_actress(client)
        gfriends = tmp_path / "gfriends"
        gfriends.mkdir(parents=True, exist_ok=True)

        # 先放一張「舊照片」
        old_bytes = self._make_jpeg_bytes(size=(120, 120), color=(1, 2, 3))
        safe = sanitize_filename(ACTRESS_NAME)
        old_path = gfriends / f"{safe}.jpg"
        old_path.write_bytes(old_bytes)

        # 讓寫入階段炸掉（模擬磁碟寫入失敗），且是在 clear_focal 成功「之後」
        with patch("web.routers.actress.GFRIENDS_DIR", gfriends), \
             patch("core.actress_photo.GFRIENDS_DIR", gfriends), \
             patch("web.routers.actress.os.replace", side_effect=OSError("disk full")):
            resp = client.post(
                f"/api/actresses/{ACTRESS_NAME}/photo/upload",
                files={"file": ("new.png", self._make_png_bytes(), "image/png")},
            )

        assert resp.status_code == 500
        assert resp.json()["error"] == _ERR_UPLOAD_FAILED
        # 🔴 承重斷言：舊照片還在，且 bytes 一個位元都沒變
        assert old_path.exists(), "寫檔失敗卻把舊照片刪了 —— spec §3.3 的失敗矩陣不成立"
        assert old_path.read_bytes() == old_bytes


# ---------------------------------------------------------------------------
# _write_actress_photo — lock-free atomic write (66b-T4b)
# ---------------------------------------------------------------------------


class TestWriteActressPhoto:
    """確定性測試 _write_actress_photo 的 lock-free 原子寫語意（不需真並發）。"""

    def test_write_actress_photo_atomic_last_wins(self, tmp_path):
        """序列兩次同 actress 寫入 → 終態 = 後者 bytes，且只剩一個 jpg（舊檔已取代）。"""
        from web.routers.actress import _write_actress_photo
        from core.organizer import sanitize_filename

        gfriends = tmp_path / "gfriends"
        with patch("web.routers.actress.GFRIENDS_DIR", gfriends):
            _write_actress_photo("Some Name", b"AAA")
            _write_actress_photo("Some Name", b"BBB")

            safe = sanitize_filename("Some Name")
            dest = gfriends / f"{safe}.jpg"
            assert dest.exists()
            assert dest.read_bytes() == b"BBB"
            # 只剩一個此 actress 的 jpg（無 temp 殘留、舊檔已取代）
            assert list(gfriends.glob(f"{safe}.*")) == [dest]
            assert list(gfriends.glob("tmp*")) == []

    def test_write_actress_photo_unlink_race_missing_ok(self, tmp_path):
        """模擬 unlink race：glob 回傳一個已被刪除的舊檔 → unlink(missing_ok=True) 不拋。"""
        from web.routers.actress import _write_actress_photo
        from core.organizer import sanitize_filename

        gfriends = tmp_path / "gfriends"
        gfriends.mkdir()
        safe = sanitize_filename("Race Name")

        # 先寫一個舊檔再刪掉，模擬「另一 writer 已 unlink 同檔」的競態
        stale = gfriends / f"{safe}.png"
        stale.write_bytes(b"OLD")
        stale.unlink()  # 已不存在

        with patch("web.routers.actress.GFRIENDS_DIR", gfriends), \
             patch.object(type(gfriends), "glob", lambda self, pat: [stale]):
            # glob 回傳已刪除的 stale → 不應拋 FileNotFoundError
            _write_actress_photo("Race Name", b"NEW")

        dest = gfriends / f"{safe}.jpg"
        assert dest.exists()
        assert dest.read_bytes() == b"NEW"

    def test_write_actress_photo_no_temp_leftover_on_error(self, tmp_path):
        """os.replace 拋 OSError → 重新拋出，且不留 tmp* 殘檔。"""
        from web.routers.actress import _write_actress_photo

        gfriends = tmp_path / "gfriends"
        with patch("web.routers.actress.GFRIENDS_DIR", gfriends), \
             patch("web.routers.actress.os.replace", side_effect=OSError("boom")):
            with pytest.raises(OSError):
                _write_actress_photo("Err Name", b"DATA")

        # 例外後不留 temp 殘檔
        assert list(gfriends.glob("tmp*")) == []
