// feature/122（Codex PR#147 P2）：合併卡的破壞性確認要明示「刪的是整組」。
//
// T4 起 DELETE /api/showcase/video 對分集片刪的是整組 DB 列，但確認彈窗的既有文案
// 只說「這筆紀錄」——prd 的「破壞性 modal 明示授權」在那個情況下不成立。
// 本檔鎖的是 state 那一半：pending 快照要帶著 part_tokens，且取消/完成後要清乾淨
// （殘留會讓下一張單檔卡的彈窗多出一段假的分集警語）。
//
// state-delete.js 用瀏覽器 importmap 別名 `@/showcase/...`，plain `node --test` 不認得，
// 比照 card-shape-persist.test.mjs 自帶與 base.html importmap 對齊的 resolve hook。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';
import path from 'node:path';

globalThis.window = globalThis;
globalThis.window.t = (key) => key;

const IMPORTMAP = {
    '@/showcase/': 'pages/showcase/',
    '@/shared/': 'shared/',
    '@/components/': 'components/',
};
const JS_ROOT = path.resolve(fileURLToPath(new URL('.', import.meta.url)), '../../..');

register('data:text/javascript,' + encodeURIComponent(`
const MAP = ${JSON.stringify(IMPORTMAP)};
const ROOT = ${JSON.stringify(pathToFileURL(JS_ROOT + path.sep).href)};
export function resolve(specifier, context, next) {
    for (const [alias, target] of Object.entries(MAP)) {
        if (specifier.startsWith(alias)) {
            return next(ROOT + target + specifier.slice(alias.length), context);
        }
    }
    return next(specifier, context);
}
`));

const { stateDelete } = await import('@/showcase/state-delete.js');

function mk(video) {
    const s = stateDelete();
    s.currentLightboxVideo = video;
    return s;
}

test('分集卡開啟確認彈窗：pending 快照帶著 part_tokens', () => {
    const s = mk({ path: 'file:///m/ABC-123-cd1.mp4', number: 'ABC-123', part_tokens: ['cd1', 'cd2'] });
    s.openDeleteVideoModal();
    assert.deepEqual(s._pendingDeleteParts, ['cd1', 'cd2']);
    assert.equal(s.deleteVideoModalOpen, true);
});



// ── 198b-T7b：confirmDeleteVideo 只移除一個版本（applyVersionRemoval）──────────────────────
const { normalizeWorkItem: normWork198, versionsOf: versionsOf198 } = await import('@/showcase/work-versions.js');
const { _videos: wallVideos198, _allVideos: wallAll198 } = await import('@/showcase/state-base.js');

function delWork198(tag) {
    const mkv = (p, o) => ({ path: 'file:///m/' + tag + p, title: 'T' + p, ...o });
    const list = [mkv('-C.mkv'), mkv('.mp4'), mkv('-LTX.mkv')];
    return normWork198({ ...list[0], versions: list.map((x) => ({ ...x })) }); // 預設版本 dict；_versions = [中字, 4K, LTX]
}

function delComp198(lightbox, extra) {
    const toasts = [];
    const c = Object.assign(stateDelete(), {
        currentLightboxVideo: lightbox, paginatedVideos: [], videoCount: 8, hiddenCount: 0,
        calls: { filter: 0, close: 0 }, toasts,
        applyFilterAndSort() { c.calls.filter++; }, closeLightbox() { c.calls.close++; },
        showToast(msg, kind) { toasts.push({ msg, kind }); }, $nextTick(fn) { fn(); },
        lbVersionCapsules() { return ['FHD 中字', '4K 原版', 'FHD LTX']; },
    }, extra);
    return c;
}

test('confirmDeleteVideo + applyVersionRemoval：移除 LTX 版 → 卡與其他版本留著、共 N 部不變；最後一版才整張消失', async () => {
    const prevFetch = globalThis.fetch;
    try {
        for (const mode of ['ok', 'reject', 'http500', 'rebuilt', 'rebuilt-reject']) {
            const rebuilt = mode.startsWith('rebuilt');   // GET 等待期間 _videos 被重建成別的順序（隱藏未連線硬碟重算）
            const getFails = mode === 'reject' || mode === 'rebuilt-reject';
            const W = delWork198('ABF');
            const [zh, k4, ltx] = versionsOf198(W);
            const other = { path: 'file:///m/OTHER.mp4' };
            wallVideos198.length = 0; wallAll198.length = 0;
            wallVideos198.push(other, W); wallAll198.push(other, W);
            const c = delComp198(ltx);
            c.openDeleteVideoModal();
            assert.equal(c._pendingDeleteVersionLabel, 'FHD LTX', '彈窗要知道是哪一版（目前版本，不是第一顆）');
            assert.deepEqual(c._pendingDeleteOthers, [zh.path, k4.path]);

            const methods = [];
            globalThis.fetch = async (url, opts) => {
                methods.push(opts && opts.method ? opts.method : 'GET');
                if (opts && opts.method === 'DELETE') return { ok: true, status: 200, json: async () => ({ deleted: 1 }) };
                if (rebuilt) { wallVideos198.length = 0; wallVideos198.push(W, other); }
                if (getFails) throw new Error('network down');
                if (mode === 'http500') return { ok: false, status: 500, json: async () => ({}) };
                const nk4 = { ...k4, title: 'NEW-4K' };
                return { ok: true, status: 200, json: async () => ({ success: true, video: { ...nk4, versions: [nk4, { ...zh }] } }) };
            };
            await c.confirmDeleteVideo();

            const want = (mode === 'ok' || mode === 'rebuilt') ? k4 : zh;
            const slot = rebuilt ? 0 : 1;   // 重建後這部作品在 _videos 的位置   // 回應決定新預設；讀不到就退成剩下的第一個
            assert.deepEqual(c.toasts.map((x) => x.msg), ['showcase.video.delete_success'], mode + '：不能先跳「移除失敗」');
            assert.equal(c.videoCount, 8, mode + '：共 N 部不變');
            assert.equal(wallVideos198[slot], want, mode + '：_videos 那格是新預設的原物件');
            assert.equal(wallVideos198[1 - slot], other, mode + '：別部作品那格不變');
            assert.equal(wallAll198[1], want, mode + '：_allVideos 同');
            assert.deepEqual(versionsOf198(want).map((x) => x.path), want === k4 ? [k4.path, zh.path] : [zh.path, k4.path]);
            assert.equal(want.title, want === k4 ? 'NEW-4K' : 'T-C.mkv', mode + '：有回應就用回應資料');
            assert.ok(![zh, k4].some((d) => versionsOf198(d).some((x) => x.path === ltx.path)), mode + '：剩下版本的清單不含 LTX');
            assert.deepEqual([c.calls.filter, c.calls.close], [1, 1]);
            assert.deepEqual(methods, ['DELETE', 'GET']);
            assert.deepEqual([c._pendingDeleteVersionLabel, c._pendingDeleteOthers, c._pendingDeletePath], ['', [], null]);
        }

        // 最後一版：整張消失、−1、只發 DELETE
        const only = normWork198({ path: 'file:///m/SOLO.mp4', versions: [] });
        wallVideos198.length = 0; wallAll198.length = 0;
        wallVideos198.push(only); wallAll198.push(only);
        const methods = [];
        globalThis.fetch = async (url, opts) => { methods.push(opts.method); return { ok: true, status: 200, json: async () => ({ deleted: 1 }) }; };
        const c = delComp198(only, { lbVersionCapsules: undefined });   // 單版本不得呼叫版本膠囊
        c.openDeleteVideoModal();
        assert.equal(c._pendingDeleteVersionLabel, '');
        await c.confirmDeleteVideo();
        assert.deepEqual(methods, ['DELETE']);
        assert.deepEqual([wallVideos198.length, wallAll198.length, c.videoCount], [0, 0, 7]);
        assert.deepEqual(c.toasts.map((x) => x.msg), ['showcase.video.delete_success']);
    } finally {
        globalThis.fetch = prevFetch;
        wallVideos198.length = 0; wallAll198.length = 0;
    }
});
