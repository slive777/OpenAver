/**
 * help-tabs.js — 說明頁三分頁外殼（TASK-191a-T1）
 *
 * 獨立 Alpine 元件（Alpine.data('helpTabs')），不進 mergeState。
 * 自有 key 僅 helpTab／selectHelpTab／syncHelpTabFromHash（＋init）；外求只用 $el／$nextTick。
 * 形狀照 settings-tabs.js，去掉 localStorage：預設分頁由 SSR 的引導旗標決定。
 *
 * 舞台引擎（TASK-191a-T5，CD-191a-2／-6）：控制器存在本模組的 Map（lazy 建立），不進 Alpine state。
 * init／selectHelpTab／syncHelpTabFromHash 都走同一個 applyTab：舊分頁 deactivate → 捲動規則 → 改 helpTab →
 * 新 panel 真的有版面後才 activate。
 */
import { createStage } from './stage-engine.js';
import { scene as libraryScene } from './stage-library.js';
import { scene as organizeScene } from './stage-organize.js';

const TABS = ['library', 'organize', 'manual'];

const isTab = (v) => TABS.includes(v);

const SCENES = { library: libraryScene, organize: organizeScene };
const stages = new Map(); // 分頁 id → 舞台控制器（lazy）
let activationToken = 0;  // 連續切換時，作廢還在等版面的舊 activate

// 優先序：hash 是分頁 id > hash 是手冊內某元素 id（→ manual）> 引導未完成 → library > manual
// 任何輸入都回三個合法分頁之一。
export function resolveHelpTab({ hash, tutorialCompleted, panelOf } = {}) {
    const id = String(hash ?? '').replace(/^#/, '');
    if (isTab(id)) return id;
    if (id && typeof panelOf === 'function' && isTab(panelOf(id))) return panelOf(id);
    return tutorialCompleted ? 'manual' : 'library';
}

function currentHash() {
    return typeof location === 'undefined' ? '' : location.hash;
}

function panelOf(id) {
    if (typeof document === 'undefined') return null;
    return document.getElementById(id)?.closest?.('[data-help-panel]')?.dataset.helpPanel ?? null;
}

// Alpine 的 x-show 把 display 還原排在 requestAnimationFrame、$nextTick 是 setTimeout，
// 兩者都可能早於元素真的有版面（display:none 的元素 scrollIntoView 無效）。
// 逐幀等 getClientRects 非空再動作（有上限，不寫固定 sleep；形狀同 settings-tabs.js）。
function whenRendered(el, fn, frames = 30) {
    if (el.getClientRects().length > 0 || frames <= 0) { fn(); return; }
    requestAnimationFrame(() => whenRendered(el, fn, frames - 1));
}

// 章節錨點（CD-191a-3 第 5 點）：hash 指到手冊的某一列 → 展開該列、版面出現後捲到。
// 分頁 id 或其他 hash 不開任何列、不捲動。捲動後不被固定頂欄蓋住由 help.css 的 scroll-margin-top 負責。
function revealChapter() {
    const id = currentHash().replace(/^#/, '');
    const el = id && !isTab(id) ? document.getElementById(id) : null;
    const row = el?.matches?.('details.help-manual-row') ? el : null;
    if (!row) return;
    row.open = true;
    whenRendered(row, () => row.scrollIntoView({ block: 'start' }));
}

function stageOf(name) {
    if (!SCENES[name] || typeof document === 'undefined') return null;
    if (!stages.has(name)) {
        const root = document.querySelector('.hs-root[data-hs-stage="' + name + '"]');
        if (!root) return null;
        stages.set(name, createStage(root, SCENES[name]));
    }
    return stages.get(name);
}

// 切分頁的捲動規則（CD-191a-6）：分頁列已黏在頂端（捲過了定位點）時，把頁面帶回「分頁列正下方」，
// 讓新舞台從第一步開始。定位點用不 sticky 的 .help-tabs-panels（分頁列自己的 rect 在 sticky 時頂端恆為 0）。
// <1024 分頁列不黏，不套用；先捲再換分頁（FE-CSS-17）。
function scrollToTabsAnchor() {
    const tabs = document.querySelector('.help-tabs');
    const panels = document.querySelector('.help-tabs-panels');
    if (!tabs || !panels || getComputedStyle(tabs).position !== 'sticky') return;
    const target = panels.getBoundingClientRect().top + window.scrollY - tabs.getBoundingClientRect().height;
    if (window.scrollY > target) window.scrollTo({ top: target, behavior: 'instant' });
}

function applyTab(vm, next, { init = false } = {}) {
    const prev = vm.helpTab;
    if (!init && next === prev) return;
    const token = ++activationToken;
    stages.get(prev)?.deactivate();
    if (!init) scrollToTabsAnchor();
    vm.helpTab = next;
    const stage = stageOf(next);
    if (!stage) return;
    // 等新 panel 真的有版面（x-show 晚一幀，FE-ALPINE-17）才啟動；窄螢幕／減少動態下 panel 有版面、畫布沒有，
    // 由 activate() 自己判斷不啟動 scroll 機制。
    // 不用 vm.$el：在 @click 內 $el 是被點的按鈕，不是元件根
    const panel = document.querySelector('[data-help-panel="' + next + '"]');
    whenRendered(panel, () => { if (token === activationToken) stage.activate(); });
}

export function helpTabs() {
    return {
        helpTab: 'library', // FE-ALPINE-06：無條件宣告；init() 依 hash／旗標改寫（x-cloak 擋住閃爍）

        init() {
            applyTab(this, resolveHelpTab({
                hash: currentHash(),
                tutorialCompleted: this.$el.dataset.tutorialCompleted === 'true',
                panelOf,
            }), { init: true });
            this.$nextTick(revealChapter);
        },

        destroy() {
            // 保險：說明頁不會被 swap 掉，這不是主路徑
            activationToken++;
            for (const stage of stages.values()) stage.deactivate();
            stages.clear();
        },

        selectHelpTab(name) {
            if (!isTab(name)) return;
            applyTab(this, name);
            // replaceState：不增歷史、不觸發 hashchange
            try { history.replaceState(history.state, '', '#' + name); } catch { /* 無 history 環境 */ }
        },

        syncHelpTabFromHash() {
            if (!currentHash().replace(/^#/, '')) return; // hash 被清空：留在目前分頁
            applyTab(this, resolveHelpTab({
                hash: currentHash(),
                tutorialCompleted: this.$el.dataset.tutorialCompleted === 'true',
                panelOf,
            }));
            this.$nextTick(revealChapter);
        },
    };
}
