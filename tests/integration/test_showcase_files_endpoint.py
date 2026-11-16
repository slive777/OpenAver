"""tests/integration/test_showcase_files_endpoint.py — GET /api/showcase/video/files（TASK-200b-T5）。

真 tmp DB＋真檔案跑端點：state 三態、唯讀旗標、純讀、通用封面名。
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

import core.video_files_info as files_info
from core import thumbnail_cache
from core.database import Video, VideoRepository, init_db
from core.media_probe import ProbeResult
from core.path_utils import to_file_uri


def _ok_probe(*, width=3840, height=2160, video_format="HEVC", duration_ms=7_200_000):
    return ProbeResult(
        status="ok", reason="", width=width, height=height,
        video_format=video_format, duration_ms=duration_ms,
        hdr_format=None, frame_rate=23.976, overall_bitrate=12_000_000,
        container="MPEG-4", audio_langs=("ja",), subtitle_langs=("zh",),
        truncated=False,
    )


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _snapshot_tree(root):
    out = {}
    for p in sorted(Path(root).rglob("*")):
        if p.is_file():
            out[str(p.relative_to(root))] = (_digest(p), p.stat().st_mtime_ns)
    return out


def _db_rows(db_path):
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute("SELECT * FROM videos ORDER BY path").fetchall()
    finally:
        conn.close()


def _wire(monkeypatch, *, db_path, config, thumb_dir):
    monkeypatch.setattr("web.routers.showcase_files.get_db_path", lambda: db_path)
    monkeypatch.setattr("web.routers.showcase_files.load_config", lambda: config)
    monkeypatch.setattr("core.readonly_paths.get_db_path", lambda: db_path)
    monkeypatch.setattr("core.thumbnail_cache._thumb_dir", lambda: thumb_dir)
    from web.app import app
    return TestClient(app)


@pytest.fixture()
def plain_env(tmp_path, monkeypatch):
    lib = tmp_path / "lib"
    lib.mkdir()
    thumb_dir = tmp_path / "thumb"
    thumb_dir.mkdir()
    mp4 = lib / "ABC-123.mp4"
    mp4.write_bytes(b"fake-video-bytes")
    cover = lib / "ABC-123.jpg"
    cover.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg")
    st = os.stat(cover)
    mtime = float(st.st_mtime)
    video_uri = to_file_uri(str(mp4), {})
    cover_uri = to_file_uri(str(cover), {})
    db_path = tmp_path / "files.db"
    init_db(db_path)
    repo = VideoRepository(db_path)
    repo.upsert_batch([Video(
        path=video_uri, number="ABC-123", title="T", cover_path=cover_uri,
        mtime=mtime, size_bytes=mp4.stat().st_size,
    )])
    repo.update_media_probe(video_uri, _ok_probe(), mtime, mp4.stat().st_size)
    repo.set_cover_signature(video_uri, st.st_mtime_ns, st.st_size)
    config = {
        "gallery": {
            "directories": [{"path": str(lib), "readonly": False, "output_path": ""}],
            "path_mappings": {},
        },
        "thumbnail_cache_enabled": True,
    }
    client = _wire(monkeypatch, db_path=db_path, config=config, thumb_dir=thumb_dir)
    return {
        "client": client, "repo": repo, "db_path": db_path,
        "lib": lib, "thumb_dir": thumb_dir, "mp4": mp4, "cover": cover,
        "video_uri": video_uri, "cover_uri": cover_uri, "config": config,
    }


def _expected_cover_url(cover_fs):
    st = os.stat(cover_fs)
    return f"/api/gallery/image?path={quote(cover_fs, safe='')}&v={st.st_mtime_ns}-{st.st_size}"


_PARAM_CASES = ["ok", "missing", "unreachable", "not_found", "out_of_scope"]


@pytest.mark.parametrize("case", _PARAM_CASES)
def test_files_state_ok_missing_unreachable(plain_env, mocker, case, tmp_path):
    if case in ("not_found", "out_of_scope"):
        if case == "out_of_scope":
            other = tmp_path / "elsewhere"
            other.mkdir()
            plain_env["config"]["gallery"]["directories"] = [
                {"path": str(other), "readonly": False, "output_path": ""},
            ]
        resp = plain_env["client"].get(
            "/api/showcase/video/files",
            params={"path": plain_env["video_uri"] if case == "out_of_scope"
                    else to_file_uri(str(tmp_path / "ghost.mp4"), {})},
        )
        expected_status = 404 if case == "not_found" else 403
        assert resp.status_code == expected_status
        assert resp.json()["success"] is False
        return

    if case == "unreachable":
        mocker.patch.object(
            files_info, "is_path_on_unreachable_source", return_value=True,
        )
        real_stat = os.stat
        seen = []

        def _spy_stat(p, *a, **k):
            if str(p).startswith(str(plain_env["lib"])):
                seen.append(str(p))
            return real_stat(p, *a, **k)

        mocker.patch.object(files_info.os, "stat", side_effect=_spy_stat)
    else:
        seen = None
        if case == "missing":
            plain_env["mp4"].unlink()

    thumb_fs = thumbnail_cache.thumb_file_for(plain_env["video_uri"])
    thumb_fs.parent.mkdir(parents=True, exist_ok=True)
    thumb_fs.write_bytes(b"fake-webp")
    if case == "ok":
        expected_url = _expected_cover_url(str(plain_env["cover"]))
        media_before = plain_env["repo"].get_media_probe_view(plain_env["video_uri"])
        assert media_before.is_ok_current

    resp = plain_env["client"].get(
        "/api/showcase/video/files", params={"path": plain_env["video_uri"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert set(body) == {
        "success", "state", "readonly", "external_mode_on", "nfo",
        "cover", "poster", "thumb", "media", "folders",
    }
    if case == "unreachable":
        assert body["state"] == "unreachable"
        assert seen == []
        assert body["cover"] == {"exists": False, "url": ""}
        assert body["thumb"]["exists"] is False
        assert body["thumb"]["url"] == ""
        assert body["thumb"]["stale"] is False
        assert body["nfo"] == {"name": ""}
    elif case == "missing":
        assert body["state"] == "missing"
        assert body["cover"]["exists"] is True
        assert body["cover"]["url"].startswith("/api/gallery/image?path=")
    else:
        assert body["state"] == "ok"
        assert body["cover"] == {"exists": True, "url": expected_url}
        thumb_st = os.stat(thumb_fs)
        assert body["thumb"]["mode"] == "cache"
        assert body["thumb"]["exists"] is True
        assert body["thumb"]["url"] == (
            f"/api/gallery/thumb?path={quote(plain_env['video_uri'], safe='')}"
            f"&v={thumb_st.st_mtime_ns}"
        )
        assert body["thumb"]["stale"] is False
        assert body["media"]["status"] == "ok"
        assert body["media"]["width"] == 3840
        assert body["media"]["height"] == 2160
        assert body["media"]["codec"] == "HEVC"
        assert body["media"]["duration_ms"] == 7_200_000
        assert body["media"]["size"] == plain_env["mp4"].stat().st_size
        assert body["media"]["tier"] == "4K"
        conn = sqlite3.connect(str(plain_env["db_path"]))
        try:
            conn.execute(
                "UPDATE videos SET mtime = ? WHERE path = ?",
                (plain_env["repo"].get_by_path(plain_env["video_uri"]).mtime + 100.0,
                 plain_env["video_uri"]),
            )
            conn.commit()
        finally:
            conn.close()
        again = plain_env["client"].get(
            "/api/showcase/video/files", params={"path": plain_env["video_uri"]},
        ).json()
        assert again["media"]["status"] == "none"
        for key in ("tier", "width", "height", "codec", "duration_ms", "size"):
            assert again["media"][key] is None


@pytest.mark.parametrize("readonly", [False, True])
def test_readonly_flags_and_folders(tmp_path, monkeypatch, readonly):
    src_dir = tmp_path / "rosrc"
    src_dir.mkdir()
    out_dir = tmp_path / "roout"
    out_dir.mkdir()
    src_mp4 = src_dir / "SRC-001.mp4"
    src_mp4.write_bytes(b"")
    out_cover = out_dir / "SRC-001.jpg"
    out_cover.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg")
    out_nfo = out_dir / "SRC-001.nfo"
    out_nfo.write_text("<movie><title>t</title></movie>", encoding="utf-8")
    video_uri = to_file_uri(str(src_mp4), {})
    db_path = tmp_path / "ro.db"
    init_db(db_path)
    output_dir_uri = to_file_uri(str(out_dir), {}) if readonly else ""
    VideoRepository(db_path).upsert_batch([Video(
        path=video_uri, number="SRC-001", title="SRC-001",
        cover_path=to_file_uri(str(out_cover), {}),
        output_dir=output_dir_uri,
    )])
    config = {"gallery": {"directories": [{
        "path": str(src_dir), "readonly": readonly,
        "output_path": str(out_dir) if readonly else "",
    }], "path_mappings": {}}}
    if readonly:
        config["scraper"] = {"external_manager": "jellyfin"}
    thumb_dir = tmp_path / "thumb"
    thumb_dir.mkdir()
    client = _wire(monkeypatch, db_path=db_path, config=config, thumb_dir=thumb_dir)
    body = client.get(
        "/api/showcase/video/files", params={"path": video_uri},
    ).json()
    assert body["success"] is True
    assert body["readonly"] is readonly
    assert body["folders"]["source"] == video_uri
    assert body["folders"]["output"] == (output_dir_uri if readonly else "")
    if readonly:
        assert body["nfo"] == {"name": "SRC-001.nfo"}
    else:
        assert body["nfo"] == {"name": ""}


def test_files_endpoint_is_read_only(plain_env):
    lib_before = _snapshot_tree(plain_env["lib"])
    thumb_before = _snapshot_tree(plain_env["thumb_dir"])
    db_before = _db_rows(plain_env["db_path"])
    sha_before = hashlib.sha256(Path(plain_env["db_path"]).read_bytes()).hexdigest()
    resp = plain_env["client"].get(
        "/api/showcase/video/files", params={"path": plain_env["video_uri"]},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    body = resp.json()
    assert body["thumb"]["mode"] == "cache"
    assert body["thumb"]["exists"] is False
    assert body["thumb"]["url"] == ""
    assert _snapshot_tree(plain_env["lib"]) == lib_before
    assert _snapshot_tree(plain_env["thumb_dir"]) == thumb_before
    assert _db_rows(plain_env["db_path"]) == db_before
    assert hashlib.sha256(Path(plain_env["db_path"]).read_bytes()).hexdigest() == sha_before
    assert resp.headers["content-type"].startswith("application/json")
    resp2 = plain_env["client"].post(
        "/api/showcase/video/files", params={"path": plain_env["video_uri"]},
    )
    assert resp2.status_code in (404, 405)


@pytest.mark.parametrize(
    "stem_kind,cover_name,video_name,mode_on,can_regen,blocked,exists_is_none",
    [
        ("generic", "fanart.jpg", "ABF-348.mp4", True, False, "generic_cover_name", True),
        ("same-stem", "ABF-348.jpg", "ABF-348.mp4", True, True, None, False),
        ("mode-off", "ABF-348.jpg", "ABF-348.mp4", False, False, None, False),
    ],
    ids=["generic-name", "same-stem", "mode-off"],
)
def test_poster_regen_block_reasons(
    tmp_path, monkeypatch, stem_kind, cover_name, video_name,
    mode_on, can_regen, blocked, exists_is_none,
):
    lib = tmp_path / "lib"
    lib.mkdir()
    thumb_dir = tmp_path / "thumb"
    thumb_dir.mkdir()
    mp4 = lib / video_name
    mp4.write_bytes(b"fake-video")
    cover = lib / cover_name
    cover.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg")
    video_uri = to_file_uri(str(mp4), {})
    db_path = tmp_path / "poster.db"
    init_db(db_path)
    VideoRepository(db_path).upsert_batch([Video(
        path=video_uri, number="ABF-348", title="T",
        cover_path=to_file_uri(str(cover), {}),
    )])
    config = {"gallery": {"directories": [{
        "path": str(lib), "readonly": False, "output_path": "",
    }], "path_mappings": {}}}
    if mode_on:
        config["scraper"] = {"external_manager": "jellyfin"}
    client = _wire(monkeypatch, db_path=db_path, config=config, thumb_dir=thumb_dir)
    body = client.get(
        "/api/showcase/video/files", params={"path": video_uri},
    ).json()
    assert body["success"] is True
    assert body["poster"]["visible"] is mode_on
    assert body["poster"]["can_regen"] is can_regen
    assert body["poster"]["regen_blocked"] == blocked
    if exists_is_none:
        assert body["poster"]["exists"] is None
        assert body["poster"]["url"] == ""
    else:
        assert body["poster"]["url"] == ""
