import { createSecretField, startReplace, requestClear, wireValue, previewText, isDirty, afterSave } from './secret-field-logic.js';
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

export function stateSecrets() {
    return {
        secretFields: Object.fromEntries(Object.keys(SECRET_PATHS).map(id => [id, createSecretField('')])),
        secretsLoad(config) {
            this.secretFields = Object.fromEntries(Object.entries(SECRET_PATHS).map(([id, path]) => [id, createSecretField(getPath(config, path))]));
        },
        secretWire(id) { return wireValue(this.secretFields[id]); },
        secretPreview(id) { return previewText(this.secretFields[id], maskSecret); },
        secretHasValue(id) { return wireValue(this.secretFields[id]) !== ''; },
        secretReplace(id) { this.secretFields[id] = startReplace(this.secretFields[id]); },
        secretClear(id) { this.secretFields[id] = requestClear(this.secretFields[id]); },
        secretsApplyToConfig(config) {
            for (const id of Object.keys(SECRET_PATHS)) {
                if (CONNECT_ONLY.has(id)) continue;
                setPath(config, SECRET_PATHS[id], wireValue(this.secretFields[id]));
            }
            return config;
        },
        get secretsDirty() { return Object.entries(this.secretFields).some(([id, field]) => !CONNECT_ONLY.has(id) && isDirty(field)); },
        secretsAfterSave() {
            for (const id of Object.keys(SECRET_PATHS)) {
                if (!CONNECT_ONLY.has(id)) this.secretFields[id] = afterSave(this.secretFields[id], maskSecret);
            }
        },
    };
}
