"""
Japanese Wikipedia (ja.wikipedia.org) 女優 scraper

Phase 42b T2 — C1 secondary text source + C3 photo (raw URL only, no download)

Public API:
    scrape_wiki_ja(name)          → live fetch + parse
    _parse_wiki_ja_html(html, name) → pure HTML parse, used by tests
    _commons_thumb_to_raw(thumb_url) → pure string transformation, no HTTP
"""

import re
import urllib.parse
from typing import Optional, Dict

import requests
from bs4 import BeautifulSoup

from core.logger import get_logger

logger = get_logger(__name__)

HEADERS = {
    "User-Agent": "OpenAver-research/1.0 (https://github.com/; research)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en;q=0.8",
}

_THUMB_RE = re.compile(
    r"(https?:)?//upload\.wikimedia\.org/wikipedia/commons/thumb/([^/]+/[^/]+/[^/]+)/\d+px-.*"
)


def _commons_thumb_to_raw(thumb_url: str) -> str:
    """
    Pure string transformation: Commons thumbnail URL → original full-res URL.

    Thumb pattern:
        //upload.wikimedia.org/wikipedia/commons/thumb/{h}/{hh}/{file}/{N}px-{file}
    Original:
        https://upload.wikimedia.org/wikipedia/commons/{h}/{hh}/{file}

    No HTTP calls made.
    """
    m = _THUMB_RE.match(thumb_url)
    if not m:
        return thumb_url
    path = m.group(2)          # e.g. "8/85/Fresh_Fes_2024_shooting_Tsumugi_Akari.jpg"
    return f"https://upload.wikimedia.org/wikipedia/commons/{path}"


def _flatten(value_text: str) -> str:
    """Join all text with simple space, strip | separators from get_text."""
    return re.sub(r"\s*\|\s*", " ", value_text).strip()


def _parse_wiki_ja_html(html: str, name: str) -> Optional[Dict]:
    """
    Parse Wikipedia JP HTML and extract infobox fields.

    Pure function — no IO, no HTTP.  Used directly by unit tests.

    Returns None if no usable infobox is found.
    """
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception as exc:
        logger.warning(f"[wiki_ja] BeautifulSoup parse error for {name}: {exc}")
        return None

    infobox = soup.find("table", class_=re.compile(r"infobox"))
    if not infobox:
        logger.debug(f"[wiki_ja] no infobox for {name}")
        return None

    result: Dict = {
        "name_ja": name,
        "nickname": "",
        "other_names": [],
        "birth": "",
        "hometown": "",
        "height": "",
        "bust": "",
        "waist": "",
        "hip": "",
        "cup": "",
        "blood": "",
        "exclusive_makers": "",
        "debut_year": "",
        "photo_url": "",
        "photo_needs_resize": True,
        "photo_license": "Commons",
    }

    # --- Walk infobox rows ---
    for tr in infobox.find_all("tr"):
        th = tr.find("th")
        td = tr.find("td")
        if not th or not td:
            continue
        label = th.get_text(" ", strip=True)
        value = _flatten(td.get_text(" | ", strip=True))

        if "愛称" in label:
            result["nickname"] = value

        elif "別名" in label:
            # Split by Japanese/Chinese/ASCII commas.
            # 不清洗 (中華圏名) 括號說明 — Phase 43 alias pipeline 責任
            raw = re.split(r"[\u3001\uFF0C,]", value)
            result["other_names"] = [s.strip() for s in raw if s.strip()]

        elif "生年月日" in label or "誕生" in label:
            m = re.search(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日", value)
            if m:
                y, mo, d = m.groups()
                result["birth"] = f"{y}-{int(mo):02d}-{int(d):02d}"

        elif "出身" in label or "出生" in label:
            # Strip leading "日本 ・"
            v = re.sub(r"^日本\s*[・·]\s*", "", value).strip()
            result["hometown"] = v

        elif "血液" in label:
            m = re.search(r"(AB型|A型|B型|O型)", value)
            if m:
                result["blood"] = m.group(1)

        elif "身長" in label:
            # Handle both "身長 / 体重" combined row AND standalone "身長" row.
            # Prefer metric (cm); imperial (ft/in) is skipped by the cm regex check.
            if re.search(r"\d+\s*cm", value):
                m = re.search(r"(\d+)\s*cm", value)
                if m:
                    result["height"] = f"{m.group(1)}cm"

        elif "スリーサイズ" in label:
            # ⚠️ INCH TRAP: infobox has cm row AND in row.
            # Filter to prefer the cm row; if bust already set (cm row was first), skip.
            if "cm" in value and not result["bust"]:
                m = re.search(
                    r"(\d+)\s*[-‐−–]\s*(\d+)\s*[-‐−–]\s*(\d+)\s*cm", value
                )
                if m:
                    result["bust"] = f"{m.group(1)}cm"
                    result["waist"] = f"{m.group(2)}cm"
                    result["hip"] = f"{m.group(3)}cm"

        elif "ブラサイズ" in label or "カップ" in label:
            m = re.search(r"([A-Z])", value)
            if m:
                result["cup"] = m.group(1)

        elif "専属契約" in label:
            result["exclusive_makers"] = value

        elif "出演期間" in label or "活動期間" in label:
            if not result["debut_year"]:
                m = re.search(r"(\d{4})年", value)
                if m:
                    result["debut_year"] = m.group(1)

    # --- Photo: first img with width >= 100 AND non-empty alt ---
    # C3: string-only URL transform, no HTTP.
    # alt guard (Finding B): 簽名圖 alt='' 會被濾掉，避免 Wiki 重排後誤抓
    for img in infobox.find_all("img"):
        try:
            w = int(img.get("width", "0") or "0")
        except (ValueError, TypeError):
            w = 0
        alt = (img.get("alt") or "").strip()
        if w >= 100 and alt:
            src = img.get("src", "")
            if not src:
                continue
            if src.startswith("//"):
                src = "https:" + src
            raw_url = _commons_thumb_to_raw(src)
            result["photo_url"] = raw_url
            break

    # Return None if we couldn't parse anything meaningful.
    # Shell results (name_ja only, maybe photo) are not good enough —
    # they would suppress richer fallback sources in the orchestrator cascade.
    meaningful_fields = ("birth", "height", "bust", "waist", "hip", "cup",
                         "blood", "hometown", "nickname", "exclusive_makers",
                         "debut_year", "other_names")
    if not any(result.get(k) for k in meaningful_fields):
        logger.debug(f"[wiki_ja] infobox found but no usable text fields for {name}")
        return None

    return result


def scrape_wiki_ja(name: str) -> Optional[Dict]:
    """
    Live fetch + parse Wikipedia JP infobox for the given actress name.

    Returns None on HTTP error, 404, or missing infobox.
    C3: photo handling is string-only — no requests.get(photo_url).
    """
    url = f"https://ja.wikipedia.org/wiki/{urllib.parse.quote(name)}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
    except requests.exceptions.Timeout:
        logger.warning(f"[wiki_ja] Timeout for {name}")
        return None
    except requests.exceptions.RequestException as exc:
        logger.warning(f"[wiki_ja] Request error for {name}: {exc}")
        return None

    if r.status_code != 200:
        logger.debug(f"[wiki_ja] HTTP {r.status_code} for {name}")
        return None

    result = _parse_wiki_ja_html(r.text, name)
    if result is not None:
        logger.debug(
            f"[wiki_ja] {name}: birth={result.get('birth')} "
            f"height={result.get('height')} photo={'yes' if result.get('photo_url') else 'no'}"
        )
    return result
