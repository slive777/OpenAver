function toggleThemeWithTransition(event, applyFn) {
    if (window.OpenAver?.prefersReducedMotion || !document.startViewTransition) {
        applyFn();
        return;
    }
    let x = event.clientX;
    let y = event.clientY;
    if (x === 0 && y === 0 && event.currentTarget) {
        const rect = event.currentTarget.getBoundingClientRect();
        x = rect.left + rect.width / 2;
        y = rect.top + rect.height / 2;
    }
    const maxRadius = Math.hypot(
        Math.max(x, innerWidth - x),
        Math.max(y, innerHeight - y)
    );
    // feature/76 T1a（CD-7/F7）：標記主題切換期間，讓 settings.css 的 root 抑制
    // 規則（html.theme-transition-active 前綴）只在此期間生效、不汙染跨頁 root crossfade。
    document.documentElement.classList.add('theme-transition-active');
    const transition = document.startViewTransition(() => {
        applyFn();
    });
    transition.finished.finally(() => {
        document.documentElement.classList.remove('theme-transition-active');
    });
    transition.ready.then(() => {
        document.documentElement.animate(
            {
                clipPath: [
                    `circle(0px at ${x}px ${y}px)`,
                    `circle(${maxRadius}px at ${x}px ${y}px)`
                ]
            },
            {
                duration: 500,
                easing: 'ease-out',
                pseudoElement: '::view-transition-new(root)'
            }
        );
    }).catch(e => {
        if (e?.name !== 'AbortError') throw e;
    });
}
window.toggleThemeWithTransition = toggleThemeWithTransition;
