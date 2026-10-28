/**
 * SearchState - Blank Card Mixin（TASK-183-T2）
 * 查不到時給右側一張可編輯的空白結果卡；資料住 file.blankCard（隨 fileList 整包持久化）。
 */
import { makeBlankCard, adoptIntoBlankFile } from '../blank-card-rules.js';

export function searchStateBlankCard() {
    return {
    /**
     * 冪等：file.blankCard 已存在就不覆寫（切走再切回不得洗掉使用者填的內容）。
     * 重複（duplicate）與已有 NFO 的檔不建；失敗記憶 not_found 的檔要建（它們正是查不到的檔）。
     */
    _ensureBlankCard(file) {
        if (!file || file.blankCard) return;
        if (file.skipReason === 'duplicate' || file.has_nfo) return;
        file.blankCard = makeBlankCard(file);
    },

    /**
     * 進階搜尋查到的結果掛回開窗那個檔（以 path 認檔）。回 true＝已寫入、false＝靜默丟棄。
     * 不走一般搜尋結果提交：listMode 不變（仍在檔案模式，不跳手動搜尋）。
     * 開窗那個檔仍是目前檔才同步共享 UI；否則只改那個檔，共享狀態不動。
     */
    _adoptIntoBlankFile(t, variant) {
        const ok = adoptIntoBlankFile(this.fileList, t, variant);
        if (!ok) return false;
        const file = this.fileList[this.currentFileIndex];
        if (file && file.path === t.filePath) {
            this.searchResults = file.searchResults;
            this.currentIndex = 0;
            this._resetCoverState();
            this.checkLocalStatus(this.searchResults);
            this.fetchUserTagsForCurrent?.();
            this._candidateReplaceSeq++;
        }
        this.saveState();
        return true;
    },
    };
}
