"""custom_sources fixtures 在乾淨樹裡存在、未被 .gitignore 吞掉、檔名已匿名化。"""
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "custom_sources"

FIXTURE_NAMES = [
    "single-og", "single-og-min", "two-step-search", "two-step-detail-a",
    "two-step-detail-b", "two-step-empty", "fuzzy-search", "fuzzy-detail",
    "text-search", "text-detail", "text-search-empty",
]
ALL_FILES = [f"{n}.html" for n in FIXTURE_NAMES] + ["README.md"]


@pytest.mark.parametrize("name", ALL_FILES)
def test_fixture_exists_nonempty(name):
    p = FIXTURE_DIR / name
    assert p.is_file() and p.stat().st_size > 0


@pytest.mark.parametrize("name", [f"{n}.html" for n in FIXTURE_NAMES])
def test_fixture_not_gitignored(name):
    # 0＝被忽略、128＝非 git repo，都算失敗；只有 1（沒被忽略）才通過
    r = subprocess.run(
        ["git", "check-ignore", "--no-index", "-q", str((FIXTURE_DIR / name).relative_to(REPO_ROOT))],
        cwd=REPO_ROOT,
    )
    assert r.returncode == 1


def test_fixture_names_anonymized():
    bad = [p.name for p in FIXTURE_DIR.iterdir()
           if re.search(r"missav|jable|hayav|avbebe|ppp", p.name, re.I)]
    assert bad == []
