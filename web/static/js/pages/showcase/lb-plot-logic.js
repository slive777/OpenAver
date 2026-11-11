/**
 * lb-plot-logic.js — 燈箱簡介純函式（187b-T5a → 199a-T6）
 *
 * plotPopButtons：簡介浮層的翻譯鈕集合（翻譯關＝無；開＋無原文＝翻譯；開＋有原文＝重新翻譯）。
 * sameAfterNormalize：譯文與來源空白正規化後相等 → 前端不送寫回。
 * 只用相對 import（FE-GUARD-11）；本檔無外部依賴。
 */

/** @param {{ translateEnabled: boolean, hasOriginal: boolean }} state */
export function plotPopButtons(state) {
    const { translateEnabled, hasOriginal } = state;
    if (!translateEnabled) return [];
    return hasOriginal ? ['retranslate'] : ['translate'];
}

/** 空白正規化後比對（與後端 `" ".join(s.split())` 同形） */
export function sameAfterNormalize(a, b) {
    const norm = (s) => String(s ?? '').split(/\s+/).filter(Boolean).join(' ');
    return norm(a) === norm(b);
}
