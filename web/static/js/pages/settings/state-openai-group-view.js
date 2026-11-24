import { MAX_CUSTOM_GROUPS, NAME_MAX_LENGTH, openaiGroupIdOf, validateGroupName, showAdd, showTrash, labelFor, deleteConfirmParts } from './openai-group-logic.js';
import { openaiEndpointPreview } from '@/shared/openai-endpoint.js';

export function stateOpenaiGroupView() {
    return {
        openaiAddUi: { translate: { open: false, name: '', error: '' }, tags: { open: false, name: '', error: '' } },
        openaiDeleteGid: '',
        openaiGroupMax: MAX_CUSTOM_GROUPS,
        openaiTabProvider(tab) { return tab === 'tags' ? this.form.aiTagsProvider : this.form.translateProvider; },
        openaiProviderLabel(value) {
            const { key, params } = labelFor(openaiGroupIdOf(value), this.form.openaiGroups);
            return window.t(key, params);
        },
        openaiGroupOptions() {
            return this.form.openaiGroups.map(g => ({ value: 'openai:' + g.id, label: this.openaiProviderLabel('openai:' + g.id) }));
        },
        openaiGroupShowAdd(tab) { return showAdd(this.openaiTabProvider(tab), this.form.openaiBaseUrl, this.form.openaiGroups.length); },
        openaiGroupShowTrash(tab) { return showTrash(this.openaiTabProvider(tab)); },
        openaiGroupShowLimit(tab) {
            const provider = this.openaiTabProvider(tab);
            return (provider === 'openai' || openaiGroupIdOf(provider) !== null) && this.form.openaiBaseUrl.trim() !== '' && this.form.openaiGroups.length >= MAX_CUSTOM_GROUPS;
        },
        openaiGroupAddDisabled(tab) { return !this.aiConnEnabled(this.openaiTabProvider(tab)); },
        openaiAddOpen(tab) {
            Object.assign(this.openaiAddUi[tab], { open: true, name: '', error: '' });
            this.$nextTick(() => document.getElementById((tab === 'tags' ? 'tags-' : '') + 'openaiGroupName')?.focus());
        },
        openaiAddCancel(tab) { Object.assign(this.openaiAddUi[tab], { open: false, name: '', error: '' }); },
        openaiAddConfirm(tab) {
            const ui = this.openaiAddUi[tab];
            const res = validateGroupName(ui.name, this.form.openaiGroups.map(g => g.name), [window.t('settings.ai.openai_group.default_name')]);
            if (!res.ok) {
                const errors = {
                    empty: 'settings.ai.openai_group.name_error_empty',
                    too_long: 'settings.ai.openai_group.name_error_too_long',
                    reserved: 'settings.ai.openai_group.name_error_reserved',
                    duplicate: 'settings.ai.openai_group.name_error_duplicate',
                };
                ui.error = errors[res.reason];
                return;
            }
            this.openaiGroupAdd(res.name, tab);
            this.openaiAddCancel(tab);
        },
        openaiAddErrorText(tab) {
            const error = this.openaiAddUi[tab].error;
            return error ? window.t(error, { max: NAME_MAX_LENGTH }) : '';
        },
        openaiDeleteAsk(tab) {
            const gid = openaiGroupIdOf(this.openaiTabProvider(tab));
            if (gid !== null) this.openaiDeleteGid = gid;
        },
        openaiDeleteCancel() { this.openaiDeleteGid = ''; },
        async openaiDeleteConfirm() {
            const gid = this.openaiDeleteGid;
            this.openaiDeleteGid = '';
            await this.openaiGroupRemove(gid);
        },
        openaiDeleteBodyText() {
            const gid = this.openaiDeleteGid;
            const { bodyKey } = deleteConfirmParts(gid, this.form.translateProvider, this.form.aiTagsProvider);
            return window.t(bodyKey, { name: this.openaiGroupById(gid)?.name ?? '' });
        },
        openaiDeleteNoteText() {
            const { noteKey } = deleteConfirmParts(this.openaiDeleteGid, this.form.translateProvider, this.form.aiTagsProvider);
            return noteKey === null ? '' : window.t(noteKey);
        },
        openaiGroupModelsOf(gid) { return this.openaiGroupRt[gid]?.models ?? []; },
        openaiPreviewText(raw) {
            const url = openaiEndpointPreview(raw);
            return url === '' ? '' : window.t('settings.ai.openai_group.preview', { url });
        },
    };
}
