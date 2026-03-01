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
    const transition = document.startViewTransition(() => {
        applyFn();
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
