"""E2E：說明頁三分頁——預設分頁依引導旗標、hash 直達、點分頁不增歷史（TASK-191a-T1）。

只驗結束狀態（settle 後的 computed display／hash）。library／organize 在 T1 是空殼（高度 0），
所以一律用 getComputedStyle(panel).display 判斷，不用 to_be_visible／to_be_hidden（對 0 高元素會假紅／假綠）。
"""
from __future__ import annotations

import json
import urllib.request

import pytest
from playwright.sync_api import Page

pytestmark = pytest.mark.e2e

PANELS = ("library", "organize", "manual")
_READY = "() => { const w = document.querySelector('.help-tabs-wrap'); return !!(w && w._x_dataStack); }"


def _api(base_url: str, method: str, path: str) -> dict:
    req = urllib.request.Request(f"{base_url}{path}", method=method, data=b"" if method == "POST" else None)
    with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310 - 本機 e2e server
        return json.loads(r.read().decode("utf-8"))


@pytest.fixture
def set_flag(base_url: str):
    """切換 tutorial_completed（會寫 server 真設定，BE-TEST-04）；測試結束一定還原成測試前的值。"""
    original = bool(_api(base_url, "GET", "/api/tutorial-status")["completed"])

    def _set(value: bool) -> None:
        _api(base_url, "POST", "/api/tutorial-completed" if value else "/api/tutorial-reset")

    yield _set
    _set(original)


def _open(page: Page, base_url: str, hash_: str, n: int) -> None:
    """整頁載入說明頁。每次用不同 ?r=N（只換 hash 是 same-document，不重跑 Alpine）。"""
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{base_url}/help?r={n}{hash_}", wait_until="domcontentloaded")
    page.wait_for_function(_READY)


def _displays(page: Page) -> dict[str, str]:
    return page.evaluate(
        """() => Object.fromEntries(['library', 'organize', 'manual'].map(p => [p,
            getComputedStyle(document.querySelector('[data-help-panel="' + p + '"]')).display]))"""
    )


def _only_active(page: Page, name: str) -> None:
    # x-show 晚一幀（FE-ALPINE-17）：等 settle
    page.wait_for_function(
        """(name) => ['library', 'organize', 'manual'].every(p =>
            (getComputedStyle(document.querySelector('[data-help-panel="' + p + '"]')).display === 'none') === (p !== name))""",
        arg=name,
    )
    d = _displays(page)
    for p in PANELS:
        assert (d[p] != "none") == (p == name), d


def test_default_tab_follows_tutorial_flag(page: Page, base_url: str, set_flag) -> None:
    set_flag(False)
    _open(page, base_url, "", 1)
    _only_active(page, "library")
    set_flag(True)
    _open(page, base_url, "", 2)
    _only_active(page, "manual")


@pytest.mark.parametrize("flag", [False, True])
def test_tab_id_hash_wins_over_flag(page: Page, base_url: str, set_flag, flag: bool) -> None:
    set_flag(flag)
    _open(page, base_url, "#organize", 3 if flag else 4)
    _only_active(page, "organize")


def test_chapter_id_hash_lands_on_manual(page: Page, base_url: str, set_flag) -> None:
    set_flag(False)
    _open(page, base_url, "#tag-alias", 5)
    _only_active(page, "manual")


def test_click_switches_without_history_or_storage_change(page: Page, base_url: str, set_flag) -> None:
    set_flag(False)
    _open(page, base_url, "", 6)
    _only_active(page, "library")
    before = page.evaluate("() => [history.length, Object.keys(localStorage).sort()]")
    page.locator("#helpTabOrganize").click()  # 真滑鼠
    _only_active(page, "organize")
    page.locator("#helpTabManual").click()
    _only_active(page, "manual")
    after = page.evaluate("() => [history.length, Object.keys(localStorage).sort()]")
    assert after == before
    assert page.evaluate("() => location.hash") == "#manual"
    assert page.locator("#helpTabManual").get_attribute("aria-selected") == "true"
