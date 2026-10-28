/**
 * SearchState - Result Card Mixin
 * 包含：結果卡片顯示、編輯、翻譯、標籤、本地狀態
 */
import { openLocal } from '@/shared/open-local.js';
import { isCloudTranslateProvider, translateFailureToastKey } from '@/shared/translate-provider.js';

// TASK-106-T3 CD-106-8: 純函式，module-level named export（非 this.-bound method）
// 三分隔符 `、`/`，`（U+FF0C 全形逗號）/`,`，對齊 core/scrapers/actress/wiki_ja.py:108 先例。
export function parseActorsInput(str) {
    return str.split(/[、，,]/).map(s => s.trim()).filter(Boolean);
}

// TASK-113c-T8：三顆純函式已搬至 shared/cover-fallback.js（單一所有者）。
// 刻意**不 re-export**——re-export 等於留第二條取得同一個決策的路徑，
// 與本 branch 的主張相反。各 consumer 一律直接 import 那個唯一所有者。
import { resolveResultCoverUrl, shouldFallbackToCover } from '@/shared/cover-fallback.js';

// ---- 131b-T2: 三組行內編輯的共用實作（module-level，不進頂層 return）----
// 收斂理由：下面這個 identity guard 曾被 Codex PR#115 / PR#116 在四份重複實作裡各修一次。
// 共用之後「同一個修正只需改一處」。

// TASK-106 Option C Part 1（唯一權威保證）：current() 已換到別的候選/檔（不論是
// navigate/switchToFile/scrapeAll/grid/lightbox 或任何未來路徑造成的）就擋下寫入，
// 不寫錯候選。必須在任何寫入之前、最先執行。
// Codex PR#115 P2：三個欄位各有專屬的 _editSourceX，不共用單一欄位——title/chinese/actors
// 三個 editingX 可同時開啟，共用一個欄位會讓後開啟者覆蓋先開啟者捕獲的來源，
// 使先開啟者的 guard 誤判「候選未換」而把 stale 內容寫進別的候選（data pollution）。
// Codex PR#116 P2：date 也走同一個 guard（同源 pattern，fail-closed：未捕獲 null 也算變了）。
function candidateChanged(ctx, c, sourceKey) {
    return c !== ctx[sourceKey];
}

const INLINE_EDIT_FIELDS = {
    title: {
        editing: 'editingTitle',
        buffer: 'editedTitleValue',
        source: '_editSourceTitle',
        ref: 'titleInput',
        read: (ctx, c) => c.title || '',
        write: (ctx, c, raw) => { c.title = raw.trim(); c._titleEdited = true; },
    },
    chineseTitle: {
        editing: 'editingChineseTitle',
        buffer: 'editedChineseTitleValue',
        source: '_editSourceChineseTitle',
        ref: 'chineseTitleInput',
        // 空白卡只讀 translated_title：chineseTitleText() 空時回 '-'，會把 '-' 預填進編輯框
        read: (ctx, c) => c._blank ? (c.translated_title || '') : (ctx.chineseTitleText() || ''),
        write: (ctx, c, raw) => { c.translated_title = raw.trim(); c._chineseTitleEdited = true; },
    },
    actors: {
        editing: 'editingActors',
        buffer: 'editedActorsValue',
        source: '_editSourceActors',
        ref: 'actorsInput',
        read: (ctx, c) => (c.actors || []).join(', '),
        // 刻意不 .trim()：交給 parseActorsInput 逐段 trim。也刻意沒有 _xxxEdited 旗標。
        write: (ctx, c, raw) => { c.actors = parseActorsInput(raw); },
    },
    // TASK-183-T2：空白結果卡的番號／片商（模板只在 current()._blank 時露出鉛筆）
    number: {
        editing: 'editingNumber',
        buffer: 'editedNumberValue',
        source: '_editSourceNumber',
        ref: 'numberInput',
        read: (ctx, c) => c.number || '',
        write: (ctx, c, raw) => {
            c.number = raw.trim();
            // 空白卡改番號要回寫到所屬檔案：「重試失敗」「搜尋全部」讀的是 file.number，
            // 不同步就會繼續搜舊番號。照 enterNumber（file-list.js）的做法兩處都寫。
            // 以 index 取檔，不比對物件身分（Alpine proxy 會讓 === 失效）。一般結果卡不動 file.number。
            if (ctx.listMode === 'file' && c._blank) {
                const f = ctx.fileList?.[ctx.currentFileIndex];
                if (f && f.blankCard) f.number = c.number;
            }
        },
    },
    maker: {
        editing: 'editingMaker',
        buffer: 'editedMakerValue',
        source: '_editSourceMaker',
        ref: 'makerInput',
        read: (ctx, c) => c.maker || '',
        write: (ctx, c, raw) => { c.maker = raw.trim(); },
    },
};

function startInlineEdit(ctx, name) {
    const f = INLINE_EDIT_FIELDS[name];
    const c = ctx.current();
    ctx[f.buffer] = f.read(ctx, c);
    ctx[f.editing] = true;
    ctx[f.source] = c;
    ctx.$nextTick(() => {
        ctx.$refs[f.ref]?.focus();
        ctx.$refs[f.ref]?.select();
    });
}

function confirmInlineEdit(ctx, name) {
    const f = INLINE_EDIT_FIELDS[name];
    const c = ctx.current();
    if (candidateChanged(ctx, c, f.source)) {
        ctx[f.editing] = false;
        return;
    }
    f.write(ctx, c, ctx[f.buffer]);
    ctx[f.editing] = false;
    ctx.saveState();
}

function cancelInlineEdit(ctx, name) {
    ctx[INLINE_EDIT_FIELDS[name].editing] = false;
}

export function searchStateResultCard() {
    return {
    // ===== T1c: Result Card Computed =====

    current() {
        if (this.listMode === 'file' && this.fileList[this.currentFileIndex]) {
            const file = this.fileList[this.currentFileIndex];
            const results = file.searchResults || [];
            return results[this.currentIndex] || file.blankCard || {};
        }
        return this.searchResults[this.currentIndex] || {};
    },

    // 改為 method（原為 getter）
    hasSubtitle() {
        if (this.listMode === 'file' && this.fileList[this.currentFileIndex]) {
            return this.fileList[this.currentFileIndex].hasSubtitle || false;
        }
        return false;
    },

    // 當前結果的版本標記 badges（Fix-1）
    currentSuffixes() {
        if (this.listMode === 'file' && this.fileList[this.currentFileIndex]) {
            return this.fileList[this.currentFileIndex].suffixes || [];
        }
        return [];  // 雲端搜尋模式無 suffix
    },

    // 改為 method（原為 getter）
    chineseTitle() {
        if (this.listMode === 'file' && this.fileList[this.currentFileIndex]) {
            return this.fileList[this.currentFileIndex].chineseTitle || null;
        }
        return null;
    },

    hasChineseTitle() {
        const c = this.current();
        return !!(c.translated_title || this.chineseTitle());
    },

    chineseTitleLabel() {
        const c = this.current();
        if (c._blank) return window.t('search.label.chinese_title');
        if (c.translated_title) return window.t('search.label.chinese_title_ai');
        return window.t('search.label.chinese_title');
    },

    chineseTitleText() {
        const c = this.current();
        if (c._blank) return c.translated_title || '-';
        return c.translated_title || this.chineseTitle() || '-';
    },

    // TASK-113c-T7：模板（hero lightbox / grid card）呼叫的 Alpine 方法包裝，
    // 委派給純函式 resolveResultCoverUrl（module-level export，見上方）。
    // 契約：回傳「原始圖片 URL」，proxy 包裹留在各呼叫點（裁決 2）。
    resolveCoverUrl(result) {
        return resolveResultCoverUrl(result);
    },

    coverUrl() {
        const c = this.current();
        // TASK-113c-T3b/T7: preview_cover_url 優先（破圖修復），_previewFailed 為 true
        // 時改用 cover（見 resolveResultCoverUrl）。proxy 包裹仍在此呼叫點處理（裁決 2）。
        const cover = this.resolveCoverUrl(c);
        if (!cover) return '';
        // 本機暫存的上傳封面不是外站圖，套 proxy 會被拒
        if (cover.startsWith('/api/scrape-cover/')) return cover;
        return `/api/proxy-image?url=${encodeURIComponent(cover)}`;
    },

    canTranslate() {
        const c = this.current();
        return this.appConfig?.translate?.enabled &&
               !this.chineseTitle() &&
               !c.translated_title &&
               !c._blank &&
               c.title &&
               this.hasJapanese(c.title) &&
               !this.isBatchTranslating(this.currentIndex);
    },

    hasLocalBadge() {
        return this.current()?._localStatus?.exists || false;
    },

    localBadgeTitle() {
        const status = this.current()?._localStatus;
        if (!status || !status.exists) return '';
        return status.count > 1
            ? window.t('search.local.has_local_count', { count: status.count })
            : window.t('search.local.has_local');
    },

    // ===== T1c: Title Edit Methods =====（實作見檔頭的 INLINE_EDIT_FIELDS）

    startEditTitle() { startInlineEdit(this, 'title'); },
    confirmEditTitle() { confirmInlineEdit(this, 'title'); },
    cancelEditTitle() { cancelInlineEdit(this, 'title'); },

    startEditChineseTitle() { startInlineEdit(this, 'chineseTitle'); },
    confirmEditChineseTitle() { confirmInlineEdit(this, 'chineseTitle'); },
    cancelEditChineseTitle() { cancelInlineEdit(this, 'chineseTitle'); },

    // ===== TASK-183-T2: Number / Maker Edit Methods（空白結果卡）=====

    startEditNumber() { startInlineEdit(this, 'number'); },
    confirmEditNumber() { confirmInlineEdit(this, 'number'); },
    cancelEditNumber() { cancelInlineEdit(this, 'number'); },

    startEditMaker() { startInlineEdit(this, 'maker'); },
    confirmEditMaker() { confirmInlineEdit(this, 'maker'); },
    cancelEditMaker() { cancelInlineEdit(this, 'maker'); },

    // ===== T3: Actor Edit Methods =====

    startEditActors() { startInlineEdit(this, 'actors'); },
    confirmEditActors() { confirmInlineEdit(this, 'actors'); },
    cancelEditActors() { cancelInlineEdit(this, 'actors'); },

    // ===== T7: Date Edit Methods =====
    // date 刻意**不**套 INLINE_EDIT_FIELDS：它沒有 editing flag、沒有 buffer、沒有 cancel、
    // 簽名也不同（吃 value）。硬套會生出三個 null 欄位的設定物件。
    // 但它**共用同一份 candidateChanged**——那正是被 Codex 修過四次的東西。

    startEditDate() {
        // TASK-106 Codex PR#116 P2: 打開原生日曆當下捕獲候選物件參照，供 confirmEditDate 比對，
        // 防「選日期期間候選被換（背景批次/換源/切檔）→ 寫錯候選」。掛 date input @focus。
        this._editSourceDate = this.current();
    },

    confirmEditDate(value) {
        // TASK-106 Codex PR#116 P2（與 confirmEditTitle 同源的 identity guard）。掛 date input @change。
        const c = this.current();
        if (candidateChanged(this, c, '_editSourceDate')) return;   // fail-closed：候選變了（含未捕獲 null）就丟棄不寫
        c.date = value;
        this.saveState();
    },

    // ===== T1c: Translate =====

    async translateWithAI() {
        if (this.isTranslating) return;
        this.isTranslating = true;
        try {
            await this._translateWithAILogic();
        } catch (error) {
            console.error('[Translate] 翻譯失敗:', error);
            const key = translateFailureToastKey(error?.reason);
            this.showToast(window.t(key), key === 'search.toast.translate_rate_limited' ? 'warning' : 'error');
        } finally {
            this.isTranslating = false;
        }
    },

    /**
     * 核心翻譯邏輯（從 core.js._translateWithAI 搬移）
     * 雲端模式（Gemini／OpenAI／Claude）：只翻譯當前片
     * Ollama 模式：批次翻譯從當前位置開始的 1 片
     */
    async _translateWithAILogic() {
        // === 雲端模式（Gemini／OpenAI／Claude）：只翻譯當前片 ===
        if (isCloudTranslateProvider(this.appConfig?.translate?.provider)) {
            let currentResult = null;

            if (this.listMode === 'file' && this.fileList[this.currentFileIndex]) {
                const results = this.fileList[this.currentFileIndex].searchResults || [];
                currentResult = results[this.currentIndex];
            } else {
                currentResult = this.searchResults[this.currentIndex];
            }

            if (!currentResult || !currentResult.title || !this.hasJapanese(currentResult.title)) {
                throw new Error(window.t('search.error.no_translation_needed'));
            }

            const result = await this.translateWithOllama(currentResult.title, 'translate', currentResult);

            if (result.success && result.result) {
                // 41d-T5: 用 captured currentResult ref 避免 await 期間切檔 race
                // currentResult 在 L158/L160 已捕獲為 searchResults 元素的 object reference，
                // 直接賦值即更新原陣列元素，無需 re-index this.fileList[this.currentFileIndex]
                currentResult.translated_title = result.result;
                this.saveState();
            } else {
                const err = new Error(result.error || window.t('search.error.translate_failed_generic'));
                err.reason = result.reason;
                throw err;
            }

            return;  // 雲端模式結束
        }

        // === Ollama 模式：批次翻譯 1 片 ===
        const batch = [];
        const batchMeta = [];

        if (this.listMode === 'file') {
            for (let fi = this.currentFileIndex; fi < this.fileList.length && batch.length < 1; fi++) {
                const file = this.fileList[fi];
                const results = file.searchResults || [];

                for (let ri = 0; ri < results.length && batch.length < 1; ri++) {
                    const result = results[ri];
                    if (result.title && this.hasJapanese(result.title) && !result.translated_title) {
                        batch.push(result);
                        batchMeta.push({ fileIndex: fi, resultIndex: ri });
                    }
                }
            }
        } else {
            for (let i = this.currentIndex; i < this.searchResults.length && batch.length < 1; i++) {
                const result = this.searchResults[i];
                if (result.title && this.hasJapanese(result.title) && !result.translated_title) {
                    batch.push(result);
                    batchMeta.push({ resultIndex: i });
                }
            }
        }

        if (batch.length === 0) {
            throw new Error(window.t('search.error.no_japanese_title'));
        }

        if (this.listMode !== 'file') {
            batchMeta.forEach(meta => {
                this._addBatchTranslatingIndex(meta.resultIndex);
            });
        }

        const titles = batch.map(r => r.title);
        const translations = await this.translateBatch(titles);

        if (translations && translations.length > 0) {
            translations.forEach((trans, i) => {
                if (!trans) return;
                const meta = batchMeta[i];

                if (this.listMode === 'file') {
                    this.fileList[meta.fileIndex].searchResults[meta.resultIndex].translated_title = trans;
                } else {
                    this.searchResults[meta.resultIndex].translated_title = trans;
                    this._deleteBatchTranslatingIndex(meta.resultIndex);
                }
            });

            this.saveState();
        }

        if (this.listMode !== 'file') {
            batchMeta.forEach(meta => {
                this._deleteBatchTranslatingIndex(meta.resultIndex);
            });
        }
    },

    // ===== T1c: User Tags =====

    /**
     * 取得當前 file 的 user_tags（file-level，非 result-level）(P2)
     * user_tags 是 file-level metadata，與哪個候選結果無關。
     */
    currentUserTags() {
        if (this.listMode === 'file') {
            return this.fileList?.[this.currentFileIndex]?.user_tags || [];
        }
        return [];
    },

    showAddTagInput() {
        this.newTagValue = '';
        this.addingTag = true;
        this.$nextTick(() => {
            this.$refs.tagInput?.focus();
        });
    },

    async confirmAddTag() {
        const tag = this.newTagValue.trim();
        if (!tag) {
            this.addingTag = false;
            return;
        }

        const file = this.fileList?.[this.currentFileIndex];
        const filePath = file?.path || '';
        if (!filePath) {
            this.showToast(window.t('search.error.tag_api_failed'), 'error');
            this.addingTag = false;
            return;
        }

        // E5: 前端去重，避免無謂 API call（P2: 用 file-level user_tags）
        const existingTags = this.fileList[this.currentFileIndex].user_tags || [];
        if (existingTags.includes(tag)) {
            this.addingTag = false;
            this.newTagValue = '';
            return;
        }

        try {
            const resp = await fetch('/api/user-tags', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file_path: filePath, add: [tag] }),
            });
            const data = await resp.json();
            if (data.success) {
                // P2: 更新 file-level user_tags（用 captured file ref 避免 await 期間切檔 race）
                file.user_tags = data.user_tags;
                this.saveState();
                // TASK-143-T4: 唯讀來源且輸出夾沒有 NFO → 標籤只存了 DB，Jellyfin 看不到。
                // 燈箱那側同一條（state-lightbox.js）；這裡不補會讓同一個靜默失敗從搜尋頁復活。
                if (data.readonly_no_output) {
                    this.showToast(window.t('search.error.tag_nfo_not_written'), 'info');
                }
                if (data.nfo_write_blocked) {
                    this.showToast(window.t('search.error.tag_nfo_write_blocked'), 'info');
                }
            } else {
                this.showToast(window.t('search.error.tag_api_failed'), 'error');
            }
        } catch {
            this.showToast(window.t('search.error.tag_api_failed'), 'error');
        }

        this.addingTag = false;
        this.newTagValue = '';
    },

    cancelAddTag() {
        this.addingTag = false;
    },

    async removeUserTag(tag) {
        const file = this.fileList?.[this.currentFileIndex];
        const filePath = file?.path || '';
        if (!filePath) {
            this.showToast(window.t('search.error.tag_api_failed'), 'error');
            return;
        }

        try {
            const resp = await fetch('/api/user-tags', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file_path: filePath, remove: [tag] }),
            });
            const data = await resp.json();
            if (data.success) {
                // P2: 更新 file-level user_tags（用 captured file ref 避免 await 期間切檔 race）
                file.user_tags = data.user_tags;
                this.saveState();
                // TASK-143-T4: 唯讀來源且輸出夾沒有 NFO → 標籤只存了 DB，Jellyfin 看不到。
                // 燈箱那側同一條（state-lightbox.js）；這裡不補會讓同一個靜默失敗從搜尋頁復活。
                if (data.readonly_no_output) {
                    this.showToast(window.t('search.error.tag_nfo_not_written'), 'info');
                }
                if (data.nfo_write_blocked) {
                    this.showToast(window.t('search.error.tag_nfo_write_blocked'), 'info');
                }
            } else {
                this.showToast(window.t('search.error.tag_api_failed'), 'error');
            }
        } catch {
            this.showToast(window.t('search.error.tag_api_failed'), 'error');
        }
    },

    /**
     * 補查當前 file 的 user_tags（策略二：前端 lazy fetch）(41b-T3)
     * 只在 listMode === 'file' 且有 file.path 時補查；靜默忽略失敗。
     * 觸發時機：切換 file 索引、頁面載入時。
     * 注意：不要在每次 current() 呼叫時觸發（避免大量 API 請求）。
     * P2: 寫入 fileList[currentFileIndex].user_tags（file-level）
     */
    async fetchUserTagsForCurrent() {
        if (this.listMode !== 'file') return;
        const file = this.fileList?.[this.currentFileIndex];
        if (!file?.path) return;

        try {
            const resp = await fetch(`/api/user-tags?file_path=${encodeURIComponent(file.path)}`);
            const data = await resp.json();
            if (Array.isArray(data.user_tags)) {
                // P2: 寫入 file-level user_tags（用 captured file ref 避免 await 期間切檔 race）
                file.user_tags = data.user_tags;
            }
        } catch {
            // E9: 靜默忽略，不阻擋搜尋結果顯示
        }
    },

    // ===== T1c: Local Badge =====

    openLocal,

    // ===== T18c: Source Link =====

    openSourceUrl(url) {
        if (!url || typeof url !== 'string') return;
        if (!url.startsWith('http://') && !url.startsWith('https://')) return;
        if (window.pywebview?.api?.open_url) {
            window.pywebview.api.open_url(url).then(ok => {
                if (ok) {
                    this.showToast(window.t('search.toast.browser_opened'), 'success');
                } else {
                    window.open(url, '_blank', 'noopener,noreferrer');
                }
            }).catch(() => window.open(url, '_blank', 'noopener,noreferrer'));
        } else {
            window.open(url, '_blank', 'noopener,noreferrer');
        }
    },

    // ===== T1c: Cover Error =====

    // TASK-113c-T7: preview 失敗且有 cover fallback 時（shouldFallbackToCover）跳過
    // PHASE 1 的 cache-bust 重試、直接改試 cover——對「host 不在白名單→403」這個失敗
    // 模式，cache-bust 本來就無效。
    //
    // **請求數不變式（實測值，非估算）**：fallback 只多送一個請求（preview 那一發），
    // cover 這一棒保有它原本的預算。CDP 實測 2026-08-07：
    //   cover 成功 → preview(403) + cover(200) = **2**
    //   cover 也失敗 → preview(403) + cover(403) + cover&_t=(403) = **3**，然後 latch
    // 三個都停在 PHASE 2 的 placeholder，沒有迴圈。卡片初版 DoD 寫「一律 ≤2」是錯的
    // ——那個數字沒把 cover 自己既有的重試預算算進去。
    handleCoverError() {
        const img = this.$refs.coverImg;
        if (!img) return;

        // No cover URL → stale @error from previous cover, ignore
        const expected = this.coverUrl();
        if (!expected) return;

        // Preview 失敗、cover fallback 可用 → 改試 cover（見上方函式註解）
        const c = this.current();

        // 空白卡上傳的暫存封面逾期（GET 404）→ 卡回到「有上傳鈕」，使用者可重新上傳
        if (c._blank && c._coverUploadToken) {
            if ((img.getAttribute('src') || '') !== expected) return; // Stale @error
            this._dropBlankCover(c);
            return;
        }
        if (shouldFallbackToCover(c)) {
            const attrSrc = img.getAttribute('src') || '';
            if (attrSrc !== expected) {
                return; // Stale @error from previous cover
            }

            // 只做「換一個 URL 重載」這一件事，**不**碰 _coverRetried、不另起計時器：
            // cover 這一棒是第一次載入，理應保有它原本的重試預算（PHASE 1 的
            // cache-bust + 5 秒計時），由既有機制接手就好。實測（CDP，2026-08-07）：
            // 早期版本在這裡複製了一份 `_coverRetried = true` ＋ 5 秒計時器，結果
            // ① 它沒有抑制到 PHASE 1（cover 失敗時 _coverRetried 實測仍是 false）
            // ② 反而讓「cover 是大圖、載超過 5 秒」被提前宣告失敗。
            c._previewFailed = true;
            img.src = this.coverUrl();
            return;
        }

        // PHASE 1: First failure — getAttribute stale guard
        if (!this._coverRetried) {
            const attrSrc = img.getAttribute('src') || '';
            if (attrSrc !== expected) {
                return; // Stale @error from previous cover
            }

            this._coverRetried = true;
            if (img.src) {
                const sep = img.src.includes('?') ? '&' : '?';
                img.src = img.src + sep + '_t=' + Date.now();

                const requestId = this._coverRequestId;
                this._setTimer('coverRetry', () => {
                    if (this._coverRequestId !== requestId) return;
                    if (this._coverRetried && !this.coverError) {
                        this._coverRetried = false;
                        this.coverError = window.t('search.cover.load_failed');
                    }
                }, 5000);
                return;
            }
        }

        // PHASE 2: Second failure (retry also failed)
        this._clearTimer('coverRetry');
        this._coverRetried = false;
        this.coverError = window.t('search.cover.load_failed');
    },

    // ===== V1d: Source Switching =====

    /**
     * 切換來源（Alpine method wrapper）
     * 呼叫 ui.js 的 switchSource() 並傳入 Alpine context
     */
    async switchSource() {
        const number = this.current()?.number;
        if (!number) {
            console.warn('[Alpine] switchSource: 無番號資訊');
            return;
        }

        // 呼叫 ui.js 的 switchSource（傳入 Alpine context）
        if (window.switchSourceCore) {
            await window.switchSourceCore(this, number);
        }
    }
    };
}
