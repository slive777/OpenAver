// 整理與改名的舞台 scene（TASK-191a-T9：跟著捲動演出四步＋游標＋結尾按鈕）。
// 介面：mount(root) 第一次成功啟動時呼叫一次；layout(canvas, scale) 量位置（畫布內座標）並算好游標路徑；
// render(v) 純函式畫面；cursorKeyframes 由 layout() 算好，scene 自己用 cursorAt() 畫游標（引擎不畫）。
//
// 結構：render(v) ＝ paint(stateOf(v))。
//   stateOf(v)：只吃 v、回傳純資料（無 DOM 參照、不讀上一幀）→ 同一個 v 不論從哪個方向到達，畫面相同。
//   paint(state)：唯一寫 DOM 的函式，只走 css／txt／cls／op（比對上次值才寫）；位置類用 layout() 量到的 geo。
// 時間表（seg／ease／out 的邊界與係數）逐字取自 poc/v4/stage.js 的 render／renderCursor／layout。
// 畫面文字全部在 partial 由多語系輸出；本檔只用 txt() 寫 ASCII 品牌名與「變形」中的檔名／預覽文字
// （兩端字串 mount 時從畫面上讀，本檔不呼叫翻譯函式、不寫非 ASCII 字面、不判斷主題）。
// 位移一律寫 matrix()（平移＋等比縮放），數值與公式取自 poc/v4/stage.js。
import { clamp, seg, ease, lerp, cursorAt } from './stage-math.js';
import { css, cls, op, txt, dropCache } from './stage-engine.js';

const TAB_PEEK = 16; // 步 2：分頁列上緣露出的餘量（POC G.S2）
const RING_PAD_X = 12; // 橘框相對 Metatube 標題的外擴（POC mtv）
const RING_PAD_Y = 10;
const RING_H = 92;
const RING_MAX_W = 720;
const SEARCH_PEEK = 16; // 步 3／4：檔案區下緣的餘量（POC G.S4）
const PV_LEAD = 150; // 步 1：預覽行上方留的高度（POC G.S1）
const TREE_SIDE = 200; // 樹卡水平置中時扣掉的側欄寬
const TREE_MAX_W = 560;
const PRESS = [0.3, 0.66, 1.16, 1.3, 2.16, 2.68, 3.16]; // 游標按下的七個時間點（POC press）
const GLYPH = 'ABCDEFGHJKLMNPQRSTUVWXYZ0123456789-_';
const N_ROWS = 6; // 樹卡的列數（資料夾 2、檔案 3、「和預覽一樣」1）

const out = (x) => 1 - Math.pow(1 - x, 3); // 三次方緩出（POC stage.js:9；不是 stage-math 的 ease）

const E = {};
let geo = { ready: false };
let TEXT = { pv0: '', pv1: '', old: '', neu: '' }; // morph 的兩端：mount 時從畫面上讀一次

function pick(root, sel) {
    return root.querySelector(sel);
}

// 平移＋等比縮放的 matrix 字串（sx 同時是 sy）
function mat(k, x, y) {
    return 'matrix(' + k + ', 0, 0, ' + k + ', ' + x.toFixed(1) + ', ' + y.toFixed(1) + ')';
}

// 旋轉矩陣（spinner 轉角由 v 驅動，不用 CSS 動畫）
function rot(deg) {
    const r = (deg * Math.PI) / 180;
    const c = Math.cos(r).toFixed(4);
    const s = Math.sin(r).toFixed(4);
    return 'matrix(' + c + ', ' + s + ', ' + (-s) + ', ' + c + ', 0, 0)';
}

// 逐字從 POC：長度內插；游標前沿幾個字換成亂碼，其餘左邊是新字、右邊是舊字
function morph(from, to, p) {
    if (p <= 0) return from;
    if (p >= 1) return to;
    const len = Math.round(lerp(from.length, to.length, p));
    const edge = p * len;
    let s = '';
    for (let i = 0; i < len; i++) {
        if (i < edge - 3) s += to.charAt(i) || '';
        else if (i < edge + 1) s += GLYPH.charAt((i * 7 + Math.floor(p * 40) * 13) % GLYPH.length);
        else s += from.charAt(i) || '';
    }
    return s;
}

/* ---------- 狀態（v 的純函式；不碰 DOM、不讀上一幀） ---------- */
// 頁面捲動量：[起點鍵, 終點鍵, 內插係數]；鍵對應 layout() 量到的 geo.S
function scrollSeg(v) {
    if (v < 1.0) return ['S1', 'S1', 0];
    if (v < 1.14) return ['S1', 'S2', ease(seg(v, 1.0, 1.1))];
    if (v < 1.56) return ['S2', 'S2', 0];
    if (v < 2.2) return ['S2', 'S3', ease(seg(v, 1.56, 1.66))];
    return ['Z', 'S4', ease(seg(v, 2.8, 2.96))];
}

function stateOf(v) {
    const t = seg(v, 3.42, 3.52);
    return {
        v,
        toSearch: v >= 2.2, // 頁面切換只看進度
        srcTab: v >= 1.18, // 分頁切換
        navSearch: v >= 2.16, // 側欄「搜尋」亮起（早於頁面切換，POC 如此）
        km: out(seg(v, 0.32, 0.44)), // 步 1：片商膠囊長出
        pv: ease(seg(v, 0.34, 0.54)), // 步 1：預覽逐字變形
        dg: ease(seg(v, 1.3, 1.5)), // 步 2：JavBus 拖到最前
        lift: v > 1.28 && v < 1.52,
        ring: seg(v, 1.64, 1.72) * (1 - seg(v, 1.96, 2.02)),
        sc: scrollSeg(v),
        chipE: ease(seg(v, 2.24, 2.4)), // 步 3：檔案 chip 拖進搜尋頁
        chipO: seg(v, 2.22, 2.24) * (1 - seg(v, 2.44, 2.5)),
        drag: seg(v, 2.3, 2.36) * (1 - seg(v, 2.4, 2.46)), // 拖放提示覆蓋層（POC 以 class 切，card 定係數）
        has: v >= 2.46, // 空狀態 → 查到的結果
        covB: (1 - seg(v, 2.48, 2.56)) * 100, // 封面擦換（第一張）
        covA: (1 - seg(v, 2.7, 2.8)) * 100, // 封面擦換（換來源後的第二張）
        srcBus: v < 2.7, // 結果卡的來源名
        run: v >= 3.18 && v < 3.42, // 步 4：整理鈕三態
        done: v >= 3.42,
        spin: (v * 1440) % 360,
        treeT: t,
        rows: Array.from({ length: N_ROWS }, (_, i) => seg(v, 3.44 + i * 0.03, 3.5 + i * 0.03)),
        nm: ease(seg(v, 3.46, 3.66)), // 樹卡的檔名變形
        cta: seg(v, 3.7, 3.8),
        press: PRESS.some((p) => v >= p && v < p + 0.05),
    };
}

/* ---------- 唯一寫 DOM 的函式 ---------- */
function paint(s) {
    if (!geo.ready) return;
    cls(E.set, 'is-on', !s.toSearch);
    cls(E.sea, 'is-on', s.toSearch);
    cls(E.tabSrc, 'is-active', s.srcTab);
    cls(E.tabScr, 'is-active', !s.srcTab);
    cls(E.panSrc, 'is-on', s.srcTab);
    cls(E.panScr, 'is-on', !s.srcTab);
    cls(E.navSearch, 'is-active', s.navSearch);
    cls(E.navSet, 'is-active', !s.navSearch);

    const S = lerp(geo.S[s.sc[0]], geo.S[s.sc[1]], s.sc[2]);
    css(E.scroll, 'transform', mat(1, 0, -S)); // 純垂直平移

    // 儲存列：App 是 sticky 貼底；畫布頁面用 transform 平移、sticky 無效，所以這裡依捲動量算「貼底」的補償位移
    const nat = (s.srcTab ? geo.barSrc : geo.barScr) - S; // 自然位置（畫布內 y）
    css(E.bar, 'transform', mat(1, 0, Math.min(0, geo.FH - geo.barH - nat)));

    // 步 1：加變數 → 片商膠囊長出、預覽逐字變形
    css(E.mk, 'maxWidth', s.km < 1 ? (s.km * geo.mkW).toFixed(1) + 'px' : 'none');
    css(E.mk, 'opacity', s.km.toFixed(3));
    txt(E.pvVis, morph(TEXT.pv0, TEXT.pv1, s.pv));

    // 步 2：JavBus 與 DMM 對調（DOM 順序不變，用水平位移）；拖曳中的 JavBus 略放大
    css(E.pBus, 'transform', mat(s.lift ? 1.05 : 1, s.dg * geo.dx, 0));
    css(E.pDmm, 'transform', mat(1, s.dg * geo.dx2, 0));
    op(E.ring, s.ring);

    // 步 3：搜尋頁——空狀態 → 結果、提示字 → 番號、封面擦換、來源名
    cls(E.empty, 'is-on', !s.has);
    cls(E.res, 'is-off', !s.has);
    cls(E.siph, 'is-on', !s.has);
    cls(E.sitext, 'is-off', !s.has);
    css(E.covB, 'clipPath', 'inset(0 ' + s.covB.toFixed(1) + '% 0 0)');
    css(E.covA, 'clipPath', 'inset(0 ' + s.covA.toFixed(1) + '% 0 0)');
    txt(E.srcName, s.srcBus ? 'JavBus' : 'DMM');
    op(E.drag, s.drag);
    css(E.chip, 'transform', mat(1, lerp(geo.chip0.x, geo.chip1.x, s.chipE), lerp(geo.chip0.y, geo.chip1.y, s.chipE)));
    op(E.chip, s.chipO);

    // 步 4：單片整理鈕（待整理／進行中／完成）、樹卡浮出、檔名變形
    cls(E.scrIdle, 'is-on', !s.run && !s.done);
    cls(E.scrRun, 'is-on', s.run);
    cls(E.scrDone, 'is-on', s.done);
    css(E.spin, 'transform', rot(s.spin));
    op(E.tree, s.treeT);
    css(E.tree, 'transform', mat(1, 0, (1 - out(s.treeT)) * 10));
    E.rows.forEach((r, i) => op(r, s.rows[i]));
    txt(E.tname, morph(TEXT.old, TEXT.neu, s.nm));

    // 游標（座標是畫布內座標；0×0 錨點，左上角即尖端；按壓縮放以尖端為中心）
    const c = cursorAt(s.v, scene.cursorKeyframes);
    if (c) {
        css(E.cur, 'transform', mat(s.press ? 0.8 : 1, c.x, c.y));
        op(E.cur, c.o);
    } else {
        op(E.cur, 0);
    }

    // 結尾按鈕（畫布外）
    op(E.cta, s.cta);
    cls(E.cta, 'is-live', s.cta > 0.5);
}

export const scene = {
    mount(root) {
        E.scroll = pick(root, '.hs-app-scroll');
        E.set = pick(root, '.hs-org-set');
        E.sea = pick(root, '.hs-org-sea');
        const tabs = root.querySelectorAll('.hs-org-tab');
        E.tabSrc = tabs[0];
        E.tabScr = tabs[1];
        E.panSrc = pick(root, '.hs-org-pan--sources');
        E.panScr = pick(root, '.hs-org-pan--scraping');
        const links = root.querySelectorAll('.hs-app-navlink');
        E.navSearch = links[0];
        E.navSet = links[6];
        E.pDmm = pick(root, '.hs-org-pills .hs-org-pill');
        E.pBus = pick(root, '.hs-org-pill--bus');
        E.ring = pick(root, '.hs-org-ring');
        E.tree = pick(root, '.hs-org-tree');
        E.rows = [...E.tree.children];
        E.tname = pick(root, '.hs-org-tname');
        E.scrIdle = pick(root, '.hs-org-scr:not(.is-done):not(.is-run)');
        E.scrRun = pick(root, '.hs-org-scr.is-run');
        E.scrDone = pick(root, '.hs-org-scr.is-done');
        E.spin = pick(root, '.hs-org-spin');
        E.pvText = pick(root, '.hs-org-ptext');
        E.pvVis = pick(root, '.hs-org-pvis');
        E.tabsBar = pick(root, '.hs-org-tabs');
        E.mtTier = pick(root, '.hs-org-mt .hs-org-tier');
        E.tray = pick(root, '.hs-org-tray');
        E.mk = pick(root, '.hs-org-chipwrap');
        E.varbtn = E.mk.closest('.hs-org-fnrow').querySelector('.hs-org-varbtn');
        E.bar = pick(root, '.hs-org-savebar');
        E.save = pick(root, '.hs-org-save');
        E.empty = pick(root, '.hs-org-empty');
        E.res = pick(root, '.hs-org-res');
        E.siph = pick(root, '.hs-org-siph');
        E.sitext = pick(root, '.hs-org-sitext');
        E.covB = pick(root, '.hs-org-cov--b');
        E.covA = pick(root, '.hs-org-cov--a');
        E.srcPill = pick(root, '.hs-org-pill--res');
        E.srcName = pick(root, '.hs-org-pill--res .hs-org-pname');
        E.drag = pick(root, '.hs-app-drag');
        E.chip = pick(root, '.hs-org-fchip');
        E.cur = pick(root, '.hs-org-cur');
        E.cta = pick(root, '.hs-cta-wrap');
        TEXT = {
            pv0: pick(root, '.hs-org-ptold').textContent,
            pv1: E.pvVis.textContent,
            old: pick(root, '.hs-org-fname').textContent,
            neu: E.tname.textContent,
        };
    },

    // 量位置。座標一律換成畫布內座標＝(rect − 基準 rect) / scale；頁面座標（含主區上內距）＝文件座標。
    // 為了量位置，暫時把頁面／分頁／位移／搜尋頁狀態全部設成「量測姿勢」，量完同一輪內還原並 dropCache，
    // 所以位置與游標路徑和目前的 v 無關（任何 v 被 resize 都得到同一組 geo 與 kf）。
    layout(canvas, scale) {
        if (!E.scroll) return;
        const FH = canvas.offsetHeight;
        const LW = canvas.offsetWidth;
        const main = E.scroll.parentElement;
        const padTop = parseFloat(getComputedStyle(main).paddingTop) || 0;
        const padBottom = parseFloat(getComputedStyle(main).paddingBottom) || 0;

        const flags = [E.set, E.sea, E.panSrc, E.panScr].map((el) => el.classList.contains('is-on'));
        const tabFlags = [E.tabSrc, E.tabScr].map((el) => el.classList.contains('is-active'));
        const scrFlags = [E.scrIdle, E.scrRun, E.scrDone].map((el) => el.classList.contains('is-on'));
        const resOff = E.res.classList.contains('is-off');
        const empOn = E.empty.classList.contains('is-on');
        const prevTf = [E.scroll, E.pBus, E.pDmm, E.bar].map((el) => el.style.transform);
        const prevMkCss = E.mk.style.cssText; // 整串還原，inline style 的屬性順序才不會被打亂
        const prevSrc = E.srcName.textContent;
        const setOn = (set, src) => {
            E.set.classList.toggle('is-on', set);
            E.sea.classList.toggle('is-on', !set);
            E.panSrc.classList.toggle('is-on', src);
            E.panScr.classList.toggle('is-on', !src);
        };
        E.scroll.style.transform = 'none';
        E.pBus.style.transform = 'none';
        E.pDmm.style.transform = 'none';
        E.bar.style.transform = 'none';
        E.mk.style.maxWidth = '';

        const sr = E.scroll.getBoundingClientRect();
        const cr = canvas.getBoundingClientRect();
        const docY = (el) => padTop + (el.getBoundingClientRect().top - sr.top) / scale;
        const rel = (el) => {
            const r = el.getBoundingClientRect();
            return { x: (r.left - cr.left) / scale, y: (r.top - cr.top) / scale, w: r.width / scale, h: r.height / scale };
        };
        const maxS = (page) => Math.max(0, padTop + page.offsetHeight + padBottom - FH);

        // 步 1：整理與命名
        setOn(true, false);
        const S1 = clamp(docY(E.pvText) - PV_LEAD, 0, maxS(E.set));
        const mkW = E.mk.getBoundingClientRect().width / scale; // 片商膠囊的自然寬
        const barH = E.bar.offsetHeight;
        const bv = rel(E.varbtn);
        const sv = rel(E.save);
        const barScr = docY(E.bar);
        // 儲存列貼底：自然位置在畫布下緣之外時，上移到剛好貼住下緣（等同 App 的 sticky; bottom: 0）
        const dock1 = Math.min(0, FH - barH - (barScr - S1));

        // 步 2：刮削來源
        setOn(true, true);
        const S2 = clamp(docY(E.tabsBar) - TAB_PEEK, 0, maxS(E.set));
        const mt = rel(E.mtTier);
        const mtDocY = docY(E.mtTier);
        const S3 = Math.max(S2, Math.min(maxS(E.set), mtDocY - FH * 0.4));
        const dmm = rel(E.pDmm);
        const bus = rel(E.pBus);
        const tab0 = rel(E.tabSrc);
        const barSrc = docY(E.bar);

        // 步 3／4：搜尋頁（以「查到結果、待整理」的非空狀態量）
        setOn(false, false);
        E.res.classList.remove('is-off');
        E.empty.classList.remove('is-on');
        E.scrIdle.classList.add('is-on');
        E.scrRun.classList.remove('is-on');
        E.scrDone.classList.remove('is-on');
        E.srcName.textContent = 'JavBus'; // 游標按它的時刻（v<2.7）顯示的是 JavBus；固定用這個量，位置才與目前的 v 無關
        const trayY = docY(E.tray);
        const trayH = E.tray.offsetHeight;
        const S4 = Math.max(0, Math.min(maxS(E.sea), trayY + trayH + SEARCH_PEEK - FH));
        const pl = rel(E.srcPill);
        const sc = rel(E.scrIdle);
        const nav = rel(E.navSearch);

        // 游標與 chip（畫布內座標）
        const chipW = E.chip.offsetWidth;
        const chipH = E.chip.offsetHeight;
        const cx = LW - chipW - 40;
        const cy = FH - chipH - 30;
        const ix = LW * 0.6 - chipW / 2;
        const iy = FH * 0.42;
        const mx = LW * 0.64;
        const my = FH * 0.5;
        const bvX = bv.x + bv.w * 0.5;
        const bvY = bv.y + bv.h * 0.6 - S1;
        const svX = sv.x + sv.w * 0.5;
        const svY = sv.y + sv.h * 0.6 - S1 + dock1;
        const tabX = tab0.x + tab0.w * 0.5;
        const tabY = tab0.y + tab0.h * 0.6 - S2;
        const bx0 = bus.x + bus.w * 0.5;
        const bx1 = dmm.x + dmm.w * 0.5;
        const by = bus.y - S2 + bus.h * 0.6;
        const dy = dmm.y - S2 + dmm.h * 0.6;
        const nx = nav.x + nav.w * 0.4;
        const ny = nav.y + nav.h * 0.55;
        const px = pl.x + pl.w * 0.5;
        const py = pl.y + pl.h * 0.6;
        const sx = sc.x + sc.w * 0.5;
        const sy = sc.y + sc.h * 0.6 - S4;
        scene.cursorKeyframes = [
            [0, mx, my, 0], [0.06, mx, my, 1], [0.26, bvX, bvY, 1], [0.36, bvX, bvY, 1], [0.62, svX, svY, 1], [0.72, svX, svY, 1], [0.8, svX, svY, 0],
            [1.0, mx, my, 0], [1.04, mx, my, 1], [1.14, tabX, tabY, 1], [1.2, tabX, tabY, 1], [1.26, bx0, by, 1], [1.3, bx0, by, 1], [1.52, bx1, dy, 1], [1.6, bx1, dy, 0],
            [2.0, mx, my, 0], [2.04, mx, my, 1], [2.14, nx, ny, 1], [2.2, nx, ny, 1],
            [2.22, cx + chipW * 0.5, cy + chipH * 0.6, 0], [2.24, cx + chipW * 0.5, cy + chipH * 0.6, 1],
            [2.4, ix + chipW * 0.5, iy + chipH * 0.6, 1], [2.46, ix + chipW * 0.5, iy + chipH * 0.6, 0],
            [2.56, mx, my, 0], [2.58, mx, my, 1], [2.66, px, py, 1], [2.72, px, py, 1], [2.78, px, py, 0],
            [3.0, mx, my, 0], [3.04, mx, my, 1], [3.14, sx, sy, 1], [3.2, sx, sy, 1], [3.26, sx, sy, 0], [4, sx, sy, 0],
        ];

        geo = {
            ready: true,
            FH,
            S: { Z: 0, S1, S2, S3, S4 },
            barH,
            barScr,
            barSrc,
            mkW,
            dx: dmm.x - bus.x,
            dx2: bus.x + bus.w - dmm.w - dmm.x,
            chip0: { x: cx, y: cy },
            chip1: { x: ix, y: iy },
        };

        // 橘框：圈住 Metatube 區塊（畫布座標，步 2 的捲動量 S3 已扣掉）
        const rw = Math.min(LW - mt.x - 60, RING_MAX_W);
        css(E.ring, 'transform', mat(1, mt.x - RING_PAD_X, mtDocY - S3 - RING_PAD_Y));
        css(E.ring, 'width', rw.toFixed(1) + 'px');
        css(E.ring, 'height', RING_H + 'px');

        // 樹卡：水平置中於主區、垂直置中於視窗
        const tw = Math.min(LW - TREE_SIDE - 60, TREE_MAX_W);
        css(E.tree, 'left', ((LW - TREE_SIDE - tw) / 2 + TREE_SIDE).toFixed(1) + 'px');
        css(E.tree, 'top', Math.max(16, (FH - 250) / 2).toFixed(1) + 'px');
        css(E.tree, 'width', tw.toFixed(1) + 'px');

        // 還原（同一輪內，不留暫時狀態）
        [E.set, E.sea, E.panSrc, E.panScr].forEach((el, k) => el.classList.toggle('is-on', flags[k]));
        [E.tabSrc, E.tabScr].forEach((el, k) => el.classList.toggle('is-active', tabFlags[k]));
        [E.scrIdle, E.scrRun, E.scrDone].forEach((el, k) => el.classList.toggle('is-on', scrFlags[k]));
        E.res.classList.toggle('is-off', resOff);
        E.empty.classList.toggle('is-on', empOn);
        [E.scroll, E.pBus, E.pDmm, E.bar].forEach((el, k) => { el.style.transform = prevTf[k]; });
        E.mk.style.cssText = prevMkCss;
        E.srcName.textContent = prevSrc;
        [
            E.set, E.sea, E.panSrc, E.panScr, E.tabSrc, E.tabScr, E.scroll, E.pBus, E.pDmm, E.bar, E.mk,
            E.scrIdle, E.scrRun, E.scrDone, E.res, E.empty, E.srcName, E.ring, E.tree,
        ].forEach(dropCache);
    },

    render(v) {
        paint(stateOf(v));
    },

    cursorKeyframes: [],
};
