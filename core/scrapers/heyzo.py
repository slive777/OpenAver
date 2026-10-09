"""HEYZO 爬蟲（JSON-LD + HTML table）"""
import json
import re
import requests
from typing import Optional

from core.logger import get_logger

logger = get_logger(__name__)
from lxml import etree
from .base import BaseScraper
from .models import Video, Actress, ScraperConfig
from .utils import rate_limit


class HEYZOScraper(BaseScraper):
    """
    HEYZO 爬蟲

    解析順序：
    1. 從英文頁 JSON-LD 取 title、actress（羅馬字）、date、rating
    2. 從同一英文頁 HTML table 取 series、tags
    3. cover URL 從 JSON-LD image 欄位建構

    番號格式：HEYZO-0783 → strip prefix → "0783"
    """

    BASE_URL = "https://www.heyzo.com/moviepages/{num}/index.html"
    EN_URL = "https://en.heyzo.com/moviepages/{num}/index.html"

    def __init__(self, config: Optional[ScraperConfig] = None):
        super().__init__(config)
        self._session = self._new_session()
        self._session.headers.update({
            'User-Agent': self.config.user_agent,
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'en-US,en;q=0.9,ja;q=0.8',
        })

    def _get_source_name(self) -> str:
        return "heyzo"

    def _extract_heyzo_num(self, number: str) -> Optional[str]:
        """
        從番號提取 HEYZO 數字 ID（保留前導零）。

        Examples:
            HEYZO-0783 → "0783"
            heyzo-1031 → "1031"
        """
        number = number.strip().upper()
        match = re.match(r'^HEYZO-(\d+)$', number)
        if match:
            return match.group(1)
        # 純數字也接受
        if re.match(r'^\d+$', number):
            return number
        return None

    def _extract_json_ld(self, html_content: bytes) -> Optional[dict]:
        """
        從 HTML 中提取 application/ld+json 內容（Path A：靜態 script tag）。

        Returns:
            解析後的 dict，找不到或解析失敗返回 None
        """
        try:
            html = etree.fromstring(html_content, etree.HTMLParser())
            scripts = html.xpath('//script[@type="application/ld+json"]/text()')
            for script in scripts:
                try:
                    data = json.loads(script)
                    if isinstance(data, dict) and data.get('@type') == 'Movie':
                        return data
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            logger.debug(f"HEYZO JSON-LD parse error: {e}")
        return None

    def _extract_js_var_block(self, html_text: str, var_name: str) -> Optional[str]:
        """
        從 `var <var_name> = { ... };`（分號可有可無）文字中，用 brace-matching
        取出配對完整的 `{...}` 區塊原始文字（尚未 json.loads）。

        對雙引號字串內容做跳脫（忽略字串內的 `{`/`}`、處理 `\\"` escape），
        避免巢狀物件或文字欄位裡的符號打亂配對。找不到變數宣告或 brace 不配對
        時回傳 None。
        """
        pattern = re.compile(r'var\s+' + re.escape(var_name) + r'\s*=\s*\{')
        m = pattern.search(html_text)
        if not m:
            return None

        start = m.end() - 1  # 指向開頭的 '{'
        depth = 0
        in_string = False
        i = start
        n = len(html_text)
        while i < n:
            c = html_text[i]
            if in_string:
                if c == '\\':
                    i += 2
                    continue
                if c == '"':
                    in_string = False
                i += 1
                continue
            if c == '"':
                in_string = True
            elif c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    return html_text[start:i + 1]
            i += 1
        return None

    def _extract_js_movie_object(self, html_text: str) -> Optional[dict]:
        """
        Path B：站方把 JSON-LD 從靜態輸出改成 `window load` 時 JS 動態組裝
        （`var person` / `var aggregateRating` / `var movie_obj`）。從純文字
        原始碼中重建等價的 movie dict。

        `movie_obj` 裡 `"actor":person` / `"aggregateRating":aggregateRating`
        是 JS 變數參照（不是合法 JSON），需先把這兩個變數各自的內容抓出來，
        再把 movie_obj 文字裡緊接在 `:` 之後、以 `,`/`}` 結尾的裸 token
        替換成對應的 json.dumps 結果，才能 json.loads。

        任何步驟失敗（找不到 / JSON 解析失敗）一律回 None，維持 fail-safe。
        """
        try:
            person_block = self._extract_js_var_block(html_text, 'person')
            agg_block = self._extract_js_var_block(html_text, 'aggregateRating')
            movie_block = self._extract_js_var_block(html_text, 'movie_obj')
            if not movie_block:
                return None

            person_dict = {}
            if person_block:
                try:
                    person_dict = json.loads(person_block)
                except json.JSONDecodeError:
                    person_dict = {}

            agg_dict = {}
            if agg_block:
                try:
                    agg_dict = json.loads(agg_block)
                except json.JSONDecodeError:
                    agg_dict = {}

            # ⚠ replacement 一律用 lambda，不可用字串。re.sub 的字串 replacement 是
            # template，會解析反斜線轉義：json.dumps 對非 ASCII 產出的 `\uXXXX` 會直接
            # 拋 `re.error: bad escape \u`，而值內的 `\\` 會被還原成 `\` 生出非法 JSON
            # ——兩者都被下方 except 吞掉、Path B 回 None，等於整個來源再次靜默查無。
            # lambda replacement 不做 template 解析，原樣插入。
            person_json = json.dumps(person_dict)
            agg_json = json.dumps(agg_dict)

            movie_text = movie_block
            movie_text = re.sub(
                r':\s*\bperson\b\s*(?=[,}])',
                lambda _m: ': ' + person_json,
                movie_text,
            )
            movie_text = re.sub(
                r':\s*\baggregateRating\b\s*(?=[,}])',
                lambda _m: ': ' + agg_json,
                movie_text,
            )

            data = json.loads(movie_text)
            if isinstance(data, dict) and data.get('@type') == 'Movie':
                return data
        except Exception as e:
            logger.debug(f"HEYZO JS movie_obj parse error: {e}")
        return None

    def _extract_table_data(self, html_content: bytes) -> dict:
        """
        從 HTML table.movieInfo 提取補充資料。

        Returns:
            dict with keys: 'series', 'tags', 'duration', 'sample_images',
            'actresses', 'date'
        """
        result = {
            'series': '', 'tags': [], 'duration': None, 'sample_images': [],
            'actresses': [], 'date': '',
        }
        try:
            html = etree.fromstring(html_content, etree.HTMLParser())

            # Series（值現在可能被 <a> 包住（有連結的 series），也可能是純文字
            # placeholder（"-----"）；讀整格文字（.//text()）而非只讀直接 text
            # node，否則 <a> 包住的值會被漏接，抽出全空字串）
            series_nodes = html.xpath(
                '//table[@class="movieInfo"]//tr/td[contains(text(),"Series")]/following-sibling::td[1]'
            )
            series_text = ''
            if series_nodes:
                raw = ''.join(series_nodes[0].xpath('.//text()')).replace('\xa0', ' ')
                series_text = ' '.join(raw.split())
            # Filter out placeholder values like "-----" or "---"
            if series_text and all(c == '-' for c in series_text):
                series_text = ''
            result['series'] = series_text

            # Tags（Type 欄位）
            tags = html.xpath(
                '//table[@class="movieInfo"]//tr/td[contains(text(),"Type")]/following-sibling::td[1]//a/text()'
            )
            result['tags'] = [t.strip() for t in tags if t.strip()]

            # Actress(es)（支援多個 <a>；文字含大量 \t\n 與 \xa0，需正規化後再判空）
            actress_nodes = html.xpath(
                '//table[@class="movieInfo"]//tr/td[contains(text(),"Actress")]'
                '/following-sibling::td[1]//a/text()'
            )
            actresses = []
            for name in actress_nodes:
                cleaned = name.replace('\xa0', ' ').strip()
                if cleaned:
                    actresses.append(cleaned)
            result['actresses'] = actresses

            # Released（可能是單一日期、日期區間「start ～ end」、"Coming Soon !!"
            # 或空白；一律取 leading date，抽不到就回空字串，不 raise）
            released = html.xpath(
                '//table[@class="movieInfo"]//tr/td[contains(text(),"Released")]/following-sibling::td[1]'
            )
            if released:
                released_text = released[0].xpath('string(.)')
                released_text = released_text.replace('\xa0', ' ').strip()
                date_match = re.match(r'^(\d{4}-\d{2}-\d{2})', released_text)
                if date_match:
                    result['date'] = date_match.group(1)

            # Duration（從 JS 變數 heyzo.duration 提取 "full":"HH:MM:SS"）
            html_text = html_content.decode('utf-8', errors='replace')
            dur_match = re.search(r'"full"\s*:\s*"(\d{2}):(\d{2}):(\d{2})"', html_text)
            if dur_match:
                try:
                    h, m = int(dur_match.group(1)), int(dur_match.group(2))
                    result['duration'] = h * 60 + m
                except ValueError:
                    pass

            # Sample images（gallery は JS document.write で生成、dir_gallery + thumbnail 連番から構築）
            dir_match = re.search(r'dir_gallery\s*=\s*"(/contents/[^"]+)"', html_text)
            if dir_match:
                dir_gallery = dir_match.group(1)
                # sample-images セクション内の thumbnail_NNN.jpg から NNN を抽出
                si_idx = html_text.find('sample-images')
                if si_idx >= 0:
                    section = html_text[si_idx:si_idx + 5000]
                    gallery_nums = re.findall(r'thumbnail_(\d{3})\.jpg', section)
                    for num in gallery_nums:
                        result['sample_images'].append(f"https://en.heyzo.com{dir_gallery}{num}.jpg")

        except Exception as e:
            logger.debug(f"HEYZO table parse error: {e}")
        return result

    def search(self, number: str) -> Optional[Video]:
        """
        搜尋影片資訊。

        Args:
            number: 番號（如 HEYZO-0783）

        Returns:
            Video 物件，找不到返回 None
        """
        heyzo_num = self._extract_heyzo_num(number)
        if not heyzo_num:
            logger.debug(f"HEYZO: invalid number format: {number}")
            return None

        en_url = self.EN_URL.format(num=heyzo_num)
        ja_url = self.BASE_URL.format(num=heyzo_num)

        try:
            # Step 1: 取英文頁 → JSON-LD（羅馬字女優名、英文 title）
            resp = self._session.get(en_url, timeout=self.config.timeout)
            if resp.status_code == 404:
                return None
            if resp.status_code != 200:
                logger.debug(f"HEYZO EN page: HTTP {resp.status_code} for {heyzo_num}")
                return None

            # Step 1b: JSON-LD 擷取（Path A 靜態 script tag 優先，Path B JS
            # 動態組裝 fallback；BE-SCRAPER-04：站方會在兩者間 toggle，
            # 兩路徑必須並存，不可只留其一）
            json_ld = self._extract_json_ld(resp.content)
            if not json_ld:
                logger.debug(
                    f"HEYZO: static ld+json not found for {heyzo_num}, "
                    f"trying JS movie_obj fallback"
                )
                html_text = resp.content.decode('utf-8', errors='replace')
                json_ld = self._extract_js_movie_object(html_text)
            if not json_ld:
                logger.warning(
                    f"HEYZO: page format changed for {heyzo_num} — "
                    f"neither static ld+json tag nor `var movie_obj` JS block "
                    f"found/parseable (not a 404 / network issue)"
                )
                return None

            # Step 2: 解析 JSON-LD
            title = json_ld.get('name', '')
            if not title:
                return None

            # 封面（image 格式：//www.heyzo.com/...）
            image = json_ld.get('image', '')
            cover_url = f"https:{image}" if image.startswith('//') else image

            # Rating
            agg_rating = json_ld.get('aggregateRating', {})
            rating = float(agg_rating['ratingValue']) if agg_rating.get('ratingValue') else None
            votes = int(agg_rating['reviewCount']) if agg_rating.get('reviewCount') else None

            # 簡介（JSON-LD description，缺欄位回退空字串）
            summary = json_ld.get('description') or ''

            # Step 3: 從同一 EN page 的 HTML table 取 tags、series、女優、發行日
            # （女優/發行日不再吃 JSON-LD，改吃 table——比 JS 動態組裝的
            # JSON-LD 更可信，見 task 說明）
            table_data = self._extract_table_data(resp.content)
            actresses = [Actress(name=name) for name in table_data['actresses']]

            rate_limit(self.config.delay)

            return Video(
                number=f"HEYZO-{heyzo_num}",
                title=title,
                actresses=actresses,
                date=table_data['date'],
                maker='HEYZO',
                cover_url=cover_url,
                tags=table_data['tags'],
                source=self.source_name,
                detail_url=ja_url,
                rating=rating,
                votes=votes,
                summary=summary,
                series=table_data['series'],
                duration=table_data['duration'],
                sample_images=table_data['sample_images'],
            )

        except requests.Timeout as e:
            raise TimeoutError(f"HEYZO request timeout for {number}") from e
        except Exception as e:
            logger.warning(f"HEYZO search failed for {number}: {e}")
            return None

    def search_by_keyword(self, keyword: str, limit: int = 20) -> list[Video]:
        """
        關鍵字搜尋（HEYZO 無公開搜尋 API，當番號處理）。

        Args:
            keyword: 搜尋關鍵字（如 HEYZO-0783）
            limit: 最大結果數（最多 1 筆）

        Returns:
            Video 列表（最多 1 筆）
        """
        result = self.search(keyword)
        return [result] if result else []
