/**
 * SearchFile - 檔案模組
 * 檔案列表、批次操作、番號解析、拖拽處理
 */

// === 檔名處理工具函數 ===

/**
 * 檢查文字是否包含中文
 */
function hasChinese(text) {
    if (!text) return false;
    return /[\u4e00-\u9fff]/.test(text);
}

/**
 * 清除無意義的來源後綴
 */
function cleanSourceSuffix(text) {
    const patterns = [
        /\s*-\s*Jable\s*TV.*$/i,
        /\s*-\s*Jable.*$/i,
        /\s*-\s*Hayav\s*AV.*$/i,
        /\s*-\s*Hayav.*$/i,
        /\s*-\s*MissAV.*$/i,
        /\s*-\s*J片.*$/i,
        /\s*-\s*免費.*$/i,
        /\s*-\s*Netflav.*$/i,
        /\s*-\s*AV看到飽.*$/i,
        /\s*-\s*Free\s*Japan.*$/i,
        /\s*-\s*Streaming.*$/i,
        /\s*-\s*[A-Za-z]{1,3}\.?$/,
        /\s*-\s*$/,
        /\s+-\d+$/,
    ];
    for (const p of patterns) {
        text = text.replace(p, '');
    }
    return text.trim();
}

// 字幕 pattern 常數（對齊 Python core/scrapers/utils.py::_SUBTITLE_PATTERNS_*）
// eslint-disable-next-line local/no-cjk-literal -- [cjk-exempt: stripSubtitleMarkers 用字幕標記比對資料，非 UI copy，現役路徑（file-list.js:357）]
const _SUBTITLE_BRACKETS = ['[中文字幕]', '【中文字幕】', '[中字]', '【中字】'];
// eslint-disable-next-line local/no-cjk-literal -- [cjk-exempt: stripSubtitleMarkers 用字幕標記比對資料，非 UI copy，現役路徑（file-list.js:357）]
const _SUBTITLE_TEXT_MARKERS = ['中文字幕', '中字', '字幕'];  // 長 pattern 先

/**
 * 剝除片名中的字幕標記（bracket / 純文字 / -C 後綴 / orphan 分隔符）
 * 對齊 Python core/scrapers/utils.py::strip_subtitle_markers()
 *
 * 剝除順序：
 *   1. Bracket（長 pattern 先）：[中文字幕] / 【中文字幕】 / [中字] / 【中字】
 *   2. 純文字（詞根邊界 Unicode property escape，避免誤剝「幕後」「字幕員」複合詞）
 *   2.5 Orphan 分隔符（marker 剝除後頭尾殘留的 - / _）
 *   3. 後綴 -C / _C（後接非英數或 EOS）
 *   4. trim
 */
function stripSubtitleMarkers(name) {
    if (!name) return name;
    // 1. Bracket
    for (const bracket of _SUBTITLE_BRACKETS) {
        name = name.split(bracket).join('');
    }
    // 2. 純文字（詞根邊界：前後非字母/數字 — 含 CJK 與 kana，用 \p{L}\p{N}）
    for (const marker of _SUBTITLE_TEXT_MARKERS) {
        const escaped = marker.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const pattern = new RegExp(`(?<![\\p{L}\\p{N}])${escaped}(?![\\p{L}\\p{N}])`, 'gu');
        name = name.replace(pattern, '');
    }
    // 2.5 marker 剝除後清頭尾 orphan -/_
    name = name.replace(/^[-_]+|[-_]+$/g, '');
    // 3. 後綴 -C / _C
    name = name.replace(/[-_][Cc](?=[^A-Za-z0-9]|$)/g, '');
    return name.trim();
}

/**
 * 從檔名提取中文片名
 */
function extractChineseTitle(filename, number, actors = []) {
    if (!filename) return null;

    let name = filename.replace(/\.[^.]+$/, '');

    if (number) {
        const escapedNum = number.replace(/[-[\]{}()*+?.,\\^$|#\s]/g, '\\$&');
        name = name.replace(new RegExp(`\\[?${escapedNum}\\]?\\s*`, 'gi'), '');
    }
    name = name.replace(/\[?[A-Za-z]{2,7}-?\d{3,5}\]?\s*/g, '');

    name = cleanSourceSuffix(name);
    name = name.replace(/\s+/g, ' ').trim();
    name = stripSubtitleMarkers(name);

    if (actors && actors.length > 0) {
        for (const actor of actors) {
            const escapedActor = actor.replace(/[-[\]{}()*+?.,\\^$|#\s]/g, '\\$&');
            name = name.replace(new RegExp(`^${escapedActor}\\s*-\\s*`, ''), '');
            name = name.replace(new RegExp(`\\s+${escapedActor}$`, ''), '');
        }
    }

    name = name.replace(/\s+[\u4e00-\u9fff]{2,4}$/, '');
    name = name.trim();

    if (name && hasChinese(name) && !/[\u3040-\u309F\u30A0-\u30FF]/.test(name)) {
        return name;
    }
    return null;
}

/**
 * 批次解析檔名（呼叫後端 API，唯一權威來源——不再有前端本地 fallback）
 * @param {string[]} filenames - 檔名列表
 * @param {{signal?: AbortSignal}} [options] - fetch 選項（signal 供呼叫端取消 in-flight 請求）
 * @returns {Promise<Array<{filename: string, number: string|null, has_subtitle: boolean}>>}
 */
async function parseFilenames(filenames, { signal } = {}) {
    const response = await fetch('/api/parse-filename', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filenames }),
        signal
    });
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
    }
    const data = await response.json();
    return data.results;
}

/**
 * 從檔名偵測版本標記關鍵字（邊界正則，與 Python _detect_suffixes 同邏輯）
 * @param {string} filename - 原始檔名
 * @param {string[]} keywords - 設定的關鍵字列表
 * @returns {string[]} 匹配到的關鍵字（如 ["-4k", "-cd1"]）
 */
function detectSuffixes(filename, keywords) {
    if (!filename || !keywords?.length) return [];
    const lower = filename.toLowerCase();
    const escapeRegex = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    return keywords.filter(kw => {
        const pattern = new RegExp(escapeRegex(kw.toLowerCase()) + '(?=[-_.\\s]|$)');
        return pattern.test(lower);
    });
}

/**
 * scrapeFile - Pure API call helper (used by Alpine methods)
 */
async function scrapeFile(file, metadata) {
    const body = {
        file_path: file.path,
        number: metadata.number,
        metadata: metadata
    };
    // 封面上傳 token 只隨「採用的空白卡」送出；有結果的卡一律不帶（避免舊上傳圖蓋掉站方封面）
    if (metadata?.manual_entry === true && file.blankCard?._coverUploadToken) {
        body.cover_upload_token = file.blankCard._coverUploadToken;
    }
    const response = await fetch('/api/scrape-single', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    });
    return await response.json();
}

// === 暴露介面 ===
window.SearchFile = {
    // Utility functions (still needed by Alpine methods)
    hasChinese,
    cleanSourceSuffix,
    stripSubtitleMarkers,
    extractChineseTitle,
    parseFilenames,
    scrapeFile,
    detectSuffixes,
};
