// eslint.config.mjs — ESLint 9 flat config
// OpenAver frontend JS lint rules
// Replaces: TestNoCreateElement, TestNoDuplicateNativeDialog(test1),
//           TestSearchConsoleLogGuard, TestShowcaseRemoveActressNoNativeConfirm,
//           TestNoAlertInSearchJs(前9 alert tests)
//
// Flat config 注意事項：
// 同一條 rule（特別是 array-style 如 no-restricted-syntax）在多個 matching configs
// 會被「後者完全替換」而非 array merge。為避免規則靜默失效，本檔以 `ignores` 切出
// 不重疊的 file glob 區段，每個區段給該 file group 完整的 selector 清單。
import js from "@eslint/js";

// ── 共用 selector 物件 ─────────────────────────────────────────
const SEL_CREATE_ELEMENT = {
  selector:
    "CallExpression[callee.object.name='document'][callee.property.name='createElement']",
  message:
    "Use Alpine x-if / x-for instead of document.createElement in state mixins. " +
    "createElement is only allowed in component files (e.g. ghost-fly.js, tutorial.js).",
};

const SEL_SHOW_MODAL = {
  selector: "CallExpression[callee.property.name='showModal']",
  message:
    "Use Alpine state-driven modal pattern instead of native showModal() in search state files. " +
    "See TestNoDuplicateNativeDialog pattern.",
};

const SEL_WINDOW_CONFIRM = {
  selector:
    "CallExpression[callee.object.name='window'][callee.property.name='confirm']",
  message:
    "Use fluent-modal pattern instead of window.confirm(). " +
    "See CD-52-11 decision for migration pattern.",
};

// ── CD-56B-T2 共用 selector 物件 ────────────────────────────────
const SEL_BREATHING_MANAGER_NEW = {
  selector: "NewExpression[callee.name='BreathingManager']",
  message:
    "BreathingManager 只能在 pages/motion-lab/constellation-host.js 建立實例（host lifecycle 持有原則）。其他模組禁止直接 new BreathingManager（CD-56B-T2 lint guard）。",
};

// ── CD-T2FIX-1 starSettle Literal ban（共用，所有非 animations.js 檔案）────
// Codex r1 P3 修正：原 v1 只在 Group 6 加 ban，但 Group 6 ignores state/** + constellation host，
// 這些檔案可繞過。改為共用 selector，由每個非 animations.js group 自帶。
const SEL_STARSETTLE_LITERAL = {
  selector: "Literal[value='starSettle']",
  message:
    "starSettle（CD-T2FIX-1）已退役。非 animations.js 檔案禁止出現 'starSettle' 字串。register 保留在 animations.js（Group 4 Property selector 白名單保護 CustomEase.create）。",
};

// ── 56c-T4fix7 filter: brightness() ban（取代 TestClipStageGuard pytest 守衛）────
// Hover dim 路徑必須改用 --slot-dim-opacity CSS var tween；filter: brightness() 已退役。
// 限定 state-similar.js + constellation-host.js（兩 host），其他檔案不限制
// （cover-image filter / scrubber 等仍可能合法用 brightness）。
const SEL_FILTER_BRIGHTNESS = {
  selector: "Literal[value=/brightness\\(/]",
  message:
    "filter: brightness() 在 56c-T4fix7 後禁用，hover dim 改用 --slot-dim-opacity CSS var tween（v0.8.6 取代 TestClipStageGuard pytest 守衛遷移到 eslint）。",
};

// ── 67-B2 (CD-67-7) unload listener ban（共用，所有 JS 檔案）────
// 新版 Chrome 以 Permissions-Policy 預設封鎖 'unload' → listener 靜默不註冊 + console 報錯。
// 一律改用 bfcache-safe 的 'pagehide'（page-lifecycle.js 已遷移）。與 SEL_WINDOW_CONFIRM 同為
// universal ban：flat config 同 rule 後者整段 replace 不 merge，故須加進每個 group 的清單（不能用
// 獨立 global block，會覆蓋各 group 的完整 selector）。
const SEL_NO_UNLOAD_LISTENER = {
  selector:
    "CallExpression[callee.property.name='addEventListener'][arguments.0.value='unload']",
  message:
    "addEventListener('unload', …) 已禁用（67-B2/CD-67-7）：新版 Chrome 以 Permissions-Policy 封鎖 'unload'，listener 靜默不註冊 + console 報錯。改用 bfcache-safe 的 'pagehide'（page-lifecycle.js 的 _doCleanup 有 _cleanedUp one-shot guard，pagehide + leavePage 雙觸發安全）。",
};

// ── 92a-T2 (CD-92a-3) hasContent 手動賦值 ban（限 search/state/**）────
// hasContent 已改 computed getter（base.js）；禁止 this.hasContent = ... 手動賦值復活，
// 否則會重現「loading 態殘留 stale true → 取消鈕＋清除鈕並排（兩組 X）」。
// 只加進 Group 1（search/state/**）陣列，不新開 block（flat config 同 scope 整段 replace，
// 新 block 會覆蓋 Group 1 既有 selector）。getter 定義是 kind:'get' Property，非 AssignmentExpression，不誤傷。
const SEL_HASCONTENT_ASSIGN = {
  selector:
    "AssignmentExpression[left.type='MemberExpression'][left.property.name='hasContent']",
  message:
    "hasContent 已改 computed getter（CD-92a-3，base.js）：禁止手動賦值 this.hasContent = ...；值由 getter 自動推導（pageState !== 'loading' && (searchResults.length>0 || fileList.length>0)）。手動賦值會重現 loading 態殘留 stale true 的「兩組 X」bug。",
};

// ── 92b-T3 (CD-92b-3) playToIcon 移除防復活 ban ────
// playToIcon 已由 GhostFly.playInboundFly 取代並移除（懸停+落地反饋+fallback 三分支）。
// Group 6 抓 definition site（ghost-fly.js），Group 1 抓 caller site（batch.js，Group 6
// ignores state/**）；flat config 同 rule 後者整段 replace，故兩 group 陣列各自帶此 selector。
const SEL_NO_PLAYTOICON = {
  selector: [
    "MemberExpression[property.name='playToIcon']",
    "Property[key.name='playToIcon']",
  ].join(', '),
  message:
    "playToIcon 已於 92b 由 GhostFly.playInboundFly 取代並移除（CD-92b-3）。禁止重新引入（定義或呼叫）；改用 playInboundFly（懸停 0.5s + 落地 scale/glow + 手機 fallback 三分支）。",
};

export default [
  // ── 全域基礎設定 ──────────────────────────────────────────────
  {
    ...js.configs.recommended,
    files: ["web/static/js/**/*.js"],
    rules: {
      // Alpine x-data 注入的 $store / $dispatch 等為 runtime global
      "no-undef": "off",
    },
  },

  // ── 全域禁止 alert / confirm（A-class: no-alert）──────────────
  // no-alert 涵蓋 alert() + confirm() + prompt()，跨所有 file group 一致
  {
    files: ["web/static/js/**/*.js"],
    rules: {
      "no-alert": "error",
    },
  },

  // ── 全域禁止引入 Sortable / sortablejs（CD-61-4：拖曳用 HTML5 native）──
  // no-restricted-imports rule key 不與既有 no-restricted-syntax 衝突（不同 rule key），
  // 故獨立全域 block 安全。只擋 ESM import（本專案 JS 全 ESM）。
  {
    files: ["web/static/js/**/*.js"],
    rules: {
      "no-restricted-imports": ["error", {
        paths: [{
          name: "sortablejs",
          message: "CD-61-4：拖曳用 HTML5 native，禁引入 Sortable.js。",
        }],
        patterns: [{
          group: ["*sortablejs*", "*Sortable*"],
          message: "CD-61-4：禁引入 Sortable / sortablejs。",
        }],
      }],
    },
  },

  // ── search 頁面禁 console.log（A-class: no-console）──────────
  {
    files: ["web/static/js/pages/search/**/*.js"],
    rules: {
      "no-console": ["error", { allow: ["error", "warn"] }],
    },
  },

  // ── no-restricted-syntax：依 file group 切段，避免覆蓋 ────────
  //
  // 設計原則：每個 file group 自成一段，給出該 group 完整的 no-restricted-syntax
  // 清單（包含從上游繼承的規則），不依賴 flat config 疊加（疊加會覆蓋）。
  //
  // 覆蓋關係（後者 wins）：
  //   Group 1 > Group 2 for search/state/**
  //   Group 3 > Group 1/2 for 非 state JS（Group 3 後，但 ignores state/**）
  //   Group 4 > Group 3 for animations.js（後，更具體）
  //   Group 5 > Group 3 for motion-lab/constellation-host.js（後，更具體）
  //   Group 6 > Group 3 for 其餘非 state/非 main/非 animations JS（最後）

  // Group 1: search/state/** — createElement + showModal + window.confirm + BreathingManager（最嚴）
  // + starSettle Literal ban（Codex r1 P3）
  {
    files: ["web/static/js/pages/search/state/**/*.js"],
    rules: {
      "no-restricted-syntax": [
        "error",
        SEL_CREATE_ELEMENT,
        SEL_SHOW_MODAL,
        SEL_WINDOW_CONFIRM,
        SEL_NO_UNLOAD_LISTENER,
        SEL_BREATHING_MANAGER_NEW,
        SEL_STARSETTLE_LITERAL,
        SEL_HASCONTENT_ASSIGN,
        SEL_NO_PLAYTOICON,
      ],
    },
  },

  // Group 2: 其他 state/** — createElement + window.confirm + BreathingManager（不含 showModal）
  // + starSettle Literal ban（Codex r1 P3）
  // + closeSimilarMode 定義唯一性守衛（CD-56C-4）：state-similar.js 白名單（Group 5b），其餘 state 禁止定義
  {
    files: ["web/static/js/pages/**/state/**/*.js"],
    ignores: ["web/static/js/pages/search/state/**/*.js"],
    rules: {
      "no-restricted-syntax": [
        "error",
        SEL_CREATE_ELEMENT,
        SEL_WINDOW_CONFIRM,
        SEL_NO_UNLOAD_LISTENER,
        SEL_BREATHING_MANAGER_NEW,
        SEL_STARSETTLE_LITERAL,
        {
          selector: [
            "Property[key.name='closeSimilarMode']",
            "MethodDefinition[key.name='closeSimilarMode']",
          ].join(', '),
          message:
            "closeSimilarMode 只能在 state-similar.js 定義（CD-56C-4 單一定義原則）。其他檔案可呼叫 this.closeSimilarMode()，但不可定義同名 method。",
        },
      ],
    },
  },

  // Group 3: 非 state/ JS — 只禁 window.confirm
  // （此 group 作為 base，後面 Group 4/5/6 會對特定檔案 supersede）
  // 注意：Group 3 不加 starSettle Literal ban — 因為 animations.js 也 match Group 3（被 Group 4 supersede），
  // 若 Group 3 有 Literal ban，Group 4 雖會替換規則，但更乾淨的做法是各 group 自帶完整清單。
  // breathing.js / 其餘 shared/ 由 Group 6 覆寫並含 SEL_STARSETTLE_LITERAL。
  {
    files: ["web/static/js/**/*.js"],
    ignores: ["web/static/js/pages/**/state/**/*.js"],
    rules: {
      "no-restricted-syntax": ["error", SEL_WINDOW_CONFIRM, SEL_NO_UNLOAD_LISTENER],
    },
  },

  // Group 4: constellation/animations.js 完整規則集（supersedes Group 3）
  // 包含：window.confirm guard + x2 setAttribute guard（rail endpoint 必須經 rails.js）
  // + BreathingManager 實例化禁令（CD-56B-T2）
  // + starSettle caller ban（CD-T2FIX-1）：禁止 ease: 'starSettle' Property（caller 不可走回頭路）
  //   注意：CustomEase.create('starSettle', ...) 是 CallExpression Argument（Literal），
  //   不符合 Property[key.name='ease'] selector，自然白名單（register 保留供 56c 評估）
  {
    files: ["web/static/js/shared/constellation/animations.js"],
    rules: {
      "no-restricted-syntax": [
        "error",
        SEL_WINDOW_CONFIRM,
        SEL_NO_UNLOAD_LISTENER,
        SEL_BREATHING_MANAGER_NEW,
        {
          selector:
            "CallExpression[callee.property.name='setAttribute'][arguments.0.value='x2']",
          message:
            "SVG rail x2 屬性只能在 rails.js（setRailCoords）或 breathing.js（ticker follow）內設定，不在 animations.js 直接 setAttribute。",
        },
        {
          selector: "Property[key.name='ease'][value.value='starSettle']",
          message:
            "starSettle（CD-T2FIX-1）已退役，caller 禁止走回頭路。被點卡飛中央請改用 'fluent-decel'。CustomEase.create('starSettle', ...) 是 CallExpression Argument，自然不符合此 Property selector（允許保留 register）。",
        },
        {
          // Codex r1 P3 修正：補捕 quoted key 形式 { 'ease': 'starSettle' }
          selector: "Property[key.value='ease'][value.value='starSettle']",
          message:
            "starSettle（CD-T2FIX-1）已退役。{ 'ease': 'starSettle' } quoted key 形式同樣禁止。改用 'fluent-decel'。",
        },
        {
          // CD-T2FIX-3：SVG rail y2 屬性只能在 rails.js / breathing.js 內設定
          selector:
            "CallExpression[callee.property.name='setAttribute'][arguments.0.value='y2']",
          message:
            "SVG rail y2 屬性只能在 rails.js（setRailCoords）或 breathing.js（ticker follow）內設定，不在 animations.js 直接 setAttribute。",
        },
      ],
    },
  },

  // Group 5: motion-lab/constellation-host.js 完整規則集（supersedes Group 3）
  // 56b-T3：thin host 從 pages/clip-lab/main.js 搬遷至 pages/motion-lab/constellation-host.js
  // 包含：window.confirm guard + drawSVG/railDrawIn thin-host guard（CD-56B-8）
  // + hover addEventListener guard + BreathingManager 不禁（host 是合法建立者）
  {
    files: ["web/static/js/pages/motion-lab/constellation-host.js"],
    rules: {
      "no-restricted-syntax": [
        "error",
        SEL_WINDOW_CONFIRM,
        SEL_NO_UNLOAD_LISTENER,
        {
          selector: "Property[key.name='drawSVG']",
          message:
            "drawSVG 屬於核心層（shared/constellation/rails.js），禁止在 thin host constellation-host.js 的 GSAP property bag 直接使用。",
        },
        {
          selector: "Property[key.value='drawSVG']",
          message:
            "drawSVG 屬於核心層（shared/constellation/rails.js），禁止在 thin host constellation-host.js 直接使用（quoted key form）。",
        },
        {
          selector: "MemberExpression[property.name='drawSVG']",
          message:
            "drawSVG 屬於核心層，禁止在 thin host constellation-host.js 透過 member access 使用。",
        },
        {
          selector: "CallExpression[callee.name='railDrawIn']",
          message:
            "railDrawIn 是核心函式，thin host 只能呼叫 animations.js 的 play* 函式，不能直接呼叫 railDrawIn。",
        },
        {
          selector:
            "CallExpression[callee.property.name='addEventListener'][arguments.0.value=/^(mouseenter|mouseleave)$/]",
          message:
            "hover 互動走 Alpine x-on:mouseenter / x-on:mouseleave，禁止在 constellation-host.js 內使用 addEventListener('mouseenter'/'mouseleave')（CD-56B-T2 lint guard）。",
        },
        // Codex r1 P3 修正：constellation-host.js 也加 starSettle Literal ban（原 Group 6 ignores 此檔導致漏網）
        SEL_STARSETTLE_LITERAL,
        // 56c-T4fix7：filter: brightness() ban（host 內 hover dim 改 CSS var tween）
        SEL_FILTER_BRIGHTNESS,
        {
          // Codex r2 F2：y2 setAttribute ban（plan §11 / task card §9 契約）
          // Group 5 加 ban；Group 6 不加（catch-all 會打到 rails.js 自己的 railSweep）
          // 取捨：Group 6 暫不加，待 ESLint 有更精細 file scoping 機制再補
          selector:
            "CallExpression[callee.property.name='setAttribute'][arguments.0.value='y2']",
          message:
            "SVG rail y2 屬性只能在 rails.js（setRailCoords）或 breathing.js（ticker follow）內設定，不在 constellation-host.js 直接 setAttribute（CD-T2FIX-3）。",
        },
        {
          // T5 (CD-T5-5 / spec §4.3)：hover 不再呼叫 railSweep。引導線改由 strokeOpacity tween +
          // dust class swap 表達（T6）。railSweep 保留供 slip-through enter feedback（host onComplete 補呼叫）。
          // 兩個 selector 同時覆蓋：
          //   - Property 形式（Alpine data object literal shorthand method）
          //   - MethodDefinition 形式（ES class method，未來可能改寫）
          selector: [
            "MethodDefinition[key.name='onHoverEnter'] CallExpression[callee.name='railSweep']",
            "Property[key.name='onHoverEnter'] CallExpression[callee.name='railSweep']",
          ].join(', '),
          message:
            "T5 決策（CD-T5-5 / spec §4.3）：hover 不再呼叫 railSweep()，引導線改由 strokeOpacity tween + dust class swap 表達（T6）。railSweep 保留供 slip-through enter 使用（host onComplete 補呼叫）。",
        },
        {
          // T6 (CD-T6-3 / spec §4.2 / §2.4)：hover guide 改用 strokeOpacity 0→0.10 tween（極淡引導線）。
          // railFocusPulse 把 strokeOpacity 拉到 0.85（粗線 + bright），是 T4fix「能量感脈衝」語義；
          // T6 是「rail 永遠不是主角」極淡引導線語義（spec §2.4），兩者互斥。
          // 兩個 selector 同時覆蓋（與 T5 railSweep ban 同形）：
          //   - Property 形式（Alpine data object literal shorthand method）
          //   - MethodDefinition 形式（ES class method，未來可能改寫）
          selector: [
            "MethodDefinition[key.name='onHoverEnter'] CallExpression[callee.name='railFocusPulse']",
            "Property[key.name='onHoverEnter'] CallExpression[callee.name='railFocusPulse']",
          ].join(', '),
          message:
            "T6 決策（CD-T6-3 / spec §4.2）：hover guide 改用 strokeOpacity 0→0.10 tween（極淡引導線），禁止在 onHoverEnter 呼叫 railFocusPulse()——後者把 strokeOpacity 拉到 0.85（粗線 + bright），不符 T6「rail 永遠不是主角」語義（spec §2.4）。",
        },
      ],
    },
  },

  // Group 5b (56c-T4)：showcase/state-similar.js 完整規則集（supersedes Group 3）
  // 56c clip mode 與 motion-lab Constellation tab 是雙 host：constellation-host.js 是
  // motion-lab sandbox 的 thin host；state-similar.js 是 showcase lightbox takeover 的 host。
  // 兩者都是合法的 BreathingManager 建立者（per-host lifecycle 持有原則，CD-56B-T2 同源延伸）。
  // 規則繼承 Group 6 base：window.confirm + Set.intersection（ES2025） + starSettle Literal
  // 但允許 new BreathingManager（host 持有 lifecycle）。
  {
    files: ["web/static/js/pages/showcase/state-similar.js"],
    rules: {
      "no-restricted-syntax": [
        "error",
        SEL_WINDOW_CONFIRM,
        SEL_NO_UNLOAD_LISTENER,
        SEL_STARSETTLE_LITERAL,
        // 56c-T4fix7：filter: brightness() ban（host 內 hover dim 改 CSS var tween）
        SEL_FILTER_BRIGHTNESS,
        {
          selector: "MemberExpression[property.name='intersection']",
          message:
            "Set.prototype.intersection 為 ES2025 API，尚未進入 OpenAver baseline。請改用 [...setA].filter(x => setB.has(x))。",
        },
      ],
    },
  },

  // Group 6: 其餘非 state/ 非 main.js 非 animations.js 非 breathing.js JS（supersedes Group 3）
  // 包含：window.confirm guard + BreathingManager 實例化禁令（CD-56B-T2）
  // + starSettle Literal ban（CD-T2FIX-1）：其他檔案完全不允許出現 'starSettle' 字串
  //   （animations.js 在 ignores 中，由 Group 4 Property selector 保護）
  //   （state-similar.js 在 ignores 中，由 Group 5b 完整覆寫並允許 new BreathingManager）
  // + closeSimilarMode 定義唯一性守衛（CD-56C-4）：state-similar.js 在 ignores 中（Group 5b 白名單）
  {
    files: ["web/static/js/**/*.js"],
    ignores: [
      "web/static/js/pages/**/state/**/*.js",
      "web/static/js/pages/motion-lab/constellation-host.js",
      "web/static/js/pages/showcase/state-similar.js",
      "web/static/js/shared/constellation/animations.js",
      "web/static/js/shared/constellation/breathing.js",
    ],
    rules: {
      "no-restricted-syntax": [
        "error",
        SEL_WINDOW_CONFIRM,
        SEL_NO_UNLOAD_LISTENER,
        SEL_BREATHING_MANAGER_NEW,
        SEL_STARSETTLE_LITERAL,
        SEL_NO_PLAYTOICON,
        {
          // CD-T2FIX-3：Set.prototype.intersection 為 ES2025 API，尚未進入 OpenAver baseline
          // Codex r2 F1：改用 MemberExpression[property.name='intersection'] 以同時捕捉
          // setA.intersection(setB)（object 為 Identifier）和 new Set().intersection(...)
          selector: "MemberExpression[property.name='intersection']",
          message:
            "Set.prototype.intersection 為 ES2025 API，尚未進入 OpenAver baseline。請改用 [...setA].filter(x => setB.has(x))。",
        },
        {
          selector: [
            "Property[key.name='closeSimilarMode']",
            "MethodDefinition[key.name='closeSimilarMode']",
          ].join(', '),
          message:
            "closeSimilarMode 只能在 state-similar.js 定義（CD-56C-4 單一定義原則）。其他檔案可呼叫 this.closeSimilarMode()，但不可定義同名 method。",
        },
        // ── spec-85 T3 variant 移除防回歸守衛（CD-85-3）────────────────
        {
          selector: "Identifier[name='variantIdx']",
          message: "variantIdx（javbus variant 維度）已隨 spec-85 全棧移除。switch-source 只在 source 維度輪替，禁止重新引入 variant 維度。",
        },
        {
          selector: "MemberExpression[property.name='_all_variant_ids']",
          message: "_all_variant_ids 後端已不再填（spec-85 T1a），前端讀取是死碼，禁止重新引入。",
        },
        {
          selector: "Literal[value='_all_variant_ids']",
          message: "_all_variant_ids 後端已不再填（spec-85 T1a），前端讀取是死碼，禁止重新引入（bracket/字面量形式）。",
        },
        {
          selector: "MemberExpression[property.name='_variant_id']",
          message: "_variant_id（javbus variant 欄位）已隨 spec-85 移除，禁止重新引入。",
        },
        {
          selector: "Literal[value='_variant_id']",
          message: "_variant_id（javbus variant 欄位）已隨 spec-85 移除，禁止重新引入（bracket/字面量形式）。",
        },
        {
          selector: "TemplateElement[value.cooked=/variant_id=/]",
          message: "variant_id= fetch param 的 route 端已在 spec-85 T2 移除，前端不應再送此參數。",
        },
      ],
    },
  },

  // Group 7b (feature/95 T7 · CD-95a-10〔2〕): settings JS — 禁硬編變數陣列復活
  //   （命名區變數集收斂為 SSOT `/api/config/format-variables`，前端不得再 fork
  //   `[{ name:'{num}', ... }, ...]` 硬編清單）。
  // ⚠ flat config 同 rule 後者整段 replace：此 group 的 no-restricted-syntax 會**取代**
  //   上方廣域 `web/static/js/**/*.js` group（含 window.confirm / unload / BreathingManager /
  //   starSettle / playToIcon / Set.intersection / closeSimilarMode / 5× variant bans）對
  //   settings JS 的規則。故必須**完整重述**該清單 + 疊加新 selector，否則 settings JS 繞過全部。
  //   （與 Group 8 對 Group 1 的重述同一 flat-config 陷阱；mutation 自驗見 test_frontend_lint。）
  {
    files: ["web/static/js/pages/settings/**/*.js"],
    rules: {
      "no-restricted-syntax": [
        "error",
        // ── 重述廣域 group（web/static/js/**/*.js）全部 selector（不可省）──
        SEL_WINDOW_CONFIRM,
        SEL_NO_UNLOAD_LISTENER,
        SEL_BREATHING_MANAGER_NEW,
        SEL_STARSETTLE_LITERAL,
        SEL_NO_PLAYTOICON,
        {
          selector: "MemberExpression[property.name='intersection']",
          message:
            "Set.prototype.intersection 為 ES2025 API，尚未進入 OpenAver baseline。請改用 [...setA].filter(x => setB.has(x))。",
        },
        {
          selector: [
            "Property[key.name='closeSimilarMode']",
            "MethodDefinition[key.name='closeSimilarMode']",
          ].join(', '),
          message:
            "closeSimilarMode 只能在 state-similar.js 定義（CD-56C-4 單一定義原則）。其他檔案可呼叫 this.closeSimilarMode()，但不可定義同名 method。",
        },
        {
          selector: "Identifier[name='variantIdx']",
          message: "variantIdx（javbus variant 維度）已隨 spec-85 全棧移除。switch-source 只在 source 維度輪替，禁止重新引入 variant 維度。",
        },
        {
          selector: "MemberExpression[property.name='_all_variant_ids']",
          message: "_all_variant_ids 後端已不再填（spec-85 T1a），前端讀取是死碼，禁止重新引入。",
        },
        {
          selector: "Literal[value='_all_variant_ids']",
          message: "_all_variant_ids 後端已不再填（spec-85 T1a），前端讀取是死碼，禁止重新引入（bracket/字面量形式）。",
        },
        {
          selector: "MemberExpression[property.name='_variant_id']",
          message: "_variant_id（javbus variant 欄位）已隨 spec-85 移除，禁止重新引入。",
        },
        {
          selector: "Literal[value='_variant_id']",
          message: "_variant_id（javbus variant 欄位）已隨 spec-85 移除，禁止重新引入（bracket/字面量形式）。",
        },
        {
          selector: "TemplateElement[value.cooked=/variant_id=/]",
          message: "variant_id= fetch param 的 route 端已在 spec-85 T2 移除，前端不應再送此參數。",
        },
        // ── 疊加 T7 新 selector：禁硬編 `{ name:'{token}' }` 變數物件陣列（CD-95a-10〔2〕）──
        // 只匹配 name 值為 `{字母}` 形（不誤傷 placeholder 樣板字串 / 一般 name 屬性）。
        {
          selector: "Property[key.name='name'][value.value=/^\\{[a-zA-Z]+\\}$/]",
          message:
            "命名區變數集已收斂為 SSOT `/api/config/format-variables`（CD-95a-8/10）。禁止在 settings JS 硬編 `[{ name:'{num}', ... }]` 變數清單復活；label 走 i18n _labelFor、whitelist 走 _whitelistFor。",
        },
      ],
    },
  },

  // Group 8 (TASK-80): persistence.js — 禁 playGridSettle 呼叫（supersedes Group 1，重述清單 + 疊加）
  // restore 返回既有 grid 應即時呈現，不重播逐行 scale stagger；
  // fresh-search 的合法 playGridSettle 呼叫在 search-flow.js（同目錄，故不能加在 Group 1 glob）。
  // flat config 同 rule 後者整段 replace：此 block 必須重述 Group 1 全部 6 個 selector 再疊加新的。
  {
    files: ["web/static/js/pages/search/state/persistence.js"],
    rules: {
      "no-restricted-syntax": [
        "error",
        SEL_CREATE_ELEMENT,
        SEL_SHOW_MODAL,
        SEL_WINDOW_CONFIRM,
        SEL_NO_UNLOAD_LISTENER,
        SEL_BREATHING_MANAGER_NEW,
        SEL_STARSETTLE_LITERAL,
        {
          selector: "CallExpression[callee.property.name='playGridSettle']",
          message:
            "TASK-80：persistence.js restore 禁呼叫 playGridSettle（返回既有 grid 即時呈現、不重播 scale stagger）。" +
            "fresh-search 入口在 search-flow.js。",
        },
      ],
    },
  },

  // Group 7 (62c-1 / 62c-3): shared/state-rescrape.js — search 分支禁 fallbackSearch（CD-62-11 負向守衛）
  // + switch-source 分支禁污染結果列（CD-62-11，62c-3）。
  // search 入口整包贏必須走 advancedSearch(source)（帶 source）；fallbackSearch（search-flow.js）
  // 簽名 (query, savedRequestId) 無 source，誤接會丟失「指定來源整包覆寫」語義（US5）。
  // 此 group 最後 match state-rescrape.js（supersedes Group 6），故重述繼承的共用 selector
  // （SEL_WINDOW_CONFIRM / SEL_BREATHING_MANAGER_NEW / SEL_STARSETTLE_LITERAL
  //  + Set.intersection ES2025 ban + closeSimilarMode 定義唯一性守衛，勿靜默丟失上游守衛）。
  // Codex 62c-3 P3：flat config 同 rule 後者整段 replace（不 merge），故 Group 7 必須是
  // Group 6 完整 selector 的超集，再疊加 62c 自己的負向 rule。
  //
  // 62c-3 switch-source 分支負向：禁 advancedSearch( / fallbackSearch( / searchResults =。
  // 注意 search 分支「合法」使用 advancedSearch( + this.searchQuery，故不能 file-wide ban；
  // 改 AST-scope 到 IfStatement[test.right.value='switch-source']（switch-source 分支 if-block）的後代。
  // switch-source 入口只替換捕捉的當前卡 slot（t.arr[t.idx] = variant），絕不走 US5 整包重設路徑。
  {
    files: ["web/static/js/shared/state-rescrape.js"],
    rules: {
      "no-restricted-syntax": [
        "error",
        SEL_WINDOW_CONFIRM,
        SEL_NO_UNLOAD_LISTENER,
        SEL_BREATHING_MANAGER_NEW,
        SEL_STARSETTLE_LITERAL,
        {
          // Group 6 繼承：Set.prototype.intersection 為 ES2025 API，尚未進入 OpenAver baseline
          // （Codex 62c-3 P3：Group 7 replace Group 6，須重述以免 state-rescrape.js 繞過此 ban）
          selector: "MemberExpression[property.name='intersection']",
          message:
            "Set.prototype.intersection 為 ES2025 API，尚未進入 OpenAver baseline。請改用 [...setA].filter(x => setB.has(x))。",
        },
        {
          // Group 6 繼承：closeSimilarMode 定義唯一性守衛（CD-56C-4）
          // （Codex 62c-3 P3：Group 7 replace Group 6，須重述以免 state-rescrape.js 繞過此 guard）
          selector: [
            "Property[key.name='closeSimilarMode']",
            "MethodDefinition[key.name='closeSimilarMode']",
          ].join(', '),
          message:
            "closeSimilarMode 只能在 state-similar.js 定義（CD-56C-4 單一定義原則）。其他檔案可呼叫 this.closeSimilarMode()，但不可定義同名 method。",
        },
        {
          selector: "CallExpression[callee.property.name='fallbackSearch']",
          message:
            "62c-1：state-rescrape.js search 分支禁呼叫 fallbackSearch（無 source 參數）。" +
            "進階搜尋整包贏須走 this.advancedSearch(source)（帶 source 整包覆寫，spec US5）。",
        },
        {
          selector:
            "IfStatement[test.right.value='switch-source'] CallExpression[callee.property.name='advancedSearch']",
          message:
            "62c-3：switch-source 分支禁呼叫 advancedSearch（US5 整包重設路徑，會污染結果列）。" +
            "switch-source 只替換捕捉的當前卡 slot（t.arr[t.idx] = variant），不重設 searchResults / currentIndex。",
        },
        {
          selector:
            "IfStatement[test.right.value='switch-source'] CallExpression[callee.property.name='fallbackSearch']",
          message:
            "62c-3：switch-source 分支禁呼叫 fallbackSearch（US5 整包重設路徑，會污染結果列）。",
        },
        {
          selector:
            "IfStatement[test.right.value='switch-source'] AssignmentExpression[left.property.name='searchResults']",
          message:
            "62c-3：switch-source 分支禁賦值 this.searchResults（US5 整包重設路徑，會污染結果列）。" +
            "只替換捕捉的 slot（t.arr[t.idx] = variant），結果列陣列 identity / currentIndex 不變。",
        },
        {
          // CD-86-13: confirm 取選定版本 URL 一律用 rescrapePreview.url
          selector: "MemberExpression[property.name='detail_url'][object.property.name='rescrapePreview']",
          message:
            "CD-86-13: confirm 取選定版本 URL 一律用 rescrapePreview.url（detail_url 為 undefined，to_legacy_dict 輸出 key 是 url）。禁止 rescrapePreview.detail_url。",
        },
        {
          // CD-86-14: search 採用分支禁 inline this.searchResults = 賦值（強制走 _commitSearchResults helper）
          selector:
            "IfStatement[test.right.value='search'] AssignmentExpression[left.property.name='searchResults']",
          message:
            "CD-86-14: search 採用分支禁止 inline 賦值 this.searchResults（會遺漏 pageState/listMode/checkLocalStatus/actressProfile 等）。改呼叫 this._commitSearchResults(...)。",
        },
      ],
    },
  },
];
