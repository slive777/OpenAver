// 建立片庫的舞台 scene（TASK-191a-T6：四步定格畫面；T7 加動畫）。
// 介面：mount(root) 第一次成功啟動時呼叫一次；layout(canvas, scale) 量位置（畫布內座標）；
// render(v) 純函式畫面；cursorKeyframes 交給 cursorAt() 由 scene 自己畫游標（引擎不畫）。
//
// 結構（T7 接得上）：render(v) ＝ paint(stateOf(stepOf(v)))。
//   stateOf(n)：回傳純資料（無 DOM 參照）；T6 的值只有 0／1，T7 換成對連續 v 的函式。
//   paint(state)：唯一寫 DOM 的函式，只走 css／txt／cls／op（比對上次值才寫）。
// 全部畫面文字都在 partial 由 partial 的多語系輸出；本檔不碰字串、不判斷主題（主題差異全在 help-stage.css）。
import { stepOf, clamp } from './stage-math.js';
import { css, cls, op } from './stage-engine.js';

const N_TILES = 12;
const MISS = [1, 4, 6, 8, 11]; // 步 2 時缺封面的 5 張（POC stage.js:22）
const GRID_COLS = 6;
const GRID_GAP = 8;
const STATS_PEEK = 14; // 統計卡下緣要露出的餘量（POC G.S 公式）

const E = {};          // mount 時查好的 DOM 參照
let tiles = [];        // [{ el, cv, ph, tg }]
let geo = { S: 0, rects: [] }; // layout() 量到的捲動量與 12 張 tile 的格位（畫布內座標）

function pick(root, sel) {
    return root.querySelector(sel);
}

/* ---------- 狀態（純資料） ---------- */
const MISS_SET = new Set(MISS);
function tileStates(shown, filled) {
    return Array.from({ length: N_TILES }, (_, i) => ({
        o: shown ? 1 : 0,                                  // 顯示度
        c: filled || !MISS_SET.has(i) ? 1 : 0,             // 填色進度（缺封面的片在步 2 為 0）
    }));
}

const STATES = {
    1: { page: 'scan', scroll: 0, term: 0, stats: 0, miss: 0, log: 0, pills: 0, note: 0, bar: 1, title: 0, tiles: tileStates(false, true) },
    2: { page: 'scan', scroll: 1, term: 1, stats: 1, miss: 1, log: 1, pills: 0, note: 0, bar: 1, title: 0, tiles: tileStates(true, false) },
    3: { page: 'scan', scroll: 1, term: 1, stats: 1, miss: 0, log: 0, pills: 1, note: 1, bar: 1, title: 1, tiles: tileStates(true, true) },
    4: { page: 'show', scroll: 0, term: 0, stats: 0, miss: 0, log: 0, pills: 0, note: 0, bar: 1, title: 1, tiles: tileStates(false, true) },
};
const stateOf = (n) => STATES[n];

/* ---------- 唯一寫 DOM 的函式 ---------- */
function paint(s) {
    const scan = s.page === 'scan' ? 1 : 0;
    op(E.scan, scan);
    op(E.show, 1 - scan);
    op(E.showFoot, 1 - scan);
    cls(E.navScan, 'is-active', scan === 1);
    cls(E.navShow, 'is-active', scan === 0);
    css(E.scroll, 'transform', 'matrix(1, 0, 0, 1, 0, ' + (-geo.S * s.scroll).toFixed(1) + ')'); // 純垂直平移

    cls(E.term, 'is-shown', s.term > 0);
    op(E.term, s.term);
    cls(E.stats, 'is-shown', s.stats > 0);
    op(E.stats, s.stats);
    cls(E.miss, 'is-shown', s.miss > 0);
    op(E.miss, s.miss);
    op(E.log, s.log);
    op(E.pills, s.pills);
    op(E.note, s.note);
    css(E.bar, 'width', (s.bar * 100).toFixed(1) + '%');
    cls(E.titleDone, 'is-on', s.title === 0);
    cls(E.titleEnrich, 'is-on', s.title === 1);

    tiles.forEach((t, i) => {
        const g = geo.rects[i];
        const ts = s.tiles[i];
        if (g) {
            css(t.el, 'left', g.x.toFixed(1) + 'px');
            css(t.el, 'top', g.y.toFixed(1) + 'px');
            css(t.el, 'width', g.w.toFixed(1) + 'px');
            css(t.el, 'height', g.h.toFixed(1) + 'px');
        }
        op(t.el, ts.o);
        cls(t.el, 'is-miss', ts.c < 1);
        css(t.cv, 'clipPath', 'inset(0 ' + ((1 - ts.c) * 100).toFixed(1) + '% 0 0)');
        op(t.ph, 1 - ts.c);
        op(t.tg, ts.c);
    });
}

export const scene = {
    mount(root) {
        E.scroll = pick(root, '.hs-app-scroll');
        E.scan = pick(root, '.hs-lib-scan');
        E.show = pick(root, '.hs-lib-show');
        E.showFoot = pick(root, '.hs-lib-showfoot');
        const links = root.querySelectorAll('.hs-app-navlink');
        E.navScan = links[1];
        E.navShow = links[2];
        E.term = pick(root, '.hs-lib-term');
        E.stats = pick(root, '.hs-lib-stats');
        E.miss = pick(root, '.hs-lib-miss');
        E.log = pick(root, '.hs-lib-log');
        E.pills = pick(root, '.hs-lib-pills');
        E.note = pick(root, '.hs-lib-note');
        E.bar = pick(root, '.hs-lib-bar');
        E.grid = pick(root, '.hs-lib-grid');
        const titles = root.querySelectorAll('.hs-lib-tt');
        E.titleDone = titles[0];
        E.titleEnrich = titles[1];
        tiles = [...root.querySelectorAll('.hs-lib-tile')].map((el) => ({
            el,
            cv: pick(el, '.hs-lib-tcv'),
            ph: pick(el, '.hs-lib-tph'),
            tg: pick(el, '.hs-lib-ttag'),
        }));
    },

    // 量「頁面捲動量 S」與 12 張 tile 的格位。座標一律換成畫布內座標＝(rect − 基準 rect) / scale。
    // 為了量位置，暫時把步 2／3 才顯示的區塊全部打開，同一輪內還原成原本的 class（不留暫時狀態）。
    layout(canvas, scale) {
        if (!E.scroll) return;
        const FH = canvas.offsetHeight;
        const hidden = [E.term, E.stats, E.miss].map((el) => !el.classList.contains('is-shown'));
        [E.term, E.stats, E.miss].forEach((el) => el.classList.add('is-shown'));
        // scroll 容器與內容一起平移，rect 相減與目前捲動量無關
        const base = E.scroll.getBoundingClientRect();
        const rel = (el) => {
            const r = el.getBoundingClientRect();
            return { x: (r.left - base.left) / scale, y: (r.top - base.top) / scale, w: r.width / scale, h: r.height / scale };
        };
        const main = E.scroll.parentElement;
        const padTop = parseFloat(getComputedStyle(main).paddingTop) || 0;
        const padBottom = parseFloat(getComputedStyle(main).paddingBottom) || 0;
        const st = rel(E.stats);
        const g = rel(E.grid);
        const contentH = padTop + E.scroll.offsetHeight + padBottom;
        const S = clamp(padTop + st.y + st.h + STATS_PEEK - FH, 0, Math.max(0, contentH - FH));
        const tw = (g.w - GRID_GAP * (GRID_COLS - 1)) / GRID_COLS;
        const th = (g.h - GRID_GAP) / 2;
        const rects = Array.from({ length: N_TILES }, (_, i) => ({
            x: g.x + (i % GRID_COLS) * (tw + GRID_GAP),
            y: g.y + Math.floor(i / GRID_COLS) * (th + GRID_GAP),
            w: tw,
            h: th,
        }));
        [E.term, E.stats, E.miss].forEach((el, k) => { if (hidden[k]) el.classList.remove('is-shown'); });
        geo = { S, rects };
    },

    render(v) {
        paint(stateOf(stepOf(v)));
    },

    cursorKeyframes: [],
};
