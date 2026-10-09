"""Scraper 資料模型"""
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

from core.proxy_policy import ProxySettings


class Actress(BaseModel):
    """女優資訊"""
    model_config = ConfigDict(frozen=True)

    name: str = Field(..., min_length=1, description="女優名稱")


class Video(BaseModel):
    """影片資訊"""
    model_config = ConfigDict(frozen=True)

    number: str = Field(..., description="番號（如 SONE-205）")
    title: str = Field(default="", description="影片標題")
    actresses: list[Actress] = Field(default_factory=list, description="女優列表")
    date: str = Field(default="", description="發行日期 (YYYY-MM-DD)")
    maker: str = Field(default="", description="片商名稱")
    cover_url: str = Field(default="", description="封面圖片 URL")
    preview_cover_url: str = Field(default="", description="metatube 預覽用封面 URL（不裁圖，僅顯示用，CD-113c-4）")
    tags: list[str] = Field(default_factory=list, description="標籤/類別")
    source: str = Field(default="", description="資料來源 (javbus/jav321/javdb)")
    detail_url: str = Field(default="", description="詳情頁 URL")
    director: str = Field(default="", description="導演")
    duration: Optional[int] = Field(default=None, description="片長（分鐘）")
    label: str = Field(default="", description="發行商/レーベル")
    series: str = Field(default="", description="系列/シリーズ")
    sample_images: list[str] = Field(default_factory=list, description="樣品圖像 URL")
    preview_sample_images: list[str] = Field(
        default_factory=list,
        description="metatube 預覽用劇照 URL（與 sample_images 等長同序；組不出填 ''；CD-126-2）",
    )

    # 選用欄位（Task 5 會加入）
    rating: Optional[float] = None
    votes: Optional[int] = None

    # 簡介欄（僅供 NFO，排除於 to_legacy_dict，US7 硬契約）
    summary: str = Field(default='', description="簡介（僅供 NFO，排除於 to_legacy_dict）")

    def to_legacy_dict(self) -> dict[str, object]:
        """轉換成舊格式（向後相容）"""
        from core.maker_mapping import normalize_maker_name
        return {
            'number': self.number,
            'title': self.title,
            'actors': [a.name for a in self.actresses],
            'date': self.date,
            'maker': normalize_maker_name(self.maker),
            'cover': self.cover_url,
            'preview_cover_url': self.preview_cover_url,
            'tags': self.tags,
            'source': self.source,
            'url': self.detail_url,
            'director': self.director,
            'duration': self.duration,
            'label': self.label,
            'series': self.series,
            'sample_images': self.sample_images,
            'preview_sample_images': self.preview_sample_images,
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
    proxy_settings: Optional[ProxySettings] = Field(
        default=None, description="代理設定；None = 由 proxy_policy 讀 live config"
    )
