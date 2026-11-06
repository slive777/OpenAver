import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
    classifyDrop,
    pasteIntent,
    shouldSkipPaste,
    isSessionFor,
    isPristine,
} from '../image-search-rules.js';

const mp4 = { name: 'ABC-123.mp4', type: 'video/mp4' };
const png = { name: 'a.png', type: 'image/png' };
const webp = { name: 'b.webp', type: 'image/webp' };
const jpg = { name: 'a.jpg', type: 'image/jpeg' };
const gif = { name: 'a.gif', type: 'image/gif' };
const dir = { name: 'dir', type: '' };
const shotUpper = { name: 'shot.PNG', type: '' };
const shotNoType = { name: 'shot.png' };
const bareMp4 = { name: 'A.mp4' };

test('classify_drop_table', () => {
    const rows = [
        ['video', [mp4], 'other', null, false],
        ['folder', [dir], 'other', null, false],
        ['video+image', [mp4, png], 'other', null, false],
        ['image+video', [png, mp4], 'other', null, false],
        ['single image', [jpg], 'image', jpg, false],
        ['gif', [gif], 'unsupported', gif, false],
        ['multiple images', [png, webp], 'image', png, true],
        ['empty type falls back to ext', [shotUpper], 'image', shotUpper, false],
        ['missing type falls back to ext', [shotNoType], 'image', shotNoType, false],
        ['undefined', undefined, 'none', null, false],
        ['null', null, 'none', null, false],
        ['empty array', [], 'none', null, false],
        ['name only mp4', [bareMp4], 'other', null, false],
    ];
    for (const [name, input, kind, file, multiple] of rows) {
        const got = classifyDrop(input);
        assert.equal(got.kind, kind, name);
        assert.strictEqual(got.file, file, name);
        assert.equal(got.multiple, multiple, name);
    }
});

const textItem = { kind: 'string', type: 'text/plain' };
const htmlItem = { kind: 'string', type: 'text/html' };
const filePng = { kind: 'file', type: 'image/png' };

test('paste_intent_table', () => {
    const rows = [
        ['plain text only', [textItem], 'text'],
        ['text+image from spreadsheet', [textItem, filePng], 'text'],
        ['image only', [filePng], 'image'],
        ['html+image from web page', [htmlItem, filePng], 'image'],
        ['undefined', undefined, 'text'],
    ];
    for (const [name, input, expected] of rows) {
        assert.equal(pasteIntent(input), expected, name);
    }
});

const S = { tagName: 'INPUT' };

test('should_skip_paste_table', () => {
    const rows = [
        ['input not search box', { tagName: 'INPUT' }, undefined, true],
        ['contenteditable div', { tagName: 'DIV', isContentEditable: true }, undefined, true],
        ['search box itself', S, undefined, false],
        ['plain div', { tagName: 'DIV' }, undefined, false],
        ['body', { tagName: 'BODY' }, undefined, false],
        ['rescrape open', { tagName: 'DIV' }, { rescrapeOpen: true }, true],
        ['browse dir open', { tagName: 'DIV' }, { browseDirOpen: true }, true],
        ['sample gallery open', { tagName: 'DIV' }, { sampleGalleryOpen: true }, true],
        ['lightbox open', { tagName: 'DIV' }, { lightboxOpen: true }, true],
        ['duplicate modal open', { tagName: 'DIV' }, { duplicateModalOpen: true }, true],
        ['wishlist lightbox open', { tagName: 'DIV' }, { wishlistLightboxOpen: true }, true],
        ['lightbox open over search box', S, { lightboxOpen: true }, true],
        ['flags missing', { tagName: 'DIV' }, undefined, false],
    ];
    for (const [name, target, flags, expected] of rows) {
        assert.equal(shouldSkipPaste(target, S, flags), expected, name);
    }
});

const a = [{ n: 1 }];

test('is_session_for_table', () => {
    const rows = [
        ['same ref', a, a, true],
        ['copied array', a, [...a], false],
        ['bound null', a, null, false],
        ['bound undefined', a, undefined, false],
        ['both null', null, null, false],
    ];
    for (const [name, rawResults, rawBound, expected] of rows) {
        assert.equal(isSessionFor(rawResults, rawBound), expected, name);
    }
});

test('is_pristine_table', () => {
    // 使用者格狀出現後自己切過檢視、開關過燈箱，第一名補上時不被自動轉走；沒動過才轉
    const base = { lightboxGen: 3, moveSeq: 0 };
    const ok = { active: true, listMode: 'search', displayMode: 'grid', currentIndex: 0, lightboxOpen: false, lightboxGen: 3, moveSeq: 0 };
    const rows = [
        ['untouched', base, ok, true],
        ['moveSeq changed', base, { ...ok, moveSeq: 1 }, false],
        ['lightboxGen changed', base, { ...ok, lightboxGen: 4 }, false],
        ['lightbox open', base, { ...ok, lightboxOpen: true }, false],
        ['currentIndex moved', base, { ...ok, currentIndex: 2 }, false],
        ['listMode changed', base, { ...ok, listMode: 'file' }, false],
        ['displayMode changed', base, { ...ok, displayMode: 'detail' }, false],
        ['array replaced (inactive)', base, { ...ok, active: false }, false],
        ['baseline missing', undefined, ok, false],
        ['now missing', base, undefined, false],
    ];
    for (const [name, b, n, expected] of rows) {
        assert.equal(isPristine(b, n), expected, name);
    }
});
