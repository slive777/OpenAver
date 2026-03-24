"""JavBus 爬蟲（自建 requests + BeautifulSoup）"""
import re
from typing import Optional

import requests
from bs4 import BeautifulSoup

from .base import BaseScraper
from .models import Video, Actress
from .utils import rate_limit
from core.logger import get_logger

logger = get_logger(__name__)

FIELD_LABELS = {
    "zh-tw": {
        "number": "識別碼", "date": "發行日期", "duration": "長度",
        "director": "導演", "maker": "製作商", "label": "發行商",
        "series": "系列", "tags": "類別", "actresses": "演員",
    },
    "ja": {
        "number": "品番", "date": "発売日", "duration": "収録時間",
        "director": "監督", "maker": "メーカー", "label": "レーベル",
        "series": "シリーズ", "tags": "ジャンル", "actresses": "出演者",
    },
    "en": {
        "number": "ID", "date": "Release Date", "duration": "Length",
        "director": "Director", "maker": "Studio", "label": "Label",
        "series": "Series", "tags": "Genre", "actresses": "JAV Idols",
    },
}

LANG_PREFIX = {"zh-tw": "", "ja": "/ja", "en": "/en"}


class JavBusScraper(BaseScraper):
    """
    JavBus 爬蟲（自建 requests + BeautifulSoup）

    優點：
    - 封面無浮水印
    - 不依賴第三方 jvav 套件
    - 支援多語言（zh-tw / ja / en）

    注意：
    - 封面只有右半邊（裁切版）
    """

    BASE_URL = "https://www.javbus.com"

    def __init__(self, config=None, lang: str = "zh-tw"):
        super().__init__(config)
        self.lang = lang
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/17.5 Safari/605.1.15"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh-Hans;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        })

    def _get_source_name(self) -> str:
        return "javbus"

    def _get_lang_prefix(self) -> str:
        return LANG_PREFIX.get(self.lang, "")

    def _get_labels(self) -> dict:
        return FIELD_LABELS.get(self.lang, FIELD_LABELS["zh-tw"])

    def search(self, number: str) -> Optional[Video]:
        """
        搜尋影片資訊

        Args:
            number: 番號（如 SNOS-143）

        Returns:
            Video 物件或 None

        Raises:
            ValueError: 番號格式錯誤
            TimeoutError: 請求超時
        """
        number = self.normalize_number(number)

        if not self.validate_number(number):
            raise ValueError(f"Invalid number format: {number}")

        prefix = self._get_lang_prefix()
        url = f"{self.BASE_URL}{prefix}/{number}"

        try:
            resp = self._session.get(url, timeout=self.config.timeout)
        except requests.Timeout:
            raise TimeoutError(f"Request timed out for {number}")

        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        return self._parse_detail_page(soup, number, url)

    def _parse_detail_page(self, soup, number: str, detail_url: str) -> Optional[Video]:
        """解析詳情頁 HTML，回傳 Video 物件。"""
        # 驗證是詳情頁（必須有 info 區塊）
        info = soup.find(class_="col-md-3 info")
        if not info:
            return None

        labels = self._get_labels()

        # Title — 優先用 h3，次用 bigImage img title
        title_elem = soup.find("h3")
        title = title_elem.get_text(strip=True) if title_elem else ""
        if not title:
            big_image = soup.find(class_="bigImage")
            if big_image:
                img = big_image.find("img", {"title": True})
                if img:
                    title = img.get("title", "")

        # Cover URL
        big_image = soup.find(class_="bigImage")
        cover_url = ""
        if big_image:
            cover_url = big_image.get("href", "")
            if cover_url and not cover_url.startswith("http"):
                cover_url = self.BASE_URL + cover_url

        # Parse info <p> tags
        paragraphs = info.find_all("p")
        parsed = self._parse_info_paragraphs(paragraphs, labels)

        # Duration → int
        duration = None
        if parsed.get("duration"):
            m = re.search(r"(\d+)", parsed["duration"])
            if m:
                duration = int(m.group(1))

        # Actresses — 去重
        actresses = []
        seen_names: set[str] = set()
        for actress_name in parsed.get("actresses", []):
            if actress_name and actress_name not in seen_names:
                seen_names.add(actress_name)
                actresses.append(Actress(name=actress_name))

        # Sample images
        sample_section = (
            soup.find(id="sample-waterfall")
            or soup.find(class_="sample-waterfall")
        )
        sample_images = []
        if sample_section:
            for a in sample_section.find_all("a", href=True):
                img_url = a["href"]
                if not img_url.startswith("http"):
                    img_url = self.BASE_URL + img_url
                sample_images.append(img_url)

        video = Video(
            number=number,
            title=title,
            actresses=actresses,
            date=parsed.get("date", ""),
            maker=parsed.get("maker", ""),
            cover_url=cover_url,
            tags=parsed.get("tags", []),
            source=self.source_name,
            detail_url=detail_url,
            director=parsed.get("director", ""),
            duration=duration,
            label=parsed.get("label", ""),
            series=parsed.get("series", ""),
            sample_images=sample_images,
        )

        rate_limit(self.config.delay)
        return video

    def _parse_info_paragraphs(self, paragraphs, labels: dict) -> dict:
        """
        解析 info 區塊的 <p> 標籤，用欄位名 mapping 辨識。

        Returns:
            dict 包含 date, duration, director, maker, label, series, tags, actresses
        """
        result: dict = {
            "date": "", "duration": "", "director": "", "maker": "",
            "label": "", "series": "", "tags": [], "actresses": [],
        }

        i = 0
        while i < len(paragraphs):
            p = paragraphs[i]
            text = p.get_text(strip=True)

            # 單值欄位：找到 label 後，取 <a> 文字或剝除 label 前綴
            for field in ("date", "director", "maker", "label", "series"):
                lbl = labels[field]
                if lbl in text:
                    a = p.find("a")
                    if a:
                        result[field] = a.get_text(strip=True)
                    else:
                        value = text
                        for char in (lbl, ":", "："):
                            value = value.replace(char, "")
                        result[field] = value.strip()
                    break

            # Duration — 保留整段文字（供後續 regex 提取數字）
            if labels["duration"] in text:
                result["duration"] = text

            # Tags — 在同 <p> 或下一個 <p> 找 <a>
            if labels["tags"] in text:
                tag_links = p.find_all("a")
                if not tag_links and i + 1 < len(paragraphs):
                    tag_links = paragraphs[i + 1].find_all("a")
                    i += 1  # skip next
                result["tags"] = [
                    a.get_text(strip=True) for a in tag_links
                    if a.get_text(strip=True)
                ]

            # Actresses — 同 tags，fallback 到下一個 <p>
            if labels["actresses"] in text:
                actress_links = p.find_all("a")
                if not actress_links and i + 1 < len(paragraphs):
                    actress_links = paragraphs[i + 1].find_all("a")
                    i += 1
                result["actresses"] = [
                    a.get_text(strip=True) for a in actress_links
                    if a.get_text(strip=True)
                ]

            i += 1

        return result

    def _build_search_url(self, keyword: str, page: int = 1, search_type: int = 0) -> str:
        """
        組建搜尋 URL。

        URL 格式：
          第 1 頁：/search/{keyword}
          第 N 頁：/search/{keyword}/{N}
          前綴搜尋：上述 URL 後加 &type=1
        """
        prefix = self._get_lang_prefix()
        base = f"{self.BASE_URL}{prefix}/search/{keyword}"
        if page > 1:
            base += f"/{page}"
        if search_type > 0:
            base += f"&type={search_type}"
        return base

    def _parse_search_ids(self, soup) -> list[str]:
        """從搜尋結果頁解析番號列表。"""
        ids = []
        waterfall = soup.find(id="waterfall")
        if not waterfall:
            return []
        for card in waterfall.find_all("a", class_="movie-box"):
            # 優先從 <date> 元素取番號（第一個 date 是番號，第二個是日期）
            dates = card.find_all("date")
            if dates:
                number = dates[0].get_text(strip=True)
                if number:
                    ids.append(number)
            else:
                # fallback：從 href 最後一段提取
                href = card.get("href", "")
                if href:
                    number = href.rstrip("/").split("/")[-1]
                    if number:
                        ids.append(number)
        return ids

    def get_ids_from_search(self, keyword: str, page: int = 1, search_type: int = 0) -> list[str]:
        """
        輕量版搜尋：只回傳番號列表，不 fetch 每筆詳情。

        Args:
            keyword: 搜尋關鍵字或前綴
            page: 頁碼（從 1 開始）
            search_type: 0=一般搜尋，1=前綴搜尋（&type=1）

        Returns:
            番號列表（list[str]）

        Raises:
            TimeoutError: 請求超時
        """
        url = self._build_search_url(keyword, page, search_type)
        try:
            resp = self._session.get(url, timeout=self.config.timeout)
        except requests.Timeout:
            raise TimeoutError(f"Search request timed out for keyword: {keyword}")
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        return self._parse_search_ids(soup)

    def _fetch_by_id(self, id_str: str) -> Optional[Video]:
        """直接用 ID 取得影片資訊（繞過 validate_number，支援 variant ID 如 SONE-001_2026-03-20）"""
        prefix = self._get_lang_prefix()
        url = f"{self.BASE_URL}{prefix}/{id_str}"

        try:
            resp = self._session.get(url, timeout=self.config.timeout)
        except requests.Timeout:
            raise TimeoutError(f"Request timed out for {id_str}")

        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        # 用 id_str 的 base part（去掉日期後綴）作為 number
        base_number = id_str.split('_')[0]
        return self._parse_detail_page(soup, base_number, url)

    def search_by_keyword(self, keyword: str, limit: int = 20, page: int = 1) -> list[Video]:
        """
        關鍵字搜尋，回傳 Video 列表。

        先呼叫 get_ids_from_search 取番號列表，再逐一呼叫 search() 取完整詳情。
        單筆 search 失敗（ValueError / TimeoutError）時跳過，不中斷整體。

        Args:
            keyword: 搜尋關鍵字
            limit: 最大結果數
            page: 搜尋結果頁碼

        Returns:
            Video 列表
        """
        ids = self.get_ids_from_search(keyword, page=page)
        results: list[Video] = []
        for num_id in ids[:limit]:
            try:
                video = self.search(num_id)
                if video:
                    results.append(video)
            except (ValueError, TimeoutError):
                continue
        return results
