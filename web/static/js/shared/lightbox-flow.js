export const LIGHTBOX_ROOT_SELECTOR = '.showcase-lightbox:not(.wishlist-lightbox)';
export const WISHLIST_LIGHTBOX_ROOT_SELECTOR = '.wishlist-lightbox';
export const SHOWCASE_LIGHTBOX_OPEN_ID = 'showcaseLightboxOpen';
export const LIGHTBOX_OPEN_ID = 'lightboxOpen';

export function settleLightboxRoot(root) {
  if (!root) return;
  root.classList.remove('gsap-animating');
  root.style.removeProperty('opacity');
}

const closeTeardowns = new WeakMap();

export function cancelCloseTeardown(root) {
  if (!root) return;
  const entry = closeTeardowns.get(root);
  if (!entry) return;
  root.removeEventListener('transitionend', entry.listener);
  clearTimeout(entry.timer);
  closeTeardowns.delete(root);
}

export function armCloseTeardown(root, run) {
  cancelCloseTeardown(root);
  if (!root) return setTimeout(run, 800);
  const fire = () => {
    cancelCloseTeardown(root);
    run();
  };
  const listener = event => {
    if (event.target !== root || event.propertyName !== 'opacity') return;
    fire();
  };
  root.addEventListener('transitionend', listener);
  const timer = setTimeout(fire, 800);
  closeTeardowns.set(root, { listener, timer });
  return timer;
}

export function flyBackToGrid(host, spec) {
  const { findCard, fromRect, coverSrc, fromImg } = spec;
  if (!fromRect || !window.GhostFly?.playLightboxToGrid) return;
  const callback = () => {
    const ghostFly = window.GhostFly;
    const card = findCard();
    if (card && ghostFly?.playLightboxToGrid) ghostFly.playLightboxToGrid(fromRect, card, { coverSrc, fromImg });
  };
  if (typeof host.$nextTick === 'function') host.$nextTick(callback);
  else callback();
}

export function openLightboxFlow(host, spec) {
  const { root, openKey, genKey, busyKey, animations, fromRect, coverSrc, posterCrop } = spec;
  const setBusy = value => { if (busyKey !== null) host[busyKey] = value; };
  cancelCloseTeardown(root);
  if (host[openKey] && typeof gsap !== 'undefined') {
    const id = animations === 'ShowcaseAnimations' ? SHOWCASE_LIGHTBOX_OPEN_ID : LIGHTBOX_OPEN_ID;
    gsap.getById(id)?.kill();
  }
  if (root) {
    root.style.opacity = '0';
    root.classList.add('gsap-animating');
  }
  host[openKey] = true;
  const generation = ++host[genKey];
  let done = false;
  const timer = setTimeout(() => {
    if (!done) {
      settleLightboxRoot(root);
      setBusy(false);
    }
  }, 800);
  const callback = () => {
    let takeover = null;
    let ghost = null;
    try {
      done = true;
      clearTimeout(timer);
      if (host[genKey] === generation && host[openKey] && root &&
          window.GhostFly && typeof gsap !== 'undefined' && !window.OpenAver?.prefersReducedMotion) {
        const animate = window[animations]?.playLightboxOpen;
        if (typeof animate === 'function') {
          if (fromRect && typeof window.GhostFly.playGridToLightbox === 'function') {
            setBusy(true);
            ghost = window.GhostFly.playGridToLightbox(fromRect, root, {
              coverSrc, posterCrop, onComplete: () => setBusy(false)
            });
          }
          if (ghost) {
            takeover = animate.call(window[animations], root, { skipCover: true });
          } else {
            setBusy(true);
            takeover = animate.call(window[animations], root, { onComplete: () => setBusy(false) });
          }
        }
      }
    } catch (error) {
      ghost = null;
      console.error(error);
    }
    if (!takeover) {
      settleLightboxRoot(root);
      if (!ghost) setBusy(false);
    }
  };
  if (typeof host.$nextTick === 'function') host.$nextTick(callback);
  else callback();
}
