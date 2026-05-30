/**
 * long-press.js — 可複用長壓 Alpine state mixin（62b-1，決策 #2）
 *
 * 通用 700ms 長壓 timer + click guard，供多入口共用：
 *   - Showcase grid 缺卡 enrich-btn（tap=enrich / 長壓=進階重刮）
 *   - Showcase lightbox cover-actions 🔍 enrich-btn（同上）
 *   - （62c-2）Search 送出鈕 #btnSubmit 統一接通（advanced-picker.js 的 timer/clickGuard 已移除，改接此 helper；
 *      form submit guard 一併移除 — US8 由 longPressClickGuard 的 preventDefault 取消 submit 按鈕隱式 form 送出保護）
 *
 * factory mixin，透過 longPressState.call(this) 接入 main.js mergeState（descriptor-preserving）。
 * method 非 getter（規避 Alpine reactivity 凍結；CD-62-14 #0）。
 *
 * 契約（鏡像 advanced-picker.js 長壓核心邏輯；六事件 wiring 一律傳 $event，見下方 synthetic-mouse 抑制）：
 *   longPressStart(cb, enabledFn, event) — 抑制窗內的 synthetic mousedown early-return（不碰旗標/timer）→
 *       設旗標 → gate（enabledFn 回 false 不啟 timer）→ 700ms 後 fire cb。
 *   longPressEnd(event) / longPressCancel(event) — 清 timer（mouseup/touchend vs mouseleave/touchcancel）；
 *       touchend/touchcancel 時設抑制窗 _lpSuppressMouseUntil = performance.now() + 700ms。
 *   longPressClickGuard(ev) — 長壓 fire 過 → 吞掉同一次 click（preventDefault + stopPropagation）並重置旗標。
 *
 * cb / enabledFn 由 template 以 arrow closure 傳入（→ this / video 在元件作用域解析），
 * 本 mixin 的 method 為 plain object method（Alpine 在 mergeState 後把 this 綁到元件）。
 *
 * touch synthetic-mouse 抑制（Codex PR#47 P2，選項 A）：
 *   touch 瀏覽器在 touchend/touchcancel 後補發 compatibility mouse events（mousedown→mouseup→click）。
 *   W3C Touch Events §7 對 synthetic event 的 target 是 UA 裁量（"may" dispatch），不保證打到當前 DOM
 *   （modal backdrop）—— 某些 UA 派回原按鈕 → synthetic mousedown 進 longPressStart 清掉 _lpFired →
 *   後續 synthetic click 的 guard 失效 → 長壓開 picker 同時又觸發底層 tap（雙觸發）。
 *   修法：touchend/touchcancel 記 monotonic timestamp（_lpSuppressMouseUntil = now + 700ms），抑制窗內的
 *   synthetic mousedown 在 longPressStart 開頭 early-return（不碰 _lpFired、不啟 timer）。method 須接 $event。
 */

const LONG_PRESS_MS = 700;   // 與 advanced-picker.js:14 LONG_PRESS_MS 對齊

export function longPressState() {
    return {
        // ── 長壓 state ──
        _lpTimer: null,
        _lpFired: false,   // 長壓已觸發旗標（攔截同一次 click）
        _lpSuppressMouseUntil: 0,   // touchend/touchcancel 後抑制 synthetic mousedown 的 monotonic 截止時間（Codex PR#47 P2）

        /**
         * 長壓開始（@mousedown / @touchstart）。
         * @param {Function} cb        — fire callback（700ms 達標後執行，如 () => openRescrape(video,'enrich')）
         * @param {Function} [enabledFn] — gate：回 false 則不啟 timer（如 () => rescrapeEnabled()）
         * @param {Event}    [event]    — 原始事件（傳 $event）：用於 touch synthetic mousedown 抑制判斷
         */
        longPressStart(cb, enabledFn, event) {
            // touch synthetic-mouse 抑制（Codex PR#47 P2）：touchend 後 UA 補發的 compatibility
            // mousedown 不得清掉 touch 長壓設的 _lpFired（否則後續 synthetic click guard 失效 → 雙觸發）。
            // W3C Touch Events §7：synthetic event target 由 UA 裁量，不保證打到 modal backdrop。
            // 必在下方 this._lpFired = false reset 之前 early-return，否則旗標已被清。
            if (event && event.type === 'mousedown' && performance.now() < this._lpSuppressMouseUntil) {
                return;   // synthetic mousedown：早退，不碰 _lpFired、不啟 timer
            }
            // 【load-bearing invariant — 勿移到 gate 之下】每次新長壓在自己的 click-guard 求值前先清旗標，
            // 中和「長壓開了 modal、放開的 click 落在 backdrop → 旗標卡在 true」（Codex P2）造成下一次
            // pointer/touch tap-enrich 被吞的疑慮：下一次互動的 mousedown/touchstart 必先進此處重置，click 才求值。
            // ⚠️ 鍵盤 / 輔助技術以 click 啟用（無 mousedown 前導）不經此處 → 改由 modal 關閉時 longPressReset() 兜底
            //    （Codex 二輪 P3：旗標只在 modal 關閉、enrich 鈕重新可點後才有害，closeRescrape 此時清乾淨）。
            this._lpFired = false;
            if (enabledFn && !enabledFn()) return;   // gate off → no-op（toggle OFF 時只剩 tap）
            if (this._lpTimer !== null) {
                clearTimeout(this._lpTimer);
            }
            this._lpTimer = setTimeout(() => {
                this._lpTimer = null;
                this._lpFired = true;   // 攔截後續同一次 click
                cb();
            }, LONG_PRESS_MS);
        },

        // 放開（@mouseup / @touchend）→ 清 timer（未達標則不 fire）。
        // touchend：開抑制窗，吞掉 UA 隨後補發的 synthetic mousedown（Codex PR#47 P2）。
        longPressEnd(event) {
            if (event && event.type === 'touchend') {
                this._lpSuppressMouseUntil = performance.now() + LONG_PRESS_MS;
            }
            if (this._lpTimer !== null) {
                clearTimeout(this._lpTimer);
                this._lpTimer = null;
            }
        },

        // 移開 / 取消（@mouseleave / @touchcancel）→ 清 timer。
        // touchcancel：同樣開抑制窗（touch 序列以 touchcancel 收尾時 UA 仍可能補發 synthetic mouse；Codex PR#47 P2）。
        longPressCancel(event) {
            if (event && event.type === 'touchcancel') {
                this._lpSuppressMouseUntil = performance.now() + LONG_PRESS_MS;
            }
            if (this._lpTimer !== null) {
                clearTimeout(this._lpTimer);
                this._lpTimer = null;
            }
        },

        // 兜底清旗標（modal 關閉時呼叫，如 closeRescrape）：涵蓋鍵盤 / 輔助技術以 click 啟用
        // （無 mousedown 前導，繞過 longPressStart 的 top reset）造成的長壓殘留旗標。modal 開著時
        // enrich 鈕被遮無法點，旗標無害；關閉後鈕重新可點，此處清乾淨防吞下一次 keyboard quick-enrich。
        longPressReset() {
            this._lpFired = false;
            if (this._lpTimer !== null) {
                clearTimeout(this._lpTimer);
                this._lpTimer = null;
            }
        },

        // @click guard：長壓 fire 過 → 吞掉這次 click（避免長壓完又觸發 tap 的 enrich）並消化旗標。
        // 回傳 truthy 時，template `longPressClickGuard($event) || enrichVideo(...)` 的短路會跳過 enrich。
        longPressClickGuard(ev) {
            if (this._lpFired) {
                ev.preventDefault();
                ev.stopPropagation();
                this._lpFired = false;
                return true;
            }
            return false;
        },
    };
}
