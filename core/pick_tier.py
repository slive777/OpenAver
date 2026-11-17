"""精選等級表單一真理來源（feature/201 T1，純函式模組，CD-201-3）。

編碼（CD-201-1）：金 3／銀 2／銅 1／未精選 0；「是否精選」判準仍是 `> 0`。

設計約束：
- 純函式，無 class。
- 不 import web（保持 core 不反向依賴）。
"""

PICK_TIERS = ('bronze', 'silver', 'gold')

_TIER_VALUES = {'bronze': 1, 'silver': 2, 'gold': 3, 'none': 0}


def tier_value(name) -> int | None:
    """等級名轉數值；未知輸入（含非字串）回 None，不拋例外。"""
    if not isinstance(name, str):
        return None
    return _TIER_VALUES.get(name)


def value_tier(v) -> str | None:
    """數值轉等級名；0／負數／None／不可比回 None，>=3 視為金，不拋例外。"""
    if v is None:
        return None
    try:
        if v >= 3:
            return 'gold'
        if v == 2:
            return 'silver'
        if v == 1:
            return 'bronze'
    except TypeError:
        return None
    return None


def best(values) -> int:
    """整數可迭代物件取 max；空回 0。"""
    return max(values, default=0)
