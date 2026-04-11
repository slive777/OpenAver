"""
Minnano-AV (みんなのAV.com) 女優 scraper
C1 primary text source — Phase 42b T1

Public API:
    scrape_minnano_av(name)  -> Optional[Dict]   live fetch + parse
    _parse_minnano_html(html, name) -> Optional[Dict]  pure parse (used by tests)
"""

import re
import urllib.parse
from typing import Optional, Dict, List

import requests
from bs4 import BeautifulSoup

from core.logger import get_logger

logger = get_logger(__name__)

BASE_URL = "https://www.minnano-av.com"
SEARCH_URL = BASE_URL + "/search_result.php"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en;q=0.8",
}

# Scene-tag suffixes that appear on alias names — strip before parse
# e.g. "笹川そら(着エロ)" → "笹川そら"
_TAG_SUFFIX_RE = re.compile(r"\s*\([^）)]*\)\s*$")


def scrape_minnano_av(name: str) -> Optional[Dict]:
    """Live fetch + parse minnano-av.com profile page.

    The server 302-redirects a unique-match search directly to the profile.
    Returns None on miss or any network/parse error.
    """
    url = (
        SEARCH_URL
        + "?search_scope=actress&search_word="
        + urllib.parse.quote(name)
    )
    try:
        session = requests.Session()
        session.headers.update(_HEADERS)
        resp = session.get(url, timeout=15, allow_redirects=True)
        resp.raise_for_status()
        return _parse_minnano_html(resp.text, name)
    except requests.exceptions.Timeout:
        logger.warning(f"[minnano_av] Timeout for '{name}'")
        return None
    except requests.exceptions.RequestException as exc:
        logger.warning(f"[minnano_av] Request error for '{name}': {exc}")
        return None
    except Exception as exc:
        logger.error(f"[minnano_av] Unexpected error for '{name}': {exc}")
        return None


def _parse_minnano_html(html: str, name: str) -> Optional[Dict]:
    """Parse minnano-av profile HTML.  Pure function — no IO.

    Used by unit tests via fixture HTML files.
    Returns None when the page title doesn't contain *name* (miss/redirect
    to wrong page) or when the profile table is absent.
    """
    if not html:
        return None

    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception as exc:
        logger.warning(f"[minnano_av] BeautifulSoup parse error: {exc}")
        return None

    # Hit verification — title must contain the queried name
    title_tag = soup.title
    title_text = title_tag.string.strip() if title_tag and title_tag.string else ""
    if name not in title_text:
        logger.debug(f"[minnano_av] Miss: '{name}' not in title '{title_text[:60]}'")
        return None

    # Locate profile table (contains 生年月日)
    profile_table = None
    for tbl in soup.find_all("table"):
        if "生年月日" in tbl.get_text():
            profile_table = tbl
            break
    if profile_table is None:
        logger.debug(f"[minnano_av] No profile table found for '{name}'")
        return None

    result: Dict = {
        "name_ja": "",
        "name_hiragana": "",
        "name_romaji": "",
        "aliases": [],        # list of {"ja": str, "hiragana": str, "romaji": str}
        "birth": "",          # "YYYY-MM-DD"
        "hometown": "",
        "height": "",
        "bust": "",
        "waist": "",
        "hip": "",
        "cup": "",
        "blood": "",
        "agency": "",
        "hobby": "",
        "debut_work": "",
        "blog_url": "",
        "official_url": "",
        "tags": [],           # list of str
        "photo_url": "",
    }

    for tr in profile_table.find_all("tr"):
        cells = tr.find_all(["th", "td"])
        if not cells:
            continue
        row_text = cells[0].get_text(" ", strip=True)
        row_text = re.sub(r"\s+", " ", row_text).strip()
        if not row_text:
            continue

        # Main name row: "天馬ゆい （てんまゆい / Tenma Yui）"
        # Use full-width （U+FF08）U+FF09 only to avoid half-width tag suffixes
        m = re.match(
            r"^([^\s\uff08]+)\s*\uff08([^/]+)\s*/\s*([^\uff09]*)\uff09", row_text
        )
        if (
            m
            and not result["name_ja"]
            and "別名" not in row_text
            and "生年月日" not in row_text
        ):
            result["name_ja"] = m.group(1).strip()
            result["name_hiragana"] = m.group(2).strip()
            result["name_romaji"] = m.group(3).strip()
            continue

        # Aliases — strip scene-tag suffixes before parsing
        if row_text.startswith("別名"):
            rest = row_text[len("別名"):].strip()
            _parse_alias_row(rest, result["aliases"])
            continue

        # Birth: "生年月日 1997年12月03日 （現在 28歳 ）いて座"
        if row_text.startswith("生年月日"):
            birth_text = row_text[len("生年月日"):]
            bm = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", birth_text)
            if bm:
                y, mo, d = bm.groups()
                result["birth"] = f"{y}-{int(mo):02d}-{int(d):02d}"
            continue

        # Size: "サイズ T159 / B83( Bカップ ) / W60 / H86 / S24.5"
        if row_text.startswith("サイズ"):
            _parse_size_row(row_text[len("サイズ"):], result)
            continue

        if row_text.startswith("血液型"):
            result["blood"] = row_text[len("血液型"):].strip()
            continue
        if row_text.startswith("出身地"):
            result["hometown"] = row_text[len("出身地"):].strip()
            continue
        if row_text.startswith("所属事務所"):
            result["agency"] = row_text[len("所属事務所"):].strip()
            continue
        if row_text.startswith("趣味・特技"):
            result["hobby"] = row_text[len("趣味・特技"):].strip()
            continue
        if row_text.startswith("デビュー作品"):
            result["debut_work"] = row_text[len("デビュー作品"):].strip()
            continue
        if row_text.startswith("ブログ"):
            result["blog_url"] = row_text[len("ブログ"):].strip()
            continue
        if row_text.startswith("公式サイト"):
            result["official_url"] = row_text[len("公式サイト"):].strip()
            continue
        if row_text.startswith("タグ"):
            raw_tags = row_text[len("タグ"):].strip()
            # Tags are space-separated on the page
            result["tags"] = [t for t in raw_tags.split() if t]
            continue

    # Profile photo: og:image is most reliable
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        result["photo_url"] = og["content"]
    else:
        header = soup.find(class_="actress-header")
        if header:
            img = header.find("img")
            if img:
                src = img.get("src", "")
                if src.startswith("/"):
                    src = BASE_URL + src
                result["photo_url"] = src

    return result


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _strip_tag_suffix(ja_name: str) -> str:
    """Remove scene-tag suffixes like (着エロ), (ハード), (コスプレ) from a name."""
    return _TAG_SUFFIX_RE.sub("", ja_name).strip()


def _parse_alias_row(rest: str, aliases: List[Dict]) -> None:
    """Parse one alias row and append to *aliases* list.

    Input examples:
        "笹川そら(着エロ) （ささがわそら / Sasagawa Sora）"   ← half-width () = tag suffix
        "上川星空 （かみかわそら / Kamikawa Sora）"            ← full-width （） = hiragana
        "上山美琴 （ / ）"
    Strategy:
        1. Strip half-width (...) tag suffixes from the Japanese name part.
        2. Match full-width （hiragana / romaji） separately.
    """
    # Match: Japanese name (before full-width 「（」) + full-width (hiragana / romaji)
    # U+FF08 = （, U+FF09 = ）
    m = re.match(r"^(.*?)\s*\uff08([^/]*)\s*/\s*([^\uff09]*)\uff09", rest)
    if m:
        ja_raw = m.group(1).strip()
        ja_clean = _strip_tag_suffix(ja_raw)
        hiragana = m.group(2).strip()
        romaji = m.group(3).strip()
        if ja_clean:
            aliases.append({"ja": ja_clean, "hiragana": hiragana, "romaji": romaji})
    else:
        # Fallback: no hiragana/romaji brackets — store bare name after stripping tags
        ja_clean = _strip_tag_suffix(rest)
        if ja_clean:
            aliases.append({"ja": ja_clean, "hiragana": "", "romaji": ""})


def _parse_size_row(text: str, result: Dict) -> None:
    """Parse 'T159 / B83( Bカップ ) / W60 / H86 / S24.5' into result dict."""
    m = re.search(r"T\s*(\d+)", text)
    if m:
        result["height"] = f"{m.group(1)}cm"

    # Bust + cup: B83(Bカップ) or B83( B カップ )
    m = re.search(r"B\s*(\d+)(?:\s*\(\s*([A-Z])\s*カップ\s*\))?", text)
    if m:
        result["bust"] = f"{m.group(1)}cm"
        if m.group(2):
            result["cup"] = m.group(2)

    m = re.search(r"W\s*(\d+)", text)
    if m:
        result["waist"] = f"{m.group(1)}cm"

    m = re.search(r"H\s*(\d+)", text)
    if m:
        result["hip"] = f"{m.group(1)}cm"
