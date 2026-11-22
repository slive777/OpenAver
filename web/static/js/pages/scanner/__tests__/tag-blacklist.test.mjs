import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { suggestionChips } from '../tag-blacklist-logic.js';
import { tagBlacklist } from '../tag-blacklist.js';

const locale = JSON.parse(readFileSync(new URL('../../../../../../locales/zh_TW.json', import.meta.url), 'utf8'));
function makeHarness() {
    const saved = { window: globalThis.window, Alpine: globalThis.Alpine, fetch: globalThis.fetch };
    const toasts = [], queue = [];
    globalThis.window = { t: (key, params = {}) => {
        const value = key.split('.').reduce((obj, part) => obj?.[part], locale);
        if (typeof value !== 'string') return undefined;
        return value.replace(/\{(\w+)\}/g, (_, name) => String(params[name] ?? ''));
    } };
    globalThis.Alpine = { store: () => ({ show: (msg, type) => toasts.push([msg, type]) }) };
    globalThis.fetch = (url, opts) => new Promise(resolve => queue.push({ url, opts, resolve: body => resolve({ ok: false, json: async () => body }) }));
    return { comp: tagBlacklist(), toasts, queue, destroy() { Object.assign(globalThis, saved); } };
}

for (const [name, code, key] of [
    ['empty', 'empty', 'scanner.tag_blacklist.error.empty'],
    ['invalid', 'invalid', 'scanner.tag_blacklist.error.invalid'],
    ['cover_badge', 'cover_badge', 'scanner.tag_blacklist.error.cover_badge'],
    ['duplicate', 'duplicate', 'scanner.tag_blacklist.error.duplicate'],
    ['no_code', undefined, 'scanner.tag_blacklist.error.generic'],
]) {
    test(`test_error_code_shows_dedicated_message: ${name}`, async () => {
        const h = makeHarness();
        try {
            h.comp.tbInput = '中文字幕';
            const pending = h.comp.tbAddFromInput();
            assert.equal(h.queue.length, 1);
            h.queue[0].resolve({ success: false, code });
            await pending;
            const expected = window.t(key, { name: '中文字幕' });
            assert.equal(typeof expected, 'string');
            assert.equal(h.comp.tbError, expected);
            assert.equal(h.comp.tbInput, '中文字幕');
            assert.deepEqual(h.toasts, []);
            assert.deepEqual(h.comp.tbItems, []);
            if (name === 'cover_badge') for (const word of ['中文字幕', '封面標章', '不能加入黑名單']) assert.ok(h.comp.tbError.includes(word));
            if (name === 'no_code') assert.ok(!h.comp.tbError.startsWith('['));
        } finally { h.destroy(); }
    });
}

test('test_suggestion_chip_added_state', async () => {
    const h = makeHarness();
    try {
        h.comp.tbItems = [{ name: 'Blu-Ray', key: 'blu-ray' }];
        h.comp.tbSuggestions = ['Blu-ray', 'ハイビジョン'];
        assert.deepEqual(suggestionChips(h.comp.tbSuggestions, h.comp.tbItems), [{ name: 'Blu-ray', added: true }, { name: 'ハイビジョン', added: false }]);
        const alreadyAdded = h.comp.tbAddSuggestion('Blu-ray');
        assert.equal(h.queue.length, 0);
        await alreadyAdded;
        const pending = h.comp.tbAddSuggestion('ハイビジョン');
        assert.equal(h.queue.length, 1);
        assert.equal(h.queue[0].opts.method, 'POST');
        assert.deepEqual(JSON.parse(h.queue[0].opts.body), { name: 'ハイビジョン' });
        h.queue[0].resolve({ success: true, items: [{ name: 'ハイビジョン', key: 'ハイビジョン' }] });
        await pending;
    } finally { h.destroy(); }
});
