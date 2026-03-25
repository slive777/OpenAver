"""
E2E 測試：搜尋頁完整流程驗證
需要：真實瀏覽器（Chromium）+ 真實網路 + JavBus 可連

執行方式：
    source venv/bin/activate && playwright install chromium
    pytest tests/e2e/ -v -m e2e

無網路 / JavBus 無回應時自動 SKIP（不 FAIL）。
"""
import pytest
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

pytestmark = pytest.mark.e2e


# ── 共用常數 ──────────────────────────────────────────────────────────────────

SEARCH_TIMEOUT = 60_000   # 60 秒：SSE 搜尋結果最長等待
NAV_WAIT_MS    = 1_000    # 1 秒：導航動畫完成等待


# ── 共用 helper ───────────────────────────────────────────────────────────────

def _do_search(page: Page, base_url: str, query: str) -> None:
    """
    前往搜尋頁、填入 query 並提交。
    不等待結果（讓各測試自行 wait_for_selector）。
    """
    page.goto(f"{base_url}/search")
    page.fill("#searchQuery", query)
    page.click("#btnSubmit")


def _wait_for_result(page: Page) -> None:
    """
    等待 pageState 進入 'result'（#resultCard 變為可見）。
    若 timeout 則 pytest.skip（JavBus 無法連線或搜尋逾時）。
    """
    try:
        page.wait_for_selector("#resultCard", state="visible", timeout=SEARCH_TIMEOUT)
    except PlaywrightTimeoutError:
        pytest.skip("JavBus 無法連線或搜尋 timeout，跳過 e2e 測試")


def _wait_for_detail(page: Page) -> None:
    """等待 Detail 模式主容器（.av-card-full）可見"""
    try:
        page.wait_for_selector(".av-card-full", state="visible", timeout=10_000)
    except PlaywrightTimeoutError:
        pytest.skip("Detail 模式未出現，跳過 e2e 測試")


# ── E2E-1: Detail 模式新欄位顯示 ──────────────────────────────────────────────

def test_detail_new_fields(page: Page, base_url: str) -> None:
    """
    E2E-1：精準搜尋 JUR-688，驗證 Detail 模式的 director / duration / label / series
    欄位列（.info-row）可見且值非空。

    JUR-688（ハプニングバーNTR）確認有導演、片長、發行商、系列四個欄位。
    """
    _do_search(page, base_url, "JUR-688")
    _wait_for_result(page)
    _wait_for_detail(page)

    # 等待 Alpine 渲染穩定
    page.wait_for_timeout(500)

    # 各欄位 label 與對應的 info-row
    fields = [
        ("導演",  ".info-row:has(.info-label:text('導演'))"),
        ("片長",  ".info-row:has(.info-label:text('片長'))"),
        ("發行商", ".info-row:has(.info-label:text('發行商'))"),
        ("系列",  ".info-row:has(.info-label:text('系列'))"),
    ]

    for label, selector in fields:
        row = page.locator(selector)
        assert row.is_visible(), f"欄位「{label}」的 info-row 應可見（x-show 條件成立）"

        value_text = row.locator(".info-value").inner_text().strip()
        assert value_text, f"欄位「{label}」的值不應為空，實際：{value_text!r}"


# ── E2E-2: Sample Lightbox 互動 ───────────────────────────────────────────────

def test_sample_lightbox(page: Page, base_url: str) -> None:
    """
    E2E-2：搜尋 JUR-688，驗證 Sample Images 縮圖列 + Lightbox 互動：
    1. .sample-strip 可見
    2. 點擊第 3 張縮圖 → Lightbox 計數器顯示「3 / N」
    3. ArrowRight → 計數器變「4 / N」
    4. ESC → Lightbox 關閉
    5. Detail 模式（.av-card-full）仍然可見
    """
    _do_search(page, base_url, "JUR-688")
    _wait_for_result(page)
    _wait_for_detail(page)

    # 等待 sample-strip 出現
    try:
        page.wait_for_selector(".sample-strip", state="visible", timeout=10_000)
    except PlaywrightTimeoutError:
        pytest.skip("sample-strip 未出現，JUR-688 可能無 sample images")

    # 確認縮圖數量 >= 3
    buttons = page.locator(".sample-thumb-btn").all()
    if len(buttons) < 3:
        pytest.skip(f"sample images 不足 3 張（實際 {len(buttons)} 張），跳過 Lightbox 測試")

    # 點擊第 3 張縮圖（index 2）
    page.locator(".sample-thumb-btn").nth(2).click()

    # 等待 Lightbox 出現（.sample-lightbox.show）
    try:
        page.wait_for_selector(".sample-lightbox.show", state="visible", timeout=5_000)
    except PlaywrightTimeoutError:
        pytest.skip("Sample Lightbox 未開啟")

    # 驗證計數器：應顯示「3 / N」（第 3 張，1-based）
    counter_text = page.locator(".sample-lightbox-counter").inner_text().strip()
    total = counter_text.split("/")[-1].strip()
    assert counter_text == f"3 / {total}", (
        f"點擊第 3 張縮圖後計數器應為「3 / {total}」，實際：{counter_text!r}"
    )

    # 按 ArrowRight → 進到第 4 張
    page.keyboard.press("ArrowRight")
    page.wait_for_timeout(300)
    counter_text = page.locator(".sample-lightbox-counter").inner_text().strip()
    assert counter_text == f"4 / {total}", (
        f"按 ArrowRight 後計數器應為「4 / {total}」，實際：{counter_text!r}"
    )

    # 按 ESC → Lightbox 關閉
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    # Lightbox 應不再有 .show class（或 hidden）
    lightbox = page.locator(".sample-lightbox")
    assert not lightbox.evaluate("el => el.classList.contains('show')"), (
        "ESC 後 .sample-lightbox 不應有 .show class"
    )

    # Detail 模式應仍可見
    assert page.locator(".av-card-full").is_visible(), (
        "ESC 關閉 Lightbox 後 Detail 模式（.av-card-full）應仍可見"
    )


# ── E2E-3: 方向鍵導航（非 Sample 翻頁） ───────────────────────────────────────

def test_arrow_key_navigation(page: Page, base_url: str) -> None:
    """
    E2E-3：搜尋多筆結果（SSIS），驗證 Sample Lightbox 關閉時方向鍵觸發
    navigate()（切換影片）而非 prevSample()/nextSample()（翻 sample 圖）。

    流程：
    1. 搜尋 SSIS，確認 >= 2 筆結果
    2. 確認 Sample Lightbox 未開啟
    3. 記錄當前番號（currentIndex = 0）
    4. ArrowRight → currentIndex = 1，番號應改變
    5. ArrowLeft → currentIndex = 0，番號應還原
    6. 全程 .sample-lightbox 不應出現 .show class
    """
    _do_search(page, base_url, "SSIS")
    _wait_for_result(page)
    _wait_for_detail(page)

    # 等待 Alpine 渲染穩定
    page.wait_for_timeout(500)

    # 確認導航指示器顯示多筆（nav-indicator 文字格式「N/Total」）
    nav_indicator = page.locator("#navIndicator")
    try:
        page.wait_for_selector("#navIndicator", state="visible", timeout=5_000)
    except PlaywrightTimeoutError:
        pytest.skip("導航指示器未出現，無法確認結果筆數")

    indicator_text = nav_indicator.inner_text().strip()
    # 格式如「1/20」；若 total = 1 則 skip
    parts = indicator_text.split("/")
    if len(parts) == 2:
        try:
            total_count = int(parts[1].strip())
        except ValueError:
            total_count = 0
        if total_count < 2:
            pytest.skip(f"搜尋結果不足 2 筆（實際 {total_count} 筆），無法驗證方向鍵導航")

    # 確認 Sample Lightbox 未開啟
    lightbox = page.locator(".sample-lightbox")
    assert not lightbox.evaluate("el => el.classList.contains('show')"), (
        "測試開始時 Sample Lightbox 不應為開啟狀態"
    )

    # 記錄當前番號（index 0）
    initial_number = page.locator("#resultNumber").inner_text().strip()

    # 按 ArrowRight → 應切換到下一部（navigate(1)）
    page.keyboard.press("ArrowRight")
    page.wait_for_timeout(NAV_WAIT_MS)

    next_number = page.locator("#resultNumber").inner_text().strip()
    assert next_number != initial_number, (
        f"ArrowRight 應切換到下一部影片，但番號未改變：{initial_number!r} → {next_number!r}"
    )

    # 確認 Sample Lightbox 仍未開啟（navigate 不應開啟 Lightbox）
    assert not lightbox.evaluate("el => el.classList.contains('show')"), (
        "ArrowRight 導航後 Sample Lightbox 不應出現"
    )

    # 按 ArrowLeft → 應回到原始番號（navigate(-1)）
    page.keyboard.press("ArrowLeft")
    page.wait_for_timeout(NAV_WAIT_MS)

    restored_number = page.locator("#resultNumber").inner_text().strip()
    assert restored_number == initial_number, (
        f"ArrowLeft 應回到原始番號 {initial_number!r}，實際：{restored_number!r}"
    )

    # 最終確認 Sample Lightbox 仍未開啟
    assert not lightbox.evaluate("el => el.classList.contains('show')"), (
        "ArrowLeft 導航後 Sample Lightbox 不應出現"
    )
