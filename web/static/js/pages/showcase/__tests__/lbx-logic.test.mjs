// TASK-199a-T2：影片燈箱規格帶純函式（formatRuntime／bandParts）。

import { test } from 'node:test';
import assert from 'node:assert/strict';

const { formatRuntime, bandParts } = await import('../lbx-logic.js');

test('test_format_runtime_hours_minutes', () => {
    assert.equal(formatRuntime(123), '2:03');
    assert.equal(formatRuntime(59), '0:59');
    assert.equal(formatRuntime(60), '1:00');
    for (const v of [0, null, undefined, NaN]) {
        assert.equal(formatRuntime(v), '');
    }
});

test('test_band_parts_omit_missing_fixed_order', () => {
    const fmt = { formatSize: (b) => 'S' + b, formatRuntime };
    const ids = (v, f = fmt) => bandParts(v, f).map((p) => p.id);

    // (a) 全欄位 → 固定順序：等級、編碼、片長、大小
    const full = { resolution_tier: '1080p', media_codec: 'HEVC', media_duration_min: 123, size: 5 };
    assert.deepEqual(ids(full), ['tier', 'codec', 'runtime', 'size']);
    assert.equal(bandParts(full, fmt).find((p) => p.id === 'runtime').text, '2:03');

    // (b) 只有大小 → 只剩大小；size 為假值時不呼叫 formatSize（其「未知」字樣不得出現）
    assert.deepEqual(ids({ size: 7 }), ['size']);
    let called = 0;
    const spy = { formatSize: () => { called += 1; return 'UNKNOWN'; }, formatRuntime };
    for (const size of [0, null, undefined]) {
        assert.deepEqual(bandParts({ size }, spy), []);
    }
    assert.equal(called, 0);
    assert.deepEqual(bandParts(null, fmt), []);

    // (c) 分集版本：media_duration_min 為 null 但來源片長有值 → 不顯示片長
    assert.deepEqual(ids({ media_duration_min: null, duration: 125, size: 7 }), ['size']);
});

// TASK-199a-T4：⋯ 選單項目條件（menuItems）。
test('test_menu_items_follow_path_samples_and_translate_gate', async () => {
    const { menuItems } = await import('../lbx-logic.js');
    const ids = (o) => menuItems({}, o).map((i) => i.id);

    // (a) 全條件成立 → 依序 samples、translate、rescrape、delete
    assert.deepEqual(ids({ sampleCount: 0, trVisible: true, hasPath: true }), ['samples', 'translate', 'rescrape', 'delete']);
    // (b) 沒有對應檔 → 只剩 rescrape（即使翻譯條件成立、沒劇照）
    assert.deepEqual(ids({ sampleCount: 0, trVisible: true, hasPath: false }), ['rescrape']);
    // (c) 已有劇照 → 不出 samples
    assert.deepEqual(ids({ sampleCount: 3, trVisible: true, hasPath: true }), ['translate', 'rescrape', 'delete']);
    // (d) 翻譯條件不成立 → 不出 translate
    assert.deepEqual(ids({ sampleCount: 0, trVisible: false, hasPath: true }), ['samples', 'rescrape', 'delete']);
});

// TASK-199a-T5：第 3 列女優露出數與作品資訊欄位。
test('test_fit_actresses_caps_at_three_and_keeps_at_least_one', async () => {
    const { fitActresses } = await import('../lbx-logic.js');
    const chip = (n) => Array(n).fill(100);
    const base = { moreChipWidth: 60, gap: 10 };

    // (a) 6 位、寬度充裕 → 上限 3
    assert.equal(fitActresses({ ...base, chipWidths: chip(6), available: 5000 }), 3);
    // (b) 連第 1 位都放不下 → 至少 1 位，不是 0
    assert.equal(fitActresses({ ...base, chipWidths: chip(6), available: 10 }), 1);
    // (c) 2 位、寬度充裕 → 兩位都露，沒有「另有」
    const two = fitActresses({ ...base, chipWidths: chip(2), available: 5000 });
    assert.equal(two, 2);
    assert.equal(2 - two, 0);
    // (d) 6 位、只夠 2 位＋more chip（2*100+10+60+10=280）→ 2
    assert.equal(fitActresses({ ...base, chipWidths: chip(6), available: 290 }), 2);
});

test('test_work_info_fields_skip_empty_and_dup_label', async () => {
    const { workInfoFields } = await import('../lbx-logic.js');
    const ids = (v, o) => workInfoFields(v, o).map((f) => f.id);
    const full = { number: 'N-1', maker: 'M', label: 'L', series: 'S', director: 'D', release_date: '2020-01-01', source_duration: 120 };

    // (a) 全欄位齊 → 固定順序
    assert.deepEqual(ids(full), ['number', 'maker', 'label', 'series', 'director', 'release', 'source_duration']);
    // (b) 廠牌等於片商 → 不重複列
    assert.ok(!ids({ ...full, label: 'M' }).includes('label'));
    // (c) 空字串／空白／來源片長 0／null → 不出現
    const empty = { number: '', maker: '  ', label: '', series: null, director: undefined, release_date: '', source_duration: 0 };
    assert.deepEqual(ids(empty), []);
    assert.ok(!ids({ ...full, source_duration: null }).includes('source_duration'));
    // (d) 發行日可不可點由呼叫端決定
    const rel = (o) => workInfoFields(full, o).find((f) => f.id === 'release').clickable;
    assert.equal(rel({ releaseClickable: false }), false);
    assert.equal(rel({ releaseClickable: true }), true);
});

test('test_fit_tag_row_user_tags_first_then_overflow_to_more', async () => {
    const { fitTagRow } = await import('../lbx-logic.js');
    const rep = (n, w) => Array(n).fill(w);
    const base = { plusWidth: 28, moreChipWidth: 36, gap: 6 };

    // (a) 寬度充裕：使用者標籤先排、全露；作品標籤用剩下的寬度，N = 13 - 6 = 7
    const a = fitTagRow({ ...base, rowWidth: 1000, userWidths: rep(5, 60), workWidths: rep(13, 80) });
    assert.equal(a.userShown, 5);
    assert.equal(a.workShown, 6);
    assert.equal(13 - a.workShown, 7);

    // (b) 使用者標籤超過半行才收；作品標籤本來放得下 3 個，但因為有使用者標籤被收起，要為 +N 讓位 → 2 個，N = (3-2) + (4-2) = 3
    const b = fitTagRow({ ...base, rowWidth: 400, userWidths: rep(4, 60), workWidths: rep(3, 70) });
    assert.equal(b.userShown, 2);
    assert.equal(b.workShown, 2);
    assert.equal(3 - b.workShown + (4 - b.userShown), 3);

    // (c) 都沒有標籤 → 0／0
    assert.deepEqual(fitTagRow({ ...base, rowWidth: 1000, userWidths: [], workWidths: [] }), { userShown: 0, workShown: 0 });
});

// TASK-199b-T2：收藏者優先穩定分組（純函式）。
test('test_orderFavoritesFirst_favs_first_stable_groups', async () => {
    const { orderFavoritesFirst } = await import('../lbx-logic.js');
    const names = ['丙', '丁', '壬', '戊', '癸'];
    const isFav = (n) => n === '壬' || n === '癸';

    // (a) 收藏者在前、兩群各自維持資料順序
    assert.deepEqual(orderFavoritesFirst(names, isFav), ['壬', '癸', '丙', '丁', '戊']);
    // (b) 全沒收藏 → 同序且回傳新陣列、輸入未被改動
    const plain = orderFavoritesFirst(names, () => false);
    assert.deepEqual(plain, names);
    assert.notEqual(plain, names);
    assert.deepEqual(names, ['丙', '丁', '壬', '戊', '癸']);
    // (c) 全收藏 → 同序；非陣列 → []
    assert.deepEqual(orderFavoritesFirst(names, () => true), names);
    assert.deepEqual(orderFavoritesFirst(null, isFav), []);
    assert.deepEqual(orderFavoritesFirst('壬', isFav), []);
});

// TASK-199b-T2：lbxActressList 接線（收藏者優先排進第 3 列與名單）。
test('test_lbxActressList_puts_favs_first_same_order_as_data', async () => {
    const { stateLightboxPop } = await import('../state-lightbox-pop.js');
    const call = (currentLightboxVideo, _lbActorFavs) =>
        stateLightboxPop().lbxActressList.call({ currentLightboxVideo, _lbActorFavs });

    const video = { actresses: '丙, 丁, 壬, 戊, 癸' };
    const favs = { 壬: { name: '壬' }, 癸: { name: '癸' } };
    // (a) 有收藏 → 收藏者排前面、兩群各自維持資料順序
    assert.deepEqual(call(video, favs), ['壬', '癸', '丙', '丁', '戊']);
    // (b) 無收藏表 → 資料順序
    assert.deepEqual(call(video, {}), ['丙', '丁', '壬', '戊', '癸']);
    assert.deepEqual(call(video, undefined), ['丙', '丁', '壬', '戊', '癸']);
});

// TASK-199b-T3：收藏女優小卡內容規則（缺哪項整行省略，不寫 null／undefined）。
test('test_actorCardLines_omit_missing_rows_never_print_null', async () => {
    const { actorCardLines } = await import('../lbx-logic.js');
    const t = (k, p) => (p ? k + '|' + p.n : k);
    const full = { name: '夾具女優丑', photo_url: '/p/a.jpg', age: 30, height: '165cm', cup: 'E', bust: '88', waist: '58', hip: '87' };
    const cases = [
        { label: '①沒生日', entity: { ...full, age: null }, opts: { ageAtRelease: 28, count: 5 },
          check: (r, l) => { assert.deepEqual(r.rows.map((x) => x.id), ['body', 'count'], l); } },
        { label: '②沒發行日／合輯', entity: full, opts: { ageAtRelease: null, count: 5 },
          check: (r, l) => {
              const age = r.rows.find((x) => x.id === 'age');
              assert.ok(age, l);
              assert.ok(age.text.includes('actor_card_age_now|30'), l);
              assert.ok(!age.text.includes('age_release') && !age.text.includes('null'), l);
          } },
        { label: '③三圍不齊且片數 0', entity: { name: '夾具女優子', age: 30, height: '159cm', bust: '80' }, opts: { ageAtRelease: 25, count: 0 },
          check: (r, l) => {
              const body = r.rows.find((x) => x.id === 'body');
              assert.equal(body.text, '159cm', l);
              assert.ok(!body.text.includes('-'), l);
              const count = r.rows.find((x) => x.id === 'count');
              assert.ok(count && count.text.includes('actor_card_count|0'), l);
          } },
        { label: '④全缺', entity: { name: '夾具女優辰' }, opts: { ageAtRelease: null, count: null },
          check: (r, l) => {
              assert.deepEqual(r.rows, [], l);
              assert.equal(r.name, '夾具女優辰', l);
              assert.equal(r.photo, '', l);
          } },
    ];
    for (const c of cases) {
        const r = actorCardLines(c.entity, { ...c.opts, t });
        for (const row of r.rows) {
            assert.ok(!/null|undefined|NaN/.test(row.text), `${c.label}: 不得出現 null／undefined：${row.text}`);
        }
        c.check(r, c.label);
    }
});

// TASK-199b-T3：頭像 click 的鍵盤啟動走「看她的片」，觸控才開小卡（R2 接線；裸 node，不碰 window）。
test('test_lbxActorAvatarTap_keyboard_searches_touch_toggles_card', async () => {
    const { stateLightboxPop } = await import('../state-lightbox-pop.js');
    const mk = () => {
        const calls = { search: [], toggle: [] };
        return { calls, ctx: { searchFromMetadata: (...a) => calls.search.push(a), lbxPopToggle: (...a) => calls.toggle.push(a) } };
    };
    const tap = stateLightboxPop().lbxActorAvatarTap;

    // (a) Enter／Space 觸發的 click（detail 0）⇒ 看她的片，不開小卡
    const a = mk();
    tap.call(a.ctx, { detail: 0, pointerType: 'mouse', currentTarget: {} }, '夾具女優丑');
    assert.deepEqual(a.calls.search, [['夾具女優丑', 'actress']], '鍵盤啟動應搜尋');
    assert.equal(a.calls.toggle.length, 0, '鍵盤啟動不得開小卡');

    // (b) 觸控 ⇒ click 模式 toggle 小卡，不搜尋
    const b = mk();
    const eb = { detail: 1, pointerType: 'touch', currentTarget: {} };
    tap.call(b.ctx, eb, '夾具女優丑');
    assert.deepEqual(b.calls.toggle, [['actorCard', eb.currentTarget, { mode: 'click', anchorKey: '夾具女優丑' }]], '觸控應 toggle 小卡');
    assert.equal(b.calls.search.length, 0, '觸控不得搜尋');
});
