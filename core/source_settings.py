"""來源設定業務層 helper（TASK-61a-1b）。

提供兩個純函數，把「依賴 config」的來源邏輯集中此層：
- `get_enabled_source_ids()` — 回傳 **Runtime Auto Pool**（實際搜尋 fan-out 用）。
- `is_uncensored_mode_effective()` — 無碼模式的單一真理來源。

設計約束（CD-61-2）：
- 本模組是**業務層**，**允許** import `core.config` 與 `core.source_config`。
- **單向依賴**：`source_settings` → `source_config` + `config`。
- **反向禁止**：`source_config.py` / `config.py` **不可** import 本模組
  （否則造成 circular import；靠 PR review + 本 docstring 守護）。
- Logger 一律 `from core.logger import get_logger`（CLAUDE.md Logger 規則）。
"""
from core.config import load_config
from core.logger import get_logger
from core.scrapers.utils import CENSORED_SOURCES

logger = get_logger(__name__)


def get_enabled_source_ids(
    availability_map: dict[str, bool] | None = None,
) -> list[str]:
    """回傳 Runtime Auto Pool 的來源 id 清單（依 order 升冪）。

    Runtime Auto Pool 過濾公式（design §2.2）：
        enabled is True AND manual_only is not True
        AND (type != 'metatube' OR available)

    - builtin（與所有非 metatube type）**bypass** availability gate（永遠視為 available）。
    - `availability_map=None`（B1 default）= 不 gate，等同全 available（含 metatube）。
    - populated map：`type == 'metatube'` 的 source 僅在 `map[id] is True` 時保留；
      id 不在 map 或值為 False → 排除。
    - 斷線的 metatube provider 仍占 cap 槽（cap basis），但**不**出現在本回傳結果。

    空 / 缺失 `sources` 段 → 回 `[]`（graceful）。malformed 條目以 `.get()` 防禦。
    """
    config = load_config()
    sources = config.get('sources', [])
    if not isinstance(sources, list):
        logger.warning("config['sources'] 非 list（got=%r）：視為空", type(sources))
        return []

    included: list[dict] = []
    for s in sources:
        if not isinstance(s, dict):
            continue
        if s.get('enabled') is not True:
            continue
        if s.get('manual_only') is True:
            continue
        # availability gate：非 metatype bypass；metatube 需 map 允許。
        if s.get('type') == 'metatube':
            if availability_map is not None and availability_map.get(s.get('id'), False) is not True:
                continue
        included.append(s)

    included.sort(key=lambda s: s.get('order', 0))
    return [s.get('id') for s in included if s.get('id') is not None]


def get_all_source_ids_ordered() -> list[str]:
    """回傳全部來源 id（含停用），依 order 升冪。模糊鏈 always-on 用（CD-65-4）。

    與 get_enabled_source_ids() 的差異：
    - 不過濾 enabled / manual_only / type / availability。
    - 純粹「全部來源依拖曳順序」，包含停用、manual_only、metatube 離線等條目。
    - 不接受任何參數（模糊鏈語意是 always-on，不依賴 runtime availability）。

    防禦：缺 sources 段回 []；malformed 非 dict 條目跳過不 crash；
    缺 order key 的條目以 0 計排序。
    """
    config = load_config()
    sources = config.get('sources', [])
    if not isinstance(sources, list):
        logger.warning("config['sources'] 非 list（got=%r）：視為空", type(sources))
        return []

    all_sources: list[dict] = [s for s in sources if isinstance(s, dict)]
    all_sources.sort(key=lambda s: s.get('order', 0))
    return [s.get('id') for s in all_sources if s.get('id') is not None]


def is_uncensored_mode_effective(config: dict) -> bool:
    """無碼模式是否生效（單一真理來源，CD-61-7b）。

    接受 config dict 作參數（**不**自己呼叫 `load_config()`，因 routing 路徑已持有 config）。

    - **Derive 分支**（`config['sources']` 存在且非空）：檢查 4 個有碼 builtin
      （`CENSORED_SOURCES` = dmm/javbus/jav321/javdb）在 sources 段的 enabled 狀態。
      全部 disabled（或缺席）→ True；任一 enabled → False。
    - **Fallback 分支**（`sources` 缺失或為空 `[]`）：讀 legacy
      `config['search']['uncensored_mode_enabled']`（default False）。

    防禦：缺失 key 不 raise。
    """
    sources = config.get('sources')
    # 注意：空 `sources: []` 故意落到 legacy fallback（migration 未跑 → 信 legacy flag），
    # 不要把 `and sources` truthiness guard「簡化」掉 — 兩個 helper 對空 list 處理不對稱是設計。
    if isinstance(sources, list) and sources:
        for s in sources:
            if not isinstance(s, dict):
                continue
            # manual_only=True 的來源（javlibrary 等）不參與無碼模式推導（CD-70b）。
            if s.get('manual_only') is True:
                continue
            if s.get('id') in CENSORED_SOURCES and s.get('enabled') is True:
                return False
        return True

    # fallback：legacy key。
    search = config.get('search', {})
    if not isinstance(search, dict):
        return False
    return bool(search.get('uncensored_mode_enabled', False))
