/**
 * SearchState - Result Card Mixin
 * 包含：結果卡片顯示、編輯、翻譯、標籤、本地狀態
 */
window.SearchStateMixin_ResultCard = {
    // ===== T1c: Result Card Computed =====

    current() {
        if (this.listMode === 'file' && this.fileList[this.currentFileIndex]) {
            const results = this.fileList[this.currentFileIndex].searchResults || [];
            return results[this.currentIndex] || {};
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
        if (c.translated_title) return '中文片名 (AI)';
        return '中文片名';
    },

    chineseTitleText() {
        const c = this.current();
        return c.translated_title || this.chineseTitle() || '-';
    },

    coverUrl() {
        const c = this.current();
        if (!c.cover) return '';
        return `/api/proxy-image?url=${encodeURIComponent(c.cover)}`;
    },

    canTranslate() {
        const c = this.current();
        return this.appConfig?.translate?.enabled &&
               !this.chineseTitle() &&
               !c.translated_title &&
               c.title &&
               window.SearchCore?.hasJapanese(c.title) &&
               !window.SearchCore?.isBatchTranslating(this.currentIndex);
    },

    hasLocalBadge() {
        return this.current()?._localStatus?.exists || false;
    },

    localBadgeTitle() {
        const status = this.current()?._localStatus;
        if (!status || !status.exists) return '';
        return status.count > 1
            ? `本地已有 ${status.count} 個版本（點擊開啟資料夾）`
            : '本地已有（點擊開啟資料夾）';
    },

    // ===== T1c: Title Edit Methods =====

    startEditTitle() {
        const c = this.current();
        this.editedTitleValue = c.title || '';
        this.editingTitle = true;
        this.$nextTick(() => {
            this.$refs.titleInput?.focus();
            this.$refs.titleInput?.select();
        });
    },

    confirmEditTitle() {
        const newValue = this.editedTitleValue.trim();
        const c = this.current();
        c.title = newValue;
        c._titleEdited = true;
        this.editingTitle = false;
        this.saveState();
    },

    cancelEditTitle() {
        this.editingTitle = false;
    },

    startEditChineseTitle() {
        this.editedChineseTitleValue = this.chineseTitleText() || '';
        this.editingChineseTitle = true;
        this.$nextTick(() => {
            this.$refs.chineseTitleInput?.focus();
            this.$refs.chineseTitleInput?.select();
        });
    },

    confirmEditChineseTitle() {
        const newValue = this.editedChineseTitleValue.trim();
        const c = this.current();
        c.translated_title = newValue;
        c._chineseTitleEdited = true;
        this.editingChineseTitle = false;
        this.saveState();
    },

    cancelEditChineseTitle() {
        this.editingChineseTitle = false;
    },

    // ===== T1c: Translate =====

    async translateWithAI() {
        if (this.isTranslating) return;
        this.isTranslating = true;
        try {
            // 呼叫 core.js 的實際翻譯邏輯（已去除 DOM 操作）
            await window.SearchCore._translateWithAI();
            // translated_title 已寫入 searchResult object → Alpine reactive 自動更新
        } catch (error) {
            console.error('[Translate] 翻譯失敗:', error);
            alert('翻譯失敗：' + error.message);
        } finally {
            this.isTranslating = false;
        }
    },

    // ===== T1c: User Tags =====

    showAddTagInput() {
        this.newTagValue = '';
        this.addingTag = true;
        this.$nextTick(() => {
            this.$refs.tagInput?.focus();
        });
    },

    confirmAddTag() {
        const tag = this.newTagValue.trim();
        if (!tag) {
            this.addingTag = false;
            return;
        }
        const c = this.current();
        if (!c.user_tags) c.user_tags = [];
        if (c.user_tags.includes(tag)) {
            this.addingTag = false;
            return;
        }
        c.user_tags.push(tag);
        this.addingTag = false;
        this.saveState();
    },

    cancelAddTag() {
        this.addingTag = false;
    },

    removeUserTag(tag) {
        const c = this.current();
        if (!c.user_tags) return;
        const idx = c.user_tags.indexOf(tag);
        if (idx > -1) {
            c.user_tags.splice(idx, 1);
            this.saveState();
        }
    },

    // ===== T1c: Local Badge =====

    openLocal(path) {
        if (!path) return;

        // 1. 擷取資料夾路徑
        const lastSlash = Math.max(path.lastIndexOf('/'), path.lastIndexOf('\\'));
        const folder = lastSlash >= 0 ? path.substring(0, lastSlash) : path;
        const winPath = folder.replace(/^file:\/\/\/?/, '').replace(/\//g, '\\');

        // 2. 複製到剪貼簿
        const clipboardOk = navigator.clipboard.writeText(winPath)
            .then(() => true)
            .catch(() => false);

        // 3. PyWebView 桌面模式：額外開啟資料夾
        if (window.pywebview?.api?.open_folder) {
            window.pywebview.api.open_folder(path)
                .then(async () => {
                    const ok = await clipboardOk;
                    this.showToast(ok ? '已開啟資料夾（路徑已複製）' : '已開啟資料夾', 'success');
                })
                .catch(async () => {
                    const ok = await clipboardOk;
                    this.showToast(ok ? '已複製: ' + winPath : '開啟資料夾失敗', ok ? 'success' : 'error');
                });
        } else {
            clipboardOk.then(ok => {
                this.showToast(ok ? '已複製: ' + winPath : '複製失敗', ok ? 'success' : 'error');
            });
        }
    },

    // ===== T6b: Toast =====

    showToast(message, type = 'success', duration = 2500) {
        // 設定 toast 內容
        this._toast.message = message;
        this._toast.type = type;
        this._toast.visible = true;

        // 清除舊的 timer
        if (this._toastTimer) {
            clearTimeout(this._toastTimer);
        }

        // 設定自動隱藏
        this._toastTimer = setTimeout(() => {
            this._toast.visible = false;
            this._toastTimer = null;
        }, duration);
    },

    // ===== T1c: Cover Error =====

    handleCoverError() {
        // Fix 4: 一次自動重試（cache bust）
        if (!this._coverRetried) {
            this._coverRetried = true;
            const img = this.$refs.coverImg;
            if (img && img.src) {
                const sep = img.src.includes('?') ? '&' : '?';
                img.src = img.src + sep + '_t=' + Date.now();
                return; // 不設 coverError，讓重試有機會成功
            }
        }
        this._coverRetried = false;
        this.coverError = '封面載入失敗';
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
