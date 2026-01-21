"""JavDB 爬蟲"""
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)
from urllib.parse import quote
from bs4 import BeautifulSoup
from .base import BaseScraper
from .models import Video, Actress
from .utils import rate_limit

# 嘗試載入 curl_cffi
try:
    from curl_cffi import requests as curl_requests
    CURL_CFFI_AVAILABLE = True
except ImportError:
    CURL_CFFI_AVAILABLE = False


class JavDBScraper(BaseScraper):
    """
    JavDB 爬蟲

    優點：
    - 資料最完整（有 maker）
    - Tag 豐富

    缺點：
    - 封面有浮水印
    - 需 curl_cffi 偽造 TLS 指紋
    """

    def _get_source_name(self) -> str:
        return "javdb"

    def _get_html(self, url: str) -> Optional[str]:
        """使用 curl_cffi 發送請求（偽造 Chrome TLS 指紋）"""
        if not CURL_CFFI_AVAILABLE:
            return None

        try:
            response = curl_requests.get(
                url,
                impersonate="chrome120",
                headers={
                    "User-Agent": self.config.user_agent,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "zh-TW,zh;q=0.9,ja;q=0.8,en;q=0.7",
                    "Referer": "https://javdb.com/",
                },
                timeout=30
            )

            if response.status_code == 200:
                return str(response.text)
        except Exception as e:
            logger.debug(f"JavDB request failed for {url}: {e}")

        return None

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
            # 先搜尋取得列表
            search_url = f"https://javdb.com/search?q={quote(number)}&f=all"
            html = self._get_html(search_url)

            if not html:
                return None

            soup = BeautifulSoup(html, 'html.parser')

            # 找到精確匹配的番號
            detail_path = None
            number_upper = number.upper().replace('-', '')

            for item in soup.select('.movie-list .item')[:5]:
                uid_elem = item.select_one('.video-title strong')
                uid = uid_elem.text.strip() if uid_elem else ''
                uid_normalized = uid.upper().replace('-', '')

                if uid_normalized == number_upper:
                    link_elem = item.select_one('a[href^="/v/"]')
                    if link_elem:
                        detail_path = str(link_elem['href'])
                        break

            if not detail_path:
                return None

            # 獲取詳情頁
            detail_url = f"https://javdb.com{detail_path}"
            detail_html = str(self._get_html(detail_url) or "")

            if not detail_html:
                return None

            soup = BeautifulSoup(detail_html, 'html.parser')

            # 標題
            title_elem = soup.select_one('.video-detail h2, .title.is-4')
            title = title_elem.text.strip() if title_elem else ''

            # 封面
            cover_elem = soup.select_one('.video-cover img, .column-video-cover img')
            cover_url = str(cover_elem.get('src', '')) if cover_elem else ''

            # 解析資訊面板
            date = ''
            maker = ''
            actresses = []
            tags = []

            for panel in soup.select('.panel-block'):
                label = panel.select_one('strong')
                value = panel.select_one('.value')

                if not label:
                    continue

                label_text = label.text.strip()

                # 日期
                if '日期' in label_text and value:
                    date = value.text.strip()

                # 片商
                if '片商' in label_text or '製作' in label_text or '發行' in label_text:
                    if value:
                        maker = value.text.strip()

                # 演員（只抓女優）
                if '演員' in label_text:
                    for a in panel.select('a'):
                        name = a.text.strip()
                        if not name:
                            continue

                        # 檢查性別標記
                        next_elem = a.find_next_sibling()
                        
                        # 跳過男優
                        classes: list[str] = []
                        if next_elem and hasattr(next_elem, 'get'):
                            cls_val = next_elem.get('class')
                            if isinstance(cls_val, list):
                                classes = [str(c) for c in cls_val]
                            else:
                                classes = [str(cls_val)] if cls_val else []
                        
                        if 'male' in classes and 'female' not in classes:
                            continue

                        actresses.append(Actress(name=name))

                # 標籤
                if '類別' in label_text:
                    tag_elems = panel.select('a')
                    tags = [t.text.strip() for t in tag_elems if t.text.strip()]

            if not title and not cover_url:
                return None

            # DMM 圖片：ps.jpg → pl.jpg（小圖 → 大圖）
            if cover_url:
                cover_url = str(cover_url).replace('ps.jpg', 'pl.jpg').replace('/pt/', '/pl/')

            video = Video(
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

            rate_limit(self.config.delay)

            return video

        except Exception as e:
            logger.warning(f"JavDB search failed for {number}: {e}")
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
            url = f"https://javdb.com/search?q={quote(keyword)}&f=all"
            html = self._get_html(url)

            if not html:
                return []

            soup = BeautifulSoup(html, 'html.parser')
            results = []

            for item in soup.select('.movie-list .item')[:limit]:
                try:
                    uid_elem = item.select_one('.video-title strong')
                    number = uid_elem.text.strip() if uid_elem else ''

                    if not number:
                        continue

                    # 遞迴呼叫 search() 取得完整資訊
                    video = self.search(number)
                    if video:
                        results.append(video)

                except Exception as e:
                    logger.debug(f"JavDB keyword search item failed: {e}")
                    continue

            return results

        except Exception as e:
            logger.warning(f"JavDB keyword search failed for {keyword}: {e}")
            return []
