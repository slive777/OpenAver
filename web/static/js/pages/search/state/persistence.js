/**
 * SearchState - Persistence Mixin
 * 包含：狀態持久化（restoreState, saveState, clearState, setupAutoSave）
 */

/**
 * pending-edit watcher 的 key 產生純函式（module-level export 供 node:test 直接測）。
 *
 * 回傳「單一基本型別字串」而非物件/陣列，是本函式的核心語意約束（見 setupAutoSave 內
 * 大註解對 Alpine `watch` 觸發條件的說明）。五個決定「候選身分」的值用 null char（`\0`，
 * path 不可能含）串接：
 *   - fileKey：file 模式下當前檔案的 `path`（穩定字串識別，非位置數字）；search 模式無檔案
 *     身分，用空字串佔位。
 *   - currentIndex：候選在結果清單中的位置。
 *   - listMode：模式本身。
 *   - length：候選清單長度（整批替換 / 重刮通常筆數不同）。
 *   - _candidateReplaceSeq：候選「原地替換」計數器（TASK-106 Codex PR#116 P2）。換源 /
 *     switch-source 流程會整顆替換 current() 候選物件（arr[idx] = variant），但 path /
 *     currentIndex / listMode / length 可能全都不變（同位置換掉一顆物件、筆數相同）——前四段
 *     字串因此不變，哨兵不觸發，stale 編輯框留著。每個原地替換點遞增此計數器，併入尾段後
 *     「同 path/index/length 但候選被原地替換」也會讓 key 變 → 哨兵關掉 stale 編輯框。
 *
 * @param {object} s - SearchState（listMode / fileList / currentFileIndex / currentIndex /
 *   searchResults / _candidateReplaceSeq）
 * @returns {string} 單一基本型別字串 key
 */
export function pendingEditWatchKey(s) {
    const results = s.listMode === 'file'
        ? s.fileList[s.currentFileIndex]?.searchResults
        : s.searchResults;
    const fileKey = s.listMode === 'file'
        ? (s.fileList[s.currentFileIndex]?.path ?? '')
        : '';
    return `${fileKey}\0${s.currentIndex}\0${s.listMode}\0${results?.length ?? 0}\0${s._candidateReplaceSeq ?? 0}`;
}

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

        // TASK-106 Option C Part 2: 候選改變時清未確認的編輯 buffer（UX 便利層，
        // 非唯一保證——唯一保證是 result-card.js confirmEditX 開頭的 identity guard，
        // 這裡漏觸發/晚一拍也不會寫壞資料，只是編輯框多留一拍才關）。
        //
        // ── Alpine `watch` 的觸發條件（查 vendored alpine.min.js 原始碼定案）──
        // Alpine.watch(getter, cb) 的核心判斷是：
        //     if (!firstTime && (typeof newValue == "object" || newValue !== oldValue)) cb(...)
        // 也就是說：getter 回傳「物件/陣列」→ `typeof == "object"` 成立 → **一律觸發**，
        // 完全不比對內容；只有回傳「基本型別」時才走 `newValue !== oldValue` 做值比對。
        // （getter body 讀到的 reactive property 仍會被 effect 追蹤成依賴——任何依賴變動都會
        // 重跑 getter；但「重跑後要不要呼叫 cb」則由上面那條 if 決定。）
        //
        // 因此本 watcher 必須讓 getter 回傳「單一基本型別字串」（見 pendingEditWatchKey），
        // 而不是回傳陣列/物件。若回傳陣列，即使四個內容值都沒變，只要 getter body 讀到的
        // 任一 reactive 依賴變動就會重跑並「一律觸發」，把使用者正在編輯、尚未確認的內容
        // 誤清掉。回傳字串後，同內容 → 同字串 → `newValue !== oldValue` 為 false → 不觸發。
        //
        // ── round-5 錯誤推理的修正（真因）──
        // round-5 曾把 key 從 `currentFileIndex`（位置數字）改成 `path`，理由是「removeFile()
        // 移除目前檔前面的一列只遞減 currentFileIndex、path 不變，故不會誤觸發」——但那次
        // 改動沒生效。真因不在 key 用 index 還是 path，而在「getter 回傳的是陣列，Alpine 對
        // 陣列一律觸發、根本不比對內容」：removeFile() 造成 fileList splice + currentFileIndex
        // 遞減，getter body 讀 currentFileIndex（為取 path/length）→ 依賴變動 → getter 重跑 →
        // 回傳新陣列 → `typeof == "object"` → 一律觸發，即使 path/index/mode/length 全都沒變。
        // 換成回傳基本型別字串後，round-5 用 path 鍵定的正確意圖（純 reindex → 同 path → 同
        // key → 不觸發）才真正生效。
        //
        // ── 為何不寫 `this.$watch('current()', cb)`（仍成立）──
        // current() 回傳候選物件（含 title/actors/date 等可變欄位）。若 watch 它，getter body
        // 會讀遍那些欄位、建立巢狀依賴，且回傳的是物件（一律觸發）——本檔既有的候選內部直寫
        // （checkLocalStatus 寫 _localStatus、translateWithAI 寫 translated_title、date input
        // @change 寫 current().date、confirmEditTitle 寫 c.title）全部會誤觸發本 watcher，在
        // 打字到一半時把編輯框關掉。pendingEditWatchKey 的 getter body 刻意只碰 fileKey/
        // currentIndex/listMode/length 四個值，不讀 title/date/actors，字串化也只碰那四個值，
        // 故候選內部直寫不建立依賴、不觸發。
        //
        // ── 單顆原地替換盲區已封（TASK-106 Codex PR#116 P2）──
        // 曾為「已知良性殘留」：同 path、同 index、剛好同長度時，候選被原地替換 → 前四段 key
        // 字串不變 → 不觸發本 watcher，stale 編輯框留著。其中「**單顆物件**原地替換」
        // （arr[idx] = variant，換源 / switch-source 流程）現由 pendingEditWatchKey 第五段
        // _candidateReplaceSeq 覆蓋：每個單顆替換點（state-rescrape.js 單版本 / confirm、
        // ui.js switchSource auto-cycle）都遞增計數器 → key 尾段變 → 值比對成立 → 觸發
        // _resetPendingEdits 關掉 stale 編輯框。
        //
        // 仍存的良性殘留：「**整包陣列**被重新指派」（this.searchResults = payload.data /
        // fileList[i].searchResults 整批換）且**湊巧同長度、同 index、同 mode** 時——此類不經
        // arr[idx]=variant、不遞增計數器，前四段 key 又碰巧不變 → 不觸發。實務多數重搜/重刮筆數
        // 會變（length 段即偵測到），此殘留窄；且 Part 1 的 confirmEditX identity guard 作第二層
        // backstop（key 漏觸發時，current() 的新物件參照對不上捕獲來源 → 靜默擋下寫入，不寫壞資料）。
        this.$watch(() => pendingEditWatchKey(this), () => this._resetPendingEdits());
    }
    };
}
