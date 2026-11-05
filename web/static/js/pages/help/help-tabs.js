/**
 * help-tabs.js — 說明頁三分頁外殼（TASK-191a-T1）
 *
 * 獨立 Alpine 元件（Alpine.data('helpTabs')），不進 mergeState。
 * 自有 key 僅 helpTab／selectHelpTab／syncHelpTabFromHash（＋init）；外求只用 $el／$nextTick。
 * 形狀照 settings-tabs.js，去掉 localStorage：預設分頁由 SSR 的引導旗標決定。
 */

const TABS = ['library', 'organize', 'manual'];

const isTab = (v) => TABS.includes(v);

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

export function helpTabs() {
    return {
        helpTab: 'library', // FE-ALPINE-06：無條件宣告；init() 依 hash／旗標改寫（x-cloak 擋住閃爍）

        init() {
            this.helpTab = resolveHelpTab({
                hash: currentHash(),
                tutorialCompleted: this.$el.dataset.tutorialCompleted === 'true',
                panelOf,
            });
            this.$nextTick(revealChapter);
        },

        selectHelpTab(name) {
            if (!isTab(name)) return;
            this.helpTab = name;
            // replaceState：不增歷史、不觸發 hashchange
            try { history.replaceState(history.state, '', '#' + name); } catch { /* 無 history 環境 */ }
        },

        syncHelpTabFromHash() {
            if (!currentHash().replace(/^#/, '')) return; // hash 被清空：留在目前分頁
            this.helpTab = resolveHelpTab({
                hash: currentHash(),
                tutorialCompleted: this.$el.dataset.tutorialCompleted === 'true',
                panelOf,
            });
            this.$nextTick(revealChapter);
        },
    };
}
