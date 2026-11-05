/**
 * help-tabs.js — 說明頁三分頁外殼（TASK-191a-T1）
 *
 * 獨立 Alpine 元件（Alpine.data('helpTabs')），不進 mergeState。
 * 自有 key 僅 helpTab／selectHelpTab／syncHelpTabFromHash（＋init）；外求只用 $el。
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

export function helpTabs() {
    return {
        helpTab: 'library', // FE-ALPINE-06：無條件宣告；init() 依 hash／旗標改寫（x-cloak 擋住閃爍）

        init() {
            this.helpTab = resolveHelpTab({
                hash: currentHash(),
                tutorialCompleted: this.$el.dataset.tutorialCompleted === 'true',
                panelOf,
            });
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
        },
    };
}
