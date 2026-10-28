"""scrape-single 的封面上傳 token（TASK-183-T5a）：失效 fail-closed、有效落地並 discard。"""
import os
from io import BytesIO

import pytest
from PIL import Image

from core import cover_upload

_SCRAPER_CFG = {
    "create_folder": True, "folder_format": "{num}", "filename_format": "{num} {title}",
    "download_cover": False, "create_nfo": False, "max_title_length": 50,
    "max_filename_length": 120, "suffix_keywords": [], "external_manager": "off",
}


@pytest.fixture
def env(tmp_path, monkeypatch, mocker):
    root = tmp_path / "data"
    monkeypatch.setattr("core.cover_upload.get_data_root", lambda: root)
    videos = tmp_path / "videos"
    videos.mkdir()
    video = videos / "JURA-1113.mp4"
    video.write_bytes(b"fake-video")

    def _cfg(**over):
        mocker.patch(
            "web.routers.scraper.load_config",
            return_value={"scraper": {**_SCRAPER_CFG, **over}, "gallery": {}},
        )

    _cfg()
    mocker.patch("web.routers.scraper.try_inflow_upsert", return_value="not_linked")
    mocker.patch("web.routers.scraper.organize_failures")
    return {"root": root, "videos": videos, "video": video, "cfg": _cfg}


def _post(client, video, token):
    return client.post("/api/scrape-single", json={
        "file_path": str(video), "number": "JURA-1113", "cover_upload_token": token,
        "metadata": {"number": "JURA-1113", "title": "測試", "cover": "", "manual_entry": True},
    })


def test_scrape_single_unknown_token_fails_closed_before_any_move(client, env):
    resp = _post(client, env["video"], "f" * 32)
    body = resp.json()
    assert body["success"] is False
    assert body["error"] == "封面暫存已失效，請重新上傳封面"
    assert env["video"].exists()
    assert os.listdir(env["videos"]) == ["JURA-1113.mp4"]


def test_scrape_single_uploaded_cover_lands_and_token_discarded(client, env):
    buf = BytesIO()
    Image.new("RGB", (40, 60), (200, 10, 10)).save(buf, format="JPEG")
    jpeg = buf.getvalue()
    token = cover_upload.store_cover(jpeg)
    env["cfg"](create_folder=False)
    body = _post(client, env["video"], token).json()
    assert body["success"] is True, body
    with open(body["cover_path"], "rb") as f:
        assert f.read() == jpeg
    assert not (env["root"] / "tmp" / "cover-upload" / f"{token}.jpg").exists()
