"""TASK-a205-T3：試過但查不到／讀不出／Jellyfin 缺哪張（後端資料）。

測試預算 3 支（原 4 支，R6 補判刪 1 支），全部只用自種 DB 列與 tmp 檔。
"""
import pytest

from core.config import load_config, save_config
from core.database import Video, VideoRepository, init_db
from core.media_probe import ProbeResult
from core.path_utils import to_file_uri

pytestmark = pytest.mark.usefixtures("isolate_reconcile_db")

MTIME, SIZE = 1_700_000_000.0, 1234


def _probe(status):
    ok = status == "ok"
    return ProbeResult(
        status=status, reason="", width=1920 if ok else None, height=1080 if ok else None,
        video_format="AVC" if ok else None, duration_ms=60_000 if ok else None,
        hdr_format=None, frame_rate=None, overall_bitrate=None, container=None,
        audio_langs=(), subtitle_langs=(), truncated=False,
    )


def _make_db(tmp_path, videos):
    db_path = tmp_path / "test.db"
    init_db(db_path)
    repo = VideoRepository(db_path)
    repo.upsert_batch(videos)
    return db_path


def _get_missing(client, db_path):
    from unittest.mock import patch
    with patch("web.routers.scanner.get_db_path", return_value=db_path):
        resp = client.get("/api/gallery/missing-check")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    return data["data"]


def test_attempted_items_membership(client, tmp_path):
    videos = [
        Video(path=to_file_uri(str(tmp_path / "both.mp4")), number="ATT-001",
              cover_path="", nfo_mtime=0.0, scrape_attempted_at=111.0),
        Video(path=to_file_uri(str(tmp_path / "nfo.mp4")), number="ATT-002",
              cover_path="/covers/n.jpg", nfo_mtime=0.0, scrape_attempted_at=222.0),
        Video(path=to_file_uri(str(tmp_path / "cover.mp4")), number="ATT-003",
              cover_path="", nfo_mtime=100.0, scrape_attempted_at=333.0),
        Video(path=to_file_uri(str(tmp_path / "done.mp4")), number="ATT-004",
              cover_path="/covers/d.jpg", nfo_mtime=100.0, scrape_attempted_at=444.0),
        Video(path=to_file_uri(str(tmp_path / "prod.mp4")), number="ATT-005",
              cover_path="", nfo_mtime=0.0,
              output_dir=to_file_uri(str(tmp_path / "out")), scrape_attempted_at=555.0),
        Video(path=to_file_uri(str(tmp_path / "nonum.mp4")), number="",
              cover_path="", nfo_mtime=0.0, scrape_attempted_at=666.0),
        Video(path=to_file_uri(str(tmp_path / "untried.mp4")), number="ATT-007",
              cover_path="", nfo_mtime=0.0),
    ]
    db_path = _make_db(tmp_path, videos)
    data = _get_missing(client, db_path)
    got = {i["number"]: i for i in data["attempted_items"]}
    assert set(got) == {"ATT-001", "ATT-002", "ATT-003"}
    assert got["ATT-001"]["category"] == "both"
    assert got["ATT-001"]["attempted_at"] == 111.0
    assert got["ATT-002"]["category"] == "nfo"
    assert got["ATT-002"]["attempted_at"] == 222.0
    assert got["ATT-003"]["category"] == "cover"
    assert got["ATT-003"]["attempted_at"] == 333.0
    assert data["attempted_count"] == len(data["attempted_items"]) == 3


def test_probe_failed_disjoint_from_pending(client, tmp_path):
    wr = tmp_path / "wr"
    wr.mkdir()
    cfg = load_config()
    cfg["gallery"]["directories"] = [
        {"path": str(wr), "readonly": False, "output_path": ""},
    ]
    save_config(cfg)
    wr_uri = to_file_uri(str(wr))
    db_path = tmp_path / "test.db"
    init_db(db_path)
    repo = VideoRepository(db_path)

    def seed(name, number):
        path = to_file_uri(str(wr / name))
        repo.upsert(Video(path=path, mtime=MTIME, size_bytes=SIZE,
                          nfo_mtime=100.0, cover_path="/covers/x.jpg", number=number))
        return path

    seed("never.mp4", "P-NEVER")
    ok_path = seed("ok.mp4", "P-OK")
    assert repo.update_media_probe(ok_path, _probe("ok"), MTIME, SIZE) is True
    fail_path = seed("fail.mp4", "FAIL-001")
    assert repo.update_media_probe(fail_path, _probe("no_video"), MTIME, SIZE) is True
    stale_path = seed("stale.mp4", "P-STALE")
    assert repo.update_media_probe(stale_path, _probe("no_video"), MTIME, SIZE) is True
    repo.upsert(Video(path=stale_path, mtime=MTIME + 1, size_bytes=SIZE,
                      nfo_mtime=100.0, cover_path="/covers/x.jpg", number="P-STALE"))
    seed("nullp.mp4", "P-NULL")
    oos_path = to_file_uri(str(tmp_path / "else" / "oos.mp4"))
    repo.upsert(Video(path=oos_path, mtime=MTIME, size_bytes=SIZE, number="P-OOS"))
    assert repo.update_media_probe(oos_path, _probe("no_video"), MTIME, SIZE) is True
    strm_path = to_file_uri(str(wr / "oos.strm"))
    repo.upsert(Video(path=strm_path, mtime=MTIME, size_bytes=SIZE, number="P-STRM"))
    assert repo.update_media_probe(strm_path, _probe("no_video"), MTIME, SIZE) is True

    data = _get_missing(client, db_path)
    assert data["probe_failed_count"] == 1
    assert data["probe_failed_items"] == [{"file_path": fail_path, "number": "FAIL-001"}]

    pending = repo.list_media_probe_pending(
        include_readonly=True,
        readonly_prefixes=[],
        writable_prefixes=[wr_uri],
        configured_dir_uris={wr_uri},
    )
    pending_paths = {p for p, _m, _s in pending}
    assert stale_path in pending_paths
    assert fail_path not in pending_paths
    assert {i["file_path"] for i in data["probe_failed_items"]} & pending_paths == set()


def test_jellyfin_missing_matches_disk(tmp_path):
    from core.cover_layout import cover_base_stem
    from web.routers.scanner import check_jellyfin_images_needed

    db_path = tmp_path / "test.db"
    init_db(db_path)
    repo = VideoRepository(db_path)

    def seed(name, have_poster, have_fanart):
        cover = tmp_path / f"{name}.jpg"
        cover.write_bytes(b"cover")
        stem = cover_base_stem(str(cover))
        if have_poster:
            (tmp_path / (stem.rsplit("/", 1)[-1] + "-poster.jpg")).write_bytes(b"p")
        if have_fanart:
            (tmp_path / (stem.rsplit("/", 1)[-1] + "-fanart.jpg")).write_bytes(b"f")
        repo.upsert(Video(path=to_file_uri(str(tmp_path / f"{name}.mp4")),
                          number=name, cover_path=to_file_uri(str(cover))))

    seed("A", False, True)
    seed("B", True, False)
    seed("C", False, False)
    seed("D", True, True)

    result = check_jellyfin_images_needed(repo, {})
    by_num = {i["number"]: i["missing"] for i in result["items"]}
    assert by_num == {"A": ["poster"], "B": ["fanart"], "C": ["poster", "fanart"]}
    assert result["need_update"] == len(result["items"]) == 3
