/**
 * ai-services-card.js — 設定頁「AI 功能」卡分頁殼（TASK-186-T2）
 *
 * 獨立 Alpine 元件（Alpine.data('aiServicesCard')），不進 mergeState。
 * 自有 key 僅 aiTab／selectAiTab；外求 0。localStorage 鍵 settings_ai_tab。
 */

const KEY = 'settings_ai_tab';
const AI_TABS = ['translate', 'similar'];

function readAiTab() {
    try {
        const v = localStorage.getItem(KEY);
        return AI_TABS.includes(v) ? v : 'translate';
    } catch {
        return 'translate';
    }
}

function writeAiTab(name) {
    try {
        localStorage.setItem(KEY, name);
    } catch {
        /* 隱私模式等：記憶失敗不影響切分頁 */
    }
}

export function aiServicesCard() {
    return {
        aiTab: readAiTab(),

        selectAiTab(name) {
            if (!AI_TABS.includes(name)) return;
            this.aiTab = name;
            writeAiTab(name);
        },
    };
}
