"""HEYZO 爬蟲（JSON-LD + HTML table）"""
import json
import logging
import re
import requests
from typing import Optional

logger = logging.getLogger(__name__)
from lxml import etree
from .base import BaseScraper
from .models import Video, Actress, ScraperConfig
from .utils import rate_limit


class HEYZOScraper(BaseScraper):
    """
    HEYZO 爬蟲

    解析順序：
    1. 從英文頁 JSON-LD 取 title、actress（羅馬字）、date、rating
    2. 從同一英文頁 HTML table 取 series、tags
    3. cover URL 從 JSON-LD image 欄位建構

    番號格式：HEYZO-0783 → strip prefix → "0783"
    """

    BASE_URL = "https://www.heyzo.com/moviepages/{num}/index.html"
    EN_URL = "https://en.heyzo.com/moviepages/{num}/index.html"

    def __init__(self, config: Optional[ScraperConfig] = None):
        super().__init__(config)
        self._session = requests.Session()
        self._session.headers.update({
            'User-Agent': self.config.user_agent,
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'en-US,en;q=0.9,ja;q=0.8',
        })

    def _get_source_name(self) -> str:
        return "heyzo"

    def _extract_heyzo_num(self, number: str) -> Optional[str]:
        """
        從番號提取 HEYZO 數字 ID（保留前導零）。

        Examples:
            HEYZO-0783 → "0783"
            heyzo-1031 → "1031"
        """
        number = number.strip().upper()
        match = re.match(r'^HEYZO-(\d+)$', number)
        if match:
            return match.group(1)
        # 純數字也接受
        if re.match(r'^\d+$', number):
            return number
        return None

    def _extract_json_ld(self, html_content: bytes) -> Optional[dict]:
        """
        從 HTML 中提取 application/ld+json 內容。

        Returns:
            解析後的 dict，找不到或解析失敗返回 None
        """
        try:
            html = etree.fromstring(html_content, etree.HTMLParser())
            scripts = html.xpath('//script[@type="application/ld+json"]/text()')
            for script in scripts:
                try:
                    data = json.loads(script)
                    if data.get('@type') == 'Movie':
                        return data
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            logger.debug(f"HEYZO JSON-LD parse error: {e}")
        return None

    def _extract_table_data(self, html_content: bytes) -> dict:
        """
        從 HTML table.movieInfo 提取補充資料。

        Returns:
            dict with keys: 'series', 'tags'
        """
        result = {'series': '', 'tags': []}
        try:
            html = etree.fromstring(html_content, etree.HTMLParser())

            # Series
            series = html.xpath(
                '//table[@class="movieInfo"]//th[contains(text(),"Series")]/following-sibling::td[1]/text()'
            )
            result['series'] = series[0].strip() if series else ''

            # Tags（Actress Type 欄位）
            tags = html.xpath(
                '//table[@class="movieInfo"]//th[contains(text(),"Type")]/following-sibling::td[1]//a/text()'
            )
            result['tags'] = [t.strip() for t in tags if t.strip()]

        except Exception as e:
            logger.debug(f"HEYZO table parse error: {e}")
        return result

    def search(self, number: str) -> Optional[Video]:
        """
        搜尋影片資訊。

        Args:
            number: 番號（如 HEYZO-0783）

        Returns:
            Video 物件，找不到返回 None
        """
        heyzo_num = self._extract_heyzo_num(number)
        if not heyzo_num:
            logger.debug(f"HEYZO: invalid number format: {number}")
            return None

        en_url = self.EN_URL.format(num=heyzo_num)
        ja_url = self.BASE_URL.format(num=heyzo_num)

        try:
            # Step 1: 取英文頁 → JSON-LD（羅馬字女優名、英文 title）
            resp = self._session.get(en_url, timeout=self.config.timeout)
            if resp.status_code == 404:
                return None
            if resp.status_code != 200:
                logger.debug(f"HEYZO EN page: HTTP {resp.status_code} for {heyzo_num}")
                return None

            json_ld = self._extract_json_ld(resp.content)
            if not json_ld:
                return None

            # Step 2: 解析 JSON-LD
            title = json_ld.get('name', '')
            if not title:
                return None

            # 女優（JSON-LD actor 可能是 dict 或 list）
            actor_data = json_ld.get('actor')
            actress_names = []
            if isinstance(actor_data, dict):
                name = actor_data.get('name', '')
                if name:
                    actress_names = [name]
            elif isinstance(actor_data, list):
                actress_names = [a.get('name', '') for a in actor_data if a.get('name')]

            actresses = [Actress(name=name) for name in actress_names if name]

            # 日期（dateCreated 格式：2015-01-17T00:00:00+09:00）
            date_created = json_ld.get('dateCreated', '')
            date = date_created[:10] if date_created else ''

            # 封面（image 格式：//www.heyzo.com/...）
            image = json_ld.get('image', '')
            cover_url = f"https:{image}" if image.startswith('//') else image

            # Rating
            agg_rating = json_ld.get('aggregateRating', {})
            rating = float(agg_rating['ratingValue']) if agg_rating.get('ratingValue') else None
            votes = int(agg_rating['reviewCount']) if agg_rating.get('reviewCount') else None

            # Step 3: 從同一 EN page 的 HTML table 取 tags、series
            # （EN page 已取得，不需額外請求 JA page；XPath 使用英文 header）
            table_data = self._extract_table_data(resp.content)

            rate_limit(self.config.delay)

            return Video(
                number=f"HEYZO-{heyzo_num}",
                title=title,
                actresses=actresses,
                date=date,
                maker='HEYZO',
                cover_url=cover_url,
                tags=table_data['tags'],
                source=self.source_name,
                detail_url=ja_url,
                rating=rating,
                votes=votes,
            )

        except requests.Timeout:
            raise TimeoutError(f"HEYZO request timeout for {number}")
        except Exception as e:
            logger.warning(f"HEYZO search failed for {number}: {e}")
            return None

    def search_by_keyword(self, keyword: str, limit: int = 20) -> list[Video]:
        """
        關鍵字搜尋（HEYZO 無公開搜尋 API，當番號處理）。

        Args:
            keyword: 搜尋關鍵字（如 HEYZO-0783）
            limit: 最大結果數（最多 1 筆）

        Returns:
            Video 列表（最多 1 筆）
        """
        result = self.search(keyword)
        return [result] if result else []
