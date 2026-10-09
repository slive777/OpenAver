"""TASK-134a-T2 / TASK-134b-T12 — runtime flatten / cache for _prefix_map."""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import pytest

import core.scrapers.dmm as dmm_module
from core.scrapers.dmm import DMMScraper, _flatten_shipped_table
from core.proxy_policy import ProxySettings
from core.scrapers.models import ScraperConfig

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REAL_TABLE_PATH = PROJECT_ROOT / "dmm_prefix_table.json"


@pytest.fixture(autouse=True)
def _reset_prefix_hint_caches(monkeypatch):
    """BE-TEST-18：重置 module-level 出貨表快取，避免互相污染。"""
    monkeypatch.setattr(dmm_module, "_shipped_table_cache", None)


def _scraper() -> DMMScraper:
    return DMMScraper(ScraperConfig(proxy_settings=ProxySettings(url="")))


# ── DoD 1 碰撞 ───────────────────────────────────────────────────────────────


def test_flatten_duplicate_prefix_raises_with_prefix_and_makers():
    """DoD 1：兩家片商同一前綴 → ValueError，訊息含前綴與兩家片商名。"""
    raw = {
        "makers": {
            "MakerA": {"abc": {"dmm_prefix": "1", "sample": "ABC-001"}},
            "MakerB": {"abc": {"dmm_prefix": "2", "sample": "ABC-002"}},
        }
    }
    with pytest.raises(ValueError) as exc_info:
        _flatten_shipped_table(raw)
    msg = str(exc_info.value)
    assert "abc" in msg
    assert "MakerA" in msg
    assert "MakerB" in msg


# ── DoD 2 正常 ───────────────────────────────────────────────────────────────


def test_real_shipped_table_flattens_to_164():
    """DoD 2：真實出貨表展平不拋例外、長度 164。"""
    raw = json.loads(REAL_TABLE_PATH.read_text(encoding="utf-8"))
    flat = _flatten_shipped_table(raw)
    assert len(flat) == 164


# ── TASK-134b-T12 DoD 2/3 毒檔無作用 + mtime/md5 未變 ───────────────────────


def test_poisoned_local_files_do_not_affect_search(tmp_path, monkeypatch):
    """DoD 2/3：即使兩個本機檔存在且內容有毒，search() 結果不受毒檔影響，
    且跑完一輪後兩個檔案的 mtime／md5 皆未變（BE-TEST-10：baseline 在操作前取）。

    毒檔內容為真實案例：
    - dmm_content_ids.json：{"MCSR-042": "h_1787mcsr04201"}（真實錯誤快取值之一）
    - dmm_prefix_hints.json：{"dvaj": "yrnkmtn"}（真實錯誤本機前綴值之一）
    """
    content_ids_path = tmp_path / "dmm_content_ids.json"
    prefix_hints_path = tmp_path / "dmm_prefix_hints.json"

    content_ids_path.write_text(
        json.dumps({"MCSR-042": "h_1787mcsr04201"}), encoding="utf-8"
    )
    prefix_hints_path.write_text(
        json.dumps({"dvaj": "yrnkmtn"}), encoding="utf-8"
    )

    # BE-TEST-10：baseline 在被測操作（search）之前取
    content_ids_before = (
        content_ids_path.stat().st_mtime,
        hashlib.md5(content_ids_path.read_bytes()).hexdigest(),
    )
    prefix_hints_before = (
        prefix_hints_path.stat().st_mtime,
        hashlib.md5(prefix_hints_path.read_bytes()).hexdigest(),
    )

    monkeypatch.setattr(dmm_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(dmm_module, "SHIPPED_TABLE_FILE", REAL_TABLE_PATH)
    monkeypatch.setattr(dmm_module, "_shipped_table_cache", None)
    monkeypatch.setattr(dmm_module, "rate_limit", lambda *a, **kw: None)

    scraper = _scraper()

    # ⚠️ 這裡必須記下「實際被拿去查的 cid」，不能只用 lambda cid: None。
    # 2026-08-29 主 session 自選 mutation 實測：只回 None 的話，就算有人把
    # 「讀逐番號快取」硬加回步驟 1，本測試照樣綠（毒 cid 被拿去 fetch 了，但
    # fetch 回 None，最終結果一樣是 None，測試分辨不出來）——DoD 2 的「快取那半」
    # 等於沒有鎖。記下 cid 才能斷言「毒值從來沒有被拿去查」。
    fetched: list[str] = []

    def _record(cid):
        fetched.append(cid)
        return None

    monkeypatch.setattr(scraper, "_fetch_by_id", _record)
    monkeypatch.setattr(scraper, "_search_content_id", lambda number: None)

    # 直接斷言：_prefix_map() 不含毒檔鍵（直接命中 mutation M3）
    assert "dvaj" not in scraper._prefix_map()

    # 探針：MCSR-042（毒 CACHE 裡有）、DVAJ-001（毒 PREFIX 的 dvaj 前綴）都查
    result_mcsr = scraper.search("MCSR-042")
    result_dvaj = scraper.search("DVAJ-001")

    assert result_mcsr is None
    assert result_dvaj is None

    # 毒快取的值（h_1787mcsr04201 ＝ MCSR-042-01，別部片）從來沒有被拿去查
    assert "h_1787mcsr04201" not in fetched, (
        f"逐番號快取被讀回來了——毒值進了查詢路徑：{fetched}"
    )
    # 毒前綴的值（dvaj → yrnkmtn）也沒有進到組出來的 cid 裡
    assert not any("yrnkmtn" in cid for cid in fetched), (
        f"本機自學檔被讀回來了——毒前綴進了 cid：{fetched}"
    )
    # 正向：確認這一輪真的有發生查詢（否則上面兩條是空的恆真）
    assert fetched, "沒有任何 cid 被查詢，上面兩條反向斷言會恆真"

    # DoD 3：mtime 與 md5 未變
    content_ids_after = (
        content_ids_path.stat().st_mtime,
        hashlib.md5(content_ids_path.read_bytes()).hexdigest(),
    )
    prefix_hints_after = (
        prefix_hints_path.stat().st_mtime,
        hashlib.md5(prefix_hints_path.read_bytes()).hexdigest(),
    )
    assert content_ids_after == content_ids_before
    assert prefix_hints_after == prefix_hints_before


# ── DoD 5 缺席降級 ───────────────────────────────────────────────────────────


def test_missing_shipped_table_degrades_to_empty(
    tmp_path, monkeypatch, caplog
):
    """DoD 5：出貨表檔案不存在 → 不拋例外、回空表、有 WARNING。"""
    missing = tmp_path / "does_not_exist.json"
    monkeypatch.setattr(dmm_module, "SHIPPED_TABLE_FILE", missing)

    scraper = _scraper()
    with caplog.at_level(logging.WARNING, logger=dmm_module.logger.name):
        merged = scraper._prefix_map()

    assert merged == {}
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_bad_json_shipped_table_degrades(tmp_path, monkeypatch, caplog):
    """DoD 5：出貨表 JSON 壞掉 → 不拋例外、回空表、有 WARNING。"""
    shipped_path = tmp_path / "dmm_prefix_table.json"
    shipped_path.write_text("{not-json", encoding="utf-8")
    monkeypatch.setattr(dmm_module, "SHIPPED_TABLE_FILE", shipped_path)

    scraper = _scraper()
    with caplog.at_level(logging.WARNING, logger=dmm_module.logger.name):
        merged = scraper._prefix_map()

    assert merged == {}
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_missing_makers_key_degrades(tmp_path, monkeypatch, caplog):
    """DoD 5：出貨表缺 makers 鍵 → 不拋例外、回空表、有 WARNING。"""
    shipped_path = tmp_path / "dmm_prefix_table.json"
    shipped_path.write_text(
        json.dumps(
            {"_meta": {"count": 0}, "foo": {"dmm_prefix": "bar"}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(dmm_module, "SHIPPED_TABLE_FILE", shipped_path)

    scraper = _scraper()
    with caplog.at_level(logging.WARNING, logger=dmm_module.logger.name):
        merged = scraper._prefix_map()

    assert merged == {}
    assert any(r.levelno == logging.WARNING for r in caplog.records)


# ── DoD 5 補強：JSON 語法合法但「形狀」壞掉（review P1）─────────────────────


@pytest.mark.parametrize(
    "bad_makers",
    [
        None,                              # {"makers": null}
        ["not", "a", "dict"],              # makers 是 list
        {"X": ["not", "dict"]},            # 片商底下不是 dict
        {"X": {"aaa": "not-a-mapping"}},   # entry 不是 mapping
    ],
    ids=["makers-null", "makers-list", "maker-value-list", "entry-not-mapping"],
)
def test_structurally_broken_shipped_table_degrades(
    tmp_path, monkeypatch, caplog, bad_makers
):
    """DoD 5／review P1：語法合法但形狀壞掉 → 降級成空表，不得穿透例外。"""
    shipped_path = tmp_path / "dmm_prefix_table.json"
    shipped_path.write_text(
        json.dumps({"_meta": {}, "makers": bad_makers}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(dmm_module, "SHIPPED_TABLE_FILE", shipped_path)

    scraper = _scraper()
    with caplog.at_level(logging.WARNING, logger=dmm_module.logger.name):
        merged = scraper._prefix_map()

    assert merged == {}
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_structurally_broken_table_does_not_break_search_step2(
    tmp_path, monkeypatch
):
    """review P1 的 sink：壞掉的出貨表不得讓 search() 步驟 2 噴例外。

    這支才是「使用者會看到什麼」那一層——上面幾支只證明 _prefix_map 不拋，
    這支證明整條搜尋路徑仍然持續是「查不到」。
    """
    shipped_path = tmp_path / "dmm_prefix_table.json"
    shipped_path.write_text(
        json.dumps({"makers": None}, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.setattr(dmm_module, "SHIPPED_TABLE_FILE", shipped_path)
    monkeypatch.setattr(dmm_module, "rate_limit", lambda *a, **kw: None)

    scraper = _scraper()
    monkeypatch.setattr(scraper, "_fetch_by_id", lambda cid: None)
    monkeypatch.setattr(scraper, "_search_content_id", lambda number: None)

    assert scraper.search("SONE-205") is None


# ── 出貨表側非字串值過濾 ───────────────────────────────────────────────────


def test_shipped_entry_with_non_string_prefix_is_dropped(tmp_path, monkeypatch):
    """出貨表若被塞非字串（build script 出錯）→ 該前綴視為不存在，
    退回預設規則，而不是把 "[]" 組進 content_id。"""
    table_path = tmp_path / "dmm_prefix_table.json"
    table_path.write_text(
        json.dumps(
            {
                "_meta": {"count": 2},
                "makers": {
                    "M": {
                        "aaa": {"dmm_prefix": [], "sample": "AAA-001"},
                        "bbb": {"dmm_prefix": "h_1", "sample": "BBB-001"},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(dmm_module, "SHIPPED_TABLE_FILE", table_path)

    scraper = _scraper()
    merged = scraper._prefix_map()

    assert "aaa" not in merged
    assert merged["bbb"] == "h_1"
    assert scraper._convert_with_hints("AAA-001") == "aaa00001"
