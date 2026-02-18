"""DMM 爬蟲（官方 GraphQL API + 動態學習）"""
import json
import logging
import re
import requests
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)
from .base import BaseScraper
from .models import Video, Actress, ScraperConfig
from .utils import rate_limit


# 快取檔案路徑（專案根目錄）
PROJECT_ROOT = Path(__file__).parent.parent.parent
CACHE_FILE = PROJECT_ROOT / "dmm_content_ids.json"      # 完整番號 → content_id
PREFIX_FILE = PROJECT_ROOT / "dmm_prefix_hints.json"    # 番號前綴 → DMM 前綴


class DMMScraper(BaseScraper):
    """
    DMM 爬蟲（使用官方 GraphQL API）

    優點：
    - 官方資料來源，資料最準確
    - 封面無浮水印、高畫質
    - 有完整簡介、導演資訊

    特點：
    - 雙層快取：前綴映射 + content_id 快取
    - 動態學習：發現新前綴會自動記錄
    - 無需預設映射表，完全由用戶運行時生成

    注意：
    - 需要日本 IP（VPN）
    - API 可能隨時變動（非公開 API）
    """

    API_URL = "https://api.video.dmm.co.jp/graphql"

    DETAIL_QUERY = """
        query ContentPageData($id: ID!) {
            ppvContent(id: $id) {
                id
                title
                description
                packageImage { largeUrl }
                makerReleasedAt
                duration
                actresses { name }
                directors { name }
                series { name }
                maker { name }
                makerContentId
            }
        }
    """

    SEARCH_QUERY = """
        query AvSearch($limit: Int!, $sort: ContentSearchPPVSort!, $queryWord: String) {
            legacySearchPPV(limit: $limit, sort: $sort, queryWord: $queryWord) {
                result { contents { id } }
            }
        }
    """

    def __init__(self, config: Optional[ScraperConfig] = None):
        super().__init__(config)
        self._session = requests.Session()
        self._session.headers.update({
            'User-Agent': self.config.user_agent,
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        })
        if self.config.proxy_url:
            self._session.proxies = {
                'http': self.config.proxy_url,
                'https': self.config.proxy_url,
            }

    def _get_source_name(self) -> str:
        return "dmm"

    # ========== 快取管理 ==========

    def _load_json(self, path: Path) -> dict:
        """讀取 JSON，檔案不存在返回空 dict"""
        if path.exists():
            try:
                return json.loads(path.read_text(encoding='utf-8'))
            except (json.JSONDecodeError, IOError):
                return {}
        return {}

    def _save_json(self, path: Path, data: dict):
        """儲存 JSON"""
        try:
            path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )
        except IOError:
            pass

    def _load_cache(self) -> dict:
        """讀取 content_id 快取"""
        return self._load_json(CACHE_FILE)

    def _save_cache(self, number: str, content_id: str):
        """儲存到 content_id 快取"""
        cache = self._load_cache()
        cache[number.upper()] = content_id
        self._save_json(CACHE_FILE, cache)

    def _load_prefix_hints(self) -> dict:
        """讀取前綴映射"""
        return self._load_json(PREFIX_FILE)

    def _save_prefix_hint(self, prefix: str, dmm_prefix: str):
        """儲存新學習的前綴映射"""
        hints = self._load_prefix_hints()
        hints[prefix.lower()] = dmm_prefix
        self._save_json(PREFIX_FILE, hints)

    # ========== content_id 轉換 ==========

    def _parse_number(self, number: str) -> tuple[str, str]:
        """
        解析番號，返回 (前綴, 數字)

        Examples:
            SONE-205 → ("sone", "205")
            STARS-804 → ("stars", "804")
        """
        number = number.upper().strip()
        match = re.match(r'^([A-Z]+)-?(\d+)$', number)
        if match:
            return match.group(1).lower(), match.group(2)
        return "", ""

    def _convert_with_hints(self, number: str) -> str:
        """
        用前綴映射轉換番號

        Examples:
            SONE-205 + hints={} → sone00205
            STARS-804 + hints={"stars": "1"} → 1stars00804
        """
        prefix, num = self._parse_number(number)
        if not prefix or not num:
            return ""

        # 數字補零到 5 位
        num_padded = num.zfill(5)

        # 查前綴映射
        hints = self._load_prefix_hints()
        dmm_prefix = hints.get(prefix, "")

        return f"{dmm_prefix}{prefix}{num_padded}"

    def _learn_prefix(self, number: str, content_id: str):
        """
        從成功的 content_id 學習前綴映射

        Examples:
            number=STARS-804, content_id=1stars00804
            → 學習到 stars → "1"
        """
        prefix, _ = self._parse_number(number)
        if not prefix:
            return

        # content_id 格式：{dmm_prefix}{prefix}{num_padded}
        # 例如：1stars00804
        # 找出 dmm_prefix
        idx = content_id.lower().find(prefix)
        if idx > 0:
            dmm_prefix = content_id[:idx]
            # 儲存學習到的映射
            self._save_prefix_hint(prefix, dmm_prefix)

    def _search_content_id(self, number: str) -> Optional[str]:
        """
        用搜索 API 查找正確的 content_id（MDCX 方法）
        """
        query_word = number.upper().replace('-', '')
        prefix, _ = self._parse_number(number)

        try:
            payload = {
                'query': self.SEARCH_QUERY,
                'variables': {
                    'limit': 5,
                    'sort': 'RELEASE_DATE',
                    'queryWord': query_word
                }
            }
            resp = self._session.post(self.API_URL, json=payload, timeout=10)

            if resp.status_code != 200:
                return None

            data = resp.json()
            if not data.get('data') or not data['data'].get('legacySearchPPV'):
                return None

            contents = data['data']['legacySearchPPV']['result']['contents']
            if not contents:
                return None

            # 找包含番號前綴的結果
            for content in contents:
                cid = content['id']
                if prefix in cid.lower():
                    return cid

            # 沒找到匹配的，返回第一個
            return contents[0]['id']

        except Exception:
            return None

    def _fetch_by_id(self, content_id: str) -> Optional[Video]:
        """用 content_id 取得影片詳細資訊"""
        if not content_id:
            return None

        try:
            payload = {
                'query': self.DETAIL_QUERY,
                'variables': {'id': content_id}
            }

            response = self._session.post(
                self.API_URL,
                json=payload,
                timeout=self.config.timeout
            )

            if response.status_code != 200:
                return None

            data = response.json()

            if not data.get('data') or not data['data'].get('ppvContent'):
                return None

            item = data['data']['ppvContent']

            actresses = [
                Actress(name=a['name'])
                for a in item.get('actresses', [])
            ]

            release_date = item.get('makerReleasedAt', '')
            if release_date and 'T' in release_date:
                release_date = release_date.split('T')[0]

            video = Video(
                number=item.get('makerContentId', ''),
                title=item.get('title', ''),
                actresses=actresses,
                date=release_date,
                maker=item.get('maker', {}).get('name', ''),
                cover_url=item.get('packageImage', {}).get('largeUrl', ''),
                tags=[],
                source=self.source_name,
                detail_url=f"https://www.dmm.co.jp/digital/videoa/-/detail/=/cid={content_id}/",
            )

            return video

        except requests.Timeout:
            raise TimeoutError(f"DMM API timeout for {content_id}")
        except Exception:
            return None

    # ========== 主要搜尋方法 ==========

    def search(self, number: str) -> Optional[Video]:
        """
        搜尋影片資訊

        流程：
        1. 查快取 → 有就直接用（最快）
        2. 用前綴映射轉換 → 嘗試查詢（快）
        3. 搜索 API 發現 → 學習前綴（慢，但只需一次）
        4. 都失敗 → 返回 None

        Args:
            number: 番號（如 SONE-205）

        Returns:
            Video 物件，找不到返回 None
        """
        # DMM 需要 proxy（日本 IP），無 proxy 時直接跳過
        if not self.config.proxy_url:
            return None

        # 正規化番號
        number = self.normalize_number(number)
        number_upper = number.upper()

        # 不支援 FC2
        if 'FC2' in number_upper:
            return None

        # 1. 查快取（最快）
        cache = self._load_cache()
        if number_upper in cache:
            cached_cid = cache[number_upper]
            result = self._fetch_by_id(cached_cid)
            if result:
                rate_limit(self.config.delay)
                return result

        # 2. 用前綴映射轉換（快）
        converted_cid = self._convert_with_hints(number)
        if converted_cid:
            result = self._fetch_by_id(converted_cid)
            if result:
                self._save_cache(number, converted_cid)
                rate_limit(self.config.delay)
                return result

        # 3. 搜索 API 發現（慢，但會學習）
        discovered_cid = self._search_content_id(number)
        if discovered_cid:
            result = self._fetch_by_id(discovered_cid)
            if result:
                self._save_cache(number, discovered_cid)
                self._learn_prefix(number, discovered_cid)  # 學習新前綴
                rate_limit(self.config.delay)
                return result

        # 4. 完全失敗
        return None

    def search_by_keyword(self, keyword: str, limit: int = 20) -> list[Video]:
        """關鍵字搜尋（目前僅支援番號）"""
        result = self.search(keyword)
        return [result] if result else []
