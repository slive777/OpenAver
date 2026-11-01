/**
 * main.js — Showcase ESM 入口（54b-T1b）
 *
 * mergeState 合併 showcase 各 state factory 與 shared state（rescrape／toast），
 * 橋接 window.showcaseState，並在 alpine:init 時以 'showcase' 名稱註冊。
 * 刻意不寫個數——這個數字歷來漂移過兩次（拆分前已是 8 個而此處長期寫「四個」），
 * 權威清單是下面的 mergeState(...) 呼叫本身。
 *
 * 使用 descriptor-preserving mergeState：stateBase 含 $persist getter，
 * plain spread 會丟失 getter descriptor，必須用 Object.defineProperties。
 */

import { stateBase }     from '@/showcase/state-base.js';
import { stateVideos }   from '@/showcase/state-videos.js';
import { stateActress }  from '@/showcase/state-actress.js';
import { stateLightbox } from '@/showcase/state-lightbox.js';
import { stateLightboxMask } from '@/showcase/state-lightbox-mask.js';
import { stateLightboxPicker } from '@/showcase/state-lightbox-picker.js';
import { stateLightboxTags } from '@/showcase/state-lightbox-tags.js';
import { stateLightboxTranslate } from '@/showcase/state-lightbox-translate.js';
import { stateLightboxPlot } from '@/showcase/state-lightbox-plot.js';
import { stateLightboxSamples } from '@/showcase/state-lightbox-samples.js';
import { stateSimilar }  from '@/showcase/state-similar.js';
import { stateDelete }   from '@/showcase/state-delete.js';
import { rescrapeState } from '@/shared/state-rescrape.js';
import { toastState } from '@/shared/state-toast.js';
import { mergeState } from '@/shared/merge-state.js';

window.showcaseState = function() {
    return mergeState(
        stateBase.call(this),
        stateVideos.call(this),
        stateActress.call(this),
        stateLightbox.call(this),
        stateLightboxMask.call(this),
        stateLightboxPicker.call(this),
        stateLightboxTags.call(this),
        stateLightboxTranslate.call(this),
        stateLightboxPlot.call(this),
        stateLightboxSamples.call(this),
        stateSimilar.call(this),
        stateDelete.call(this),
        rescrapeState.call(this),
        toastState.call(this),
    );
};

document.addEventListener('alpine:init', () => {
    Alpine.data('showcase', window.showcaseState);
});
