"""tests/integration/test_showcase_files_actions.py — TASK-200b-T6。

POST /api/showcase/video/poster-regenerate 與 POST /api/showcase/video/reprobe。
harness 自建（複製 T2／T5 形狀，不 import 其他測試檔）。
"""
from __future__ import annotations

import hashlib
import os
import random
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageChops, ImageStat

from core.database import Video, VideoRepository, init_db
from core.media_probe import ProbeResult
from core.path_utils import to_file_uri


def _stripes(path, seed, size=(800, 538)):
    rng = random.Random(seed)
    image = Image.new("RGB", size)
    for x in range(size[0]):
        color = tuple(rng.randrange(256) for _ in range(3))
        for y in range(size[1]):
            image.putpixel((x, y), color)
    image.save(path, quality=100, subsampling=0)


def _solid(path, color, size=(142, 200)):
    Image.new("RGB", size, color).save(path, quality=95, subsampling=0)


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _snapshot_tree(root):
    root = Path(root)
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out[str(p.relative_to(root))] = (_digest(p), p.stat().st_mtime_ns)
    return out


def _wire(monkeypatch, *, db_path, config):
    monkeypatch.setattr("web.routers.showcase_files.get_db_path", lambda: db_path)
    monkeypatch.setattr("web.routers.showcase_files.load_config", lambda: config)
    monkeypatch.setattr("core.readonly_paths.get_db_path", lambda: db_path)
    from web.app import app
    return TestClient(app)


def _expected_x0(focal_x, size=(800, 538)):
    win_w = round(0.71 * size[1])
    return max(0, min(round(focal_x * size[0] - win_w / 2), size[0] - win_w))


def _actual_x0(poster_fs, cover_fs):
    with Image.open(cover_fs) as src, Image.open(poster_fs) as out:
        win_w = round(0.71 * src.height)
        assert out.size == (win_w, src.height)
        scores = {}
        for x in range(0, src.width - win_w + 1):
            diff = ImageChops.difference(out, src.crop((x, 0, x + win_w, src.height)))
            scores[x] = sum(ImageStat.Stat(diff).mean)
        return min(scores, key=scores.get)


def _ok_probe(*, width=3840, height=2160, video_format="HEVC", duration_ms=7_200_000):
    return ProbeResult(
        status="ok", reason="", width=width, height=height,
        video_format=video_format, duration_ms=duration_ms,
        hdr_format=None, frame_rate=23.976, overall_bitrate=12_000_000,
        container="MPEG-4", audio_langs=("ja",), subtitle_langs=("zh",),
        truncated=False,
    )


def _unreadable_probe():
    return ProbeResult(
        status="unreadable", reason="io error", width=None, height=None,
        video_format=None, duration_ms=None, hdr_format=None, frame_rate=None,
        overall_bitrate=None, container=None, audio_langs=(),
        subtitle_langs=(), truncated=False,
    )


def _make_base(tmp_path, stem="RGN-001", seed=700, focal="0.65,0.5"):
    video_dir = tmp_path / f"lib_{stem}"
    video_dir.mkdir()
    mp4 = video_dir / f"{stem}.mp4"
    mp4.write_bytes(b"fake-video-bytes-0123456789")
    cover = video_dir / f"{stem}.jpg"
    _stripes(cover, seed)
    st = os.stat(mp4)
    mtime = float(st.st_mtime)
    size = st.st_size
    video_uri = to_file_uri(str(mp4), {})
    cover_uri = to_file_uri(str(cover), {})
    db_path = tmp_path / f"{stem}.db"
    init_db(db_path)
    repo = VideoRepository(db_path)
    repo.upsert_batch([Video(
        path=video_uri, number=stem, title=stem, cover_path=cover_uri,
        mtime=mtime, size_bytes=size, crop_mode="manual", auto_focal=focal,
    )])
    config = {
        "gallery": {
            "directories": [{"path": str(video_dir), "readonly": False, "output_path": ""}],
            "path_mappings": {},
        },
        "scraper": {"external_manager": "jellyfin"},
    }
    return {
        "video_dir": video_dir, "mp4": mp4, "cover": cover,
        "video_uri": video_uri, "cover_uri": cover_uri,
        "db_path": db_path, "repo": repo, "config": config,
        "mtime": mtime, "size": size,
    }


_REGEN_CASES = [
    "updated_manual",
    "updated_auto",
    "unreachable",
    "mode_off",
    "portrait_cover",
    "broken_cover",
    "generic_cover_name",
    "no_cover",
    "readonly_output_not_current",
    "other_folder",
]


@pytest.mark.parametrize("case", _REGEN_CASES)
def test_poster_regenerate_outcomes(tmp_path, monkeypatch, mocker, case):
    """poster-regenerate 九格：成功／原因碼／unreachable 零 IO；每格是不同的使用者後果。"""
    if case == "readonly_output_not_current":
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        video = src_dir / "X-001.mp4"
        video.write_bytes(b"fake-video-bytes-0123456789")
        cover = src_dir / "X-001.jpg"
        _stripes(cover, 501)
        poster = src_dir / "X-001-poster.jpg"
        _solid(poster, (30, 200, 30))
        video_uri = to_file_uri(str(video), {})
        cover_uri = to_file_uri(str(cover), {})
        db_path = tmp_path / "flipped.db"
        init_db(db_path)
        VideoRepository(db_path).upsert_batch([Video(
            path=video_uri, number="X-001", title="X-001", cover_path=cover_uri,
            crop_mode="manual", auto_focal="0.65,0.5",
        )])
        config = {
            "gallery": {
                "directories": [{"path": str(src_dir), "readonly": True,
                                 "output_path": str(out_dir)}],
                "path_mappings": {},
            },
            "scraper": {"external_manager": "jellyfin"},
        }
        client = _wire(monkeypatch, db_path=db_path, config=config)
        before = _snapshot_tree(src_dir)
        resp = client.post("/api/showcase/video/poster-regenerate",
                           json={"path": video_uri})
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"success": False, "error": "readonly_output_not_current"}
        assert _snapshot_tree(src_dir) == before
        assert _snapshot_tree(out_dir) == {}
        return

    env = _make_base(tmp_path)
    video_dir = env["video_dir"]
    config = env["config"]
    client = _wire(monkeypatch, db_path=env["db_path"], config=config)

    if case == "other_folder":
        other = tmp_path / "other"
        other.mkdir()
        cover = other / env["cover"].name
        env["cover"].rename(cover)
        env["repo"].upsert_batch([Video(path=env["video_uri"], number="RGN-001", title="RGN-001", cover_path=to_file_uri(str(cover), {}))])
        before = _snapshot_tree(tmp_path)
        spy = mocker.patch("web.routers.showcase_files.refresh_poster")
        resp = client.post("/api/showcase/video/poster-regenerate", json={"path": env["video_uri"]})
        assert resp.json() == {"success": False, "error": "generic_cover_name"}
        assert _snapshot_tree(tmp_path) == before
        spy.assert_not_called()
        return

    if case == "unreachable":
        mocker.patch(
            "web.routers.showcase_files.is_path_on_unreachable_source",
            return_value=True,
        )
        refresh_spy = mocker.patch("web.routers.showcase_files.refresh_poster")
        before = _snapshot_tree(video_dir)
        resp = client.post("/api/showcase/video/poster-regenerate",
                           json={"path": env["video_uri"]})
        assert resp.status_code == 200
        assert resp.json() == {"success": False, "error": "unreachable"}
        assert _snapshot_tree(video_dir) == before
        assert not (video_dir / "RGN-001-poster.jpg").exists()
        refresh_spy.assert_not_called()
        return

    if case == "mode_off":
        config.pop("scraper", None)
        cover_before = _digest(env["cover"])
        before = _snapshot_tree(video_dir)
        resp = client.post("/api/showcase/video/poster-regenerate",
                           json={"path": env["video_uri"]})
        assert resp.status_code == 200
        assert resp.json() == {"success": True, "poster": {"status": "skipped"}}
        assert _snapshot_tree(video_dir) == before
        assert _digest(env["cover"]) == cover_before
        return

    if case == "portrait_cover":
        portrait = Image.new("RGB", (200, 800), (10, 200, 10))
        portrait.save(env["cover"], quality=100, subsampling=0)
        before = _snapshot_tree(video_dir)
        resp = client.post("/api/showcase/video/poster-regenerate",
                           json={"path": env["video_uri"]})
        assert resp.status_code == 200
        assert resp.json() == {"success": True, "poster": {"status": "skipped"}}
        assert _snapshot_tree(video_dir) == before
        return

    if case == "broken_cover":
        env["cover"].write_bytes(b"\xff\xd8\xff\xe0not-really-a-jpeg\x00\x01\x02")
        before = _snapshot_tree(video_dir)
        resp = client.post("/api/showcase/video/poster-regenerate",
                           json={"path": env["video_uri"]})
        assert resp.status_code == 200
        assert resp.json() == {"success": True, "poster": {"status": "failed"}}
        assert _snapshot_tree(video_dir) == before
        return

    if case == "generic_cover_name":
        fanart = video_dir / "fanart.jpg"
        env["cover"].rename(fanart)
        fanart_uri = to_file_uri(str(fanart), {})
        VideoRepository(env["db_path"]).upsert_batch([Video(
            path=env["video_uri"], number="RGN-001", title="RGN-001",
            cover_path=fanart_uri, mtime=env["mtime"], size_bytes=env["size"],
            crop_mode="manual", auto_focal="0.65,0.5",
        )])
        before = _snapshot_tree(video_dir)
        resp = client.post("/api/showcase/video/poster-regenerate",
                           json={"path": env["video_uri"]})
        assert resp.status_code == 200
        assert resp.json() == {"success": False, "error": "generic_cover_name"}
        assert _snapshot_tree(video_dir) == before
        return

    if case == "no_cover":
        missing_uri = to_file_uri(str(video_dir / "does-not-exist.jpg"), {})
        VideoRepository(env["db_path"]).upsert_batch([Video(
            path=env["video_uri"], number="RGN-001", title="RGN-001",
            cover_path=missing_uri, mtime=env["mtime"], size_bytes=env["size"],
            crop_mode="manual", auto_focal="0.65,0.5",
        )])
        env["cover"].unlink()
        before = _snapshot_tree(video_dir)
        resp = client.post("/api/showcase/video/poster-regenerate",
                           json={"path": env["video_uri"]})
        assert resp.status_code == 200
        assert resp.json() == {"success": False, "error": "no_cover"}
        assert _snapshot_tree(video_dir) == before
        return

    if case in ("updated_manual", "updated_auto"):
        if case == "updated_auto":
            _conn = sqlite3.connect(str(env["db_path"]))
            try:
                _conn.execute(
                    "UPDATE videos SET crop_mode = 'auto', auto_focal = '' WHERE path = ?",
                    (env["video_uri"],),
                )
                _conn.commit()
            finally:
                _conn.close()
            expected_x0 = 800 - round(0.71 * 538)
        else:
            expected_x0 = _expected_x0(0.65)
        fanart = video_dir / "RGN-001-fanart.jpg"
        fanart.write_bytes(b"\xff\xd8\xff\xe0different-fanart-bytes")
        fanart_before = _digest(fanart)
        cover_before = _digest(env["cover"])
        mp4_before = _digest(env["mp4"])
        poster_fs = video_dir / "RGN-001-poster.jpg"
        assert not poster_fs.exists()
        resp = client.post("/api/showcase/video/poster-regenerate",
                           json={"path": env["video_uri"]})
        assert resp.status_code == 200
        assert resp.json() == {"success": True, "poster": {"status": "updated"}}
        assert poster_fs.exists()
        actual_x0 = _actual_x0(str(poster_fs), str(env["cover"]))
        assert abs(actual_x0 - expected_x0) <= 1
        if case == "updated_auto":
            assert abs(actual_x0 - 329) > 50
        assert _digest(env["cover"]) == cover_before
        assert _digest(fanart) == fanart_before
        assert _digest(env["mp4"]) == mp4_before
        return


@pytest.mark.parametrize("layout", ["stem_no_poster", "fanart_cover_old_poster", "cover_is_poster"])
def test_poster_regenerate_never_writes_cover_or_fanart(tmp_path, monkeypatch, layout):
    """三種佈局下封面／fanart／影片檔 sha256 與 mtime_ns 不變（寫錯檔的 mutation 有感）。"""
    video_dir = tmp_path / f"layout_{layout}"
    video_dir.mkdir()
    mp4 = video_dir / "LAY-001.mp4"
    mp4.write_bytes(b"fake-video-bytes-0123456789")
    if layout == "stem_no_poster":
        cover = video_dir / "LAY-001.jpg"
    elif layout == "fanart_cover_old_poster":
        cover = video_dir / "LAY-001-fanart.jpg"
    else:
        cover = video_dir / "LAY-001-poster.jpg"
    _stripes(cover, 710)
    fanart = video_dir / "LAY-001-fanart.jpg"
    if not fanart.exists():
        fanart.write_bytes(b"\xff\xd8\xff\xe0layout-fanart-bytes")
    poster = video_dir / "LAY-001-poster.jpg"
    if layout == "fanart_cover_old_poster":
        _solid(poster, (9, 9, 200))
    elif layout == "cover_is_poster" or layout == "stem_no_poster":
        if poster.exists() and layout == "stem_no_poster":
            poster.unlink()
    st = os.stat(mp4)
    mtime = float(st.st_mtime)
    size = st.st_size
    video_uri = to_file_uri(str(mp4), {})
    cover_uri = to_file_uri(str(cover), {})
    db_path = tmp_path / f"{layout}.db"
    init_db(db_path)
    VideoRepository(db_path).upsert_batch([Video(
        path=video_uri, number="LAY-001", title="LAY-001", cover_path=cover_uri,
        mtime=mtime, size_bytes=size, crop_mode="manual", auto_focal="0.65,0.5",
    )])
    config = {
        "gallery": {
            "directories": [{"path": str(video_dir), "readonly": False, "output_path": ""}],
            "path_mappings": {},
        },
        "scraper": {"external_manager": "jellyfin"},
    }
    client = _wire(monkeypatch, db_path=db_path, config=config)
    keep = [cover, fanart, mp4]
    before = {str(p): (_digest(p), p.stat().st_mtime_ns) for p in keep}
    poster_before = (_digest(poster), poster.stat().st_mtime_ns) if poster.exists() else None
    resp = client.post("/api/showcase/video/poster-regenerate",
                       json={"path": video_uri})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    after = {str(p): (_digest(p), p.stat().st_mtime_ns) for p in keep}
    for path_str, snapshot in before.items():
        assert after.get(path_str) == snapshot, path_str
    if layout == "stem_no_poster":
        assert body == {"success": True, "poster": {"status": "updated"}}
        assert poster.exists()
    elif layout == "fanart_cover_old_poster":
        assert body == {"success": True, "poster": {"status": "updated"}}
        assert (_digest(poster), poster.stat().st_mtime_ns) != poster_before
    else:
        assert body == {"success": True, "poster": {"status": "skipped"}}
        assert (_digest(poster), poster.stat().st_mtime_ns) == poster_before


def test_poster_regenerate_readonly_writes_only_output(tmp_path, monkeypatch):
    """唯讀來源按重新產生：輸出夾海報被新產、來源夾（含誘餌海報）快照不變。"""
    src_dir = tmp_path / "rosrc"
    src_dir.mkdir()
    out_dir = tmp_path / "roout"
    out_dir.mkdir()
    src_mp4 = src_dir / "SRC-001.mp4"
    src_mp4.write_bytes(b"fake-video-bytes-0123456789")
    src_mp4_stat = src_mp4.stat()
    src_poster = src_dir / "SRC-001-poster.jpg"
    _solid(src_poster, (30, 200, 30))
    out_cover = out_dir / "SRC-001.jpg"
    _stripes(out_cover, 500)
    out_poster = out_dir / "SRC-001-poster.jpg"
    _solid(out_poster, (200, 200, 30))
    video_uri = to_file_uri(str(src_mp4), {})
    cover_uri = to_file_uri(str(out_cover), {})
    db_path = tmp_path / "ro.db"
    init_db(db_path)
    VideoRepository(db_path).upsert_batch([Video(
        path=video_uri, number="SRC-001", title="SRC-001",
        cover_path=cover_uri, mtime=float(src_mp4_stat.st_mtime),
        size_bytes=src_mp4_stat.st_size,
        crop_mode="manual", auto_focal="0.65,0.5",
    )])
    config = {
        "gallery": {
            "directories": [{"path": str(src_dir), "readonly": True,
                             "output_path": str(out_dir)}],
            "path_mappings": {},
        },
        "scraper": {"external_manager": "jellyfin"},
    }
    client = _wire(monkeypatch, db_path=db_path, config=config)
    src_before = _snapshot_tree(src_dir)
    out_poster_before = _digest(out_poster)
    out_cover_before = _digest(out_cover)
    resp = client.post("/api/showcase/video/poster-regenerate",
                       json={"path": video_uri})
    assert resp.status_code == 200
    assert resp.json() == {"success": True, "poster": {"status": "updated"}}
    assert _snapshot_tree(src_dir) == src_before
    assert _digest(out_poster) != out_poster_before
    assert _digest(out_cover) == out_cover_before
    assert abs(_actual_x0(str(out_poster), str(out_cover)) - _expected_x0(0.65)) <= 1


_REPROBE_CASES = [
    "readonly_key_matched_still_rereads",
    "prior_ok_now_unreadable",
    "changed_writable",
    "changed_readonly",
    "unavailable",
    "unreachable",
]


@pytest.mark.parametrize("case", _REPROBE_CASES)
def test_reprobe_endpoint_results(tmp_path, monkeypatch, mocker, case):
    """reprobe 六格：每格是不同的使用者後果；unreachable 零 IO、fake probe 零呼叫。"""
    if case == "changed_readonly":
        src_dir = tmp_path / "ro_reprobe_src"
        src_dir.mkdir()
        out_dir = tmp_path / "ro_reprobe_out"
        out_dir.mkdir()
        src_mp4 = src_dir / "RO-001.mp4"
        src_mp4.write_bytes(b"fake-video-bytes-0123456789")
        st = src_mp4.stat()
        video_uri = to_file_uri(str(src_mp4), {})
        db_path = tmp_path / "ro_reprobe.db"
        init_db(db_path)
        repo = VideoRepository(db_path)
        repo.upsert_batch([Video(
            path=video_uri, number="RO-001", title="RO-001",
            mtime=float(st.st_mtime), size_bytes=st.st_size,
        )])
        assert repo.update_media_probe(video_uri, _ok_probe(), float(st.st_mtime), st.st_size) is True
        before = repo.get_media_probe_view(video_uri)
        src_mp4.write_bytes(b"fake-video-bytes-0123456789-CHANGED-much-longer-content")
        mocker.patch("core.media_probe.is_available", return_value=True)
        config = {
            "gallery": {
                "directories": [{"path": str(src_dir), "readonly": True,
                                 "output_path": str(out_dir)}],
                "path_mappings": {},
            },
            "scraper": {"external_manager": "jellyfin"},
        }
        client = _wire(monkeypatch, db_path=db_path, config=config)
        spy = mocker.patch("core.media_probe.probe_file", side_effect=AssertionError("changed must not probe"))
        resp = client.post("/api/showcase/video/reprobe", json={"path": video_uri})
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["status"] == "changed"
        assert body["readonly"] is True
        after = repo.get_media_probe_view(video_uri)
        assert (after.media_width, after.media_probe_size) == (before.media_width, before.media_probe_size)
        assert body["media"]["status"] == "ok"
        spy.assert_not_called()
        return

    env = _make_base(tmp_path, stem="RPB-001", seed=720, focal="0.65,0.5")
    client = _wire(monkeypatch, db_path=env["db_path"], config=env["config"])

    if case == "unreachable":
        mocker.patch(
            "web.routers.showcase_files.is_path_on_unreachable_source",
            return_value=True,
        )
        spy = mocker.patch("core.media_probe.probe_file", side_effect=AssertionError("unreachable must not probe"))
        probe_before = env["repo"].get_media_probe_view(env["video_uri"])
        resp = client.post("/api/showcase/video/reprobe", json={"path": env["video_uri"]})
        assert resp.status_code == 200
        assert resp.json() == {"success": False, "error": "unreachable"}
        probe_after = env["repo"].get_media_probe_view(env["video_uri"])
        assert (probe_after.media_probe_status, probe_after.media_width) == (
            probe_before.media_probe_status, probe_before.media_width)
        spy.assert_not_called()
        return

    if case == "unavailable":
        mocker.patch("core.media_probe.is_available", return_value=False)
        spy = mocker.patch("core.media_probe.probe_file", side_effect=AssertionError("unavailable must not probe"))
        probe_before = env["repo"].get_media_probe_view(env["video_uri"])
        resp = client.post("/api/showcase/video/reprobe", json={"path": env["video_uri"]})
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["status"] == "unavailable"
        assert body["readonly"] is False
        probe_after = env["repo"].get_media_probe_view(env["video_uri"])
        assert (probe_after.media_probe_status, probe_after.media_width) == (
            probe_before.media_probe_status, probe_before.media_width)
        spy.assert_not_called()
        return

    if case == "readonly_key_matched_still_rereads":
        src_dir = tmp_path / "ro_reread_src"
        src_dir.mkdir()
        out_dir = tmp_path / "ro_reread_out"
        out_dir.mkdir()
        src_mp4 = src_dir / "RO-002.mp4"
        src_mp4.write_bytes(b"fake-video-bytes-0123456789")
        st = src_mp4.stat()
        video_uri = to_file_uri(str(src_mp4), {})
        db_path = tmp_path / "ro_reread.db"
        init_db(db_path)
        repo = VideoRepository(db_path)
        repo.upsert_batch([Video(
            path=video_uri, number="RO-002", title="RO-002",
            mtime=float(st.st_mtime), size_bytes=st.st_size,
        )])
        assert repo.update_media_probe(video_uri, _ok_probe(width=640, height=360),
                                       float(st.st_mtime), st.st_size) is True
        config = {
            "gallery": {
                "directories": [{"path": str(src_dir), "readonly": True,
                                 "output_path": str(out_dir)}],
                "path_mappings": {},
            },
            "scraper": {"external_manager": "jellyfin"},
        }
        ro_client = _wire(monkeypatch, db_path=db_path, config=config)
        mocker.patch("core.media_probe.is_available", return_value=True)
        mocker.patch("core.media_probe.probe_file", return_value=_ok_probe(width=1280, height=720))
        resp = ro_client.post("/api/showcase/video/reprobe", json={"path": video_uri})
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["status"] == "ok"
        assert body["readonly"] is True
        assert body["media"]["width"] == 1280
        assert repo.get_media_probe_view(video_uri).media_width == 1280
        return

    if case == "prior_ok_now_unreadable":
        assert env["repo"].update_media_probe(
            env["video_uri"], _ok_probe(), env["mtime"], env["size"]) is True
        mocker.patch("core.media_probe.is_available", return_value=True)
        mocker.patch("core.media_probe.probe_file", return_value=_unreadable_probe())
        resp = client.post("/api/showcase/video/reprobe", json={"path": env["video_uri"]})
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["status"] == "unreadable"
        assert body["media"]["status"] == "ok"
        assert body["media"]["width"] == 3840
        after = env["repo"].get_media_probe_view(env["video_uri"])
        assert after.media_width == 3840
        assert after.media_probe_status == "ok"
        return

    assert case == "changed_writable"
    assert env["repo"].update_media_probe(
        env["video_uri"], _ok_probe(), env["mtime"], env["size"]) is True
    before = env["repo"].get_media_probe_view(env["video_uri"])
    env["mp4"].write_bytes(b"fake-video-bytes-0123456789-CHANGED-much-longer-content")
    mocker.patch("core.media_probe.is_available", return_value=True)
    spy = mocker.patch("core.media_probe.probe_file", side_effect=AssertionError("changed must not probe"))
    resp = client.post("/api/showcase/video/reprobe", json={"path": env["video_uri"]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["status"] == "changed"
    assert body["readonly"] is False
    assert body["media"]["status"] == "ok"
    after = env["repo"].get_media_probe_view(env["video_uri"])
    assert (after.media_width, after.media_probe_size) == (before.media_width, before.media_probe_size)
    spy.assert_not_called()
