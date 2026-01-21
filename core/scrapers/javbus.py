"""JavBus 爬蟲（透過 jvav 庫）"""
import logging
from typing import Optional
from .base import BaseScraper

logger = logging.getLogger(__name__)
from .models import Video, Actress
from .utils import rate_limit

# 嘗試載入 jvav
try:
    from jvav import JavBusUtil
    JVAV_AVAILABLE = True
except ImportError:
    JVAV_AVAILABLE = False


class JavBusScraper(BaseScraper):
    """
    JavBus 爬蟲

    優點：
    - 封面無浮水印
    - jvav 套件維護良好

    注意：
    - 需安裝 jvav 套件
    - 封面只有右半邊（裁切版）
    """

    def _get_source_name(self) -> str:
        return "javbus"

    def search(self, number: str) -> Optional[Video]:
        """
        搜尋影片資訊

        Args:
            number: 番號

        Returns:
            Video 物件或 None
        """
        if not JVAV_AVAILABLE:
            return None

        # 正規化番號
        number = self.normalize_number(number)

        # 驗證格式
        if not self.validate_number(number):
            raise ValueError(f"Invalid number format: {number}")

        try:
            jb = JavBusUtil()
            code, data = jb.get_av_by_id(number, False, False)

            if code != 200 or not data:
                return None

            # 轉換成 Video 模型
            actresses = [Actress(name=actor['name']) for actor in data.get('stars', [])]

            video = Video(
                number=number,
                title=data.get('title', ''),
                actresses=actresses,
                date=data.get('date', ''),
                maker=data.get('maker', ''),  # JavBus 沒有 maker，由外部補全
                cover_url=data.get('img', ''),
                tags=data.get('tags', []),
                source=self.source_name,
                detail_url=data.get('url', f'https://www.javbus.com/{number}'),
            )

            # 節流
            rate_limit(self.config.delay)

            return video

        except Exception as e:
            logger.warning(f"JavBus search failed for {number}: {e}")
            return None

    def search_by_keyword(self, keyword: str, limit: int = 20) -> list[Video]:
        """
        關鍵字搜尋（JavBus 不支援女優搜尋）

        Args:
            keyword: 搜尋關鍵字
            limit: 最大結果數

        Returns:
            空列表（JavBus 透過 jvav 不支援關鍵字搜尋）
        """
        # JavBus 的 jvav 套件不支援列表搜尋
        # 返回空列表而非拋例外（優雅降級）
        return []
