/**
 * numberDrilldown — 「數字點得開」清單浮層共用元件（155b-T2）
 *
 * 形狀照 help-popover.js：獨立 Alpine.data()，不掛 mergeState。
 * 呼叫端把觸發鈕與本浮層包在同一個 wrapper，掛 x-data="numberDrilldown"。
 */
import { pathToDisplay } from './path-utils.js';
import { buildCopyText, copyItemList } from '../shared/drilldown-copy.js';

function showToast(msg, type = 'success', duration = 2500) {
    Alpine.store('toast').show(msg, type, duration);
}

export function numberDrilldown() {
    return {
        open: false,
        _title: '',
        _items: [],
        _footnote: '',

        get count() {
            return this._items.length;
        },

        get countLabel() {
            return window.t('common.number_drilldown.count', { count: this.count });
        },

        get hasFootnote() {
            return !!this._footnote;
        },

        toggle(payload = {}) {
            if (!this.open) {
                this._title = payload.title || '';
                this._items = Array.isArray(payload.items) ? payload.items : [];
                this._footnote = payload.footnote || '';
            }
            this.open = !this.open;
        },

        close() {
            this.open = false;
        },

        _fileName(path) {
            const display = pathToDisplay(path);
            const idx = Math.max(display.lastIndexOf('/'), display.lastIndexOf('\\'));
            return idx >= 0 ? display.slice(idx + 1) : display;
        },

        rowId(it) {
            return it.number || this._fileName(it.path);
        },

        copyText() {
            return buildCopyText(this._items);
        },

        async copy() {
            if (!this._items.length) return;
            const result = await copyItemList(this._items);
            if (result.ok) {
                showToast(window.t('common.number_drilldown.copy_toast', { count: result.count }), 'success');
            } else if (window.dispatchEvent(new CustomEvent('copy-fail-dump', { detail: { text: result.text }, cancelable: true }))) {
                showToast(window.t('common.number_drilldown.copy_failed'), 'error');
            }
        },
    };
}

document.addEventListener('alpine:init', () => {
    Alpine.data('numberDrilldown', numberDrilldown);
});
