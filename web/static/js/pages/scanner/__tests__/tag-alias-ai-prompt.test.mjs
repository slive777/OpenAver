import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { register } from 'node:module';

const saved = { window: globalThis.window, locale: globalThis.__locale, location: globalThis.window?.location, dispatchEvent: globalThis.window?.dispatchEvent, t: globalThis.window?.t, winLocale: globalThis.window?.__locale };
const locale = JSON.parse(readFileSync(new URL('../../../../../../locales/zh_TW.json', import.meta.url), 'utf8'));
const BODY = locale.scanner.tag_alias.ai_prompt.body;

function setupWindow() {
    globalThis.window = globalThis;
    window.t = (key, params = {}) => {
        const value = key.split('.').reduce((obj, part) => obj?.[part], locale);
        if (typeof value !== 'string') return `[${key}]`;
        return value.replace(/\{(\w+)\}/g, (_, name) => String(params[name] ?? ''));
    };
}

setupWindow();
register(new URL('../../search/__tests__/alias-loader.mjs', import.meta.url), import.meta.url);
const { buildAiAliasPrompt } = await import('../tag-alias-ai-prompt.js');
const { stateTagAlias } = await import('../state-tag-alias.js');

function destroyWindow() {
    if (saved.window === undefined) delete globalThis.window;
    else globalThis.window = saved.window;
    if (saved.locale === undefined) delete globalThis.__locale;
    else globalThis.__locale = saved.locale;
    if (globalThis.window !== undefined && globalThis.window !== null && typeof globalThis.window === 'object') {
        if (saved.location === undefined) delete globalThis.window.location;
        else globalThis.window.location = saved.location;
        if (saved.dispatchEvent === undefined) delete globalThis.window.dispatchEvent;
        else globalThis.window.dispatchEvent = saved.dispatchEvent;
        if (saved.t === undefined) delete globalThis.window.t;
        else globalThis.window.t = saved.t;
        if (saved.winLocale === undefined) delete globalThis.window.__locale;
        else globalThis.window.__locale = saved.winLocale;
    }
}

const LANG_NAMES = {
    'zh-TW': '繁體中文',
    'zh-CN': '简体中文',
    'ja': '日本語',
    'en': 'English',
    'ko': '한국어',
};

const NUMBER_KEYWORDS = ['完整存下來', '一次只換一組', '別組', '原樣建回', '全部的字'];

test('test_ai_prompt_per_locale fills lang url and five steps', async () => {
    setupWindow();
    try {
    const origin = 'http://127.0.0.1:8000';
    const numbered = BODY.split('\n').filter(line => /^\d+\. /.test(line));
    assert.equal(numbered.length, 5);
    for (let i = 0; i < 5; i += 1) assert.ok(numbered[i].startsWith(`${i + 1}. `));
    for (const target of ['zh-TW', 'zh-CN', 'ja', 'en', 'ko', undefined]) {
        const text = buildAiAliasPrompt(target, origin);
        const key = target === undefined ? 'zh-TW' : target;
        assert.ok(text.includes(LANG_NAMES[key]), key);
        assert.ok(text.includes(`${origin}/api/capabilities`), key);
        assert.ok(!text.includes('{lang}'), key);
        assert.ok(!text.includes('{url}'), key);
        assert.ok(!text.includes('[scanner.'), key);
        for (const line of numbered) assert.ok(text.includes(line), `${key}: ${line.slice(0, 8)}`);
        for (const word of NUMBER_KEYWORDS) assert.ok(text.includes(word), `${key}: ${word}`);
        if (key === 'ko') {
            assert.ok(text.includes('한국어'), 'ko');
            assert.ok(!text.includes('繁體中文'), 'ko');
        }
    }
    } finally { destroyWindow(); }
});

test('test_copy_failure_dispatches_full_text', async () => {
    setupWindow();
    try {
    const origin = 'http://127.0.0.1:8000';
    const expected = buildAiAliasPrompt('zh-TW', origin);
    window.__locale = 'zh-TW';
    window.location = { origin };
    const events = [];
    window.dispatchEvent = ev => { events.push(ev); return true; };
    const toasts = [];
    const comp = stateTagAlias();
    comp.showToast = (...args) => toasts.push(args);
    await comp.copyTagAliasAiPrompt(async () => false);
    assert.equal(events.length, 1);
    assert.equal(events[0].detail.text, expected);
    assert.equal(events[0].cancelable, true);
    assert.deepEqual(toasts, [[window.t('scanner.tag_alias.toast.prompt_copy_failed'), 'error']]);

    events.length = 0;
    toasts.length = 0;
    window.dispatchEvent = ev => { events.push(ev); ev.preventDefault(); return false; };
    await comp.copyTagAliasAiPrompt(async () => false);
    assert.equal(events.length, 1);
    assert.equal(events[0].detail.text, expected);
    assert.deepEqual(toasts, []);

    events.length = 0;
    toasts.length = 0;
    window.dispatchEvent = ev => { events.push(ev); return true; };
    await comp.copyTagAliasAiPrompt(async () => true);
    assert.equal(events.length, 0);
    assert.deepEqual(toasts, [[window.t('scanner.tag_alias.toast.prompt_copied'), 'success']]);

    } finally { destroyWindow(); }
});
