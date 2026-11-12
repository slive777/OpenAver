/**
 * state-lightbox-fit.js — Showcase ESM（199a-T5）
 *
 * 影片燈箱文字區第 3 列的「女優露出數」量測：最多露 3 位、放不下逐位減少、至少 1 位，其餘收成「另有 N 位」。
 * mergeState 分片（plan-199a CD-199a-3／9）：不定義 init()（FE-ALPINE-05）、頂層 key 一律 lbxFit 前綴、
 * 分片內不掛任何 $watch（FE-ALPINE-08）——觸發全靠模板第 3 列的 x-effect＝lbxFitSchedule(輸入簽章)。
 *
 * 外求 0：輸入一律以函式引數傳入（簽章與列元素），分片內不讀 currentLightboxVideo／addingLbTag／_lbActorAges／lbxPop*。
 * 時序：lbxFitSchedule 在 x-effect 內執行，effect 內讀寫響應式欄位會自己觸發自己 ⇒ 排程狀態
 * （最後一次輸入、ResizeObserver、fonts.ready 旗標）全放工廠閉包的 let，不放 this._xxx；量完一次整包寫入 lbxFit
 * （整包替換 Alpine Proxy 才重繪）。量測完成前模板用 lbxFitMeasuring 讓列 visibility:hidden（版面保留），不顯示半成品。
 * 年齡（_lbActorAges）晚到時簽章不變、量測層 chip 變寬——所以 ResizeObserver 除了文字區也觀察每個 .lbx-measure。
 * 分片頂層不讀 window／document（FE-GUARD-11）：ResizeObserver／document.fonts 在方法內才讀並先 typeof 檢查。
 */

import { fitActresses, fitSig, fitTagRow } from './lbx-logic.js';

const LBX_FIT_DEFAULT_SHOWN = 3;

// 第 5 列（199a-T7）：讀 DOM 回 { userWidths, workWidths, plusWidth, moreChipWidth, rowWidth, gap }；任何元素缺或寬度不可用 → null（標籤全露）
function measureTagRow(rowEl) {
    const tagRowEl = rowEl.closest?.('.lbx-meta')?.querySelector('.lbx-tag-row');
    if (!tagRowEl) return null;
    const measureEl = tagRowEl.querySelector('.lbx-measure');
    const controlEl = tagRowEl.querySelector('.lbx-tag-control');
    if (!measureEl || !controlEl) return null;
    const widths = (sel) => Array.from(measureEl.querySelectorAll(sel)).map((el) => el.offsetWidth);
    const userWidths = widths('.lbx-utag');
    const workWidths = widths('.lbx-tag');
    const moreEl = measureEl.querySelector('.lbx-more-tags');
    const moreChipWidth = moreEl ? moreEl.offsetWidth : 0;
    const plusWidth = controlEl.offsetWidth;
    const rowWidth = tagRowEl.clientWidth;
    const gap = parseFloat(getComputedStyle(tagRowEl).columnGap) || 0;
    if (!(Number.isFinite(rowWidth) && rowWidth > 0)) return null;
    if (![...userWidths, ...workWidths, moreChipWidth, plusWidth, gap].every(Number.isFinite)) return null;
    return { userWidths, workWidths, plusWidth, moreChipWidth, rowWidth, gap };
}

// 預設量測：讀 DOM 回 { chipWidths, moreChipWidth, available, gap, tagRow }；任何元素缺或寬度不可用 → null（呼叫端退回預設露出數）
function measureRow({ rowEl } = {}) {
    if (!rowEl || typeof rowEl.querySelector !== 'function') return null;
    const actorsEl = rowEl.querySelector('.lbx-actors');
    const measureEl = rowEl.querySelector('.lbx-measure');
    if (!actorsEl || !measureEl || !rowEl.clientWidth) return null;
    const chipWidths = Array.from(measureEl.querySelectorAll('.lbx-actor-chip')).map((el) => el.offsetWidth);
    const moreEl = measureEl.querySelector('.lbx-more-actors');
    const moreChipWidth = moreEl ? moreEl.offsetWidth : 0;
    const available = actorsEl.clientWidth;
    const gap = parseFloat(getComputedStyle(actorsEl).columnGap) || 0;
    if (!(Number.isFinite(available) && available > 0)) return null;
    if (!chipWidths.every(Number.isFinite) || !Number.isFinite(moreChipWidth)) return null;
    return { chipWidths, moreChipWidth, available, gap, tagRow: measureTagRow(rowEl) };
}

export function stateLightboxFit() {
    // 閉包狀態（不放 this，見檔頭）
    let last = null; // { rowEl, sig }：最後一次排程
    let observer = null;
    let fontsHooked = false;

    return {
        // workTagShown／userTagShown（199a-T7）：null＝量測失敗／尚未量到＝全露（模板的 lbxTagShown 把非整數視為 ∞）
        lbxFit: { sig: '', actressShown: LBX_FIT_DEFAULT_SHOWN, workTagShown: null, userTagShown: null },

        // favKey（199b-T1）：頭像表鍵集合，由呼叫端傳入（分片外求仍為 0）
        lbxFitSig(video, adding, favKey) {
            return fitSig(video, adding, favKey);
        },

        // 輸入改了、尚未量測 ⇒ 為真 ⇒ 列帶 is-measuring（visibility:hidden，版面保留）
        lbxFitMeasuring(sig) {
            return this.lbxFit.sig !== sig;
        },

        // 綁 x-effect：只記輸入、延到 $nextTick 量（x-for／x-if 內容那時才畫好，FE-ALPINE-03）；快速連換只認最後一次
        lbxFitSchedule(rowEl, sig) {
            last = { rowEl, sig };
            this.$nextTick?.(() => {
                if (!last || last.sig !== sig || last.rowEl !== rowEl || !rowEl || !rowEl.isConnected) return;
                this.lbxFitRun(sig, { rowEl });
            });
            this._lbxFitObserve(rowEl);
        },

        // 重新掛 ResizeObserver（單一實例，冪等）與 fonts.ready（只掛一次）。回呼一律以「最後一次排程」重跑。
        _lbxFitObserve(rowEl) {
            const rerun = () => {
                if (!last || !last.rowEl || !last.rowEl.isConnected) return;
                this.lbxFitRun(last.sig, { rowEl: last.rowEl });
            };
            if (typeof ResizeObserver === 'function' && rowEl && typeof rowEl.closest === 'function') {
                if (observer) observer.disconnect();
                observer = new ResizeObserver(rerun);
                const metaEl = rowEl.closest('.lbx-meta');
                if (metaEl) observer.observe(metaEl);
                for (const el of (metaEl || rowEl).querySelectorAll('.lbx-measure, .lbx-tag-control')) observer.observe(el);
            }
            if (!fontsHooked && typeof document !== 'undefined' && document.fonts?.ready?.then) {
                fontsHooked = true;
                document.fonts.ready.then(rerun, () => {});
            }
        },

        // 量完一次寫入；sig 與露出數都沒變就不寫（RO／fonts 重跑不要讓畫面無謂重繪）。量測失敗也寫（退回預設數、不卡在隱藏）。
        lbxFitRun(sig, inputs, measure = measureRow) {
            const m = measure(inputs);
            const actressShown = m ? fitActresses(m) : LBX_FIT_DEFAULT_SHOWN;
            const tagFit = m && m.tagRow ? fitTagRow(m.tagRow) : null;
            const workTagShown = tagFit ? tagFit.workShown : null;
            const userTagShown = tagFit ? tagFit.userShown : null;
            const cur = this.lbxFit;
            if (cur.sig === sig && cur.actressShown === actressShown && cur.workTagShown === workTagShown && cur.userTagShown === userTagShown) return;
            this.lbxFit = { ...cur, sig, actressShown, workTagShown, userTagShown };
        },
    };
}
