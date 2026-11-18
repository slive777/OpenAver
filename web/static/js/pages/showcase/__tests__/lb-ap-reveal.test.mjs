import test from 'node:test';
import assert from 'node:assert/strict';

globalThis.window = globalThis;
globalThis.document = { addEventListener() {} };
await import('../animations.js');

function setup() {
    const saved = { gsap: globalThis.gsap, OpenAver: globalThis.OpenAver };
    const tweens = [];
    const calls = [];
    const list = targets => [].concat(targets);
    globalThis.gsap = {
        fromTo(targets, from, to) {
            calls.push('fromTo');
            targets = list(targets);
            for (const target of targets) {
                if ('opacity' in from) target.style.opacity = from.opacity;
                if ('y' in from) target.style.transform = `translateY(${from.y}px)`;
            }
            const tween = { targets, from, to };
            tweens.push(tween);
            return tween;
        },
        killTweensOf(targets) {
            calls.push('killTweensOf');
            targets = list(targets);
            for (let i = tweens.length - 1; i >= 0; i--) {
                if (tweens[i].targets.length === targets.length &&
                    tweens[i].targets.every((target, index) => target === targets[index])) tweens.splice(i, 1);
            }
        },
        set(targets, { clearProps }) {
            calls.push('set');
            for (const target of list(targets)) {
                for (const prop of clearProps.split(',')) delete target.style[prop];
            }
        },
        getTweensOf(target) { return tweens.filter(tween => tween.targets.includes(target)); },
        getById() { return null; },
    };
    globalThis.OpenAver = { prefersReducedMotion: false, motion: { DURATION: { fast: 0.167, medium: 0.333, emphasis: 0.5 } } };
    return { calls, tweens, restore() { globalThis.gsap = saved.gsap; globalThis.OpenAver = saved.OpenAver; } };
}

function makeStrip() {
    const cell = cls => ({ cls, style: {}, children: [{ style: {} }, { style: {} }] });
    const photo = cell('photo'), films = [cell('film'), cell('film')], next = cell('next');
    return { photo, films, next,
        querySelector(selector) { return selector === '.lbx-ap-photo' ? photo : selector === '.lbx-ap-next' ? next : null; },
        querySelectorAll(selector) { return selector === '.lbx-ap-film' ? films : []; } };
}
const all = strip => [strip.photo, ...strip.films, strip.next];
const targets = cells => cells.flatMap(cell => [cell, ...cell.children]);
const options = { photo: true, films: true, next: true };

test('test_ap_strip_reveal_reduced_motion_calls_no_gsap', () => {
    const mock = setup();
    try {
        const strip = makeStrip();
        window.ShowcaseAnimations.playApStripReveal(strip, options);
        assert.ok(mock.calls.includes('fromTo'), '一般模式應建立 tween');
        mock.calls.length = 0;
        OpenAver.prefersReducedMotion = true;
        assert.equal(window.ShowcaseAnimations.playApStripReveal(strip, options), null);
        assert.deepEqual(mock.calls, []);
    } finally { mock.restore(); }
});

test('test_ap_strip_reveal_replay_keeps_only_latest', () => {
    const mock = setup();
    try {
        const first = makeStrip(), second = makeStrip();
        window.ShowcaseAnimations.playApStripReveal(first, options);
        assert.ok(mock.tweens.length && first.photo.style.opacity === 0, '首次播放應有 tween 與殘值');
        window.ShowcaseAnimations.playApStripReveal(second, { photo: false, films: true, next: false });
        for (const target of targets(all(first))) {
            assert.deepEqual(target.style, {});
            assert.equal(gsap.getTweensOf(target).length, 0);
        }
        for (const target of targets(second.films)) assert.ok(gsap.getTweensOf(target).length);
        for (const target of targets([second.photo, second.next])) {
            assert.deepEqual(target.style, {});
            assert.equal(gsap.getTweensOf(target).length, 0);
        }
    } finally { mock.restore(); }
});

test('test_kill_lightbox_animations_clears_strip_reveal_residue', () => {
    const mock = setup();
    try {
        const strip = makeStrip();
        window.ShowcaseAnimations.playApStripReveal(strip, options);
        assert.ok('opacity' in strip.photo.style && 'transform' in strip.photo.children[0].style, '播放後應有 opacity 與 transform');
        window.ShowcaseAnimations.killLightboxAnimations();
        for (const target of targets(all(strip))) {
            assert.deepEqual(target.style, {});
            assert.equal(gsap.getTweensOf(target).length, 0);
        }
        delete globalThis.gsap;
        assert.doesNotThrow(() => window.ShowcaseAnimations.killLightboxAnimations());
    } finally { mock.restore(); }
});

test('test_ap_strip_reveal_button_tweens_opacity_only', () => {
    const mock = setup();
    try {
        const strip = makeStrip();
        window.ShowcaseAnimations.playApStripReveal(strip, options);
        const buttons = mock.tweens.filter(tween => all(strip).some(cell => tween.targets.includes(cell)));
        assert.ok(buttons.length, '應有按鈕 tween');
        for (const tween of buttons) {
            assert.deepEqual(Object.keys(tween.from), ['opacity']);
            assert.deepEqual(Object.keys(tween.to).filter(key => !['duration', 'ease', 'delay', 'clearProps'].includes(key)), ['opacity']);
        }
        for (const cell of all(strip)) {
            for (const child of cell.children) assert.ok(gsap.getTweensOf(child).some(tween => 'y' in tween.from && 'y' in tween.to));
        }
    } finally { mock.restore(); }
});
