"""
JAV Scraper - 搜尋模組
從 JavBus, Jav321, DMM, AVSOX, MGStage 抓取影片資訊
"""

import re
import requests
from typing import Optional, Dict, List
from urllib.parse import quote, urljoin
from bs4 import BeautifulSoup

# 嘗試載入 jvav（JavBus API）
try:
    from jvav import JavBusUtil
    JVAV_AVAILABLE = True
except ImportError:
    JVAV_AVAILABLE = False

# HTTP 請求設定
REQUEST_TIMEOUT = 15
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'ja-JP,ja;q=0.9,zh-TW;q=0.8,zh;q=0.7,en;q=0.6',
}

# 刮削來源優先順序（只保留有效的）
SCRAPER_PRIORITY = ['javbus', 'jav321']


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


# ============ 搜尋器實現 ============

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
    number = number.strip().upper()

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

    # 優先用 Jav321（有完整封面），JavBus 補充
    if 'jav321' in all_data:
        main_data = all_data['jav321']
        backup_data = all_data.get('javbus')
    elif 'javbus' in all_data:
        main_data = all_data['javbus']
        backup_data = all_data.get('jav321')
    else:
        main_data = list(all_data.values())[0]
        backup_data = None

    # 用 backup 補全缺失欄位
    if backup_data:
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

def is_number_format(s: str) -> bool:
    """判斷是否為完整番號格式 (如 SONE-001, ABC-123)"""
    return bool(re.match(r'^[a-zA-Z]+-?\d{3,}$', s.strip()))


def is_partial_number(s: str) -> bool:
    """判斷是否為部分番號 (如 SONE-0, IPZZ-03)"""
    match = re.match(r'^([a-zA-Z]+)-?(\d{1,2})$', s.strip())
    return bool(match)


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
    局部搜尋：自動展開並查詢所有可能的番號
    只返回有結果的
    """
    candidates = expand_partial_number(partial)
    results = []

    for number in candidates:
        data = search_jav(number)
        if data and data.get('title'):  # 確保有實際資料
            results.append(data)

    return results


def search_actress(name: str, limit: int = 20) -> List[Dict]:
    """
    搜尋女優作品列表

    使用 JavBus 搜尋功能，返回作品列表
    """
    try:
        # JavBus 搜尋 URL（使用 URL 編碼的名字）
        search_url = f'https://www.javbus.com/search/{quote(name)}'
        headers = HEADERS.copy()
        headers['Cookie'] = 'existmag=all'

        html = get_html(search_url, headers=headers)
        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')

        results = []
        count = 0

        # 解析搜尋結果列表
        for item in soup.select('.movie-box'):
            if count >= limit:
                break

            # 取得番號
            number_elem = item.select_one('date:first-of-type')
            if not number_elem:
                # 嘗試其他方式取得番號
                frame = item.select_one('.photo-frame')
                if frame:
                    img = frame.select_one('img')
                    if img and img.get('title'):
                        # 從標題提取番號
                        title = img.get('title', '')
                        match = re.match(r'^([A-Z]+-\d+)', title)
                        if match:
                            number = match.group(1)
                        else:
                            continue
                    else:
                        continue
                else:
                    continue
            else:
                number = number_elem.get_text(strip=True)

            if not number:
                continue

            # 取得詳細資訊
            data = search_jav(number)
            if data and data.get('title'):
                results.append(data)
                count += 1

        return results

    except Exception:
        pass
    return []


def smart_search(query: str) -> List[Dict]:
    """
    智慧搜尋：自動判斷搜尋類型並執行

    - 完整番號 → 精確搜尋
    - 部分番號 → 展開搜尋
    - 其他文字 → 女優搜尋
    """
    query = query.strip()

    if not query or len(query) < 2:
        return []

    # 判斷搜尋類型
    if is_partial_number(query):
        # 部分番號 → 展開搜尋
        return search_partial(query)
    elif is_number_format(query):
        # 完整番號 → 精確搜尋
        data = search_jav(query)
        return [data] if data else []
    else:
        # 其他文字 → 女優搜尋
        return search_actress(query)
