/**
 * SearchState - Blank Card Mixin（TASK-183-T2）
 * 查不到時給右側一張可編輯的空白結果卡；資料住 file.blankCard（隨 fileList 整包持久化）。
 */
import { makeBlankCard } from '../blank-card-rules.js';

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
    };
}
