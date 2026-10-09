"""
core/scrapers/javlibrary.py
────────────────────────────────────────────────────────────────
JavLibraryScraper — Cloudflare-aware scraper for www.javlibrary.com

依賴：
  - core.cf_transport（CfTransport Protocol、get_cf_transport、例外類別）
  - core.scrapers.base（BaseScraper）
  - core.scrapers.models（Video、Actress）
  - beautifulsoup4

設計決策（plan-70b §7 T2）：
  - LANG='ja'（CD-70b-2：固定 /ja/，不跟隨 UI locale）
  - search_by_keyword 永遠回傳 []（CD-70b：exact-only）
  - _is_cf_challenge / _is_age_gate 放 module-level，T4 的
    windows/cf_transport_impl.py 可直接 from core.scrapers.javlibrary import
  - transport.fetch 回傳 str（T1 Protocol），不是 tuple
"""
from __future__ import annotations

import re
from typing import Optional

from bs4 import BeautifulSoup

from core.cf_transport import (
    CfChallengeRequired,
    CfTransportUnavailable,
    get_cf_transport,
)
from core.logger import get_logger
from core.scrapers.base import BaseScraper
from core.scrapers.models import Actress, Video
from core.source_probe import VERIFIER_PROBE_HEADERS, ProbePlan, ProbeTarget

# ──────────────────────────────────────────────────────────────
# Module-level 常數（column 0）
# 硬契約（plan-70b §6）：windows/ 和 web/routers/ 從此 import，禁止在那邊重定義
# ──────────────────────────────────────────────────────────────
LANG = 'ja'
BASE_URL = 'https://www.javlibrary.com'
JAVLIBRARY_ORIGIN = f'{BASE_URL}/{LANG}/'

logger = get_logger(__name__)


# ──────────────────────────────────────────────────────────────
# CF / 年齡閘偵測輔助（module-level，供 T4 import）
# ──────────────────────────────────────────────────────────────

def _is_cf_challenge(title: str, html: str) -> bool:
    """
    判斷頁面是否仍在 CF challenge（真人驗證未過）。

    注意：舊版 challenge-form / cf-chl-widget marker 在新版 CF Turnstile 已不注入，
    改以 title + 小頁面判定（參見 spec-70a §1.2 / §5）。
    """
    title_lc = title.lower()
    if "just a moment" in title_lc or "請稍候" in title_lc:
        return True
    # CF 注入的隱藏欄位（舊版仍可能存在，保留為低成本 fallback）
    if 'id="challenge-form"' in html or 'name="cf-turnstile-response"' in html:
        return True
    return False


def _is_age_gate(html: str) -> bool:
    """True 表示頁面是 JavLibrary 的 18 歲/利用規約「同意閘」interstitial。

    僅偵測同意頁特有的 agree 控制（agreeBtn）。**不**用 footer 也會出現的
    「利用規約」/「18歳」文字或 over18 連結——那些在正常內容頁/首頁 footer
    也有，broad 比對會 false-positive（is_ready 卡死）。同意閘是用戶必須在
    彈窗手動點過的可恢復步驟，故 is_ready 需辨識它（回 False 讓彈窗保留）。

    正常 fetch 路徑恆 False 是「刻意」的：站台 #adultwarningmask 是 client-side
    overlay，每頁 server HTML 都有、靠 JS 讀 over18 cookie 才隱藏，從不擋 fetch/parse。
    若改成偵測 mask 會每頁誤判 age-gate → is_ready 永遠 False / fetch 永遠 raise → 全壞。
    本函式查 agreeBtn（真同意頁控制項），供 is_ready 偵測「視窗顯示中的真同意頁」異常路徑。
    """
    return 'agreeBtn' in html


# ──────────────────────────────────────────────────────────────
# HTML 解析輔助函式（module-level，直接移植 POC）
# ──────────────────────────────────────────────────────────────

def _sel_text(soup: BeautifulSoup, *selectors: str) -> Optional[str]:
    """依序試 selector，回傳第一個非空文字，或 None。"""
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            t = " ".join(el.get_text().split())
            if t:
                return t
    return None


def _sel_attr(soup: BeautifulSoup, selector: str, attr: str) -> Optional[str]:
    """取單一元素屬性值。"""
    el = soup.select_one(selector)
    if el:
        v = el.get(attr, "")
        return v if v else None
    return None


def _sel_all(soup: BeautifulSoup, *selectors: str) -> list[str]:
    """取所有匹配元素的文字 list（依序試 selector，回傳第一個有結果的）。"""
    for sel in selectors:
        items = soup.select(sel)
        if items:
            texts = []
            for el in items:
                t = " ".join(el.get_text().split())
                if t:
                    texts.append(t)
            if texts:
                return texts
    return []


def _extract_score(soup: BeautifulSoup) -> Optional[float]:
    """從 #video_review 中提取 0–10 的浮點評分（如 '(7.90)' → 7.90）。"""
    raw = _sel_text(soup, "#video_review span", "#video_review .score", "#video_review")
    if not raw:
        return None
    for part in re.split(r"[^\d.]+", raw):
        try:
            v = float(part)
            if 0.0 <= v <= 10.0:
                return v
        except ValueError:
            continue
    return None


def parse_detail(html: str, num: str) -> dict:
    """
    解析詳情頁，回傳 fields dict。
    Selector 來源：spec-70a §5 + 2026-06-08 實測 + javm Rust reference。

    sample_images：收集 .previewthumbs a 的 href（// → https: 補全），
    而非 POC 的只計數（T2 改動）。
    """
    soup = BeautifulSoup(html, "html.parser")

    # 番號
    number = _sel_text(soup,
        "#video_id td.text",
        "#video_id .text",
    ) or num

    # 標題（剝除開頭的番號 token 和空白/破折號）
    raw_title = _sel_text(soup, "h3.post-title") or ""
    # 去除 "TCD-332 -　" 這類前綴（番號 + 空格/破折號/全形空格）
    # 注意：char-class 含全形字元（—―ー　），移植時保留原樣
    stripped = re.sub(
        r"(?i)^" + re.escape(num) + r"\s*[-—―ー　]*\s*", "", raw_title
    ).strip()
    title = stripped or raw_title.strip() or None

    # 日期
    date = _sel_text(soup,
        "#video_date td.text",
        "#video_date .text",
    )

    # 片長（分鐘）
    length = _sel_text(soup,
        "#video_length td.text span",
        "#video_length .text",
    )

    # 導演
    director = _sel_text(soup,
        "#video_director td.text span a",
        "#video_director .text",
    )

    # 片商（maker）
    maker = _sel_text(soup,
        "#video_maker td.text span a",
        "#video_maker .text",
    )

    # 廠牌（label）
    label = _sel_text(soup,
        "#video_label td.text span a",
        "#video_label .text",
    )

    # 評分
    score = _extract_score(soup)

    # 封面（// → https:）
    cover = _sel_attr(soup, "img#video_jacket_img", "src")
    if cover and cover.startswith("//"):
        cover = "https:" + cover

    # 類型標籤
    genres = _sel_all(soup, "#video_genres a", "span.genre a")

    # 演員
    cast = _sel_all(soup, "#video_cast .star a", "span.star a")

    # 預覽縮圖 — 收集 href（T2 改動：POC 只計數，T2 改為收集 href list）
    sample_images: list[str] = []
    for a_tag in soup.select(".previewthumbs a"):
        href = a_tag.get("href", "")
        if href:
            if href.startswith("//"):
                href = "https:" + href
            sample_images.append(href)

    return dict(
        number=number,
        title=title,
        date=date,
        length=length,
        director=director,
        maker=maker,
        label=label,
        score=score,
        cover=cover,
        genres=genres,
        cast=cast,
        samples=sample_images,   # samples key 保留（映射表左欄），值已改為 list[str]
    )


def _is_detail_page(soup: BeautifulSoup) -> bool:
    """搜尋結果 302 redirect 到詳情頁時，頁面含 #video_id。"""
    return soup.select_one("#video_id") is not None


def _extract_detail_url(html: str, num: str, base_lang_url: str) -> Optional[str]:
    """
    從搜尋結果頁中取出詳情頁的完整 URL。
    優先精確比對番號，fallback 取第一個 .video a。
    相對路徑（./xxx.html / /ja/xxx.html）補全為絕對 URL。
    """
    soup = BeautifulSoup(html, "html.parser")
    links = soup.select(".video a")
    if not links:
        return None

    num_upper = num.upper()
    best: Optional[str] = None

    for el in links:
        text = el.get_text().upper()
        title_attr = el.get("title", "").upper()
        href = el.get("href", "")
        if not href:
            continue
        if num_upper in text or num_upper in title_attr:
            best = href
            break

    if best is None:
        best = links[0].get("href", "") or None

    if not best:
        return None

    # 正規化相對路徑
    if best.startswith("http"):
        return best
    if best.startswith("//"):
        return "https:" + best
    if best.startswith("./"):
        # ./javmezzbqu.html → https://www.javlibrary.com/ja/javmezzbqu.html
        return base_lang_url.rstrip("/") + "/" + best[2:]
    if best.startswith("/"):
        return BASE_URL + best
    # 其他相對路徑
    return base_lang_url.rstrip("/") + "/" + best


def _extract_all_detail_urls(html: str, num: str, base_lang_url: str) -> list[str]:
    """
    從搜尋結果頁收集所有與番號精確相符的 detail URL。

    boundary-aware 比對（避免 MIDV-010 誤收 MIDV-100 等前綴鄰號，
    或 AMIDV-010 / 1MIDV-010 等前置黏連號）。
    去重保序，無相符回 []（不 fallback links[0]）。
    """
    soup = BeautifulSoup(html, "html.parser")
    num_upper = num.upper()
    # 前後皆需番號邊界：lookbehind 擋前置黏連（AMIDV-010），lookahead 擋後綴鄰號（MIDV-100）
    pattern_str = r'(?<![0-9A-Za-z])' + re.escape(num_upper) + r'(?![0-9A-Za-z])'
    seen: set[str] = set()
    result: list[str] = []
    for el in soup.select(".video a"):
        href = el.get("href", "")
        if not href:
            continue
        title_attr = el.get("title", "").upper()
        text_attr = el.get_text().upper()
        # 一致性（對齊 _extract_detail_url :255 的 text OR title）：title 或 link text
        # 任一 boundary-match 即收。boundary regex 不變，仍嚴格擋鄰號/黏連，故多比對來源不引入 false positive。
        if not (re.search(pattern_str, title_attr) or re.search(pattern_str, text_attr)):
            continue
        # 正規化相對路徑（同 _extract_detail_url :265-276）
        if href.startswith("http"):
            normalized: str = href
        elif href.startswith("//"):
            normalized = "https:" + href
        elif href.startswith("./"):
            normalized = base_lang_url.rstrip("/") + "/" + href[2:]
        elif href.startswith("/"):
            normalized = BASE_URL + href
        else:
            normalized = base_lang_url.rstrip("/") + "/" + href
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _raise_if_cf(html: str) -> None:
    """CF challenge 偵測 helper。偵測到 CF challenge 則拋 CfChallengeRequired。"""
    soup_title_tag = BeautifulSoup(html, "html.parser").title
    page_title = soup_title_tag.string if soup_title_tag else ""
    if _is_cf_challenge(page_title, html):
        raise CfChallengeRequired("CF challenge detected")


# ──────────────────────────────────────────────────────────────
# JavLibraryScraper
# ──────────────────────────────────────────────────────────────

class JavLibraryScraper(BaseScraper):
    """
    JavLibrary scraper — 依賴 CfTransport（plan-70b §7 T2）。

    desktop-only：get_cf_transport() 在 dev/server 環境回 None，
    search() 拋 CfTransportUnavailable，不 fallback。
    """

    def _get_source_name(self) -> str:
        return 'javlibrary'

    def probe_plan(self, timeout):
        """測試連線：GET 首頁（與搜尋同一個出口）；拿到 Cloudflare 驗證頁＝通，不叫驗證視窗。"""
        session = self._new_session()

        def send():
            return session.get(
                JAVLIBRARY_ORIGIN, headers=VERIFIER_PROBE_HEADERS, timeout=timeout, stream=True)
        return ProbePlan([ProbeTarget('www.javlibrary.com', send, cf_challenge_ok=True)])

    def search(self, number: str) -> Optional[Video]:
        """
        以番號精確搜尋 JavLibrary，回傳 Video 或 None。

        流程（plan-70b §7 T2 search() 11 步）：
        1. get_cf_transport()；None → raise CfTransportUnavailable
        2. normalize_number()
        3. 建構 search_url
        4. transport.fetch(search_url)
        5. 防禦性 CF 偵測（只檢 CF challenge；age gate 由 transport begin_solve 處理）
        6. BeautifulSoup parse
        7. 若 _is_detail_page → 直接 parse（single-hit 302）
        8. 否則 _extract_detail_url → None → return None；有 URL → 第二次 fetch
        9. parse_detail
        10. title/cover 均空 → return None
        11. 建構並回傳 Video
        """
        # 步驟 1
        transport = get_cf_transport()
        if transport is None:
            raise CfTransportUnavailable(
                "JavLibrary scraper requires CF transport (desktop standalone only)"
            )

        # 步驟 2
        number = self.normalize_number(number)

        # 步驟 3
        search_url = f'{BASE_URL}/{LANG}/vl_searchbyid.php?keyword={number}'

        # 步驟 4
        html: str = transport.fetch(search_url, cache_key='javlibrary')

        # 步驟 5：防禦性 CF 檢查
        # 只檢 CF challenge，不檢 age gate。
        # 理由：「利用規約」「18歳」等字串出現在所有正常詳情頁的 footer，
        # 用 _is_age_gate 會把有效頁面誤判為閘門 → CfChallengeRequired 死循環。
        # Age gate 由 transport.begin_solve（設 over18 cookie）+ is_ready 把關，
        # post-solve fetch 不會再遇 age gate（比照 POC scrape_b 設計）。
        _raise_if_cf(html)

        # 步驟 6
        soup = BeautifulSoup(html, "html.parser")

        # 步驟 7：single-hit 302 shortcut
        if _is_detail_page(soup):
            detail_html = html
            # FIX-4：single-hit 時 detail_url 留空（search-php URL 不是 canonical，
            # 寫進 NFO website 欄位語義不正確；正解留 follow-up 由 transport 回 final_url）
            detail_url = ""
        else:
            # 步驟 8：multi-result
            base_lang_url = f'{BASE_URL}/{LANG}'
            found_url = _extract_detail_url(html, number, base_lang_url)
            if not found_url:
                logger.info("javlibrary: no detail URL found for %s (站上真的沒有此番號)", number)
                return None
            detail_url = found_url
            detail_html = transport.fetch(detail_url, cache_key='javlibrary')

            # 第二次 fetch 防禦性 CF 檢查（同上，只檢 CF，不檢 age gate）
            _raise_if_cf(detail_html)

        return self._video_from_detail_html(detail_html, number, detail_url)

    def search_by_keyword(self, keyword: str, limit: int = 20) -> list[Video]:
        """永遠回傳空 list（CD-70b：exact-only，不做模糊搜尋）。"""
        return []

    def _video_from_detail_html(
        self,
        detail_html: str,
        number: str,
        detail_url: str,
    ) -> Optional[Video]:
        """
        parse_detail + 品質保護 + FIX-5 番號核對 + Video 映射（steps 9-11）。
        行為與原 search() :367-419 完全相同。
        """
        # 步驟 9
        fields = parse_detail(detail_html, number)

        # 步驟 10：parse 品質保護
        if not fields.get("title") and not fields.get("cover"):
            logger.info(
                "javlibrary: parse failed for %s (title+cover both empty — selector 失準或頁面結構變動)",
                number,
            )
            return None

        # FIX-5：番號核對守衛
        parsed_number_norm = self.normalize_number(fields.get("number") or "")
        request_number_norm = self.normalize_number(number)
        if parsed_number_norm and request_number_norm and parsed_number_norm != request_number_norm:
            logger.warning(
                "javlibrary: number mismatch — requested %r, parsed %r; returning None",
                request_number_norm,
                parsed_number_norm,
            )
            return None

        # 步驟 11：欄位映射 → Video
        # length → duration（re.search → int，無值 → None）
        duration: Optional[int] = None
        length_str = fields.get("length")
        if length_str:
            m = re.search(r'\d+', str(length_str))
            if m:
                duration = int(m.group())

        # cast → actresses（過濾空名，防 Actress min_length=1 ValidationError）
        actresses = [
            Actress(name=name)
            for name in fields.get("cast", [])
            if name.strip()
        ]

        return Video(
            number=fields.get("number") or number,
            title=str(fields.get("title") or ""),
            date=str(fields.get("date") or ""),
            duration=duration,
            director=str(fields.get("director") or ""),
            maker=str(fields.get("maker") or ""),
            label=str(fields.get("label") or ""),
            rating=fields.get("score"),
            cover_url=str(fields.get("cover") or ""),
            tags=fields.get("genres") or [],
            actresses=actresses,
            sample_images=fields.get("samples") or [],
            source='javlibrary',
            detail_url=detail_url,
        )

    def search_all_versions(self, number: str) -> list[Video]:
        """
        以番號搜尋 JavLibrary，收集全部版本（同番號複數 detail），回傳 list[Video]。
        新片優先（date desc）。

        - 單一命中 302 → 1-element list
        - 多版本列表 → boundary-aware 列舉全部 detail URL，各別 fetch parse
        - 列表頁或 detail fetch 遇 CF challenge → CfChallengeRequired propagate
        - 無相符 → []
        """
        transport = get_cf_transport()
        if transport is None:
            raise CfTransportUnavailable(
                "JavLibrary scraper requires CF transport (desktop standalone only)"
            )
        number = self.normalize_number(number)
        search_url = f'{BASE_URL}/{LANG}/vl_searchbyid.php?keyword={number}'
        html: str = transport.fetch(search_url, cache_key='javlibrary')
        _raise_if_cf(html)
        soup = BeautifulSoup(html, "html.parser")
        if _is_detail_page(soup):
            # 單一命中 302（已是 detail 頁）
            v = self._video_from_detail_html(html, number, "")
            return [v] if v else []
        base_lang_url = f'{BASE_URL}/{LANG}'
        urls = _extract_all_detail_urls(html, number, base_lang_url)
        out: list[Video] = []
        for url in urls:
            dhtml: str = transport.fetch(url, cache_key='javlibrary')
            _raise_if_cf(dhtml)
            v = self._video_from_detail_html(dhtml, number, url)
            if v:
                out.append(v)
        out.sort(key=lambda v: v.date or "", reverse=True)  # 新片優先（CD-86-3）
        return out

    def fetch_by_detail_url(self, detail_url: str, number: str) -> Optional[Video]:
        """
        直接以 detail URL 抓取並解析，回傳 Video 或 None。
        detail_url 會落地在 Video.detail_url。
        """
        transport = get_cf_transport()
        if transport is None:
            raise CfTransportUnavailable(
                "JavLibrary scraper requires CF transport (desktop standalone only)"
            )
        dhtml: str = transport.fetch(detail_url, cache_key='javlibrary')
        _raise_if_cf(dhtml)
        return self._video_from_detail_html(dhtml, self.normalize_number(number), detail_url)
