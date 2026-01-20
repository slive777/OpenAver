"""FC2 爬蟲（使用 FC2Hub/javten.com）"""
import re
import requests
from typing import Optional
from lxml import etree
from .base import BaseScraper
from .models import Video, Actress, ScraperConfig
from .utils import rate_limit


class FC2Scraper(BaseScraper):
    """
    FC2 爬蟲（使用 FC2Hub 鏡像站）

    優點：
    - 不需要登入
    - 有封面、預覽圖
    - 有簡介、賣家資訊

    注意：
    - 使用第三方鏡像站
    - 無發售日期

    參考：mdcx/crawlers/fc2hub.py
    """

    BASE_URL = "https://javten.com"

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
        正規化 FC2 番號

        Examples:
            FC2-PPV-1234567 → 1234567
            FC2PPV-1234567  → 1234567
            FC2-1234567     → 1234567
            fc2ppv1234567   → 1234567
            1234567         → 1234567
        """
        number = number.upper().strip()
        # 移除各種 FC2 前綴
        number = re.sub(r'^FC2[-_]?PPV[-_]?', '', number)
        number = re.sub(r'^FC2[-_]?', '', number)
        number = number.replace('-', '').replace('_', '')
        return number

    def _get_title(self, html) -> str:
        """取得標題"""
        result = html.xpath("//h1/text()")
        # 第二個 h1 是標題（第一個是番號）
        return result[1].strip() if len(result) > 1 else ""

    def _get_number_from_page(self, html) -> str:
        """從頁面取得番號"""
        result = html.xpath("//h1/text()")
        return result[0].strip() if result else ""

    def _get_cover(self, html) -> str:
        """取得封面"""
        result = html.xpath('//a[@data-fancybox="gallery"]/@href')
        if result:
            url = result[0]
            return f"https:{url}" if url.startswith("//") else url
        return ""

    def _get_extrafanart(self, html) -> list[str]:
        """取得額外劇照"""
        result = html.xpath('//div[@style="padding: 0"]/a/@href')
        return [f"https:{u}" if u.startswith("//") else u for u in result]

    def _get_studio(self, html) -> str:
        """取得賣家（作為片商）"""
        result = html.xpath('//div[@class="col-8"]/text()')
        return result[0].strip() if result else ""

    def _get_tags(self, html) -> list[str]:
        """取得標籤"""
        result = html.xpath('//p[@class="card-text"]/a[contains(@href, "/tag/")]/text()')
        return [tag.strip() for tag in result if tag.strip()]

    def _get_outline(self, html) -> str:
        """取得簡介"""
        result = html.xpath('//div[@class="col des"]//text()')
        text = "".join(result).strip()
        # 清理文字
        text = text.replace("\\n", " ").replace("・", "").strip()
        return text

    def _is_uncensored(self, tags: list[str], title: str) -> bool:
        """判斷是否無碼"""
        text = " ".join(tags) + " " + title
        return any(kw in text for kw in ["無修正", "无修正", "uncensored"])

    def _search_url(self, fc2_number: str) -> Optional[str]:
        """搜尋並取得詳情頁 URL"""
        search_url = f"{self.BASE_URL}/search?kw={fc2_number}"

        try:
            resp = self._session.get(search_url, timeout=self.config.timeout)
            if resp.status_code != 200:
                return None

            html = etree.fromstring(resp.content, etree.HTMLParser())

            # 找符合番號的連結（在 <a> 標籤中）
            urls = html.xpath(f"//a[contains(@href, 'id{fc2_number}')]/@href")

            if not urls:
                return None

            # 優先選擇日文版（排除 /tw/, /ko/, /en/）
            non_jp_langs = ["/tw/", "/ko/", "/en/"]
            for url in urls:
                if all(lang not in url for lang in non_jp_langs):
                    return url

            # 若都沒有，返回第一個
            return urls[0]

        except Exception:
            return None

    def search(self, number: str) -> Optional[Video]:
        """
        搜尋影片資訊

        Args:
            number: 番號（如 FC2-PPV-1234567）

        Returns:
            Video 物件，找不到返回 None
        """
        # 正規化番號
        fc2_number = self._normalize_fc2_number(number)

        try:
            # 搜尋取得詳情頁 URL
            detail_url = self._search_url(fc2_number)
            if not detail_url:
                return None

            # 取得詳情頁
            resp = self._session.get(detail_url, timeout=self.config.timeout)
            if resp.status_code != 200:
                return None

            html = etree.fromstring(resp.content, etree.HTMLParser())

            # 取得標題
            title = self._get_title(html)
            if not title:
                return None

            # 取得各項資訊
            cover_url = self._get_cover(html)
            studio = self._get_studio(html)
            tags = self._get_tags(html)
            outline = self._get_outline(html)
            is_uncensored = self._is_uncensored(tags, title)

            # 移除無修正標籤（已用其他方式表示）
            tags = [t for t in tags if t not in ["無修正", "无修正"]]

            # FC2 沒有女優資訊，可用賣家名替代
            actresses = [Actress(name=studio)] if studio else []

            video = Video(
                number=f"FC2-{fc2_number}",
                title=title,
                actresses=actresses,
                date="",  # FC2Hub 沒有發售日期
                maker=studio,
                cover_url=cover_url,
                tags=tags,
                source=self.source_name,
                detail_url=detail_url,
            )

            # 節流
            rate_limit(self.config.delay)

            return video

        except requests.Timeout:
            raise TimeoutError(f"FC2 request timeout for {number}")
        except Exception:
            return None

    def search_by_keyword(self, keyword: str, limit: int = 20) -> list[Video]:
        """
        關鍵字搜尋

        Args:
            keyword: 搜尋關鍵字（會被當作番號處理）
            limit: 最大結果數（FC2 只返回 1 筆）

        Returns:
            Video 列表（最多 1 筆）
        """
        result = self.search(keyword)
        return [result] if result else []


# 測試用
if __name__ == "__main__":
    scraper = FC2Scraper()

    print("=== FC2 番號正規化測試 ===")
    test_numbers = [
        ("FC2-PPV-1723984", "1723984"),
        ("FC2PPV1723984", "1723984"),
        ("FC2-1723984", "1723984"),
        ("1723984", "1723984"),
    ]
    for num, expected in test_numbers:
        result = scraper._normalize_fc2_number(num)
        status = "✓" if result == expected else "✗"
        print(f"{status} {num} → {result} (expected: {expected})")

    print("\n=== API 測試 ===")
    # 測試一個已知存在的 FC2 番號
    video = scraper.search("FC2-PPV-1723984")
    if video:
        print(f"番號: {video.number}")
        print(f"標題: {video.title[:50]}..." if len(video.title) > 50 else f"標題: {video.title}")
        print(f"片商: {video.maker}")
        print(f"標籤: {video.tags[:5]}...")
        print(f"封面: {video.cover_url[:60]}..." if video.cover_url else "封面: (無)")
    else:
        print("✗ 搜尋失敗")
