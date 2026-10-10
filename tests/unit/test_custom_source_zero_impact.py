# 行為測試（真的執行 import、看 sys.modules），不是源碼字串存在性檢查，故不屬 lint 守衛範疇。
# 必須用 subprocess：pytest 本行程可能已被其他測試 import 過 core.custom_source，
# 在本行程的 sys.modules 上斷言會失真。
"""AC-10：載入 core.scraper（一般搜尋入口）不得連帶載入 core.custom_source。"""
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_CODE = (
    "import sys, core.scraper, core.source_config, core.config\n"
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


_CODE_AFTER_SYNTAX = (
    "import sys, core.scraper, core.source_config\n"
    "from core.source_config import validate_source_id\n"
    "assert validate_source_id('auto') and not validate_source_id('nope')\n"
    "print('custom=' + str(any(m == 'core.custom_source' or m.startswith('core.custom_source.')"
    " for m in sys.modules)))\n"
)


def test_non_custom_ids_do_not_load_custom_source():
    """非 custom: 的 id 驗證不得觸發 custom_source 載入（custom: 分支自己可以載入）。"""
    proc = subprocess.run(
        [sys.executable, "-c", _CODE_AFTER_SYNTAX],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
    )
    detail = f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert proc.returncode == 0, detail
    assert "custom=False" in proc.stdout, detail


_CODE_POLICY = (
    "import sys, core.image_host_policy as p\n"
    "v = p.proxy_verdict('https://pics.dmm.co.jp/a.jpg')\n"
    "assert v.allowed\n"
    "print('custom=' + str(any(m == 'core.custom_source' or m.startswith('core.custom_source.')"
    " for m in sys.modules)))\n"
)
_CODE_IMPORT_ONLY = (
    "import sys, core.image_host_policy\n"
    "print('custom=' + str(any(m == 'core.custom_source' or m.startswith('core.custom_source.')"
    " for m in sys.modules)))\n"
)


def _custom_loaded(code):
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True, text=True, timeout=60,
    )
    detail = f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    assert proc.returncode == 0, detail
    return proc.stdout, detail


def test_importing_image_host_policy_does_not_load_custom_source():
    out, detail = _custom_loaded(_CODE_IMPORT_ONLY)
    assert "custom=False" in out, detail


def test_static_host_verdict_does_not_load_custom_source():
    out, detail = _custom_loaded(_CODE_POLICY)
    assert "custom=False" in out, detail


def test_unknown_host_without_custom_dir_does_not_load_custom_source():
    code = (
        "import os, sys, tempfile\n"
        "os.environ['OPENAVER_DATA_DIR'] = tempfile.mkdtemp()\n"
        "import core.image_host_policy as p\n"
        "assert not p.proxy_verdict('https://nope.example/a.jpg').allowed\n"
        "print('custom=' + str(any(m == 'core.custom_source' or m.startswith('core.custom_source.')"
        " for m in sys.modules)))\n"
    )
    out, detail = _custom_loaded(code)
    assert "custom=False" in out, detail
