"""D2Pass 聯合爬蟲（1Pondo / Caribbeancom / 10musume）"""
import json
import logging
import re
import requests
from typing import Optional

logger = logging.getLogger(__name__)
from .base import BaseScraper
from .models import Video, Actress, ScraperConfig
from .utils import rate_limit


class D2PassScraper(BaseScraper):
    """
    D2Pass 聯合爬蟲 — 共享 JSON API，不同 base URL

    三個站點使用相同 API 路徑格式：
      /dyn/phpauto/movie_details/movie_id/{movie_id}.json

    番號格式偵測：
      DDMMYY-NNN  → Caribbeancom first
      DDMMYY_NNN  → 1Pondo first（3-digit suffix）
      DDMMYY_NN   → 10musume first（2-digit suffix）
    """

    SITES = {
        '1pondo':       'https://www.1pondo.tv/dyn/phpauto/movie_details/movie_id/{id}.json',
        'caribbeancom': 'https://b.caribbeancom.com/dyn/phpauto/movie_details/movie_id/{id}.json',
        '10musume':     'https://www.10musume.com/dyn/phpauto/movie_details/movie_id/{id}.json',
    }

    SITE_DETAIL_URL = {
        '1pondo':       'https://www.1pondo.tv/movies/{id}/',
        'caribbeancom': 'https://www.caribbeancom.com/moviepages/{id}/index.html',
        '10musume':     'https://www.10musume.com/moviepages/{id}/index.html',
    }

    def __init__(self, config: Optional[ScraperConfig] = None):
        super().__init__(config)
        self._session = requests.Session()
        self._session.headers.update({
            'User-Agent': self.config.user_agent,
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'ja-JP,ja;q=0.9',
            'Referer': 'https://www.1pondo.tv/',
        })

    def _get_source_name(self) -> str:
        return "d2pass"

    def normalize_number(self, number: str) -> str:
        """
        Override：D2Pass 番號不做大寫化或加 hyphen 處理。
        日期型番號 (120415_201, 071409-113) 必須原樣傳入 API URL。
        """
        return number.strip()

    def _detect_site_order(self, number: str) -> list[str]:
        """
        根據番號格式決定 site 嘗試順序。

        Returns:
            site key 列表，按嘗試優先順序排列
        """
        if re.match(r'^\d{6}-\d{2,3}$', number):
            # 071409-113 → Caribbeancom（hyphen）
            return ['caribbeancom', '1pondo', '10musume']
        elif re.match(r'^\d{6}_\d{3}$', number):
            # 120415_201 → 1Pondo（underscore, 3-digit）
            return ['1pondo', 'caribbeancom', '10musume']
        elif re.match(r'^\d{6}_\d{2}$', number):
            # 082912_01 → 10musume（underscore, 2-digit）
            return ['10musume', '1pondo', 'caribbeancom']
        else:
            return ['1pondo', 'caribbeancom', '10musume']

    def _fetch_json(self, site: str, movie_id: str) -> Optional[dict]:
        """
        從指定站點取得 JSON 資料。

        Returns:
            解析後的 dict，失敗返回 None
        """
        url = self.SITES[site].format(id=movie_id)
        try:
            resp = self._session.get(url, timeout=self.config.timeout)
            if resp.status_code == 404:
                logger.debug(f"D2Pass {site}: 404 for {movie_id}")
                return None
            if resp.status_code != 200:
                logger.debug(f"D2Pass {site}: HTTP {resp.status_code} for {movie_id}")
                return None
            return resp.json()
        except requests.Timeout:
            logger.debug(f"D2Pass {site}: timeout for {movie_id}")
            return None
        except Exception as e:
            logger.debug(f"D2Pass {site}: error for {movie_id}: {e}")
            return None

    def _parse_json(self, data: dict, site: str, movie_id: str) -> Optional[Video]:
        """
        將 D2Pass JSON 解析為 Video 物件。

        Args:
            data: 解析後的 JSON dict
            site: 站點 key（'1pondo'/'caribbeancom'/'10musume'）
            movie_id: 原始番號（如 '120415_201'）

        Returns:
            Video 物件，解析失敗返回 None
        """
        if not data.get('Status', False):
            return None

        title = data.get('Title') or data.get('TitleEn') or ''
        if not title:
            return None

        # 女優列表（日文名優先）
        actresses_ja = data.get('ActressesJa') or []
        actresses_en = data.get('ActressesEn') or []
        actress_names = actresses_ja or actresses_en

        # 若 ActressesJa/En 均為空，從 ActressesList 取
        if not actress_names:
            actress_list = data.get('ActressesList') or {}
            actress_names = [
                v.get('NameJa') or v.get('NameEn', '')
                for v in actress_list.values()
                if v.get('NameJa') or v.get('NameEn')
            ]

        actresses = [Actress(name=name) for name in actress_names if name]

        # 封面（ThumbHigh 優先，再 MovieThumb）
        cover_url = data.get('ThumbHigh') or data.get('MovieThumb') or ''
        if not cover_url and site == 'caribbeancom':
            cover_url = f'https://www.caribbeancom.com/moviepages/{movie_id}/images/l_l.jpg'
        if not cover_url and site == '1pondo':
            cover_url = f'https://www.1pondo.tv/moviepages/{movie_id}/images/str.jpg'

        # 標籤（日文名優先）
        tags = data.get('UCNAME') or data.get('UCNAMEEn') or []
        # 過濾解析度標籤（如 "720p", "1080p"）
        tags = [t for t in tags if not re.match(r'^\d+p$', t)]

        # 詳情頁 URL
        detail_url = self.SITE_DETAIL_URL[site].format(id=movie_id)

        # AvgRating（Video 選用欄位）
        avg_rating = data.get('AvgRating')
        rating = float(avg_rating) if avg_rating is not None else None

        return Video(
            number=movie_id,
            title=title,
            actresses=actresses,
            date=data.get('Release', ''),
            maker='',  # D2Pass JSON 無片商欄位
            cover_url=cover_url,
            tags=tags,
            source=self.source_name,
            detail_url=detail_url,
            rating=rating,
        )

    def search(self, number: str) -> Optional[Video]:
        """
        搜尋影片資訊。

        Args:
            number: 番號（如 120415_201, 071409-113, 082912_01）

        Returns:
            Video 物件，找不到返回 None
        """
        movie_id = self.normalize_number(number)
        site_order = self._detect_site_order(movie_id)

        for site in site_order:
            try:
                data = self._fetch_json(site, movie_id)
                if data is None:
                    continue

                video = self._parse_json(data, site, movie_id)
                if video is not None:
                    rate_limit(self.config.delay)
                    return video

            except requests.Timeout:
                raise TimeoutError(f"D2Pass request timeout for {number}")
            except Exception as e:
                logger.warning(f"D2Pass search failed for {number} on {site}: {e}")
                continue

        return None

    def search_by_keyword(self, keyword: str, limit: int = 20) -> list[Video]:
        """
        關鍵字搜尋。D2Pass 無關鍵字搜尋 API，直接當番號處理。

        Args:
            keyword: 搜尋關鍵字（會被當作番號處理）
            limit: 最大結果數（D2Pass 只返回 1 筆）

        Returns:
            Video 列表（最多 1 筆）
        """
        result = self.search(keyword)
        return [result] if result else []
