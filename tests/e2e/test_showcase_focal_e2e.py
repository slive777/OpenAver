"""
E2E 測試：焦點手動編輯（99a-T6）— 4 條精簡回歸網
需要：真實瀏覽器（Chromium）+ 真實 e2e server（tests/e2e/conftest.py::ensure_e2e_server）
      + 真實 owner library（至少一支有封面的影片）

存在理由（見 TASK-99a-T6.md）：99a-T4 落地時 948 條 static_guard + 5209 條 pytest 全綠，
但功能整組不可用 —— 「hit-test 結果」「渲染是否到達目標」兩件事，字串/AST 守衛結構上
量不到，只有真瀏覽器 e2e 量得到。本檔案只鎖 4 條斷言（owner 拍板精簡版），對應
TASK-99a-T5.md 修的兩個 P1 bug：
  1. hit-test：✓/✗ 座標真的命中按鈕本身（非 .lb-mask-overlay 疊層攔截）。
  2. detect-first：.lb-mask-window 在偵測期間不渲染；resolve 後第一幀為全幅，隨後單調
     收斂到偵測終值，全程無一幀等於基準幾何（101b-T2 CD-2/CD-4a：全幅→收斂→終值，
     取代舊有「resolve 後第一幀即終值」的無過渡態契約）。
  3. ✓ 確實呼叫 confirmMask()，觸發正確 payload 的 POST /api/showcase/video/save-focal，
     且前端把回應正確套用到 client state（crop_mode 變 manual）。
  4. ✗ 什麼都不存（無 /video/save-focal request，crop_mode 不變）。

無封面影片 / app 不可達 / 找不到合適候選 → pytest.skip()（不 FAIL，e2e 對缺環境用戶不可假紅）。

**斷言 3 設計（Codex 第二輪 review P1 修復）**：`tests/e2e/conftest.py::ensure_e2e_server`
可能重用 port 8001 上一個既有 server——那個 server 的 `get_db_path()` 不保證與本測試
進程的 `get_db_path()` 是同一個檔案（`get_db_path()` 是純 `__file__`-derived 路徑函式，
不吃任何 env var / config key，見 `core/database/connection.py`；沒有非侵入式的方式能讓
e2e fixture 指揮一個「已經在跑、我們不擁有」的 server 改用別的 DB）。舊版設計用「寫入前
比對 crop_mode/auto_focal 是否巧合相同」做前置篩選、寫入後再用 sentinel-write 補證明，
但這只是**事後量測**，不是結構性保證——若兩個不相關 DB 剛好在同一 path 有相同既有值
（例如複製過的 library），✓ 點擊仍會先打穿被重用 server 背後的**真實 DB**，測試才在那之後
偵測到不一致，木已成舟。

本版改用 Playwright request interception（`page.route`）在瀏覽器網路層攔截
`POST /api/showcase/video/save-focal`：斷言 payload（`path` + canonical `"x.xxxx,y.xxxx"` 4dp
格式、y 固定 0.5000）完全正確後，直接用 mocked 200 response `route.fulfill()`——請求**從不
離開瀏覽器**，不可能觸及任何 DB（無論是本地 get_db_path() 還是被重用 server 背後的
任一檔案）。這在結構上排除了整個「port 8001 服務不明 DB」的風險類別，不需要 DB 身分
比對、快照、還原機制。

**為什麼這樣測仍然有牙齒（不是 gutted）**：persistence 本身已由整合層驗證
（`tests/integration/test_showcase_focal_endpoints.py::TestManualFocalEndpoint` 證明
`/video/save-focal` 原子寫入 auto_focal + crop_mode='manual'、out-of-scope → 403 且 DB 不變等
server-side 行為）。e2e 這層獨一無二、integration 測試無法涵蓋的是**瀏覽器端的接線**——
99a-T5 修的兩個 P1（z-index 疊層攔截 ✓/✗ 點擊、detect-first 二次跳動）都是「事件有沒有
真的從 DOM 走到 confirmMask() 並打出正確 payload」這一類，跟 payload 送達後 DB 有沒有
正確更新是正交的兩件事。攔截並嚴格斷言 payload + 前端套用回應後的 client-side crop_mode
變化，完整覆蓋了 e2e 這層該獨有覆蓋的東西，重複測 persistence 只會多花一份「打穿 owner
真實 library」的風險，不會多驗到任何 integration 測不到的邏輯。
"""
import json
import re

import pytest
from playwright.sync_api import Page, Route, Request, TimeoutError as PlaywrightTimeoutError

pytestmark = pytest.mark.e2e


# ── 共用常數 ──────────────────────────────────────────────────────────────────

DETECT_TIMEOUT_MS = 8_000     # 實測 force-detect ~3.0-3.3s，抓生成 buffer（非固定 sleep）
LB_FULL_TIMEOUT_MS = 15_000
MASK_BTN_TIMEOUT_MS = 5_000
MAX_CANDIDATES = 8            # 候選影片探索迴圈上限，避免無上限拖垮執行時間
MIN_FOCAL_DIFF = 0.05         # 判定「偵測值與右裁基準有材料差異」的門檻（focalX 為 0..1 比例）
PROBE_MAX_MS = 6_500          # 單次 rAF 取樣迴圈總時長上限（生成 buffer vs 3.0-3.3s + 0.5s 收斂實測）
# 101b-T3：停止條件從「!detecting 後留 8 幀」改為「!detecting && !settling 後留 2-3 幀」
# （idle 判定本身已涵蓋整段 0.5s 收斂動畫，不再需要 8 幀=133ms 去「趕上」還在跑的動畫），
# 3 為 plan 給定範圍「2-3 幀」的上限，留一點餘裕。
PROBE_TAIL_FRAMES = 3         # idle（!detecting && !settling）後再多取幾幀，驗證落點穩定
# 101b-T3（§C-2 iii）：候選篩選裁切餘裕門檻——重用 mask-geometry.js:44 的
# MASK_MIN_DRAG_ROOM 語意（非發明新門檻），排除 a<=r 的退化圖（全幅與終值每個維度都
# 同值，只因 baseline_focal != final_focal 就會通過舊的單一篩選條件，證不出任何事）。
MIN_CROP_ROOM = 0.20

# 101b-T5：no-face 落點測試專用常數。
# `_maskFocalX` 對 video 分支恆為右裁基準（openMask 起手一次性解出並凍結，見
# state-lightbox.js:976-977），對應窗恆貼右緣（`left = W - winW` 已是 clamp 上界）——
# 這代表 no-face 窗的 translateX 恆等於「可拖裁切餘裕」本身（cover_w - width），與
# `test_hit_test_and_detect_first_render` 的 MIN_CROP_ROOM 語意一致，此處另訂常數只因
# 門檻表達方式不同（width 對 coverW 的比例上限，非裁切餘裕比例下限）。
NO_FACE_MAX_WIDTH_RATIO = 0.8   # width 應 < 0.8×coverW，證明有明顯裁切餘裕（scrim 有面積可見）
NO_FACE_SETTLE_TIMEOUT_MS = 4_000
NO_FACE_DRAG_STEP_PX = 15.0
# 跟手容差：真實瀏覽器事件（CDP dispatch）與 clamp 邊界都可能引入 1-2px 誤差，此門檻只
# 用來排除「跳變」（修前 bug 的症狀：起手視覺位置＝全幅，第一次 pointermove 觸發的
# `computeMaskWinGeometry` 立即算出正確終值，位移量與滑鼠實際移動量無關、可達數十至
# 上百 px），非用來要求逐 px 精確跟手。
NO_FACE_DRAG_TOLERANCE_PX = 6.0

# 101b-T3（CD-4a 首幀全幅的判準）：首個 paint 幀「已收斂比例」的容忍上限。
#
# 🔴 為何不是 ε=0.5px（plan §C-2 原寫的值，實測推翻）：GSAP ticker 的**第一次 tick 必然
#    落在 timeline 建立後的下一幀**（startTime 取自上一次 tick 的時間），故首個 paint 幀
#    **恆已走掉 ~1-4 幀的 ease 進度**——這是 ticker 的性質，**任何 ease、任何實作都躲不掉**
#    （`immediateRender:true` 亦無效：它只改建立當下的 render，不改第一次 tick 的跳躍量）。
#    「首幀 == 全幅」只能是 ≈，不可能是 ==。
#
# 為何是 15%（三批實測定值，非拍腦袋）：
#   正確實作（ease='fluent'）：2.25% / 2.5%（101b-T2 CDP，兩支 FC2）
#                             4.7%–5.9% 連續分佈（101b-T3 本檔 START-525 八跑，環境 jitter）
#   ease 誤用 'fluent-decel' ：~42%（101b-T2 CDP 實測，該 ease 把 1 幀 ticker 延遲放大成
#                             24.4% 視覺進度——正是 T2 修掉的那個 P1）
#   終值 flash（無預寫）     ：100%
#   ⇒ 門檻須同時遠離 5.9% 與 42%。取幾何中點 sqrt(5.9×42)≈15.7 → **15%**：
#     對正確實作有 2.5x 餘裕（不 flaky）、對 mutation 有 2.8x 餘裕（仍必紅）。
#     **5.9% 與 42% 之間不存在任何真實值**，故放寬只吃掉 jitter、不吃掉任何一種它要抓的缺陷。
#     （曾定 5% → 對 START-525 實測 ~40-50% flaky；flaky 守衛比沒有守衛更糟。）
MAX_FIRST_FRAME_SETTLE = 0.15

# 前端 confirmMask() 送出的 canonical focal 格式契約（state-lightbox.js:935）：
# `${x.toFixed(4)},0.5000`——y 恆 0.5（render 只用 X，spec §3.3）。
# ⚠ 格式（regex）只驗形狀，**不等於** server 契約：`\d` 放行 2.0000~9.9999，但
# core/focal/detector.py::parse_focal 要求 x ∈ [0,1] 閉區間（超出→400、不碰 DB）。
# 故斷言處另加數值範圍檢查（FOCAL_X_RANGE），否則「canonical」會比 server 寬。
FOCAL_PAYLOAD_RE = re.compile(r"^(\d\.\d{4}),0\.5000$")
FOCAL_X_MIN, FOCAL_X_MAX = 0.0, 1.0   # 鏡射 parse_focal 的 [0,1] 閉區間契約


ALPINE_ROOT_SELECTOR = '[x-data="showcase"]'
# 只認影片卡：.av-card-preview 亦匹配隱藏的 .hero-card（女優 hero，x-show 常為 false）
VIDEO_CARD_SELECTOR = ".av-card-preview[data-flip-id]"


# ── 共用 helper：抓 Alpine state / DOM rect / hit-test ─────────────────────────

def _fetch_cover_videos(page: Page, base_url: str) -> list:
    """候選影片探索：以 showcase 第一頁「DOM 上真的存在的卡片」為準，再 join
    /api/showcase/videos 的 metadata（has_cover / crop_mode）。

    刻意不直接用 API 回傳順序挑候選：API 是全庫順序，UI 有排序（預設 date desc）+
    分頁（items_per_page=90），兩者順序不一致——直接拿 API 前幾筆去找卡片會全部
    落在第一頁之外（實測 match 0/8），導致測試靜默 skip（假綠）。
    """
    resp = page.request.get(f"{base_url}/api/showcase/videos")
    if not resp.ok:
        return []
    by_path = {v["path"]: v for v in resp.json().get("videos", [])}

    page.goto(f"{base_url}/showcase")
    try:
        # 只認影片卡（[data-flip-id]）——.av-card-preview 亦匹配隱藏的 .hero-card
        # （女優 hero），若不限定會 wait 在永遠不可見的元素上 timeout（假 skip）。
        page.wait_for_selector(VIDEO_CARD_SELECTOR, state="visible", timeout=LB_FULL_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        return []

    dom_paths = page.eval_on_selector_all(
        VIDEO_CARD_SELECTOR, "els => els.map(e => e.getAttribute('data-flip-id'))"
    )
    out = []
    for p in dom_paths:
        v = by_path.get(p)
        if v and v.get("has_cover"):
            out.append(v)
    return out


def _open_lightbox_for(page: Page, base_url: str, video_path: str) -> bool:
    """導到 showcase、點對應卡片、等 _lbFullLoaded===true + .lb-mask-btn 可見。"""
    page.goto(f"{base_url}/showcase")
    try:
        page.wait_for_selector(VIDEO_CARD_SELECTOR, state="visible", timeout=LB_FULL_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        return False

    card = page.locator(f'.av-card-preview[data-flip-id="{video_path}"]')
    if card.count() == 0:
        return False
    card.first.click()

    try:
        page.wait_for_function(
            """() => {
                const root = document.querySelector('%s');
                const data = window.Alpine && Alpine.$data(root);
                return !!(data && data._lbFullLoaded);
            }""" % ALPINE_ROOT_SELECTOR,
            timeout=LB_FULL_TIMEOUT_MS,
        )
    except PlaywrightTimeoutError:
        return False

    try:
        page.wait_for_selector(".lb-mask-btn", state="visible", timeout=MASK_BTN_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        return False
    return True


def _wait_detect_resolved(page: Page, timeout: int = DETECT_TIMEOUT_MS) -> None:
    """等 _maskDetecting 翻 false（force-detect resolve，成功或失敗皆算）。"""
    page.wait_for_function(
        """() => {
            const root = document.querySelector('%s');
            const data = window.Alpine && Alpine.$data(root);
            return !!(data && data._maskDetecting === false);
        }""" % ALPINE_ROOT_SELECTOR,
        timeout=timeout,
    )


def _cancel_mask_if_open(page: Page) -> None:
    """清理 helper：若遮罩仍開著就呼叫 cancelMask()（不透過真實 click，純粹收尾用）。"""
    page.evaluate(
        """() => {
            const root = document.querySelector('%s');
            const data = window.Alpine && Alpine.$data(root);
            if (data && data._maskVisible && typeof data.cancelMask === 'function') {
                data.cancelMask();
            }
        }"""
        % ALPINE_ROOT_SELECTOR
    )


def _get_hit_test_rects(page: Page) -> dict:
    """讀 overlay / window / ✓ / ✗ 四個元素的 getBoundingClientRect()（viewport 座標）。"""
    return page.evaluate(
        """() => {
            const rect = (el) => {
                if (!el) return null;
                const r = el.getBoundingClientRect();
                return { x: r.left, y: r.top, width: r.width, height: r.height };
            };
            return {
                overlay: rect(document.querySelector('.lb-mask-overlay')),
                win: rect(document.querySelector('.lb-mask-window')),
                success: rect(document.querySelector('.lb-action-btn--success')),
                danger: rect(document.querySelector('.lb-action-btn--danger')),
            };
        }"""
    )


def _elem_from_point(page: Page, x: float, y: float) -> dict:
    """document.elementFromPoint(x, y) 命中結果，經 .closest() 分類。"""
    return page.evaluate(
        """([x, y]) => {
            const el = document.elementFromPoint(x, y);
            if (!el) return { tag: null, isButton: false, inOverlay: false, inWindow: false };
            const btn = el.closest('.lb-action-btn');
            const overlay = el.closest('.lb-mask-overlay');
            const win = el.closest('.lb-mask-window');
            return {
                tag: el.tagName,
                cls: el.className,
                isButton: !!btn,
                btnCls: btn ? btn.className : null,
                inOverlay: !!overlay,
                inWindow: !!win,
            };
        }""",
        [x, y],
    )


def _pick_outside_point(overlay: dict, window_r: dict, margin: float = 10):
    """在 overlay 內、window 外找一個安全座標（用來驗證「點外＝取消」未回歸）。

    動態依當次 rect 找左右兩側的縫隙，不假設 window 固定停在某一側
    （detect resolve 後 window 可能滑到任意位置，含貼齊 overlay 左/右緣的極端值）。
    """
    gap_left = window_r["x"] - overlay["x"]
    gap_right = (overlay["x"] + overlay["width"]) - (window_r["x"] + window_r["width"])
    mid_y = overlay["y"] + overlay["height"] / 2
    if gap_left >= margin:
        return overlay["x"] + margin / 2, mid_y
    if gap_right >= margin:
        return overlay["x"] + overlay["width"] - margin / 2, mid_y
    return None


_WIDTH_PX_RE = re.compile(r"^([\d.]+)px$")


def _parse_width(style_obj):
    """從 `_computeMaskWinStyle()` 回傳的 `{width:"123.45px", ...}`（或 `None`）解出 float。

    101b-T3：探針以 `_computeMaskWinStyle()` 作為「地面真相」（既有公開 method，純讀無
    副作用），取代對「基準幾何」「偵測終值幾何」的重複計算或猜測（CD-3 零重複實作）。
    """
    if not style_obj:
        return None
    m = _WIDTH_PX_RE.match(style_obj.get("width", ""))
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


_TRANSLATE_X_MATRIX_RE = re.compile(r"^matrix\(([^)]+)\)$")
_TRANSLATE_X_LITERAL_RE = re.compile(r"^translateX\(([-\d.]+)px\)$")


def _parse_translate_x(transform):
    """解出 translateX 分量（px），相容兩種來源格式：`getComputedStyle()` 的
    `matrix(...)`（瀏覽器正規化）與 `_computeMaskWinStyle()`/`computeMaskWinGeometry()`
    回傳的字面樣板 `translateX(Npx)`（見 mask-geometry.js）。

    101b-T3 實測發現（真跑 e2e 才量到，非理論推導）：`computeMaskWinGeometry` 的
    `winW = Math.min(W, H * r)` **不吃 `focalX`**——crop window 的寬度只取決於長寬比 r
    與影像尺寸 W/H，與焦點 X 位置無關。這代表「基準幾何」（偵測前 fallback）與「偵測
    終值幾何」在**同一支影片**（同一 W/H/r）之下，width 恆數學相等，只有 `left`/
    `transform`（X 偏移）會因 focalX 不同而不同。故「一幀是否等於基準幾何」必須同時比對
    width 與 transform 才有鑑別力——只比 width（且候選已保證 focal 有材料差異）會在收斂
    完成、width 收斂回等於基準的那一刻起造成必然的假 FAIL（非候選特例，任何非退化影片
    皆會在尾端觸發，因為收斂終值 by construction 就是「同一 r 算出的 width」）。
    """
    if not transform:
        return None
    m = _TRANSLATE_X_LITERAL_RE.match(transform.strip())
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    if transform == "none":
        return None
    m = _TRANSLATE_X_MATRIX_RE.match(transform.strip())
    if not m:
        return None
    parts = [p.strip() for p in m.group(1).split(",")]
    if len(parts) < 6:
        return None
    try:
        return float(parts[4])
    except ValueError:
        return None


_RENDER_PROBE_JS = """
() => new Promise((resolve) => {
    const root = document.querySelector('%s');
    const data = window.Alpine && Alpine.$data(root);
    if (!data) { resolve({ error: 'no-alpine-data' }); return; }
    const samples = [];
    let seenDetecting = false;
    let seenIdle = false;
    let tailCount = 0;
    let baselineStyle = null;
    const t0 = performance.now();
    function tick() {
        const win = document.querySelector('.lb-mask-window');
        const detecting = !!data._maskDetecting;
        const settling = !!data._maskSettling;
        if (detecting && !seenDetecting && typeof data._computeMaskWinStyle === 'function') {
            // 首次觀察到 detecting===true：此刻 _maskFocalX 恆為 openMask 起手基準
            // （尚未被偵測結果覆寫），呼叫既有 method 取得「地面真相」基準幾何物件，
            // 不靠讀 .lb-mask-window 的 computed style（此時 x-show 為 false，rect 是 0）。
            baselineStyle = data._computeMaskWinStyle();
        }
        seenDetecting = seenDetecting || detecting;
        let display = null, transform = null, winWidth = null;
        if (win) {
            const cs = getComputedStyle(win);
            display = cs.display;
            transform = cs.transform;
            const r = win.getBoundingClientRect();
            winWidth = r.width;
        }
        let coverWidth = null;
        const imgEl = typeof data._maskTarget === 'function' ? data._maskTarget().imgEl : null;
        if (imgEl) { coverWidth = imgEl.getBoundingClientRect().width; }
        samples.push({
            t: performance.now() - t0,
            detecting: detecting, settling: settling,
            display: display, transform: transform,
            winWidth: winWidth, coverWidth: coverWidth,
            focalX: data._maskFocalX,
        });
        const idle = seenDetecting && !detecting && !settling;
        if (idle) { seenIdle = true; }
        if (seenIdle) { tailCount += 1; }
        if ((seenIdle && tailCount >= %d) || (performance.now() - t0) > %d) {
            const groundTruthFinal = (typeof data._computeMaskWinStyle === 'function')
                ? data._computeMaskWinStyle() : null;
            resolve({
                samples: samples,
                finalFocalX: data._maskFocalX,
                baselineStyle: baselineStyle,
                groundTruthFinal: groundTruthFinal,
            });
        } else {
            requestAnimationFrame(tick);
        }
    }
    requestAnimationFrame(tick);
})
""" % (ALPINE_ROOT_SELECTOR, PROBE_TAIL_FRAMES, PROBE_MAX_MS)


def _run_render_probe(page: Page) -> dict:
    """假設 .lb-mask-btn 剛被真實點擊、force-detect 剛啟動——在瀏覽器內以
    requestAnimationFrame 連續取樣直到 detect resolve 後再多取幾幀，整段留在瀏覽器內
    執行（避免 Python↔瀏覽器 IPC 往返污染逐幀時序精度）。
    """
    return page.evaluate(_RENDER_PROBE_JS)


# ── 斷言 1 + 2：hit-test + detect-first 無二次跳動 ────────────────────────────

def test_hit_test_and_detect_first_render(page: Page, base_url: str) -> None:
    """
    斷言 1（hit-test）：✓/✗ 按鈕中心座標的 elementFromPoint 命中按鈕本身；
                         窗外座標仍命中 .lb-mask-overlay（點外＝取消未回歸）。
    斷言 2（detect-first / CD-2 / CD-4a）：.lb-mask-window 在整段 _maskDetecting===true
                         期間 display:none；resolve 後第一幀為全幅（收斂進度 <=15%），隨後
                         單調收斂到偵測終值，全程無一幀等於基準幾何（無基準閃現過渡態）。

    動態尋找一支「偵測值與右裁基準有材料差異」且「裁切餘裕足夠」的影片（不寫死番號）——
    若窗子終值恰好等於基準（退化圖 a<=r），全幅/收斂/基準三者每個維度都同值，觀察不出
    任何契約，斷言會失去意義（101b-T3 §C-2 候選篩選新增裁切餘裕條件即為此）。
    """
    videos = _fetch_cover_videos(page, base_url)
    if not videos:
        pytest.skip("找不到任何有封面的影片，跳過焦點編輯 e2e")

    counters = {"scanned": 0, "open_failed": 0, "probe_error": 0, "no_focal_diff": 0, "degenerate": 0}
    found = None
    for v in videos[:MAX_CANDIDATES]:
        path = v["path"]
        counters["scanned"] += 1
        if not _open_lightbox_for(page, base_url, path):
            counters["open_failed"] += 1
            continue

        page.locator(".lb-mask-btn").click()
        result = _run_render_probe(page)
        samples = result.get("samples") or []
        if result.get("error") or not samples:
            counters["probe_error"] += 1
            _cancel_mask_if_open(page)
            continue

        detecting_samples = [s for s in samples if s["detecting"]]
        if not detecting_samples:
            counters["probe_error"] += 1
            _cancel_mask_if_open(page)
            continue

        baseline_focal = detecting_samples[0]["focalX"]
        final_focal = result.get("finalFocalX")
        if baseline_focal is None or final_focal is None:
            counters["probe_error"] += 1
            _cancel_mask_if_open(page)
            continue

        if abs(final_focal - baseline_focal) < MIN_FOCAL_DIFF:
            counters["no_focal_diff"] += 1
            _cancel_mask_if_open(page)
            continue

        # 101b-T3（§C-2 iii）：裁切餘裕條件——退化圖（a<=r）的全幅/終值/基準每個維度都
        # 同值，只因 baseline_focal != final_focal 就會通過上面的篩選，證不出任何事。
        # finalWinW 取自完整樣本序列的 groundTruthFinal（地面真相），不取截斷樣本中途值。
        cover_w = next((s["coverWidth"] for s in reversed(samples) if s["coverWidth"]), None)
        final_win_w = _parse_width(result.get("groundTruthFinal"))
        crop_room = (cover_w - final_win_w) / cover_w if (cover_w and final_win_w is not None) else None
        if crop_room is None or crop_room < MIN_CROP_ROOM:
            counters["degenerate"] += 1
            _cancel_mask_if_open(page)
            continue

        found = {
            "path": path,
            "samples": samples,
            "baseline_focal": baseline_focal,
            "final_focal": final_focal,
            "ground_truth_final": result.get("groundTruthFinal"),
            "baseline_style": result.get("baselineStyle"),
        }
        break

    if found is None:
        pytest.skip(
            f"窮舉 {counters['scanned']} 部候選影片找不到合格樣本："
            f"open_failed={counters['open_failed']}, probe_error={counters['probe_error']}, "
            f"no_focal_diff={counters['no_focal_diff']}（差異 < {MIN_FOCAL_DIFF}）, "
            f"degenerate={counters['degenerate']}（裁切餘裕 < {MIN_CROP_ROOM}），跳過 e2e"
        )

    try:
        samples = found["samples"]

        # --- 斷言 2a：detecting 期間全程 display:none ---
        detecting_rows = [s for s in samples if s["detecting"]]
        for s in detecting_rows:
            assert s["display"] == "none", (
                f".lb-mask-window 應在 _maskDetecting===true 期間 display:none，"
                f"實際樣本：{s}"
            )

        # 101b-T3：detect resolve 後「已 paint」的幀（display 可能仍是 'none' 一拍，Alpine
        # 的 x-show effect 尚未 flush，那一幀還沒畫出任何東西、不構成「使用者看得到的第一
        # 幀」，取樣要篩掉）。
        first_false_idx = next(i for i, s in enumerate(samples) if not s["detecting"])
        post = [s for s in samples[first_false_idx:] if s["display"] and s["display"] != "none"]
        assert len(post) >= 2, (
            f"detect resolve 後「已 paint」的取樣幀數不足（{len(post)}），無法驗證收斂序列"
        )

        cover_w = post[0]["coverWidth"]
        gt = found["ground_truth_final"]
        assert gt is not None, "groundTruthFinal 缺失，可能 _computeMaskWinStyle 不可用"
        final_win_w = _parse_width(gt)
        assert final_win_w is not None, f"groundTruthFinal 無法解出 width：{gt}"

        # --- 斷言 2b（CD-4a）：首幀為全幅（收斂進度 <= MAX_FIRST_FRAME_SETTLE，非 ε=0.5px——見其宣告處） ---
        first = post[0]
        assert first["winWidth"] is not None and cover_w, (
            f"首幀 winWidth/coverWidth 缺失：{first}"
        )
        threshold = cover_w - MAX_FIRST_FRAME_SETTLE * (cover_w - final_win_w)
        assert first["winWidth"] >= threshold - 0.5, (
            f"首次可見幀應為全幅（收斂進度 <={MAX_FIRST_FRAME_SETTLE:.0%}），實際 winWidth={first['winWidth']:.2f}px，"
            f"coverWidth={cover_w:.2f}px, finalWinW={final_win_w:.2f}px, threshold={threshold:.2f}px"
        )

        # --- 斷言 2c：收斂終值 == 偵測終值（地面真相）——width 與 transform 都要比 ---
        # Codex PR review P1 修正：`winW = min(W, H*r)` 不吃 focalX（見 _parse_translate_x
        # 註解），故只比 width 時，proxy 若停在**錯的** focalX（非基準、也非正確終值）仍會
        # 因 width 數學相等而通過——錯的終值 X 整條溜過。追加 translateX 比對（容差比照
        # 2d 的 1.0px），兩者都要等於地面真相才判定「收斂到正確終值」。
        last = post[-1]
        assert last["winWidth"] is not None, f"末幀 winWidth 缺失：{last}"
        assert abs(last["winWidth"] - final_win_w) < 0.5, (
            f"收斂終值應等於偵測終值（地面真相），實際 last winWidth={last['winWidth']:.2f}px, "
            f"ground truth={final_win_w:.2f}px"
        )
        final_win_tx = _parse_translate_x(gt.get("transform"))
        last_tx = _parse_translate_x(last.get("transform"))
        assert final_win_tx is not None and last_tx is not None, (
            f"末幀或地面真相的 transform 無法解出 translateX：last={last.get('transform')!r}, "
            f"ground_truth={gt.get('transform')!r}"
        )
        assert abs(last_tx - final_win_tx) < 1.0, (
            f"收斂終值的 transform 應等於偵測終值（地面真相），實際 last translateX={last_tx:.2f}px, "
            f"ground truth translateX={final_win_tx:.2f}px（winWidth 相符不足以證明終值正確，"
            f"因 winW 不吃 focalX）"
        )

        # --- 斷言 2d：全程無一幀「同時」width 與 transform 都等於基準幾何（baseline flash
        # 復發）。🔴 101b-T3 真跑 e2e 才發現（非理論推導）：`computeMaskWinGeometry` 的
        # `winW = Math.min(W, H * r)` 不吃 `focalX`，故「基準幾何」與「偵測終值幾何」在
        # 同一支影片（同一 W/H/r）之下 width 恆數學相等——只比 width 會在收斂完成、width
        # 收斂回等於基準的那一刻起造成必然假 FAIL（任何非退化影片皆會在尾端觸發，因為
        # 收斂終值 by construction 就是「同一 r 算出的 width」）。真正能區分「仍是基準」
        # 與「已收斂到終值」的維度是 transform（X 偏移，隨 focalX 而異）——候選篩選已保證
        # `abs(final_focal - baseline_focal) >= MIN_FOCAL_DIFF`，故終值 transform 必與
        # 基準 transform 有材料差異，兩者同時相等（width AND transform）才判定為
        # 「baseline flash 復發」，避免在收斂終值幀誤判。
        baseline = found["baseline_style"]
        assert baseline is not None, "baselineStyle 缺失，探針啟動時可能從未觀察到 detecting===true"
        baseline_w = _parse_width(baseline)
        assert baseline_w is not None, f"baselineStyle 無法解出 width：{baseline}"
        baseline_tx = _parse_translate_x(baseline.get("transform"))
        for s in post:
            if s["winWidth"] is None:
                continue
            width_matches = abs(s["winWidth"] - baseline_w) < 0.5
            tx = _parse_translate_x(s["transform"])
            tx_matches = (
                baseline_tx is not None and tx is not None and abs(tx - baseline_tx) < 1.0
            )
            assert not (width_matches and tx_matches), (
                f"偵測到一幀等於基準幾何（baseline flash 復發）：t={s['t']:.1f}ms, "
                f"winWidth={s['winWidth']:.2f}px == baseline={baseline_w:.2f}px, "
                f"transform={s['transform']!r} == baseline_transform={baseline.get('transform')!r}"
            )

        # --- 斷言 2e：單調無回彈 ---
        widths = [s["winWidth"] for s in post if s["winWidth"] is not None]
        for i in range(1, len(widths)):
            assert widths[i] <= widths[i - 1] + 0.5, (
                f"收斂應單調不遞增（無回彈），實際第 {i-1} 幀 {widths[i-1]:.2f}px → "
                f"第 {i} 幀 {widths[i]:.2f}px"
            )

        # --- 斷言 1：hit-test ---
        rects = _get_hit_test_rects(page)
        overlay, window_r = rects["overlay"], rects["win"]
        success_btn, danger_btn = rects["success"], rects["danger"]
        assert overlay and window_r and success_btn and danger_btn, (
            f"必要元素 rect 缺失（遮罩可能已提前關閉）：{rects}"
        )

        sx = success_btn["x"] + success_btn["width"] / 2
        sy = success_btn["y"] + success_btn["height"] / 2
        dx = danger_btn["x"] + danger_btn["width"] / 2
        dy = danger_btn["y"] + danger_btn["height"] / 2

        hit_success = _elem_from_point(page, sx, sy)
        assert hit_success["isButton"], (
            f"✓ 按鈕中心 ({sx:.1f}, {sy:.1f}) 的 elementFromPoint 應命中按鈕本身"
            f"（經 .closest('.lb-action-btn')），實際：{hit_success}"
        )

        hit_danger = _elem_from_point(page, dx, dy)
        assert hit_danger["isButton"], (
            f"✗ 按鈕中心 ({dx:.1f}, {dy:.1f}) 的 elementFromPoint 應命中按鈕本身"
            f"（經 .closest('.lb-action-btn')），實際：{hit_danger}"
        )

        outside = _pick_outside_point(overlay, window_r)
        assert outside is not None, (
            f"找不到「遮罩窗外仍在 overlay 內」的安全座標——overlay={overlay}, window={window_r}"
        )
        ox, oy = outside
        hit_outside = _elem_from_point(page, ox, oy)
        assert hit_outside["inOverlay"] and not hit_outside["inWindow"] and not hit_outside["isButton"], (
            f"窗外座標 ({ox:.1f}, {oy:.1f}) 應仍命中 .lb-mask-overlay（點外＝取消不回歸），"
            f"實際：{hit_outside}"
        )
    finally:
        _cancel_mask_if_open(page)


# ── 斷言 3 + 4：✓ 確實存 / ✗ 什麼都不存 ────────────────────────────────────────

def test_confirm_saves_and_cancel_saves_nothing(page: Page, base_url: str) -> None:
    """
    斷言 4（✗ 不存）：真實 click ✗ → 無 /video/save-focal request，crop_mode 不變。
    斷言 3（✓ 確實存）：真實 click ✓ → POST /api/showcase/video/save-focal 真的以正確 payload
                         觸發，且前端把回應正確套用到 client state（crop_mode 變 manual）。

    斷言 3 的請求用 `page.route()` 攔截並以 mocked 200 response `fulfill()`——請求
    **從不離開瀏覽器**，結構上不可能寫入任何 DB（見本檔開頭模組 docstring「斷言 3 設計」
    段落：`get_db_path()` 無任何非侵入式 override 機制，`ensure_e2e_server` 重用既有
    server 時無法保證它與本測試進程用同一個 DB 檔案，唯一結構安全的做法是讓寫入請求
    根本不送達任何 server）。persistence 本身已由
    `tests/integration/test_showcase_focal_endpoints.py::TestManualFocalEndpoint` 在
    server 端驗證（原子寫 auto_focal + crop_mode='manual'、out-of-scope→403 且 DB 不變）。
    """
    videos = _fetch_cover_videos(page, base_url)
    candidates = [v for v in videos if v.get("crop_mode") == "auto"]
    if not candidates:
        pytest.skip(
            "找不到 crop_mode='auto' 且有封面的影片，跳過"
            "（避免動到已是 manual/default 的既有資料列）"
        )

    target = None
    for v in candidates[:MAX_CANDIDATES]:
        if _open_lightbox_for(page, base_url, v["path"]):
            target = v
            break
    if target is None:
        pytest.skip("候選影片皆無法開啟 lightbox，跳過")

    video_path = target["path"]

    # ── 斷言 4：✗ 應該什麼都不存（無 DB 寫入，讀真實 server 狀態是安全的，不需 mock） ──
    page.locator(".lb-mask-btn").click()
    _wait_detect_resolved(page)
    page.wait_for_selector(".lb-action-btn--danger", state="visible", timeout=3_000)

    focal_requests = []

    def _record(req):
        if req.method == "POST" and "/api/showcase/video/save-focal" in req.url:
            focal_requests.append(req.url)

    page.on("request", _record)
    try:
        rects = _get_hit_test_rects(page)
        danger = rects["danger"]
        assert danger, "✗ 按鈕 rect 缺失，遮罩可能未正確開啟"
        dx = danger["x"] + danger["width"] / 2
        dy = danger["y"] + danger["height"] / 2
        page.mouse.click(dx, dy)
        page.wait_for_timeout(800)  # 讓「什麼都沒發生」有機會被觀察到
    finally:
        page.remove_listener("request", _record)

    assert not focal_requests, (
        f"✗ 點擊後不應有 /video/save-focal request，實際攔到：{focal_requests}"
    )

    resp = page.request.get(f"{base_url}/api/showcase/video", params={"path": video_path})
    body = resp.json()
    assert body.get("success"), f"確認影片狀態失敗：{body}"
    assert body["video"]["crop_mode"] == "auto", (
        f"✗ 後 crop_mode 不應改變，實際：{body['video']['crop_mode']}"
    )

    # ── 斷言 3：✓ 應該真的觸發正確 payload 的 POST，且前端套用回應更新 client state ──
    # route 攔截：payload 驗證後 fulfill 一個 mocked 200，請求從不到達 server/DB。
    captured = {}

    def _handle_focal_route(route: Route) -> None:
        request: Request = route.request
        captured["url"] = request.url
        captured["method"] = request.method
        try:
            captured["payload"] = request.post_data_json
        except Exception:
            captured["payload"] = None
        # mocked response：直接把送來的 focal 回顯為 auto_focal（模擬 server 端
        # format_focal(parse_focal(...)) 對合法 canonical 字串的 idempotent 正規化）。
        mocked_auto_focal = (captured["payload"] or {}).get("focal", "")
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"success": True, "auto_focal": mocked_auto_focal}),
        )

    page.route("**/api/showcase/video/save-focal", _handle_focal_route)
    try:
        page.locator(".lb-mask-btn").click()
        _wait_detect_resolved(page)
        page.wait_for_selector(".lb-action-btn--success", state="visible", timeout=3_000)

        rects = _get_hit_test_rects(page)
        success = rects["success"]
        assert success, "✓ 按鈕 rect 缺失，遮罩可能未正確開啟"
        cx = success["x"] + success["width"] / 2
        cy = success["y"] + success["height"] / 2

        # 用 expect_response（非 expect_request）等待——這是刻意選擇，非隨手替換：
        # expect_request 只保證 Chromium 的 'Network.requestWillBeSent' 事件已送達，
        # 不保證我們這支 Python route handler（收到 'Fetch.requestPaused' 後才觸發、
        # 走獨立的 CDP event stream）已經執行完 route.fulfill()——兩者之間有真實 race
        # window（實測 ~500ms，見 99a-T6 P1 第二輪修復除錯記錄）。若之後的斷言在這個
        # race window 內失敗，下面 finally 的 page.unroute() 會把「尚未被我們的
        # handler 處理、還卡在 Fetch domain 的 paused request」直接放行到真實網路——
        # 這正是上一輪修復漏掉的路徑：mocked route 看似攔截成功，實際上在特定時序下
        # 讓請求逃逸打穿真實 server。expect_response 等的是 fulfill() 產生的回應本身，
        # 只有 handler 真正跑完、呼叫過 fulfill() 之後才可能有 response 事件，用它才能
        # 結構性保證「with 區塊結束時 handler 必已執行完」，徹底關掉這個 race。
        with page.expect_response(
            lambda r: r.request.method == "POST" and "/api/showcase/video/save-focal" in r.url,
            timeout=5_000,
        ) as resp_info:
            page.mouse.click(cx, cy)
        assert resp_info.value is not None, "✓ 點擊後應觸發 POST /api/showcase/video/save-focal"
        assert resp_info.value.status == 200, (
            f"mocked route 應回 200，實際：{resp_info.value.status}"
            "（非 200 代表 fulfill 未如預期執行，或請求真的打穿到別處）"
        )

        # --- payload 契約斷言（嚴格：防止 browser↔endpoint contract drift 溜過） ---
        assert captured.get("payload") is not None, (
            f"攔截到的 request 應有 JSON body，實際：{captured}"
        )
        payload = captured["payload"]
        assert payload.get("path") == video_path, (
            f"POST payload path 應等於目標影片 path，實際：{payload}"
        )
        focal_value = payload.get("focal", "")
        m = FOCAL_PAYLOAD_RE.match(focal_value)
        assert m is not None, (
            f"POST payload focal 應符合 canonical \"x.xxxx,y.xxxx\" 4dp 格式且 y=0.5000"
            f"（state-lightbox.js confirmMask() 契約），實際：{focal_value!r}"
        )
        # 形狀對還不夠：x 必須落在 server 的 [0,1] 閉區間（parse_focal），否則真實
        # server 會 400、不寫 DB——mocked 200 會讓這種 payload 靜默通過（Codex P3）。
        focal_x = float(m.group(1))
        assert FOCAL_X_MIN <= focal_x <= FOCAL_X_MAX, (
            f"POST payload focal 的 x 應落在 server parse_focal 的 [{FOCAL_X_MIN},{FOCAL_X_MAX}] "
            f"閉區間（超出→真實 server 回 400、不碰 DB），實際：{focal_x}（payload {focal_value!r}）"
        )

        # expect_response 只保證 HTTP response 已送達頁面，不保證 fetch() 的 .then()
        # chain（confirmMask 內 await resp.json() 之後才 mutate targetVideo）已跑完——
        # 用 wait_for_function 輪詢等 client state 真的翻到 manual 或逾時，取代盲猜的
        # 固定 sleep（也讓底下 assert 拿到的 lb_state 不會因為時序差一點點而誤判）。
        try:
            page.wait_for_function(
                """() => {
                    const root = document.querySelector('%s');
                    const data = window.Alpine && Alpine.$data(root);
                    const v = data && data.currentLightboxVideo;
                    return !!(v && v.crop_mode === 'manual');
                }""" % ALPINE_ROOT_SELECTOR,
                timeout=3_000,
            )
        except PlaywrightTimeoutError:
            pass  # 逾時不在此立即 fail——讓下面的 assert 讀到目前實際狀態、給出明確診斷訊息

        # --- 前端套用回應後的 client state 斷言 ---
        lb_state = page.evaluate(
            """() => {
                const root = document.querySelector('%s');
                const data = window.Alpine && Alpine.$data(root);
                const v = data && data.currentLightboxVideo;
                return v ? { crop_mode: v.crop_mode, auto_focal: v.auto_focal, path: v.path } : null;
            }"""
            % ALPINE_ROOT_SELECTOR
        )
        assert lb_state is not None, "✓ 後應仍在 lightbox 內，currentLightboxVideo 不應為 null"
        assert lb_state["path"] == video_path, f"currentLightboxVideo path 不符：{lb_state}"
        assert lb_state["crop_mode"] == "manual", (
            f"✓ 後前端 client state 的 crop_mode 應變 manual，實際：{lb_state}"
            "（若仍是 auto，代表 ✓ 靜默觸發了 cancelMask 或 confirmMask 回應處理回歸，"
            "T5 的 P1 bug 復發）"
        )
        assert lb_state["auto_focal"] == focal_value, (
            f"前端套用 mocked response 後 auto_focal 應等於送出的 focal payload："
            f"期望 {focal_value!r}，實際 {lb_state!r}"
        )
    finally:
        page.unroute("**/api/showcase/video/save-focal", _handle_focal_route)
        _cancel_mask_if_open(page)

    # ── 結構性保證的收尾驗證：真實 server DB 應完全未被寫入 ──
    # 上面整段 ✓ 流程的 POST 從未離開瀏覽器（page.route 攔截 + fulfill），這裡再對
    # 真實 server 讀一次確認 crop_mode 仍是候選篩選時保證的 'auto'——不是「補救措施」，
    # 是結構論證的複驗（request interception 正確運作的話，這裡必然通過）。
    resp = page.request.get(f"{base_url}/api/showcase/video", params={"path": video_path})
    body = resp.json()
    assert body.get("success"), f"確認影片狀態失敗：{body}"
    assert body["video"]["crop_mode"] == "auto", (
        f"結構性保證複驗失敗：真實 server DB 的 crop_mode 應仍是 'auto'（mocked ✓ 流程"
        f"從未送達 server），實際：{body['video']['crop_mode']}——若不是 'auto'，代表"
        f"page.route() 攔截失效、請求真的打穿了 server，需要立即調查。"
    )


# ── no-face 落點：窗應落基準幾何（非全幅），DoD①②（TASK-101b-T5） ─────────────

def _read_mask_window_measurements(page: Page) -> dict:
    """讀 `.lb-mask-window` 實際 computed style（width/transform）+ 地面真相
    （`_computeMaskWinStyle()`）+ `_mask*` flags，供 no-face 落點斷言與拖曳過程中的
    即時量測共用（101b-T5，比照既有 `_get_hit_test_rects` 的「單一 evaluate 取全部值」
    寫法，避免逐項往返 IPC 造成量測時間點不一致）。
    """
    return page.evaluate(
        """() => {
            const root = document.querySelector('%s');
            const data = window.Alpine && Alpine.$data(root);
            if (!data) return { error: 'no-alpine-data' };
            const win = document.querySelector('.lb-mask-window');
            let width = null, transform = null;
            if (win) {
                const cs = getComputedStyle(win);
                width = cs.width;
                transform = cs.transform;
            }
            const imgEl = typeof data._maskTarget === 'function' ? data._maskTarget().imgEl : null;
            const coverWidth = imgEl ? imgEl.getBoundingClientRect().width : null;
            const groundTruth = typeof data._computeMaskWinStyle === 'function'
                ? data._computeMaskWinStyle() : null;
            return {
                width: width, transform: transform, coverWidth: coverWidth,
                groundTruth: groundTruth,
                maskVisible: !!data._maskVisible,
                maskSettling: !!data._maskSettling,
                maskDetecting: !!data._maskDetecting,
            };
        }"""
        % ALPINE_ROOT_SELECTOR
    )


def test_no_face_settles_to_baseline_geometry(page: Page, base_url: str) -> None:
    """
    TASK-101b-T5：`_maskStartSettle` 步驟③ no-face（沒找到臉／偵測失敗）分支落點修復驗證。

    修前 bug：該分支一律寫 `this._maskWinStyle = g0`（全幅收斂起點），但 no-face 沒有
    步驟⑥的 proxy tween 收斂它 → 窗**永久停在全幅**——全幅時窗外可暗化寬度為 0，
    `box-shadow` scrim 無可暗化區域，遮罩對使用者**隱形**，違反 spec §4.2「沒找到臉→
    亮窗直接以基準位置淡入，不收斂」。

    用 `page.route` 攔截 `POST /api/showcase/video/detect-focal`，回 200 但
    `auto_focal: ''`（→ `parseFocal('')` 回 `null` → `sawFace` 恆 `false`，見
    `state-lightbox.js:1062`）——確定性觸發 no-face 分支，不依賴真實素材是否恰好無臉
    可測。🔴 用 `expect_response` 等 `fulfill()` 真正跑完（既有 gotcha，同
    `test_confirm_saves_and_cancel_saves_nothing`：`expect_request` 只保證請求已發出，
    不保證我們的 handler 已跑完 `fulfill()`，競態下可能落到真 DB／真 pigo 呼叫）。

    斷言①（DoD①）：no-face 窗最終 `width` < 0.8×coverW（有明顯裁切餘裕，非全幅——
                    `width < coverW` 本身即證明 scrim 有面積可見）、`translateX` > 0
                    （右裁，非全幅的 0），且等於 `_computeMaskWinStyle()` 地面真相
                    （容差 0.5px/1px，比照既有 `test_hit_test_and_detect_first_render`
                    斷言 2c 的容差慣例）。
    斷言②（DoD②，次要症狀）：真實 `pointerdown→pointermove→pointerup` 序列
                    （`page.mouse`，非函式呼叫模擬——繞過真實 hit-test 判定）在 no-face
                    窗上拖曳，過程中 `_maskVisible` 全程為 `true`（未誤觸
                    `.lb-mask-overlay` 的 `@click.self="cancelMask()"`），且窗跟手
                    移動、無「跳變」（第一次 `pointermove` 的位移量應與滑鼠位移相稱，
                    非離散跳到別處——修前 bug 的「起手視覺位置＝全幅」會讓第一次 move
                    因 `computeMaskWinGeometry` 即時寫入正確終值而產生一次與滑鼠位移量
                    無關的大跳動）。
    """
    videos = _fetch_cover_videos(page, base_url)
    if not videos:
        pytest.skip("找不到任何有封面的影片，跳過 no-face 落點 e2e")

    def _handle_no_face_route(route: Route) -> None:
        request: Request = route.request
        try:
            payload = request.post_data_json or {}
        except Exception:
            payload = {}
        path = payload.get("path", "")
        # cover_path 只需為字串（confirmMask 前置條件之一，本測試不按 ✓，值本身不影響
        # 任何斷言）；直接回傳前端傳來的 path（本就是合法 file:/// DB-key URI），不手動
        # 建構 file:///（違反 CLAUDE.md 路徑契約、test_no_manual_uri_construct 會紅）。
        # auto_focal 空字串 → parseFocal('') 回 null → sawFace 恆 false。
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"success": True, "cover_path": path, "auto_focal": ""}),
        )

    counters = {"scanned": 0, "open_failed": 0, "route_error": 0, "no_room": 0, "settle_timeout": 0}
    found = None
    page.route("**/api/showcase/video/detect-focal", _handle_no_face_route)
    try:
        for v in videos[:MAX_CANDIDATES]:
            path = v["path"]
            counters["scanned"] += 1
            if not _open_lightbox_for(page, base_url, path):
                counters["open_failed"] += 1
                continue

            try:
                with page.expect_response(
                    lambda r: r.request.method == "POST" and "/api/showcase/video/detect-focal" in r.url,
                    timeout=DETECT_TIMEOUT_MS,
                ):
                    page.locator(".lb-mask-btn").click()
            except PlaywrightTimeoutError:
                counters["route_error"] += 1
                _cancel_mask_if_open(page)
                continue

            _wait_detect_resolved(page)
            try:
                # 等 settling timeline 也跑完（星空/spinner 淡出＋窗 opacity 淡入），
                # 幾何本身在 _maskDetecting 翻 false 那一刻已是終值（同步賦值，見
                # _maskStartSettle 步驟③），這裡只是確保量測落在穩定態、非過渡中繼幀。
                page.wait_for_function(
                    """() => {
                        const root = document.querySelector('%s');
                        const data = window.Alpine && Alpine.$data(root);
                        return !!(data && data._maskDetecting === false && data._maskSettling === false);
                    }""" % ALPINE_ROOT_SELECTOR,
                    timeout=NO_FACE_SETTLE_TIMEOUT_MS,
                )
            except PlaywrightTimeoutError:
                counters["settle_timeout"] += 1
                _cancel_mask_if_open(page)
                continue

            m = _read_mask_window_measurements(page)
            if m.get("error") or not m.get("groundTruth") or not m.get("coverWidth"):
                counters["route_error"] += 1
                _cancel_mask_if_open(page)
                continue

            actual_w = _parse_width(m)
            actual_tx = _parse_translate_x(m.get("transform"))
            cover_w = m["coverWidth"]
            if actual_w is None or actual_tx is None:
                counters["route_error"] += 1
                _cancel_mask_if_open(page)
                continue

            # 🔴 候選篩選必須用「地面真相」（_computeMaskWinStyle()，純函式，只吃
            # el/rect/r/_maskFocalX——no-face 時 _maskFocalX 全程未被 detect 回應改動，
            # 見 state-lightbox.js:1062，故此值與本 task 要修的 bug 完全解耦），不可用
            # `actual_w`（受 bug 影響的觀察值）篩選：若用 actual_w，mutation 還原成
            # `= g0` 後**每一支影片**的 actual_w 都會等於 coverW（bug 本身就是全域性的、
            # 非個別影片幾何造成），篩選迴圈會把全部候選判定為「裁切餘裕不足」而
            # pytest.skip()，讓「必紅」的 mutation 驗證假綠成 skip——地面真相不受
            # bug 影響，篩的是「這支影片本身的長寬比是否退化（a<=r）」，與 bug 正交。
            gt_w_candidate = _parse_width(m.get("groundTruth"))
            if gt_w_candidate is None:
                counters["route_error"] += 1
                _cancel_mask_if_open(page)
                continue

            if gt_w_candidate >= NO_FACE_MAX_WIDTH_RATIO * cover_w:
                counters["no_room"] += 1
                _cancel_mask_if_open(page)
                continue

            found = {
                "path": path, "measurement": m,
                "actual_w": actual_w, "actual_tx": actual_tx, "cover_w": cover_w,
            }
            break

        if found is None:
            pytest.skip(
                f"窮舉 {counters['scanned']} 部候選影片找不到合格樣本（no-face 落點 e2e）："
                f"open_failed={counters['open_failed']}, route_error={counters['route_error']}, "
                f"settle_timeout={counters['settle_timeout']}, no_room={counters['no_room']}"
                f"（裁切餘裕不足，width >= {NO_FACE_MAX_WIDTH_RATIO}×coverW），跳過 e2e"
            )

        try:
            m = found["measurement"]
            actual_w = found["actual_w"]
            actual_tx = found["actual_tx"]
            cover_w = found["cover_w"]
            gt = m["groundTruth"]
            gt_w = _parse_width(gt)
            gt_tx = _parse_translate_x(gt.get("transform"))
            assert gt_w is not None and gt_tx is not None, (
                f"groundTruth（_computeMaskWinStyle()）無法解出 width/transform：{gt}"
            )

            # --- 斷言①a：width < 0.8×coverW（有明顯裁切餘裕，非全幅——scrim 有面積可見） ---
            assert actual_w < NO_FACE_MAX_WIDTH_RATIO * cover_w, (
                f"no-face 窗應落基準（有明顯裁切餘裕），實際 width={actual_w:.2f}px "
                f"應 < {NO_FACE_MAX_WIDTH_RATIO}×coverW={cover_w:.2f}px"
                "（若相等或接近 coverW，代表窗停在全幅，遮罩對使用者隱形——bug 復發）"
            )

            # --- 斷言①b：translateX > 0（右裁，非全幅的 0） ---
            assert actual_tx > 0, (
                f"no-face 窗應右裁（translateX > 0），實際 translateX={actual_tx:.2f}px"
                "（0 代表窗貼左緣＝全幅或未裁切，bug 復發）"
            )

            # --- 斷言①c：等於地面真相（_computeMaskWinStyle()），容差比照既有斷言 2c ---
            assert abs(actual_w - gt_w) < 0.5, (
                f"no-face 窗 width 應等於 _computeMaskWinStyle() 地面真相，"
                f"實際 {actual_w:.2f}px，地面真相 {gt_w:.2f}px"
            )
            assert abs(actual_tx - gt_tx) < 1.0, (
                f"no-face 窗 translateX 應等於 _computeMaskWinStyle() 地面真相，"
                f"實際 {actual_tx:.2f}px，地面真相 {gt_tx:.2f}px"
            )

            # --- 斷言②：拖曳不誤觸「點外取消」，且跟手無跳變（真實 pointer 事件序列） ---
            rects = _get_hit_test_rects(page)
            window_r = rects["win"]
            assert window_r, "no-face 窗 rect 缺失，遮罩可能已提前關閉"
            cx = window_r["x"] + window_r["width"] / 2
            cy = window_r["y"] + window_r["height"] / 2

            page.mouse.move(cx, cy)
            page.mouse.down()
            try:
                # video 分支的基準恆貼右緣（_maskFocalX = openMask 起手一次性解出的右裁
                # 常數，見 state-lightbox.js:976-977），故 translateX 已是 clamp 上界——
                # 唯一有效可拖方向是往左，且步距不可超過現有 translateX 的安全比例，
                # 避免撞左緣 clamp 讓「跟手」量測失真。
                step = min(NO_FACE_DRAG_STEP_PX, actual_tx / 3) if actual_tx > 0 else NO_FACE_DRAG_STEP_PX
                assert step > 0.5, f"可拖裁切餘裕過小，無法可靠量測跟手（actual_tx={actual_tx:.2f}px）"

                page.mouse.move(cx - step, cy)
                after_move1 = _read_mask_window_measurements(page)
                tx1 = _parse_translate_x(after_move1.get("transform"))
                assert tx1 is not None, f"拖曳第一次 move 後 transform 無法解出：{after_move1}"
                delta1 = actual_tx - tx1
                assert abs(delta1 - step) < NO_FACE_DRAG_TOLERANCE_PX, (
                    f"拖曳第一次 pointermove 應跟手（位移量與滑鼠位移相稱），"
                    f"滑鼠位移 {step:.1f}px，窗實際位移 {delta1:.1f}px"
                    "（差異過大＝跳變，代表起手視覺位置與拖曳起點不一致，次要症狀復發）"
                )
                assert bool(after_move1.get("maskVisible")), (
                    "拖曳第一次 move 後遮罩不應被關閉（_maskVisible 應仍 true）"
                )

                page.mouse.move(cx - step * 2, cy)
                after_move2 = _read_mask_window_measurements(page)
                tx2 = _parse_translate_x(after_move2.get("transform"))
                assert tx2 is not None, f"拖曳第二次 move 後 transform 無法解出：{after_move2}"
                delta2 = tx1 - tx2
                assert abs(delta2 - step) < NO_FACE_DRAG_TOLERANCE_PX, (
                    f"拖曳第二次 pointermove 應持續跟手，"
                    f"預期再位移 {step:.1f}px，窗實際位移 {delta2:.1f}px"
                )
                assert bool(after_move2.get("maskVisible")), (
                    "拖曳第二次 move 後遮罩不應被關閉（_maskVisible 應仍 true）"
                )
            finally:
                page.mouse.up()

            after_up = _read_mask_window_measurements(page)
            assert bool(after_up.get("maskVisible")), (
                "拖曳完（pointerup）後遮罩不應被關閉（_maskVisible 應仍 true）——次要症狀："
                "全幅窗被拖曳時起手位置與視覺不一致，可能讓 pointerup 落在跳變後的窗外"
                "觸發 .lb-mask-overlay 的 @click.self=\"cancelMask()\""
            )
        finally:
            _cancel_mask_if_open(page)
    finally:
        page.unroute("**/api/showcase/video/detect-focal", _handle_no_face_route)
