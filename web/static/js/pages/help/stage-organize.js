// 整理與改名的舞台 scene（TASK-191a-T8：四步終態定格畫面）。
// 介面：mount(root) 第一次成功啟動時呼叫一次；layout(canvas, scale) 量位置（畫布內座標）；
// render(v) 純函式畫面；cursorKeyframes 之後由 T9 補（此刻為空，引擎不畫游標）。
//
// 結構：render(v) ＝ paint(stateOf(stepOf(v)))。
//   stateOf(n)：只吃步驟號、回傳純資料（無 DOM 參照、不讀上一幀）→ 同一步不論從哪個方向到達，畫面相同。
//   paint(state)：唯一寫 DOM 的函式，只走 css／txt／cls／op（比對上次值才寫）；位置類用 layout() 量到的 geo。
// 畫面文字全部在 partial 由多語系輸出（本檔不呼叫翻譯函式，也不判斷主題）。
// 位移一律寫 matrix()（純垂直／水平平移），數值與公式逐字取自 poc/v4/stage.js 的 layout()。
import { clamp, stepOf } from './stage-math.js';
import { css, cls, op, dropCache } from './stage-engine.js';

const TAB_PEEK = 16; // 步 2：分頁列上緣露出的餘量（POC G.S2）
const RING_PAD_X = 12; // 橘框相對 Metatube 標題的外擴（POC mtv）
const RING_PAD_Y = 10;
const RING_H = 92;
const RING_MAX_W = 720;
const SEARCH_PEEK = 16; // 步 3／4：檔案區下緣的餘量（POC G.S4）
const PV_LEAD = 150; // 步 1：預覽行上方留的高度（POC G.S1）
const TREE_SIDE = 200; // 樹卡水平置中時扣掉的側欄寬
const TREE_MAX_W = 560;

const E = {};
let geo = { ready: false };

function pick(root, sel) {
    return root.querySelector(sel);
}

/* ---------- 狀態（步驟號的純函式；不碰 DOM、不讀上一幀） ---------- */
function stateOf(n) {
    return {
        n,
        toSearch: n >= 3, // 步 3／4 在搜尋頁
        srcTab: n === 2, // 步 2 是「刮削來源」分頁，其餘是「整理與命名」
        swapped: n >= 2, // JavBus 排到 DMM 前面
        ring: n === 2 ? 1 : 0,
        tree: n === 4 ? 1 : 0,
        done: n === 4, // 單片整理鈕：步 4 是「完成」態
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
    cls(E.navSearch, 'is-active', s.toSearch);
    cls(E.navSet, 'is-active', !s.toSearch);

    const S = s.toSearch ? geo.S4 : s.srcTab ? geo.S3 : geo.S1;
    css(E.scroll, 'transform', 'matrix(1, 0, 0, 1, 0, ' + (-S).toFixed(1) + ')'); // 純垂直平移

    // 來源膠囊：JavBus 與 DMM 對調（DOM 順序不變，用水平位移；T9 之後直接驅動這兩個值）
    css(E.pBus, 'transform', 'matrix(1, 0, 0, 1, ' + (s.swapped ? geo.dx : 0).toFixed(1) + ', 0)');
    css(E.pDmm, 'transform', 'matrix(1, 0, 0, 1, ' + (s.swapped ? geo.dx2 : 0).toFixed(1) + ', 0)');

    // 演示層
    op(E.ring, s.ring);
    op(E.tree, s.tree);

    // 單片整理鈕
    cls(E.scrIdle, 'is-on', !s.done);
    cls(E.scrDone, 'is-on', s.done);
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
        const pills = root.querySelectorAll('.hs-org-pills .hs-org-pill');
        E.pDmm = pills[0];
        E.pBus = pills[1];
        E.ring = pick(root, '.hs-org-ring');
        E.tree = pick(root, '.hs-org-tree');
        E.scrIdle = pick(root, '.hs-org-scr:not(.is-done)');
        E.scrDone = pick(root, '.hs-org-scr.is-done');
        E.pvText = pick(root, '.hs-org-ptext');
        E.tabsBar = pick(root, '.hs-org-tabs');
        E.mtTier = pick(root, '.hs-org-mt .hs-org-tier');
        E.tray = pick(root, '.hs-org-tray');
    },

    // 量位置。座標一律換成畫布內座標＝(rect − 基準 rect) / scale；頁面座標（含主區上內距）＝文件座標。
    // 為了量位置，暫時把頁面／分頁／位移全部設成「量測姿勢」，量完同一輪內還原並 dropCache，
    // 所以位置與目前的 v 無關（任何 v 被 resize 都得到同一組 geo）。
    layout(canvas, scale) {
        if (!E.scroll) return;
        const FH = canvas.offsetHeight;
        const LW = canvas.offsetWidth;
        const main = E.scroll.parentElement;
        const padTop = parseFloat(getComputedStyle(main).paddingTop) || 0;
        const padBottom = parseFloat(getComputedStyle(main).paddingBottom) || 0;

        const flags = [E.set, E.sea, E.panSrc, E.panScr].map((el) => el.classList.contains('is-on'));
        const tabFlags = [E.tabSrc, E.tabScr].map((el) => el.classList.contains('is-active'));
        const prevTf = [E.scroll, E.pBus, E.pDmm].map((el) => el.style.transform);
        const setOn = (set, src) => {
            E.set.classList.toggle('is-on', set);
            E.sea.classList.toggle('is-on', !set);
            E.panSrc.classList.toggle('is-on', src);
            E.panScr.classList.toggle('is-on', !src);
        };
        E.scroll.style.transform = 'none';
        E.pBus.style.transform = 'none';
        E.pDmm.style.transform = 'none';

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

        // 步 2：刮削來源
        setOn(true, true);
        const S2 = clamp(docY(E.tabsBar) - TAB_PEEK, 0, maxS(E.set));
        const mt = rel(E.mtTier);
        const mtDocY = docY(E.mtTier);
        const S3 = Math.max(S2, Math.min(maxS(E.set), mtDocY - FH * 0.4));
        const dmm = rel(E.pDmm);
        const bus = rel(E.pBus);

        // 步 3／4：搜尋頁
        setOn(false, false);
        const trayY = docY(E.tray);
        const trayH = E.tray.offsetHeight;
        const S4 = Math.max(0, Math.min(maxS(E.sea), trayY + trayH + SEARCH_PEEK - FH));

        geo = {
            ready: true,
            S1,
            S3,
            S4,
            dx: dmm.x - bus.x,
            dx2: bus.x + bus.w - dmm.w - dmm.x,
        };

        // 橘框：圈住 Metatube 區塊（畫布座標，步 2 的捲動量 S3 已扣掉）
        const rw = Math.min(LW - mt.x - 60, RING_MAX_W);
        css(E.ring, 'transform', 'matrix(1, 0, 0, 1, ' + (mt.x - RING_PAD_X).toFixed(1) + ', ' + (mtDocY - S3 - RING_PAD_Y).toFixed(1) + ')');
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
        [E.scroll, E.pBus, E.pDmm].forEach((el, k) => { el.style.transform = prevTf[k]; });
        [E.set, E.sea, E.panSrc, E.panScr, E.tabSrc, E.tabScr, E.scroll, E.pBus, E.pDmm, E.ring, E.tree].forEach(dropCache);
    },

    render(v) {
        paint(stateOf(stepOf(v)));
    },

    cursorKeyframes: [],
};
