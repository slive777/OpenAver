"""爬蟲共用工具"""
import re
import time
import requests
from typing import Optional

from core.logger import get_logger

logger = get_logger(__name__)


# 全域設定
DEFAULT_TIMEOUT = 15
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept-Language': 'ja-JP,ja;q=0.9,zh-TW;q=0.8,zh;q=0.7,en;q=0.6',
}


def get_html(url: str, timeout: int = DEFAULT_TIMEOUT,
             headers: Optional[dict[str, str]] = None, cookies: Optional[dict[str, str]] = None,
             proxies: Optional[dict] = None) -> Optional[str]:
    """
    GET 請求獲取 HTML

    Args:
        url: 目標 URL
        timeout: 超時秒數
        headers: 自訂 headers
        cookies: Cookies
        proxies: 代理（proxy policy 選中才傳；None = 不帶 kwarg）

    Returns:
        HTML 文本，失敗返回 None
    """
    try:
        h = DEFAULT_HEADERS.copy()
        if headers:
            h.update(headers)

        resp = requests.get(url, headers=h, cookies=cookies, timeout=timeout, **({'proxies': proxies} if proxies else {}))
        resp.encoding = resp.apparent_encoding

        if resp.status_code == 200:
            return resp.text
    except Exception as e:
        logger.debug(f"GET {url} failed: {e}")
    return None


def post_html(url: str, data: Optional[dict[str, object]] = None, timeout: int = DEFAULT_TIMEOUT,
              headers: Optional[dict[str, str]] = None, proxies: Optional[dict] = None) -> Optional[str]:
    """
    POST 請求獲取 HTML

    Args:
        url: 目標 URL
        data: POST 資料
        timeout: 超時秒數
        headers: 自訂 headers
        proxies: 代理（選中才傳）

    Returns:
        HTML 文本，失敗返回 None
    """
    try:
        h = DEFAULT_HEADERS.copy()
        if headers:
            h.update(headers)

        resp = requests.post(url, data=data, headers=h, timeout=timeout, **({'proxies': proxies} if proxies else {}))
        resp.encoding = resp.apparent_encoding

        if resp.status_code == 200:
            return resp.text
    except Exception as e:
        logger.debug(f"POST {url} failed: {e}")
    return None


# FC2 正典形式 FC2-<純數字> 的抓取樣式（139-T1b）：
# A（extract_number）／B（VideoScanner.NUM_PATTERNS）／H（normalize_number_impl）三處共用這一支。
# 任何一處都不得自己組 f"FC2-{...}" 字面（CD-2；散裝維護正是 BE-TEST-14 的假綠溫床）。
# 左邊界 (?<![A-Za-z0-9])：不加的話 re.search 會咬進別的 token 中間——
# 實測 'SONE-205fc21.mp4' 會從 SONE-205 變成 FC2-1、'notfc2-1234567' 變成 FC2-1234567
# （第 3 輪 review 由 grok/sonnet 各自獨立命中）。H 的 fullmatch 與 B 的 (.*[\W_])? 前綴
# 都不受這條影響（位置 0 或前一字元本來就是非英數）。
FC2_TOKEN_PATTERN = r'(?<![A-Za-z0-9])FC2[ \t　_-]*(?:PPV[ \t　_-]*)?(?P<fc2digits>\d+)'


def extract_number(filename: str) -> Optional[str]:
    """
    從檔名中提取番號

    Args:
        filename: 檔案名稱或路徑

    Returns:
        提取的番號（如 SONE-205），找不到返回 None

    Examples:
        >>> extract_number("SONE-205.mp4")
        'SONE-205'
        >>> extract_number("[JavBus] ABC-123 標題.mp4")
        'ABC-123'
        >>> extract_number("T28-103.mp4")
        'T28-103'
    """
    from pathlib import Path
    basename = Path(filename).stem

    # 預處理 - 清理常見後綴（需有分隔符，避免誤刪 JUC-123 等合法前綴）
    basename = re.sub(
        r'[-_](UC|UNCEN|UNCENSORED|LEAK|LEAKED)(?=[-_.\s]|$)',
        '', basename, flags=re.IGNORECASE
    )

    patterns = [
        rf'(?P<fc2>{FC2_TOKEN_PATTERN})',
        r'(\d{6}-\d{2,})',              # 041417-413 日期-編號格式（無碼）
        r'(\d{6}_\d{2,})',             # 120415_201 / 082912_01 底線格式（無碼）
        r'([A-Za-z]+\d+-\d+)',          # T28-103 混合格式
        r'\[([A-Za-z]{1,7}-\d{3,5})\]', # [ABC-123] 方括號
        r'([A-Za-z]{1,7}-\d{3,5})',     # ABC-123 帶橫線
        r'([A-Za-z]{2,7})(\d{3,5})',    # ABC12345 不帶橫線（index 6，兩 group → 插 hyphen）
        r'([nkcmsNKCMS]\d{4})(?!\d)',      # n0762 單字母 + 恰 4 位（Tokyo Hot 無碼，前綴限 n/k/c/m/s（spec-73 US2 權威模型），右側無更多數字）
        # 139c 若要恢復數字前綴保留是新設計，不是還原這條
    ]

    for i, pattern in enumerate(patterns):
        match = re.search(pattern, basename, re.IGNORECASE)
        if match:
            if i == 0:
                return normalize_number_impl(match.group('fc2'))
            elif i == 6:  # 不帶橫線需重組（ABC12345）
                number = f"{match.group(1).upper()}-{match.group(2)}"
            else:
                number = match.group(1).upper()
            return number
    return None


def rate_limit(delay: float = 0.3) -> None:
    """請求節流（避免被封禁）"""
    time.sleep(delay)


# ============================================================
# 文字檢測函數
# ============================================================

def has_japanese(text: str) -> bool:
    """
    檢測文字是否包含日文（平假名或片假名）

    Args:
        text: 待檢測的文字

    Returns:
        True 如果包含日文字符，否則 False

    Examples:
        >>> has_japanese("これはテスト")
        True
        >>> has_japanese("中文標題")
        False
    """
    if not text:
        return False
    for char in text:
        if '\u3040' <= char <= '\u309f':  # 平假名
            return True
        if '\u30a0' <= char <= '\u30ff':  # 片假名
            return True
    return False


def has_chinese(text: str) -> bool:
    """
    檢測文字是否包含中文

    Args:
        text: 待檢測的文字

    Returns:
        True 如果包含中文字符，否則 False

    Examples:
        >>> has_chinese("標題")
        True
        >>> has_chinese("Title")
        False
    """
    if not text:
        return False
    for char in text:
        if '\u4e00' <= char <= '\u9fff':
            return True
    return False


# 字幕 pattern 常數（單一真理來源，供 check_subtitle / strip_subtitle_markers 共用）
_SUBTITLE_PATTERNS_UPPER = ['-C', '_C']
_SUBTITLE_PATTERNS_CHINESE = ['中文字幕', '字幕', '中字', '[中字]', '【中字】']


def check_subtitle(filename: str) -> bool:
    """
    檢查檔名是否包含字幕標記

    支援的標記：
    - -C, -c, _C（常見字幕標記）
    - 中文字幕, 字幕, 中字, [中字], 【中字】

    Args:
        filename: 檔案名稱

    Returns:
        True 如果包含字幕標記，否則 False

    Examples:
        >>> check_subtitle("ABC-123-C.mp4")
        True
        >>> check_subtitle("[中文字幕] ABC-123.mp4")
        True
        >>> check_subtitle("ABC-123.mp4")
        False
    """
    if not filename:
        return False

    upper = filename.upper()

    for p in _SUBTITLE_PATTERNS_UPPER:
        idx = upper.find(p)
        if idx != -1:
            next_idx = idx + len(p)
            if next_idx >= len(upper) or not upper[next_idx].isalnum():
                return True

    for p in _SUBTITLE_PATTERNS_CHINESE:
        if p in filename:
            return True

    return False


def strip_subtitle_markers(name: Optional[str]) -> Optional[str]:
    """
    剝除片名中的字幕標記（bracket 形式、純文字形式、後綴形式）。

    剝除順序：
    1. Bracket 形式（先長後短，避免殘留括號）：[中文字幕]、【中文字幕】、[中字]、【中字】
    2. 純文字形式（詞根邊界 regex，避免誤剝「幕後」「字幕員」等複合詞）：
       中文字幕、中字、字幕（長 pattern 先）
    3. 後綴形式：[-_][Cc] 後接非英數邊界
    4. strip() 頭尾空白（不 collapse 中間空格）

    Args:
        name: 原始片名（可為 None 或空字串）

    Returns:
        剝除字幕標記後的片名。None / "" passthrough。

    Examples:
        >>> strip_subtitle_markers("[中字] ABC-123")
        'ABC-123'
        >>> strip_subtitle_markers("ABC-123-C")
        'ABC-123'
        >>> strip_subtitle_markers("字幕員特典")
        '字幕員特典'
    """
    if not name:
        return name

    # 1. Bracket 形式（長 pattern 先）
    for bracket in ['[中文字幕]', '【中文字幕】', '[中字]', '【中字】']:
        name = name.replace(bracket, '')

    # 2. 純文字形式（長 pattern 先，詞根邊界避免複合詞誤剝）
    for marker in ['中文字幕', '中字', '字幕']:
        name = re.sub(rf'(?<![^\W_]){re.escape(marker)}(?![^\W_])', '', name)

    # 2.5 marker 剝除後，清掉頭尾 orphan 的 -/_ 分隔符
    # 例如「正妹の中文版-中字」剝「中字」後留「正妹の中文版-」，尾端 `-` 是 orphan
    # 不動「-C/_C」組合 — 尾端 C 不匹配 [-_]+$
    name = re.sub(r'^[-_]+|[-_]+$', '', name)

    # 3. 後綴 -C / _C（後接非英數或字串結尾）
    name = re.sub(r'[-_][Cc](?=[^A-Za-z0-9]|$)', '', name)

    return name.strip()


def strip_number_prefix(title: str, number: str) -> str:
    """
    剝除片名開頭的番號前綴。

    Args:
        title: 原始片名（可能帶番號前綴，如 "START-424 市役所の..."）
        number: 番號（如 "START-424"）

    Returns:
        剝除番號前綴後的片名。title 為 None/空 → ""；number 為空 → 原 title。

    Examples:
        >>> strip_number_prefix("START-424 市役所の窓口勤務の...", "START-424")
        '市役所の窓口勤務の...'
        >>> strip_number_prefix("START424 市役所の窓口勤務の...", "START-424")
        '市役所の窓口勤務の...'
    """
    if not title:
        return ""
    if not number:
        return title

    # 先嘗試有 dash 形式（精確匹配），再嘗試無 dash 形式（備用）
    for candidate in (number, number.replace('-', '')):
        pattern = r'^\s*' + re.escape(candidate) + r'(?![A-Za-z0-9])\s*'
        result = re.sub(pattern, '', title, flags=re.IGNORECASE)
        if result != title:
            return result

    return title


def format_number(number: str) -> str:
    """
    格式化番號為標準格式

    Args:
        number: 原始番號

    Returns:
        標準化的番號（大寫、去空白）

    Examples:
        >>> format_number("sone-205")
        'SONE-205'
        >>> format_number("  ABC-123  ")
        'ABC-123'
    """
    if not number:
        return number
    return number.upper().strip()


def normalize_number_impl(number: str) -> str:
    """
    正規化番號（統一大寫、格式）— standalone 實作，無 I/O、無網路。

    BaseScraper.normalize_number 委派此函式；core.scraper.normalize_number
    module-level wrapper 同樣委派此函式，不再需要實例化 JavBusScraper。

    Args:
        number: 原始番號（可含空白、UC/UNCEN 後綴）

    Returns:
        正規化後的番號

    Examples:
        >>> normalize_number_impl("sone103")
        'SONE-103'
        >>> normalize_number_impl("n0762")
        'N0762'
        >>> normalize_number_impl("ABC-123-UC")
        'ABC-123'
        >>> normalize_number_impl("  SONE-103  ")
        'SONE-103'
    """
    number = number.strip()
    # 清理常見後綴（需有分隔符，避免誤刪 JUC-123 等合法前綴）
    number = re.sub(
        r'[-_](UC|UNCEN|UNCENSORED|LEAK|LEAKED)(?=[-_.\s]|$)',
        '', number, flags=re.IGNORECASE
    )
    number = number.upper()
    # FC2 正規化（139-T1b）：七種寫法全部收斂成 FC2-<純數字>
    fc2_match = re.fullmatch(FC2_TOKEN_PATTERN, number)
    if fc2_match:
        return f"FC2-{fc2_match.group('fc2digits')}"
    # 單字母 + 恰 4 位（如 N0762, K0150）→ Tokyo Hot 無碼番號，不插 hyphen
    if re.match(r'^[A-Z]\d{4}$', number):
        return number
    # ABC123 → ABC-123
    match = re.match(r'^([A-Z]+)(\d+)$', number)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return number


# ============================================================
# 來源配置常數
# ============================================================

# 分群常數（供 scraper.py / settings UI 使用）
CENSORED_SOURCES = ['dmm', 'javbus', 'jav321', 'javdb']
UNCENSORED_SOURCES = ['d2pass', 'heyzo', 'fc2', 'avsox']
PROXY_SOURCES = {'dmm'}  # 需要日本 IP 的來源

# 模糊候選池白名單（CL-1 / CD-plan-65-4 / TASK-65g）：javbus + dmm 兩源。
# 排除：AVSOX（無碼專用）、FC2/HEYZO/D2Pass（keyword=番號，非真模糊）、
# jav321（keyword 恆回空）、javdb（重複呼叫觸發 Cloudflare ban）。
FUZZY_SEARCH_SOURCES = ['javbus', 'dmm']

SOURCE_ORDER = CENSORED_SOURCES + UNCENSORED_SOURCES

# CD-70b-10：javlibrary 有碼 manual_only BETA。
# - 加入 CENSORED_SOURCES 讓 SourceConfig.is_censored（builtin 分支）查到，避免 L77 warning。
# - 不加入 SOURCE_ORDER（manual_only 不進 fan-out 排序；SOURCE_ORDER = 8-elem fan-out 順序）。
# - 不加入 FUZZY_SEARCH_SOURCES（CD-70b：exact-only）。
# - 必須在 SOURCE_ORDER 建立後才 append，否則 SOURCE_ORDER tuple 已含 javlibrary（污染 fan-out）。
CENSORED_SOURCES.append('javlibrary')
# CD-118a-1：fc-javten 無碼 manual_only BETA。鏡射 javlibrary 的 append 時機（SOURCE_ORDER 建立後）。
UNCENSORED_SOURCES.append('fc-javten')

SOURCE_NAMES = {
    'dmm': 'DMM',
    'javbus': 'JavBus',
    'jav321': 'Jav321',
    'javdb': 'JavDB',
    'd2pass': 'D2Pass',
    'heyzo': 'HEYZO',
    'fc2': 'FC2',
    'avsox': 'AVSOX',
    'javlibrary': 'JavLibrary',
    'fc-javten': 'FC2-javten',
}

# ============================================================
# Metatube 30-provider 分類常數（CD-63a-4）
# key 對齊 /v1/providers 原字串（大小寫敏感）
# ============================================================

METATUBE_CENSORED: set[str] = {  # 15 有碼
    'JavBus', 'FANZA', 'JAV321', 'DUGA', 'MGS', 'SOD', 'DAHLIA', 'FALENO',
    'TOKYO-HOT', 'AVE', 'HeyDouga', 'JAVFREE', 'Gcolle', 'Getchu', 'Pcolle',
}

METATUBE_UNCENSORED: set[str] = {  # 15 無碼
    'HEYZO', '1Pondo', 'Caribbeancom', 'CaribbeancomPR', 'FC2', 'FC2PPVDB', 'fc2hub',
    '10musume', 'C0930', 'H0930', 'H4610', 'MURAMURA', 'MYWIFE', 'PACOPACOMAMA', 'KIN8',
}

# 日期型無碼 provider（11 個）：METATUBE_UNCENSORED 去掉 HEYZO / FC2 / FC2PPVDB / fc2hub
# （後四者由 _get_uncensored_sources 的 fc2 / heyzo 前綴分支各自處理）。
# 用於 spec US4 staged promotion：日期型番號（d2pass 格式）prepend 這些 metatube 源（CD-63c-8）。
METATUBE_DATE_UNCENSORED: frozenset[str] = frozenset({
    'Caribbeancom', 'CaribbeancomPR', '1Pondo', '10musume',
    'C0930', 'H0930', 'H4610', 'MURAMURA', 'MYWIFE', 'PACOPACOMAMA', 'KIN8',
})

# 固定 canonical 順序：有碼 15（依序）+ 無碼 15（依序）= 30（CD-63a-5）
# JAV321/SOD/FC2PPVDB/KIN8 為已知失敗源，仍列入 order 使 builder 能正確排序
METATUBE_PROVIDER_ORDER: list[str] = [
    # 有碼 15
    'JavBus', 'FANZA', 'JAV321', 'DUGA', 'MGS', 'SOD', 'DAHLIA', 'FALENO',
    'TOKYO-HOT', 'AVE', 'HeyDouga', 'JAVFREE', 'Gcolle', 'Getchu', 'Pcolle',
    # 無碼 15
    'HEYZO', '1Pondo', 'Caribbeancom', 'CaribbeancomPR', 'FC2', 'FC2PPVDB', 'fc2hub',
    '10musume', 'C0930', 'H0930', 'H4610', 'MURAMURA', 'MYWIFE', 'PACOPACOMAMA', 'KIN8',
]


# ============================================================
# 整串番號判定（139-T1a）：C／D／G 三處判斷的單一事實來源
# ============================================================

# (regex, kind)；kind ∈ {'censored', 'uncensored'}
# 比對方式：對「已 strip + upper」的整串做 re.fullmatch。
# 為什麼要先 strip 才 fullmatch，不是直接對原字串套 ^...$ 錨定：
# 若不 strip，Python 的 $ 會放行結尾換行——'SONE-103\n' 這種輸入會被 ^...$ 誤判為合法番號。
# 先 .strip() 再 fullmatch 兩個問題一次解決：使用者從別處貼進來的番號帶前後空白/換行時
# （POSITIVE_SURROUNDING_WHITESPACE 覆蓋的情境）視為合法去除，'SONE-103\n' 本身因此正確判 True；
# 真正該擋的是「夾在字串中間」的換行（ALL_NEGATIVE 的 'SONE-103\nSSIS-001' 那類），
# strip 不動中間字元，fullmatch 對它仍然失敗。
_STRICT_NUMBER_PATTERNS = [
    # ❗FC2／HEYZO 這三條的數字同樣要求「至少 3 位」——理由與下面 censored 三條同源：
    # 1-2 位尾數是 is_partial_number（候選清單）的地盤。少了它，使用者打 HEYZO-12 想瀏覽系列時，
    # 會被判成完整番號而改走精準／無碼單片搜尋 → 候選清單消失、多半查無結果。
    # （真實 FC2 編號 6-7 位、HEYZO 4 位，3 位下限不會擋掉任何真番號。）
    (r'FC2[ \t　_-]*PPV[ \t　_-]*\d{3,}', 'uncensored'),   # FC2PPV-4943690 / FC2 PPV 4943690 / FC2-PPV-4943690
    (r'FC2[ \t　_-]*\d{3,}', 'uncensored'),             # FC2-4943690 / FC24943690
    (r'HEYZO[ \t　_-]*\d{3,}', 'uncensored'),           # HEYZO-1234 / heyzo1234（G 現況以 startswith('heyzo') 判無碼，收斂後不得漏）
    (r'\d{6}-\d{2,}', 'uncensored'),              # 020317-001 日期-編號（無碼）
    (r'\d{6}_\d{2,}', 'uncensored'),              # 090122_001 日期_編號（無碼）
    (r'[A-Z]\d{4}', 'uncensored'),                # N0762 單字母 + 恰 4 位（東京熱）
    (r'\d{1,4}[A-Z]+-\d{3,}', 'censored'),        # 200GANA-3360 / 529STCV-152 / 7IPZ-154 數字前綴
    (r'[A-Z]+\d+-\d{3,}', 'censored'),            # T28-103 混合
    (r'[A-Z]+-?\d{3,}', 'censored'),              # SONE-205 / SONE205 一般（hyphen 可省、至少 3 位——
                                                  # 與舊 is_number_format 的 ^[a-zA-Z]+-?\d{3,}$ 邊界逐字對齊。
                                                  # 1-2 位數是「部分番號」的地盤，故意不收：那條路要給候選清單）
]


def is_strict_number(s: str) -> bool:
    """判斷輸入字串是否為整串合法番號。

    空字串 / None 回傳 False。
    前置正規化 s.strip().upper() 後對 _STRICT_NUMBER_PATTERNS 整表做 re.fullmatch 比對，任一命中即 True。
    """
    if not s or not isinstance(s, str):
        return False
    normalized = s.strip().upper()
    if not normalized:
        return False
    for pattern, _ in _STRICT_NUMBER_PATTERNS:
        if re.fullmatch(pattern, normalized):
            return True
    return False


def is_strict_uncensored_number(s: str) -> bool:
    """判斷輸入字串是否為整串合法無碼番號。

    空字串 / None 回傳 False。
    前置正規化 s.strip().upper() 後只對 _STRICT_NUMBER_PATTERNS 中 kind == 'uncensored' 的子集做 re.fullmatch 比對，任一命中即 True。
    """
    if not s or not isinstance(s, str):
        return False
    normalized = s.strip().upper()
    if not normalized:
        return False
    for pattern, kind in _STRICT_NUMBER_PATTERNS:
        if kind == 'uncensored' and re.fullmatch(pattern, normalized):
            return True
    return False


# D 專用寬表（139-T8，CD-b2）：strict 表 ∪ 短尾碼（1-2 位）。
# 不供 C／G 使用——C 的 ≥3 位下限是刻意的（1-2 位要留給 is_partial_number 給候選清單），
# D 只是「送去查之前的格式衛生檢查」，不該替 C 做路由決定。
_LENIENT_NUMBER_PATTERN = r'[A-Z]+\d*-\d{1,2}'   # 有 hyphen 且尾碼 1-2 位（HITMA-16 / T28-10）


def is_lenient_number(s: str) -> bool:
    """D 專用：is_strict_number(s) 或符合 _LENIENT_NUMBER_PATTERN（短尾碼）。

    空字串 / None 回傳 False。前置正規化與 is_strict_number 一致（s.strip().upper()）。
    """
    if not s or not isinstance(s, str):
        return False
    normalized = s.strip().upper()
    if not normalized:
        return False
    if is_strict_number(normalized):
        return True
    return bool(re.fullmatch(_LENIENT_NUMBER_PATTERN, normalized))


def is_uncensored_route(s: str) -> bool:
    """G 專用：判斷是否應走無碼搜尋路由（139-T9，CD-b3 拍板①）。

    條件集＝舊 G 語意（FC2 兩條 ＋ HEYZO 一條 ＋ 日期式兩條），刻意排除
    [A-Z]\\d{4}（那是 C 的無碼判定範疇，不該連帶把路由也搶走，見 CD-b3 放寬方向）。
    呼叫端須先用 resolve_route_target() 把輸入變乾淨再傳進來（CD-b3 拍板② B＋）；
    本函式自己不做尾綴剝除或前綴寬鬆比對。空字串 / None 回傳 False。
    """
    if not s or not isinstance(s, str):
        return False
    normalized = s.strip().upper()
    if not normalized:
        return False
    if re.fullmatch(r'FC2[ \t　_-]*PPV[ \t　_-]*\d{3,}', normalized):
        return True
    if re.fullmatch(r'FC2[ \t　_-]*\d{3,}', normalized):
        return True
    if re.fullmatch(r'HEYZO[ \t　_-]*\d{3,}', normalized):
        return True
    if re.fullmatch(r'\d{6}-\d{2,}', s.strip()):
        return True
    if re.fullmatch(r'\d{6}_\d{2,}', s.strip()):
        return True
    return False


def resolve_route_target(q: str) -> str:
    """G／C 路由決策前的共用前處理（139-T9，CD-b3 B＋ 對稱修法）。

    對輸入跑一次 extract_number()，只有抽出的結果本身也通過 is_strict_number()
    才採用為 candidate；沒有合格候選則原樣回傳輸入字串。

    那道 is_strict_number 閘不得省略，但**它的見證形狀不是 '2024'**——
    extract_number('2024') 回 None，candidate 在進閘之前就已經是 None，
    拿它驗閘會得到假綠（Codex plan review 第四輪抓到的錯，139-T9 卡片 D3）。
    真正會被閘擋下來的是「抽得出、但 is_strict_number 判 False」的輸入，
    實測全庫只有 FC2 短尾這一類：
        extract_number('fc2 12') -> 'FC2-12'，is_strict_number('FC2-12') -> False
    ⇒ 閘在守的是「resolve_route_target('fc2 12') 必須回原字串 'fc2 12'」。
    ('2024' / 'VR 8K' / 女優名那批鎖的是「本來就不該被抽出」，是另一件事。)

    呼叫端注意：partial() / prefix() 判斷不得使用本函式的回傳值，仍須用原字串 q
    （CD-b3 證據 C：這是設計的一部分，不是巧合）。
    """
    raw = q.strip() if isinstance(q, str) else q
    if raw and is_strict_number(raw):
        # 🔴 原字串本身已經是完整番號 → 直接用它，**不得**拿 A 的抽取結果覆寫。
        # 少了這道閘，數字前綴番號會被 A 的 ([A-Za-z]{1,7}-\d{3,5}) 咬掉前綴：
        #     200GANA-3360 -> GANA-3360、259LUXU-1234 -> LUXU-1234、7IPZ-154 -> IPZ-154
        # 而那三種正是 0.15.7 CHANGELOG 明文承諾「現在會走精準搜尋」的形狀
        # ——會路由到 exact，但查的是另一個番號。（grok-4.6 branch review 抓到，139-T9 第 3 輪）
        # A 的職責是「從一堆雜訊裡挖出番號」，C 已經承認整串就是番號時，A 沒有發言權。
        return raw
    n = extract_number(q)
    candidate = n if (n and is_strict_number(n)) else None
    return candidate or q


