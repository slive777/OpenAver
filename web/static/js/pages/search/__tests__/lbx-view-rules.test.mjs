import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';

globalThis.window = globalThis;
register(new URL('./alias-loader.mjs', import.meta.url), import.meta.url);
const { toLbxVideo, lbxItemKey } = await import('../lbx-view-rules.js');
const { searchStateLbxView } = await import('../state/lbx-view.js');
const { searchStateGridMode } = await import('../state/grid-mode.js');
const { searchStateWishlist } = await import('../state/wishlist.js');
const { workInfoFields, sourceDurationPillShown, parseActresses, hasDistinctOtitle } = await import('../../showcase/lbx-logic.js');

test('test_lbx_toLbxVideo_field_mapping', () => {
    const item = { number: 'A', title: '原題', translated_title: '中文', translated_summary: '中', _summary: '日', actors: ['甲', '乙'], tags: ['標'], date: '2020-01-01', duration: '90', maker: '廠', label: '牌', series: '系列', director: '導', sample_images: ['原'], preview_sample_images: ['預'] };
    const video = toLbxVideo(item, 'result');
    assert.deepEqual(video, { number: 'A', title: '中文', original_title: '原題', actresses: '甲,乙', tags: '標', release_date: '2020-01-01', source_duration: 90, duration: 90, maker: '廠', label: '牌', series: '系列', director: '導', sample_images: ['原'], preview_sample_images: ['預'], summary: '中' });
    assert.equal(hasDistinctOtitle(video), true);
    assert.equal(sourceDurationPillShown(video), true);
    assert.deepEqual(parseActresses(video), ['甲', '乙']);
    assert.equal(video.release_date, '2020-01-01');
    assert.ok(workInfoFields(video).some((field) => field.id === 'release'));
    const plain = toLbxVideo({ title: '原題', _summary: '日' }, 'result');
    assert.equal(plain.title, '原題'); assert.equal(plain.original_title, ''); assert.equal(plain.summary, '日');
    const wish = toLbxVideo({ ...item, actresses: ['丙'], release_date: '2021' }, 'wishlist');
    assert.equal(wish.title, '原題'); assert.equal(wish.original_title, ''); assert.equal(wish.summary, '');
    assert.equal(wish.actresses, '丙'); assert.equal(wish.release_date, '2021');
    const skeleton = toLbxVideo({ number: 'S', _skeleton: true }, 'result');
    assert.equal(skeleton.title, ''); assert.equal(skeleton.duration, 0); assert.deepEqual(skeleton.sample_images, []);
    assert.equal(workInfoFields(skeleton).length, 1);
    assert.equal(toLbxVideo(null, 'result'), null); assert.equal(toLbxVideo('x', 'result'), null);
});

test('test_lbx_item_key_and_view_contract', () => {
    const item = { number: 'A', source: 'one', url: 'url' };
    const key = lbxItemKey('result', item);
    assert.equal(key, 'r|A|one|url');
    assert.equal(lbxItemKey('result', { ...item, translated_summary: '中', _localStatus: 1 }), key);
    assert.notEqual(lbxItemKey('result', { ...item, source: 'two' }), key);
    assert.notEqual(lbxItemKey('result', { ...item, url: 'other' }), key);
    assert.equal(lbxItemKey('wishlist', item), 'w|A');
    assert.equal(lbxItemKey('wishlist', { ...item, source: 'two' }), 'w|A');
    assert.notEqual(lbxItemKey('wishlist', item), key); assert.equal(lbxItemKey('result', null), '');
    const s = { ...searchStateLbxView(), currentLightboxVideo: searchStateGridMode().currentLightboxVideo, currentWishlistLightboxItem: searchStateWishlist().currentWishlistLightboxItem, searchResults: [], lightboxIndex: 0, wishlistItems: [], wishlistLightboxIndex: -1, wishlistLightboxOpen: false, lightboxOpen: false, lightboxCloseTimer: null };
    assert.equal(s.lbxOwner(), 'search'); assert.equal(s.lbxView(), null); assert.equal(s.lbxViewKey(), '');
    s.wishlistLightboxIndex = 0; assert.equal(s.lbxOwner(), 'wishlist'); assert.equal(s.lbxView(), null); assert.equal(s.lbxViewKey(), '');
    s.wishlistItems = [item]; assert.equal(s.lbxView().number, 'A');
    s.lightboxCloseTimer = 1; assert.equal(s.lbxOwner(), 'search');
    s.lightboxCloseTimer = null; s.lightboxOpen = true; s.lightboxIndex = -1;
    assert.equal(s.lbxOwner(), 'search'); assert.equal(s.lbxView(), null); assert.equal(s.lbxViewKey(), '');
    s.lightboxIndex = 0; s.searchResults = [{ number: 'S', _skeleton: true }];
    assert.equal(s.lbxView().number, 'S'); assert.equal(s.lbxViewKey(), 'r|S||');
    s.wishlistLightboxOpen = true; assert.equal(s.lbxOwner(), 'wishlist'); assert.equal(s.lbxViewKey(), 'w|A');
    s.wishlistLightboxOpen = false; s.lightboxOpen = false; assert.equal(s.lbxOwner(), 'wishlist'); assert.equal(s.lbxView().number, 'A');
});
