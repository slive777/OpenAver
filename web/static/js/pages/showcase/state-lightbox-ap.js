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
 *
 * 199b-T6（點縮圖看封面）：lbxApCover＝點擊當下的快照（逐欄位挑選的新物件，不是 video 本身；null＝顯示照片）。
 * 「讀不到」「已顯示」兩個旗標是分片純量，不寫到 video 或 lbxApCover。封面開著與對焦／換照片互斥：
 * 封面端由 _focalIconVisible 與 .cover-actions 的 x-show 擋（P 擋 Q），縮圖排端由 lbxApStripLocked 擋（Q 擋 P）。
 * lbxApStripVisible 不讀封面（封面開著時縮圖排仍要渲染，最左格是回照片的唯一入口）。
 * lbxApRebuild 只在「封面那部片已不在可見清單、或片庫沒就緒」時清封面回照片（branch review F2：片庫重算後縮圖排可能整排消失，
 * 大圖卻停在離線檔的封面，回照片的入口跟著不見）；封面那部還在就不動，換批、隱藏切換都不影響已選的那部。
 */

import { _videos, _videosReady, _aliasMapLoaded, _actressIndex } from '@/showcase/state-base.js';
import { worksOfActress } from '@/shared/actress-lookup.js';
import { focalCellObjectPosition } from '@/shared/focal.js';
import { batchLabel, nextBatchStart, sortWorksByRelease } from './lbx-logic.js';
import { sameWork } from './work-versions.js';

const LBX_AP_BATCH_SIZE = 6;

export function stateLightboxAp() {
    // 閉包狀態（不放 this，見檔頭）：整份排好序的作品清單
    let items = [];

    return {
        lbxApBatch: [],
        lbxApStart: 0,
        lbxApTotal: 0,
        lbxApCover: null,
        lbxApCoverFailed: false,   // 封面讀不到（@error）；沒有任何封面網址由 lbxApCoverNoImage 另判
        lbxApCoverShown: false,    // 封面疊層已淡入：第一張封面載入完成（或無圖可載）後恆真，A→B 不再歸零（歸零會露出底下的女優照片）

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
                this.lbxApBackToPhoto();   // 片庫沒就緒：縮圖排沒了，封面也要回照片（否則回照片的入口不見）
                return;
            }
            items = sortWorksByRelease(worksOfActress(_videos, _actressIndex, actress));
            // 封面那部片已不在可見清單（被「隱藏未連線硬碟」藏起、或她的片全沒了）→ 回照片。
            // 用 sameWork（任一版本的 path 相符）不只比 path：多版本作品換過預設版本不會誤清。
            if (this.lbxApCover && !items.some((v) => sameWork(v, this.lbxApCover))) this.lbxApBackToPhoto();
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
            this.lbxApCover = null;
            this.lbxApCoverFailed = false;
            this.lbxApCoverShown = false;
        },

        // 點縮圖看封面：逐欄位挑選組新物件（不 spread／Object.assign video，不在 video 上寫欄位——video 是牆上同一個物件，
        // 且是 Alpine Proxy，直接存參考會讓比對失效）。同一部再點不動；換成不同的片時清「讀不到」。
        // 這裡不判 lbxApStripLocked：鎖死只靠縮圖排的 :inert，多一道保險會讓「:inert 接線遺失」無人發現（FE-GUARD-25）。
        lbxApOpenCover(video) {
            if (!video || this.lbxApCover?.path === video.path) return;
            this.lbxApCover = {
                path: video.path,
                number: video.number,
                title: video.title,
                cover_url: video.cover_url,
                cover_full_url: video.cover_full_url,
                auto_focal: video.auto_focal,
                crop_mode: video.crop_mode,
            };
            this.lbxApCoverFailed = false;
            // 沒有封面網址：沒有圖要等，直接顯示無封面塊（不透明底）
            this.lbxApCoverShown = !(video.cover_full_url || video.cover_url) || this.lbxApCoverShown;
        },

        lbxApBackToPhoto() { this.lbxApCover = null; this.lbxApCoverFailed = false; this.lbxApCoverShown = false; },

        // 封面 <img> @error：讀不到 → 顯示無封面塊，同時結束淡入等待
        lbxApCoverError() {
            this.lbxApCoverFailed = true;
            this.lbxApCoverShown = true;
        },

        // 封面 <img> @load：疊層盒（imgEl 的父層）比例量得到就套焦點裁法，量不到或不需裁就清成 ''（退 CSS 的右半邊基線）。
        // 回 null 也要清 inline——同一個 <img> 在 A→B 時是重用的，不清會把 A 的裁法殘留到 B。
        lbxApCoverLoaded(imgEl) {
            this.lbxApCoverShown = true;
            if (!imgEl) return;
            const box = imgEl.parentElement?.getBoundingClientRect?.();
            const boxRatio = box && box.height > 0 ? box.width / box.height : 0;
            const pos = boxRatio > 0
                ? focalCellObjectPosition(this.lbxApCover, imgEl.naturalWidth / imgEl.naturalHeight, boxRatio)
                : null;
            imgEl.style.objectPosition = pos || '';
        },

        // 無封面：沒開、或兩個網址皆空、或讀不到
        lbxApCoverNoImage() {
            const cover = this.lbxApCover;
            const failed = this.lbxApCoverFailed;
            return !cover || !(cover.cover_full_url || cover.cover_url) || failed;
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
