/**
 * Motion Preferences Bridge — Phase E (GSAP) 準備
 * CSS @media 在 theme.css:2128 已覆蓋，但 GSAP 繞過 CSS 需要 JS 層檢查
 */
(function () {
    window.OpenAver = window.OpenAver || {};

    var mql = window.matchMedia('(prefers-reduced-motion: reduce)');
    window.OpenAver.prefersReducedMotion = mql.matches;

    function onChange(e) {
        // MediaQueryListEvent 或 legacy MediaQueryList
        var matches = (e.matches !== undefined) ? e.matches : mql.matches;
        window.OpenAver.prefersReducedMotion = matches;
        window.dispatchEvent(new CustomEvent('openaver:motion-pref-change', {
            detail: { reducedMotion: matches }
        }));
    }

    // 相容性：Safari <14 / 舊版 WebView 只有 addListener
    if (mql.addEventListener) {
        mql.addEventListener('change', onChange);
    } else if (mql.addListener) {
        mql.addListener(onChange);
    }
})();
