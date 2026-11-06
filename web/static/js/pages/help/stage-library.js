// 建立片庫的舞台 scene（TASK-191a-T7：四步演出＋游標＋結尾按鈕）。
// 介面：mount(root) 第一次成功啟動時呼叫一次；layout(canvas, scale) 量位置（畫布內座標）；
// render(v) 純函式畫面；cursorKeyframes 由 layout() 算好，scene 自己用 cursorAt() 畫游標（引擎不畫）。
//
// 結構：render(v) ＝ paint(stateOf(v))。
//   stateOf(v)：只吃 v、回傳純資料（無 DOM 參照、不讀上一幀）→ 同一個 v 不論從哪個方向到達，畫面相同。
//   paint(state)：唯一寫 DOM 的函式，只走 css／txt／cls／op／attr（比對上次值才寫）；位置類用 layout() 量到的 geo。
// 時間表（seg／ease／out 的邊界與係數）逐字取自 poc/v3/stage.js 的 render／renderCursor／layout。
// 全部畫面文字都在 partial 由多語系輸出並列切換；本檔只用 txt() 寫 ASCII（番號、來源品牌名、數字），不判斷主題。
import { clamp, seg, ease, lerp, cursorAt } from './stage-math.js';
import { css, cls, op, txt, dropCache } from './stage-engine.js';

const N_TILES = 12;
const MISS = [1, 4, 6, 8, 11]; // 步 3 補完時缺封面的 5 張（POC stage.js:22）
const SRC = [0, 1, 0, 3, 2]; // 這 5 張各由第幾個來源補上
const SOURCES = ['DMM', 'JavBus', 'Jav321', 'JavDB', 'D2Pass', 'HEYZO', 'FC2', 'AVSOX'];
const SLOT = 0.1; // 補完每張佔的 v 長度
const GRID_COLS = 6;
const GRID_GAP = 8;
const STATS_PEEK = 14; // 統計卡下緣要露出的餘量（POC G.S 公式）
const NOTE_PEEK = 12; // step 3: headroom above the unchanged-note mark = mark outset 4px (--hs-mark-pad in help-stage.css) + 8px
const PRESS = [1.18, 2.16, 3.16]; // 游標按下的三個時間點（POC press）
const N_LINES = 14; // 紀錄：找到 1 行＋進度 12 行＋完成 1 行
// mark hosts, same order as the mk array of stateOf (= DOM order: note inside the log area, missing row inside the stats card)
const MARKS = ['.hs-lib-notefit', '.hs-lib-miss'];

const out = (x) => 1 - Math.pow(1 - x, 3); // 三次方緩出（POC stage.js:9；不是 stage-math 的 ease）

const TILE_M = Array.from({ length: N_TILES }, (_, i) => MISS.indexOf(i)); // 缺封面的序位，-1＝本來就有封面
const TILE_O = (() => { // 有封面的片之中的序位（決定填色先後）
    let o = 0;
    return TILE_M.map((m) => (m < 0 ? o++ : -1));
})();

const E = {};          // mount 時查好的 DOM 參照
let tiles = [];        // [{ el, fn, cd, ph, cv, tg, act, mark, rs }]
let beams = [];        // [{ p, c, L }]
let geo = { ready: false };
// layout() 量到的：S 頁面捲動量；G／R／W 12 張 tile 的 6×2 格位／兩欄列／牆卡位；c 格區中心；chip0／chip1 chip 起訖

function pick(root, sel) {
    return root.querySelector(sel);
}

// SVG 屬性寫入快取（同 css／txt／cls：比對上次值才寫）
function attr(el, name, val) {
    const c = el._hsa || (el._hsa = {});
    if (c[name] === val) return;
    c[name] = val;
    el.setAttribute(name, val);
}

/* ---------- 狀態（v 的純函式；不碰 DOM、不讀上一幀） ---------- */
function tileState(v, i) {
    const m = TILE_M[i];
    const o = TILE_O[i];
    const c = m < 0
        ? seg(v, 1.66 + o * 0.016, 1.76 + o * 0.016)
        : seg(v, 2.2 + m * SLOT + 0.08, 2.2 + m * SLOT + 0.1);
    const sp = out(seg(v, 1.3 + i * 0.008, 1.4 + i * 0.008));
    return {
        sp,                                                        // 從中心長出來
        m1: ease(seg(v, 1.52 + i * 0.006, 1.66 + i * 0.006)),      // 兩欄列 → 6×2 格
        m2: ease(seg(v, 3.2 + i * 0.01, 3.5 + i * 0.01)),          // 格 → 牆卡
        hl: seg(v, 1.4 + i * 0.008, 1.46 + i * 0.008),             // 檔名中的番號高亮
        fn: 1 - seg(v, 1.52, 1.6),                                 // 檔名條
        cd: seg(v, 1.54 + i * 0.006, 1.64 + i * 0.006),            // 封面卡
        c,                                                         // 封面填色進度
        miss: m >= 0 && c < 1,
        tg: c * (1 - seg(v, 3.2, 3.3)),
        a: seg(v, 3.4, 3.55),                                      // 頁腳演員（還要看卡寬，見 paint）
        o: sp * (1 - seg(v, 3.58, 3.68)),
    };
}

function pillLit(v, k) {
    let lit = 0;
    SRC.forEach((hit, j) => {
        const s = 2.2 + j * SLOT + k * 0.008;
        lit = Math.max(lit, seg(v, s, s + 0.004) * (1 - seg(v, s + 0.012, s + 0.016)));
        if (k === hit) {
            const e = 2.2 + j * SLOT + 0.056;
            lit = Math.max(lit, seg(v, e, e + 0.004) * (1 - seg(v, e + 0.03, e + 0.04)));
        }
    });
    return lit;
}

function beamState(v, j) {
    const s = 2.2 + j * SLOT + 0.056;
    const k = ease(seg(v, s, s + 0.03));
    const o = k > 0 ? 1 - seg(v, s + 0.03, s + 0.042) : 0;
    return { k, p: o * 0.85, c: o * (k < 1 ? 1 : 0) };
}

function stateOf(v) {
    const upto = Math.floor(12 * seg(v, 1.36, 1.62));
    const enriching = v >= 2.18 && v < 2.72;
    const nowM = clamp(Math.floor((v - 2.2) / SLOT), 0, 4);
    const hit = v >= 2.2 + nowM * SLOT + 0.056;
    const tl = Array.from({ length: N_TILES }, (_, i) => tileState(v, i));
    const filled = tl.reduce((n, t, i) => n + (TILE_M[i] >= 0 && t.c >= 1 ? 1 : 0), 0);
    const enrichSeg = seg(v, 2.18, 2.72);
    return {
        v,
        // 第 1 步：拖進來
        chipE: ease(seg(v, 0.06, 0.3)),
        chipO: 1 - seg(v, 0.36, 0.46),
        drag: seg(v, 0.14, 0.2) * (1 - seg(v, 0.38, 0.44)),
        empty: v < 0.38,
        // 第 2 步：更新片庫
        gen: v >= 1.2 && v < 1.8,
        term: v >= 1.2 && v < 3.3,
        stats: v >= 1.78 && v < 3.3,
        miss: v >= 1.8 && v < 2.76,
        title: v < 1.3 ? 0 : v < 1.68 ? 1 : v < 1.8 ? 2 : v < 2.18 ? 3 : enriching ? 4 : 5,
        bar: v < 2.18 ? seg(v, 1.3, 1.78) : enrichSeg,
        scroll: ease(seg(v, 1.26, 1.42)) * (1 - ease(seg(v, 3.18, 3.3))),
        found: v >= 1.32 && v < 1.66,
        upto,
        done: v >= 1.66,
        logO: 1 - seg(v, 2.14, 2.2),
        // 第 3 步：一鍵補完
        enriching,
        cardO: seg(v, 2.18, 2.22) * (1 - seg(v, 2.68, 2.72)),
        noteO: seg(v, 2.74, 2.82),
        noteS: ease(seg(v, 2.72, 2.8)), // page scroll eases from S to Snote while the note fades in
        mk: [ // marks: the unchanged note (step 3), the missing-data row (step 2)
            seg(v, 2.78, 2.83) * (1 - seg(v, 3.08, 3.14)),
            seg(v, 1.8, 1.84) * (1 - seg(v, 2.06, 2.12)),
        ],
        // 進度卡淡出（v≥2.72）後文字回到第一張：看不見，但步 3 定格時卡片文字與 T6 終態一致
        showM: v >= 2.72 ? 0 : nowM,
        hit,
        filled,
        pillsO: seg(v, 2.04, 2.14) * (1 - seg(v, 3.2, 3.26)),
        pills: Array.from({ length: SOURCES.length }, (_, k) => pillLit(v, k)),
        beams: MISS.map((_, j) => beamState(v, j)),
        tiles: tl,
        // 第 4 步：點瀏覽 → 換頁
        navShow: v >= 3.18,
        scanO: 1 - seg(v, 3.18, 3.3),
        showO: seg(v, 3.3, 3.46),
        cta: seg(v, 3.66, 3.76),
        press: PRESS.some((p) => v >= p && v < p + 0.05),
        spin: (v * 1440) % 360,
    };
}

/* ---------- 唯一寫 DOM 的函式 ---------- */
function paintTiles(s) {
    tiles.forEach((t, i) => {
        const ts = s.tiles[i];
        const r = geo.R[i];
        const g = geo.G[i];
        const w = geo.W[i];
        let x = lerp(geo.c.x - r.w / 2, r.x, ts.sp);
        let y = lerp(geo.c.y - r.h / 2, r.y, ts.sp);
        let tw = r.w;
        let th = r.h;
        x = lerp(x, g.x, ts.m1);
        y = lerp(y, g.y, ts.m1);
        tw = lerp(tw, g.w, ts.m1);
        th = lerp(th, g.h, ts.m1);
        // 飛向牆：牆座標是 scroll 原點座標，這時頁面捲動量已回到 0
        x = lerp(x, w.x, ts.m2);
        y = lerp(y, w.y, ts.m2);
        tw = lerp(tw, w.w, ts.m2);
        th = lerp(th, w.h, ts.m2);
        css(t.el, 'transform', 'translate(' + x.toFixed(1) + 'px, ' + y.toFixed(1) + 'px)');
        css(t.el, 'width', tw.toFixed(1) + 'px');
        css(t.el, 'height', th.toFixed(1) + 'px');
        op(t.el, ts.o);
        css(t.mark, '--hs-hl', ts.hl.toFixed(3));
        t.rs.forEach((el) => css(el, 'opacity', (1 - ts.hl * 0.5).toFixed(3)));
        op(t.fn, ts.fn);
        op(t.cd, ts.cd);
        css(t.cv, 'clipPath', 'inset(0 ' + ((1 - ts.c) * 100).toFixed(1) + '% 0 0)');
        op(t.ph, 1 - ts.c);
        op(t.tg, ts.tg);
        cls(t.el, 'is-miss', ts.miss);
        op(t.act, tw > 150 ? ts.a : 0);
    });
}

function paintBeams(s) {
    beams.forEach((b, j) => {
        const bs = s.beams[j];
        css(b.p, 'strokeDashoffset', (1 - bs.k).toFixed(3));
        op(b.p, bs.p);
        const q = b.L > 0 ? b.p.getPointAtLength(b.L * bs.k) : { x: 0, y: 0 };
        attr(b.c, 'cx', q.x.toFixed(1));
        attr(b.c, 'cy', q.y.toFixed(1));
        op(b.c, bs.c);
    });
}

function paintLog(s) {
    E.lines.forEach((el, idx) => {
        let on;
        if (idx === 0) on = s.found;
        else if (idx === N_LINES - 1) on = s.done;
        else on = idx > s.upto - 3 && idx <= s.upto;
        cls(el, 'hs-lib-logline', on);
    });
    op(E.log, s.logO);
}

function paintDemo(s) {
    // 資料夾 chip：從右下角拖進資料夾區
    css(E.chip, 'transform', 'translate(' + lerp(geo.chip0.x, geo.chip1.x, s.chipE).toFixed(1) + 'px, ' + lerp(geo.chip0.y, geo.chip1.y, s.chipE).toFixed(1) + 'px)');
    op(E.chip, s.chipO);
    op(E.drag, s.drag);
    // 游標（座標是畫布內座標；0×0 錨點，左上角即尖端）
    const c = cursorAt(s.v, scene.cursorKeyframes);
    if (c) {
        css(E.cur, 'transform', 'translate(' + c.x.toFixed(1) + 'px, ' + c.y.toFixed(1) + 'px)' + (s.press ? ' scale(.8)' : ''));
        op(E.cur, c.o);
    } else {
        op(E.cur, 0);
    }
    // 結尾按鈕（畫布外）
    op(E.cta, s.cta);
    cls(E.cta, 'is-live', s.cta > 0.5);
}

function paint(s) {
    if (!geo.ready) return;
    // 兩層頁面交接
    op(E.scan, s.scanO);
    op(E.show, s.showO);
    op(E.showFoot, s.showO);
    cls(E.navScan, 'is-active', !s.navShow);
    cls(E.navShow, 'is-active', s.navShow);
    css(E.scroll, 'transform', 'matrix(1, 0, 0, 1, 0, ' + (-lerp(geo.S, geo.Snote, s.noteS) * s.scroll).toFixed(1) + ')'); // 純垂直平移

    // 第 1 步
    cls(E.folderlist, 'is-empty', s.empty);

    // 第 2 步：按鈕、進度區、統計
    cls(E.btnIdle, 'is-on', !s.gen);
    cls(E.btnLoad, 'is-on', s.gen);
    cls(E.term, 'is-shown', s.term);
    op(E.term, 1);
    cls(E.stats, 'is-shown', s.stats);
    op(E.stats, 1);
    cls(E.miss, 'is-shown', s.miss);
    op(E.miss, 1);
    E.titles.forEach((el, i) => cls(el, 'is-on', i === s.title));
    css(E.bar, 'width', (s.bar * 100).toFixed(1) + '%');
    paintLog(s);

    // 第 3 步：一鍵補完
    cls(E.enIdle, 'is-on', !s.enriching);
    cls(E.enLoad, 'is-on', s.enriching);
    op(E.card, s.cardO);
    op(E.note, s.noteO);
    E.marks.forEach((el, i) => css(el, '--hs-mark', s.mk[i].toFixed(3)));
    txt(E.cNum, 'DEMO-' + (101 + MISS[s.showM]));
    txt(E.cSrc, SOURCES[SRC[s.showM]]);
    op(E.cSrc, s.hit ? 1 : 0);
    op(E.cStat, s.hit ? 0 : 1);
    txt(E.missNum, String(MISS.length - s.filled));
    op(E.pills, s.pillsO);
    E.pillEls.forEach((el, k) => {
        css(el, '--hs-lit', s.pills[k].toFixed(3));
        cls(el, 'is-on', s.pills[k] > 0.5);
    });
    E.spins.forEach((el) => css(el, 'transform', 'rotate(' + s.spin.toFixed(1) + 'deg)'));

    paintTiles(s);
    paintBeams(s);
    paintDemo(s);
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
        E.folderlist = pick(root, '.hs-lib-folderlist');
        E.btnhero = pick(root, '.hs-lib-btnhero');
        E.enrichbtn = pick(root, '.hs-lib-enrichbtn');
        const labs = root.querySelectorAll('.hs-lib-lab'); // 順序：更新片庫 idle／loading、一鍵補完 idle／loading
        E.btnIdle = labs[0];
        E.btnLoad = labs[1];
        E.enIdle = labs[2];
        E.enLoad = labs[3];
        E.spins = [...root.querySelectorAll('.hs-lib-spin')];
        E.term = pick(root, '.hs-lib-term');
        E.stats = pick(root, '.hs-lib-stats');
        E.miss = pick(root, '.hs-lib-miss');
        E.log = pick(root, '.hs-lib-log');
        E.lines = [...root.querySelectorAll('.hs-lib-ll')];
        E.pills = pick(root, '.hs-lib-pills');
        E.pillEls = [...root.querySelectorAll('.hs-lib-pill')];
        E.note = pick(root, '.hs-lib-note');
        E.marks = MARKS.map((sel) => pick(root, sel));
        E.bar = pick(root, '.hs-lib-bar');
        E.grid = pick(root, '.hs-lib-grid');
        E.titles = [...root.querySelectorAll('.hs-lib-tt')];
        E.card = pick(root, '.hs-lib-enrich');
        E.cNum = pick(root, '.hs-lib-enrich-num');
        E.cSrc = pick(root, '.hs-lib-enrich-src');
        E.cStat = pick(root, '.hs-lib-enrich-status');
        E.missNum = pick(root, '.hs-lib-missnum');
        E.walls = [...root.querySelectorAll('.hs-lib-wcard')];
        E.chip = pick(root, '.hs-lib-chip');
        E.cur = pick(root, '.hs-lib-cur');
        E.drag = pick(root, '.hs-app-drag');
        E.cta = pick(root, '.hs-cta-wrap');
        tiles = [...root.querySelectorAll('.hs-lib-tile')].map((el) => ({
            el,
            fn: pick(el, '.hs-lib-tfn'),
            mark: pick(el, '.hs-lib-tmark'),
            rs: [...pick(el, '.hs-lib-tfn').children].filter((c) => !c.classList.contains('hs-lib-tmark')),
            cd: pick(el, '.hs-lib-tcard'),
            cv: pick(el, '.hs-lib-tcv'),
            ph: pick(el, '.hs-lib-tph'),
            tg: pick(el, '.hs-lib-ttag'),
            act: pick(el, '.hs-lib-tact'),
        }));
        const bp = [...root.querySelectorAll('.hs-lib-beams path')];
        const bc = [...root.querySelectorAll('.hs-lib-beams circle')];
        beams = bp.map((p, j) => ({ p, c: bc[j], L: 0 }));
    },

    // 量位置。座標一律換成畫布內座標＝(rect − 基準 rect) / scale：
    //   scroll 原點座標（tile、beams、牆卡；基準＝.hs-app-scroll）與畫布座標（chip、游標；基準＝.hs-canvas）。
    // 為了量位置，暫時把 scroll 平移清成 0、步 2／3 才顯示的區塊全部打開、空狀態關掉、按鈕切 idle 標籤，
    // 量完同一輪內還原並 dropCache，所以游標路徑與 v 無關（任何 v 被 resize 都得到同一組 kf）。
    layout(canvas, scale) {
        if (!E.scroll) return;
        const FH = canvas.offsetHeight;
        const LW = canvas.offsetWidth;
        const shown = [E.term, E.stats, E.miss];
        const hidden = shown.map((el) => !el.classList.contains('is-shown'));
        const wasEmpty = E.folderlist.classList.contains('is-empty');
        const labs = [E.btnIdle, E.btnLoad, E.enIdle, E.enLoad];
        const labOn = labs.map((el) => el.classList.contains('is-on'));
        const prevTf = E.scroll.style.transform;
        shown.forEach((el) => el.classList.add('is-shown'));
        E.folderlist.classList.remove('is-empty');
        labs.forEach((el, k) => el.classList.toggle('is-on', k % 2 === 0));
        E.scroll.style.transform = 'none';

        const cr = canvas.getBoundingClientRect();
        const sr = E.scroll.getBoundingClientRect();
        const relC = (el) => {
            const r = el.getBoundingClientRect();
            return { x: (r.left - cr.left) / scale, y: (r.top - cr.top) / scale, w: r.width / scale, h: r.height / scale };
        };
        const relS = (el) => {
            const r = el.getBoundingClientRect();
            return { x: (r.left - sr.left) / scale, y: (r.top - sr.top) / scale, w: r.width / scale, h: r.height / scale };
        };

        // 頁面捲動量 S
        const main = E.scroll.parentElement;
        const padTop = parseFloat(getComputedStyle(main).paddingTop) || 0;
        const padBottom = parseFloat(getComputedStyle(main).paddingBottom) || 0;
        const st = relS(E.stats);
        const g = relS(E.grid);
        const contentH = padTop + E.scroll.offsetHeight + padBottom;
        const S = clamp(padTop + st.y + st.h + STATS_PEEK - FH, 0, Math.max(0, contentH - FH));
        const Snote = clamp(padTop + relS(E.marks[0]).y - NOTE_PEEK, 0, S); // short canvas: scroll back up so the note mark stays on screen

        // 12 張 tile 的三組格位與牆卡位
        const tw = (g.w - GRID_GAP * (GRID_COLS - 1)) / GRID_COLS;
        const th = (g.h - GRID_GAP) / 2;
        const G = Array.from({ length: N_TILES }, (_, i) => ({
            x: g.x + (i % GRID_COLS) * (tw + GRID_GAP),
            y: g.y + Math.floor(i / GRID_COLS) * (th + GRID_GAP),
            w: tw,
            h: th,
        }));
        const rw = (g.w - 10) / 2;
        const rh = (g.h - 5 * 4) / 6;
        const R = Array.from({ length: N_TILES }, (_, i) => ({
            x: g.x + (i % 2) * (rw + 10),
            y: g.y + Math.floor(i / 2) * (rh + 4),
            w: rw,
            h: rh,
        }));
        const W = E.walls.map(relS);

        // beams：來源膠囊底中心 → 缺封面 tile 中心
        beams.forEach((b, j) => {
            const p = relS(E.pillEls[SRC[j]]);
            const t = G[MISS[j]];
            const x0 = p.x + p.w / 2;
            const y0 = p.y + p.h;
            const x1 = t.x + t.w / 2;
            const y1 = t.y + t.h / 2;
            b.p.setAttribute('d', 'M' + x0.toFixed(2) + ' ' + y0.toFixed(2) + ' C' + x0.toFixed(2) + ' ' + (y0 + 30).toFixed(2) + ',' + x1.toFixed(2) + ' ' + (y1 - 30).toFixed(2) + ',' + x1.toFixed(2) + ' ' + y1.toFixed(2));
            b.L = b.p.getTotalLength();
        });

        // 游標路徑（畫布內座標）與按壓點
        const chipW = E.chip.offsetWidth;
        const chipH = E.chip.offsetHeight;
        const cx = LW - chipW - 70;
        const cy = FH - chipH - 40;
        const over = relC(E.folderlist);
        const ix = over.x + over.w / 2 - chipW / 2;
        const iy = over.y + Math.max(0, over.h / 2 - chipH / 2);
        const btn = relC(E.btnhero);
        const en = relC(E.enrichbtn);
        const nav = relC(E.navShow);
        const bx = btn.x + btn.w * 0.6;
        const by = btn.y + btn.h * 0.6;
        const ex = en.x + en.w * 0.55;
        const ey = en.y + en.h * 0.6 - S;
        const nx = nav.x + nav.w * 0.4;
        const ny = nav.y + nav.h * 0.55;
        const mx = LW * 0.62;
        const my = FH * 0.5;
        scene.cursorKeyframes = [
            [0, cx + chipW * 0.5, cy + chipH * 0.6, 1], [0.06, cx + chipW * 0.5, cy + chipH * 0.6, 1],
            [0.3, ix + chipW * 0.5, iy + chipH * 0.6, 1], [0.4, ix + chipW * 0.5, iy + chipH * 0.6, 1], [0.5, ix + chipW * 0.5, iy + chipH * 0.6, 0],
            [0.96, mx, my, 0], [1.02, mx, my, 1], [1.16, bx, by, 1], [1.24, bx, by, 1], [1.32, bx, by, 0],
            [1.94, mx, my, 0], [2.0, mx, my, 1], [2.14, ex, ey, 1], [2.22, ex, ey, 1], [2.3, ex, ey, 0],
            [2.94, mx, my, 0], [3.0, mx, my, 1], [3.14, nx, ny, 1], [3.24, nx, ny, 1], [3.32, nx, ny, 0], [4, nx, ny, 0],
        ];
        geo = { ready: true, S, Snote, G, R, W, c: { x: g.x + g.w / 2, y: g.y + g.h / 2 }, chip0: { x: cx, y: cy }, chip1: { x: ix, y: iy } };

        // 還原（同一輪內，不留暫時狀態）
        shown.forEach((el, k) => { if (hidden[k]) el.classList.remove('is-shown'); });
        if (wasEmpty) E.folderlist.classList.add('is-empty');
        labs.forEach((el, k) => el.classList.toggle('is-on', labOn[k]));
        E.scroll.style.transform = prevTf;
        [...shown, E.folderlist, E.scroll, ...labs].forEach(dropCache);
    },

    render(v) {
        paint(stateOf(v));
    },

    cursorKeyframes: [],
};
