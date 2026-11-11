/**
 * state-lightbox-pop.js — Showcase ESM（199a-T3）
 *
 * 影片燈箱浮層底座：單槽（同一時間最多一個浮層）＋ 單一 DOM 宿主（.lbx-pop-host，.showcase-lightbox 的直接子節點）。
 * 第一個消費者是規格帶版本膠囊的檔案提示 verTip；T4–T7 的片名／原文／女優／簡介等浮層共用這個底座。
 * mergeState 分片（plan-199a CD-199a-3／4）：不定義 init()（FE-ALPINE-05）、頂層 key 一律 lbxPop／_lbxPop 前綴；
 * 分片內不掛任何 $watch（換片收合的 watch 在 state-base.js，與 187b 簡介層同一個位置）。
 * 時序：定位量測延到 $nextTick（x-if 內容那時才存在，FE-ALPINE-03），用遞增整數世代 _lbxPopGen 擋遲到的定位，
 * 不比對物件身分（Alpine Proxy，FE-ALPINE-14）。
 * 分片頂層不 import 會寫 window 的檔、不讀 window／document（FE-GUARD-11）：window.pathToDisplay 在呼叫時才讀。
 */

import { versionsOf } from './work-versions.js';
import { bandParts, formatRuntime, placePop, isOutsidePop, menuItems, popPlacement, hasDistinctOtitle } from './lbx-logic.js';

const LBX_POP_HOVER_CLOSE_MS = 160;
const LBX_POP_ANCHOR_SEL = '[data-lbx-anchor]';

// 片名／原文是塊級單行省略號元素：內容寬超過可視寬才算被截斷（FE-REVIEW-16：inline 元素量不到，恆 0）
function isTruncated(el) {
    return !!el && el.scrollWidth > el.clientWidth + 1;
}

export function stateLightboxPop() {
    return {
        // null | { kind, mode: 'hover'|'click', anchorKey, placed, style: { left, top, maxHeight? } }
        lbxPop: null,
        _lbxPopAnchorEl: null,
        _lbxPopGen: 0,
        _lbxPopTimer: null,

        _lbxPopClearTimer() {
            if (this._lbxPopTimer) {
                clearTimeout(this._lbxPopTimer);
                this._lbxPopTimer = null;
            }
        },

        // 取代現有浮層（單槽）。anchorEl 只存起來，量測延到 $nextTick。
        lbxPopOpen(kind, anchorEl, { mode = 'click', anchorKey = '' } = {}) {
            this._lbxPopClearTimer();
            const gen = ++this._lbxPopGen;
            this._lbxPopAnchorEl = anchorEl || null;
            this.lbxPop = { kind, mode, anchorKey, placed: false, style: { left: '0px', top: '0px' } };
            this.$nextTick?.(() => this._lbxPopPlace(gen));
        },

        // 量完一次寫入（整包替換才會重繪）；任何量測值取不到 → 維持不可見、不 throw
        _lbxPopPlace(gen) {
            if (gen !== this._lbxPopGen || !this.lbxPop) return;
            const anchor = this._lbxPopAnchorEl;
            const panel = this.$refs?.lbxPopHost?.querySelector?.('.lbx-pop');
            if (!panel || !anchor || typeof anchor.getBoundingClientRect !== 'function') return;
            // 限定在燈箱內查封面（搜尋頁兩個燈箱共用 .showcase-lightbox，FE-JS-03）
            const coverEl = anchor.closest?.('.lightbox-content')?.querySelector('.lightbox-cover');
            if (!coverEl) return;
            const anchorRect = anchor.getBoundingClientRect();
            const coverBottom = coverEl.getBoundingClientRect().bottom;
            const popSize = { w: panel.offsetWidth, h: panel.offsetHeight };
            const vw = window.innerWidth;
            const vh = window.innerHeight;
            const nums = [anchorRect.left, anchorRect.right, anchorRect.top, anchorRect.bottom, coverBottom, popSize.w, popSize.h, vw, vh];
            if (!nums.every(Number.isFinite)) return;
            const placement = popPlacement(this.lbxPop.kind);
            const pos = placePop({
                anchorRect,
                coverBottom,
                vw,
                vh,
                popSize,
                mode: placement.mode,
                align: placement.align,
                interactive: this.lbxPop.mode === 'click',
            });
            const style = { left: pos.left + 'px', top: pos.top + 'px' };
            if (pos.maxHeight !== undefined) style.maxHeight = pos.maxHeight + 'px';
            this.lbxPop = { ...this.lbxPop, placed: true, style };
        },

        // 同 kind＋同 anchorKey＋click 模式 → 收；否則開
        lbxPopToggle(kind, anchorEl, opts) {
            const cur = this.lbxPop;
            if (cur && cur.kind === kind && cur.mode === 'click' && cur.anchorKey === (opts?.anchorKey ?? '')) {
                this.lbxPopClose();
                return;
            }
            this.lbxPopOpen(kind, anchorEl, opts);
        },

        // lbxPop 已是 null 時零成本早退（@resize.window 與 closeLightbox 會在浮層沒開時也呼叫）
        lbxPopClose({ restoreFocus = false } = {}) {
            this._lbxPopClearTimer();
            this._lbxPopGen++;
            const cur = this.lbxPop;
            if (!cur) return;
            const anchor = this._lbxPopAnchorEl;
            this.lbxPop = null;
            this._lbxPopAnchorEl = null;
            if (restoreFocus && cur.mode === 'click' && anchor && anchor.isConnected) anchor.focus?.();
        },

        // hover／鍵盤焦點開浮層（綁 @pointerenter 與 @focus）。忽略條件全在這一處。
        lbxPopHoverStart(e, kind, anchorKey) {
            const el = e?.currentTarget;
            if (!el) return;
            if (this._lightboxAnimating) return;
            if (this.lbxPop && this.lbxPop.mode === 'click') return;
            if (e.type === 'pointerenter') {
                if (e.pointerType !== 'mouse' && e.pointerType !== 'pen') return;
                // hover 能力檢查只對指標；鍵盤 focus（:focus-visible）在無 hover 裝置（平板接鍵盤）上也要能開
                if (window.matchMedia?.('(any-hover: hover)')?.matches === false) return;
            }
            if (e.type === 'focus') {
                let visible = false;
                try { visible = !!el.matches?.(':focus-visible'); } catch (_) { visible = false; }
                if (!visible) return;
            }
            if ((kind === 'title' || kind === 'otitle') && !isTruncated(el)) return;
            this._lbxPopClearTimer();
            const cur = this.lbxPop;
            if (cur && cur.mode === 'hover' && cur.kind === kind && cur.anchorKey === anchorKey) return;
            this.lbxPopOpen(kind, el, { mode: 'hover', anchorKey });
        },

        // 離開錨點：只在 hover 模式、160ms 後才收；期間再進任何錨點就不收
        lbxPopHoverEnd() {
            if (!this.lbxPop || this.lbxPop.mode !== 'hover') return;
            this._lbxPopClearTimer();
            this._lbxPopTimer = setTimeout(() => {
                this._lbxPopTimer = null;
                if (this.lbxPop && this.lbxPop.mode === 'hover') this.lbxPopClose();
            }, LBX_POP_HOVER_CLOSE_MS);
        },

        // 主 session 裁決（觸控／無 hover 裝置）：點「目前這顆」版本膠囊 → 開關 verTip（click 模式）；
        // 點別顆照舊切版本。綁在膠囊的 @click.capture，必須先於 T2 的 @click.stop="switchLightboxVersion(...)" 執行，
        // 否則切版本後 currentLightboxVideo 已變，會把「剛切過去的那顆」誤判成目前這顆。
        lbxVerCapTap(e, path) {
            const el = e?.currentTarget;
            if (!el || path !== this.currentLightboxVideo?.path) return;
            const touch = e.pointerType === 'touch' || window.matchMedia?.('(hover: none)')?.matches === true;
            if (!touch) return;
            this.lbxPopToggle('verTip', el, { mode: 'click', anchorKey: path });
        },

        // 觸控／無 hover 裝置：點片名／原文開關全文浮層（click 模式——hover 模式會被觸控放開後的 pointerleave 立刻收掉）。
        // 滑鼠使用者點片名什麼都不發生（hover 已開，click 再 toggle 會把它關掉）。未截斷的片名不開。
        lbxPopTapOpen(e, kind, anchorKey) {
            const el = e?.currentTarget;
            if (!el) return;
            const noHover = window.matchMedia?.('(any-hover: hover)')?.matches === false;
            if (e.pointerType !== 'touch' && !noHover) return;
            if ((kind === 'title' || kind === 'otitle') && !isTruncated(el)) return;
            this.lbxPopToggle(kind, el, { mode: 'click', anchorKey });
        },

        // ⋯ 選單項目（條件在 lbx-logic.menuItems；模板只讀 lbxMenuHas，不再各自寫一份 gate）
        lbxMenuItems() {
            return menuItems(this.currentLightboxVideo, {
                sampleCount: (this.currentLightboxVideo?.sample_images || []).length,
                trVisible: this.lbTrShowOnTitle() || this.lbTrShowOnOtitle(),
                hasPath: !!this.currentLightboxVideo?.path,
            });
        },

        lbxMenuHas(id) {
            return this.lbxMenuItems().some((i) => i.id === id);
        },

        lbxHasOtitle() {
            return hasDistinctOtitle(this.currentLightboxVideo);
        },

        // 燈箱根節點 @pointerdown.window：點在浮層與錨點之外 → 收（不還焦點）
        lbxPopOnPointerDown(e) {
            if (!this.lbxPop) return;
            const panel = this.$refs?.lbxPopHost?.querySelector?.('.lbx-pop');
            if (isOutsidePop(e?.target, panel, LBX_POP_ANCHOR_SEL)) this.lbxPopClose();
        },

        lbxPopIs(kind, anchorKey) {
            return !!this.lbxPop && this.lbxPop.kind === kind && this.lbxPop.anchorKey === anchorKey;
        },

        // verTip 內容：檔名（路徑最後一段）＋ 編碼／實際片長／大小（與規格帶同源 bandParts，去掉等級）
        lbxVerTipParts() {
            const key = this.lbxPop?.anchorKey;
            const ver = versionsOf(this.currentLightboxVideo).find((x) => x.path === key);
            if (!ver) return { name: '', specs: [] };
            const shown = typeof window.pathToDisplay === 'function' ? window.pathToDisplay(ver.path) : ver.path;
            const name = String(shown || '').split(/[\\/]/).pop();
            const specs = bandParts(ver, { formatSize: (b) => this.formatSize(b), formatRuntime })
                .filter((p) => p.id !== 'tier')
                .map((p) => p.text);
            return { name, specs };
        },
    };
}
