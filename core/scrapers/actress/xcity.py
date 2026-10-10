"""xcity.jp actress profile scraper."""

import re
from typing import Dict, Optional
from urllib.parse import quote, urlparse

import requests
from bs4 import BeautifulSoup

from core.logger import get_logger
from core.proxy_policy import proxy_kwargs


logger = get_logger(__name__)

HEADERS = {
    "User-Agent": "OpenAver-research/1.0 (https://github.com/; research)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en;q=0.8",
}


def _find_exact_match(html: str, name: str) -> Optional[str]:
    """Return the first result whose title attribute equals the requested name."""
    try:
        soup = BeautifulSoup(html, "html.parser")
        for link in soup.select('a[href][title]'):
            title = link.get("title")
            match = re.fullmatch(r"(?:/idol/)?detail/(\d+)/", link.get("href", ""))
            if not match:
                continue
            if title == name:
                return match.group(1)
    except Exception:
        logger.exception("[xcity] Search result parse failed")
    return None


def _parse_xcity_detail_html(html: str, name: str) -> Optional[Dict]:
    """Parse a detail page without making a network request."""
    try:
        soup = BeautifulSoup(html, "html.parser")
        heading = soup.select_one("#avidolDetails h1")
        h1_text = heading.get_text(strip=True) if heading else ""
    except Exception:
        logger.exception("[xcity] Detail parse failed for %s", name)
        return None
    if not h1_text:
        return None

    try:
        result: Dict = {"name_ja": name}
        hobby = ""
        special_skill = ""
        for dd in soup.select("#avidolDetails dl.profile dd"):
            label_node = dd.select_one("span.koumoku")
            if label_node is None:
                continue
            label = label_node.get_text(strip=True)
            value = dd.get_text(strip=True)
            if not value.startswith(label):
                continue
            value = value[len(label):].strip()

            if label == "生年月日":
                match = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", value)
                if match:
                    year, month, day = match.groups()
                    result["birth"] = f"{year}-{int(month):02d}-{int(day):02d}"
            elif label == "血液型":
                if value and not value.startswith("-"):
                    result["blood"] = value
            elif label == "出身地":
                if value:
                    result["hometown"] = value
            elif label == "身長":
                match = re.search(r"(\d+)\s*cm", value)
                if match:
                    result["height"] = f"{match.group(1)}cm"
            elif label == "サイズ":
                bust = re.search(r"B\s*(\d+)(?:\s*\(\s*([A-Z]+)(?:-\d+)?\s*\))?", value)
                waist = re.search(r"W\s*(\d+)", value)
                hip = re.search(r"H\s*(\d+)", value)
                if bust:
                    result["bust"] = f"{bust.group(1)}cm"
                    if bust.group(2):
                        result["cup"] = bust.group(2)
                if waist:
                    result["waist"] = f"{waist.group(1)}cm"
                if hip:
                    result["hip"] = f"{hip.group(1)}cm"
            elif label == "趣味":
                hobby = value
            elif label == "特技":
                special_skill = value

        hobby_parts = [part for part in (hobby.strip(), special_skill.strip()) if part]
        if hobby_parts:
            result["hobby"] = "、".join(hobby_parts)

        photo = soup.select_one("#avidolDetails img.actressThumb[src]")
        if photo:
            src = photo.get("src", "").strip()
            if src.startswith("//"):
                src = "https:" + src
            # xcity 用一張共用的 "No Image" GIF 頂替沒有照片的女優（如 idol 11000/12000）；
            # 這張佔位圖不是她的照片，過濾掉比留著「有 photo_url 但其實是無圖示」更正確。
            if src and urlparse(src).path != "/actress/large/image/noimage.gif":
                result["photo_url"] = src

        # 除了 name_ja（呼叫端傳入的查詢名，非本頁解析所得）以外，本頁完全沒有任何
        # 可用資料（無文字欄位、無真實照片）——視同沒找到，讓 orchestrator 的
        # any(sources.values()) 判斷不被這種「有頁面但無內容」的空殼字典擋住，
        # 本地封面裁圖 fallback（TASK-122-T10）才有機會跑。
        if len(result) <= 1:
            return None
        return result
    except Exception:
        logger.exception("[xcity] Detail parse failed for %s", name)
        return None


def scrape_xcity(name: str) -> Optional[Dict]:
    """Fetch an exact xcity match and return its parsed profile, or None."""
    search_url = f"https://xcity.jp/idol/?genre=%2Fidol%2F&q={quote(name)}&sg=idol"
    try:
        search = requests.get(search_url, headers=HEADERS, timeout=15, **proxy_kwargs('actress'))
        if search.status_code != 200:
            return None
        actress_id = _find_exact_match(search.text, name)
        if actress_id is None:
            return None
        detail = requests.get(
            f"https://xcity.jp/idol/detail/{actress_id}/", headers=HEADERS, timeout=15,
            **proxy_kwargs('actress'),
        )
        if detail.status_code != 200:
            return None
        return _parse_xcity_detail_html(detail.text, name)
    except requests.RequestException:
        logger.exception("[xcity] Request failed for %s", name)
        return None
