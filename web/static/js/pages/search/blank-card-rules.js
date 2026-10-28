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

const hasText = (v) => String(v || '').trim() !== '';

/**
 * isBlankOrganizable(card) → 空白卡的番號與標題都有字才算可整理（TASK-183-T4）
 */
export function isBlankOrganizable(card) {
    return hasText(card.number) && hasText(card.title);
}

/**
 * organizeState(file) → 'ready'｜'needs_number'｜'none'
 * ready：有搜尋結果（優先於殘留的 blankCard），或空白卡番號＋標題皆填。
 * needs_number：只填了標題、番號空白。其餘（含只填標籤／日期／演員）為 none。
 */
export function organizeState(file) {
    if (file.searched && file.searchResults?.length > 0) return 'ready';
    const card = file.blankCard;
    if (!card) return 'none';
    if (isBlankOrganizable(card)) return 'ready';
    if (hasText(card.title)) return 'needs_number';
    return 'none';
}

/**
 * skipAutoTranslate(metadata) → 手填的中文片名不被自動翻譯蓋掉
 */
export function skipAutoTranslate(metadata) {
    return metadata.manual_entry === true && hasText(metadata.translated_title);
}
