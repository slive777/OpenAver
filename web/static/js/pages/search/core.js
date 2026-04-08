/**
 * SearchCore - T4 後殘留常數
 *
 * T4 完成後，所有函數已搬入 Alpine mixin（state/*.js）：
 * - hasJapanese → state/base.js
 * - checkLocalStatus → state/base.js
 * - translateWithOllama → state/batch.js
 * - _translateWithAI / translateBatch → state/result-card.js + state/batch.js
 * - isBatchTranslating → state/batch.js
 * - loadAppConfig → state/search-flow.js
 * - clearAll → state/search-flow.js
 * - preloadImages → state/navigation.js
 *
 * initDOM / dom / updateClearButton 已刪除（Alpine mixin 改用 $refs）
 * window.SearchCore facade 已刪除（無循環依賴）
 */

// 保留 PAGE_SIZE 供向後相容（state/base.js 已有對應值）
const PAGE_SIZE = 20;

// 保留 STATE_KEY 供向後相容（state/base.js 已有對應值）
const STATE_KEY = 'javhelper_search_state';
