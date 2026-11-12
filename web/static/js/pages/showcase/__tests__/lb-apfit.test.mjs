// TASK-199b-T4: lbxApFit state slice（女優燈箱「別名＋資訊」單行的露出數；量測失敗＝全露、不卡在隱藏）。
// 時序類（lbxApFitSchedule / ResizeObserver / fonts.ready）由 CDP 終態檢查負責，這裡只守算術與下限。

import { test } from 'node:test';
import assert from 'node:assert/strict';

const { stateLightboxApFit } = await import('../state-lightbox-apfit.js');

function makeFit() {
    const fit = stateLightboxApFit();
    let store = fit.lbxApFit;
    Object.defineProperty(fit, 'lbxApFit', {
        get: () => store,
        set: (v) => { store = v; },
        configurable: true,
    });
    return fit;
}

test('test_apfit_overflow_count', () => {
    const n = 5;
    const wide = (available) => () => ({ chipWidths: [100, 100, 100, 100, 100], moreChipWidth: 40, available, gap: 10 });

    // 寬度只夠 3 顆（3×100 + 2×10 + 收起後的「+N」50 = 370 ≤ 400；4 顆要 530）→ 露 3、收 2
    const fit = makeFit();
    fit.lbxApFitRun('s1', {}, wide(400));
    assert.equal(fit.lbxApFitShown(n), 3);
    assert.equal(fit.lbxApFitHidden(n), n - 3);

    // 比一顆還窄 → 仍露 1 顆（不是 0 顆），收起 n − 1
    fit.lbxApFitRun('s2', {}, wide(30));
    assert.equal(fit.lbxApFitShown(n), 1);
    assert.equal(fit.lbxApFitHidden(n), n - 1);

    // 全部放得下 → 全露、沒有「+N」
    fit.lbxApFitRun('s3', {}, wide(2000));
    assert.equal(fit.lbxApFitShown(n), n);
    assert.equal(fit.lbxApFitHidden(n), 0);

    // 量測失敗 → shown: null ＝全露，且簽章已更新（不卡在隱藏）
    fit.lbxApFitRun('s4', {}, () => null);
    assert.equal(fit.lbxApFit.shown, null);
    assert.equal(fit.lbxApFitShown(n), n);
    assert.equal(fit.lbxApFitHidden(n), 0);
    assert.equal(fit.lbxApFitMeasuring('s4'), false);
});
