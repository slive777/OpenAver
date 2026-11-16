"""core.cover_signature — 封面簽章網址版本記號（200b-T2 CD-200b-4）。"""


def cover_version_suffix(sig) -> str:
    """有簽章回 ``&v=<mtime_ns>-<size>``；None／半缺回 ``""``。"""
    if sig is None:
        return ""
    mtime_ns, size = sig
    if mtime_ns is None or size is None:
        return ""
    return f"&v={mtime_ns}-{size}"
