# 行為測試（真的執行 import、看 sys.modules），不是源碼字串存在性檢查，故不屬 lint 守衛範疇。
# 必須用 subprocess：pytest 本行程可能已被其他測試 import 過 core.custom_source，
# 在本行程的 sys.modules 上斷言會失真。
"""AC-10：載入 core.scraper（一般搜尋入口）不得連帶載入 core.custom_source。"""
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_CODE = (
    "import sys, core.scraper\n"
    "print('scraper=' + str('core.scraper' in sys.modules))\n"
    "print('custom=' + str(any(m == 'core.custom_source' or m.startswith('core.custom_source.')"
    " for m in sys.modules)))\n"
)


def test_importing_scraper_does_not_load_custom_source():
    proc = subprocess.run(
        [sys.executable, "-c", _CODE],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
    )
    detail = f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert proc.returncode == 0, detail
    assert "scraper=True" in proc.stdout, detail
    assert "custom=False" in proc.stdout, detail
