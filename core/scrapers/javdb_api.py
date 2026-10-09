"""JavDB App 資料介面的傳輸層：簽名、網域備援、逾時、例外映射。"""

from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any, Optional

import requests

from core.image_host_policy import proxy_verdict
from core.logger import get_logger
from core.scrapers.errors import SourceBlocked, SourceUnreachable
from core.scrapers.models import Actress, Video
from core.scrapers.utils import strip_number_prefix

logger = get_logger(__name__)

# JavDB App 資料介面的請求簽名參數。這組值失效時（例如站方輪替簽章），
# API 路徑會整條失敗 → search() 自動降級回 HTML，使用者無感，
# 我們靠金絲雀 A 轉紅知道。
_API_HOSTS = ("https://jdforrepam.com", "https://javdb.com")

_SIGN_PREFIX = (
    "71cf27bb3c0bcdf207b64abecddc970098c7421ee7203b9cdae54478478a199e"
    "7d5a6e1a57691123c1a931c057842fb73ba3b3c83bcd69c17ccf174081e3d8aa"
)
_SIGN_SUFFIX = "lpw6vgqzsp"

_USER_AGENT = "Dart/3.4 (dart:io)"

_SEARCH_PATH = "/api/v2/search"
_DETAIL_PATH = "/api/v4/movies/{movie_id}"

_TIMEOUT = 20

_PUBLIC_PARAMS = {
    "app_channel": "official",
    "app_version": "1.9.28",
    "app_version_number": "10928",
    "platform": "android",
    "system_version": "13",
    "device_model": "Pixel 6",
    "device_name": "Pixel",
}

# 一個 process 共用一個裝置 id；寫死會讓所有安裝撞同一個 id，每次請求都換又像洗裝置。
_DEVICE_UUID = str(uuid.uuid4())


def sign(ts: int | None = None) -> str:
    """回傳 jdsignature；ts 為 None 或 <=0 時用當下 unix 時間。"""
    if ts is None or ts <= 0:
        ts = int(time.time())
    digest = hashlib.md5(f"{ts}{_SIGN_PREFIX}".encode("utf-8")).hexdigest()
    return f"{ts}.{_SIGN_SUFFIX}.{digest}"


def _success_truthy(value: Any) -> bool:
    """寬鬆判斷信封 success 為真（實測常見 int 1；也可能是 true / \"1\"）。"""
    return bool(value) and value not in (0, "0", "false", "False")


def api_get(path: str, params: Optional[dict] = None, proxies: Optional[dict] = None) -> dict:
    """對 javdb App API 發 GET，回傳信封裡的 data（dict）；失敗一律 raise。"""
    query = dict(_PUBLIC_PARAMS)
    query["device_uuid"] = _DEVICE_UUID
    if params:
        query.update(params)

    last_error: Optional[BaseException] = None

    for host in _API_HOSTS:
        url = host + path
        # 每次嘗試重新簽名：簽名帶時間戳且有效期有限，主網域吃滿逾時後
        # 沿用同一份簽名，鏡像那一趟可能拿到一個已經過期的簽名。
        headers = {
            "jdsignature": sign(),
            "user-agent": _USER_AGENT,
            "accept-language": "zh-TW",
            "connection": "keep-alive",
        }
        try:
            # 未被 proxy policy 選中時不傳 proxies kwarg（傳了會把系統代理靜默關掉）；
            # 選中（使用者的 Proxy 欄＋範圍涵蓋 javdb）才帶。
            resp = requests.get(
                url,
                params=query,
                headers=headers,
                timeout=_TIMEOUT,
                **({"proxies": proxies} if proxies else {}),
            )
        except requests.exceptions.RequestException as e:
            last_error = SourceUnreachable(str(e))
            continue

        status = resp.status_code
        if status in (403, 429, 503):
            logger.warning("JavDB API blocked (%s) for %s", status, url)
            last_error = SourceBlocked(f"blocked {status} for {url}")
            continue

        if status != 200:
            logger.warning("JavDB API non-200 for %s: %s", url, status)
            last_error = SourceUnreachable(f"non-200 {status} for {url}")
            continue

        try:
            envelope = resp.json()
        except (ValueError, requests.exceptions.JSONDecodeError):
            last_error = SourceUnreachable(f"non-json for {url}")
            continue

        if not isinstance(envelope, dict) or not _success_truthy(envelope.get("success")):
            action = envelope.get("action") if isinstance(envelope, dict) else None
            logger.warning("JavDB API rejected (%s) for %s", action, url)
            last_error = SourceUnreachable(f"rejected {action} for {url}")
            continue

        data = envelope.get("data")
        if not isinstance(data, dict):
            last_error = SourceUnreachable(f"data not dict for {url}")
            continue

        return data

    if last_error is not None:
        raise last_error
    raise SourceUnreachable("JavDB API unreachable")


def api_search(keyword: str, proxies: Optional[dict] = None) -> list[dict]:
    """回搜尋結果清單；查無回 []（不是錯誤，不 raise）。"""
    data = api_get(_SEARCH_PATH, {"q": keyword, "page": "1"}, **({"proxies": proxies} if proxies else {}))
    movies = data.get("movies")
    return movies if isinstance(movies, list) else []


def api_movie_detail(movie_id: str, proxies: Optional[dict] = None) -> dict:
    """回詳情 movie 物件；形狀不對就 raise SourceUnreachable。"""
    data = api_get(_DETAIL_PATH.format(movie_id=movie_id), **({"proxies": proxies} if proxies else {}))
    movie = data.get("movie")
    if not isinstance(movie, dict):
        raise SourceUnreachable(f"movie detail missing for id={movie_id}")
    return movie


def _norm(v: Any) -> str:
    return str(v or "").upper().replace("-", "").strip()


def _s(v: Any) -> str:
    return str(v).strip() if v is not None else ""


def _parse_rating(score: Any) -> Optional[float]:
    if score is None:
        return None
    try:
        return float(str(score).strip())
    except (ValueError, TypeError):
        return None


def _parse_duration(duration: Any) -> Optional[int]:
    if duration is None:
        return None
    try:
        d = int(duration)
        return d if d > 0 else None
    except (ValueError, TypeError):
        return None


def _parse_votes(reviews_count: Any) -> Optional[int]:
    if reviews_count is None:
        return None
    try:
        return int(reviews_count)
    except (ValueError, TypeError):
        return None


def _map_actresses(actors: Any) -> list[Actress]:
    actresses: list[Actress] = []
    for actor in actors or []:
        if not isinstance(actor, dict):
            continue
        if actor.get("gender") != 0:
            continue
        name = (actor.get("name") or "").strip()
        if name:
            actresses.append(Actress(name=name))
    return actresses


def _map_sample_images(preview_images: Any) -> list[str]:
    if not isinstance(preview_images, list):
        return []
    # 只收字串：站方若哪天在這裡塞 dict／list，Video 會拋 ValidationError 而
    # 逃出 fetch_video，破壞「只有 Video 或 None」的契約（review P3）。
    return [
        u for u in (p.get("large_url") for p in preview_images if isinstance(p, dict))
        if u and isinstance(u, str)
    ]


def _to_video(detail: dict, number: str) -> Video:
    detail_id = detail.get("id")
    detail_url = f"https://javdb.com/v/{detail_id}" if detail_id else ""

    actresses = _map_actresses(detail.get("actors"))
    sample_images = _map_sample_images(detail.get("preview_images"))

    raw_tags = detail.get("tags")
    tags = [
        name
        for name in (
            str(t.get("name")).strip()
            for t in (raw_tags if isinstance(raw_tags, list) else [])
            if isinstance(t, dict) and t.get("name") is not None
        )
        if name  # strip 之後才判斷：純空白的 name 不得變成一顆空的標籤 pill（review P3）
    ]

    return Video(
        number=number,
        # 與 HTML 那條走同一支正規化（javdb.py:210）：兩條路的標題處理必須逐字相同，
        # 否則站方哪天在 title 前加上番號，只有其中一條會清掉（F4 破口，review P3）。
        title=strip_number_prefix(_s(detail.get("title")), number),
        actresses=actresses,
        date=_s(detail.get("release_date")),
        maker=_s(detail.get("maker_name")),
        cover_url=_s(detail.get("cover_url")),
        preview_cover_url="",
        tags=tags,
        source="javdb",
        detail_url=detail_url,
        director=_s(detail.get("director_name")),
        duration=_parse_duration(detail.get("duration")),
        label=_s(detail.get("publisher_name")),
        series=_s(detail.get("series_name")),
        sample_images=sample_images,
        preview_sample_images=[],
        rating=_parse_rating(detail.get("score")),
        votes=_parse_votes(detail.get("reviews_count")),
        summary="",
    )


def _match_movie(movie: dict, number: str) -> bool:
    if _norm(movie.get("number")) != _norm(number):
        return False
    return True


def _assert_image_urls_proxyable(video: Video) -> None:
    """CD-132b-7：cover / sample 的網址必須是**圖片代理收得下**的形狀。

    問的不是「host 有沒有登記」而是 `proxy_verdict()`（review round-2 P2）。
    差別會咬人的三種形狀，全都是「登記過但代理仍 403」：
    `http://tp.spfcas.com/...`（scheme）、只給女優照片下載用的 host（沒有 proxy
    consumer）、以及 host 根本 parse 不出來的網址（舊版直接 `continue` 放行）。
    放行它們的下場是閘門過了 ⇒ **不降級**，而瀏覽器那頭是破圖；擋下來則降級 HTML，
    使用者拿到有浮水印但看得見的封面。

    空字串／None 的 cover_url 不算違規。不可代理 → ValueError（search 會降級 HTML）。
    """
    urls: list[str] = []
    if video.cover_url:
        urls.append(video.cover_url)
    urls.extend(u for u in (video.sample_images or []) if u)

    for url in urls:
        verdict = proxy_verdict(url)
        if not verdict.allowed:
            raise ValueError(
                f"javdb: 圖片網址不可代理（{verdict.reason}）: "
                f"host={verdict.host or '?'} scheme={verdict.scheme or '?'}"
            )


def fetch_video(number: str, proxies: Optional[dict] = None) -> Optional[Video]:
    """依番號查詢影片並映射成 Video 物件；查無或無效回傳 None。"""
    # 未選中時上游不多帶 proxies kwarg（保住既有呼叫簽名）
    _pk = {"proxies": proxies} if proxies else {}
    movies = api_search(number, **_pk)
    movie = None
    for m in (movies or [])[:5]:
        if isinstance(m, dict) and _match_movie(m, number):
            movie = m
            break

    if not movie or not movie.get("id"):
        return None

    detail = api_movie_detail(str(movie["id"]), **_pk)
    video = _to_video(detail, number)
    if video.title or video.cover_url:
        _assert_image_urls_proxyable(video)
        return video
    return None

