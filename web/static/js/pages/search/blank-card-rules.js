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
