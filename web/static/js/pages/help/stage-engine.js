/**
 * stage-engine.js — 說明頁舞台引擎（TASK-191a-T5，CD-191a-2／-5／-6／-7）
 *
 * 普通 ES module 控制器，不是 Alpine 元件；舞台 markup 沒有任何 Alpine 指令。
 * 畫面是「捲動位置」的純函式：scroll → v（0–4）→ scene.render(v)；來源是 poc/v3/stage.js 的下半段。
 * 模式切換的單一真相在 help-stage.css 的媒體查詢；這裡只看畫布有沒有版面（activate 與環境翻轉時各判斷一次）。
 * 模組頂層不碰 window／document（FE-GUARD-11）。
 *
 * 兩層監聽：
 *   環境監聽（activate 註冊，deactivate 拆）：matchMedia 兩個條件的 change＋window resize，翻轉時重新判斷。
 *   scroll 機制（畫布有版面時才有）：scroll／wheel／touchstart／keydown／按鈕與圓點 click、rAF、glide。
 *   非作用分頁、窄螢幕、減少動態下不註冊 scroll 機制、不排 rAF。
 */
import { N_STEPS, HOLD, clamp, seg, ease, lerp, progressOf, stepPxOf, stepOf, stepForward, stepBack } from './stage-math.js';

const DESIGN_W = 1100;
// 與 help-stage.css 舞台模式的 @media 逐字相同
const MQ_WIDE = '(min-width: 1024px)';
const MQ_MOTION = '(prefers-reduced-motion: no-preference)';

/* ---------- 寫入快取：比對上次值才寫 DOM（scene 也用） ---------- */
export function css(el, prop, val) {
    const c = el._hsc || (el._hsc = {});
    if (c[prop] === val) return;
    c[prop] = val;
    if (prop.charAt(0) === '-') el.style.setProperty(prop, val);
    else el.style[prop] = val;
}
export function txt(el, s) {
    if (el._hst === s) return;
    el._hst = s;
    el.textContent = s;
}
export function cls(el, name, on) {
    const c = el._hsk || (el._hsk = {});
    if (c[name] === on) return;
    c[name] = on;
    el.classList.toggle(name, on);
}
export function op(el, v) {
    const x = clamp(v, 0, 1);
    css(el, 'opacity', x.toFixed(3));
    css(el, 'visibility', x < 0.004 ? 'hidden' : 'visible');
}
// scene.layout() 手動改過元素的 style／文字後呼叫，否則下一幀以為值沒變而不寫
export function dropCache(el) {
    el._hsc = null;
    el._hst = undefined;
    el._hsk = null;
}

/* ---------- 控制器 ---------- */
export function createStage(root, scene) {
    const q = (s) => root.querySelector(s);
    const track = q('.hs-track');
    const pin = q('.hs-pin');
    const stageEl = q('.hs-stage');
    const canvas = q('.hs-canvas');
    const hint = q('.hs-hint');
    const count = q('.hs-count');
    const prevBtn = q('[data-hs-prev]');
    const nextBtn = q('[data-hs-next]');
    const dots = [...root.querySelectorAll('[data-hs-dot]')];
    const caps = [...root.querySelectorAll('.hs-step')];

    let active = false;   // activate() 後、deactivate() 前
    let mounted = false;  // scene.mount 只在第一次成功啟動時呼叫
    let envAc = null;     // 環境監聽的 AbortController
    let envRaf = 0;
    let ac = null;        // scroll 機制的 AbortController（所有 scroll 機制監聽共用其 signal）
    let ro = null;        // 舞台自身寬度的 ResizeObserver（側欄收合展開時視窗沒變、舞台寬度會變）
    let roW = 0;
    let cur = 0;
    let goal = 0;
    let running = false;
    let raf = 0;
    let shown = 0;
    let glideId = 0;
    let glideRaf = 0;
    let glideStep = 0;
    let glideUntil = 0;

    const hasLayout = () => canvas.getClientRects().length > 0 && canvas.offsetWidth > 0;

    function metrics() {
        const r = track.getBoundingClientRect();
        return { top: r.top, h: r.height, pinH: pin.getBoundingClientRect().height, gap: parseFloat(getComputedStyle(pin).top) || 0 };
    }
    let lastM = null; // 最近一次量到的 track 位置（含當時的 scrollY），給 resize 在 scroll 事件之前推算進度
    function readGoal() {
        const m = metrics();
        lastM = { m, y: window.scrollY };
        return progressOf(m);
    }
    // 用「現在的捲動位置」配上 resize 前量到的版面算進度；不用 cur（動畫還沒追上時會把畫面拉回舊的一步）
    function goalFromScroll() {
        if (!lastM) return readGoal();
        return progressOf({ ...lastM.m, top: lastM.m.top + lastM.y - window.scrollY });
    }

    // 畫布設計寬 1100、高 = 舞台高 / scale；scene 量位置一律換成畫布內座標
    function fit() {
        const scale = stageEl.clientWidth / DESIGN_W;
        css(canvas, 'height', (stageEl.clientHeight / scale).toFixed(2) + 'px');
        css(canvas, 'transform', 'scale(' + scale.toFixed(5) + ')');
        scene.layout(canvas, scale);
    }

    function draw(v) {
        scene.render(v);
        css(canvas, '--hs-v', v.toFixed(3)); // e2e 的「一組畫面量」探針（引擎統一寫，scene 不用寫）
        op(hint, 1 - seg(v, 0, 0.05));
        const n = stepOf(v);
        if (n === shown) return;
        shown = n;
        caps.forEach((c, i) => cls(c, 'is-on', i === n - 1));
        dots.forEach((b, i) => {
            if (i === n - 1) b.setAttribute('aria-current', 'step');
            else b.removeAttribute('aria-current');
        });
        txt(count, n + ' / ' + N_STEPS);
        prevBtn.disabled = n === 1;
        nextBtn.disabled = n === N_STEPS;
    }

    function frameTick() {
        raf = 0;
        cur += (goal - cur) * 0.2;
        if (Math.abs(goal - cur) < 0.0007) cur = goal;
        draw(cur);
        if (cur !== goal) raf = requestAnimationFrame(frameTick);
        else running = false;
    }
    function kick() {
        goal = readGoal();
        if (running) return;
        running = true;
        raf = requestAnimationFrame(frameTick);
    }

    /* ----- glide：自己算的 rAF window.scrollTo（CD-191a-9，非 GSAP、非 CSS transition） ----- */
    function stopGlide() {
        glideId++;
        glideUntil = 0;
        cancelAnimationFrame(glideRaf);
    }
    function yOf(v) {
        const m = metrics();
        return window.scrollY + m.top - m.gap + v * stepPxOf(m) + 1;
    }
    function glideTo(y) {
        const max = document.documentElement.scrollHeight - window.innerHeight;
        const y1 = clamp(y, 0, Math.max(0, max));
        const id = ++glideId;
        const y0 = window.scrollY;
        const t0 = performance.now();
        const dur = clamp(Math.abs(y1 - y0) * 0.9, 500, 1100);
        const f = (now) => {
            if (id !== glideId) return;
            const k = seg(now, t0, t0 + dur);
            window.scrollTo({ top: lerp(y0, y1, ease(k)), behavior: 'instant' });
            if (k < 1) glideRaf = requestAnimationFrame(f);
        };
        f(t0);
    }
    function goStep(n) {
        glideStep = n;
        glideUntil = performance.now() + 1100;
        glideTo(yOf(n - 1 + HOLD));
    }
    const glideState = () => ({ active: performance.now() < glideUntil, step: glideStep });

    function onKeydown(e) {
        if (e.altKey || e.ctrlKey || e.metaKey) return;
        const space = e.key === ' ';
        const tg = e.target;
        if (space && tg && tg.closest && tg.closest('button, a, summary, input')) return;
        if (!space && e.key !== 'PageDown' && e.key !== 'PageUp') return;
        const m = metrics();
        const pinned = m.top <= m.gap + 1 && m.top + m.h - m.pinH > m.gap - 1;
        if (!pinned) return; // 未釘住：瀏覽器原生行為
        const back = e.key === 'PageUp' || (space && e.shiftKey);
        const n = back ? stepBack(readGoal(), glideState()) : stepForward(readGoal(), glideState());
        if (n < 1 || n > N_STEPS) return;
        e.preventDefault();
        goStep(n);
    }

    /* ----- resize 後停在同一步（POC keepAt） ----- */
    function keepAt(k) {
        fit();
        if (k > 0 && k < N_STEPS) {
            stopGlide();
            window.scrollTo({ top: yOf(k) - 1, behavior: 'instant' });
            cur = goal = k;
        } else {
            cur = goal = readGoal();
        }
        shown = 0;
        draw(cur);
    }

    /* ----- scroll 機制的啟停 ----- */
    function startMachinery() {
        if (!mounted) { scene.mount(root); mounted = true; }
        ac = new AbortController();
        const signal = ac.signal;
        fit();
        cur = goal = readGoal();
        shown = 0;
        draw(cur);
        cls(root, 'is-ready', true); // 第一幀畫完才顯示畫布內容（CSS 以此類別解除隱藏），不閃未 render 的 markup
        window.addEventListener('scroll', kick, { passive: true, signal });
        window.addEventListener('wheel', stopGlide, { passive: true, signal });
        window.addEventListener('touchstart', stopGlide, { passive: true, signal });
        window.addEventListener('keydown', onKeydown, { signal });
        prevBtn.addEventListener('click', () => {
            const n = stepBack(readGoal(), glideState());
            if (n >= 1) goStep(n);
        }, { signal });
        nextBtn.addEventListener('click', () => {
            const n = stepForward(readGoal(), glideState());
            if (n <= N_STEPS) goStep(n);
        }, { signal });
        dots.forEach((b, i) => b.addEventListener('click', () => goStep(i + 1), { signal }));
        // 舞台寬度變（☰ 切側欄：.main-content 的 margin-left 有 0.2s transition，逐幀都會觸發）
        // → 與 window resize 同一條 reflow 路徑（rAF 去抖，保持步數），最後一次落在最終寬度
        roW = stageEl.clientWidth;
        ro = new ResizeObserver(() => {
            const w = stageEl.clientWidth;
            if (w === roW) return; // observe 起始的第一次回呼、或只有高度變
            roW = w;
            reflow();
        });
        ro.observe(stageEl);
    }
    function stopMachinery() {
        if (!ac) return;
        ac.abort();
        ac = null;
        ro.disconnect();
        ro = null;
        cancelAnimationFrame(raf);
        cancelAnimationFrame(glideRaf);
        raf = glideRaf = 0;
        running = false;
        glideId++;
        glideUntil = 0;
    }

    /* ----- 環境翻轉：只在翻轉那一刻重新判斷，不輪詢 ----- */
    function syncEnv() {
        envRaf = 0;
        if (!active) return;
        const ok = hasLayout();
        if (ok && !ac) startMachinery();
        else if (!ok && ac) stopMachinery();
        else if (ok && ac) keepAt(goalFromScroll());
    }
    function reflow() {
        cancelAnimationFrame(envRaf);
        envRaf = requestAnimationFrame(syncEnv);
    }

    return {
        activate() {
            if (active) return;
            active = true;
            envAc = new AbortController();
            const signal = envAc.signal;
            matchMedia(MQ_WIDE).addEventListener('change', reflow, { signal });
            matchMedia(MQ_MOTION).addEventListener('change', reflow, { signal });
            window.addEventListener('resize', reflow, { signal });
            syncEnv();
        },
        deactivate() {
            if (!active) return;
            active = false;
            envAc.abort();
            envAc = null;
            cancelAnimationFrame(envRaf);
            envRaf = 0;
            // 離開分頁當下重畫回第一幀：再切回來時 activate 排在 rAF 之後，這之前畫面不能還停在舊的一步
            if (ac) { cur = goal = 0; shown = 0; draw(0); }
            stopMachinery();
        },
    };
}
