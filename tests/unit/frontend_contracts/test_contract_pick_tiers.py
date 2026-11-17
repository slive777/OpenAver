# [lint-guard: pytest-justified] 跨 Python／JS 兩檔的等級表契約，lint 不能表達。
"""201-T3：前端 pick-tier.js 的等級表與後端 core.pick_tier 逐項相等。"""
import re
from pathlib import Path

from core.pick_tier import PICK_TIERS

PICK_JS = Path(__file__).parent.parent.parent.parent / "web" / "static" / "js" / "shared" / "pick-tier.js"


# [lint-guard: pytest-justified] 跨檔契約（等級名錯一位＝存錯級），pytest 是唯一可表達處。
def test_pick_tiers_match_backend():
    m = re.search(r"export const PICK_TIERS = \[([^\]\n]*)\];", PICK_JS.read_text(encoding="utf-8"))
    assert m, "pick-tier.js 必須有單行 PICK_TIERS 陣列字面"
    front = tuple(re.findall(r"'([^']+)'", m.group(1)))
    assert front == tuple(PICK_TIERS)
