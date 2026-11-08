// TASK-121c-T3: computeBadges / resolveEnabledIds 契約。
// 純函式、零 window / Alpine；邊界各至少一條真斷言。
// TASK-196-T4: MANIFEST 鏡像加 ltx／supersedes；新增 4 支蓋過規則測試。

import { test } from 'node:test';
import assert from 'node:assert/strict';

const { computeBadges, resolveEnabledIds } = await import('../cover-badges.js');

// 鏡射 core/cover_attributes.py ATTRIBUTE_TABLE 的 id / display_name / display_order /
// match_aliases / supersedes。陣列順序刻意與後端表相同（4k 在 vr 前面、但 display_order 是 vr < 4k），
// 用來鎖「resolveEnabledIds 不排序、computeBadges 依 display_order 排」。
const MANIFEST = [
    { id: 'subtitle', canonical_tag: '中文字幕', display_name: '中字', match_aliases: ['中文字幕', '中字', '字幕'], display_order: 1, supersedes: [] },
    { id: 'cracked', canonical_tag: '無碼破解', display_name: 'AI', match_aliases: ['無碼破解', '破解', '克破', 'AI'], display_order: 2, supersedes: [] },
    { id: 'ltx', canonical_tag: 'LTX', display_name: 'LTX', match_aliases: ['LTX'], display_order: 2, supersedes: ['cracked'] },
    { id: 'leaked', canonical_tag: '無碼流出', display_name: 'LEAK', match_aliases: ['無碼流出', '流出', 'leak'], display_order: 2, supersedes: [] },
    { id: '4k', canonical_tag: '4K', display_name: '4K', match_aliases: ['4K'], display_order: 4, supersedes: [] },
    { id: 'vr', canonical_tag: 'VR', display_name: 'VR', match_aliases: ['VR'], display_order: 3, supersedes: [] },
];

const ALL_IDS = MANIFEST.map((r) => r.id);

function badges(video, opts) {
    const o = opts || {};
    return computeBadges(
        video,
        o.manifest === undefined ? MANIFEST : o.manifest,
        o.tagToGroup === undefined ? {} : o.tagToGroup,
        o.enabledIds === undefined ? ALL_IDS : o.enabledIds,
    );
}

function idsOf(result) {
    return result.map((b) => b.id);
}

function namesOf(result) {
    return result.map((b) => b.display_name);
}

// ── 1. 只有 tags 命中 ────────────────────────────────────────────────

test('computeBadges: 只有 tags 命中 → 亮 中字', () => {
    const result = badges({ tags: '中文字幕,單體作品' });
    assert.deepEqual(result, [{ id: 'subtitle', display_name: '中字' }]);
});

// ── 2. 只有 user_tags 命中 ───────────────────────────────────────────

test('computeBadges: 只有 user_tags 命中 → 亮 中字', () => {
    const result = badges({ tags: '', user_tags: ['中文字幕'] });
    assert.deepEqual(result, [{ id: 'subtitle', display_name: '中字' }]);
});

// ── 3. 兩者皆有同一屬性 → 只出現一顆 ─────────────────────────────────


// ── 4. 使用者自建 alias group ────────────────────────────────────────

test('computeBadges: 使用者自建 alias group 命中（繁中 → 中字）', () => {
    const tagToGroup = {
        '中文字幕': ['中文字幕', '繁中'],
        '繁中': ['中文字幕', '繁中'],
    };
    const result = badges({ user_tags: ['繁中'] }, { tagToGroup });
    assert.deepEqual(result, [{ id: 'subtitle', display_name: '中字' }]);
});

// ── 5. tagToGroup 為 {} 時 match_aliases 仍命中 ──────────────────────
// 靜態 match_aliases 不依賴 alias map：手貼「破解」仍亮 AI。
// 本條是 mutation 2 的鎖（若命中集合只建 canonical_tag 就會紅）。


// ── 6. 命中 4 條以上 → 只回 3 個，順序符合 display_order ─────────────
// 中字 > AI/LEAK > VR > 4K。manifest 陣列裡 4k 排在 vr 前面，
// 若不依 display_order 排就會截到 4K、丟掉 VR。
// 本條是 mutation 1 的鎖（slice(0, 4) 會讓 length 變成 4）。

test('computeBadges: 命中 4 條以上只回 3 個且順序符合 display_order', () => {
    const result = badges({ tags: '中文字幕,無碼破解,VR,4K' });
    assert.equal(result.length, 3);
    assert.deepEqual(idsOf(result), ['subtitle', 'cracked', 'vr']);
    assert.deepEqual(namesOf(result), ['中字', 'AI', 'VR']);
});

// ── 7. 關掉的屬性不佔用截斷名額 ──────────────────────────────────────
// 關掉 中字 後命中 4 條 → 回剩下那 3 個（含原本會被截掉的 4K）。
// 若先截斷再過濾，中字佔走一格，只剩 2 個。


// ── 8. items 缺某個 id → 該屬性視為開啟（稀疏語意） ─────────────────

test('resolveEnabledIds: items 缺 id 視為開啟（稀疏覆寫）', () => {
    const enabled = resolveEnabledIds(MANIFEST, {
        enabled: true,
        items: { subtitle: false },
    });
    assert.equal(enabled.includes('subtitle'), false);
    assert.equal(enabled.includes('cracked'), true);
    assert.equal(enabled.includes('leaked'), true);
    assert.equal(enabled.includes('4k'), true);
    assert.equal(enabled.includes('vr'), true);
    // 不排序：回傳順序 = manifest 原順序（4k 在 vr 前）
    assert.deepEqual(enabled, ['cracked', 'ltx', 'leaked', '4k', 'vr']);

    const allOnMissingItems = resolveEnabledIds(MANIFEST, { enabled: true });
    assert.deepEqual(allOnMissingItems, ['subtitle', 'cracked', 'ltx', 'leaked', '4k', 'vr']);

    const allOnEmptyItems = resolveEnabledIds(MANIFEST, { enabled: true, items: {} });
    assert.deepEqual(allOnEmptyItems, ['subtitle', 'cracked', 'ltx', 'leaked', '4k', 'vr']);

    const explicitTrue = resolveEnabledIds(MANIFEST, {
        enabled: true,
        items: { subtitle: true },
    });
    assert.equal(explicitTrue.includes('subtitle'), true);
    assert.equal(explicitTrue.includes('4k'), true);
});

// ── 9. cfg.enabled 為 false / undefined / 缺 key → [] ────────────────

test('resolveEnabledIds: enabled 為 false/undefined/缺 key → []，computeBadges 亦回 []', () => {
    assert.deepEqual(resolveEnabledIds(MANIFEST, { enabled: false, items: {} }), []);
    assert.deepEqual(resolveEnabledIds(MANIFEST, { enabled: undefined }), []);
    assert.deepEqual(resolveEnabledIds(MANIFEST, {}), []);
    assert.deepEqual(resolveEnabledIds(MANIFEST, undefined), []);

    const off = resolveEnabledIds(MANIFEST, { enabled: false });
    assert.deepEqual(badges({ tags: '中文字幕,無碼破解,VR,4K' }, { enabledIds: off }), []);
});

// ── 10. manifest 為 [] → []、不拋例外 ────────────────────────────────


// ── 11. video null / tags undefined / user_tags 非陣列 → []、不拋 ───


// ── 12. 整串相等不是子字串 ───────────────────────────────────────────

test('computeBadges: 整串相等不是子字串（AI生成作品 不命中 AI、VR専用 不命中 VR）', () => {
    assert.deepEqual(idsOf(badges({ tags: 'AI生成作品' })), []);
    assert.deepEqual(idsOf(badges({ tags: 'VR専用' })), []);
    // 對照：精確相等仍命中，證明不是「什麼都不亮」的假綠
    assert.deepEqual(idsOf(badges({ tags: 'AI' })), ['cracked']);
    assert.deepEqual(idsOf(badges({ tags: 'VR' })), ['vr']);
});

// ── resolveEnabledIds 其餘 fail-closed 分支 ──────────────────────────


// ── TASK-196-T4: 蓋過規則 ────────────────────────────────────────────

test('supersede-1: LTX 蓋過 AI，關掉 LTX 膠囊則 AI 恢復', () => {
    const withoutLtx = ALL_IDS.filter((id) => id !== 'ltx');

    assert.deepEqual(idsOf(badges({ tags: '中文字幕,無碼破解,LTX' })), ['subtitle', 'ltx']);
    assert.deepEqual(
        idsOf(badges({ tags: '中文字幕,無碼破解,LTX' }, { enabledIds: withoutLtx })),
        ['subtitle', 'cracked'],
    );
    assert.deepEqual(idsOf(badges({ tags: '無碼破解,LTX' })), ['ltx']);
    assert.deepEqual(
        idsOf(badges({ tags: '無碼破解,LTX' }, { enabledIds: withoutLtx })),
        ['cracked'],
    );
    assert.deepEqual(idsOf(badges({ tags: 'LTX' })), ['ltx']);
    assert.deepEqual(idsOf(badges({ tags: '無碼破解' })), ['cracked']);
});

test('supersede-2: 蓋過發生在 3 顆上限之前', () => {
    assert.deepEqual(
        idsOf(badges({ tags: '中文字幕,無碼破解,LTX,無碼流出,VR' })),
        ['subtitle', 'ltx', 'leaked'],
    );
});

test('supersede-3: LTX 與 AI 佔同一個位置', () => {
    const a = idsOf(badges({ tags: '中文字幕,無碼破解,無碼流出' }));
    const b = idsOf(badges({ tags: '中文字幕,無碼破解,LTX,無碼流出' }));
    assert.deepEqual(a, ['subtitle', 'cracked', 'leaked']);
    assert.deepEqual(b, ['subtitle', 'ltx', 'leaked']);
    assert.equal(a.length, b.length);
    for (let i = 0; i < a.length; i++) {
        if (i === 1) {
            assert.notEqual(a[i], b[i]);
            assert.equal(a[i], 'cracked');
            assert.equal(b[i], 'ltx');
        } else {
            assert.equal(a[i], b[i]);
        }
    }
});

test('supersede-4: 蓋過關係讀 manifest 的 supersedes，不寫死 id', () => {
    // 舊 manifest：每列刪掉 supersedes 鍵（不是設成 []）
    const oldManifest = MANIFEST.map((r) => {
        const { supersedes, ...rest } = r;
        return rest;
    });
    assert.deepEqual(
        idsOf(badges({ tags: '無碼破解,LTX' }, { manifest: oldManifest, enabledIds: oldManifest.map((r) => r.id) })),
        ['cracked', 'ltx'],
    );

    // 非陣列 supersedes（字串）不得炸
    const stringSup = MANIFEST.map((r) => {
        if (r.id !== 'ltx') return { ...r };
        return { ...r, supersedes: 'cracked' };
    });
    assert.deepEqual(
        idsOf(badges({ tags: '無碼破解,LTX' }, { manifest: stringSup, enabledIds: stringSup.map((r) => r.id) })),
        ['cracked', 'ltx'],
    );

    // 自訂：leaked 蓋過 vr（證明讀表、不寫死 ltx→cracked）
    const custom = MANIFEST.map((r) => {
        if (r.id === 'leaked') return { ...r, supersedes: ['vr'] };
        if (r.id === 'ltx') return { ...r, supersedes: [] };
        return { ...r };
    });
    const customIds = custom.map((r) => r.id);
    assert.deepEqual(
        idsOf(badges({ tags: '無碼流出,VR' }, { manifest: custom, enabledIds: customIds })),
        ['leaked'],
    );
    // 對照：ltx.supersedes 清空後 LTX 與 AI 並列
    assert.deepEqual(
        idsOf(badges({ tags: '無碼破解,LTX' }, { manifest: custom, enabledIds: customIds })),
        ['cracked', 'ltx'],
    );
});
