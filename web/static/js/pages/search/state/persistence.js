/**
 * SearchState - Persistence Mixin
 * 包含：狀態持久化（restoreState, saveState, clearState, setupAutoSave）
 */
export function searchStatePersistence() {
    return {
    // ===== State Persistence =====
    restoreState() {
        const saved = sessionStorage.getItem(this.STATE_KEY);
        if (!saved) return;

        try {
            const state = JSON.parse(saved);
            this.searchResults = state.searchResults || [];
            this.currentIndex = state.currentIndex || 0;
            this.currentQuery = state.currentQuery || '';
            this.currentOffset = state.currentOffset || 0;
            this.hasMoreResults = state.hasMoreResults || false;
            this.fileList = state.fileList || [];
            this.currentFileIndex = state.currentFileIndex || 0;
            this.listMode = state.listMode || null;
            this.displayMode = state.displayMode || 'detail';
            this.currentMode = state.currentMode || '';  // T3 fix: 還原搜尋模式
            this.actressProfile = state.actressProfile || null;  // T5: 恢復女優資料

            // 還原搜尋框輸入值
            if (state.queryValue) {
                this.searchQuery = state.queryValue;
            }

            // U8b: 清除封面狀態（防止還原時殘留舊狀態）
            this._resetCoverState();
            // A6-1: 還原時清除舊 hero image error state
            this._heroCardImageError = false;
            this._heroLightboxImageError = false;

            // 還原顯示狀態（透過舊 JS 的 showState 同時處理 .hidden + Alpine pageState）
            var hasResult = false;
            if (this.searchResults.length > 0) {
                this.pageState = 'result';
                hasResult = true;
            } else if (this.fileList.length > 0 && this.listMode === 'file') {
                const currentFile = this.fileList[this.currentFileIndex];
                if (currentFile?.searchResults?.length > 0) {
                    this.searchResults = currentFile.searchResults;
                    this.hasMoreResults = currentFile.hasMoreResults || false;
                    this.pageState = 'result';
                    hasResult = true;
                }
            }

            // A6-2: Lightbox 狀態正規化 — 還原後 lightbox 不應開著
            this.lightboxOpen = false;
            if (this.actressProfile) {
                this.lightboxIndex = -1;
            }

        } catch (e) {
            console.error('[Alpine] 還原狀態失敗:', e);
            sessionStorage.removeItem(this.STATE_KEY);
        }
    },

    saveState() {
        // 搜尋進行中：用 _searchSnapshot 保存（上一輪完整一致狀態）
        // 條件：snapshot 存在 + pageState 仍是 loading（覆蓋 SSE 和 REST fallback 兩條路徑）
        if (this._searchSnapshot && this.pageState === 'loading') {
            const snap = this._searchSnapshot;
            const state = {
                searchResults: snap.searchResults,
                currentIndex: snap.currentIndex,
                currentQuery: snap.currentQuery,
                currentOffset: snap.currentOffset,
                hasMoreResults: snap.hasMoreResults,
                fileList: snap.fileList,
                currentFileIndex: snap.currentFileIndex,
                listMode: snap.listMode,
                queryValue: snap.currentQuery,    // 上一輪的 query
                displayMode: snap.displayMode,
                currentMode: snap.currentMode,
                actressProfile: snap.actressProfile
            };
            sessionStorage.setItem(this.STATE_KEY, JSON.stringify(state));
            return;
        }

        // T3.2 Step 3: SearchCore.state 已代理 Alpine，直接用 Alpine state
        const state = {
            searchResults: this.searchResults,
            currentIndex: this.currentIndex,
            currentQuery: this.currentQuery,
            currentOffset: this.currentOffset,
            hasMoreResults: this.hasMoreResults,
            fileList: this.fileList,
            currentFileIndex: this.currentFileIndex,
            listMode: this.listMode,
            queryValue: this.searchQuery,
            displayMode: this.displayMode,
            currentMode: this.currentMode,  // T3 fix: 持久化搜尋模式
            actressProfile: this.actressProfile  // T5: 持久化女優資料
        };
        sessionStorage.setItem(this.STATE_KEY, JSON.stringify(state));
    },

    clearState() {
        sessionStorage.removeItem(this.STATE_KEY);
    },

    setupAutoSave() {
        // Watch 主要狀態變化並自動儲存（debounce 100ms）
        // T4.2: 改用 _setTimer 取代 local debounce variable，支援離頁統一清除
        const debouncedSave = () => {
            this._setTimer('autosave', () => this.saveState(), 100);
        };

        this.$watch('searchResults', debouncedSave);
        this.$watch('currentIndex', debouncedSave);
        this.$watch('fileList', debouncedSave);
        this.$watch('listMode', debouncedSave);

        // TASK-106 Option C Part 2: current() 候選改變時清未確認的編輯 buffer（UX 便利層，
        // 非唯一保證——唯一保證是 result-card.js confirmEditX 開頭的 identity guard，
        // 這裡漏觸發/晚一拍也不會寫壞資料，只是編輯框多留一拍才關）。
        //
        // 刻意不寫 `this.$watch('current()', cb)`：經 context7 查證 Alpine 官方文件
        // （https://alpinejs.dev/magics/watch「Deep watching」段，範例 `$watch('foo', cb)`
        // 在 `foo.bar = 'bob'` 時仍會觸發）與原始碼（Alpine.watch() 內部對回傳值跑
        // `JSON.stringify(value)` 逼自己深度讀遍 value 底下每個屬性以建立 granular
        // 依賴）— 兩者一致證實 $watch 對「回傳一個物件/陣列」的表達式一律深度追蹤其
        // 全部巢狀屬性，不是只認參照是否改變。current() 回傳的候選物件含 title/actors/
        // date 等可變欄位，若直接 watch 它，本檔既有的候選內部直寫（checkLocalStatus 寫
        // _localStatus、translateWithAI 寫 translated_title、date input @change 寫
        // current().date、甚至 confirmEditTitle 自己寫 c.title）全部會誤觸發本 watcher，
        // 在使用者輸入到一半時把編輯框關掉——正是本次要修的過度觸發那類 bug。
        //
        // 改用只讀 primitives 的複合表達式：候選「在檔案清單中的身分」用 fileList 模式下
        // 當前檔案的 `path`（字串，穩定不變的識別，非位置數字）鍵定，search 模式無檔案身分
        // 用空字串佔位；候選「在結果清單中的位置」用 currentIndex；「候選清單被整批替換」
        // 用清單長度變化偵測（重新搜尋/重刮通常筆數不同）。JSON.stringify 對純 primitives
        // 陣列不會再往下巢狀追蹤，故打字/候選內部直寫不會誤觸發；只在候選真的換位/換檔/
        // 換模式/清單被替換時才觸發。
        //
        // Codex PR#115 P2 fix：原本用 `currentFileIndex`（位置數字）鍵定，removeFile() 移除
        // currentFileIndex 之前的一列時只會遞減 currentFileIndex（見 file-list.js
        // removeFile 的 removingCurrent gate 註解——目前檢視的檔沒變，只是它在陣列中的
        // 位置往前移一格），currentFileIndex 這個數字因此改變、誤觸發本 watcher，把使用者
        // 正在編輯、尚未確認的內容清掉——但實際上目前檔案/候選完全沒變，是誤傷。改鍵定
        // `path`（該檔案的穩定字串識別）後，純 reindex（陣列位置位移但同一份 file 物件）
        // 不會改變 path，複合表達式不變，watcher 不誤觸發，編輯得以保留。
        // 換檔（path 真的變了）/候選導覽（currentIndex 變）/re-search 替換清單（多數情況下
        // length 變）仍會正確觸發。
        //（已知邊界：同 path、同 index、剛好同長度的清單被整批替換不會觸發本 watcher——
        // 但 current() 此時回傳的已是新陣列裡的新物件參照，confirmEditX 的 identity guard
        // 仍會擋下寫入，不會寫壞資料，只是編輯框慢一拍才關。）
        this.$watch(() => {
            const results = this.listMode === 'file'
                ? this.fileList[this.currentFileIndex]?.searchResults
                : this.searchResults;
            const fileKey = this.listMode === 'file'
                ? (this.fileList[this.currentFileIndex]?.path ?? '')
                : '';
            return [fileKey, this.currentIndex, this.listMode, results?.length ?? 0];
        }, () => this._resetPendingEdits());
    }
    };
}
