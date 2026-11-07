// TASK-195-T9（195d）：只認純數字——正規化後整串 [0-9]+ 才 true。
import { normalizePillValue } from './pill-filter.js';

export function isDigitsOnlySearch(text) {
    return /^[0-9]+$/.test(normalizePillValue(text));
}
