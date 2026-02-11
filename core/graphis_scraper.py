"""
Graphis 女優照片爬蟲
從 graphis.ne.jp 抓取高品質女優照片
"""

from typing import Optional, Dict
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from core.logger import get_logger
logger = get_logger(__name__)


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
        response = requests.get(url, headers=headers, timeout=5)
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

        return {
            'name': name,
            'prof_url': prof_url,
            'backdrop_url': backdrop_url
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
