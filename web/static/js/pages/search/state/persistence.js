/**
 * SearchState - Persistence Mixin
 * 包含：狀態持久化（restoreState, saveState, clearState, setupAutoSave）
 * listMode/displayMode 原樣存、原樣還原（對齊 showcase $persist）
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

// TASK-113c-T7（Opus 審核裁決 3）：狀態還原流程（下方 searchStatePersistence 內的
// state-restore 方法）的 _previewFailed 清除邏輯抽成 module-level 純函式，供 node:test
// 直接呼叫——測「清除函式本身」（輸入帶 `_previewFailed:true` 的物件陣列 → 輸出不帶），
// 不是「狀態還原跑完之後某個時間點是乾淨的」（後者測不出時序）。呼叫方必須在把資料指派
// 進 Alpine state 之前呼叫本函式，否則首幀會用殘留的 _previewFailed=true 渲成 cover，
// 下一幀才翻回 preview——多一個請求，畫面會閃一下換圖。
//
// 就地清除（不建新陣列/新物件）：results 若已是 sessionStorage 解析出的原始物件，
// 呼叫方緊接著才把它們指派進 Alpine state，此時 mutate 原物件、原陣列參照不變是安全的、
// 成本也最低。非陣列輸入（undefined/null，例如 saved JSON 缺 searchResults 鍵）原樣
// 回傳，不炸。
export function clearPreviewFailedFlags(results) {
    if (!Array.isArray(results)) return results;
    results.forEach((r) => {
        if (r && r._previewFailed) delete r._previewFailed;
    });
    return results;
}

/**
 * 還原後的 (listMode, displayMode) 是否至少有一個 search.html 渲染器會顯示；
 * 不合法就把 displayMode 修正成 'detail'（對任何 listMode !== 'wishlist' 恆合法，是唯一
 * 「永遠救得回來」的落點）。不動 listMode——那會竄改使用者離開時所在的模式。
 *
 * 合法組合對照 search.html 四個渲染器：
 *   - listMode === 'wishlist'                          （L1061 書籤格，不看 displayMode）
 *   - listMode === 'search' && displayMode === 'grid'  （L757 搜尋格子牆）
 *   - displayMode === 'detail'（且 listMode !== 'wishlist'）（L449 detail 大卡，
 *     祖先 #resultCard 要求 listMode !== 'wishlist'，L443）
 *
 * `listMode === 'file'` 不獨立成一支：本專案目前只在賦值處（file-list.js:102-103,439-440）
 * 成對寫入 listMode='file' + displayMode='detail'，從未產生 ('file','grid') 這個組合；
 * 沒有其他證據顯示 ('file','grid') 是設計上合法的畫面，保守收斂進 detail 分支即可
 * ——('file','grid') 因此會被本函式修正成 ('file','detail')。
 *
 * T11a 之後若新增 wishlistLightboxOpen 閘，這裡要跟著擴充合法組合清單（見 plan「不變式」段）。
 *
 * @param {string|null} listMode
 * @param {string} displayMode
 * @returns {string} 修正後的 displayMode（合法組合原樣傳回）
 */
export function resolveVisibleDisplayMode(listMode, displayMode) {
    if (listMode === 'wishlist') return displayMode;
    if (listMode === 'search' && displayMode === 'grid') return displayMode;
    if (displayMode === 'detail') return displayMode;
    return 'detail';
}

export function searchStatePersistence() {
    return {
    // ===== State Persistence =====
    /**
     * saveState() 兩條分支共用的取值邏輯（Codex Phase 2 review P2-1）：一律讀 live state，
     * 永不讀 snapshot——snapshot 保住的是上一輪的結果集，不是「你在看哪個模式」。
     * 搜尋還在跑時（pageState==='loading'）書籤分段沒有 disabled，使用者切書籤再離頁／F5
     * 是走得到的路徑，這時若讀 snap.listMode 會把使用者丟回舊的搜尋畫面。
     */
    _liveModeFields() {
        return {
            listMode: this.listMode,
            displayMode: this.displayMode,
            _preWishlistDisplayMode: this._preWishlistDisplayMode,
            _preWishlistListMode: this._preWishlistListMode,
        };
    },

    restoreState() {
        const saved = sessionStorage.getItem(this.STATE_KEY);
        if (!saved) return;

        try {
            const state = JSON.parse(saved);

            // TASK-113c-T7 裁決3: 清除殘留 _previewFailed，必須在指派進 Alpine state
            // 之前完成（見上方 clearPreviewFailedFlags 註解）。
            clearPreviewFailedFlags(state.searchResults);
            if (Array.isArray(state.fileList)) {
                state.fileList.forEach((file) => clearPreviewFailedFlags(file?.searchResults));
            }

            this.searchResults = state.searchResults || [];
            this.currentIndex = state.currentIndex || 0;
            this.currentQuery = state.currentQuery || '';
            this.currentOffset = state.currentOffset || 0;
            this.hasMoreResults = state.hasMoreResults || false;
            this.fileList = state.fileList || [];
            this.currentFileIndex = state.currentFileIndex || 0;
            this.listMode = state.listMode || null;
            this.displayMode = resolveVisibleDisplayMode(this.listMode, state.displayMode || 'detail');
            this._preWishlistDisplayMode = state._preWishlistDisplayMode || null;
            // 與 _preWishlistDisplayMode 對稱（Codex PR#175 P2）：不一起還原的話，
            // 在書籤頁重新整理再點回搜尋段，仍然會掉進 'search' 而不是原本的 'file'。
            this._preWishlistListMode = state._preWishlistListMode || null;
            this.currentMode = state.currentMode || '';  // T3 fix: 還原搜尋模式
            this.currentMaker = state.currentMaker ?? null;
            this.currentCursor = state.currentCursor ?? null;  // 175d：舊存檔缺欄位 ⇒ null
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
                } else if (currentFile?.blankCard) {
                    // TASK-183-T2：查無但有空白結果卡（使用者可能已填內容）→ F5 後直接還原成 result 頁
                    this.pageState = 'result';
                    hasResult = true;
                }
            }

            // A6-2: Lightbox 狀態正規化 — 還原後 lightbox 不應開著
            this.lightboxOpen = false;
            if (this.actressProfile) {
                this.lightboxIndex = -1;
            }

            // T10：listMode 現在原樣還原（不再被舊的淨化邏輯清成 null）。
            // 還原成 wishlist 時，只設欄位不夠——清單資料要重新對帳，否則畫面上的格子牆永遠是空的。
            // fire-and-forget：restoreState() 必須維持同步函式，不 await switchToWishlist()/loadWishlist()。
            // 順序硬約束：this.listMode 必須先被設成 'wishlist'（上面已經做了）才能呼叫，否則
            // switchToWishlist() 內 `if (this.listMode !== 'wishlist')` 會誤判成「剛切換」，
            // 用當下的 this.displayMode（可能是預設值）覆寫掉剛還原的 _preWishlistDisplayMode。
            if (this.listMode === 'wishlist') {
                this.switchToWishlist();
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
            const live = this._liveModeFields();
            const state = {
                searchResults: snap.searchResults,
                currentIndex: snap.currentIndex,
                currentQuery: snap.currentQuery,
                currentOffset: snap.currentOffset,
                hasMoreResults: snap.hasMoreResults,
                fileList: snap.fileList,
                currentFileIndex: snap.currentFileIndex,
                listMode: live.listMode,
                queryValue: snap.currentQuery,    // 上一輪的 query
                displayMode: live.displayMode,
                _preWishlistDisplayMode: live._preWishlistDisplayMode,
                _preWishlistListMode: live._preWishlistListMode,
                currentMode: snap.currentMode,
                currentMaker: snap.currentMaker ?? null,
                currentCursor: snap.currentCursor ?? null,
                actressProfile: snap.actressProfile
            };
            sessionStorage.setItem(this.STATE_KEY, JSON.stringify(state));
            return;
        }

        // T3.2 Step 3: SearchCore.state 已代理 Alpine，直接用 Alpine state
        const live = this._liveModeFields();
        const state = {
            searchResults: this.searchResults,
            currentIndex: this.currentIndex,
            currentQuery: this.currentQuery,
            currentOffset: this.currentOffset,
            hasMoreResults: this.hasMoreResults,
            fileList: this.fileList,
            currentFileIndex: this.currentFileIndex,
            listMode: live.listMode,
            queryValue: this.searchQuery,
            displayMode: live.displayMode,
            _preWishlistDisplayMode: live._preWishlistDisplayMode,
                _preWishlistListMode: live._preWishlistListMode,
            currentMode: this.currentMode,  // T3 fix: 持久化搜尋模式
            currentMaker: this.currentMaker ?? null,
            currentCursor: this.currentCursor ?? null,
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
