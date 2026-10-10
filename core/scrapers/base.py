"""BaseScraper 抽象類"""
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional
from .models import Video, ScraperConfig
from core.scrapers.utils import is_lenient_number, normalize_number_impl
from core.proxy_policy import new_session, proxy_kwargs

if TYPE_CHECKING:
    from core.source_probe import ProbePlan


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

    def _new_session(self):
        """依 proxy policy 建 Session（選中時每個 request 帶 proxies=）。"""
        return new_session(self.source_name, settings=self.config.proxy_settings)

    def _proxy_kwargs(self) -> dict:
        """非 Session 通道用：選中 → {'proxies': {...}}；未選中 → {}。"""
        return proxy_kwargs(
            'source_query', source_id=self.source_name,
            settings=self.config.proxy_settings,
        )

    def probe_plan(self, timeout) -> "Optional[ProbePlan]":
        """宣告「測試連線」要探測哪些目標；None ＝不可探測（判讀由 core.source_probe 負責）。"""
        return None

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
        return is_lenient_number(number)

    def normalize_number(self, number: str) -> str:
        """正規化番號（統一大寫、格式）"""
        return normalize_number_impl(number)
