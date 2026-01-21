"""JAV321 爬蟲"""
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from .base import BaseScraper
from .models import Video, Actress
from .utils import get_html, post_html, rate_limit


class JAV321Scraper(BaseScraper):
    """
    JAV321 爬蟲

    優點：
    - 資料完整
    - 封面完整（非裁切）
    - 穩定性高
    """

    def _get_source_name(self) -> str:
        return "jav321"

    def search(self, number: str) -> Optional[Video]:
        """
        搜尋影片資訊

        Args:
            number: 番號

        Returns:
            Video 物件或 None
        """
        number = self.normalize_number(number)

        if not self.validate_number(number):
            raise ValueError(f"Invalid number format: {number}")

        try:
            # POST 搜尋
            search_url = 'https://www.jav321.com/search'
            html = post_html(search_url, data={'sn': number}, timeout=self.config.timeout)

            if not html:
                return None

            # 檢查是否直接跳轉到詳情頁
            if '/video/' in html and '<h3>' in html:
                detail_html = html
            else:
                # 解析搜尋結果
                soup = BeautifulSoup(html, 'html.parser')
                link = soup.select_one('.row a[href*="/video/"]')

                if not link:
                    return None

                detail_url = urljoin('https://www.jav321.com', str(link.get('href')))
                dh = get_html(detail_url, timeout=self.config.timeout)
                detail_html = dh if dh else ""
                
                if not detail_html:
                    return None

            # 解析詳情頁
            soup = BeautifulSoup(detail_html, 'html.parser')

            # 標題
            title_elem = soup.select_one('h3')
            title = title_elem.get_text(strip=True) if title_elem else ''
            # 移除番號前綴
            title = re.sub(rf'^{re.escape(number)}\s*', '', title, flags=re.IGNORECASE)

            # 封面（轉換成完整版）
            img_elem = soup.select_one('.col-md-3 img')
            cover_url = img_elem.get('src', '') if img_elem else ''
            if cover_url and not str(cover_url).startswith('http'):
                cover_url = urljoin('https://www.jav321.com', str(cover_url))
            # DMM 圖片：ps.jpg → pl.jpg（小圖 → 大圖）
            if cover_url:
                cover_url = str(cover_url).replace('ps.jpg', 'pl.jpg').replace('/pt/', '/pl/')

            # 女優（去重）
            actresses = []
            seen_names = set()
            for a in soup.select('a[href*="/star/"]'):
                name = a.get_text(strip=True)
                if name and name not in seen_names:
                    actresses.append(Actress(name=name))
                    seen_names.add(name)

            # 日期
            date = ''
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', detail_html)
            if date_match:
                date = date_match.group(1)

            # 標籤
            tags = []
            for a in soup.select('a[href*="/genre/"]'):
                tag = a.get_text(strip=True)
                if tag:
                    tags.append(tag)

            if not title and not cover_url:
                return None

            video = Video(
                number=number,
                title=title,
                actresses=actresses,
                date=date,
                maker='',  # JAV321 沒有 maker
                cover_url=str(cover_url) if cover_url else "",
                tags=tags,
                source=self.source_name,
                detail_url=f'https://www.jav321.com/video/{number.lower()}',
            )

            rate_limit(self.config.delay)

            return video

        except Exception as e:
            logger.warning(f"JAV321 search failed for {number}: {e}")
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
        try:
            search_url = 'https://www.jav321.com/search'
            html = post_html(search_url, data={'sn': keyword}, timeout=self.config.timeout)

            if not html:
                return []

            soup = BeautifulSoup(html, 'html.parser')
            results = []

            for item in soup.select('.row .item')[:limit]:
                try:
                    # 提取番號
                    link = item.select_one('a[href*="/video/"]')
                    if not link:
                        continue

                    href = str(link.get('href', ''))
                    number_match = re.search(r'/video/([^/]+)', href)
                    if not number_match:
                        continue

                    number = number_match.group(1).upper()

                    # 遞迴呼叫 search() 取得完整資訊
                    video = self.search(number)
                    if video:
                        results.append(video)

                except Exception as e:
                    logger.debug(f"JAV321 keyword search item failed: {e}")
                    continue

            return results

        except Exception as e:
            logger.warning(f"JAV321 keyword search failed for {keyword}: {e}")
            return []
