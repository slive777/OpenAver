"""
測試 /api/actresses/{name}/photo-candidates 本機候選 alias 展開（TASK-58a-A2）

涵蓋 4 個 case：
1. 有 alias 的女優（primary 查）→ 展開多名
2. 有 alias 的女優（alias 查，bob）→ 雙向展開
3. 無 alias → resolve 回 {primary} 單名，行為不退化
4. 雲端路徑只收到 primary name（不被 alias 污染）
"""

import json
import pytest
from unittest.mock import patch, MagicMock, call


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

def test_local_candidates_alias_expand_via_alias(client):
    """
    alias 查 'bob'，resolve 雙向解析回 {"alice", "bob", "cody"}
    → get_videos_by_actress_names 收到包含三名的 list
    """
    mock_actress = _make_mock_actress("bob")

    mock_resolve = MagicMock(return_value={"alice", "bob", "cody"})
    mock_get_videos = MagicMock(return_value=[])

    with patch('web.routers.actress.ActressRepository') as mock_actress_repo_cls, \
         patch('web.routers.actress.AliasRepository') as mock_alias_repo_cls, \
         patch('web.routers.actress.VideoRepository') as mock_video_repo_cls, \
         patch('web.routers.actress.init_db'), \
         patch('web.routers.actress._fetch_single_source', return_value=None):

        mock_actress_repo_cls.return_value.get_by_name.return_value = mock_actress
        mock_alias_repo_cls.return_value.resolve = mock_resolve
        mock_video_repo_cls.return_value.get_videos_by_actress_names = mock_get_videos

        response = client.get("/api/actresses/bob/photo-candidates")
        assert response.status_code == 200

    # resolve 應以 "bob" 呼叫（雙向解析發生在 resolve 內部）
    mock_resolve.assert_called_once_with("bob")

    called_names = mock_get_videos.call_args[0][0]
    assert set(called_names) == {"alice", "bob", "cody"}


# ---------------------------------------------------------------------------
# Case 3: 無 alias → resolve 回 {primary} 單名，行為不退化
# ---------------------------------------------------------------------------

def test_local_candidates_no_alias_single_name(client):
    """
    無 alias 的女優 'dana'，resolve 回 {"dana"}
    → get_videos_by_actress_names(["dana"]) 呼叫，行為等價舊版
    → 舊版的 get_videos_by_actress 不應被呼叫
    """
    mock_actress = _make_mock_actress("dana")

    mock_resolve = MagicMock(return_value={"dana"})
    mock_get_videos = MagicMock(return_value=[])
    mock_get_videos_single = MagicMock(return_value=[])  # 舊版，不應被呼叫

    with patch('web.routers.actress.ActressRepository') as mock_actress_repo_cls, \
         patch('web.routers.actress.AliasRepository') as mock_alias_repo_cls, \
         patch('web.routers.actress.VideoRepository') as mock_video_repo_cls, \
         patch('web.routers.actress.init_db'), \
         patch('web.routers.actress._fetch_single_source', return_value=None):

        mock_actress_repo_cls.return_value.get_by_name.return_value = mock_actress
        mock_alias_repo_cls.return_value.resolve = mock_resolve
        mock_video_repo_cls.return_value.get_videos_by_actress_names = mock_get_videos
        mock_video_repo_cls.return_value.get_videos_by_actress = mock_get_videos_single

        response = client.get("/api/actresses/dana/photo-candidates")
        assert response.status_code == 200

    mock_resolve.assert_called_once_with("dana")

    # 新版：應呼叫 get_videos_by_actress_names，不是舊版 get_videos_by_actress
    assert mock_get_videos.called
    called_names = mock_get_videos.call_args[0][0]
    assert set(called_names) == {"dana"}

    # 舊版不應被呼叫
    mock_get_videos_single.assert_not_called()


# ---------------------------------------------------------------------------
# Case 4: 雲端路徑只收到 primary name（不被 alias 污染）
# ---------------------------------------------------------------------------

def test_cloud_sources_use_primary_name_only(client):
    """
    雲端 scraper（graphis / gfriends / wiki / minnano）的 _fetch_single_source
    應收到 URL path param（即 "alice"），不被 alias set 污染。

    本測試涵蓋 attempt 省略/0 情境；attempt>0 的雲端換名輪替行為見
    test_cloud_attempt_rotation_sequence 等 TASK-102b-T1 輪替測試。
    """
    mock_actress = _make_mock_actress("alice")
    # photo_source=None → 所有雲端都在 cloud_sources
    mock_actress.photo_source = None

    mock_resolve = MagicMock(return_value={"alice", "bob", "cody"})
    mock_get_videos = MagicMock(return_value=[])

    # 追蹤 _fetch_single_source 的呼叫
    fetch_calls = []

    def mock_fetch(name, src):
        fetch_calls.append((name, src))
        return None

    with patch('web.routers.actress.ActressRepository') as mock_actress_repo_cls, \
         patch('web.routers.actress.AliasRepository') as mock_alias_repo_cls, \
         patch('web.routers.actress.VideoRepository') as mock_video_repo_cls, \
         patch('web.routers.actress.init_db'), \
         patch('web.routers.actress._fetch_single_source', side_effect=mock_fetch):

        mock_actress_repo_cls.return_value.get_by_name.return_value = mock_actress
        mock_alias_repo_cls.return_value.resolve = mock_resolve
        mock_video_repo_cls.return_value.get_videos_by_actress_names = mock_get_videos

        response = client.get("/api/actresses/alice/photo-candidates")
        assert response.status_code == 200

    # 雲端呼叫的 name 參數必須全是 "alice"（URL param），不可是 alias
    for name_arg, src_arg in fetch_calls:
        assert name_arg == "alice", (
            f"雲端 scraper '{src_arg}' 收到 '{name_arg}'，應只收到 'alice'（primary/URL param）"
        )


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


def test_cloud_attempt_omitted_equals_attempt_zero(client):
    """
    省略 attempt 與 attempt=0 的雲端 fetch name 序列相同（spec §4.3-3）。
    """
    mock_actress = _make_mock_actress("alice")
    mock_actress.photo_source = None

    mock_resolve = MagicMock(return_value={"alice", "bob", "cody"})
    mock_get_videos = MagicMock(return_value=[])

    def _run(params):
        fetch_calls = []

        def mock_fetch(name, src, _calls=fetch_calls):
            _calls.append(name)
            return None

        with patch('web.routers.actress.ActressRepository') as mock_actress_repo_cls, \
             patch('web.routers.actress.AliasRepository') as mock_alias_repo_cls, \
             patch('web.routers.actress.VideoRepository') as mock_video_repo_cls, \
             patch('web.routers.actress.init_db'), \
             patch('web.routers.actress._fetch_single_source', side_effect=mock_fetch):

            mock_actress_repo_cls.return_value.get_by_name.return_value = mock_actress
            mock_alias_repo_cls.return_value.resolve = mock_resolve
            mock_video_repo_cls.return_value.get_videos_by_actress_names = mock_get_videos

            response = client.get("/api/actresses/alice/photo-candidates", params=params)
            assert response.status_code == 200
        return fetch_calls

    omitted = _run({})
    explicit_zero = _run({"attempt": 0})
    assert omitted and explicit_zero, "應有雲端 fetch 呼叫"
    assert set(omitted) == set(explicit_zero) == {"alice"}
    assert len(omitted) == len(explicit_zero)


def test_cloud_attempt_no_alias_degrades(client):
    """
    無 alias 退化（spec §4.1-6）：resolve('dana') → {"dana"}，attempt=5 → fetch name
    仍是 "dana"，行為與省略時一致。
    """
    mock_actress = _make_mock_actress("dana")
    mock_actress.photo_source = None

    mock_resolve = MagicMock(return_value={"dana"})
    mock_get_videos = MagicMock(return_value=[])
    fetch_calls = []

    def mock_fetch(name, src):
        fetch_calls.append(name)
        return None

    with patch('web.routers.actress.ActressRepository') as mock_actress_repo_cls, \
         patch('web.routers.actress.AliasRepository') as mock_alias_repo_cls, \
         patch('web.routers.actress.VideoRepository') as mock_video_repo_cls, \
         patch('web.routers.actress.init_db'), \
         patch('web.routers.actress._fetch_single_source', side_effect=mock_fetch):

        mock_actress_repo_cls.return_value.get_by_name.return_value = mock_actress
        mock_alias_repo_cls.return_value.resolve = mock_resolve
        mock_video_repo_cls.return_value.get_videos_by_actress_names = mock_get_videos

        response = client.get(
            "/api/actresses/dana/photo-candidates", params={"attempt": 5}
        )
        assert response.status_code == 200

    assert fetch_calls, "應有雲端 fetch 呼叫"
    assert all(n == "dana" for n in fetch_calls), (
        f"無 alias 女優 attempt=5 應仍以 'dana' 查詢，實際: {fetch_calls}"
    )


def test_cloud_attempt_local_crop_unaffected(client):
    """
    本機補位不受輪替影響（spec §4.3-5）：attempt=2 時 get_videos_by_actress_names
    仍收到全展開 set，resolve() 仍以請求 name（"alice"）呼叫。
    """
    mock_actress = _make_mock_actress("alice")
    mock_actress.photo_source = None

    mock_resolve = MagicMock(return_value={"alice", "bob", "cody"})
    mock_get_videos = MagicMock(return_value=[])

    with patch('web.routers.actress.ActressRepository') as mock_actress_repo_cls, \
         patch('web.routers.actress.AliasRepository') as mock_alias_repo_cls, \
         patch('web.routers.actress.VideoRepository') as mock_video_repo_cls, \
         patch('web.routers.actress.init_db'), \
         patch('web.routers.actress._fetch_single_source', return_value=None):

        mock_actress_repo_cls.return_value.get_by_name.return_value = mock_actress
        mock_alias_repo_cls.return_value.resolve = mock_resolve
        mock_video_repo_cls.return_value.get_videos_by_actress_names = mock_get_videos

        response = client.get(
            "/api/actresses/alice/photo-candidates", params={"attempt": 2}
        )
        assert response.status_code == 200

    # resolve() 至少被以請求 name "alice" 呼叫過（_resolve_query_names 與
    # _get_random_videos_with_covers 各呼叫一次，皆以 "alice"）
    assert call("alice") in mock_resolve.call_args_list

    assert mock_get_videos.called
    called_names = mock_get_videos.call_args[0][0]
    assert set(called_names) == {"alice", "bob", "cody"}


def test_cloud_attempt_boundary_invalid_returns_422(client):
    """CD-8：attempt=-1 / attempt=abc → FastAPI 422。"""
    with patch('web.routers.actress.ActressRepository') as mock_actress_repo_cls, \
         patch('web.routers.actress.init_db'):
        mock_actress_repo_cls.return_value.get_by_name.return_value = _make_mock_actress("alice")

        response = client.get(
            "/api/actresses/alice/photo-candidates", params={"attempt": -1}
        )
        assert response.status_code == 422

        response = client.get(
            "/api/actresses/alice/photo-candidates", params={"attempt": "abc"}
        )
        assert response.status_code == 422


def test_cloud_attempt_boundary_large_int(client):
    """
    CD-8：attempt=10**9 → 200，modulo 正確算出。
    names = ["alice", "bob", "cody"]（len=3）；10**9 % 3 == 1 → query_name == "bob"。
    """
    mock_actress = _make_mock_actress("alice")
    mock_actress.photo_source = None

    mock_resolve = MagicMock(return_value={"alice", "bob", "cody"})
    mock_get_videos = MagicMock(return_value=[])
    fetch_calls = []

    def mock_fetch(name, src):
        fetch_calls.append(name)
        return None

    with patch('web.routers.actress.ActressRepository') as mock_actress_repo_cls, \
         patch('web.routers.actress.AliasRepository') as mock_alias_repo_cls, \
         patch('web.routers.actress.VideoRepository') as mock_video_repo_cls, \
         patch('web.routers.actress.init_db'), \
         patch('web.routers.actress._fetch_single_source', side_effect=mock_fetch):

        mock_actress_repo_cls.return_value.get_by_name.return_value = mock_actress
        mock_alias_repo_cls.return_value.resolve = mock_resolve
        mock_video_repo_cls.return_value.get_videos_by_actress_names = mock_get_videos

        response = client.get(
            "/api/actresses/alice/photo-candidates", params={"attempt": 10**9}
        )
        assert response.status_code == 200

    assert fetch_calls, "應有雲端 fetch 呼叫"
    assert all(n == "bob" for n in fetch_calls), (
        f"attempt=10**9 modulo 應算出 'bob'，實際: {fetch_calls}"
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

    def test_list_photo_candidates_crop_url_stays_canonical_wsl_unc(self, client, monkeypatch):
        """TASK-91 Codex round-2 P1：list_photo_candidates 不做磁碟 I/O，crop_url 的
        path 參數必須是 DB/URL 命名空間下的「正規」路徑（uri_to_fs_path，此處即映射端
        UNC 字串），不可反解成本機路徑 —— 否則 actress_crop 收到本機路徑後，
        is_known_cover_path 用裸 to_file_uri() 比對 DB（DB 存的是映射端 UNC URI）
        永遠對不上，造成誤 403（bug 重現）。反解只能發生在 actress_crop 真正碰磁碟的那一刻。
        """
        import core.path_utils as path_utils

        monkeypatch.setattr(path_utils, "CURRENT_ENV", "wsl")
        monkeypatch.setattr(
            "web.routers.actress.load_config",
            lambda: {"gallery": {"path_mappings": self._MAPPINGS}},
        )

        mock_actress = _make_mock_actress("alice")
        mock_video = _make_mock_video(
            path="file:///home/user/media/video.mp4",
            cover_path="file://///NAS/share/cover.jpg",
        )

        with patch('web.routers.actress.ActressRepository') as mock_actress_repo_cls, \
             patch('web.routers.actress.init_db'), \
             patch('web.routers.actress._fetch_single_source', return_value=None), \
             patch('web.routers.actress._get_random_videos_with_covers', return_value=[mock_video]):
            mock_actress_repo_cls.return_value.get_by_name.return_value = mock_actress

            response = client.get("/api/actresses/alice/photo-candidates")
            assert response.status_code == 200

        events = _parse_sse(response.text)
        candidate = next(
            data for (event, data) in events
            if event == "candidate" and data.get("source") == "local_crop"
        )
        assert "//NAS/share/cover.jpg" in candidate["thumb_url"], (
            "crop_url 應保持 DB/URL 命名空間的正規路徑（uri_to_fs_path，映射端 UNC），"
            f"反解須留給 actress_crop 磁碟 I/O 那一刻，實際: {candidate['thumb_url']}"
        )
        assert "/home/user/nas/cover.jpg" not in candidate["thumb_url"], (
            f"crop_url 不應提前反解為本機路徑，實際: {candidate['thumb_url']}"
        )

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

    def test_actress_crop_real_db_not_403(self, tmp_path, monkeypatch):
        """TASK-91 Finding 2 real test（無 is_known_cover_path mock）：
        真實 DB 存一筆 mapped cover_path（file://///NAS/share/cover.jpg），真實磁碟檔案
        放在反解後的本機路徑；GET actress-crop?path=//NAS/share/cover.jpg 必須通過
        DB round-trip 檢查（不應 403）。若 cover_fs_for_db 誤用反解後路徑比對，
        DB round-trip 永遠 miss → 錯誤 403（bug 重現）。
        """
        import core.path_utils as path_utils
        from core.database import init_db, VideoRepository, Video
        from core.path_utils import to_file_uri
        from fastapi.testclient import TestClient

        db_path = tmp_path / "test_actress_crop_real.db"
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
        repo = VideoRepository()
        repo.upsert(Video(
            path=to_file_uri(str(tmp_path / "video.mp4")),
            title="Test Video",
            cover_path=cover_uri,
        ))

        from web.app import app
        test_client = TestClient(app)

        with patch('web.routers.actress.crop_video_cover', return_value=b"fakejpeg"):
            response = test_client.get(
                "/api/actresses/actress-crop",
                params={"path": "//NAS/share/cover.jpg", "spec": "v1"},
            )

        assert response.status_code != 403, (
            "真實 DB round-trip（is_known_cover_path）應通過，不應誤 403，"
            f"實際 status={response.status_code}, body={response.text!r}"
        )

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

        with patch('web.routers.actress._fetch_single_source', return_value=None):
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
