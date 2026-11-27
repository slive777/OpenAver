import os
from io import BytesIO
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from core.actress_face import avatar_stamp, current_photo_fp
from core.database import Actress, ActressRepository, init_db
from core.focal.face_judge import format_face_box
from web.app import app

NAME = "測試女優"


@pytest.fixture
def face_setup(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    init_db(db)
    repo = ActressRepository(db)
    repo.save(Actress(name=NAME))
    gf = tmp_path / "gf"
    gf.mkdir()
    photo = gf / f"{NAME}.jpg"
    image = Image.new("RGB", (400, 600), "gray")
    ImageDraw.Draw(image).rectangle((140, 150, 260, 330), fill="red")
    image.save(photo, "JPEG")
    monkeypatch.setattr("core.database.connection.get_db_path", lambda: db)
    monkeypatch.setattr("core.actress_avatar.get_db_path", lambda: db)
    monkeypatch.setattr("core.actress_photo.GFRIENDS_DIR", gf)
    fp = current_photo_fp(NAME)
    box = format_face_box(0.5, 0.4, 0.3)
    repo.update_face_result(NAME, "found", box, "ext-model", *fp)
    return TestClient(app), repo, photo, fp, box


def test_face_crop_and_avatar_url_stop_trusting_result_after_photo_changes(face_setup):
    client, repo, photo, _, _ = face_setup
    row = repo.get_by_name(NAME)
    stamp = avatar_stamp(row)
    url = f"/api/actresses/face-crop/{quote(NAME)}?v={stamp}"
    original = f"/api/actresses/photo/{quote(NAME)}"
    item = client.get("/api/actresses").json()["actresses"][0]
    assert item["avatar_url"] == url
    assert item["photo_url"] == original
    response = client.get(url)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert Image.open(BytesIO(response.content)).size == (128, 128)
    assert response.headers["cache-control"] == "no-cache"
    etag = f'"{stamp}"'
    assert response.headers["etag"] == etag
    cached = client.get(url, headers={"If-None-Match": etag})
    assert cached.status_code == 304 and cached.content == b""
    stale = client.get(f"/api/actresses/face-crop/{quote(NAME)}?v=old", follow_redirects=False)
    assert stale.status_code == 307 and stale.headers["location"] == original
    old_mtime = photo.stat().st_mtime_ns
    Image.new("RGB", (250, 350), "blue").save(photo, "JPEG")
    os.utime(photo, ns=(old_mtime + 10**9,) * 2)
    assert client.get("/api/actresses").json()["actresses"][0]["avatar_url"] == ""
    for target, headers in ((url, {"If-None-Match": etag}), (url.split("?")[0], {})):
        response = client.get(target, headers=headers, follow_redirects=False)
        assert response.status_code == 307 and response.headers["location"] == original


def test_face_crop_redirects_to_original_when_no_valid_crop_and_404s_without_photo(face_setup, monkeypatch):
    client, repo, photo, fp, box = face_setup
    original = f"/api/actresses/photo/{quote(NAME)}"
    crop = f"/api/actresses/face-crop/{quote(NAME)}"
    for status in ("", "none", "unsure", "multi"):
        repo.update_face_result(NAME, status, "", "ext-model", *fp)
        item = client.get("/api/actresses").json()["actresses"][0]
        assert item["avatar_url"] == "" and item["photo_url"] == original
        response = client.get(crop, follow_redirects=False)
        assert response.status_code == 307 and response.headers["location"] == original
    monkeypatch.setattr("core.actress_avatar.get_or_create", lambda *args: None)
    repo.update_face_result(NAME, "found", box, "ext-model", *fp)
    response = client.get(crop, follow_redirects=False)
    assert response.status_code == 307 and response.headers["location"] == original
    photo.unlink()
    assert client.get(crop, follow_redirects=False).status_code == 404
    assert client.get("/api/actresses/face-crop/不存在", follow_redirects=False).status_code == 404
