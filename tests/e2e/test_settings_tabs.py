"""E2E：設定頁分頁切換不丟值、舊書籤／欄位 id 落在對的分頁（TASK-190a-T3）。

只驗結束狀態（settle 後的可見性／值／hash），不寫動畫時序；不按儲存。
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

PANELS = ("sources", "scraping", "gallery", "ai", "system")
_READY = (
    "() => { const r = document.getElementById('settings-components');"
    " return !!(r && window.Alpine && Alpine.$data(r)._configLoading === false); }"
)


def _open(page: Page, base_url: str, hash_: str, n: int) -> None:
    """整頁載入設定頁。每次用不同 ?r=N（只換 hash 是 same-document，不重跑 Alpine）。"""
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{base_url}/settings?r={n}{hash_}", wait_until="domcontentloaded")
    # <form> 載入中 inert：沒等這步，點不到、值也還是預設值
    page.wait_for_function(_READY)


def _only_visible(page: Page, name: str) -> None:
    for p in PANELS:
        card = page.locator(f'[data-settings-panel="{p}"]')
        if p == name:
            expect(card).to_be_visible()
        else:
            expect(card).to_be_hidden()


def _is_dirty(page: Page) -> bool:
    return page.evaluate(
        "() => Alpine.$data(document.getElementById('settings-components')).isDirty"
    )


def test_tab_switch_keeps_unsaved_value_and_remembers_tab(page: Page, base_url: str) -> None:
    config_gets: list[str] = []
    page.on(
        "request",
        lambda r: config_gets.append(r.url)
        if r.method == "GET" and "/api/config" in r.url
        else None,
    )
    _open(page, base_url, "", 1)
    _only_visible(page, "sources")  # 乾淨 context：預設分頁

    page.locator("#settingsTabScraping").click()  # 真滑鼠
    _only_visible(page, "scraping")
    assert page.evaluate("() => location.hash") == "#scraping"
    assert page.evaluate("() => localStorage.getItem('settings_tab')") == "scraping"

    field = page.locator("#maxTitleLength")
    original = field.input_value()
    field.fill(str(int(original) + 1))
    assert _is_dirty(page) is True

    # 切走再切回：未存值還在、仍是 dirty、期間沒重新載入設定
    config_gets.clear()
    page.locator("#settingsTabGallery").click()
    _only_visible(page, "gallery")
    page.locator("#settingsTabScraping").click()
    _only_visible(page, "scraping")
    assert field.input_value() == str(int(original) + 1)
    assert _is_dirty(page) is True
    assert config_gets == [], f"切分頁不該重載設定：{config_gets}"

    # 還原成不 dirty（否則 beforeunload 擋住 reload），再驗重整回到上次分頁
    field.fill(original)
    assert _is_dirty(page) is False
    page.locator("#settingsTabGallery").click()
    _only_visible(page, "gallery")
    _open(page, base_url, "", 2)
    _only_visible(page, "gallery")


@pytest.mark.parametrize(
    ("hash_", "tab"),
    [("#sec-ai", "ai"), ("#filenameFormat", "scraping")],
)
def test_hash_wins_over_stored_tab(page: Page, base_url: str, hash_: str, tab: str) -> None:
    # 先預埋別的分頁，證明 hash 優先於 localStorage
    page.add_init_script("localStorage.setItem('settings_tab', 'gallery')")
    _open(page, base_url, hash_, 3)
    _only_visible(page, tab)
    if hash_ == "#filenameFormat":
        # scroll 排在顯示之後晚一幀：輪詢到元素與視窗相交
        page.wait_for_function(
            "() => { const r = document.getElementById('filenameFormat').getBoundingClientRect();"
            " return r.top < innerHeight && r.bottom > 0; }"
        )


def _stub_put(page: Page) -> list[str]:
    """攔 PUT /api/config：計次並回成功，不寫真設定。"""
    puts: list[str] = []

    def handler(route):
        if route.request.method == "PUT":
            puts.append(route.request.url)
            route.fulfill(json={"success": True})
        else:
            route.continue_()

    page.route("**/api/config", handler)
    return puts


def _active_id(page: Page) -> str:
    return page.evaluate("() => document.activeElement && document.activeElement.id")


def test_save_blocked_by_invalid_field_in_hidden_tab_reveals_it(page: Page, base_url: str) -> None:
    """在別的分頁按儲存被原生驗證擋下 → 切到第一個無效欄位所在分頁並聚焦（不是靜默無反應）。"""
    puts = _stub_put(page)
    _open(page, base_url, "", 5)

    # 兩欄同時無效：scraping 的 maxTitleLength（DOM 序在前）與 gallery 的 avlistMinSize
    page.locator("#settingsTabScraping").click()
    _only_visible(page, "scraping")
    page.locator("#maxTitleLength").fill("10")  # min=20
    page.locator("#settingsTabGallery").click()
    _only_visible(page, "gallery")
    page.locator("#avlistMinSize").fill("-1")  # min=0
    page.locator("#settingsTabSystem").click()
    _only_visible(page, "system")

    # 按儲存：只切一次、落在 DOM 序第一個無效欄位（scraping，不是被第二個 invalid 事件帶去 gallery）
    page.locator("#saveBtn").click()
    _only_visible(page, "scraping")
    page.wait_for_function("() => document.activeElement && document.activeElement.id === 'maxTitleLength'")
    assert page.evaluate("() => location.hash") == "#scraping"
    assert page.evaluate("() => localStorage.getItem('settings_tab')") == "scraping"
    assert puts == []

    # 修好第一欄 → 再按儲存 → 換到第二欄所在分頁
    page.locator("#maxTitleLength").fill("60")
    page.locator("#saveBtn").click()
    _only_visible(page, "gallery")
    page.wait_for_function("() => document.activeElement && document.activeElement.id === 'avlistMinSize'")
    assert puts == []

    # 全部合法 → 真的送出一次 PUT
    page.locator("#avlistMinSize").fill("0")
    with page.expect_response(lambda r: r.request.method == "PUT" and r.url.endswith("/api/config")):
        page.locator("#saveBtn").click()
    assert len(puts) == 1
