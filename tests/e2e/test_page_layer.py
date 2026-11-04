"""
E2E 安全網：plan-146b T1 — 「一頁一個矩形」Layer 幾何與材質驗收（先紅）。

依 TASK-146b-T1.md：以冷讀草稿為起點，套用 CD-146b-14 與本卡技術要點 1–10 修正。
covers:
  - spec §3 可自動化的 10 條（左緣對齊、換邊、側欄互斥、封面對齊、手機頂欄深淺、
    blur 不變式、釘頂 boundingRect、<1024 offset、空狀態拆框、閱讀欄/滿版）
  - CD-146b-2 blur 不變式（強制 data-theme=dim；排除清單反向；.showcase-footer 抽驗）
  - CD-146b-5 斷點對帳（1000 寬側欄/頂欄互斥）
  - CD-146b-8 第 5 點 <1024 釘頂 offset/z-index oracle

執行：
    source venv/bin/activate && pytest tests/e2e/test_page_layer.py -q
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page

pytestmark = pytest.mark.e2e

DESKTOP = 1280
TABLET_STUCK = 1000  # <1024，仍應觸發手機頂欄 + <1024 釘頂 offset
SHOWCASE_800 = 800
MOBILE = 390

PAGES = {
    "search": "/search",
    "showcase": "/showcase",
    "settings": "/settings",
    "scanner": "/scanner",
}

# 每頁「工具列 / 內容」對齊錨點：兩側都是 CD-146b-7 ownership 表上的元素。
# 每個錨點各自的量法寫死不動態判斷（CD-146b-8-OVERRIDE / CD-146b-15 §6）：
#   "content-box"              → 任何寬度都用 rect.left + paddingLeft（透明貼齊區塊）。
#   "border-box-desktop-only"  → ≥1024 用 rect.left（border-box，圓角矩形的邊——浮動元素）；
#                                 <1024 退回 content-box（浮動只在 ≥1024 成立，Rule 13b）。
# settings 內容側 = #settingsForm（#settings-components 的直接子、四張卡外層容器；
# 不是 #settings-components 本身——那是 .page-layer，padding-inline 永遠 0）。
# 190a-T1（路徑 B）：頁首桌機（≥1024）加 margin-inline:--layer-inset 縮到卡片寬，
# 所以頁首量 border-box（盒緣 ＝ #settingsForm content-box ＝ 卡片盒緣）；<1024 仍貼齊、量 content-box。
# scanner 工具列側 = .avlist-header，量法 "border-box"（CD-146b-21；鑑別力邊界見下方）。
ALIGN_ANCHORS = {
    "search": ((".search-bar", "border-box-desktop-only"), (".result-area", "content-box")),
    "showcase": ((".showcase-toolbar", "border-box-desktop-only"), (".showcase-grid", "content-box")),
    "settings": ((".settings-header", "border-box-desktop-only"), ("#settingsForm", "content-box")),
    "scanner": ((".avlist-header", "border-box"), (".avlist-container", "content-box")),
}
# "border-box" → 任何寬度都用 rect.left（無條件 border-box；CD-146b-21）。
# Rule 47 的設計註解自己就寫著「NO margin (C-夾4: column-width alignment for centered
# 900/800px columns)」——頁首從設計上就沒有 margin，這不是巧合，是 77d 當初刻意的
# 「置中欄寬度對齊」決策：頁首與卡片都是 .avlist-container 的直接子層、零自身水平 margin，
# 所以 border-box 左緣天生重合。
# ⚠️ 這條斷言的鑑別力邊界：.avlist-header 是 block 子元素且無 margin，它的 border-box
# 左緣在 block layout 下本來就等於父容器（.avlist-container）的內容邊——所以這條斷言
# 只擋得住「有人給頁首加了水平 margin」，擋不住「Rule 46 的 padding 是不是真的吃
# var(--layer-inset)」（那件事字面值與 token 值恰好都是 24px，e2e 對此無鑑別力，見
# CG-LAYER-03）。掃描頁真正吃 token 的不變式由 test_content_inset_equals_layer_inset_token
# （驗 .avlist-container 吃 --layer-inset）負責，兩條合起來才是完整覆蓋，缺一不可。

# 每頁的 Layer 外框 selector（CD-146b-7）；T3 才掛 .page-layer，T1 預期找不到
LAYER_SELECTORS = {
    "search": ".search-container.page-layer",
    "showcase": ".showcase-container.page-layer",
    "settings": "#settings-components.page-layer",
    "scanner": ".page-layer",
}

STICKY_PAGES = {
    "showcase": ".showcase-toolbar",
    "settings": ".settings-header",
}

PAGE_READY_SELECTORS = {
    "search": ".search-bar",
    "showcase": ".showcase-container",
    "settings": ".settings-header",
    "scanner": ".avlist-container",
}


def _set_theme(page: Page, theme: str) -> None:
    """繞過 Alpine 單向綁定直接寫 attribute（冷讀實測可行）。"""
    page.evaluate(
        "theme => document.documentElement.setAttribute('data-theme', theme)",
        theme,
    )


def _wait_alpine_hydrated(page: Page) -> None:
    page.wait_for_function(
        "window.Alpine && document.querySelector('[x-data]')?._x_dataStack",
        timeout=15_000,
    )


def _goto(
    page: Page,
    base_url: str,
    path: str,
    wait_sel: str,
    *,
    theme: str | None = None,
) -> None:
    page.goto(f"{base_url}{path}")
    _wait_alpine_hydrated(page)
    page.wait_for_selector(wait_sel, state="visible", timeout=15_000)
    if theme is not None:
        _set_theme(page, theme)


def _skip_if_empty_library(page: Page, base_url: str) -> None:
    """showcase 工具列/封面格在空片庫下整段不渲染（CD-146b-14 第 1 點）。"""
    resp = page.request.get(f"{base_url}/api/showcase/videos")
    total = 0
    if resp.ok:
        total = int(resp.json().get("total", 0) or 0)
    if total == 0:
        pytest.skip("片庫為空，showcase 幾何斷言需要至少一部片")


def _left_edge(page: Page, selector: str) -> float:
    box = page.locator(selector).first.bounding_box()
    assert box is not None, f"selector 找不到或不可見: {selector}"
    return box["x"]


def _content_box_left(page: Page, sel: str) -> float:
    """容器 content-box 左緣 = rect.left + paddingLeft。

    C/D（DOM 第一個 / 視覺最左可見子）在三頁各壞一種——showcase 撞到置中的
    `.toolbar-search`（1280 時 x=365）、scanner 撞到 `#dragOverlay`（恆 0）、
    settings@1280 撞到 `dialog.modal`（恆 0）；A（容器邊）在 T3 掛上 `.page-layer`
    之後會恆等於 0 差而變成永遠綠的假斷言。只有 content-box 左緣正好就是
    CD-146b-7 的 inset ownership 決定的那條線（每個元素自己吃一次
    `--layer-inset`），而且四頁十七格全部落在可解釋的範圍內。
    """
    left = page.evaluate(
        """(sel) => {
            const el = document.querySelector(sel);
            if (!el) return null;
            const r = el.getBoundingClientRect();
            const padL = parseFloat(getComputedStyle(el).paddingLeft) || 0;
            return r.left + padL;
        }""",
        sel,
    )
    assert left is not None, f"selector 找不到: {sel}"
    return float(left)


def _anchor_left(page: Page, selector: str, mode: str, width: int) -> float:
    """依 ALIGN_ANCHORS 寫死的 mode 取左緣；width 是已知靜態斷點門檻，不是 DOM introspection。"""
    if mode == "border-box-desktop-only" and width >= 1024:
        return _left_edge(page, selector)
    if mode == "border-box":
        return _left_edge(page, selector)
    return _content_box_left(page, selector)


def _backdrop_filter(page: Page, selector: str) -> str:
    loc = page.locator(selector).first
    assert loc.count() > 0, f"selector 找不到: {selector}"
    return loc.evaluate("el => getComputedStyle(el).backdropFilter")


def _fixed_viewport_size(page: Page) -> dict[str, float]:
    """`position:fixed; inset:0` 實際蓋住的矩形。

    本專案 `scrollbar-gutter: stable`（fluent-materials Rule 48）下，fixed inset:0
    比 `window.innerWidth` 窄一條捲軸溝（實測 ~15px）。蓋滿視窗的 oracle 應對這個
    fixed containing block，而不是 raw innerWidth（否則既有已成立類會假紅）。
    """
    return page.evaluate(
        """() => {
            const p = document.createElement('div');
            p.style.cssText = 'position:fixed;inset:0;visibility:hidden;pointer-events:none;';
            document.body.appendChild(p);
            const r = p.getBoundingClientRect();
            p.remove();
            return {width: r.width, height: r.height};
        }"""
    )


def _scroll_window(page: Page, y: int = 500) -> None:
    """捲動視窗並等到 scrollY 穩定（避免 showcase 非同步載入把捲動重置）。

    內容高度不足時退而求其次捲到文件底，不因 scrollY 達不到目標而假紅。
    """
    page.evaluate(
        f"""() => {{
            window.scrollTo(0, {y});
            if (window.scrollY < {max(y - 100, 1)}) {{
                window.scrollTo(0, document.documentElement.scrollHeight);
            }}
        }}"""
    )
    page.wait_for_timeout(200)
    # 若仍幾乎沒捲（內容極短），至少再試一次強制捲動
    scroll_y = page.evaluate("window.scrollY")
    if scroll_y < 1:
        page.evaluate("window.scrollTo(0, 500)")
        page.wait_for_timeout(100)


# ── spec §3 第 1/2 條：左緣對齊（1280/900/390） ────────────────────────────

@pytest.mark.parametrize("width", [DESKTOP, 900, MOBILE])
@pytest.mark.parametrize("page_name", list(PAGES.keys()))
def test_toolbar_content_left_edge_aligned(
    page: Page, base_url: str, page_name: str, width: int
) -> None:
    if page_name == "showcase":
        _skip_if_empty_library(page, base_url)

    page.set_viewport_size({"width": width, "height": 900})
    assert page.evaluate("window.innerWidth") == width

    (toolbar_sel, toolbar_mode), (content_sel, content_mode) = ALIGN_ANCHORS[page_name]
    _goto(page, base_url, PAGES[page_name], PAGE_READY_SELECTORS[page_name])
    page.wait_for_selector(toolbar_sel, state="visible", timeout=15_000)
    page.wait_for_selector(content_sel, state="visible", timeout=15_000)

    toolbar_left = _anchor_left(page, toolbar_sel, toolbar_mode, width)
    content_left = _anchor_left(page, content_sel, content_mode, width)

    assert abs(toolbar_left - content_left) == pytest.approx(0, abs=1.0), (
        f"{page_name}@{width}: 工具列左緣 {toolbar_left} vs 內容左緣 {content_left}，"
        f"差 {abs(toolbar_left - content_left)}px（spec §3 要求相差 0px）"
    )


# ── spec §3 第 1 條：四頁 Layer 左右緣同一組數字（1280 寬） ────────────────

def test_four_pages_layer_same_edges_desktop(page: Page, base_url: str) -> None:
    page.set_viewport_size({"width": DESKTOP, "height": 900})
    assert page.evaluate("window.innerWidth") == DESKTOP

    edges: dict[str, tuple[float, float]] = {}
    for name, path in PAGES.items():
        _goto(page, base_url, path, PAGE_READY_SELECTORS[name])
        loc = page.locator(LAYER_SELECTORS[name])
        assert loc.count() > 0, (
            f"{name}: 找不到 .page-layer 容器（selector={LAYER_SELECTORS[name]}；"
            f"T3 才會掛 class，T1 預期紅燈原因＝selector 未命中）"
        )
        box = loc.first.bounding_box()
        assert box is not None, (
            f"{name}: .page-layer 存在但不可見（selector={LAYER_SELECTORS[name]}）"
        )
        edges[name] = (round(box["x"], 1), round(box["x"] + box["width"], 1))

    values = set(edges.values())
    assert len(values) == 1, f"四頁 Layer 左右緣不同：{edges}"


# ── spec §3 第 3 條：1000 寬側欄與手機頂欄只出現一個（CD-146b-5） ──────────

def test_sidebar_and_mobile_topbar_mutually_exclusive_at_1000(
    page: Page, base_url: str
) -> None:
    page.set_viewport_size({"width": TABLET_STUCK, "height": 900})
    assert page.evaluate("window.innerWidth") == TABLET_STUCK
    _goto(page, base_url, PAGES["search"], PAGE_READY_SELECTORS["search"])

    sidebar_visible = page.locator(".sidebar").first.is_visible()
    topbar_visible = page.locator(".top-navbar").first.is_visible()
    sidebar_display = page.locator(".sidebar").first.evaluate(
        "el => getComputedStyle(el).display"
    )
    topbar_visibility = page.locator(".top-navbar").first.evaluate(
        "el => getComputedStyle(el).visibility"
    )

    assert sidebar_visible != topbar_visible, (
        f"1000 寬：sidebar visible={sidebar_visible} (display={sidebar_display!r}), "
        f"top-navbar visible={topbar_visible} (visibility={topbar_visibility!r})"
        f"（應該只有一個可見；今天 992-1023 是已知 bug 兩者同時顯示）"
    )


# ── spec §3 第 4 條：瀏覽頁 800 寬封面對齊工具列 ───────────────────────────

def test_showcase_cover_aligned_with_toolbar_at_800(page: Page, base_url: str) -> None:
    _skip_if_empty_library(page, base_url)
    page.set_viewport_size({"width": SHOWCASE_800, "height": 900})
    assert page.evaluate("window.innerWidth") == SHOWCASE_800
    _goto(page, base_url, PAGES["showcase"], ".showcase-toolbar")
    page.wait_for_selector(".showcase-grid", state="visible", timeout=15_000)

    # 與 test_toolbar_content_left_edge_aligned 同一 oracle：content-box 左緣
    toolbar_left = _content_box_left(page, ".showcase-toolbar")
    grid_left = _content_box_left(page, ".showcase-grid")

    assert abs(toolbar_left - grid_left) == pytest.approx(0, abs=1.0), (
        f"瀏覽頁 800 寬：工具列左緣 {toolbar_left} vs 封面格左緣 {grid_left}，"
        f"差 {abs(toolbar_left - grid_left)}px"
    )


# ── spec §3 第 5 條：手機頂欄深淺主題 boundingRect 相同 ────────────────────

def test_mobile_topbar_same_rect_light_vs_dim(page: Page, base_url: str) -> None:
    page.set_viewport_size({"width": MOBILE, "height": 900})
    assert page.evaluate("window.innerWidth") == MOBILE
    _goto(page, base_url, PAGES["search"], PAGE_READY_SELECTORS["search"])

    _set_theme(page, "light")
    page.wait_for_selector(".top-navbar", state="visible", timeout=15_000)
    light_box = page.locator(".top-navbar").first.bounding_box()

    _set_theme(page, "dim")
    page.wait_for_selector(".top-navbar", state="visible", timeout=15_000)
    dim_box = page.locator(".top-navbar").first.bounding_box()

    assert light_box is not None and dim_box is not None
    for key in ("x", "y", "width", "height"):
        assert light_box[key] == pytest.approx(dim_box[key], abs=1.0), (
            f"手機頂欄 {key}: light={light_box[key]} vs dim={dim_box[key]} "
            f"（light={light_box} vs dim={dim_box}；今天 dim 內縮 1rem）"
        )


# ── CD-146b-2：排除清單元素仍保留 blur（既有已成立類，應綠） ───────────────

def test_excluded_surfaces_keep_blur_in_dim_theme(page: Page, base_url: str) -> None:
    """反向斷言：拖放遮罩／手機頂欄／燈箱 computed backdrop-filter 仍非 none。"""
    page.set_viewport_size({"width": DESKTOP, "height": 900})
    _goto(page, base_url, PAGES["search"], PAGE_READY_SELECTORS["search"], theme="dim")

    # 拖放遮罩：啟動後讀 blur（CSS 在 base 規則就有 backdrop-filter，不依賴 .active）
    page.evaluate(
        """() => {
            const root = document.querySelector('.search-container');
            const data = window.Alpine && Alpine.$data(root);
            if (data) { data.dragActive = true; }
        }"""
    )
    page.wait_for_timeout(100)
    drag_bf = _backdrop_filter(page, "#dragOverlay")
    assert drag_bf not in ("none", ""), (
        f"拖放遮罩 #dragOverlay backdrop-filter={drag_bf!r}（排除清單應保留 blur）"
    )

    # 手機頂欄：窄螢幕 + dim
    page.set_viewport_size({"width": MOBILE, "height": 900})
    _goto(page, base_url, PAGES["search"], PAGE_READY_SELECTORS["search"], theme="dim")
    page.wait_for_selector(".top-navbar", state="visible", timeout=15_000)
    topbar_bf = _backdrop_filter(page, ".top-navbar")
    assert topbar_bf not in ("none", ""), (
        f"手機頂欄 .top-navbar backdrop-filter={topbar_bf!r}（排除清單應保留 blur）"
    )

    # 燈箱：開啟後讀 blur
    _skip_if_empty_library(page, base_url)
    page.set_viewport_size({"width": DESKTOP, "height": 900})
    _goto(page, base_url, PAGES["showcase"], ".showcase-container", theme="dim")
    opened = page.evaluate(
        """() => {
            const root = document.querySelector('[x-data="showcase"]');
            const data = window.Alpine && Alpine.$data(root);
            if (data) { data.lightboxOpen = true; return true; }
            return false;
        }"""
    )
    assert opened, "無法透過 Alpine.$data 開啟燈箱"
    page.wait_for_timeout(100)
    lb_bf = _backdrop_filter(page, ".showcase-lightbox")
    assert lb_bf not in ("none", ""), (
        f"燈箱 .showcase-lightbox backdrop-filter={lb_bf!r}（排除清單應保留 blur）"
    )


# ── spec §3 第 7 條：桌機釘頂，捲動 500px 後 boundingRect.top === 0 ────────

@pytest.mark.parametrize("page_name,selector", list(STICKY_PAGES.items()))
def test_sticky_toolbar_top_zero_after_scroll_desktop(
    page: Page, base_url: str, page_name: str, selector: str
) -> None:
    if page_name == "showcase":
        _skip_if_empty_library(page, base_url)

    page.set_viewport_size({"width": DESKTOP, "height": 900})
    assert page.evaluate("window.innerWidth") == DESKTOP
    _goto(page, base_url, PAGES[page_name], selector)
    if page_name == "showcase":
        page.wait_for_selector(".showcase-grid", state="visible", timeout=15_000)

    _scroll_window(page, 500)

    box = page.locator(selector).first.bounding_box()
    assert box is not None, f"{page_name}: 找不到 {selector}"
    assert box["y"] == pytest.approx(0, abs=1.0), (
        f"{page_name} {selector}: top={box['y']}（應為 0；scrollY={page.evaluate('window.scrollY')}）"
    )


# ── spec §3 第 8 條 ＋ CD-146b-8 第 5 點：<1024 釘頂 offset/z-index ────────

@pytest.mark.parametrize("width", [SHOWCASE_800, TABLET_STUCK])
@pytest.mark.parametrize("page_name,selector", list(STICKY_PAGES.items()))
def test_sticky_toolbar_stops_below_mobile_topbar(
    page: Page, base_url: str, page_name: str, selector: str, width: int
) -> None:
    if page_name == "showcase":
        _skip_if_empty_library(page, base_url)

    page.set_viewport_size({"width": width, "height": 900})
    assert page.evaluate("window.innerWidth") == width
    _goto(page, base_url, PAGES[page_name], selector)
    page.wait_for_selector(".top-navbar", state="visible", timeout=15_000)
    if page_name == "showcase":
        page.wait_for_selector(".showcase-grid", state="visible", timeout=15_000)

    _scroll_window(page, 500)

    topbar_box = page.locator(".top-navbar").first.bounding_box()
    toolbar_box = page.locator(selector).first.bounding_box()
    assert topbar_box is not None and toolbar_box is not None

    expected_top = topbar_box["y"] + topbar_box["height"]
    assert toolbar_box["y"] == pytest.approx(expected_top, abs=1.0), (
        f"{page_name}@{width} 捲動後 {selector}.top={toolbar_box['y']} vs "
        f"頂欄 bottom={expected_top}"
    )

    menu_btn = page.locator(".top-navbar .btn-square").first
    btn_box = menu_btn.bounding_box()
    assert btn_box is not None
    cx = btn_box["x"] + btn_box["width"] / 2
    cy = btn_box["y"] + btn_box["height"] / 2
    hit_is_btn = page.evaluate(
        """([x, y]) => {
            const el = document.elementFromPoint(x, y);
            const btn = document.querySelector('.top-navbar .btn-square');
            return el === btn || (btn && btn.contains(el));
        }""",
        [cx, cy],
    )
    assert hit_is_btn, (
        f"{page_name}@{width}: 選單鈕座標被工具列攔截（elementFromPoint 沒命中選單鈕）"
    )


def test_settings_header_scrolls_away_at_390_sticky_at_768(
    page: Page, base_url: str
) -> None:
    """手機（<768）設定頁首 static、不釘頂；≥768 維持釘頂。

    刻意改行為，非回歸：舊 CD-146b-22 的 ≤480 釘頂斷言作廢。
    """
    width = MOBILE
    selector = STICKY_PAGES["settings"]

    page.set_viewport_size({"width": width, "height": 900})
    assert page.evaluate("window.innerWidth") == width
    _goto(page, base_url, PAGES["settings"], selector)
    page.wait_for_selector(".top-navbar", state="visible", timeout=15_000)

    _scroll_window(page, 500)

    topbar_box = page.locator(".top-navbar").first.bounding_box()
    toolbar_box = page.locator(selector).first.bounding_box()
    assert topbar_box is not None and toolbar_box is not None

    position = page.evaluate(
        "getComputedStyle(document.querySelector('.settings-header')).position"
    )
    assert position == "static", (
        f"settings@{width} 捲動後 .settings-header position={position!r}（應為 static）"
    )
    assert toolbar_box["y"] < topbar_box["y"] + topbar_box["height"], (
        f"settings@{width} 捲動後 {selector}.top={toolbar_box['y']} "
        f"（應已跟著捲走、不在頂欄下方，頂欄 bottom="
        f"{topbar_box['y'] + topbar_box['height']}）"
    )

    menu_btn = page.locator(".top-navbar .btn-square").first
    btn_box = menu_btn.bounding_box()
    assert btn_box is not None
    cx = btn_box["x"] + btn_box["width"] / 2
    cy = btn_box["y"] + btn_box["height"] / 2
    hit_is_btn = page.evaluate(
        """([x, y]) => {
            const el = document.elementFromPoint(x, y);
            const btn = document.querySelector('.top-navbar .btn-square');
            return el === btn || (btn && btn.contains(el));
        }""",
        [cx, cy],
    )
    assert hit_is_btn, (
        f"settings@{width}: 選單鈕座標被頁首攔截（elementFromPoint 沒命中選單鈕）"
    )

    page.set_viewport_size({"width": 768, "height": 900})
    assert page.evaluate("window.innerWidth") == 768
    position = page.evaluate(
        "getComputedStyle(document.querySelector('.settings-header')).position"
    )
    assert position == "sticky", (
        f"settings@768 .settings-header position={position!r}（應仍為 sticky）"
    )


# ── spec §3 第 10 條：掃描頁閱讀欄 800px 不變、設定頁滿版 ─────────────────

def test_scanner_reading_column_width_unchanged(page: Page, base_url: str) -> None:
    page.set_viewport_size({"width": DESKTOP, "height": 900})
    assert page.evaluate("window.innerWidth") == DESKTOP
    _goto(page, base_url, PAGES["scanner"], ".avlist-container")

    box = page.locator(".avlist-container").first.bounding_box()
    assert box is not None
    assert box["width"] == pytest.approx(800, abs=2.0), (
        f".avlist-container width={box['width']}（應為 800）"
    )


def test_settings_content_full_width(page: Page, base_url: str) -> None:
    """設定頁內容滿版（既有已成立）。不依賴尚未存在的 .page-layer。"""
    page.set_viewport_size({"width": DESKTOP, "height": 900})
    assert page.evaluate("window.innerWidth") == DESKTOP
    _goto(page, base_url, PAGES["settings"], ".settings-header")

    card = page.locator("#settings-components .card").first
    assert card.count() > 0, "找不到 #settings-components .card"
    card_box = card.bounding_box()
    assert card_box is not None

    # 「滿版」＝遠大於歷史 900px 死碼曾經限制的寬度
    assert card_box["width"] > 900, (
        f"設定頁卡片寬 {card_box['width']}（900px 死碼規則可能仍生效）"
    )
    # 確認讀到的是 settings.css `#settings-components .card` 規則的渲染結果
    # （mutation 把選擇器改成 .card2 後，瀏覽器預設 border 回 0px → 仍會紅；
    #  但不鎖死 1px，避免 T5 Rule 14 tint-only / 平面卡拿掉字面 border 時誤殺）
    border_top = card.evaluate("el => getComputedStyle(el).borderTopWidth")
    assert border_top != "0px", (
        f"設定頁卡片 borderTopWidth={border_top!r}：沒吃到 "
        f"`#settings-components .card` 規則（selector 未命中時預設為 0px）。"
        f"若 T5 之後刻意改成無 border 的平面卡，這條要跟著改，不是滿版壞了。"
    )


# ── CD-146b-2：Layer 本身 backdrop-filter 恆為 none（dim） ─────────────────

@pytest.mark.parametrize("page_name", list(PAGES.keys()))
def test_layer_itself_no_blur(page: Page, base_url: str, page_name: str) -> None:
    page.set_viewport_size({"width": DESKTOP, "height": 900})
    _goto(
        page,
        base_url,
        PAGES[page_name],
        PAGE_READY_SELECTORS[page_name],
        theme="dim",
    )

    layer = page.locator(LAYER_SELECTORS[page_name])
    assert layer.count() > 0, (
        f"{page_name}: 找不到 .page-layer 容器（selector={LAYER_SELECTORS[page_name]}；"
        f"T3 才會掛 class，T1 預期紅燈原因＝selector 未命中）"
    )
    backdrop = layer.first.evaluate("el => getComputedStyle(el).backdropFilter")
    assert backdrop in ("none", ""), (
        f"{page_name} .page-layer: computed backdrop-filter = {backdrop!r}"
    )


# ── CD-146b-2：拖放遮罩開啟時蓋滿視窗（既有已成立） ─────────────────────────

def test_drag_overlay_covers_viewport_when_active(page: Page, base_url: str) -> None:
    page.set_viewport_size({"width": DESKTOP, "height": 900})
    assert page.evaluate("window.innerWidth") == DESKTOP
    _goto(page, base_url, PAGES["search"], PAGE_READY_SELECTORS["search"])

    overlay = page.locator("#dragOverlay").first
    assert overlay.count() > 0, "找不到 #dragOverlay"

    # 開啟前：比 opacity/visibility（不能只比 bounding_box——預設就是 inset:0）
    opacity_before = overlay.evaluate("el => getComputedStyle(el).opacity")
    visibility_before = overlay.evaluate("el => getComputedStyle(el).visibility")
    assert opacity_before == "0", (
        f"拖放遮罩開啟前 opacity={opacity_before!r}（應為 '0'）"
    )
    assert visibility_before == "hidden", (
        f"拖放遮罩開啟前 visibility={visibility_before!r}（應為 'hidden'）"
    )

    page.evaluate(
        """() => {
            const root = document.querySelector('.search-container');
            const data = window.Alpine && Alpine.$data(root);
            if (data) { data.dragActive = true; }
        }"""
    )
    page.wait_for_timeout(150)

    opacity_after = overlay.evaluate("el => getComputedStyle(el).opacity")
    assert opacity_after != "0", (
        f"拖放遮罩開啟後 opacity={opacity_after!r}（應非 '0'）"
    )

    box_after = overlay.bounding_box()
    fixed = _fixed_viewport_size(page)
    assert box_after is not None, "拖放遮罩開啟後 bounding_box 為 None"
    assert box_after["x"] == pytest.approx(0, abs=1.0)
    assert box_after["y"] == pytest.approx(0, abs=1.0)
    assert box_after["width"] == pytest.approx(fixed["width"], abs=1.0), (
        f"拖放遮罩寬 {box_after['width']} vs fixed-viewport {fixed['width']} "
        f"(innerWidth={page.evaluate('window.innerWidth')})"
    )
    assert box_after["height"] == pytest.approx(fixed["height"], abs=1.0), (
        f"拖放遮罩高 {box_after['height']} vs fixed-viewport {fixed['height']}"
    )


# ── CD-146b-2：燈箱開啟時蓋滿視窗（既有已成立） ─────────────────────────────

def test_lightbox_covers_viewport_when_open(page: Page, base_url: str) -> None:
    _skip_if_empty_library(page, base_url)
    page.set_viewport_size({"width": DESKTOP, "height": 900})
    assert page.evaluate("window.innerWidth") == DESKTOP
    _goto(page, base_url, PAGES["showcase"], ".showcase-container")

    opened = page.evaluate(
        """() => {
            const root = document.querySelector('[x-data="showcase"]');
            const data = window.Alpine && Alpine.$data(root);
            if (data) { data.lightboxOpen = true; return true; }
            return false;
        }"""
    )
    assert opened, "無法透過 Alpine.$data 開啟燈箱"
    page.wait_for_timeout(150)

    box = page.locator(".showcase-lightbox").first.bounding_box()
    fixed = _fixed_viewport_size(page)
    assert box is not None, "燈箱開啟後 bounding_box 為 None"
    assert box["x"] == pytest.approx(0, abs=1.0)
    assert box["y"] == pytest.approx(0, abs=1.0)
    assert box["width"] == pytest.approx(fixed["width"], abs=1.0), (
        f"燈箱寬 {box['width']} vs fixed-viewport {fixed['width']} "
        f"(innerWidth={page.evaluate('window.innerWidth')})"
    )
    assert box["height"] == pytest.approx(fixed["height"], abs=1.0), (
        f"燈箱高 {box['height']} vs fixed-viewport {fixed['height']}"
    )


# ── CD-146b-2：瀏覽頁手機滑出工具列蓋滿視窗寬（既有已成立） ────────────────

def test_mobile_toolbar_slideout_covers_viewport_when_open(
    page: Page, base_url: str
) -> None:
    _skip_if_empty_library(page, base_url)
    page.set_viewport_size({"width": MOBILE, "height": 900})
    assert page.evaluate("window.innerWidth") == MOBILE
    _goto(page, base_url, PAGES["showcase"], ".showcase-container")

    opened = page.evaluate(
        """() => {
            try {
                if (window.Alpine && Alpine.store('ui')) {
                    Alpine.store('ui').toolbarOpen = true;
                    return true;
                }
            } catch (e) {}
            return false;
        }"""
    )
    if not opened:
        pytest.skip(
            "無法透過 Alpine.store('ui').toolbarOpen 觸發滑出工具列"
            "（store 名稱或欄位可能與 plan 假設不同）"
        )

    page.wait_for_timeout(200)
    box = page.locator(".showcase-toolbar").first.bounding_box()
    fixed = _fixed_viewport_size(page)
    assert box is not None
    assert box["x"] == pytest.approx(0, abs=1.0)
    assert (box["x"] + box["width"]) == pytest.approx(fixed["width"], abs=1.0), (
        f"滑出工具列 right={box['x'] + box['width']} vs fixed-viewport {fixed['width']} "
        f"(innerWidth={page.evaluate('window.innerWidth')})"
    )

    # 146b-T4 AC-6：≤480 滑出 overlay 的 z-index 必須高於 .mobile-toolbar-backdrop，
    # 否則新 <1024 top/z-index 覆寫若未排除 ≤480，會把 toolbar 壓到 40（低於 backdrop 85），
    # 使用者點開搜尋 icon 後點不到裡面的輸入框。
    page.wait_for_selector(".mobile-toolbar-backdrop", state="visible", timeout=5_000)
    stacking = page.evaluate(
        """() => {
            const tb = document.querySelector('.showcase-toolbar');
            const bd = document.querySelector('.mobile-toolbar-backdrop');
            if (!tb || !bd) return null;
            const zTb = parseInt(getComputedStyle(tb).zIndex, 10);
            const zBd = parseInt(getComputedStyle(bd).zIndex, 10);
            const r = tb.getBoundingClientRect();
            const el = document.elementFromPoint(
                r.left + r.width / 2,
                r.top + Math.min(24, r.height / 2),
            );
            return {
                zToolbar: zTb, zBackdrop: zBd,
                hitToolbar: !!(el && el.closest('.showcase-toolbar')),
                hitBackdrop: !!(el && el.closest('.mobile-toolbar-backdrop')),
            };
        }"""
    )
    assert stacking is not None, "找不到 .showcase-toolbar 或 .mobile-toolbar-backdrop"
    assert stacking["zToolbar"] > stacking["zBackdrop"], (
        f"≤480 滑出疊層：toolbar z-index={stacking['zToolbar']} 應高於 "
        f"backdrop z-index={stacking['zBackdrop']}（新 <1024 覆寫不得波及 ≤480）"
    )
    assert stacking["hitToolbar"] and not stacking["hitBackdrop"]


# ── CD-146b-2 T8 抽驗：.showcase-footer 貼視窗底（既有已成立；不需空庫 skip） ─

def test_showcase_footer_pinned_to_viewport_bottom(
    page: Page, base_url: str
) -> None:
    page.set_viewport_size({"width": DESKTOP, "height": 900})
    assert page.evaluate("window.innerWidth") == DESKTOP
    _goto(page, base_url, PAGES["showcase"], ".showcase-footer")

    _scroll_window(page, 500)

    box = page.locator(".showcase-footer").first.bounding_box()
    assert box is not None, "找不到 .showcase-footer"
    inner_h = page.evaluate("window.innerHeight")
    assert box["y"] + box["height"] == pytest.approx(inner_h, abs=1.0), (
        f".showcase-footer bottom={box['y'] + box['height']} vs innerHeight={inner_h}"
    )


# ── CD-146b-9 斷點收斂協同：992-1023 區間無版位縫隙（T2） ─────────────────

def test_no_layout_gap_in_992_1023_band(page: Page, base_url: str) -> None:
    """CD-146b-9 斷點收斂的協同規則驗證：992-1023 這個側欄剛消失的區間，
    footer / 檔案托盤 / 內容起始點都不該殘留舊斷點（991.98/992）留下的縫隙。"""
    page.set_viewport_size({"width": TABLET_STUCK, "height": 900})
    assert page.evaluate("window.innerWidth") == TABLET_STUCK

    # 1) 瀏覽頁 footer 左緣應為 0（不論 sidebar 展開/收合，showcase.css:2776-2782 兩個 selector 都要覆蓋）
    _skip_if_empty_library(page, base_url)
    _goto(page, base_url, PAGES["showcase"], ".showcase-footer")
    footer_box = page.locator(".showcase-footer").first.bounding_box()
    assert footer_box is not None
    assert footer_box["x"] == pytest.approx(0, abs=1.0), (
        f"992-1023 區間瀏覽頁 footer 左緣={footer_box['x']}（應為 0；"
        f"側欄已在 1024 才可見，992-1023 側欄應已隱藏，footer 不該再留側欄寬度的補償）"
    )

    # 2) 搜尋頁檔案托盤左緣應為 0（強制進入 file mode，不依賴真實拖放流程）
    _goto(page, base_url, PAGES["search"], PAGE_READY_SELECTORS["search"])
    page.evaluate("""
        () => {
            const el = document.querySelector('.search-container');
            const data = Alpine.$data(el);
            data.pageState = 'result';
            data.listMode = 'file';
            data.fileList = [{ path: '/tmp/e2e-fixture.mp4', number: 'E2E-001' }];
        }
    """)
    tray = page.locator(".file-list-section.organize-tray")
    tray.first.wait_for(state="visible", timeout=10_000)
    tray_box = tray.first.bounding_box()
    assert tray_box is not None
    assert tray_box["x"] == pytest.approx(0, abs=1.0), (
        f"992-1023 區間搜尋頁檔案托盤左緣={tray_box['x']}（應為 0；"
        f"92a-T5 補償規則已刪除，側欄隱藏後不該再有殘留偏移）"
    )

    # 3) 內容起始點不應被固定頂欄蓋住（.search-bar 頂緣 >= 頂欄底緣，含 --mobile-topbar-height 修正案）
    topbar_box = page.locator(".top-navbar").first.bounding_box()
    searchbar_box = page.locator(".search-bar").first.bounding_box()
    assert topbar_box is not None and searchbar_box is not None
    assert searchbar_box["y"] >= topbar_box["y"] + topbar_box["height"] - 1.0, (
        f"992-1023 區間搜尋頁內容起始 y={searchbar_box['y']} vs 頂欄底緣="
        f"{topbar_box['y'] + topbar_box['height']}（內容不該被固定頂欄蓋住）"
    )


# ── CD-146b-5 斷點邊界對齊：正好 1024 寬側欄與手機化規則互斥（T2） ─────────

def test_no_overlap_at_1024_boundary(page: Page, base_url: str) -> None:
    """CD-146b-5 斷點收斂的邊界對齊驗證：正好 1024px 寬時，側欄可見（桌機模式）
    就不該讓 .search-container 還留在 search.css:672 的手機化規則群裡
    （決策 B 第 1 步：max-width 1024→1023.98，讓兩個「含 1024」的區間不再互撞）。"""
    page.set_viewport_size({"width": 1024, "height": 900})
    assert page.evaluate("window.innerWidth") == 1024
    _goto(page, base_url, PAGES["search"], PAGE_READY_SELECTORS["search"])

    sidebar_visible = page.locator(".sidebar").first.evaluate(
        "el => getComputedStyle(el).display"
    ) != "none"
    search_container_mobile_mode = page.locator(".search-container").first.evaluate(
        "el => getComputedStyle(el).overflowY"
    ) == "auto"

    assert not (sidebar_visible and search_container_mobile_mode), (
        f"1024 寬邊界：sidebar visible={sidebar_visible}、"
        f".search-container 仍在 search.css:672 手機化規則群（overflow-y=auto）"
        f"={search_container_mobile_mode}——"
        f"兩者不該同時成立，"
        f"否則 iPad 橫向（1024×768）開啟搜尋頁時，手機化的 .file-list-section.organize-tray "
        f"fixed 定位會被同時可見的側欄蓋住左緣"
    )


# ── CD-146b-7 T7 oracle：內容側水平內距必須吃 --layer-inset（T3 先紅）──

def test_content_inset_equals_layer_inset_token(page: Page, base_url: str) -> None:
    """四頁內容側錨點的 padding-inline 必須等於 :root --layer-inset 的像素值。

    相對左緣對齊（test_toolbar_content_left_edge_aligned）在掃描頁已因 Rule 46
    拆解而綠；T7 把 .avlist-container 的 padding: 1rem 改成 padding-inline:
    var(--layer-inset) 會讓兩側同步位移，那條相對斷言抓不到漏做。本斷言量絕對
    內距對 token。只在桌機 1280 量（<1024 滿版內距是 T4-T7 各自的事）。
    """
    page.set_viewport_size({"width": DESKTOP, "height": 900})
    assert page.evaluate("window.innerWidth") == DESKTOP

    _skip_if_empty_library(page, base_url)

    token: dict | None = None
    measured: dict[str, dict] = {}
    mismatches: list[str] = []

    for name, path in PAGES.items():
        _goto(page, base_url, path, PAGE_READY_SELECTORS[name])
        content_sel, _mode = ALIGN_ANCHORS[name][1]
        page.wait_for_selector(content_sel, state="visible", timeout=15_000)

        if token is None:
            token = page.evaluate(
                """() => {
                    const raw = getComputedStyle(document.documentElement)
                        .getPropertyValue('--layer-inset').trim();
                    const probe = document.createElement('div');
                    probe.style.width = raw || '0px';
                    document.documentElement.appendChild(probe);
                    const px = parseFloat(getComputedStyle(probe).width);
                    probe.remove();
                    return { raw, px };
                }"""
            )

        pads = page.evaluate(
            """(sel) => {
                const el = document.querySelector(sel);
                if (!el) return null;
                const cs = getComputedStyle(el);
                return {
                    paddingLeft: parseFloat(cs.paddingLeft) || 0,
                    paddingRight: parseFloat(cs.paddingRight) || 0,
                };
            }""",
            content_sel,
        )
        assert pads is not None, f"{name}: 找不到內容錨點 {content_sel}"
        measured[name] = {"sel": content_sel, **pads}

        expected = float(token["px"])
        for side in ("paddingLeft", "paddingRight"):
            val = float(pads[side])
            if abs(val - expected) > 1.0:
                mismatches.append(
                    f"{name} {content_sel} {side}={val} "
                    f"vs --layer-inset {token['raw']!r}={expected}px"
                )

    # 146b-T9：說明頁不在 PAGES（沒有工具列，ALIGN_ANCHORS 的兩錨點結構不適用）——
    # 併入同一組 mismatches／measured／token，內容錨點是 .help-cards（CD-146b-7
    # ownership 的說明頁等價：.page-layer 直接子區塊，自己吃一次 --layer-inset）。
    _goto(page, base_url, "/help", ".help-container")
    assert page.locator(".help-container.page-layer").count() == 1, (
        "help: 找不到 .help-container.page-layer（CD-146b-12 要求的 class 未掛上）"
    )
    help_pads = page.evaluate(
        """(sel) => {
            const el = document.querySelector(sel);
            if (!el) return null;
            const cs = getComputedStyle(el);
            return {
                paddingLeft: parseFloat(cs.paddingLeft) || 0,
                paddingRight: parseFloat(cs.paddingRight) || 0,
            };
        }""",
        ".help-cards",
    )
    assert help_pads is not None, "help: 找不到 .help-cards"
    measured["help"] = {"sel": ".help-cards", **help_pads}
    for side in ("paddingLeft", "paddingRight"):
        val = float(help_pads[side])
        if abs(val - expected) > 1.0:
            mismatches.append(
                f"help .help-cards {side}={val} "
                f"vs --layer-inset {token['raw']!r}={expected}px"
            )

    assert not mismatches, (
        f"內容側水平內距尚未吃 --layer-inset（T4-T7 才轉綠）：{mismatches}；"
        f"量測={measured}；token={token}"
    )
