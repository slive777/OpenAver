"""TASK-205b-T3a：瀏覽頁後端 tags_display／hidden_tags 整合測試（T3b 會在同檔續加）。

只用字面標籤字串、tmp_path 的 SQLite 與真的 repo；不 mock
build_context／display_tags／repo 類別（BE-TEST-23）。
"""

import pytest

from core.database import (
    TagAliasRepository,
    TagBlacklistRepository,
    Video,
    VideoRepository,
    init_db,
)
from core.path_utils import to_file_uri


def _showcase_config(video_dir) -> dict:
    return {
        "gallery": {
            "directories": [str(video_dir)],
            "path_mappings": {},
            "min_size_mb": 0,
            "thumbnail_width": 400,
        },
        "scraper": {"video_extensions": [".mp4", ".mkv"], "image_extensions": [".jpg"]},
        "database": {"path": ":memory:"},
        "translate": {"provider": "ollama", "ollama_model": "llama3"},
        "thumbnail_cache_enabled": False,
    }


def _patch_showcase(mocker, db_path, config) -> None:
    mocker.patch("web.routers.showcase.get_db_path", return_value=db_path)
    mocker.patch("web.routers.showcase.load_config", return_value=config)


def _setup_seed_a(tmp_path):
    """種子 A（單檔、有 NFO）：tags＝5 字、user_tags＝2 字。"""
    video_dir = tmp_path / "videos"
    video_dir.mkdir()
    uri = to_file_uri(str(video_dir / "SEED-A.mp4"), {})
    db_path = tmp_path / "seed_a.db"
    init_db(db_path)
    VideoRepository(db_path).upsert_batch([
        Video(
            path=uri,
            number="SEED-A",
            title="Seed A",
            tags=["ハイビジョン", "高畫質", "中出し", "中出", "巨乳"],
            user_tags=["ハイビジョン", "想看"],
            size_bytes=1000,
            mtime=1700000000.0,
            nfo_mtime=1700000100.0,
        ),
    ])
    return {"db_path": db_path, "config": _showcase_config(video_dir), "uri": uri}


def _setup_seed_b(tmp_path):
    """種子 B（併組格）：原始標籤只有ハイビジョン。"""
    video_dir = tmp_path / "videos"
    video_dir.mkdir()
    uri = to_file_uri(str(video_dir / "SEED-B.mp4"), {})
    db_path = tmp_path / "seed_b.db"
    init_db(db_path)
    VideoRepository(db_path).upsert_batch([
        Video(
            path=uri,
            number="SEED-B",
            title="Seed B",
            tags=["ハイビジョン"],
            size_bytes=1000,
            mtime=1700000000.0,
            nfo_mtime=1700000100.0,
        ),
    ])
    return {"db_path": db_path, "config": _showcase_config(video_dir), "uri": uri}


def _apply_setting_s(db_path) -> None:
    TagBlacklistRepository(db_path).add("ハイビジョン")
    TagAliasRepository(db_path).add("ハイビジョン", ["高畫質"])
    TagAliasRepository(db_path).add("中出", ["中出し"])


def _apply_setting_b(db_path) -> None:
    TagBlacklistRepository(db_path).add("ハイビジョン")
    TagAliasRepository(db_path).add("中文字幕", ["ハイビジョン"])


def _setup_seed_c(tmp_path):
    """種子 C（多版本借用）：ABF-900/ 下來源版有 NFO、中字版無 NFO 借用。"""
    video_dir = tmp_path / "videos"
    work_dir = video_dir / "ABF-900"
    work_dir.mkdir(parents=True)
    src_uri = to_file_uri(str(work_dir / "ABF-900.mp4"), {})
    c_uri = to_file_uri(str(work_dir / "ABF-900-C.mkv"), {})
    db_path = tmp_path / "seed_c.db"
    init_db(db_path)
    VideoRepository(db_path).upsert_batch([
        Video(
            path=src_uri,
            number="ABF-900",
            title="ABF-900",
            tags=["ハイビジョン", "中出し"],
            size_bytes=5000,
            mtime=1700000002.0,
            nfo_mtime=1700000100.0,
        ),
        Video(
            path=c_uri,
            number="ABF-900",
            title="ABF-900-C",
            tags=[],
            size_bytes=1000,
            mtime=1700000001.0,
            nfo_mtime=0.0,
        ),
    ])
    return {
        "db_path": db_path,
        "config": _showcase_config(video_dir),
        "src_uri": src_uri,
        "c_uri": c_uri,
    }


@pytest.mark.parametrize("seed", ["A", "B"])
def test_tags_display_masks_renames_and_keeps_raw_tags(client, tmp_path, mocker, seed):
    if seed == "A":
        setup = _setup_seed_a(tmp_path)
        apply = _apply_setting_s
        expect_display = "中出,巨乳"
        expect_hidden = ["ハイビジョン", "高畫質"]
        expect_tags = "ハイビジョン,高畫質,中出し,中出,巨乳"
        expect_user_tags = ["ハイビジョン", "想看"]
    else:
        setup = _setup_seed_b(tmp_path)
        apply = _apply_setting_b
        expect_display = "中文字幕"
        expect_hidden = []
        expect_tags = "ハイビジョン"
        expect_user_tags = []
    _patch_showcase(mocker, setup["db_path"], setup["config"])

    before = client.get("/api/showcase/videos")
    assert before.status_code == 200
    before_data = before.json()
    assert before_data["hidden_tags"] == []
    before_item = next(v for v in before_data["videos"] if v["path"] == setup["uri"])
    assert before_item["tags_display"] == before_item["tags"]
    before_tags = before_item["tags"]
    before_user_tags = before_item["user_tags"]
    before_versions = [(v["path"], v["tags"], v["user_tags"]) for v in before_item["versions"]]

    apply(setup["db_path"])

    after = client.get("/api/showcase/videos")
    assert after.status_code == 200
    after_data = after.json()
    assert after_data["hidden_tags"] == expect_hidden
    for name in after_data["hidden_tags"]:
        assert name == name.strip().lower()
    item = next(v for v in after_data["videos"] if v["path"] == setup["uri"])
    assert item["tags_display"] == expect_display
    assert item["tags"] == expect_tags
    assert item["tags"] == before_tags
    assert item["user_tags"] == expect_user_tags
    assert item["user_tags"] == before_user_tags
    for v in item["versions"]:
        old = next(b for b in before_versions if b[0] == v["path"])
        assert v["tags"] == old[1]
        assert v["user_tags"] == old[2]


def test_borrowed_version_tags_display_uses_reassembled_tags(client, tmp_path, mocker):
    setup = _setup_seed_c(tmp_path)
    _apply_setting_s(setup["db_path"])
    _patch_showcase(mocker, setup["db_path"], setup["config"])

    resp = client.get("/api/showcase/videos")
    assert resp.status_code == 200
    data = resp.json()
    assert data["hidden_tags"] == ["ハイビジョン", "高畫質"]
    assert data["total"] == 1
    work = data["videos"][0]
    by_path = {v["path"]: v for v in work["versions"]}
    assert set(by_path) == {setup["src_uri"], setup["c_uri"]}
    borrowed = by_path[setup["c_uri"]]
    assert borrowed["borrowed_from"] == setup["src_uri"]
    assert borrowed["tags"] == "ハイビジョン,中出し,中文字幕"
    assert borrowed["tags_display"] == "中出,中文字幕"
    assert by_path[setup["src_uri"]]["tags_display"] == "中出"
    assert work["tags_display"] == by_path[work["path"]]["tags_display"]


@pytest.mark.parametrize("branch", ["success", "fail_safe"])
def test_single_video_refresh_keeps_tags_display(client, tmp_path, mocker, branch):
    if branch == "success":
        setup = _setup_seed_c(tmp_path)
        _apply_setting_s(setup["db_path"])
        _patch_showcase(mocker, setup["db_path"], setup["config"])
        resp = client.get("/api/showcase/video", params={"path": setup["c_uri"]})
        assert resp.status_code == 200
        video = resp.json()["video"]
        assert video["path"] == setup["c_uri"]
        assert video["tags_display"] == "中出,中文字幕"
        by_path = {v["path"]: v for v in video["versions"]}
        assert by_path[setup["c_uri"]]["tags_display"] == "中出,中文字幕"
        assert by_path[setup["src_uri"]]["tags_display"] == "中出"
    else:
        setup = _setup_seed_a(tmp_path)
        _apply_setting_s(setup["db_path"])
        _patch_showcase(mocker, setup["db_path"], setup["config"])
        mocker.patch("web.routers.showcase.resolve_work", return_value=None)
        resp = client.get("/api/showcase/video", params={"path": setup["uri"]})
        assert resp.status_code == 200
        assert resp.json()["video"]["tags_display"] == "中出,巨乳"


# ================= TASK-205b-T3b：其餘後端出口（只用字面字串／tmp 庫／真 repo）=================

def test_tags_top_omits_blacklisted_group_before_limit(client, tmp_path, mocker):
    db_path = tmp_path / "tags_top.db"
    init_db(db_path)
    VideoRepository(db_path).upsert_batch([
        Video(path=to_file_uri(str(tmp_path / f"TT-{i:03d}.mp4"), {}), number=f"TT-{i:03d}", title=f"TT-{i:03d}", tags=tags)
        for i, tags in [
            (0, ["ハイビジョン", "高畫質", "巨乳"]),
            (1, ["ハイビジョン", "高畫質", "巨乳"]),
            (2, ["ハイビジョン", "高畫質"]),
        ]
    ])
    mocker.patch("web.routers.tags.get_db_path", return_value=db_path)

    before = client.get("/api/tags/top", params={"limit": 1})
    assert before.status_code == 200
    assert [item["tag"] for item in before.json()["items"]] == ["ハイビジョン"]
    assert before.json()["total_unique_tags"] == 3

    _apply_setting_s(db_path)

    after = client.get("/api/tags/top", params={"limit": 1})
    assert after.status_code == 200
    assert after.json()["items"] == [{"tag": "巨乳", "count": 2}]
    assert after.json()["total_unique_tags"] == 1


def test_insights_snapshot_records_omit_blacklisted_tags(client, tmp_path, mocker):
    setup = _setup_seed_a(tmp_path)
    _apply_setting_s(setup["db_path"])
    mocker.patch("web.routers.insights.get_db_path", return_value=setup["db_path"])
    mocker.patch("web.routers.insights.load_config", return_value=setup["config"])

    resp = client.get("/api/insights/snapshot")
    assert resp.status_code == 200
    records = resp.json()["records"]
    assert len(records) == 1
    assert records[0]["tags"] == ["中出", "巨乳"]


def test_similar_ranking_drops_blacklisted_tag_after_post(client, tmp_path, monkeypatch):
    import core.similar.canonicalize as _canon_mod
    from core.similar.canonicalize import canonical_video_tags
    from core.similar.ranker_cache import SimilarRankerCache

    video_dir = tmp_path / "videos"
    video_dir.mkdir()
    db_path = tmp_path / "similar.db"
    init_db(db_path)
    seed = [
        ("T-001", ["拘束", "制服"], "M0"),
        ("V-001", ["拘束", "f1"], "M1"),
        ("V-002", ["制服", "f2"], "M2"),
        ("F-003", ["fill3"], "M3"),
        ("F-004", ["fill4"], "M4"),
        ("F-005", ["fill5"], "M5"),
        ("F-006", ["fill6"], "M6"),
        ("F-007", ["fill7"], "M7"),
        ("F-008", ["fill8"], "M8"),
    ]
    VideoRepository(db_path).upsert_batch([
        Video(
            path=to_file_uri(str(video_dir / f"{num}.mp4"), {}),
            number=num,
            title=num,
            tags=tags,
            maker=maker,
        )
        for num, tags, maker in seed
    ])

    _canon_mod._invalidate_cache()
    SimilarRankerCache.invalidate()
    monkeypatch.setattr("core.database.connection.get_db_path", lambda: db_path)
    monkeypatch.setattr("core.similar.ranker_cache.VideoRepository", lambda: VideoRepository(db_path))
    monkeypatch.setattr("web.routers.similar.VideoRepository", lambda *a, **k: VideoRepository(db_path))
    try:
        target = VideoRepository(db_path).get_by_number("T-001")
        warm = client.get(f"/api/similar-covers/{target.id}")
        assert warm.status_code == 200
        results = warm.json()["results"]
        assert {r["number"] for r in results[:2]} == {"V-001", "V-002"}
        assert next(r for r in results if r["number"] == "V-001")["cosine_score"] > 0
        assert "拘束" in canonical_video_tags(VideoRepository(db_path).get_by_number("V-001"))

        post = client.post("/api/tag-blacklist", json={"name": "拘束"})
        assert post.status_code == 200

        cold = client.get(f"/api/similar-covers/{target.id}")
        assert cold.status_code == 200
        results2 = cold.json()["results"]
        assert next(r for r in results2 if r["number"] == "V-001")["cosine_score"] == 0.0
        assert results2[0]["number"] == "V-002"
        assert "拘束" not in canonical_video_tags(VideoRepository(db_path).get_by_number("V-001"))
    finally:
        _canon_mod._invalidate_cache()
        SimilarRankerCache.invalidate()


def test_offline_page_genre_masks_and_renames_db_hit(client, tmp_path, mocker):
    from unittest.mock import MagicMock

    setup = _setup_seed_a(tmp_path)
    _apply_setting_s(setup["db_path"])
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    mocker.patch("web.routers.scanner.get_db_path", return_value=setup["db_path"])
    mocker.patch("web.routers.scanner.load_config", return_value={
        "gallery": {"output_dir": str(out_dir), "path_mappings": {}},
        "general": {"theme": "light"},
    })
    mock_generator = MagicMock()
    mocker.patch("web.routers.scanner.HTMLGenerator", return_value=mock_generator)

    resp = client.post("/api/gallery/generate-from-ids", json={"numbers": ["SEED-A"]})
    assert resp.status_code == 200
    videos = mock_generator.generate.call_args.args[0]
    assert len(videos) == 1
    assert videos[0].genre == "中出,巨乳"


@pytest.mark.parametrize("url", ["/api/showcase/videos", "/api/insights/snapshot"])
def test_old_etag_misses_after_blacklist_post(client, tmp_path, mocker, monkeypatch, url):
    setup = _setup_seed_a(tmp_path)
    db_path = setup["db_path"]
    if url == "/api/showcase/videos":
        mocker.patch("web.routers.showcase.get_db_path", return_value=db_path)
        mocker.patch("web.routers.showcase.load_config", return_value=setup["config"])
    else:
        mocker.patch("web.routers.insights.get_db_path", return_value=db_path)
        mocker.patch("web.routers.insights.load_config", return_value=setup["config"])
    monkeypatch.setattr("core.database.connection.get_db_path", lambda: db_path)

    first = client.get(url)
    assert first.status_code == 200
    etag = first.headers["etag"]
    assert client.get(url, headers={"If-None-Match": etag}).status_code == 304

    post = client.post("/api/tag-blacklist", json={"name": "高畫質"})
    assert post.status_code == 200

    third = client.get(url, headers={"If-None-Match": etag})
    assert third.status_code == 200
    if url == "/api/showcase/videos":
        body = third.json()
        assert body["hidden_tags"] == ["高畫質"]
        item = next(v for v in body["videos"] if v["path"] == setup["uri"])
        assert "高畫質" not in item["tags_display"].split(",")
    else:
        assert "高畫質" not in third.json()["records"][0]["tags"]
