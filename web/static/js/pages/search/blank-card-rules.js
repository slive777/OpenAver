/**
 * blank-card-rules.js — 查不到時的空白結果卡（TASK-183-T2）。
 * 純函式、零 window／DOM 依賴、無 module 級可變狀態。
 */

/**
 * makeBlankCard(file) → 空白結果卡物件
 * 字串欄位全 ''、陣列欄位全 []，不出現 undefined／null；番號預填 file.number。
 * 住在 file.blankCard，不進 file.searchResults。
 */
export function makeBlankCard(file) {
    return {
        _blank: true,
        _source: 'auto',
        number: (file && file.number) || '',
        title: '',
        translated_title: '',
        date: '',
        maker: '',
        actors: [],
        tags: [],
        cover: '',
        source: '',
    };
}

/**
 * adoptIntoBlankFile(fileList, target, variant) → true（已寫入）／false（丟棄）
 * 進階搜尋查到的結果只掛到 target.filePath 那個檔（以 path 認檔，不比 index）。
 * 該檔已不在清單、或已先查到正式結果時靜默丟棄、不動任何檔。
 * 不認得「目前檔」、不碰共享 UI 狀態。
 */
export function adoptIntoBlankFile(fileList, target, variant) {
    const file = fileList.find(f => f.path === target.filePath);
    if (!file) return false;
    if (file.searchResults?.length > 0) return false;
    file.searchResults = [variant];
    file.searched = true;
    file.selectedCandidateIndex = 0;
    file.hasMoreResults = false;
    file.blankCard = null;
    if (!file.number) file.number = variant.number;
    return true;
}
