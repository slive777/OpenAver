import hashlib
from dataclasses import replace
from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from core.actress_avatar import build, get_or_create, invalidate
from core.database import Actress


def test_original_photo_is_never_modified(tmp_path, monkeypatch):
    monkeypatch.setattr("core.actress_avatar.get_db_path", lambda: tmp_path / "openaver.db")
    photos = tmp_path / "photos"
    photos.mkdir()
    for orientation in (1, 6):
        photo = photos / f"{orientation}.jpg"
        exif = Image.Exif()
        exif[274] = orientation
        Image.new("RGB", (400, 300), "red").save(photo, exif=exif)
    before_names = set(photos.iterdir())
    for photo in sorted(before_names):
        before_hash = hashlib.sha256(photo.read_bytes()).digest()
        before_mtime = photo.stat().st_mtime_ns
        actress = Actress(name=photo.stem, face_box="0.5,0.5,0.5", face_model="test",
                          photo_fp_mtime_ns=before_mtime, photo_fp_size=photo.stat().st_size)
        build(photo, actress.face_box)
        dst = get_or_create(actress, photo)
        assert dst is not None and dst.is_relative_to(tmp_path / "actress_avatar")
        with Image.open(dst) as img:
            assert img.format == "WEBP" and img.size == (128, 128)
        assert hashlib.sha256(photo.read_bytes()).digest() == before_hash
        assert photo.stat().st_mtime_ns == before_mtime
        assert set(photos.iterdir()) == before_names


@pytest.mark.parametrize("orientation", [1, 6])
def test_build_crops_face_after_exif_transpose(tmp_path, orientation):
    img = Image.new("RGB", (400, 300), (110, 110, 110))
    ImageDraw.Draw(img).rectangle((65, 55, 135, 125), fill=(255, 0, 0))
    if orientation == 6:
        img = img.transpose(Image.Transpose.ROTATE_90)
    exif = Image.Exif()
    exif[274] = orientation
    photo = tmp_path / "photo.jpg"
    img.save(photo, exif=exif, quality=100)
    with Image.open(BytesIO(build(photo, "0.25,0.3,0.4"))) as result:
        def red(pixel):
            return pixel[0] > 180 and pixel[1] < 70 and pixel[2] < 70

        assert red(result.getpixel((result.width // 2, result.height // 2)))
        for point in ((0, 0), (0, result.height - 1),
                      (result.width - 1, 0), (result.width - 1, result.height - 1)):
            assert not red(result.getpixel(point))


def test_new_face_box_gets_new_file_and_old_removed(tmp_path, monkeypatch):
    monkeypatch.setattr("core.actress_avatar.get_db_path", lambda: tmp_path / "openaver.db")
    photos = tmp_path / "photos"
    photos.mkdir()
    photo = photos / "photo.jpg"
    Image.new("RGB", (400, 300), "red").save(photo)
    actress = Actress(name="第一位", face_box="0.5,0.5,0.5", face_model="test",
                      photo_fp_mtime_ns=1, photo_fp_size=100)
    p1 = get_or_create(actress, photo)
    assert p1 is not None
    actress = replace(actress, face_box="0.4,0.5,0.5")
    p2 = get_or_create(actress, photo)
    assert p2 is not None and p2 != p1 and not p1.exists()
    assert list(p2.parent.glob(f"{p2.stem.split('-')[0]}-*.webp")) == [p2]
    actress = replace(actress, photo_fp_mtime_ns=2)
    p3 = get_or_create(actress, photo)
    assert p3 is not None and p3 != p2 and not p2.exists()
    assert list(p3.parent.glob(f"{p3.stem.split('-')[0]}-*.webp")) == [p3]
    other = get_or_create(replace(actress, name="另一位"), photo)
    assert other is not None and other.exists()
    invalidate(actress.name)
    assert not list(p3.parent.glob(f"{p3.stem.split('-')[0]}-*.webp"))
    assert other.exists()
