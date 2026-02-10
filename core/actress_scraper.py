"""
女優爬蟲 - 從 JavBus 抓取女優個人檔案
使用 jvav 套件進行搜尋，再手動帶 cookie 解析詳情頁
"""

import re
import requests
from datetime import datetime
from typing import Optional, Dict

from bs4 import BeautifulSoup

# 嘗試載入 jvav（JavBus API）
try:
    from jvav import JavBusUtil
    JVAV_AVAILABLE = True
except ImportError:
    JVAV_AVAILABLE = False


def scrape_actress_profile(name: str) -> Optional[Dict]:
    """
    從 JavBus 抓取女優個人資料

    Args:
        name: 女優名字（日文或英文）

    Returns:
        {
            'name': str,        # 姓名
            'img': str,         # 頭像 URL
            'birth': str,       # 生日 (e.g. "1996-12-03")
            'age': int,         # 年齡
            'height': str,      # 身高 (e.g. "160cm")
            'cup': str,         # 罩杯 (e.g. "G")
            'bust': str,        # 胸圍
            'waist': str,       # 腰圍
            'hip': str,         # 臀圍
            'hometown': str,    # 出生地
            'hobby': str,       # 興趣
        }
        找不到返回 None
    """
    if not name or not name.strip():
        return None

    if not JVAV_AVAILABLE:
        return None

    name = name.strip()

    try:
        jb = JavBusUtil()

        # 檢查 jvav 是否有 check_star_exists 方法（版本相容性）
        if not hasattr(jb, 'check_star_exists'):
            print("[actress_scraper] Error: jvav 版本過舊，缺少 check_star_exists 方法")
            return None

        # Step 1: 使用 jvav 搜尋女優，取得 star_id
        code, search_result = jb.check_star_exists(name)
        if code != 200 or not search_result:
            return None

        star_id = search_result.get('star_id')
        star_name = search_result.get('star_name', name)

        if not star_id:
            return None

        # Step 2: 手動帶 cookie 獲取女優詳情頁（jvav 的 send_req 不處理 cookie）
        detail_url = f"https://www.javbus.com/star/{star_id}"
        headers = jb.get_headers()
        cookies = {'existmag': 'all'}  # JavBus 年齡驗證 cookie

        resp = requests.get(detail_url, headers=headers, cookies=cookies, timeout=15)
        if resp.status_code != 200:
            return None

        html = resp.text

        # Step 3: 解析詳情頁
        soup = BeautifulSoup(html, 'html.parser')

        result = {
            'name': star_name,
            'img': '',
            'birth': '',
            'age': None,
            'height': '',
            'cup': '',
            'bust': '',
            'waist': '',
            'hip': '',
            'hometown': '',
            'hobby': '',
        }

        # 頭像圖片
        img_elem = soup.select_one('.photo-frame img')
        if img_elem:
            img_url = img_elem.get('src', '')
            # 確保是完整 URL
            if img_url and not img_url.startswith('http'):
                img_url = f"https://www.javbus.com{img_url}"
            result['img'] = img_url

        # 解析個人資料區塊
        info_elem = soup.select_one('.photo-info')
        if info_elem:
            for p in info_elem.select('p'):
                text = p.get_text(strip=True)
                _parse_info_line(text, result)

        # 驗證是否有有效資料
        if result['name'] or result['img']:
            return result

        return None

    except Exception as e:
        print(f"[actress_scraper] Error: {e}")
        return None


def _parse_info_line(text: str, result: Dict) -> None:
    """解析個人資料行"""

    # 生日
    if '生日:' in text or '生日：' in text:
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', text)
        if date_match:
            result['birth'] = date_match.group(1)
            # 計算年齡
            try:
                birth_date = datetime.strptime(result['birth'], '%Y-%m-%d')
                today = datetime.now()
                age = today.year - birth_date.year
                if (today.month, today.day) < (birth_date.month, birth_date.day):
                    age -= 1
                result['age'] = age
            except ValueError:
                pass

    # 身高
    if '身高:' in text or '身高：' in text:
        height_match = re.search(r'(\d+)\s*cm', text, re.IGNORECASE)
        if height_match:
            result['height'] = f"{height_match.group(1)}cm"

    # 罩杯
    if '罩杯:' in text or '罩杯：' in text:
        cup_match = re.search(r'([A-KO-Z])(?:\s*カップ|\s*cup|\s*$)', text, re.IGNORECASE)
        if cup_match:
            result['cup'] = cup_match.group(1).upper()

    # 胸圍
    if '胸圍:' in text or '胸圍：' in text:
        bust_match = re.search(r'(\d+)\s*cm', text, re.IGNORECASE)
        if bust_match:
            result['bust'] = f"{bust_match.group(1)}cm"

    # 腰圍
    if '腰圍:' in text or '腰圍：' in text:
        waist_match = re.search(r'(\d+)\s*cm', text, re.IGNORECASE)
        if waist_match:
            result['waist'] = f"{waist_match.group(1)}cm"

    # 臀圍
    if '臀圍:' in text or '臀圍：' in text:
        hip_match = re.search(r'(\d+)\s*cm', text, re.IGNORECASE)
        if hip_match:
            result['hip'] = f"{hip_match.group(1)}cm"

    # 出生地
    if '出生地:' in text or '出生地：' in text:
        hometown = text.split(':')[-1].split('：')[-1].strip()
        if hometown:
            result['hometown'] = hometown

    # 興趣
    if '愛好:' in text or '愛好：' in text or '興趣:' in text or '興趣：' in text:
        hobby = text.split(':')[-1].split('：')[-1].strip()
        if hobby:
            result['hobby'] = hobby


# Cache 結構（模組層級變數）
_cache = {}  # key: str (正規化女優名), value: dict (profile + timestamp)
_CACHE_TTL = 3600  # 1 小時


def _normalize_name(name: str) -> str:
    """正規化女優名稱（用於 cache key）"""
    import unicodedata
    name = name.strip()
    # 全形 → 半形
    name = unicodedata.normalize('NFKC', name)
    # 統一空白符
    name = ' '.join(name.split())
    return name


def get_actress_profile(name: str) -> Optional[Dict]:
    """
    取得女優完整資料（Graphis + JavBus 雙來源並行）

    Args:
        name: 女優名稱（日文）

    Returns:
        {
            'name': str,           # 姓名
            'img': str,            # 頭像 URL（Graphis 優先）
            'backdrop': str,       # 背景 URL（僅 Graphis 有）
            'birth': str,          # 生日 "1996-12-03"
            'age': int,            # 年齡
            'height': str,         # 身高 "160cm"
            'cup': str,            # 罩杯 "G"
            'bust': str,           # 胸圍 "90cm"
            'waist': str,          # 腰圍 "55cm"
            'hip': str,            # 臀圍 "86cm"
            'hometown': str,       # 出身地
            'hobby': str,          # 興趣
        }
        兩邊都沒資料返回 None
    """
    import time
    from concurrent.futures import ThreadPoolExecutor
    from core.graphis_scraper import scrape_graphis_photo

    # Cache 檢查
    cache_key = _normalize_name(name)
    if cache_key in _cache:
        cached = _cache[cache_key]
        if time.time() - cached['timestamp'] < _CACHE_TTL:
            return cached['data']
        else:
            del _cache[cache_key]  # 過期清理

    # 並行抓取（嚴格 5s 上限，shutdown 不等待背景執行緒）
    executor = ThreadPoolExecutor(max_workers=2)
    graphis_future = executor.submit(scrape_graphis_photo, name)
    javbus_future = executor.submit(scrape_actress_profile, name)

    start = time.time()

    try:
        graphis_result = graphis_future.result(timeout=5)
    except Exception:
        graphis_result = None

    remaining = max(0, 5 - (time.time() - start))
    try:
        javbus_result = javbus_future.result(timeout=remaining)
    except Exception:
        javbus_result = None

    executor.shutdown(wait=False)

    # 資料合併
    if javbus_result:
        result = javbus_result.copy()
    elif graphis_result:
        result = {'name': name}
    else:
        return None

    # Graphis 照片優先覆蓋
    if graphis_result:
        result['img'] = graphis_result['prof_url']
        result['backdrop'] = graphis_result['backdrop_url']

    # Cache 寫入
    _cache[cache_key] = {
        'data': result,
        'timestamp': time.time()
    }

    return result
