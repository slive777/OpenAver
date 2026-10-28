"""core/cover_upload.py — 封面暫存的驗證與 token 信任邊界（TASK-183-T5a）。"""
from io import BytesIO

from PIL import Image

from core import cover_upload


def _img_bytes(fmt: str, size=(40, 60), mode="RGB") -> bytes:
    buf = BytesIO()
    Image.new(mode, size, (200, 10, 10) if mode == "RGB" else 1).save(buf, format=fmt)
    return buf.getvalue()


def test_validate_and_normalize_rejects_bad_input_and_converts_png():
    # 非圖片位元組（改副檔名的文字檔）→ 415
    out, err = cover_upload.validate_and_normalize_cover(b"this is not an image\n" * 20)
    assert out is None and err[0] == 415 and err[1]
    # 像素超限：1-bit PNG 只有幾 KB，但 8000x8000 = 64M 像素 → 413
    out, err = cover_upload.validate_and_normalize_cover(_img_bytes("PNG", (8000, 8000), "1"))
    assert out is None and err[0] == 413 and err[1]
    # 合法 PNG → JPEG 位元組
    out, err = cover_upload.validate_and_normalize_cover(_img_bytes("PNG"))
    assert err is None
    assert Image.open(BytesIO(out)).format == "JPEG"
    # 合法 JPEG → 原樣
    jpeg = _img_bytes("JPEG")
    out, err = cover_upload.validate_and_normalize_cover(jpeg)
    assert err is None and out == jpeg


def test_resolve_rejects_traversal_and_malformed_tokens(tmp_path, monkeypatch):
    root = tmp_path / "data"
    monkeypatch.setattr("core.cover_upload.get_data_root", lambda: root)
    jpeg = _img_bytes("JPEG")
    token = cover_upload.store_cover(jpeg)  # 建出 tmp/cover-upload/
    upload_dir = root / "tmp" / "cover-upload"
    # 穿越得到的位置真的放檔：格式檢查被拿掉時這裡會回非 None
    (root / "tmp" / "secret.jpg").write_bytes(b"secret")
    (upload_dir / ("A" * 32 + ".jpg")).write_bytes(b"secret")
    for bad in ("../secret", "../../etc/passwd", "A" * 32, token + "\n", token[:-1], None, 123):
        assert cover_upload.resolve_cover_token(bad) is None, bad
    # 正向格：合法 token 回伺服器端路徑，內容＝當初存的位元組
    path = cover_upload.resolve_cover_token(token)
    assert path is not None
    with open(path, "rb") as f:
        assert f.read() == jpeg
