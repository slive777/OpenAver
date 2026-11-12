/**
 * state-delete.js — Showcase ESM（71-T7）
 *
 * 影片「從收藏移除」：燈箱垃圾桶 → 破壞性確認 modal → DELETE /api/showcase/video
 * → splice _videos 即時移卡 + 關燈箱 + 成功 toast。
 *
 * 只刪 DB row + 衍生縮圖（後端 delete_by_paths + thumbnail_cache.invalidate），
 * **絕不刪磁碟上的影片檔或原始封面**。鏡像 state-actress.js 的 remove modal 三段路徑。
 *
 * 從 state-base.js import 共用大陣列（F1：移出 Alpine reactive scope），
 * splice _videos 即影響 grid。
 */

import { _videos, _allVideos, _recomputeVideoBadges, _recomputeCardActorAges } from '@/showcase/state-base.js';
import { versionsOf, sameWork, applyVersionRemoval, viaRendered } from './work-versions.js';

export function stateDelete() {
    return {

        // --- 71-T7: Delete Video fluent-modal 狀態（必宣告 stub，Alpine 3 ReferenceError）---
        deleteVideoModalOpen: false,
        _pendingDeleteNumber: null,
        _pendingDeletePath: null,
        // feature/122 T4 起，合併卡的「移除」刪的是整組 DB 列。破壞性彈窗是授權面，
        // 只說「這筆紀錄」等於沒有明示授權（prd「破壞性 modal 明示授權」）。
        _pendingDeleteParts: [],
        // 198b-T7b：多版本作品只移除目前這一版——彈窗要寫明是哪一版；others ＝ 同作品其餘版本的 path。
        _pendingDeleteVersionLabel: '',
        _pendingDeleteOthers: [],
        _deleteLoading: false,

        // --- 71-T7: Delete Video 三段路徑（鏡像 openRemoveActressModal / cancel / confirm）---
        openDeleteVideoModal() {
            if (!this.currentLightboxVideo?.path) return;
            this._pendingDeletePath = this.currentLightboxVideo.path;
            this._pendingDeleteNumber = this.currentLightboxVideo.number || '';
            this._pendingDeleteParts = this.currentLightboxVideo.part_tokens || [];
            const vs = versionsOf(this.currentLightboxVideo);
            this._pendingDeleteOthers = vs.filter((v) => v.path !== this._pendingDeletePath).map((v) => v.path);
            // 單版本不呼叫 lbVersionCapsules（既有測試單獨組分片，沒有 T7a 的方法）
            this._pendingDeleteVersionLabel = vs.length > 1
                ? (this.lbVersionCapsules()[vs.findIndex((v) => v.path === this._pendingDeletePath)] || '')
                : '';
            this.deleteVideoModalOpen = true;
        },

        cancelDeleteVideo() {
            // 取消 / ESC / backdrop 統一走此：只關 modal + 清 pending，no-op 不發請求
            this.deleteVideoModalOpen = false;
            this._pendingDeletePath = null;
            this._pendingDeleteNumber = null;
            this._pendingDeleteParts = [];
            this._pendingDeleteVersionLabel = '';
            this._pendingDeleteOthers = [];
        },

        async confirmDeleteVideo() {
            // 請求發起時鎖定 path（避免請求期間切換燈箱導致 splice 誤刪別片）
            const path = this._pendingDeletePath;
            const others = this._pendingDeleteOthers.slice();   // FE-TIMING-16：第一個 await 前取快照
            if (!path) {
                this.deleteVideoModalOpen = false;
                return;
            }
            this._deleteLoading = true;
            try {
                const resp = await fetch(
                    '/api/showcase/video?path=' + encodeURIComponent(path),
                    { method: 'DELETE' }
                );
                const data = await resp.json();
                if (resp.ok) {
                    if (others.length === 0) {
                        // 最後一版：整張卡移除。以「同作品」找格（sameWork，path 比對，FE-ALPINE-14）。
                        // 195b-T4：全庫也要同步移除，否則「隱藏未連線硬碟」切換時被刪的片會復活
                        // （被藏的片不在 _videos，但刪的是可見那片）。
                        const allIdx = _allVideos.findIndex(v => sameWork(v, { path }));
                        if (allIdx >= 0) _allVideos.splice(allIdx, 1);
                        const idx = _videos.findIndex(v => sameWork(v, { path }));
                        if (idx >= 0) {
                            _videos.splice(idx, 1);
                            // videoCount 是 reactive scalar（state-base），applyFilterAndSort 不重算它
                            // → 手動 decrement（控制 grid vs empty-state 顯示 + 總數）
                            if (this.videoCount > 0) this.videoCount -= 1;
                        }
                    } else {
                        // 還有其他版本：卡留著、不減 videoCount，只把該作品縮減成剩下的版本（不經 refreshRoute，CD-198b-12）。
                        // 作品原物件先記下（縮減前，被刪那版的 _versions 還在，sameWork 找得到）當後備；
                        // 格的位置不能在 await 前記——GET 等待期間 _videos 可能被重建（隱藏未連線硬碟的重算），
                        // index 會指到別部作品，所以 GET 完成後、寫入前才重找（FE-ALPINE-14：path 比對）。
                        const workBefore = _allVideos.find(v => sameWork(v, { path })) || _videos.find(v => sameWork(v, { path })) || null;
                        // DELETE 已成功：讀剩餘版本失敗一律當 fresh = null，不 throw、不 toast（落到外層 catch 會跳「移除失敗」）。
                        let fresh = null;
                        try {
                            const gr = await fetch('/api/showcase/video?path=' + encodeURIComponent(others[0]));
                            if (gr.ok) {
                                const gd = await gr.json();
                                if (gd && gd.success === true && gd.video) fresh = gd.video;
                            }
                        } catch (e) {
                            fresh = null;
                        }
                        // 縮減之前重找：_allVideos、_videos 各自重找；找不到就只縮減原 dict、不寫陣列格。
                        const allIdx = _allVideos.findIndex(v => sameWork(v, { path }));
                        const idx = _videos.findIndex(v => sameWork(v, { path }));
                        const work = allIdx >= 0 ? _allVideos[allIdx] : (idx >= 0 ? _videos[idx] : workBefore);
                        if (work) {
                            const { defaultDict, byPath } = applyVersionRemoval(
                                work, path, fresh,
                                (target, patch) => Object.assign(viaRendered(target, this.paginatedVideos, this.currentLightboxVideo), patch)
                            );
                            if (fresh) {
                                Object.keys(byPath).forEach((p) => {
                                    const via = viaRendered(byPath[p], this.paginatedVideos, this.currentLightboxVideo);
                                    _recomputeVideoBadges(via);
                                    _recomputeCardActorAges(via);
                                });
                            }
                            if (defaultDict) {
                                if (allIdx >= 0) _allVideos[allIdx] = defaultDict;
                                if (idx >= 0) _videos[idx] = defaultDict;
                            }
                        }
                    }
                    // 刪除請求在飛時該片可能已被藏：被藏數只能由全庫與可見數相減得出（賦值，不重篩、不動頁碼）
                    this.hiddenCount = _allVideos.length - _videos.length;
                    this._refreshActressDerived?.();   // 199b-T4b：兩條分支共同尾段——移除任一版本後女優片數與排序都要重算
                    this.applyFilterAndSort();
                    this.closeLightbox();
                    this.showToast(window.t('showcase.video.delete_success'), 'success');
                } else {
                    this.showToast(window.t('showcase.video.delete_failed'), 'error');
                }
            } catch (e) {
                // 失敗：不 splice、不關燈箱（卡仍在，使用者可重試）
                this.showToast(window.t('showcase.video.delete_failed'), 'error');
            } finally {
                this._deleteLoading = false;
                this.deleteVideoModalOpen = false;
                this._pendingDeletePath = null;
                this._pendingDeleteNumber = null;
                this._pendingDeleteParts = [];
                this._pendingDeleteVersionLabel = '';
                this._pendingDeleteOthers = [];
            }
        },

    };
}
