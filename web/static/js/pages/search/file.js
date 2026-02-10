/**
 * SearchFile - 檔案模組
 * 檔案列表、批次操作、番號解析、拖拽處理
 */

// === 檔名處理工具函數 ===

/**
 * 檢查檔名是否包含字幕標記
 * [FALLBACK] 當 /api/parse-filename 失敗時使用
 */
function checkSubtitle(filename) {
    if (!filename) return false;
    const upper = filename.toUpperCase();

    const patterns = ['-C', '_C'];
    for (const p of patterns) {
        const idx = upper.indexOf(p);
        if (idx !== -1) {
            const nextIdx = idx + p.length;
            if (nextIdx >= upper.length || !/[A-Z0-9]/i.test(upper[nextIdx])) {
                return true;
            }
        }
    }

    const chinesePatterns = ['中文字幕', '字幕', '中字', '[中字]', '【中字】'];
    for (const p of chinesePatterns) {
        if (filename.includes(p)) return true;
    }

    return false;
}

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
    name = name.replace(/\[?[A-Za-z]{2,6}-?\d{3,5}\]?\s*/g, '');

    name = cleanSourceSuffix(name);
    name = name.replace(/\s+/g, ' ').trim();
    name = name.replace(/^中文字幕\s*/, '');

    if (actors && actors.length > 0) {
        for (const actor of actors) {
            const escapedActor = actor.replace(/[-[\]{}()*+?.,\\^$|#\s]/g, '\\$&');
            name = name.replace(new RegExp(`^${escapedActor}\\s*-\\s*`, ''), '');
            name = name.replace(new RegExp(`\\s+${escapedActor}$`, ''), '');
        }
    }

    name = name.replace(/\s+[\u4e00-\u9fff]{2,4}$/, '');
    name = name.trim();

    if (name && hasChinese(name) && !window.SearchCore.hasJapanese(name)) {
        return name;
    }
    return null;
}

/**
 * 從檔名提取番號
 * [FALLBACK] 當 /api/parse-filename 失敗時使用
 * 主要路徑應優先呼叫後端 API
 */
function extractNumber(filename) {
    const basename = filename.split(/[/\\]/).pop().replace(/\.[^.]+$/, '');

    const patterns = [
        /\b(FC2-PPV)-(\d{5,7})\b/i,          // FC2-PPV-1234567（優先）
        /\b([A-Z]+\d+-\d+)\b/i,              // T28-103 混合格式（字母+數字-數字）
        /\b([A-Z]{1,5})-(\d{3,5})\b/i,       // SONE-205（支援單字母）
        /\b([A-Z]{2,5})(\d{3,5})\b/i,        // IPTD927（無連字號需 2+ 字母避免誤判）
    ];

    for (const pattern of patterns) {
        const match = basename.match(pattern);
        if (match) {
            const prefix = match[1].toUpperCase();
            // FC2-PPV 特殊處理
            if (prefix === 'FC2-PPV') return `FC2-PPV-${match[2]}`;
            // 混合格式已包含完整番號
            if (pattern === patterns[1]) return prefix;
            // 其他格式需組合
            return `${prefix}-${match[2]}`;
        }
    }
    return null;
}

/**
 * 批次解析檔名（呼叫後端 API）
 * @param {string[]} filenames - 檔名列表
 * @returns {Promise<Array<{filename: string, number: string|null, has_subtitle: boolean}>>}
 */
async function parseFilenames(filenames) {
    try {
        const response = await fetch('/api/parse-filename', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filenames })
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        return data.results;
    } catch (error) {
        console.warn('[parseFilenames] API 失敗，使用本地解析:', error.message);
        // Fallback 到本地解析
        return filenames.map(filename => ({
            filename,
            number: extractNumber(filename),
            has_subtitle: checkSubtitle(filename)
        }));
    }
}

/**
 * 格式化番號（標準化格式）
 */
function formatNumber(input) {
    if (!input) return null;
    const match = input.match(/([A-Z]{1,5})-?(\d{3,7})/i);
    if (match) {
        return `${match[1].toUpperCase()}-${match[2]}`;
    }
    const fc2Match = input.match(/FC2-?PPV-?(\d{5,7})/i);
    if (fc2Match) {
        return `FC2-PPV-${fc2Match[1]}`;
    }
    return input.toUpperCase();
}

/**
 * scrapeFile - Pure API call helper (used by Alpine methods)
 */
async function scrapeFile(file, metadata) {
    const response = await fetch('/api/scrape-single', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            file_path: file.path,
            number: metadata.number,
            metadata: metadata
        })
    });
    return await response.json();
}

// === 暴露介面 ===
window.SearchFile = {
    // Utility functions (still needed by Alpine methods)
    checkSubtitle,
    hasChinese,
    cleanSourceSuffix,
    extractChineseTitle,
    extractNumber,
    formatNumber,
    parseFilenames,
    scrapeFile,
    // Bridge stubs (overwritten by Alpine setupBridgeLayer)
    switchToFile: function() {},
    searchAll: function() {},
    scrapeAll: function() {},
    setFileList: function() {},
    handleFileDrop: function() {},
    renderFileList: function() {},
    renderSearchResultsList: function() {}
};
