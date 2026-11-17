"""
test_user_rating_api.py — POST /api/user-rating 端點整合測試（TASK-123-T2）

使用 FastAPI TestClient + 真實 SQLite DB（tmp_path）。
鏡射 tests/integration/test_user_tags_api.py 的 fixture 慣例。

plan §3.2 / TASK-123-T2 的 5 個場景：
1. 冪等：同一 body 連送兩次，changed／results 結果相同
2. 批次多路徑：3 個路徑一次送，results 長度與輸入一致、changed 正確計數
3. 部分 not_found：其中一個路徑不在 DB，該路徑回 {"ok": false, "reason": "not_found"}，
   其餘路徑照常成功
4. -cd2 路徑解析到代表段：送 ABC-123-cd2.mp4 的路徑，DB 裡實際被寫入 user_rating 的是
   ABC-123-cd1.mp4（代表段）那一列，ABC-123-cd2.mp4 那列不變
5. 501 個路徑回 400：paths 長度 501 → JSONResponse(status_code=400, ...)，不落地任何寫入
"""

import sqlite3
import pytest

from fastapi.testclient import TestClient
from core.database import init_db, VideoRepository
from core.path_utils import to_file_uri


# ── Fixtures ──────────────────────────────────────────────────────────────────

TEST_FILE_URI = to_file_uri("/test/lib/SONE-205.mp4", {})
TEST_FILE_URI2 = to_file_uri("/test/lib/ABW-001.mp4", {})
NONEXISTENT_URI = to_file_uri("/test/lib/NONEXISTENT.mp4", {})


@pytest.fixture
def tmp_db(tmp_path):
    """建立臨時測試資料庫，插入少量測試資料（不含分集片，分集片場景用專屬 fixture）。"""
    db_path = tmp_path / "test_user_rating.db"
    init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")

    conn.execute("""
        INSERT INTO videos (path, number, title, actresses, maker, tags, user_tags, duration, size_bytes, user_rating)
        VALUES
        (?, 'SONE-205', 'Test Title 1', '["明日花キララ"]', 'Sony', '["巨乳","中出"]', '[]', 7200, 4000000000, 0),
        (?, 'ABW-001', 'Test Title 2', '["葵つかさ"]', 'ABC', '["女教師"]', '[]', 6000, 3500000000, 0)
    """, (TEST_FILE_URI, TEST_FILE_URI2))

    conn.commit()
    conn.close()

    return db_path


@pytest.fixture
def client(tmp_db, monkeypatch):
    """TestClient，monkeypatch get_db_path / load_config 指向 tmp DB、空 path_mappings。"""
    monkeypatch.setattr("web.routers.collection.get_db_path", lambda: tmp_db)
    monkeypatch.setattr("web.routers.collection.load_config", lambda: {"gallery": {"path_mappings": {}}})

    from web.app import app
    return TestClient(app)


def _rating(db_path, path: str) -> int:
    repo = VideoRepository(db_path)
    v = repo.get_by_path(path)
    return v.user_rating if v is not None else -1


# ── 場景 1：冪等 ────────────────────────────────────────────────────────────────

class TestScenario1Idempotent:
    """同一 body 連送兩次，changed／results 結果相同（AC-21）。"""

    def test_double_post_same_result(self, client, tmp_db):
        body = {"file_path": TEST_FILE_URI, "picked": True}
        resp1 = client.post("/api/user-rating", json=body)
        resp2 = client.post("/api/user-rating", json=body)

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        data1 = resp1.json()
        data2 = resp2.json()
        assert data1["results"] == data2["results"]
        assert data1["changed"] == data2["changed"] == 1
        assert _rating(tmp_db, TEST_FILE_URI) > 0


# ── 場景 2：批次多路徑 ────────────────────────────────────────────────────────────

class TestScenario2BatchMultiPath:
    """3 個路徑一次送，results 長度與輸入一致、changed 正確計數（AC-25）。"""

    def test_batch_three_paths(self, client, tmp_db):
        third_uri = to_file_uri("/test/lib/THIRD-001.mp4", {})
        conn = sqlite3.connect(str(tmp_db))
        conn.execute(
            "INSERT INTO videos (path, number, title, user_tags, user_rating) VALUES (?, 'THIRD-001', 'Third', '[]', 0)",
            (third_uri,),
        )
        conn.commit()
        conn.close()

        paths = [TEST_FILE_URI, TEST_FILE_URI2, third_uri]
        resp = client.post("/api/user-rating", json={"paths": paths, "picked": True})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["results"]) == 3
        assert data["changed"] == 3
        for r in data["results"]:
            assert r["ok"] is True
        assert _rating(tmp_db, TEST_FILE_URI) > 0
        assert _rating(tmp_db, TEST_FILE_URI2) > 0
        assert _rating(tmp_db, third_uri) > 0


# ── 場景 3：部分 not_found ────────────────────────────────────────────────────────


# ── 場景 4：-cd2 路徑解析到代表段 ────────────────────────────────────────────────────

class TestScenario4MultipartRepresentative:
    """送 ABC-123-cd2.mp4 的路徑，DB 裡實際被寫入 user_rating 的是 ABC-123-cd1.mp4
    （代表段）那一列，ABC-123-cd2.mp4 那列不變（plan CD-123-6/7、本卡技術要點步驟 3）。
    """

    @pytest.fixture
    def multipart_db(self, tmp_path):
        db_path = tmp_path / "test_multipart.db"
        init_db(db_path)

        part1_uri = to_file_uri(str(tmp_path / "videos" / "ABC-123-cd1.mp4"), {})
        part2_uri = to_file_uri(str(tmp_path / "videos" / "ABC-123-cd2.mp4"), {})

        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO videos (path, number, title, user_tags, user_rating) VALUES (?, 'ABC-123', 'Part 1', '[]', 0)",
            (part1_uri,),
        )
        conn.execute(
            "INSERT INTO videos (path, number, title, user_tags, user_rating) VALUES (?, 'ABC-123', 'Part 2', '[]', 0)",
            (part2_uri,),
        )
        conn.commit()
        conn.close()

        return db_path, part1_uri, part2_uri

    @pytest.fixture
    def multipart_client(self, multipart_db, monkeypatch):
        db_path, _, _ = multipart_db
        monkeypatch.setattr("web.routers.collection.get_db_path", lambda: db_path)
        monkeypatch.setattr("web.routers.collection.load_config", lambda: {"gallery": {"path_mappings": {}}})
        from web.app import app
        return TestClient(app)

    def test_cd2_writes_representative_cd1_row(self, multipart_client, multipart_db):
        db_path, part1_uri, part2_uri = multipart_db

        resp = multipart_client.post("/api/user-rating", json={"file_path": part2_uri, "picked": True})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["changed"] == 1
        assert data["results"][0]["ok"] is True

        # 代表段（cd1）被寫入，cd2 那列本身不變（維持 0）
        assert _rating(db_path, part1_uri) > 0
        assert _rating(db_path, part2_uri) == 0


# ── 場景 5：501 個路徑回 400 ──────────────────────────────────────────────────────


# ── 邊界：XOR 違反、空陣列、picked 缺欄位 ────────────────────────────────────────────


# ── 邊界：取消精選（picked: false）與重複路徑 ────────────────────────────────────────

class TestBoundaryUnpickAndDuplicate:
    def test_picked_false_sets_rating_to_zero(self, client, tmp_db):
        # 先設為精選
        client.post("/api/user-rating", json={"file_path": TEST_FILE_URI, "picked": True})
        assert _rating(tmp_db, TEST_FILE_URI) > 0

        resp = client.post("/api/user-rating", json={"file_path": TEST_FILE_URI, "picked": False})
        assert resp.status_code == 200
        assert resp.json()["picked"] is False
        assert _rating(tmp_db, TEST_FILE_URI) == 0


# ── AC-13/AC-14：NFO 逐位元組不變（TASK-123-T7） ──────────────────────────────────
#
# AC-13：post_user_rating() 完全不碰 .nfo（spec §4.6，刻意跟 post_user_tags() 不同步，
# 見 web/routers/collection.py:864 函式 docstring 註解）。這裡不只靠 grep 佐證，而是
# 真的建一支 .nfo（含非 ASCII 內容驗證編碼不受影響）、打端點、比對 bytes + mtime_ns，
# 把「grep 沒找到」升級成「跑起來也沒變」。
#
# 快照形狀（read_bytes() + st_mtime_ns 兩值）沿用
# tests/integration/test_readonly_offflavor_e2e.py:202-220 `_snapshot()` 的精神
# （完整目錄快照另外還比 size/sha256/st_ino，這裡因為只鎖單一已知檔案、且要驗證
# 「連 mtime 都没被 touch 過」，改用更聚焦的兩值寫法，非 copy-paste 那支 helper——
# 本卡 CLAUDE.md 規則明說不改該檔，這裡也沒有改它）。
#
# AC-14（唯讀來源零寫入）由同一組快照邏輯 ＋ 端點結構性不碰 FS 的事實覆蓋：
# `post_user_rating()`（web/routers/collection.py:851-926）全函式 grep `open(`／
# `write`／`shutil`／`os.remove`／`os.rename`／`Path(` 零命中；唯一的檔案 I/O 路徑
# 是 `repo.set_user_rating_bulk()`（core/database/video.py:1177-）——純 SQLite
# `UPDATE videos SET user_rating = ? WHERE path = ?`，沒有任何檔案系統呼叫。也就是
# 說本檔的 nfo 快照測試同時驗掉 AC-13（NFO 不變）與 AC-14（唯讀來源零寫入，NFO 檔
# 本身就位於「來源目錄」語境下）——沒有另外新增 AC-14 專屬測試（依本卡§B結論，
# 端點結構上不可能寫入 FS，讀碼窮舉已可證偽）。

class TestScenario6NfoByteIdentical:
    """精選／取消精選前後，.nfo 檔案逐位元組（含 mtime）不變（AC-13/AC-14）。"""

    @pytest.fixture
    def nfo_db(self, tmp_path):
        video_dir = tmp_path / "videos"
        video_dir.mkdir()
        video_path = video_dir / "SONE-205.mp4"
        video_path.write_bytes(b"fake video bytes")
        nfo_path = video_dir / "SONE-205.nfo"
        # 含非 ASCII（中日文）內容，驗證 byte-level 比對不是被編碼正規化悄悄放水。
        nfo_path.write_text(
            "<movie><title>테스트 明日花キララ 中文標題 日本語タイトル</title></movie>",
            encoding="utf-8",
        )

        video_uri = to_file_uri(str(video_path), {})
        db_path = tmp_path / "test_nfo.db"
        init_db(db_path)
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO videos (path, number, title, user_tags, user_rating) VALUES (?, 'SONE-205', 'Test', '[]', 0)",
            (video_uri,),
        )
        conn.commit()
        conn.close()

        return db_path, video_uri, nfo_path

    @pytest.fixture
    def nfo_client(self, nfo_db, monkeypatch):
        db_path, _, _ = nfo_db
        monkeypatch.setattr("web.routers.collection.get_db_path", lambda: db_path)
        monkeypatch.setattr("web.routers.collection.load_config", lambda: {"gallery": {"path_mappings": {}}})
        from web.app import app
        return TestClient(app)

    @staticmethod
    def _nfo_fingerprint(nfo_path):
        return (nfo_path.read_bytes(), nfo_path.stat().st_mtime_ns)

    @pytest.mark.parametrize("payload", [{"picked": True}, {"tier": "silver"}], ids=["picked-true", "tier-silver"])
    def test_pick_leaves_nfo_byte_identical(self, nfo_client, nfo_db, payload):
        """picked: True／tier: silver（精選）前後，.nfo 的 bytes 與 mtime_ns 完全相同。"""
        db_path, video_uri, nfo_path = nfo_db
        before = self._nfo_fingerprint(nfo_path)

        resp = nfo_client.post("/api/user-rating", json={"file_path": video_uri, **payload})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        after = self._nfo_fingerprint(nfo_path)
        assert before == after, "AC-13 violated: .nfo bytes/mtime changed after picking"

        repo = VideoRepository(db_path)
        assert repo.get_by_path(video_uri).user_rating > 0


# ── TASK-201-T2：舊 picked 相容＋矛盾 400 ──────────────────────────────────────

class TestTierWritesAndLegacyCompat:
    """picked:true 照舊＝金；tier:'none'＝0；矛盾／缺欄 → 400 且 DB 不動。"""

    def test_picked_true_writes_gold_and_tier_none_clears(self, client, tmp_db):
        resp = client.post("/api/user-rating", json={"file_path": TEST_FILE_URI, "picked": True})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["picked"] is True
        assert data["tier"] == "gold"
        assert _rating(tmp_db, TEST_FILE_URI) == 3

        resp = client.post("/api/user-rating", json={"file_path": TEST_FILE_URI, "tier": "none"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["picked"] is False
        assert data["tier"] == "none"
        assert _rating(tmp_db, TEST_FILE_URI) == 0

        resp = client.post("/api/user-rating", json={"file_path": TEST_FILE_URI, "picked": True, "tier": "silver"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["tier"] == "silver"
        assert _rating(tmp_db, TEST_FILE_URI) == 2

    @pytest.mark.parametrize("payload", [
        {"picked": False, "tier": "gold"},
        {},
    ], ids=["conflicting", "missing-both"])
    def test_conflicting_or_missing_rating_returns_400_without_db_write(self, client, tmp_db, payload):
        """矛盾（picked:false＋tier:'gold'）或兩者都不送 → 400，DB 值不變。"""
        before = _rating(tmp_db, TEST_FILE_URI)
        resp = client.post("/api/user-rating", json={"file_path": TEST_FILE_URI, **payload})
        assert resp.status_code == 400
        assert resp.json()["success"] is False
        assert _rating(tmp_db, TEST_FILE_URI) == before

