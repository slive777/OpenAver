"""
測試 JavDB 爬蟲（使用 curl_cffi 繞過 TLS 指紋檢測）

目的：
1. 測試 curl_cffi 能否成功連接 JavDB
2. 測試搜尋列表解析
3. 測試詳情頁解析（含 maker）
4. 測試女優搜尋
"""

from curl_cffi import requests
from bs4 import BeautifulSoup
import re
import time


# HTTP 設定
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,ja;q=0.8,en;q=0.7",
    "Referer": "https://javdb.com/",
}


def get_javdb(url: str) -> str:
    """發送請求到 JavDB（使用 TLS 指紋偽造）"""
    try:
        response = requests.get(
            url,
            impersonate="chrome120",
            headers=HEADERS,
            timeout=30
        )
        if response.status_code == 200:
            return response.text
        else:
            print(f"HTTP Error: {response.status_code}")
            return ""
    except Exception as e:
        print(f"Request Error: {e}")
        return ""


def search_javdb(keyword: str, limit: int = 10):
    """
    搜尋 JavDB

    支援：番號、女優名、關鍵字
    """
    url = f"https://javdb.com/search?q={keyword}&f=all"
    print(f"[Search] {url}")

    html = get_javdb(url)
    if not html:
        return []

    soup = BeautifulSoup(html, 'html.parser')
    results = []

    # JavDB 搜尋結果在 .movie-list 中
    items = soup.select('.movie-list .item')
    print(f"[Found] {len(items)} items")

    for item in items[:limit]:
        try:
            # 番號
            uid_elem = item.select_one('.video-title strong')
            uid = uid_elem.text.strip() if uid_elem else ''

            # 標題
            title_elem = item.select_one('.video-title')
            title = title_elem.text.strip() if title_elem else ''
            # 移除番號前綴
            if uid and title.startswith(uid):
                title = title[len(uid):].strip()

            # 詳情頁連結 (hash 格式)
            link_elem = item.select_one('a[href^="/v/"]')
            detail_url = f"https://javdb.com{link_elem['href']}" if link_elem else ''

            # 日期
            date_elem = item.select_one('.meta')
            date = ''
            if date_elem:
                date_match = re.search(r'(\d{4}-\d{2}-\d{2})', date_elem.text)
                if date_match:
                    date = date_match.group(1)

            # 封面
            cover_elem = item.select_one('img')
            cover = cover_elem.get('src', '') if cover_elem else ''

            results.append({
                'number': uid,
                'title': title,
                'date': date,
                'cover': cover,
                'detail_url': detail_url,
            })

        except Exception as e:
            print(f"Parse error: {e}")
            continue

    return results


def get_javdb_detail(url: str):
    """
    獲取 JavDB 詳情頁資訊

    包含：maker, 演員, 標籤, 完整封面
    """
    print(f"[Detail] {url}")

    html = get_javdb(url)
    if not html:
        return None

    soup = BeautifulSoup(html, 'html.parser')

    result = {
        'number': '',
        'title': '',
        'date': '',
        'maker': '',
        'actors': [],
        'tags': [],
        'cover': '',
    }

    # 番號
    number_elem = soup.select_one('.first-block .value')
    if number_elem:
        result['number'] = number_elem.text.strip()

    # 標題
    title_elem = soup.select_one('.video-detail h2')
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
        if '片商' in label_text or '製作' in label_text:
            if value:
                result['maker'] = value.text.strip()

        # 演員
        if '演員' in label_text:
            actors = panel.select('a')
            result['actors'] = [a.text.strip() for a in actors if a.text.strip()]

        # 標籤
        if '類別' in label_text:
            tags = panel.select('a')
            result['tags'] = [t.text.strip() for t in tags if t.text.strip()]

    # 封面
    cover_elem = soup.select_one('.video-cover img, .column-video-cover img')
    if cover_elem:
        result['cover'] = cover_elem.get('src', '')

    return result


def test_search():
    """測試搜尋功能"""
    print("\n" + "="*50)
    print("測試 1: 番號搜尋")
    print("="*50)

    results = search_javdb('SONE-103')
    for r in results[:3]:
        print(f"  {r['number']}: {r['title'][:30]}... ({r['date']})")

    print("\n" + "="*50)
    print("測試 2: 女優搜尋")
    print("="*50)

    results = search_javdb('小島みなみ')
    for r in results[:5]:
        print(f"  {r['number']}: {r['title'][:30]}...")


def test_detail():
    """測試詳情頁（含 maker）"""
    print("\n" + "="*50)
    print("測試 3: 詳情頁 (Maker)")
    print("="*50)

    # 先搜尋取得 detail_url
    results = search_javdb('SONE-103')
    if results:
        detail_url = results[0]['detail_url']
        time.sleep(1)  # 避免請求太快

        detail = get_javdb_detail(detail_url)
        if detail:
            print(f"  番號: {detail['number']}")
            print(f"  標題: {detail['title'][:50]}...")
            print(f"  片商: {detail['maker']}")
            print(f"  演員: {detail['actors']}")
            print(f"  日期: {detail['date']}")
            print(f"  標籤: {detail['tags'][:5]}...")


def test_actress_search():
    """測試女優作品列表"""
    print("\n" + "="*50)
    print("測試 4: 女優作品列表")
    print("="*50)

    results = search_javdb('三上悠亜', limit=5)
    print(f"找到 {len(results)} 部作品:")
    for r in results:
        print(f"  {r['number']}: {r['title'][:40]}...")


if __name__ == '__main__':
    test_search()
    time.sleep(1)
    test_detail()
    time.sleep(1)
    test_actress_search()
