import { createSecretField, startReplace, requestClear, wireValue, previewText, isDirty, afterSave } from './secret-field-logic.js';
import { openaiGroupIdOf } from './openai-group-logic.js';
import { maskSecret } from '@/shared/secret-mask.js';

export const SECRET_PATHS = {
    gemini: 'translate.gemini.api_key',
    openai: 'translate.openai.api_key',
    openaiOfficial: 'translate.openai_official.api_key',
    claude: 'translate.claude.api_key',
    aiSimilar: 'ai_services.image_similar.api_key',
    aiFaces: 'ai_services.faces.api_key',
    metatube: 'metatube.token',
};

// MetaTube token is persisted by /api/settings/metatube/connect, not global save.
const CONNECT_ONLY = new Set(['metatube']);

function getPath(obj, dotted) {
    const value = dotted.split('.').reduce((current, key) => current?.[key], obj);
    return typeof value === 'string' ? value : '';
}

function setPath(obj, dotted, value) {
    const keys = dotted.split('.');
    const last = keys.pop();
    for (const key of keys) {
        if (!obj[key] || typeof obj[key] !== 'object') obj[key] = {};
        obj = obj[key];
    }
    obj[last] = value;
}

function isGroupId(gid) {
    return typeof gid === 'string' && openaiGroupIdOf('openai:' + gid) === gid;
}

function secretPathOf(id) {
    if (Object.hasOwn(SECRET_PATHS, id)) return SECRET_PATHS[id];
    if (isGroupId(id)) return `translate.openai_custom.${id}.api_key`;
    return null;
}

function customGroupIds(config) {
    const groups = config?.translate?.openai_custom;
    if (!groups || typeof groups !== 'object') return [];
    return Object.keys(groups).filter(isGroupId);
}

export function stateSecrets() {
    return {
        secretFields: Object.fromEntries(Object.keys(SECRET_PATHS).map(id => [id, createSecretField('')])),
        secretsLoad(config) {
            this.secretFields = Object.fromEntries([
                ...Object.entries(SECRET_PATHS).map(([id, path]) => [id, createSecretField(getPath(config, path))]),
                ...customGroupIds(config).map((gid) => [gid, createSecretField(getPath(config, `translate.openai_custom.${gid}.api_key`))]),
            ]);
        },
        secretWire(id) { return wireValue(this.secretFields[id]); },
        secretPreview(id) { return previewText(this.secretFields[id], maskSecret); },
        secretHasValue(id) { return wireValue(this.secretFields[id]) !== ''; },
        secretReplace(id) { this.secretFields[id] = startReplace(this.secretFields[id]); },
        secretClear(id) { this.secretFields[id] = requestClear(this.secretFields[id]); },
        secretFieldAdd(gid) {
            if (!isGroupId(gid)) return;
            this.secretFields[gid] = createSecretField('');
        },
        secretFieldRemove(gid) {
            delete this.secretFields[gid];
        },
        secretsApplyToConfig(config) {
            for (const id of Object.keys(this.secretFields)) {
                const path = secretPathOf(id);
                if (path === null || CONNECT_ONLY.has(id)) continue;
                setPath(config, path, wireValue(this.secretFields[id]));
            }
            return config;
        },
        get secretsDirty() { return Object.entries(this.secretFields).some(([id, field]) => !CONNECT_ONLY.has(id) && isDirty(field)); },
        secretsAfterSave() {
            for (const [id, field] of Object.entries(this.secretFields)) {
                if (!CONNECT_ONLY.has(id)) this.secretFields[id] = afterSave(field, maskSecret);
            }
        },
    };
}
