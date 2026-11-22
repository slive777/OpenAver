import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';

globalThis.window = globalThis;
window.t = (key) => key;
let alpineInit;
let registeredComponent;
const previousDocument = globalThis.document;
const previousAlpine = globalThis.Alpine;
globalThis.document = { addEventListener: (name, callback) => { if (name === 'alpine:init') alpineInit = callback; } };
globalThis.Alpine = { data: (name, factory) => { if (name === 'numberDrilldown') registeredComponent = factory; } };
register(new URL('../../pages/search/__tests__/alias-loader.mjs', import.meta.url), import.meta.url);
const { buildCopyText } = await import('../drilldown-copy.js');
const { stateScan } = await import('../../pages/scanner/state-scan.js');
const { stateBatch } = await import('../../pages/scanner/state-batch.js');
const { numberDrilldown } = await import('../../components/number-drilldown.js');
// In shared-isolation runs another test file may already have imported the module.
if (alpineInit) {
    alpineInit();
    assert.equal(registeredComponent, numberDrilldown);
}
globalThis.document = previousDocument;
globalThis.Alpine = previousAlpine;

function harness(factory) {
    return Object.defineProperties({}, Object.getOwnPropertyDescriptors(factory()));
}

function setup(ok) {
    const copied = [], toasts = [], events = [], translations = [];
    window.t = (key, params) => { translations.push([key, params]); return key; };
    window.pywebview = { api: { copy_text: async text => { copied.push(text); return { ok }; } } };
    Object.defineProperty(globalThis, 'navigator', { value: {}, configurable: true });
    const body = { appendChild(ta) { ta.parentElement = body; }, focus() {} };
    globalThis.document = {
        body, activeElement: body, addEventListener() {}, execCommand: () => false,
        createElement() {
            const ta = { value: '', style: {}, focus() {}, remove() { ta.parentElement = null; },
                select() { document.activeElement = ta; ta.selectionStart = 0; ta.selectionEnd = ta.value.length; } };
            return ta;
        },
    };
    globalThis.Alpine = { store: () => ({ show: (...args) => toasts.push(args) }) };
    globalThis.dispatchEvent = ev => { events.push(ev); return !ev.defaultPrevented; };
    return { copied, toasts, events, translations };
}

test('test_copy_entries_same_text_and_format', async () => {
    const { copied, toasts, translations } = setup(true);
    const scan = harness(stateScan), batch = harness(stateBatch);
    scan.showToast = (...args) => toasts.push(args);
    batch.missingItems = [
        { category: 'nfo', number: 'A', file_path: 'file:///D:/a.mp4' },
        { category: 'nfo', number: 'A2', file_path: 'file:///D:/a2.mp4' },
        { category: 'both', number: '', file_path: 'file:///D:/b%20c.mp4' },
        { category: 'cover', number: 'C', file_path: 'file:///D:/c.mp4' },
    ];
    const items = batch.missingAllDrilldownItems;
    const dd = numberDrilldown(); dd.toggle({ items });
    await scan.copyRowList(items); await dd.copy();
    assert.equal(copied[0], copied[1]);
    assert.deepEqual(copied[0].split('\n').map(line => line.split('\t').length), [3, 3, 3, 3, 3]);
    assert.equal(copied[0].split('\n')[0], ['common.number_drilldown.copy_col_number', 'common.number_drilldown.copy_col_path', 'common.number_drilldown.copy_col_reason'].join('\t'));
    assert.equal(copied[0].split('\n')[1], '\tD:\\b%20c.mp4\tscanner.stats.reason.missing_both');
    assert.deepEqual(items.map(i => i.number), ['', 'A', 'A2', 'C']);
    assert.equal(toasts[0][1], 'success');
    const single = numberDrilldown(); single.toggle({ items: batch.missingNfoDrilldownItems });
    await single.copy(); assert.equal(copied[2], buildCopyText(batch.missingNfoDrilldownItems));
    assert.deepEqual(toasts.at(-1).slice(0, 2), ['common.number_drilldown.copy_toast', 'success']);
    assert.deepEqual(translations.filter(([key]) => key === 'common.number_drilldown.copy_toast').at(-1), ['common.number_drilldown.copy_toast', { count: 2 }]);
    await scan.copyRowList([]); await numberDrilldown().copy(); assert.equal(copied.length, 3);
});

test('test_copy_failure_dumps_full_text', async () => {
    const { toasts, events } = setup(false);
    const items = [{ number: 'A', path: 'file:///D:/a.mp4', reason: 'reason' }];
    const scan = harness(stateScan); let dump;
    scan.openCopyFailModal = text => { dump = text; };
    scan.showToast = (...args) => toasts.push(args);
    await scan.copyRowList(items); assert.equal(dump, buildCopyText(items));
    const dd = numberDrilldown(); dd.toggle({ items });
    globalThis.dispatchEvent = ev => { events.push(ev); ev.preventDefault(); return false; };
    await dd.copy(); assert.equal(events[0].detail.text, dump); assert.equal(toasts.length, 0);
    globalThis.dispatchEvent = ev => { events.push(ev); return true; };
    await dd.copy(); assert.equal(toasts[0][0], 'common.number_drilldown.copy_failed');
});

test('test_copy_reason_present_for_three_row_kinds', () => {
    setup(true);
    const scan = harness(stateScan), batch = harness(stateBatch);
    scan.nfoUpdateItems = [{ number: 'A', path: 'a', missing: ['title'] }];
    scan.jellyfinItems = [ { missing: ['poster'] }, { missing: ['fanart'] }, { missing: ['poster', 'fanart'] }, {} ];
    batch.missingItems = ['both', 'nfo', 'cover'].map(category => ({ category }));
    assert.equal(scan.nfoUpdateDrilldownItems[0].reason, 'scanner.stats.reason.nfo_fields');
    assert.deepEqual(scan.jellyfinDrilldownItems.map(i => i.reason), ['poster', 'fanart', 'both', 'both'].map(k => `scanner.stats.reason.jellyfin_${k}`));
    assert.deepEqual(batch.missingAllDrilldownItems.map(i => i.reason), ['both', 'nfo', 'cover'].map(k => `scanner.stats.reason.missing_${k}`));
});
