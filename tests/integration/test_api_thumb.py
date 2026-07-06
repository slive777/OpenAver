"""test_api_thumb.py - 縮圖快取 API 整合測試（feature/71 T3）

涵蓋 TASK-71-T3 邊界 1-9：
- GET /api/gallery/thumb：hit serve webp + no-cache + 強 ETag；If-None-Match → 304；
  hit 零 DB/零 NAS；miss 生成；無 cover 404；generate 失敗 fallback 原圖。
- POST /api/gallery/thumb/prewarm：disabled gate / started / already_running 重入。

隔離關鍵：thumbnail_cache._thumb_dir 與 scanner.get_db_path 是兩個獨立 reference，
兩者都要 patch（見 TASK card 測試隔離坑）。
"""
import pytest
from pathlib import Path

from PIL import Image

from core.path_utils import to_file_uri, uri_to_fs_path
from core import thumbnail_cache


# ---------- helpers ----------

def _make_small_jpg(path: Path, size=(800, 600)):
    """產生一張真 JPG 小圖（用於 cover 來源）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (120, 60, 200)).save(path, "JPEG")
    return path


def _make_webp(path: Path, size=(400, 300)):
    """直接放一張真 webp 到 thumb 位置（用於 hit 測試）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (10, 200, 100)).save(path, "WEBP")
    return path


@pytest.fixture
def thumb_dir(tmp_path, mocker):
    """把 thumbnail_cache._thumb_dir 導向 temp，避免污染真 output/thumb。"""
    d = tmp_path / "thumb"
    d.mkdir()
    mocker.patch("core.thumbnail_cache._thumb_dir", return_value=d)
    return d


@pytest.fixture
def thumb_enabled(mocker):
    """把 thumbnail_cache_enabled 設 True（P2-B gate：預設 False，generate 測試需啟用）。"""
    mocker.patch(
        "web.routers.scanner.load_config",
        return_value={"thumbnail_cache_enabled": True},
    )


@pytest.fixture
def temp_db(tmp_path, mocker):
    """建真 temp DB + 把 scanner.get_db_path 導向它，回 (db_path, repo)。"""
    from core.database import init_db, VideoRepository
    db_path = tmp_path / "test.db"
    init_db(db_path)
    repo = VideoRepository(db_path)
    mocker.patch("web.routers.scanner.get_db_path", return_value=db_path)
    return db_path, repo


# ============ GET /api/gallery/thumb ============

class TestGetThumbHit:
    def test_hit_serves_webp_with_no_cache_and_etag(self, client, thumb_dir):
        """邊界1：hit → 200 image/webp + Cache-Control: no-cache + 強 ETag。"""
        uri = to_file_uri("/movies/v1.mp4")
        _make_webp(thumbnail_cache.thumb_file_for(uri))

        resp = client.get("/api/gallery/thumb", params={"path": uri})

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/webp"
        assert resp.headers["cache-control"] == "no-cache"
        etag = resp.headers["etag"]
        assert etag.startswith('"') and etag.endswith('"')
        assert etag.strip('"').isdigit()

    def test_hit_zero_db_zero_nas(self, client, thumb_dir, mocker):
        """邊界2：hit 路徑零 DB、零 NAS（generate / VideoRepository 未被呼叫）。"""
        uri = to_file_uri("/movies/v1.mp4")
        _make_webp(thumbnail_cache.thumb_file_for(uri))

        gen_spy = mocker.patch("web.routers.scanner.thumbnail_cache.generate")
        repo_spy = mocker.patch("web.routers.scanner.VideoRepository")
        db_spy = mocker.patch("web.routers.scanner.get_db_path")

        resp = client.get("/api/gallery/thumb", params={"path": uri})

        assert resp.status_code == 200
        gen_spy.assert_not_called()
        repo_spy.assert_not_called()
        db_spy.assert_not_called()

    def test_if_none_match_returns_304(self, client, thumb_dir):
        """邊界3：If-None-Match 命中 → 304 空 body。"""
        uri = to_file_uri("/movies/v1.mp4")
        _make_webp(thumbnail_cache.thumb_file_for(uri))

        first = client.get("/api/gallery/thumb", params={"path": uri})
        etag = first.headers["etag"]

        resp = client.get(
            "/api/gallery/thumb",
            params={"path": uri},
            headers={"If-None-Match": etag},
        )
        assert resp.status_code == 304
        assert resp.content == b""


class TestGetThumbMiss:
    def test_miss_generates_webp(self, client, thumb_dir, thumb_enabled, temp_db, tmp_path):
        """邊界4：miss + DB 有 video + cover 真小圖 → 200 image/webp，thumb 檔被建立。"""
        from core.database import Video
        _, repo = temp_db
        cover = _make_small_jpg(tmp_path / "cover.jpg")
        uri = to_file_uri("/movies/v1.mp4")
        repo.upsert_batch([
            Video(path=uri, mtime=100.0, cover_path=to_file_uri(str(cover))),
        ])

        tf = thumbnail_cache.thumb_file_for(uri)
        assert not tf.exists()

        resp = client.get("/api/gallery/thumb", params={"path": uri})

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/webp"
        assert tf.exists()

    def test_no_cover_returns_404(self, client, thumb_dir, temp_db):
        """邊界5a：DB 有 video 但 cover_path 空 → 404。"""
        from core.database import Video
        _, repo = temp_db
        uri = to_file_uri("/movies/nocover.mp4")
        repo.upsert_batch([Video(path=uri, mtime=100.0)])

        resp = client.get("/api/gallery/thumb", params={"path": uri})
        assert resp.status_code == 404

    def test_no_video_returns_404(self, client, thumb_dir, temp_db):
        """邊界5b：DB 無該 video → 404。"""
        uri = to_file_uri("/movies/ghost.mp4")
        resp = client.get("/api/gallery/thumb", params={"path": uri})
        assert resp.status_code == 404

    def test_db_not_exists_returns_404(self, client, thumb_dir, mocker):
        """miss 但 DB 不存在 → 404（不 500）。"""
        mocker.patch("web.routers.scanner.get_db_path",
                     return_value=Path("/nonexistent/openaver.db"))
        uri = to_file_uri("/movies/v1.mp4")
        resp = client.get("/api/gallery/thumb", params={"path": uri})
        assert resp.status_code == 404

    def test_generate_fail_fallbacks_to_original(self, client, thumb_dir, temp_db, tmp_path, mocker):
        """邊界6：generate 失敗 → fallback 原圖（200，非 image/webp、非 404、非破圖）。"""
        from core.database import Video
        _, repo = temp_db
        cover = _make_small_jpg(tmp_path / "cover.jpg")
        uri = to_file_uri("/movies/v1.mp4")
        repo.upsert_batch([
            Video(path=uri, mtime=100.0, cover_path=to_file_uri(str(cover))),
        ])
        mocker.patch("web.routers.scanner.thumbnail_cache.generate", return_value=False)

        resp = client.get("/api/gallery/thumb", params={"path": uri})

        assert resp.status_code == 200
        assert resp.headers["content-type"] != "image/webp"
        assert resp.headers["content-type"] == "image/jpeg"
        assert len(resp.content) > 0

    def test_generate_fail_missing_cover_returns_404_not_500(
        self, client, thumb_dir, temp_db, tmp_path, mocker
    ):
        """Codex P2(a)：generate 失敗且 cover 原圖不存在（並發刪/搬移）→ 404，
        而非 FileResponse(cover_fs) 在 send 時拋 → 500。讓前端破圖三態接手（D6）。
        """
        from core.database import Video
        _, repo = temp_db
        # 建一個真檔讓 is_known_cover_path 通過後再刪，模擬 cover 消失
        cover = _make_small_jpg(tmp_path / "cover.jpg")
        uri = to_file_uri("/movies/v1.mp4")
        repo.upsert_batch([
            Video(path=uri, mtime=100.0, cover_path=to_file_uri(str(cover))),
        ])
        cover.unlink()  # cover 原圖消失
        mocker.patch("web.routers.scanner.thumbnail_cache.generate", return_value=False)

        resp = client.get("/api/gallery/thumb", params={"path": uri})

        assert resp.status_code == 404, (
            f"cover 不存在時 fallback 應回 404（非 500/200），實際 {resp.status_code}"
        )


# ============ Codex round-2 P2: miss→generate 成功的 serve 在 OSError guard 外 ============

class TestGetThumbMissServeConcurrentUnlinkRace:
    """Codex round-2 P2：miss→generate 成功後 _serve_thumb_file 不在 try/except OSError 內。
    generate 成功 → DB row 刪除 + invalidate 移除 thumb → _serve_thumb_file 拋
    FileNotFoundError → 應降級 fallback（200 原圖 / 404），不得 500。
    """

    def test_miss_serve_oserror_does_not_500(self, client, thumb_dir, thumb_enabled, temp_db, tmp_path, mocker):
        """miss→generate True，但 miss-serve 拋 FileNotFoundError → 降級 fallback 原圖 200（非 500）。"""
        from core.database import Video
        _, repo = temp_db
        cover = _make_small_jpg(tmp_path / "cover.jpg")
        uri = to_file_uri("/movies/v1.mp4")
        repo.upsert_batch([
            Video(path=uri, mtime=100.0, cover_path=to_file_uri(str(cover))),
        ])
        # generate 回 True（但不真寫 thumb），miss-serve _serve_thumb_file 拋 FileNotFoundError
        mocker.patch("web.routers.scanner.thumbnail_cache.generate", return_value=True)

        real_serve = __import__("web.routers.scanner", fromlist=["_serve_thumb_file"])._serve_thumb_file
        state = {"raised": False}

        def racing_serve(tf, request):
            if not state["raised"]:
                state["raised"] = True
                raise FileNotFoundError("raced unlink before serve")
            return real_serve(tf, request)

        mocker.patch("web.routers.scanner._serve_thumb_file", side_effect=racing_serve)

        resp = client.get("/api/gallery/thumb", params={"path": uri})

        assert resp.status_code != 500, (
            f"miss→generate 成功後 serve 拋 OSError 不得 500，實際 {resp.status_code}"
        )
        # 降級 fallback：cover 原圖仍在 → 200 原圖
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/jpeg"


# ============ Codex round-2 P1: generate 後 fresh is None / 空 cover → stale ============

class TestGetThumbFreshNoneAfterGenerate:
    """Codex round-2 P1：generate 成功後 re-read DB 回 None（或 cover_path 空）→
    視為 stale，invalidate 丟棄剛寫 thumb 並回 404，不 serve 剛生成的 stale thumb。
    """

    def test_fresh_none_invalidates_and_404(self, client, thumb_dir, thumb_enabled, temp_db, tmp_path, mocker):
        from core.database import Video
        _, repo = temp_db
        cover = _make_small_jpg(tmp_path / "cover.jpg")
        uri = to_file_uri("/movies/v1.mp4")
        repo.upsert_batch([
            Video(path=uri, mtime=100.0, cover_path=to_file_uri(str(cover))),
        ])

        invalidate_spy = mocker.patch("web.routers.scanner.thumbnail_cache.invalidate")

        # get_by_path 第一次回真 video（miss 取 cover），generate 後第二次回 None（並發刪除）
        real_get = repo.get_by_path
        calls = {"n": 0}

        def get_then_none(p):
            calls["n"] += 1
            if calls["n"] == 1:
                return real_get(p)
            return None

        mocker.patch.object(
            __import__("web.routers.scanner", fromlist=["VideoRepository"]).VideoRepository,
            "get_by_path",
            autospec=True,
            side_effect=lambda self, p: get_then_none(p),
        )
        # generate 真寫一個 thumb（回 True）
        resp = client.get("/api/gallery/thumb", params={"path": uri})

        invalidate_spy.assert_called_once_with(uri)
        assert resp.status_code == 404, (
            f"fresh is None 應視為 stale → invalidate + 404，實際 {resp.status_code}"
        )


# ============ P1: generate 後 cover stale → invalidate + serve 當前封面 ============

class TestGetThumbStaleCoverAfterGenerate:
    """Codex P1：miss 路徑 generate(cover_fs) 成功後、serve 前 re-read DB cover；
    若 cover_path 已被並發換掉（enrich/rescrape）→ 丟棄剛寫的 stale thumb（invalidate）
    並改 serve 當前封面，避免把舊封面 thumb 當新圖回給用戶。
    """

    def test_stale_cover_invalidates_and_serves_current_cover(
        self, client, thumb_dir, thumb_enabled, temp_db, tmp_path, mocker
    ):
        from core.database import Video
        _, repo = temp_db
        cover_a = _make_small_jpg(tmp_path / "cover_a.jpg", size=(800, 600))
        cover_b = _make_small_jpg(tmp_path / "cover_b.jpg", size=(640, 480))
        uri = to_file_uri("/movies/v1.mp4")
        # DB 初始 cover A
        repo.upsert_batch([
            Video(path=uri, mtime=100.0, cover_path=to_file_uri(str(cover_a))),
        ])

        invalidate_spy = mocker.patch(
            "web.routers.scanner.thumbnail_cache.invalidate"
        )

        # generate(cover_a, tf) 「成功」後，模擬 DB 已被換成 cover B：
        # 讓 generate 真寫一個 thumb（回 True），且在 generate 後把 DB cover_path 改 B。
        real_generate = thumbnail_cache.generate

        def generate_then_swap(cover_fs, dst):
            ok = real_generate(cover_fs, dst)
            # 模擬並發 enrich 換封面
            repo.upsert_batch([
                Video(path=uri, mtime=100.0, cover_path=to_file_uri(str(cover_b))),
            ])
            return ok

        mocker.patch(
            "web.routers.scanner.thumbnail_cache.generate",
            side_effect=generate_then_swap,
        )

        resp = client.get("/api/gallery/thumb", params={"path": uri})

        # 偵測 stale → invalidate(path) 被呼叫丟棄剛寫的舊 thumb
        invalidate_spy.assert_called_once_with(uri)
        # serve 的不是 stale thumb（非 image/webp），而是當前封面 B 的原圖
        assert resp.status_code == 200
        assert resp.headers["content-type"] != "image/webp"
        assert resp.headers["content-type"] == "image/jpeg"
        # 內容是 cover B（當前封面），不是 cover A
        assert resp.content == cover_b.read_bytes()


# ============ POST /api/gallery/thumb/prewarm ============

class TestThumbPrewarm:
    def test_disabled_returns_disabled(self, client, mocker):
        """邊界7：thumbnail_cache_enabled=False → disabled，worker 未啟動。"""
        mocker.patch("web.routers.scanner.load_config",
                     return_value={"thumbnail_cache_enabled": False})
        iter_spy = mocker.patch("web.routers.scanner.thumbnail_cache.iter_missing")
        gen_spy = mocker.patch("web.routers.scanner.thumbnail_cache.generate")
        thread_spy = mocker.patch("web.routers.scanner.threading.Thread")

        resp = client.post("/api/gallery/thumb/prewarm")

        assert resp.status_code == 200
        assert resp.json()["status"] == "disabled"
        iter_spy.assert_not_called()
        gen_spy.assert_not_called()
        thread_spy.assert_not_called()

    def test_started_returns_started(self, client, mocker):
        """邊界8：enabled → started（patch Thread no-op 避免 flakiness）。"""
        import web.routers.scanner as scanner_mod
        mocker.patch("web.routers.scanner.load_config",
                     return_value={"thumbnail_cache_enabled": True})
        thread_spy = mocker.patch("web.routers.scanner.threading.Thread")

        # 確保 flag 乾淨
        scanner_mod._prewarming = False
        try:
            resp = client.post("/api/gallery/thumb/prewarm")
            assert resp.status_code == 200
            assert resp.json()["status"] == "started"
            thread_spy.assert_called_once()
            thread_spy.return_value.start.assert_called_once()
        finally:
            scanner_mod._prewarming = False

    def test_reentrant_returns_already_running(self, client, mocker):
        """邊界9：_prewarming=True → already_running，且不啟新 thread。"""
        import web.routers.scanner as scanner_mod
        mocker.patch("web.routers.scanner.load_config",
                     return_value={"thumbnail_cache_enabled": True})
        thread_spy = mocker.patch("web.routers.scanner.threading.Thread")

        scanner_mod._prewarming = True
        try:
            resp = client.post("/api/gallery/thumb/prewarm")
            assert resp.status_code == 200
            assert resp.json()["status"] == "already_running"
            thread_spy.assert_not_called()
        finally:
            scanner_mod._prewarming = False


# ============ M1: hit 後並發 unlink race（feature/71 T8）============

class TestThumbHitConcurrentUnlinkRace:
    """T8 邊界9：hit 判定（tf.exists()）通過後、_serve_thumb_file 內 tf.stat() 前，
    thumb 被並發 invalidate(unlink) → 不得 500（降級走 miss 重生或 404）。
    """

    def test_stat_filenotfound_does_not_500(self, client, thumb_dir, thumb_enabled, temp_db, tmp_path, mocker):
        """hit 後 stat 拋 FileNotFoundError：DB 有 video+cover → 降級重生 200（非 500）。"""
        from core.database import Video
        _, repo = temp_db
        cover = _make_small_jpg(tmp_path / "cover.jpg")
        uri = to_file_uri("/movies/v1.mp4")
        # 放真 thumb 讓 tf.exists() 為 True（hit 判定通過）
        _make_webp(thumbnail_cache.thumb_file_for(uri))
        repo.upsert_batch([
            Video(path=uri, mtime=100.0, cover_path=to_file_uri(str(cover))),
        ])

        # 模擬 race：tf.exists() 仍 True（hit 判定通過），但 _serve_thumb_file 的
        # tf.stat()（無 follow_symlinks kwarg）拋 FileNotFoundError。
        # Path.exists() 內部 stat 帶 follow_symlinks → 用此區分，不影響 hit 判定。
        # 只在「第一次」serve stat 拋（模擬 race）；降級重生後的 serve stat 正常。
        real_stat = Path.stat
        tf = thumbnail_cache.thumb_file_for(uri)
        state = {"raised": False}

        def racing_stat(self, *a, **kw):
            if self == tf and "follow_symlinks" not in kw and not state["raised"]:
                state["raised"] = True
                raise FileNotFoundError("raced unlink")
            return real_stat(self, *a, **kw)

        mocker.patch.object(Path, "stat", racing_stat)

        resp = client.get("/api/gallery/thumb", params={"path": uri})

        assert resp.status_code != 500, (
            f"hit 後並發 unlink（stat FileNotFound）不得 500，實際 {resp.status_code}"
        )
        # 降級重生：200 webp（DB 有 cover）
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/webp"

    def test_stat_filenotfound_no_cover_returns_404_not_500(
        self, client, thumb_dir, temp_db, mocker
    ):
        """hit 後 stat 拋 FileNotFoundError、DB 無 video → 404（非 500）。"""
        uri = to_file_uri("/movies/ghost.mp4")
        _make_webp(thumbnail_cache.thumb_file_for(uri))  # 有檔 → hit

        real_stat = Path.stat
        tf = thumbnail_cache.thumb_file_for(uri)

        def racing_stat(self, *a, **kw):
            if self == tf and "follow_symlinks" not in kw:
                raise FileNotFoundError("raced unlink")
            return real_stat(self, *a, **kw)

        mocker.patch.object(Path, "stat", racing_stat)

        resp = client.get("/api/gallery/thumb", params={"path": uri})

        assert resp.status_code != 500
        assert resp.status_code == 404


# ============ P2: clear/prewarm 競態（feature/71 round-3）============

class TestPrewarmClearRace:
    """round-3 P2：_prewarm_worker 從 stale snapshot 逐一 generate；期間用戶按
    「清除所有影片快取」→ clear_cache 跑 repo.clear_all() + thumbnail_cache.clear_all()
    （rmtree）。worker 不可在已清空目錄重建 orphan webp（DB 空 thumb 在）。
    修法：迴圈內 get_by_path re-check（before 跳過 / after 清 TOCTOU 孤兒），surgical。
    """

    def _patch_worker_deps(self, mocker, iter_items, get_by_path_side,
                           load_config_side=None):
        """共用：patch worker 內 get_db_path / VideoRepository / iter_missing /
        load_config（P2 race：worker 每 item 重讀 thumbnail_cache_enabled）。
        回 (gen_spy, invalidate_spy, repo_mock)。

        load_config_side：None → 預設一律回 enabled=True（既有測試不受 enabled-check
        影響）；傳 list → 逐次 side_effect（精準控制每次 load_config 回值）。
        """
        # db_path.exists() True
        db_path = mocker.MagicMock()
        db_path.exists.return_value = True
        mocker.patch("web.routers.scanner.get_db_path", return_value=db_path)

        if load_config_side is None:
            mocker.patch(
                "web.routers.scanner.load_config",
                return_value={"thumbnail_cache_enabled": True},
            )
        else:
            mocker.patch(
                "web.routers.scanner.load_config",
                side_effect=load_config_side,
            )

        repo_mock = mocker.MagicMock()
        repo_mock.get_all.return_value = []  # iter_missing 被 mock，回值不重要
        if isinstance(get_by_path_side, list):
            repo_mock.get_by_path.side_effect = get_by_path_side
        else:
            repo_mock.get_by_path.return_value = get_by_path_side
        mocker.patch("web.routers.scanner.VideoRepository", return_value=repo_mock)

        mocker.patch(
            "web.routers.scanner.thumbnail_cache.iter_missing",
            return_value=iter(iter_items),
        )
        gen_spy = mocker.patch(
            "web.routers.scanner.thumbnail_cache.generate", return_value=True
        )
        invalidate_spy = mocker.patch(
            "web.routers.scanner.thumbnail_cache.invalidate"
        )
        return gen_spy, invalidate_spy, repo_mock

    def test_before_check_skips_generate_when_video_gone(self, mocker):
        """RED1（before-check）：iter_missing 回幾筆，但 get_by_path 一律 None
        （模擬 clear 後 DB 空）→ generate 完全不被呼叫（不生成孤兒）。"""
        import web.routers.scanner as scanner_mod

        items = [
            (to_file_uri("/m/a.mp4"), "/cover/a.jpg"),
            (to_file_uri("/m/b.mp4"), "/cover/b.jpg"),
            (to_file_uri("/m/c.mp4"), "/cover/c.jpg"),
        ]
        gen_spy, invalidate_spy, repo_mock = self._patch_worker_deps(
            mocker, items, get_by_path_side=None  # 一律 None
        )
        mocker.patch("web.routers.scanner._emit_notif")
        scanner_mod._prewarming = True
        try:
            scanner_mod._prewarm_worker()
        finally:
            scanner_mod._prewarming = False

        gen_spy.assert_not_called()
        invalidate_spy.assert_not_called()

    def test_after_check_invalidates_toctou_orphan(self, mocker):
        """RED2（after-check）：get_by_path 第一次（before）回 video、第二次（after）
        回 None（模擬 generate 期間被清）+ generate 回 True → invalidate(uri) 被呼叫
        清掉剛寫的孤兒。"""
        import web.routers.scanner as scanner_mod

        uri = to_file_uri("/m/raced.mp4")
        items = [(uri, "/cover/raced.jpg")]
        # before → video（有 cover，據此生成）；after → None（被清，孤兒）
        sentinel_video = mocker.MagicMock(cover_path=to_file_uri("/cover/raced.jpg"))
        gen_spy, invalidate_spy, repo_mock = self._patch_worker_deps(
            mocker, items, get_by_path_side=[sentinel_video, None]
        )
        mocker.patch("web.routers.scanner._emit_notif")
        scanner_mod._prewarming = True
        try:
            scanner_mod._prewarm_worker()
        finally:
            scanner_mod._prewarming = False

        gen_spy.assert_called_once()
        invalidate_spy.assert_called_once_with(uri)

    def test_generate_uses_current_db_cover_not_stale_snapshot(self, mocker):
        """round-4 RED（cover-path-change，Codex repro）：iter_missing 的 snapshot
        cover 是 old，但 DB 當前 cover 已換成 new（enrich/rescrape）。worker 必須用
        「當前 DB cover」生成，忽略 stale snapshot cover → generate 收到 new 的 fs path。
        """
        import web.routers.scanner as scanner_mod

        uri = to_file_uri("/m/swapped.mp4")
        new_uri = to_file_uri("/cover/new.jpg")
        # snapshot 給 old；DB（before+after）一律回 new
        items = [(uri, "/cover/old.jpg")]
        cur_video = mocker.MagicMock(cover_path=new_uri)
        gen_spy, invalidate_spy, repo_mock = self._patch_worker_deps(
            mocker, items, get_by_path_side=cur_video  # before/after 都回 new
        )
        mocker.patch("web.routers.scanner._emit_notif")
        scanner_mod._prewarming = True
        try:
            scanner_mod._prewarm_worker()
        finally:
            scanner_mod._prewarming = False

        gen_spy.assert_called_once()
        used_cover_fs = gen_spy.call_args.args[0]
        assert used_cover_fs == uri_to_fs_path(new_uri)
        assert used_cover_fs != "/cover/old.jpg"
        # cover 沒在 generate 期間再變（before==after）→ 不 invalidate、計入
        invalidate_spy.assert_not_called()

    def test_after_check_invalidates_when_cover_changed_during_generate(self, mocker):
        """round-4 RED（after cover-change）：before 回 cover A、after 回 cover B
        （generate 期間 cover 又被換）+ generate True → invalidate(uri) 丟棄剛寫的
        stale thumb、不計入。"""
        import web.routers.scanner as scanner_mod

        uri = to_file_uri("/m/midswap.mp4")
        cover_a = to_file_uri("/cover/a.jpg")
        cover_b = to_file_uri("/cover/b.jpg")
        items = [(uri, "/cover/snapshot.jpg")]
        video_a = mocker.MagicMock(cover_path=cover_a)
        video_b = mocker.MagicMock(cover_path=cover_b)
        gen_spy, invalidate_spy, repo_mock = self._patch_worker_deps(
            mocker, items, get_by_path_side=[video_a, video_b]
        )
        mocker.patch("web.routers.scanner._emit_notif")
        scanner_mod._prewarming = True
        try:
            scanner_mod._prewarm_worker()
        finally:
            scanner_mod._prewarming = False

        gen_spy.assert_called_once()
        # before 用 cover A 生成
        assert gen_spy.call_args.args[0] == uri_to_fs_path(cover_a)
        # after 偵測 cover 變 B → 丟棄
        invalidate_spy.assert_called_once_with(uri)

    # ---- Codex P2 race：快取被關閉（+clear）期間 worker 仍重建縮圖 ----
    # 修法 Option A：worker 每 item 重讀 load_config().thumbnail_cache_enabled。
    # 前端契約「先 save(false) 才 clear」→ config.json 寫 false 必早於 clear fetch，
    # worker 重讀拿得到 false（load_config 無 lru_cache，每次讀 disk）。

    def test_after_check_invalidates_when_disabled_during_generate(self, mocker):
        """RED（disabled_after）：item A before-check enabled=True、generate 後
        after-check enabled=False（generate 期間用戶關閉快取）→ generate 只跑一次
        （item B 因 break 沒跑）+ invalidate(A) 清掉剛生成的殘留 thumb。"""
        import web.routers.scanner as scanner_mod

        uri_a = to_file_uri("/m/a.mp4")
        uri_b = to_file_uri("/m/b.mp4")
        cover_a = to_file_uri("/cover/a.jpg")
        items = [(uri_a, "/cover/a.jpg"), (uri_b, "/cover/b.jpg")]
        # before/after get_by_path 都回有效 video（cover 沒換）；隔離出 enabled 變化
        video_a = mocker.MagicMock(cover_path=cover_a)
        # load_config：第 1 次（A before）True、第 2 次（A after）False
        gen_spy, invalidate_spy, repo_mock = self._patch_worker_deps(
            mocker, items,
            get_by_path_side=[video_a, video_a],
            load_config_side=[
                {"thumbnail_cache_enabled": True},   # TASK-91-T2b #11: 迴圈外 path_mappings 讀取
                {"thumbnail_cache_enabled": True},   # A before-check
                {"thumbnail_cache_enabled": False},  # A after-check（generate 期間關閉）
            ],
        )
        notif_spy = mocker.patch("web.routers.scanner._emit_notif")
        scanner_mod._prewarming = True
        try:
            scanner_mod._prewarm_worker()
        finally:
            scanner_mod._prewarming = False

        # item A generate 跑了一次；item B 因 disabled break 沒跑
        gen_spy.assert_called_once()
        # 剛生成的 A thumb 殘留被清
        invalidate_spy.assert_called_once_with(uri_a)
        # Codex P3：被 disable 中止 → 不送「完成 N 張」done 通知（避免與關閉並清除打架）
        done_keys = [c.args[1] for c in notif_spy.call_args_list if len(c.args) > 1]
        assert "notif.thumb_prewarm_done" not in done_keys

    def test_before_check_skips_all_when_disabled_first_item(self, mocker):
        """RED（before-check disabled）：第一筆 before-check 就 enabled=False →
        generate 完全不被呼叫、invalidate 也沒（worker 立即 break）。"""
        import web.routers.scanner as scanner_mod

        items = [
            (to_file_uri("/m/a.mp4"), "/cover/a.jpg"),
            (to_file_uri("/m/b.mp4"), "/cover/b.jpg"),
        ]
        video = mocker.MagicMock(cover_path=to_file_uri("/cover/a.jpg"))
        gen_spy, invalidate_spy, repo_mock = self._patch_worker_deps(
            mocker, items,
            get_by_path_side=video,
            load_config_side=[{"thumbnail_cache_enabled": False}],  # 第一筆 before 就關
        )
        notif_spy = mocker.patch("web.routers.scanner._emit_notif")
        scanner_mod._prewarming = True
        try:
            scanner_mod._prewarm_worker()
        finally:
            scanner_mod._prewarming = False

        gen_spy.assert_not_called()
        invalidate_spy.assert_not_called()
        # Codex P3：第一筆就 disabled → 立即 break，不送「完成 0 張」done 通知
        done_keys = [c.args[1] for c in notif_spy.call_args_list if len(c.args) > 1]
        assert "notif.thumb_prewarm_done" not in done_keys

    def test_disabled_after_break_even_when_generate_fails(self, mocker):
        """RED（Codex P3-2）：最後一筆 generate 回 False（失敗）且 generate 期間用戶關閉
        快取（disabled_after=True, ok=False）→ 仍須 stopped_disabled break、不送 done
        通知。失敗無 thumb → 不 invalidate。防 disabled-after 被埋在 `if ok` 下漏 break。"""
        import web.routers.scanner as scanner_mod

        uri_a = to_file_uri("/m/a.mp4")
        cover_a = to_file_uri("/cover/a.jpg")
        # 單筆（即「最後一筆」）：loop 跑完即抵達 done emit，old code 漏 break 會誤送 done（RED）
        items = [(uri_a, "/cover/a.jpg")]
        video_a = mocker.MagicMock(cover_path=cover_a)
        gen_spy, invalidate_spy, repo_mock = self._patch_worker_deps(
            mocker, items,
            get_by_path_side=[video_a, video_a],
            load_config_side=[
                {"thumbnail_cache_enabled": True},   # TASK-91-T2b #11: 迴圈外 path_mappings 讀取
                {"thumbnail_cache_enabled": True},   # A before-check
                {"thumbnail_cache_enabled": False},  # A after-check（generate 期間關閉）
            ],
        )
        gen_spy.return_value = False  # generate 失敗
        notif_spy = mocker.patch("web.routers.scanner._emit_notif")
        scanner_mod._prewarming = True
        try:
            scanner_mod._prewarm_worker()
        finally:
            scanner_mod._prewarming = False

        gen_spy.assert_called_once()              # A 生成一次（失敗）
        invalidate_spy.assert_not_called()        # generate 失敗，無 thumb 可清
        done_keys = [c.args[1] for c in notif_spy.call_args_list if len(c.args) > 1]
        assert "notif.thumb_prewarm_done" not in done_keys  # 不送誤導 done


# ============ POST /api/gallery/thumb/clear (71b-T2) ============

class TestThumbClear:
    """71b-T2：DB-safe 清空端點。清 output/thumb/、回 {"cleared": True}，
    **絕不碰 videos DB**（row 數不變）。鏡像 prewarm 端點測試模式。"""

    def test_clear_returns_cleared_true(self, client, thumb_dir):
        resp = client.post("/api/gallery/thumb/clear")
        assert resp.status_code == 200
        assert resp.json() == {"cleared": True}

    def test_clear_removes_thumb_dir_contents(self, client, thumb_dir):
        """thumb_dir 內既有 webp → 清後目錄被移除（rmtree，缺目錄 no-op）。"""
        uri = to_file_uri("/movies/v1.mp4")
        _make_webp(thumbnail_cache.thumb_file_for(uri))
        assert any(thumb_dir.iterdir()), "前置：thumb_dir 應有檔"

        resp = client.post("/api/gallery/thumb/clear")

        assert resp.status_code == 200
        # rmtree(_thumb_dir())：整個目錄移除（CD-11 缺目錄 no-op）
        assert not thumb_dir.exists() or not any(thumb_dir.iterdir()), \
            "thumb_dir 應被清空"

    def test_clear_does_not_touch_videos_db(self, client, thumb_dir, temp_db):
        """硬約束：videos DB row 數清前清後不變（端點絕不碰 DB）。"""
        from core.database import Video
        _, repo = temp_db
        repo.upsert_batch([
            Video(path=to_file_uri("/movies/a.mp4"), mtime=1.0),
            Video(path=to_file_uri("/movies/b.mp4"), mtime=2.0),
            Video(path=to_file_uri("/movies/c.mp4"), mtime=3.0),
        ])
        before = repo.count()
        assert before == 3, "前置：DB 應有 3 筆"

        resp = client.post("/api/gallery/thumb/clear")

        assert resp.status_code == 200
        assert repo.count() == before, \
            f"videos DB row 數不得變（清前 {before}，清後 {repo.count()}）"

    def test_clear_idempotent_when_dir_missing(self, client, thumb_dir):
        """冪等：目錄不存在時再 clear 仍 200 + cleared（rmtree ignore_errors）。"""
        client.post("/api/gallery/thumb/clear")
        resp = client.post("/api/gallery/thumb/clear")
        assert resp.status_code == 200
        assert resp.json() == {"cleared": True}


# ============ TASK-71c P2-A：double-decode（字面 % 路徑 miss → 404）============

class TestGetThumbDoubleDecodeP2A:
    """P2-A：get_thumb 對 FastAPI 已 decode 的 path 再 unquote → double-decode。
    路徑含字面 % 字元（如 file:///nas/Test%20File.mp4）→ key 失配 → miss 404。
    修法：移除 get_thumb 內的 path = unquote(path)，信任 FastAPI 已 decode。
    """

    def test_miss_with_literal_percent_in_path(self, client, thumb_dir, temp_db, tmp_path):
        """P2-A RED → GREEN：path 含字面 %，FastAPI 已 decode，handler 不應再 unquote。
        TestClient 走真 FastAPI decode pipeline（quote → ASGI → FastAPI decode → handler）。
        修前 double-decode → key 失配 → 404（RED）。修後 200（GREEN）。
        """
        from core.database import Video

        _, repo = temp_db
        # path 含字面 %（不是 URL encode 序列，而是檔名本身含 % 的字串）
        v_path = to_file_uri("/nas/Test%20File.mp4")  # 字面 % 在 URI 中
        cover = _make_small_jpg(tmp_path / "cover_percent.jpg")
        repo.upsert_batch([
            Video(path=v_path, mtime=100.0, cover_path=to_file_uri(str(cover))),
        ])

        # TestClient(httpx) 自動 percent-encode params → FastAPI decode 一次 → handler 收到的
        # path 應等於原始 v_path（含字面 %）。修前多餘 unquote 會再 decode 一次 → key 失配。
        resp = client.get("/api/gallery/thumb", params={"path": v_path})

        # 修前：double-decode → key 失配 → 404（RED）
        # 修後：handler 直接用 FastAPI decode 後的值 → key 命中 → 不是 404（GREEN）
        assert resp.status_code != 404, (
            f"path 含字面 % 不應 double-decode 導致 key 失配 404，實際 {resp.status_code}\n"
            f"v_path={v_path!r}"
        )


# ============ TASK-71c P2-B：miss 路徑無 disabled gate ============

class TestGetThumbMissDisabledGateP2B:
    """P2-B：get_thumb miss 路徑未先檢查 thumbnail_cache_enabled，
    用戶關閉快取後仍重生 WebP → 「關閉並清除」無效。
    修法：generate 前加 gate，disabled → fall through 到 fallback 原圖。
    """

    def test_miss_disabled_does_not_generate(
        self, client, thumb_dir, temp_db, tmp_path, mocker
    ):
        """P2-B RED → GREEN：快取關閉時 miss 路徑不應呼叫 generate。
        修前：generate 被呼叫（RED）。修後：generate 未被呼叫 + 200 fallback 原圖（GREEN）。
        """
        from core.database import Video

        _, repo = temp_db
        cover = _make_small_jpg(tmp_path / "cover_disabled.jpg")
        uri = to_file_uri("/movies/disabled_test.mp4")
        repo.upsert_batch([
            Video(path=uri, mtime=100.0, cover_path=to_file_uri(str(cover))),
        ])

        # 快取關閉
        mocker.patch(
            "web.routers.scanner.load_config",
            return_value={"thumbnail_cache_enabled": False},
        )
        gen_spy = mocker.patch("web.routers.scanner.thumbnail_cache.generate")

        # thumb_dir 空（模擬 clear 後 miss），不預建 thumb

        resp = client.get("/api/gallery/thumb", params={"path": uri})

        # generate 不得被呼叫（快取已關閉）
        gen_spy.assert_not_called()
        # fallback 原圖：200 image/jpeg（不是 404、不是 image/webp）
        assert resp.status_code == 200, (
            f"disabled miss 應 fallback 原圖 200，實際 {resp.status_code}"
        )
        assert resp.headers["content-type"] == "image/jpeg", (
            f"fallback 應是原圖 jpeg，實際 {resp.headers['content-type']}"
        )


# ============ TASK-91-T2b #9/#10/#11: WSL+UNC path_mappings 反解 ============

class TestUriToLocalFsPathReverseMappingThumb:
    """get_thumb miss 分支（#9 首次 generate 用的 cover_fs / #10 generate 後
    re-read 的 fresh_fs）與 _prewarm_worker（#11）在 WSL + UNC path_mappings
    環境下，餵給磁碟 I/O（thumbnail_cache.generate/os.path.exists）的路徑必須是
    反解後的本機路徑，而不是裸 uri_to_fs_path() 產生的映射端 UNC 字串。
    """

    def test_get_thumb_miss_generate_uses_reverse_mapped_path(
        self, client, thumb_dir, temp_db, tmp_path, mocker, monkeypatch
    ):
        """#9：miss→generate，DB cover_path 為 mapped UNC URI，config 帶 WSL+mapping
        → thumbnail_cache.generate 收到的 cover_fs 是反解後的本機路徑（可 open()），
        而非裸 UNC 字串 //NAS/share/...（該路徑在測試環境不存在，會讓 generate 失敗）。
        """
        import core.path_utils as path_utils
        from core.database import Video

        _, repo = temp_db
        monkeypatch.setattr(path_utils, "CURRENT_ENV", "wsl")

        nas_dir = tmp_path / "nas"
        nas_dir.mkdir()
        cover = _make_small_jpg(nas_dir / "cover.jpg")
        mappings = {str(nas_dir): "//NAS/share"}

        mocker.patch(
            "web.routers.scanner.load_config",
            return_value={
                "thumbnail_cache_enabled": True,
                "gallery": {"path_mappings": mappings},
            },
        )

        uri = to_file_uri("/movies/wsl_unc.mp4")
        cover_uri = "file://///NAS/share/cover.jpg"
        repo.upsert_batch([Video(path=uri, mtime=100.0, cover_path=cover_uri)])

        gen_spy = mocker.spy(thumbnail_cache, "generate")

        resp = client.get("/api/gallery/thumb", params={"path": uri})

        assert resp.status_code == 200, (
            f"反解後應能真的 open() 本機檔案生成 webp，實際 {resp.status_code}"
        )
        assert resp.headers["content-type"] == "image/webp"
        gen_spy.assert_called_once()
        called_cover_fs = gen_spy.call_args[0][0]
        assert called_cover_fs == str(cover), (
            f"generate 應收到反解後的本機路徑 {cover}，實際 {called_cover_fs}"
        )
        assert "//NAS/share" not in called_cover_fs, (
            f"generate 不應收到裸 UNC 映射端字串，實際 {called_cover_fs}"
        )

    def test_get_thumb_miss_reread_uses_reverse_mapped_path(
        self, client, thumb_dir, temp_db, tmp_path, mocker, monkeypatch
    ):
        """#10：generate 成功後 re-read DB 拿到「換過的」cover_path（也是 mapped UNC URI），
        fresh_fs 反解比對也必須是本機路徑，換封面判定（fresh_fs != cover_fs）才正確。
        """
        import core.path_utils as path_utils
        from core.database import Video

        _, repo = temp_db
        monkeypatch.setattr(path_utils, "CURRENT_ENV", "wsl")

        nas_dir = tmp_path / "nas"
        nas_dir.mkdir()
        _make_small_jpg(nas_dir / "cover_a.jpg")  # 只需存在於磁碟，供 generate() 讀
        _make_small_jpg(nas_dir / "cover_b.jpg")
        mappings = {str(nas_dir): "//NAS/share"}

        mocker.patch(
            "web.routers.scanner.load_config",
            return_value={
                "thumbnail_cache_enabled": True,
                "gallery": {"path_mappings": mappings},
            },
        )

        uri = to_file_uri("/movies/wsl_unc_reread.mp4")
        repo.upsert_batch([
            Video(path=uri, mtime=100.0, cover_path="file://///NAS/share/cover_a.jpg"),
        ])

        # generate() 由第一個 cover_a 觸發後，模擬並發換封面：re-read 拿到 cover_b
        real_get_by_path = repo.get_by_path
        calls = {"n": 0}

        def fake_get_by_path(p):
            calls["n"] += 1
            if calls["n"] == 1:
                return real_get_by_path(p)
            # 第二次呼叫（re-read）：換成 cover_b
            v = real_get_by_path(p)
            v.cover_path = "file://///NAS/share/cover_b.jpg"
            return v

        mocker.patch.object(repo, "get_by_path", side_effect=fake_get_by_path)
        mocker.patch("web.routers.scanner.VideoRepository", return_value=repo)
        invalidate_spy = mocker.patch("web.routers.scanner.thumbnail_cache.invalidate")

        resp = client.get("/api/gallery/thumb", params={"path": uri})

        # cover 換了 → invalidate 被呼叫，fallback serve 當前（cover_b）封面
        invalidate_spy.assert_called_once_with(uri)
        assert resp.status_code == 200
        # fallback 應是本機反解後的 cover_b（可真的 open()），非 404/500
        assert resp.headers["content-type"] == "image/jpeg"

    def test_prewarm_worker_generate_uses_reverse_mapped_path(
        self, mocker, tmp_path, monkeypatch, thumb_dir
    ):
        """#11：_prewarm_worker 迴圈內 cover_fs 反解後才傳入 thumbnail_cache.generate。"""
        import core.path_utils as path_utils
        import web.routers.scanner as scanner_mod

        monkeypatch.setattr(path_utils, "CURRENT_ENV", "wsl")

        nas_dir = tmp_path / "nas"
        nas_dir.mkdir()
        cover = _make_small_jpg(nas_dir / "cover.jpg")
        mappings = {str(nas_dir): "//NAS/share"}

        uri_a = "file:///movies/wsl_prewarm.mp4"
        cover_uri = "file://///NAS/share/cover.jpg"

        db_path = mocker.MagicMock()
        db_path.exists.return_value = True
        mocker.patch("web.routers.scanner.get_db_path", return_value=db_path)

        video_a = mocker.MagicMock(cover_path=cover_uri)
        repo_mock = mocker.MagicMock()
        repo_mock.get_all.return_value = []  # iter_missing 被 mock，回值不重要
        repo_mock.get_by_path.side_effect = [video_a, video_a]
        mocker.patch("web.routers.scanner.VideoRepository", return_value=repo_mock)

        mocker.patch(
            "web.routers.scanner.load_config",
            return_value={
                "thumbnail_cache_enabled": True,
                "gallery": {"path_mappings": mappings},
            },
        )
        mocker.patch(
            "web.routers.scanner.thumbnail_cache.iter_missing",
            return_value=[(uri_a, "/stale/cover.jpg")],
        )
        gen_spy = mocker.patch("web.routers.scanner.thumbnail_cache.generate", return_value=True)
        mocker.patch("web.routers.scanner.thumbnail_cache.invalidate")
        mocker.patch("web.routers.scanner._emit_notif")

        scanner_mod._prewarming = True
        try:
            scanner_mod._prewarm_worker()
        finally:
            scanner_mod._prewarming = False

        gen_spy.assert_called_once()
        called_cover_fs = gen_spy.call_args[0][0]
        assert called_cover_fs == str(cover), (
            f"generate 應收到反解後的本機路徑 {cover}，實際 {called_cover_fs}"
        )
        assert "//NAS/share" not in called_cover_fs, (
            f"generate 不應收到裸 UNC 映射端字串，實際 {called_cover_fs}"
        )
