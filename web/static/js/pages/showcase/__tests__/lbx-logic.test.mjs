// TASK-199a-T2：影片燈箱規格帶純函式（formatRuntime／bandParts）。

import { test } from 'node:test';
import assert from 'node:assert/strict';

const { formatRuntime, bandParts } = await import('../lbx-logic.js');

test('test_is_same_work_follows_membership_not_index_or_order', async () => {
    const { isSameWork } = await import('../lbx-logic.js');
    const work = (path, paths) => Object.defineProperty({ path }, '_versions', { value: paths.map((p) => ({ path: p })) });
    const versions = [{ path: '/a' }, { path: '/b' }];
    const [a, b] = versions.map((v) => Object.defineProperty(v, '_versions', { value: versions }));
    assert.equal(isSameWork(b, a), true);
    assert.equal(isSameWork(a, b), true);
    assert.equal(isSameWork(work('/b', ['/a', '/b']), { path: '/a' }), true);
    assert.equal(isSameWork(work('/b', ['/b', '/a']), a), true);
    assert.equal(isSameWork(work('/c', ['/c']), a), false);
    assert.equal(isSameWork({ number: ' abc ' }, { path: '/a', number: 'ABC' }), true);
    assert.equal(isSameWork({ number: 'xyz' }, { path: '/a', number: 'ABC' }), false);
    assert.equal(isSameWork(null, a), true);
    assert.equal(isSameWork(a, null), false);
    assert.equal(isSameWork(work('/new', ['/new']), work('/old', ['/old'])), false);
});

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
    assert.deepEqual(ids({ sampleCount: 0, trVisible: true, hasPath: true }), ['samples', 'translate', 'advedit', 'rescrape', 'delete']);
    // (b) 沒有對應檔 → 只剩 rescrape（即使翻譯條件成立、沒劇照）
    assert.deepEqual(ids({ sampleCount: 0, trVisible: true, hasPath: false }), ['rescrape']);
    // (c) 已有劇照 → 不出 samples
    assert.deepEqual(ids({ sampleCount: 3, trVisible: true, hasPath: true }), ['translate', 'advedit', 'rescrape', 'delete']);
    // (d) 翻譯條件不成立 → 不出 translate
    assert.deepEqual(ids({ sampleCount: 0, trVisible: false, hasPath: true }), ['samples', 'advedit', 'rescrape', 'delete']);
});

// TASK-200a-T3：⋯ 選單「調整海報裁切」項（canFocal 閘 + 排在 rescrape 前）。
test('test_menu_items_focal_item_follows_can_focal_and_sits_before_rescrape', async () => {
    const { menuItems } = await import('../lbx-logic.js');
    const ids = (o) => menuItems({}, o).map((i) => i.id);
    const allOn = { sampleCount: 0, trVisible: true, hasPath: true };

    // (a) canFocal true → focal 出現且在 translate 與 rescrape 之間
    assert.deepEqual(ids({ ...allOn, canFocal: true }), ['samples', 'translate', 'focal', 'advedit', 'rescrape', 'delete']);
    // (b) canFocal false → 不含 focal
    assert.deepEqual(ids({ ...allOn, canFocal: false }), ['samples', 'translate', 'advedit', 'rescrape', 'delete']);
    // (c) 缺省 canFocal → 不含 focal（既有呼叫端不傳時行為不變）
    assert.deepEqual(ids(allOn), ['samples', 'translate', 'advedit', 'rescrape', 'delete']);
});

// TASK-199a-T5：第 3 列女優露出數與作品資訊欄位。
test('test_fit_actresses_default_has_no_cap_and_keeps_at_least_one', async () => {
    const { fitActresses } = await import('../lbx-logic.js');
    const chip = (n) => Array(n).fill(100);
    const base = { moreChipWidth: 60, gap: 10 };

    // (a) 6 位、寬度充裕 → 全數露出
    assert.equal(fitActresses({ ...base, chipWidths: chip(6), available: 5000 }), 6);
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

test('test_focal_save_toast_maps_poster_status_to_key_and_type', async () => {
    const { focalSaveToast } = await import('../lbx-logic.js');
    const cases = [
        [{ status: 'updated' }, 'showcase.lightbox.focal_saved_poster_updated', 'success'],
        [{ status: 'failed' }, 'showcase.lightbox.focal_saved_poster_failed', 'error'],
        [{ status: 'none' }, 'showcase.lightbox.focal_saved', 'success'],
        [{ status: 'skipped' }, 'showcase.lightbox.focal_saved', 'success'],
        [undefined, 'showcase.lightbox.focal_saved', 'success'], [null, 'showcase.lightbox.focal_saved', 'success'],
        [{}, 'showcase.lightbox.focal_saved', 'success'], [{ status: 'bogus' }, 'showcase.lightbox.focal_saved', 'success'],
    ];
    const seen = new Set();
    for (const [poster, key, type] of cases) {
        assert.deepEqual(focalSaveToast(poster), { key, type });
        seen.add(key);
    }
    const { readFileSync } = await import('node:fs');
    const { default: path } = await import('node:path');
    const { fileURLToPath } = await import('node:url');
    const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../../../..');
    const strings = JSON.parse(readFileSync(path.join(root, 'locales/zh_TW.json'), 'utf8'));
    for (const key of seen) {
        const value = key.split('.').reduce((o, part) => (o == null ? o : o[part]), strings);
        assert.ok(typeof value === 'string' && value.length > 0, key);
    }
});

test('test_adv_edit_media_text_and_missing_states', async () => {
    const { formatHms, fileInfoParts, mediaInfoText } = await import('../lbx-logic.js');
    const opts = { formatHms, formatSize: n => `${n} B`, t: k => k };
    const full = { status: 'ok', tier: '4K', width: 3840, height: 2160, codec: 'HEVC', duration_ms: 7394000, size: 5 };
    const cases = [[full, '4K（3840×2160） · HEVC · 2:03:14 · 5 B'], [{ ...full, codec: null }, '4K（3840×2160） · 2:03:14 · 5 B'], [{ ...full, duration_ms: 0 }, '4K（3840×2160） · HEVC · 5 B'], [{ ...full, size: 0 }, '4K（3840×2160） · HEVC · 2:03:14'], [{ status: 'ok', width: 10, height: 20 }, '10×20'], [{ status: 'ok', tier: 'HD' }, 'HD'], [{ status: 'none' }, 'showcase.adv_edit.files.media_none'], [{ status: 'failed' }, 'showcase.adv_edit.files.media_failed'], [null, 'showcase.adv_edit.files.media_none']];
    assert.ok(fileInfoParts(full, opts).length);
    for (const [media, expected] of cases) assert.equal(mediaInfoText(media, opts), expected);
    assert.equal(formatHms(7394000), '2:03:14'); assert.equal(formatHms(45000), '0:00:45');
});

test('test_adv_edit_files_view_and_action_notices', async () => {
    const { advEditFilesView, advEditActionNotice, advEditOutputTarget } = await import('../lbx-logic.js');
    const info = { state: 'ok', readonly: false, cover: { exists: true }, poster: { visible: true, exists: true, can_regen: true }, thumb: { mode: 'cache', exists: true }, folders: { source: 'src', output: 'out' }, nfo: { name: 'a b.nfo' } };
    const view = (patch = {}, opts = {}) => advEditFilesView({ ...info, ...patch }, { borrowed: false, imgFail: {}, ...opts });
    assert.equal(view().poster, 'img');
    assert.equal(view({ poster: { visible: true, exists: null } }).poster, 'generic');
    assert.equal(view({ poster: { visible: true, exists: false, can_regen: true } }).poster, 'empty');
    assert.equal(view({ poster: { visible: false } }).poster, 'hidden');
    assert.equal(view({}, { borrowed: true }).canRegen, false);
    assert.equal(view({ cover: { exists: false } }).cover, 'broken');
    assert.equal(view({ readonly: true }).folders.output, 'out/a%20b.nfo');
    assert.equal(advEditOutputTarget({ output: 'out/' }, ''), 'out/');
    assert.equal(view({ state: 'missing' }).banner, 'missing');
    assert.equal(view({ state: 'missing', readonly: true }).banner, 'missing_readonly');
    assert.equal(view({ state: 'unreachable' }).banner, 'unreachable');
    assert.equal(view({ thumb: { mode: 'cache', stale: true } }).thumbChip, 'stale');
    assert.equal(view({ thumb: { mode: 'cover', exists: true } }).thumbChip, 'direct');
    assert.equal(view({ thumb: { mode: 'cache', exists: false } }).thumb, 'pending');
    assert.equal(advEditFilesView(null, { imgFail: {} }).canReread, false);
    const t = k => k;
    const cases = [['regen', { success: true, poster: { status: 'updated' } }, 'poster_updated', true], ['regen', { success: true, poster: { status: 'skipped' } }, 'poster_skipped', false], ['regen', { success: true, poster: { status: 'failed' } }, 'poster_failed', false], ...[['generic_cover_name','poster_generic_cover'],['no_cover','poster_no_cover'],['readonly_output_not_current','poster_readonly_output'],['unreachable','unreachable']].map(([error,key]) => ['regen', { success: false, error }, key, false]), ['regen', null, 'poster_failed', false], ...[['ok','reread_done',true],['failed','media_failed',true],['unreadable','reread_unreadable',false],['stale','reread_stale',false],['changed','reread_changed',false],['timeout','reread_timeout',false],['unavailable','reread_unavailable',false],['skipped','reread_skipped',false]].map(([status,key,reload]) => ['reread', { success: true, status }, key, reload]), ['reread', { success: true, status: 'changed', readonly: true }, 'reread_changed_readonly', false], ['reread', { success: false, error: 'unreachable' }, 'unreachable', false], ['reread', null, 'reread_error', false]];
    for (const [kind, data, key, reload] of cases) { const notice = advEditActionNotice(kind, data, t); assert.equal(notice.text, `showcase.adv_edit.files.${key}`); assert.equal(notice.reload, reload); }
});

// TASK-207a-T1：來源片長膠囊去重判準（sourceDurationPillShown 真值表）。
test('test_source_duration_pill_shown_truth_table', async () => {
    const { sourceDurationPillShown } = await import('../lbx-logic.js');
    const cases = [
        ['來源缺 key → 藏', {}, false],
        ['來源 0 → 藏', { source_duration: 0, media_duration_min: 100 }, false],
        ['來源 null → 藏', { source_duration: null, media_duration_min: 100 }, false],
        ['實際缺 key（undefined）→ 顯示', { source_duration: 100 }, true],
        ['實際 null → 顯示', { source_duration: 100, media_duration_min: null }, true],
        ['實際 <1 分鐘 → 顯示', { source_duration: 100, media_duration_min: 0.4 }, true],
        ['差 <30% → 藏', { source_duration: 100, media_duration_min: 90 }, false],
        ['恰 30%（70 vs 100）→ 藏', { source_duration: 100, media_duration_min: 70 }, false],
        ['殘檔 0:42 vs 139 → 顯示', { source_duration: 139, media_duration_min: 42 }, true],
        ['無影片 → 藏', null, false],
    ];
    for (const [label, video, expected] of cases) {
        assert.equal(sourceDurationPillShown(video), expected, label);
    }
});
