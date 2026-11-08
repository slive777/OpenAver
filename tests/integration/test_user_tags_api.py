"""
test_user_tags_api.py — POST/GET /api/user-tags 端點整合測試

使用 FastAPI TestClient + 真實 SQLite DB（tmp_path）。
TDD-lite：先從邊界條件 E1–E9 提取 RED 測試 → 實作 GREEN。
"""

import os
import sqlite3
import pytest
from unittest.mock import patch

from fastapi.testclient import TestClient
from core.database import init_db
from core.path_utils import to_file_uri


# ── Fixtures ──────────────────────────────────────────────────────────────────

# 使用 to_file_uri() 產生 canonical 形式的測試 key（路徑契約：禁止手刻 file:///）
TEST_FILE_URI = to_file_uri("/test/SONE-205.mp4")
TEST_FILE_URI2 = to_file_uri("/test/ABW-001.mp4")


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


# ── E3: remove 包含不存在的 tag（靜默忽略）───────────────────────────────────


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


# ── E6: NFO 寫入失敗 ──────────────────────────────────────────────────────────

class TestE6NfoWriteFailure:
    """E6: NFO 寫入失敗 → success=True, nfo_updated=False（DB 已更新）"""


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


# ── E8: user_tags 為空，remove 含任意 tag ────────────────────────────────────


# ── E9: GET 查詢不存在的 file_path ────────────────────────────────────────────


# ── Happy Path ────────────────────────────────────────────────────────────────

class TestHappyPath:
    """Happy path：正常操作流程"""


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


# ── E10: _normalize_to_uri canonicalization（P0 修正）──────────────────────────

class TestE10PathCanonicalization:
    """E10: _normalize_to_uri 完整 canonicalization

    P0 修正：前端不再呼叫 JS 路徑轉換，直接傳 file.path 給後端。
    後端 _normalize_to_uri() 透過 uri_to_fs_path → to_file_uri round-trip
    做完整 canonicalization，確保不同形式的同一檔案產生相同 DB key。
    """

    def test_canonicalizes_mnt_uri_to_drive_uri(self, monkeypatch):
        """file:///mnt/c/X 與 file:///C:/X 應該產生相同 canonical key（WSL 路徑）"""
        from web.routers.collection import _normalize_to_uri
        monkeypatch.setattr("core.path_utils.CURRENT_ENV", "wsl")
        canon1 = _normalize_to_uri("file:///mnt/c/test.mp4")
        canon2 = _normalize_to_uri("file:///C:/test.mp4")
        # 兩種輸入應該映射到同一 canonical 形式
        assert canon1 == canon2
        # canonical 形式是 file:///C:/...（Windows drive letter 形式）
        assert canon1 == "file:///C:/test.mp4"


    def test_canonicalizes_windows_native_path(self):
        """native C:\\X path 應 canonical 為 file:///C:/X"""
        from web.routers.collection import _normalize_to_uri
        assert _normalize_to_uri("C:\\Videos\\test.mp4") == "file:///C:/Videos/test.mp4"
        assert _normalize_to_uri("C:/Videos/test.mp4") == "file:///C:/Videos/test.mp4"


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


# ── T4: 唯讀來源自訂標籤寫進輸出夾 NFO（TASK-143-T4）──────────────────────────

_MINIMAL_NFO = b"""<?xml version='1.0' encoding='utf-8'?>
<movie>
  <title>TEST-001</title>
  <num>TEST-001</num>
</movie>
"""


def setup_readonly_user_tags_env(tmp_db, tmp_path, monkeypatch, *,
                                 with_source_nfo=True, with_output_nfo=True,
                                 output_dir_empty=False, extra_output_nfos=0):
    """建唯讀來源 + 可選輸出夾，回傳 (client, src_dir, out_dir, file_uri)。

    **模組層函式，不是測試 class 的方法**（Codex PR #179 P1）：環境準備一旦寫成
    class 的 method，別的測試檔要借用就得把整個 `Test*` class import 過去，於是又得
    想辦法阻止 pytest 重複收集它——而「改那個 class 的 `__test__` 屬性」是**全域改動**：
    一旦兩邊的模組身分合而為一（例如有人補了 `tests/integration/__init__.py`），
    原始檔那幾支測試會整組靜默不被收集。純函式沒有這個攻擊面：名字不以 Test 開頭，
    pytest 根本不會看它。同 `test_readonly_offflavor_e2e.py` 的既有慣例
    （`_make_source_dir` / `_make_config` / `_wire` / `_snapshot` 全是模組層函式）。
    """
    from web.routers import collection as collection_mod
    from web.app import app
    from core.database import Video, VideoRepository

    src_dir = tmp_path / "ro_src"
    src_dir.mkdir()
    mp4 = src_dir / "TEST-001.mp4"
    mp4.write_bytes(b"fake-video")
    if with_source_nfo:
        (src_dir / "TEST-001.nfo").write_bytes(_MINIMAL_NFO)

    out_dir = None
    output_dir_uri = ""
    if not output_dir_empty:
        out_dir = tmp_path / "ro_out" / "TEST-001"
        out_dir.mkdir(parents=True)
        if with_output_nfo:
            (out_dir / "TEST-001.nfo").write_bytes(_MINIMAL_NFO)
        for i in range(extra_output_nfos):
            (out_dir / f"extra-{i}.nfo").write_bytes(_MINIMAL_NFO)
        output_dir_uri = to_file_uri(str(out_dir))

    file_uri = to_file_uri(str(mp4))
    repo = VideoRepository(tmp_db)
    repo.upsert(Video(
        path=file_uri,
        number="TEST-001",
        title="TEST-001",
        output_dir=output_dir_uri,
        user_tags=[],
    ))

    fake_config = {
        "gallery": {
            "directories": [{"path": str(src_dir), "readonly": True, "output_path": ""}],
            "path_mappings": {},
        },
        "scraper": {},
    }
    monkeypatch.setattr(collection_mod, "load_config", lambda: fake_config)
    monkeypatch.setattr("web.routers.collection.get_db_path", lambda: tmp_db)

    return TestClient(app), src_dir, out_dir, file_uri


class TestT4ReadonlyUserTags:
    """TASK-143-T4: 唯讀來源加／刪標籤 → 改寫輸出夾 NFO，來源零寫入。"""


    def test_ac2_1_source_nfo_untouched_output_nfo_gets_tag(
        self, tmp_db, tmp_path, monkeypatch
    ):
        """AC2-1: 來源有 NFO → 來源雜湊不變；輸出夾 NFO 帶新標籤。"""
        from test_readonly_offflavor_e2e import _snapshot

        client, src_dir, out_dir, file_uri = setup_readonly_user_tags_env(
            tmp_db, tmp_path, monkeypatch,
            with_source_nfo=True, with_output_nfo=True,
        )

        before = _snapshot(src_dir)
        resp = client.post("/api/user-tags", json={
            "file_path": file_uri,
            "add": ["T4TAG"],
        })
        after = _snapshot(src_dir)

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "T4TAG" in data["user_tags"]
        assert data["nfo_updated"] is True
        assert data["readonly_no_output"] is False
        assert after == before, "來源目錄被寫入（零寫入承諾破掉）"

        out_nfo = (out_dir / "TEST-001.nfo").read_text(encoding="utf-8")
        assert "T4TAG" in out_nfo
        assert "<user_tag>T4TAG</user_tag>" in out_nfo


    def test_ac2_malformed_output_nfo_also_reports_no_output(
        self, tmp_db, tmp_path, monkeypatch
    ):
        """輸出夾恰有一份 NFO，但它壞掉（或 glob 之後消失）→ 一樣要回報未更新。

        使用者流程：對唯讀來源的片加標籤 → 輸出夾那份 NFO 是壞的（手動編輯過、
        寫到一半斷電、被外部工具改壞）→ `update_nfo_user_tags` **catch 後回 False
        不是 raise** ⇒ 舊寫法三個分支一個都沒中 ⇒ 畫面一則提示都沒有，而標籤其實
        只進了 DB。這是 Codex PR #179 round 2 的 P3，也是「列舉失敗分支」這個形狀
        自己生出來的第四個洞——現在旗標改成從 `nfo_updated` 導出。
        """
        client, _src_dir, out_dir, file_uri = setup_readonly_user_tags_env(
            tmp_db, tmp_path, monkeypatch,
            with_source_nfo=False, with_output_nfo=True,
        )
        (out_dir / "TEST-001.nfo").write_bytes(b"<movie><unclosed>")  # 壞掉的 XML

        resp = client.post("/api/user-tags", json={
            "file_path": file_uri,
            "add": ["BADNFO"],
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True          # 標籤仍進 DB
        assert data["nfo_updated"] is False
        assert data["readonly_no_output"] is True

    def test_normal_video_never_reports_readonly_no_output(
        self, tmp_db, tmp_path, monkeypatch
    ):
        """反向鎖：非唯讀的片即使 NFO 寫失敗，也不得回 readonly_no_output=True。

        導出式旗標最容易壞的方向就是把 `is_readonly` 這一半弄丟——那會讓一般片
        每次 NFO 沒寫成都跳一則「媒體伺服器讀的那份沒更新」的唯讀專用提示。
        """
        with patch("web.routers.collection.update_nfo_user_tags", return_value=False):
            monkeypatch.setattr("web.routers.collection.get_db_path", lambda: tmp_db)
            from web.app import app
            resp = TestClient(app).post("/api/user-tags", json={
                "file_path": TEST_FILE_URI,
                "add": ["NORMAL"],
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["nfo_updated"] is False
        assert data["readonly_no_output"] is False


class TestT10bNfoWriteBlocked:
    """非唯讀 sidecar 寫入失敗提示，及唯讀來源反向鎖。"""

    @pytest.mark.skipif(os.name != "posix" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                        reason="chmod 0444 needs POSIX non-root DAC enforcement")
    def test_nfo_write_blocked_true_when_sidecar_readonly_write_fails(
        self, client, tmp_db, tmp_path
    ):
        from core.database import VideoRepository

        video_path = tmp_path / "T10B-001.mp4"
        video_path.write_bytes(b"fake-video")
        nfo_path = video_path.with_suffix(".nfo")
        nfo_path.write_bytes(_MINIMAL_NFO)
        nfo_path.chmod(0o444)
        file_uri = to_file_uri(str(video_path))

        resp = client.post("/api/user-tags", json={"file_path": file_uri, "add": ["T10B"]})

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["nfo_write_blocked"] is True
        assert data["nfo_updated"] is False
        assert data["readonly_no_output"] is False
        assert "T10B" in VideoRepository(tmp_db).get_by_path(file_uri).user_tags

    def test_nfo_write_blocked_false_when_sidecar_absent(self, client, tmp_path):
        video_path = tmp_path / "T10B-002.mp4"
        video_path.write_bytes(b"fake-video")

        resp = client.post("/api/user-tags", json={
            "file_path": to_file_uri(str(video_path)), "add": ["T10B"],
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["nfo_updated"] is False
        assert data["nfo_write_blocked"] is False
        assert data["readonly_no_output"] is False

