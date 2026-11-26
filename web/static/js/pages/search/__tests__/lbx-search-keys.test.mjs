import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';

globalThis.window = globalThis;
register(new URL('./alias-loader.mjs', import.meta.url), import.meta.url);
const { searchStateNavigation } = await import('../state/navigation.js');
const { searchStateGridMode } = await import('../state/grid-mode.js');

test('test_lbx_search_esc_closes_pop_before_lightbox', (t) => {
    const previousDocument = globalThis.document;
    t.after(() => { globalThis.document = previousDocument; });
    globalThis.document = { activeElement: { tagName: 'DIV' } };
    const calls = [];
    const fake = { ...searchStateNavigation(), lightboxOpen: true, lbxPop: { kind: 'info' },
        lbxPopClose(options) { calls.push(['pop', options]); this.lbxPop = null; },
        closeLightbox() { calls.push(['lightbox']); } };
    let prevented = 0;
    const event = { key: 'Escape', preventDefault() { prevented++; } };
    fake.handleKeydown(event);
    assert.deepEqual(calls, [['pop', { restoreFocus: true }]]);
    assert.equal(prevented, 1);
    fake.handleKeydown(event);
    assert.deepEqual(calls, [['pop', { restoreFocus: true }], ['lightbox']]);
});

test('test_lbx_search_backdrop_swallow_after_pop_close', (t) => {
    const previousDocument = globalThis.document;
    t.after(() => { globalThis.document = previousDocument; });
    let clicks = 0, closes = 0;
    globalThis.document = { elementFromPoint: () => ({ closest: () => ({ click() { clicks++; } }) }) };
    const fake = { ...searchStateGridMode(), _lbxPopSwallowClick: true, closeLightbox() { closes++; } };
    const event = { target: { closest: () => null }, currentTarget: { style: {} } };
    fake.handleLightboxBackdropClick(event);
    assert.equal(clicks, 0);
    assert.equal(closes, 0);
    assert.equal(fake._lbxPopSwallowClick, false);
    fake.handleLightboxBackdropClick(event);
    assert.equal(clicks, 1);
});
