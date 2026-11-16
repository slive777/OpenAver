// TASK-168b-T7: copyText 三層降級（bridge → navigator.clipboard → execCommand）

import { test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';

globalThis.window = globalThis;

let execCalls;
let taValues;
let execSeen;
let createdTas;
function stubDocument(execResult, opts = {}) {
    execCalls = 0;
    taValues = [];
    execSeen = null;
    createdTas = [];
    const body = {
        _children: [],
        appendChild: (ta) => {
            ta.parentElement = body;
            body._children.push(ta);
            taValues.push(ta.value);
        },
    };
    const doc = { body, activeElement: body };
    let container = null;
    let button = null;
    if (opts.trap) {
        container = {
            _children: [],
            parentElement: body,
            appendChild: (ta) => {
                ta.parentElement = container;
                container._children.push(ta);
            },
        };
        button = {
            parentElement: container,
            focus: () => { doc.activeElement = button; },
        };
        container._children.push(button);
        body._children.push(container);
        doc.activeElement = button;
        doc._trapButton = button;
        doc._trapContainer = container;
    }
    doc.createElement = () => {
        const ta = {
            value: '',
            style: {},
            selectionStart: 0,
            selectionEnd: 0,
            parentElement: null,
            select: () => {
                if (opts.trap === 'always') {
                    doc.activeElement = button;
                    ta.selectionStart = 0;
                    ta.selectionEnd = 0;
                    return;
                }
                if (opts.trap) {
                    if (ta.parentElement === container) {
                        doc.activeElement = ta;
                        ta.selectionStart = 0;
                        ta.selectionEnd = ta.value.length;
                    } else {
                        doc.activeElement = button;
                        ta.selectionStart = 0;
                        ta.selectionEnd = 0;
                    }
                    return;
                }
                doc.activeElement = ta;
                ta.selectionStart = 0;
                ta.selectionEnd = ta.value.length;
            },
            remove: () => {
                const host = ta.parentElement;
                if (host && host._children) {
                    const i = host._children.indexOf(ta);
                    if (i >= 0) host._children.splice(i, 1);
                }
                ta.parentElement = null;
                if (doc.activeElement === ta) doc.activeElement = body;
            },
        };
        createdTas.push(ta);
        return ta;
    };
    doc.execCommand = () => {
        execCalls += 1;
        if (execResult instanceof Error) throw execResult;
        const ta = createdTas[createdTas.length - 1];
        execSeen = {
            activeIsTa: ta ? doc.activeElement === ta : false,
            selection: ta ? ta.value.slice(ta.selectionStart, ta.selectionEnd) : '',
            host: ta ? ta.parentElement : null,
        };
        return execResult;
    };
    globalThis.document = doc;
}
function setNavigator(value) {
    Object.defineProperty(globalThis, 'navigator', { value, configurable: true });
}

const { copyText } = await import('../clipboard.js');

beforeEach(() => {
    delete globalThis.pywebview;
    stubDocument(false);
    setNavigator({});
});
afterEach(() => {
    delete globalThis.pywebview;
    delete globalThis.document;
    delete globalThis.navigator;
});

function counter(impl) {
    const fn = (...a) => { fn.calls += 1; return impl(...a); };
    fn.calls = 0;
    return fn;
}


test('bridge 回 ok:false 時降到 navigator 而非當成功', async () => {
    const bridgeGot = [];
    const writeGot = [];
    const bridge = counter((t) => { bridgeGot.push(t); return Promise.resolve({ ok: false }); });
    const write = counter((t) => { writeGot.push(t); return Promise.resolve(); });
    globalThis.pywebview = { api: { copy_text: bridge } };
    setNavigator({ clipboard: { writeText: write } });
    assert.equal(await copyText('x'), true);
    assert.equal(bridge.calls, 1);
    assert.equal(write.calls, 1);
    assert.deepEqual(bridgeGot, ['x']);
    assert.deepEqual(writeGot, ['x']);
});


test('navigator 為 {} 時降到 execCommand', async () => {
    setNavigator({});
    stubDocument(true);
    assert.equal(await copyText('中文 🎬 x'), true);
    assert.equal(execCalls, 1);
    assert.deepEqual(taValues, ['中文 🎬 x']);
});

test('三層全失敗回 false 且不丟例外', async () => {
    globalThis.pywebview = { api: { copy_text: () => Promise.reject(new Error('a')) } };
    setNavigator({ clipboard: { writeText: () => Promise.reject(new Error('b')) } });
    stubDocument(false);
    assert.equal(await copyText('x'), false);
    stubDocument(new Error('c'));
    assert.equal(await copyText('x'), false);
});

test('execCommand 在選取為空時即使回 true 也不算複製成功', async () => {
    setNavigator({});
    stubDocument(true, { trap: 'always' });
    assert.equal(await copyText('x'), false);
    assert.equal(execCalls, 0);
});

test('隱藏 textarea 掛在焦點元素的父層，結束後焦點回到原按鈕', async () => {
    setNavigator({});
    stubDocument(true, { trap: true });
    const btn = document.activeElement;
    assert.equal(await copyText('路徑 x'), true);
    assert.equal(execCalls, 1);
    assert.equal(execSeen.selection, '路徑 x');
    assert.equal(execSeen.host, btn.parentElement);
    assert.notEqual(execSeen.host, document.body);
    assert.equal(document.activeElement, btn);
    assert.equal(createdTas[0].parentElement, null);
});
