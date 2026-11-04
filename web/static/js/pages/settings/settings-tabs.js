/**
 * settings-tabs.js — 設定頁五分頁外殼（TASK-190a-T1）
 *
 * 獨立 Alpine 元件（Alpine.data('settingsTabs')），不進 mergeState。
 * 自有 key 僅 settingsTab／selectSettingsTab／syncFromHash；外求 0。
 * localStorage 鍵 settings_tab；網址 hash = 分頁 id。
 */

const KEY = 'settings_tab';
const TABS = ['sources', 'scraping', 'gallery', 'ai', 'system'];
const DEFAULT_TAB = 'sources';
const LEGACY_SEC = {
    'sec-search': 'sources',
    'sec-gallery': 'gallery',
    'sec-ai': 'ai',
    'sec-system': 'system',
};

const isTab = (v) => TABS.includes(v);

// 優先序：hash 是分頁 id > 舊 sec-* > hash 是頁內某元素 id（取所屬分頁）> storage > 預設
export function resolveSettingsTab({ hash, stored, panelOf } = {}) {
    const id = String(hash ?? '').replace(/^#/, '');
    let fromHash = null;
    if (isTab(id)) fromHash = id;
    else if (Object.hasOwn(LEGACY_SEC, id)) fromHash = LEGACY_SEC[id];
    else if (id && typeof panelOf === 'function' && isTab(panelOf(id))) fromHash = panelOf(id);
    return fromHash ?? (isTab(stored) ? stored : DEFAULT_TAB);
}

function readStored() {
    try {
        return localStorage.getItem(KEY);
    } catch {
        return null;
    }
}

function writeStored(name) {
    try { localStorage.setItem(KEY, name); } catch { /* 隱私模式等：記憶失敗不影響切分頁 */ }
}

function currentHash() {
    return typeof location === 'undefined' ? '' : location.hash;
}

const tabOfEl = (el) => el?.closest?.('[data-settings-panel]')?.dataset.settingsPanel ?? null;

function panelOf(id) {
    if (typeof document === 'undefined') return null;
    return tabOfEl(document.getElementById(id));
}

// Alpine 的 x-show 把 display 還原排在 requestAnimationFrame、$nextTick 是 setTimeout，
// 兩者都可能早於欄位真的有版面（WebKit 上 focus／scrollIntoView 會落在 display:none 的元素 → 無效）。
// 逐幀等 getClientRects 非空再動作（有上限，不寫固定 sleep；等不到就照做，行為同隱藏元素本來的結果）。
function whenRendered(el, fn, frames = 30) {
    if (el.getClientRects().length > 0 || frames <= 0) { fn(); return; }
    requestAnimationFrame(() => whenRendered(el, fn, frames - 1));
}

// I-2d：欄位 id 進入（或頁內改 hash）時，分頁顯示後再捲到該欄位
function scrollToHashTarget() {
    const id = currentHash().replace(/^#/, '');
    if (!id || isTab(id) || Object.hasOwn(LEGACY_SEC, id)) return;
    const el = document.getElementById(id);
    if (el) whenRendered(el, () => el.scrollIntoView({ block: 'center' }));
}

export function settingsTabs() {
    let batchSeen = false; // 一次 submit 會對每個無效欄位各發一次 invalid，只認 DOM 順序第一個
    return {
        settingsTab: resolveSettingsTab({ hash: currentHash(), stored: readStored(), panelOf }),

        init() {
            writeStored(this.settingsTab); // hash／舊書籤落地的分頁也記住，重整後回到這裡
            this.$nextTick(scrollToHashTarget);
        },

        selectSettingsTab(name) {
            if (!isTab(name)) return;
            this.settingsTab = name;
            writeStored(name);
            // replaceState：不增歷史、不觸發 hashchange
            try { history.replaceState(history.state, '', '#' + name); } catch { /* 無 history 環境 */ }
        },

        // 按儲存時原生驗證擋下、而無效欄位在隱藏分頁 → 切過去再聚焦並顯示原生訊息
        // （@invalid.capture：invalid 不冒泡；欄位 display:none 時瀏覽器聚焦不到、使用者什麼都看不到）
        revealInvalid(ev) {
            if (batchSeen) return;
            batchSeen = true;
            setTimeout(() => { batchSeen = false; }, 0); // 批次邊界，不是等顯示
            const field = ev.target;
            const tab = tabOfEl(field);
            if (!isTab(tab) || tab === this.settingsTab) return; // 已在目前分頁：瀏覽器自己處理
            this.selectSettingsTab(tab);
            this.$nextTick(() => whenRendered(field, () => {
                field.focus();
                field.reportValidity();
            }));
        },

        syncFromHash() {
            const next = resolveSettingsTab({ hash: currentHash(), stored: this.settingsTab, panelOf });
            if (next !== this.settingsTab) {
                this.settingsTab = next;
                writeStored(next);
            }
            this.$nextTick(scrollToHashTarget);
        },
    };
}
