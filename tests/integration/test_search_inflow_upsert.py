"""
test_search_inflow_upsert.py — TDD-lite: POST /api/scrape-single 後端 in-flow upsert

4 個 case（既有）：
1. synced  — 在 directories 內，scan_file 回有效 VideoInfo，upsert 成功 → db_sync_status: "synced"
2. not_linked — 不在 directories 內 → find_matched_directory 回 None → db_sync_status: "not_linked"
3. failed  — upsert 拋例外 → except 包裹，response 仍 success: true，db_sync_status: "failed"
4. missing_filename — organize_file 回傳缺 new_filename → db_sync_status: "not_linked"，不 crash

B1 dead-card 守衛（新增）：
I1 — B1 端到端死卡守衛（external_manager=off）
I2 — B1 端到端死卡守衛（external_manager=jellyfin，驗 mode-agnostic）
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


# ─── helper stubs ────────────────────────────────────────────────────────────

def _make_video_info(num="ABC-001"):
    """回傳最小可用的 VideoInfo stub。"""
    from core.gallery_scanner import VideoInfo
    info = VideoInfo()
    info.num = num
    info.path = "file:///tmp/ABC-001/ABC-001.mp4"
    info.title = "Test Title"
    return info


def _organize_ok(new_filename="/tmp/ABC-001/ABC-001.mp4"):
    """organize_file 回傳成功 dict（含 new_filename）。"""
    return {
        "success": True,
        "new_filename": new_filename,
        "new_folder": "/tmp/ABC-001",
        "original_path": "/tmp/ABC-001.mp4",
    }


def _scrape_request_body(file_path="/tmp/ABC-001.mp4"):
    return {
        "file_path": file_path,
        "number": "ABC-001",
        "metadata": {
            "title": "Test Title",
            "number": "ABC-001",
            "cover": "",
            "actresses": [],
            "tags": [],
            "release": "",
        },
    }


# ─── case 1: synced ──────────────────────────────────────────────────────────

def test_scrape_single_db_sync_status_synced(client):
    """
    在 directories 內 + scan_file 回有效 VideoInfo + upsert 成功
    → response db_sync_status == "synced"
    """
    video_info = _make_video_info()

    with (
        patch("web.routers.scraper.organize_file", return_value=_organize_ok()) as _mock_org,
        patch("core.db_inflow.load_config", return_value={
            "gallery": {"directories": ["/tmp"], "path_mappings": {}}
        }),
        patch("core.db_inflow.find_matched_directory", return_value="/tmp"),
        patch("core.db_inflow.VideoScanner") as MockScanner,
        patch("core.db_inflow.VideoRepository") as MockRepo,
        patch("core.db_inflow.Video") as MockVideo,
    ):
        MockScanner.return_value.scan_file.return_value = video_info
        mock_video = MagicMock()
        mock_video.path = "file:///tmp/ABC-001/ABC-001.mp4"
        MockVideo.from_video_info.return_value = mock_video
        MockRepo.return_value.repath.return_value = None  # B1: repath replaces upsert

        resp = client.post("/api/scrape-single", json=_scrape_request_body())

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["db_sync_status"] == "synced"


# ─── case 2: not_linked ──────────────────────────────────────────────────────

def test_scrape_single_db_sync_status_not_linked(client):
    """
    不在 directories 內 → find_matched_directory 回 None
    → db_sync_status == "not_linked"，不呼叫 scan_file / upsert
    """
    with (
        patch("web.routers.scraper.organize_file", return_value=_organize_ok()),
        patch("core.db_inflow.load_config", return_value={
            "gallery": {"directories": ["/other"], "path_mappings": {}}
        }),
        patch("core.db_inflow.find_matched_directory", return_value=None),
        patch("core.db_inflow.VideoScanner") as MockScanner,
        patch("core.db_inflow.VideoRepository") as MockRepo,
    ):
        resp = client.post("/api/scrape-single", json=_scrape_request_body())

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["db_sync_status"] == "not_linked"
    MockScanner.return_value.scan_file.assert_not_called()
    MockRepo.return_value.upsert.assert_not_called()


# ─── case 3: failed (upsert 拋例外) ──────────────────────────────────────────

def test_scrape_single_db_sync_status_failed_on_upsert_exception(client):
    """
    upsert 拋 Exception → except 包裹
    → response 仍 success: true，db_sync_status == "failed"（整理本身不受影響）
    """
    video_info = _make_video_info()

    with (
        patch("web.routers.scraper.organize_file", return_value=_organize_ok()),
        patch("core.db_inflow.load_config", return_value={
            "gallery": {"directories": ["/tmp"], "path_mappings": {}}
        }),
        patch("core.db_inflow.find_matched_directory", return_value="/tmp"),
        patch("core.db_inflow.VideoScanner") as MockScanner,
        patch("core.db_inflow.VideoRepository") as MockRepo,
        patch("core.db_inflow.Video") as MockVideo,
    ):
        MockScanner.return_value.scan_file.return_value = video_info
        mock_video = MagicMock()
        mock_video.path = "file:///tmp/ABC-001/ABC-001.mp4"
        MockVideo.from_video_info.return_value = mock_video
        # B1: now calls repath() instead of upsert()
        MockRepo.return_value.repath.side_effect = Exception("DB write error")

        resp = client.post("/api/scrape-single", json=_scrape_request_body())

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["db_sync_status"] == "failed"


# ─── case 5: VideoScanner 用 path_mappings= 構建 ────────────────────────────────

def test_scrape_single_video_scanner_receives_path_mappings(client):
    """
    try_inflow_upsert 必須用 path_mappings=... 構建 VideoScanner（P1 fix 驗證）。
    spy VideoScanner constructor，assert call kwargs 含 path_mappings。
    """
    video_info = _make_video_info()
    path_mappings = {"/mnt/e": "E:"}

    with (
        patch("web.routers.scraper.organize_file", return_value=_organize_ok()),
        patch("core.db_inflow.load_config", return_value={
            "gallery": {"directories": ["/tmp"], "path_mappings": path_mappings}
        }),
        patch("core.db_inflow.find_matched_directory", return_value="/tmp"),
        patch("core.db_inflow.VideoScanner") as MockScanner,
        patch("core.db_inflow.VideoRepository") as MockRepo,
        patch("core.db_inflow.Video") as MockVideo,
    ):
        MockScanner.return_value.scan_file.return_value = video_info
        mock_video = MagicMock()
        mock_video.path = "file:///tmp/ABC-001/ABC-001.mp4"
        MockVideo.from_video_info.return_value = mock_video
        MockRepo.return_value.repath.return_value = None  # B1: repath replaces upsert

        resp = client.post("/api/scrape-single", json=_scrape_request_body())

    assert resp.status_code == 200
    assert resp.json()["db_sync_status"] == "synced"
    # VideoScanner 必須以 path_mappings= 構建
    MockScanner.assert_called_once_with(path_mappings=path_mappings)


# ─── case 4: missing new_filename ─────────────────────────────────────────────

def test_scrape_single_db_sync_status_not_linked_on_missing_filename(client):
    """
    organize_file 回傳缺 new_filename（或空字串）
    → skip try_inflow_upsert，log warning
    → db_sync_status == "not_linked"，不 crash
    """
    organize_result = {
        "success": True,
        "new_filename": "",          # 空字串 — 缺失情境
        "new_folder": "/tmp/ABC-001",
        "original_path": "/tmp/ABC-001.mp4",
    }

    with (
        patch("web.routers.scraper.organize_file", return_value=organize_result),
        patch("core.db_inflow.VideoScanner") as MockScanner,
        patch("core.db_inflow.VideoRepository") as MockRepo,
    ):
        resp = client.post("/api/scrape-single", json=_scrape_request_body())

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["db_sync_status"] == "not_linked"
    MockScanner.return_value.scan_file.assert_not_called()
    MockRepo.return_value.repath.assert_not_called()


# ─── T-3: U7 readonly organize guard ─────────────────────────────────────────
#
# guard 插在 handler 最前段（file_path = request.file_path 之後、extract_number/
# search_jav/organize_file 之前）。只依 file_path 判斷所屬來源是否 readonly。
#
# patch targets:
#   organize_file  → web.routers.scraper.organize_file
#   search_jav     → web.routers.scraper.search_jav
#   extract_number → core.scraper.extract_number（handler 內 function-local import）
#   config 注入    → web.routers.scraper.load_config（iter_gallery_sources 用 real）


def _readonly_gallery_config(path, path_mappings=None, readonly=True):
    return {
        "gallery": {
            "directories": [{"path": path, "readonly": readonly}],
            "path_mappings": path_mappings or {},
        }
    }


def _scrape_body_no_metadata(file_path, number="ABC-001"):
    """不帶 metadata → 非 readonly 時會走 search_jav（讓 assert_not_called 有意義）。"""
    body = {"file_path": file_path}
    if number is not None:
        body["number"] = number
    return body


# case 1: readonly 來源擋 organize（核心）— 三下游 assert_not_called
def test_scrape_single_readonly_blocks_organize(client):
    with (
        patch("web.routers.scraper.load_config",
              return_value=_readonly_gallery_config("/tmp/ro_src")),
        patch("web.routers.scraper.organize_file") as mock_org,
        patch("web.routers.scraper.search_jav") as mock_search,
        patch("core.scraper.extract_number", return_value="ABC-001") as mock_extract,
    ):
        # number=None → 無 guard 時 `if not number:` 為真 → extract_number 會被呼叫；
        # 有 guard 時 guard 早於番號解析 → 三下游皆 assert_not_called 皆為 live lock。
        resp = client.post(
            "/api/scrape-single",
            json=_scrape_body_no_metadata("/tmp/ro_src/ABC-001.mp4", number=None),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "唯讀" in data["error"]
    mock_org.assert_not_called()
    mock_search.assert_not_called()
    mock_extract.assert_not_called()


# case 2: 無番號 + 檔名不可解析 在 readonly 來源下 → 仍回唯讀提示（Acceptance #12 哨兵）
def test_scrape_single_readonly_no_number_still_readonly_prompt(client):
    with (
        patch("web.routers.scraper.load_config",
              return_value=_readonly_gallery_config("/tmp/ro_src")),
        patch("web.routers.scraper.organize_file") as mock_org,
        patch("web.routers.scraper.search_jav") as mock_search,
    ):
        # 不帶 number、檔名不可解析番號；不 patch extract_number（用 real）
        resp = client.post(
            "/api/scrape-single",
            json=_scrape_body_no_metadata("/tmp/ro_src/random.mp4", number=None),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "唯讀" in data["error"]
    assert "無法識別番號" not in data["error"]
    mock_org.assert_not_called()
    mock_search.assert_not_called()


# case 3: UNC readonly 來源 → guard 不拋 ValueError（Codex P2 哨兵）
def test_scrape_single_readonly_unc_no_valueerror(client):
    with (
        patch("web.routers.scraper.load_config",
              return_value=_readonly_gallery_config(r"\\server\share")),
        patch("web.routers.scraper.organize_file") as mock_org,
        patch("web.routers.scraper.search_jav") as mock_search,
    ):
        resp = client.post(
            "/api/scrape-single",
            json=_scrape_body_no_metadata(r"\\server\share\ABC-001.mp4"),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "唯讀" in data["error"]
    mock_org.assert_not_called()
    mock_search.assert_not_called()


# case 4: 非 readonly 來源放行 → 走既有 organize
def test_scrape_single_non_readonly_passes_through(client):
    with (
        patch("web.routers.scraper.load_config",
              return_value=_readonly_gallery_config("/tmp/rw_src", readonly=False)),
        patch("web.routers.scraper.organize_file",
              return_value=_organize_ok("/tmp/rw_src/ABC-001/ABC-001.mp4")) as mock_org,
        patch("web.routers.scraper.search_jav"),
    ):
        resp = client.post(
            "/api/scrape-single",
            json=_scrape_request_body(file_path="/tmp/rw_src/ABC-001.mp4"),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    mock_org.assert_called_once()


# case 5: 不屬任何來源放行 → guard 不誤擋
def test_scrape_single_no_matching_source_passes_through(client):
    with (
        patch("web.routers.scraper.load_config",
              return_value={"gallery": {"directories": [], "path_mappings": {}}}),
        patch("web.routers.scraper.organize_file",
              return_value=_organize_ok("/elsewhere/ABC-001/ABC-001.mp4")) as mock_org,
        patch("web.routers.scraper.search_jav"),
    ):
        resp = client.post(
            "/api/scrape-single",
            json=_scrape_request_body(file_path="/elsewhere/ABC-001.mp4"),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    mock_org.assert_called_once()


# case 6: 訊息描述清楚（AI 友善）
def test_scrape_single_readonly_message_descriptive(client):
    with (
        patch("web.routers.scraper.load_config",
              return_value=_readonly_gallery_config("/tmp/ro_src")),
        patch("web.routers.scraper.organize_file"),
        patch("web.routers.scraper.search_jav"),
    ):
        resp = client.post(
            "/api/scrape-single",
            json=_scrape_body_no_metadata("/tmp/ro_src/ABC-001.mp4"),
        )

    error = resp.json()["error"]
    assert "唯讀" in error
    assert len(error) > 15  # 非單一 code，描述清楚


# case 7: file_path 是 canonical file:/// URI（DB / 鄰近寫入路徑格式）在 readonly
#          來源下 → guard 仍須觸發（Codex P1：to_file_uri 會雙重包 file:///file:///
#          繞過 guard；coerce_to_file_uri 對已是 URI 原樣回才能命中）。
def test_scrape_single_readonly_file_uri_input_blocks_organize(client):
    from core.path_utils import to_file_uri
    # DB canonical file:/// URI（drive-letter，真實 Windows/WSL 部署形態）。
    # 舊碼 to_file_uri 對它再包一層 → file:///file:/// → guard 繞過（RED）；
    # coerce_to_file_uri 對已是 URI 原樣回 → guard 命中（GREEN）。
    src_path = "C:/ro_src"
    file_uri = to_file_uri("C:/ro_src/ABC-001.mp4", {})  # 'file:///C:/ro_src/ABC-001.mp4'
    with (
        patch("web.routers.scraper.load_config",
              return_value=_readonly_gallery_config(src_path)),
        patch("web.routers.scraper.organize_file") as mock_org,
        patch("web.routers.scraper.search_jav") as mock_search,
        patch("core.scraper.extract_number", return_value="ABC-001") as mock_extract,
    ):
        resp = client.post(
            "/api/scrape-single",
            json=_scrape_body_no_metadata(file_uri, number=None),
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "唯讀" in data["error"]
    mock_org.assert_not_called()
    mock_search.assert_not_called()
    mock_extract.assert_not_called()


# ─── B1 helpers ──────────────────────────────────────────────────────────────

def _seed_old_card_b1(repo, old_uri: str, user_tags=None, created_at_str: str = None):
    """Seed an old card in the given repo. Returns the stored Video row."""
    from core.database import Video
    with patch("core.similar.ranker_cache.SimilarRankerCache"):
        repo.upsert(Video(
            path=old_uri,
            number="ABC-001",
            title="Old Title",
            original_title="",
            actresses=[],
            maker="",
            director="",
            series=None,
            label="",
            tags=[],
            user_tags=user_tags or ["看過"],
            sample_images=[],
            duration=None,
            size_bytes=0,
            cover_path="old_cover.jpg",
            release_date="",
            mtime=0.0,
            nfo_mtime=0.0,
        ))
    if created_at_str:
        conn = repo._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE videos SET created_at = ? WHERE path = ?",
                (created_at_str, old_uri),
            )
            conn.commit()
        finally:
            conn.close()
    return repo.get_by_path(old_uri)


def _make_scan_info_for_new_b1(new_uri: str, num: str = "ABC-001"):
    """Build a VideoInfo stub for the newly-scanned file (no browse tags)."""
    from core.gallery_scanner import VideoInfo
    info = VideoInfo()
    info.path = new_uri
    info.num = num
    info.title = "New Title"
    info.originaltitle = ""
    info.actor = ""
    info.genre = ""
    info.maker = ""
    info.director = ""
    info.series = None
    info.label = ""
    info.user_tags = []   # scrape NFO does not carry browse tags
    info.sample_images = []
    info.duration = None
    info.size = 0
    info.img = ""
    info.date = ""
    info.mtime = 0
    return info


# ─── I1: B1 死卡守衛（external_manager=off） ────────────────────────────────

def test_b1_repath_no_dead_card_off(client, tmp_path):
    """
    I1 — B1 端到端死卡守衛（external_manager=off）：
    seed 舊卡（user_tags=['看過'] + 已知 created_at + 記下 id）
    → POST /api/scrape-single
    → count() 不增、舊 URI 消失、新 URI 有效、
      id==舊 id（browse 不跳位）、user_tags⊇['看過']、created_at==舊值
    """
    from core.database import Video, VideoRepository, init_db
    from core.path_utils import normalize_path, to_file_uri

    db_file = tmp_path / "b1_off_test.db"
    init_db(db_file)
    repo = VideoRepository(db_path=db_file)

    old_fs = str(tmp_path / "ABC-001.mp4")
    new_fs = str(tmp_path / "[ABC-001] New Title.mp4")
    old_uri = to_file_uri(normalize_path(old_fs), None)
    new_uri = to_file_uri(normalize_path(new_fs), None)
    old_created = "2024-02-01 10:00:00"

    old_row = _seed_old_card_b1(repo, old_uri, user_tags=["看過"], created_at_str=old_created)
    old_id = old_row.id
    count_before = repo.count()

    video_info = _make_scan_info_for_new_b1(new_uri)

    with (
        patch("web.routers.scraper.organize_file", return_value={
            "success": True,
            "new_filename": new_fs,
            "new_folder": str(tmp_path),
            "original_path": old_fs,
        }),
        patch("core.db_inflow.load_config", return_value={
            "gallery": {"directories": [str(tmp_path)], "path_mappings": None}
        }),
        patch("core.db_inflow.find_matched_directory", return_value=str(tmp_path)),
        patch("core.db_inflow.VideoScanner") as MockScanner,
        patch("core.db_inflow.VideoRepository", return_value=repo),
        patch("core.db_inflow.Video") as MockVideo,
        patch("core.similar.ranker_cache.SimilarRankerCache"),
        patch("web.routers.scraper.VideoRepository", return_value=repo),
    ):
        MockScanner.return_value.scan_file.return_value = video_info
        MockVideo.from_video_info.return_value = Video(
            path=new_uri, number="ABC-001", title="New Title",
            original_title="", actresses=[], maker="", director="",
            series=None, label="", tags=[], user_tags=[],
            sample_images=[], duration=None, size_bytes=0,
            cover_path="", release_date="", mtime=0.0, nfo_mtime=0.0,
        )

        resp = client.post("/api/scrape-single", json=_scrape_request_body(file_path=old_fs))

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["db_sync_status"] == "synced"

    # 死卡守衛：count 不增
    assert repo.count() == count_before, \
        f"count 應不增（{count_before}），得 {repo.count()}"

    # 舊路徑消失
    assert repo.get_by_path(old_uri) is None, "舊 URI 應消失（無死卡）"

    # 新路徑有效
    new_card = repo.get_by_path(new_uri)
    assert new_card is not None, "新 URI 應存在"

    # browse 不跳位：id 不變
    assert new_card.id == old_id, \
        f"id 應保留 {old_id}（browse ORDER BY id 不跳位），得 {new_card.id}"

    # browse tag 存活（union，非被 NFO 覆寫沖掉）
    assert "看過" in new_card.user_tags, \
        f"user_tags 應含 '看過'，實際: {new_card.user_tags}"

    # created_at 不變
    ca_str = str(new_card.created_at) if new_card.created_at else ""
    assert "2024-02-01" in ca_str, \
        f"created_at 應保留 2024-02-01，得 {ca_str!r}"


# ─── I2: B1 死卡守衛（external_manager=jellyfin） ─────────────────────

def test_b1_repath_no_dead_card_jellyfin(client, tmp_path):
    """
    I2 — B1 端到端死卡守衛（external_manager=jellyfin）：
    與 I1 相同斷言 — 驗 mode-agnostic（CD-c8）。
    B1 落在 try_inflow_upsert，不讀 external_manager。
    """
    from core.database import Video, VideoRepository, init_db
    from core.path_utils import normalize_path, to_file_uri

    db_file = tmp_path / "b1_jelly_test.db"
    init_db(db_file)
    repo = VideoRepository(db_path=db_file)

    old_fs = str(tmp_path / "ABC-002.mp4")
    new_fs = str(tmp_path / "[ABC-002] New Title.mp4")
    old_uri = to_file_uri(normalize_path(old_fs), None)
    new_uri = to_file_uri(normalize_path(new_fs), None)
    old_created = "2024-03-15 08:00:00"

    old_row = _seed_old_card_b1(repo, old_uri, user_tags=["看過", "喜歡"], created_at_str=old_created)
    old_id = old_row.id
    count_before = repo.count()

    video_info = _make_scan_info_for_new_b1(new_uri, num="ABC-002")

    request_body = {
        "file_path": old_fs,
        "number": "ABC-002",
        "metadata": {
            "title": "New Title",
            "number": "ABC-002",
            "cover": "",
            "actresses": [],
            "tags": [],
            "release": "",
        },
    }

    with (
        patch("web.routers.scraper.organize_file", return_value={
            "success": True,
            "new_filename": new_fs,
            "new_folder": str(tmp_path),
            "original_path": old_fs,
        }),
        patch("core.db_inflow.load_config", return_value={
            "gallery": {"directories": [str(tmp_path)], "path_mappings": None},
            "scraper": {"external_manager": "jellyfin"},
        }),
        patch("core.db_inflow.find_matched_directory", return_value=str(tmp_path)),
        patch("core.db_inflow.VideoScanner") as MockScanner,
        patch("core.db_inflow.VideoRepository", return_value=repo),
        patch("core.db_inflow.Video") as MockVideo,
        patch("core.similar.ranker_cache.SimilarRankerCache"),
        patch("web.routers.scraper.VideoRepository", return_value=repo),
    ):
        MockScanner.return_value.scan_file.return_value = video_info
        MockVideo.from_video_info.return_value = Video(
            path=new_uri, number="ABC-002", title="New Title",
            original_title="", actresses=[], maker="", director="",
            series=None, label="", tags=[], user_tags=[],
            sample_images=[], duration=None, size_bytes=0,
            cover_path="", release_date="", mtime=0.0, nfo_mtime=0.0,
        )

        resp = client.post("/api/scrape-single", json=request_body)

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["db_sync_status"] == "synced"

    # 死卡守衛：count 不增
    assert repo.count() == count_before, \
        f"count 應不增（{count_before}），得 {repo.count()}"

    # 舊路徑消失
    assert repo.get_by_path(old_uri) is None, "舊 URI 應消失"

    # 新路徑有效
    new_card = repo.get_by_path(new_uri)
    assert new_card is not None, "新 URI 應存在"

    # id 不變（browse 不跳位）
    assert new_card.id == old_id, \
        f"id 應保留 {old_id}，得 {new_card.id}"

    # browse tags 存活（union）
    assert "看過" in new_card.user_tags, \
        f"user_tags 應含 '看過'，得 {new_card.user_tags}"
    assert "喜歡" in new_card.user_tags, \
        f"user_tags 應含 '喜歡'，得 {new_card.user_tags}"

    # created_at 不變
    ca_str = str(new_card.created_at) if new_card.created_at else ""
    assert "2024-03-15" in ca_str, \
        f"created_at 應保留 2024-03-15，得 {ca_str!r}"


# ─── TASK-98b-T2: 首刮重建 URI == DB row key（focal silent-miss 回歸鎖） ─────────
#
# 最關鍵回歸：scraper.py 用 to_file_uri(target_file, path_mappings) 重建 focal 的
# video_path_uri，必須 byte-equal db_inflow 寫入的 DB row key，否則 update_auto_focal
# WHERE path=? rowcount=0 → silent-miss。跑真 VideoScanner（不 mock scan_file）取得
# 真實 DB key，再用 scraper 的重建公式比對。

def _scraper_rebuild_uri(target_file, config):
    """複製 web/routers/scraper.py 的 focal video_path_uri 重建公式。"""
    from core.path_utils import to_file_uri
    path_mappings = config.get('gallery', {}).get('path_mappings', {})
    return to_file_uri(target_file, path_mappings)


def test_focal_uri_matches_db_key_empty_mappings(tmp_path):
    """path_mappings 空：scraper 用 {}、db_inflow 用 None → 兩者仍相等（{}≡None）。"""
    from core.database import init_db, VideoRepository
    from core.db_inflow import try_inflow_upsert
    from core.path_utils import to_file_uri

    scan_dir = tmp_path / "lib"
    scan_dir.mkdir()
    target = scan_dir / "[2024-01-01][SIRO][SIRO-1234] T.mp4"
    target.write_bytes(b"x" * 1024)

    db_file = tmp_path / "focal_key.db"
    init_db(db_file)
    repo = VideoRepository(db_path=db_file)

    config = {"gallery": {"directories": [str(scan_dir)], "path_mappings": {}}}

    with (
        patch("core.db_inflow.load_config", return_value=config),
        patch("core.db_inflow.VideoRepository", return_value=repo),
        patch("core.similar.ranker_cache.SimilarRankerCache"),
    ):
        status = try_inflow_upsert(str(target))

    assert status == "synced"

    # scraper 重建公式（config 派生 path_mappings={}）
    rebuilt = _scraper_rebuild_uri(str(target), config)
    # {} ≡ None 對齊（db_inflow 用 `path_mappings or None`）
    assert to_file_uri(str(target), {}) == to_file_uri(str(target), None)

    # 重建 URI == DB row key（防 silent-miss）
    assert repo.get_by_path(rebuilt) is not None, \
        f"重建 URI 未命中 DB row：{rebuilt!r}"
    row = repo.get_by_path(rebuilt)
    assert repo.update_auto_focal(rebuilt, "0.5,0.5", row.cover_path) is True, \
        "update_auto_focal 應命中（rowcount==1），否則 silent-miss"


def test_focal_uri_matches_db_key_nonempty_mappings(tmp_path):
    """path_mappings 非空：scraper 與 db_inflow 同用該 mapping → 對齊（平台無關）。

    `to_file_uri` 的 path_mappings 轉換分支只在 CURRENT_ENV == 'wsl' 時生效
    （見 core/path_utils.py to_file_uri docstring）；純 Linux（CI）下這裡的
    Windows 磁碟機字母 mapping 對 to_file_uri 是 no-op，屬設計如此、非 bug。
    「mapping 確實生效（非 trivial identity）」只在 WSL 才有意義，故限定於該
    環境驗證；核心對齊契約（scraper 重建 URI == DB row key）不論平台皆須成立，
    因為兩端呼叫的是同一個 to_file_uri(fs_path, path_mappings)。
    """
    from core.database import init_db, VideoRepository
    from core.db_inflow import try_inflow_upsert
    from core.path_utils import CURRENT_ENV, to_file_uri

    scan_dir = tmp_path / "lib"
    scan_dir.mkdir()
    target = scan_dir / "[2024-01-01][SIRO][SIRO-5678] T.mp4"
    target.write_bytes(b"x" * 1024)

    # 把掃描夾映射到 Windows 磁碟機字母 → WSL 環境下 URI 實際被轉換（非 identity）；
    # 非 WSL 環境（含 CI）下 to_file_uri 的 mapping 分支不生效，屬設計如此。
    path_mappings = {str(scan_dir): "Z:/lib"}

    db_file = tmp_path / "focal_key2.db"
    init_db(db_file)
    repo = VideoRepository(db_path=db_file)

    config = {"gallery": {"directories": [str(scan_dir)], "path_mappings": path_mappings}}

    with (
        patch("core.db_inflow.load_config", return_value=config),
        patch("core.db_inflow.VideoRepository", return_value=repo),
        patch("core.similar.ranker_cache.SimilarRankerCache"),
    ):
        status = try_inflow_upsert(str(target))

    assert status == "synced"

    rebuilt = _scraper_rebuild_uri(str(target), config)

    if CURRENT_ENV == 'wsl':
        # WSL 環境：確認 mapping 真的生效（非 trivial identity）
        assert rebuilt != to_file_uri(str(target), {}), \
            "path_mappings 應實際轉換 URI，否則非有效非空情境"
        assert "Z:/lib" in rebuilt or "Z:" in rebuilt

    # 核心契約（平台無關）：scraper 與 db_inflow 同用同一 path_mappings → 對齊
    assert repo.get_by_path(rebuilt) is not None, \
        f"非空 mapping 下重建 URI 未命中 DB row：{rebuilt!r}"
    row2 = repo.get_by_path(rebuilt)
    assert repo.update_auto_focal(rebuilt, "0.4,0.6", row2.cover_path) is True, \
        "非空 mapping 下 update_auto_focal 應命中（rowcount==1）"


# ─── TASK-98b-T2 DoD-4: scraper 首刮 focal wire gate（驅動真 route，spy helper） ──
#
# 上面兩個 test 只驗「重建公式」與 DB key 對齊（手抄 _scraper_rebuild_uri），沒有
# 驅動 web/routers/scraper.py 真正的接線點（~:214 `if db_sync_status == "synced"`）。
# DoD-4「db_sync_status != 'synced' → 不 submit」因此無鎖。以下 spy
# web.routers.scraper.maybe_submit_video_focal 並打真 route 驗接線閘。
#
# 接線閘只看兩件事：`target_file` 為真 AND `db_sync_status == "synced"`。無 censor
# 閘、無 cover 存在閘——那兩者活在 helper 內部（helper 被 spy，不會實跑）。


def _organize_ok_with_cover(new_filename="/tmp/ABC-001/ABC-001.mp4",
                            cover_path="/tmp/ABC-001/ABC-001-fanart.jpg"):
    d = _organize_ok(new_filename)
    d["cover_path"] = cover_path
    return d


def _scrape_body_with_maker(file_path="/tmp/ABC-001.mp4", maker="S1"):
    body = _scrape_request_body(file_path=file_path)
    body["metadata"]["maker"] = maker
    return body


# ─── 99b-T2 caller #5：首刮 read-back 真 DB fixture 驅動 ──────────────────────
#
# 案 A（下方 test_focal_wire_called_on_synced）原本用 mock 位置參數斷言
# `args[3] == result['cover_path']`——caller #5 改 read-back 後這組斷言直接失效
# （新實作不再把 result['cover_path'] 傳給 maybe_submit_video_focal，而是先
# focal_repo.get_by_path() 讀 row.cover_path 再反解）。改走真 DB + 真
# try_inflow_upsert + 真 VideoScanner.scan_file（只 mock organize_file 與網路面），
# 讓 read-back 邏輯被真正驅動——純 mock `get_by_path` 回傳值會削弱 DoD ⑤
# 「external-manager 模式下 scan_file 選到不同 sidecar」這個真實情境的覆蓋力。


def _real_scrape_focal_fixture(client, tmp_path, video_stem, cover_layout,
                                claimed_cover_suffix=".jpg", existing_cover_path=None):
    """建立真實檔案 fixture 並打真 route，只 mock organize_file（不搬檔）與
    web.routers.scraper.maybe_submit_video_focal（spy，不真跑 pigo）。

    Args:
        cover_layout: "off"（同 stem 封面，scan_file L1 命中）或
            "external_manager"（{stem}-fanart 命名，scan_file L1.5 命中，
            與 result['cover_path']（同 stem 假設）不同源，即 DoD ⑤ 地雷情境）。
        existing_cover_path: 若提供，先在真 DB seed 一筆帶此 cover_path 的既有
            row（DoD ⑥ 既有 row race 情境；None 則不預先 seed，模擬全新首刮）。

    Returns: (resp, repo, captured, video_file, real_cover_file)
    """
    from core.database import init_db, VideoRepository, Video
    from core.path_utils import to_file_uri

    lib_dir = tmp_path / "lib"
    lib_dir.mkdir(exist_ok=True)
    video_file = lib_dir / f"{video_stem}.mp4"
    video_file.write_bytes(b"x")

    if cover_layout == "off":
        real_cover_file = lib_dir / f"{video_stem}{claimed_cover_suffix}"
    else:
        real_cover_file = lib_dir / f"{video_stem}-fanart{claimed_cover_suffix}"
    real_cover_file.write_bytes(b"cover")

    # scraper 自己「以為」下載到的位置：一律同 stem（off 模式下與磁碟一致；
    # external-manager 模式下磁碟並無此檔，代表 db_inflow.try_inflow_upsert 內部
    # VideoScanner.scan_file() 重新偵測到的是別張圖，CD-99b-4 要治的分歧）。
    claimed_cover_path = str(lib_dir / f"{video_stem}{claimed_cover_suffix}")

    db_file = tmp_path / f"scrape_focal_{video_stem}.db"
    init_db(db_file)
    repo = VideoRepository(db_path=db_file)

    video_uri = to_file_uri(str(video_file))
    if existing_cover_path is not None:
        with patch("core.similar.ranker_cache.SimilarRankerCache"):
            repo.upsert(Video(path=video_uri, number=video_stem, maker="S1",
                               cover_path=existing_cover_path))

    captured = {}

    def _capture_submit(number, maker, video_path_uri, cover_fs, *, cover_path_uri, db_path=None):
        captured["number"] = number
        captured["maker"] = maker
        captured["video_path_uri"] = video_path_uri
        captured["cover_fs"] = cover_fs
        captured["cover_path_uri"] = cover_path_uri

    with (
        patch("web.routers.scraper.maybe_submit_video_focal", side_effect=_capture_submit),
        patch("web.routers.scraper.VideoRepository", return_value=repo),
        patch("web.routers.scraper.load_config", return_value={
            "gallery": {"directories": [], "path_mappings": {}}
        }),
        patch("web.routers.scraper.organize_file", return_value={
            "success": True,
            "new_filename": str(video_file),
            "new_folder": str(lib_dir),
            "original_path": str(video_file),
            "cover_path": claimed_cover_path,
        }),
        patch("core.db_inflow.load_config", return_value={
            "gallery": {"directories": [str(lib_dir)], "path_mappings": {}}
        }),
        patch("core.db_inflow.VideoRepository", return_value=repo),
        patch("core.similar.ranker_cache.SimilarRankerCache"),
    ):
        body = _scrape_body_with_maker(file_path=str(video_file))
        body["number"] = video_stem
        body["metadata"]["number"] = video_stem
        resp = client.post("/api/scrape-single", json=body)

    return resp, repo, captured, video_file, real_cover_file


# case A（重寫）：off 模式首刮 read-back——分析檔 == 反解自 row.cover_path，
# cover_path_uri == row.cover_path，commit 命中非 0 列。
def test_focal_wire_called_on_synced(client, tmp_path):
    from core.path_utils import to_file_uri, uri_to_local_fs_path

    resp, repo, captured, video_file, real_cover_file = _real_scrape_focal_fixture(
        client, tmp_path, "ABC9101", cover_layout="off",
    )

    assert resp.status_code == 200
    assert resp.json()["db_sync_status"] == "synced"

    row = repo.get_by_path(to_file_uri(str(video_file)))
    assert row is not None

    assert captured, "helper 應被呼叫一次"
    assert captured["number"] == "ABC9101"
    assert captured["maker"] == "S1"
    assert captured["video_path_uri"] == row.path
    # 分析檔 == 反解自 row.cover_path（同源，CD-99b-4）
    assert captured["cover_fs"] == uri_to_local_fs_path(row.cover_path, {})
    assert captured["cover_fs"] == str(real_cover_file)
    # expected URI == row.cover_path（同源，非 result['cover_path'] 推導）
    assert captured["cover_path_uri"] == row.cover_path

    # commit 命中非 0 列（真 DB 核心契約）
    assert repo.update_auto_focal(row.path, "0.5,0.5", captured["cover_path_uri"]) is True


# DoD ⑤：external-manager 模式——scan_file 選到與 result['cover_path']（同 stem
# 假設）不同的 sidecar（-fanart 命名），read-back 讓分析檔與 expected URI 對齊
# 真正裁切的那張圖。mutation：若改回傳 to_file_uri(result['cover_path']) 當
# expected，此 fixture 下 commit 必然 0 列（見本測試最後一段直接示範）。
def test_focal_read_back_external_manager_mode_real_fixture(client, tmp_path):
    from core.path_utils import to_file_uri, uri_to_local_fs_path

    resp, repo, captured, video_file, real_cover_file = _real_scrape_focal_fixture(
        client, tmp_path, "ABC9102", cover_layout="external_manager",
    )

    assert resp.status_code == 200
    assert resp.json()["db_sync_status"] == "synced"

    row = repo.get_by_path(to_file_uri(str(video_file)))
    assert row is not None
    assert row.cover_path == to_file_uri(str(real_cover_file)), (
        "external-manager 模式下 scan_file 應選到 -fanart 命名的 sidecar，"
        f"得 {row.cover_path!r}"
    )

    claimed_cover_uri = to_file_uri(str(video_file.with_suffix(".jpg")))
    assert row.cover_path != claimed_cover_uri, (
        "測試前提：DB 實際 cover_path 必須與 scraper 自稱的同 stem 路徑不同，"
        "否則本 fixture 沒有重現 external-manager 分歧情境"
    )

    assert captured["cover_fs"] == uri_to_local_fs_path(row.cover_path, {})
    assert captured["cover_fs"] == str(real_cover_file)
    assert captured["cover_path_uri"] == row.cover_path

    # 核心契約：commit 用 read-back 值命中非 0 列
    assert repo.update_auto_focal(row.path, "0.4,0.6", captured["cover_path_uri"]) is True

    # mutation 自證（已推翻方案）：若誤用 result['cover_path'] 當 expected（未 read-back），
    # 在 external-manager fixture 下 commit 必 0 列——這正是 CD-99b-4 要治的 fail-open。
    assert repo.update_auto_focal(row.path, "0.9,0.9", claimed_cover_uri) is False


# DoD ⑥：首刮落在既有 row 的 race 鎖（推翻「首刮=新 row 無 race」的錯誤直覺）。
# 既有 row 的 cover_path 是「上一輪」的舊封面（模擬先前掃描留下的 in-flight job
# 分析對象）；本輪首刮發現封面已換成 disk 上的新檔 → upsert 的 CD-10/CD-99b 換封面
# 語意重置 auto_focal/focal_attempted_at，read-back 拿到新值。
def test_focal_readback_lands_on_existing_row_cover_race(client, tmp_path):
    from core.path_utils import to_file_uri

    stale_cover_uri = "file:///stale/ABC9103_old_cover.jpg"

    resp, repo, captured, video_file, real_cover_file = _real_scrape_focal_fixture(
        client, tmp_path, "ABC9103", cover_layout="off",
        existing_cover_path=stale_cover_uri,
    )

    assert resp.status_code == 200
    assert resp.json()["db_sync_status"] == "synced"

    row = repo.get_by_path(to_file_uri(str(video_file)))
    assert row is not None
    assert row.cover_path == to_file_uri(str(real_cover_file)), (
        "本輪首刮應把 cover_path 換成本輪磁碟上的新封面"
    )
    assert row.cover_path != stale_cover_uri

    # read-back 拿到的是新值，不是舊 in-flight job 分析的舊值
    assert captured["cover_path_uri"] == row.cover_path

    # 舊（上一輪）job commit：expected 仍是舊封面 → 0 列（race 鎖）
    assert repo.update_auto_focal(row.path, "0.1,0.1", stale_cover_uri) is False

    # 本輪（新）job commit：expected 是 read-back 拿到的新值 → 命中
    assert repo.update_auto_focal(row.path, "0.5,0.5", captured["cover_path_uri"]) is True


# DoD ⑦：row is None（read-back 之後才 commit 完成的極端時序）→ 不排、不炸。
def test_focal_readback_row_none_does_not_submit_or_crash(client):
    video_info = _make_video_info()

    with (
        patch("web.routers.scraper.maybe_submit_video_focal") as mock_focal,
        patch("web.routers.scraper.load_config", return_value={
            "gallery": {"directories": [], "path_mappings": {}}
        }),
        patch("web.routers.scraper.organize_file",
              return_value=_organize_ok_with_cover()),
        # focal_repo（scraper.py 端）get_by_path 回 None——模擬理論上不該發生但防禦式
        # guard 要擋住的極端時序。
        patch("web.routers.scraper.VideoRepository") as MockFocalRepo,
        patch("core.db_inflow.load_config", return_value={
            "gallery": {"directories": ["/tmp"], "path_mappings": {}}
        }),
        patch("core.db_inflow.find_matched_directory", return_value="/tmp"),
        patch("core.db_inflow.VideoScanner") as MockScanner,
        patch("core.db_inflow.VideoRepository") as MockRepo,
        patch("core.db_inflow.Video") as MockVideo,
    ):
        MockFocalRepo.return_value.get_by_path.return_value = None
        MockScanner.return_value.scan_file.return_value = video_info
        mock_video = MagicMock()
        mock_video.path = "file:///tmp/ABC-001/ABC-001.mp4"
        MockVideo.from_video_info.return_value = mock_video
        MockRepo.return_value.repath.return_value = None  # → synced

        resp = client.post("/api/scrape-single", json=_scrape_body_with_maker())

    assert resp.status_code == 200
    assert resp.json()["db_sync_status"] == "synced"
    mock_focal.assert_not_called()


# DoD ⑦：row.cover_path == '' → 不排、不炸（封面下載失敗的合法值，非 bug）。
def test_focal_readback_empty_cover_path_does_not_submit_or_crash(client):
    video_info = _make_video_info()

    with (
        patch("web.routers.scraper.maybe_submit_video_focal") as mock_focal,
        patch("web.routers.scraper.load_config", return_value={
            "gallery": {"directories": [], "path_mappings": {}}
        }),
        patch("web.routers.scraper.organize_file",
              return_value=_organize_ok_with_cover()),
        patch("web.routers.scraper.VideoRepository") as MockFocalRepo,
        patch("core.db_inflow.load_config", return_value={
            "gallery": {"directories": ["/tmp"], "path_mappings": {}}
        }),
        patch("core.db_inflow.find_matched_directory", return_value="/tmp"),
        patch("core.db_inflow.VideoScanner") as MockScanner,
        patch("core.db_inflow.VideoRepository") as MockRepo,
        patch("core.db_inflow.Video") as MockVideo,
    ):
        mock_row = MagicMock()
        mock_row.cover_path = ""
        mock_row.path = "file:///tmp/ABC-001/ABC-001.mp4"
        MockFocalRepo.return_value.get_by_path.return_value = mock_row
        MockScanner.return_value.scan_file.return_value = video_info
        mock_video = MagicMock()
        mock_video.path = "file:///tmp/ABC-001/ABC-001.mp4"
        MockVideo.from_video_info.return_value = mock_video
        MockRepo.return_value.repath.return_value = None  # → synced

        resp = client.post("/api/scrape-single", json=_scrape_body_with_maker())

    assert resp.status_code == 200
    assert resp.json()["db_sync_status"] == "synced"
    mock_focal.assert_not_called()


# DoD ⑧(a)：無 user_tags 的正常刮削路徑（最常見路徑，scrape_single :177 分支不執行、
# 外層 `repo` 變數未綁定）走完 read-back 不 UnboundLocalError——本測試請求 body 本就
# 沒有 metadata.user_tags（_scrape_request_body 預設無此欄），off 模式 fixture 全程
# 200 即已隱含證明沒有 UnboundLocalError（若誤用外層 repo 名稱會直接 500）。
def test_focal_readback_no_user_tags_path_does_not_crash(client, tmp_path):
    resp, repo, captured, video_file, real_cover_file = _real_scrape_focal_fixture(
        client, tmp_path, "ABC9104", cover_layout="off",
    )

    assert resp.status_code == 200
    assert resp.json()["db_sync_status"] == "synced"
    assert captured, "無 user_tags 路徑仍應正常走到 read-back 並排入 focal"


# DoD ⑧(b)：read-back 內部任何呼叫（此處 get_by_path）拋例外 → 刮削仍回 200 + 原
# result 形狀，只 logger.warning，不冒泡打斷已成功的整理結果。
def test_focal_readback_get_by_path_raises_still_returns_200(client):
    video_info = _make_video_info()

    with (
        patch("web.routers.scraper.maybe_submit_video_focal") as mock_focal,
        patch("web.routers.scraper.load_config", return_value={
            "gallery": {"directories": [], "path_mappings": {}}
        }),
        patch("web.routers.scraper.organize_file",
              return_value=_organize_ok_with_cover()),
        patch("web.routers.scraper.VideoRepository") as MockFocalRepo,
        patch("core.db_inflow.load_config", return_value={
            "gallery": {"directories": ["/tmp"], "path_mappings": {}}
        }),
        patch("core.db_inflow.find_matched_directory", return_value="/tmp"),
        patch("core.db_inflow.VideoScanner") as MockScanner,
        patch("core.db_inflow.VideoRepository") as MockRepo,
        patch("core.db_inflow.Video") as MockVideo,
    ):
        MockFocalRepo.return_value.get_by_path.side_effect = RuntimeError("DB locked")
        MockScanner.return_value.scan_file.return_value = video_info
        mock_video = MagicMock()
        mock_video.path = "file:///tmp/ABC-001/ABC-001.mp4"
        MockVideo.from_video_info.return_value = mock_video
        MockRepo.return_value.repath.return_value = None  # → synced

        resp = client.post("/api/scrape-single", json=_scrape_body_with_maker())

    assert resp.status_code == 200, "read-back 內部例外不得冒泡打斷已成功的刮削請求"
    body = resp.json()
    assert body["success"] is True
    assert body["db_sync_status"] == "synced"
    mock_focal.assert_not_called()


# case B（DoD-4 核心）：db_sync_status == "not_linked"（非 synced）→ helper NOT called
def test_focal_wire_not_called_when_not_linked(client):
    with (
        patch("web.routers.scraper.maybe_submit_video_focal") as mock_focal,
        patch("web.routers.scraper.load_config", return_value={
            "gallery": {"directories": [], "path_mappings": {}}
        }),
        patch("web.routers.scraper.organize_file",
              return_value=_organize_ok_with_cover()),
        patch("core.db_inflow.load_config", return_value={
            "gallery": {"directories": ["/other"], "path_mappings": {}}
        }),
        patch("core.db_inflow.find_matched_directory", return_value=None),  # → not_linked
        patch("core.db_inflow.VideoScanner"),
        patch("core.db_inflow.VideoRepository"),
    ):
        resp = client.post("/api/scrape-single", json=_scrape_body_with_maker())

    assert resp.status_code == 200
    assert resp.json()["db_sync_status"] == "not_linked"
    mock_focal.assert_not_called()


# case B'（DoD-4 補強）：db_sync_status == "failed"（upsert 拋例外）→ helper NOT called
def test_focal_wire_not_called_when_failed(client):
    video_info = _make_video_info()

    with (
        patch("web.routers.scraper.maybe_submit_video_focal") as mock_focal,
        patch("web.routers.scraper.load_config", return_value={
            "gallery": {"directories": [], "path_mappings": {}}
        }),
        patch("web.routers.scraper.organize_file",
              return_value=_organize_ok_with_cover()),
        patch("core.db_inflow.load_config", return_value={
            "gallery": {"directories": ["/tmp"], "path_mappings": {}}
        }),
        patch("core.db_inflow.find_matched_directory", return_value="/tmp"),
        patch("core.db_inflow.VideoScanner") as MockScanner,
        patch("core.db_inflow.VideoRepository") as MockRepo,
        patch("core.db_inflow.Video") as MockVideo,
    ):
        MockScanner.return_value.scan_file.return_value = video_info
        mock_video = MagicMock()
        mock_video.path = "file:///tmp/ABC-001/ABC-001.mp4"
        MockVideo.from_video_info.return_value = mock_video
        MockRepo.return_value.repath.side_effect = Exception("DB write error")  # → failed

        resp = client.post("/api/scrape-single", json=_scrape_body_with_maker())

    assert resp.status_code == 200
    assert resp.json()["db_sync_status"] == "failed"
    mock_focal.assert_not_called()
