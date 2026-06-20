"""AVSOX 爬蟲"""
import re
import json
import requests
from typing import Optional

from core.logger import get_logger

logger = get_logger(__name__)
from .base import BaseScraper
from .models import Video, Actress, ScraperConfig
from .utils import rate_limit


class CsrfExpired(Exception):
    """API 回 403 或 code != 200 指示 token 失效 → search() 清 cache 重抓 token 重試一次。"""


class AVSOXScraper(BaseScraper):
    """
    AVSOX 爬蟲

    優點：
    - 主要收錄無碼作品
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
            'Accept': 'application/json, text/html',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        })
        self._working_domain: Optional[str] = None
        self._csrf_token: Optional[str] = None

    def _get_source_name(self) -> str:
        return "avsox"

    def _ensure_session(self) -> tuple[Optional[str], Optional[str]]:
        """
        回 (base_url, token)；遍歷 BASE_DOMAINS，逐一 GET {domain}/cn、
        regex 抽 <meta name="csrf-token" content="...">，成功即 cache
        self._working_domain + self._csrf_token 並回傳。
        全失敗回 (None, None)。
        兼任「域名輪替」+「token 抓取」（韌性 #3）。
        """
        # Return cached if available
        if self._working_domain and self._csrf_token:
            return self._working_domain, self._csrf_token

        for domain in self.BASE_DOMAINS:
            try:
                resp = self._session.get(f"{domain}/cn", timeout=self.config.timeout)
                if resp.status_code != 200:
                    continue
                match = re.search(r'<meta\s+name="csrf-token"\s+content="([^"]+)"', resp.text)
                if not match:
                    logger.debug(f"AVSOX domain {domain} returned no csrf-token")
                    continue
                token = match.group(1)
                self._working_domain = domain
                self._csrf_token = token
                return domain, token
            except Exception as e:
                logger.debug(f"AVSOX domain {domain} unavailable: {e}")
                continue

        return None, None

    def _api_post(self, path: str, body) -> dict:
        """
        POST {base}{path}，帶 x-csrf-token / x-requested-with / content-type。
        回 parsed JSON dict。
        HTTP 403 或 json["code"] != 200 → raise CsrfExpired。
        其餘非 200 HTTP → raise Exception。
        """
        base = self._working_domain
        url = f"{base}{path}"
        headers = {
            "x-csrf-token": self._csrf_token,
            "x-requested-with": "XMLHttpRequest",
            "content-type": "application/json",
        }
        resp = self._session.post(url, data=json.dumps(body), headers=headers,
                                  timeout=self.config.timeout)
        if resp.status_code == 403:
            raise CsrfExpired(f"HTTP 403 from {url}")
        if resp.status_code != 200:
            raise Exception(f"AVSOX API {url} returned HTTP {resp.status_code}")
        parsed = resp.json()
        if parsed.get("code") != 200:
            raise CsrfExpired(f"API code={parsed.get('code')} from {url}")
        return parsed

    def _search_movie_id(self, number: str) -> Optional[str]:
        """
        搜尋番號，遍歷 data 用 _number_match 比對，回首個命中 movieId 或 None。
        """
        result = self._api_post("/javu/data/api/search", [{"search": number, "lang": "cn"}, 60, 1])
        for d in result.get("data", []):
            fan_hao = d.get("movieFanHao", "")
            if self._number_match(fan_hao, number):
                return d.get("movieId")
        return None

    def _get_movie(self, movie_id: str) -> dict:
        """
        呼叫 getMovie API，回 data dict。
        """
        result = self._api_post("/javu/data/api/getMovie", [movie_id, "cn"])
        return result["data"]

    def _build_video(self, number: str, base: str, data: dict) -> Video:
        """
        依 Video 欄位 map 組 Video。
        number 用傳入 canonical（非 movieFanHao）。
        None-safe（studio/series 可能 None 或 key 缺席）。
        """
        maker = (data.get("studio") or {}).get("studioName", "") or ""
        series = (data.get("series") or {}).get("seriesName", "") or ""
        actresses = [
            Actress(name=s["starName"])
            for s in data.get("star", [])
            if s.get("starName")
        ]
        tags = [g["genreName"] for g in data.get("genre", []) if g.get("genreName")]
        detail_url = f"{base}/cn/movies/{data['movieId']}"

        return Video(
            number=number,
            title=data.get("title_ja", ""),
            actresses=actresses,
            date=data.get("releaseDate", ""),
            maker=maker,
            cover_url=data.get("posterLarge", ""),
            tags=tags,
            source=self.source_name,
            detail_url=detail_url,
            duration=data.get("length"),
            series=series,
        )

    def _number_match(self, a: str, b: str) -> bool:
        """
        比對兩個番號是否相同（忽略大小寫、-PPV、連字符/底線差異）。
        韌性 #1：吃 062719-001 ↔ 062719_001。
        僅內部比對用，不影響 Video.number 輸出。
        """
        def normalize(s: str) -> str:
            return s.upper().replace("-PPV", "").replace("-", "").replace("_", "")
        return normalize(a) == normalize(b)

    def _lookup(self, number: str, base: str) -> Optional[Video]:
        """核心兩段流程，抽出供重試用。"""
        movie_id = self._search_movie_id(number)
        if not movie_id:
            return None  # 查無此番號（個別下架/未收；None 或空字串皆視為未命中）
        return self._build_video(number, base, self._get_movie(movie_id))

    def search(self, raw: str) -> Optional[Video]:
        """
        搜尋影片資訊

        Args:
            raw: 番號（如 012523-001, FC2-1234567）

        Returns:
            Video 物件，找不到返回 None

        Raises:
            TimeoutError: 請求超時
        """
        number = self.normalize_number(raw)
        try:
            base, _ = self._ensure_session()
            if not base:
                return None  # 全域名連不上（韌性 #4；canary probe False → skip）
            try:
                return self._lookup(number, base)
            except CsrfExpired:  # 韌性 #2：token 失效 → 清 cache 重抓一次重試
                self._working_domain = None
                self._csrf_token = None
                base, _ = self._ensure_session()
                if not base:
                    return None
                return self._lookup(number, base)  # 只重試一次；再 CsrfExpired → 冒到下方 except → None
        except requests.Timeout as e:
            raise TimeoutError(f"AVSOX request timeout for {number}") from e  # 沿用舊行為（canary → skip）
        except Exception as e:
            logger.debug(f"AVSOX search failed for {number}: {e}")
            return None  # 韌性 #4：任何解析/網路爆掉 → None，不崩
        finally:
            rate_limit(self.config.delay)  # 節流照舊

    def search_by_keyword(self, keyword: str, limit: int = 20) -> list[Video]:
        """
        關鍵字搜尋

        ⚠️ DEAD CODE（feature/65 CL-3 / CD-65-7）：AVSOX 不在 FUZZY_SEARCH_SOURCES
        白名單內（core/scrapers/utils.py），模糊鏈 `_fuzzy_search_chain` 永不呼叫此方法。
        無碼模式 × 模糊搜尋已定案維持「回空」，AVSOX keyword 搜刻意不接線（實用性低）。
        保留方法本體但不啟用；勿據此誤以為 AVSOX 有參與模糊搜尋。

        Args:
            keyword: 搜尋關鍵字
            limit: 最大結果數

        Returns:
            Video 列表
        """
        return []


# 測試用
if __name__ == "__main__":
    scraper = AVSOXScraper()

    print("=== AVSOX Session 測試 ===")
    base, token = scraper._ensure_session()
    if base:
        print(f"✓ 可用網域: {base}")
        print(f"✓ CSRF token: {token[:20]}...")
    else:
        print("✗ 無法連接到 AVSOX")
        exit(1)

    print("\n=== API 測試 ===")
    test_numbers = ["051119-917", "FC2-2101993"]

    for num in test_numbers:
        print(f"\n--- 測試 {num} ---")
        video = scraper.search(num)
        if video:
            print(f"番號: {video.number}")
            print(f"標題: {video.title[:40]}..." if len(video.title) > 40 else f"標題: {video.title}")
            print(f"女優: {[a.name for a in video.actresses]}")
            print(f"片商: {video.maker}")
            print(f"系列: {video.series}")
            print(f"發售: {video.date}")
            print(f"片長: {video.duration} 分鐘")
            print(f"標籤: {video.tags}")
            print(f"封面: {video.cover_url[:50]}..." if video.cover_url else "封面: (無)")
            print(f"詳情: {video.detail_url}")
        else:
            print("✗ 搜尋失敗")
