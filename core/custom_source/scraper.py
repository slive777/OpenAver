"""自訂來源的 BaseScraper 轉接：ScrapeResult 轉 Video、錯誤映射、詳情頁網址 host 限制。"""
from urllib.parse import urlparse

from pydantic import ValidationError

from core.custom_source.interpret import scrape, scrape_detail
from core.logger import get_logger
from core.scrapers.base import BaseScraper
from core.scrapers.errors import SourceBlocked, SourceUnreachable
from core.scrapers.models import Actress, Video

log = get_logger(__name__)

_BLOCKED_STATUSES = frozenset({403, 429, 503})
_UNREACHABLE_REASONS = frozenset({"network", "timeout"})


def _host_allowed(spec, detail_url):
    """詳情頁網址的 host 必須是 spec 宣告的 host 或其子網域。"""
    try:
        host = urlparse(detail_url).hostname
    except ValueError:
        return False
    if not host:
        return False
    return any(host == h or host.endswith("." + h) for h in spec.hosts)


def _raise_for(source_id, result):
    """依封閉映射丟例外；訊息只含來源 id 與 reason code。"""
    message = f"{source_id}: {result.reason}"
    if result.reason == "http_status" and result.http_status in _BLOCKED_STATUSES:
        raise SourceBlocked(message)
    if result.reason in _UNREACHABLE_REASONS:
        raise SourceUnreachable(message)
    raise RuntimeError(message)


class CustomScraper(BaseScraper):
    """把一份 Spec 包成一般 scraper；source_id 即 Video.source。"""

    def __init__(self, spec, source_id, config=None):
        self.spec = spec
        self.source_id = source_id
        super().__init__(config)

    def _get_source_name(self):
        return self.source_id

    def _to_video(self, item, canon):
        fields = item.fields
        return Video(
            number=canon,
            title=fields.get("title") or "",
            actresses=[Actress(name=n) for n in fields.get("actors", ()) if n],
            date=fields.get("date") or "",
            maker=fields.get("maker") or "",
            cover_url=fields.get("cover") or "",
            tags=list(fields.get("tags", ())),
            source=self.source_id,
            detail_url=item.detail_url,
            director=fields.get("director") or "",
            duration=fields.get("duration"),
            label=fields.get("label") or "",
            series=fields.get("series") or "",
            sample_images=list(fields.get("sample_images", ())),
            summary=fields.get("summary") or "",
        )

    def _videos(self, result, number):
        if result.status == "error":
            _raise_for(self.source_id, result)
        if not result.items:
            return []
        canon = self.normalize_number(number)
        videos = []
        for item in result.items:
            try:
                videos.append(self._to_video(item, canon))
            except ValidationError:
                log.info("custom source %s: item dropped (%s)", self.source_id, "ValidationError")
        if not videos:
            raise RuntimeError(f"{self.source_id}: parse_empty")
        return videos

    def search_all_versions(self, number):
        return self._videos(scrape(self.spec, number, self.config), number)

    def search(self, number):
        videos = self.search_all_versions(number)
        return videos[0] if videos else None

    def fetch_by_detail_url(self, detail_url, number):
        if not _host_allowed(self.spec, detail_url):
            raise RuntimeError(f"{self.source_id}: blocked_target")
        result = scrape_detail(self.spec, detail_url, number, self.config)
        return next(iter(self._videos(result, number)), None)

    def search_by_keyword(self, keyword, limit=20):
        return []

    def probe_plan(self, timeout):
        return None
