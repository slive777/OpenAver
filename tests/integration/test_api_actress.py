"""
test_api_actress.py — 女優 API 整合測試

使用 FastAPI TestClient + 真實 SQLite DB（tmp_path）。
外部依賴（orchestrator + requests）全部 mock。
"""

import time

import pytest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from core.database import init_db
from core.focal.subprocess_runner import RunnerOutcome
from core.path_utils import to_file_uri
from tests.conftest import MOCK_FOCAL_XY


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
    "primary_text_source": "xcity",
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


    # ---- TASK-117-T1: covered_names（成功／409 兩條路徑，AC-3.1/3.3/3.4 形狀）----


    def test_add_favorite_covered_names_shape_b_includes_clicked_alias(self, client):
        """covered_names 形狀 B：使用者點的別名（新ありな）不在 scraper 回傳的正式名與
        aliases 裡，仍必須出現在 covered_names——靠 `∪ {name}` 那一半。

        🔴 獨立 reviewer REQUEST CHANGES（mutation 實測）：光斷言 `"新ありな" in
        covered_names` 鎖不住 `resolve(sync_primary)` vs `resolve(name)` 的分歧——
        兩者都會落回「miss → {自己}」分支，因為 `新ありな` 從未被 sync 寫進 alias 表
        （它不在這次 profile 的 aliases=["其他別名"] 裡，只透過 `∪ {name}` 進來）。
        必須額外斷言一個**只有 `resolve(sync_primary)` 才拿得到**的成員：sync 後
        `actress_aliases` 的 group 是 {橋本ありな, 其他別名}（`sync_primary` =
        `actress.name` = "橋本ありな"，來自 profile 的 name 欄位，不是使用者這次
        POST 的 "新ありな"）——`其他別名` 只會出現在 `resolve("橋本ありな")` 裡，
        `resolve("新ありな")`（miss）拿不到它。若實作把 `resolve(sync_primary)`
        誤改成 `resolve(name)`，這條斷言會轉紅（已用 mutation 實地驗證，見
        TASK-117-T1.md 的驗證紀錄）。
        """
        profile = {
            **MOCK_PROFILE,
            "name": "橋本ありな",
            "text": {**MOCK_PROFILE["text"], "aliases": ["其他別名"]},
        }
        with patch("web.routers.actress.get_cached_profile", return_value=None), \
             patch("web.routers.actress.get_actress_profile") as mock_get_profile, \
             patch("web.routers.actress.download_actress_photo", return_value=True), \
             patch("web.routers.actress.get_local_photo_path", return_value=None):

            from core.scrapers.actress.orchestrator import ProfileResult
            mock_get_profile.return_value = ProfileResult(data=profile, timed_out=False)

            resp = client.post("/api/actresses/favorite", json={"name": "新ありな"})

        assert resp.status_code == 200
        covered_names = resp.json()["covered_names"]
        assert "新ありな" in covered_names          # ∪ {name} 那一半
        assert "其他別名" in covered_names           # resolve(sync_primary) 那一半（分歧點）
        assert "橋本ありな" in covered_names

    def test_add_favorite_covered_names_not_persisted_to_alias_table(self, client):
        """covered_names 的聯集只存在於這次 HTTP 回應，不得寫進 actress_aliases 表
        （CD-117-9：庫內存在非人名字串，猜錯會污染全站別名資料）——反向測試釘住。"""
        profile = {
            **MOCK_PROFILE,
            "name": "橋本ありな",
            "text": {**MOCK_PROFILE["text"], "aliases": ["其他別名"]},
        }
        with patch("web.routers.actress.get_cached_profile", return_value=None), \
             patch("web.routers.actress.get_actress_profile") as mock_get_profile, \
             patch("web.routers.actress.download_actress_photo", return_value=True), \
             patch("web.routers.actress.get_local_photo_path", return_value=None):

            from core.scrapers.actress.orchestrator import ProfileResult
            mock_get_profile.return_value = ProfileResult(data=profile, timed_out=False)

            client.post("/api/actresses/favorite", json={"name": "新ありな"})

        from core.database import AliasRepository as _AliasRepository
        record = _AliasRepository().get_by_primary("橋本ありな")
        assert "新ありな" not in record.aliases


# ---------------------------------------------------------------------------
# T2: GET /api/actresses/{name} — 查詢已收藏女優
# ---------------------------------------------------------------------------

class TestPreviewActress:
    """POST /api/actresses/preview 只讀預覽。"""

    @staticmethod
    def _preview(client, name, sources=None):
        if sources is None:
            sources = {"xcity": None, "wiki": None, "graphis": None, "gfriends": None}
        with patch("web.routers.actress.get_actress_profile_preview", create=True) as mock_preview:
            mock_preview.return_value = {"name": name, "sources": sources}
            response = client.post("/api/actresses/preview", json={"name": name})
        mock_preview.assert_called_once_with(name)
        return response


    def test_preview_unfavorited_alias_of_favorited_primary(self, client):
        """PR #211 第三輪 v2：命中已收藏 primary 的別名時，`current` 改回 primary
        的資料（`_actress_to_response` 形狀），不再是 null——即使查詢的別名自己
        沒有既有 row。"""
        from core.database import Actress, ActressRepository, AliasRepository

        ActressRepository().save(Actress(name=ACTRESS_NAME, name_en="Yua Mikami"))
        AliasRepository().add(primary_name=ACTRESS_NAME, aliases=["鬼頭桃菜"])
        response = self._preview(client, "鬼頭桃菜")

        assert response.status_code == 200
        data = response.json()
        assert data["alias_of"] == ACTRESS_NAME
        assert data["current"] is not None
        assert data["current"]["name"] == ACTRESS_NAME
        assert data["current"]["name_en"] == "Yua Mikami"
        assert data["current"]["is_favorite"] is True


# ---------------------------------------------------------------------------
# TASK-100a-T1: _actress_to_response 序列化契約（auto_focal / crop_mode，spec-100）
# ---------------------------------------------------------------------------

class TestActressFocalSerialization:
    """GET /api/actresses/{name} 應吐出 auto_focal / crop_mode，且值真的來自 DB"""


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


# ---------------------------------------------------------------------------
# T4: GET /api/actresses/photo/{name} — 本地照片 binary response
# ---------------------------------------------------------------------------


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


    def test_photo_candidates_sse_happy_path(self, client):
        """actress 存在，雲端 mock 回 URL → SSE stream 含 candidate + done events"""
        self._save_actress(client)

        def mock_fetch(name, source):
            return f"https://example.com/{source}/photo.jpg"

        with patch("web.routers.actress._fetch_single_source", side_effect=mock_fetch), \
             patch("web.routers.actress.graphis_candidates", return_value=[]), \
             patch("web.routers.actress._get_random_videos_with_covers", return_value=[]):
            resp = client.get(f"/api/actresses/{ACTRESS_NAME}/photo-candidates")

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")

        events = _parse_sse_events(resp.text)
        event_names = [e["event"] for e in events]
        assert "done" in event_names

        candidates = [e for e in events if e["event"] == "candidate"]
        # 雲端 mock 成功（gfriends 被過濾，因 photo_source=gfriends），最多 3 來源 + Graphis（此處回空）
        assert len(candidates) <= 5
        for c in candidates:
            assert "source" in c["data"]
            assert "thumb_url" in c["data"]
            assert "full_url" in c["data"]

        # done event 含 total
        done_events = [e for e in events if e["event"] == "done"]
        assert len(done_events) == 1
        assert "total" in done_events[0]["data"]


    def test_photo_candidates_excludes_current_source(self, client):
        """photo_source='gfriends' 時 gfriends 不會被呼叫，剩 3 來源並行"""
        self._save_actress(client)  # photo_source='gfriends'（MOCK_PROFILE 預設）

        called_sources = []

        def mock_fetch(name, source):
            called_sources.append(source)
            return None

        with patch("web.routers.actress._fetch_single_source", side_effect=mock_fetch), \
             patch("web.routers.actress.graphis_candidates", return_value=[]), \
             patch("web.routers.actress._get_random_videos_with_covers", return_value=[]):
            resp = client.get(f"/api/actresses/{ACTRESS_NAME}/photo-candidates")

        assert resp.status_code == 200
        assert "gfriends" not in called_sources
        assert set(called_sources) == {"wiki", "xcity"}  # Graphis 不再經 _fetch_single_source

    # --- spec-185 T3：Graphis 拆出、遞補、exclude ---------------------------

    @staticmethod
    def _sse(client, exclude=None, *, fetch, graphis, videos=()):
        """跑一次 SSE，回傳 (candidates, done_total, graphis 收到的引數 list)。"""
        from unittest.mock import MagicMock
        g_calls = []

        def g_stub(*a):
            g_calls.append(a)
            return graphis(*a)

        vids = []
        for i, cover in enumerate(videos):
            v = MagicMock()
            v.path, v.cover_path = to_file_uri(f"/v/{i}.mp4"), cover
            vids.append(v)
        params = {"exclude": exclude} if exclude is not None else {}
        with patch("web.routers.actress._fetch_single_source", side_effect=fetch), \
             patch("web.routers.actress.graphis_candidates", side_effect=g_stub), \
             patch("web.routers.actress.AliasRepository") as al, \
             patch("web.routers.actress.VideoRepository") as vr:
            al.return_value.resolve.side_effect = lambda n: {n}
            vr.return_value.get_videos_by_actress_names.return_value = vids
            resp = client.get(f"/api/actresses/{ACTRESS_NAME}/photo-candidates", params=params)
        assert resp.status_code == 200
        evs = _parse_sse_events(resp.text)
        done = [e for e in evs if e["event"] == "done"]
        assert len(done) == 1
        return [e["data"] for e in evs if e["event"] == "candidate"], done[0]["data"]["total"], g_calls

    def test_graphis_failure_degrades(self, client, monkeypatch):
        """Graphis 回空／丟例外／逾時 → 與沒有 Graphis 時輸出相同、仍有 done"""
        self._save_actress_with_source(client, "local_crop")
        monkeypatch.setattr("web.routers.actress._GRAPHIS_TIMEOUT_S", 0.2)
        fetch = lambda n, s: f"https://example.com/{s}/p.jpg"
        covers = [to_file_uri("/c/a.jpg"), to_file_uri("/c/b.jpg")]

        def boom(*a):
            raise RuntimeError("x")

        def slow(*a):
            time.sleep(1)
            return ["https://example.com/g/late.jpg"]

        base, bt, _ = self._sse(client, fetch=fetch, graphis=lambda *a: [], videos=covers)
        assert {c["source"] for c in base} >= {"gfriends", "wiki", "xcity", "local_crop"}
        for g in (boom, slow):
            got, total, _ = self._sse(client, fetch=fetch, graphis=g, videos=covers)
            assert sorted(c["id"] for c in got) == sorted(c["id"] for c in base)
            assert total == bt

    def test_quota_and_backfill(self, client):
        """Graphis 固定 2、空位本機優先、本機不夠才由 Graphis 補到 6、photo_source=graphis 仍執行 Graphis"""
        from web.routers.actress import candidate_id
        self._save_actress_with_source(client, "local_crop")
        urls3 = {s: f"https://example.com/{s}/p.jpg" for s in ("gfriends", "wiki", "xcity")}
        picks = [f"https://example.com/g/{i}.jpg" for i in range(6)]
        covers = [to_file_uri(f"/c/{i}.jpg") for i in range(4)]
        ex = ",".join(candidate_id(u) for u in urls3.values())

        def slow_fetch(n, s):
            time.sleep(0.2)
            return urls3[s]

        def slow_graphis(*a):
            time.sleep(0.3)
            return picks

        def counts(got):
            return tuple(sum(c["source"] == k for c in got) for k in ("graphis", "local_crop"))

        # (i) 三源各 1：Graphis 恰 2、本機補 1（早到／晚到）
        for fetch, graphis in ((slow_fetch, lambda *a: picks), (lambda n, s: urls3[s], slow_graphis)):
            got, total, _ = self._sse(client, fetch=fetch, graphis=graphis, videos=covers)
            assert counts(got) == (2, 1) and total == 6
        # (ii)(iii)(iv) 三源全被 exclude：本機優先，不夠才由 Graphis 補
        for n_local, expect in ((4, (2, 4)), (1, (5, 1)), (0, (6, 0))):
            got, total, _ = self._sse(client, ex, fetch=lambda n, s: urls3[s], graphis=lambda *a: picks, videos=covers[:n_local])
            assert counts(got) == expect and total == 6

        from core.database import ActressRepository
        assert ActressRepository().update_fields(ACTRESS_NAME, {"photo_source": "graphis"})
        got, _, calls = self._sse(client, fetch=lambda n, s: None, graphis=lambda *a: picks)
        assert calls[0][2] == "graphis"
        assert any(c["source"] == "graphis" for c in got)

    def test_exclude_filter_dedupe_and_empty(self, client, monkeypatch):
        """exclude 濾三源／Graphis／本機、跨來源去重、全空→0 張＋done、畸形 exclude 不 422"""
        from web.routers.actress import candidate_id, local_crop_url
        from unittest.mock import MagicMock
        self._save_actress_with_source(client, "local_crop")
        covers = [to_file_uri("/c/a.jpg"), to_file_uri("/c/b.jpg")]
        crop = lambda c: local_crop_url(MagicMock(cover_path=c))
        urls3 = {s: f"https://example.com/{s}/p.jpg" for s in ("gfriends", "wiki", "xcity")}
        picks = [f"https://example.com/g/{i}.jpg" for i in range(3)]
        hit = [candidate_id(urls3["wiki"]), candidate_id(picks[0]), candidate_id(crop(covers[0]))]
        ex = ",".join(hit + ["deadbeef"])
        got, _, calls = self._sse(client, ex, fetch=lambda n, s: urls3[s], graphis=lambda *a: picks, videos=covers)
        ids = [c["id"] for c in got]
        assert not set(ids) & set(hit) and len(ids) == len(set(ids))
        assert {c["source"] for c in got} >= {"gfriends", "xcity", "graphis", "local_crop"}
        assert [c["thumb_url"] for c in got if c["source"] == "local_crop"] == [crop(covers[1])]
        assert set(calls[0][3]) == set(hit + ["deadbeef"])

        same = "https://example.com/same.jpg"
        got, _, _ = self._sse(client, fetch=lambda n, s: same, graphis=lambda *a: [same])
        assert [c["full_url"] for c in got] == [same]

        # 兩部影片共用同一封面＋第三部不同、名額只剩 2：共用封面不佔名額，仍送 2 張不同本機候選
        monkeypatch.setattr("web.routers.actress.random.shuffle", lambda x: None)
        shared = [to_file_uri("/c/s.jpg"), to_file_uri("/c/s.jpg"), to_file_uri("/c/t.jpg")]
        got, _, _ = self._sse(client, fetch=lambda n, s: urls3[s], graphis=lambda *a: picks[:1], videos=shared)
        local = [c["thumb_url"] for c in got if c["source"] == "local_crop"]
        assert len(local) == 2 and len(set(local)) == 2

        got, total, _ = self._sse(client, "zzz,,'", fetch=lambda n, s: None, graphis=lambda *a: [])
        assert got == [] and total == 0


# ---------------------------------------------------------------------------
# T6: GET /api/actresses/actress-crop — on-demand crop endpoint (T2 新增)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# T7: POST /api/actresses/{name}/photo — 設定女優照片 (T3 新增)
# ---------------------------------------------------------------------------

# CD-8 固定中文錯誤文案（TASK-100a-T3 新增失敗路徑）——測試與實作各自獨立宣告
# 字面值，不共用常數，避免「改常數同時改測試」讓 mutation 測試失去意義。
_SET_PHOTO_ERR_FAILED = "設定照片失敗，請稍後再試"


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

    @staticmethod
    def _cloud_download_writer(gfriends_dir, content: bytes, ext: str = ".jpg"):
        """回傳可作為 `download_actress_photo` side_effect 的函式：真的把 bytes 寫進
        `gfriends_dir`（TASK-100a-T3：CD-6 讓 `set_actress_photo` 寫完後一律
        `get_local_photo_path` 重解析，`download_actress_photo` 若只是 mock
        `return_value=True` 不寫真檔，重解析會找不到檔案而 500 —— 必須真的落地）。
        """
        from core.organizer import sanitize_filename

        def _write(name, url, source):
            (gfriends_dir / f"{sanitize_filename(name)}{ext}").write_bytes(content)
            return True
        return _write

    # ---- 雲端 happy path ----

    def test_set_actress_photo_cloud_success(self, client, tmp_path):
        """POST /photo source=graphis + url，mock 下載成功且真的落地寫檔，回 200 + photo_url 含 ?v=

        🔴 必改既有測試 #1（TASK-100a-T3 card）：原本 mock `download_actress_photo`
        只 `return_value=True` 不真的寫檔、也沒 patch 任一 GFRIENDS_DIR binding——T3
        新增的 CD-6 `get_local_photo_path(name)` 重解析在真實/production GFRIENDS_DIR
        找不到檔案會回 None → 500。改用 side_effect 真寫檔 + 雙 binding patch。
        """
        self._save_actress(client)
        gfriends = tmp_path / "gfriends"
        gfriends.mkdir()

        with patch(
            "web.routers.actress.download_actress_photo",
            side_effect=self._cloud_download_writer(gfriends, b"\xff\xd8\xff\xe0FAKE_CLOUD_JPEG"),
        ), patch("web.routers.actress.GFRIENDS_DIR", gfriends), \
                patch("core.actress_photo.GFRIENDS_DIR", gfriends):
            resp = client.post(
                f"/api/actresses/{ACTRESS_NAME}/photo",
                json={"source": "graphis", "url": "https://www.graphis.ne.jp/photo.jpg"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "photo_url" in data
        assert "?v=" in data["photo_url"]
        assert data["photo_source"] == "graphis"

    # ---- local_crop happy path ----


    # ---- 錯誤處理 ----


    def test_set_actress_photo_offwhitelist_url_400_and_keeps_focal(self, client, tmp_db):
        """🔴 Codex P2 回歸鎖：白名單外的 URL → 400，且**不得清掉使用者的手動焦點**。

        原本白名單驗證埋在 download_actress_photo 內部、在 clear_focal 之後才跑 →
        一個注定失敗的請求會先把焦點清掉，使用者的手動焦點無聲消失（舊圖還在）。
        這與 T3 對 local_crop 的裁決是同一條原則：不為一次注定失敗的操作先清焦點。
        可達性：set_actress_photo 已揭露於 capabilities，agent 可 POST 任意 url。

        mutation：把 validate_photo_url 檢查移到 _pre_invalidate_focal 之後 → 必紅。
        """
        from core.database import ActressRepository

        self._save_actress(client)
        repo = ActressRepository(tmp_db)
        assert repo.update_manual_focal(ACTRESS_NAME, "0.3000,0.7000") is True

        resp = client.post(
            f"/api/actresses/{ACTRESS_NAME}/photo",
            json={"source": "graphis", "url": "https://evil.example.com/x.jpg"},
        )

        assert resp.status_code == 400
        assert resp.json()["error"] == "照片來源網址不合法"   # CD-8：固定中文，非 snake_case
        # 🔴 承重斷言：焦點原封不動
        row = repo.get_by_name(ACTRESS_NAME)
        assert row.auto_focal == "0.3000,0.7000", "白名單外的 URL 把使用者的手動焦點清掉了"
        assert row.crop_mode == "manual"


    # ---- 🔴 PR#108 Codex 二審 P2-B：清舊檔失敗不可拖垮已成功的換圖 ----


    # ---- DB 更新驗證 ----

    def test_set_actress_photo_updates_db_photo_source(self, client, tmp_path):
        """成功後 DB actress.photo_source 更新為 req.source

        🔴 必改既有測試 #3：原本 `get_local_photo_path(return_value=None)` 的 mock
        涵蓋整個 `with` block（含 POST `/photo` 本身）——T3 的 POST 呼叫需要
        `get_local_photo_path` 讀到真檔，被永遠 mock 成 None 會 500。拆開兩個
        scope：POST 讓它讀到真檔（真寫檔 + 雙 binding patch），GET（僅用於驗證
        `photo_source`，不關心 `photo_url`）繼續 mock None。
        """
        self._save_actress(client)  # photo_source='gfriends' 初始

        gfriends = tmp_path / "gfriends"
        gfriends.mkdir()
        with patch(
            "web.routers.actress.download_actress_photo",
            side_effect=self._cloud_download_writer(gfriends, b"\xff\xd8\xff\xe0FAKE_NEW"),
        ), patch("web.routers.actress.GFRIENDS_DIR", gfriends), \
                patch("core.actress_photo.GFRIENDS_DIR", gfriends):
            resp = client.post(
                f"/api/actresses/{ACTRESS_NAME}/photo",
                json={"source": "graphis", "url": "https://www.graphis.ne.jp/new_photo.jpg"},
            )

        assert resp.status_code == 200

        # Re-fetch actress from DB to verify photo_source updated
        with patch("web.routers.actress.get_local_photo_path", return_value=None):
            get_resp = client.get(f"/api/actresses/{ACTRESS_NAME}")

        assert get_resp.status_code == 200
        actress_data = get_resp.json()["actress"]
        assert actress_data["photo_source"] == "graphis"

    # ---- cache-bust 驗證 ----


    # ---- 5a: 連續換圖整合測試 ----


    # ---- Fix 3: actress-crop 路徑驗證 ----

    def test_actress_crop_rejects_unknown_path(self, client):
        """actress-crop endpoint：任意路徑（不在 DB cover_path 中）→ 403"""
        with patch("web.routers.actress.VideoRepository") as mock_repo_cls:
            mock_repo = mock_repo_cls.return_value
            mock_repo.is_known_cover_path.return_value = False
            resp = client.get("/api/actresses/actress-crop?path=/evil/path.jpg&spec=v1")
        assert resp.status_code == 403


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
        """模擬 production：DB 存 file:/// URI，request 傳 file:/// URI，比對成功

        🔴 必改既有測試 #6：`?t=`→`?v=` + 補 `core.actress_photo.GFRIENDS_DIR` patch
        （只 patch `web.routers.actress.GFRIENDS_DIR` 撞上 §3b 雙 binding 陷阱）。
        """
        self._save_actress(client)
        video_uri, cover_uri, video_path, cover_path = self._save_video_with_uri_path(tmp_path)
        fake_jpeg = b"\xff\xd8\xff\xe0FAKE_URI_CROP"

        gfriends = tmp_path / "gfriends"
        gfriends.mkdir()
        with patch("web.routers.actress.crop_video_cover", return_value=fake_jpeg), \
             patch("web.routers.actress.GFRIENDS_DIR", gfriends), \
             patch("core.actress_photo.GFRIENDS_DIR", gfriends):
            resp = client.post(
                f"/api/actresses/{ACTRESS_NAME}/photo",
                json={"source": "local_crop", "video_path": video_uri},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["photo_source"] == "local_crop"
        assert "?v=" in data["photo_url"]

    # ---- DoD① spec §3.7-4 專屬回歸鎖：換候選圖必須作廢舊焦點 ----

    def test_set_actress_photo_cloud_clears_manual_focal(self, client, tmp_db, tmp_path):
        """cloud：換圖前存好偏側焦點 → 換圖後 DB auto_focal/crop_mode 回 auto

        mutation①：拿掉 clear_focal 呼叫 → 本測試單獨變紅（auto_focal 仍是舊偏側值）。
        """
        self._save_actress(client)
        from core.database import ActressRepository
        repo = ActressRepository(tmp_db)
        repo.update_manual_focal(ACTRESS_NAME, "0.3000,0.4000")

        gfriends = tmp_path / "gfriends"
        gfriends.mkdir()
        with patch(
            "web.routers.actress.download_actress_photo",
            side_effect=self._cloud_download_writer(gfriends, b"\xff\xd8\xff\xe0NEW_CLOUD"),
        ), patch("web.routers.actress.GFRIENDS_DIR", gfriends), \
                patch("core.actress_photo.GFRIENDS_DIR", gfriends):
            resp = client.post(
                f"/api/actresses/{ACTRESS_NAME}/photo",
                json={"source": "graphis", "url": "https://www.graphis.ne.jp/new.jpg"},
            )

        assert resp.status_code == 200
        actress = ActressRepository(tmp_db).get_by_name(ACTRESS_NAME)
        assert actress.auto_focal == ""
        assert actress.crop_mode == "auto"

    def test_set_actress_photo_local_crop_clears_manual_focal(self, client, tmp_db, tmp_path):
        """local_crop：換圖前存好偏側焦點 → 換圖後 DB auto_focal/crop_mode 回 auto

        mutation①：拿掉 clear_focal 呼叫 → 本測試單獨變紅。
        """
        self._save_actress(client)
        from core.database import ActressRepository
        repo = ActressRepository(tmp_db)
        repo.update_manual_focal(ACTRESS_NAME, "0.6000,0.2000")

        video_path, cover_path = self._save_video_with_cover(tmp_path)
        video_uri = f"file://{video_path}"
        fake_jpeg = b"\xff\xd8\xff\xe0NEW_CROP"

        gfriends = tmp_path / "gfriends"
        gfriends.mkdir()
        with patch("web.routers.actress.crop_video_cover", return_value=fake_jpeg), \
             patch("web.routers.actress.GFRIENDS_DIR", gfriends), \
             patch("core.actress_photo.GFRIENDS_DIR", gfriends):
            resp = client.post(
                f"/api/actresses/{ACTRESS_NAME}/photo",
                json={"source": "local_crop", "video_path": video_uri},
            )

        assert resp.status_code == 200
        actress = ActressRepository(tmp_db).get_by_name(ACTRESS_NAME)
        assert actress.auto_focal == ""
        assert actress.crop_mode == "auto"

    # ---- DoD② 🔴 CD-4 排序鎖：clear_focal 失敗 → 不得碰檔案 ----

    def test_set_actress_photo_cloud_clear_focal_failure_blocks_download(self, client, tmp_db, tmp_path):
        """cloud：clear_focal 回 False → 500，download_actress_photo 未被呼叫，舊圖/舊焦點完全不變

        mutation②：把實作改成先呼叫 download_actress_photo、再呼叫 clear_focal
        （順序對調）→ 本測試單獨變紅（download_actress_photo 會被呼叫）。
        """
        self._save_actress(client)
        from core.database import ActressRepository
        from core.organizer import sanitize_filename
        repo = ActressRepository(tmp_db)
        repo.update_manual_focal(ACTRESS_NAME, "0.2500,0.7500")

        gfriends = tmp_path / "gfriends"
        gfriends.mkdir()
        safe = sanitize_filename(ACTRESS_NAME)
        old_photo = gfriends / f"{safe}.jpg"
        old_bytes = b"\xff\xd8\xff\xe0OLD_CLOUD_PHOTO"
        old_photo.write_bytes(old_bytes)

        with patch("web.routers.actress.GFRIENDS_DIR", gfriends), \
             patch("core.actress_photo.GFRIENDS_DIR", gfriends), \
             patch("web.routers.actress.clear_focal", return_value=False), \
             patch("web.routers.actress.download_actress_photo") as mock_download:
            resp = client.post(
                f"/api/actresses/{ACTRESS_NAME}/photo",
                json={"source": "graphis", "url": "https://www.graphis.ne.jp/new.jpg"},
            )
            mock_download.assert_not_called()

        assert resp.status_code == 500
        assert resp.json() == {"error": _SET_PHOTO_ERR_FAILED}
        # 磁碟上的舊照片完全不變
        assert old_photo.read_bytes() == old_bytes
        assert list(gfriends.glob(f"{safe}.*")) == [old_photo]
        # DB 完全不變（仍是換圖前的舊值）
        fresh_actress = ActressRepository(tmp_db).get_by_name(ACTRESS_NAME)
        assert fresh_actress.auto_focal == "0.2500,0.7500"
        assert fresh_actress.crop_mode == "manual"
        assert fresh_actress.photo_source == "gfriends"


    def test_set_actress_photo_local_crop_failed_does_not_call_clear_focal(self, client, tmp_db, tmp_path):
        """local_crop：crop_video_cover 回 None（crop_failed）發生在 clear_focal 之前——
        插入點裁決（TASK-100a-T3 技術要點）：crop 是純運算，crop 失敗不該白清使用者
        存好的焦點。此測試釘住「crop_failed 路徑 clear_focal 未被呼叫」這條非 DoD
        編號但屬承重的行為（plan 補充段落明定）。
        """
        self._save_actress(client)
        video_path, cover_path = self._save_video_with_cover(tmp_path)
        video_uri = f"file://{video_path}"

        with patch("web.routers.actress.crop_video_cover", return_value=None), \
             patch("web.routers.actress.clear_focal") as mock_clear:
            resp = client.post(
                f"/api/actresses/{ACTRESS_NAME}/photo",
                json={"source": "local_crop", "video_path": video_uri},
            )
            mock_clear.assert_not_called()

        assert resp.status_code == 500
        assert resp.json()["error"] == "crop_failed"

    # ---- DoD③ cloud 分支 fp 對實際落地檔 stat（CD-6，副檔名非 .jpg 亦正確） ----


    # ---- DoD④ ?v={mtime_ns}-{size} 取代秒級 ?t=：同秒連續切換兩候選 → URL 必不同 ----

    def test_set_actress_photo_v_param_differs_on_identical_rapid_changes(self, client, tmp_path):
        """DoD④：同秒連續換兩次候選圖（餵完全相同 bytes）→ 兩次 ?v= 不同。

        🔴 刻意餵**完全相同的 bytes**（比照 T2 review finding）：若餵不同尺寸圖，
        `?v={mtime_ns}-{size}` 的 size 分量會獨自保證不同，測試即使實作退回秒級
        `int(time.time())` 也照樣綠，等於沒鎖到 CD-11。

        sleep 10ms 理由（gotchas-backend.md 實測）：本機檔案系統 st_mtime_ns 精度約
        4ms，背靠背寫入可能落在同一格拿到相同 mtime_ns；10ms 遠小於 1 秒，「同秒」
        前提不變。mutation④：把實作改回 `?t={int(time.time())}` → 本測試單獨變紅
        （兩次值相同，因 sleep 遠小於 1 秒）。
        """
        self._save_actress(client)
        same_bytes = b"\xff\xd8\xff\xe0IDENTICAL_BYTES_FOR_CACHE_BUST_TEST"

        gfriends = tmp_path / "gfriends"
        gfriends.mkdir()
        with patch(
            "web.routers.actress.download_actress_photo",
            side_effect=self._cloud_download_writer(gfriends, same_bytes),
        ), patch("web.routers.actress.GFRIENDS_DIR", gfriends), \
                patch("core.actress_photo.GFRIENDS_DIR", gfriends):
            resp1 = client.post(
                f"/api/actresses/{ACTRESS_NAME}/photo",
                json={"source": "graphis", "url": "https://www.graphis.ne.jp/a.jpg"},
            )
            time.sleep(0.01)
            resp2 = client.post(
                f"/api/actresses/{ACTRESS_NAME}/photo",
                json={"source": "graphis", "url": "https://www.graphis.ne.jp/a.jpg"},
            )

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        v1 = resp1.json()["photo_url"].split("?v=")[1]
        v2 = resp2.json()["photo_url"].split("?v=")[1]
        assert v1 != v2, "同 bytes 的兩次換圖 ?v= 相同 → mtime_ns 分量沒有生效"
        assert int(v1.split("-")[0]) > 10**18, "?v= 第一分量不是奈秒級 mtime_ns"

    # ---- 成功回應 body 含 auto_focal/crop_mode（🔴 Opus 裁決：與 T2 對稱） ----

    def test_set_actress_photo_success_body_has_focal_fields(self, client, tmp_path):
        """成功回應 body 須含 auto_focal=='' 且 crop_mode=='auto'（cloud + local_crop 各一）"""
        self._save_actress(client)

        gfriends = tmp_path / "gfriends"
        gfriends.mkdir()
        with patch(
            "web.routers.actress.download_actress_photo",
            side_effect=self._cloud_download_writer(gfriends, b"\xff\xd8\xff\xe0BODY_CHECK_CLOUD"),
        ), patch("web.routers.actress.GFRIENDS_DIR", gfriends), \
                patch("core.actress_photo.GFRIENDS_DIR", gfriends):
            cloud_resp = client.post(
                f"/api/actresses/{ACTRESS_NAME}/photo",
                json={"source": "graphis", "url": "https://www.graphis.ne.jp/body.jpg"},
            )
        assert cloud_resp.status_code == 200
        cloud_data = cloud_resp.json()
        assert cloud_data["auto_focal"] == ""
        assert cloud_data["crop_mode"] == "auto"
        assert set(cloud_data.keys()) == {"photo_url", "photo_source", "auto_focal", "crop_mode"}

        video_path, cover_path = self._save_video_with_cover(tmp_path)
        video_uri = f"file://{video_path}"
        fake_jpeg = b"\xff\xd8\xff\xe0BODY_CHECK_LOCAL"
        with patch("web.routers.actress.crop_video_cover", return_value=fake_jpeg), \
             patch("web.routers.actress.GFRIENDS_DIR", gfriends), \
             patch("core.actress_photo.GFRIENDS_DIR", gfriends):
            local_resp = client.post(
                f"/api/actresses/{ACTRESS_NAME}/photo",
                json={"source": "local_crop", "video_path": video_uri},
            )
        assert local_resp.status_code == 200
        local_data = local_resp.json()
        assert local_data["auto_focal"] == ""
        assert local_data["crop_mode"] == "auto"
        assert set(local_data.keys()) == {"photo_url", "photo_source", "auto_focal", "crop_mode"}

    # ---- TASK-102a-T1: alias 展開對稱（RED→GREEN） ----

    def test_set_actress_photo_local_crop_alias_video_success(self, client, tmp_db, tmp_path):
        """別名片候選儲存：片子掛在別名（非主名）名下，POST 仍須成功（spec-102 §3.1-1）。

        修碼前紅在 404 video_or_cover_not_found（_get_actress_videos 只用主名單查）；
        修碼後 200，比照 test_set_actress_photo_local_crop_success 的斷言深度。
        """
        from core.database import AliasRepository, VideoRepository, Video

        self._save_actress(client)
        alias_name = "別名A"
        # _save_actress → favorite 端點已透過 sync_from_favorite 建立 ACTRESS_NAME 的
        # primary alias 群組（aliases=[]），因此這裡用 add_alias 掛新別名，而非 add()
        # 新建群組（add() 對已存在的 primary_name 會拋 ValueError）。
        ok, err = AliasRepository().add_alias(ACTRESS_NAME, alias_name)
        assert ok, f"add_alias 失敗: {err}"

        video_path = str(tmp_path / "alias_video.mp4")
        cover_path = str(tmp_path / "alias_cover.jpg")
        Path(cover_path).write_bytes(b"\xff\xd8\xff\xe0fake_alias_cover")
        video = Video(
            path=video_path,
            title="Alias Video",
            actresses=[alias_name],
            cover_path=cover_path,
        )
        VideoRepository().upsert(video)
        video_uri = to_file_uri(video_path)
        fake_jpeg = b"\xff\xd8\xff\xe0FAKE_ALIAS_CROP_JPEG"

        gfriends = tmp_path / "gfriends"
        gfriends.mkdir()
        with patch("web.routers.actress.crop_video_cover", return_value=fake_jpeg), \
             patch("web.routers.actress.GFRIENDS_DIR", gfriends), \
             patch("core.actress_photo.GFRIENDS_DIR", gfriends):
            resp = client.post(
                f"/api/actresses/{ACTRESS_NAME}/photo",
                json={"source": "local_crop", "video_path": video_uri},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["photo_source"] == "local_crop"
        assert "?v=" in data["photo_url"]
        written = list(gfriends.glob("*.jpg"))
        assert len(written) == 1
        assert written[0].read_bytes() == fake_jpeg

    def test_set_actress_photo_local_crop_unrelated_actress_still_404(self, client, tmp_db, tmp_path):
        """偽造路徑：片子掛在「無關女優」名下（不在目標 alias set 內），仍須 404
        （spec-102 §3.1-2 安全邊界不動）。
        """
        from core.database import AliasRepository, VideoRepository, Video

        self._save_actress(client)
        ok, err = AliasRepository().add_alias(ACTRESS_NAME, "別名A")
        assert ok, f"add_alias 失敗: {err}"

        unrelated_video_path = str(tmp_path / "unrelated_video.mp4")
        unrelated_cover_path = str(tmp_path / "unrelated_cover.jpg")
        Path(unrelated_cover_path).write_bytes(b"\xff\xd8\xff\xe0fake_unrelated_cover")
        video = Video(
            path=unrelated_video_path,
            title="Unrelated Video",
            actresses=["無關女優XYZ"],
            cover_path=unrelated_cover_path,
        )
        VideoRepository().upsert(video)
        video_uri = to_file_uri(unrelated_video_path)

        resp = client.post(
            f"/api/actresses/{ACTRESS_NAME}/photo",
            json={"source": "local_crop", "video_path": video_uri},
        )
        assert resp.status_code == 404
        assert resp.json()["error"] == "video_or_cover_not_found"


    # ---- 🔴 PR #211 第三輪 v3：身分守衛新擴及本端點 ----

    def test_set_actress_photo_alias_of_favorited_primary_rejected_even_with_own_row(self, client, tmp_db):
        """alias 自己意外也有一筆既有 row（例如曾被單獨收藏過，之後才被同步成
        某個已收藏 primary 的別名）時，舊版 `set_actress_photo` 完全沒有 alias
        檢查——只用字面 name 查 `_load_actress` 找得到那筆孤兒 row 就直接放行
        換圖，繞過 submit_actress／upload_actress_photo 那套「一律擋下並告知
        正確名字」的身分守衛。

        mutation：拿掉 set_actress_photo 裡的 `_favorited_primary_for_alias`
        呼叫 → 本測試必紅（200 而非 400，且 alias 的孤兒 row 被換圖覆寫）。
        """
        from core.database import Actress, ActressRepository, AliasRepository

        primary = ACTRESS_NAME
        alias = "鬼頭桃菜"
        self._save_actress(client)  # 收藏 primary（初始 photo_source='gfriends'）
        repo = ActressRepository(tmp_db)
        repo.save(Actress(name=alias, photo_source="wiki"))
        AliasRepository(tmp_db).sync_from_favorite(primary, [alias])

        resp = client.post(
            f"/api/actresses/{alias}/photo",
            json={"source": "graphis", "url": "https://www.graphis.ne.jp/photo.jpg"},
        )

        assert resp.status_code == 400
        assert primary in resp.json()["error"]
        # 孤兒 row 與 primary row 都必須原封不動——沒有任何寫入發生
        assert repo.get_by_name(alias).photo_source == "wiki"
        assert repo.get_by_name(primary).photo_source == "gfriends"


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


    # ---- DoD⑤ 假 Content-Type → 415（兩子案例） ----


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


    # ---- DoD⑨ 錯誤 body 固定中文、無 str(e) ----


    # ---- DoD⑩ 同秒兩次上傳 → ?v= 不同 ----


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

    # ---- 🔴 Codex P2：repo.update_fields 失敗必須回固定中文，不可逸出成純文字 500 ----


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
             patch("core.atomic_write.os.replace", side_effect=OSError("disk full")):
            resp = client.post(
                f"/api/actresses/{ACTRESS_NAME}/photo/upload",
                files={"file": ("new.png", self._make_png_bytes(), "image/png")},
            )

        assert resp.status_code == 500
        assert resp.json()["error"] == _ERR_UPLOAD_FAILED
        # 🔴 承重斷言：舊照片還在，且 bytes 一個位元都沒變
        assert old_path.exists(), "寫檔失敗卻把舊照片刪了 —— spec §3.3 的失敗矩陣不成立"
        assert old_path.read_bytes() == old_bytes

    # ---- 🔴 PR#108 Codex 二審 P2-B：清舊檔失敗不可拖垮已成功的換圖 ----


    # ---- 🔴 157-post-merge-2：alias 身分守衛必須擋在任何寫入之前 ----

    def test_upload_photo_alias_of_favorited_primary_rejected_even_with_own_row(self, client, tmp_db):
        """alias 自己意外也有一筆既有 row（例如曾被單獨收藏過，之後才被同步成某個
        已收藏 primary 的別名）時，舊版 `upload_actress_photo` 只用字面 name 查
        `_load_actress` 找得到那筆孤兒 row 就直接放行上傳，完全沒有 alias 檢查——
        繞過 submit_actress 那套「一律擋下並告知正確名字」的身分守衛。

        mutation：拿掉 upload_actress_photo 裡的 `_favorited_primary_for_alias` 呼叫 →
        本測試必紅（200 而非 400，且 alias 的孤兒 row 被覆寫）。
        """
        from core.database import Actress, ActressRepository, AliasRepository

        primary = ACTRESS_NAME
        alias = "鬼頭桃菜"
        self._save_actress(client)  # 收藏 primary（初始 photo_source='gfriends'）
        repo = ActressRepository(tmp_db)
        repo.save(Actress(name=alias, photo_source="wiki"))
        AliasRepository(tmp_db).sync_from_favorite(primary, [alias])

        resp = client.post(
            f"/api/actresses/{alias}/photo/upload",
            files={"file": ("photo.jpg", self._make_jpeg_bytes(), "image/jpeg")},
        )

        assert resp.status_code == 400
        assert primary in resp.json()["detail"]
        # 孤兒 row 與 primary row 都必須原封不動——沒有任何寫入發生
        assert repo.get_by_name(alias).photo_source == "wiki"
        assert repo.get_by_name(primary).photo_source == "gfriends"

    def test_upload_photo_serves_new_image_when_stale_sibling_survives(self, client, tmp_path):
        """🔴 PR#108 Codex 三審 P2（端對端）：清舊檔失敗留下舊 .jpg 時，
        GET /photo/{name} 必須送出**剛上傳的 PNG**，不是舊 JPEG。

        上一條（..._permission_error_still_succeeds）只斷言「回 200 + 舊檔還在」，
        **沒斷言 URL 到底送出哪個檔**——這正是本 bug 溜過去的破口：回應 URL 是
        name-based（`/photo/{name}?v=...` 不帶路徑）⇒ 每次 GET 重新 glob ⇒ 舊圖
        bytes 被貼上新圖的 `?v=` 指紋，瀏覽器長期快取錯的圖。

        glob 強制成 NTFS 名稱序（.jpg < .png，舊檔在前）：ext4 是 name-hash 序
        （約 50/50），不 patch 就是擲硬幣、mutation 只有一半機率紅＝假綠。

        mutation：`get_local_photo_path` 改回 `return matches[0]` → 本測試必紅。
        """
        from core.organizer import sanitize_filename

        self._save_actress(client)
        gfriends = tmp_path / "gfriends"
        gfriends.mkdir(parents=True, exist_ok=True)
        old_path = gfriends / f"{sanitize_filename(ACTRESS_NAME)}.jpg"
        old_path.write_bytes(self._make_jpeg_bytes())

        real_unlink = Path.unlink

        def fake_unlink(self_path, *a, **kw):
            if self_path == old_path:
                raise PermissionError("locked by AV scanner")
            return real_unlink(self_path, *a, **kw)

        png_bytes = self._make_png_bytes()
        with patch("web.routers.actress.GFRIENDS_DIR", gfriends), \
             patch("core.actress_photo.GFRIENDS_DIR", gfriends), \
             patch.object(Path, "unlink", fake_unlink):
            resp = client.post(
                f"/api/actresses/{ACTRESS_NAME}/photo/upload",
                files={"file": ("new.png", png_bytes, "image/png")},
            )
        assert resp.status_code == 200

        new_path = gfriends / f"{sanitize_filename(ACTRESS_NAME)}.png"
        assert old_path.exists() and new_path.exists(), "前提：兩檔並存才測得到解析歧義"

        with patch("core.actress_photo.GFRIENDS_DIR", gfriends), \
             patch.object(type(gfriends), "glob", lambda self, pat: [old_path, new_path]):
            photo = client.get(f"/api/actresses/photo/{ACTRESS_NAME}")

        assert photo.status_code == 200
        # 🔴 承重：送出的是新 PNG，不是字母序在前的舊 JPEG
        assert photo.headers["content-type"] == "image/png"
        assert photo.content == png_bytes

    # ---- 🔴 PR #211 第三輪 v2：整段主體防護（前段原本沒有任何 try/except） ----


# ---------------------------------------------------------------------------
# TASK-100a-T4: POST /{name}/detect-focal + POST /{name}/focal
# ---------------------------------------------------------------------------

_FOCAL_ERR_NOT_FOUND = "查無此女優"
_FOCAL_ERR_NO_PHOTO = "找不到照片檔案"
_FOCAL_ERR_INVALID_FORMAT = "無效的焦點座標格式"
_FOCAL_ERR_SAVE_FAILED = "存入手動焦點失敗"


def _save_actress_for_focal(client):
    """Helper（mirror TestUploadActressPhoto._save_actress）：收藏 ACTRESS_NAME。"""
    with patch("web.routers.actress.get_cached_profile", return_value=MOCK_PROFILE), \
         patch("web.routers.actress.get_actress_profile"), \
         patch("web.routers.actress.download_actress_photo", return_value=True), \
         patch("web.routers.actress.get_local_photo_path", return_value=None):
        client.post("/api/actresses/favorite", json={"name": ACTRESS_NAME})


def _place_fixture_photo(gfriends_dir: Path, fixture_name: str) -> Path:
    """把 tests/fixtures/actress_photos/{fixture_name} 複製進 gfriends_dir，檔名對齊 sanitize_filename(ACTRESS_NAME)。"""
    from core.organizer import sanitize_filename
    gfriends_dir.mkdir(parents=True, exist_ok=True)
    safe = sanitize_filename(ACTRESS_NAME)
    ext = Path(fixture_name).suffix
    dest = gfriends_dir / f"{safe}{ext}"
    dest.write_bytes((_ACTRESS_PHOTO_FIXTURES_DIR / fixture_name).read_bytes())
    return dest


class TestDetectActressFocal:
    """POST /api/actresses/{name}/detect-focal 測試（TASK-100a-T4，純預覽，ratio 0.75）"""

    # ---- 女優不存在 → 404 ----


    # ---- 女優存在但無照片 → 400（Opus 裁決：mirror showcase.py:264-266）----


    # ---- §3.7-6 無臉圖不崩（真 fixture）----


    # ---- 真實 fixture 偵測輸出落在寬鬆區間（證明真的有在偵測，非鎖 ratio）----
    # TASK-102c-T1：吸收原本獨立的 test_detect_focal_ratio_is_075_via_spy
    # 的 pass-through spy + ratio==0.75 斷言，省下對同一張圖多跑一次真偵測。
    # 🔴 Opus 裁決 2026-07-15（原適用於獨立 spy 測試，併入後精神原樣延續）：
    # 禁止 stub mock（return_value=...）——那會換掉真偵測器，測試就不再走完整
    # production path。此處用 spy 包住真函式，只多觀察一個參數。

    def test_detect_focal_narrow_face_top_range(self, client, tmp_path):
        _save_actress_for_focal(client)
        gfriends = tmp_path / "gfriends"
        _place_fixture_photo(gfriends, "narrow_face_top.jpg")

        from core.focal import detect_focal as real_detect_focal
        calls = []

        def spy(fs_path, ratio, *, job_key, timeout_s, pre_spawn_check=None, on_outcome=None, external_profile=None):
            calls.append((fs_path, ratio))
            focal = real_detect_focal(fs_path, ratio)  # 真的呼叫下去，回真結果
            return RunnerOutcome(kind="FOUND" if focal is not None else "NO_FACE", focal=focal)

        with patch("web.routers.actress.GFRIENDS_DIR", gfriends), \
             patch("core.actress_photo.GFRIENDS_DIR", gfriends), \
             patch("web.routers.actress.run_detection", spy):
            resp = client.post(f"/api/actresses/{ACTRESS_NAME}/detect-focal")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        x_str, y_str = data["auto_focal"].split(",")
        x, y = float(x_str), float(y_str)
        assert 0.45 < x < 0.55
        assert 0.15 < y < 0.25

        # DoD② ratio 傳 0.75（併入自 test_detect_focal_ratio_is_075_via_spy）
        assert len(calls) == 1, "detect_focal 應恰好被呼叫一次"
        _fs_path, ratio = calls[0]
        assert ratio == 0.75

    # ---- DoD① detect 純預覽，全程零 DB 寫入 ----

    def test_detect_focal_does_not_write_db(self, client, tmp_db, tmp_path):
        _save_actress_for_focal(client)
        from core.database import ActressRepository
        ActressRepository(tmp_db).update_manual_focal(ACTRESS_NAME, "0.3000,0.4000")

        gfriends = tmp_path / "gfriends"
        _place_fixture_photo(gfriends, "narrow_face_top.jpg")
        with patch("web.routers.actress.GFRIENDS_DIR", gfriends), \
             patch("core.actress_photo.GFRIENDS_DIR", gfriends), \
             patch("web.routers.actress.run_detection", return_value=RunnerOutcome(kind="FOUND", focal=MOCK_FOCAL_XY)):
            resp = client.post(f"/api/actresses/{ACTRESS_NAME}/detect-focal")

        assert resp.status_code == 200
        data = resp.json()
        # 偵測出的新值必須與呼叫前存的值不同（否則測試無法區分「有寫入」vs「沒寫入」）
        assert data["auto_focal"] != "0.3000,0.4000"

        actress = ActressRepository(tmp_db).get_by_name(ACTRESS_NAME)
        assert actress.auto_focal == "0.3000,0.4000", "detect-focal 是純預覽，不得寫入 DB"
        assert actress.crop_mode == "manual"

    # ---- DoD⑤ response 不含任何 FS path（全分支）----


    # ---- CD-13：不揭露進 capabilities ----


    def test_disabled_short_circuits_before_runner_lock(self, client, tmp_path, monkeypatch):
        """關掉自動對焦後，點裁切工具不得進 run_detection 全域鎖排隊。

        端點層用 await to_thread(is_disabled) 短路；本測試寫真的 focal_device config，
        並用 assert_not_called() 鎖「一次都不准呼叫」這個不變式。
        """
        import core.config as core_config
        from core.config import save_config

        _save_actress_for_focal(client)
        gfriends = tmp_path / "gfriends"
        _place_fixture_photo(gfriends, "narrow_face_top.jpg")

        # 選 set_by_user=True：使用者關掉對焦與版本無關，is_disabled_in 直接讀 disabled，
        # 不依賴 judged_at_version == VERSION（避免 lazy-reset 把測試讀成「未停用」）。
        config_path = tmp_path / "config.json"
        monkeypatch.setattr(core_config, "CONFIG_PATH", config_path)
        monkeypatch.setattr(core_config, "CONFIG_DEFAULT_PATH", tmp_path / "config.default.json")
        save_config({
            "focal_device": {
                "disabled": True,
                "set_by_user": True,
                "judged_at_version": "",
                "consecutive_timeout_count": 0,
            }
        })

        # stub 回一個看得出來的 focal（0.99）而不是拋例外：拋例外會被端點的 except
        # 收成 500，紅字只剩 `assert 500 == 200`，跟「端點因為別的原因炸了」分不出來。
        with patch("web.routers.actress.GFRIENDS_DIR", gfriends), \
             patch("core.actress_photo.GFRIENDS_DIR", gfriends), \
             patch(
                 "web.routers.actress.run_detection",
                 return_value=RunnerOutcome(kind="FOUND", focal=(0.99, 0.99)),
             ) as spy:
            resp = client.post(f"/api/actresses/{ACTRESS_NAME}/detect-focal")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["auto_focal"] == "", "短路被拿掉了：偵測真的跑了並回了座標"
        assert body["reason"] == "device_disabled"
        assert "cover_path" not in body
        spy.assert_not_called()


    def test_manual_detect_timeout_does_not_contribute(self, client, tmp_path):
        """CD-152d-2b②：前景逾時走 record_manual_outcome（非 record_outcome），reason=too_slow_auto_disabled。"""
        from core.focal import device_state

        _save_actress_for_focal(client)
        gfriends = tmp_path / "gfriends"
        _place_fixture_photo(gfriends, "narrow_face_top.jpg")

        def fake_run(
            fs_path, ratio, *, job_key, timeout_s, pre_spawn_check=None, on_outcome=None,
            external_profile=None,
        ):
            outcome = RunnerOutcome(kind="ABANDONED", reason="detect_timeout")
            if on_outcome is not None:
                on_outcome(outcome)
            return outcome

        with patch("web.routers.actress.GFRIENDS_DIR", gfriends), \
             patch("core.actress_photo.GFRIENDS_DIR", gfriends), \
             patch.object(device_state, "record_outcome") as record_bg_spy, \
             patch.object(device_state, "record_manual_outcome", return_value=True) as record_manual_spy, \
             patch("web.routers.actress.run_detection", side_effect=fake_run) as spy:
            resp = client.post(f"/api/actresses/{ACTRESS_NAME}/detect-focal")

        assert resp.status_code == 200
        assert resp.json() == {
            "success": True, "auto_focal": "", "reason": "too_slow_auto_disabled",
        }
        assert "on_outcome" in spy.call_args.kwargs, "path③ must pass on_outcome= explicitly"
        assert spy.call_args.kwargs["on_outcome"] is not None
        assert record_manual_spy.call_count == 1
        assert record_bg_spy.call_count == 0


    @pytest.mark.parametrize("abandoned_reason", ["crashed"])
    def test_reason_failed_for_non_timeout_abandoned(self, client, tmp_path, abandoned_reason):
        """reason 值域：startup_timeout／crashed／circuit_open → 'failed'。"""
        _save_actress_for_focal(client)
        gfriends = tmp_path / "gfriends"
        _place_fixture_photo(gfriends, "narrow_face_top.jpg")
        with patch("web.routers.actress.GFRIENDS_DIR", gfriends), \
             patch("core.actress_photo.GFRIENDS_DIR", gfriends), \
             patch(
                 "web.routers.actress.run_detection",
                 return_value=RunnerOutcome(kind="ABANDONED", reason=abandoned_reason),
             ):
            resp = client.post(f"/api/actresses/{ACTRESS_NAME}/detect-focal")
        assert resp.status_code == 200
        assert resp.json()["reason"] == "failed"
        assert resp.json()["reason"] not in ("too_slow", "too_slow_auto_disabled")


class TestSetActressFocal:
    """POST /api/actresses/{name}/focal 測試（TASK-100a-T4，CD-3：無 compare token / 無 409）"""

    # ---- DoD④ parse_focal 驗證先於一切（含 DB）----


    def test_set_focal_invalid_format_existing_actress_400(self, client):
        _save_actress_for_focal(client)
        resp = client.post(
            f"/api/actresses/{ACTRESS_NAME}/focal",
            json={"focal": ""},
        )
        assert resp.status_code == 400
        assert resp.json() == {"success": False, "error": _FOCAL_ERR_INVALID_FORMAT}

    # ---- 格式合法、女優不存在 → 404 ----


    # ---- DoD③ 單一 UPDATE 同寫 auto_focal + crop_mode 兩欄 ----

    def test_set_focal_single_update_writes_both_columns(self, client, tmp_db):
        _save_actress_for_focal(client)  # crop_mode 預設 'auto'
        resp = client.post(
            f"/api/actresses/{ACTRESS_NAME}/focal",
            json={"focal": "0.4000,0.6000"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"success": True, "auto_focal": "0.4000,0.6000"}

        from core.database import ActressRepository
        actress = ActressRepository(tmp_db).get_by_name(ACTRESS_NAME)
        assert actress.auto_focal == "0.4000,0.6000"
        assert actress.crop_mode == "manual"

    # ---- DoD⑤ response 不含任何 FS path（全分支）----


    # ---- CD-13：不揭露進 capabilities ----


# ---------------------------------------------------------------------------
# _write_actress_photo — lock-free atomic write (66b-T4b)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 157-post-merge-1: _persist_photo_source 改單欄寫入，不可覆蓋並發寫入的其他欄位
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# TASK-122-T10: 刮不到女優改用本地封面建卡（miss + 庫裡有片 → best-effort 裁圖）
# ---------------------------------------------------------------------------

class TestAddFavoriteLocalCropFallback:
    """POST /api/actresses/favorite 的 miss 分支：四來源全刮不到、片庫裡有片時，
    改建一張只有名字的本地卡，照片 best-effort 從片封面右側裁 3:4（issue #143）。

    🔴 全 class 硬前提：任何會寫／讀本地照片的測試，`GFRIENDS_DIR` 雙 binding
    （`web.routers.actress` ＋ `core.actress_photo`）都要 patch，否則會寫進
    owner 真實的 output/Gfriends/（gotchas-backend.md §3b）。
    """

    ACTRESS = "長澤史華"

    @staticmethod
    def _profile_result_miss(timed_out=False):
        from core.scrapers.actress.orchestrator import ProfileResult
        return ProfileResult(data=None, timed_out=timed_out)

    def _save_video(self, tmp_path, actress_name, with_cover=True, suffix=""):
        """在 tmp DB 存一筆該女優的片。path / cover_path 一律用 to_file_uri
        產生（CLAUDE.md 路徑禁止清單：禁止手拼 file:/// 字串）。"""
        from core.database import VideoRepository, Video

        video_fs = str(tmp_path / f"video{suffix}.mp4")
        cover_uri = ""
        if with_cover:
            cover_fs = str(tmp_path / f"cover{suffix}.jpg")
            Path(cover_fs).write_bytes(b"\xff\xd8\xff\xe0fake_cover")
            cover_uri = to_file_uri(cover_fs)
        video = Video(
            path=to_file_uri(video_fs),
            title="Test Video",
            actresses=[actress_name],
            cover_path=cover_uri,
        )
        VideoRepository().upsert(video)
        return video

    def test_add_favorite_local_crop_success(self, client, tmp_path):
        """AC-1: miss ＋ 庫裡有片有封面 → 200，本地裁圖建卡且照片真的落地"""
        self._save_video(tmp_path, self.ACTRESS)
        gfriends = tmp_path / "gfriends"
        gfriends.mkdir()
        fake_jpeg = b"\xff\xd8\xff\xe0FAKE_LOCAL_CROP"

        with patch("web.routers.actress.get_cached_profile", return_value=None), \
             patch("web.routers.actress.get_actress_profile",
                   return_value=self._profile_result_miss()), \
             patch("web.routers.actress.crop_video_cover", return_value=fake_jpeg), \
             patch("web.routers.actress.GFRIENDS_DIR", gfriends), \
             patch("core.actress_photo.GFRIENDS_DIR", gfriends):
            resp = client.post("/api/actresses/favorite", json={"name": self.ACTRESS})

        assert resp.status_code == 200
        data = resp.json()
        actress = data["actress"]
        assert actress["photo_url"] is not None
        assert actress["photo_source"] == "local_crop"
        assert actress["primary_text_source"] == "local"
        assert data["photo_downloaded"] is True

        written = list(gfriends.glob("*.jpg"))
        assert len(written) == 1
        assert written[0].read_bytes() == fake_jpeg


    def test_add_favorite_timeout_with_videos_does_not_create_card(self, client, tmp_path):
        """AC-4: timeout ＋ 庫裡有片 → 仍 504、不建卡（閘門不得誤套進 504 分支，
        既有空 DB 的 test_add_favorite_timeout_returns_504 擋不住這個回歸）"""
        self._save_video(tmp_path, self.ACTRESS)
        gfriends = tmp_path / "gfriends"

        with patch("web.routers.actress.get_cached_profile", return_value=None), \
             patch("web.routers.actress.get_actress_profile",
                   return_value=self._profile_result_miss(timed_out=True)), \
             patch("web.routers.actress.GFRIENDS_DIR", gfriends), \
             patch("core.actress_photo.GFRIENDS_DIR", gfriends):
            resp = client.post("/api/actresses/favorite", json={"name": self.ACTRESS})
            assert resp.status_code == 504
            assert resp.json()["error"] == "timeout"

            get_resp = client.get(f"/api/actresses/{self.ACTRESS}")
        assert get_resp.status_code == 404


# ---------------------------------------------------------------------------
# TASK-174-T3a / CD-174-17：沒有任何雲端照片 → 收藏時從片封面裁頭像
# ---------------------------------------------------------------------------

class TestAddFavoriteCropWhenNoCloudPhoto:
    """POST /api/actresses/favorite：orchestrator 有資料（例：只有 avbase）但所有
    照片來源都沒照片時，片庫裡有她的片 → 從片封面裁頭像；沒有片 → 照片空白仍 200；
    有雲端照片 → 照舊下載、不裁圖。

    以 `_fetch_all_sources` 替身跑真的 get_actress_profile 與真快取（不 patch
    get_actress_profile／get_cached_profile），才驗得到 cache hit 的共享 dict。
    """

    ACTRESS = "甘夏唯"

    @pytest.fixture(autouse=True)
    def _clear_profile_cache(self):
        from core.scrapers.actress import orchestrator
        orchestrator._cache.clear()
        yield
        orchestrator._cache.clear()

    @staticmethod
    def _sources(graphis=None):
        from core.scrapers.actress.orchestrator import _FetchedSources
        return _FetchedSources({
            "xcity": None,
            "wiki": None,
            "graphis": graphis,
            "gfriends": None,
            "avbase": {"birth": "1999-11-30", "height": "162cm"},
        })

    def _save_video(self, tmp_path, actress_name):
        from core.database import VideoRepository, Video

        video_fs = str(tmp_path / "video.mp4")
        cover_fs = str(tmp_path / "cover.jpg")
        Path(cover_fs).write_bytes(b"\xff\xd8\xff\xe0fake_cover")
        VideoRepository().upsert(Video(
            path=to_file_uri(video_fs),
            title="Test Video",
            actresses=[actress_name],
            cover_path=to_file_uri(cover_fs),
        ))


    def test_cloud_photo_present_never_crops(self, client, tmp_path):
        """③：有雲端照片（graphis）且片庫有她的片 → 照舊下載、不裁圖"""
        self._save_video(tmp_path, self.ACTRESS)
        gfriends = tmp_path / "gfriends"
        gfriends.mkdir()

        with patch("core.scrapers.actress.orchestrator._fetch_all_sources",
                   return_value=self._sources(graphis={"prof_url": "https://example.com/p.jpg"})), \
             patch("web.routers.actress._try_local_crop_photo") as mock_try_crop, \
             patch("web.routers.actress.download_actress_photo", return_value=True) as mock_dl, \
             patch("web.routers.actress.GFRIENDS_DIR", gfriends), \
             patch("core.actress_photo.GFRIENDS_DIR", gfriends):
            resp = client.post("/api/actresses/favorite", json={"name": self.ACTRESS})

        assert resp.status_code == 200
        assert resp.json()["actress"]["photo_source"] == "graphis"
        assert mock_try_crop.call_count == 0
        assert mock_dl.call_count == 1


class TestPreviewIncludesAvbase:
    """174-T3（AC13）：真的 get_actress_profile_preview＋_fetch_all_sources 跑，
    只 patch 五個來源函式；預覽的 sources 多一份 avbase，照片候選不含 avbase。"""

    def test_preview_sources_include_avbase_dict(self, client):
        name = "二階堂麗"
        avbase_dict = {"birth": "1999-11-30", "other_names": ["二階堂れい"]}
        wiki_dict = {"name_ja": name, "photo_url": "https://example.com/wiki-photo.jpg"}

        with patch("core.scrapers.actress.xcity.scrape_xcity", return_value=None), \
             patch("core.scrapers.actress.wiki_ja.scrape_wiki_ja", return_value=wiki_dict), \
             patch("core.scrapers.actress.graphis.scrape_graphis_photo", return_value=None), \
             patch("core.scrapers.actress.gfriends.lookup_gfriends", return_value=None), \
             patch("core.scrapers.actress.avbase.scrape_avbase", return_value=avbase_dict):
            resp = client.post("/api/actresses/preview", json={"name": name})

        assert resp.status_code == 200
        data = resp.json()
        assert set(data["sources"]) == {"xcity", "wiki", "graphis", "gfriends", "avbase"}
        assert data["sources"]["avbase"] == avbase_dict
        assert data["sources"]["wiki"] == wiki_dict
        assert data["photo_candidates"] == [
            {"source": "wiki", "url": "https://example.com/wiki-photo.jpg"}
        ]


# ---------------------------------------------------------------------------
# TASK-174-T4a：文字欄位順序「維基 → xcity → graphis → avbase」（五源替身 → 收藏 → DB）
# ---------------------------------------------------------------------------

def _t4a_sources(xcity=None, wiki=None, avbase=None):
    """五鍵一律給齊；graphis／gfriends 為 None（不走下載與裁圖）。"""
    from core.scrapers.actress.orchestrator import _FetchedSources
    return _FetchedSources({
        "xcity": xcity,
        "wiki": wiki,
        "graphis": None,
        "gfriends": None,
        "avbase": avbase,
    })


@pytest.fixture
def _t4a_clear_profile_cache():
    from core.scrapers.actress import orchestrator
    orchestrator._cache.clear()
    yield
    orchestrator._cache.clear()


_T4A_XCITY = {"name_ja": "順序女優", "birth": "1992-02-02", "bust": "82cm", "height": "152cm"}
_T4A_WIKI = {"name_ja": "順序女優", "birth": "1991-01-01", "bust": "81cm", "height": "151cm"}
_T4A_AVBASE = {"birth": "1994-04-04", "bust": "84cm", "height": "154cm"}


@pytest.mark.usefixtures("_t4a_clear_profile_cache")
class TestAddFavoriteTextSourceOrder:
    """174-T4a：收藏後 DB 的 bust／birth／primary_text_source 依新順序取值。"""

    ACTRESS = "順序女優"

    @pytest.mark.parametrize(
        "xcity,wiki,avbase,exp_bust,exp_birth,exp_primary",
        [
            (_T4A_XCITY, _T4A_WIKI, _T4A_AVBASE, 81, "1991-01-01", "wiki"),
            (None, None, _T4A_AVBASE, 84, "1994-04-04", "avbase"),
        ],
        ids=["wiki_over_xcity_over_avbase", "avbase_only"],
    )
    def test_db_row_follows_field_order(self, client, xcity, wiki, avbase,
                                        exp_bust, exp_birth, exp_primary):
        from core.database import ActressRepository

        with patch("core.scrapers.actress.orchestrator._fetch_all_sources",
                   return_value=_t4a_sources(xcity, wiki, avbase)), \
             patch("web.routers.actress.download_actress_photo", return_value=False), \
             patch("web.routers.actress._get_actress_videos", return_value=[]):
            resp = client.post("/api/actresses/favorite", json={"name": self.ACTRESS})

        assert resp.status_code == 200
        stored = ActressRepository().get_by_name(self.ACTRESS)
        assert type(stored.bust) is int
        assert stored.bust == exp_bust
        assert stored.birth == exp_birth
        assert stored.primary_text_source == exp_primary
        assert resp.json()["actress"]["primary_text_source"] == exp_primary


@pytest.mark.usefixtures("_t4a_clear_profile_cache")
class TestAddFavoriteExistingNotRewritten:
    """174-T4a（plan F4）：已收藏的女優再收藏 → 409，DB 值一個字不變、不重抓。"""

    ACTRESS = "順序女優"

    def test_second_favorite_409_leaves_db_row_unchanged(self, client):
        from core.database import ActressRepository
        from core.scrapers.actress import orchestrator

        first = _t4a_sources(
            xcity={"name_ja": self.ACTRESS, "birth": "1990-01-01", "bust": "80cm"},
            wiki={"name_ja": self.ACTRESS, "birth": "1999-11-30", "bust": "86cm",
                  "other_names": ["あかね麗"]},
            avbase={"birth": "1994-04-04", "bust": "84cm"},
        )
        second = _t4a_sources(
            xcity={"name_ja": self.ACTRESS, "birth": "2001-05-05", "bust": "70cm"},
            wiki={"name_ja": self.ACTRESS, "birth": "2000-12-31", "bust": "71cm",
                  "other_names": ["べつ名"]},
            avbase={"birth": "2002-06-06", "bust": "72cm"},
        )

        def _row():
            a = ActressRepository().get_by_name(self.ACTRESS)
            return (a.birth, a.bust, list(a.aliases or []), a.photo_source,
                    a.primary_text_source)

        with patch("core.scrapers.actress.orchestrator._fetch_all_sources",
                   return_value=first), \
             patch("web.routers.actress.download_actress_photo", return_value=False), \
             patch("web.routers.actress._get_actress_videos", return_value=[]):
            resp1 = client.post("/api/actresses/favorite", json={"name": self.ACTRESS})
        assert resp1.status_code == 200
        before = _row()
        assert before == ("1999-11-30", 86, ["あかね麗"], None, "wiki")

        orchestrator._cache.clear()
        with patch("core.scrapers.actress.orchestrator._fetch_all_sources",
                   return_value=second) as mock_fetch, \
             patch("web.routers.actress.download_actress_photo", return_value=False), \
             patch("web.routers.actress._get_actress_videos", return_value=[]):
            resp2 = client.post("/api/actresses/favorite", json={"name": self.ACTRESS})

        assert resp2.status_code == 409
        assert resp2.json()["error"] == "already_exists"
        assert mock_fetch.call_count == 0
        assert _row() == before


# ---------------------------------------------------------------------------
# TASK-174-T4b：別名來源鏈（維基 → avbase）＋別名過濾器 → 別名群組／線上搜尋建議
# ---------------------------------------------------------------------------

_T4B_NEW = "二階堂麗"
_T4B_OLD = "あかね麗"


@pytest.mark.usefixtures("_t4a_clear_profile_cache")
class TestAddFavoriteAliasGroup:
    """174-T4b：收藏後別名群組含另一個名字、不含自己重複與 @ 帳號。

    端點把別名同步包在 try/except（失敗只寫 warning、仍回 200），
    所以必須讀 tmp DB 的別名群組，不能只看 HTTP 200。
    """

    @pytest.mark.parametrize(
        "query,other",
        [(_T4B_NEW, _T4B_OLD)],
        ids=["query_new_name"],
    )
    def test_favorite_writes_other_name_into_alias_group(self, client, query, other):
        from core.database import ActressRepository, AliasRepository

        avbase = {"birth": "1999-11-30",
                  "other_names": [_T4B_NEW, _T4B_OLD, "@Faerina"]}
        with patch("core.scrapers.actress.orchestrator._fetch_all_sources",
                   return_value=_t4a_sources(avbase=avbase)), \
             patch("web.routers.actress.download_actress_photo", return_value=False), \
             patch("web.routers.actress._get_actress_videos", return_value=[]):
            resp = client.post("/api/actresses/favorite", json={"name": query})

        assert resp.status_code == 200
        assert resp.json()["skipped_aliases"] == []
        assert AliasRepository().resolve(query) == {_T4B_NEW, _T4B_OLD}
        assert list(ActressRepository().get_by_name(query).aliases) == [other]

    def test_favorite_alias_only_avbase_still_writes_alias_group(self, client):
        from core.database import ActressRepository, AliasRepository

        avbase = {"other_names": [_T4B_NEW, _T4B_OLD]}
        with patch("core.scrapers.actress.orchestrator._fetch_all_sources",
                   return_value=_t4a_sources(avbase=avbase)), \
             patch("web.routers.actress.download_actress_photo", return_value=False), \
             patch("web.routers.actress._get_actress_videos", return_value=[]):
            resp = client.post("/api/actresses/favorite", json={"name": _T4B_NEW})

        assert resp.status_code == 200
        body = resp.json()
        assert body["skipped_aliases"] == []
        assert body["actress"]["primary_text_source"] is None
        assert AliasRepository().resolve(_T4B_NEW) == {_T4B_NEW, _T4B_OLD}
        assert list(ActressRepository().get_by_name(_T4B_NEW).aliases) == [_T4B_OLD]


@pytest.mark.usefixtures("_t4a_clear_profile_cache")
class TestSearchOnlineAliasChain:
    """174-T4b（F2）：真的 get_actress_profile ＋ 替身五源，打 search-online。"""


    def test_search_online_suggests_avbase_names_without_self_or_accounts(self, client):
        avbase = {"other_names": [_T4B_NEW, "@Faerina", _T4B_OLD]}
        with patch("core.scrapers.actress.orchestrator._fetch_all_sources",
                   return_value=_t4a_sources(avbase=avbase)):
            resp = client.post("/api/actress-aliases/search-online",
                               json={"name": _T4B_NEW})

        assert resp.status_code == 200
        assert resp.json()["suggested_aliases"] == [_T4B_OLD]


class TestAddFavoriteCropAfterAliasSync:
    """TASK-174-T3a 第 2 輪（Codex review P2）：裁封面備援要在別名同步「之後」跑——
    新別名剛寫進 actress_aliases，她的片可能全以舊名登錄。"""

    NEW_NAME = "二階堂麗"
    OLD_NAME = "あかね麗"

    @pytest.fixture(autouse=True)
    def _clear_profile_cache(self):
        from core.scrapers.actress import orchestrator
        orchestrator._cache.clear()
        yield
        orchestrator._cache.clear()

    def _sources(self):
        from core.scrapers.actress.orchestrator import _FetchedSources
        return _FetchedSources({
            "xcity": None,
            "wiki": None,
            "graphis": None,
            "gfriends": None,
            "avbase": {"birth": "1999-11-30", "other_names": [self.OLD_NAME]},
        })

    def _save_old_name_video(self, tmp_path):
        from core.database import VideoRepository, Video

        cover_fs = str(tmp_path / "cover.jpg")
        Path(cover_fs).write_bytes(b"\xff\xd8\xff\xe0fake_cover")
        VideoRepository().upsert(Video(
            path=to_file_uri(str(tmp_path / "video.mp4")),
            title="Old Name Video",
            actresses=[self.OLD_NAME],
            cover_path=to_file_uri(cover_fs),
        ))

    def _post_favorite(self, client, tmp_path):
        gfriends = tmp_path / "gfriends"
        gfriends.mkdir()
        with patch("core.scrapers.actress.orchestrator._fetch_all_sources",
                   return_value=self._sources()), \
             patch("web.routers.actress.crop_video_cover",
                   return_value=b"\xff\xd8\xff\xe0FAKE_LOCAL_CROP") as mock_crop, \
             patch("web.routers.actress.GFRIENDS_DIR", gfriends), \
             patch("core.actress_photo.GFRIENDS_DIR", gfriends):
            resp = client.post("/api/actresses/favorite", json={"name": self.NEW_NAME})
        return resp, mock_crop, gfriends

    def test_new_name_crops_cover_of_old_name_videos(self, client, tmp_path):
        """首次以新名收藏、片全以舊名登錄、無任何雲端照片 → 用舊名的片裁頭像，DB 也記 local_crop"""
        from core.database import ActressRepository

        self._save_old_name_video(tmp_path)
        resp, mock_crop, gfriends = self._post_favorite(client, tmp_path)

        assert resp.status_code == 200
        data = resp.json()
        assert data["skipped_aliases"] == []
        assert data["actress"]["photo_source"] == "local_crop"
        assert data["photo_downloaded"] is True
        assert mock_crop.call_count == 1
        assert len(list(gfriends.glob("*.jpg"))) == 1
        assert ActressRepository().get_by_name(self.NEW_NAME).photo_source == "local_crop"

    def test_rejected_conflict_alias_videos_not_used_for_crop(self, client, tmp_path):
        """舊名已屬於別的女優群組（衝突別名被拒）→ 不拿那些片裁，照片空白、仍 200"""
        from core.database import ActressRepository, AliasRepository

        AliasRepository().sync_from_favorite("他人", [self.OLD_NAME])
        self._save_old_name_video(tmp_path)
        resp, mock_crop, gfriends = self._post_favorite(client, tmp_path)

        assert resp.status_code == 200
        data = resp.json()
        assert data["skipped_aliases"] == [self.OLD_NAME]
        assert data["actress"]["photo_source"] is None
        assert not data["photo_downloaded"]
        assert mock_crop.call_count == 0
        assert ActressRepository().get_by_name(self.NEW_NAME).photo_source is None
