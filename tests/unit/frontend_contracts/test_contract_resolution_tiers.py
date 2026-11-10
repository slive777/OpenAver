"""198a-T4：前端 resolution-tier.js 的等級表與後端 core.media_probe 逐項相等（R1 跨檔契約）。"""
import re
from pathlib import Path

from core.media_probe import RESOLUTION_TIERS, resolution_tier

TIER_JS = Path(__file__).parent.parent.parent.parent / "web" / "static" / "js" / "shared" / "resolution-tier.js"


def test_resolution_tiers_match_backend():
    m = re.search(r"export const RESOLUTION_TIERS = \[([^\]\n]*)\];", TIER_JS.read_text(encoding="utf-8"))
    assert m, "resolution-tier.js 必須有單行 RESOLUTION_TIERS 陣列字面"
    front = tuple(re.findall(r"'([^']+)'", m.group(1)))
    assert front == tuple(RESOLUTION_TIERS)
    # 寬度判準（前端只信後端給的等級名，這兩例鎖住「寬度優先」的門檻語意）
    assert resolution_tier(3840, 1600) == "4K"
    assert resolution_tier(1920, 1072) == "FHD"
