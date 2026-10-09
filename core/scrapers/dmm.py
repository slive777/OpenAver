"""DMM 爬蟲（官方 GraphQL API）"""
import json
import re
import requests
from pathlib import Path
from typing import Optional

from core.logger import get_logger

logger = get_logger(__name__)
from .base import BaseScraper
from .errors import SourceBlocked, SourceUnreachable
from .models import Video, Actress, ScraperConfig
from .utils import rate_limit
from core.source_probe import ProbePlan, ProbeTarget


# 出貨前綴表路徑（專案根目錄，依片商分組）
PROJECT_ROOT = Path(__file__).parent.parent.parent
SHIPPED_TABLE_FILE = PROJECT_ROOT / "dmm_prefix_table.json"

# module-level capability cache（三態）
# None = 未知（首次或暫時性失敗），True = schema 支援，False = schema 不支援
_genres_supported: Optional[bool] = None
_sample_images_supported: Optional[bool] = None
_review_supported: Optional[bool] = None

# 出貨表快取（None = 尚未讀）
_shipped_table_cache: Optional[dict] = None


def _flatten_shipped_table(raw: dict) -> dict[str, dict]:
    """展平出貨表 makers → {prefix: entry}；跨片商撞名時 raise。"""
    flat: dict[str, dict] = {}
    for maker, prefixes in raw.get("makers", {}).items():
        for prefix, entry in prefixes.items():
            if prefix in flat:
                raise ValueError(
                    f"dmm_prefix_table.json 撞名：前綴 '{prefix}' 同時出現在片商 "
                    f"'{flat[prefix]['_maker']}' 與 '{maker}' 底下"
                )
            flat[prefix] = {**entry, "_maker": maker}
    return flat


class DMMScraper(BaseScraper):
    """
    DMM 爬蟲（使用官方 GraphQL API）

    優點：
    - 官方資料來源，資料最準確
    - 封面無浮水印、高畫質
    - 有完整簡介、導演資訊

    特點：
    - 隨版本出貨的番號前綴對照表（dmm_prefix_table.json，見 spec-134 F1）
      ⚠️ 該檔是出貨產物，build.py / build_macos.py 的 COPY_ITEMS 必須帶上；
         拿掉它冷啟動命中率會從 320/335 掉回 175/335。

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

    SEARCH_LIST_QUERY = """
        query AvSearch($limit: Int!, $offset: Int!, $sort: ContentSearchPPVSort!, $queryWord: String) {
            legacySearchPPV(limit: $limit, offset: $offset, sort: $sort, queryWord: $queryWord) {
                result {
                    contents {
                        id
                        title
                        packageImage { largeUrl }
                        actresses { name }
                        maker { name }
                    }
                }
            }
        }
    """

    # 獨立 probe query — 與 DETAIL_QUERY 分離，失敗不影響主流程
    GENRES_PROBE_QUERY = """
        query ProbeGenres($id: ID!) {
            ppvContent(id: $id) {
                genres { name }
                label { name }
            }
        }
    """

    SAMPLE_IMAGES_PROBE_QUERY = """
        query ProbeSampleImages($id: ID!) {
            ppvContent(id: $id) {
                sampleImages { imageUrl }
            }
        }
    """

    # 評分 probe — root field reviewSummary（arg 名 contentId，非 id）
    REVIEW_PROBE_QUERY = """
        query ProbeReview($contentId: ID!) {
            reviewSummary(contentId: $contentId) { average }
        }
    """

    # GraphQL schema error patterns — 不同實作回傳的訊息格式不同
    SCHEMA_ERROR_PATTERNS = ('Unknown field', 'Cannot query field')

    def __init__(self, config: Optional[ScraperConfig] = None):
        super().__init__(config)
        self._session = self._new_session()
        self._session.headers.update({
            'User-Agent': self.config.user_agent,
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        })

    def probe_plan(self, timeout):
        """測試連線：打查資料實際走的 graphql 端點（帶 session 的代理與 header）。"""
        def send():
            return self._session.post(self.API_URL, json={'query': '{ __typename }'}, timeout=timeout, stream=True)
        return ProbePlan([ProbeTarget('api.video.dmm.co.jp', send)])

    def _get_source_name(self) -> str:
        return "dmm"

    def _probe_genres(self, content_id: str) -> tuple[list[str], str]:
        """
        探測 ppvContent 是否支援 genres/label 欄位。

        三態 cache 控制：
        - _genres_supported is False → 立即回傳空（永久跳過）
        - _genres_supported is True  → 仍查詢（該片可能有 tags）
        - _genres_supported is None  → 首次查詢，依結果更新 cache

        Returns:
            (tags, label) — 探測失敗時回傳 ([], '')
        """
        global _genres_supported

        # 已確認 schema 不支援 → 永久跳過
        if _genres_supported is False:
            return [], ''

        try:
            payload = {
                'query': self.GENRES_PROBE_QUERY,
                'variables': {'id': content_id}
            }
            resp = self._session.post(self.API_URL, json=payload, timeout=5)

            if resp.status_code != 200:
                # HTTP 錯誤 → 暫時性失敗，維持 None
                return [], ''

            resp_json = resp.json()
            errors = resp_json.get('errors', [])

            # 判定 1：schema error（unknown field / validation error）→ 確認不支援
            if any(
                any(pat in (e.get('message', '') or '') for pat in self.SCHEMA_ERROR_PATTERNS)
                for e in errors
            ):
                _genres_supported = False
                logger.info("[DMM] GraphQL schema 不支援 genres，已永久停用 probe")
                return [], ''

            # 判定 2：GraphQL 錯誤但非 schema error → 暫時性，維持 None
            data = resp_json.get('data') or {}
            item = data.get('ppvContent')

            if item is None:
                # content_id 不存在或其他 null，無法判定 → 維持 None
                return [], ''

            # 判定 3：正常回應 → schema 支援（即使此片 tags 為空）
            _genres_supported = True
            genres = item.get('genres') or []
            tags = [g['name'] for g in genres if g.get('name')]
            label = (item.get('label') or {}).get('name', '')
            return tags, label

        except Exception:
            # 網路錯誤、timeout → 暫時性失敗，維持 None（不設 False）
            return [], ''

    def _probe_sample_images(self, content_id: str) -> list[str]:
        """
        探測 ppvContent 是否支援 sampleImages 欄位。

        獨立於 genres/label probe，避免互相干擾。
        三態 cache 控制同 _probe_genres()。
        """
        global _sample_images_supported

        if _sample_images_supported is False:
            return []

        try:
            payload = {
                'query': self.SAMPLE_IMAGES_PROBE_QUERY,
                'variables': {'id': content_id}
            }
            resp = self._session.post(self.API_URL, json=payload, timeout=5)

            if resp.status_code != 200:
                return []

            resp_json = resp.json()
            errors = resp_json.get('errors', [])

            if any(
                any(pat in (e.get('message', '') or '') for pat in self.SCHEMA_ERROR_PATTERNS)
                for e in errors
            ):
                _sample_images_supported = False
                logger.info("[DMM] GraphQL schema 不支援 sampleImages，已永久停用 probe")
                return []

            data = resp_json.get('data') or {}
            item = data.get('ppvContent')

            if item is None:
                return []

            _sample_images_supported = True
            raw_samples = item.get('sampleImages') or []
            return [re.sub(r'(?<!jp)-(\d+)\.jpg$', r'jp-\1.jpg', s['imageUrl']) for s in raw_samples if s.get('imageUrl')]

        except Exception:
            return []

    def _probe_review(self, content_id: str) -> Optional[float]:
        """
        探測 root field reviewSummary 是否被 schema 支援，並取回評分。

        三態 cache 控制同 _probe_genres()，但注意一處差異：
        reviewSummary 為 root field，主 query 已成功代表 content 存在，
        故 reviewSummary is None 代表「此片無評分」→ 判定 True + 回傳 None
        （非「無法判定」）。

        Returns:
            average（0–5）；此片無評分或探測失敗時回傳 None。
        """
        global _review_supported

        # 已確認 schema 不支援 → 永久跳過（不再發 POST）
        if _review_supported is False:
            return None

        try:
            payload = {
                'query': self.REVIEW_PROBE_QUERY,
                'variables': {'contentId': content_id}
            }
            resp = self._session.post(self.API_URL, json=payload, timeout=5)

            if resp.status_code != 200:
                # HTTP 錯誤 → 暫時性失敗，維持 None（不設 False）
                return None

            resp_json = resp.json()
            errors = resp_json.get('errors', [])

            # 判定 1：schema error → 確認不支援，永久停用
            if any(
                any(pat in (e.get('message', '') or '') for pat in self.SCHEMA_ERROR_PATTERNS)
                for e in errors
            ):
                _review_supported = False
                logger.info("[DMM] GraphQL schema 不支援 reviewSummary，已永久停用 probe")
                return None

            # 判定 2：正常回應 → schema 支援
            data = resp_json.get('data') or {}
            summary = data.get('reviewSummary')

            # content 一定存在（主 query 已成功），summary is None 代表此片無評分
            _review_supported = True

            if summary is None:
                return None

            average = summary.get('average')
            if average is None:
                return None
            return float(average)

        except Exception:
            # 網路錯誤、timeout → 暫時性失敗，維持 None（不設 False）
            return None

    def _fetch_tags_from_html(self, content_id: str) -> list[str]:
        """
        從 DMM 商品頁 HTML 抓取 genres（ジャンル）。
        使用同一 session（代理由 proxy policy 決定），傳 age_check_done=1 cookie 繞過年齡驗證。

        兩種解析策略：
        1. JSON-LD VideoObject.genre（較快）
        2. XPath ジャンル 欄（備援）

        Returns:
            tags list（失敗時回傳 []，不 raise）
        """
        url = f"https://www.dmm.co.jp/digital/videoa/-/detail/=/cid={content_id}/"
        try:
            resp = self._session.get(
                url,
                timeout=self.config.timeout,
                cookies={"age_check_done": "1"}
            )
            if resp.status_code != 200:
                return []

            from lxml import etree
            import json as _json

            html = etree.fromstring(resp.content, etree.HTMLParser())

            # 方法 1: JSON-LD VideoObject.genre
            for script in html.xpath('//script[@type="application/ld+json"]/text()'):
                try:
                    ld = _json.loads(script)
                    if isinstance(ld, dict) and ld.get('@type') == 'VideoObject':
                        genre = ld.get('genre')
                        if genre and isinstance(genre, list):
                            return [g for g in genre if isinstance(g, str)]
                except _json.JSONDecodeError:
                    continue

            # 方法 2: XPath ジャンル 表格欄
            tags = html.xpath(
                '//th[contains(.//text(),"ジャンル")]/following-sibling::td//a/text()'
            )
            return [t.strip() for t in tags if t.strip()]

        except Exception:
            return []

    # ========== 前綴映射 ==========

    def _prefix_map(self) -> dict:
        """讀出貨前綴表（只讀、不寫）。"""
        global _shipped_table_cache

        # 出貨表：process 內讀一次；缺席／壞 JSON／缺 makers → 空表（D1）
        if _shipped_table_cache is None:
            try:
                if not SHIPPED_TABLE_FILE.exists():
                    logger.warning(
                        "dmm_prefix_table.json 不存在，視為空表繼續"
                    )
                    _shipped_table_cache = {}
                else:
                    raw = json.loads(
                        SHIPPED_TABLE_FILE.read_text(encoding="utf-8")
                    )
                    if "makers" not in raw:
                        logger.warning(
                            "dmm_prefix_table.json 缺少 makers 鍵，視為空表繼續"
                        )
                        _shipped_table_cache = {}
                    else:
                        # 撞名 ValueError 不得在此吞掉（D2）
                        _shipped_table_cache = _flatten_shipped_table(raw)
            except (json.JSONDecodeError, OSError, AttributeError, TypeError) as e:
                # AttributeError/TypeError：JSON 語法合法但形狀不對（makers 是
                # null/list、片商底下不是 dict、entry 不是 mapping…）。這些同樣屬
                # D1「出貨表是加分項不是必要條件」的範圍——出貨表壞掉只該讓它失效，
                # 不該讓整支 DMM 來源在每次搜尋時噴例外（search() 步驟 1 沒有接例外）。
                # ⚠️ 不含 ValueError：撞名必須逃出去（D2），且 JSONDecodeError 是
                # ValueError 的子類、已單獨列在前面，順序不可調換。
                logger.warning(
                    "dmm_prefix_table.json 讀取失敗，視為空表繼續：%s", e
                )
                _shipped_table_cache = {}

        shipped = _shipped_table_cache

        # 只取 dmm_prefix 字串（sample 不得外洩）
        # 非字串值一律丟棄（不是改成 ""）——丟掉之後 .get(prefix, "") 自然
        # 退回「預設規則」。出貨表那半另有 test_hit_rate 守著。
        merged = {
            p: e["dmm_prefix"]
            for p, e in shipped.items()
            if isinstance(e.get("dmm_prefix"), str)
        }
        return merged

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

    def _convert_with_hints(self, number: str, zfill: bool = True) -> str:
        """
        用前綴映射轉換番號

        Examples:
            SONE-205 + hints={} → sone00205
            STARS-804 + hints={"stars": "1"} → 1stars00804
            MIDD-357 + zfill=False → midd357
        """
        prefix, num = self._parse_number(number)
        if not prefix or not num:
            return ""

        # 數字補零到 5 位（zfill=False 時保留原樣，供步驟 1 的第二試）
        num_padded = num.zfill(5) if zfill else num

        # 查前綴映射
        hints = self._prefix_map()
        dmm_prefix = hints.get(prefix, "")

        return f"{dmm_prefix}{prefix}{num_padded}"

    def _number_matches(self, video_number: str, input_number: str) -> bool:
        """比對 Video.number（makerContentId）與輸入番號是否為同一片。

        兩邊都丟進 _parse_number()，比較 (prefix, num.lstrip("0") or "0")。
        任一側解析不出來即視同不符。
        """
        vp, vn = self._parse_number(video_number)
        ip, in_ = self._parse_number(input_number)
        if not vp or not vn or not ip or not in_:
            return False
        return (vp, vn.lstrip("0") or "0") == (ip, in_.lstrip("0") or "0")

    def _number_conflicts(self, video_number: str, input_number: str) -> bool:
        """**不對稱**版本：只有「兩邊都解析得出來、而且不同」才算衝突。

        與 `_number_matches` 的差別就在解析不出來的那一半：
        `_number_matches` 回 False（＝不採用），這支回 False（＝不拒絕）。

        Why 要兩支：DMM 的 `makerContentId` 常常是分片番號（`MCSR-042-01`）
        或異形（`OLM-343M`），解析不出來是常態、不是異常。步驟 1 若用嚴格版，
        那批全部會被誤擋；若完全不驗，`OTHER-999` 這種明顯是別部片的也會被
        寫進 NFO（`core/enricher.py` 那一層不比對番號）。不對稱版兩邊都要。
        """
        vp, vn = self._parse_number(video_number)
        ip, in_ = self._parse_number(input_number)
        if not vp or not vn or not ip or not in_:
            return False  # 解析不出來 → 不拒絕（這就是「不對稱」）
        return (vp, vn.lstrip("0") or "0") != (ip, in_.lstrip("0") or "0")

    def _content_id_to_number(self, content_id: str) -> str:
        """
        從 content_id 推導標準番號格式。

        DMM content_id 固定 5 位數字零補位（zfill(5)）。
        反向推導時 strip leading zeros 但保留至少 3 位數字。

        Examples:
            sone00205   → SONE-205
            1stars00804 → STARS-804
            ssni00001   → SSNI-001
            ofje00709   → OFJE-709
            abp01234    → ABP-1234
        """
        m = re.match(r'^(\d*)([a-z]+)(\d+)$', content_id.lower())
        if m:
            alpha = m.group(2).upper()
            num = m.group(3)
            # Strip leading zeros but keep at least 3 digits
            stripped = num.lstrip('0') or '0'
            if len(stripped) < 3 and len(num) >= 3:
                stripped = num[-3:]
            return f"{alpha}-{stripped}"
        return content_id

    def _search_content_id(self, number: str) -> Optional[str]:
        """
        用搜索 API 查找正確的 content_id（MDCX 方法）
        """
        prefix, num = self._parse_number(number)

        if not prefix:
            return None

        query_word = f"{prefix.upper()} {num}"

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
                raise SourceBlocked(f"DMM: HTTP {resp.status_code}")

            data = resp.json()
            if not data.get('data') or not data['data'].get('legacySearchPPV'):
                return None

            contents = data['data']['legacySearchPPV']['result']['contents']
            if not contents:
                return None

            # 找系列段精確匹配番號前綴的結果（防誤學：搜 ERK-116 不應命中 gerk116，
            # 搜 ID-xxx 不應命中 midv 系）。結構 {dmm_prefix}{series}{num}，series 段
            # 必須 == prefix；找不到精確匹配 → 返回 None（不盲取第一個，避免誤刮）。
            for content in contents:
                cid = content['id']
                m = re.match(
                    r'^((?:h_\d+)|(?:\d+))?([a-z]+)(\d+)$',
                    cid.lower()
                )
                if m and m.group(2) == prefix:
                    return cid

            # 沒找到精確匹配 → 返回 None（原邏輯 return contents[0]['id'] 會誤刮
            # 子串相近的其他系列，例如 ERK-116 → gerk116）
            return None

        except (SourceBlocked, SourceUnreachable):
            raise
        except requests.exceptions.JSONDecodeError:
            return None  # 200 但 body 非 JSON：查無，不是連不到
        except requests.RequestException as e:
            raise SourceUnreachable(f"DMM: {type(e).__name__}") from e
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
                raise SourceBlocked(f"DMM: HTTP {response.status_code}")

            data = response.json()

            if not data.get('data') or not data['data'].get('ppvContent'):
                return None

            item = data['data']['ppvContent']

            actresses = [
                Actress(name=a['name'])
                for a in item.get('actresses', [])
            ]

            release_date = item.get('makerReleasedAt') or ''
            if release_date and 'T' in release_date:
                release_date = release_date.split('T')[0]

            # T5a: GraphQL probe → T5b: HTML fallback
            tags, label = self._probe_genres(content_id)
            if not tags:
                tags = self._fetch_tags_from_html(content_id)

            sample_images = self._probe_sample_images(content_id)

            rating = self._probe_review(content_id)

            # 新欄位提取
            directors_list = item.get('directors') or []
            director = directors_list[0]['name'] if directors_list else ''

            raw_duration = item.get('duration')
            duration = raw_duration // 60 if raw_duration is not None else None

            series = (item.get('series') or {}).get('name', '')

            # null 防護：amateur 等內容的 largeUrl/makerReleasedAt 可能為 null，
            # 直接傳 None 給 pydantic str 欄位會 ValidationError（被 except 吞掉→整片失敗）。
            # 統一 or '' 歸一為空串；title 不加防護（內容標識保險絲，為空寧可失敗）。
            cover_url = (item.get('packageImage') or {}).get('largeUrl') or ''
            # amateur 封面兜底：老式無前綴 cid（如 erk116）無 largeUrl，
            # 但 DMM 封面有規律 {cid}jp.jpg（digital/amateur 目錄，1458×1458 方形）。
            # 帶前綴新 cid（hpet/hoip/herk 等）走 digital/video 目錄、largeUrl 有值，不觸發。
            if not cover_url and re.match(r'^[a-z]+\d+$', content_id):
                cover_url = (f"https://awsimgsrc.dmm.co.jp/pics_dig/digital/amateur/"
                             f"{content_id}/{content_id}jp.jpg")

            video = Video(
                number=item.get('makerContentId', ''),
                title=item.get('title', ''),
                actresses=actresses,
                date=release_date,
                maker=item.get('maker', {}).get('name', ''),
                cover_url=cover_url,
                tags=tags,
                source=self.source_name,
                detail_url=f"https://www.dmm.co.jp/digital/videoa/-/detail/=/cid={content_id}/",
                director=director,
                duration=duration,
                label=label,
                series=series,
                sample_images=sample_images,
                summary=item.get('description') or '',
                rating=rating,
            )

            return video

        except (SourceBlocked, SourceUnreachable):
            raise
        except requests.exceptions.JSONDecodeError:
            return None  # 200 但 body 非 JSON：查無，不是連不到
        except requests.RequestException as e:
            raise SourceUnreachable(f"DMM: {type(e).__name__} (detail)") from e
        except Exception:
            return None

    # ========== 主要搜尋方法 ==========

    def search(self, number: str) -> Optional[Video]:
        """
        搜尋影片資訊

        流程：
        1. 用前綴映射轉換 → 嘗試查詢（快）
        2. 搜索 API 發現 → 嘗試查詢（慢）
        3. 使用者直接提供完整 cid 兜底
        4. 都失敗 → 返回 None

        Args:
            number: 番號（如 SONE-205）

        Returns:
            Video 物件，找不到返回 None
        """
        # 正規化番號（保留原始輸入，供第 3 步 cid 直拉兜底使用）
        raw_input = number.strip()
        number = self.normalize_number(number)
        number_upper = number.upper()

        # 不支援 FC2
        if 'FC2' in number_upper:
            return None

        # 1. 用前綴映射轉換（快）
        converted_cid = self._convert_with_hints(number)
        if converted_cid:
            result = self._fetch_by_id(converted_cid)
            if result and not self._number_conflicts(result.number, number):
                # 不對稱守衛（2026-08-29 branch review P3）：只擋「解析得出來且不符」，
                # 解析不出來照舊接受。CD-134-11 的 320 命中是**離線算式**、不經過
                # 這條路，所以不受影響；實測 24 筆真連線裡 0 筆會被這條擋掉。
                rate_limit(self.config.delay)
                return result

            # 第一試失敗才試不補零第二試；兩式相同就不重複發請求
            unpadded_cid = self._convert_with_hints(number, zfill=False)
            if unpadded_cid and unpadded_cid != converted_cid:
                second_result = self._fetch_by_id(unpadded_cid)
                if second_result and self._number_matches(second_result.number, number):
                    rate_limit(self.config.delay)
                    return second_result
                # 驗證失敗或未命中 → 不回傳、不加 log，靜靜落到步驟 2

        # 2. 搜索 API 發現（慢）
        discovered_cid = self._search_content_id(number)
        if discovered_cid:
            result = self._fetch_by_id(discovered_cid)
            if result and self._number_matches(result.number, number):
                rate_limit(self.config.delay)
                return result
            # 驗證失敗仍屬 discovered_cid 有值分支，不會落到 elif，F5 不會被誤觸
        elif self._parse_number(number)[0]:
            # 只在「番號可解析 ⇒ _search_content_id 真的發了 API」時留痕。
            # 輸入是完整 cid（h_113id00057）時它在發請求前就 return None，
            # 此時印「可能是地區限制」是假話——那條路接著會被步驟 3 救回來。
            #
            # legacySearchPPV 在非日本 IP 下回 HTTP 200 + 空陣列 + 無 errors，
            # 「DMM 沒收這片」與「被地區封鎖」在 log 裡長得一模一樣 → 只留痕，不宣稱能分辨。
            logger.debug(
                "[DMM] 搜尋 API 查無結果，番號=%s（可能是 DMM 未收錄，也可能是地區限制——見 spec-134 F5）",
                number_upper,
            )

        # 3. 使用者直接提供完整 cid 兜底（如 h_113id00057）
        #    - 觸發條件：輸入無法解析為標準番號（非 ABC-123 格式）
        #    - GraphQL 對 cid 大小寫敏感且僅認小寫 → 統一轉小寫
        prefix, _ = self._parse_number(raw_input)
        if not prefix:
            result = self._fetch_by_id(raw_input.lower())
            if result:
                rate_limit(self.config.delay)
                return result

        # 4. 完全失敗
        return None

    def search_by_keyword_with_ids(self, keyword: str, limit: int = 20, offset: int = 0) -> list[tuple[str, Video]]:
        """
        關鍵字搜尋（輕量版）— 回傳 (content_id, shallow_Video) tuples。
        供 facade 層 ThreadPoolExecutor enrichment 使用。
        不呼叫 _fetch_by_id（不做 enrichment）。
        """
        try:
            payload = {
                'query': self.SEARCH_LIST_QUERY,
                'variables': {
                    'limit': limit,
                    'offset': offset,
                    'sort': 'RELEASE_DATE',
                    'queryWord': keyword,
                }
            }
            response = self._session.post(
                self.API_URL,
                json=payload,
                timeout=self.config.timeout,
            )

            if response.status_code != 200:
                return []

            data = response.json()
            if not data.get('data') or not data['data'].get('legacySearchPPV'):
                return []

            contents = data['data']['legacySearchPPV']['result']['contents']
            if not contents:
                return []

            pairs = []
            for item in contents:
                content_id = item.get('id', '')
                if not content_id:
                    continue
                actresses = [
                    Actress(name=a['name'])
                    for a in (item.get('actresses') or [])
                    if a.get('name')
                ]
                video = Video(
                    number=self._content_id_to_number(content_id),
                    title=item.get('title', ''),
                    actresses=actresses,
                    maker=(item.get('maker') or {}).get('name', ''),
                    cover_url=(item.get('packageImage') or {}).get('largeUrl', ''),
                    source=self.source_name,
                    detail_url=f"https://www.dmm.co.jp/digital/videoa/-/detail/=/cid={content_id}/",
                )
                pairs.append((content_id, video))

            return pairs

        except Exception:
            return []

    def search_by_keyword(self, keyword: str, limit: int = 20, offset: int = 0) -> list[Video]:
        """關鍵字搜尋（女優名、片商名等日文關鍵字）"""
        try:
            payload = {
                'query': self.SEARCH_LIST_QUERY,
                'variables': {
                    'limit': limit,
                    'offset': offset,
                    'sort': 'RELEASE_DATE',
                    'queryWord': keyword,
                }
            }
            response = self._session.post(
                self.API_URL,
                json=payload,
                timeout=self.config.timeout,
            )

            if response.status_code != 200:
                return []

            data = response.json()
            if not data.get('data') or not data['data'].get('legacySearchPPV'):
                return []

            contents = data['data']['legacySearchPPV']['result']['contents']
            if not contents:
                return []

            results = []
            for item in contents:
                content_id = item.get('id', '')
                if not content_id:
                    continue

                # Enrichment: 逐筆 _fetch_by_id 取得完整 Video
                try:
                    video = self._fetch_by_id(content_id)
                except Exception:
                    video = None
                if video is None:
                    # Fallback: 從搜尋結果建構 shallow Video
                    actresses = [
                        Actress(name=a['name'])
                        for a in (item.get('actresses') or [])
                        if a.get('name')
                    ]
                    video = Video(
                        number=self._content_id_to_number(content_id),
                        title=item.get('title', ''),
                        actresses=actresses,
                        maker=(item.get('maker') or {}).get('name', ''),
                        cover_url=(item.get('packageImage') or {}).get('largeUrl', ''),
                        source=self.source_name,
                        detail_url=f"https://www.dmm.co.jp/digital/videoa/-/detail/=/cid={content_id}/",
                    )
                results.append(video)
                rate_limit(self.config.delay)

            return results

        except Exception:
            return []
