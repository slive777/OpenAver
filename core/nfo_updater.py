"""
NFO Updater - 批次更新 NFO 檔案中缺失的欄位
整合到 AVList 頁面使用
"""

import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Generator

from core.scraper import search_jav
from core.path_utils import normalize_path


def needs_update(info: dict, has_nfo: bool = True) -> Tuple[bool, List[str]]:
    """檢查影片是否需要更新

    Args:
        info: VideoInfo.to_dict() 的結果
        has_nfo: 是否有 NFO 檔案（從 cache 的 nfo_mtime > 0 判斷）

    Returns:
        Tuple[bool, List[str]]: (是否需要更新, 缺失欄位列表)
    """
    # 必須有 NFO 且有番號才檢查
    if not has_nfo or not info.get('num'):
        return False, []

    missing = []

    # 檢查各欄位
    if not info.get('title'):
        missing.append('title')
    if not info.get('date'):
        missing.append('date')
    if not info.get('actor'):
        missing.append('actor')
    if not info.get('genre'):
        missing.append('genre')
    if not info.get('maker'):
        missing.append('maker')

    return len(missing) > 0, missing


def check_cache_needs_update(cache: Dict[str, dict]) -> Dict:
    """檢查 cache 中需要更新的影片

    只檢查有 NFO 檔案的影片（nfo_mtime > 0）

    Args:
        cache: avlist_output_cache.json 的內容

    Returns:
        統計資訊字典
    """
    stats = {
        'need_update': 0,
        'no_title': 0,
        'no_date': 0,
        'no_actor': 0,
        'no_genre': 0,
        'no_maker': 0,
        'has_nfo_count': 0,  # 有 NFO 的影片數
        'paths': []  # 需要更新的影片路徑
    }

    for path, data in cache.items():
        if path.startswith('_'):  # 跳過 metadata
            continue

        # 檢查是否有 NFO 檔案（nfo_mtime > 0 表示有）
        nfo_mtime = data.get('nfo_mtime', 0)
        has_nfo = nfo_mtime > 0

        if has_nfo:
            stats['has_nfo_count'] += 1

        info = data.get('info', {})
        need, missing = needs_update(info, has_nfo)

        if need:
            stats['need_update'] += 1
            stats['paths'].append(path)

            for field in missing:
                key = f'no_{field}'
                if key in stats:
                    stats[key] += 1

    return stats


def get_nfo_path_from_video(video_path: str) -> Optional[str]:
    """從影片路徑取得對應的 NFO 檔案路徑

    Args:
        video_path: 影片檔案路徑（可能是 file:/// URL 或 Linux 路徑）

    Returns:
        NFO 檔案的路徑，不存在則返回 None
    """
    # 移除 file:/// 前綴
    if video_path.startswith('file:///'):
        video_path = video_path[8:]

    # 嘗試轉換 Windows 路徑為 WSL 路徑
    # C:/Users/... -> /mnt/c/Users/...
    if len(video_path) >= 2 and video_path[1] == ':':
        drive = video_path[0].lower()
        rest = video_path[2:].replace('\\', '/')
        video_path = f'/mnt/{drive}{rest}'

    # 取得 NFO 路徑
    video_p = Path(video_path)
    nfo_path = video_p.with_suffix('.nfo')

    if nfo_path.exists():
        return str(nfo_path)

    return None


def parse_nfo(nfo_path: str) -> Tuple[Optional[ET.ElementTree], Optional[ET.Element]]:
    """解析 NFO 檔案"""
    try:
        tree = ET.parse(nfo_path)
        root = tree.getroot()
        return tree, root
    except Exception:
        return None, None


def get_element_text(root: ET.Element, tag: str) -> str:
    """取得元素文字"""
    elem = root.find(tag)
    if elem is not None and elem.text:
        return elem.text.strip()
    return ''


def set_element_text(root: ET.Element, tag: str, text: str, after_tag: str = None):
    """設定或新增元素文字"""
    elem = root.find(tag)
    if elem is not None:
        elem.text = text
    else:
        new_elem = ET.Element(tag)
        new_elem.text = text
        if after_tag:
            for i, child in enumerate(root):
                if child.tag == after_tag:
                    root.insert(i + 1, new_elem)
                    return
        root.append(new_elem)


def add_actor(root: ET.Element, actor_name: str):
    """新增演員元素"""
    # 檢查是否已存在
    for actor_elem in root.findall('.//actor/name'):
        if actor_elem.text and actor_elem.text.strip() == actor_name:
            return False

    actor = ET.SubElement(root, 'actor')
    name = ET.SubElement(actor, 'name')
    name.text = actor_name
    return True


def add_tags_and_genres(root: ET.Element, new_tags: List[str]) -> int:
    """新增 tag 和 genre 元素"""
    existing_tags = set()
    existing_genres = set()

    for elem in root.findall('tag'):
        if elem.text:
            existing_tags.add(elem.text.strip())
    for elem in root.findall('genre'):
        if elem.text:
            existing_genres.add(elem.text.strip())

    added_count = 0
    for tag_text in new_tags:
        tag_text = tag_text.strip()
        if not tag_text:
            continue
        if tag_text not in existing_tags:
            tag_elem = ET.SubElement(root, 'tag')
            tag_elem.text = tag_text
            existing_tags.add(tag_text)
            added_count += 1
        if tag_text not in existing_genres:
            genre_elem = ET.SubElement(root, 'genre')
            genre_elem.text = tag_text
            existing_genres.add(tag_text)

    return added_count


def indent_xml(elem: ET.Element, level: int = 0):
    """格式化 XML 縮排"""
    i = "\n" + level * "  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for child in elem:
            indent_xml(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i


def update_nfo_file(nfo_path: str, metadata: dict, info: dict) -> Tuple[bool, str]:
    """更新單個 NFO 檔案

    只補全空欄位，不覆蓋已有資料

    Args:
        nfo_path: NFO 檔案路徑
        metadata: 從 search_jav() 取得的 metadata
        info: 原始 VideoInfo 資料（用於判斷哪些欄位需要補）

    Returns:
        Tuple[bool, str]: (是否有修改, 訊息)
    """
    tree, root = parse_nfo(nfo_path)
    if not root:
        return False, "無法解析 NFO"

    modified = False
    changes = []

    # 補標題
    if not info.get('title') and metadata.get('title'):
        # 保留 originaltitle
        existing_title = get_element_text(root, 'title')
        if existing_title and not get_element_text(root, 'originaltitle'):
            set_element_text(root, 'originaltitle', existing_title, after_tag='title')
        set_element_text(root, 'title', metadata['title'])
        modified = True
        changes.append('title')

    # 補日期
    if not info.get('date') and metadata.get('date'):
        set_element_text(root, 'premiered', metadata['date'])
        modified = True
        changes.append('date')

    # 補演員
    if not info.get('actor') and metadata.get('actors'):
        for actor_name in metadata['actors']:
            if actor_name:
                add_actor(root, actor_name)
        modified = True
        changes.append('actors')

    # 補標籤
    if not info.get('genre') and metadata.get('tags'):
        added = add_tags_and_genres(root, metadata['tags'])
        if added > 0:
            modified = True
            changes.append(f'tags({added})')

    # 補片商
    if not info.get('maker') and metadata.get('maker'):
        set_element_text(root, 'studio', metadata['maker'])
        modified = True
        changes.append('maker')

    if modified:
        indent_xml(root)
        tree.write(nfo_path, encoding='utf-8', xml_declaration=True)
        return True, ','.join(changes)

    return False, "無需更新"


def update_videos_generator(
    cache: Dict[str, dict],
    paths: List[str]
) -> Generator[dict, None, dict]:
    """更新影片的生成器（用於 SSE 串流）

    Args:
        cache: avlist_output_cache.json 的內容
        paths: 需要更新的影片路徑列表

    Yields:
        進度訊息 dict

    Returns:
        統計結果 dict
    """
    stats = {
        'total': len(paths),
        'success': 0,
        'failed': 0,
        'skipped': 0,
        'no_nfo': 0,
        'no_metadata': 0,
    }

    for i, path in enumerate(paths, 1):
        data = cache.get(path, {})
        info = data.get('info', {})
        num = info.get('num', '')

        yield {
            'type': 'progress',
            'current': i,
            'total': len(paths),
            'num': num,
            'status': f'處理 {num}'
        }

        # 取得 NFO 路徑
        nfo_path = get_nfo_path_from_video(path)
        if not nfo_path:
            yield {
                'type': 'log',
                'level': 'warn',
                'message': f'[{i}] {num}: NFO 不存在'
            }
            stats['no_nfo'] += 1
            stats['skipped'] += 1
            continue

        # 從網路取得 metadata
        yield {
            'type': 'log',
            'level': 'info',
            'message': f'[{i}] {num}: 搜尋中...'
        }

        try:
            metadata = search_jav(num)
        except Exception as e:
            yield {
                'type': 'log',
                'level': 'error',
                'message': f'[{i}] {num}: 搜尋錯誤 - {e}'
            }
            stats['failed'] += 1
            continue

        if not metadata:
            yield {
                'type': 'log',
                'level': 'warn',
                'message': f'[{i}] {num}: 找不到資料'
            }
            stats['no_metadata'] += 1
            stats['skipped'] += 1
            continue

        # 更新 NFO
        try:
            updated, msg = update_nfo_file(nfo_path, metadata, info)
            if updated:
                yield {
                    'type': 'log',
                    'level': 'info',
                    'message': f'[{i}] {num}: 已更新 ({msg})'
                }
                stats['success'] += 1
            else:
                yield {
                    'type': 'log',
                    'level': 'info',
                    'message': f'[{i}] {num}: {msg}'
                }
                stats['skipped'] += 1
        except Exception as e:
            yield {
                'type': 'log',
                'level': 'error',
                'message': f'[{i}] {num}: 更新失敗 - {e}'
            }
            stats['failed'] += 1

    return stats
