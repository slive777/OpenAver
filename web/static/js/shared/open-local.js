/**
 * open-local.js — 共用「開啟資料夾」純函式（shared ESM，T4）
 *
 * openLocal：從檔案路徑萃取所在資料夾，複製顯示用路徑到剪貼簿，
 * PyWebView 桌面模式下額外呼叫 open_folder 開啟資料夾；純瀏覽器模式
 * 僅複製剪貼簿。三個結果分支（開啟成功/開啟失敗/純瀏覽器）各自對應
 * 不同 toast 文案，逐字保留自搬移前行為。
 *
 * 必須用一般 function 宣告（非 arrow）：函式體內以 this.showToast(...)
 * 存取呼叫端 Alpine component 的方法，this 綁定由呼叫時機決定，arrow
 * function 會把 this 詞法綁死在模組頂層（undefined），導致 runtime
 * TypeError。
 *
 * 被 search/state/result-card.js 與 showcase/state-videos.js 兩頁
 * import，各自以 shorthand property 掛回其 Alpine state 物件。
 * 由 tests/unit/frontend_contracts/test_contract_desktop.py::TestOpenLocalGuard 鎖死。
 */

import { pathToDisplay } from '@/components/path-utils.js';

/**
 * 開啟本地資料夾（複製路徑到剪貼簿 + PyWebView 桌面模式額外開啟資料夾）。
 * this 綁定於呼叫端的 Alpine component（需要 this.showToast）。
 *
 * @param {string} path 檔案路徑
 */
export function openLocal(path) {
  if (!path) return;

  // 1. 擷取資料夾路徑
  const lastSlash = Math.max(path.lastIndexOf('/'), path.lastIndexOf('\\'));
  const folder = lastSlash >= 0 ? path.substring(0, lastSlash) : path;
  const displayPath = pathToDisplay(folder);

  // 2. 複製到剪貼簿
  // T3.7 fix: guard against undefined navigator.clipboard (HTTP / older WebView)
  // sync property access 在 clipboard undefined 時會 TypeError，.catch 不會跑。
  const clipboardOk = navigator.clipboard?.writeText
    ? navigator.clipboard.writeText(displayPath).then(() => true).catch(() => false)
    : Promise.resolve(false);

  // 3. PyWebView 桌面模式：額外開啟資料夾
  if (window.pywebview?.api?.open_folder) {
    window.pywebview.api.open_folder(path)
      .then(async (opened) => {
        const ok = await clipboardOk;
        if (opened) {
          this.showToast(ok ? window.t('common.open_local.folder_opened_copied') : window.t('common.open_local.folder_opened'), 'success');
        } else {
          this.showToast(ok ? window.t('common.open_local.path_copied', { path: displayPath }) : window.t('common.open_local.folder_open_failed'), ok ? 'success' : 'error');
        }
      })
      .catch(async () => {
        const ok = await clipboardOk;
        this.showToast(ok ? window.t('common.open_local.path_copied', { path: displayPath }) : window.t('common.open_local.folder_open_failed'), ok ? 'success' : 'error');
      });
  } else {
    clipboardOk.then(ok => {
      this.showToast(ok ? window.t('common.open_local.path_copied', { path: displayPath }) : window.t('common.open_local.copy_failed'), ok ? 'success' : 'error');
    });
  }
}
