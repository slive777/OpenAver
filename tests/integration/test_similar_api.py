"""
tests/integration/test_similar_api.py
integration tests for GET /api/similar-covers/* endpoints（57b-T2）

Strategy:
- TestClient + 獨立 mini-app（只掛 similar router，不用 web.app 避免 clip router 衝突）
- in-memory SQLite via tmp_path（不依賴真 DB）
- patch VideoRepository to use tmp_path DB
- patch SimilarRankerCache.get() to return a real ranker built from test corpus
"""
from __future__ import annotations

from urllib.parse import quote

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.database import init_db, Video, VideoRepository
from core.path_utils import to_file_uri, uri_to_fs_path
from core.similar.ranker import SimilarRanker
from core.similar.ranker_cache import SimilarRankerCache
from web.routers.similar import router as similar_router


def _make_test_app() -> FastAPI:
    """建立只掛 similar_router 的最小 FastAPI app，用於 integration test。"""
    app = FastAPI()
    app.include_router(similar_router)
    return app


@pytest.fixture(autouse=True)
def _isolate_canonicalize_alias_repo():
    """本檔 7 處 `SimilarRanker(corpus)` 建構都會經 canonicalize() 的
    `_load_merged_map()`：module-level cache 為 None 時 lazy-import
    core.database.TagAliasRepository 連真實 DB（同手法見
    tests/unit/test_similar_canonicalize.py 的 isolate_canonicalize_cache／
    127b-T4 已修正的 test_ranker_cache.py）。集中在檔案層級的 autouse fixture，
    不逐一 patch 7 個呼叫點，也不是 conftest.py 層的全域機制——僅本檔生效。"""
    from unittest.mock import MagicMock, patch as _patch
    from core.similar.canonicalize import _invalidate_cache

    _invalidate_cache()
    mock_alias_repo = MagicMock()
    mock_alias_repo.get_all.return_value = []
    with _patch("core.database.TagAliasRepository", return_value=mock_alias_repo), \
         _patch("core.database.TagBlacklistRepository", return_value=MagicMock(**{"get_all.return_value": []})):
        yield
    _invalidate_cache()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EXPECTED_RESULT_KEYS = frozenset({
    "video_id",
    "number",
    "title",
    "cover_path",
    "cover_url",
    "cover_full_url",  # 71c：恆原圖 url，供燈箱 blur-up .lb-full overlay（slip-through 路徑必要）
    "cosine_score",
    "penalty_applied",
    "actresses",
})

_EXPECTED_QUERY_VIDEO_KEYS = frozenset({
    "video_id",
    "number",
    "title",
    "cover_url",
})

_EXPECTED_TOP_KEYS = frozenset({
    "video_id",
    "model_id",
    "query_video",
    "results",
})


def _make_video(
    idx: int,
    number: str | None = None,
    tags: list[str] | None = None,
    maker: str = "MakerA",
    series: str | None = None,
    actresses: list[str] | None = None,
    release_date: str = "2023-01-01",
    duration: int = 90,
    cover_path: str = "",
) -> Video:
    """Build a Video for upsert; path must be unique."""
    return Video(
        path=to_file_uri(f"/fake/video_{idx:03d}.mp4"),
        number=number or f"ABC-{idx:03d}",
        title=f"Test Video {idx:03d}",
        maker=maker,
        series=series,
        actresses=actresses or [],
        tags=tags or ["高畫質", "單體作品", f"tag{idx}"],
        release_date=release_date,
        duration=duration,
        cover_path=cover_path,
        mtime=float(idx),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_with_corpus(tmp_path):
    """建立 13 部影片的測試 DB（1 target + 12 candidates）。
    回傳 (db_path, target_id, target_number)。
    """
    db_path = tmp_path / "test.db"
    init_db(db_path)
    repo = VideoRepository(db_path)

    # target video
    target = _make_video(
        idx=1,
        number="TEST-001",
        tags=["高畫質", "單體作品", "美乳", "巨乳"],
        maker="MakerA",
        actresses=[],
    )
    target_id = repo.upsert(target)

    # 12 candidate videos — 共用部分 tag 讓 ranker 可以找到它們
    candidates = [
        _make_video(
            idx=i,
            number=f"TEST-{i:03d}",
            tags=["高畫質", "單體作品", "美乳"],
            maker="MakerA",
        )
        for i in range(2, 14)
    ]
    repo.upsert_batch(candidates)

    return db_path, target_id, "TEST-001"


@pytest.fixture
def client_with_corpus(db_with_corpus, monkeypatch):
    """TestClient with patched VideoRepository + SimilarRankerCache."""
    db_path, target_id, target_number = db_with_corpus

    # Patch VideoRepository to use test DB（router 裡 VideoRepository() 無參數呼叫）
    real_repo_cls = VideoRepository

    class _PatchedRepo(real_repo_cls):
        def __init__(self, db_path_arg=None):
            super().__init__(db_path)

    monkeypatch.setattr("web.routers.similar.VideoRepository", _PatchedRepo)

    # Build a real ranker from test corpus and patch cache
    repo = VideoRepository(db_path)
    corpus = repo.get_all()
    ranker = SimilarRanker(corpus)
    monkeypatch.setattr(SimilarRankerCache, "_instance", ranker)

    yield TestClient(_make_test_app()), target_id, target_number

    # cleanup: 清 singleton 避免汙染其他測試
    SimilarRankerCache._instance = None


@pytest.fixture
def db_single_video(tmp_path):
    """只有 target 一部影片的 DB（corpus size = 1）。"""
    db_path = tmp_path / "single.db"
    init_db(db_path)
    repo = VideoRepository(db_path)
    vid = _make_video(idx=1, number="SOLO-001")
    vid_id = repo.upsert(vid)
    return db_path, vid_id, "SOLO-001"


@pytest.fixture
def client_single_video(db_single_video, monkeypatch):
    """TestClient with only 1 video in corpus."""
    db_path, vid_id, number = db_single_video

    real_repo_cls = VideoRepository

    class _PatchedRepo(real_repo_cls):
        def __init__(self, db_path_arg=None):
            super().__init__(db_path)

    monkeypatch.setattr("web.routers.similar.VideoRepository", _PatchedRepo)

    repo = VideoRepository(db_path)
    corpus = repo.get_all()
    ranker = SimilarRanker(corpus)
    monkeypatch.setattr(SimilarRankerCache, "_instance", ranker)

    yield TestClient(_make_test_app()), vid_id, number

    SimilarRankerCache._instance = None


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestSimilarCoversAPI:

    # --- T1: by-number 200 + 12 結果 ---

    def test_by_number_200_12_results(self, client_with_corpus):
        client, target_id, target_number = client_with_corpus
        resp = client.get(f"/api/similar-covers/by-number/{target_number}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 12

    # --- T2: by-id 200 + 12 結果 ---


    # --- T3: by-number 404 ---

    def test_by_number_404(self, client_with_corpus):
        client, _, _ = client_with_corpus
        resp = client.get("/api/similar-covers/by-number/NONEXISTENT-999")
        assert resp.status_code == 404

    # --- T4: by-id 404 ---


    # --- T5: response shape 含全部 v0.8.6 key ---


    def test_response_shape_result_keys(self, client_with_corpus):
        client, target_id, _ = client_with_corpus
        resp = client.get(f"/api/similar-covers/{target_id}")
        results = resp.json()["results"]
        assert len(results) > 0, "results 為空，無法驗 key set"
        for r in results:
            missing = _EXPECTED_RESULT_KEYS - set(r.keys())
            assert not missing, f"result item 缺少 key：{missing}，item={r}"

    # --- T6: model_id == "rule-based:v1" ---


    # --- T7: penalty_applied is False for all results ---


    # --- T8: corpus 只有 target 一部 → results: [] (200 不報錯) ---

    def test_single_video_corpus_returns_empty_results(self, client_single_video):
        client, vid_id, _ = client_single_video
        resp = client.get(f"/api/similar-covers/{vid_id}")
        assert resp.status_code == 200
        assert resp.json()["results"] == []

    # --- T9: target 全 hot tag + corpus ≥ 12 部 → results 仍 12 部 (Tier 3/4 fallback) ---

    def test_hot_tag_target_still_returns_12_results(self, tmp_path, monkeypatch):
        """target 的 tags 全為 hot tag（IDF=0），Tier 1/2 retrieve 無結果，
        靠 Tier 3（同 prefix random）或 Tier 4（全庫 random）兜底仍能回 12 部。
        """
        db_path = tmp_path / "hot_tag.db"
        init_db(db_path)
        repo = VideoRepository(db_path)

        # 超高頻 tag → 全庫都有 → IDF = 0 → "hot"
        hot_tags = ["高畫質"]  # 全部影片都有此 tag → IDF 會是 0

        # target（prefix = TEST）
        target = _make_video(idx=1, number="TEST-001", tags=hot_tags)
        repo.upsert(target)

        # 12 candidates 全用同 prefix TEST，讓 Tier 3 可以接住
        candidates = [
            _make_video(idx=i, number=f"TEST-{i:03d}", tags=hot_tags)
            for i in range(2, 14)
        ]
        repo.upsert_batch(candidates)

        real_repo_cls = VideoRepository

        class _PatchedRepo(real_repo_cls):
            def __init__(self, _=None):
                super().__init__(db_path)

        monkeypatch.setattr("web.routers.similar.VideoRepository", _PatchedRepo)

        corpus = repo.get_all()
        ranker = SimilarRanker(corpus)
        monkeypatch.setattr(SimilarRankerCache, "_instance", ranker)

        client = TestClient(_make_test_app())
        try:
            target_row = repo.get_by_number("TEST-001")
            resp = client.get(f"/api/similar-covers/{target_row.id}")
            assert resp.status_code == 200
            assert len(resp.json()["results"]) == 12
        finally:
            SimilarRankerCache._instance = None

    # --- T10: limit query parameter 生效 ---


    # --- 98b-T1: 每個 result 含 auto_focal / crop_mode 兩欄 ---


    def test_focal_fields_reflect_fresh_db_after_cached_ranker(
        self, client_with_corpus, db_with_corpus, seed_crop_mode
    ):
        """Codex PR#105 P2：SimilarRankerCache 已建好後，寫 auto_focal/crop_mode 不
        invalidate 整個 ranker cache（焦點/裁切模式是顯示欄位、不影響排序特徵，比照
        upsert/delete invalidate 代價不對稱）。similar-covers 端點改用 fresh DB 值覆蓋
        ranker 快取 Video 物件的 auto_focal/crop_mode，驗證卡片不會停留在 warmup 當下的
        stale 值。crop_mode 這欄用 conftest 的 test-only `seed_crop_mode` 直接寫 DB
        （production 已無獨立的 update_crop_mode mutator，見 99a-T7 retire），只為模擬
        「DB 已 commit 但未 invalidate cache」這個前置狀態，不代表真實寫入路徑。
        """
        client, target_id, target_number = client_with_corpus
        db_path, _, _ = db_with_corpus

        resp_before = client.get(f"/api/similar-covers/by-number/{target_number}")
        results_before = resp_before.json()["results"]
        assert len(results_before) > 0
        victim = results_before[0]
        assert victim["auto_focal"] == ""       # baseline：_make_video 未設 auto_focal
        assert victim["crop_mode"] == "auto"     # Video dataclass 預設值

        # 直接寫 DB（模擬 focal 欄位已 commit，但未 invalidate ranker cache，鏡射
        # web/routers/showcase.py 的 crop-mode / detect-focal 端點）
        repo = VideoRepository(db_path)
        victim_video = repo.get_by_id(victim["video_id"])
        assert repo.update_auto_focal(victim_video.path, "0.6000,0.3000", victim_video.cover_path)
        assert seed_crop_mode(repo, victim_video.path, "default")

        resp_after = client.get(f"/api/similar-covers/by-number/{target_number}")
        results_after = resp_after.json()["results"]
        victim_after = next(r for r in results_after if r["video_id"] == victim["video_id"])
        assert victim_after["auto_focal"] == "0.6000,0.3000", (
            "similar-covers 仍回傳 ranker 快取的 stale 焦點，未 fresh 覆蓋"
        )
        assert victim_after["crop_mode"] == "default", (
            "similar-covers 仍回傳 ranker 快取的 stale crop_mode，未 fresh 覆蓋"
        )

    # --- T11: target 不在 results 中 ---


# ---------------------------------------------------------------------------
# feature/71 T4 — thumbnail_cache cover_url switch
# ---------------------------------------------------------------------------

class TestSimilarThumbnailCacheCoverUrl:
    """enabled → thumb url（key = video path）；disabled → image url（字節不變）。"""

    @pytest.fixture
    def client_with_covers(self, tmp_path, monkeypatch):
        """target + 12 candidates，每部都有 cover_path（驗 thumb url 用 v.path 非 cover）。"""
        db_path = tmp_path / "covers.db"
        init_db(db_path)
        repo = VideoRepository(db_path)

        def _cover(idx):
            return to_file_uri(f"/fake/cover_{idx:03d}.jpg")

        target = _make_video(
            idx=1, number="TEST-001",
            tags=["高畫質", "單體作品", "美乳", "巨乳"],
            maker="MakerA", cover_path=_cover(1),
        )
        target_id = repo.upsert(target)
        candidates = [
            _make_video(idx=i, number=f"TEST-{i:03d}",
                        tags=["高畫質", "單體作品", "美乳"],
                        maker="MakerA", cover_path=_cover(i))
            for i in range(2, 14)
        ]
        repo.upsert_batch(candidates)

        real_repo_cls = VideoRepository

        class _PatchedRepo(real_repo_cls):
            def __init__(self, db_path_arg=None):
                super().__init__(db_path)

        monkeypatch.setattr("web.routers.similar.VideoRepository", _PatchedRepo)

        repo2 = VideoRepository(db_path)
        corpus = repo2.get_all()
        ranker = SimilarRanker(corpus)
        monkeypatch.setattr(SimilarRankerCache, "_instance", ranker)

        def _set_flag(enabled):
            monkeypatch.setattr(
                "web.routers.similar.load_config",
                lambda: {"thumbnail_cache_enabled": enabled},
            )

        yield TestClient(_make_test_app()), target_id, _set_flag, repo2
        SimilarRankerCache._instance = None

    def test_enabled_cover_url_is_thumb_keyed_by_video_path(self, client_with_covers):
        """邊界 6：enabled → cover_url = /api/gallery/thumb?path=quote(v.path)，非 cover。"""
        client, target_id, set_flag, repo = client_with_covers
        set_flag(True)
        resp = client.get(f"/api/similar-covers/{target_id}")
        assert resp.status_code == 200
        data = resp.json()

        target = repo.get_by_id(target_id)
        qv_expected = f"/api/gallery/thumb?path={quote(target.path, safe='')}"
        assert data["query_video"]["cover_url"] == qv_expected

        for r in data["results"]:
            v = repo.get_by_id(r["video_id"])
            expected = f"/api/gallery/thumb?path={quote(v.path, safe='')}"
            assert r["cover_url"] == expected
            # thumb key 必須是 video path，不是 cover path
            assert quote(r["cover_path"], safe="") not in r["cover_url"]
            assert quote(uri_to_fs_path(r["cover_path"]), safe="") not in r["cover_url"]


    def test_cover_full_url_is_always_original_image(self, client_with_covers):
        """71c 邊界 9：cover_full_url 恆為原圖 /api/gallery/image?path=...，不受 enabled 影響。

        slip-through 路徑（星座退出）的 similarExitVideo.cover_full_url 若缺失 → .lb-full opacity:0 卡死。
        """
        client, target_id, set_flag, repo = client_with_covers
        for enabled_flag in [True, False]:
            set_flag(enabled_flag)
            resp = client.get(f"/api/similar-covers/{target_id}")
            assert resp.status_code == 200
            data = resp.json()
            for r in data["results"]:
                # cover_full_url 必須存在且為原圖（/api/gallery/image? 而非 /api/gallery/thumb?）
                assert "cover_full_url" in r, (
                    f"similar result 缺 cover_full_url（enabled={enabled_flag}）"
                )
                if r["cover_path"]:
                    # 有封面時 cover_full_url 必須指向 image endpoint
                    assert r["cover_full_url"].startswith("/api/gallery/image?path="), (
                        f"cover_full_url 應為 /api/gallery/image?path=...（enabled={enabled_flag}），"
                        f"got {r['cover_full_url']!r}"
                    )
                    # 無論 enabled 是否開啟，cover_full_url 不走 thumb endpoint
                    assert "/api/gallery/thumb?" not in r["cover_full_url"], (
                        f"cover_full_url 不應走 /api/gallery/thumb?（enabled={enabled_flag}）"
                    )


class TestSimilarCoverUrlPathMappingsReverse:
    """TASK-91-T2a #3,#4: `_build_cover_url`/`_build_cover_full_url` 在 WSL +
    UNC path_mappings 環境下必須反解成真正能 open() 的本機路徑，而不是留下裸
    uri_to_fs_path() 產生的映射端 UNC 字串（get_image 端沒有第二次反解機會）。
    """

    @pytest.fixture
    def client_with_wsl_unc_cover(self, tmp_path, monkeypatch):
        import core.path_utils as path_utils

        monkeypatch.setattr(path_utils, "CURRENT_ENV", "wsl")

        db_path = tmp_path / "wsl_unc.db"
        init_db(db_path)
        repo = VideoRepository(db_path)

        unc_cover = "file://///NAS/share/cover_001.jpg"
        target = _make_video(idx=1, number="TEST-001",
                              tags=["高畫質", "單體作品", "美乳"], cover_path=unc_cover)
        target_id = repo.upsert(target)
        candidates = [
            _make_video(idx=i, number=f"TEST-{i:03d}",
                        tags=["高畫質", "單體作品", "美乳"],
                        cover_path=("file://///NAS/share/cover_%03d.jpg" % i))
            for i in range(2, 14)
        ]
        repo.upsert_batch(candidates)

        real_repo_cls = VideoRepository

        class _PatchedRepo(real_repo_cls):
            def __init__(self, _=None):
                super().__init__(db_path)

        monkeypatch.setattr("web.routers.similar.VideoRepository", _PatchedRepo)
        corpus = repo.get_all()
        ranker = SimilarRanker(corpus)
        monkeypatch.setattr(SimilarRankerCache, "_instance", ranker)
        monkeypatch.setattr(
            "web.routers.similar.load_config",
            lambda: {
                "thumbnail_cache_enabled": False,
                "gallery": {"path_mappings": {"/home/user/nas": "//NAS/share"}},
            },
        )

        yield TestClient(_make_test_app()), target_id
        SimilarRankerCache._instance = None

    def test_cover_url_reverse_maps_wsl_unc(self, client_with_wsl_unc_cover):
        from urllib.parse import unquote

        client, target_id = client_with_wsl_unc_cover
        resp = client.get(f"/api/similar-covers/{target_id}")
        assert resp.status_code == 200
        data = resp.json()

        qv_url = unquote(data["query_video"]["cover_url"])
        assert "/home/user/nas/cover_001.jpg" in qv_url, (
            f"cover_url 應反解為本機路徑，實際: {qv_url}"
        )
        assert "//NAS/share/cover_001.jpg" not in qv_url, (
            f"cover_url 不應殘留裸 UNC 映射端字串，實際: {qv_url}"
        )

    def test_cover_full_url_reverse_maps_wsl_unc(self, client_with_wsl_unc_cover):
        from urllib.parse import unquote

        client, target_id = client_with_wsl_unc_cover
        resp = client.get(f"/api/similar-covers/{target_id}")
        assert resp.status_code == 200
        data = resp.json()

        for r in data["results"]:
            full_url = unquote(r["cover_full_url"])
            assert "/home/user/nas/" in full_url, (
                f"cover_full_url 應反解為本機路徑，實際: {full_url}"
            )
            assert "//NAS/share/" not in full_url, (
                f"cover_full_url 不應殘留裸 UNC 映射端字串，實際: {full_url}"
            )


# ---------------------------------------------------------------------------
# Codex P1 — legacy DB startup path regression test
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# TASK-200b-T2 ③b：相似片封面網址版本記號（檔尾新 class，既有不動，自建夾具）
# ---------------------------------------------------------------------------

class TestSimilarCoverSignature:
    """有簽章列 cover_full_url 帶 &v=<mtime_ns>-<size>；關閉時 cover_url 同值；query_video 也帶。"""

    MTIME_NS = 1_700_000_000_123_456_789
    SIZE = 123456

    @pytest.fixture
    def client_with_sig(self, tmp_path, monkeypatch):
        db_path = tmp_path / "sig.db"
        init_db(db_path)
        repo = VideoRepository(db_path)

        def _cover(idx):
            return to_file_uri(f"/fake/sig_cover_{idx:03d}.jpg")

        target = _make_video(
            idx=1, number="SIG-001", tags=["高畫質", "單體作品", "美乳", "巨乳"],
            maker="MakerA", cover_path=_cover(1),
        )
        target_id = repo.upsert(target)
        candidates = [
            _make_video(
                idx=i, number=f"SIG-{i:03d}", tags=["高畫質", "單體作品", "美乳"],
                maker="MakerA", cover_path=_cover(i),
            )
            for i in range(2, 14)
        ]
        repo.upsert_batch(candidates)
        assert repo.set_cover_signature(
            to_file_uri("/fake/video_001.mp4"), self.MTIME_NS, self.SIZE) is True
        assert repo.set_cover_signature(
            to_file_uri("/fake/video_002.mp4"), self.MTIME_NS, self.SIZE) is True

        real_repo_cls = VideoRepository

        class _PatchedRepo(real_repo_cls):
            def __init__(self, db_path_arg=None):
                super().__init__(db_path)

        monkeypatch.setattr("web.routers.similar.VideoRepository", _PatchedRepo)

        corpus = VideoRepository(db_path).get_all()
        ranker = SimilarRanker(corpus)
        monkeypatch.setattr(SimilarRankerCache, "_instance", ranker)

        def _set_flag(enabled):
            monkeypatch.setattr(
                "web.routers.similar.load_config",
                lambda: {"thumbnail_cache_enabled": enabled},
            )

        yield TestClient(_make_test_app()), target_id, _set_flag, VideoRepository(db_path)
        SimilarRankerCache._instance = None

    def test_similar_cover_urls_carry_signature(self, client_with_sig):
        client, target_id, set_flag, repo = client_with_sig
        suffix = f"&v={self.MTIME_NS}-{self.SIZE}"

        set_flag(False)
        resp = client.get(f"/api/similar-covers/{target_id}")
        assert resp.status_code == 200
        data = resp.json()

        assert data["query_video"]["cover_url"].endswith(suffix)
        results = {r["video_id"]: r for r in data["results"]}
        signed = repo.get_by_path(to_file_uri("/fake/video_002.mp4"))
        assert results[signed.id]["cover_full_url"].endswith(suffix)
        assert results[signed.id]["cover_url"].endswith(suffix)
        unsigned = repo.get_by_path(to_file_uri("/fake/video_003.mp4"))
        assert results[unsigned.id]["cover_full_url"].startswith("/api/gallery/image?path=")
        assert "&v=" not in results[unsigned.id]["cover_full_url"]

        set_flag(True)
        resp = client.get(f"/api/similar-covers/{target_id}")
        data = resp.json()
        results = {r["video_id"]: r for r in data["results"]}
        assert results[signed.id]["cover_full_url"].endswith(suffix)
        assert "/api/gallery/thumb?" in results[signed.id]["cover_url"]
        assert "&v=" not in results[signed.id]["cover_url"]
