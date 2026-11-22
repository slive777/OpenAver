/** 對外名單：tbItems、tbSuggestions、tbInput、tbError、tbBusy、tbLoading、tbCollapsed；
 * tbLoad、tbToggle、tbChips、tbAddFromInput、tbAddSuggestion、tbAdd、tbRemove。 */
import { errorKeyFor, suggestionChips } from './tag-blacklist-logic.js';

const BASE = '/api/tag-blacklist';
async function request(url, options) {
    try {
        const response = await fetch(url, options);
        return await response.json();
    } catch {
        return { success: false };
    }
}

export function tagBlacklist() {
    return {
        tbItems: [], tbSuggestions: [], tbInput: '', tbError: '', tbBusy: false, tbLoading: false, tbCollapsed: true,
        init() { this.tbLoad(); },
        async tbLoad() {
            this.tbLoading = true;
            const result = await request(BASE);
            if (result?.success) {
                this.tbItems = result.items;
                this.tbSuggestions = result.suggestions;
                this.tbError = '';
            } else this.tbError = window.t('scanner.tag_blacklist.error.load_failed');
            this.tbLoading = false;
        },
        tbToggle() { this.tbCollapsed = !this.tbCollapsed; },
        tbChips() { return suggestionChips(this.tbSuggestions, this.tbItems); },
        async tbAddFromInput() {
            if (await this.tbAdd(this.tbInput)) this.tbInput = '';
        },
        async tbAddSuggestion(name) {
            const chip = this.tbChips().find(item => item.name === name);
            if (!chip || chip.added || this.tbBusy) return;
            await this.tbAdd(name);
        },
        async tbAdd(value) {
            if (this.tbBusy) return false;
            const name = String(value).trim();
            this.tbBusy = true;
            try {
                const result = await request(BASE, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) });
                if (!result?.success) {
                    this.tbError = window.t(errorKeyFor(result?.code), { name });
                    return false;
                }
                this.tbItems = result.items;
                this.tbError = '';
                Alpine.store('toast').show(window.t('scanner.tag_blacklist.toast.add_success', { name }), 'success');
                return true;
            } finally { this.tbBusy = false; }
        },
        async tbRemove(item) {
            if (this.tbBusy) return;
            this.tbBusy = true;
            try {
                const result = await request(BASE + '/' + encodeURIComponent(item.key), { method: 'DELETE' });
                if (!result?.success) {
                    this.tbError = window.t('scanner.tag_blacklist.error.remove_failed');
                    return;
                }
                this.tbItems = this.tbItems.filter(i => i.key !== item.key);
                this.tbError = '';
                Alpine.store('toast').show(window.t('scanner.tag_blacklist.toast.remove_success', { name: item.name }), 'success');
            } finally { this.tbBusy = false; }
        },
    };
}
