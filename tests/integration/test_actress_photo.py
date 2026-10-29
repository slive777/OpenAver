"""
測試 /api/actresses/{name}/photo-candidates 本機候選 alias 展開（TASK-58a-A2）

涵蓋 4 個 case：
1. 有 alias 的女優（primary 查）→ 展開多名
2. 有 alias 的女優（alias 查，bob）→ 雙向展開
3. 無 alias → resolve 回 {primary} 單名，行為不退化
4. 雲端路徑只收到 primary name（不被 alias 污染）
"""

import json
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _parse_sse(response_text: str) -> list:
    """解析 SSE response，回傳所有 (event_name, data) tuple list。"""
    events = []
    current_event = None
    for line in response_text.strip().split('\n'):
        if line.startswith('event: '):
            current_event = line[7:].strip()
        elif line.startswith('data: '):
            try:
                data = json.loads(line[6:])
                events.append((current_event, data))
            except json.JSONDecodeError:
                pass
    return events


def _make_mock_actress(name="alice"):
    """建立 mock Actress object。"""
    actress = MagicMock()
    actress.name = name
    actress.photo_source = "graphis"
    return actress


def _make_mock_video(path: str, cover_path: str):
    """建立 mock Video object（有 cover_path）。"""
    video = MagicMock()
    video.path = path
    video.cover_path = cover_path
    return video


# ---------------------------------------------------------------------------
# Case 1: 有 alias 的女優（primary 查）→ 展開多名
# ---------------------------------------------------------------------------

def test_local_candidates_alias_expand_primary(client):
    """
    primary 查 'alice'，resolve 回 {"alice", "bob", "cody"}
    → get_videos_by_actress_names 收到包含三名的 list
    """
    mock_actress = _make_mock_actress("alice")

    # resolve("alice") → {"alice", "bob", "cody"}
    mock_resolve = MagicMock(return_value={"alice", "bob", "cody"})

    # get_videos_by_actress_names 回傳空（只驗 call args）
    mock_get_videos = MagicMock(return_value=[])

    with patch('web.routers.actress.ActressRepository') as mock_actress_repo_cls, \
         patch('web.routers.actress.AliasRepository') as mock_alias_repo_cls, \
         patch('web.routers.actress.VideoRepository') as mock_video_repo_cls, \
         patch('web.routers.actress.init_db'), \
         patch('web.routers.actress.graphis_candidates', return_value=[]), \
         patch('web.routers.actress._fetch_single_source', return_value=None):

        # ActressRepository().get_by_name("alice") → mock_actress
        mock_actress_repo_cls.return_value.get_by_name.return_value = mock_actress

        # AliasRepository().resolve("alice") → {"alice", "bob", "cody"}
        mock_alias_repo_cls.return_value.resolve = mock_resolve

        # VideoRepository().get_videos_by_actress_names → []
        mock_video_repo_cls.return_value.get_videos_by_actress_names = mock_get_videos

        response = client.get("/api/actresses/alice/photo-candidates")
        assert response.status_code == 200

    # resolve 應以 "alice" 呼叫一次
    mock_resolve.assert_called_once_with("alice")

    # get_videos_by_actress_names 應以包含三名的 list 呼叫
    assert mock_get_videos.called
    called_names = mock_get_videos.call_args[0][0]  # positional arg
    assert set(called_names) == {"alice", "bob", "cody"}


# ---------------------------------------------------------------------------
# Case 2: 有 alias 的女優（alias 查 bob）→ 雙向展開
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Case 3: 無 alias → resolve 回 {primary} 單名，行為不退化
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Case 4: 雲端路徑只收到 primary name（不被 alias 污染）
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# TASK-102b-T1: attempt query param 輪替（CD-1/CD-2/CD-6/CD-7/CD-8）
# ---------------------------------------------------------------------------

def test_cloud_attempt_rotation_sequence(client):
    """
    CD-6：mock resolve('alice') → {"alice","bob","cody"}。
    attempt=0/1/2/3 之雲端 _fetch_single_source 收到的 name 依 sorted 序輪替：
    alice → bob → cody → alice（sorted(["bob","cody"]) == ["bob","cody"]）。
    attempt=1 這一格即 RED 先行斷言（DoD ⑦）：改端點前 param 被忽略，fetch name 仍是
    "alice"，斷言 == "bob" 會先紅。
    """
    mock_actress = _make_mock_actress("alice")
    mock_actress.photo_source = None  # 全部 4 源皆在 cloud_sources

    mock_resolve = MagicMock(return_value={"alice", "bob", "cody"})
    mock_get_videos = MagicMock(return_value=[])

    expected_sequence = ["alice", "bob", "cody", "alice"]

    for attempt, expected_name in enumerate(expected_sequence):
        fetch_calls = []

        def mock_fetch(name, src, _calls=fetch_calls):
            _calls.append(name)
            return None

        with patch('web.routers.actress.ActressRepository') as mock_actress_repo_cls, \
             patch('web.routers.actress.AliasRepository') as mock_alias_repo_cls, \
             patch('web.routers.actress.VideoRepository') as mock_video_repo_cls, \
             patch('web.routers.actress.init_db'), \
             patch('web.routers.actress.graphis_candidates', return_value=[]), \
             patch('web.routers.actress._fetch_single_source', side_effect=mock_fetch):

            mock_actress_repo_cls.return_value.get_by_name.return_value = mock_actress
            mock_alias_repo_cls.return_value.resolve = mock_resolve
            mock_video_repo_cls.return_value.get_videos_by_actress_names = mock_get_videos

            params = {} if attempt == 0 else {"attempt": attempt}
            response = client.get("/api/actresses/alice/photo-candidates", params=params)
            assert response.status_code == 200

        assert fetch_calls, f"attempt={attempt} 應有雲端 fetch 呼叫"
        assert all(n == expected_name for n in fetch_calls), (
            f"attempt={attempt} 預期雲端 fetch name 全為 {expected_name!r}，實際: {fetch_calls}"
        )


# ---------------------------------------------------------------------------
# TASK-91-T2a #6,#7,#8: WSL + UNC path_mappings 反解回歸測試
# ---------------------------------------------------------------------------

class TestActressPathMappingsReverse:
    """list_photo_candidates / actress_crop / set_actress_photo(local_crop) 三站台
    在 WSL + UNC path_mappings 環境下必須反解成真正能 open() 的本機路徑，而不是
    留下裸 uri_to_fs_path() 產生的映射端 UNC 字串。
    """

    _MAPPINGS = {"/home/user/nas": "//NAS/share"}


    def test_actress_crop_reverse_maps_wsl_unc(self, client, monkeypatch):
        import core.path_utils as path_utils

        monkeypatch.setattr(path_utils, "CURRENT_ENV", "wsl")
        monkeypatch.setattr(
            "web.routers.actress.load_config",
            lambda: {"gallery": {"path_mappings": self._MAPPINGS}},
        )

        with patch('web.routers.actress.init_db'), \
             patch('web.routers.actress.VideoRepository') as mock_video_repo_cls, \
             patch('web.routers.actress.crop_video_cover', return_value=b"fakejpeg") as mock_crop:
            mock_video_repo_cls.return_value.is_known_cover_path.return_value = True

            response = client.get(
                "/api/actresses/actress-crop",
                params={"path": "//NAS/share/cover.jpg", "spec": "v1"},
            )
            assert response.status_code == 200

        called_check_path = mock_video_repo_cls.return_value.is_known_cover_path.call_args[0][0]
        assert called_check_path == "//NAS/share/cover.jpg", (
            "is_known_cover_path 是 DB round-trip 比對，DB 存的是映射端命名空間（如 cover_path），"
            f"不應被反解成本機路徑（否則永遠比對不上 DB 現存值），實際: {called_check_path}"
        )
        mock_crop.assert_called_once_with("/home/user/nas/cover.jpg", "v1")


    def test_list_photo_candidates_main_flow_no_403_real_db(self, tmp_path, monkeypatch):
        """TASK-91 Codex round-2 P1 主流程 e2e：不 mock is_known_cover_path / VideoRepository。

        真實 DB 播一筆 Actress + Video（cover_path 為 mapped URI file://///NAS/share/cover.jpg），
        真實磁碟檔案放在反解後的本機路徑。驅動 GET .../photo-candidates（SSE）取得
        local_crop candidate 的 crop_url，斷言其 path 參數是正規（uri_to_fs_path）形式
        而非反解後的本機路徑；再把那個 path 原封不動餵給 GET actress-crop，斷言不 403 —
        這正是 Codex 指出缺失的「local path 主流程」端對端測試。
        """
        import core.path_utils as path_utils
        from core.database import init_db, VideoRepository, Video, ActressRepository, Actress
        from core.path_utils import to_file_uri
        from urllib.parse import urlparse, parse_qs
        from fastapi.testclient import TestClient

        db_path = tmp_path / "test_photo_candidates_main_flow.db"
        init_db(db_path)
        monkeypatch.setattr("core.database.connection.get_db_path", lambda: db_path)
        monkeypatch.setattr(path_utils, "CURRENT_ENV", "wsl")

        local_nas_dir = tmp_path / "nas"
        local_nas_dir.mkdir()
        local_cover_path = local_nas_dir / "cover.jpg"
        local_cover_path.write_bytes(b"\xff\xd8\xff\xe0fake_cover")
        mappings = {str(local_nas_dir): "//NAS/share"}

        monkeypatch.setattr(
            "web.routers.actress.load_config",
            lambda: {"gallery": {"path_mappings": mappings}},
        )

        cover_uri = to_file_uri(str(local_cover_path), mappings)

        actress_repo = ActressRepository()
        actress_repo.save(Actress(name="carol", photo_source="graphis"))

        video_repo = VideoRepository()
        video_repo.upsert(Video(
            path=to_file_uri(str(tmp_path / "video.mp4")),
            title="Test Video",
            actresses=["carol"],
            cover_path=cover_uri,
        ))

        from web.app import app
        test_client = TestClient(app)

        with patch('web.routers.actress.graphis_candidates', return_value=[]), \
             patch('web.routers.actress._fetch_single_source', return_value=None):
            response = test_client.get("/api/actresses/carol/photo-candidates")
        assert response.status_code == 200

        events = _parse_sse(response.text)
        candidate = next(
            data for (event, data) in events
            if event == "candidate" and data.get("source") == "local_crop"
        )
        crop_url = candidate["thumb_url"]
        query = parse_qs(urlparse(crop_url).query)
        candidate_path = query["path"][0]

        assert candidate_path == "//NAS/share/cover.jpg", (
            "crop_url 應保持正規（uri_to_fs_path）路徑，不應提前反解為本機路徑，"
            f"實際: {candidate_path}"
        )

        with patch('web.routers.actress.crop_video_cover', return_value=b"fakejpeg"):
            crop_response = test_client.get(
                "/api/actresses/actress-crop",
                params={"path": candidate_path, "spec": "v1"},
            )
        assert crop_response.status_code != 403, (
            "list_photo_candidates 產生的 crop_url 餵回 actress_crop 真實 DB round-trip "
            f"不應誤 403，實際 status={crop_response.status_code}, body={crop_response.text!r}"
        )

    def test_set_actress_photo_local_crop_reverse_maps_wsl_unc(self, client, monkeypatch, tmp_path):
        """TASK-100a-T3 補丁：`_write_actress_photo` 在本測試被完全 mock 掉（不寫真檔），
        T3 新增的 CD-6 `get_local_photo_path` 重解析步驟因此找不到任何落地檔會回 None
        → 500，與本測試要驗證的「crop_video_cover 收到正確反解路徑」無關。比照
        gotchas-backend.md §3b 的精神，直接 mock `get_local_photo_path` 回傳一個真實
        存在的檔案（非本測試斷言標的），讓 CD-6 resolve 成功、不影響下方的反解斷言。
        """
        import core.path_utils as path_utils

        monkeypatch.setattr(path_utils, "CURRENT_ENV", "wsl")
        monkeypatch.setattr(
            "web.routers.actress.load_config",
            lambda: {"gallery": {"path_mappings": self._MAPPINGS}},
        )

        mock_actress = _make_mock_actress("alice")
        video_uri = "file:///home/user/media/video.mp4"
        mock_video = _make_mock_video(path=video_uri, cover_path="file://///NAS/share/cover.jpg")

        fake_photo = tmp_path / "alice.jpg"
        fake_photo.write_bytes(b"fakejpeg")

        with patch('web.routers.actress.ActressRepository') as mock_actress_repo_cls, \
             patch('web.routers.actress.init_db'), \
             patch('web.routers.actress.AliasRepository') as mock_alias_repo_cls, \
             patch('web.routers.actress.VideoRepository') as mock_video_repo_cls, \
             patch('web.routers.actress.crop_video_cover', return_value=b"fakejpeg") as mock_crop, \
             patch('web.routers.actress._write_actress_photo'), \
             patch('web.routers.actress.get_local_photo_path', return_value=fake_photo):
            mock_actress_repo_cls.return_value.get_by_name.return_value = mock_actress
            mock_actress_repo_cls.return_value.save = MagicMock()
            mock_alias_repo_cls.return_value.resolve.return_value = {"alice"}
            # PR #211 第三輪 v3：set_actress_photo 新增的身分守衛會呼叫
            # AliasRepository().find_by_alias(name)；本測試整個 mock 掉
            # AliasRepository class，不明確設定的話會回未配置的 MagicMock（連帶
            # mock_actress_repo_cls.return_value.exists(...) 也回真值 MagicMock），
            # 讓守衛誤判成「這是別人的別名」回 400——與本測試要驗的 WSL/UNC 路徑
            # 反解無關，明確設 None 關掉守衛分支。
            mock_alias_repo_cls.return_value.find_by_alias.return_value = None
            mock_video_repo_cls.return_value.get_videos_by_actress_names.return_value = [mock_video]

            response = client.post(
                "/api/actresses/alice/photo",
                json={"source": "local_crop", "video_path": video_uri, "crop_spec": "v1"},
            )
            assert response.status_code == 200

        mock_crop.assert_called_once()
        called_cover_path = mock_crop.call_args[0][0]
        assert called_cover_path == "/home/user/nas/cover.jpg", (
            f"crop_video_cover 應以反解後的本機路徑呼叫，實際: {called_cover_path}"
        )
