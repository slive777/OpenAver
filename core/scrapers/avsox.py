"""AVSOX 爬蟲"""
import re
import requests
from typing import Optional
from lxml import etree
from .base import BaseScraper
from .models import Video, Actress, ScraperConfig
from .utils import rate_limit


class AVSOXScraper(BaseScraper):
    """
    AVSOX 爬蟲

    優點：
    - 主要收錄無碼作品
    - 有女優頭像
    - 支援 FC2 等特殊番號

    注意：
    - 網域可能變動
    - 速度較慢

    參考：mdcx/crawlers/avsox.py
    """

    # 已知可用網域，可能需要更新
    BASE_DOMAINS = [
        "https://avsox.click",
        "https://avsox.monster",
        "https://avsox.website",
    ]

    def __init__(self, config: Optional[ScraperConfig] = None):
        super().__init__(config)
        self._session = requests.Session()
        self._session.headers.update({
            'User-Agent': self.config.user_agent,
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        })
        self._working_domain: Optional[str] = None

    def _get_source_name(self) -> str:
        return "avsox"

    def _get_working_domain(self) -> Optional[str]:
        """取得可用網域"""
        if self._working_domain:
            return self._working_domain

        for domain in self.BASE_DOMAINS:
            try:
                resp = self._session.get(domain, timeout=5)
                if resp.status_code == 200:
                    self._working_domain = domain
                    return domain
            except Exception:
                continue
        return None

    def _get_title(self, html) -> str:
        """取得標題"""
        result = html.xpath('//div[@class="container"]/h3/text()')
        return result[0].strip() if result else ""

    def _get_number(self, html) -> str:
        """取得番號"""
        result = html.xpath('//div[@class="col-md-3 info"]/p/span[@style="color:#CC0000;"]/text()')
        return result[0].strip() if result else ""

    def _get_cover(self, html) -> str:
        """取得封面"""
        result = html.xpath('//a[@class="bigImage"]/@href')
        return result[0] if result else ""

    def _get_actors(self, html) -> list[str]:
        """取得演員列表"""
        result = html.xpath("//div[@id='avatar-waterfall']/a/span/text()")
        return [a.strip() for a in result if a.strip()]

    def _get_release(self, html) -> str:
        """取得發售日期"""
        result = html.xpath(
            '//span[contains(text(),"发行时间:") or contains(text(),"發行日期:") or contains(text(),"発売日:")]/../text()'
        )
        return result[0].strip() if result else ""

    def _get_runtime(self, html) -> str:
        """取得片長"""
        result = html.xpath(
            '//span[contains(text(),"长度:") or contains(text(),"長度:") or contains(text(),"収録時間:")]/../text()'
        )
        if result:
            minutes = re.findall(r"(\d+)", result[0])
            return minutes[0] if minutes else ""
        return ""

    def _get_series(self, html) -> str:
        """取得系列"""
        result = html.xpath('//p/a[contains(@href,"/series/")]/text()')
        return result[0].strip() if result else ""

    def _get_studio(self, html) -> str:
        """取得片商"""
        result = html.xpath('//p/a[contains(@href,"/studio/")]/text()')
        return result[0].strip() if result else ""

    def _get_tags(self, html) -> list[str]:
        """取得標籤"""
        result = html.xpath('//span[@class="genre"]/a/text()')
        return [tag.strip() for tag in result if tag.strip()]

    def _search_and_get_url(self, number: str, base_url: str) -> Optional[tuple[str, str]]:
        """
        搜尋並取得詳情頁 URL

        Returns:
            (detail_url, poster_url) or None
        """
        search_url = f"{base_url}/cn/search/{number}"

        try:
            resp = self._session.get(search_url, timeout=self.config.timeout)
            if resp.status_code != 200:
                return None

            html = etree.fromstring(resp.content, etree.HTMLParser())

            # 找所有搜尋結果
            url_list = html.xpath('//*[@id="waterfall"]/div/a/@href')
            if not url_list:
                return None

            # 比對番號找到正確的結果
            for i, url in enumerate(url_list, 1):
                number_found = html.xpath(
                    f'//*[@id="waterfall"]/div[{i}]/a/div[@class="photo-info"]/span/date[1]/text()'
                )
                if number_found:
                    number_found = number_found[0].strip().upper()
                    # 比對時忽略 -PPV 差異
                    if number.upper().replace("-PPV", "") == number_found.replace("-PPV", ""):
                        detail_url = "https:" + url if url.startswith("//") else url
                        # 取得海報
                        poster = html.xpath(
                            f'//*[@id="waterfall"]/div[{i}]/a/div[@class="photo-frame"]/img/@src'
                        )
                        poster_url = poster[0] if poster else ""
                        return detail_url, poster_url

            return None

        except Exception:
            return None

    def search(self, number: str) -> Optional[Video]:
        """
        搜尋影片資訊

        Args:
            number: 番號（如 012523-001, FC2-1234567）

        Returns:
            Video 物件，找不到返回 None
        """
        # 正規化番號
        number = self.normalize_number(number)

        # 取得可用網域
        base_url = self._get_working_domain()
        if not base_url:
            return None

        try:
            # 搜尋取得詳情頁 URL
            search_result = self._search_and_get_url(number, base_url)
            if not search_result:
                return None

            detail_url, poster_url = search_result

            # 取得詳情頁
            resp = self._session.get(detail_url, timeout=self.config.timeout)
            if resp.status_code != 200:
                return None

            html = etree.fromstring(resp.content, etree.HTMLParser())

            # 取得番號（從頁面取得正確格式）
            web_number = self._get_number(html)

            # 取得標題（移除番號）
            title = self._get_title(html)
            if web_number and title.startswith(web_number):
                title = title[len(web_number):].strip()

            if not title:
                return None

            # 取得各項資訊
            cover_url = self._get_cover(html)
            actors = self._get_actors(html)
            release = self._get_release(html)
            studio = self._get_studio(html)
            series = self._get_series(html)
            tags = self._get_tags(html)

            # 建立女優列表
            actresses = [Actress(name=name) for name in actors]

            video = Video(
                number=web_number or number,
                title=title,
                actresses=actresses,
                date=release,
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
            raise TimeoutError(f"AVSOX request timeout for {number}")
        except Exception:
            return None

    def search_by_keyword(self, keyword: str, limit: int = 20) -> list[Video]:
        """
        關鍵字搜尋

        Args:
            keyword: 搜尋關鍵字
            limit: 最大結果數

        Returns:
            Video 列表
        """
        # AVSOX 搜尋可以用關鍵字
        base_url = self._get_working_domain()
        if not base_url:
            return []

        search_url = f"{base_url}/cn/search/{keyword}"

        try:
            resp = self._session.get(search_url, timeout=self.config.timeout)
            if resp.status_code != 200:
                return []

            html = etree.fromstring(resp.content, etree.HTMLParser())

            # 取得所有結果
            results = []
            url_list = html.xpath('//*[@id="waterfall"]/div/a/@href')

            for i, url in enumerate(url_list[:limit], 1):
                number = html.xpath(
                    f'//*[@id="waterfall"]/div[{i}]/a/div[@class="photo-info"]/span/date[1]/text()'
                )
                if number:
                    video = self.search(number[0])
                    if video:
                        results.append(video)

                # 節流
                rate_limit(self.config.delay)

            return results

        except Exception:
            return []


# 測試用
if __name__ == "__main__":
    scraper = AVSOXScraper()

    print("=== AVSOX 網域測試 ===")
    domain = scraper._get_working_domain()
    if domain:
        print(f"✓ 可用網域: {domain}")
    else:
        print("✗ 無法連接到 AVSOX")
        exit(1)

    print("\n=== API 測試 ===")
    # 測試一個無碼番號
    test_numbers = ["051119-917", "FC2-2101993"]

    for num in test_numbers:
        print(f"\n--- 測試 {num} ---")
        video = scraper.search(num)
        if video:
            print(f"番號: {video.number}")
            print(f"標題: {video.title[:40]}..." if len(video.title) > 40 else f"標題: {video.title}")
            print(f"女優: {[a.name for a in video.actresses]}")
            print(f"片商: {video.maker}")
            print(f"發售: {video.date}")
            print(f"封面: {video.cover_url[:50]}..." if video.cover_url else "封面: (無)")
        else:
            print("✗ 搜尋失敗")
