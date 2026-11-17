import { ADV_EDIT_DATA_FIELDS, errorKeyOf, errorIsInline, isComposingEnter, tagDraftNew, tagDraftRemove, tagDraftAdd, tagDraftView, tagDraftPayload, tagRemovable, validateNfoTagInput } from './adv-edit-data-logic.js';
import { parseWorkTags } from './lbx-logic.js';

export function stateAdvEditData() {
    return {
        advEditData: null,
        advEditDataLoading: false,
        advEditDataDraft: '',
        advEditDataError: '',
        advEditDataTagDraft: null,
        advEditDataTagInput: '',
        _advEditDataGen: 0,

        onAdvEditOpen() {
            this.advEditData = null;
            this.advEditDataDraft = '';
            this.advEditDataError = '';
            this.advEditDataTagDraft = null;
            this.advEditDataTagInput = '';
            this.loadAdvEditData();
        },
        onAdvEditClose() {
            this._advEditDataGen++;
            this.advEditDataLoading = false;
            this.advEditData = null;
            this.advEditDataDraft = '';
            this.advEditDataError = '';
            this.advEditDataTagDraft = null;
            this.advEditDataTagInput = '';
        },
        onAdvEditCellCancel() {
            const cell = String(this._advEditCell);
            if (!cell.startsWith('data:')) return false;
            if (cell.endsWith('+')) { this.cancelAdvEditTagInput(); return true; }
            this.cancelAdvEditData();
            return true;
        },
        onAdvEditSynced() { this.loadAdvEditData(); },
        async loadAdvEditData() {
            if (!this.advEditOpen) return;
            const path = this.currentLightboxVideo?.path;
            if (!path) { this.advEditData = null; return; }
            const gen = ++this._advEditDataGen;
            this.advEditDataLoading = true;
            this.advEditDataError = '';
            try {
                const resp = await fetch(`/api/showcase/video/edit-data?path=${encodeURIComponent(path)}`);
                const data = await resp.json();
                if (gen !== this._advEditDataGen) return;   // 200c-T6a：晚到的載入回應（已關窗、重開或重載）不寫畫面
                this.advEditData = resp.ok && data?.success === true && (data.state === 'ok' || data.state === 'blocked') ? data : null;
            } catch (e) {
                if (gen === this._advEditDataGen) this.advEditData = null;
            } finally {
                if (gen === this._advEditDataGen) this.advEditDataLoading = false;
            }
        },
        advEditDataEditing() {
            return String(this._advEditCell).startsWith('data:');
        },
        startAdvEditData(key) {
            const field = ADV_EDIT_DATA_FIELDS.find(f => f.key === key);
            if (!this.advEditOpen || this.advEditData?.state !== 'ok' || this._advEditCell || this._advEditBusy || this.advEditDataLoading || !field) return;
            this._advEditCell = 'data:' + key;
            this.advEditDataDraft = field.read(this.advEditData.values);
            this.advEditDataError = '';
            this.$nextTick?.(() => this.$refs?.advEditDataInput?.focus());
        },
        cancelAdvEditData() {
            if (String(this._advEditCell).startsWith('data:')) this._advEditCell = '';
            this.advEditDataDraft = '';
            this.advEditDataError = '';
            this.advEditDataTagDraft = null;
            this.advEditDataTagInput = '';
        },
        onAdvEditDataEnter(e) {
            if (isComposingEnter(e)) return;
            this.confirmAdvEditData();
        },
        async confirmAdvEditData() {
            if (!this.advEditOpen || this._advEditBusy || !String(this._advEditCell).startsWith('data:')) return;
            const field = ADV_EDIT_DATA_FIELDS.find(f => f.key === this._advEditCell.slice(5));
            if (!field) return;
            const code = field.validate(this.advEditDataDraft);
            if (code !== null) { this.advEditDataError = code; return; }
            const video = this.currentLightboxVideo, path = video.path, cell = this._advEditCell;
            const value = field.toValue(this.advEditDataDraft), gen = this._advEditDataGen;
            this._advEditBusy = 'data';
            try {
                let data = null;
                try {
                    const resp = await fetch('/api/showcase/video/edit-field', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path, field: field.key, value }) });
                    data = await resp.json().catch(() => null);
                } catch (e) { data = null; }
                if (gen !== this._advEditDataGen) return;   // 200c-T6a：晚到的寫入回應（已關窗或重開）不寫畫面、不 toast
                const stillEditing = this._advEditCell === cell;
                if (data?.success === true) {
                    this.advEditData = { ...this.advEditData, values: { ...this.advEditData.values, ...data.values } };
                    if (stillEditing) this.cancelAdvEditData();
                    await this.refreshVideoData(video);
                    if (gen !== this._advEditDataGen) return;
                } else if (errorIsInline(data?.error)) {
                    if (stillEditing) this.advEditDataError = data.error;
                } else {
                    if (stillEditing) this.cancelAdvEditData();
                    this.showToast(window.t(errorKeyOf(data?.error)), 'error');
                }
            } finally {
                if (gen === this._advEditDataGen) this._advEditBusy = '';
            }
        },
        advEditTagKinds() {
            return this.advEditData ? ['tags', 'utags'] : this.advEditDataLoading ? [] : ['utags'];
        },
        advEditTagLabel(kind) {
            return kind === 'tags' ? window.t('showcase.adv_edit.data.label_tags') : window.t('showcase.adv_edit.data.label_utags');
        },
        advEditTagsCanEdit(kind) { return kind === 'utags' ? !!this.currentLightboxVideo?.path : this.advEditData?.state === 'ok'; },
        advEditTagsEditing(kind) { return this._advEditCell === 'data:' + kind || this._advEditCell === 'data:' + kind + '+'; },
        advEditTagBase(kind) {
            if (kind === 'utags') return this.currentLightboxVideo?.user_tags || [];
            return this.advEditData?.state === 'ok' ? this.advEditData.tags || [] : parseWorkTags(this.currentLightboxVideo);
        },
        advEditTagsView(kind) {
            const draft = this.advEditDataTagDraft;
            return tagDraftView(this.advEditTagBase(kind), draft?.kind === kind ? draft : tagDraftNew(kind));
        },
        advEditTagRemovable(tag) { return tagRemovable(tag); },
        startAdvEditTags(kind) {
            if (!['tags', 'utags'].includes(kind) || !this.advEditOpen || this._advEditCell || this._advEditBusy || this.advEditDataLoading || !this.advEditTagsCanEdit(kind)) return;
            this._advEditCell = 'data:' + kind;
            this.advEditDataTagDraft = tagDraftNew(kind);
            this.advEditDataTagInput = '';
            this.advEditDataError = '';
        },
        removeAdvEditTag(kind, text) {
            const draft = this.advEditDataTagDraft;
            if (this._advEditBusy || !draft || draft.kind !== kind || !this.advEditTagsEditing(kind)) return;
            this.advEditDataTagDraft = tagDraftRemove(draft, this.advEditTagBase(kind), text);
        },
        startAdvEditTagInput(kind) {
            if (this._advEditCell !== 'data:' + kind || this._advEditBusy) return;
            this._advEditCell = 'data:' + kind + '+';
            this.advEditDataTagInput = '';
            this.advEditDataError = '';
            this.$nextTick?.(() => this.$refs?.advEditTagInput?.focus());
        },
        onAdvEditTagInputEnter(kind, e) {
            if (isComposingEnter(e)) return;
            this.commitAdvEditTagInput(kind);
        },
        commitAdvEditTagInput(kind) {
            const draft = this.advEditDataTagDraft;
            if (this._advEditCell !== 'data:' + kind + '+' || draft?.kind !== kind) return true;
            const text = String(this.advEditDataTagInput).trim();
            if (text && kind === 'tags' && validateNfoTagInput(text) === 'tag_invalid') { this.advEditDataError = 'tag_invalid'; return false; }
            if (text) this.advEditDataTagDraft = tagDraftAdd(draft, this.advEditTagBase(kind), text);
            this._advEditCell = 'data:' + kind;
            this.advEditDataTagInput = '';
            return true;
        },
        cancelAdvEditTagInput() {
            const cell = String(this._advEditCell);
            if (!cell.startsWith('data:') || !cell.endsWith('+')) return;
            this._advEditCell = cell.slice(0, -1);
            this.advEditDataTagInput = '';
            this.advEditDataError = '';
        },
        cancelAdvEditTags() { this.cancelAdvEditData(); },
        async confirmAdvEditTags(kind) {
            if (!this.advEditOpen || this._advEditBusy || !this.advEditTagsEditing(kind)) return;
            if (String(this._advEditCell).endsWith('+') && this.commitAdvEditTagInput(kind) === false) return;
            const payload = tagDraftPayload(this.advEditDataTagDraft);
            if (payload === null) { this.cancelAdvEditData(); return; }
            const video = this.currentLightboxVideo, path = video.path, cell = this._advEditCell, gen = this._advEditDataGen;
            this._advEditBusy = 'data';
            try {
                if (kind === 'utags') {
                    await this._applyUserTagsChange(payload);
                    if (gen !== this._advEditDataGen) return;
                    if (this._advEditCell === cell) this.cancelAdvEditData();
                    return;
                }
                let data = null;
                try {
                    const resp = await fetch('/api/showcase/video/edit-field', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path, field: 'tags', add: payload.add, remove: payload.remove }) });
                    data = await resp.json().catch(() => null);
                } catch (e) { data = null; }
                if (gen !== this._advEditDataGen) return;
                const stillEditing = this._advEditCell === cell;
                if (data?.success === true) {
                    if (Array.isArray(data.tags)) this.advEditData = { ...this.advEditData, tags: data.tags };
                    if (stillEditing) this.cancelAdvEditData();
                    await this.refreshVideoData(video);
                    if (gen !== this._advEditDataGen) return;
                } else if (errorIsInline(data?.error)) {
                    if (stillEditing) this.advEditDataError = data.error;
                } else {
                    if (stillEditing) this.cancelAdvEditData();
                    this.showToast(window.t(errorKeyOf(data?.error)), 'error');
                }
            } finally {
                if (gen === this._advEditDataGen) this._advEditBusy = '';
            }
        },
        advEditDataFields() {
            if (this.advEditData?.state === 'ok') return ADV_EDIT_DATA_FIELDS;
            if (this.advEditData?.state === 'blocked') return ADV_EDIT_DATA_FIELDS.filter(f => f.kind !== 'textarea');
            return [];
        },
        advEditDataValue(key) {
            const field = ADV_EDIT_DATA_FIELDS.find(f => f.key === key);
            if (!field) return '';
            if (this.advEditData?.state === 'ok') return field.read(this.advEditData.values);
            if (this.advEditData?.state === 'blocked') {
                const value = this.currentLightboxVideo?.[key] ?? '';
                return key === 'actresses' ? String(value).replaceAll(',', '、') : value;
            }
            return '';
        },
        advEditDataNoteText() { return this.advEditData?.state === 'blocked' ? window.t(errorKeyOf(this.advEditData.reason)) : ''; },
        advEditDataErrorText() { return this.advEditDataError ? window.t(errorKeyOf(this.advEditDataError)) : ''; },
    };
}
