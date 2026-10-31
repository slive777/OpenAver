/**
 * state-lightbox-mask.js — Showcase ESM（149a-T4a／T4b）
 *
 * 焦點裁切遮罩：session 生命週期（openMask/confirmMask/cancelMask/_resetMask）、
 * 拖曳互動（_maskDragStart 及對應 pointermove/pointerup）、force-detect 幾何計算
 * 與星空等待/收斂動畫（GhostFly timeline）的 kill 生命週期。從 state-lightbox.js
 * 拆出，逐字搬移，見 plan-149a.md CD-149a-1。
 */

import { computeMaskWinGeometry, computeMaskSettleGeometry } from '@/shared/mask-geometry.js';
import { parseFocal, clampMaskWinLeft } from '@/shared/focal.js';

export function stateLightboxMask() {
    return {
        // 99a-T3：焦點裁切遮罩 — 一律 force-detect 預覽 + 左右拖曳微調 + ✓/✗ 提交（Alpine 短狀態，
        // 單一提交生命週期 CD-98b-8 沿用）。98b 的 default⇄auto toggle 已整條移除（見 CHANGELOG）。
        // _maskSession 為單調遞增 session id（98b P2 fix 沿用，Codex）：openMask()/_resetMask() 遞增，
        // confirmMask()/_maskDragStart() 的 pointermove 在 await/事件前捕捉、之後比對，不符即代表
        // 已換片/關燈箱，跳過該次的共用 UI 狀態寫入。
        // 100b-T1：_maskKind 是本 task 唯一新增的 state（CD-4/§B-1b dispatch key）。openMask()
        // 起手第一行凍結一次（'video'|'actress'，依 currentLightboxActress 是否有值），
        // _maskTarget() 內部不得重新判斷（G4：actress/video 各自獨立 state，需在觸發點凍結，
        // 不可逐次重判）。T1 階段 openMask 唯一觸發入口（.lb-mask-btn）只在 video 分支渲染，
        // 故本欄此刻恆解析為 'video'——這正是 T1 DoD ③「女優路徑仍不可達」的結構性保證，
        // 非約定俗成。_resetMask()/_maskTeardown() 收尾時重置（見兩函式末尾，裁決 D-3：
        // 排在最後，防先清 kind 再做依賴 _maskTarget() 的收尾查到錯的分支/元素）。
        _maskKind: null,                // 'video' | 'actress'，dispatch key（100b-T1）
        _maskVisible: false,            // 遮罩 overlay 是否顯示
        _maskSession: 0,                // 單調遞增 session id（openMask/_resetMask 遞增）
        _maskDetecting: false,          // force-detect 進行中（spinner）
        // 99a-T3：手動焦點編輯狀態。_maskFocalX 恆為具體數字（geometry 已知後）——僅在 openMask
        // 幾何尚未解出的極短暫態為 null（見 openMask 內註解，Opus correction B）。
        _maskFocalX: null,
        // Codex PR#107 第二輪 P2：使用者開遮罩當下觀察到的 cover_path（server 端 DB-key
        // file:/// URI 原樣值，由 /detect-focal 回應帶回，非前端反解/推算）。null＝尚未
        // 從 server 取得任何值（openMask 起手重置、或本次 detect 連 JSON body 都沒拿到，
        // 見 openMask 內 try/catch 註解）——confirmMask 见 null 一律 fail-closed 拒存，
        // 不送 POST，避免用「猜的」cover_path 打穿 compare-and-store 守衛的保護意圖。
        _maskExpectedCoverPath: null,
        _maskDragging: false,           // 拖曳中（停用 CSS transition，跟手不打架，見 showcase.css）
        _maskDragMoveHandler: null,     // document pointermove listener 參照（成對 add/remove）
        _maskDragUpHandler: null,       // document pointerup/pointercancel listener 參照（成對 add/remove）
        // 98b-T6：亮窗幾何 reactive data（openMask/drag 同步 imperative 算，非量測-in-binding）。
        // 99a-T5：型別恆為 object（非 string）——headless self-verify 實測抓到：Alpine `:style`
        // 綁 STRING 值時走 `el.setAttribute('style', ...)` 整串覆寫（Alpine 內部 `Xn()`），會把
        // `x-show` 剛設的 inline `display:none` 一併洗掉；`x-show` 本身又會快取「上次算出的布林值」，
        // 布林值沒變就不重跑 show/hide（Alpine 內部 x-show 的 `f===l` 短路），兩者疊加＝窗子在
        // `_maskDetecting` 為真期間仍卡在 `display:block`（baseline flash 不會消失，一路卡到
        // detect resolve）。物件值改走 `el.style.setProperty(key, val)` 逐屬性設值（Alpine 內部
        // `Yn()`），不觸碰 `display`，與 x-show 互不干擾。永遠回傳/賦值 object，不可再退回 string。
        _maskWinStyle: {},
        _maskResizeHandler: null,       // 98b-T6：開遮罩時綁 window resize 重算，teardown/reset 時解


        // 101b-T2（CD-4a/CD-5）：收斂補間進行中旗標——只在 _maskDetecting 翻 false 之後才可能為
        // true（結構上不與 _maskDetecting 重疊，見 _maskStartSettle 步驟④⑤順序）。x-show 驅動
        // .lb-mask-wait-burst/.lb-mask-spinner 延壽 + .lb-mask-window--settling class（CD-5，
        // 停用 CSS transition，防與 GSAP 逐 tick 寫 Alpine :style 雙重 easing）。
        _maskSettling: false,


        _maskWaitTl: null,              // 99a-T5：星空等待動畫 handle（{tl,burst,stars}），detect
                                         // 期間播放；openMask 啟動，finally/_resetMask/_maskTeardown
                                         // 三處對稱停止（_maskStopWaitAnim helper，idempotent）。
                                         // 101b-T2：正常（收斂）路徑改由 _maskStartSettle 交棒
                                         // （handoffFocalDetectWait，不置 null），fallback 分支
                                         // 仍走 _maskStopWaitAnim 全停清空（CD-4b）。
        _maskSettleTl: null,            // 101b-T2：收斂 GSAP timeline handle（id:'focalSettle'），
                                         // _maskStopSettleAnim（拖曳接管/中斷路徑）與 onComplete/
                                         // onInterrupt（正常結束）對稱清空，見 _maskClearSettleProps。


        // 100b-T1（CD-4/§B-1b）：video/actress 兩分支識別資訊統一出口。_maskKind 已由 openMask()
        // 起手凍結（G4，不在此重判）。⚠️ 舊註解曾寫「actress 分支目前結構性不可達」——那只在
        // 100b-T1 完成的當下成立，同日的 100b-T2a／100c-T2 就把 .lb-mask-btn 接進女優分支了
        // （v0.12.2）。兩分支今天都活著。detectEndpoint/focalEndpoint 各自完整字面 URL（Opus 裁決 C：
        // 不可拼接 base，否則 static_guard_lint.mjs:147 的 detect-focal 規則因字面字串消失而
        // 靜默 RED）。imgEl 對 actress 分支须 null-safe（G3：$refs.pickerCoverImg 在 x-if 內）。
        _maskTarget() {
            if (this._maskKind === 'actress') {
                return {
                    obj: this.currentLightboxActress,
                    imgEl: this.$refs && this.$refs.pickerCoverImg,   // G3：x-if 內，null-safe
                    loaded: this._actressPhotoLoaded,   // T2 才宣告；未宣告的 this.xxx property access 回 undefined，非 ReferenceError
                    identity: this.currentLightboxActress?.name,
                    ratio: '--actress-crop-ratio',
                    detectEndpoint: `/api/actresses/${encodeURIComponent(this.currentLightboxActress?.name || '')}/detect-focal`,
                    focalEndpoint: `/api/actresses/${encodeURIComponent(this.currentLightboxActress?.name || '')}/focal`,
                    focalBody: (focal) => ({ focal }),   // v3：無 token，只此一欄
                    handles409: false,   // spec §3.5：女優無背景 writer、無 409
                };
            }
            return {
                obj: this.currentLightboxVideo,
                imgEl: this.$refs.lightboxCoverFull,
                loaded: this._lbFullLoaded,
                identity: this.currentLightboxVideo?.path,
                ratio: '--poster-crop-ratio',
                detectEndpoint: '/api/showcase/video/detect-focal',
                focalEndpoint: '/api/showcase/video/save-focal',
                focalBody: (focal) => ({
                    path: this.currentLightboxVideo?.path,
                    focal,
                    expected_cover_path: this._maskExpectedCoverPath,
                }),
                handles409: true,   // 封面已變更時的 compare-and-store 409
            };
        },
        async openMask() {
            if (this._maskVisible) return;   // 98b-T6：re-entry guard——按鈕在遮罩開啟時仍可見，
                                             // 再點不重複裝 resize listener。
            // 100b-T1（CD-4/§B-1b，G4）：凍結 kind，_maskTarget() 內部不得重判。
            // 🔴 位置是承重的，必須夾在 re-entry guard 之後、第一個 _maskTarget() 消費者之前：
            //   • 排 re-entry guard「之前」→ 遮罩已開時再次進入會覆寫 in-flight session 的 kind，
            //     才 return——「凍結」語意當場破功（T1 恆 'video' 故無影響，但 T2 女優可達後，
            //     kind 被改成別的分支會讓後續 _maskDragStart 抓到錯的 $refs 元素）。
            //   • 排 `_maskTarget().identity` 之後 → helper 讀到未凍結的 kind，dispatch 到錯分支。
            // 用排序讓該類 race 結構上不可能發生，而非事後補旗標（feedback_order_over_flag_guards）。
            // （100b-T1 時 .lb-mask-btn 只在 video 分支渲染，此處恆為 'video'；100c-T2 起女優也有。）
            this._maskKind = this.currentLightboxActress ? 'actress' : 'video';
            if (!this._maskTarget().identity) return;
            // 98b-T6 防线：圖未就緒不開（按鈕也 gate _lbFullLoaded，此為 defense-in-depth）。
            if (!this._maskTarget().loaded) return;

            // 99a-T3：_maskFocalX 暫時設 null（幾何尚未解出的極短暫態，見 state 宣告處註解）。
            // _computeMaskWinStyle 讀到 null 即貼右裁基準（D2）——99a-T5：此值只作為「detect
            // 失敗/無臉」時的終值 fallback，不會先畫出來再滑走（.lb-mask-window 在 _maskDetecting
            // 為真時不渲染，見 showcase.html x-show）。
            this._maskFocalX = null;
            // Codex PR#107 第二輪 P2：新 session 起手先清舊 token，防止「這次 detect 連
            // JSON body 都沒拿到」時沿用上一支影片/上一個 session 殘留的 cover_path
            // 誤配到這支影片（confirmMask 的 fail-closed 判斷才有意義）。
            this._maskExpectedCoverPath = null;

            // 初始焦點基準在此一次性解出並凍結，_computeMaskWinStyle()/pointermove 內不得
            // 重判。el/rect/r 的讀取與 _computeMaskWinStyle 內部刻意重複（Opus correction B
            // 既有註解：ratio 讀取受 static guard 錨定在 _computeMaskWinStyle 本體內，不可
            // 抽成共用 helper）。
            const gEl = this._maskTarget().imgEl;
            if (!gEl || !gEl.naturalWidth) {
                this.showToast(window.t('showcase.lightbox.mask_detect_failed'), 'error');
                return;
            }
            const gRect = gEl.getBoundingClientRect();
            if (!gRect.width || !gRect.height) {
                this.showToast(window.t('showcase.lightbox.mask_detect_failed'), 'error');
                return;
            }
            const gR = parseFloat(getComputedStyle(gEl).getPropertyValue(this._maskTarget().ratio));
            if (!Number.isFinite(gR) || gR <= 0) {
                this.showToast(window.t('showcase.lightbox.mask_detect_failed'), 'error');
                return;
            }
            if (this._maskKind === 'actress') {
                // spec §3.4/§3.7-6：女優基準恆 3/4 置中（非右裁）。
                this._maskFocalX = 0.5;
            } else {
                // Opus correction B：幾何一旦解出，_maskFocalX 收斂為具體數字（右裁基準 x），
                // 不留 null 終態；`s` 成功即代表 el/rect/r 皆已驗證合法，這裡不需再驗一次。
                const winW = Math.min(gRect.width, gRect.height * gR);
                this._maskFocalX = (gRect.width - winW / 2) / gRect.width;
            }

            const s = this._computeMaskWinStyle();
            if (!s) {
                // 幾何算不出（rect=0 / naturalWidth=0 / ratio CSS var 讀不到 → NaN）→ 不開、
                // 不留「全灰無窗」死態，toast 提示。兩個 ratio var（--poster-crop-ratio /
                // --actress-crop-ratio）皆已定義於 theme.css :root，此處為防禦性 fallback。
                this.showToast(window.t('showcase.lightbox.mask_detect_failed'), 'error');
                return;
            }

            this._maskDetecting = false; // 98b P2 fix(二)：清舊 session 遺留的偵測態——舊 detect await 的
                                         // finally 因 session 不符會**跳過**清 spinner，若不在此重置，新遮罩
                                         // 會頂著卡死的 spinner（Codex）。新 session 起手一律非偵測中。
            this._maskWinStyle = s;      // 先設幾何（右裁基準，detect resolve 前 / 無臉時的 fallback 終值）

            this._maskSession++;         // 98b P2 fix：新開 session，讓任何舊 session 的 await 後寫入失效

            // D1（CD-1）：一律 force-detect，僅預覽、不寫 DB。偵測完成後若有臉，_maskFocalX 更新為
            // 偵測 x；無臉則維持右裁基準不變。99a-T5：.lb-mask-window 在 _maskDetecting 為真時不
            // 渲染（showcase.html x-show="_maskVisible && !_maskDetecting"），故偵測完成翻 false
            // 那一刻起才第一次畫出來，畫出來就已是終值——不再有「先貼右裁基準再滑到偵測位置」的
            // 過渡態，拖曳入口（@pointerdown）在 detect 完成前也不存在，Bug 1 的 race 結構性消失。
            const session = this._maskSession;
            // 101b-T2（CD-4a/CD-8）：try 之外宣告，finally 讀得到。不可從 _maskFocalX 反推
            // （無臉時 _maskFocalX 停在起手基準，與 pigo 真的回同值的基準無法區分——女優基準
            // 恆 0.5，pigo 也可能回 0.5；video 基準是右裁算式，pigo 也可能剛好回同值）。
            let sawFace = false;
            const targetVideo = this._maskTarget().obj;   // 100b-T1：identity 統一走 helper（video 分支＝currentLightboxVideo）
            // 100b-T2a：actress 分支 targetVideo = currentLightboxActress（無 .path）——下方
            // fetch body 的 `targetVideo.path` 對 actress 恆 undefined，JSON.stringify 會直接
            // drop 該 key（body 變 {}）。女優 detect-focal 端點簽名為
            // `async def detect_actress_focal(name: str)`（web/routers/actress.py:950），無
            // request body model，name 全靠 URL path segment（detectEndpoint 已含編碼後的
            // name），送空 body 不影響行為，故此處沿用 T1 既有寫法、不需 kind-aware 分流。
            // 99a-T5（headless self-verify 實測抓到，非理論推測）：_maskDetecting 必須先翻 true，
            // 才能設 _maskVisible=true——Alpine 的 x-show reactive effect 對每次同步賦值都立即
            // 重新求值（非批次到下個 microtask 才跑），若順序顛倒（先 _maskVisible=true，
            // _maskDetecting 還停在上面剛重置的 false），x-show="_maskVisible && !_maskDetecting"
            // 會在兩行賦值之間的中繼態被評估為 true，短暫畫出「貼右裁基準」的窗（baseline
            // flash），違反本卡「畫出來就已是終值」的核心承諾。實測：START-525 這支影片 100%
            // 重現（baseline 144.30px ≠ 最終偵測值 0px，flash 全程持續到 detect resolve 為止）。
            this._maskDetecting = true;
            this._maskVisible = true;    // 再顯示 overlay（此刻 _maskDetecting 已是 true，無空窗閃）
            // 開啟期間 window resize 重算（開時綁、teardown/reset 時解，lifecycle 對稱）。
            // 99a-T5：`|| this._maskWinStyle` fallback——_computeMaskWinStyle 失敗時回傳 null，
            // 不可讓 null 流進 :style 綁定（見 _maskWinStyle 宣告處註解），保留前一次的合法幾何。
            this._maskResizeHandler = () => {
                if (this._maskVisible) this._maskWinStyle = this._computeMaskWinStyle() || this._maskWinStyle;
            };
            window.addEventListener('resize', this._maskResizeHandler);

            // 99a-T5：星空等待動畫（detect 期間佔位）。單一入口——只在這裡啟動；停止見下方
            // finally（正常結束）與 _resetMask/_maskTeardown（中斷路徑），_maskStopWaitAnim 對稱。
            // C23 per-callsite PRM guard（比照 state-similar.js isPRM pattern）：PRM 為真時整段
            // 跳過 GSAP，唯一等待指示回退成 .lb-mask-spinner（純 CSS animation，PRM blanket 規則
            // 保證仍渲染不轉，不留死白）。
            const isPRM = !!(window.OpenAver && window.OpenAver.prefersReducedMotion);
            if (!isPRM) {
                const coverEl = this._maskTarget().imgEl?.closest('.lightbox-cover');
                if (coverEl && window.GhostFly && window.GhostFly.playFocalDetectWait) {
                    this._maskWaitTl = window.GhostFly.playFocalDetectWait(coverEl);
                }
            }

            try {
                const resp = await fetch(this._maskTarget().detectEndpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ path: targetVideo.path }),
                });
                // Codex PR#107 第二輪 P2：先嘗試解 body 拿 cover_path，不管 resp.ok——
                // server 在成功偵測與「找到 row 但封面檔缺失」兩個分支都帶 cover_path
                // （見 web/routers/showcase.py detect_video_focal），拖到下面 !resp.ok
                // 才 throw 會漏接後者。真正的網路層失敗（fetch reject / body 非 JSON）
                // 才會讓 data 維持 null，此時 _maskExpectedCoverPath 停在 openMask 起手
                // 清空的 null，confirmMask 見 null 一律 fail-closed 拒存（不可用猜的值）。
                let data = null;
                try { data = await resp.json(); } catch (_jsonErr) { data = null; }
                if (data && typeof data.cover_path === 'string' && session === this._maskSession) {
                    this._maskExpectedCoverPath = data.cover_path;
                }
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                if (!data || !data.success) throw new Error((data && data.error) || 'API failed');
                if (session === this._maskSession) {
                    const parsed = parseFocal(data.auto_focal);   // '' / 畸形 → null，維持起手基準
                    if (parsed) {
                        // 女優基準恆 3/4 置中（spec §3.4）：僅更新 X 焦點，Y 分量已無讀寫點
                        // （恆 0.5000，見 CD-11／confirmMask 硬編 ,0.5000）。
                        sawFace = true;   // 101b-T2（CD-8）：找到臉，_maskStartSettle 據此掛收斂 tween
                        this._maskFocalX = parsed.x;
                        // 101b-T2（CD-4a）：這行原本在此重算終值——現整行移除，終值改由收斂
                        // timeline 的 t=1 端點產生（computeMaskSettleGeometry），由構造保證
                        // 「首次可見幀＝全幅」不被本行的終值寫入破壞。
                    }
                    // else：無臉——維持起手基準（video：右裁 x；actress：3/4 置中 0.5，
                    // openMask 起手已算好），不動它。逃生口仍可拖曳 + ✓ 存入（spec §3.7-6）。

                    // 152d-T-D4 插入點 B：reason → 就地提示（CD-152d-4b）。
                    // failed 走 success:true，必須在此成功分支開口；與下方 catch 同 key 是刻意的。
                    if (data.reason === 'too_slow_auto_disabled') {
                        this.showToast(window.t('showcase.lightbox.mask_focal_too_slow_auto_disabled'), 'info');
                    } else if (data.reason === 'too_slow') {
                        this.showToast(window.t('showcase.lightbox.mask_focal_too_slow_hint'), 'info');
                    } else if (data.reason === 'still_detecting') {
                        // 159 pre-merge：5 秒外殼到了但背景那輪還在跑——結局未定，文案不能先說「已關掉」或「可以去關」。
                        this.showToast(window.t('showcase.lightbox.mask_focal_still_detecting'), 'info');
                    } else if (data.reason === 'endpoint_down') {
                        // 187a-T5／CD-16：外部端點沒回應，這次退回本機找臉。
                        this.showToast(window.t('showcase.lightbox.mask_focal_endpoint_down'), 'info');
                    } else if (data.reason === 'failed') {
                        this.showToast(window.t('showcase.lightbox.mask_detect_failed'), 'error');
                    }
                    // "" / device_disabled / 缺欄 → 靜默
                }
            } catch (e) {
                // 偵測失敗只 toast，_maskFocalX 維持右裁基準，不讓 UI 卡在半套態。
                if (session === this._maskSession) {
                    this.showToast(window.t('showcase.lightbox.mask_detect_failed'), 'error');
                }
            } finally {
                // session guard 同時包住 _maskDetecting 與停星空動畫：若這期間已被 _resetMask
                // 中斷（換片/關燈箱），_resetMask 早已呼叫過 _maskStopWaitAnim 並清空
                // this._maskWaitTl；此處若不 session-gate，會誤殺「新 session 剛啟動的星空」
                // （見本 task 的「等待期間快速連續開關」邊界案例）。
                // 101b-T2（CD-4a/CD-4b）：原本這裡直呼 _maskDetecting=false + _maskStopWaitAnim()
                // ——那是「硬切」本體，本 Part 要消滅的正是這個。改呼叫 _maskStartSettle(sawFace)，
                // 由它接手決定全幅預寫→_maskDetecting 解禁→交棒星空→掛收斂 timeline 的完整順序
                // （或 g0/canAnimate 不成立時走 fallback 原路）。finally 是 timeline 的起跑點，
                // 不是收尾點——_maskStopSettleAnim() 刻意不放在這裡。
                if (session === this._maskSession) {
                    this._maskStartSettle(sawFace);
                }
            }
        },

        // 拖曳起手（pointerdown，同步非 async）：drag-start 當下一次性讀取 W/H/winW，全程不在
        // pointermove 內呼叫 getBoundingClientRect（效能 + 98b-T6 量測-in-binding gotcha 同型陷阱）。
        _maskDragStart(evt) {
            if (!this._maskVisible) return;
            // 再入防線（自查補強）：拖曳進行中若再來一個 pointerdown（如觸控第二指落在窗上），
            // 直接忽略——否則會覆寫 _maskDragMoveHandler/_maskDragUpHandler 參考，讓第一組
            // document listener 永遠移不掉（洩漏 + 並發 stale 寫入）。
            if (this._maskDragging) return;
            // 拖曳接管：收斂補間進行中被拖曳接管——kill 收斂 tween 讓使用者的手勝出
            // （比照 killTweensOf「最新的勝出」慣例）。插入點在兩個 early-return 之後、第一次
            // 取樣之前，不放首行（放首行會在早退情境誤 kill）。
            this._maskStopSettleAnim();
            const el = this._maskTarget().imgEl;   // 100b-T1：G3 null-safe（x-if 內 $refs 可能 undefined）
            if (!el || !el.naturalWidth) return;
            const rect = el.getBoundingClientRect();
            const W = rect.width;
            const H = rect.height;
            if (!W || !H) return;
            const r = parseFloat(getComputedStyle(el).getPropertyValue(this._maskTarget().ratio));
            if (!Number.isFinite(r) || r <= 0) return;
            const winW = Math.min(W, H * r);
            const startClientX = evt.clientX;
            // 101b-T2 P2（Codex PR review）：拖曳接管「收斂中」的窗——_maskStopSettleAnim() 已 kill
            // timeline，但 _maskFocalX 仍是偵測終值，而視覺上的窗還停在收斂中的**中間**幾何（settle
            // onUpdate 每 tick 寫 _maskWinStyle 的內插值：中間寬度 + 中間中心 focal_t）。若直接用終值
            // 算 startLeft，首次 pointermove 會把窗從當前可見中心瞬跳到終值中心（X snap）。修法：交棒
            // 當下把 _maskFocalX 同步成「當前可見窗的中心焦點」（從 _maskWinStyle 反解），讓終寬窗以
            // **當前中心**落定——中心不跳、只有寬度收到終值（WYSIWYG 必需：存的裁窗恆為終比例），
            // 再從那裡跟手。非收斂態時可見窗中心本就 == _maskFocalX（同一 computeMaskWinGeometry
            // writer），此步為 no-op。解析失敗（_maskWinStyle 尚未成幾何）→ 保留 _maskFocalX（防禦）。
            const curWin = this._maskWinStyle;
            if (curWin && typeof curWin.width === 'string' && typeof curWin.transform === 'string') {
                const curWinW = parseFloat(curWin.width);
                const curLeftMatch = /translateX\(\s*(-?[\d.]+)px\s*\)/.exec(curWin.transform);
                const curLeft = curLeftMatch ? parseFloat(curLeftMatch[1]) : NaN;
                if (Number.isFinite(curWinW) && Number.isFinite(curLeft)) {
                    this._maskFocalX = (curLeft + curWinW / 2) / W;
                }
            }
            // 101b P2（Codex PR#110 二審）：交棒當下立刻把窗重算成「終比例窗、以當前中心落定」，
            // 不等 onMove。否則「收斂中按下→未拖曳即放開（tap／aborted drag）」時 _maskWinStyle 仍卡在
            // _maskStopSettleAnim 凍結的中間寬度，比 confirmMask 會存的終窗更寬 → WYSIWYG 破。與 onMove
            // 同一 writer（computeMaskWinGeometry），第一次 pointermove 再算一次亦一致；非收斂態 no-op。
            this._maskWinStyle = computeMaskWinGeometry(W, H, r, this._maskFocalX);
            // 起手左緣必須與「視覺上看到的窗位置」一致＝比照 _computeMaskWinStyle 一樣 clamp
            // （99a Gemini P2）。raw _maskFocalX 貼邊時未鉗的 start 值會落在邊界外，窗子停在
            // 邊界但拖曳從界外起算 → 反向拖曳有死區、不跟手。clampMaskWinLeft 是數學軸無關的純量
            // clamp（B-4：只改 JSDoc 參數名，不改實作），(left,W,winW) 傳法完全正確。
            const startLeft = clampMaskWinLeft(
                (this._maskFocalX !== null && this._maskFocalX !== undefined)
                    ? this._maskFocalX * W - winW / 2
                    : W - winW,
                W,
                winW,
            );
            const session = this._maskSession;   // 拖曳中途換片/關燈箱防線（雙保險，見下）

            this._maskDragging = true;

            const onMove = (e) => {
                // 防禦性早退：正常路徑 _resetMask 已同步移除本 listener，此處只防「移除時序」邊界。
                if (session !== this._maskSession) return;
                e.preventDefault();
                const dx = e.clientX - startClientX;
                const left = clampMaskWinLeft(startLeft + dx, W, winW);   // clamp 進封面邊界
                this._maskFocalX = (left + winW / 2) / W;
                // 99a-T5：恆 object——委派 computeMaskWinGeometry（同 _computeMaskWinStyle 的
                // writer 來源，見 _maskWinStyle 宣告處註解與 shared/mask-geometry.js 開頭說明）。
                this._maskWinStyle = computeMaskWinGeometry(W, H, r, this._maskFocalX);
            };
            const onUp = () => {
                if (session === this._maskSession) this._maskDragging = false;
                this._maskRemoveDragListeners();
            };
            this._maskDragMoveHandler = onMove;
            this._maskDragUpHandler = onUp;
            document.addEventListener('pointermove', onMove, { passive: false });
            document.addEventListener('pointerup', onUp);
            document.addEventListener('pointercancel', onUp);
            evt.preventDefault();
        },

        // 成對移除 document 上的拖曳 listener：pointerup/pointercancel 正常路徑會自呼叫；
        // _maskTeardown/_resetMask 異常路徑（拖曳中途換片/關燈箱、確認/取消）兜底，防洩漏。
        _maskRemoveDragListeners() {
            if (this._maskDragMoveHandler) {
                document.removeEventListener('pointermove', this._maskDragMoveHandler);
                this._maskDragMoveHandler = null;
            }
            if (this._maskDragUpHandler) {
                document.removeEventListener('pointerup', this._maskDragUpHandler);
                document.removeEventListener('pointercancel', this._maskDragUpHandler);
                this._maskDragUpHandler = null;
            }
        },

        // ✓ 確認：存手動焦點 → POST /video/save-focal，同參考 mutate targetVideo（lightbox + grid 即時對臉）。
        async confirmMask() {
            // _maskFocalX null 只應發生在極短暫態（geometry 尚未解出）；openMask 一旦幾何解出即收斂
            // 為具體值（correction B），此處 null-guard 純防禦（幾何失敗 / identity 遺失等異常態才會觸發）。
            if (this._maskFocalX === null || this._maskFocalX === undefined || !this._maskTarget().identity) {
                this._maskTeardown();
                return;
            }
            // 100b-T2a（§B-1b）：token guard 只在 handles409（video）成立時檢查——女優無 token、
            // 無 409（v3 契約），不得因缺 token 被 fail-closed 擋下。await 前捕獲：_maskKind 若
            // 因中途換片被 _resetMask 清空，_maskTarget() 之後會 dispatch 回預設（video）分支，
            // 捕獲值才能忠實反映「這次送出的到底是哪個 kind 的請求」。
            const handlesToken = this._maskTarget().handles409;
            // Codex PR#107 第二輪 P2 fail-closed guard（video-only）：從未拿到 server 端
            // cover_path token（openMask 的 /detect-focal 連 JSON body 都沒解析成功，例如
            // 純網路層失敗）→ 拒絕送出，不可用猜的 cover_path 打穿 compare-and-store 守衛的
            // 保護意圖（寧可這次存不進、逼使用者重開遮罩，也不可能誤配錯封面）。
            if (handlesToken && (this._maskExpectedCoverPath === null || this._maskExpectedCoverPath === undefined)) {
                this.showToast(window.t('showcase.lightbox.mask_save_failed'), 'error');
                this._maskTeardown();
                return;
            }
            const session = this._maskSession;
            const targetObj = this._maskTarget().obj;   // 捕獲：await 期間可能已換片/切走
            // 與 targetObj 同時捕獲 kind——本函式下方所有對
            // 「這次送出的到底是哪個 kind」的判斷（含下面組 focal 字串、下方 _syncActressesArray
            // 的 gate）一律讀這個捕獲值，不讀 this._maskKind 即時值。換片路徑
            // （nextActressLightbox → _setActressLightboxIndex → _resetMask）會把 this._maskKind
            // 清空，若 await 之後才判斷即時值，使用者在存檔 request resolve 前切走女優就會讓判斷
            // 誤判成 video 分支、跳過牆格同步。
            const kind = this._maskKind;
            // Y 分量恆 0.5000（video 恆右裁 X 定基準，render 只用 X，spec §3.3；actress 恆
            // 3/4 置中，Y 軸讀寫已移除，見 CD-11）。
            const focal = `${this._maskFocalX.toFixed(4)},0.5000`;
            try {
                const resp = await fetch(this._maskTarget().focalEndpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    // Codex PR#107 第二輪 P2：video 分支原樣帶回 openMask 期間 server 給的
                    // cover_path，讓 update_manual_focal 的 compare-and-store 守衛比對「使用者
                    // 觀察當下」與「存檔當下」的封面是否一致，擋掉 rescan/rescrape 換封面的
                    // race；actress 分支只送 {focal}（v3：無 token，_maskTarget().focalBody 內
                    // 已 dispatch，此處統一呼叫不裸組 body）。
                    body: JSON.stringify(this._maskTarget().focalBody(focal)),
                });
                const data = await resp.json().catch(() => null);
                if (handlesToken && resp.status === 409) {
                    // 封面已變更（compare-and-store 守衛擋下）：與一般失敗分開給更明確的提示。
                    // actress 無此分支（handlesToken=false，v3 無 409，spec §3.5）。
                    if (session === this._maskSession) {
                        this.showToast(window.t('showcase.lightbox.mask_cover_changed'), 'error');
                    }
                    return;
                }
                if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                if (!data || !data.success) throw new Error((data && data.error) || 'API failed');
                // 燈箱主圖：video 走 T2 既有 applyCellFocal $watch 接手；actress 直接寫
                // targetObj（= 這次送出時捕獲的 currentLightboxActress，await 前已凍結）。
                targetObj.auto_focal = data.auto_focal;
                targetObj.crop_mode = 'manual';
                // 100b-T4（Opus 審核裁決 1，CDP 實測背書）：牆上小格側寫入。
                // 🔴 上面兩行原本的舊註解主張「actress 分支的 targetObj 與 paginatedActresses[idx]
                // 恆為同一物件參考、改一邊即改兩邊」——這個前提已被推翻，此處曾經是全函式唯一的
                // 缺口：`_fetchLiveAliases`（state-actress.js:791-793）
                // 在 alias fetch resolve 時，若該女優 alias 端點回 200（21 位中 3 位），會執行
                // `currentLightboxActress = Object.assign({}, currentLightboxActress, {aliases})`
                // ——把 currentLightboxActress 換成脫鉤副本、不寫回 paginatedActresses。此時只寫
                // 上面的 targetObj 只改到脫鉤副本，牆上小格永遠停在存檔前的裁法（必須重載才會
                // 更新，違反 spec §3.4「✓ 存入後焦點立即生效」）。alias 回 404 的 18 位因前提
                // 僥倖成立而正常 ⇒ 資料相依的間歇失敗，抽測/CDP 抽樣都可能整批放行。
                // 與 _uploadActressPhoto／_onPickerSelect 對稱：改資料一律 by-name 呼叫
                // _syncActressesArray；用 targetObj.name（await 前捕獲值）而非
                // this.currentLightboxActress?.name，防使用者在 await 期間切走女優時寫錯格。
                // gate 在 kind 為 'actress' 時才做：video 分支 targetObj 是 currentLightboxVideo，
                // 沒有 paginatedActresses 可查（那是 paginatedVideos），video/actress 是正交的
                // 兩條資料，不可讓這段在 video 分支被誤觸發。
                // gate 讀上方捕獲的 kind（await 前凍結值），不讀
                // this._maskKind 的即時值——切走 → _resetMask 清掉 kind 欄位 → 若讀即時值會誤判
                // 成 video 分支而跳過本次同步，牆格停在存檔前的裁法。與 _onPickerSelect／
                // _uploadActressPhoto 一致：改資料（by captured name）無條件做，只有「改當前畫面」
                // 才需要 gate 在使用者還留在原處。
                if (kind === 'actress') {
                    this._syncActressesArray(targetObj.name, { auto_focal: data.auto_focal, crop_mode: 'manual' });
                }
                // TASK-138-T5（CD-E3）：hero 卡 by-name 回寫，對稱於上面牆格 _syncActressesArray。
                // openHeroCardLightbox 先讓 currentLightboxActress === _matchedActress，隨後
                // _fetchLiveAliases 的 Object.assign 會把 currentLightboxActress 換成脫鉤副本；
                // 此時只寫 targetObj（= 脫鉤副本）改不到 hero 卡讀的 _matchedActress。
                // 不得拆 Object.assign；不動 syncActressFields 簽章；用 targetObj.name
                // （await 前捕獲）比對，沿用既有 by-name 寫法，不自創正規化。
                if (kind === 'actress' && this._matchedActress && this._matchedActress.name === targetObj.name) {
                    this._matchedActress.auto_focal = data.auto_focal;
                    this._matchedActress.crop_mode = 'manual';
                }
            } catch (e) {
                if (session === this._maskSession) {
                    this.showToast(window.t('showcase.lightbox.mask_save_failed'), 'error');   // 沿用既有 key
                }
            } finally {
                if (session === this._maskSession) this._maskTeardown();
            }
        },

        // ✗ 取消：純同步收尾，不寫 DB——force-detect 本就沒寫，✗ 天然無殘留（CD-2）。
        cancelMask() {
            this._maskTeardown();
        },

        // confirmMask/cancelMask 共用收尾：收 overlay + 解 resize listener + 解拖曳 listener。
        _maskTeardown() {
            this._maskVisible = false;
            this._maskDragging = false;
            if (this._maskResizeHandler) {
                window.removeEventListener('resize', this._maskResizeHandler);
                this._maskResizeHandler = null;
            }
            this._maskRemoveDragListeners();   // 防禦性：理論上 pointerup 已先清，這裡再保險一次。
            // 99a-T5：防禦性再保險——理論上 confirmMask/cancelMask 觸發時 detect 早已 resolve
            // （✓/✗ 只在 _maskDetecting===false 才可見/可點），星空動畫應該已由 openMask 的
            // finally 停過；比照上面 _maskRemoveDragListeners 的「再保險一次」寫法補一次 kill。
            this._maskStopWaitAnim();
            // 收斂補間對稱再保險——理論上 ✓/✗ 觸發時收斂早已播完，比照上面
            // 「再保險一次」寫法補一次 kill（idempotent，收斂已結束時安全 no-op）。
            this._maskStopSettleAnim();
            // 本函式刻意**不**在此清女優圖已載入旗標。
            // 該旗標的生命週期屬於「燈箱這張照片」（writer 只有 @load handler +
            // _refreshActressPhotoLoaded() 的 4 個呼叫點），不屬於「這次遮罩編輯 session」。
            // confirmMask/cancelMask 收尾走到本函式之後，沒有任何路徑會把它重新判定回真值
            // ——URL 未變的已載入 img 不會重觸發 @load——在此清掉會讓 showcase.html 的
            // focal 按鈕 x-show 判斷永久失效（confirm/cancel 各一次即消失），直到關燈箱重開
            // 或切換女優才恢復。真正該清（且會被重新判定）的收尾路徑是換片/關燈箱的
            // _resetMask()（下方）——其後必經 _setActressLightboxIndex 呼叫
            // _refreshActressPhotoLoaded() 重新判定，兩者語意不同，不可為了對稱一併刪除。
            // 100b-T1（裁決 D-3）：kind 收尾排最後——本函式內以上收尾皆不依賴 _maskTarget()（皆
            // 直接操作 handler/listener 參考），故順序本身不影響現有行為；仍照裁決排最後，
            // 避免未來新增依賴 _maskTarget() 的收尾時誤踩「先清 kind 查到錯元素」。
            this._maskKind = null;
        },

        // 換片 / 關燈箱：丟棄未提交態（不 commit，不把前片焦點帶到下一片）。
        // 124c-T3（spec-124c §3.4）：對焦編輯進行中，換片的每一個入口都不作用。
        // 定義在這裡（_mask* 狀態的擁有者）而不是各檔各讀一次 this._maskVisible——
        // state-actress.js 依 100b-T5 CD-1 不得直接碰 _mask* 識別字，一律走本檔的共用方法
        // （同 this._resetMask() 的既有慣例）。四個 chokepoint 因此用同一個判斷式。
        _navBlockedByFocalEdit() {
            return this._maskVisible === true;
        },

        _resetMask() {
            // 98b P2 fix：換片/關燈箱一律使舊 session 失效（即使當下沒開新遮罩），
            // 讓仍在途的舊 await 回應之後必被 session gate 擋下，不依賴 _maskVisible 的
            // x-show 巢狀結構作為唯一防線（defense-in-depth，同時涵蓋「切 B 但沒開 B 遮罩」）。
            this._maskSession++;
            this._maskDetecting = false; // 98b P2 fix(二)：invalidate 時清偵測態，防舊 detect 的 spinner 漏進下個 session（Codex）
            this._maskVisible = false;
            this._maskWinStyle = {};     // 98b-T6：清窗幾何避免殘留閃（下次 open 同步重算覆蓋）。
                                          // 99a-T5：恆 object，不可退回 '' string（見宣告處註解）。
            this._maskFocalX = null;     // 99a-T3：清 component-state 焦點，防下一片沿用上一片的拖曳結果
            this._maskExpectedCoverPath = null;   // Codex PR#107 P2：防下一片沿用上一片的 cover token
            this._maskDragging = false;  // 99a-T3：防拖曳中途換片，dragging class 卡死在 true
            this._maskRemoveDragListeners();   // 99a-T3：拖曳中途換片/關燈箱兜底，移除 document listener
            this._maskStopWaitAnim();    // 99a-T5：detect 期間中斷（換片/關燈箱/ESC）對稱停星空動畫，
                                          // 防「舊 session 星空還在跑、新 session 又疊一份」
            this._maskStopSettleAnim();  // 收斂期間中斷（換片/關燈箱/ESC）對稱停止，
                                          // 防「舊 session 收斂還在跑、新 session 又疊一份」
            if (this._maskResizeHandler) {
                window.removeEventListener('resize', this._maskResizeHandler);
                this._maskResizeHandler = null;
            }
            // 100c-T2（CD-5）：兩旗標同步清除收斂進 helper，語意不變（換片/關燈箱必須清，
            // 之後必經 _refreshActressPhotoLoaded() 重新判定）。
            this._clearActressPhotoState();
            // 100b-T1（裁決 D-3）：kind 收尾排最後，理由同 _maskTeardown。
            this._maskKind = null;
        },


        // 99a-T5：星空等待動畫對稱停止 helper——openMask finally（正常結束，session-gated）、
        // _resetMask（中斷：換片/關燈箱/ESC）、_maskTeardown（防禦性再保險）三處對稱呼叫。
        // idempotent：this._maskWaitTl 已 null 時安全 no-op（GhostFly.stopFocalDetectWait 內部
        // 亦對 null handle 安全 no-op，belt-and-suspenders）。
        _maskStopWaitAnim() {
            if (this._maskWaitTl && window.GhostFly && window.GhostFly.stopFocalDetectWait) {
                window.GhostFly.stopFocalDetectWait(this._maskWaitTl);
            }
            this._maskWaitTl = null;
        },

        // 101b-T2（CD-4a/CD-4b/CD-4c/CD-5/CD-7/CD-8/CD-9/CD-11a，§A-3a 權威步驟表）：由 openMask
        // finally 呼叫（已 session-gated），取代舊有的「_maskDetecting=false + _maskStopWaitAnim()」
        // 硬切。決定「偵測完成 → 星空淡出 → 亮窗收斂到終值」是否以單一 GSAP timeline overlap 播放，
        // 或退化成今天的瞬現路徑（g0 為 null / PRM / 動畫層不可用）。
        //
        // hasFace：CD-8——找到臉才掛第 4 條 proxy tween（收斂），無臉/偵測失敗仍走同一條 timeline
        // （星空/spinner 淡出＋窗淡入），只是窗停在起手基準不收斂。
        _maskStartSettle(hasFace) {
            // ① 取樣一次（比照 _maskDragStart 首次取樣，刻意不逐 tick 量測）。coverEl 是
            // openMask 內 `if (!isPRM)` block 的區域變數，離開該 block 即不可見，此處需自己重取。
            const el = this._maskTarget().imgEl;
            const coverEl = el?.closest('.lightbox-cover');
            let W, H, r;
            if (el && el.naturalWidth) {
                const rect = el.getBoundingClientRect();
                W = rect.width;
                H = rect.height;
                r = parseFloat(getComputedStyle(el).getPropertyValue(
                    this._maskKind === 'actress' ? '--actress-crop-ratio' : '--poster-crop-ratio'
                ));
            }

            // ② gate（CD-11a fail-closed 幾何 + CD-4c 動畫層可用性，同一個 fallback 分支）。
            const g0 = computeMaskSettleGeometry(W, H, r, this._maskFocalX, 0);
            const isPRM = !!(window.OpenAver && window.OpenAver.prefersReducedMotion);
            // 🔴 Codex PR review P2 修正：canAnimate 必須連 gate `this._maskWaitTl`——
            // wait handle 是 :1386 handoffFocalDetectWait(this._maskWaitTl) 交棒的前提，
            // 缺它（burst/star DOM 不在場，即使 gsap 存在）_maskWaitTl 恆為 null，
            // handoffFocalDetectWait(null) 回 null，解構 `{ stars, burst }` 會拋
            // TypeError，此時 _maskSettling 已設 true 卻無 cleanup，卡死 spinner/遮罩。
            // gate 掉後走既有 fallback 分支（瞬現、_maskStopWaitAnim 對 null 安全 no-op），
            // 不是 belt-and-suspenders 式 null-safe 解構——單一決策點，結構上不可能再拿到 null。
            const canAnimate = !isPRM
                && typeof gsap !== 'undefined'
                && window.GhostFly && typeof window.GhostFly.handoffFocalDetectWait === 'function'
                && this._maskWaitTl;
            if (!g0 || !canAnimate) {
                // 既有 :1043 原路——不得用已知無效的 W/H/r 重算終值（那組值已知不合法，
                // computeMaskSettleGeometry 才會回 null）；合法 fallback 恆存在（openMask
                // pre-flight 已擋掉不合法幾何，_maskWinStyle 此刻必為合法值）。
                this._maskWinStyle = this._computeMaskWinStyle() || this._maskWinStyle;
                this._maskStopWaitAnim();   // CD-4b：不呼叫 → repeat:-1 loop 整條洩漏
                this._maskDetecting = false;
                return;
            }

            // ③ 全幅，同步寫在 x-show 翻真之前（CD-4a 核心不變式）——但這只是 hasFace（收斂）
            // 路徑的起點約定：no-face 沒有步驟⑥掛收斂 tween，寫「全幅」給它既非「起點」也非
            // spec §4.2 要求的「終點」（基準）。101b-T5：hasFace 分支一字不動（g0），!hasFace
            // 直接落基準幾何（與既有 PRM fallback 分支 :1380 呼叫同一個 _computeMaskWinStyle()）
            // ——CD-8「找到／沒找到的差別＝收斂 vs 不收斂，只此一項」的直接編碼。
            this._maskWinStyle = hasFace ? g0 : (this._computeMaskWinStyle() || this._maskWinStyle);
            // ④ 必須晚於 ② 的 gate（CD-4c：早於它＝動畫層不可用時永久卡 true）。
            this._maskSettling = true;
            // ⑤ x-show 此刻才放行；首次 paint 讀到步驟③寫入的值——hasFace＝全幅（g0，收斂起點）、
            //    no-face＝基準（右裁/置中，直接落定不收斂，spec §4.2）。
            this._maskDetecting = false;

            // ⑥ 交棒星空（CD-4b，不 clearProps）+ 建立單一 timeline（overlap 由 timeline 保證）。
            const { stars, burst } = window.GhostFly.handoffFocalDetectWait(this._maskWaitTl);
            const win = coverEl?.querySelector('.lb-mask-window');
            const spinner = coverEl?.querySelector('.lb-mask-spinner');
            const cleanup = () => this._maskClearSettleProps();
            // 101b-T2 / Codex PR#110 P2-2：GSAP 編排移入 GhostFly（shared/，不被 pages 守衛掃描，
            // 已是 focal 動畫家族的家）。tween 結構／ease／duration 一字不動，此處只注入
            // onConverge（每 tick 寫收斂中間幾何）與 onDone（收尾）兩個副作用。
            const tl = window.GhostFly.buildFocalSettleTimeline({
                stars, spinner, win, hasFace,
                onConverge: (t) => { this._maskWinStyle = computeMaskSettleGeometry(W, H, r, this._maskFocalX, t) || this._maskWinStyle; },
                onDone: cleanup,
            });
            this._maskSettleTl = tl;
        },

        // 101b-T2（§A-5）：收斂 tween 對稱停止 helper，逐字比照 _maskStopWaitAnim 的形狀
        // （idempotent、單一 helper、多處對稱呼叫）。呼叫點：_maskDragStart（CD-10 拖曳接管）、
        // _maskTeardown／_resetMask（中斷路徑再保險）。openMask finally 刻意不呼叫——那是
        // timeline 的起跑點，kill 等於自殺。
        _maskStopSettleAnim() {
            if (this._maskSettleTl && typeof this._maskSettleTl.kill === 'function') this._maskSettleTl.kill();
            // 顯式呼叫，不依賴 kill() 觸發 onInterrupt（ghost-fly.js 既有註解：GSAP 3 .kill()
            // 不保證 fire onInterrupt）。_maskClearSettleProps 本身冪等，onInterrupt 若仍另外
            // 觸發一次亦安全。
            this._maskClearSettleProps();
        },

        // 101b-T2（CD-9a）：settle timeline 的 onComplete/onInterrupt 共用收尾（比照
        // ghost-fly.js clearLanding「一個 closure、兩路徑共用」先例）。單一清理真理，供
        // _maskStopSettleAnim 與 timeline 自身收尾兩處呼叫，必須冪等（clearProps 對已無 inline
        // style 的元素是 no-op；clearFocalDetectWait 對 null handle 亦 no-op）。
        _maskClearSettleProps() {
            if (window.GhostFly && window.GhostFly.clearFocalDetectWait) {
                window.GhostFly.clearFocalDetectWait(this._maskWaitTl);   // 星空 clearProps 延到此刻
            }
            const el = this._maskTarget().imgEl;
            const coverEl = el?.closest('.lightbox-cover');
            if (coverEl && window.GhostFly?.clearFocalSettleProps) {
                // 101b-T2 (CD-9a) / Codex PR#110 P2-2：clearProps 移入 GhostFly（DOM lookup 仍在此）。
                const win = coverEl.querySelector('.lb-mask-window');
                const spinner = coverEl.querySelector('.lb-mask-spinner');
                window.GhostFly.clearFocalSettleProps({ win, spinner });
            }
            this._maskWaitTl = null;
            this._maskSettleTl = null;
            this._maskSettling = false;   // burst/spinner 此刻才被 x-show 收掉（兩者已 opacity 0）
        },

        // 亮窗幾何：讀 CSS var --poster-crop-ratio（非硬編）+ _maskFocalX 解焦點 x（component state，
        // 非 video.auto_focal——編輯態顯示真實落點，不套 focalObjectPosition 的 deadzone）。
        // 回傳 inline style OBJECT（width/height + transform translateX）供 template :style 綁定
        // （99a-T5：不可回傳 string，見 _maskWinStyle 宣告處註解——string 值會被 Alpine `:style`
        // 整串覆寫 style attribute，洗掉 x-show 設的 display:none）。失敗（rect=0 / ratio 讀不到）
        // 回傳 null，呼叫端（openMask）以 `if (!s)` 判斷；resize handler 呼叫端已知 null 會 fallback
        // 保留前值（見 openMask 內 _maskResizeHandler 定義）。
        // 亮窗以外由 CSS box-shadow spotlight 壓暗；transform 變化時 CSS transition 左右滑動（拖曳中停用，見 showcase.css）。
        // 98b-T6：純 compute（原 _maskWindowStyle 邏輯不變），由 openMask/drag/resize imperative 呼叫。
        // 100b-T2a（§B-3）：el 改走 _maskTarget().imgEl（G3 null-safe，dispatch 兩分支）；
        // 窗幾何建構（winW/winH）委派 computeMaskWinGeometry（shared/mask-geometry.js，
        // 可測試性 + G1 收斂單一 writer 來源，見該檔開頭說明）——ratio 讀取仍留在本函式體內
        // （裁決3，見下）。
        _computeMaskWinStyle() {
            const el = this._maskTarget().imgEl;
            // C17/#10：圖 render 前 rect=0 → 不畫（naturalWidth 未就緒）
            if (!el || !el.naturalWidth) return null;
            const rect = el.getBoundingClientRect();
            const W = rect.width;
            const H = rect.height;
            if (!W || !H) return null;
            // 100b-T2a（裁決3）：兩個字面 CSS var 名保留在本函式體內、不委派 _maskTarget().ratio——
            // static_guard_lint.mjs 有 4 條 scope-anchor 規則錨定本函式本體（getComputedStyle
            // required／--poster-crop-ratio required／兩條硬編比例常數 forbidden）。改成
            // getComputedStyle(el).getPropertyValue(this._maskTarget().ratio) 會讓
            // --poster-crop-ratio 字面字串離開此函式 scope，required 規則靜默 RED（T5-② 才是
            // 調整這 4 條 scope rule 的正式責任 task，T2 不搶做）。三元式是刻意重複，不可「清理」
            // 成委派寫法。
            const r = parseFloat(getComputedStyle(el).getPropertyValue(
                this._maskKind === 'actress' ? '--actress-crop-ratio' : '--poster-crop-ratio'
            ));
            if (!Number.isFinite(r) || r <= 0) return null;
            return computeMaskWinGeometry(W, H, r, this._maskFocalX);
        },
    };
}
