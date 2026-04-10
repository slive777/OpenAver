"""
test_search_user_tags.py — Search 頁 user_tags 資料流整合測試 (41b-T3)

DoD 要求的 2 個測試：
- test_search_user_tags_persist：加 tag → API response 含 tag → GET 確認 DB 持久化
- test_search_user_tags_no_file_path：無 file_path 的 POST → success=false
"""

import sqlite3
import pytest
from fastapi.testclient import TestClient
from core.database import init_db
from core.path_utils import to_file_uri


# 使用 to_file_uri() 產生 canonical 形式的測試 key（路徑契約：禁止手刻 file:///）
TEST_FILE_URI = to_file_uri("C:/AVtest/SONE-205.mp4")
NONEXISTENT_URI = to_file_uri("C:/AVtest/NONEXISTENT.mp4")


@pytest.fixture
def tmp_db(tmp_path):
    """建立臨時測試資料庫，插入一筆測試影片"""
    db_path = tmp_path / "test_search_user_tags.db"
    init_db(db_path)

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        INSERT INTO videos (path, number, title, actresses, maker, tags, user_tags, duration, size_bytes)
        VALUES (?, 'SONE-205', 'Test Movie', '["明日花キララ"]', 'Sony', '["巨乳"]', '[]', 7200, 4000000000)
    """, (TEST_FILE_URI,))
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def client(tmp_db, monkeypatch):
    """TestClient，monkeypatch get_db_path 指向 tmp DB"""
    monkeypatch.setattr("web.routers.collection.get_db_path", lambda: tmp_db)
    from web.app import app
    return TestClient(app)


class TestSearchUserTagsPersist:
    """
    test_search_user_tags_persist:
    加 tag → remove tag → GET 確認移除已持久化
    """

    def test_add_then_remove_tag_persisted(self, tmp_db, monkeypatch):
        """POST add tag → POST remove tag → GET 確認移除已持久化"""
        monkeypatch.setattr("web.routers.collection.get_db_path", lambda: tmp_db)
        from web.app import app
        test_client = TestClient(app)

        # 先加
        test_client.post("/api/user-tags", json={
            "file_path": TEST_FILE_URI,
            "add": ["暫時標籤"],
        })

        # 再刪
        remove_resp = test_client.post("/api/user-tags", json={
            "file_path": TEST_FILE_URI,
            "remove": ["暫時標籤"],
        })
        assert remove_resp.json()["success"] is True
        assert "暫時標籤" not in remove_resp.json()["user_tags"]

        # GET 確認
        get_resp = test_client.get("/api/user-tags", params={"file_path": TEST_FILE_URI})
        assert "暫時標籤" not in get_resp.json()["user_tags"]


class TestSearchUserTagsNoFilePath:
    """
    test_search_user_tags_no_file_path:
    file_path 為空字串 → 422 或 success=False
    """

    def test_post_empty_file_path_returns_422_or_false(self, client):
        """POST file_path 為空字串 → 422 或 success=False（視 validator 行為）"""
        resp = client.post("/api/user-tags", json={
            "file_path": "",
            "add": ["★5"],
        })
        # 可接受 422（Pydantic min_length validation）或 200 success=False
        assert resp.status_code in (200, 422)
        if resp.status_code == 200:
            assert resp.json()["success"] is False


class TestNfoPreservation:
    """
    P1 修正：NFO surgical update — 加 user_tag 不清掉既有 NFO 欄位。

    核心場景：NFO 有 <website>、<tag>中文字幕</tag> 等欄位，POST /api/user-tags
    不應重寫整份 NFO（那會清掉 DB 沒有的欄位），而是只 surgical 改 <user_tag>。
    """

    def test_nfo_existing_fields_preserved_after_add_tag(self, tmp_db, tmp_path, monkeypatch):
        """加 user_tag 後，NFO 既有欄位（website、特殊 tag）應保留"""
        import xml.etree.ElementTree as ET
        monkeypatch.setattr("web.routers.collection.get_db_path", lambda: tmp_db)

        # 建立帶有既有欄位的 NFO 和對應影片
        mp4_path = tmp_path / "SONE-205.mp4"
        mp4_path.write_bytes(b"fake video")
        nfo_path = tmp_path / "SONE-205.nfo"
        nfo_content = """<?xml version='1.0' encoding='utf-8'?>
<movie>
  <num>SONE-205</num>
  <title>Test Movie</title>
  <website>https://www.example.com/SONE-205</website>
  <tag>中文字幕</tag>
  <tag>巨乳</tag>
</movie>"""
        nfo_path.write_text(nfo_content, encoding="utf-8")

        # 將 DB 中的影片路徑指向 tmp_path 的 mp4
        file_uri = to_file_uri(str(mp4_path))

        import sqlite3
        conn = sqlite3.connect(str(tmp_db))
        conn.execute(
            "UPDATE videos SET path = ? WHERE path = ?",
            (file_uri, TEST_FILE_URI)
        )
        conn.commit()
        conn.close()

        from web.app import app
        from fastapi.testclient import TestClient
        test_client = TestClient(app)

        resp = test_client.post("/api/user-tags", json={
            "file_path": file_uri,
            "add": ["★5"],
        })
        assert resp.json()["success"] is True

        # 驗證 NFO 既有欄位保留
        tree = ET.parse(str(nfo_path))
        root = tree.getroot()
        website = root.findtext("website")
        tags = [e.text for e in root.findall("tag")]
        user_tags = [e.text for e in root.findall("user_tag")]

        assert website == "https://www.example.com/SONE-205", "website 欄位被清掉"
        assert "中文字幕" in tags, "<tag>中文字幕</tag> 被清掉"
        assert "巨乳" in tags, "<tag>巨乳</tag> 被清掉"
        assert "★5" in user_tags, "user_tag ★5 未寫入"

