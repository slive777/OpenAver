/**
 * play-video.js — 共用「播放影片」函式（shared ESM，195-T6）
 *
 * playVideo：桌面 App（PyWebView）呼叫 open_file 交給 PotPlayer／系統預設播放器；
 * 開不開得了的結果交給 notifyOpenResult 顯示統一 toast。無桌面殼（手機、一般瀏覽器）
 * 才開播放分頁。呼叫當下才檢查 bridge，不另外等待就緒。
 *
 * 必須用一般 function 宣告（非 arrow）：函式體內以 this.showToast(...)
 * 存取呼叫端 Alpine component 的方法，this 綁定由呼叫時機決定，arrow
 * function 會把 this 詞法綁死在模組頂層（undefined），導致 runtime
 * TypeError。
 *
 * 被 search/state/result-card.js 與 showcase/state-videos.js 兩頁
 * import，各自以 shorthand property 掛回其 Alpine state 物件。
 * 行為由 showcase/__tests__/bridge-open-wiring.test.mjs 守；字面由
 * scripts/static_guard_lint.mjs 的 TestVideoPlaybackGuard／CD-120a-11 兩條規則
 * 與 195-T6 三條 search.html 規則守。
 */

import { notifyOpenResult } from '@/shared/bridge-notify.js';

/**
 * 播放影片。this 綁定於呼叫端的 Alpine component（需要 this.showToast）。
 *
 * @param {string} path 檔案路徑
 */
export function playVideo(path) {
  if (window.pywebview && window.pywebview.api) {
    window.pywebview.api.open_file(path)
      .then(result => {
        if (!notifyOpenResult(this.showToast.bind(this), result, 'file')) return;
      })
      .catch(err => {
        console.error('Failed to open file:', err);
        this.showToast(window.t('showcase.video.play_failed'), 'error');
      });
  } else {
    window.open('/api/gallery/player?path=' + encodeURIComponent(path), '_blank');
  }
}
