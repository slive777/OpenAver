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


# ───────────────────────── TASK-191a-T2：使用手冊分頁（17 列 details）─────────────────────────
# 只驗結束狀態。<details> 收合時 body 不渲染（rect 全 0），所以「展開且可見」用 open ＋ body 高度 > 0。
# 每支測試第一個斷言先 len(rows)==17，防空集合假綠。

FAQ_IDS = ["faq-crash", "faq-display", "faq-dmm", "faq-translate", "faq-report"]
CHAPTER_IDS = [
    "scanner", "showcase", "search", "batch", "actress", "similar",
    "tag-alias", "scraper", "metatube", "format", "shortcuts", "server-mode",
]
ALL_ROW_IDS = FAQ_IDS + CHAPTER_IDS

_ROW_IDS_JS = "() => [...document.querySelectorAll('.help-manual-row')].map(d => d.id)"


def _open_at(page: Page, base_url: str, hash_: str, n: int, width: int = 1280) -> None:
    page.set_viewport_size({"width": width, "height": 900 if width >= 1024 else 844})
    page.goto(f"{base_url}/help?r={n}{hash_}", wait_until="domcontentloaded")
    page.wait_for_function(_READY)


def _assert_17_rows(page: Page) -> None:
    ids = page.evaluate(_ROW_IDS_JS)
    assert len(ids) == 17, ids


def _row_state(page: Page, row_id: str) -> dict:
    return page.evaluate(
        """(id) => { const d = document.getElementById(id); if (!d) return null;
            const b = d.querySelector('.help-manual-body');
            return { open: d.open, bodyH: b ? b.getBoundingClientRect().height : 0 }; }""",
        row_id,
    )


def test_manual_lists_five_faq_then_twelve_chapters_in_order(page: Page, base_url: str) -> None:
    _open_at(page, base_url, "#manual", 100)
    _assert_17_rows(page)
    assert page.evaluate(_ROW_IDS_JS) == ALL_ROW_IDS
    # 任何寬度 summary 高 ≥ 44
    for width in (1280, 390):
        page.set_viewport_size({"width": width, "height": 900})
        heights = page.evaluate(
            "() => [...document.querySelectorAll('.help-manual-row > summary')].map(s => s.getBoundingClientRect().height)"
        )
        assert len(heights) == 17 and min(heights) >= 44, (width, heights)


def test_manual_rows_collapsed_by_default_and_click_toggles(page: Page, base_url: str) -> None:
    _open_at(page, base_url, "#manual", 101)
    _assert_17_rows(page)
    page.wait_for_function("() => getComputedStyle(document.querySelector('[data-help-panel=\"manual\"]')).display !== 'none'")
    opens = page.evaluate("() => [...document.querySelectorAll('.help-manual-row')].map(d => d.open)")
    assert opens == [False] * 17, opens
    assert page.evaluate("() => window.scrollY") == 0
    summary = page.locator("#faq-dmm > summary")
    summary.click()  # 真滑鼠
    page.wait_for_function("() => document.getElementById('faq-dmm').open === true")
    st = _row_state(page, "faq-dmm")
    assert st["open"] is True and st["bodyH"] > 0, st
    others = page.evaluate(
        "() => [...document.querySelectorAll('.help-manual-row')].filter(d => d.id !== 'faq-dmm').map(d => d.open)"
    )
    assert others == [False] * 16, others
    summary.click()
    page.wait_for_function("() => document.getElementById('faq-dmm').open === false")


@pytest.mark.parametrize(
    "case",
    [("#tag-alias", None), ("#faq-dmm", None), ("#library", "#faq-dmm")],
    ids=["load-tag-alias", "load-faq-dmm", "in-page-hash-faq-dmm"],
)
def test_chapter_hash_opens_row(page: Page, base_url: str, case: tuple) -> None:
    load_hash, later_hash = case
    n = {"#tag-alias": 102, "#faq-dmm": 103, "#library": 104}[load_hash]
    _open_at(page, base_url, load_hash, n)
    _assert_17_rows(page)
    if later_hash:
        page.wait_for_function(
            "() => getComputedStyle(document.querySelector('[data-help-panel=\"library\"]')).display !== 'none'"
        )
        page.evaluate("(h) => { location.hash = h; }", later_hash)
    target = (later_hash or load_hash).lstrip("#")
    page.wait_for_function(
        "(id) => getComputedStyle(document.querySelector('[data-help-panel=\"manual\"]')).display !== 'none'"
        " && document.getElementById(id).open === true",
        arg=target,
    )
    st = _row_state(page, target)
    assert st["open"] is True and st["bodyH"] > 0, st
    opened = page.evaluate("() => [...document.querySelectorAll('.help-manual-row')].filter(d => d.open).map(d => d.id)")
    assert opened == [target], opened


_COVER_JS = """([id, barSel]) => {
    const d = document.getElementById(id), bar = document.querySelector(barSel);
    if (!d || !bar) return false;
    const r = d.getBoundingClientRect(), b = bar.getBoundingClientRect();
    return r.height > 0 && r.top < innerHeight && r.bottom > 0 && r.top >= b.bottom - 1;
}"""


@pytest.mark.parametrize("route", ["load", "in-page"])
@pytest.mark.parametrize("width,bar", [(1280, ".help-tabs"), (390, ".top-navbar")], ids=["w1280", "w390"])
def test_chapter_hash_scrolls_row_into_view(page: Page, base_url: str, width: int, bar: str, route: str) -> None:
    # 目標用最後一列 server-mode：自然位置在首屏之外，沒捲過去就看不到
    # load：帶 hash 載入（瀏覽器可能自己做一次 fragment 捲動）；in-page：先落在 library 再頁內改 hash
    # （此時目標在 display:none 的 manual 內，原生 fragment 不會捲——只有我們的 scrollIntoView 能把它帶到眼前）
    n = 105 + 4 * (route == "in-page") + (width == 390)
    _open_at(page, base_url, "#server-mode" if route == "load" else "#library", n, width)
    _assert_17_rows(page)
    if route == "in-page":
        page.wait_for_function(
            "() => getComputedStyle(document.querySelector('[data-help-panel=\"library\"]')).display !== 'none'"
        )
        page.evaluate("() => { location.hash = '#server-mode'; }")
    # 等到「那一列在眼前且沒被固定頂欄蓋住」；從沒捲過去就會逾時紅
    page.wait_for_function(_COVER_JS, arg=["server-mode", bar], timeout=5000)
    # 再等位置連續多幀不變（排除還在捲動途中碰巧通過），之後仍成立
    page.wait_for_function(
        """() => new Promise(res => { const d = document.getElementById('server-mode'); let last = null, same = 0;
            const tick = () => { const t = d.getBoundingClientRect().top;
                same = (t === last) ? same + 1 : 0; last = t; same >= 8 ? res(true) : requestAnimationFrame(tick); };
            tick(); })""",
        timeout=5000,
    )
    assert page.evaluate(_COVER_JS, ["server-mode", bar]) is True


_OVERFLOW_JS = """() => {
    const root = document.querySelector('.help-cards'), W = innerWidth, bad = [];
    for (const el of root.querySelectorAll('*')) {
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) continue;                   // display:none／收合內容
        let scroller = false;
        for (let p = el; p && p !== root; p = p.parentElement) {          // 走到 .help-cards 為止（不含）
            const ox = getComputedStyle(p).overflowX;
            if (ox === 'auto' || ox === 'scroll') { scroller = true; break; }
        }
        if (!scroller && r.right > W + 1) bad.push(el.tagName + '.' + el.className + ':' + Math.round(r.right));
    }
    return { sw: document.documentElement.scrollWidth, W, bad: bad.slice(0, 10), n: bad.length };
}"""


@pytest.mark.parametrize("width", [390, 360])
def test_mobile_no_horizontal_overflow(page: Page, base_url: str, width: int) -> None:
    _open_at(page, base_url, "#manual", 107 if width == 390 else 108, width)
    page.wait_for_function("() => getComputedStyle(document.querySelector('[data-help-panel=\"manual\"]')).display !== 'none'")
    _assert_17_rows(page)
    # 先把 17 列全展開再量（oracle 的 RED 見 card：舊模板 390 寬必須量得到 518px 的 <code>）
    page.evaluate("() => document.querySelectorAll('.help-manual-row').forEach(d => d.open = true)")
    page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
    res = page.evaluate(_OVERFLOW_JS)
    assert res["sw"] <= res["W"], res
    assert res["n"] == 0, res
    bell = page.evaluate(
        """() => { const b = document.querySelector('[x-ref="mobileBellBtn"]'); const r = b.getBoundingClientRect();
            return { l: r.left, r: r.right, w: r.width, W: innerWidth }; }"""
    )
    assert bell["w"] > 0 and bell["l"] >= 0 and bell["r"] <= bell["W"], bell
