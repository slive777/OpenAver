/**
 * state-lightbox-ap.js — Showcase ESM（199b-T5）
 *
 * 女優燈箱資料區最下面的縮圖排：照片格＋最多 6 張她的片（新→舊）＋「下一批」格。
 * mergeState 分片（plan-199b CD-199b-10，不做獨立元件）：不定義 init()（FE-ALPINE-05）、頂層 key 一律 lbxAp 前綴、
 * 分片內不掛任何 $watch（FE-ALPINE-08）——重建由 _setActressLightboxIndex／_refreshActressDerived 以可選呼叫觸發，
 * 清空由 _setActressLightboxIndex（賦值前）與 closeLightbox 觸發。
 *
 * 外求不為 0（刻意）：讀 currentLightboxActress、開燈箱來源旗標、_maskVisible、_pickerOpen、_pickerLoading、_pickerSelected。
 * 整份排好序的清單放工廠閉包 items（不放 this、不進 reactive scope，FE-ALPINE-18）；響應式只有 lbxApBatch／lbxApStart／lbxApTotal，
 * 且一律整包賦值，不就地 push／splice（FE-ALPINE-20）。清單裡的每一項就是 _videos 的格子本身，這裡不在它上面寫任何欄位（會污染牆）。
 * 分片頂層不讀 window／document（FE-GUARD-11）。
 */

import { _videos, _videosReady, _aliasMapLoaded, _actressIndex } from '@/showcase/state-base.js';
import { worksOfActress } from '@/shared/actress-lookup.js';
import { batchLabel, nextBatchStart, sortWorksByRelease } from './lbx-logic.js';

const LBX_AP_BATCH_SIZE = 6;

export function stateLightboxAp() {
    // 閉包狀態（不放 this，見檔頭）：整份排好序的作品清單
    let items = [];

    return {
        lbxApBatch: [],
        lbxApStart: 0,
        lbxApTotal: 0,

        // 重建：只看「她是誰」與「片庫就緒沒」。開燈箱的來源（牆／hero／影片橋接）一律不在這裡判，
        // 而是在 lbxApStripVisible 顯示時判——openActressLightbox 先賦值、之後才設來源，
        // 重建當下來源還是 null，關掉燈箱再開的第一次開啟會因此沒有縮圖排。
        lbxApRebuild() {
            const actress = this.currentLightboxActress;
            if (!actress || !_actressIndex || !(_videosReady && _aliasMapLoaded)) {
                items = [];
                this.lbxApStart = 0;
                this.lbxApTotal = 0;
                this.lbxApBatch = [];
                return;
            }
            items = sortWorksByRelease(worksOfActress(_videos, _actressIndex, actress));
            const total = items.length;
            const start = this.lbxApStart < total ? this.lbxApStart : 0;
            this.lbxApTotal = total;
            this.lbxApStart = start;
            this.lbxApBatch = items.slice(start, start + LBX_AP_BATCH_SIZE);
        },

        // 換人（賦值前）與關燈箱都呼叫：回第一批、清空
        lbxApReset() {
            items = [];
            this.lbxApStart = 0;
            this.lbxApTotal = 0;
            this.lbxApBatch = [];
        },

        lbxApNext() {
            const next = nextBatchStart(this.lbxApStart, LBX_AP_BATCH_SIZE, this.lbxApTotal);
            this.lbxApStart = next;
            this.lbxApBatch = items.slice(next, next + LBX_AP_BATCH_SIZE);
        },

        // ≤ 6 部整個「下一批」格不渲染
        lbxApHasNext() {
            return this.lbxApTotal > LBX_AP_BATCH_SIZE;
        },

        lbxApLabel() {
            return batchLabel(this.lbxApStart, LBX_AP_BATCH_SIZE, this.lbxApTotal);
        },

        // 顯示條件（綁 <template x-if>）：從女優牆開的、她有片
        lbxApStripVisible() {
            return !!this.currentLightboxActress && this.actressLightboxSource === 'grid' && this.lbxApTotal > 0;
        },

        // 鎖死：對焦拖曳中或換照片流程中整排不能點。四個旗標各自獨立陳述式讀完再組合，
        // 不直接用 &&／|| 串 this.*（短路求值會漏訂閱，同 _focalIconVisible 的理由）。
        lbxApStripLocked() {
            const masking = this._maskVisible;
            const picking = this._pickerOpen;
            const loading = this._pickerLoading;
            const selected = this._pickerSelected;
            return !!(masking || picking || loading || selected);
        },
    };
}
