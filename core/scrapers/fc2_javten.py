"""FC2-javten 爬蟲（javten.com 鏡像站，來源 id `fc-javten`）"""
import json
import re
from typing import Optional
from urllib.parse import urlsplit

from lxml import etree

from core.cf_transport import (
    CfChallengeRequired,
    CfTransportUnavailable,
    get_cf_transport,
)
from core.logger import get_logger
from .base import BaseScraper
from .models import Video, Actress, ScraperConfig
from .utils import rate_limit

logger = get_logger(__name__)

# 模組層公開常數（CD-118a-12）。windows/ 與 web/routers/ 一律 import 這個，禁止重定義。
JAVTEN_ORIGIN = "https://javten.com/"

# T6-P3-2（Codex review）：落地 URL 的 host/scheme 白名單。
#
# 為什麼是這次才需要：T6/F-1 之前，navigate_and_settle() 回的是
# `get_current_url() or url`，而 WebView2 的那個值不跟轉址走 —— 等於**意外地**把 host
# 鎖死在我們請求的 javten URL 上。F-1 改讀 location.href 之後才真的會跟著轉址離開
# javten，信任面是這次改動放開的，所以由這次補上。
#
# 為什麼 INV-1 的 origin gate 擋不住：它比對「transport 記錄的 origin」與「要 fetch 的
# origin」，兩者都源自同一個落地 URL，by construction 必然相等。它防的是內部狀態走鐘，
# 不是「這個 host 該不該信」。
#
# 使用者流程：javten 是第三方鏡像站（本來就不可信）。它哪天把搜尋轉去別的 host，我們就
# 把那個 host 的頁面當成影片資料 —— 標題／封面／標籤／劇照網址寫進使用者的 NFO 與資料庫，
# 而他看不出來，只能整批重刮。
#
# 寫法沿用本專案既有慣例（`web/routers/scraper.py` 的 `_is_javlibrary_url()`）：
# urlparse → scheme 精確比對 → netloc 精確比對，**不用 startswith**（`javten.com.evil.com`
# 會通過 prefix 比對），也不靠命中 regex（它是 re.search 未錨定，`?x=` 塞得進去）。
_JAVTEN_ALLOWED_NETLOCS = frozenset({"javten.com", "www.javten.com"})


def _is_javten_url(url: str) -> bool:
    """落地 URL 是否仍在 javten 自己的 https origin 上。"""
    try:
        parts = urlsplit(url)
    except (ValueError, TypeError):
        return False
    return parts.scheme == "https" and parts.netloc.lower() in _JAVTEN_ALLOWED_NETLOCS


def strip_lang_segment(url: str) -> str:
    """/{tw|en|ko}/video/{id}/id{num}/{slug} → /video/{id}/id{num}/{slug}

    slug 不可省（省掉是 500）；不要用 /ja/（404）——這裡不新增語言段，只剝除既有的。
    """
    return re.sub(r'^(https?://[^/]+)/(?:tw|en|ko)/', r'\1/', url)


class FC2JavtenScraper(BaseScraper):
    """
    FC2 爬蟲（javten.com 鏡像站，來源 id `fc-javten`）

    優點：
    - 不需要登入
    - 有封面、預覽圖
    - 有簡介、賣家資訊

    注意：
    - 使用第三方鏡像站
    - 無發售日期
    - 需 CF transport（desktop standalone）

    參考：mdcx/crawlers/fc2hub.py
    """

    BASE_URL = "https://javten.com"

    def __init__(self, config: Optional[ScraperConfig] = None):
        super().__init__(config)

    def _get_source_name(self) -> str:
        return "fc-javten"

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
        # BE-SCRAPER-05：/text() 已知脆弱點（站方多包一層 <a> 會靜默抽空）；T0 真檔實測全中，不改
        result = html.xpath("//h1/text()")
        # 第二個 h1 是標題（第一個是番號）
        return result[1].strip() if len(result) > 1 else ""

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
        # BE-SCRAPER-05：/text() 已知脆弱點（站方多包一層 <a> 會靜默抽空）；T0 真檔實測全中，不改
        result = html.xpath('//div[@class="col-8"]/text()')
        return result[0].strip() if result else ""

    def _get_tags(self, html) -> list[str]:
        """取得標籤"""
        # BE-SCRAPER-05：/text() 已知脆弱點（站方多包一層 <a> 會靜默抽空）；T0 真檔實測全中，不改
        result = html.xpath('//p[@class="card-text"]/a[contains(@href, "/tag/")]/text()')
        return [tag.strip() for tag in result if tag.strip()]

    def _get_outline(self, html) -> str:
        """取得簡介"""
        result = html.xpath('//div[@class="col des"]//text()')
        text = "".join(result).strip()
        # 清理文字
        text = text.replace("\\n", " ").replace("・", "").strip()
        return text

    def _get_rating(self, html) -> Optional[float]:
        """取得評分（JSON-LD aggregateRating.ratingValue，0–5，defensive）"""
        scripts = html.xpath('//script[@type="application/ld+json"]/text()')
        for script in scripts:
            try:
                data = json.loads(script)
                # JSON-LD 可能是：單一物件（dict）、頂層陣列（list）、
                # 或 {"@graph": [...]} 包裹（常見於多節點 JSON-LD）
                if isinstance(data, list):
                    nodes = data
                elif isinstance(data, dict):
                    graph = data.get("@graph")
                    # 同時把頂層 dict 與其 @graph 子節點都納入候選，
                    # 涵蓋 aggregateRating 掛在 wrapper 或 @graph 內的兩種真實形狀
                    nodes = [data] + (graph if isinstance(graph, list) else [])
                else:
                    nodes = []
                for node in nodes:
                    if isinstance(node, dict) and "aggregateRating" in node:
                        return float(node["aggregateRating"]["ratingValue"])
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
        return None

    def _is_uncensored(self, tags: list[str], title: str) -> bool:
        """判斷是否無碼"""
        text = " ".join(tags) + " " + title
        return any(kw in text for kw in ["無修正", "无修正", "uncensored"])

    def search(self, number: str) -> Optional[Video]:
        """
        搜尋影片資訊（navigate_and_settle → 剝語言段 → fetch）

        Args:
            number: 番號（如 FC2-PPV-1234567）

        Returns:
            Video 物件，找不到返回 None
        """
        transport = get_cf_transport()
        if transport is None:
            raise CfTransportUnavailable(
                "FC2-javten scraper requires CF transport (desktop standalone only)"
            )

        digits = self._normalize_fc2_number(number)

        try:
            final = transport.navigate_and_settle(
                f'{JAVTEN_ORIGIN}search?kw={digits}', 'fc-javten'
            )

            # CD-118a-19 的命中判準要「同時擋掉查無此片與拿到別片」。
            # re.escape 是必要的，不是防禦性冗餘：_normalize_fc2_number() 只剝 FC2/PPV 前綴與
            # 分隔符，**不保證回傳純數字**（實測 'garbage' → 'GARBAGE'）。番號裡的 `.` `*` 會
            # 讓這條 pattern 變寬 → javten 的搜尋 302 到別片時我們會照收 → 別片的標題／封面／
            # 標籤被寫進使用者的 NFO 與 DB，而他看不出來。
            # T6-P3-2：先擋 host/scheme，再談路徑命中。順序不能反 —— 命中判準是未錨定的
            # re.search，`https://evil.com/?x=https://javten.com/video/1/id<番號>/` 會通過它。
            # 這裡檢 `final`（strip_lang_segment 只剝語言段、不動 host，實測與測試皆已覆蓋）。
            if not _is_javten_url(final):
                logger.warning(
                    "FC2-javten 搜尋落在 javten 之外的位址，已拒絕（不 fetch）：%s", final
                )
                return None

            if not re.search(rf'/video/\d+/id{re.escape(digits)}(/|$)', final):
                # 仍停在 /search?kw= ＝ 查無此片（CD-118a-19，前提是 transport 已擋掉挑戰頁）
                return None

            ja_url = strip_lang_segment(final)
            html = transport.fetch(ja_url, 'fc-javten')

            html_tree = etree.fromstring(html.encode('utf-8'), etree.HTMLParser())
            title = self._get_title(html_tree)
            if not title:
                return None

            cover_url = self._get_cover(html_tree)
            studio = self._get_studio(html_tree)
            tags = self._get_tags(html_tree)
            outline = self._get_outline(html_tree)
            rating = self._get_rating(html_tree)
            sample_images = self._get_extrafanart(html_tree)

            tags = [t for t in tags if t not in ["無修正", "无修正"]]

            actresses = [Actress(name=studio)] if studio else []

            video = Video(
                number=f"FC2-{digits}",
                title=title,
                actresses=actresses,
                # javten 結構性沒有發售日欄位（T0 實測：販売日/発売日 在整份 HTML 出現 0 次，見 tests/fixtures/scrapers/README.md）
                date="",
                maker=studio,
                cover_url=cover_url,
                tags=tags,
                source=self.source_name,
                detail_url=ja_url,
                sample_images=sample_images,
                summary=outline,
                rating=rating,
            )

            rate_limit(self.config.delay)
            return video
        except (CfChallengeRequired, CfTransportUnavailable):
            raise  # CD-118a-13①：CF 兩個例外原樣往外拋，不吞、不轉型
        except Exception as e:
            logger.debug(f"FC2-javten search failed for {number}: {e}")
            return None  # CD-118a-13②：其餘失敗一律靜默 miss

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
