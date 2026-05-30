"""
Video Extensions - Single Source of Truth

All video extension definitions and helpers live here.
Other modules should import from this module instead of hardcoding extension sets.
"""

# Stable-ordered default video extensions (tuple = immutable + ordered)
DEFAULT_VIDEO_EXTENSIONS = (
    '.avi', '.asf', '.divx', '.flv', '.iso', '.m2ts', '.m4v',
    '.mkv', '.mov', '.mp4', '.mpeg', '.mpg', '.rm', '.rmvb',
    '.strm', '.ts', '.vob', '.webm', '.wmv'
)

# HTTP file proxy safety whitelist (hardcoded, NOT affected by user config)
# Known video/media formats safe for HTTP streaming proxy.
# Note: .strm is NOT here - it's a text file (playlist URL), not a video stream.
SAFE_PROXY_EXTENSIONS = frozenset({
    '.avi', '.asf', '.divx', '.flv', '.iso', '.m2ts', '.m4v',
    '.mkv', '.mov', '.mp4', '.mpeg', '.mpg', '.rm', '.rmvb',
    '.ts', '.vob', '.webm', '.wmv'
})

# Extensions exempt from min_size filtering (e.g. .strm files are typically < 1KB)
ZERO_SIZE_EXTENSIONS = frozenset({'.strm'})


def normalize_extensions(exts):
    """Normalize a list of extension strings.

    Each element: strip whitespace -> lowercase -> add leading '.' if missing -> collect to set.

    Args:
        exts: list of extension strings (e.g. ['mp4', '.AVI', '  .MKV  '])

    Returns:
        set of normalized extension strings (e.g. {'.mp4', '.avi', '.mkv'})
    """
    # Guard: if a string is passed instead of a list, wrap it in a list
    if isinstance(exts, str):
        exts = [exts]
    result = set()
    for ext in exts:
        ext = ext.strip().lower()
        if not ext.startswith('.'):
            ext = '.' + ext
        result.add(ext)
    return result


def get_video_extensions(config):
    """Get video extensions from config, with fallback to DEFAULT_VIDEO_EXTENSIONS.

    Args:
        config: dict with optional 'scraper.video_extensions' key

    Returns:
        set of normalized extension strings
    """
    try:
        exts = config.get('scraper', {}).get('video_extensions', [])
        if exts:
            # Guard: if config value is not a list/tuple (e.g. a bare string),
            # fall back to DEFAULT to avoid iterating over characters
            if not isinstance(exts, (list, tuple)):
                return set(DEFAULT_VIDEO_EXTENSIONS)
            return normalize_extensions(exts)
    except (AttributeError, TypeError):
        pass
    return set(DEFAULT_VIDEO_EXTENSIONS)


def get_proxy_extensions(config):
    """Get proxy-safe video extensions = user config intersection with SAFE_PROXY_EXTENSIONS.

    This ensures user-added arbitrary extensions (like .exe) don't become
    HTTP file proxy permissions.

    Args:
        config: dict with optional 'scraper.video_extensions' key

    Returns:
        set of normalized extension strings that are safe for HTTP proxy
    """
    return get_video_extensions(config) & SAFE_PROXY_EXTENSIONS
