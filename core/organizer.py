"""
Organizer 模組 - 檔案整理功能（重命名、資料夾、封面、NFO）
從 jav_scraper.py 簡化而來，只處理檔案操作，不含搜尋功能
"""

import os
import re
import sys
import shutil
import requests
import html
from pathlib import Path
from PIL import Image
from typing import Optional, Dict, Any, List, Tuple

from core.config import _STEM_IMAGE_MODES
from core.path_utils import normalize_path
from core.scrapers.utils import has_chinese, check_subtitle, strip_subtitle_markers
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


def _strip_windows_trailing(name: str) -> str:
    # Win32 directory creation silently strips trailing dots/spaces, so target
    # path string and on-disk name diverge → shutil.move WinError 3. See #31.
    if sys.platform == 'win32':
        return name.rstrip('. ')
    return name


def truncate_title(title: str, max_len: int = 50) -> str:
    """截斷標題長度"""
    if not title:
        return ''
    if len(title) <= max_len:
        return title
    return _strip_windows_trailing(title[:max_len - 3] + '...')


def truncate_to_chars(text: str, max_chars: int = 60) -> str:
    """按字符截斷，確保不超過指定長度"""
    if max_chars <= 0:
        return ''
    if max_chars <= 3:
        return text[:max_chars]
    if len(text) <= max_chars:
        return text
    return _strip_windows_trailing(text[:max_chars - 3] + '...')


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

    # 剝除字幕標記（bracket / 純文字 / -C 後綴）
    name = strip_subtitle_markers(name)

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


# ---------------------------------------------------------------------------
# B2：標題 junk-validation + 前綴剝除 helpers（plan-72c FIX A / FIX B）
# ---------------------------------------------------------------------------

def _extracted_has_organize_junk(
    extracted: str,
    number: str,
    metadata: dict,
    config: dict,
) -> bool:
    """
    判斷 extract_chinese_title 的結果是否殘留 organize 模板 artifact。
    回 True（= 應丟棄 extracted）IFF 以下任一命中：
      (i)  日期 token：YYYY[-.]MM[-.]DD 格式
      (ii) 刮削 maker 殘留：maker 非空且出現在提取結果中（大小寫不敏感）
      (iii) suffix token 殘留：config['suffix_keywords'] 中帶前導 '-' 的 token
            以整段帶 dash 比對（不去 dash），尾端加 boundary——
            避免誤殺生檔 standalone '4K'（B-1）。
    mode-agnostic：不讀 external_manager。
    """
    if not extracted:
        return False

    # (i) 日期 token
    if re.search(r'\d{4}[-.]\d{2}[-.]\d{2}', extracted):
        return True

    # (ii) maker 殘留（非空才比對）
    maker = (metadata.get('maker') or '').strip()
    if maker and maker.lower() in extracted.lower():
        return True

    # (iii) suffix token 殘留（保留前導 '-'，帶 boundary）
    for kw in config.get('suffix_keywords', []):
        kw_l = kw.lower().strip()
        if not kw_l:
            continue
        if re.search(re.escape(kw_l) + r'(?=[-_.\s]|$)', extracted.lower()):
            return True

    return False


def _strip_num_prefixes(s: str, number: str) -> str:
    """
    迴圈剝除字串開頭的番號前綴層，直到 fixpoint。
    支援 bracket 形式 [number] 及裸 number（後接非英數邊界）。
    使用 re.escape(number) 防特殊番號（如 FC2-PPV-123）。
    邊界 guard 保證不 over-strip 真標題、不誤命中 ABC-1234 開頭的 ABC-123。
    """
    if not s or not number:
        return s
    _re = re.compile(
        r'^(?:\[' + re.escape(number) + r'\]|' + re.escape(number) + r'(?![0-9A-Za-z]))[\s\-_]*',
        re.IGNORECASE,
    )
    while s:
        nxt = _re.sub('', s, count=1)
        if nxt == s:
            break
        s = nxt
    return s


# ---------------------------------------------------------------------------
# 多段（multi-part）token 偵測與剝除（CD-8 / plan-72b §1.4）
# ---------------------------------------------------------------------------

#: 支援的多段 token 前綴集合（全小寫）
MULTIPART_TOKENS: frozenset = frozenset({'cd', 'dvd', 'part', 'pt', 'disc'})

# 共用編譯正則：前後邊界皆檢查，數字限 1-9 且後不可再接數字
# - 前緣 (?<![A-Za-z0-9])：避免 apartment1 誤命中 part1
# - 後緣 (?=[-_.\s\[\]()]|$)：token 後須為分隔符 / bracket / 字串終點
_MULTIPART_RE = re.compile(
    r'(?<![A-Za-z0-9])(cd|dvd|part|pt|disc)([1-9])(?![0-9])(?=[-_.\s\[\]()]|$)',
    re.IGNORECASE,
)


def _detect_multipart_token(filename: str) -> Optional[Tuple[str, int]]:
    """
    偵測原始檔名中的多段 token（cd/dvd/part/pt/disc 後接 1-9）。

    Args:
        filename: 原始檔名（含副檔名，如 ``MIRD-151-cd1.mkv``）。

    Returns:
        ``(raw_token_lower, part_number)`` — 如 ``("cd1", 1)``；無匹配回 ``None``。
        多個匹配時取 stem 中位置最靠後者（避免標題中段巧合字串蓋過尾端 token）。
    """
    if not filename:
        return None
    stem = os.path.splitext(filename)[0]
    lower_stem = stem.lower()
    matches = list(_MULTIPART_RE.finditer(lower_stem))
    if not matches:
        return None
    # 取最靠後（span 最大 start）的匹配
    last = matches[-1]
    prefix = last.group(1).lower()
    digit = int(last.group(2))
    return (f'{prefix}{digit}', digit)


def _strip_part_token(stem: str) -> str:
    """
    從已去副檔名的 stem 剝除最靠後的多段 token（含其前導分隔符）。

    與 ``_detect_multipart_token`` 共用同一套邊界正則，確保契約一致。

    Args:
        stem: 已去副檔名的字串（如 ``MIRD-151-cd1``）。

    Returns:
        剝除多段 token 及其前導分隔符後的 stem；無 token 時原樣回傳（no-op）。
        保留 base 段原始大小寫。
    """
    if not stem:
        return stem
    lower_stem = stem.lower()
    matches = list(_MULTIPART_RE.finditer(lower_stem))
    if not matches:
        return stem
    last = matches[-1]
    token_start = last.start()  # token 本體在 lower_stem 的起始位置
    token_end = last.end()      # 不含後緣 lookahead（lookahead 不消耗）
    # 若 token 前有分隔符，一併剝除（[-_.\s\[(]）
    if token_start > 0 and stem[token_start - 1] in '-_. \t([':
        strip_from = token_start - 1
    else:
        strip_from = token_start
    return stem[:strip_from] + stem[token_end:]


def _is_multipart_kw(kw: str) -> bool:
    """
    判斷一個 suffix keyword 是否為多段 token（cd/dvd/part/pt/disc 後接 1-9）。

    外部模式下用來濾掉 suffix_keywords 中的多段 token，避免與 part_tail 雙寫。
    複用 `_MULTIPART_RE` 與 `MULTIPART_TOKENS`，確保契約與 `_detect_multipart_token` 一致。

    Args:
        kw: suffix keyword，如 ``'-cd1'``、``'_uc'``、``'-4k'``。

    Returns:
        True 若 keyword 是多段 token（strip 前導分隔符後 fullmatch）；否則 False。
        ``'-cd1'`` / ``'-dvd1'`` / ``'part2'`` → True；``'-4k'`` / ``'_uc'`` → False。
    """
    if not kw:
        return False
    # strip 前導分隔符（keyword 慣例帶 -/_/.，也允許無前綴如 'cd1'）
    stripped = kw.lstrip('-_. ')
    if not stripped:
        return False
    # fullmatch：整個 stripped 字串必須是 (prefix)(1-9)，且後不再接數字
    # 與 _MULTIPART_RE 用同一 MULTIPART_TOKENS 集合、同一數字規則（1-9，不含 cd10+）
    m = re.fullmatch(r'(cd|dvd|part|pt|disc)([1-9])', stripped, re.IGNORECASE)
    return m is not None


_VR_UNIQUE: frozenset = frozenset({
    'mkx200', 'mkx220', 'vrca220', 'rf52', 'fisheye190', 'fisheye',
    'f180', '180f', '180x180', 'eac360', '360eac', 'mono180', '180mono',
    'mono360', '360mono', '3dh', '3dv', 'lrf', 'sbsf', 'fsbs', 'hsbs',
    'tbf', 'ftab', 'htab',
})

_VR_AMBIGUOUS: frozenset = frozenset({
    '180', '360', 'sbs', 'lr', 'rl', 'tb', 'bt', 'ou',
})


def _detect_vr_cluster(filename: str) -> Optional[str]:
    """
    偵測檔名中的 VR 投影 token cluster，回傳首個~末個 confirmed run 的 raw 子字串。
    無 VR token 或不滿足共現條件時回傳 None（守零變化）。

    演算法（CD-68-1/2/3，Codex P2 修正）：
    1. 去副檔名取 stem
    2. 以 [_.-空格[]()] 為分隔符切詞，取 (token, start, end) 序列
    3. 逐 token 分類：unique / ambiguous / none
    4. 將連續的 VR token（unique 或 ambiguous，中間無 none token）聚成 maximal run。
       遇到 none token 立即斷開當前 run。
    5. 每個 run 的「confirmed」條件：含 ≥1 unique 或 ≥2 ambiguous。
       單一孤立 ambiguous 自成一 run，不 confirmed。
    6. 無任何 confirmed run → return None。
    7. 有 confirmed run → 回傳「第一個 confirmed run 的首 token start」到
       「最後一個 confirmed run 的末 token end」之間的 raw 子字串（stem[start:end]）。

    共現限定在連續 run 內（high-precision「same cluster」契約），
    取代原 whole-stem min/max（Codex P2 修正）。
    """
    stem = os.path.splitext(filename)[0]
    tokens = [(m.group(), m.start(), m.end()) for m in re.finditer(r'[^_.\-\s\[\]()]+', stem)]

    # 建立每個 token 的 VR 類別
    classified = []  # (tok, s, e, kind)  kind: 'unique' | 'ambiguous' | 'none'
    for tok, s, e in tokens:
        low = tok.lower()
        if low in _VR_UNIQUE:
            classified.append((tok, s, e, 'unique'))
        elif low in _VR_AMBIGUOUS:
            classified.append((tok, s, e, 'ambiguous'))
        else:
            classified.append((tok, s, e, 'none'))

    # 聚成 maximal 連續 VR run（none token 斷開）
    runs = []  # list of [(tok, s, e, kind), ...]
    current_run = []
    for entry in classified:
        _, _, _, kind = entry
        if kind != 'none':
            current_run.append(entry)
        else:
            if current_run:
                runs.append(current_run)
                current_run = []
    if current_run:
        runs.append(current_run)

    # 判斷每個 run 是否 confirmed
    confirmed_runs = []
    for run in runs:
        has_unique = any(kind == 'unique' for _, _, _, kind in run)
        ambiguous_count = sum(1 for _, _, _, kind in run if kind == 'ambiguous')
        if has_unique or ambiguous_count >= 2:
            confirmed_runs.append(run)

    if not confirmed_runs:
        return None

    # 只取第一個 confirmed run（避免兩個被 non-VR token 隔開的 confirmed run
    # 被 span 在一起、把中間非 VR 文字包進 cluster，Codex P3）。
    # 真實 VR 命名 cluster 為單一連續 run；多 confirmed run 屬非常規命名。
    first_run = confirmed_runs[0]
    start = first_run[0][1]    # 首 token start
    end = first_run[-1][2]     # 末 token end
    return stem[start:end]


FALLBACKS = {
    'actor':  '未知女優',
    'actors': '未知女優',
    'maker':  '未知片商',
    'title':  '未知標題',
    'date':   '未知日期',
    'year':   '未知年份',
    'month':  '未知月份',
    'day':    '未知日',
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
    - {month}: 月份（2位）
    - {day}: 日（2位）
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
    result = result.replace('{month}', date[5:7] if len(date) >= 7 else fb.get('month', ''))
    result = result.replace('{day}',   date[8:10] if len(date) >= 10 else fb.get('day', ''))

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


def generate_jellyfin_images(cover_path: str, base_stem: str) -> dict:
    """為單部影片產生 Jellyfin poster + fanart（供批次補齊用）。

    Args:
        cover_path: 封面圖片的完整檔案系統路徑
        base_stem: 目標檔名 stem（不含副檔名，已移除 -poster/-fanart 後綴）
    """
    result = {'fanart': False, 'poster': False}

    fanart_path = base_stem + '-fanart.jpg'
    poster_path = base_stem + '-poster.jpg'

    # fanart = 原圖複製
    try:
        shutil.copy2(cover_path, fanart_path)
        result['fanart'] = True
        result['fanart_path'] = fanart_path
    except Exception as e:
        logger.warning(f"[!] generate_jellyfin_images fanart 複製失敗: {e}")

    # poster = 裁切
    if crop_to_poster(cover_path, poster_path):
        result['poster'] = True
        result['poster_path'] = poster_path

    return result


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
    has_vr: bool = False,
    output_path: str = '',
    has_poster: bool = False,
    has_fanart: bool = False,
    director: str = '',
    duration: Optional[int] = None,
    series: str = '',
    label: str = '',
    user_tags: List[str] = None,
    summary: str = '',
    rating: Optional[float] = None,
    mpaa: str = 'JP-18+',
    external_manager: str = 'off',
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
        external_manager: 外部媒體管理器模式（"off" / "jellyfin" / "emby" / "kodi"）
            - "off"（預設）：最小輸出，無 F3 欄位
            - "jellyfin" / "emby"：附加 F3 五欄位，poster/fanart 使用 stem 長格式命名
            - "kodi"：附加 F3 五欄位；poster/fanart 與 jellyfin/emby 相同（stem 長格式），
              Kodi 在所有資料夾 layout 下均識別 {basename}-poster.jpg/{basename}-fanart.jpg
    """
    if not output_path:
        return False

    actors = actors or []
    tags = tags or []
    user_tags = user_tags or []
    year = date[:4] if date else ''

    # 封面檔名（不含副檔名）
    basename = os.path.splitext(os.path.basename(output_path))[0]

    # 顯示標題（belt-and-suspenders：剝除前置番號前綴後組 display_title，B2 FIX B CD-c7）
    _t = title or original_title
    _t = _strip_num_prefixes(_t, number) if _t else _t
    display_title = f"[{number}]{_t}" if _t else f"[{number}]"

    poster_suffix = '-poster' if has_poster else ''
    fanart_suffix = '-fanart' if has_fanart else ''

    # poster/fanart tag：所有模式（off / jellyfin / emby / kodi）均使用 stem 長格式。
    # off → poster_suffix='' → {basename}.jpg；jellyfin/emby/kodi → {basename}-poster.jpg。
    poster_tag = f'{html.escape(basename)}{poster_suffix}.jpg'
    fanart_tag = f'{html.escape(basename)}{fanart_suffix}.jpg'

    set_tag = (
        f"<set><name>{html.escape(series)}</name></set>" if series else "<set></set>"
    )
    runtime_tag = f"<runtime>{duration}</runtime>" if duration is not None else "<runtime></runtime>"
    director_tag = f"<director>{html.escape(director)}</director>" if director else "<director></director>"
    label_tag = f"<label>{html.escape(label)}</label>"
    # 63c-5（CD-63c-10）：metatube summary→<plot>，rating×2→<rating>（0-10 Jellyfin scale，
    # 僅有值才寫），<mpaa>JP-18+ 無條件寫（所有 JAV 共通）。rating_line 含 \n + 2-space 縮排，
    # 空時不留空行（embedded 在 <plot> 之前）。
    rating_line = f"  <rating>{rating * 2:.1f}</rating>\n" if (rating is not None and rating > 0) else ""

    nfo_content = f'''<?xml version="1.0" encoding="utf-8"?>
<movie>
  <title>{html.escape(display_title)}</title>
  <originaltitle>{html.escape(original_title)}</originaltitle>
  {set_tag}
  <studio>{html.escape(maker)}</studio>
  {label_tag}
  <year>{html.escape(year)}</year>
  <premiered>{html.escape(date)}</premiered>
{rating_line}  <plot>{html.escape(summary)}</plot>
  <mpaa>{html.escape(mpaa)}</mpaa>
  {runtime_tag}
  {director_tag}
  <poster>{poster_tag}</poster>
  <thumb>{html.escape(basename)}.jpg</thumb>
  <fanart>{fanart_tag}</fanart>
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

    if has_vr and not any(t.strip().lower() == 'vr' for t in tags):
        nfo_content += '  <tag>VR</tag>\n'

    # 用戶自訂標籤（獨立於 scraper tags，其他平台忽略）
    for ut in user_tags:
        nfo_content += f'  <user_tag>{html.escape(ut)}</user_tag>\n'

    # Genre
    for tag in tags:
        nfo_content += f'  <genre>{html.escape(tag)}</genre>\n'

    if has_subtitle:
        nfo_content += '  <genre>中文字幕</genre>\n'

    if has_vr and not any(t.strip().lower() == 'vr' for t in tags):
        nfo_content += '  <genre>VR</genre>\n'

    # T3：F3 五欄位區塊（僅 external_manager != "off" 時輸出）
    # 注意：這會造成 NFO 內同時有兩個 default="true" 的 uniqueid（home + num）。
    # POC 實證 Jellyfin 容忍（兩個 ProviderId 都正確讀到），故意保留 home 行不動。
    if external_manager != 'off':
        external_block = (
            f'  <lockdata>true</lockdata>\n'
            f'  <uniqueid type="num" default="true">{html.escape(number)}</uniqueid>\n'
            f'  <sorttitle>{html.escape(display_title)}</sorttitle>\n'
            f'  <country>Japan</country>\n'
            f'  <language>ja</language>\n'
        )
    else:
        external_block = ''

    nfo_content += f'''  <num>{html.escape(number)}</num>
  <release>{html.escape(date)}</release>
  <cover></cover>
  <website>{html.escape(url)}</website>
{external_block}  <uniqueid type="home" default="true">{html.escape(number)}</uniqueid>
</movie>'''

    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(nfo_content)
        return True
    except Exception as e:
        logger.error(f"[!] 生成 NFO 失敗: {e}")
        return False


def find_subtitle_files(video_path: str) -> List[str]:
    """
    找出與影片同名的字幕檔（.srt/.ass/.ssa）。

    匹配規則：
    - {stem}.srt / {stem}.ass / {stem}.ssa  （完全同名）
    - {stem}.*.srt / {stem}.*.ass / {stem}.*.ssa  （帶語言後綴，如 .cht.srt）

    不匹配：
    - 不同名字幕（bbb.srt）
    - 底線分隔（aaa_chs.srt）

    Args:
        video_path: 影片完整路徑

    Returns:
        符合規則的字幕路徑列表（影片不存在時回傳空列表）
    """
    p = Path(video_path)
    if not p.parent.exists():
        return []

    stem = p.stem
    # escape glob 特殊字元（如 [ ] ? *），防止檔名被誤解讀
    from glob import escape as glob_escape
    stem_esc = glob_escape(stem)
    results = []
    for ext in ('srt', 'ass', 'ssa'):
        # 完全同名：aaa.srt
        for match in p.parent.glob(f"{stem_esc}.{ext}"):
            results.append(str(match))
        # 帶語言後綴：aaa.*.srt（.cht.srt, .chs.srt 等）
        for match in p.parent.glob(f"{stem_esc}.*.{ext}"):
            results.append(str(match))
    return results


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
    except ValueError:
        logger.exception("normalize_path 失敗")
        result['error'] = '路徑格式不支援，請確認路徑設定'
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

    # 外部管理器模式（單一來源，早偵測層；CD-72b-T5）
    ext_mode = config.get('external_manager', 'off')

    # 偵測 VR cluster（CD-68-5/6/7）：算一次，作用域涵蓋 title 剝除、組裝段與 nfo 呼叫（GA）
    # 上移至 extract_chinese_title 之前，用於剝除 extracted_title 尾端的 VR token（Codex P2）
    vr_cluster = _detect_vr_cluster(original_filename)
    vr_tail = f'_{vr_cluster}' if vr_cluster else ''

    # 多段（multipart）token 早偵測（CD-72b-T5）；off 模式恆不啟用（part_tail=''）
    part_match = _detect_multipart_token(original_filename) if ext_mode != 'off' else None
    part_tail = f'-{part_match[0]}' if part_match else ''   # e.g. '-cd1'；off 模式恆 ''

    # budget reserve：兩分支共用，part_tail 也預留；off 模式 part_tail='' → 等同現狀（CD-68-7/CD-72b-T5）
    reserve = len(vr_tail) + len(part_tail)

    # 準備格式化資料
    actors = metadata.get('actors', [])

    # 標題優先順序：翻譯 > 檔名提取 > 日文原始
    original_title = metadata.get('title', '')  # 日文原始標題
    translated_title = metadata.get('translated_title', '')  # LLM 翻譯/優化的標題
    extracted_title = extract_chinese_title(original_filename, number, actors)

    # 剝除 extracted_title 尾端的 VR cluster（含可選 bracket/paren 包裝，Codex P2 二次修正）
    # _detect_vr_cluster 把 []() 當分隔符 → cluster 不含 bracket，但 extracted_title 保留 bracket，
    # 故需匹配可選的開/閉 bracket/paren 包裝；否則 _[180_LR] 不被剝 → 與尾端 vr_tail 雙寫。
    if vr_cluster and extracted_title:
        _vr_tail_re = re.compile(r'[\[(]?' + re.escape(vr_cluster) + r'[\])]?[\s_.\-]*$')
        _m = _vr_tail_re.search(extracted_title)
        if _m:
            _trimmed = extracted_title[:_m.start()].rstrip('_-. ')
            extracted_title = _trimmed or extracted_title

    # FIX A：B2 junk-validation（CD-c5/c6）
    # 若提取結果殘留 organize 模板 artifact（日期/maker/suffix），丟棄改用翻譯/刮削源
    if extracted_title and _extracted_has_organize_junk(extracted_title, number, metadata, config):
        extracted_title = None   # fall through 到翻譯/刮削源（CD-c6）

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

    # FIX B：B2 標題決定段去前綴（CD-c7）
    # 勝出 title 若帶 [{number}]/{number} 前綴，迴圈剝盡至本體
    # → 檔名（format_data['title']）、NFO <title>、<sorttitle> 同時受惠
    # → 迴圈剝盡可修復舊 bug 寫進磁碟/DB 的 [ABC-123][ABC-123]Title 雙重堆疊
    if title:
        title = _strip_num_prefixes(title, number)

    format_data = {
        'number': number,
        'title': truncate_title(title, config.get('max_title_length', 50)),
        'actors': actors,
        'maker': metadata.get('maker', ''),
        'date': metadata.get('date', ''),
    }

    # 偵測版本後綴；外部模式過濾掉多段 token 避免 {suffix}+part_tail 雙寫（CD-72b-T5）
    # 注意：絕不 mutate config['suffix_keywords']，只過濾傳入 _detect_suffixes 的區域變數
    suffix_keywords = config.get('suffix_keywords', [])
    if ext_mode != 'off':
        detect_keywords = [kw for kw in suffix_keywords if not _is_multipart_kw(kw)]
    else:
        detect_keywords = suffix_keywords   # off 模式：原始未過濾 list，byte-identical
    suffix = _detect_suffixes(original_filename, detect_keywords)
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
        date_val = format_data.get('date', '') or ''
        date_missing = (
            ('{date}' in folder_template and not date_val) or
            ('{year}' in folder_template and len(date_val) < 4) or
            ('{month}' in folder_template and len(date_val) < 7) or
            ('{day}' in folder_template and len(date_val) < 10)
        )
        if date_missing:
            used_fallbacks.append('日期')
        if '{title}' in folder_template and not format_data.get('title'):
            used_fallbacks.append('標題')

    # 字幕偵測：先看 metadata，再補檔案系統級偵測
    has_subtitle = metadata.get('has_subtitle')
    subtitle_files = find_subtitle_files(file_path)
    if has_subtitle is None:
        has_subtitle = check_subtitle(original_filename) or bool(subtitle_files)
    elif subtitle_files:
        has_subtitle = True  # sidecar 字幕存在 → 覆寫上游 False

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
        # 先用空 suffix 產生 base，截斷後再接回 suffix；base_budget 扣 reserve（CD-68-5/7）
        no_suffix_data = dict(format_data, suffix='')
        base_without_suffix = format_string(filename_template, no_suffix_data)
        base_budget = max(0, max_chars - len(suffix) - reserve)
        if base_budget == 0:
            filename_base = truncate_to_chars(suffix, max(0, max_chars - reserve))
        else:
            base_without_suffix = truncate_to_chars(base_without_suffix, base_budget)
            filename_base = base_without_suffix + suffix
    else:
        filename_base = format_string(filename_template, format_data)
        filename_base = truncate_to_chars(filename_base, max(0, max_chars - reserve))
    # VR tail 永遠最後接（CD-68-6）；vr_tail='' 時零變化（CD-68-9）
    filename_base = filename_base + vr_tail
    # P1-A 修正（Codex）：{title} 欄位（尤其是 extracted_title）可能殘留多段 token
    # （如 extract_chinese_title 保留 '某中文標題-part2[HD]'），導致 part_tail 雙寫。
    # 在接 part_tail 之前，先從 filename_base 剝除最靠後的多段 token（_strip_part_token
    # 無 token 時為 no-op → 乾淨標題案例完全不影響輸出）。
    # off 模式 part_tail='' → if 分支不進入，行為與修前 byte-identical。
    # 注意：不需另在 extracted_title 層剝除，組裝後整體剝更穩健（任何欄位來源均覆蓋）。
    if part_tail:
        filename_base = _strip_part_token(filename_base)  # 移除 {title} 等欄位遺留的多段 token
    # part token 接在 VR tail 之後（最末）；off 模式 part_tail='' → no-op（CD-72b-T5）
    # 順序：{base}{vr_tail}{part_tail}；Jellyfin stacking 要求 part token 落在 stem 最末
    filename_base = filename_base + part_tail
    # 最終長度上限保護（Codex PR P2）：即使退化情形也不突破 max_filename_length。
    # 正常/spec 情形 reserve 已預留 → base+vr_tail+part_tail == max_chars → 此為 no-op；
    # 僅 max_filename_length 被設到連 ext+VR cluster+part token 都裝不下時才作用。
    filename_base = truncate_to_chars(filename_base, max_chars)

    new_filename = filename_base + original_ext
    target_path = os.path.join(target_dir, new_filename)

    try:
        # 建立資料夾
        if config.get('create_folder', True):
            try:
                os.makedirs(target_dir, exist_ok=True)
            except PermissionError:
                result['error'] = '無法建立資料夾，請確認目標路徑的寫入權限'
                return result
            result['new_folder'] = target_dir

        # 移動並重命名檔案
        if file_path != target_path:
            if os.path.exists(target_path):
                result['success'] = False
                result['duplicate'] = True
                result['duplicate_target'] = os.path.basename(target_path)
                return result
            shutil.move(file_path, target_path)

            # 搬移字幕檔（影片有搬移時才執行）
            subs_to_move = subtitle_files
            video_stem = Path(file_path).stem
            for sub_path in subs_to_move:
                try:
                    sub_name = os.path.basename(sub_path)
                    sub_suffix = sub_name[len(video_stem):]  # e.g. ".cht.srt" or ".srt"
                    sub_target = os.path.join(target_dir, filename_base + sub_suffix)
                    shutil.move(sub_path, sub_target)
                except Exception as e:
                    logger.warning(f"字幕搬移失敗 {sub_path}: {e}")

        result['new_filename'] = target_path

        # 下載封面（檔名跟隨影片命名）
        img_url = metadata.get('cover', '')
        if img_url:
            cover_path = os.path.join(target_dir, filename_base + '.jpg')
            if download_image(img_url, cover_path):
                result['cover_path'] = cover_path

        # 外部管理器模式：依 ext_mode 決定 poster/fanart 命名規則（ext_mode 已在早偵測層定義）
        # jellyfin/emby 與 kodi 均使用 stem 長格式（{stem}-poster.jpg / {stem}-fanart.jpg），
        # Kodi 在所有資料夾 layout 下均識別此命名，無需 per-folder 偵測。
        if ext_mode != 'off' and result.get('cover_path'):
            cover_jpg = result['cover_path']
            if ext_mode in _STEM_IMAGE_MODES:
                # 兩種模式均使用 stem 長格式（collision-free，Kodi 正典）
                fanart_path = os.path.join(target_dir, filename_base + '-fanart.jpg')
                poster_path = os.path.join(target_dir, filename_base + '-poster.jpg')
            else:
                # 未知值防禦：不產圖
                fanart_path = None
                poster_path = None
            if fanart_path:
                # fanart = 原圖複製
                try:
                    shutil.copy2(cover_jpg, fanart_path)
                    result['fanart_path'] = fanart_path
                except Exception as e:
                    logger.warning(f"[!] Fanart 複製失敗: {e}")
            if poster_path:
                # poster = 裁切
                if crop_to_poster(cover_jpg, poster_path):
                    result['poster_path'] = poster_path

        # extrafanart 下載（download_sample_images 控制，需 create_folder=True 才有 per-video 目錄）
        # create_folder=False 時多片共用同一資料夾，fanart1.jpg 會互相覆蓋，故禁用
        if config.get('download_sample_images') and config.get('create_folder'):
            sample_images = metadata.get('sample_images', [])
            if sample_images:
                extrafanart_dir = os.path.join(target_dir, 'extrafanart')
                try:
                    os.makedirs(extrafanart_dir, exist_ok=True)
                    for i, url in enumerate(sample_images, 1):
                        try:
                            dest = os.path.join(extrafanart_dir, f'fanart{i}.jpg')
                            download_image(url, dest)
                        except Exception as e:
                            logger.warning(f"extrafanart {i} 下載失敗: {e}")
                except Exception as e:
                    logger.warning(f"extrafanart 目錄建立失敗: {e}")

        # 生成 NFO（檔名跟隨影片命名）
        nfo_path = os.path.join(target_dir, filename_base + '.nfo')
        # part-2+ 且外部模式：跳過 NFO（CD-2 只有一份 metadata 由 cd1 產；封面/poster/fanart 照常）
        # off 模式恆不跳（即使 cd2 也照產 NFO，byte-identical）（CD-72b-T5）
        skip_nfo = bool(part_match) and part_match[1] >= 2 and ext_mode != 'off'
        if skip_nfo:
            result['nfo_path'] = None            # dict 初值已 None，明確設更清楚
            result['skipped_nfo_multipart'] = True
        else:
            tags = metadata.get('tags', [])
            user_tags = metadata.get('user_tags', [])
            if generate_nfo(
                number=number,
                title=format_data['title'],
                original_title=original_title,  # 日文原始標題
                actors=actors,
                tags=tags,
                user_tags=user_tags,
                date=metadata.get('date', ''),
                maker=metadata.get('maker', ''),
                url=metadata.get('url', ''),
                has_subtitle=has_subtitle,
                has_vr=(vr_cluster is not None),
                output_path=nfo_path,
                has_poster=bool(result.get('poster_path')),
                has_fanart=bool(result.get('fanart_path')),
                director=metadata.get('director', ''),
                duration=metadata.get('duration'),
                series=metadata.get('series', ''),
                label=metadata.get('label', ''),
                # 63c-5：metadata 是 raw search_jav 結果 dict，summary/rating 走 _ 前綴 carrier
                # （server re-search 路徑帶值；frontend-passed 路徑因 echo strip 無值 → default）
                summary=metadata.get('_summary', ''),
                rating=metadata.get('_rating'),
                external_manager=ext_mode,
            ):
                result['nfo_path'] = nfo_path

        result['used_fallbacks'] = used_fallbacks
        result['success'] = True

    except Exception as e:
        logger.exception("organize_file 失敗: %s → %s", file_path, target_dir)
        result['error'] = '檔案整理失敗，請查看日誌'

    return result
