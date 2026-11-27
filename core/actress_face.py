"""女優照片指紋與臉部結果。"""

import hashlib

from core.actress_photo import get_local_photo_path


def current_photo_fp(name) -> tuple[str, int, int] | None:
    path = get_local_photo_path(name)
    if path is None:
        return None
    try:
        st = path.stat()
    except OSError:
        return None
    return (str(path), st.st_mtime_ns, st.st_size)


def result_is_valid(actress, fp) -> bool:
    if fp is None or not actress.face_status:
        return False
    return (actress.photo_fp_path, actress.photo_fp_mtime_ns, actress.photo_fp_size) == fp


def avatar_stamp(actress) -> str:
    return hashlib.sha1(f"{actress.photo_fp_mtime_ns}-{actress.photo_fp_size}|{actress.face_box}|{actress.face_model}".encode("utf-8")).hexdigest()[:10]
