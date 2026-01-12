"""
Search Gallery Service - 將搜尋結果轉換為 Gallery HTML

核心策略：Data Adapter
將女優資料「偽裝」成 VideoInfo 物件，直接複用 Gallery Generator 渲染。
"""

import tempfile
import uuid
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote

from core.gallery_scanner import VideoInfo
from core.gallery_generator import HTMLGenerator
from core.scraper import smart_search
from core.actress_scraper import scrape_actress_profile


class SearchGalleryService:
    """搜尋結果轉換為 Gallery HTML"""

    def __init__(self, output_dir: str = None):
        """
        初始化服務
        
        Args:
            output_dir: HTML 輸出目錄，預設使用系統暫存目錄
        """
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            self.output_dir = Path(tempfile.gettempdir()) / "openaver_gallery"
        
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_search_gallery(self, query: str, 
                                theme: str = "dark",
                                limit: int = 20) -> Optional[str]:
        """
        執行搜尋並生成 Gallery HTML
        
        Args:
            query: 搜尋關鍵字
            theme: 主題 (light/dark)
            limit: 最大結果數
            
        Returns:
            生成的 HTML 檔案路徑，失敗返回 None
        """
        if not query or not query.strip():
            return None

        query = query.strip()

        # 1. 執行智慧搜尋
        results = smart_search(query, limit=limit)
        
        if not results:
            return None

        # 2. 判斷是否為女優搜尋
        is_actress_mode = results[0].get('_mode') == 'actress'

        # 3. 如果是女優搜尋，取得女優資料
        actress_profile = None
        if is_actress_mode:
            actress_profile = scrape_actress_profile(query)

        # 4. 轉換為 VideoInfo 列表
        videos = self._convert_to_videos(results, actress_profile)

        if not videos:
            return None

        # 5. 生成 HTML
        output_path = self.output_dir / f"gallery_{uuid.uuid4().hex[:8]}.html"
        
        generator = HTMLGenerator()
        generator.generate(
            videos=videos,
            output_path=str(output_path),
            title=f"搜尋：{query}",
            mode="image",
            theme=theme,
            click_action="postMessage"
        )

        return str(output_path)

    def _convert_to_videos(self, results: List[Dict], 
                           actress_profile: Optional[Dict] = None) -> List[VideoInfo]:
        """
        將搜尋結果和女優資料轉換為 VideoInfo 列表
        
        Args:
            results: smart_search 的搜尋結果
            actress_profile: 女優個人資料（可選）
            
        Returns:
            VideoInfo 列表
        """
        videos = []

        # 如果有女優資料，插入到第一位（Hero Card）
        if actress_profile:
            hero_card = self._convert_actress_to_video(actress_profile)
            videos.append(hero_card)

        # 轉換搜尋結果
        for r in results:
            video = self._convert_result_to_video(r)
            videos.append(video)

        return videos

    def _convert_actress_to_video(self, profile: Dict) -> VideoInfo:
        """
        將女優資料轉換為 VideoInfo（偽裝）
        
        映射邏輯：
        - name → title (片名位置顯示姓名)
        - cup → num (紅色番號位顯示罩杯)
        - birth → date (日期位置)
        - age → actor (演員位置顯示年齡)
        - height, BWH, hobby → genre (Tags 區)
        - img → img (透過代理)
        """
        # 組合三圍資料
        bwh_parts = []
        if profile.get('bust'):
            bwh_parts.append(f"B{profile['bust']}")
        if profile.get('waist'):
            bwh_parts.append(f"W{profile['waist']}")
        if profile.get('hip'):
            bwh_parts.append(f"H{profile['hip']}")
        bwh = "/".join(bwh_parts) if bwh_parts else ""

        # 組合 Tags
        tags = []
        if profile.get('height'):
            tags.append(profile['height'])
        if bwh:
            tags.append(bwh)
        if profile.get('hobby'):
            tags.append(profile['hobby'])
        if profile.get('hometown'):
            tags.append(profile['hometown'])

        # 圖片 URL（透過代理）
        img_url = ""
        if profile.get('img'):
            img_url = f"/api/proxy-image?url={quote(profile['img'])}"

        return VideoInfo(
            path=f"actress:{profile.get('name', '')}",  # 特殊標記
            title=profile.get('name', ''),
            originaltitle="",
            num=f"{profile.get('cup', '')}-Cup" if profile.get('cup') else "",
            actor=f"{profile.get('age')}歲" if profile.get('age') else "",
            maker="",
            # 使用未來日期確保在按日期降序排列時永遠排第一
            # Y2K38 彩蛋：Unix 32-bit 時間戳溢出日期
            date="2038-01-19",
            genre=", ".join(tags),
            size=0,
            mtime=0,
            img=img_url
        )

    def _convert_result_to_video(self, result: Dict) -> VideoInfo:
        """
        將搜尋結果轉換為 VideoInfo
        """
        # 處理演員列表
        actors = result.get('actors', [])
        if isinstance(actors, list):
            actor_names = [a if isinstance(a, str) else a.get('name', '') for a in actors]
            actor_str = ", ".join(filter(None, actor_names))
        else:
            actor_str = str(actors) if actors else ""

        # 處理標籤
        tags = result.get('tags', [])
        if isinstance(tags, list):
            genre_str = ", ".join(filter(None, tags))
        else:
            genre_str = str(tags) if tags else ""

        # 圖片 URL（透過代理）
        cover = result.get('cover', '')
        img_url = ""
        if cover:
            img_url = f"/api/proxy-image?url={quote(cover)}"

        return VideoInfo(
            path=result.get('number', ''),  # 番號作為 path
            title=result.get('title', ''),
            originaltitle="",
            num=result.get('number', ''),
            actor=actor_str,
            maker=result.get('maker', ''),
            date=result.get('date', ''),
            genre=genre_str,
            size=0,
            mtime=0,
            img=img_url
        )
