/**
 * stage-math.js — 舞台進度的純函式（TASK-191a-T5，CD-191a-5）
 *
 * 畫面是「捲動位置」的純函式：同一個 scrollY 不論從上往下或從下往上到達，v 都相同。
 * 模組頂層不碰 window／document（FE-GUARD-11），node:test 可直接 import。
 * glide＝null 或 { active:boolean, step:number }（引擎正在滑向第 step 步時）。
 */

export const N_STEPS = 4;
export const HOLD = 0.86; // 每一步的定格點（該步內進度的小數部分）

export function clamp(x, a, b) { return x < a ? a : x > b ? b : x; }
export function seg(v, a, b) { return clamp((v - a) / (b - a), 0, 1); }
export function ease(x) { return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2; }
export function lerp(a, b, k) { return a + (b - a) * k; }

// 每一步的捲動像素：一律由 track 實際高度反推，不另存步長
export function stepPxOf({ h, pinH }, steps = N_STEPS) {
    return Math.max(1, (h - pinH) / steps);
}

// top＝track 的 rect.top；gap＝pin 黏住時離視窗頂的距離
export function progressOf({ top, h, pinH, gap }, steps = N_STEPS) {
    const stepPx = stepPxOf({ h, pinH }, steps);
    return clamp((gap - top) / stepPx, 0, steps);
}

export function stepOf(v, steps = N_STEPS) {
    return Math.min(steps, Math.floor(v) + 1);
}

export function stepForward(v, glide, steps = N_STEPS) {
    if (glide && glide.active) return glide.step + 1;
    const n = stepOf(v, steps);
    return v < n - 1 + HOLD - 0.02 ? n : n + 1;
}

export function stepBack(v, glide, steps = N_STEPS) {
    if (glide && glide.active) return glide.step - 1;
    const n = stepOf(v, steps);
    return v > n - 1 + HOLD + 0.02 ? n : n - 1;
}

// keyframes: [[v, x, y, opacity], …]（v 遞增）→ { x, y, o }；空陣列回 null
export function cursorAt(v, keyframes) {
    const kf = keyframes;
    if (!kf || kf.length === 0) return null;
    let i = 0;
    while (i < kf.length - 1 && kf[i + 1][0] <= v) i++;
    const a = kf[i];
    const b = kf[Math.min(i + 1, kf.length - 1)];
    const k = b[0] > a[0] ? ease(seg(v, a[0], b[0])) : 0;
    return { x: lerp(a[1], b[1], k), y: lerp(a[2], b[2], k), o: lerp(a[3], b[3], k) };
}
