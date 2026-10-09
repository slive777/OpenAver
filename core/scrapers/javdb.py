"""JavDB 爬蟲"""
import locale
import re
import sys
from typing import Optional

from core.logger import get_logger

logger = get_logger(__name__)
from urllib.parse import quote, urlparse
from urllib.request import getproxies, proxy_bypass
from bs4 import BeautifulSoup
from .base import BaseScraper
from .errors import SourceBlocked, SourceUnreachable
from .models import Video, Actress
from .utils import rate_limit, strip_number_prefix
from . import javdb_api
from core.source_probe import ProbePlan, ProbeTarget

# 嘗試載入 curl_cffi
# CURL_CFFI_IMPORT_ERROR 先在頂層初始化：正常 import 成功時此變數仍須存在，否則單獨
# patch CURL_CFFI_AVAILABLE=False 的測試會 NameError（spec-97 Codex P2）。
CURL_CFFI_IMPORT_ERROR: Optional[BaseException] = None
try:
    from curl_cffi import requests as curl_requests, CurlOpt
    import certifi
    CURL_CFFI_AVAILABLE = True
except ImportError as e:
    CURL_CFFI_AVAILABLE = False
    CURL_CFFI_IMPORT_ERROR = e

# curl_cffi 不可用時 _get_html 首次呼叫發一次 warning（module flag 一次性，spec-97 CD-97-5）。
# 歷史教訓：released 版 dist-info 被剝除 → curl_cffi PackageNotFoundError → 這裡靜默
# 吞掉 → javdb 瞬回無結果、零 log。補此可觀測性（不改降級行為本身）。
_warned = False

_UNSET = object()
_cainfo_override = _UNSET   # _UNSET=未算 / None=no-op 或降級 / bytes=CAINFO override
_ca_warned = False


def _parse_rating_votes(text: str) -> tuple[Optional[float], Optional[int]]:
    """'4.58分, 由48人評價' → (4.58, 48)。抽不到的那一半回 None，不拋。"""
    rating: Optional[float] = None
    votes: Optional[int] = None
    m = re.search(r'([0-9.]+)\s*分', text)
    if m:
        rating = float(m.group(1))
    vm = re.search(r'由(\d+)人', text)
    if vm:
        votes = int(vm.group(1))
    return rating, votes


def _parse_panel_blocks(soup: BeautifulSoup) -> dict:
    """解析詳情頁 `.panel-block`，回傳 date/maker/label/director/series/duration/actresses/tags/rating/votes。"""
    date = ''
    maker = ''
    label = ''
    director = ''
    series = ''
    duration: Optional[int] = None
    actresses: list[Actress] = []
    tags: list[str] = []
    rating: Optional[float] = None
    votes: Optional[int] = None

    for panel in soup.select('.panel-block'):
        label_elem = panel.select_one('strong')
        value = panel.select_one('.value')

        if not label_elem:
            continue

        label_text = label_elem.text.strip()

        # 日期
        if '日期' in label_text and value:
            date = value.text.strip()

        # 片商（排除「發行日期」；「發行」另走 label，避免覆蓋片商）
        if ('片商' in label_text or '製作' in label_text) and '日期' not in label_text:
            if value:
                maker = value.text.strip()

        # 發行 → label（同樣排除「發行日期」）
        if '發行' in label_text and '日期' not in label_text:
            if value:
                label = value.text.strip()

        # 時長 → duration（分鐘）；只抽數字，不比對「分鍾」
        if '時長' in label_text and value:
            dm = re.search(r'(\d+)', value.text)
            if dm:
                duration = int(dm.group(1))

        # 導演
        if '導演' in label_text and value:
            director = value.text.strip()

        # 系列
        if '系列' in label_text and value:
            series = value.text.strip()

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

        # 評分（D8：0–5 真實用戶評分，`分` 錨定；javdb 無簡介）
        if '評分' in label_text and value:
            rating, votes = _parse_rating_votes(value.text)

    return {
        'date': date,
        'maker': maker,
        'label': label,
        'director': director,
        'series': series,
        'duration': duration,
        'actresses': actresses,
        'tags': tags,
        'rating': rating,
        'votes': votes,
    }


def _resolve_proxies(url: str) -> Optional[dict]:
    """Resolve system proxy for curl_cffi. None = omit proxies kwarg (same as pre-F1).

    No cache: user may toggle system proxy mid-session (CD-132a-2).
    """
    try:
        host = urlparse(url).hostname
        if host and proxy_bypass(host):
            return None
    except Exception as e:
        logger.debug("javdb: proxy_bypass 檢查失敗，視為不繞道: %s", e)
    try:
        raw = getproxies() or {}
        filtered = {k: v for k, v in raw.items() if k in ("http", "https")}
        return filtered or None
    except Exception:
        return None


def _cainfo_override_bytes():
    """Windows + 非 ASCII certifi 路徑 → 回 ACP bytes（給 curl_options CAINFO）；否則 None。
    算一次快取；併發安全＝算完才 publish（CD-98-6）。只在 CURL_CFFI_AVAILABLE 時被 _get_html 呼叫。"""
    global _cainfo_override, _ca_warned
    if _cainfo_override is not _UNSET:
        return _cainfo_override
    result = None                                   # 區域變數，計算期間不碰全域（CD-98-6）
    ca = certifi.where()
    if sys.platform == "win32" and not ca.isascii():
        try:
            result = ca.encode(locale.getencoding(), errors="strict")   # CD-98-1
        except UnicodeEncodeError as e:                                  # CD-98-3
            if not _ca_warned:
                _ca_warned = True
                logger.warning("javdb: CA 憑證路徑含當前 code page 無法表示的字元，"
                               "TLS 可能失敗（請改用純英文安裝路徑）: %s", e)
            # 不覆寫、退回 curl_cffi 原行為
    _cainfo_override = result                        # 最後一步才 publish（避免併發讀半成品）
    return result


class JavDBScraper(BaseScraper):
    """
    JavDB 爬蟲

    精準番號搜尋優先走資料介面，失敗或查無時自動退回網頁解析。

    優點：
    - 資料最完整（有 maker）
    - Tag 豐富
    - 資料介面路徑封面無浮水印（網頁備援路徑封面有 javdb.com 浮水印）

    缺點：
    - 需 curl_cffi 偽造 TLS 指紋（僅網頁備援路徑）
    """

    SAMPLE_NUMBER = "SONE-205"

    def _get_source_name(self) -> str:
        return "javdb"

    def _api_sender(self, host, path, timeout):
        def send():
            return javdb_api._signed_get(host, path, javdb_api.probe_query(self.SAMPLE_NUMBER), timeout=timeout, stream=True, **self._proxy_kwargs())
        return send

    def probe_plan(self, timeout):
        """測試連線：只測 App 資料通道（兩個鏡像 host，任一通即可）；不測網頁備援。"""
        path = javdb_api._SEARCH_PATH
        targets = [
            ProbeTarget(host.split('//', 1)[1], self._api_sender(host, path, timeout), check=javdb_api.envelope_ok, read='full_capped')
            for host in javdb_api._API_HOSTS
        ]
        return ProbePlan(targets, mode='any')

    def _get_html(self, url: str) -> Optional[str]:
        """使用 curl_cffi 發送請求（偽造 Chrome TLS 指紋）"""
        if not CURL_CFFI_AVAILABLE:
            global _warned
            if not _warned:
                _warned = True
                if CURL_CFFI_IMPORT_ERROR is not None:
                    logger.warning("javdb 已停用：curl_cffi 不可用: %s", CURL_CFFI_IMPORT_ERROR)
                else:
                    logger.warning("javdb 已停用：curl_cffi 不可用")
            return None

        _ca = _cainfo_override_bytes()
        extra = {"curl_options": {CurlOpt.CAINFO: _ca}} if _ca is not None else {}
        _pk = self._proxy_kwargs()
        _proxies = _pk.get('proxies') or _resolve_proxies(url)

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
                timeout=30,
                **extra,
                **({"proxies": _proxies} if _proxies else {}),
            )

            if response.status_code == 200:
                text = str(response.text)
                if len(text) < 20000:
                    text_lower = text.lower()
                    if (
                        "cf-browser-verification" in text_lower
                        or "just a moment" in text_lower
                        or "challenge-platform" in text_lower
                    ):
                        logger.warning("JavDB blocked (Cloudflare challenge) for %s", url)
                        raise SourceBlocked(f"javdb: Cloudflare challenge detected for {url}")
                return text

            if response.status_code in (403, 429, 503):
                logger.warning("JavDB blocked (%s) for %s", response.status_code, url)
                raise SourceBlocked(
                    f"javdb: HTTP {response.status_code} for {url}"
                )

            logger.warning("JavDB non-200 for %s: %s", url, response.status_code)
        except (SourceUnreachable, SourceBlocked):
            raise
        except Exception as e:
            logger.warning(f"JavDB request failed for {url}: {e}")
            raise SourceUnreachable(f"javdb: {e}") from e

        return None

    def search_via_api(self, number: str) -> Optional[Video]:
        """走 App 資料介面。呼叫端必須傳入已正規化的番號。

        查無回 None；傳輸失敗照 B6 拋 SourceUnreachable / SourceBlocked
        （由 search() 攔下並降級，見 CD-132b-5）。
        """
        return javdb_api.fetch_video(number, **self._proxy_kwargs())

    def search_via_html(self, number: str) -> Optional[Video]:
        """走網頁解析。呼叫端必須傳入已正規化的番號。

        查無回 None；傳輸失敗照 132a 契約拋 SourceUnreachable / SourceBlocked。
        """
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

            # 標題：優先取 strong.current-title，避免混入「顯示原標題」按鈕與隱藏原文
            title_elem = soup.select_one('.video-detail h2, .title.is-4')
            title = ''
            if title_elem:
                current = title_elem.select_one('strong.current-title')
                if current is not None:
                    title = current.get_text(separator=' ', strip=True)
                else:
                    title = title_elem.get_text(separator=' ', strip=True)
            title = strip_number_prefix(title, number)

            # 封面
            cover_elem = soup.select_one('.video-cover img, .column-video-cover img')
            cover_url = str(cover_elem.get('src', '')) if cover_elem else ''

            # 劇照：必須限定 .preview-images，否則會混進「相關影片」封面
            sample_images = [
                str(a['href'])
                for a in soup.select('.preview-images a.tile-item')
                if a.get('href')
            ]

            # 解析資訊面板（抽出以壓低 search() 複雜度，見 TASK §7）
            panel = _parse_panel_blocks(soup)

            if not title and not cover_url:
                return None

            # DMM 圖片：ps.jpg → pl.jpg（小圖 → 大圖）
            if cover_url:
                cover_url = str(cover_url).replace('ps.jpg', 'pl.jpg').replace('/pt/', '/pl/')

            video = Video(
                number=number,
                title=title,
                actresses=panel['actresses'],
                date=panel['date'],
                maker=panel['maker'],
                cover_url=cover_url,
                tags=panel['tags'],
                rating=panel['rating'],
                votes=panel['votes'],
                director=panel['director'],
                duration=panel['duration'],
                label=panel['label'],
                series=panel['series'],
                sample_images=sample_images,
                source=self.source_name,
                detail_url=detail_url,
            )

            return video

        except (SourceUnreachable, SourceBlocked):
            raise
        except Exception as e:
            logger.warning(f"JavDB search failed for {number}: {e}")
            return None

    def search(self, number: str) -> Optional[Video]:
        """
        搜尋影片資訊。精準番號搜尋優先走資料介面，失敗或查無時自動退回網頁解析。

        Args:
            number: 番號

        Returns:
            Video 物件或 None
        """
        return self._search_number(number, allow_api=True)

    def _search_number(self, number: str, *, allow_api: bool) -> Optional[Video]:
        """`search()` 與 `search_by_keyword()` 共用的番號查詢本體。

        `allow_api=False` ＝ 只走 HTML，給關鍵字搜尋用。
        **spec-132 Non-Goals：關鍵字搜尋維持現行 HTML 做法。** plan 的 CD-132b-12
        以為「`search_by_keyword()` 一個字都不動」就等於這件事，但那支是逐筆呼叫
        `search()` 取詳情的——`search()` 改成 API 優先之後，一次關鍵字搜尋會對資料介面
        打最多 20 次，而那正是我們想省著用、且精準番號搜尋唯一依賴的那條路。

        正規化與格式檢查留在這裡（CD-132b-13）：兩條路徑之前只做一次，
        搬進任一條就會漂移，而 parity 測試抓不到（BE-TEST-14）。
        """
        number = self.normalize_number(number)

        if not self.validate_number(number):
            raise ValueError(f"Invalid number format: {number}")

        if not allow_api:
            video = self.search_via_html(number)
            if video is not None:
                rate_limit(self.config.delay)
            return video

        try:
            video = self.search_via_api(number)
        except Exception as api_err:
            # 刻意攔 Exception 而不是只攔那兩個 typed exception：資料介面回了沒見過的
            # 形狀時 Video(...) 會拋 pydantic ValidationError，只攔兩個就等於
            # 「API 壞了 ＝ javdb 壞了」，而所有單元測試都會是綠的（CD-132b-5）。
            logger.warning("javdb: API 降級 → HTML（%s: %s）", type(api_err).__name__, api_err)
        else:
            if video is not None:
                rate_limit(self.config.delay)
                return video
            logger.info("javdb: API 查無 %s，改試 HTML", number)

        video = self.search_via_html(number)
        if video is not None:
            rate_limit(self.config.delay)
        return video

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

                    # 逐筆取詳情。**刻意不呼叫 `search()`**：那支是 API 優先的，
                    # 關鍵字搜尋走它等於一次搜尋打最多 20 次資料介面
                    # （spec-132 Non-Goals：關鍵字搜尋維持 HTML）。
                    video = self._search_number(number, allow_api=False)
                    if video:
                        results.append(video)

                except (SourceUnreachable, SourceBlocked):
                    raise
                except Exception as e:
                    logger.debug(f"JavDB keyword search item failed: {e}")
                    continue

            return results

        except (SourceUnreachable, SourceBlocked):
            raise
        except Exception as e:
            logger.warning(f"JavDB keyword search failed for {keyword}: {e}")
            return []
