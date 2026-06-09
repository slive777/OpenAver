"""來源配置資料模型層（TASK-61a-1）

純資料模型層：定義 SourceConfig Pydantic 模型、render_name helper、
get_builtin_sources 預設清單、validate_source_id 啟動 validator，作為
後續所有 61 task 的共用型別契約。

設計約束：
- **禁止 top-level import core/config.py**（CD-61-2 circular import 緩解）。
- 僅 import core/scrapers/utils.py 的純常數（無 circular import 風險）。
- Logger 一律 from core.logger import get_logger（CLAUDE.md Logger 規則）。
"""
from pydantic import BaseModel, Field, computed_field, model_validator

from core.logger import get_logger
from core.scrapers.utils import (
    CENSORED_SOURCES,
    METATUBE_CENSORED,
    METATUBE_PROVIDER_ORDER,
    METATUBE_UNCENSORED,
    PROXY_SOURCES,
    SOURCE_NAMES,
    SOURCE_ORDER,
    UNCENSORED_SOURCES,
)

logger = get_logger(__name__)

# 單一搜尋同時啟用來源數上限（CD-61-16）
MAX_ENABLED_SOURCES = 10


class SourceConfig(BaseModel):
    """單一來源的配置。

    `is_censored` 為 computed field（非 stored），True 代表「有碼」。
    `available` 為 RUNTIME-ONLY 軸，**不**列入 schema（OQ-8）。
    """

    id: str
    type: str  # 'builtin' / 'metatube' / ...
    display_name_key: str | None = None
    display_name_raw: str = ''
    enabled: bool = True
    order: int = 0
    config: dict = Field(default_factory=dict)
    is_beta: bool = False
    manual_only: bool = False  # B1 day-one schema（預留 B4 javlibrary）；B1 全 False
    requires_proxy: bool = False  # CD-63a-3：DMM=True，metatube 全 False

    @model_validator(mode='after')
    def _derive_requires_proxy(self) -> 'SourceConfig':
        """Builtin sources always derive requires_proxy from PROXY_SOURCES.

        Ensures that even when reconstructed from a stored dict that lacks the
        requires_proxy key (e.g. old config.json entries), DMM and other proxy
        builtins correctly reflect True.  Non-builtin types (metatube, etc.) are
        left unchanged — they keep whatever value was passed (default False).
        """
        if self.type == 'builtin':
            self.requires_proxy = self.id in PROXY_SOURCES
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_censored(self) -> bool:
        """是否為有碼來源（CD-61-3 round-2 雙路徑）。

        - builtin：查 CENSORED_SOURCES / UNCENSORED_SOURCES 常數。
        - 其他 type：讀 config['censored_type']。
        - 未知值（含 key 不存在 / 非法值）：保守當「有碼」回 True + log warning。
        """
        if self.type == 'builtin':
            if self.id in CENSORED_SOURCES:
                return True
            if self.id in UNCENSORED_SOURCES:
                return False
            logger.warning(
                "未知 builtin 來源 id '%s'：無法判定有碼/無碼，保守視為有碼", self.id
            )
            return True

        censored_type = self.config.get('censored_type')
        if censored_type == 'censored':
            return True
        if censored_type == 'uncensored':
            return False
        logger.warning(
            "來源 '%s' (type=%s) 缺少有效 config['censored_type']（got=%r）："
            "保守視為有碼",
            self.id,
            self.type,
            censored_type,
        )
        return True


def render_name(s: SourceConfig) -> str:
    """解析來源顯示名稱。

    - builtin → display_name_key（品牌名本身不走 i18n，CD-61-15）。
    - 其他（metatube 等）→ display_name_raw（外部來源原樣名稱，不翻譯）。

    builtin 的 display_name_key 由 get_builtin_sources() 保證非 None；
    metatube 走 display_name_raw 分支，永不讀到 None（CD-63a-1）。
    """
    if s.type == 'builtin':
        return s.display_name_key or ''
    return s.display_name_raw


def get_builtin_sources() -> list[SourceConfig]:
    """回傳 8 個內建來源，order 對齊 SOURCE_ORDER（dmm 開頭）。

    全部 type='builtin'、enabled=True、manual_only=False、is_beta=False。
    不含 'auto'（auto 是 mode 不是 source，CD-61-5）。
    """
    return [
        SourceConfig(
            id=sid,
            type='builtin',
            display_name_key=SOURCE_NAMES[sid],
            display_name_raw='',
            enabled=True,
            order=index,
            config={},
            is_beta=False,
            manual_only=False,
            requires_proxy=(sid in PROXY_SOURCES),
        )
        for index, sid in enumerate(SOURCE_ORDER)
    ]


def get_manual_only_sources() -> list[SourceConfig]:
    """回傳 manual_only=True 的 builtin 來源（目前只有 javlibrary BETA）。

    不進 SOURCE_ORDER / fan-out，不揭露至 capabilities，僅供：
    - config migration additive step（追加至 sources 段）
    - picker 顯示（T5）
    - source registration（validate_source_id / source_to_scraper）
    """
    return [
        SourceConfig(
            id='javlibrary',
            type='builtin',
            display_name_key='JavLibrary',
            display_name_raw='',
            enabled=False,
            order=99,          # pinned-last（高於 8 個 builtin 的 0-7）
            config={},
            is_beta=True,
            manual_only=True,
            # requires_proxy 由 _derive_requires_proxy model_validator 自動推為 False
            # （javlibrary 不在 PROXY_SOURCES）
        )
    ]


def get_source_enum(include_auto: bool = False) -> list[str]:
    """回傳 source enum 清單（單一真理來源，供 capabilities 等揭露使用）。

    - 順序對齊 SOURCE_ORDER（dmm 開頭，see get_builtin_sources）。
    - include_auto=True 時於最前加上 'auto'（auto 是 mode 不是 builtin source）。
    """
    ids = [s.id for s in get_builtin_sources()]
    return ['auto', *ids] if include_auto else ids


def build_metatube_sources(provider_names: list[str]) -> list['SourceConfig']:
    """從 provider name 清單建立 metatube SourceConfig 列表（CD-63a-5）。

    純函數：不吃 config、不寫檔。
    - id = 'metatube:{name}'
    - type = 'metatube'
    - enabled = False（Parts Bin，不自動 promote，spec US1）
    - censored_type 由 METATUBE_CENSORED / METATUBE_UNCENSORED map 推導；
      不在 map 中的 provider 保守填 'censored' + log warning。
    - order：在 METATUBE_PROVIDER_ORDER 的 index；
      不在 list 的未知 provider 排末尾，彼此按字母序（deterministic）。
    """
    known_count = len(METATUBE_PROVIDER_ORDER)

    # 分出已知 / 未知 provider
    unknown_names = sorted(n for n in provider_names if n not in METATUBE_PROVIDER_ORDER)

    def _order(name: str) -> int:
        if name in METATUBE_PROVIDER_ORDER:
            return METATUBE_PROVIDER_ORDER.index(name)
        return known_count + unknown_names.index(name)

    def _censored_type(name: str) -> str:
        if name in METATUBE_CENSORED:
            return 'censored'
        if name in METATUBE_UNCENSORED:
            return 'uncensored'
        logger.warning(
            "metatube provider '%s' 不在 censored/uncensored map，保守視為有碼",
            name,
        )
        return 'censored'

    return [
        SourceConfig(
            id=f'metatube:{name}',
            type='metatube',
            display_name_key=None,
            display_name_raw=name,
            enabled=False,
            manual_only=False,
            is_beta=False,
            requires_proxy=False,
            config={'censored_type': _censored_type(name)},
            order=_order(name),
        )
        for name in provider_names
    ]


def validate_source_id(sid: str) -> bool:
    """驗證來源 id 是否合法（替代 core/scraper.py 的 VALID_SOURCES set）。

    - 'auto' → True（特判，CD-61-5；但 get_builtin_sources() 不含 auto）。
    - 8 個 builtin id → True。
    - 'metatube:*'（非空後綴）→ True（63c，CD-63c-1）。
    - 其他 → False。
    """
    if sid == 'auto':
        return True
    if sid == 'javlibrary':
        return True
    if sid in SOURCE_ORDER:
        return True
    # 63c：放行 metatube provider id（CD-63a-2 延到此 task）
    if sid.startswith('metatube:') and len(sid) > len('metatube:'):
        return True
    return False
