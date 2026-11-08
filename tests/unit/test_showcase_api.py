"""測試 Showcase API"""
import pytest
from fastapi.testclient import TestClient

from core.database import Video, VideoRepository
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
        [
            "core.database.connection.get_db_path",
            "web.routers.showcase.get_db_path",
            "web.routers.showcase.load_config",
            # test_player_page_returns_html 打 /api/gallery/player（TASK-150a-T2 起
            # video_player() 搬到 web/routers/gallery_media.py），該端點自己也呼叫
            # get_db_path() 做分組查詢，未 mock 前會連上 output/openaver.db。
            "web.routers.gallery_media.get_db_path",
        ],
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
        monkeypatch.setattr("core.path_utils.CURRENT_ENV", "wsl")
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


class TestVideoProxy:
    """測試 GET /api/gallery/video 影片代理"""


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
        monkeypatch.setattr("web.routers.gallery_media.load_config", mock_load_config)

        response = client.get(f"/api/gallery/video?path={str(video)}")
        assert response.status_code == 403


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
        monkeypatch.setattr("web.routers.gallery_media.load_config", mock_load_config)

        response = client.get(
            f"/api/gallery/video?path={str(video)}",
            headers={"Range": "bytes=0-499"}
        )
        assert response.status_code == 206
        assert response.headers["content-range"] == "bytes 0-499/1000"
        assert len(response.content) == 500


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
        monkeypatch.setattr("web.routers.gallery_media.load_config", mock_load_config)

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
        monkeypatch.setattr("web.routers.gallery_media.load_config", mock_load_config)

        # realpath 追蹤 symlink target 到白名單外 → 403
        response = client.get(f"/api/gallery/video?path={str(symlink)}")
        assert response.status_code == 403, \
            "realpath 追蹤 symlink target：target 在白名單外應回傳 403"


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
        monkeypatch.setattr("web.routers.gallery_media.load_config", mock_load_config)

        response = client.get(f"/api/gallery/video?path={str(exe_file)}")
        assert response.status_code == 403, \
            ".exe should be blocked by proxy security (SAFE_PROXY_EXTENSIONS)"


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
        monkeypatch.setattr("web.routers.gallery_media.load_config", mock_load_config)

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
        monkeypatch.setattr("web.routers.gallery_media.load_config", mock_load_config)

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
        monkeypatch.setattr("web.routers.gallery_media.load_config", mock_load_config)

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
        monkeypatch.setattr("web.routers.gallery_media.load_config", mock_load_config)

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
        monkeypatch.setattr("web.routers.gallery_media.load_config", mock_load_config)

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
        monkeypatch.setattr("web.routers.gallery_media.load_config", mock_load_config)
        monkeypatch.setattr(os.path, "realpath", Mock(side_effect=OSError("WinError 1005")))

        response = client.get(f"/api/gallery/image?path={str(img)}")
        assert response.status_code == 200, \
            "realpath OSError 時應降級 normpath，FUSE/WinFsp 掛載下 endpoint 應回傳 200 而非 500"


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
        import web.routers.gallery_media as _media
        _media._dir_forms_cache.clear()

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
        monkeypatch.setattr("web.routers.gallery_media.load_config", mock_load_config)

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
        monkeypatch.setattr("web.routers.gallery_media.load_config", mock_load_config)

        response = video_client.get(f"/api/gallery/video?path={str(kform_dir / 'movie.mp4')}")
        assert response.status_code == 200, (
            "T2: SMB mapped drive — get_video realpath 改寫後應雙向對齊 → 200，"
            f"實際: {response.status_code}"
        )

    # ── T3: DFS-aliased UNC — get_image → 200 ─────────────────────────────────

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
        monkeypatch.setattr("web.routers.gallery_media.load_config", mock_load_config)

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
        import web.routers.gallery_media as _media
        _media._dir_forms_cache.clear()

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
        monkeypatch.setattr("web.routers.gallery_media.load_config", mock_load_config)

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
        monkeypatch.setattr("web.routers.gallery_media.load_config", mock_load_config)
        monkeypatch.setattr("web.routers.gallery_media.os.path.getsize", lambda p: 1000)

        response = video_client.get("/api/gallery/video?path=file://///NAS/share/x.mp4")
        assert response.status_code in (200, 206), (
            "反解 → 正向重新映射對稱性應保住白名單比對，不應 403/404，"
            f"實際: {response.status_code}"
        )


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

