"""TASK-198b-T5 端對端：兩次 POST /api/scrape-single 收成一張卡、兩個版本。"""
from core.database.connection import init_db


def _metadata():
    return {
        "number": "ABF-348",
        "title": "title",
        "actors": [],
        "tags": [],
        "maker": "maker",
        "date": "",
        "cover": "",
        "url": "",
    }


def test_scrape_single_version_marker_collapses_into_one_work(client, tmp_path, monkeypatch, mocker):
    video_dir = tmp_path / "videos"
    video_dir.mkdir()
    db_path = tmp_path / "t5_e2e.db"
    init_db(db_path)
    monkeypatch.setattr("core.database.connection.get_db_path", lambda: db_path)

    config = {
        "gallery": {"directories": [str(video_dir)], "path_mappings": {}, "min_size_mb": 0},
        "scraper": {
            "create_folder": False,
            "filename_format": "[{num}][{maker}] {title}",
            "download_cover": False,
            "cover_filename": "poster.jpg",
            "create_nfo": True,
            "max_title_length": 50,
            "max_filename_length": 60,
            "suffix_keywords": ["-cd1", "-cd2", "-4k", "-uc"],
            "external_manager": "off",
        },
    }
    monkeypatch.setattr("web.routers.scraper.load_config", lambda: config)
    monkeypatch.setattr("web.routers.showcase.load_config", lambda: config)
    monkeypatch.setattr("web.routers.showcase.get_db_path", lambda: db_path)
    monkeypatch.setattr("core.db_inflow.load_config", lambda: config)
    mocker.patch("web.routers.scraper._media_probe_after_scrape", return_value=None)
    mocker.patch("web.routers.scraper._post_ingest_after_scrape", return_value=None)

    src1 = video_dir / "ABF-348.mp4"
    src1.write_bytes(b"orig-video")
    r1 = client.post("/api/scrape-single", json={"file_path": str(src1), "number": "ABF-348", "metadata": _metadata()})
    assert r1.status_code == 200, r1.text
    assert r1.json()["success"] is True, r1.json()

    src2 = video_dir / "ABF-348-LTX.mp4"
    src2.write_bytes(b"ltx-video")
    r2 = client.post("/api/scrape-single", json={"file_path": str(src2), "number": "ABF-348", "metadata": _metadata()})
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert body2["success"] is True, body2
    assert body2.get("duplicate") is not True, body2

    listing = client.get("/api/showcase/videos")
    assert listing.status_code == 200, listing.text
    data = listing.json()
    assert data["total"] == 1, data
    assert len(data["videos"]) == 1, data
    assert len(data["videos"][0]["versions"]) == 2, data["videos"][0]
