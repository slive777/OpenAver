"""爬蟲共用工具"""
import re
import time
import requests
from typing import Optional


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
    except Exception:
        pass
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
    except Exception:
        pass
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

    patterns = [
        r'(FC2-PPV-\d+)',               # FC2-PPV-1234567
        r'([A-Za-z]+\d+-\d+)',          # T28-103 混合格式
        r'\[([A-Za-z]{1,6}-\d{3,5})\]', # [ABC-123] 方括號
        r'([A-Za-z]{1,6}-\d{3,5})',     # ABC-123 帶橫線
        r'([A-Za-z]{2,6})(\d{3,5})',    # ABC12345 不帶橫線
        r'(\d{3}[A-Za-z]{3,4}-?\d{3,4})', # 123ABC-456 或 123ABC456
    ]

    for i, pattern in enumerate(patterns):
        match = re.search(pattern, basename, re.IGNORECASE)
        if match:
            if i == 4:  # 不帶橫線需重組
                number = f"{match.group(1).upper()}-{match.group(2)}"
            else:
                number = match.group(1).upper()
            return number
    return None


def rate_limit(delay: float = 0.3) -> None:
    """請求節流（避免被封禁）"""
    time.sleep(delay)
