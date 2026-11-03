"""poster_* prep (TASK-188b-T5)."""
from __future__ import annotations
import io, re
from pathlib import Path
import pytest
from PIL import Image
from core.ai_services.image_prep import (
    POSTER_CROP_RATIO, poster_crop_box, poster_to_data_uri, poster_to_jpeg_bytes,
)

def _css_r():
    t = (Path(__file__).resolve().parents[2] / "web/static/css/theme.css").read_text()
    return float(re.search(r"--poster-crop-ratio:\s*([0-9.]+)\s*;", t).group(1))

def _oracle(w, h, r):  # float CSS cover: aspect R, cover, object-position right center
    if w / h > r:
        vw, vh, x0, y0 = r * h, float(h), w - r * h, 0.0
    else:
        vw, vh, x0, y0 = float(w), w / r, 0.0, (h - w / r) / 2
    return tuple(int(round(v)) for v in (x0, y0, x0 + vw, y0 + vh))

@pytest.mark.parametrize("w,h", [(300, 600), (710, 1000), (800, 800), (1600, 900), (1420, 1000)])
def test_poster_crop_box_matches_css_cover_geometry(w, h):
    r = _css_r(); assert POSTER_CROP_RATIO == r
    box = poster_crop_box(w, h, "default", "")
    for got, exp in zip(box, _oracle(w, h, r), strict=True):
        assert abs(got - exp) <= 1
    x0, y0, x1, y1 = box
    assert 0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h

@pytest.mark.parametrize("w,h,mode,focal,ex0", [
    (1600, 900, "manual", "0.7000,0.5000", 801), (1600, 900, "auto", "0.7000,0.5000", 961),
    (1600, 900, "auto", "0.2500,0.5000", 81), (1600, 900, "default", "0.2500,0.5000", 961),
    (1600, 900, "manual", "abc", 961), (1600, 900, "manual", "1.5,0.5", 961),
    (1600, 900, "manual", "0.0000,0.5000", 0), (300, 600, "manual", "0.2000,0.5000", 0),
])
def test_poster_crop_box_focal_rules(w, h, mode, focal, ex0):
    x0, y0, x1, y1 = poster_crop_box(w, h, mode, focal)
    assert x0 == ex0 and 0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h
    if (w, h) == (300, 600):
        assert x1 - x0 == w

def test_poster_to_jpeg_bytes_upright_no_black_border_and_edge_cap(tmp_path):
    up = Image.new("RGB", (300, 200), (30, 30, 220))
    up.paste(Image.new("RGB", (150, 200), (220, 30, 30)), (0, 0))
    raw = up.transpose(Image.Transpose.ROTATE_90); p = tmp_path / "o6.jpg"
    exif = raw.getexif(); exif[0x0112] = 6
    raw.save(p, format="JPEG", quality=95, exif=exif)
    out = Image.open(io.BytesIO(poster_to_jpeg_bytes(str(p), "default", "")))
    ow, oh = out.size; assert abs(ow - 142) <= 1 and abs(oh - 200) <= 1
    for xy in ((0, 0), (ow - 1, 0), (0, oh - 1), (ow - 1, oh - 1), (ow // 2, oh // 2)):
        assert max(out.getpixel(xy)) > 120
    r, _g, b = out.getpixel((ow // 2, oh // 2)); assert b > r
    Image.new("RGB", (2000, 1400)).save(tmp_path / "big.jpg", format="JPEG", quality=90)
    assert max(Image.open(io.BytesIO(poster_to_jpeg_bytes(str(tmp_path / "big.jpg"), "default", ""))).size) == 800
    Image.new("RGB", (379, 538)).save(tmp_path / "poc.jpg", format="JPEG", quality=90)
    ps = Image.open(io.BytesIO(poster_to_jpeg_bytes(str(tmp_path / "poc.jpg"), "default", ""))).size
    assert abs(ps[0] - 379) <= 1 and abs(ps[1] - 534) <= 1
    assert poster_to_data_uri(str(p), "default", "").startswith("data:image/jpeg;base64,")

def test_poster_functions_return_none_on_unreadable_input(tmp_path):
    fake = tmp_path / "fake.jpg"; fake.write_text("not an image")
    for path in ("", str(tmp_path / "nope.jpg"), str(fake)):
        assert poster_to_jpeg_bytes(path, "default", "") is None
        assert poster_to_data_uri(path, "default", "") is None


def test_poster_to_jpeg_bytes_logs_warning_on_corrupt_image(tmp_path, caplog):
    bad = tmp_path / "broken.jpg"; bad.write_bytes(b"\x00not-an-image\x01")
    with caplog.at_level("WARNING"):
        assert poster_to_jpeg_bytes(str(bad), "default", "") is None
    assert any("broken.jpg" in r.getMessage() and r.levelname == "WARNING" for r in caplog.records)


def test_poster_to_jpeg_bytes_missing_file_returns_none_without_warning(tmp_path, caplog):
    with caplog.at_level("WARNING"):
        assert poster_to_jpeg_bytes(str(tmp_path / "nope.jpg"), "default", "") is None
    assert not [r for r in caplog.records if r.levelname == "WARNING"]
