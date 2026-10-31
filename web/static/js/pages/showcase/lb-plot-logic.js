/**
 * lb-plot-logic.js — 燈箱簡介面純函式（187b-T5a）
 *
 * plotFaceButtons：spec §3.3 按鈕集合真值表。
 * sameAfterNormalize：譯文與來源空白正規化後相等 → 前端不送寫回。
 * 只用相對 import（FE-GUARD-11）；本檔無外部依賴。
 */

/** @param {{ translateEnabled: boolean, hasOriginal: boolean, showing: 'plot'|'original' }} state */
export function plotFaceButtons(state) {
    const { translateEnabled, hasOriginal, showing } = state;
    if (!hasOriginal) {
        return translateEnabled ? ['translate'] : [];
    }
    if (showing === 'plot') {
        return ['toggle'];
    }
    // showing === 'original'
    return translateEnabled ? ['toggle', 'retranslate'] : ['toggle'];
}

/** 空白正規化後比對（與後端 `" ".join(s.split())` 同形） */
export function sameAfterNormalize(a, b) {
    const norm = (s) => String(s ?? '').split(/\s+/).filter(Boolean).join(' ');
    return norm(a) === norm(b);
}
