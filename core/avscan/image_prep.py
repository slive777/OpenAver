import struct
from io import BytesIO

from PIL import Image, ImageOps

from core.cover_upload import MAX_PIXELS

MAX_EDGE = 1024
JPEG_QUALITY = 85


class ImageTooLarge(ValueError):
    pass


class ImageUnsupported(ValueError):
    pass


def prepare_image(data: bytes) -> bytes:
    try:
        img = Image.open(BytesIO(data))
        w, h = img.size
        if w * h > MAX_PIXELS:
            raise ImageTooLarge(f"image {w}x{h} exceeds pixel limit")
    except ImageTooLarge:
        raise
    except Image.DecompressionBombError as e:
        raise ImageTooLarge("image exceeds pixel limit") from e
    except (OSError, ValueError) as e:
        raise ImageUnsupported("cannot open image") from e
    if max(w, h) <= MAX_EDGE:
        return data
    try:
        img = ImageOps.exif_transpose(img)
        img.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)
        out = BytesIO()
        img.convert("RGB").save(out, "JPEG", quality=JPEG_QUALITY)
        return out.getvalue()
    except Image.DecompressionBombError as e:
        raise ImageTooLarge("image exceeds pixel limit") from e
    except (OSError, ValueError, SyntaxError, EOFError, struct.error) as e:
        raise ImageUnsupported("cannot decode or resize image") from e
