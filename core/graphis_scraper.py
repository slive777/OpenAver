"""
Graphis 女優照片爬蟲
從 graphis.ne.jp 抓取高品質女優照片
"""

import re
from typing import Optional, Dict
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from core.logger import get_logger
logger = get_logger(__name__)


def _parse_graphis_profile(html: str) -> dict:
    """
    解析 Graphis model.php 詳情頁

    Returns:
        { name_en, age, height, cup, bust, waist, hip, hobby }
        缺少的欄位為 '' 或 None
    """
    result = {
        'name_en': '',
        'age': None,
        'height': '',
        'cup': '',
        'bust': '',
        'waist': '',
        'hip': '',
        'hobby': '',
    }

    try:
        soup = BeautifulSoup(html, 'html.parser')

        # 英文名：breadcrumb p.pan-link → 最後 > 後取 / 右側
        pan_link = soup.select_one('p.pan-link')
        if pan_link:
            pan_text = pan_link.get_text()
            # Split by last '>'
            parts = pan_text.rsplit('>', 1)
            if len(parts) == 2:
                last_part = parts[1].strip()
                # Take right side of '/'
                if '/' in last_part:
                    name_en = last_part.split('/', 1)[1].strip()
                    result['name_en'] = name_en

        # Profile fields: li.model-prof ul li
        for li in soup.select('li.model-prof ul li'):
            spans = li.select('span')
            if len(spans) < 2:
                continue
            label = spans[0].get_text(strip=True).lower()
            value_span = spans[1]
            value_text = value_span.get_text(strip=True)

            if 'age' in label or '年齢' in label:
                # Extract integer from second span
                age_match = re.search(r'(\d+)', value_text)
                if age_match:
                    result['age'] = int(age_match.group(1))

            elif 'height' in label or '身長' in label:
                # Extract (\d+)cm pattern
                height_match = re.search(r'(\d+)cm', value_text, re.IGNORECASE)
                if height_match:
                    result['height'] = f"{height_match.group(1)}cm"

            elif 'bwh' in label or 'スリーサイズ' in label:
                # B(\d+)(?:\(([A-Z])\))?\s*W(\d+)\s*H(\d+)
                bwh_match = re.search(
                    r'B(\d+)(?:\(([A-Z])\))?\s*W(\d+)\s*H(\d+)',
                    value_text
                )
                if bwh_match:
                    result['bust'] = f"{bwh_match.group(1)}cm"
                    if bwh_match.group(2):
                        result['cup'] = bwh_match.group(2)
                    result['waist'] = f"{bwh_match.group(3)}cm"
                    result['hip'] = f"{bwh_match.group(4)}cm"

            elif 'hobby' in label or '趣味' in label:
                # Full text of second span
                result['hobby'] = value_text

    except Exception as e:
        logger.warning(f"[graphis] _parse_graphis_profile error: {e}")

    return result


def scrape_graphis_photo(name: str) -> Optional[Dict]:
    """
    從 Graphis 網站抓取女優照片

    Args:
        name: 女優名稱（日文）

    Returns:
        {
            'name': str,           # 女優名稱
            'prof_url': str,       # 頭像 URL (360×508)
            'backdrop_url': str    # 背景 URL (1185×835)
        }
        找不到或錯誤返回 None
    """
    try:
        # Build search URL with URL-encoded name
        url = f"https://graphis.ne.jp/monthly/?K={quote(name)}"

        # Request with timeout
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=4)
        response.raise_for_status()

        # Parse HTML
        soup = BeautifulSoup(response.text, 'html.parser')

        # Find model boxes - structure: div.gp-model-box > ul > li > a > img
        model_boxes = soup.select('div.gp-model-box ul li a img')

        # Find Japanese names - structure: li.name-jp > span
        name_elements = soup.select('li.name-jp span')
        jp_names = [elem.get_text(strip=True) for elem in name_elements]

        # Check if actress name is in results
        if name not in jp_names:
            return None

        # Get the index and corresponding image
        idx = jp_names.index(name)
        if idx >= len(model_boxes):
            return None

        img_src = model_boxes[idx].get('src', '')
        if not img_src:
            return None

        # prof.jpg is the profile photo, model.jpg is the backdrop
        prof_url = img_src
        backdrop_url = img_src.replace('/prof.jpg', '/model.jpg')

        # Extract model_id from img_src for profile page
        profile_data = {}
        model_match = re.search(r'/model/([^/]+)/prof\.jpg', img_src)
        if model_match:
            model_id = model_match.group(1)
            try:
                profile_url = f"https://graphis.ne.jp/monthly/model.php?ID={model_id}"
                profile_resp = requests.get(profile_url, headers=headers, timeout=3)
                if profile_resp.status_code == 200:
                    profile_data = _parse_graphis_profile(profile_resp.text)
            except Exception as e:
                logger.warning(f"[graphis] model.php failed for {name}: {e}")
                # fail-open: profile_data stays empty dict

        return {
            'name': name,
            'prof_url': prof_url,
            'backdrop_url': backdrop_url,
            'name_en': profile_data.get('name_en', ''),
            'age': profile_data.get('age'),
            'height': profile_data.get('height', ''),
            'cup': profile_data.get('cup', ''),
            'bust': profile_data.get('bust', ''),
            'waist': profile_data.get('waist', ''),
            'hip': profile_data.get('hip', ''),
            'hobby': profile_data.get('hobby', ''),
        }

    except requests.exceptions.Timeout:
        logger.warning(f"[graphis] Timeout for {name}")
        return None
    except requests.exceptions.RequestException as e:
        logger.warning(f"[graphis] Request error for {name}: {e}")
        return None
    except Exception as e:
        logger.error(f"[graphis] Unexpected error for {name}: {e}")
        return None
