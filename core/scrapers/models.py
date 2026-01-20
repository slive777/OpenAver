"""Scraper 資料模型"""
from typing import Optional
from pydantic import BaseModel, Field


class Actress(BaseModel):
    """女優資訊"""
    name: str = Field(..., min_length=1, description="女優名稱")

    class Config:
        frozen = True  # 不可變


class Video(BaseModel):
    """影片資訊"""
    number: str = Field(..., description="番號（如 SONE-205）")
    title: str = Field(default="", description="影片標題")
    actresses: list[Actress] = Field(default_factory=list, description="女優列表")
    date: str = Field(default="", description="發行日期 (YYYY-MM-DD)")
    maker: str = Field(default="", description="片商名稱")
    cover_url: str = Field(default="", description="封面圖片 URL")
    tags: list[str] = Field(default_factory=list, description="標籤/類別")
    source: str = Field(default="", description="資料來源 (javbus/jav321/javdb)")
    detail_url: str = Field(default="", description="詳情頁 URL")

    # 選用欄位（Task 5 會加入）
    rating: Optional[float] = None
    votes: Optional[int] = None

    class Config:
        frozen = True

    def to_legacy_dict(self) -> dict[str, object]:
        """轉換成舊格式（向後相容）"""
        return {
            'number': self.number,
            'title': self.title,
            'actors': [a.name for a in self.actresses],
            'date': self.date,
            'maker': self.maker,
            'cover': self.cover_url,
            'tags': self.tags,
            'source': self.source,
            'url': self.detail_url,
        }


class ScraperConfig(BaseModel):
    """爬蟲配置"""
    timeout: int = Field(default=15, ge=5, le=60, description="請求超時（秒）")
    max_retries: int = Field(default=2, ge=0, le=5, description="最大重試次數")
    delay: float = Field(default=0.3, ge=0, le=5, description="請求間隔（秒）")
    user_agent: str = Field(
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        description="User-Agent"
    )
