"""TASK-198b-T2：多版本收成「一部作品」的整合測試（恰 4 支）。

共用片庫（6 列 → 3 作品）：
- ABF-348/：插入順序刻意打亂（先 LTX、再 4K、最後中字），預期預設順序為
  中字 → 4K → LTX（只靠路徑字典序會是 -C < -LTX < .mp4，不等於預期）。
- ABF-360/：中字版排第一（預設）但沒資料，第二順位有資料（data_source=1）。
- SOLO-001/：單版本對照組。
"""

import datetime

import pytest

from core.database import Video, VideoRepository, init_db
from core.media_probe import ProbeResult
from core.path_utils import to_file_uri
from core.search_providers.relay import MakerCapsulePolicy


def _ok_probe(*, width=1920, height=1080) -> ProbeResult:
    return ProbeResult(
        status="ok",
        reason="",
        width=width,
        height=height,
        video_format="AVC",
        duration_ms=7_380_000,
        hdr_format=None,
        frame_rate=23.976,
        overall_bitrate=5_000_000,
        container="MPEG-4",
        audio_langs=("ja",),
        subtitle_langs=(),
        truncated=False,
    )


@pytest.fixture
def works_lib(tmp_path):
    video_dir = tmp_path / "videos"
    d348 = video_dir / "ABF-348"
    d348.mkdir(parents=True)
    d360 = video_dir / "ABF-360"
    d360.mkdir(parents=True)
    dsolo = video_dir / "SOLO-001"
    dsolo.mkdir(parents=True)

    c_uri = to_file_uri(str(d348 / "ABF-348-C.mkv"), {})
    o_uri = to_file_uri(str(d348 / "ABF-348.mp4"), {})
    ltx_uri = to_file_uri(str(d348 / "ABF-348-LTX.mkv"), {})
    c360_uri = to_file_uri(str(d360 / "ABF-360-C.mkv"), {})
    o360_uri = to_file_uri(str(d360 / "ABF-360.mp4"), {})
    solo_uri = to_file_uri(str(dsolo / "SOLO-001.mp4"), {})
    cover348 = to_file_uri(str(d348 / "poster.jpg"), {})

    db_path = tmp_path / "versions.db"
    init_db(db_path)
    repo = VideoRepository(db_path)
    repo.upsert_batch([
        Video(
            path=ltx_uri, number="ABF-348", title="ABF-348-LTX",
            actresses=[], maker="", release_date="", tags=[],
            user_tags=["想看"], size_bytes=777, mtime=1700000003.0,
            nfo_mtime=0.0,
        ),
        Video(
            path=o_uri, number="ABF-348", title="片名乙",
            actresses=[], maker="MakerX", release_date="",
            tags=["單體作品"], size_bytes=5000, mtime=1700000002.0,
            nfo_mtime=1700000100.0,
        ),
        Video(
            path=c_uri, number="ABF-348", title="片名甲",
            original_title="オリジナル甲", actresses=["女優A"],
            maker="MakerX", release_date="2024-05-01",
            tags=["中文字幕", "單體作品"], cover_path=cover348,
            size_bytes=1000, mtime=1700000001.0, nfo_mtime=1700000100.0,
        ),
        Video(
            path=c360_uri, number="ABF-360", title="ABF-360-C",
            maker="", tags=[], size_bytes=100, mtime=1700000010.0,
            nfo_mtime=0.0,
        ),
        Video(
            path=o360_uri, number="ABF-360", title="片名丙",
            maker="MakerY", tags=[], size_bytes=200, mtime=1700000011.0,
            nfo_mtime=1700000200.0,
        ),
        Video(
            path=solo_uri, number="SOLO-001", title="Solo",
            maker="MakerS", tags=[], size_bytes=300,
            mtime=1700000020.0, nfo_mtime=1700000200.0,
        ),
    ])
    repo.set_user_rating(ltx_uri, 1)
    assert repo.update_media_probe(
        c_uri, _ok_probe(width=1920, height=1080), 1700000001.0, 1000
    ) is True
    assert repo.update_media_probe(
        o_uri, _ok_probe(width=3840, height=2160), 1700000002.0, 5000
    ) is True
    assert repo.update_media_probe(
        ltx_uri, _ok_probe(width=1920, height=1080), 1700000003.0, 777
    ) is True

    config = {
        "gallery": {
            "directories": [str(video_dir)],
            "path_mappings": {},
            "min_size_mb": 0,
            "thumbnail_width": 400,
        },
        "scraper": {"video_extensions": [".mp4", ".mkv"], "image_extensions": [".jpg"]},
        "database": {"path": ":memory:"},
        "translate": {"provider": "ollama", "ollama_model": "llama3"},
    }
    return {
        "db_path": db_path,
        "config": config,
        "video_dir": video_dir,
        "c_uri": c_uri,
        "o_uri": o_uri,
        "ltx_uri": ltx_uri,
        "c360_uri": c360_uri,
        "o360_uri": o360_uri,
        "solo_uri": solo_uri,
    }


def _patch_showcase(mocker, setup):
    mocker.patch("web.routers.showcase.get_db_path", return_value=setup["db_path"])
    mocker.patch("web.routers.showcase.load_config", return_value=setup["config"])


def test_versions_collapse_into_one_work(client, works_lib, mocker):
    _patch_showcase(mocker, works_lib)
    resp = client.get("/api/showcase/videos")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["videos"]) == 3

    work = next(v for v in data["videos"] if v["path"] == works_lib["c_uri"])
    assert [v["path"] for v in work["versions"]] == [
        works_lib["c_uri"], works_lib["o_uri"], works_lib["ltx_uri"],
    ]
    assert work["title"] == "片名甲"

    c_v, o_v, ltx_v = work["versions"]

    assert c_v["borrowed_from"] == ""
    assert c_v["version_kinds"] == ["subtitle"]

    assert o_v["borrowed_from"] == ""
    assert o_v["title"] == "片名乙"
    assert o_v["version_kinds"] == []

    assert ltx_v["path"] == works_lib["ltx_uri"]
    assert ltx_v["title"] == "片名甲"
    assert ltx_v["borrowed_from"] == works_lib["c_uri"]
    assert ltx_v["size"] == 777
    assert ltx_v["resolution_tier"] == "FHD"
    assert ltx_v["has_nfo"] is False
    assert "LTX" in ltx_v["tags"].split(",")
    assert "中文字幕" not in ltx_v["tags"].split(",")
    assert ltx_v["cover_url"] == c_v["cover_url"]
    assert ltx_v["has_cover"] is True
    assert ltx_v["version_kinds"] == ["ltx"]

    b360 = next(v for v in data["videos"] if v["path"] == works_lib["c360_uri"])
    assert b360["title"] == "片名丙"

    solo = next(v for v in data["videos"] if v["path"] == works_lib["solo_uri"])
    assert solo["versions"] == []
    assert solo["borrowed_from"] == ""
    assert "version_kinds" not in solo


def test_work_level_rating_and_tags_union(client, works_lib, mocker):
    _patch_showcase(mocker, works_lib)
    resp = client.get("/api/showcase/videos")
    assert resp.status_code == 200
    work = next(
        v for v in resp.json()["videos"] if v["path"] == works_lib["c_uri"]
    )
    assert work["user_rating"] == 1
    assert "想看" in work["user_tags"]
    for v in work["versions"]:
        assert v["user_rating"] == 1
        assert "想看" in v["user_tags"]


def test_single_video_top_is_requested_version(client, works_lib, mocker):
    _patch_showcase(mocker, works_lib)

    r = client.get("/api/showcase/video", params={"path": works_lib["ltx_uri"]})
    assert r.status_code == 200
    video = r.json()["video"]
    assert video["path"] == works_lib["ltx_uri"]
    assert len(video["versions"]) == 3
    assert [v["path"] for v in video["versions"]] == [
        works_lib["c_uri"], works_lib["o_uri"], works_lib["ltx_uri"],
    ]
    assert video["title"] == "片名甲"
    assert video["borrowed_from"] != ""

    r2 = client.get("/api/showcase/video", params={"path": works_lib["c_uri"]})
    assert r2.status_code == 200
    assert r2.json()["video"]["path"] == works_lib["c_uri"]

    r3 = client.get("/api/showcase/video", params={"path": works_lib["solo_uri"]})
    assert r3.status_code == 200
    solo = r3.json()["video"]
    assert solo["versions"] == []
    assert solo["borrowed_from"] == ""
    assert "src" not in solo


def test_analysis_and_maker_counts_follow_works(client, works_lib, mocker):
    mocker.patch(
        "web.routers.insights.get_db_path", return_value=works_lib["db_path"]
    )
    mocker.patch(
        "web.routers.insights.load_config", return_value=works_lib["config"]
    )
    snap = client.get("/api/insights/snapshot")
    assert snap.status_code == 200
    body = snap.json()
    assert body["logicalTitles"] == 3
    assert body["physicalRows"] == 6
    assert len(body["records"]) == 3

    _patch_showcase(mocker, works_lib)
    show = client.get("/api/showcase/videos")
    assert show.status_code == 200
    assert show.json()["total"] == 3
    assert body["logicalTitles"] == show.json()["total"]

    mocker.patch(
        "web.routers.search.get_db_path", return_value=works_lib["db_path"]
    )
    mocker.patch(
        "web.routers.search._today", return_value=datetime.date(2026, 1, 1)
    )
    mocker.patch(
        "web.routers.search.maker_capsule_policy",
        return_value=MakerCapsulePolicy(True, False),
    )
    mocker.patch(
        "web.routers.search.get_configured_gallery_dirs",
        return_value=({to_file_uri(str(works_lib["video_dir"]), {})}, {}),
    )
    caps = client.get("/api/search/maker-capsules")
    assert caps.status_code == 200
    by_maker = {m["maker"]: m for m in caps.json()["makers"]}
    assert by_maker["MakerX"]["total"] == 1
    assert by_maker["MakerY"]["total"] == 1
    assert by_maker["MakerS"]["total"] == 1
    assert "" not in by_maker
