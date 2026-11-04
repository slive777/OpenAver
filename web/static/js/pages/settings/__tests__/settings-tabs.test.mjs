// TASK-190a-T1: settingsTabs — 分頁解析優先序與 storage 被擋的後備。不經 Alpine。
import { test } from 'node:test';
import assert from 'node:assert/strict';

globalThis.window = globalThis;

function stubStorage({ blocked = false } = {}) {
    const store = {};
    const guard = () => { if (blocked) throw new Error('storage blocked'); };
    globalThis.localStorage = {
        getItem: (k) => { guard(); return k in store ? store[k] : null; },
        setItem: (k, v) => { guard(); store[k] = String(v); },
    };
    globalThis.location = { hash: '' };
    globalThis.history = { replaceState: () => {} };
}

const { resolveSettingsTab, settingsTabs } = await import('../settings-tabs.js');
const panelOf = (id) => ({ filenameFormat: 'scraping' })[id] ?? null;
const pick = (hash, stored) => resolveSettingsTab({ hash, stored, panelOf });

test('legacy_sec_and_field_id_hash_land_on_owning_tab', () => {
    assert.equal(pick('#sec-search'), 'sources');
    assert.equal(pick('#sec-gallery'), 'gallery');
    assert.equal(pick('#sec-ai'), 'ai');
    assert.equal(pick('#sec-system'), 'system');
    assert.equal(pick('#filenameFormat'), 'scraping');
    assert.equal(pick('#nowhere', 'ai'), 'ai');
});

test('hash_beats_stored_and_stored_beats_default', () => {
    assert.equal(pick('#gallery', 'ai'), 'gallery');
    assert.equal(pick('', 'ai'), 'ai');
    assert.equal(pick('', undefined), 'sources');
    assert.equal(pick('', 'bogus'), 'sources');
});

test('storage_blocked_still_inits_and_switches', () => {
    stubStorage({ blocked: true });
    const tabs = settingsTabs();
    assert.equal(tabs.settingsTab, 'sources');
    tabs.selectSettingsTab('ai');
    assert.equal(tabs.settingsTab, 'ai');
});
