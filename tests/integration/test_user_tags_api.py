"""
test_user_tags_api.py — POST/GET /api/user-tags 端點整合測試

使用 FastAPI TestClient + 真實 SQLite DB（tmp_path）。
TDD-lite：先從邊界條件 E1–E9 提取 RED 測試 → 實作 GREEN。
"""

import sqlite3
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient
from core.database import init_db
from core.path_utils import to_file_uri


# ── Fixtures ──────────────────────────────────────────────────────────────────

# 使用 to_file_uri() 產生 canonical 形式的測試 key（路徑契約：禁止手刻 file:///）
TEST_FILE_URI = to_file_uri("/test/SONE-205.mp4")
TEST_FILE_URI2 = to_file_uri("/test/ABW-001.mp4")
NONEXISTENT_URI = to_file_uri("/test/NONEXISTENT.mp4")


@pytest.fixture
def tmp_db(tmp_path):
    """建立臨時測試資料庫，插入少量測試資料"""
    db_path = tmp_path / "test_user_tags.db"
    init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")

    # 插入測試影片（含 user_tags）
    conn.execute("""
        INSERT INTO videos (path, number, title, actresses, maker, tags, user_tags, duration, size_bytes)
        VALUES
        (?, 'SONE-205', 'Test Title 1', '["明日花キララ"]', 'Sony', '["巨乳","中出"]', '["★4"]', 7200, 4000000000),
        (?, 'ABW-001', 'Test Title 2', '["葵つかさ"]', 'ABC', '["女教師"]', '[]', 6000, 3500000000)
    """, (TEST_FILE_URI, TEST_FILE_URI2))

    conn.commit()
    conn.close()

    return db_path


@pytest.fixture
def client(tmp_db, monkeypatch):
    """TestClient，monkeypatch get_db_path 指向 tmp DB"""
    monkeypatch.setattr("web.routers.collection.get_db_path", lambda: tmp_db)

    from web.app import app
    return TestClient(app)


# ── E1: file_path 不在 DB ─────────────────────────────────────────────────────

class TestE1FilePathNotInDB:
    """E1: file_path 不在 DB → success=false, error 存在"""

    def test_post_nonexistent_returns_success_false(self, client):
        """POST 不存在的 file_path → success=False，包含 error"""
        resp = client.post("/api/user-tags", json={
            "file_path": NONEXISTENT_URI,
            "add": ["★5"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "error" in data
        assert data["error"]


# ── E1b: file 存在於 FS 但不在 DB → 自動建立 stub ──────────────────────────────


class TestE1bAutoCreateStub:
    """E1b: 檔案存在於 FS 但不在 DB → 自動建立 stub 紀錄並寫入 user_tags

    用於 Search 拖入但未掃描的檔案場景。
    """

    def test_auto_create_stub_on_add(self, tmp_db, tmp_path, monkeypatch):
        """檔案在 FS 但不在 DB → 自動建 stub + add 成功"""
        monkeypatch.setattr("web.routers.collection.get_db_path", lambda: tmp_db)

        # 建一個真實檔案，但不在 DB
        real_file = tmp_path / "STUB-001.mp4"
        real_file.write_bytes(b"fake video")
        file_uri = to_file_uri(str(real_file))

        from web.app import app
        client = TestClient(app)

        with patch("web.routers.collection.update_nfo_user_tags", return_value=True):
            resp = client.post("/api/user-tags", json={
                "file_path": file_uri,
                "add": ["★5"],
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "★5" in data["user_tags"]

        # 確認 DB 已建立 stub 紀錄
        from core.database import VideoRepository
        repo = VideoRepository(tmp_db)
        video = repo.get_by_path(file_uri)
        assert video is not None
        assert "★5" in video.user_tags
        # 從檔名解析 number
        assert video.number == "STUB-001"

    def test_no_stub_when_file_missing(self, client, tmp_path, monkeypatch):
        """檔案在 FS 也不存在 → 不建 stub，回 success=false"""
        ghost_uri = to_file_uri(str(tmp_path / "GHOST.mp4"))
        resp = client.post("/api/user-tags", json={
            "file_path": ghost_uri,
            "add": ["★5"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "檔案不存在" in data["error"]


# ── E2: add 包含已存在的 tag（idempotent）─────────────────────────────────────

class TestE2AddExistingTag:
    """E2: add 包含已存在的 tag → 去重，不重複加入"""

    def test_add_existing_tag_no_duplicate(self, client):
        """add 包含已存在的 '★4' → 最終 user_tags 只有一個 '★4'"""
        resp = client.post("/api/user-tags", json={
            "file_path": TEST_FILE_URI,
            "add": ["★4"],  # 已存在
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        tags = data["user_tags"]
        assert tags.count("★4") == 1

    def test_add_existing_tag_idempotent(self, client):
        """多次 add 同一 tag → 結果相同，不累積"""
        # 第一次
        resp1 = client.post("/api/user-tags", json={
            "file_path": TEST_FILE_URI,
            "add": ["新標"],
        })
        tags1 = resp1.json()["user_tags"]

        # 第二次（重複 add）
        resp2 = client.post("/api/user-tags", json={
            "file_path": TEST_FILE_URI,
            "add": ["新標"],
        })
        tags2 = resp2.json()["user_tags"]

        assert tags1.count("新標") == 1
        assert tags2.count("新標") == 1
        assert tags1 == tags2


# ── E3: remove 包含不存在的 tag（靜默忽略）───────────────────────────────────

class TestE3RemoveNonexistentTag:
    """E3: remove 包含不存在的 tag → 靜默忽略，不報錯"""

    def test_remove_nonexistent_tag_no_error(self, client):
        """remove 不存在的 tag → success=True，不報錯；原有 tags 不受影響"""
        resp = client.post("/api/user-tags", json={
            "file_path": TEST_FILE_URI,
            "remove": ["不存在的標籤"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "★4" in data["user_tags"]  # 原有 ★4 仍保留


# ── E4: add 和 remove 同時含相同 tag（remove 優先）───────────────────────────

class TestE4AddRemoveConflict:
    """E4: add 和 remove 同時包含相同 tag → remove 優先"""

    def test_remove_wins_over_add(self, client):
        """add=['足'] 且 remove=['足'] → 最終不含 '足'"""
        resp = client.post("/api/user-tags", json={
            "file_path": TEST_FILE_URI,
            "add": ["足"],
            "remove": ["足"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "足" not in data["user_tags"]


# ── E5: add=[], remove=[]（純查詢式 POST）────────────────────────────────────

class TestE5EmptyAddRemove:
    """E5: add=[], remove=[] → DB 更新、NFO 重寫仍執行（user_tags 不變）"""

    def test_empty_add_remove_success(self, client):
        """add=[], remove=[] → success=True，user_tags 不變"""
        resp = client.post("/api/user-tags", json={
            "file_path": TEST_FILE_URI,
            "add": [],
            "remove": [],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["user_tags"] == ["★4"]  # 不變


# ── E6: NFO 寫入失敗 ──────────────────────────────────────────────────────────

class TestE6NfoWriteFailure:
    """E6: NFO 寫入失敗 → success=True, nfo_updated=False（DB 已更新）"""

    def test_nfo_write_fail_exception(self, client, monkeypatch):
        """mock update_nfo_user_tags 拋出 OSError → success=True, nfo_updated=False"""
        with patch("web.routers.collection.update_nfo_user_tags", side_effect=OSError("Permission denied")):
            resp = client.post("/api/user-tags", json={
                "file_path": TEST_FILE_URI,
                "add": ["★5"],
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["nfo_updated"] is False

    def test_nfo_write_fail_returns_false(self, client, monkeypatch):
        """mock update_nfo_user_tags 回傳 False（靜默失敗）→ success=True, nfo_updated=False"""
        with patch("web.routers.collection.update_nfo_user_tags", return_value=False):
            resp = client.post("/api/user-tags", json={
                "file_path": TEST_FILE_URI,
                "add": ["★5"],
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["nfo_updated"] is False

    def test_nfo_write_fail_db_still_updated(self, tmp_db, monkeypatch):
        """mock update_nfo_user_tags 拋出 OSError → DB 仍然更新"""
        monkeypatch.setattr("web.routers.collection.get_db_path", lambda: tmp_db)

        with patch("web.routers.collection.update_nfo_user_tags", side_effect=OSError("Permission denied")):
            from web.app import app
            test_client = TestClient(app)
            resp = test_client.post("/api/user-tags", json={
                "file_path": TEST_FILE_URI,
                "add": ["★5"],
            })

        assert resp.json()["success"] is True

        # 確認 DB 已更新
        from core.database import VideoRepository
        repo = VideoRepository(tmp_db)
        video = repo.get_by_path(TEST_FILE_URI)
        assert "★5" in video.user_tags


# ── E7: add 含重複 tag ─────────────────────────────────────────────────────────

class TestE7AddDuplicatesInRequest:
    """E7: add 含重複 tag（["★5", "★5"]）→ 去重，結果只有一個 "★5"""""

    def test_add_duplicate_tags_in_request(self, client):
        """add=['★5', '★5'] → 結果只有一個 '★5'"""
        resp = client.post("/api/user-tags", json={
            "file_path": TEST_FILE_URI2,  # ABW-001，初始 user_tags=[]
            "add": ["★5", "★5"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["user_tags"].count("★5") == 1


# ── E8: user_tags 為空，remove 含任意 tag ────────────────────────────────────

class TestE8EmptyTagsRemove:
    """E8: user_tags 為空 list，remove 含任意 tag → 回傳空 list，不報錯"""

    def test_empty_tags_remove_returns_empty(self, client):
        """ABW-001 user_tags=[], remove=['任意'] → [] 不報錯"""
        resp = client.post("/api/user-tags", json={
            "file_path": TEST_FILE_URI2,  # 初始 user_tags=[]
            "remove": ["任意標籤"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["user_tags"] == []


# ── E9: GET 查詢不存在的 file_path ────────────────────────────────────────────

class TestE9GetNonexistent:
    """E9: GET 查詢不存在的 file_path → 200 + {user_tags: [], file_path: ...}"""

    def test_get_nonexistent_returns_empty_list(self, client):
        """GET 不存在的 file_path → 200，user_tags=[]"""
        resp = client.get("/api/user-tags", params={"file_path": NONEXISTENT_URI})
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_tags"] == []
        assert data["file_path"] == NONEXISTENT_URI


# ── Happy Path ────────────────────────────────────────────────────────────────

class TestHappyPath:
    """Happy path：正常操作流程"""

    def test_post_add_new_tag(self, client):
        """add 新 tag → success=True，tag 在 user_tags"""
        resp = client.post("/api/user-tags", json={
            "file_path": TEST_FILE_URI2,
            "add": ["★5"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "★5" in data["user_tags"]
        assert "nfo_updated" in data

    def test_post_remove_existing_tag(self, client):
        """remove 已存在的 tag → tag 不在 user_tags"""
        resp = client.post("/api/user-tags", json={
            "file_path": TEST_FILE_URI,
            "remove": ["★4"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "★4" not in data["user_tags"]

    def test_get_existing_file_path(self, client):
        """GET 已存在的 file_path → 回傳現有 user_tags"""
        resp = client.get("/api/user-tags", params={"file_path": TEST_FILE_URI})
        assert resp.status_code == 200
        data = resp.json()
        assert data["file_path"] == TEST_FILE_URI
        assert "★4" in data["user_tags"]

    def test_post_add_and_remove_combined(self, client):
        """同時 add 新 tag 和 remove 舊 tag"""
        # 先確認初始狀態（★4 存在）
        resp = client.post("/api/user-tags", json={
            "file_path": TEST_FILE_URI,
            "add": ["足"],
            "remove": ["★4"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "足" in data["user_tags"]
        assert "★4" not in data["user_tags"]

    def test_post_db_persists(self, tmp_db, monkeypatch):
        """POST 後再 GET → DB 已持久化"""
        monkeypatch.setattr("web.routers.collection.get_db_path", lambda: tmp_db)

        from web.app import app
        test_client = TestClient(app)

        # POST 添加 tag
        test_client.post("/api/user-tags", json={
            "file_path": TEST_FILE_URI2,
            "add": ["持久化測試"],
        })

        # GET 查詢
        resp = test_client.get("/api/user-tags", params={"file_path": TEST_FILE_URI2})
        data = resp.json()
        assert "持久化測試" in data["user_tags"]

    def test_post_missing_file_path_returns_422(self, client):
        """file_path 缺失 → Pydantic 422"""
        resp = client.post("/api/user-tags", json={
            "add": ["★5"],
        })
        assert resp.status_code == 422

    def test_get_missing_file_path_returns_422(self, client):
        """GET 缺少 file_path → 422"""
        resp = client.get("/api/user-tags")
        assert resp.status_code == 422


# ── E10: _normalize_to_uri canonicalization（P0 修正）──────────────────────────

class TestE10PathCanonicalization:
    """E10: _normalize_to_uri 完整 canonicalization

    P0 修正：前端不再呼叫 JS 路徑轉換，直接傳 file.path 給後端。
    後端 _normalize_to_uri() 透過 uri_to_fs_path → to_file_uri round-trip
    做完整 canonicalization，確保不同形式的同一檔案產生相同 DB key。
    """

    def test_canonicalizes_mnt_uri_to_drive_uri(self):
        """file:///mnt/c/X 與 file:///C:/X 應該產生相同 canonical key（WSL 路徑）"""
        from web.routers.collection import _normalize_to_uri
        canon1 = _normalize_to_uri("file:///mnt/c/test.mp4")
        canon2 = _normalize_to_uri("file:///C:/test.mp4")
        # 兩種輸入應該映射到同一 canonical 形式
        assert canon1 == canon2
        # canonical 形式是 file:///C:/...（Windows drive letter 形式）
        assert canon1 == "file:///C:/test.mp4"

    def test_canonicalizes_native_mnt_path(self):
        """native /mnt/c/X path 應 canonical 為 file:///C:/X"""
        from web.routers.collection import _normalize_to_uri
        assert _normalize_to_uri("/mnt/c/test.mp4") == "file:///C:/test.mp4"

    def test_canonicalizes_windows_native_path(self):
        """native C:\\X path 應 canonical 為 file:///C:/X"""
        from web.routers.collection import _normalize_to_uri
        assert _normalize_to_uri("C:\\Videos\\test.mp4") == "file:///C:/Videos/test.mp4"
        assert _normalize_to_uri("C:/Videos/test.mp4") == "file:///C:/Videos/test.mp4"

    def test_idempotent_for_canonical_uri(self):
        """canonical 形式的 file:///C:/X 應冪等"""
        from web.routers.collection import _normalize_to_uri
        assert _normalize_to_uri("file:///C:/test.mp4") == "file:///C:/test.mp4"

    def test_normalize_uses_gallery_path_mappings(self, monkeypatch):
        """_normalize_to_uri 會從 gallery config 取出 path_mappings 並傳給 to_file_uri。

        WSL 環境下，DB 通常存 UNC/Windows 形式的 URI（scanner.py 也用 path_mappings）；
        若用戶傳的是本地 mount 路徑（例如 /home/user/nas/...），必須透過 path_mappings
        映射成同一個 canonical key，否則同一個檔案會被當成不同 DB 記錄。
        """
        from web.routers import collection as collection_mod

        # Mock config + 強制 WSL env（path_mappings 只在 WSL 生效）
        fake_config = {
            "gallery": {
                "path_mappings": {"/home/user/nas": "//NAS-SERVER/share"}
            }
        }
        monkeypatch.setattr(collection_mod, "load_config", lambda: fake_config)
        monkeypatch.setattr("core.path_utils.CURRENT_ENV", "wsl")
        monkeypatch.setattr(collection_mod, "CURRENT_ENV", "wsl")

        # 本地 mount 路徑應 canonical 為 UNC URI
        # canonical UNC 形式：to_file_uri 對 //X/share/... 回傳 file:///{//X/share/...}
        # = file://///X/share/... （5 slashes，與 scanner.py 寫入 DB 的形式一致）
        result = collection_mod._normalize_to_uri("/home/user/nas/foo.mp4")
        assert result == "file://///NAS-SERVER/share/foo.mp4", \
            f"path_mappings 未被套用，got: {result}"

        # round-trip：用 canonical UNC URI 再 normalize 一次應冪等
        round_trip = collection_mod._normalize_to_uri(result)
        assert round_trip == result, f"UNC URI 不冪等，got: {round_trip}"

    def test_resolve_user_tag_paths_native_wsl_mount(self, monkeypatch):
        """native /home/user/nas/... → canonical=UNC URI, local_fs=原 mount 路徑"""
        from web.routers import collection as collection_mod

        fake_config = {"gallery": {"path_mappings": {"/home/user/nas": "//NAS-SERVER/share"}}}
        monkeypatch.setattr(collection_mod, "load_config", lambda: fake_config)
        monkeypatch.setattr("core.path_utils.CURRENT_ENV", "wsl")
        monkeypatch.setattr(collection_mod, "CURRENT_ENV", "wsl")

        canonical, local_fs = collection_mod._resolve_user_tag_paths("/home/user/nas/foo.mp4")
        # DB key 用 forward map → UNC URI
        assert canonical == "file://///NAS-SERVER/share/foo.mp4"
        # FS 操作用原 mount path（直接可開）
        assert local_fs == "/home/user/nas/foo.mp4"

    def test_resolve_user_tag_paths_uri_reverse_maps_unc(self, monkeypatch):
        """canonical UNC URI 輸入 → canonical 不變，local_fs 反向映射為 mount 路徑"""
        from web.routers import collection as collection_mod

        fake_config = {"gallery": {"path_mappings": {"/home/user/nas": "//NAS-SERVER/share"}}}
        monkeypatch.setattr(collection_mod, "load_config", lambda: fake_config)
        monkeypatch.setattr("core.path_utils.CURRENT_ENV", "wsl")
        monkeypatch.setattr(collection_mod, "CURRENT_ENV", "wsl")

        # Showcase 從 DB 拿到的 canonical UNC URI 場景
        canonical, local_fs = collection_mod._resolve_user_tag_paths(
            "file://///NAS-SERVER/share/foo.mp4"
        )
        assert canonical == "file://///NAS-SERVER/share/foo.mp4"
        # 關鍵：FS 操作要用 reverse-mapped 的 mount path，否則 WSL 開不到檔
        assert local_fs == "/home/user/nas/foo.mp4", \
            f"reverse map 失敗，local_fs={local_fs}"

    def test_resolve_user_tag_paths_no_mappings_passthrough(self, monkeypatch):
        """無 path_mappings → local_fs == fs_normalized（不嘗試 reverse map）"""
        from web.routers import collection as collection_mod

        fake_config = {"gallery": {}}
        monkeypatch.setattr(collection_mod, "load_config", lambda: fake_config)

        canonical, local_fs = collection_mod._resolve_user_tag_paths("/test/foo.mp4")
        # 無 mapping → fallback 到通用 file:/// 形式
        assert canonical.startswith("file:///")
        assert local_fs == "/test/foo.mp4"

    def test_resolve_user_tag_paths_uri_reverse_backslash_unc(self, monkeypatch):
        """backslash UNC 形式的 fs_normalized → 反向映射同樣命中，local_fs 為 mount 路徑。

        mock uri_to_fs_path 回傳 backslash UNC，驗證 reverse_path_mapping 能處理 \\ 形式。
        """
        from web.routers import collection as collection_mod

        fake_config = {"gallery": {"path_mappings": {"/home/user/nas": "//NAS-SERVER/share"}}}
        monkeypatch.setattr(collection_mod, "load_config", lambda: fake_config)
        monkeypatch.setattr("core.path_utils.CURRENT_ENV", "wsl")
        monkeypatch.setattr(collection_mod, "CURRENT_ENV", "wsl")
        # 強制 uri_to_fs_path 回傳 backslash UNC（模擬 Windows-style normalize 結果）
        monkeypatch.setattr(
            collection_mod, "uri_to_fs_path",
            lambda _: "\\\\NAS-SERVER\\share\\foo.mp4"
        )

        canonical, local_fs = collection_mod._resolve_user_tag_paths(
            "file://///NAS-SERVER/share/foo.mp4"
        )
        # canonical 由 to_file_uri 決定（path_mappings forward map）
        assert canonical == "file://///NAS-SERVER/share/foo.mp4"
        # local_fs 應由 backslash UNC 反向映射到 mount 路徑
        assert local_fs == "/home/user/nas/foo.mp4", \
            f"backslash UNC reverse map 失敗，local_fs={local_fs}"

    def test_resolve_user_tag_paths_uri_no_hit_fallback(self, monkeypatch):
        """URI 輸入但 mapping 不涵蓋該路徑 → local_fs fallback 為 fs_normalized（無錯誤）"""
        from web.routers import collection as collection_mod

        # mapping 只涵蓋 NAS-SERVER，不涵蓋 OTHER-NAS
        fake_config = {"gallery": {"path_mappings": {"/home/user/nas": "//NAS-SERVER/share"}}}
        monkeypatch.setattr(collection_mod, "load_config", lambda: fake_config)
        monkeypatch.setattr("core.path_utils.CURRENT_ENV", "wsl")
        monkeypatch.setattr(collection_mod, "CURRENT_ENV", "wsl")

        canonical, local_fs = collection_mod._resolve_user_tag_paths(
            "file://///OTHER-NAS/share/video.mp4"
        )
        assert canonical.startswith("file:///")
        # 無命中 → fallback 到 fs_normalized（//OTHER-NAS/share/video.mp4），不為空
        assert local_fs != ""
        assert local_fs == "//OTHER-NAS/share/video.mp4", \
            f"no-hit fallback 不符預期，local_fs={local_fs}"

    def test_resolve_user_tag_paths_empty_mappings_no_error(self, monkeypatch):
        """path_mappings 為 empty dict → 不報錯，canonical 為 file:/// 形式"""
        from web.routers import collection as collection_mod

        fake_config = {"gallery": {"path_mappings": {}}}
        monkeypatch.setattr(collection_mod, "load_config", lambda: fake_config)

        # empty mappings 不需要 WSL patch（if block 的 `path_mappings` 條件為 falsy）
        canonical, local_fs = collection_mod._resolve_user_tag_paths("file:///C:/Videos/foo.mp4")
        # 不應拋例外，canonical 應為合法 file:/// URI
        assert canonical.startswith("file:///")
        # local_fs 為 fs_normalized（無 reverse map）
        assert local_fs != ""

    def test_resolve_user_tag_paths_post_api_unc_forward(self, monkeypatch, tmp_db):
        """POST /api/user-tags 傳 UNC URI → API 層不 500（reverse mapping 路徑不爆炸）"""
        from web.routers import collection as collection_mod
        from web.app import app
        from fastapi.testclient import TestClient

        fake_config = {"gallery": {"path_mappings": {"/home/user/nas": "//NAS-SERVER/share"}}}
        monkeypatch.setattr(collection_mod, "load_config", lambda: fake_config)
        monkeypatch.setattr("core.path_utils.CURRENT_ENV", "wsl")
        monkeypatch.setattr(collection_mod, "CURRENT_ENV", "wsl")
        monkeypatch.setattr("web.routers.collection.get_db_path", lambda: tmp_db)

        client = TestClient(app)
        resp = client.post("/api/user-tags", json={
            "file_path": "file://///NAS-SERVER/share/foo.mp4",
            "add": ["★5"],
        })
        # 檔案不存在 → 可能 4xx（E1 auto-stub or 404），但不應 500（內部錯誤）
        assert resp.status_code != 500, \
            f"UNC URI 導致 API 500，response={resp.text}"
