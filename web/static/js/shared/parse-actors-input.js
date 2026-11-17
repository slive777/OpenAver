/**
 * parse-actors-input.js — actress string split (single owner)
 *
 * Moved here from `pages/search/state/result-card.js` (TASK-200c-T5):
 * single owner for the actress-split decision, `pages/` imports this file.
 * Three separators, aligned with the `core/scrapers/actress/wiki_ja.py` precedent.
 */

export function parseActorsInput(str) {
    return str.split(/[、，,]/).map(s => s.trim()).filter(Boolean);
}
