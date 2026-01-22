"""BaseScraper 抽象類"""
from abc import ABC, abstractmethod
from typing import Optional
from .models import Video, ScraperConfig


class BaseScraper(ABC):
    """
    爬蟲基礎類

    所有爬蟲必須繼承此類並實作抽象方法
    """

    def __init__(self, config: Optional[ScraperConfig] = None):
        """
        初始化爬蟲

        Args:
            config: 爬蟲配置，None 則使用預設值
        """
        self.config = config or ScraperConfig()
        self.source_name = self._get_source_name()

    @abstractmethod
    def _get_source_name(self) -> str:
        """返回爬蟲來源名稱 (如 'javbus')"""
        pass

    @abstractmethod
    def search(self, number: str) -> Optional[Video]:
        """
        搜尋影片資訊

        Args:
            number: 番號（如 SONE-205）

        Returns:
            Video 物件，找不到返回 None

        Raises:
            ValueError: 番號格式錯誤
            TimeoutError: 請求超時
        """
        pass

    @abstractmethod
    def search_by_keyword(self, keyword: str, limit: int = 20) -> list[Video]:
        """
        關鍵字搜尋（用於女優名、模糊搜尋）

        Args:
            keyword: 搜尋關鍵字
            limit: 最大結果數

        Returns:
            Video 列表，可能為空
        """
        pass

    def validate_number(self, number: str) -> bool:
        """
        驗證番號格式

        Args:
            number: 番號

        Returns:
            True 如果格式正確
        """
        import re
        patterns = [
            r'^[A-Z]+-\d+$',         # ABC-123
            r'^FC2-PPV-\d+$',        # FC2-PPV-1234567
            r'^[A-Z]+\d+-\d+$',      # T28-103
        ]
        return any(re.match(p, number.upper()) for p in patterns)

    def normalize_number(self, number: str) -> str:
        """
        正規化番號（統一大寫、格式）

        Args:
            number: 番號

        Returns:
            正規化後的番號
        """
        import re
        number = number.strip()
        # 清理常見後綴（UC, UNCEN, UNCENSORED, LEAK, LEAKED）
        number = re.sub(
            r'[-_]?(UC|UNCEN|UNCENSORED|LEAK|LEAKED)(?=[-_.\s]|$)',
            '', number, flags=re.IGNORECASE
        )
        number = number.upper()
        # ABC123 → ABC-123
        match = re.match(r'^([A-Z]+)(\d+)$', number)
        if match:
            return f"{match.group(1)}-{match.group(2)}"
        return number
