/**
 * helpPopover — 「? 說明浮層」共用元件（131b-T4）
 *
 * 掛在**既有的** .popover-anchor / wrapper 元素上，不新增任何 DOM
 * （新增一層 <div> 會動到 position: relative 的定位鏈與 flex 佈局）。
 *
 * 這支是 CLAUDE.md「新前端功能：獨立元件 vs mergeState 分片」③ 的可抄樣板：
 * 觸發鈕與它自己的畫面同在一個子樹（條件 A）、外面沒有任何人需要知道它開沒開（條件 B）、
 * 不跨 x-if / x-for 邊界（條件 C）——三條全過才做成獨立元件。
 */
export function helpPopover() {
    return {
        open: false,
        toggle() { this.open = !this.open; },
        close() { this.open = false; },
    };
}

/**
 * tagHintPopover — scanner 別名卡／黑名單卡兩顆 (?) 專用（205b-T6 owner F1）。
 *
 * 為什麼另開新元件：兩顆浮窗在收合卡片（只有標題列高）內用絕對定位一定被
 * `.actress-alias-card { overflow: hidden }` 裁掉；dim 主題卡片又有
 * backdrop-filter，會成為 fixed 的 containing block，單用 fixed 仍不保險。
 * 所以浮窗 `x-teleport="body"` 逃出卡片，`position: fixed` 由 `place()` 依
 * 按鈕 `getBoundingClientRect()` 算座標並 clamp 進 viewport。
 * `open`／`toggle`／`close` 語意與 `helpPopover` 相同；既有 helpPopover 零改動。
 */
export function tagHintPopover() {
    return {
        open: false,
        pos: { left: 0, top: 0, width: 352 },
        _btn: null,
        toggle(event) {
            this.open = !this.open;
            if (this.open) {
                const btn = event?.currentTarget?.getBoundingClientRect
                    ? event.currentTarget
                    : event?.target?.closest?.('button');
                this._btn = btn ?? null;
                this.$nextTick(() => this.place());
            }
        },
        close() { this.open = false; },
        place() {
            const rect = this._btn?.getBoundingClientRect?.();
            if (!rect) return;
            const margin = 16;
            const gap = 8;
            const width = Math.min(352, window.innerWidth - margin * 2);
            const height = this.$refs?.pop?.offsetHeight || 120;
            let left = rect.left + rect.width / 2 - width / 2;
            left = Math.max(margin, Math.min(left, window.innerWidth - margin - width));
            let top = rect.bottom + gap;
            if (top + height > window.innerHeight - margin) {
                top = rect.top - gap - height;
            }
            top = Math.max(margin, Math.min(top, window.innerHeight - margin - height));
            this.pos = { left, top, width };
        },
    };
}

document.addEventListener('alpine:init', () => {
    Alpine.data('helpPopover', helpPopover);
});
