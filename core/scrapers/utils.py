"""爬蟲共用工具"""
import logging
import re
import time
import requests
from typing import Optional

logger = logging.getLogger(__name__)


# 全域設定
DEFAULT_TIMEOUT = 15
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept-Language': 'ja-JP,ja;q=0.9,zh-TW;q=0.8,zh;q=0.7,en;q=0.6',
}


def get_html(url: str, timeout: int = DEFAULT_TIMEOUT,
             headers: Optional[dict[str, str]] = None, cookies: Optional[dict[str, str]] = None) -> Optional[str]:
    """
    GET 請求獲取 HTML

    Args:
        url: 目標 URL
        timeout: 超時秒數
        headers: 自訂 headers
        cookies: Cookies

    Returns:
        HTML 文本，失敗返回 None
    """
    try:
        h = DEFAULT_HEADERS.copy()
        if headers:
            h.update(headers)

        resp = requests.get(url, headers=h, cookies=cookies, timeout=timeout)
        resp.encoding = resp.apparent_encoding

        if resp.status_code == 200:
            return resp.text
    except Exception as e:
        logger.debug(f"GET {url} failed: {e}")
    return None


def post_html(url: str, data: Optional[dict[str, object]] = None, timeout: int = DEFAULT_TIMEOUT,
              headers: Optional[dict[str, str]] = None) -> Optional[str]:
    """
    POST 請求獲取 HTML

    Args:
        url: 目標 URL
        data: POST 資料
        timeout: 超時秒數
        headers: 自訂 headers

    Returns:
        HTML 文本，失敗返回 None
    """
    try:
        h = DEFAULT_HEADERS.copy()
        if headers:
            h.update(headers)

        resp = requests.post(url, data=data, headers=h, timeout=timeout)
        resp.encoding = resp.apparent_encoding

        if resp.status_code == 200:
            return resp.text
    except Exception as e:
        logger.debug(f"POST {url} failed: {e}")
    return None


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
        r'(FC2-PPV-\d+)',               # FC2-PPV-1234567
        r'(\d{6}-\d{3,})',              # 041417-413 日期-編號格式（無碼）
        r'(\d{6}_\d{2,3})',             # 120415_201 / 082912_01 底線格式（無碼）
        r'([A-Za-z]+\d+-\d+)',          # T28-103 混合格式
        r'\[([A-Za-z]{1,6}-\d{3,5})\]', # [ABC-123] 方括號
        r'([A-Za-z]{1,6}-\d{3,5})',     # ABC-123 帶橫線
        r'([A-Za-z]{2,6})(\d{3,5})',    # ABC12345 不帶橫線
        r'(\d{3}[A-Za-z]{3,4}-?\d{3,4})', # 123ABC-456 或 123ABC456
    ]

    for i, pattern in enumerate(patterns):
        match = re.search(pattern, basename, re.IGNORECASE)
        if match:
            if i == 6:  # 不帶橫線需重組（ABC12345）
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
    patterns_upper = ['-C', '_C']
    patterns_chinese = ['中文字幕', '字幕', '中字', '[中字]', '【中字】']

    for p in patterns_upper:
        idx = upper.find(p)
        if idx != -1:
            next_idx = idx + len(p)
            if next_idx >= len(upper) or not upper[next_idx].isalnum():
                return True

    for p in patterns_chinese:
        if p in filename:
            return True

    return False


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


# ============================================================
# 來源配置常數
# ============================================================

SOURCE_ORDER = ['javbus', 'jav321', 'javdb', 'fc2', 'avsox']

SOURCE_NAMES = {
    'javbus': 'JavBus',
    'jav321': 'Jav321',
    'javdb': 'JavDB',
    'fc2': 'FC2',
    'avsox': 'AVSOX'
}
