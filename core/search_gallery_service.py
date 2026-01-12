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
from collections import Counter

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

    def _analyze_top_actor(self, results: List[Dict],
                           threshold: float = 0.8) -> Optional[str]:
        """
        分析搜尋結果中的主要演員

        Args:
            results: 搜尋結果列表
            threshold: 演員佔比閾值（預設 80%）

        Returns:
            主要演員名稱，如果沒有達到閾值則返回 None
        """
        if not results:
            return None

        # 統計每個演員出現的次數
        actor_counter = Counter()

        for result in results:
            actors = result.get('actors', [])

            # 處理不同的 actors 格式
            if isinstance(actors, list):
                for actor in actors:
                    if isinstance(actor, str):
                        actor_name = actor
                    elif isinstance(actor, dict):
                        actor_name = actor.get('name', '')
                    else:
                        continue

                    if actor_name:
                        actor_counter[actor_name] += 1
            elif isinstance(actors, str):
                # 單一演員字串
                if actors:
                    actor_counter[actors] += 1

        if not actor_counter:
            return None

        # 找出出現次數最多的演員
        top_actor, top_count = actor_counter.most_common(1)[0]

        # 計算佔比
        total_results = len(results)
        ratio = top_count / total_results

        # 記錄分析結果（方便 debug）
        print(f"[Hero Analysis] Top actor: {top_actor} ({top_count}/{total_results} = {ratio:.1%})")

        # 檢查是否達到閾值
        if ratio >= threshold:
            return top_actor
        else:
            print(f"[Hero Analysis] Ratio {ratio:.1%} < threshold {threshold:.0%}, skip Hero Card")
            return None

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

        # 2. 分析是否有主要演員（取代原本的 is_actress_mode 判斷）
        top_actor = self._analyze_top_actor(results, threshold=0.8)

        # 3. 如果有主要演員，取得女優資料
        actress_profile = None
        if top_actor:
            print(f"[Hero] Scraping profile for: {top_actor}")
            actress_profile = scrape_actress_profile(top_actor)

            if not actress_profile:
                print(f"[Hero] Profile not found for: {top_actor}")
        else:
            print(f"[Hero] No dominant actor, skip Hero Card")

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
            # 日期恢復正常（透過 generator 的 JS 邏輯置頂）
            date=profile.get('birth', ''),
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
