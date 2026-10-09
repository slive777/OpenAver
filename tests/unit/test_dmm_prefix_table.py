"""Offline acceptance for dmm_prefix_table.json (TASK-134a-T1 DoD 1-5)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from core.scrapers.dmm import DMMScraper, _flatten_shipped_table
from core.proxy_policy import ProxySettings
from core.scrapers.models import ScraperConfig

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TABLE_PATH = PROJECT_ROOT / "dmm_prefix_table.json"
FIXTURE_PATH = PROJECT_ROOT / "tests/fixtures/scrapers/dmm_crawl_groups.json"


def _load_table() -> dict:
    return json.loads(TABLE_PATH.read_text(encoding="utf-8"))


def _load_fixture() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


# ── DoD 1 ─────────────────────────────────────────────────────────────────────


class TestDmmPrefixTableTracked:
    def test_dmm_prefix_table_is_git_tracked(self):
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "dmm_prefix_table.json"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr


# ── DoD 2 ─────────────────────────────────────────────────────────────────────


class TestDmmPrefixTableCountAndKeys:
    def test_meta_count_matches_flattened_length(self):
        """Internal consistency: seed lives under feature/ (gitignored) so CI
        cannot re-read nonempty seed keys. Instead assert _meta.count, flattened
        length, and sum of per-maker sizes are all 164 and equal."""
        table = _load_table()
        flat = _flatten_shipped_table(table)
        per_maker = sum(len(v) for v in table["makers"].values())
        assert table["_meta"]["count"] == 164
        assert len(flat) == 164
        assert per_maker == 164
        assert table["_meta"]["count"] == len(flat) == per_maker

    def test_flattened_keys_lowercase_unique(self):
        table = _load_table()
        flat = _flatten_shipped_table(table)
        keys = list(flat.keys())
        assert all(k == k.lower() for k in keys)
        assert len(keys) == len(set(keys))

    def test_flattened_keys_diff_from_crawl_fixture_is_harvested(self):
        """Stand-in for bidirectional seed equality (seed not in CI):
        flattened keys minus fixture pfx (lowered) equals the harvested set exactly.
        Harvested prefixes (stars, ie, sddm, zzza) come from real-machine self-learning,
        not in the frozen 2026-07 crawl fixture (TASK-134b-T11 D7).

        NOT a completeness proof. The three DoD-2 checks (count/lowercase/subset)
        all survive an equal-sized swap — dropping one nonempty seed prefix while
        adding one empty-valued one. That hole is closed by DoD 5
        (``test_hit_rate_is_320_0_15``), which runs the real derivation formula
        instead of repeating a set operation: a dropped prefix flips its group
        from hit to miss and trips ``assert miss == 0``.
        Do not weaken DoD 5 believing DoD 2 already covers completeness.
        """
        table = _load_table()
        flat = _flatten_shipped_table(table)
        fixture = _load_fixture()
        fixture_pfx = {g["pfx"].lower() for g in fixture}
        harvested = {"stars", "ie", "sddm", "zzza"}  # 來自兩台實機的自學值，不在 2026-07 crawl 樣本裡
        assert set(flat.keys()) - fixture_pfx == harvested


# ── DoD 3 ─────────────────────────────────────────────────────────────────────


class TestDmmPrefixCorrections:
    def test_id_dmm_prefix_is_h_113(self):
        """Verified live in feature/dmm/build_prefix_table_verification.log
        at 2026-08-28T16:26:55.560828+00:00 — h_113id00057 → ID-057."""
        table = _load_table()
        flat = _flatten_shipped_table(table)
        assert flat["id"]["dmm_prefix"] == "h_113"

    def test_grmo_dmm_prefix_is_h_1534(self):
        """Verified live in feature/dmm/build_prefix_table_verification.log
        at 2026-08-28T16:26:55.845010+00:00 — h_1534grmo00333 → GRMO-333."""
        table = _load_table()
        flat = _flatten_shipped_table(table)
        assert flat["grmo"]["dmm_prefix"] == "h_1534"

    def test_mcsr_dmm_prefix_is_57(self):
        """Verified live in feature/dmm/build_prefix_table_verification.log
        at 2026-08-28T16:26:56.090410+00:00 — 57mcsr00042 → MCSR-042.
        Seed already held 57; not a correction (承重段 D1)."""
        table = _load_table()
        flat = _flatten_shipped_table(table)
        assert flat["mcsr"]["dmm_prefix"] == "57"

    def test_inferred_57_prefixes_have_live_evidence(self):
        """六條 `57` 的真連線佐證（2026-08-29 pre-merge branch review P2 追認）。

        Reviewer 正確地指出：這六條在 `dmm_crawl_groups.json` 裡**只觀測到**
        `h_1454` / `h_1787`，表值 `57` 是從 `itsr`（crawl 裡同時有 `57itsr00153`
        與 `h_1454itsr15303`）與 `mcsr`（另有 live log）兩個佐證**推論**出來的；
        而且它們所屬的 group 正好就是 `test_hit_rate_is_320_0_15` 那 15 筆
        `unparseable`（番號是 `JKSR-741-01` 這種三段式），**結構上不可能被
        320/0/15 那條算式碰到**。⇒ 不用推理，改用真連線逐條定案。

        實測結果（`feature/dmm/build_prefix_table_verification.log` 有完整留檔）：
        `57bdsr00500` → `BDSR-500`、`57bdst00111` → `BDST-111`、
        `57husr00304` → `HUSR-304`、`57sgsr00401` → `SGSR-401`、
        `57jksr00741` → `JKSR-741`，`hust` 用同前綴的
        `57hust00020/00081/00083` 佐證（`HUST-082` 的整片版 DMM 沒收，
        那是**這一個番號**的事，不是前綴錯）。**6/6 正確。**

        這支測試的作用是**把那次實測釘住**：下次有人看到「crawl 裡沒有 57」
        而想把這六條改掉或刪掉時，會先撞到這裡的理由。
        """
        table = _load_table()
        flat = _flatten_shipped_table(table)
        for pfx in ("jksr", "bdsr", "bdst", "husr", "hust", "sgsr", "itsr", "mcsr"):
            assert flat[pfx]["dmm_prefix"] == "57", (
                f"{pfx} 的 dmm_prefix 被改動了——改之前請先讀本測試的 docstring："
                "這個值是 2026-08-29 真連線逐條驗過的，不是從 crawl 抽出來的"
            )

    def test_harvested_prefixes_have_expected_values(self):
        """TASK-134b-T11 DoD 2: 斷言四個收割前綴的 dmm_prefix 值與所屬 maker key。"""
        table = _load_table()
        flat = _flatten_shipped_table(table)
        assert table["makers"]["SOD"]["stars"]["dmm_prefix"] == "1"
        assert table["makers"]["SOD Create"]["sddm"]["dmm_prefix"] == "1"
        assert table["makers"]["Wanz Factory"]["ie"]["dmm_prefix"] == "3"
        assert table["makers"]["ズボズバ"]["zzza"]["dmm_prefix"] == "h_1510"
        assert flat["stars"]["dmm_prefix"] == "1"
        assert flat["sddm"]["dmm_prefix"] == "1"
        assert flat["ie"]["dmm_prefix"] == "3"
        assert flat["zzza"]["dmm_prefix"] == "h_1510"


# ── DoD 4 ─────────────────────────────────────────────────────────────────────


class TestFlattenCollisionDetection:
    def test_synthetic_duplicate_prefix_raises_value_error(self):
        raw = {
            "makers": {
                "MakerA": {"abc": {"dmm_prefix": "1", "sample": "ABC-001"}},
                "MakerB": {"abc": {"dmm_prefix": "2", "sample": "ABC-002"}},
            }
        }
        with pytest.raises(ValueError) as exc_info:
            _flatten_shipped_table(raw)
        assert "abc" in str(exc_info.value)

    def test_real_table_flattens_to_164_without_error(self):
        table = _load_table()
        flat = _flatten_shipped_table(table)
        assert len(flat) == 164


# ── DoD 5 ─────────────────────────────────────────────────────────────────────


class TestCrawlFixtureHitRate:
    def test_hit_rate_is_320_0_15(self):
        """Offline derivation over the frozen 335-group fixture using production
        ``DMMScraper._parse_number`` + zfill(5) + f-string assembly.
        Literals 320 / 0 / 15 are fixed (BE-TEST-09 / 承重段 D4)."""
        table = _load_table()
        flat = _flatten_shipped_table(table)
        groups = _load_fixture()
        assert len(groups) == 335

        scraper = DMMScraper(ScraperConfig(proxy_settings=ProxySettings(url="")))
        hit = miss = unparseable = 0
        for entry in groups:
            prefix, num = scraper._parse_number(entry["authNum"])
            if not prefix or not num:
                unparseable += 1
                continue
            dmm_prefix = flat.get(prefix, {}).get("dmm_prefix", "")
            cid = f"{dmm_prefix}{prefix}{num.zfill(5)}"
            if cid in entry["ids"]:
                hit += 1
            else:
                miss += 1

        assert hit == 320
        assert miss == 0
        assert unparseable == 15
