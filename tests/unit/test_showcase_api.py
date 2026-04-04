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
        ["core.database.get_db_path", "web.routers.showcase.get_db_path", "web.routers.showcase.load_config"],
        mock_db_path=temp_db,
        config_override=showcase_config,
    )

@pytest.fixture
def populated_db(make_populated_db):
    videos = [
        Video(
            path="file:////home/user/media/SONE-205.mp4",
            number="SONE-205",
            title="Test Video 1",
            original_title="テストビデオ1",
            actresses=["坂道みる", "深田えいみ"],
            maker="S1 NO.1 STYLE",
            release_date="2024-01-15",
            tags=["単体作品", "ハイビジョン", "独占配信"],
            size_bytes=3145728000,
            cover_path="file:////home/user/media/SONE-205/poster.jpg",
            mtime=1705276800.0
        ),
        Video(
            path="file:///C:/Videos/ABW-001.mp4",
            number="ABW-001",
            title="Test Video 2",
            original_title="",
            actresses=["新ありな"],
            maker="Prestige",
            release_date="2024-02-01",
            tags=["スレンダー"],
            size_bytes=2147483648,
            cover_path="file:///C:/Videos/ABW-001/cover.jpg",
            mtime=1706745600.0
        ),
        Video(
            path="file:///D:/AV/FC2-001.mp4",
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
            path="file://///NAS/share/PRED-001.mp4",
            number="PRED-001",
            title="Test Video 4 - UNC Path",
            original_title="",
            actresses=["篠田ゆう"],
            maker="Premium",
            release_date="2024-03-01",
            tags=[],
            size_bytes=1073741824,
            cover_path="file://///NAS/share/PRED-001/cover.jpg",
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
                path="file:////home/user/media/SONE-205.mp4",
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
                path="file:///C:/Videos/ABW-001.mp4",
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

    def test_wsl_mount_path_filtering(self, client, temp_db, monkeypatch):
        """WSL /mnt/c/ 設定值能正確匹配 DB 中的 file:///C:/ URI"""
        repo = VideoRepository(temp_db)
        repo.upsert_batch([
            Video(
                path="file:///C:/Videos/ABW-001.mp4",
                number="ABW-001", title="WSL mount test",
                actresses=["新ありな"], tags=[], size_bytes=0, mtime=0.0,
            ),
            Video(
                path="file:///D:/AV/OTHER-001.mp4",
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
                path="file:///E:/media/SONE-205.mp4",
                number="SONE-205", title="Under media",
                actresses=[], tags=[], size_bytes=0, mtime=0.0,
            ),
            Video(
                path="file:///E:/media2/ABW-001.mp4",
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
        """路徑穿越 ../ 被 realpath 擋下回傳 403"""
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
        """symlink 穿越被 realpath 擋下回傳 403"""
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

        response = client.get(f"/api/gallery/video?path={str(symlink)}")
        assert response.status_code == 403, "symlink 穿越應被 403 擋下"

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
        """../ 路徑穿越被 realpath 擋下回傳 403"""
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
        """symlink 穿越被 realpath 擋下回傳 403"""
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

        response = client.get(f"/api/gallery/image?path={str(symlink)}")
        assert response.status_code == 403, "symlink 穿越應被 403 擋下"


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
                path="file:////home/user/media/ABC-001.mp4",
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
                path="file:////home/user/media/ABC-002.mp4",
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
            ["core.database.get_db_path", "web.routers.showcase.get_db_path", "web.routers.showcase.load_config"],
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
