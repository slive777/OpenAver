import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';

globalThis.window = globalThis;
window.t = (key) => key;
register(new URL('./alias-loader.mjs', import.meta.url), import.meta.url);
const { searchStateResultCard } = await import('../state/result-card.js');

function makeState(searchResults, translateWithOllama) {
    const calls = { saves: 0, toasts: [] };
    const state = {
        ...searchStateResultCard(), listMode: 'search', currentIndex: 0, searchResults,
        hasJapanese: () => true,
        showToast: (...args) => calls.toasts.push(args),
        saveState: () => { calls.saves++; },
        translateWithOllama,
    };
    return { state, calls };
}

test('test_translate_summary_writes_back_to_pressed_candidate', async () => {
    const a = { _summary: 'テスト A' }, b = { _summary: 'テスト B' };
    let release;
    const deferred = new Promise((resolve) => { release = resolve; });
    const { state, calls } = makeState([a, b], () => deferred);
    try {
        const pending = state.translateSummary();
        state.currentIndex = 1;
        release({ success: true, result: '譯文' });
        await pending;
        assert.equal(a.translated_summary, '譯文');
        assert.equal('translated_summary' in b, false);
        assert.equal(calls.saves, 1);
        assert.equal(state.isTranslatingSummary, false);
    } finally {
        release({ success: true, result: '譯文' });
    }
});

test('test_translate_summary_skipped_or_same_writes_nothing', async () => {
    for (const response of [
        { success: true, skipped: true, reason: 'no_japanese' },
        { success: true, result: 'テスト\n  内容' },
    ]) {
        const candidate = { _summary: 'テスト 内容' };
        const { state, calls } = makeState([candidate], async () => response);
        await state.translateSummary();
        assert.deepEqual(calls.toasts, [['search.toast.summary_already_zh', 'info']]);
        assert.equal('translated_summary' in candidate, false);
        assert.equal(calls.saves, 0);
        assert.equal(state.isTranslatingSummary, false);
    }
});
