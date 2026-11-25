// TASK-199a-T5: lbxFit state slice (hide until measured, single atomic write).
// Timing-class behaviour (lbxFitSchedule / ResizeObserver / fonts.ready) is covered by CDP end-state checks, not here.

import { test } from 'node:test';
import assert from 'node:assert/strict';

const { stateLightboxFit } = await import('../state-lightbox-fit.js');

test('test_fit_hides_until_measured_then_writes_once', () => {
    const fit = stateLightboxFit();
    let writes = 0;
    let store = fit.lbxFit;
    Object.defineProperty(fit, 'lbxFit', {
        get: () => store,
        set: (v) => { writes += 1; store = v; },
        configurable: true,
    });
    const measure = () => ({ chipWidths: [100, 100, 100, 100], moreChipWidth: 60, available: 290, gap: 10 });

    // (a) signature changed but not measured yet → still hidden
    assert.equal(fit.lbxFitMeasuring('sig-a'), true);

    // (b) one run → shown, exactly one assignment carrying both sig and count
    fit.lbxFitRun('sig-a', {}, measure);
    assert.equal(fit.lbxFitMeasuring('sig-a'), false);
    assert.equal(writes, 1);
    assert.equal(store.sig, 'sig-a');
    assert.equal(store.actressShown, 2);

    // (c) measurement failed → sig still updated, fallback count Infinity (never stuck hidden)
    fit.lbxFitRun('sig-b', {}, () => null);
    assert.equal(fit.lbxFitMeasuring('sig-b'), false);
    assert.equal(store.actressShown, Infinity);
});

test('test_fit_measure_uses_whole_row_width', () => {
    const fit = stateLightboxFit();
    const actors = { clientWidth: 120 };
    const measure = {
        querySelectorAll: () => Array.from({ length: 5 }, () => ({ offsetWidth: 100 })),
        querySelector: () => ({ offsetWidth: 60 }),
    };
    const rowEl = {
        clientWidth: 600,
        querySelector: (selector) => ({ '.lbx-actors': actors, '.lbx-measure': measure })[selector],
    };
    const hadStyle = Object.hasOwn(globalThis, 'getComputedStyle');
    const originalStyle = globalThis.getComputedStyle;
    try {
        globalThis.getComputedStyle = () => ({ columnGap: '10px' });
        fit.lbxFitRun('sig', { rowEl });
        assert.equal(fit.lbxFit.actressShown, 5);
    } finally {
        if (hadStyle) globalThis.getComputedStyle = originalStyle;
        else delete globalThis.getComputedStyle;
    }
});

