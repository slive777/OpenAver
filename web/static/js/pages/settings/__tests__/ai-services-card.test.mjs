// TASK-186-T2: aiServicesCard 分頁殼 — localStorage 讀寫與未知值後備。
// 不經 Alpine：直接呼叫 factory。

import { test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';

globalThis.window = globalThis;
window.t = (k) => k;

const KEY = 'settings_ai_tab';
let store;
let throwingGet = false;
let throwingSet = false;

function installStorage({ getThrows = false, setThrows = false } = {}) {
    store = Object.create(null);
    throwingGet = getThrows;
    throwingSet = setThrows;
    globalThis.localStorage = {
        getItem(k) {
            if (throwingGet) throw new Error('getItem blocked');
            return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null;
        },
        setItem(k, v) {
            if (throwingSet) throw new Error('setItem blocked');
            store[k] = String(v);
        },
        removeItem(k) {
            delete store[k];
        },
        clear() {
            store = Object.create(null);
        },
    };
}

beforeEach(() => {
    installStorage();
});

afterEach(() => {
    installStorage();
});

const { aiServicesCard } = await import('../ai-services-card.js');

const CASES = [
    {
        name: 'legal_stored_tab_is_restored',
        setup() { store[KEY] = 'similar'; },
        run(c) { assert.equal(c.aiTab, 'similar'); },
    },
    {
        name: 'unknown_stored_tab_falls_back_to_translate',
        setup() { store[KEY] = 'bogus'; },
        run(c) { assert.equal(c.aiTab, 'translate'); },
    },
    {
        name: 'selectAiTab_writes_storage',
        setup() {},
        run(c) {
            c.selectAiTab('similar');
            assert.equal(c.aiTab, 'similar');
            assert.equal(store[KEY], 'similar');
        },
    },
    {
        name: 'getItem_throw_still_shows_translate',
        setup() { installStorage({ getThrows: true }); },
        run(c) { assert.equal(c.aiTab, 'translate'); },
    },
    {
        name: 'setItem_throw_still_switches_tab',
        setup() { installStorage({ setThrows: true }); },
        run(c) {
            c.selectAiTab('similar');
            assert.equal(c.aiTab, 'similar');
        },
    },
];

for (const tc of CASES) {
    test(tc.name, () => {
        tc.setup();
        const c = aiServicesCard();
        tc.run(c);
    });
}
