"""
Organizer 模組 - 檔案整理功能（重命名、資料夾、封面、NFO）
從 jav_scraper.py 簡化而來，只處理檔案操作，不含搜尋功能
"""

import os
import re
import shutil
import requests
from pathlib import Path
from typing import Optional, Dict, Any, List


# HTTP 請求設定
REQUEST_TIMEOUT = 30
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}


def sanitize_filename(name: str) -> str:
    """清理檔名中的非法字元"""
    illegal_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
    for char in illegal_chars:
        name = name.replace(char, ' ')
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def truncate_title(title: str, max_len: int) -> str:
    """截斷標題長度"""
    if not title:
        return ''
    if len(title) <= max_len:
        return title
    return title[:max_len - 3] + '...'


def format_string(template: str, data: Dict[str, Any]) -> str:
    """
    根據模板格式化字串

    支援變數:
    - {num}: 番號
    - {title}: 標題
    - {actor}: 第一位演員
    - {actors}: 所有演員
    - {maker}: 片商
    - {date}: 發行日期
    - {year}: 年份
    """
    result = template

    # 番號
    result = result.replace('{num}', data.get('number', ''))

    # 標題
    result = result.replace('{title}', data.get('title', ''))

    # 演員
    actors = data.get('actors', [])
    if actors:
        result = result.replace('{actor}', actors[0])
        result = result.replace('{actors}', ', '.join(actors))
    else:
        result = result.replace('{actor}', '')
        result = result.replace('{actors}', '')

    # 片商
    result = result.replace('{maker}', data.get('maker', ''))

    # 日期
    date = data.get('date', '')
    result = result.replace('{date}', date)
    result = result.replace('{year}', date[:4] if date else '')

    return sanitize_filename(result.strip())


def download_image(url: str, save_path: str, referer: str = '') -> bool:
    """下載圖片"""
    if not url:
        return False
    try:
        headers = HEADERS.copy()

        # 根據 URL 設置對應的 Referer
        if not referer:
            if "javbus.com" in url:
                referer = "https://www.javbus.com/"
            elif "dmm.co.jp" in url:
                referer = "https://www.dmm.co.jp/"
            elif "jav321.com" in url:
                referer = "https://www.jav321.com/"

        if referer:
            headers['Referer'] = referer

        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200 and len(resp.content) > 1000:
            with open(save_path, 'wb') as f:
                f.write(resp.content)
            return True
    except Exception as e:
        print(f"[!] 下載圖片失敗: {e}")
    return False


def generate_nfo(
    number: str,
    title: str,
    original_title: str = '',
    actors: List[str] = None,
    tags: List[str] = None,
    date: str = '',
    maker: str = '',
    url: str = '',
    has_subtitle: bool = False,
    output_path: str = ''
) -> bool:
    """
    生成 NFO 檔案

    Args:
        number: 番號
        title: 標題（中文）
        original_title: 原始標題（日文）
        actors: 演員列表
        tags: 標籤列表
        date: 發行日期（YYYY-MM-DD）
        maker: 片商
        url: 來源 URL
        has_subtitle: 是否有字幕
        output_path: NFO 輸出路徑
    """
    if not output_path:
        return False

    actors = actors or []
    tags = tags or []
    year = date[:4] if date else ''

    # 封面檔名（不含副檔名）
    basename = os.path.splitext(os.path.basename(output_path))[0]

    # 顯示標題
    display_title = f"[{number}]{title}" if title else f"[{number}]{original_title}"

    nfo_content = f'''<?xml version="1.0" encoding="utf-8"?>
<movie>
  <title>{display_title}</title>
  <originaltitle>{original_title}</originaltitle>
  <set></set>
  <studio>{maker}</studio>
  <year>{year}</year>
  <premiered>{date}</premiered>
  <plot></plot>
  <runtime></runtime>
  <director></director>
  <poster>{basename}.png</poster>
  <thumb></thumb>
  <fanart>{basename}.jpg</fanart>
'''

    # 演員
    for actor in actors:
        nfo_content += f'''  <actor>
    <name>{actor}</name>
    <role></role>
  </actor>
'''

    # 標籤
    for tag in tags:
        nfo_content += f'  <tag>{tag}</tag>\n'

    if has_subtitle:
        nfo_content += '  <tag>中文字幕</tag>\n'

    # Genre
    for tag in tags:
        nfo_content += f'  <genre>{tag}</genre>\n'

    if has_subtitle:
        nfo_content += '  <genre>中文字幕</genre>\n'

    nfo_content += f'''  <num>{number}</num>
  <release>{date}</release>
  <cover></cover>
  <website>{url}</website>
</movie>'''

    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(nfo_content)
        return True
    except Exception as e:
        print(f"[!] 生成 NFO 失敗: {e}")
        return False


def organize_file(
    file_path: str,
    metadata: Dict[str, Any],
    config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    整理單個檔案

    Args:
        file_path: 原始檔案路徑
        metadata: 影片元數據 {number, title, actors, tags, date, maker, img, url}
        config: 設定 {create_folder, folder_format, filename_format, download_cover,
                      cover_filename, create_nfo, max_title_length, max_filename_length}

    Returns:
        {success, original_path, new_folder, new_filename, cover_path, nfo_path, error}
    """
    result = {
        'success': False,
        'original_path': file_path,
        'new_folder': None,
        'new_filename': None,
        'cover_path': None,
        'nfo_path': None,
        'error': None
    }

    if not os.path.exists(file_path):
        result['error'] = '檔案不存在'
        return result

    # 提取必要資訊
    number = metadata.get('number', '')
    if not number:
        result['error'] = '缺少番號'
        return result

    # 準備格式化資料
    actors = []
    stars = metadata.get('stars', [])
    if stars:
        actors = [s.get('name', '') for s in stars if s.get('name')]

    format_data = {
        'number': number,
        'title': truncate_title(metadata.get('title', ''), config.get('max_title_length', 80)),
        'actors': actors,
        'maker': metadata.get('maker', ''),
        'date': metadata.get('date', ''),
    }

    # 原始檔案資訊
    original_dir = os.path.dirname(file_path)
    original_ext = os.path.splitext(file_path)[1]

    # 計算目標路徑
    if config.get('create_folder', True):
        folder_name = format_string(config.get('folder_format', '{num}'), format_data)
        target_dir = os.path.join(original_dir, folder_name)
    else:
        target_dir = original_dir

    # 計算新檔名
    filename_base = format_string(config.get('filename_format', '{num} {title}'), format_data)

    # 確保檔名長度限制
    max_len = config.get('max_filename_length', 200)
    if len(filename_base) + len(original_ext) > max_len:
        filename_base = filename_base[:max_len - len(original_ext) - 3] + '...'

    new_filename = filename_base + original_ext
    target_path = os.path.join(target_dir, new_filename)

    try:
        # 建立資料夾
        if config.get('create_folder', True):
            os.makedirs(target_dir, exist_ok=True)
            result['new_folder'] = target_dir

        # 移動並重命名檔案
        if file_path != target_path:
            shutil.move(file_path, target_path)
        result['new_filename'] = target_path

        # 下載封面
        if config.get('download_cover', True):
            img_url = metadata.get('cover', '')
            if img_url:
                cover_name = config.get('cover_filename', 'poster.jpg')
                cover_path = os.path.join(target_dir, cover_name)
                if download_image(img_url, cover_path):
                    result['cover_path'] = cover_path

        # 生成 NFO
        if config.get('create_nfo', True):
            nfo_path = os.path.join(target_dir, f"{number}.nfo")
            tags = metadata.get('tags', [])
            if generate_nfo(
                number=number,
                title=format_data['title'],
                original_title=metadata.get('original_title', metadata.get('title', '')),
                actors=actors,
                tags=tags,
                date=metadata.get('date', ''),
                maker=metadata.get('maker', ''),
                url=metadata.get('url', ''),
                has_subtitle=metadata.get('has_subtitle', False),
                output_path=nfo_path
            ):
                result['nfo_path'] = nfo_path

        result['success'] = True

    except Exception as e:
        result['error'] = str(e)

    return result
