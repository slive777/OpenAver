"""
Organizer 模組 - 檔案整理功能（重命名、資料夾、封面、NFO）
從 jav_scraper.py 簡化而來，只處理檔案操作，不含搜尋功能
"""

import os
import re
import shutil
import requests
import html
from pathlib import Path
from PIL import Image
from typing import Optional, Dict, Any, List

from core.path_utils import normalize_path
from core.scrapers.utils import has_chinese, check_subtitle
from core.logger import get_logger

logger = get_logger(__name__)


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


def truncate_title(title: str, max_len: int = 50) -> str:
    """截斷標題長度"""
    if not title:
        return ''
    if len(title) <= max_len:
        return title
    return title[:max_len - 3] + '...'


def truncate_to_chars(text: str, max_chars: int = 60) -> str:
    """按字符截斷，確保不超過指定長度"""
    if max_chars <= 0:
        return ''
    if max_chars <= 3:
        return text[:max_chars]
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 3] + '...'


def clean_source_suffix(text: str) -> str:
    """清除無意義的來源後綴"""
    patterns = [
        r'\s*-\s*Jable\s*TV.*$',
        r'\s*-\s*Jable.*$',
        r'\s*-\s*Hayav\s*AV.*$',
        r'\s*-\s*Hayav.*$',
        r'\s*-\s*MissAV.*$',
        r'\s*-\s*J片.*$',
        r'\s*-\s*免費.*$',
        r'\s*-\s*Netflav.*$',
        r'\s*-\s*AV看到飽.*$',
        r'\s*-\s*Free\s*Japan.*$',
        r'\s*-\s*Streaming.*$',
        r'\s*-\s*[A-Za-z]{1,3}\.?$',
        r'\s*-\s*$',
        r'\s+-\d+$',
    ]
    for p in patterns:
        text = re.sub(p, '', text, flags=re.IGNORECASE)
    return text.strip()


def extract_chinese_title(filename: str, number: str, actors: List[str] = None) -> Optional[str]:
    """
    從檔名提取原始中文片名

    Args:
        filename: 檔案名稱（不含路徑）
        number: 番號
        actors: 演員名單（用於移除）

    Returns:
        提取的中文片名，如果沒有則返回 None
    """
    if not filename:
        return None

    # 移除副檔名
    name = os.path.splitext(filename)[0]

    # 移除番號（各種格式）
    if number:
        name = re.sub(rf'\[?{re.escape(number)}\]?\s*', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\[?[A-Za-z]{2,6}-?\d{3,5}\]?\s*', '', name)

    # 清除來源後綴
    name = clean_source_suffix(name)

    # 清理多餘空格
    name = re.sub(r'\s+', ' ', name).strip()

    # 移除開頭的「中文字幕」標記
    name = re.sub(r'^中文字幕\s*', '', name)

    # 移除開頭和結尾的演員名
    if actors:
        for actor in actors:
            name = re.sub(rf'^{re.escape(actor)}\s*-\s*', '', name)
            name = re.sub(rf'\s+{re.escape(actor)}$', '', name)

    # 移除結尾可能的 2-4 字中文名（演員名）
    name = re.sub(r'\s+[\u4e00-\u9fff]{2,4}$', '', name)

    name = name.strip()

    # 只有包含中文才返回
    if name and has_chinese(name):
        return name

    return None


def _detect_suffixes(filename: str, keywords: list) -> str:
    """
    從原始檔名偵測版本標記關鍵字。
    邊界正則避免 -cd1 匹配 -cd10。
    """
    lower = filename.lower()
    matched = []
    for kw in keywords:
        kw_lower = kw.lower().strip()
        if not kw_lower:
            continue
        if re.search(re.escape(kw_lower) + r'(?=[-_.\s]|$)', lower):
            matched.append(kw_lower)
    return ''.join(matched)


FALLBACKS = {
    'actor':  '未知女優',
    'actors': '未知女優',
    'maker':  '未知片商',
    'title':  '未知標題',
    'date':   '未知日期',
    'year':   '未知年份',
}


def format_string(template: str, data: Dict[str, Any], use_fallback: bool = False) -> str:
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
    - {suffix}: 版本後綴（Fix-1）

    Args:
        use_fallback: True 時空值使用 FALLBACKS（僅資料夾層級傳 True）。
                      False 時空值保持空字串（檔名格式用，避免 [未知片商] 等雜訊）。
    """
    result = template
    fb = FALLBACKS if use_fallback else {}

    # 番號（保證非空，不需 fallback）
    result = result.replace('{num}', data.get('number', ''))

    # 標題
    title = data.get('title', '') or fb.get('title', '')
    result = result.replace('{title}', title)

    # 演員
    actors = data.get('actors', [])
    if actors:
        result = result.replace('{actor}', actors[0])
        result = result.replace('{actors}', ', '.join(actors))
    else:
        result = result.replace('{actor}', fb.get('actor', ''))
        result = result.replace('{actors}', fb.get('actors', ''))

    # 片商
    maker = data.get('maker', '') or fb.get('maker', '')
    result = result.replace('{maker}', maker)

    # 日期
    date = data.get('date', '')
    result = result.replace('{date}', date or fb.get('date', ''))
    result = result.replace('{year}', date[:4] if date else fb.get('year', ''))

    # 後綴（Fix-1，空值就是空字串，不需 fallback）
    result = result.replace('{suffix}', data.get('suffix', ''))

    return sanitize_filename(result.strip())


def crop_to_poster(src_path: str, dst_path: str) -> bool:
    """
    從橫向封面裁切直向海報（Jellyfin poster）。

    裁切模式（純比例自動判斷）：
    - h/w >= 1.4 → 已是直向，直接複製
    - h/w >= 1.0 → 方形（FC2/無碼），裁中間（寬度 = h/1.5，置中）
    - h/w <  1.0 → 標準橫向（有碼），裁右側（起點 = w/1.9 ≈ 右47%）
    """
    try:
        with Image.open(src_path) as img:
            w, h = img.size
            ratio = h / w

            if ratio >= 1.4:
                shutil.copy2(src_path, dst_path)
                return True
            elif ratio >= 1.0:
                crop_w = int(h / 1.5)
                x0 = (w - crop_w) // 2
                cropped = img.convert("RGB").crop((x0, 0, x0 + crop_w, h))
            else:
                x0 = int(w / 1.9)
                cropped = img.convert("RGB").crop((x0, 0, w, h))

            cropped.save(dst_path, 'JPEG', quality=95, subsampling=0)
            return True
    except Exception as e:
        logger.warning(f"[!] crop_to_poster 失敗: {e}")
        return False


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
        logger.warning(f"[!] 下載圖片失敗: {e}")
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
  <title>{html.escape(display_title)}</title>
  <originaltitle>{html.escape(original_title)}</originaltitle>
  <set></set>
  <studio>{html.escape(maker)}</studio>
  <year>{html.escape(year)}</year>
  <premiered>{html.escape(date)}</premiered>
  <plot></plot>
  <runtime></runtime>
  <director></director>
  <poster>{html.escape(basename)}.png</poster>
  <thumb></thumb>
  <fanart>{html.escape(basename)}.jpg</fanart>
'''

    # 演員
    for actor in actors:
        nfo_content += f'''  <actor>
    <name>{html.escape(actor)}</name>
    <role></role>
  </actor>
'''

    # 標籤
    for tag in tags:
        nfo_content += f'  <tag>{html.escape(tag)}</tag>\n'

    if has_subtitle:
        nfo_content += '  <tag>中文字幕</tag>\n'

    # Genre
    for tag in tags:
        nfo_content += f'  <genre>{html.escape(tag)}</genre>\n'

    if has_subtitle:
        nfo_content += '  <genre>中文字幕</genre>\n'

    nfo_content += f'''  <num>{html.escape(number)}</num>
  <release>{html.escape(date)}</release>
  <cover></cover>
  <website>{html.escape(url)}</website>
</movie>'''

    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(nfo_content)
        return True
    except Exception as e:
        logger.error(f"[!] 生成 NFO 失敗: {e}")
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
        'error': None,
        'used_fallbacks': []
    }

    # 轉換路徑為當前環境格式
    try:
        file_path = normalize_path(file_path)
    except ValueError as e:
        result['error'] = str(e)
        return result

    if not os.path.exists(file_path):
        result['error'] = '檔案不存在'
        return result

    # 提取必要資訊
    number = metadata.get('number', '')
    if not number:
        result['error'] = '缺少番號'
        return result

    # 原始檔案資訊
    original_dir = os.path.dirname(file_path)
    original_ext = os.path.splitext(file_path)[1]
    original_filename = os.path.basename(file_path)

    # 準備格式化資料
    actors = metadata.get('actors', [])

    # 標題優先順序：翻譯 > 檔名提取 > 日文原始
    original_title = metadata.get('title', '')  # 日文原始標題
    translated_title = metadata.get('translated_title', '')  # LLM 翻譯/優化的標題
    extracted_title = extract_chinese_title(original_filename, number, actors)

    # 決定最終使用的標題
    if translated_title:
        title = translated_title
        result['title_source'] = 'translated'
    elif extracted_title:
        title = extracted_title
        result['title_source'] = 'extracted'
        result['extracted_title'] = extracted_title
    else:
        title = original_title
        result['title_source'] = 'original'

    format_data = {
        'number': number,
        'title': truncate_title(title, config.get('max_title_length', 50)),
        'actors': actors,
        'maker': metadata.get('maker', ''),
        'date': metadata.get('date', ''),
    }

    # 偵測版本後綴
    suffix_keywords = config.get('suffix_keywords', [])
    suffix = _detect_suffixes(original_filename, suffix_keywords)
    format_data['suffix'] = suffix

    # 記錄哪些欄位實際用了 fallback（僅資料夾層級會觸發 fallback）
    used_fallbacks = []
    if config.get('create_folder', True):
        # 解析資料夾層級中實際使用的 placeholder
        layers = config.get('folder_layers', [])
        if not layers:
            old_format = config.get('folder_format', '{num}')
            layers = [p.strip() for p in old_format.replace('\\', '/').split('/') if p.strip()]
        folder_template = ' '.join(layers)  # 合併所有層級一次檢查

        if ('{actor}' in folder_template or '{actors}' in folder_template) and not format_data.get('actors'):
            used_fallbacks.append('女優')
        if '{maker}' in folder_template and not format_data.get('maker'):
            used_fallbacks.append('片商')
        if ('{date}' in folder_template or '{year}' in folder_template) and not format_data.get('date'):
            used_fallbacks.append('日期')
        if '{title}' in folder_template and not format_data.get('title'):
            used_fallbacks.append('標題')

    # 自動偵測字幕標記（如果 metadata 沒有指定）
    has_subtitle = metadata.get('has_subtitle')
    if has_subtitle is None:
        has_subtitle = check_subtitle(original_filename)

    # 計算目標路徑
    if config.get('create_folder', True):
        # 優先使用新格式 folder_layers
        layers = config.get('folder_layers', [])
        if not layers:
            # 相容舊格式：folder_format 可能含 / 分隔
            old_format = config.get('folder_format', '{num}')
            layers = [p.strip() for p in old_format.replace('\\', '/').split('/') if p.strip()]

        # 過濾空值，分別格式化每層
        # 讀取設定，但上限 120 字符
        max_folder_chars = min(config.get('max_filename_length', 60), 120)
        path_parts = []
        for layer in layers[:3]:  # 限制最多 3 層
            if layer:
                part = truncate_to_chars(format_string(layer, format_data, use_fallback=True), max_folder_chars)
                if part:
                    path_parts.append(part)

        target_dir = os.path.join(original_dir, *path_parts) if path_parts else original_dir
    else:
        target_dir = original_dir

    # 計算新檔名（suffix 保護：先截斷 base，再接回 suffix）
    filename_template = config.get('filename_format', '{num} {title}')
    max_filename_chars = min(config.get('max_filename_length', 60), 120)
    max_chars = max_filename_chars - len(original_ext)

    suffix = format_data.get('suffix', '')
    if suffix and '{suffix}' in filename_template:
        # 先用空 suffix 產生 base，截斷後再接回 suffix
        no_suffix_data = dict(format_data, suffix='')
        base_without_suffix = format_string(filename_template, no_suffix_data)
        base_budget = max(0, max_chars - len(suffix))
        if base_budget == 0:
            filename_base = truncate_to_chars(suffix, max_chars)
        else:
            base_without_suffix = truncate_to_chars(base_without_suffix, base_budget)
            filename_base = base_without_suffix + suffix
    else:
        filename_base = format_string(filename_template, format_data)
        filename_base = truncate_to_chars(filename_base, max_chars)

    new_filename = filename_base + original_ext
    target_path = os.path.join(target_dir, new_filename)

    try:
        # 建立資料夾
        if config.get('create_folder', True):
            os.makedirs(target_dir, exist_ok=True)
            result['new_folder'] = target_dir

        # 移動並重命名檔案
        if file_path != target_path:
            if os.path.exists(target_path):
                result['success'] = False
                result['duplicate'] = True
                result['duplicate_target'] = os.path.basename(target_path)
                return result
            shutil.move(file_path, target_path)
        result['new_filename'] = target_path

        # 下載封面（檔名跟隨影片命名）
        img_url = metadata.get('cover', '')
        if img_url:
            cover_path = os.path.join(target_dir, filename_base + '.jpg')
            if download_image(img_url, cover_path):
                result['cover_path'] = cover_path

        # Jellyfin 模式：產生 poster + fanart
        if config.get('jellyfin_mode') and result.get('cover_path'):
            cover_jpg = result['cover_path']
            # fanart = 原圖複製
            fanart_path = os.path.join(target_dir, filename_base + '-fanart.jpg')
            try:
                shutil.copy2(cover_jpg, fanart_path)
                result['fanart_path'] = fanart_path
            except Exception as e:
                logger.warning(f"[!] Fanart 複製失敗: {e}")
            # poster = 裁切
            poster_path = os.path.join(target_dir, filename_base + '-poster.jpg')
            if crop_to_poster(cover_jpg, poster_path):
                result['poster_path'] = poster_path

        # 生成 NFO（檔名跟隨影片命名）
        nfo_path = os.path.join(target_dir, filename_base + '.nfo')
        tags = metadata.get('tags', [])
        user_tags = metadata.get('user_tags', [])
        all_tags = tags + [t for t in user_tags if t not in tags]  # 合併用戶標籤
        if generate_nfo(
            number=number,
            title=format_data['title'],
            original_title=original_title,  # 日文原始標題
            actors=actors,
            tags=all_tags,
            date=metadata.get('date', ''),
            maker=metadata.get('maker', ''),
            url=metadata.get('url', ''),
            has_subtitle=has_subtitle,
            output_path=nfo_path
        ):
            result['nfo_path'] = nfo_path

        result['used_fallbacks'] = used_fallbacks
        result['success'] = True

    except Exception as e:
        result['error'] = str(e)

    return result
