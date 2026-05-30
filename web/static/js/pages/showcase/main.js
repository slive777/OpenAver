/**
 * main.js — Showcase ESM 入口（54b-T1b）
 *
 * mergeState 合併四個 state factory，橋接 window.showcaseState，
 * 並在 alpine:init 時以 'showcase' 名稱註冊。
 *
 * 使用 descriptor-preserving mergeState：stateBase 含 $persist getter，
 * plain spread 會丟失 getter descriptor，必須用 Object.defineProperties。
 */

import { stateBase }     from '@/showcase/state-base.js';
import { stateVideos }   from '@/showcase/state-videos.js';
import { stateActress }  from '@/showcase/state-actress.js';
import { stateLightbox } from '@/showcase/state-lightbox.js';
import { stateSimilar }  from '@/showcase/state-similar.js';
import { rescrapeState } from '@/shared/state-rescrape.js';
import { longPressState } from '@/shared/long-press.js';

function mergeState(...parts) {
    const target = {};
    for (const part of parts) {
        Object.defineProperties(target, Object.getOwnPropertyDescriptors(part));
    }
    return target;
}

window.showcaseState = function() {
    return mergeState(
        stateBase.call(this),
        stateVideos.call(this),
        stateActress.call(this),
        stateLightbox.call(this),
        stateSimilar.call(this),
        rescrapeState.call(this),
        longPressState.call(this),
    );
};

document.addEventListener('alpine:init', () => {
    Alpine.data('showcase', window.showcaseState);
});
