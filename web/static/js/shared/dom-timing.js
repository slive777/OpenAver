'use strict';

/**
 * waitForMount — MutationObserver 版「等 DOM 就緒」（nexttick-hydrate T2 / CD-3）。
 *
 * 取代脆弱的 `await this.$nextTick()`：95a-T8 證實 `$nextTick` 在冷模組快取下
 * callback / promise 可能不 fire → 一次性 mount-dependent 副作用永久不執行。
 *
 * 本 util 改用 MutationObserver 觀察「同步即存在的容器 root」，每次子樹 mutation
 * 重檢 predicate，就緒即 resolve。**只在兩種情況 settle**：
 *   (a) predicate 通過（entry 同步命中 or observer 觀察到）→ { ready: true }
 *   (b) signal abort（含 entry 已中止）→ { ready: false, aborted: true }
 * **無時間性 settle**：`warnAfterMs` 逾時只 console.warn 診斷、不 disconnect、不 settle
 * （Codex round-3：timeout settle(false)+disconnect 是終止式放棄，卡片第 4.1 秒才 mount
 *  會回到永久隱藏，與「無論何時 mount 都 reveal」矛盾）。observer 存活到 abort。
 *
 * 為何 MutationObserver 而非 rAF poll：observer callback 走 microtask，不受 paint / 背景頁
 * 節流影響（Codex P2）；且 observer 唯讀（只在 mutation 時測 predicate，不 clone / 不注入
 * Alpine-bound 節點）→ 與 Alpine 全域 observer 正交，不觸「cloneNode 洪水」。
 *
 * @param {Element|null} root       同步即存在的容器（必須 x-show / 恆掛載，非 x-if 內元素）
 * @param {() => boolean} predicate  就緒判定（通常查子孫元素是否 mount）
 * @param {{ signal?: AbortSignal, warnAfterMs?: number }} [opts]
 *        signal      — per-open/per-run AbortController.signal；abort → disconnect + resolve aborted
 *        warnAfterMs — 逾時只 console.warn 診斷（預設 4000）；不影響 settle
 * @returns {Promise<{ ready: boolean, aborted?: boolean }>}
 */
export function waitForMount(root, predicate, { signal, warnAfterMs = 4000 } = {}) {
    // 〔0〕入口同步防呆：傳入已中止 signal → 不掛 observer 空等（Codex round-3）
    if (signal && signal.aborted) {
        return Promise.resolve({ ready: false, aborted: true });
    }
    // 〔0b〕root 不存在無從 observe（observe(null) 會 throw）→ 靜默 bail
    if (!root) {
        return Promise.resolve({ ready: false });
    }
    // 〔1〕同步命中即返回
    if (predicate()) {
        return Promise.resolve({ ready: true });
    }
    // 〔2〕掛 observer，等就緒 or abort
    return new Promise((resolve) => {
        let settled = false;
        let observer = null;
        let warnTimer = null;

        function settle(result) {
            if (settled) return;
            settled = true;
            if (observer) { observer.disconnect(); observer = null; }
            if (warnTimer !== null) { clearTimeout(warnTimer); warnTimer = null; }
            if (signal) signal.removeEventListener('abort', onAbort);
            resolve(result);
        }

        function onAbort() {
            settle({ ready: false, aborted: true });
        }

        observer = new MutationObserver(() => {
            if (predicate()) settle({ ready: true });
        });
        observer.observe(root, { childList: true, subtree: true });

        if (signal) signal.addEventListener('abort', onAbort);

        // 診斷用 warn timer：**不 settle、不 disconnect**，observer 續存活到 ready / abort
        warnTimer = setTimeout(() => {
            warnTimer = null;
            if (!settled) {
                console.warn(   // 診斷用；observer 仍存活，非放棄
                    '[waitForMount] predicate 逾 ' + warnAfterMs +
                    'ms 仍未就緒；observer 續等 ready 或 abort（非放棄）。',
                );
            }
        }, warnAfterMs);
    });
}
