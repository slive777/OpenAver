from io import BytesIO

import pytest
from PIL import Image

from core.avscan.image_prep import MAX_EDGE, ImageTooLarge, ImageUnsupported, prepare_image
from core.avscan.rules import CLEAR_HIT_LEAD, is_clear_hit, map_code, parse_frame_name, safe_thumb_path


@pytest.mark.parametrize(
    ("code", "number", "searchable"),
    [
        ("MIMK-200", "MIMK-200", True),
        ("IPX-338", "IPX-338", True),
        ("SSNI-780", "SSNI-780", True),
        ("FC2-PPV-4966131", "FC2-4966131", True),
        ("062213-01", "062213-01", True),
        ("091015-354", "091015-354", True),
        ("K1395", "K1395", True),
        ("178X023", "178X023", False),
        ("H0930-ORI1444", "H0930-ORI1444", True),
        ("C0930-KI221211", "C0930-KI221211", True),
        ("H4610-KI220710", "H4610-KI220710", True),
        ("PARATHD-3988", "PARATHD-3988", True),
        ("OPUD-092", "OPUD-092", True),
        ("fc2-ppv-12", "fc2-ppv-12", False),
    ],
)
def test_map_code(code, number, searchable):
    assert CLEAR_HIT_LEAD == 8
    assert map_code(code) == (number, searchable)


@pytest.mark.parametrize(
    ("sims", "expected"),
    [
        ([88.9, 80.7], (True, 8.2)),
        ([91.4, 85.1], (False, 6.3)),
        ([90.0, 82.0], (True, 8.0)),
        ([70.1, 62.1], (True, 8.0)),
        ([95.0], (False, None)),
        ([], (False, None)),
    ],
)
def test_is_clear_hit(sims, expected):
    hit, lead = is_clear_hit(sims)
    assert (hit, lead) == expected
    if lead is not None:
        assert lead == expected[1] and isinstance(lead, float)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("MIMK-200_00-38-26.jpg", ("frame", None, 2306, "00:38:26")),
        ("062213-01_00-29-16.jpg", ("frame", None, 1756, "00:29:16")),
        ("IPX-338_cover_full.jpg", ("cover", "full", None, None)),
        ("MIDV-876_cover_right.jpg", ("cover", "right", None, None)),
        ("SSNI-780_cover_left.jpg", ("cover", "left", None, None)),
        ("062213_01_00-29-16.jpg", ("frame", None, 1756, "00:29:16")),
        ("MIMK-200_abc.jpg", ("frame", None, None, None)),
        ("MIMK-200.jpg", ("frame", None, None, None)),
    ],
)
def test_parse_frame_name(name, expected):
    assert parse_frame_name(name) == expected


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/thumb/abc123/MIMK-200/main.webp", True),
        ("/thumb/abc123/covers/IPX-338.webp", True),
        ("/thumb/tok/../x.webp", False),
        ("/thumb/abc123/MIMK-200/main.webp\n", False),
        ("/thumb/abc123/MIMK-200/main.jpg", False),
        ("/thumb/abc123/MIMK-200/main.webp?x=1", False),
        ("/other/abc123/MIMK-200/main.webp", False),
        (None, False),
    ],
)
def test_safe_thumb_path(path, expected):
    assert safe_thumb_path(path) is expected


def _gradient_jpeg(w, h, quality=95, orientation=None):
    img = Image.new("RGB", (w, h))
    img.putdata([(x % 256, y % 256, (x + y) % 256) for y in range(h) for x in range(w)])
    buf = BytesIO()
    if orientation is not None:
        e = Image.Exif()
        e[0x0112] = orientation
        img.save(buf, "JPEG", quality=quality, exif=e)
    else:
        img.save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def test_prepare_image_resizes_large():
    out = prepare_image(_gradient_jpeg(2000, 1000))
    img = Image.open(BytesIO(out))
    assert img.format == "JPEG"
    assert img.size == (1024, 512)
    out2 = prepare_image(_gradient_jpeg(2000, 1000, orientation=6))
    assert Image.open(BytesIO(out2)).size == (512, 1024)


def test_prepare_image_passthrough_small():
    assert MAX_EDGE == 1024
    data = _gradient_jpeg(200, 100)
    assert prepare_image(data) == data
    assert prepare_image(data) is data


@pytest.mark.parametrize("kind", ["too_large", "not_image"])
def test_prepare_image_rejects(kind):
    if kind == "too_large":
        buf = BytesIO()
        Image.new("1", (7100, 7100)).save(buf, "PNG")
        with pytest.raises(ImageTooLarge):
            prepare_image(buf.getvalue())
    else:
        with pytest.raises(ImageUnsupported):
            prepare_image(b"this is not an image")
