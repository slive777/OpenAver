// TASK-155b-T2: Alpine.data('numberDrilldown') toggle/copyText/hasFootnote + 註冊

import { test } from 'node:test';
import assert from 'node:assert/strict';

let alpineInitCb;
globalThis.window = globalThis;
const doc = {
    addEventListener: (_name, fn) => { alpineInitCb = fn; },
    execCommand: () => { throw new Error('execCommand not stubbed for this test'); },
};
const body = {
    appendChild: (ta) => { ta.parentElement = body; },
};
doc.body = body;
doc.activeElement = body;
doc.createElement = () => {
    const ta = {
        value: '',
        style: {},
        selectionStart: 0,
        selectionEnd: 0,
        parentElement: null,
        focus: () => {},
        select: () => {
            doc.activeElement = ta;
            ta.selectionStart = 0;
            ta.selectionEnd = ta.value.length;
        },
        remove: () => {
            ta.parentElement = null;
            if (doc.activeElement === ta) doc.activeElement = body;
        },
    };
    return ta;
};
globalThis.document = doc;

const registered = [];
const toastCalls = [];
globalThis.Alpine = {
    data: (name, fn) => registered.push([name, fn]),
    store: (name) => (name === 'toast'
        ? { show: (msg, type) => { toastCalls.push([msg, type]); } }
        : undefined),
};
globalThis.window.t = (key, params) => {
    if (!params) return key;
    return key.replace(/\{(\w+)\}/g, (_, k) => (
        Object.prototype.hasOwnProperty.call(params, k) ? String(params[k]) : `{${k}}`
    ));
};

const { numberDrilldown } = await import('../number-drilldown.js');

function fresh() {
    return numberDrilldown();
}

test('模組在 alpine:init 時註冊 Alpine.data(\'numberDrilldown\', …)', () => {
    assert.equal(typeof alpineInitCb, 'function');
    alpineInitCb();
    assert.equal(registered.length, 1);
    assert.equal(registered[0][0], 'numberDrilldown');
    assert.equal(typeof registered[0][1], 'function');
    const instance = registered[0][1]();
    assert.equal(instance.open, false);
    assert.equal(typeof instance.toggle, 'function');
    assert.equal(typeof instance.close, 'function');
});

test('toggle 第一次呼叫會開啟並寫入 title／items', () => {
    const dd = fresh();
    assert.equal(dd.open, false);
    const items = [
        { number: 'ABP-001', path: 'file:///C:/AVtest/ABP-001.mp4', note: '' },
    ];
    dd.toggle({ title: '缺封面', items });
    assert.equal(dd.open, true);
    assert.equal(dd._title, '缺封面');
    assert.equal(dd._items, items);
    assert.equal(dd.count, 1);
});


test('無番號片時複製結果那一行是檔名', () => {
    const dd = fresh();
    dd.toggle({
        title: '外部媒體管理器封面缺失',
        items: [
            { number: 'WAAA-158', path: 'file:///C:/AVtest/WAAA-158.mp4', note: '' },
            { number: '', path: 'file:///C:/AVtest/無番號片.mp4', note: '' },
        ],
    });
    const lines = dd.copyText().split('\n');
    assert.equal(lines[0], 'WAAA-158');
    assert.equal(lines[1], '無番號片.mp4');
});


test('copy() 無 navigator.clipboard 且備援 execCommand 回 false 時，顯示失敗 toast 而非成功', async () => {
    const dd = fresh();
    dd.toggle({ title: '缺封面', items: [{ number: 'ABP-001', path: 'file:///C:/AVtest/ABP-001.mp4' }] });

    Object.defineProperty(globalThis, 'navigator', { value: {}, configurable: true });
    globalThis.document.execCommand = () => false;
    toastCalls.length = 0;

    await dd.copy();

    assert.equal(toastCalls.length, 1);
    assert.equal(toastCalls[0][1], 'error');
    assert.equal(toastCalls[0][0], 'common.number_drilldown.copy_failed');
});

test('copy() 備援 execCommand 回 true 時，顯示成功 toast', async () => {
    const dd = fresh();
    dd.toggle({ title: '缺封面', items: [{ number: 'ABP-001', path: 'file:///C:/AVtest/ABP-001.mp4' }] });

    Object.defineProperty(globalThis, 'navigator', { value: {}, configurable: true });
    globalThis.document.execCommand = () => true;
    toastCalls.length = 0;

    await dd.copy();

    assert.equal(toastCalls.length, 1);
    assert.equal(toastCalls[0][1], 'success');
    assert.equal(toastCalls[0][0], 'common.number_drilldown.copy_toast');
});
