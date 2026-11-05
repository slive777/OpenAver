"""E2E：說明頁三分頁——預設分頁依引導旗標、hash 直達、點分頁不增歷史（TASK-191a-T1）。

只驗結束狀態（settle 後的 computed display／hash）。library／organize 在 T1 是空殼（高度 0），
所以一律用 getComputedStyle(panel).display 判斷，不用 to_be_visible／to_be_hidden（對 0 高元素會假紅／假綠）。
"""
from __future__ import annotations

import json
import urllib.request

import pytest
from playwright.sync_api import Page, expect

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


def test_tutorial_four_steps_link_marks_done_first(page: Page, base_url: str, set_flag) -> None:
    """引導四步；最後一步點「到說明頁看…」→ 落在整理與改名，且旗標已寫（回片庫管理不再被打擾）。"""
    set_flag(False)
    page.set_viewport_size({"width": 1280, "height": 900})
    page.bring_to_front()
    page.goto(f"{base_url}/scanner?r=191", wait_until="domcontentloaded")
    page.wait_for_selector("#tutorialOverlay.active", timeout=10000)
    progress = page.locator("#tutorialProgress")
    for n in (1, 2, 3, 4):
        expect(progress).to_have_text(f"{n} / 4")
        if n < 4:
            page.click("#tutorialNext")
    link = page.locator("#tutorialContent a[data-tutorial-go]")
    assert link.count() == 1
    assert link.get_attribute("href") == "/help#organize"
    link.click()
    page.wait_for_url("**/help#organize")
    page.wait_for_function(_READY)
    _only_active(page, "organize")
    assert _api(base_url, "GET", "/api/tutorial-status")["completed"] is True
    with page.expect_response("**/api/tutorial-status"):
        page.goto(f"{base_url}/scanner?r=192", wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    assert page.locator("#tutorialOverlay").count() == 0


# ───────────────────────── TASK-191a-T5：舞台引擎＋桌機／文字版切換（stub scene）─────────────────────────
# 只驗結束狀態。每個零值斷言（零 DOM 變動、零請求）前都有「舞台真的在跑」的前置斷言，防空轉假綠。
# v 的換算全由 DOM 量（track／pin rect、pin 的 computed top），不寫死像素。

_LIB = """
const root = (n) => document.querySelector('.hs-root[data-hs-stage="' + n + '"]');
const metr = (n) => { const r = root(n), t = r.querySelector('.hs-track'), p = r.querySelector('.hs-pin');
    const tr = t.getBoundingClientRect(), ph = p.getBoundingClientRect().height;
    const gap = parseFloat(getComputedStyle(p).top) || 0;
    return { trackTop: tr.top, h: tr.height, pinH: ph, gap, stepPx: (tr.height - ph) / 4 }; };
const goalV = (n) => { const m = metr(n); return Math.min(4, Math.max(0, (m.gap - m.trackTop) / m.stepPx)); };
const vAttr = (n) => root(n).querySelector('.hs-canvas').style.getPropertyValue('--hs-v');
"""
_ARMED = "(n) => {" + _LIB + " return vAttr(n) !== ''; }"
_SETTLED = "(n) => {" + _LIB + " return vAttr(n) === goalV(n).toFixed(3); }"
_TO_V = """([n, v]) => {""" + _LIB + """
    const m = metr(n), max = document.documentElement.scrollHeight - innerHeight;
    window.scrollTo({ top: Math.max(0, Math.min(max, Math.round(scrollY + m.trackTop - m.gap + v * m.stepPx + 1))), behavior: 'instant' }); }"""
_READ = """(n) => {""" + _LIB + """
    const r = root(n), q = (s) => [...r.querySelectorAll(s)];
    return { count: r.querySelector('.hs-count').textContent,
             dots: q('.hs-dot').flatMap((d, i) => d.hasAttribute('aria-current') ? [i + 1] : []),
             on: q('.hs-step').flatMap((s, i) => s.classList.contains('is-on') ? [i + 1] : []),
             term: (q('.hs-lib-term')[0] || {}).classList?.contains('is-shown') ?? null,
             navShow: (q('.hs-app-navlink')[2] || {}).classList?.contains('is-active') ?? null,
             v: vAttr(n) }; }"""
_OBSERVE_SCROLL = """async (sels) => {
    let n = 0;
    const obs = sels.map(s => { const o = new MutationObserver(m => { n += m.length; });
        o.observe(document.querySelector(s), { subtree: true, attributes: true, childList: true, characterData: true }); return o; });
    let lo = scrollY, hi = scrollY, dir = 1;
    const t0 = performance.now();
    while (performance.now() - t0 < 2200) {
        window.scrollBy({ top: dir * 120, behavior: 'instant' }); dir = -dir;
        lo = Math.min(lo, scrollY); hi = Math.max(hi, scrollY);
        await new Promise(r => setTimeout(r, 40));
        window.scrollBy({ top: dir * 120, behavior: 'instant' });
        lo = Math.min(lo, scrollY); hi = Math.max(hi, scrollY);
        await new Promise(r => requestAnimationFrame(r));
    }
    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
    obs.forEach(o => o.disconnect());
    return { records: n, lo, hi }; }"""


def _stage_open(page: Page, base_url: str, name: str, n: int) -> None:
    page.bring_to_front()  # FE-MOTION-04：背景分頁的鍵盤／真 click 靜默無效
    _open_at(page, base_url, f"#{name}", n)
    _stage_wait_armed(page, name)


def _stage_wait_armed(page: Page, name: str) -> None:
    page.wait_for_function(_ARMED, arg=name)


def _stage_goto_v(page: Page, name: str, v: float) -> dict:
    page.evaluate(_TO_V, [name, v])
    page.wait_for_function(_SETTLED, arg=name)
    return page.evaluate(_READ, name)


def test_stage_progress_is_pure_function_of_scroll_and_pin_releases(page: Page, base_url: str) -> None:
    _stage_open(page, base_url, "library", 200)
    page.evaluate("() => scrollTo({ top: 0, behavior: 'instant' })")
    from_top = _stage_goto_v(page, "library", 2.5)
    page.evaluate(_TO_V, ["library", 4])
    page.wait_for_function(_SETTLED, arg="library")
    bottom = page.evaluate(_READ, "library")
    assert bottom["count"] == "4 / 4" and bottom["dots"] == [4], bottom  # 兩端真的不同，下面的相等才有意義
    # scene 真的有畫：步 4 是瀏覽頁（進度區收起、側欄「瀏覽」亮起），步 3 是進度區展開（讀 scene 自己寫的 DOM，不是引擎探針）
    assert bottom["term"] is False and bottom["navShow"] is True, bottom
    from_bottom = _stage_goto_v(page, "library", 2.5)
    assert from_top == from_bottom, (from_top, from_bottom)
    assert from_top["count"] == "3 / 4" and from_top["dots"] == [3] and from_top["on"] == [3], from_top
    assert from_top["term"] is True and from_top["navShow"] is False, from_top
    assert 2.4 < float(from_top["v"]) < 2.6, from_top
    # I-5b：v=3.5 時 pin 黏著；track 之後有內容（注入 spacer）捲過去 pin 就釋放
    _stage_goto_v(page, "library", 3.5)
    pin_top = page.evaluate("() => document.querySelector('.hs-root[data-hs-stage=\"library\"] .hs-pin').getBoundingClientRect().top")
    gap = page.evaluate("() => parseFloat(getComputedStyle(document.querySelector('.hs-root[data-hs-stage=\"library\"] .hs-pin')).top)")
    assert abs(pin_top - gap) <= 1, (pin_top, gap)
    released = page.evaluate(
        """() => { const r = document.querySelector('.hs-root[data-hs-stage="library"]');
            const sp = document.createElement('div'); sp.style.height = '2000px'; r.after(sp);
            const t = r.querySelector('.hs-track').getBoundingClientRect(), p = r.querySelector('.hs-pin');
            const gap = parseFloat(getComputedStyle(p).top), ph = p.getBoundingClientRect().height;
            window.scrollTo({ top: Math.round(scrollY + t.bottom - gap - ph + 300), behavior: 'instant' });
            return new Promise(res => requestAnimationFrame(() => requestAnimationFrame(() =>
                res(p.getBoundingClientRect().top)))); }"""
    )
    assert released < 0, released


def test_stage_keyboard_walks_four_steps(page: Page, base_url: str) -> None:
    _stage_open(page, base_url, "library", 201)
    count = page.locator('.hs-root[data-hs-stage="library"] .hs-count')
    _stage_goto_v(page, "library", 0.02)
    page.evaluate("() => { window.__kd = []; addEventListener('keydown', e => window.__kd.push({ key: e.key, dp: e.defaultPrevented })); }")
    for _ in range(4):
        page.keyboard.press("PageDown")
    expect(count).to_have_text("4 / 4", timeout=6000)
    page.wait_for_function("(n) => {" + _LIB + " return Math.abs(parseFloat(vAttr(n)) - 3.86) < 0.02; }", arg="library")
    page.keyboard.press("PageUp")
    expect(count).to_have_text("3 / 4", timeout=6000)
    kd = page.evaluate("() => window.__kd")
    assert [k["key"] for k in kd] == ["PageDown"] * 4 + ["PageUp"] and all(k["dp"] for k in kd), kd  # 釘住時全攔截
    # 圓點與上一步箭頭
    page.locator('.hs-root[data-hs-stage="library"] .hs-dot[data-hs-dot="2"]').click()
    expect(count).to_have_text("2 / 4", timeout=6000)
    page.locator('.hs-root[data-hs-stage="library"] [data-hs-prev]').click()
    expect(count).to_have_text("1 / 4", timeout=6000)
    # 未釘住：PageDown 是瀏覽器原生行為（引擎不攔）。先等上一步的 glide 滑完，否則它會把 scrollTo(0) 蓋回去
    page.wait_for_function("(n) => {" + _LIB + " return Math.abs(parseFloat(vAttr(n)) - 0.86) < 0.01; }", arg="library")
    page.evaluate("() => { scrollTo({ top: 0, behavior: 'instant' }); window.__kd = []; }")
    page.wait_for_function("() => scrollY === 0")
    page.keyboard.press("PageDown")
    page.wait_for_function("() => scrollY > 0")
    kd = page.evaluate("() => window.__kd")
    assert kd == [{"key": "PageDown", "dp": False}], kd


@pytest.mark.parametrize("src,dst", [("library", "organize"), ("organize", "library")])
def test_switching_tab_resets_stage_to_first_step(page: Page, base_url: str, src: str, dst: str) -> None:
    _stage_open(page, base_url, src, 202 if src == "library" else 203)
    assert _stage_goto_v(page, src, 2.5)["count"] == "3 / 4"
    tab = {"library": "#helpTabLibrary", "organize": "#helpTabOrganize"}
    for a, b in ((src, dst), (dst, src)):  # 去程：目標第一次啟動；回程：已跑過的舞台重新啟動
        page.locator(tab[b]).click()  # 真滑鼠
        _only_active(page, b)
        _stage_wait_armed(page, b)
        page.wait_for_function(_SETTLED, arg=b)
        res = page.evaluate(
            """([a, b]) => {""" + _LIB + """
            const q = (s) => root(b).querySelector(s), tr = document.querySelector('.help-tabs').getBoundingClientRect();
            const cv = q('.hs-canvas').getBoundingClientRect();
            const anchor = document.querySelector('.help-tabs-panels').getBoundingClientRect().top + scrollY;
            return { count: q('.hs-count').textContent, v: vAttr(b),
                     tabsIn: tr.top >= 0 && tr.bottom <= innerHeight, cw: cv.width, ch: cv.height,
                     vis: getComputedStyle(q('.hs-canvas')).visibility, dy: Math.abs(scrollY - (anchor - tr.height)),
                     srcDisplay: getComputedStyle(document.querySelector('[data-help-panel="' + a + '"]')).display }; }""",
            [a, b],
        )
        assert res["count"] == "1 / 4" and res["v"] == "0.000", res
        assert res["tabsIn"] and res["cw"] > 0 and res["ch"] > 0 and res["vis"] != "hidden", res
        assert res["dy"] <= 2 and res["srcDisplay"] == "none", res
        if a == src:
            assert _stage_goto_v(page, b, 2.5)["count"] == "3 / 4"


def test_hidden_stage_has_no_dom_mutations(page: Page, base_url: str) -> None:
    _stage_open(page, base_url, "library", 204)
    assert _stage_goto_v(page, "library", 1.5)["count"] == "2 / 4"  # 舞台真的在跑，下面的 0 才不是空轉
    page.locator("#helpTabManual").click()
    _only_active(page, "manual")
    page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
    page.wait_for_timeout(300)
    res = page.evaluate(_OBSERVE_SCROLL, ['.hs-root[data-hs-stage="library"]', '.hs-root[data-hs-stage="organize"]'])
    assert res["hi"] > res["lo"], res  # 真的有捲動
    assert res["records"] == 0, res


def test_stage_walk_makes_no_requests_or_page_errors(page: Page, base_url: str) -> None:
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.bring_to_front()
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{base_url}/help?r=205#library", wait_until="networkidle")
    page.wait_for_function(_READY)
    _stage_wait_armed(page, "library")
    seen: list[str] = []
    page.on("request", lambda r: seen.append(r.url.split(base_url, 1)[-1].split("?", 1)[0] if r.url.startswith(base_url) else r.url))
    for name in ("library", "organize"):
        if name == "organize":
            page.locator("#helpTabOrganize").click()
            _only_active(page, "organize")
            _stage_wait_armed(page, "organize")
        for v, want in ((0.02, "1 / 4"), (1.2, "2 / 4"), (2.2, "3 / 4"), (3.2, "4 / 4"), (4, "4 / 4")):
            assert _stage_goto_v(page, name, v)["count"] == want, (name, v)
    polling = [u for u in seen if u == "/api/notifications"]
    others = [u for u in seen if u != "/api/notifications"]
    print(f"excluded notification polls: {len(polling)}")
    assert others == [], others
    assert errors == [], errors
    assert page.evaluate("() => [...document.querySelectorAll('.hs-root')].map(r => [r.querySelectorAll('img').length, r.querySelectorAll('[style*=\"url(\"]').length])") == [[0, 0], [0, 0]]


@pytest.mark.parametrize("width,reduced", [(390, False), (360, False), (1280, True)])
def test_narrow_and_reduced_motion_show_text_steps(page: Page, base_url: str, width: int, reduced: bool) -> None:
    page.bring_to_front()
    if reduced:
        page.emulate_media(reduced_motion="reduce")  # 要在 goto 之前
    for i, name in enumerate(("library", "organize")):
        _open_at(page, base_url, f"#{name}", 210 + i + 2 * [390, 360, 1280].index(width), width)
        _only_active(page, name)
        # 文字版的頁面可能短到不能捲；補一段在 .hs-root 之外的高度，確保「捲動」真的發生
        page.evaluate("(n) => { const s = document.createElement('div'); s.style.height = '2000px'; document.querySelector('.hs-root[data-hs-stage=\"' + n + '\"]').after(s); }", name)
        res = page.evaluate(
            """(name) => { const r = document.querySelector('.hs-root[data-hs-stage="' + name + '"]');
                const steps = [...r.querySelectorAll('.hs-step')], vis = (e) => e.getClientRects().length > 0;
                return { iw: innerWidth, n: steps.length,
                    shown: steps.every(s => { const c = getComputedStyle(s), b = s.getBoundingClientRect();
                        return c.display !== 'none' && c.visibility === 'visible' && b.height > 0; }),
                    text: steps.every(s => s.querySelector('.hs-you').textContent.trim() && s.querySelector('.hs-bg').textContent.trim()),
                    canvasN: r.querySelectorAll('.hs-canvas').length, canvasRects: r.querySelector('.hs-canvas').getClientRects().length,
                    nav: vis(r.querySelector('.hs-nav')), hint: vis(r.querySelector('.hs-hint')) }; }""",
            name,
        )
        assert res["iw"] == width and res["n"] == 4 and res["shown"] and res["text"], res
        assert res["canvasN"] == 1 and res["canvasRects"] == 0 and not res["nav"] and not res["hint"], res
        obs = page.evaluate(_OBSERVE_SCROLL, [f'.hs-root[data-hs-stage="{name}"]'])
        assert obs["hi"] > obs["lo"], obs
        assert obs["records"] == 0, obs
