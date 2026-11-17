/**
 * adv-edit-data-logic.js — adv-edit data-section pure functions (TASK-200c-T5)
 *
 * Eight-field table, date/title validation, actress split, tag draft rules.
 * Pure functions only: browser-free, no DOM access, no requests.
 */

import { parseActorsInput } from '@/shared/parse-actors-input.js';

function normalizeBase(base) {
    return (base || []).map((item) => (
        typeof item === 'string' ? { text: item, from_filename: false } : { text: item.text, from_filename: !!item.from_filename }
    ));
}

function cloneDraft(draft) {
    return { kind: draft.kind, added: [...draft.added], removed: [...draft.removed] };
}

export function validateDate(raw) {
    const s = String(raw ?? '').trim();
    if (!s) return null;
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
    if (!m) return 'invalid_date';
    const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])));
    if (d.getUTCMonth() !== Number(m[2]) - 1 || d.getUTCDate() !== Number(m[3])) return 'invalid_date';
    return null;
}

export function tagRemovable(tag) {
    return !(tag && tag.from_filename);
}

export function isComposingEnter(e) {
    if (!e) return false;
    return e.isComposing === true;
}

export function tagDraftNew(kind) {
    return { kind, added: [], removed: [] };
}

export function tagDraftRemove(draft, base, text) {
    const t = String(text ?? '').trim();
    if (!t) return cloneDraft(draft);
    const items = normalizeBase(base);
    const hit = items.find((x) => x.text === t);
    if (hit && hit.from_filename) return cloneDraft(draft);
    if (draft.added.includes(t)) {
        const next = cloneDraft(draft);
        next.added = draft.added.filter((x) => x !== t);
        return next;
    }
    if (hit && !draft.removed.includes(t)) {
        const next = cloneDraft(draft);
        next.removed = [...draft.removed, t];
        return next;
    }
    return cloneDraft(draft);
}

export function tagDraftAdd(draft, base, text) {
    const t = String(text ?? '').trim();
    if (!t) return cloneDraft(draft);
    if (draft.removed.includes(t)) return { ...cloneDraft(draft), removed: draft.removed.filter((x) => x !== t) };
    const items = normalizeBase(base);
    const hit = items.find((x) => x.text === t);
    if (hit) return cloneDraft(draft);
    if (draft.added.includes(t)) return cloneDraft(draft);
    const next = cloneDraft(draft);
    next.added = [...draft.added, t];
    return next;
}

export function tagDraftView(base, draft) {
    const items = normalizeBase(base);
    const removed = new Set(draft.removed);
    const view = items.filter((x) => !removed.has(x.text)).map((x) => ({ text: x.text, from_filename: x.from_filename }));
    for (const t of draft.added) view.push({ text: t, from_filename: false });
    return view;
}

export function tagDraftPayload(draft) {
    if (draft.added.length === 0 && draft.removed.length === 0) return null;
    return { add: [...draft.added], remove: [...draft.removed] };
}

export function validateNfoTagInput(text) {
    const t = String(text ?? '').trim();
    if (!t) return 'empty';
    if (t.includes(',')) return 'tag_invalid';
    return null;
}

function stringToValue(raw) {
    return String(raw ?? '').trim();
}

function readString(values, key) {
    if (!values) return '';
    const v = values[key];
    if (v === null || v === undefined) return '';
    return v;
}

export const ADV_EDIT_DATA_FIELDS = [
    {
        key: 'title',
        kind: 'text',
        required: true,
        read: (values) => readString(values, 'title'),
        toValue: (raw) => stringToValue(raw),
        validate: (raw) => (stringToValue(raw) ? null : 'title_empty'),
    },
    {
        key: 'original_title',
        kind: 'text',
        required: false,
        read: (values) => readString(values, 'original_title'),
        toValue: (raw) => stringToValue(raw),
        validate: () => null,
    },
    {
        key: 'maker',
        kind: 'text',
        required: false,
        read: (values) => readString(values, 'maker'),
        toValue: (raw) => stringToValue(raw),
        validate: () => null,
    },
    {
        key: 'series',
        kind: 'text',
        required: false,
        read: (values) => readString(values, 'series'),
        toValue: (raw) => stringToValue(raw),
        validate: () => null,
    },
    {
        key: 'actresses',
        kind: 'actors',
        required: false,
        read: (values) => {
            if (!values) return '';
            const v = values.actresses;
            if (!v) return '';
            if (Array.isArray(v)) return v.join('、');
            return v;
        },
        toValue: (raw) => parseActorsInput(stringToValue(raw)),
        validate: () => null,
    },
    {
        key: 'release_date',
        kind: 'date',
        required: false,
        read: (values) => readString(values, 'release_date'),
        toValue: (raw) => stringToValue(raw),
        validate: (raw) => validateDate(raw),
    },
    {
        key: 'plot',
        kind: 'textarea',
        required: false,
        read: (values) => readString(values, 'plot'),
        toValue: (raw) => stringToValue(raw),
        validate: () => null,
    },
    {
        key: 'plot_translation',
        kind: 'textarea',
        required: false,
        read: (values) => readString(values, 'plot_translation'),
        toValue: (raw) => stringToValue(raw),
        validate: () => null,
    },
];

export const ADV_EDIT_DATA_ERROR_KEYS = {
    invalid_date: 'showcase.adv_edit.data.err_invalid_date',
    title_empty: 'showcase.adv_edit.data.err_title_empty',
    tag_invalid: 'showcase.adv_edit.data.err_tag_invalid',
    tag_hidden: 'showcase.adv_edit.data.err_tag_hidden',
    nfo_write_failed: 'showcase.adv_edit.data.err_write_failed',
    db_write_failed: 'showcase.adv_edit.data.err_db_failed',
    not_found: 'showcase.adv_edit.data.err_generic',
    invalid_path: 'showcase.adv_edit.data.err_generic',
    invalid_field: 'showcase.adv_edit.data.err_generic',
    invalid_value: 'showcase.adv_edit.data.err_generic',
    borrowed: 'showcase.adv_edit.data.note_borrowed',
    no_nfo: 'showcase.adv_edit.data.note_no_nfo',
    readonly_no_nfo: 'showcase.adv_edit.data.note_readonly_no_nfo',
    nfo_ambiguous: 'showcase.adv_edit.data.note_nfo_ambiguous',
    nfo_unreadable: 'showcase.adv_edit.data.note_nfo_unreadable',
    unreachable: 'showcase.adv_edit.data.note_unreachable',
    nfo_link_outside: 'showcase.adv_edit.data.note_nfo_link_outside',
};

export function errorKeyOf(code) {
    return Object.hasOwn(ADV_EDIT_DATA_ERROR_KEYS, code) ? ADV_EDIT_DATA_ERROR_KEYS[code] : ADV_EDIT_DATA_ERROR_KEYS.not_found;
}

export function errorIsInline(code) {
    return ['invalid_date', 'title_empty', 'tag_invalid', 'tag_hidden'].includes(code);
}
