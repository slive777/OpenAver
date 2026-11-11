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

    // (b) one run → shown, exactly one assignment carrying both sig and count; T7 fields untouched
    fit.lbxFitRun('sig-a', {}, measure);
    assert.equal(fit.lbxFitMeasuring('sig-a'), false);
    assert.equal(writes, 1);
    assert.equal(store.sig, 'sig-a');
    assert.equal(store.actressShown, 2);
    assert.equal(store.workTagShown, null);
    assert.equal(store.userTagShown, null);

    // (c) measurement failed → sig still updated, fallback count 3 (never stuck hidden)
    fit.lbxFitRun('sig-b', {}, () => null);
    assert.equal(fit.lbxFitMeasuring('sig-b'), false);
    assert.equal(store.actressShown, 3);
});
