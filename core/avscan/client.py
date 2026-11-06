"""avscan 以圖查番號 client（CD-193-1／2／9／10）：全 repo 唯一對站方送圖的出口，也是唯一含站台網址的檔。

只回「站方原料＋解析後的 match＋thumb_url」；rank／number／searchable／in_library／clear_hit
由 router 組。log 只記候選數、耗時、固定短詞與例外類別名。
"""
import math
import time

import requests

from core.avscan import rules
from core.avscan.gate import AVSCAN_MAX_PENALTY_SECONDS, AVSCAN_MIN_GAP_SECONDS, get_gate
from core.logger import get_logger
from core.proxy_policy import proxy_kwargs
from core.scrapers.utils import DEFAULT_HEADERS

logger = get_logger(__name__)

AVSCAN_ORIGIN = "https://avscan.cc"
AVSCAN_SEARCH_URL = AVSCAN_ORIGIN + "/search"
MAX_CANDIDATES = 5


class AvscanError(Exception):
    pass


class AvscanRateLimited(AvscanError):
    def __init__(self, retry_after: int):
        super().__init__("rate_limited")
        self.retry_after = retry_after


class AvscanUnreachable(AvscanError):
    pass


class AvscanUnparseable(AvscanError):
    pass


class AvscanInvalidImage(AvscanError):
    pass


def _is_number(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _parse_item(item) -> dict:
    if not isinstance(item, dict):
        raise AvscanUnparseable("item")
    code, sim, frames, thumb = item.get("video_code"), item.get("best_similarity"), item.get("frames"), None
    if not (isinstance(code, str) and code and _is_number(sim)):
        raise AvscanUnparseable("item")
    if not (isinstance(frames, list) and frames and isinstance(frames[0], dict)):
        raise AvscanUnparseable("frames")
    name, thumb = frames[0].get("image_name"), frames[0].get("thumb")
    if not isinstance(name, str) or not (thumb is None or isinstance(thumb, str)):
        raise AvscanUnparseable("frame")
    kind, cover_part, time_seconds, time_text = rules.parse_frame_name(name)
    return {
        "code": code,
        "similarity": float(sim),
        "match": {
            "kind": kind,
            "cover_part": cover_part,
            "time_seconds": time_seconds,
            "time_text": time_text,
            "thumb_url": AVSCAN_ORIGIN + thumb if rules.safe_thumb_path(thumb) else None,
        },
    }


def parse_response(data) -> list[dict]:
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise AvscanUnparseable("shape")
    return [_parse_item(item) for item in data["results"][:MAX_CANDIDATES]]


def _retry_seconds(resp) -> float:
    try:
        body = resp.json()
    except ValueError:
        return AVSCAN_MIN_GAP_SECONDS
    value = body.get("retry_after") if isinstance(body, dict) else None
    if _is_number(value) and math.isfinite(value) and value > 0:
        return value
    return AVSCAN_MIN_GAP_SECONDS


def _is_invalid_image(resp) -> bool:
    try:
        return resp.json() == {"detail": "invalid image"}
    except ValueError:
        return False


def _fail(reason: str, exc_type, started: float):
    logger.warning("avscan lookup failed: %s (%d ms)", reason, int((time.monotonic() - started) * 1000))
    return exc_type(reason)


def _handle_response(resp, started: float) -> list[dict]:
    status = resp.status_code
    if status == 429:
        seconds = _retry_seconds(resp)
        get_gate().penalize(seconds)
        logger.warning("avscan lookup failed: rate_limited")
        wait = min(max(seconds, AVSCAN_MIN_GAP_SECONDS), AVSCAN_MAX_PENALTY_SECONDS)
        raise AvscanRateLimited(math.ceil(wait))
    if status == 400 and _is_invalid_image(resp):
        raise _fail("invalid_image", AvscanInvalidImage, started)
    if 300 <= status < 400:
        raise _fail("redirect", AvscanUnreachable, started)
    if status != 200:
        raise _fail(f"status={status}", AvscanUnreachable, started)
    try:
        data = resp.json()
    except ValueError:
        raise _fail("non_json", AvscanUnreachable, started) from None
    try:
        candidates = parse_response(data)
    except AvscanUnparseable:
        logger.warning("avscan lookup failed: AvscanUnparseable")
        raise
    logger.info("avscan lookup ok: %d candidates (%d ms)", len(candidates), int((time.monotonic() - started) * 1000))
    return candidates


def lookup(image_bytes: bytes) -> list[dict]:
    proxies = proxy_kwargs("image_search")
    ok, retry_after = get_gate().try_acquire()
    if not ok:
        raise AvscanRateLimited(retry_after)
    started = time.monotonic()
    try:
        try:
            resp = requests.post(
                AVSCAN_SEARCH_URL,
                files={"file": ("q.jpg", image_bytes)},
                headers=DEFAULT_HEADERS,
                timeout=(5, 15),
                allow_redirects=False,
                **proxies,
            )
        except requests.Timeout:
            raise _fail("timeout", AvscanUnreachable, started) from None
        except requests.ConnectionError:
            raise _fail("connection", AvscanUnreachable, started) from None
        except requests.RequestException:
            raise _fail("request_error", AvscanUnreachable, started) from None
        return _handle_response(resp, started)
    finally:
        get_gate().release()
