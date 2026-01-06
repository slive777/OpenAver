"""
JAV Scraper - 搜尋模組
從 JavDB, JavBus, Jav321 抓取影片資訊
"""

import re
import json
import time
import requests
from pathlib import Path
from typing import Optional, Dict, List
from urllib.parse import quote, urljoin
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

# 嘗試載入 jvav（JavBus API）
try:
    from jvav import JavBusUtil
    JVAV_AVAILABLE = True
except ImportError:
    JVAV_AVAILABLE = False

# 嘗試載入 curl_cffi（JavDB TLS 指紋偽造）
try:
    from curl_cffi import requests as curl_requests
    CURL_CFFI_AVAILABLE = True
except ImportError:
    CURL_CFFI_AVAILABLE = False

# HTTP 請求設定
REQUEST_TIMEOUT = 15
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'ja-JP,ja;q=0.9,zh-TW;q=0.8,zh;q=0.7,en;q=0.6',
}

# 爬蟲節流設定（避免被網站封禁）
MAX_WORKERS = 2          # 並行請求數（保守設定）
REQUEST_DELAY = 0.3      # 每次請求後延遲（秒）

# 刮削來源優先順序（JavBus 優先，封面無浮水印）
SCRAPER_PRIORITY = ['javbus', 'jav321']

# 片商對照表檔案路徑
MAKER_MAPPING_FILE = Path(__file__).parent.parent / "maker_mapping.json"

# 快取片商對照表（避免重複讀檔）
_maker_mapping_cache: Dict[str, str] = {}
_maker_mapping_loaded = False


# ============ 番號提取 ============

def extract_number(filename: str) -> Optional[str]:
    """
    從檔名中提取番號

    Args:
        filename: 檔案名稱或路徑

    Returns:
        提取的番號（如 SONE-205），找不到返回 None
    """
    # 只取檔名部分
    basename = Path(filename).stem

    patterns = [
        r'(FC2-PPV-\d+)',               # FC2-PPV-1234567 (優先)
        r'\[([A-Za-z]{2,6}-\d{3,5})\]',  # [ABC-123] 方括號內
        r'([A-Za-z]{2,6}-\d{3,5})',     # ABC-123 帶橫線
        r'([A-Za-z]{2,6})(\d{3,5})',    # ABC12345 不帶橫線（需重組）
        r'(\d{3}[A-Za-z]{3,4}-?\d{3,4})', # 123ABC-456
    ]

    for i, pattern in enumerate(patterns):
        match = re.search(pattern, basename, re.IGNORECASE)
        if match:
            if i == 3:  # 不帶橫線的格式需重組
                number = f"{match.group(1).upper()}-{match.group(2)}"
            else:
                number = match.group(1).upper()
            return number
    return None


# ============ 片商對照表 ============

def load_maker_mapping() -> Dict[str, str]:
    """載入片商對照表（番號前綴 → 片商名稱）"""
    global _maker_mapping_cache, _maker_mapping_loaded
    if _maker_mapping_loaded:
        return _maker_mapping_cache

    if MAKER_MAPPING_FILE.exists():
        try:
            with open(MAKER_MAPPING_FILE, 'r', encoding='utf-8') as f:
                _maker_mapping_cache = json.load(f)
        except (json.JSONDecodeError, IOError):
            _maker_mapping_cache = {}
    _maker_mapping_loaded = True
    return _maker_mapping_cache


def save_maker_mapping(mapping: Dict[str, str]):
    """儲存片商對照表"""
    global _maker_mapping_cache, _maker_mapping_loaded
    try:
        with open(MAKER_MAPPING_FILE, 'w', encoding='utf-8') as f:
            json.dump(mapping, f, ensure_ascii=False, indent=2)
        _maker_mapping_cache = mapping
        _maker_mapping_loaded = True
    except IOError:
        pass


def get_maker_by_prefix(number: str) -> str:
    """
    從對照表查片商，沒有則查 JavDB 並更新對照表

    Args:
        number: 番號（如 SONE-103）

    Returns:
        片商名稱，找不到返回空字串
    """
    mapping = load_maker_mapping()

    # 提取前綴（如 SONE-103 → SONE）
    match = re.match(r'^([A-Za-z]+)', number)
    if not match:
        return ""

    prefix = match.group(1).upper()

    # 對照表有 → 直接返回
    if prefix in mapping:
        return mapping[prefix]

    # 對照表沒有 → 查 JavDB
    if CURL_CFFI_AVAILABLE:
        try:
            detail = scrape_javdb(number)
            if detail and detail.get('maker'):
                maker = detail['maker']
                # 更新對照表
                mapping[prefix] = maker
                save_maker_mapping(mapping)
                return maker
        except Exception:
            pass

    return ""


# ============ HTTP 工具 ============

def get_html(url: str, cookies: dict = None, headers: dict = None) -> Optional[str]:
    """獲取網頁 HTML"""
    try:
        h = HEADERS.copy()
        if headers:
            h.update(headers)
        resp = requests.get(url, headers=h, cookies=cookies, timeout=REQUEST_TIMEOUT)
        resp.encoding = resp.apparent_encoding
        if resp.status_code == 200:
            return resp.text
    except Exception:
        pass
    return None


def post_html(url: str, data: dict = None, headers: dict = None) -> Optional[str]:
    """POST 請求獲取 HTML"""
    try:
        h = HEADERS.copy()
        if headers:
            h.update(headers)
        resp = requests.post(url, data=data, headers=h, timeout=REQUEST_TIMEOUT)
        resp.encoding = resp.apparent_encoding
        if resp.status_code == 200:
            return resp.text
    except Exception:
        pass
    return None


# ============ JavDB 工具 ============

def get_javdb_html(url: str) -> Optional[str]:
    """發送請求到 JavDB（使用 TLS 指紋偽造）"""
    if not CURL_CFFI_AVAILABLE:
        return None
    try:
        response = curl_requests.get(
            url,
            impersonate="chrome120",
            headers={
                "User-Agent": HEADERS['User-Agent'],
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-TW,zh;q=0.9,ja;q=0.8,en;q=0.7",
                "Referer": "https://javdb.com/",
            },
            timeout=30
        )
        if response.status_code == 200:
            return response.text
    except Exception:
        pass
    return None


def search_javdb_list(keyword: str, limit: int = 20) -> List[Dict]:
    """
    搜尋 JavDB 列表頁面

    用於女優搜尋、模糊搜尋
    返回: [{'number': 'SONE-103', 'title': '...', 'detail_url': '/v/xxx', 'date': '...'}]
    """
    url = f"https://javdb.com/search?q={quote(keyword)}&f=all"
    html = get_javdb_html(url)
    if not html:
        return []

    soup = BeautifulSoup(html, 'html.parser')
    results = []

    for item in soup.select('.movie-list .item')[:limit]:
        try:
            uid_elem = item.select_one('.video-title strong')
            uid = uid_elem.text.strip() if uid_elem else ''

            title_elem = item.select_one('.video-title')
            title = title_elem.text.strip() if title_elem else ''
            if uid and title.startswith(uid):
                title = title[len(uid):].strip()

            link_elem = item.select_one('a[href^="/v/"]')
            detail_url = link_elem['href'] if link_elem else ''

            date_elem = item.select_one('.meta')
            date = ''
            if date_elem:
                date_match = re.search(r'(\d{4}-\d{2}-\d{2})', date_elem.text)
                if date_match:
                    date = date_match.group(1)

            cover_elem = item.select_one('img')
            cover = cover_elem.get('src', '') if cover_elem else ''

            if uid:
                results.append({
                    'number': uid,
                    'title': title,
                    'date': date,
                    'cover': cover,
                    'detail_url': detail_url,
                })
        except Exception:
            continue

    return results


def get_javdb_detail(detail_path: str) -> Optional[Dict]:
    """
    獲取 JavDB 詳情頁資訊

    detail_path: '/v/xxx' 格式
    返回完整資訊包含 maker
    """
    if not detail_path:
        return None

    url = f"https://javdb.com{detail_path}" if detail_path.startswith('/') else detail_path
    html = get_javdb_html(url)
    if not html:
        return None

    soup = BeautifulSoup(html, 'html.parser')

    result = {
        'title': '',
        'img': '',
        'stars': [],
        'date': '',
        'tags': [],
        'maker': '',
        'url': url,
        'source': 'javdb'
    }

    # 標題
    title_elem = soup.select_one('.video-detail h2, .title.is-4')
    if title_elem:
        result['title'] = title_elem.text.strip()

    # 解析資訊面板
    for panel in soup.select('.panel-block'):
        label = panel.select_one('strong')
        value = panel.select_one('.value')
        if not label:
            continue

        label_text = label.text.strip()

        # 日期
        if '日期' in label_text and value:
            result['date'] = value.text.strip()

        # 片商 (Maker)
        if '片商' in label_text or '製作' in label_text or '發行' in label_text:
            if value:
                result['maker'] = value.text.strip()

        # 演員（只抓女優，跳過男優）
        if '演員' in label_text:
            actors = []
            for a in panel.select('a'):
                name = a.text.strip()
                if not name:
                    continue
                # 檢查後面的性別標記
                next_elem = a.find_next_sibling()
                # 如果有 female 標記，或沒有性別標記（舊格式），都加入
                # 只跳過明確標記為 male 的
                if next_elem and 'male' in next_elem.get('class', []) and 'female' not in next_elem.get('class', []):
                    continue  # 跳過男優
                actors.append({'name': name})
            result['stars'] = actors

        # 標籤
        if '類別' in label_text:
            tags = panel.select('a')
            result['tags'] = [t.text.strip() for t in tags if t.text.strip()]

    # 封面
    cover_elem = soup.select_one('.video-cover img, .column-video-cover img')
    if cover_elem:
        result['img'] = cover_elem.get('src', '')

    return result if result['title'] or result['img'] else None


# ============ 搜尋器實現 ============

def scrape_javdb(number: str) -> Optional[Dict]:
    """
    JavDB 刮削器

    優點：有 maker、數據完整
    需要 curl_cffi 繞過 TLS 指紋檢測
    """
    if not CURL_CFFI_AVAILABLE:
        return None

    try:
        # 先搜尋取得 detail_url
        results = search_javdb_list(number, limit=5)

        # 找到精確匹配的番號
        target = None
        number_upper = number.upper().replace('-', '')
        for r in results:
            r_num = r['number'].upper().replace('-', '')
            if r_num == number_upper:
                target = r
                break

        if not target or not target.get('detail_url'):
            return None

        # 獲取詳情頁
        detail = get_javdb_detail(target['detail_url'])
        return detail

    except Exception:
        pass
    return None


def scrape_javbus(number: str) -> Optional[Dict]:
    """JavBus 刮削器（透過 jvav）- 注意：只有右半邊封面"""
    if not JVAV_AVAILABLE:
        return None
    try:
        jb = JavBusUtil()
        code, data = jb.get_av_by_id(number, False, False)
        if code == 200 and data:
            data['source'] = 'javbus'
            return data
    except Exception:
        pass
    return None


def scrape_jav321(number: str) -> Optional[Dict]:
    """Jav321 刮削器"""
    try:
        # 搜尋頁面
        search_url = 'https://www.jav321.com/search'
        html = post_html(search_url, data={'sn': number})
        if not html:
            return None

        # 檢查是否直接跳轉到詳情頁
        if '/video/' in html or '<h3>' in html:
            detail_html = html
        else:
            # 解析搜尋結果
            soup = BeautifulSoup(html, 'html.parser')
            link = soup.select_one('.row a[href*="/video/"]')
            if not link:
                return None
            detail_url = urljoin('https://www.jav321.com', link.get('href'))
            detail_html = get_html(detail_url)
            if not detail_html:
                return None

        soup = BeautifulSoup(detail_html, 'html.parser')

        # 提取標題
        title_elem = soup.select_one('h3')
        title = title_elem.get_text(strip=True) if title_elem else ''
        # 移除番號前綴
        title = re.sub(rf'^{re.escape(number)}\s*', '', title, flags=re.IGNORECASE)

        # 提取封面
        img_elem = soup.select_one('.col-md-3 img')
        img = img_elem.get('src', '') if img_elem else ''
        if img and not img.startswith('http'):
            img = urljoin('https://www.jav321.com', img)
        # 轉換成完整封面（DMM: ps.jpg -> pl.jpg）
        if img:
            img = img.replace('ps.jpg', 'pl.jpg').replace('/pt/', '/pl/')

        # 提取演員（去重）
        actors = []
        seen_names = set()
        for a in soup.select('a[href*="/star/"]'):
            name = a.get_text(strip=True)
            if name and name not in seen_names:
                actors.append({'name': name})
                seen_names.add(name)

        # 提取日期
        date = ''
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', detail_html)
        if date_match:
            date = date_match.group(1)

        # 提取標籤
        tags = []
        for a in soup.select('a[href*="/genre/"]'):
            tag = a.get_text(strip=True)
            if tag:
                tags.append(tag)

        if title or img:
            return {
                'title': title,
                'img': img,
                'stars': actors,
                'date': date,
                'tags': tags,
                'url': f'https://www.jav321.com/video/{number.lower()}',
                'source': 'jav321'
            }
    except Exception:
        pass
    return None


def scrape_dmm(number: str) -> Optional[Dict]:
    """DMM 刮削器"""
    try:
        # DMM 需要年齡驗證 cookie
        cookies = {'age_check_done': '1'}

        # 搜尋 URL
        search_number = number.replace('-', '').lower()
        search_url = f'https://www.dmm.co.jp/mono/dvd/-/search/=/searchstr={quote(number)}/'

        html = get_html(search_url, cookies=cookies)
        if not html:
            return None

        soup = BeautifulSoup(html, 'html.parser')

        # 找到第一個結果
        item = soup.select_one('#list li a')
        detail_url = ''
        if not item:
            # 嘗試直接訪問商品頁
            cid = search_number
            detail_url = f'https://www.dmm.co.jp/mono/dvd/-/detail/=/cid={cid}/'
            html = get_html(detail_url, cookies=cookies)
            if not html:
                return None
        else:
            detail_url = item.get('href', '')
            if not detail_url.startswith('http'):
                detail_url = urljoin('https://www.dmm.co.jp', detail_url)
            html = get_html(detail_url, cookies=cookies)
            if not html:
                return None

        soup = BeautifulSoup(html, 'html.parser')

        # 提取標題
        title_elem = soup.select_one('#title')
        title = title_elem.get_text(strip=True) if title_elem else ''

        # 提取封面
        img_elem = soup.select_one('#sample-video img, .center img[src*="pics.dmm.co.jp"]')
        img = ''
        if img_elem:
            img = img_elem.get('src', '') or img_elem.get('data-src', '')
            # 轉換成大圖
            img = img.replace('ps.jpg', 'pl.jpg').replace('/pt/', '/pl/')

        # 提取演員
        actors = []
        for a in soup.select('a[href*="/actress/"]'):
            name = a.get_text(strip=True)
            if name and name not in ['すべて', '一覧']:
                actors.append({'name': name})

        # 提取日期
        date = ''
        date_td = soup.find('td', string=re.compile(r'発売日|配信開始日'))
        if date_td:
            date_val = date_td.find_next_sibling('td')
            if date_val:
                date_match = re.search(r'(\d{4})/(\d{2})/(\d{2})', date_val.get_text())
                if date_match:
                    date = f'{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}'

        # 提取標籤
        tags = []
        for a in soup.select('a[href*="/genre/"]'):
            tag = a.get_text(strip=True)
            if tag:
                tags.append(tag)

        if title or img:
            return {
                'title': title,
                'img': img,
                'stars': actors,
                'date': date,
                'tags': tags,
                'url': detail_url,
                'source': 'dmm'
            }
    except Exception:
        pass
    return None


def scrape_avsox(number: str) -> Optional[Dict]:
    """AVSOX 刮削器（主要用於無碼內容）"""
    try:
        # 搜尋
        search_url = f'https://avsox.click/cn/search/{quote(number)}'
        html = get_html(search_url)
        if not html:
            # 嘗試備用域名
            search_url = f'https://avsox.monster/cn/search/{quote(number)}'
            html = get_html(search_url)
        if not html:
            return None

        soup = BeautifulSoup(html, 'html.parser')

        # 找到匹配的結果
        item = None
        for box in soup.select('.photo-frame'):
            box_text = box.get_text()
            if number.upper() in box_text.upper() or number.replace('-', '').upper() in box_text.upper():
                item = box.find_parent('a')
                break

        if not item:
            item = soup.select_one('.photo-frame')
            if item:
                item = item.find_parent('a')

        if not item:
            return None

        detail_url = item.get('href', '')
        if not detail_url.startswith('http'):
            detail_url = urljoin(search_url, detail_url)

        html = get_html(detail_url)
        if not html:
            return None

        soup = BeautifulSoup(html, 'html.parser')

        # 提取標題
        title_elem = soup.select_one('h3')
        title = title_elem.get_text(strip=True) if title_elem else ''
        title = re.sub(rf'^{re.escape(number)}\s*', '', title, flags=re.IGNORECASE)

        # 提取封面
        img_elem = soup.select_one('.bigImage img, .container img[src*="pics"]')
        img = img_elem.get('src', '') if img_elem else ''

        # 提取演員
        actors = []
        for a in soup.select('a[href*="/star/"]'):
            name = a.get_text(strip=True)
            if name:
                actors.append({'name': name})

        # 提取日期
        date = ''
        for p in soup.select('.info p'):
            text = p.get_text()
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', text)
            if date_match:
                date = date_match.group(1)
                break

        # 提取標籤
        tags = []
        for a in soup.select('a[href*="/genre/"]'):
            tag = a.get_text(strip=True)
            if tag:
                tags.append(tag)

        if title or img:
            return {
                'title': title,
                'img': img,
                'stars': actors,
                'date': date,
                'tags': tags,
                'url': detail_url,
                'source': 'avsox'
            }
    except Exception:
        pass
    return None


def scrape_mgstage(number: str) -> Optional[Dict]:
    """MGStage 刮削器"""
    try:
        # MGS 專用番號格式
        detail_url = f'https://www.mgstage.com/product/product_detail/{number}/'
        cookies = {'adc': '1'}  # 年齡驗證

        html = get_html(detail_url, cookies=cookies)
        if not html or '404' in html[:500]:
            return None

        soup = BeautifulSoup(html, 'html.parser')

        # 提取標題
        title_elem = soup.select_one('.tag')
        title = title_elem.get_text(strip=True) if title_elem else ''

        # 提取封面
        img_elem = soup.select_one('.sample_image img, img[src*="image.mgstage.com"]')
        img = img_elem.get('src', '') if img_elem else ''

        # 提取演員
        actors = []
        actor_row = soup.find('th', string='出演')
        if actor_row:
            actor_td = actor_row.find_next_sibling('td')
            if actor_td:
                for a in actor_td.select('a'):
                    name = a.get_text(strip=True)
                    if name:
                        actors.append({'name': name})

        # 提取日期
        date = ''
        date_row = soup.find('th', string='配信開始日')
        if date_row:
            date_td = date_row.find_next_sibling('td')
            if date_td:
                date_match = re.search(r'(\d{4})/(\d{2})/(\d{2})', date_td.get_text())
                if date_match:
                    date = f'{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}'

        # 提取標籤
        tags = []
        genre_row = soup.find('th', string='ジャンル')
        if genre_row:
            genre_td = genre_row.find_next_sibling('td')
            if genre_td:
                for a in genre_td.select('a'):
                    tag = a.get_text(strip=True)
                    if tag:
                        tags.append(tag)

        if title or img:
            return {
                'title': title,
                'img': img,
                'stars': actors,
                'date': date,
                'tags': tags,
                'url': detail_url,
                'source': 'mgstage'
            }
    except Exception:
        pass
    return None


# 刮削器映射
SCRAPERS = {
    'javdb': scrape_javdb,
    'javbus': scrape_javbus,
    'jav321': scrape_jav321,
    'dmm': scrape_dmm,
    'avsox': scrape_avsox,
    'mgstage': scrape_mgstage,
}


def get_female_actors(stars: List[Dict]) -> List[Dict]:
    """過濾出女優（排除男優）"""
    if not stars:
        return []
    female = []
    for s in stars:
        # 如果有性別標記，只保留女性
        sex = s.get('sex', '')
        if sex and sex in ['男', 'male', 'm']:
            continue
        female.append(s)
    return female


def normalize_number(number: str) -> str:
    """
    標準化番號格式（自動加連字號）

    例如:
      'sone103' → 'SONE-103'
      'SONE-103' → 'SONE-103'
      'abc00123' → 'ABC-00123'
    """
    number = number.strip().upper()
    # 如果已經有連字號，直接返回
    if '-' in number:
        return number
    # 嘗試在字母和數字之間插入連字號
    match = re.match(r'^([A-Z]+)(\d+)$', number)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return number


def search_jav(number: str, source: str = 'auto') -> Optional[Dict]:
    """
    搜尋 JAV 資訊（自動從多來源補全）

    Args:
        number: 番號（如 SONE-001）
        source: 來源 ('auto', 'javbus', 'jav321')

    Returns:
        {
            'number': str,      # 番號
            'title': str,       # 標題
            'actors': [str],    # 演員列表（名字）
            'date': str,        # 發行日期
            'maker': str,       # 片商（如有）
            'cover': str,       # 封面 URL
            'tags': [str],      # 標籤
            'source': str,      # 資料來源
            'url': str,         # 詳情頁 URL
        }
    """
    number = normalize_number(number)

    # 收集所有來源的資料
    all_data = {}
    for src in SCRAPER_PRIORITY:
        if src not in SCRAPERS:
            continue
        try:
            data = SCRAPERS[src](number)
            if data and (data.get('title') or data.get('img')):
                all_data[src] = data
        except Exception:
            pass

    if not all_data:
        return None

    # 選擇主要來源（優先順序：JavBus > Jav321）
    # JavBus 封面無浮水印，jvav 套件有維護
    if 'javbus' in all_data:
        main_data = all_data['javbus']
    elif 'jav321' in all_data:
        main_data = all_data['jav321']
    else:
        main_data = list(all_data.values())[0]

    # 用其他來源補全缺失欄位
    for src, backup_data in all_data.items():
        if backup_data is main_data:
            continue
        # 補全標題
        if not main_data.get('title') and backup_data.get('title'):
            main_data['title'] = backup_data['title']
        # 補全演員
        if not main_data.get('stars') and backup_data.get('stars'):
            main_data['stars'] = backup_data['stars']
        # 補全日期
        if not main_data.get('date') and backup_data.get('date'):
            main_data['date'] = backup_data['date']
        # 補全標籤
        if not main_data.get('tags') and backup_data.get('tags'):
            main_data['tags'] = backup_data['tags']
        # 補全片商 (maker)
        if not main_data.get('maker') and backup_data.get('maker'):
            main_data['maker'] = backup_data['maker']
        # 補全封面（如果主來源沒有）
        if not main_data.get('img') and backup_data.get('img'):
            main_data['img'] = backup_data['img']

    # 最後用對照表補全片商（如果還是沒有）
    if not main_data.get('maker'):
        main_data['maker'] = get_maker_by_prefix(number)

    return _normalize_result(number, main_data)


def _normalize_result(number: str, data: Dict) -> Dict:
    """標準化搜尋結果"""
    # 提取演員名字列表
    actors = []
    for s in data.get('stars', []):
        if isinstance(s, dict):
            name = s.get('name', '')
            if name:
                actors.append(name)
        elif isinstance(s, str):
            actors.append(s)

    return {
        'number': number,
        'title': data.get('title', ''),
        'actors': actors,
        'date': data.get('date', ''),
        'maker': data.get('maker', ''),  # JavBus 可能有
        'cover': data.get('img', ''),
        'tags': data.get('tags', []),
        'source': data.get('source', ''),
        'url': data.get('url', ''),
    }


# ============ 進階搜尋功能 ============

def sort_results_by_date(results: List[Dict], reverse: bool = True) -> List[Dict]:
    """
    按發行日期排序搜尋結果

    Args:
        results: 搜尋結果列表
        reverse: True=新的在前（降序），False=舊的在前（升序）

    Returns:
        排序後的結果列表
    """
    def sort_key(item):
        date = item.get('date', '') or '0000-00-00'
        number = item.get('number', '')
        return (date, number)

    return sorted(results, key=sort_key, reverse=reverse)


def is_number_format(s: str) -> bool:
    """判斷是否為完整番號格式 (如 SONE-001, ABC-123)"""
    return bool(re.match(r'^[a-zA-Z]+-?\d{3,}$', s.strip()))


def is_partial_number(s: str) -> bool:
    """判斷是否為部分番號 (如 SONE-0, IPZZ-03)"""
    match = re.match(r'^([a-zA-Z]+)-?(\d{1,2})$', s.strip())
    return bool(match)


def is_prefix_only(s: str) -> bool:
    """判斷是否為純前綴 (如 IPZZ, SONE)"""
    s = s.strip().upper()
    # 2-6 個大寫字母，無數字
    return bool(re.match(r'^[A-Z]{2,6}$', s))


def expand_partial_number(partial: str) -> List[str]:
    """
    展開部分番號為完整番號列表

    例如:
      'ipzz-03' → ['IPZZ-030', 'IPZZ-031', ..., 'IPZZ-039']
      'sone-1'  → ['SONE-010', 'SONE-011', ..., 'SONE-019']
    """
    match = re.match(r'^([a-zA-Z]+)-?(\d+)$', partial.strip())
    if not match:
        return [partial]

    prefix, num = match.groups()
    prefix = prefix.upper()

    # 如果數字部分已經是3位以上，當作完整番號
    if len(num) >= 3:
        return [f"{prefix}-{num}"]

    # 展開成可能的完整番號
    candidates = []
    for i in range(10):
        full_num = num + str(i)
        # 補零到3位
        while len(full_num) < 3:
            full_num = '0' + full_num
        candidates.append(f"{prefix}-{full_num}")

    return candidates


def search_partial(partial: str) -> List[Dict]:
    """
    局部搜尋：並行查詢 JavBus/Jav321（無浮水印封面）

    展開候選號碼後並行查詢，提升速度
    """
    candidates = expand_partial_number(partial)
    results = []

    # 並行查詢（節流設定）
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(search_jav, num): num for num in candidates}
        for future in as_completed(futures):
            try:
                data = future.result()
                if data and data.get('title'):
                    results.append(data)
            except Exception:
                pass
            time.sleep(REQUEST_DELAY)  # 請求間隔

    # 按日期排序（新的在前）
    return sort_results_by_date(results)


def search_prefix(prefix: str, limit: int = 20, offset: int = 0, status_callback=None) -> List[Dict]:
    """
    搜尋番號前綴（如 IPZZ, SONE）

    使用 JavBus 搜尋頁面，直接返回最新番號

    Args:
        prefix: 番號前綴
        limit: 最大結果數
        offset: 跳過前 N 個結果（用於分頁）
        status_callback: 狀態回調函數 (source, status)
    """
    if not JVAV_AVAILABLE:
        return []

    results = []
    prefix = prefix.strip().upper()

    if status_callback:
        status_callback('javbus', 'searching')

    jb = JavBusUtil()

    # 計算分頁（JavBus 每頁約 30 個）
    page = (offset // 30) + 1
    skip_in_page = offset % 30

    # 從 JavBus 搜尋頁面獲取番號列表（已按最新排序）
    search_url = f'https://www.javbus.com/search/{prefix}&type=1'
    code, ids = jb.get_ids_from_page(search_url, page=page)

    if code != 200 or not ids:
        if status_callback:
            status_callback('javbus', 'found:0')
            status_callback('done', 'total:0')
        return []

    # 跳過 offset 對應的部分，取 limit 個
    target_ids = ids[skip_in_page:][:limit]

    if not target_ids:
        if status_callback:
            status_callback('javbus', 'found:0')
            status_callback('done', 'total:0')
        return []

    if status_callback:
        status_callback('javbus', f'found:{len(target_ids)}')
        status_callback('javbus', 'fetching_details')

    # 並行取得詳情（節流設定）
    total_count = len(target_ids)
    completed_count = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(scrape_javbus, num): num for num in target_ids}
        for future in as_completed(futures):
            num = futures[future]
            completed_count += 1
            if status_callback:
                status_callback('javbus', f'details:{completed_count}/{total_count}')
            try:
                data = future.result()
                if data and (data.get('title') or data.get('img')):
                    actors = []
                    for s in data.get('stars', []):
                        if isinstance(s, dict):
                            actors.append(s.get('name', ''))
                        elif isinstance(s, str):
                            actors.append(s)

                    results.append({
                        'number': num,
                        'title': data.get('title', ''),
                        'actors': actors,
                        'date': data.get('date', ''),
                        'maker': data.get('maker', '') or get_maker_by_prefix(num),
                        'cover': data.get('img', ''),
                        'tags': data.get('tags', []),
                        'source': 'javbus',
                        'url': data.get('url', ''),
                    })
            except Exception:
                pass
            time.sleep(REQUEST_DELAY)  # 請求間隔

    # JavBus 搜尋頁面已按最新排序，保持原順序
    # 但 as_completed 會打亂順序，需要按原始 ID 順序重排
    id_order = {id: i for i, id in enumerate(target_ids)}
    results.sort(key=lambda x: id_order.get(x['number'], 999))

    if status_callback:
        status_callback('done', f'total:{len(results)}')
    return results


def search_actress(name: str, limit: int = 20, offset: int = 0, status_callback=None) -> List[Dict]:
    """
    搜尋女優作品列表

    使用 jvav 套件的 get_ids_by_star_name

    Args:
        name: 女優名
        limit: 最大結果數
        offset: 跳過前 N 個結果（用於分頁）
        status_callback: 狀態回調函數 (source, status)
    """
    results = []

    if status_callback:
        status_callback('javbus', 'searching')

    # 使用 jvav 套件
    if JVAV_AVAILABLE:
        try:
            jb = JavBusUtil()
            # 計算起始頁和需要的頁數（每頁約 30 個）
            start_page = (offset // 30) + 1
            skip_in_page = offset % 30  # 第一頁要跳過的數量
            pages_needed = ((limit + skip_in_page) // 30) + 2  # 多取一些確保夠

            all_ids = []
            for page in range(start_page, start_page + pages_needed):
                code, ids = jb.get_ids_by_star_name(name, page)
                if code == 200 and ids:
                    all_ids.extend(ids)
                    if len(all_ids) >= limit + skip_in_page:
                        break
                else:
                    break

            # 跳過 offset 對應的部分
            all_ids = all_ids[skip_in_page:]

            if all_ids:
                if status_callback:
                    status_callback('javbus', f'found:{len(all_ids[:limit])}')
                    status_callback('javbus', 'fetching_details')

                # 並行取得詳情（節流設定）
                target_ids = all_ids[:limit]
                total_count = len(target_ids)
                completed_count = 0
                with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                    futures = {executor.submit(scrape_javbus, num): num for num in target_ids}
                    for future in as_completed(futures):
                        num = futures[future]
                        completed_count += 1
                        # 發送進度更新
                        if status_callback:
                            status_callback('javbus', f'details:{completed_count}/{total_count}')
                        try:
                            data = future.result()
                            if data and (data.get('title') or data.get('img')):
                                actors = []
                                for s in data.get('stars', []):
                                    if isinstance(s, dict):
                                        actors.append(s.get('name', ''))
                                    elif isinstance(s, str):
                                        actors.append(s)

                                results.append({
                                    'number': num,
                                    'title': data.get('title', ''),
                                    'actors': actors if actors else [name],
                                    'date': data.get('date', ''),
                                    'maker': data.get('maker', '') or get_maker_by_prefix(num),
                                    'cover': data.get('img', ''),
                                    'tags': data.get('tags', []),
                                    'source': 'javbus',
                                    'url': data.get('url', ''),
                                })
                        except Exception:
                            pass
                        time.sleep(REQUEST_DELAY)  # 請求間隔

                # 按日期排序（新的在前）
                results = sort_results_by_date(results)

                if status_callback:
                    status_callback('done', f'total:{len(results)}')
                return results

        except Exception:
            if status_callback:
                status_callback('javbus', 'failed')

    if status_callback:
        status_callback('done', f'total:{len(results)}')
    return results


def search_jav321_keyword(keyword: str, limit: int = 20, status_callback=None) -> List[Dict]:
    """
    Jav321 通用關鍵字搜尋（用於 fallback）

    可搜尋：番號、女優名、片名片段
    """
    if status_callback:
        status_callback('jav321', 'searching')

    search_url = 'https://www.jav321.com/search'
    html = post_html(search_url, data={'sn': keyword})
    if not html:
        if status_callback:
            status_callback('jav321', 'failed')
        return []

    soup = BeautifulSoup(html, 'html.parser')

    # 解析搜尋結果列表
    items = soup.select('.row .col-md-3')[:limit]
    if not items:
        if status_callback:
            status_callback('jav321', 'found:0')
        return []

    results = []
    for item in items:
        link = item.select_one('a[href*="/video/"]')
        if not link:
            continue

        href = link.get('href', '')
        number = href.split('/video/')[-1].upper() if '/video/' in href else ''

        # 取得封面
        img = item.select_one('img')
        cover = img.get('src', '') if img else ''

        if number:
            results.append({
                'number': number,
                'cover': cover,
                'source': 'jav321',
            })

    if not results:
        if status_callback:
            status_callback('jav321', 'found:0')
        return []

    if status_callback:
        status_callback('jav321', f'found:{len(results)}')
        status_callback('jav321', 'fetching_details')

    # 並行取得詳情（節流設定）
    detailed = []
    total_count = len(results)
    completed_count = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(scrape_jav321, r['number']): r for r in results}
        for future in as_completed(futures):
            r = futures[future]
            completed_count += 1
            # 發送進度更新
            if status_callback:
                status_callback('jav321', f'details:{completed_count}/{total_count}')
            try:
                detail = future.result()
                if detail:
                    actors = [s.get('name', '') for s in detail.get('stars', [])]
                    detailed.append({
                        'number': r['number'],
                        'title': detail.get('title', ''),
                        'actors': actors,
                        'date': detail.get('date', ''),
                        'maker': get_maker_by_prefix(r['number']),
                        'cover': detail.get('img') or r['cover'],
                        'tags': detail.get('tags', []),
                        'source': 'jav321',
                        'url': detail.get('url', ''),
                    })
            except Exception:
                pass
            time.sleep(REQUEST_DELAY)  # 請求間隔

    return sort_results_by_date(detailed)


def smart_search(query: str, limit: int = 20, offset: int = 0, status_callback=None) -> List[Dict]:
    """
    智慧搜尋：自動判斷搜尋類型並執行

    - 完整番號 → 精確搜尋
    - 部分番號 → 展開搜尋 (IPZZ-03)
    - 純前綴 → 前綴搜尋 (IPZZ)
    - 其他文字 → 女優搜尋

    Args:
        query: 搜尋關鍵字
        limit: 最大結果數（預設 20）
        offset: 跳過前 N 個結果（用於分頁）
        status_callback: 狀態回調函數 (source, status)

    Returns:
        搜尋結果列表，包含 'mode' 欄位表示搜尋類型
    """
    query = query.strip()
    mode = 'unknown'

    if not query or len(query) < 2:
        return []

    # 判斷搜尋類型
    if is_number_format(query):
        # 完整番號 → 精確搜尋（不支援分頁）
        mode = 'exact'
        if offset > 0:
            return []  # 精確搜尋只有一個結果，offset>0 時回傳空
        if status_callback:
            status_callback('javbus', 'searching')
        data = search_jav(query)
        if status_callback:
            status_callback('done', 'found:1' if data else 'found:0')
        results = [data] if data else []

    elif is_partial_number(query):
        # 部分番號 → 展開搜尋 (IPZZ-03)（固定範圍，不支援分頁）
        mode = 'partial'
        if offset > 0:
            return []  # 局部搜尋只有 10 個結果，offset>0 時回傳空
        if status_callback:
            status_callback('javbus', 'searching')
        results = search_partial(query)
        if status_callback:
            status_callback('done', f'found:{len(results)}')

    elif is_prefix_only(query):
        # 純前綴 → 前綴搜尋 (IPZZ)
        mode = 'prefix'
        results = search_prefix(query, limit=limit, offset=offset, status_callback=status_callback)

        # Fallback 1: 當作女優名搜尋（可能是英文女優名如 miru, Rio）
        if not results:
            if status_callback:
                status_callback('mode', 'actress')  # 通知前端切換模式
            results = search_actress(query, limit=limit, status_callback=status_callback)
            if results:
                mode = 'actress'

        # Fallback 2: Jav321 通用關鍵字搜尋
        if not results:
            if status_callback:
                status_callback('mode', 'keyword')  # 通知前端切換模式
            results = search_jav321_keyword(query, limit=limit, status_callback=status_callback)
            if results:
                mode = 'keyword'

    else:
        # 其他文字 → 女優搜尋
        mode = 'actress'
        results = search_actress(query, limit=limit, offset=offset, status_callback=status_callback)

        # Fallback: Jav321 通用關鍵字搜尋
        if not results:
            if status_callback:
                status_callback('mode', 'keyword')  # 通知前端切換模式
            results = search_jav321_keyword(query, limit=limit, status_callback=status_callback)
            if results:
                mode = 'keyword'

    # 在結果中加入搜尋模式
    for r in results:
        r['_mode'] = mode

    return results
