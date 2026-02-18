"""JavGuru 爬蟲（HTML 解析）"""
import logging
import re
import requests
from typing import Optional

logger = logging.getLogger(__name__)
from lxml import etree
from .base import BaseScraper
from .models import Video, Actress, ScraperConfig
from .utils import rate_limit


class JavGuruScraper(BaseScraper):
    """
    JavGuru 爬蟲

    流程：
    1. 搜尋頁取得第一個匹配的詳情頁 URL
    2. 詳情頁解析 .infoleft div（lxml XPath）

    特點：
    - 無 Cloudflare 保護（直接 requests 可用）
    - 聚合站，同時涵蓋有碼 + 無碼
    - 主要使用英文欄位名稱（Director, Studio, Label, Tags, Series, Actress）
    """

    SEARCH_URL = "https://jav.guru/?s={query}"
    BASE_URL = "https://jav.guru"

    def __init__(self, config: Optional[ScraperConfig] = None):
        super().__init__(config)
        self._session = requests.Session()
        self._session.headers.update({
            'User-Agent': self.config.user_agent,
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'en-US,en;q=0.9,ja;q=0.8',
            'Referer': 'https://jav.guru/',
        })

    def _get_source_name(self) -> str:
        return "javguru"

    def _search_detail_url(self, number: str) -> Optional[str]:
        """
        搜尋番號，取得詳情頁 URL。

        Args:
            number: 正規化後的番號（如 SONE-205）

        Returns:
            詳情頁 URL，找不到返回 None
        """
        url = self.SEARCH_URL.format(query=requests.utils.quote(number))
        try:
            resp = self._session.get(url, timeout=self.config.timeout)
            if resp.status_code != 200:
                logger.debug(f"JavGuru search: HTTP {resp.status_code} for {number}")
                return None

            html = etree.fromstring(resp.content, etree.HTMLParser())

            # 取得所有搜尋結果連結
            links = html.xpath('//a[@class="grid1"]/@href')
            if not links:
                # fallback：取寬鬆 selector
                links = html.xpath('//div[contains(@class,"grid")]//a/@href')
            if not links:
                return None

            # 找第一個 URL 中包含番號（不分大小寫）的連結
            number_clean = number.lower().replace('-', '').replace(' ', '')
            for link in links:
                link_clean = link.lower().replace('-', '').replace('/', '')
                if number_clean in link_clean:
                    return link

            # 若都沒有精確匹配，返回第一個結果
            return links[0]

        except Exception as e:
            logger.debug(f"JavGuru search_detail_url failed for {number}: {e}")
            return None

    def _xpath_first(self, html, xpath: str) -> str:
        """執行 XPath 並返回第一個非空字串結果，找不到返回空字串。"""
        results = html.xpath(xpath)
        for r in results:
            text = r.strip() if isinstance(r, str) else ""
            if text:
                return text
        return ""

    def _xpath_all(self, html, xpath: str) -> list[str]:
        """執行 XPath 並返回所有非空字串結果列表。"""
        results = html.xpath(xpath)
        return [r.strip() for r in results if isinstance(r, str) and r.strip()]

    def _parse_detail(self, html_content: bytes, detail_url: str) -> Optional[Video]:
        """
        解析詳情頁 HTML，回傳 Video 物件。

        Args:
            html_content: 詳情頁 HTTP response bytes
            detail_url: 詳情頁 URL（用於 Video.detail_url）

        Returns:
            Video 物件，解析失敗返回 None
        """
        try:
            html = etree.fromstring(html_content, etree.HTMLParser())

            # 標題
            title = self._xpath_first(html, '//*[contains(@class,"titl")]/text()')
            if not title:
                return None

            # 番號（從頁面取得，更準確）
            number = self._xpath_first(
                html,
                '//div[@class="infoleft"]//strong[contains(text(),"Code")]/following-sibling::a[1]/text()'
            )
            if not number:
                # fallback：從 URL 解析
                match = re.search(r'jav\.guru/([^/]+)/?$', detail_url)
                number = match.group(1).upper().replace('/', '') if match else ''

            # Release Date（直接文字節點，非連結）
            date = self._xpath_first(
                html,
                '//div[@class="infoleft"]//strong[contains(text(),"Release Date")]'
                '/following-sibling::text()[normalize-space()][1]'
            )
            # 取 YYYY-MM-DD 格式
            date_match = re.search(r'\d{4}-\d{2}-\d{2}', date)
            date = date_match.group(0) if date_match else ''

            # Studio（映射至 maker）
            maker = self._xpath_first(
                html,
                '//div[@class="infoleft"]//strong[contains(text(),"Studio")]'
                '/following-sibling::a[1]/text()'
            )

            # Director（不映射至 Video，暫存）
            # director = self._xpath_first(html, '//div[@class="infoleft"]//strong[contains(text(),"Director")]/following-sibling::a[1]/text()')

            # Tags（取全部 <a> 連結文字）
            tags = self._xpath_all(
                html,
                '//div[@class="infoleft"]//strong[contains(text(),"Tags")]'
                '/following-sibling::a/text()'
            )

            # Actress（取全部 <a> 連結文字，支援多人）
            actress_names = self._xpath_all(
                html,
                '//div[@class="infoleft"]//strong[contains(text(),"Actress")]'
                '/following-sibling::a/text()'
            )
            actresses = [Actress(name=name) for name in actress_names if name]

            # Cover
            cover_url = self._xpath_first(
                html,
                '//div[@class="large-screenimg"]//img/@src'
            )

            return Video(
                number=number,
                title=title,
                actresses=actresses,
                date=date,
                maker=maker,
                cover_url=cover_url,
                tags=tags,
                source=self.source_name,
                detail_url=detail_url,
            )

        except Exception as e:
            logger.debug(f"JavGuru parse_detail failed for {detail_url}: {e}")
            return None

    def search(self, number: str) -> Optional[Video]:
        """
        搜尋影片資訊。

        Args:
            number: 番號（如 SONE-205）

        Returns:
            Video 物件，找不到返回 None
        """
        number = self.normalize_number(number)

        try:
            # Step 1: 搜尋取得詳情頁 URL
            detail_url = self._search_detail_url(number)
            if not detail_url:
                return None

            # Step 2: 取得詳情頁
            resp = self._session.get(detail_url, timeout=self.config.timeout)
            if resp.status_code == 404:
                return None
            if resp.status_code != 200:
                logger.debug(f"JavGuru detail: HTTP {resp.status_code} for {number}")
                return None

            # Step 3: 解析詳情頁
            video = self._parse_detail(resp.content, detail_url)
            if video is None:
                return None

            rate_limit(self.config.delay)
            return video

        except requests.Timeout:
            raise TimeoutError(f"JavGuru request timeout for {number}")
        except Exception as e:
            logger.warning(f"JavGuru search failed for {number}: {e}")
            return None

    def search_by_keyword(self, keyword: str, limit: int = 20) -> list[Video]:
        """
        關鍵字搜尋（將關鍵字當番號處理）。

        Args:
            keyword: 搜尋關鍵字（如 SONE-205）
            limit: 最大結果數（JavGuru 單次搜尋最多 1 筆）

        Returns:
            Video 列表（最多 1 筆）
        """
        result = self.search(keyword)
        return [result] if result else []
