/**
 * state-lightbox-apfit.js — Showcase ESM（199b-T4）
 *
 * 女優燈箱資料區第 3 行（別名＋資訊同一行）的「露出幾顆」量測：放不下逐顆減少、至少 1 顆，其餘收成「+N」。
 * mergeState 分片（plan-199b CD-199b-3）：不定義 init()（FE-ALPINE-05）、頂層 key 一律 lbxApFit 前綴、
 * 分片內不掛任何 $watch（FE-ALPINE-08）——觸發全靠模板 .lbx-ap-chips 的 x-effect＝lbxApFitSchedule(輸入簽章)。
 * 形狀複製 state-lightbox-fit.js（199a-T5），不抽共用、不改 199a。
 *
 * 外求 0：輸入一律以函式引數傳入（名字、chips、展開旗標與列元素），分片內不讀 currentLightboxActress／_actressChipsExpanded。
 * 時序：lbxApFitSchedule 在 x-effect 內執行，effect 內讀寫響應式欄位會自己觸發自己 ⇒ 排程狀態
 * （最後一次輸入、ResizeObserver、fonts.ready 旗標）全放工廠閉包的 let，不放 this._xxx；量完一次整包寫入 lbxApFit
 * （整包替換 Alpine Proxy 才重繪）。量測完成前模板用 lbxApFitMeasuring 讓列 visibility:hidden（版面保留），不顯示半成品。
 * 量測失敗（元素尚未顯示、寬度不可用）＝ shown: null ＝全露，也照樣寫入簽章（不卡在隱藏）；ResizeObserver 會在顯示後重量。
 * 分片頂層不讀 window／document（FE-GUARD-11）：ResizeObserver／document.fonts 在方法內才讀並先 typeof 檢查。
 */

import { fitChipRow } from './lbx-logic.js';

// 預設量測：讀 DOM 回 { chipWidths, moreChipWidth, available, gap }；任何元素缺或寬度不可用 → null（呼叫端全露）
function measureApRow({ rowEl } = {}) {
    if (!rowEl || typeof rowEl.querySelector !== 'function') return null;
    const listEl = rowEl.querySelector('.lbx-ap-list');
    const measureEl = rowEl.querySelector('.lbx-ap-measure');
    if (!listEl || !measureEl) return null;
    const chipWidths = Array.from(measureEl.querySelectorAll('.lbx-ap-chip')).map((el) => el.offsetWidth);
    const moreEl = measureEl.querySelector('.lbx-ap-more');
    const moreChipWidth = moreEl ? moreEl.offsetWidth : 0;
    const available = listEl.clientWidth;
    const gap = parseFloat(getComputedStyle(listEl).columnGap) || 0;
    if (!(Number.isFinite(available) && available > 0)) return null;
    if (!chipWidths.every(Number.isFinite) || !Number.isFinite(moreChipWidth)) return null;
    return { chipWidths, moreChipWidth, available, gap };
}

export function stateLightboxApFit() {
    // 閉包狀態（不放 this，見檔頭）
    let last = null; // { rowEl, sig }：最後一次排程
    let observer = null;
    let fontsHooked = false;

    return {
        // shown: null＝量測失敗／尚未量到＝全露（lbxApFitShown 把非整數視為全部）
        lbxApFit: { sig: '', shown: null },

        // 量測簽章：名字、各 chip 的 kind:text、展開旗標（分隔字元避免欄位內容互相拼出相同字串）
        lbxApFitSig(name, chips, expanded) {
            const chipPart = (chips || []).map((c) => c.kind + ':' + c.text).join('\u0001');
            return [name || '', chipPart, expanded ? '1' : '0'].join('\u0000');
        },

        // 輸入改了、尚未量測 ⇒ 為真 ⇒ 列帶 is-measuring（visibility:hidden，版面保留）
        lbxApFitMeasuring(sig) {
            return this.lbxApFit.sig !== sig;
        },

        // 綁 x-effect：只記輸入、延到 $nextTick 量（x-for 內容那時才畫好，FE-ALPINE-03）；快速連換只認最後一次
        lbxApFitSchedule(rowEl, sig) {
            last = { rowEl, sig };
            this.$nextTick?.(() => {
                if (!last || last.sig !== sig || last.rowEl !== rowEl || !rowEl || !rowEl.isConnected) return;
                this.lbxApFitRun(sig, { rowEl });
            });
            this._lbxApFitObserve(rowEl);
        },

        // 重新掛 ResizeObserver（單一實例，冪等）與 fonts.ready（只掛一次）。回呼一律以「最後一次排程」重跑。
        _lbxApFitObserve(rowEl) {
            const rerun = () => {
                if (!last || !last.rowEl || !last.rowEl.isConnected) return;
                this.lbxApFitRun(last.sig, { rowEl: last.rowEl });
            };
            if (typeof ResizeObserver === 'function' && rowEl && typeof rowEl.closest === 'function') {
                if (observer) observer.disconnect();
                observer = new ResizeObserver(rerun);
                const metaEl = rowEl.closest('.lbx-ap-meta');
                if (metaEl) observer.observe(metaEl);
                for (const el of rowEl.querySelectorAll('.lbx-ap-list, .lbx-ap-measure')) observer.observe(el);
            }
            if (!fontsHooked && typeof document !== 'undefined' && document.fonts?.ready?.then) {
                fontsHooked = true;
                document.fonts.ready.then(rerun, () => {});
            }
        },

        // 量完一次寫入；sig 與露出數都沒變就不寫（RO／fonts 重跑不要讓畫面無謂重繪）。量測失敗也寫（shown: null＝全露、不卡在隱藏）。
        lbxApFitRun(sig, inputs, measure = measureApRow) {
            const m = measure(inputs);
            const shown = m ? fitChipRow(m) : null;
            const cur = this.lbxApFit;
            if (cur.sig === sig && cur.shown === shown) return;
            this.lbxApFit = { sig, shown };
        },

        // 露出顆數（total＝全部 chip 數）；量測失敗／尚未量到＝全露
        lbxApFitShown(total) {
            return Number.isInteger(this.lbxApFit.shown) ? Math.min(this.lbxApFit.shown, total) : total;
        },

        // 被收起的顆數＝模板「+N」的 N（唯一來源）
        lbxApFitHidden(total) {
            return Math.max(0, total - this.lbxApFitShown(total));
        },
    };
}
