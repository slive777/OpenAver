"""FC2 官方站爬蟲（adult.contents.fc2.com，單次 GET）

與 core/scrapers/fc2_javten.py（javten 鏡像站版，來源 id `fc-javten`）並存，本檔取代它成為
`fc2` 來源的 dispatch 目標（core/scraper.py）。本檔零耦合 fc2_javten.py。

失敗語意與其他七支來源相同：逾時／連不上／非 200／解析不出商品頁，
一律回 None（不拋自訂例外）。
"""
import json
import re
from typing import Optional

import requests
from lxml import etree

from core.logger import get_logger

from .base import BaseScraper
from .models import Actress, ScraperConfig, Video
from .utils import rate_limit

logger = get_logger(__name__)


class FC2OfficialScraper(BaseScraper):
    """
    FC2 爬蟲（官方站 adult.contents.fc2.com）

    優點：
    - 官方資料，發售日／評分／劇照齊全
    - 單次 GET，無 search step

    注意：
    - 賣家名同時作為片商與唯一「女優」代表（FC2 無女優資訊）
    - 軟 404（HTTP 200 但查無資料）與連不上／逾時／非 200 一律回 None，
      與其他來源的靜默 miss 慣例一致
    """

    BASE_URL = "https://adult.contents.fc2.com"

    def __init__(self, config: Optional[ScraperConfig] = None):
        super().__init__(config)
        self._session = requests.Session()
        self._session.headers.update({
            'User-Agent': self.config.user_agent,
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'ja,en;q=0.9',
        })

    def _get_source_name(self) -> str:
        return "fc2"

    def _normalize_fc2_number(self, number: str) -> str:
        """
        正規化 FC2 番號（與 fc2_javten.py:_normalize_fc2_number 等價，獨立實作）

        Examples:
            FC2-PPV-1234567 → 1234567
            FC2PPV-1234567  → 1234567
            FC2-1234567     → 1234567
            fc2ppv1234567   → 1234567
            1234567         → 1234567
        """
        number = number.upper().strip()
        number = re.sub(r'^FC2[-_]?PPV[-_]?', '', number)
        number = re.sub(r'^FC2[-_]?', '', number)
        number = number.replace('-', '').replace('_', '')
        return number

    def _get_json_ld_product(self, html) -> Optional[dict]:
        """取得 JSON-LD Product 節點（頁面只有一個 ld+json script）"""
        scripts = html.xpath('//script[@type="application/ld+json"]')
        for script in scripts:
            text = "".join(script.itertext())
            if not text:
                continue
            try:
                data = json.loads(text)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(data, dict) and data.get("@type") == "Product":
                return data
        return None

    def _get_meta_content(self, html, prop: str) -> str:
        result = html.xpath(f'//meta[@property="{prop}"]/@content')
        return result[0].strip() if result else ""

    def _get_title(self, ld: Optional[dict], html, fc2_number: str) -> str:
        """標題來源：JSON-LD name 為主（CD-118b-3）；無 JSON-LD 時退回 og:title
        並剝掉 ``FC2-PPV-<請求的 id>`` 前綴（大小寫不敏感，剝完再 strip）。"""
        if ld:
            name = ld.get("name")
            return name.strip() if isinstance(name, str) else ""
        og_title = self._get_meta_content(html, "og:title")
        if not og_title:
            return ""
        prefix = f"FC2-PPV-{fc2_number}"
        if og_title.lower().startswith(prefix.lower()):
            return og_title[len(prefix):].strip()
        return og_title

    def _is_hit(self, ld: Optional[dict], og_url: str, fc2_number: str, title: str) -> bool:
        """
        命中判準（CD-118b-4）：

        先判 id 相等（JSON-LD sku／@id，取不到才看 og:url 的 /article/<n>/），
        再判標題非空。不相等或兩者皆無 → 未命中；無標題同樣視同未命中。
        """
        if ld:
            sku = str(ld.get("sku") or "")
            article_id = str(ld.get("@id") or "")
            id_matches = sku == fc2_number or article_id == f"article:{fc2_number}"
        elif og_url:
            id_matches = f"/article/{fc2_number}/" in og_url
        else:
            id_matches = False
        if not id_matches:
            return False
        return bool(title)

    def _get_cover(self, html) -> str:
        """封面：og:image（CD-118b-8，不吃 LD image 可能的 http://）"""
        return self._get_meta_content(html, "og:image")

    def _get_tags(self, html) -> list[str]:
        """
        標籤：items_article_TagArea 之內的 a[href*="/search/?tag="]
        （選擇器不釘標籤名，實測該區塊是 section，CD-118b-9 的鄰居陷阱）
        再套既有過濾移除 無修正／无修正（CD-118b-5＋18）
        """
        nodes = html.xpath(
            '//*[contains(@class,"items_article_TagArea")]'
            '//a[contains(@href,"/search/?tag=")]'
        )
        tags = []
        for node in nodes:
            text = "".join(node.itertext()).strip()
            if text:
                tags.append(text)
        return [t for t in tags if t not in ("無修正", "无修正")]

    def _get_seller(self, html) -> str:
        """賣家：sellerBox 的 h4//a 文字（同時填 maker 與 actresses[0]，CD-118b-18）"""
        nodes = html.xpath('//*[contains(@class,"items_comment_sellerBox")]//h4//a')
        if not nodes:
            return ""
        return "".join(nodes[0].itertext()).strip()

    def _get_date(self, html) -> str:
        """
        發售日：含「販売日」的 items_article_softDevice → YYYY/MM/DD → YYYY-MM-DD
        （實測同頁該 class 出現 3 次：對應裝置／販売日／商品ID，CD-118b-6）
        """
        nodes = html.xpath('//*[contains(@class,"items_article_softDevice")]')
        for node in nodes:
            text = "".join(node.itertext())
            if "販売日" not in text:
                continue
            m = re.search(r'(\d{4})/(\d{2})/(\d{2})', text)
            if m:
                return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        return ""

    def _get_sample_images(self, html) -> list[str]:
        """
        劇照：items_article_SampleImagesArea 內 a/@href（w1280）
        （實測該區塊是 ul 不是 section，CD-118b-9）；// 補 https:
        """
        result = html.xpath(
            '//*[contains(@class,"items_article_SampleImagesArea")]//a/@href'
        )
        images = []
        for url in result:
            url = url.strip()
            if not url:
                continue
            if url.startswith("//"):
                url = f"https:{url}"
            images.append(url)
        return images

    def _get_rating(self, ld: Optional[dict]) -> Optional[float]:
        """評分：JSON-LD aggregateRating；reviewCount == 0 → None（CD-118b-7）"""
        if not ld:
            return None
        rating = ld.get("aggregateRating")
        if not isinstance(rating, dict):
            return None
        try:
            review_count = int(rating.get("reviewCount") or 0)
        except (TypeError, ValueError):
            return None
        if review_count == 0:
            return None
        try:
            return float(rating.get("ratingValue"))
        except (TypeError, ValueError):
            return None

    def search(self, number: str) -> Optional[Video]:
        """
        搜尋影片資訊（單次 GET，無 search step，CD-118b-11）

        Args:
            number: 番號（如 FC2-PPV-1234567 / 1234567）

        Returns:
            Video 物件；查無此片（軟 404 / id 不符）或連不上／逾時／非 200
            一律回 None（與其他來源靜默 miss 慣例一致）
        """
        fc2_number = self._normalize_fc2_number(number)
        url = f"{self.BASE_URL}/article/{fc2_number}/?lang=ja"

        try:
            resp = self._session.get(url, timeout=self.config.timeout)
        except requests.RequestException as e:
            # requests.Timeout / ConnectionError 皆是 RequestException 子類，單一
            # except 即覆蓋兩者
            logger.debug(f"FC2 official request failed for {fc2_number}: {e}")
            return None

        if resp.status_code != 200:
            logger.debug("FC2 official non-200 for %s: %s", fc2_number, resp.status_code)
            return None

        try:
            html = etree.fromstring(resp.content, etree.HTMLParser())

            ld = self._get_json_ld_product(html)
            og_url = self._get_meta_content(html, "og:url")
            title = self._get_title(ld, html, fc2_number)

            if not self._is_hit(ld, og_url, fc2_number, title):
                return None

            cover_url = self._get_cover(html)
            tags = self._get_tags(html)
            seller = self._get_seller(html)
            date = self._get_date(html)
            sample_images = self._get_sample_images(html)
            rating = self._get_rating(ld)

            actresses = [Actress(name=seller)] if seller else []

            video = Video(
                number=f"FC2-{fc2_number}",
                title=title,
                actresses=actresses,
                date=date,
                maker=seller,
                cover_url=cover_url,
                tags=tags,
                source=self.source_name,
                detail_url=f"{self.BASE_URL}/article/{fc2_number}/",
                sample_images=sample_images,
                summary="",
                rating=rating,
            )

            rate_limit(self.config.delay)

            return video

        except Exception as e:
            logger.warning(f"FC2 official search failed for {number}: {e}")
            return None

    def search_by_keyword(self, keyword: str, limit: int = 20) -> list[Video]:
        """
        關鍵字搜尋（比照 fc2_javten.py:219-231）

        Args:
            keyword: 搜尋關鍵字（會被當作番號處理）
            limit: 最大結果數（FC2 只返回 1 筆）

        Returns:
            Video 列表（最多 1 筆）
        """
        result = self.search(keyword)
        return [result] if result else []
