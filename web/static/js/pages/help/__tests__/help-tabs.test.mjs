// TASK-191a-T1: helpTabs — 預設分頁與 hash 解析優先序。不經 Alpine。
import { test } from 'node:test';
import assert from 'node:assert/strict';

const { resolveHelpTab } = await import('../help-tabs.js');
const TABS = ['library', 'organize', 'manual'];
const panelOf = (id) => ({ 'tag-alias': 'manual' })[id] ?? null;
const pick = (hash, tutorialCompleted, po = panelOf) => resolveHelpTab({ hash, tutorialCompleted, panelOf: po });

test('completed_flag_decides_default_tab', () => {
    assert.equal(pick('', false), 'library');
    assert.equal(pick('', true), 'manual');
});

test('hash_beats_flag_and_chapter_id_lands_on_manual', () => {
    assert.equal(pick('#organize', false), 'organize');
    assert.equal(pick('#organize', true), 'organize');
    assert.equal(pick('#tag-alias', false), 'manual');
    assert.equal(pick('#library', true), 'library');
});

test('unknown_hash_still_lands_on_a_valid_tab', () => {
    for (const flag of [false, true]) {
        assert.ok(TABS.includes(pick('#nowhere', flag)));
        assert.ok(TABS.includes(pick('#tag-alias', flag, () => 'bogus')));
        assert.ok(TABS.includes(pick(undefined, flag, undefined)));
    }
});
