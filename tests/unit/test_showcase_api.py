"""測試 Showcase API"""
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from core.database import init_db, Video, VideoRepository
from core.path_utils import to_file_uri


# temp_db fixture 定義於 tests/unit/conftest.py

@pytest.fixture
def showcase_config():
    return {
        "gallery": {
            "directories": [
                "/home/user/media",
                "C:/Videos",
                "D:/AV",
                "//NAS/share",
            ],
            "path_mappings": {},
            "min_size_mb": 1,
            "thumbnail_width": 400
        },
        "scraper": {"video_extensions": [".mp4"], "image_extensions": [".jpg"]},
        "database": {"path": ":memory:"},
        "translate": {"provider": "ollama", "ollama_model": "llama3"}
    }

@pytest.fixture
def client(make_client, temp_db, showcase_config):
    return make_client(
        ["core.database.connection.get_db_path", "web.routers.showcase.get_db_path", "web.routers.showcase.load_config"],
        mock_db_path=temp_db,
        config_override=showcase_config,
    )

@pytest.fixture
def populated_db(make_populated_db):
    videos = [
        Video(
            path=to_file_uri("/home/user/media/SONE-205.mp4"),
            number="SONE-205",
            title="Test Video 1",
            original_title="テストビデオ1",
            actresses=["坂道みる", "深田えいみ"],
            maker="S1 NO.1 STYLE",
            release_date="2024-01-15",
            tags=["単体作品", "ハイビジョン", "独占配信"],
            size_bytes=3145728000,
            cover_path=to_file_uri("/home/user/media/SONE-205/poster.jpg"),
            mtime=1705276800.0
        ),
        Video(
            path=to_file_uri("C:/Videos/ABW-001.mp4"),
            number="ABW-001",
            title="Test Video 2",
            original_title="",
            actresses=["新ありな"],
            maker="Prestige",
            release_date="2024-02-01",
            tags=["スレンダー"],
            size_bytes=2147483648,
            cover_path=to_file_uri("C:/Videos/ABW-001/cover.jpg"),
            mtime=1706745600.0
        ),
        Video(
            path=to_file_uri("D:/AV/FC2-001.mp4"),
            number="FC2-PPV-001",
            title="Test Video 3 - No Cover",
            original_title="",
            actresses=[],
            maker="",
            release_date="",
            tags=[],
            size_bytes=0,
            cover_path="",
            mtime=0.0
        ),
        Video(
            path=to_file_uri("//NAS/share/PRED-001.mp4"),
            number="PRED-001",
            title="Test Video 4 - UNC Path",
            original_title="",
            actresses=["篠田ゆう"],
            maker="Premium",
            release_date="2024-03-01",
            tags=[],
            size_bytes=1073741824,
            cover_path=to_file_uri("//NAS/share/PRED-001/cover.jpg"),
            mtime=1709251200.0
        ),
    ]
    return make_populated_db(videos)


# === API 端點測試 ===

class TestShowcaseVideosAPI:
    """測試 /api/showcase/videos 端點"""

    def test_get_videos_empty_db(self, client, temp_db, monkeypatch):
        """測試空資料庫回傳正確格式"""
        def mock_get_db_path():
            return temp_db
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        response = client.get("/api/showcase/videos")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["videos"] == []
        assert data["total"] == 0

    def test_get_videos_db_not_exists(self, client, tmp_path, monkeypatch):
        """測試資料庫檔案不存在時不報錯"""
        nonexistent_db = tmp_path / "nonexistent.db"

        def mock_get_db_path():
            return nonexistent_db
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        response = client.get("/api/showcase/videos")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["videos"] == []
        assert data["total"] == 0

    @pytest.fixture
    def showcase_videos_response(self, client, populated_db, monkeypatch):
        """共用 fixture：取得有資料時的 API 回應"""
        def mock_get_db_path():
            return populated_db
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)
        return client.get("/api/showcase/videos")

    def test_get_videos_returns_list_structure(self, showcase_videos_response):
        """測試回傳列表基本結構"""
        response = showcase_videos_response
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["total"] == 4
        assert len(data["videos"]) == 4

    def test_get_videos_item_basic_fields(self, showcase_videos_response):
        """測試單筆影片資源基本與元資料欄位"""
        data = showcase_videos_response.json()
        video1 = data["videos"][0]
        assert "path" in video1
        assert "title" in video1
        assert "original_title" in video1
        assert "number" in video1
        assert "maker" in video1
        assert "release_date" in video1

    def test_get_videos_item_media_fields(self, showcase_videos_response):
        """測試單筆影片資源多媒體與陣列欄位"""
        data = showcase_videos_response.json()
        video1 = data["videos"][0]
        assert "actresses" in video1
        assert "tags" in video1
        assert "size" in video1
        assert "cover_url" in video1
        assert "mtime" in video1

    def test_cover_url_conversion_unix_path(self, client, populated_db, monkeypatch):
        """測試 cover_url 正確轉換（Unix 路徑）— 使用真實 Unix 路徑，CI 環境無關"""
        from urllib.parse import unquote

        def mock_get_db_path():
            return populated_db
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        response = client.get("/api/showcase/videos")
        data = response.json()

        # 第一筆：file:////home/user/media/SONE-205/poster.jpg（真實 Unix 路徑，4 斜線）
        video1 = data["videos"][0]
        assert video1["cover_url"].startswith("/api/gallery/image?path=")

        # 解碼 URL 以驗證路徑格式
        path_param = video1["cover_url"].split("path=")[1]
        decoded_path = unquote(path_param)

        # Unix 路徑必須以 / 開頭
        assert decoded_path.startswith("/"), f"Unix 路徑前導 / 丟失: {decoded_path}"
        assert "SONE-205" in decoded_path
        # URL encoded，路徑分隔符 / 會變成 %2F
        assert "%2F" in video1["cover_url"]

    def test_cover_url_conversion_windows_path(self, client, populated_db, monkeypatch):
        """測試 cover_url 正確轉換（Windows 路徑）"""
        from urllib.parse import unquote

        def mock_get_db_path():
            return populated_db
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        response = client.get("/api/showcase/videos")
        data = response.json()

        # 第二筆：file:///C:/Videos/ABW-001/cover.jpg
        # normalize_path 在 WSL 會轉為 /mnt/c/...，在 Windows 保持 C:/...
        video2 = data["videos"][1]
        assert video2["cover_url"].startswith("/api/gallery/image?path=")
        assert "ABW-001" in video2["cover_url"]

        # 解碼 URL 驗證路徑合理性（不是相對路徑）
        path_param = video2["cover_url"].split("path=")[1]
        decoded_path = unquote(path_param)
        # 路徑應該是絕對路徑（/ 開頭或盤符開頭）
        assert decoded_path.startswith("/") or (len(decoded_path) >= 2 and decoded_path[1] == ":"), \
            f"Windows 路徑轉換結果不是絕對路徑: {decoded_path}"

    def test_cover_url_conversion_unc_path(self, client, populated_db, monkeypatch):
        """測試 cover_url 正確轉換（UNC 路徑，不多加 /）"""
        from urllib.parse import unquote

        def mock_get_db_path():
            return populated_db
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        response = client.get("/api/showcase/videos")
        data = response.json()

        # 第四筆：file://///NAS/share/PRED-001/cover.jpg
        # strip file:/// → //NAS/share/PRED-001/cover.jpg（已有前導 /，不應再加）
        video4 = data["videos"][3]
        assert video4["cover_url"].startswith("/api/gallery/image?path=")

        path_param = video4["cover_url"].split("path=")[1]
        decoded_path = unquote(path_param)
        # UNC 路徑應保持 //server/share 格式（恰好兩個 /）
        assert decoded_path.startswith("//"), f"UNC 路徑格式錯誤: {decoded_path}"
        assert not decoded_path.startswith("///"), f"UNC 路徑多了 /: {decoded_path}"
        assert "PRED-001" in decoded_path

    def test_cover_url_empty_when_no_cover(self, client, populated_db, monkeypatch):
        """測試無封面圖時 cover_url 為空字串"""
        def mock_get_db_path():
            return populated_db
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        response = client.get("/api/showcase/videos")
        data = response.json()

        # 第三筆：無封面
        video3 = data["videos"][2]
        assert video3["cover_url"] == ""

    def test_actresses_comma_separated_string(self, client, populated_db, monkeypatch):
        """測試 actresses 正確轉為逗號分隔字串"""
        def mock_get_db_path():
            return populated_db
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        response = client.get("/api/showcase/videos")
        data = response.json()

        # 第一筆：多位女優
        video1 = data["videos"][0]
        assert isinstance(video1["actresses"], str)
        assert video1["actresses"] == "坂道みる,深田えいみ"

        # 第二筆：單一女優
        video2 = data["videos"][1]
        assert video2["actresses"] == "新ありな"

        # 第三筆：空陣列 → 空字串
        video3 = data["videos"][2]
        assert video3["actresses"] == ""

    def test_tags_comma_separated_string(self, client, populated_db, monkeypatch):
        """測試 tags 正確轉為逗號分隔字串"""
        def mock_get_db_path():
            return populated_db
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        response = client.get("/api/showcase/videos")
        data = response.json()

        # 第一筆：多個標籤
        video1 = data["videos"][0]
        assert isinstance(video1["tags"], str)
        assert video1["tags"] == "単体作品,ハイビジョン,独占配信"

        # 第三筆：空陣列 → 空字串
        video3 = data["videos"][2]
        assert video3["tags"] == ""

    def test_mtime_is_integer(self, client, populated_db, monkeypatch):
        """測試 mtime 為整數（不是浮點數）"""
        def mock_get_db_path():
            return populated_db
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        response = client.get("/api/showcase/videos")
        data = response.json()

        # 第一筆：有 mtime
        video1 = data["videos"][0]
        assert isinstance(video1["mtime"], int)
        assert video1["mtime"] == 1705276800  # 浮點數 1705276800.0 → 整數 1705276800

        # 第三筆：零時間
        video3 = data["videos"][2]
        assert video3["mtime"] == 0
        assert isinstance(video3["mtime"], int)

    def test_empty_fields_response_structure(self, client, populated_db, monkeypatch):
        """測試空值欄位的回應結構與狀態欄位"""
        def mock_get_db_path():
            return populated_db
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        response = client.get("/api/showcase/videos")
        data = response.json()

        # 第三筆：多個空值欄位 — 基本結構與狀態
        video3 = data["videos"][2]
        assert video3["number"] == "FC2-PPV-001"  # number 有值
        assert video3["original_title"] == ""  # 空字串
        assert video3["maker"] == ""  # 空字串
        assert video3["release_date"] == ""  # 空字串

    def test_empty_fields_content_values(self, client, populated_db, monkeypatch):
        """測試空值欄位的內容值（陣列、數值、封面）"""
        def mock_get_db_path():
            return populated_db
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        response = client.get("/api/showcase/videos")
        data = response.json()

        # 第三筆：多個空值欄位 — 內容值
        video3 = data["videos"][2]
        assert video3["actresses"] == ""  # 空陣列 → 空字串
        assert video3["tags"] == ""  # 空陣列 → 空字串
        assert video3["size"] == 0  # 零值
        assert video3["cover_url"] == ""  # 無封面
        assert video3["mtime"] == 0  # 零時間

    def test_response_structure(self, client, populated_db, monkeypatch):
        """測試回應結構完整性"""
        def mock_get_db_path():
            return populated_db
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        response = client.get("/api/showcase/videos")
        assert response.status_code == 200

        data = response.json()
        # 必須包含三個頂層欄位
        assert "success" in data
        assert "videos" in data
        assert "total" in data

        # videos 必須是陣列
        assert isinstance(data["videos"], list)
        # total 必須是整數且等於陣列長度
        assert isinstance(data["total"], int)
        assert data["total"] == len(data["videos"])

    def test_video_path_format(self, client, populated_db, monkeypatch):
        """測試 path 欄位保持 file:/// URI 格式"""
        def mock_get_db_path():
            return populated_db
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        response = client.get("/api/showcase/videos")
        data = response.json()

        # 所有 path 都應該保持 file:/// 格式（開啟影片用）
        for video in data["videos"]:
            assert video["path"].startswith("file:///")

    def test_get_videos_error_handling(self, client, populated_db, monkeypatch):
        """測試 DB 錯誤時回傳 500 + 錯誤訊息"""
        def mock_get_db_path():
            return populated_db
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        # Mock VideoRepository.get_all() 拋出異常
        def mock_get_all_error(self):
            raise Exception("db error")

        monkeypatch.setattr("core.database.VideoRepository.get_all", mock_get_all_error)

        response = client.get("/api/showcase/videos")
        assert response.status_code == 500

        data = response.json()
        assert data["success"] is False
        assert data["error"] == "取得影片資料失敗"
        assert data["videos"] == []
        assert data["total"] == 0


class TestShowcaseMetadataFields:
    """T3: 驗證 /api/showcase/videos 回傳含 director/duration/series/label 欄位"""

    @pytest.fixture
    def populated_db_with_meta(self, make_populated_db):
        """含有 director/duration/series/label 資料的 DB"""
        videos = [
            Video(
                path=to_file_uri("/home/user/media/SONE-205.mp4"),
                number="SONE-205",
                title="Full Meta Video",
                original_title="",
                actresses=["坂道みる"],
                maker="S1 NO.1 STYLE",
                release_date="2024-01-15",
                tags=["単体作品"],
                size_bytes=3145728000,
                cover_path="",
                mtime=1705276800.0,
                director="山田太郎",
                duration=120,
                series="素人シリーズ",
                label="S1",
            ),
            Video(
                path=to_file_uri("C:/Videos/ABW-001.mp4"),
                number="ABW-001",
                title="Empty Meta Video",
                original_title="",
                actresses=[],
                maker="",
                release_date="",
                tags=[],
                size_bytes=0,
                cover_path="",
                mtime=0.0,
                director="",
                duration=None,
                series=None,
                label="",
            ),
        ]
        return make_populated_db(videos)

    def test_new_fields_present_in_response(self, client, populated_db_with_meta, monkeypatch):
        """API 回傳每個 video 物件都包含 director/duration/series/label 欄位"""
        def mock_get_db_path():
            return populated_db_with_meta
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        response = client.get("/api/showcase/videos")
        assert response.status_code == 200

        data = response.json()
        for video in data["videos"]:
            assert "director" in video, "回應缺少 director 欄位"
            assert "duration" in video, "回應缺少 duration 欄位"
            assert "series" in video, "回應缺少 series 欄位"
            assert "label" in video, "回應缺少 label 欄位"

    def test_duration_is_int_when_present(self, client, populated_db_with_meta, monkeypatch):
        """duration 有值時為 int（非字串）"""
        def mock_get_db_path():
            return populated_db_with_meta
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        response = client.get("/api/showcase/videos")
        data = response.json()

        video1 = data["videos"][0]
        assert video1["duration"] == 120
        assert isinstance(video1["duration"], int)

    def test_duration_is_none_when_absent(self, client, populated_db_with_meta, monkeypatch):
        """duration 無值時為 None（前端 x-show 自動隱藏）"""
        def mock_get_db_path():
            return populated_db_with_meta
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        response = client.get("/api/showcase/videos")
        data = response.json()

        video2 = data["videos"][1]
        assert video2["duration"] is None

    def test_director_empty_string_when_absent(self, client, populated_db_with_meta, monkeypatch):
        """director 無值時為空字串（不是 None）"""
        def mock_get_db_path():
            return populated_db_with_meta
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        response = client.get("/api/showcase/videos")
        data = response.json()

        video2 = data["videos"][1]
        assert video2["director"] == ""

    def test_series_empty_string_when_absent(self, client, populated_db_with_meta, monkeypatch):
        """series 為 None 時回傳空字串（v.series or ''）"""
        def mock_get_db_path():
            return populated_db_with_meta
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        response = client.get("/api/showcase/videos")
        data = response.json()

        video2 = data["videos"][1]
        assert video2["series"] == ""

    def test_label_empty_string_when_absent(self, client, populated_db_with_meta, monkeypatch):
        """label 無值時為空字串"""
        def mock_get_db_path():
            return populated_db_with_meta
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        response = client.get("/api/showcase/videos")
        data = response.json()

        video2 = data["videos"][1]
        assert video2["label"] == ""

    def test_full_meta_values_returned_correctly(self, client, populated_db_with_meta, monkeypatch):
        """有值時 director/duration/series/label 正確回傳"""
        def mock_get_db_path():
            return populated_db_with_meta
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        response = client.get("/api/showcase/videos")
        data = response.json()

        video1 = data["videos"][0]
        assert video1["director"] == "山田太郎"
        assert video1["duration"] == 120
        assert video1["series"] == "素人シリーズ"
        assert video1["label"] == "S1"


class TestShowcaseDirectoryFiltering:
    """測試 Showcase 只回傳「當前設定資料夾」底下的影片"""

    def test_only_configured_dirs_returned(self, client, populated_db, monkeypatch):
        """只設定部分資料夾時，不應回傳其他資料夾的影片"""
        def mock_get_db_path():
            return populated_db
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        # 只設定 /home/user/media，不包含 C:/Videos、D:/AV、//NAS/share
        def mock_load_config():
            return {
                "gallery": {
                    "directories": ["/home/user/media"],
                    "path_mappings": {},
                }
            }
        monkeypatch.setattr("web.routers.showcase.load_config", mock_load_config)

        response = client.get("/api/showcase/videos")
        data = response.json()

        assert data["success"] is True
        assert data["total"] == 1
        assert data["videos"][0]["number"] == "SONE-205"

    def test_uri_source_path_filtering(self, client, populated_db, monkeypatch):
        """PR#91 P2-D: 來源 path 已是 file:/// URI（schema「FS 路徑或 URI」）時，
        該資料夾底下的列仍要出現在 Showcase。

        pre-fix `to_file_uri('file:///…')` 二次包成 'file:///file:///…' → 過濾掉
        所有列 → total == 0 (RED)。
        """
        def mock_get_db_path():
            return populated_db
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        # 來源 path 用 URI 形式（等價 /home/user/media），只設這一個來源
        def mock_load_config():
            return {
                "gallery": {
                    "directories": [to_file_uri("/home/user/media")],
                    "path_mappings": {},
                }
            }
        monkeypatch.setattr("web.routers.showcase.load_config", mock_load_config)

        response = client.get("/api/showcase/videos")
        data = response.json()

        assert data["success"] is True
        assert data["total"] == 1
        assert data["videos"][0]["number"] == "SONE-205"

    def test_wsl_mount_path_filtering(self, client, temp_db, monkeypatch):
        """WSL /mnt/c/ 設定值能正確匹配 DB 中的 file:///C:/ URI"""
        repo = VideoRepository(temp_db)
        repo.upsert_batch([
            Video(
                path=to_file_uri("C:/Videos/ABW-001.mp4"),
                number="ABW-001", title="WSL mount test",
                actresses=["新ありな"], tags=[], size_bytes=0, mtime=0.0,
            ),
            Video(
                path=to_file_uri("D:/AV/OTHER-001.mp4"),
                number="OTHER-001", title="Other drive",
                actresses=[], tags=[], size_bytes=0, mtime=0.0,
            ),
        ])

        def mock_get_db_path():
            return temp_db
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        # WSL 使用者設定 /mnt/c/Videos → to_file_uri 轉成 file:///C:/Videos
        def mock_load_config():
            return {
                "gallery": {
                    "directories": ["/mnt/c/Videos"],
                    "path_mappings": {},
                }
            }
        monkeypatch.setattr("web.routers.showcase.load_config", mock_load_config)

        response = client.get("/api/showcase/videos")
        data = response.json()

        assert data["success"] is True
        assert data["total"] == 1, f"應只命中 C:/Videos 底下的 1 筆，實際 {data['total']} 筆"
        assert data["videos"][0]["number"] == "ABW-001"
        assert "C:/Videos" in data["videos"][0]["path"], "回傳影片路徑應在 C:/Videos 底下"

    def test_prefix_collision_not_matched(self, client, temp_db, monkeypatch):
        """設定 E:/media 時，E:/media2 底下的影片不應被混入（前綴碰撞回歸測試）"""
        # 插入兩筆：一筆在 E:/media，一筆在 E:/media2（前綴碰撞候選）
        repo = VideoRepository(temp_db)
        repo.upsert_batch([
            Video(
                path=to_file_uri("E:/media/SONE-205.mp4"),
                number="SONE-205", title="Under media",
                actresses=[], tags=[], size_bytes=0, mtime=0.0,
            ),
            Video(
                path=to_file_uri("E:/media2/ABW-001.mp4"),
                number="ABW-001", title="Under media2",
                actresses=[], tags=[], size_bytes=0, mtime=0.0,
            ),
        ])

        def mock_get_db_path():
            return temp_db
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        # 只設定 E:/media — 不應包含 E:/media2
        def mock_load_config():
            return {
                "gallery": {
                    "directories": ["E:/media"],
                    "path_mappings": {},
                }
            }
        monkeypatch.setattr("web.routers.showcase.load_config", mock_load_config)

        response = client.get("/api/showcase/videos")
        data = response.json()

        assert data["success"] is True
        assert data["total"] == 1
        assert data["videos"][0]["number"] == "SONE-205"

    def test_no_dirs_configured_returns_empty(self, client, populated_db, monkeypatch):
        """未設定資料夾時回傳空結果"""
        def mock_get_db_path():
            return populated_db
        monkeypatch.setattr("web.routers.showcase.get_db_path", mock_get_db_path)

        def mock_load_config():
            return {"gallery": {"directories": [], "path_mappings": {}}}
        monkeypatch.setattr("web.routers.showcase.load_config", mock_load_config)

        response = client.get("/api/showcase/videos")
        data = response.json()

        assert data["success"] is True
        assert data["total"] == 0


class TestVideoProxy:
    """測試 GET /api/gallery/video 影片代理"""

    def test_allowed_path_returns_200(self, client, tmp_path, monkeypatch):
        """白名單內的影片路徑回傳 200"""
        video = tmp_path / "test.mp4"
        video.write_bytes(b'\x00' * 100)

        def mock_load_config():
            return {
                "gallery": {
                    "directories": [str(tmp_path)],
                    "path_mappings": {},
                }
            }
        monkeypatch.setattr("web.routers.scanner.load_config", mock_load_config)

        response = client.get(f"/api/gallery/video?path={str(video)}")
        assert response.status_code == 200
        assert "video" in response.headers["content-type"]

    def test_outside_dir_returns_403(self, client, tmp_path, monkeypatch):
        """白名單外的路徑回傳 403"""
        video = tmp_path / "test.mp4"
        video.write_bytes(b'\x00' * 100)

        def mock_load_config():
            return {
                "gallery": {
                    "directories": ["/some/other/directory"],
                    "path_mappings": {},
                }
            }
        monkeypatch.setattr("web.routers.scanner.load_config", mock_load_config)

        response = client.get(f"/api/gallery/video?path={str(video)}")
        assert response.status_code == 403

    def test_non_video_extension_returns_403(self, client, tmp_path, monkeypatch):
        """非影片副檔名回傳 403"""
        txt_file = tmp_path / "readme.txt"
        txt_file.write_bytes(b'hello')

        def mock_load_config():
            return {
                "gallery": {
                    "directories": [str(tmp_path)],
                    "path_mappings": {},
                }
            }
        monkeypatch.setattr("web.routers.scanner.load_config", mock_load_config)

        response = client.get(f"/api/gallery/video?path={str(txt_file)}")
        assert response.status_code == 403

    def test_not_found_returns_404(self, client, tmp_path, monkeypatch):
        """檔案不存在回傳 404"""
        nonexistent = tmp_path / "ghost.mp4"

        def mock_load_config():
            return {
                "gallery": {
                    "directories": [str(tmp_path)],
                    "path_mappings": {},
                }
            }
        monkeypatch.setattr("web.routers.scanner.load_config", mock_load_config)

        response = client.get(f"/api/gallery/video?path={str(nonexistent)}")
        assert response.status_code == 404

    def test_range_request_returns_206(self, client, tmp_path, monkeypatch):
        """Range request 回傳 206 Partial Content"""
        video = tmp_path / "test.mp4"
        video.write_bytes(b'\x00' * 1000)

        def mock_load_config():
            return {
                "gallery": {
                    "directories": [str(tmp_path)],
                    "path_mappings": {},
                }
            }
        monkeypatch.setattr("web.routers.scanner.load_config", mock_load_config)

        response = client.get(
            f"/api/gallery/video?path={str(video)}",
            headers={"Range": "bytes=0-499"}
        )
        assert response.status_code == 206
        assert response.headers["content-range"] == "bytes 0-499/1000"
        assert len(response.content) == 500

    def test_player_page_returns_html(self, client, tmp_path, monkeypatch):
        """播放頁面回傳包含 <video> 標籤的 HTML"""
        video = tmp_path / "test.mp4"
        video.write_bytes(b'\x00' * 100)

        response = client.get(f"/api/gallery/player?path={str(video)}")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "<video" in response.text
        assert "/api/gallery/video?path=" in response.text

    def test_path_traversal_blocked(self, client, tmp_path, monkeypatch):
        """路徑穿越 ../ 被 normpath + 白名單兜底擋下回傳 403"""
        # 建立 allowed_dir/sub/test.mp4
        allowed_dir = tmp_path / "allowed"
        allowed_dir.mkdir()
        sub = allowed_dir / "sub"
        sub.mkdir()
        video = sub / "test.mp4"
        video.write_bytes(b'\x00' * 100)

        # 也在 tmp_path 根建立 secret.mp4（在 allowed_dir 之外）
        secret = tmp_path / "secret.mp4"
        secret.write_bytes(b'\x00' * 100)

        def mock_load_config():
            return {
                "gallery": {
                    "directories": [str(allowed_dir)],
                    "path_mappings": {},
                }
            }
        monkeypatch.setattr("web.routers.scanner.load_config", mock_load_config)

        # 嘗試用 ../ 穿越到 allowed_dir 之外
        traversal_path = str(allowed_dir / "sub" / ".." / ".." / "secret.mp4")
        response = client.get(f"/api/gallery/video?path={traversal_path}")
        assert response.status_code == 403, "路徑穿越應被 403 擋下"

    def test_symlink_traversal_blocked(self, client, tmp_path, monkeypatch):
        """symlink target 在白名單外應回 403：realpath 追蹤 symlink target 後若越界則拒絕"""
        # 建立 allowed_dir 和外部的 secret.mp4
        allowed_dir = tmp_path / "allowed"
        allowed_dir.mkdir()
        secret = tmp_path / "secret.mp4"
        secret.write_bytes(b'\x00' * 100)

        # 在 allowed_dir 內建立指向 secret.mp4 的 symlink
        symlink = allowed_dir / "link.mp4"
        try:
            symlink.symlink_to(secret)
        except OSError:
            pytest.skip("系統不支援 symlink")

        def mock_load_config():
            return {
                "gallery": {
                    "directories": [str(allowed_dir)],
                    "path_mappings": {},
                }
            }
        monkeypatch.setattr("web.routers.scanner.load_config", mock_load_config)

        # realpath 追蹤 symlink target 到白名單外 → 403
        response = client.get(f"/api/gallery/video?path={str(symlink)}")
        assert response.status_code == 403, \
            "realpath 追蹤 symlink target：target 在白名單外應回傳 403"

    def test_invalid_range_returns_416(self, client, tmp_path, monkeypatch):
        """無效 Range（start 超出檔案大小）回傳 416"""
        video = tmp_path / "test.mp4"
        video.write_bytes(b'\x00' * 100)

        def mock_load_config():
            return {
                "gallery": {
                    "directories": [str(tmp_path)],
                    "path_mappings": {},
                }
            }
        monkeypatch.setattr("web.routers.scanner.load_config", mock_load_config)

        response = client.get(
            f"/api/gallery/video?path={str(video)}",
            headers={"Range": "bytes=9999-"}
        )
        assert response.status_code == 416

    def test_exe_file_returns_403(self, client, tmp_path, monkeypatch):
        """Proxy security: .exe file returns 403 even if in config video_extensions"""
        exe_file = tmp_path / "test.exe"
        exe_file.write_bytes(b'\x00' * 100)

        def mock_load_config():
            return {
                "scraper": {
                    "video_extensions": [".mp4", ".exe"],
                },
                "gallery": {
                    "directories": [str(tmp_path)],
                    "path_mappings": {},
                }
            }
        monkeypatch.setattr("web.routers.scanner.load_config", mock_load_config)

        response = client.get(f"/api/gallery/video?path={str(exe_file)}")
        assert response.status_code == 403, \
            ".exe should be blocked by proxy security (SAFE_PROXY_EXTENSIONS)"

    def test_video_api_uses_get_proxy_extensions(self):
        """get_video() must use get_proxy_extensions (not hardcoded ALLOWED_VIDEO_EXTENSIONS)"""
        scanner_py = Path(__file__).parent.parent.parent / "web" / "routers" / "scanner.py"
        content = scanner_py.read_text(encoding='utf-8')
        assert 'get_proxy_extensions' in content, \
            "scanner.py get_video() should use get_proxy_extensions from core.video_extensions"

    def test_endpoint_works_when_realpath_would_raise(self, client, tmp_path, monkeypatch):
        """FUSE/WinFsp 相容：mock os.path.realpath 丟 OSError 時 endpoint 走 except 分支降級 normpath，仍回傳 200"""
        import os
        from unittest.mock import Mock

        video = tmp_path / "test.mp4"
        video.write_bytes(b'\x00' * 100)

        def mock_load_config():
            return {
                "gallery": {
                    "directories": [str(tmp_path)],
                    "path_mappings": {},
                }
            }
        monkeypatch.setattr("web.routers.scanner.load_config", mock_load_config)
        monkeypatch.setattr(os.path, "realpath", Mock(side_effect=OSError("WinError 1005")))

        response = client.get(f"/api/gallery/video?path={str(video)}")
        assert response.status_code == 200, \
            "realpath OSError 時應降級 normpath，FUSE/WinFsp 掛載下 endpoint 應回傳 200 而非 500"

    def test_video_fuse_symlink_fallback(self, client, tmp_path, monkeypatch):
        """FUSE 環境 mock realpath raise OSError → 降級 normpath → symlink 在白名單內 → 200
        明確記錄 FUSE 下接受 symlink escape 殘留風險（target 不被追蹤）"""
        import os
        from unittest.mock import Mock

        allowed_dir = tmp_path / "gallery"
        allowed_dir.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        target = outside / "target.mp4"
        target.write_bytes(b'\x00' * 100)
        link = allowed_dir / "link.mp4"
        try:
            link.symlink_to(target)
        except OSError:
            pytest.skip("系統不支援 symlink")

        def mock_load_config():
            return {
                "gallery": {
                    "directories": [str(allowed_dir)],
                    "path_mappings": {},
                }
            }
        monkeypatch.setattr("web.routers.scanner.load_config", mock_load_config)
        # mock realpath raise OSError（模擬 WinFsp GetFinalPathNameByHandle 失敗）
        monkeypatch.setattr(os.path, "realpath", Mock(side_effect=OSError("WinError 1005")))

        response = client.get(f"/api/gallery/video?path={str(link)}")
        assert response.status_code == 200, \
            "FUSE 降級 normpath 後 symlink 本身在白名單內應回 200（接受 FUSE 下 symlink escape 殘留風險）"

    def test_normpath_resolves_traversal(self, client, tmp_path, monkeypatch):
        """normpath 正確解析 .. 並交給白名單兜底：合法 .. → 200；穿越 → 403"""
        allowed_dir = tmp_path / "allowed"
        allowed_dir.mkdir()
        sub = allowed_dir / "sub"
        sub.mkdir()
        video = allowed_dir / "cover.mp4"
        video.write_bytes(b'\x00' * 100)

        def mock_load_config():
            return {
                "gallery": {
                    "directories": [str(allowed_dir)],
                    "path_mappings": {},
                }
            }
        monkeypatch.setattr("web.routers.scanner.load_config", mock_load_config)

        # Case A: sub/../cover.mp4 → normpath → allowed_dir/cover.mp4 → 200
        legal_path = str(sub / ".." / "cover.mp4")
        response = client.get(f"/api/gallery/video?path={legal_path}")
        assert response.status_code == 200, \
            "合法 .. 移動（仍在白名單內）應回傳 200"

        # Case B: allowed_dir/../../etc → normpath → 白名單外 → 403
        traversal_path = str(allowed_dir / ".." / ".." / "etc" / "passwd.mp4")
        response = client.get(f"/api/gallery/video?path={traversal_path}")
        assert response.status_code == 403, \
            "穿越出白名單的 .. 路徑應被 403 擋下"


class TestImageProxy:
    """get_image() 安全防護 — regression tests"""

    @pytest.fixture
    def client(self):
        from web.app import app
        return TestClient(app)

    def test_image_in_whitelist_200(self, client, tmp_path, monkeypatch):
        """白名單內的 .jpg 圖片回傳 200"""
        allowed_dir = tmp_path / "gallery"
        allowed_dir.mkdir()
        img = allowed_dir / "cover.jpg"
        img.write_bytes(b'\xff\xd8\xff' + b'\x00' * 100)

        def mock_load_config():
            return {
                "gallery": {
                    "directories": [str(allowed_dir)],
                    "path_mappings": {},
                }
            }
        monkeypatch.setattr("web.routers.scanner.load_config", mock_load_config)

        response = client.get(f"/api/gallery/image?path={str(img)}")
        assert response.status_code == 200, "白名單內圖片應回傳 200"

    def test_image_outside_whitelist_403(self, client, tmp_path, monkeypatch):
        """白名單外的路徑回傳 403"""
        allowed_dir = tmp_path / "gallery"
        allowed_dir.mkdir()
        outside_dir = tmp_path / "secret"
        outside_dir.mkdir()
        img = outside_dir / "secret.jpg"
        img.write_bytes(b'\xff\xd8\xff' + b'\x00' * 100)

        def mock_load_config():
            return {
                "gallery": {
                    "directories": [str(allowed_dir)],
                    "path_mappings": {},
                }
            }
        monkeypatch.setattr("web.routers.scanner.load_config", mock_load_config)

        response = client.get(f"/api/gallery/image?path={str(img)}")
        assert response.status_code == 403, "白名單外路徑應被 403 擋下"

    def test_image_path_traversal_403(self, client, tmp_path, monkeypatch):
        """../ 路徑穿越被 normpath + 白名單兜底擋下回傳 403"""
        allowed_dir = tmp_path / "gallery"
        allowed_dir.mkdir()
        sub = allowed_dir / "sub"
        sub.mkdir()

        # secret.jpg 在 allowed_dir 之外
        secret = tmp_path / "secret.jpg"
        secret.write_bytes(b'\xff\xd8\xff' + b'\x00' * 100)

        def mock_load_config():
            return {
                "gallery": {
                    "directories": [str(allowed_dir)],
                    "path_mappings": {},
                }
            }
        monkeypatch.setattr("web.routers.scanner.load_config", mock_load_config)

        # 用 ../ 穿越到 allowed_dir 之外
        traversal_path = str(allowed_dir / "sub" / ".." / ".." / "secret.jpg")
        response = client.get(f"/api/gallery/image?path={traversal_path}")
        assert response.status_code == 403, "路徑穿越應被 403 擋下"

    def test_image_non_image_extension_403(self, client, tmp_path, monkeypatch):
        """非圖片副檔名（.py、.txt）回傳 403"""
        allowed_dir = tmp_path / "gallery"
        allowed_dir.mkdir()
        py_file = allowed_dir / "exploit.py"
        py_file.write_bytes(b"import os")

        def mock_load_config():
            return {
                "gallery": {
                    "directories": [str(allowed_dir)],
                    "path_mappings": {},
                }
            }
        monkeypatch.setattr("web.routers.scanner.load_config", mock_load_config)

        response = client.get(f"/api/gallery/image?path={str(py_file)}")
        assert response.status_code == 403, ".py 副檔名應被 403 擋下"

        txt_file = allowed_dir / "config.txt"
        txt_file.write_bytes(b"secret=abc")
        response = client.get(f"/api/gallery/image?path={str(txt_file)}")
        assert response.status_code == 403, ".txt 副檔名應被 403 擋下"

    def test_image_symlink_traversal_blocked(self, client, tmp_path, monkeypatch):
        """symlink target 在白名單外應回 403：realpath 追蹤 symlink target 後若越界則拒絕"""
        allowed_dir = tmp_path / "gallery"
        allowed_dir.mkdir()
        secret = tmp_path / "secret.jpg"
        secret.write_bytes(b'\xff\xd8\xff' + b'\x00' * 100)

        symlink = allowed_dir / "link.jpg"
        try:
            symlink.symlink_to(secret)
        except OSError:
            pytest.skip("系統不支援 symlink")

        def mock_load_config():
            return {
                "gallery": {
                    "directories": [str(allowed_dir)],
                    "path_mappings": {},
                }
            }
        monkeypatch.setattr("web.routers.scanner.load_config", mock_load_config)

        # realpath 追蹤 symlink target 到白名單外 → 403
        response = client.get(f"/api/gallery/image?path={str(symlink)}")
        assert response.status_code == 403, \
            "realpath 追蹤 symlink target：target 在白名單外應回傳 403"

    def test_endpoint_works_when_realpath_would_raise(self, client, tmp_path, monkeypatch):
        """FUSE/WinFsp 相容：mock os.path.realpath 丟 OSError 時 endpoint 走 except 分支降級 normpath，仍回傳 200"""
        import os
        from unittest.mock import Mock

        allowed_dir = tmp_path / "gallery"
        allowed_dir.mkdir()
        img = allowed_dir / "cover.jpg"
        img.write_bytes(b'\xff\xd8\xff' + b'\x00' * 100)

        def mock_load_config():
            return {
                "gallery": {
                    "directories": [str(allowed_dir)],
                    "path_mappings": {},
                }
            }
        monkeypatch.setattr("web.routers.scanner.load_config", mock_load_config)
        monkeypatch.setattr(os.path, "realpath", Mock(side_effect=OSError("WinError 1005")))

        response = client.get(f"/api/gallery/image?path={str(img)}")
        assert response.status_code == 200, \
            "realpath OSError 時應降級 normpath，FUSE/WinFsp 掛載下 endpoint 應回傳 200 而非 500"

    def test_image_fuse_symlink_fallback(self, client, tmp_path, monkeypatch):
        """FUSE 環境 mock realpath raise OSError → 降級 normpath → symlink 在白名單內 → 200
        明確記錄 FUSE 下接受 symlink escape 殘留風險（target 不被追蹤）"""
        import os
        from unittest.mock import Mock

        allowed_dir = tmp_path / "gallery"
        allowed_dir.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        target = outside / "target.jpg"
        target.write_bytes(b'\xff\xd8\xff' + b'\x00' * 100)
        link = allowed_dir / "link.jpg"
        try:
            link.symlink_to(target)
        except OSError:
            pytest.skip("系統不支援 symlink")

        def mock_load_config():
            return {
                "gallery": {
                    "directories": [str(allowed_dir)],
                    "path_mappings": {},
                }
            }
        monkeypatch.setattr("web.routers.scanner.load_config", mock_load_config)
        # mock realpath raise OSError（模擬 WinFsp GetFinalPathNameByHandle 失敗）
        monkeypatch.setattr(os.path, "realpath", Mock(side_effect=OSError("WinError 1005")))

        response = client.get(f"/api/gallery/image?path={str(link)}")
        assert response.status_code == 200, \
            "FUSE 降級 normpath 後 symlink 本身在白名單內應回 200（接受 FUSE 下 symlink escape 殘留風險）"

    def test_normpath_resolves_traversal(self, client, tmp_path, monkeypatch):
        """normpath 正確解析 .. 並交給白名單兜底：合法 .. → 200；穿越 → 403"""
        allowed_dir = tmp_path / "gallery"
        allowed_dir.mkdir()
        sub = allowed_dir / "sub"
        sub.mkdir()
        img = allowed_dir / "cover.jpg"
        img.write_bytes(b'\xff\xd8\xff' + b'\x00' * 100)

        def mock_load_config():
            return {
                "gallery": {
                    "directories": [str(allowed_dir)],
                    "path_mappings": {},
                }
            }
        monkeypatch.setattr("web.routers.scanner.load_config", mock_load_config)

        # Case A: sub/../cover.jpg → normpath → allowed_dir/cover.jpg → 200
        legal_path = str(sub / ".." / "cover.jpg")
        response = client.get(f"/api/gallery/image?path={legal_path}")
        assert response.status_code == 200, \
            "合法 .. 移動（仍在白名單內）應回傳 200"

        # Case B: allowed_dir/../../etc → normpath → 白名單外 → 403
        traversal_path = str(allowed_dir / ".." / ".." / "etc" / "passwd.jpg")
        response = client.get(f"/api/gallery/image?path={traversal_path}")
        assert response.status_code == 403, \
            "穿越出白名單的 .. 路徑應被 403 擋下"


class TestMappedDriveWhitelist:
    """T1–T5: SMB 連線磁碟機 / DFS-UNC 白名單比對不對稱修正（TASK-73）

    環境無關：不使用真實 K:\\ 字串；改用兩個 POSIX tmp 子樹模擬
    「config 存放的路徑格式」與「realpath 回傳的真實路徑格式」之間的差異。
    """

    @pytest.fixture
    def image_client(self):
        from web.app import app
        from fastapi.testclient import TestClient
        return TestClient(app)

    @pytest.fixture
    def video_client(self):
        from web.app import app
        from fastapi.testclient import TestClient
        return TestClient(app)

    def _clear_cache(self):
        """在每個測試開始前清除 TTL 快取，避免跨測試污染。"""
        import web.routers.scanner as _scanner
        _scanner._dir_forms_cache.clear()

    # ── T1: SMB mapped drive — get_image → 200 ────────────────────────────────
    def test_smb_mapped_drive_get_image_200(self, image_client, tmp_path, monkeypatch):
        """T1: config dir 為 kform_dir，realpath 把請求路徑映射到 real_dir；
        修正前 403（兩端格式不同），修正後白名單比對雙向正規化 → 200。"""
        import os
        self._clear_cache()

        kform_dir = tmp_path / "kdrive" / "media"
        real_dir  = tmp_path / "realshare" / "media"
        real_dir.mkdir(parents=True, exist_ok=True)
        cover = real_dir / "cover.jpg"
        cover.write_bytes(b'\xff\xd8\xff' + b'\x00' * 100)

        # realpath: kform_dir -> real_dir (both file and dir)
        mapping = {
            str(kform_dir / "cover.jpg"): str(cover),
            str(kform_dir): str(real_dir),
        }
        def fake_realpath(p):
            return mapping.get(str(p), os.path.normpath(str(p)))

        monkeypatch.setattr(os.path, "realpath", fake_realpath)

        def mock_load_config():
            return {
                "gallery": {
                    "directories": [str(kform_dir)],
                    "path_mappings": {},
                }
            }
        monkeypatch.setattr("web.routers.scanner.load_config", mock_load_config)

        response = image_client.get(f"/api/gallery/image?path={str(kform_dir / 'cover.jpg')}")
        assert response.status_code == 200, (
            "T1: SMB mapped drive — realpath 改寫後請求 URI 和 config dir URI 應雙向對齊 → 200，"
            f"實際: {response.status_code}"
        )

    # ── T2: SMB mapped drive — get_video → 200 ────────────────────────────────
    def test_smb_mapped_drive_get_video_200(self, video_client, tmp_path, monkeypatch):
        """T2: 同 T1 邏輯，副檔名 .mp4，走 get_video 端點。"""
        import os
        self._clear_cache()

        kform_dir = tmp_path / "kdrive" / "media"
        real_dir  = tmp_path / "realshare" / "media"
        real_dir.mkdir(parents=True, exist_ok=True)
        video = real_dir / "movie.mp4"
        video.write_bytes(b'\x00' * 100)

        mapping = {
            str(kform_dir / "movie.mp4"): str(video),
            str(kform_dir): str(real_dir),
        }
        def fake_realpath(p):
            return mapping.get(str(p), os.path.normpath(str(p)))

        monkeypatch.setattr(os.path, "realpath", fake_realpath)

        def mock_load_config():
            return {
                "scraper": {
                    "video_extensions": [".mp4"],
                },
                "gallery": {
                    "directories": [str(kform_dir)],
                    "path_mappings": {},
                }
            }
        monkeypatch.setattr("web.routers.scanner.load_config", mock_load_config)

        response = video_client.get(f"/api/gallery/video?path={str(kform_dir / 'movie.mp4')}")
        assert response.status_code == 200, (
            "T2: SMB mapped drive — get_video realpath 改寫後應雙向對齊 → 200，"
            f"實際: {response.status_code}"
        )

    # ── T3: DFS-aliased UNC — get_image → 200 ─────────────────────────────────
    def test_dfs_aliased_unc_get_image_200(self, image_client, tmp_path, monkeypatch):
        """T3: 模擬 DFS alias（\\\\server\\pikpak → \\\\ERICPAN\\usbshare3-2）；
        config 存 dfs_dir，realpath 把請求映射到 target_dir。"""
        import os
        self._clear_cache()

        dfs_dir    = tmp_path / "eric" / "pikpak" / "media"
        target_dir = tmp_path / "eric" / "usbshare" / "media"
        target_dir.mkdir(parents=True, exist_ok=True)
        cover = target_dir / "cover.jpg"
        cover.write_bytes(b'\xff\xd8\xff' + b'\x00' * 100)

        mapping = {
            str(dfs_dir / "cover.jpg"): str(cover),
            str(dfs_dir): str(target_dir),
        }
        def fake_realpath(p):
            return mapping.get(str(p), os.path.normpath(str(p)))

        monkeypatch.setattr(os.path, "realpath", fake_realpath)

        def mock_load_config():
            return {
                "gallery": {
                    "directories": [str(dfs_dir)],
                    "path_mappings": {},
                }
            }
        monkeypatch.setattr("web.routers.scanner.load_config", mock_load_config)

        response = image_client.get(f"/api/gallery/image?path={str(dfs_dir / 'cover.jpg')}")
        assert response.status_code == 200, (
            "T3: DFS-aliased UNC — realpath 改寫後請求端 URI 應能命中 dir 的 realpath-form → 200，"
            f"實際: {response.status_code}"
        )

    # ── T4: 間歇不對稱（dual-form 保證）────────────────────────────────────────
    def test_intermittent_asymmetry_dual_form_200(self, image_client, tmp_path, monkeypatch):
        """T4: 先讓 dir 的 realpath 成功（暖快取 dual-form），
        然後讓「請求端的 realpath」拋 OSError（NAS 間歇斷線 → normpath 降級）；
        dir 快取的 normpath-form 仍在 tuple 中 → 比對命中 → 200。
        不清快取（與 T1–T3 不同，意在驗證快取 warmup 後的降級行為）。

        設計：kform_dir 是「config + request 路徑的未 realpath 形式」，
              real_dir 是 realpath 指向的實際目標。
              Phase 1: realpath 成功（cover.jpg + kform_dir 都被映射到 real_dir）
                       → 第一個請求走通（200）且暖 dir 快取的 dual-form。
              Phase 2: realpath 全 OSError（NAS 間歇斷線）
                       → request_uri = to_file_uri(normpath(kform_dir/cover.jpg))
                       → dir 快取 normpath-form = to_file_uri(normpath(kform_dir))
                       → 請求 uri 在 dir normpath-form 之下 → 白名單通過
                       → 但 normpath(kform_dir/cover.jpg) 必須真實存在（os.path.exists）
                       → 因此 kform_dir 必須真實建立且 cover.jpg 放在裡面。"""
        import os
        from unittest.mock import Mock
        self._clear_cache()

        # 兩個 subtree：kform_dir（normpath 形式）和 real_dir（realpath target）
        kform_dir = tmp_path / "kdrive" / "media"
        kform_dir.mkdir(parents=True, exist_ok=True)
        # kform_dir 也有實際檔案（供 phase 2 normpath fallback 後 os.path.exists 用）
        cover_kform = kform_dir / "cover.jpg"
        cover_kform.write_bytes(b'\xff\xd8\xff' + b'\x00' * 100)

        real_dir = tmp_path / "realshare" / "media"
        real_dir.mkdir(parents=True, exist_ok=True)
        cover_real = real_dir / "cover.jpg"
        cover_real.write_bytes(b'\xff\xd8\xff' + b'\x00' * 100)

        # Phase 1: realpath 把 kform_dir → real_dir（模擬 SMB mapped drive）
        mapping = {
            str(kform_dir / "cover.jpg"): str(cover_real),
            str(kform_dir): str(real_dir),
        }
        def fake_realpath_phase1(p):
            return mapping.get(str(p), os.path.normpath(str(p)))

        monkeypatch.setattr(os.path, "realpath", fake_realpath_phase1)

        def mock_load_config():
            return {
                "gallery": {
                    "directories": [str(kform_dir)],
                    "path_mappings": {},
                }
            }
        monkeypatch.setattr("web.routers.scanner.load_config", mock_load_config)

        # 第一次請求：realpath 成功，warm dir cache（dual-form），200（預期）
        response1 = image_client.get(f"/api/gallery/image?path={str(kform_dir / 'cover.jpg')}")
        assert response1.status_code == 200, f"T4 phase1（warm cache）應 200，實際: {response1.status_code}"

        # Phase 2: realpath 全 OSError（NAS 間歇斷線）
        # dir 快取已存在（TTL 未過），不再呼叫 realpath 重算
        # request: normpath(kform_dir/cover.jpg) → 在 kform_dir 下 → normpath-form 命中
        monkeypatch.setattr(os.path, "realpath", Mock(side_effect=OSError("NAS 斷線")))

        # 第二次請求：請求端降 normpath；dir 快取的 normpath-form 應命中 → 200
        response2 = image_client.get(f"/api/gallery/image?path={str(kform_dir / 'cover.jpg')}")
        assert response2.status_code == 200, (
            "T4: 間歇斷線 — 請求端 realpath OSError 降 normpath，"
            "dir 快取的 normpath-form 仍應命中 → 200，"
            f"實際: {response2.status_code}"
        )

    # ── T5: 契約守衛（behavioral regression guard）─────────────────────────────
    def test_dir_whitelist_canonicalization_is_symmetric(self, image_client, tmp_path, monkeypatch):
        """T5: 契約守衛 — config dir 端必須也經過 realpath 正規化（與請求端對稱）。
        設定：config dir = kform_dir（未被 realpath），請求路徑的 realpath → real_dir；
        修正前：兩端格式不同 → 403（RED）；修正後：dir 端也跑 realpath → dual-form → 200（GREEN）。
        此測試作為 TASK-73 的 regression guard 永久留存。"""
        import os
        self._clear_cache()

        kform_dir = tmp_path / "kguard" / "media"
        real_dir  = tmp_path / "realguard" / "media"
        real_dir.mkdir(parents=True, exist_ok=True)
        cover = real_dir / "cover.jpg"
        cover.write_bytes(b'\xff\xd8\xff' + b'\x00' * 100)

        mapping = {
            str(kform_dir / "cover.jpg"): str(cover),
            str(kform_dir): str(real_dir),
        }
        def fake_realpath(p):
            return mapping.get(str(p), os.path.normpath(str(p)))

        monkeypatch.setattr(os.path, "realpath", fake_realpath)

        def mock_load_config():
            return {
                "gallery": {
                    "directories": [str(kform_dir)],
                    "path_mappings": {},
                }
            }
        monkeypatch.setattr("web.routers.scanner.load_config", mock_load_config)

        response = image_client.get(f"/api/gallery/image?path={str(kform_dir / 'cover.jpg')}")
        assert response.status_code == 200, (
            "T5 契約守衛: config dir 端白名單比對必須對稱地跑 realpath-or-normpath 正規化；"
            "若此測試失敗表示白名單比對不對稱已回歸。"
            f"實際: {response.status_code}"
        )


class TestMappedDriveWhitelistWslUncSymmetry:
    """TASK-91-T2b（Opus 加測）：WSL + UNC path_mappings 環境下白名單對稱性
    end-to-end 驗證。

    - get_image：T2a 呼叫端（showcase/similar/motion_lab）反解後會產生
      `?path=<反解後本機路徑>` 這種請求，config directories 存的是同一份本機路徑
      （native `/home/user/nas` 形式）——這條路徑本來就該直接命中白名單，證明
      T2a 的反解不會製造白名單誤殺。
    - get_video：T2b #12 修正後，`local_path = uri_to_local_fs_path(path, ...)`
      反解成本機路徑，`to_file_uri(local_path, path_mappings)` 再正向重新映射回
      mapped-namespace request_uri，跟 `_dir_candidate_forms` 比對仍需命中 → 200/206。
    """

    @pytest.fixture
    def image_client(self):
        from web.app import app
        from fastapi.testclient import TestClient
        return TestClient(app)

    @pytest.fixture
    def video_client(self):
        from web.app import app
        from fastapi.testclient import TestClient
        return TestClient(app)

    def _clear_cache(self):
        import web.routers.scanner as _scanner
        _scanner._dir_forms_cache.clear()

    def test_get_image_reverse_mapped_native_path_passes_whitelist(
        self, image_client, tmp_path, monkeypatch
    ):
        """get_image：請求 `?path=<反解後本機路徑>`（T2a 呼叫端 WSL+UNC 反解後產生的
        形式），config directories 也是同一份本機路徑 → 200（非 403）。"""
        import core.path_utils as path_utils
        self._clear_cache()

        monkeypatch.setattr(path_utils, "CURRENT_ENV", "wsl")

        local_dir = tmp_path / "home_user_nas"
        local_dir.mkdir(parents=True, exist_ok=True)
        cover = local_dir / "x.jpg"
        cover.write_bytes(b'\xff\xd8\xff' + b'\x00' * 100)

        mappings = {str(local_dir): "//NAS/share"}

        def mock_load_config():
            return {
                "gallery": {
                    "directories": [str(local_dir)],
                    "path_mappings": mappings,
                }
            }
        monkeypatch.setattr("web.routers.scanner.load_config", mock_load_config)

        response = image_client.get(f"/api/gallery/image?path={str(cover)}")
        assert response.status_code == 200, (
            "反解後的本機路徑（跟 config directories 同一份格式）應直接命中白名單，"
            f"實際: {response.status_code}"
        )

    def test_get_video_mapped_unc_uri_reverse_maps_and_passes_whitelist(
        self, video_client, tmp_path, monkeypatch
    ):
        """get_video：請求 `?path=file://///NAS/share/x.mp4`（mapped-namespace URI）。
        TASK-91-T2b #12 修正後：local_path 反解成本機路徑（真實檔案在此），
        request_uri 用同一份 path_mappings 正向重新映射回 mapped-namespace，
        跟 `_dir_candidate_forms`（也用同一份 path_mappings 產生）比對仍命中 → 200/206。
        """
        import core.path_utils as path_utils
        self._clear_cache()

        monkeypatch.setattr(path_utils, "CURRENT_ENV", "wsl")

        local_dir = tmp_path / "home_user_nas"
        local_dir.mkdir(parents=True, exist_ok=True)
        video = local_dir / "x.mp4"
        video.write_bytes(b'\x00' * 1000)

        mappings = {str(local_dir): "//NAS/share"}

        def mock_load_config():
            return {
                "scraper": {"video_extensions": [".mp4"]},
                "gallery": {
                    "directories": [str(local_dir)],
                    "path_mappings": mappings,
                },
            }
        monkeypatch.setattr("web.routers.scanner.load_config", mock_load_config)
        monkeypatch.setattr("web.routers.scanner.os.path.getsize", lambda p: 1000)

        response = video_client.get("/api/gallery/video?path=file://///NAS/share/x.mp4")
        assert response.status_code in (200, 206), (
            "反解 → 正向重新映射對稱性應保住白名單比對，不應 403/404，"
            f"實際: {response.status_code}"
        )


class TestSampleImagesAPI:
    """sample_images 欄位 — Showcase API integration 測試"""

    @pytest.fixture
    def populated_db_with_sample_images(self, make_populated_db, tmp_path):
        from core.database import Video
        # 建立假圖片檔案供 URI 使用
        img1 = tmp_path / "extrafanart" / "fanart1.jpg"
        img1.parent.mkdir(parents=True, exist_ok=True)
        img1.write_bytes(b"img")
        img2 = tmp_path / "extrafanart" / "fanart2.jpg"
        img2.write_bytes(b"img")

        videos = [
            Video(
                path=to_file_uri("/home/user/media/ABC-001.mp4"),
                number="ABC-001",
                title="Video with sample images",
                original_title="",
                actresses=[],
                maker="",
                release_date="",
                tags=[],
                size_bytes=0,
                cover_path="",
                mtime=0.0,
                sample_images=[
                    to_file_uri(str(img1)),
                    to_file_uri(str(img2)),
                ],
            ),
            Video(
                path=to_file_uri("/home/user/media/ABC-002.mp4"),
                number="ABC-002",
                title="Video without sample images",
                original_title="",
                actresses=[],
                maker="",
                release_date="",
                tags=[],
                size_bytes=0,
                cover_path="",
                mtime=0.0,
                sample_images=[],
            ),
        ]
        return make_populated_db(videos)

    @pytest.fixture
    def client_media(self, make_client, populated_db_with_sample_images):
        return make_client(
            ["core.database.connection.get_db_path", "web.routers.showcase.get_db_path", "web.routers.showcase.load_config"],
            mock_db_path=populated_db_with_sample_images,
            config_override={
                "gallery": {
                    "directories": ["/home/user/media"],
                    "path_mappings": {},
                    "min_size_mb": 0,
                    "thumbnail_width": 400,
                },
                "scraper": {"video_extensions": [".mp4"], "image_extensions": [".jpg"]},
                "database": {"path": ":memory:"},
                "translate": {"provider": "ollama", "ollama_model": "llama3"},
            },
        )

    def test_sample_images_key_present(self, client_media, populated_db_with_sample_images, monkeypatch):
        """API response 包含 sample_images key（即使無資料也需存在）"""
        monkeypatch.setattr("web.routers.showcase.get_db_path", lambda: populated_db_with_sample_images)
        response = client_media.get("/api/showcase/videos")
        assert response.status_code == 200
        data = response.json()
        for video in data["videos"]:
            assert "sample_images" in video, "每筆 video 必須含 sample_images 欄位"

    def test_sample_images_empty_list_when_no_images(self, client_media, populated_db_with_sample_images, monkeypatch):
        """v.sample_images 為 [] → 回傳 sample_images: []，不拋 exception"""
        monkeypatch.setattr("web.routers.showcase.get_db_path", lambda: populated_db_with_sample_images)
        response = client_media.get("/api/showcase/videos")
        assert response.status_code == 200
        data = response.json()
        # 第二筆無 sample_images
        video2 = next(v for v in data["videos"] if v["number"] == "ABC-002")
        assert video2["sample_images"] == []

    def test_sample_images_uri_converted_to_api_url(self, client_media, populated_db_with_sample_images, monkeypatch):
        """含有效 file:/// URI → 轉換為 /api/gallery/image?path=...（路徑已 percent-encode）"""
        monkeypatch.setattr("web.routers.showcase.get_db_path", lambda: populated_db_with_sample_images)
        response = client_media.get("/api/showcase/videos")
        assert response.status_code == 200
        data = response.json()
        video1 = next(v for v in data["videos"] if v["number"] == "ABC-001")
        assert len(video1["sample_images"]) == 2
        for url in video1["sample_images"]:
            assert url.startswith("/api/gallery/image?path="), f"期望 /api/gallery/image?path=... 格式，實際: {url}"
            assert "fanart" in url


class TestSerializeVideoPathMappingsReverse:
    """TASK-91-T2a #1,#2: `_serialize_video` 的 cover_full_url / sample_images URL
    在 WSL + UNC path_mappings 環境下必須反解成真正能 open() 的本機路徑，
    而不是留下裸 uri_to_fs_path() 產生的映射端 UNC 字串（get_image 端沒有第二次反解機會）。
    """

    @pytest.fixture
    def wsl_video(self):
        from core.database import Video
        return Video(
            path="file://///NAS/share/video.mp4",
            number="TEST-001",
            title="WSL UNC Video",
            cover_path="file://///NAS/share/cover.jpg",
            sample_images=["file://///NAS/share/sample1.jpg"],
        )

    def test_cover_full_url_reverse_maps_wsl_unc(self, wsl_video, monkeypatch):
        import core.path_utils as path_utils
        from urllib.parse import unquote
        from web.routers.showcase import _serialize_video

        monkeypatch.setattr(path_utils, "CURRENT_ENV", "wsl")
        mappings = {"/home/user/nas": "//NAS/share"}

        result = _serialize_video(wsl_video, mappings, enabled=False)
        decoded = unquote(result["cover_full_url"])

        assert "/home/user/nas/cover.jpg" in decoded, (
            f"cover_full_url 應反解為本機路徑，實際: {decoded}"
        )
        assert "//NAS/share/cover.jpg" not in decoded, (
            f"cover_full_url 不應殘留裸 UNC 映射端字串，實際: {decoded}"
        )

    def test_sample_images_url_reverse_maps_wsl_unc(self, wsl_video, monkeypatch):
        import core.path_utils as path_utils
        from urllib.parse import unquote
        from web.routers.showcase import _serialize_video

        monkeypatch.setattr(path_utils, "CURRENT_ENV", "wsl")
        mappings = {"/home/user/nas": "//NAS/share"}

        result = _serialize_video(wsl_video, mappings, enabled=False)

        assert len(result["sample_images"]) == 1
        sample_url = unquote(result["sample_images"][0])
        assert "/home/user/nas/sample1.jpg" in sample_url, (
            f"sample_images URL 應反解為本機路徑，實際: {sample_url}"
        )
        assert "//NAS/share/sample1.jpg" not in sample_url, (
            f"sample_images URL 不應殘留裸 UNC 映射端字串，實際: {sample_url}"
        )
