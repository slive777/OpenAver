// 195b-T4: 「隱藏未連線硬碟」純函式（computeHiddenIndexes／splitVisible／hiddenNumberSet）。
// 195b-T5: footerNotice 句型逐格（測試 A）。
// 純函式、無 DOM／Alpine／importmap 別名，plain node --test 直接 import。
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const { computeHiddenIndexes, splitVisible, hiddenNumberSet, footerNotice } = await import('../hidden-sources.js');

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../../../');
const ZH_TW = JSON.parse(readFileSync(path.join(REPO_ROOT, 'locales/zh_TW.json'), 'utf8'));

/** 真的 zh_TW 查表（點路徑取值、{param} 代換；查無回 '[key]'）。不得用 key => key。 */
function t(key, params) {
    params = params || {};
    const keys = key.split('.');
    let val = ZH_TW;
    for (const k of keys) {
        if (val == null) break;
        val = val[k];
    }
    if (typeof val !== 'string') return '[' + key + ']';
    return val.replace(/\{(\w+)\}/g, (_, k) => (
        Object.prototype.hasOwnProperty.call(params, k) ? params[k] : '{' + k + '}'
    ));
}

const offline = (display, members = []) => ({ display, reason: 'unreachable', dsm_hint: null, members });
const denied = (display, dsm_hint = null) => ({ display, reason: 'no_permission', dsm_hint, members: [] });

test('splitVisible：藏的是離線硬碟的片，沒有 src 的片視為可見，可見片順序不變', () => {
    const sources = ['D:\\電影', 'E:\\FC2', 'F:\\x'];
    const hiddenIdx = computeHiddenIndexes(sources, ['D:\\電影']);
    assert.deepEqual([...hiddenIdx], [0], 'D: 離線 → 只有索引 0 被藏');
    // 離線成員不在 sources 內、或沒有離線 → 什麼都不藏
    assert.deepEqual([...computeHiddenIndexes(sources, ['Z:\\nope'])], []);
    assert.deepEqual([...computeHiddenIndexes(sources, [])], []);

    // src === 0 是合法索引（不得用 truthy 判斷）；缺 src／非整數 src 一律可見（fail-open）
    const all = [
        { number: 'aaa-001', src: 0 },
        { number: 'bbb-002', src: 1 },
        { number: 'ccc-003' },
        { number: 'ddd-004', src: 0 },
        { number: 'eee-005', src: 2 },
        { number: 'fff-006', src: '0' },
        { number: 'ggg-007', src: null },
        { number: '', src: 0 },
    ];
    const { visible, hidden } = splitVisible(all, hiddenIdx);
    assert.deepEqual(visible.map((v) => v.number), ['bbb-002', 'ccc-003', 'eee-005', 'fff-006', 'ggg-007']);
    assert.deepEqual(hidden.map((v) => v.number), ['aaa-001', 'ddd-004', '']);
    assert.ok(visible[0] === all[1] && hidden[0] === all[0], '同一物件 ref，不複製');

    // 被藏番號集合：轉大寫、空番號略過
    assert.deepEqual([...hiddenNumberSet(hidden)].sort(), ['AAA-001', 'DDD-004']);
    // 空集合 → 全部可見、順序不變
    assert.deepEqual(splitVisible(all, new Set()).visible.map((v) => v.number), all.map((v) => v.number));
});

// [lint-guard: node-justified] 求值型行為：footerNotice 完成句／按鈕／title 依組數×開關逐格正確；lint 無 JS 求值能力
test('footerNotice：1／2／3 顆 × 隱藏開／關，句型、已隱藏 N 部與按鈕字樣逐格正確', () => {
    // 全接上
    assert.deepEqual(footerNotice([], false, 0, t), { offline: null, permission: null });
    assert.deepEqual(footerNotice(null, true, 5, t), { offline: null, permission: null });

    const d1 = [offline('D:')];
    const d2 = [offline('D:'), offline('E:')];
    const d3 = [offline('C:'), offline('D:'), offline('E:')];
    const d4 = [offline('C:'), offline('D:'), offline('E:'), offline('F:')];

    // 1 組 × 關（deepEqual：空殼回 null 時是值斷言失敗，不是 TypeError）
    assert.deepEqual(footerNotice(d1, false, 312, t).offline, {
        text: 'D: 沒有連線', title: '', button: '隱藏',
    });
    assert.equal(footerNotice(d1, false, 312, t).permission, null);
    // 1 組 × 開（hiddenCount 取 312，≠組數，守 M2）
    assert.deepEqual(footerNotice(d1, true, 312, t).offline, {
        text: 'D: 沒有連線・已隱藏 ' + (312).toLocaleString() + ' 部',
        title: '', button: '顯示',
    });
    // 2 組 × 關／開
    assert.deepEqual(footerNotice(d2, false, 1203, t).offline, {
        text: 'D:、E: 沒有連線', title: '', button: '隱藏',
    });
    assert.deepEqual(footerNotice(d2, true, 1203, t).offline, {
        text: 'D:、E: 沒有連線・已隱藏 ' + (1203).toLocaleString() + ' 部',
        title: '', button: '顯示',
    });
    // 3 組（count 句型邊界）× 關／開
    assert.deepEqual(footerNotice(d3, false, 312, t).offline, {
        text: '3 顆硬碟沒有連線', title: 'C:、D:、E:', button: '隱藏',
    });
    assert.deepEqual(footerNotice(d3, true, 312, t).offline, {
        text: '3 顆硬碟沒有連線・已隱藏 ' + (312).toLocaleString() + ' 部',
        title: 'C:、D:、E:', button: '顯示',
    });
    // 4 組 × 開
    assert.deepEqual(footerNotice(d4, true, 1203, t).offline, {
        text: '4 顆硬碟沒有連線・已隱藏 ' + (1203).toLocaleString() + ' 部',
        title: 'C:、D:、E:、F:', button: '顯示',
    });

    // 無權限單獨（含／不含 dsm_hint）——沿用今天文案
    {
        const r = footerNotice([denied('/a')], false, 0, t);
        assert.equal(r.offline, null);
        assert.deepEqual(r.permission, { text: '沒有權限讀取：/a', title: '' });
    }
    assert.deepEqual(footerNotice([denied('/a', 'DSM 指引')], false, 0, t).permission, {
        text: '沒有權限讀取：/a DSM 指引', title: '',
    });
    assert.deepEqual(footerNotice([denied('/a'), denied('/b')], false, 0, t).permission, {
        text: '沒有權限讀取：/a、/b', title: '',
    });
    // 無權限 3 組（count 句型＋hint＋title）
    assert.deepEqual(
        footerNotice([denied('/a', 'DSM 指引'), denied('/b'), denied('/c')], false, 0, t).permission,
        { text: '3 個位置沒有權限讀取 DSM 指引', title: '/a、/b、/c' },
    );

    // 離線 ＋ 無權限並存 → 兩段各自存在；開關只影響離線段
    {
        const r = footerNotice([offline('D:'), denied('/nas', '請授權')], true, 312, t);
        assert.deepEqual(r.offline, {
            text: 'D: 沒有連線・已隱藏 ' + (312).toLocaleString() + ' 部',
            title: '', button: '顯示',
        });
        assert.deepEqual(r.permission, { text: '沒有權限讀取：/nas 請授權', title: '' });
    }
});
