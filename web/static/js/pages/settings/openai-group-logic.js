/**
 * openai-group-logic.js — multiple OpenAI-compatible group rules (pure logic, no DOM, no Alpine, no window)
 *
 * CD-206-8 (name gates / provider values), CD-206-18 (openaiGroupIdOf shares
 * the 11-vector table with the backend parser), W9/W10 (add/delete fallback).
 */

export const MAX_CUSTOM_GROUPS = 5;

export const NAME_MAX_LENGTH = 30;

const GROUP_ID_RE = /^oc[0-9a-f]{8}$/;

const norm = (s) => String(s ?? '').trim().toLowerCase();

export function openaiGroupIdOf(provider) {
    if (typeof provider !== 'string') return null;
    if (!provider.startsWith('openai:')) return null;
    const id = provider.slice('openai:'.length);
    if (!GROUP_ID_RE.test(id)) return null;
    return id;
}

export function newGroupId(rand = () => globalThis.crypto.getRandomValues(new Uint32Array(1))[0]) {
    return 'oc' + (rand() >>> 0).toString(16).padStart(8, '0');
}

export function validateGroupName(name, existingNames, reservedNames) {
    const value = String(name ?? '').trim();
    if (value === '') return { ok: false, reason: 'empty' };
    if ([...value].length > NAME_MAX_LENGTH) return { ok: false, reason: 'too_long' };
    if ((reservedNames ?? []).some((n) => norm(n) === norm(value))) return { ok: false, reason: 'reserved' };
    const key = norm(value);
    if ((existingNames ?? []).some((n) => norm(n) === key)) return { ok: false, reason: 'duplicate' };
    return { ok: true, name: value };
}

export function canAdd(defaultBaseUrl, customCount) {
    return String(defaultBaseUrl ?? '').trim() !== '' && customCount < MAX_CUSTOM_GROUPS;
}

export function showAdd(provider, defaultBaseUrl, customCount) {
    return (provider === 'openai' || openaiGroupIdOf(provider) !== null) && canAdd(defaultBaseUrl, customCount);
}

export function showTrash(provider) {
    return openaiGroupIdOf(provider) !== null;
}

export function labelFor(groupId, groups) {
    const list = groups ?? [];
    if (list.length === 0) return { key: 'settings.translate.openai_compatible', params: {} };
    const found = list.find((g) => g.id === groupId);
    if (!found) return { key: 'settings.ai.openai_group.label_default', params: {} };
    return { key: 'settings.ai.openai_group.label_named', params: { name: found.name } };
}

export function fallbackAfterDelete(provider, deletedGroupId) {
    if (openaiGroupIdOf(provider) === deletedGroupId) return 'openai';
    return provider;
}

export function deleteConfirmParts(groupId, translateProvider, tagsProvider) {
    const ref = 'openai:' + String(groupId ?? '');
    const both = translateProvider === ref && tagsProvider === ref;
    if (both) return { bodyKey: 'settings.ai.openai_group.delete_confirm', noteKey: 'settings.ai.openai_group.delete_confirm_also_used' };
    return { bodyKey: 'settings.ai.openai_group.delete_confirm', noteKey: null };
}

export function newGroupDraft() {
    return { baseUrl: '', model: '', useCustomModel: false };
}
