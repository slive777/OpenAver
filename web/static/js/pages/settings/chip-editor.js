// 命名區膠囊編輯器（feature/95 Part A）。
//
// 本檔分兩層（CLAUDE.md lint 守衛規則：演算法正確性走 node:test、結構防 fork 走 ESLint）：
//   1. 純函式 tokenize / serializeTokens —— 無 DOM，可被 node:test import（本 T3）。
//   2. ChipEditor class —— contentEditable 非受控 widget（T4 append）。
//
// ⚠ module top-level 不得碰 `document`/`window`（否則 node --test import 會炸）；
//   DOM 只在 class 方法內觸碰。tokenize/serializeTokens 皆為純函式。

'use strict';

/**
 * 全函數 tokenizer（D-A3 / CD-95a-4）：任何字串 → token model 陣列，永不拋錯。
 *
 * 候選 regex `\{[a-zA-Z]+\}`；只有**精確匹配** whitelist 的 `{name}` 轉膠囊（chip），
 * 其餘一律字面（text）——未知 token（`{studio}`）、缺括號（`{title`）、字面大括號
 * （`{`、`}`、`{123}`）都保留原樣。whitelist 由呼叫端注入（CD-95a-10〔2〕：不硬編 token）。
 *
 * @param {string} str
 * @param {Set<string>} whitelist  形如 `new Set(['{num}', '{title}', ...])`（含大括號）
 * @returns {Array<{t:'chip'|'text', v:string}>}
 */
export function tokenize(str, whitelist) {
  const out = [];
  // 每次呼叫新建 regex，避免共享 lastIndex 造成有狀態 bug
  const re = /\{[a-zA-Z]+\}/g;
  let last = 0;
  let m;
  while ((m = re.exec(str)) !== null) {
    if (m.index > last) out.push({ t: 'text', v: str.slice(last, m.index) });
    if (whitelist.has(m[0])) out.push({ t: 'chip', v: m[0] });
    else out.push({ t: 'text', v: m[0] });  // 未知 token 保留字面
    last = re.lastIndex;
  }
  if (last < str.length) out.push({ t: 'text', v: str.slice(last) });
  return out;
}

/**
 * 純 serializer（CD-95a-13，**單一序列化真理**）：token model → 字串。
 *
 * chip 的 `v` 即完整 `{token}` 字串、text 的 `v` 即字面，故兩者皆取 `v` 串接即還原原字串。
 * ChipEditor 的 DOM serialize 必須 delegate 到此函式（DOM → token model → serializeTokens），
 * 產出與本純函式逐字元相同，避免兩條 serialize 路徑漂移。
 *
 * @param {Array<{t:'chip'|'text', v:string}>} tokens
 * @returns {string}
 */
export function serializeTokens(tokens) {
  let out = '';
  for (const tk of tokens) out += tk.v;
  return out;
}

/**
 * 主動移除字串中「情境排除」的已知 token（D-A6 / CD-95a-6/8）。
 *
 * 用途：資料夾層級載入時剝除 `{suffix}`（檔名限定變數）——舊設定若在資料夾樣板放了
 * `{suffix}`，載入即精確移除、存檔後不再參與資料夾命名。候選 regex 與 `tokenize` 同
 * （`\{[a-zA-Z]+\}`），故只移除**精確等於** `excluded` 集合的整顆 token：
 *   - 未知 token（`{studio}`）、資料夾有效 token（`{num}`）、更長 token（`{mysuffix}`、
 *     `{suffixx}`）、缺括號（`{suffix`）、字面大括號 → 一律**保留**。
 *   - 殘留分隔符（`{num}-{suffix}` → `{num}-`）刻意不猜、不清（對齊 U-A2 誠實呈現）。
 * `excluded` 為空集合（如 SSOT fetch 失敗）→ 原字串不變（安全 no-op）。
 *
 * @param {string} str
 * @param {Set<string>} excluded  形如 `new Set(['{suffix}'])`
 * @returns {string}
 */
export function stripFolderExcludedTokens(str, excluded) {
  return String(str).replace(/\{[a-zA-Z]+\}/g, (m) => (excluded.has(m) ? '' : m));
}

/**
 * 資料夾層級載入正規化（CD-95a-7 / D-A6）：原始 `folder_layers` → 乾淨字串陣列（呼叫端配 id）。
 *
 * **順序關鍵（Codex PR P1）**：
 *   1. **先** `slice(0, 3)` 固定後端有效集合——organizer/readonly 皆 `layers[:3]`，第 4 層以上
 *      是從未建過資料夾的死資料，**不得被提升**成有效層。
 *   2. **再**於前 3 層內剝除資料夾排除 token（`{suffix}`，D-A6）並濾除剝空的層。
 *
 * 若先剝除+濾空再 slice，前導 `{suffix}`-only 層被丟會把原第 4 層以上提升進前 3，違反
 * 「只保留後端原先使用的前 3 層、功能零改變」。故 slice 必須在 strip/filter 之前。
 *
 * @param {string[]} rawLayers    config.scraper.folder_layers（外→內序）
 * @param {Set<string>} excluded  資料夾排除 token（如 `new Set(['{suffix}'])`）
 * @returns {string[]}  ≤3 個非空層值
 */
export function normalizeFolderLayers(rawLayers, excluded) {
  return rawLayers
    .slice(0, 3)                                             // 1. 固定後端有效集合（前 3），死資料不提升
    .map((v) => stripFolderExcludedTokens(v, excluded))     // 2. 前 3 層內剝除 {suffix}
    .filter((v) => v.trim() !== '');                        //    剝空的層丟棄
}

/**
 * ChipEditor —— contentEditable 非受控膠囊編輯器（CD-95a-9 整合模式，plan-95a T4）。
 *
 * 完全依賴注入（不硬編 token/label，配合 SSOT + CD-95a-10〔2〕）：
 *   new ChipEditor(hostEl, {
 *     whitelist,      // Set<string> 如 new Set(['{num}',...])，供 paste tokenize
 *     labelFor,       // (name)=>string 膠囊顯示標籤（序列化仍用完整 {token}）
 *     deleteAriaFor,  // (name)=>string 刪除鈕 aria-label（i18n；可省）
 *     onChange,       // ()=>void 每次編輯（IME 合成中延到 compositionend）
 *     placeholder,    // string 空狀態提示
 *   })
 *
 * 序列化真相 = 呼叫端的序列化字串；本 widget hydrate 單向（load→膠囊）、serialize 單向
 * （編輯→字串，delegate 純 serializeTokens，CD-95a-13）。不做雙向 x-model（避免 reactive
 * re-render 打斷游標）。
 */
export class ChipEditor {
  constructor(hostEl, opts = {}) {
    this.host = hostEl;
    this.whitelist = opts.whitelist || new Set();
    this.labelFor = opts.labelFor || ((name) => name);
    this.deleteAriaFor = opts.deleteAriaFor || (() => '');
    this.onChange = opts.onChange || (() => {});
    this._composing = false;
    this._drag = null;
    this._marker = null;
    this._markerRef = undefined;

    const ed = document.createElement('div');
    ed.className = 'chip-editor';
    ed.contentEditable = 'true';
    ed.spellcheck = false;
    ed.dataset.placeholder = opts.placeholder || '';
    this.ed = ed;
    hostEl.appendChild(ed);

    this._handlers = this._bind();
  }

  _emit() { this.onChange(); }

  _bind() {
    const ed = this.ed;
    const h = {
      input: () => { if (!this._composing) this._emit(); },
      compositionstart: () => { this._composing = true; },
      compositionend: () => { this._composing = false; this._emit(); },
      keydown: (e) => this._onKey(e),
      paste: (e) => this._onPaste(e),
      click: (e) => {
        const x = e.target.closest('.chip-x');
        if (x) {
          e.preventDefault();
          const chip = x.closest('.source-pill');
          if (chip) { chip.remove(); this._emit(); }
        }
      },
      dragstart: (e) => {
        const chip = e.target.closest('.source-pill');
        if (!chip) return;
        this._drag = chip;
        chip.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
        try { e.dataTransfer.setData('text/plain', chip.dataset.var); } catch { /* noop */ }
      },
      dragend: () => {
        if (this._drag) this._drag.classList.remove('dragging');
        this._clearMarker();
        this._drag = null;
      },
      dragover: (e) => {
        if (!this._drag) {
          // 外部拖入（非內部膠囊排序）：允許 drop，於 drop 時走 tokenize 消毒
          e.preventDefault();
          if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
          return;
        }
        e.preventDefault();
        if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
        this._showMarker(e.clientX, e.clientY);
      },
      drop: (e) => {
        if (!this._drag) {
          // 外部拖入：擋掉 contentEditable 原生 raw 插入，改走 tokenize（CD-95a-4 消毒邊界，
          // 與 paste 同一 invariant）。非文字（檔案/HTML）→ 擋原生插入、不插入。
          e.preventDefault();
          const dt = e.dataTransfer;
          const text = dt ? dt.getData('text') : '';
          if (text) {
            this._insertAtPoint(e.clientX, e.clientY, this._buildFragment(tokenize(text, this.whitelist)));
            this._emit();
          }
          return;
        }
        e.preventDefault();
        const ref = this._markerRef;
        this._clearMarker();
        if (ref === undefined) ed.appendChild(this._drag);
        else ed.insertBefore(this._drag, ref);
        this._emit();
      },
    };
    for (const [type, fn] of Object.entries(h)) ed.addEventListener(type, fn);
    return h;
  }

  _onKey(e) {
    // IME 合成中：Enter 確認候選、Backspace 編輯候選，一律讓 IME 處理（勿攔）。
    if (e.isComposing) return;
    // 單行命名：Enter 不換行（CD-95a-9〔b〕）
    if (e.key === 'Enter') { e.preventDefault(); return; }
    if (e.key !== 'Backspace' && e.key !== 'Delete') return;
    const sel = window.getSelection();
    if (!sel.rangeCount || !sel.isCollapsed) return;
    const r = sel.getRangeAt(0);
    const target = e.key === 'Backspace' ? this._nodeBefore(r) : this._nodeAfter(r);
    if (target && target.nodeType === 1 && target.dataset && target.dataset.var) {
      e.preventDefault();
      target.remove();
      this._emit();
    }
  }

  _nodeBefore(r) {
    const { startContainer: c, startOffset: o } = r;
    if (c === this.ed) return o > 0 ? this.ed.childNodes[o - 1] : null;
    if (c.nodeType === 3 && o === 0) return c.previousSibling;
    return null;
  }

  _nodeAfter(r) {
    const { startContainer: c, startOffset: o } = r;
    if (c === this.ed) return this.ed.childNodes[o] || null;
    if (c.nodeType === 3 && o === c.textContent.length) return c.nextSibling;
    return null;
  }

  _onPaste(e) {
    e.preventDefault();
    const text = (e.clipboardData || window.clipboardData).getData('text');
    // 貼上自動 token 化已知變數、未知 {...} 留字面（CD-95a-4）
    this._insertAtCaret(this._buildFragment(tokenize(text, this.whitelist)));
    this._emit();
  }

  _makeChip(varName) {
    const c = document.createElement('span');
    c.className = 'source-pill source-pill--chip';
    c.contentEditable = 'false';
    c.setAttribute('draggable', 'true');
    c.dataset.var = varName;
    c.dataset.enabled = 'true';  // canonical accent 外觀
    const lab = document.createElement('span');
    lab.className = 'pill-name';
    lab.textContent = this.labelFor(varName);
    const x = document.createElement('button');
    x.className = 'chip-x';
    x.type = 'button';
    x.tabIndex = -1;
    x.textContent = '×';
    const aria = this.deleteAriaFor(varName);
    if (aria) x.setAttribute('aria-label', aria);
    c.appendChild(lab);
    c.appendChild(x);
    return c;
  }

  _buildFragment(tokens) {
    const frag = document.createDocumentFragment();
    for (const tk of tokens) {
      if (tk.t === 'chip') frag.appendChild(this._makeChip(tk.v));
      else if (tk.v) frag.appendChild(document.createTextNode(tk.v));
    }
    return frag;
  }

  _insertAtCaret(node) {
    const sel = window.getSelection();
    // 先讀既有游標（focus() 會把無游標的 contentEditable 重置到「開頭」，故須在 focus 前判斷）：
    // 有真實游標在編輯器內 → 用它；否則 focus 後退回「末端」append（非誤植開頭）。
    let r = null;
    if (sel.rangeCount && this.ed.contains(sel.getRangeAt(0).startContainer)) {
      r = sel.getRangeAt(0);
    }
    this.ed.focus();
    if (!r) {
      r = document.createRange();
      r.selectNodeContents(this.ed);
      r.collapse(false);
    }
    r.deleteContents();
    // node 可能是 DocumentFragment（nodeType 11，插入後 fragment 自身清空 → 用其 lastChild）
    // 或單一元素（用該元素本身）。取「插入後仍在流中的最後實體節點」以正確定位游標。
    const lastReal = node.nodeType === 11 ? node.lastChild : node;
    r.insertNode(node);
    if (lastReal) {
      const nr = document.createRange();
      nr.setStartAfter(lastReal);
      nr.collapse(true);
      sel.removeAllRanges();
      sel.addRange(nr);
    }
  }

  /** 於 (x,y) 放置游標後插入（外部拖入用）；點不在編輯器內時 _insertAtCaret 自退回末端。 */
  _insertAtPoint(x, y, node) {
    const r = this._caretRangeFromPoint(x, y);
    if (r && this.ed.contains(r.startContainer)) {
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(r);
    }
    this._insertAtCaret(node);
  }

  _caretRangeFromPoint(x, y) {
    if (document.caretRangeFromPoint) return document.caretRangeFromPoint(x, y);
    if (document.caretPositionFromPoint) {
      const pos = document.caretPositionFromPoint(x, y);
      if (pos) {
        const r = document.createRange();
        r.setStart(pos.offsetNode, pos.offset);
        r.collapse(true);
        return r;
      }
    }
    return null;
  }

  _showMarker(x, y) {
    this._clearMarker();
    const marker = document.createElement('span');
    marker.className = 'drop-marker';
    marker.dataset.marker = '1';
    const kids = Array.from(this.ed.childNodes)
      .filter((n) => n !== this._drag && !(n.dataset && n.dataset.marker));
    let ref = null;
    for (const k of kids) {
      if (k.nodeType !== 1) continue;  // 只用元素節點幾何當錨點
      const rect = k.getBoundingClientRect();
      const mid = rect.left + rect.width / 2;
      if (y < rect.top - 4) { ref = k; break; }
      if (y <= rect.bottom + 4 && x < mid) { ref = k; break; }
    }
    this._markerRef = ref === null ? undefined : ref;
    if (ref) this.ed.insertBefore(marker, ref);
    else this.ed.appendChild(marker);
    this._marker = marker;
  }

  _clearMarker() {
    if (this._marker) { this._marker.remove(); this._marker = null; }
    this._markerRef = undefined;
  }

  insertVar(varName) {
    // 走 fragment（與 paste 同一插入路徑）：_insertAtCaret 的游標定位以 fragment.lastChild
    // 為錨；直接傳單一膠囊會讓 lastChild 指到膠囊內部的 .chip-x → 下一顆插進膠囊內丟失。
    this._insertAtCaret(this._buildFragment([{ t: 'chip', v: varName }]));
    this._emit();
  }

  /** load → tokenize → 渲染膠囊（hydrate 單向）。不觸發 onChange（呼叫端 load 後自行同步）。 */
  load(str) {
    this.ed.innerHTML = '';
    this.ed.appendChild(this._buildFragment(tokenize(str || '', this.whitelist)));
  }

  /**
   * DOM → token model → 純 serializeTokens（CD-95a-13，唯一序列化真理，不自寫串接）。
   * 跳過 <br>（contentEditable 空殘留）與 drop-marker。
   */
  serialize() {
    const tokens = [];
    for (const n of this.ed.childNodes) {
      if (n.nodeType === 3) {
        tokens.push({ t: 'text', v: n.textContent });
      } else if (n.nodeType === 1 && n.dataset && n.dataset.var) {
        tokens.push({ t: 'chip', v: n.dataset.var });
      } else if (n.nodeType === 1 && n.tagName !== 'BR' && !(n.dataset && n.dataset.marker)) {
        tokens.push({ t: 'text', v: n.textContent });
      }
    }
    return serializeTokens(tokens);
  }

  get isEmpty() { return this.serialize().trim() === ''; }

  setDisabled(d) {
    this.ed.setAttribute('aria-disabled', d ? 'true' : 'false');
    this.ed.contentEditable = d ? 'false' : 'true';
  }

  /** 對稱 teardown（供 Alpine keyed x-for 換層清乾淨，CD-95a-12）。 */
  destroy() {
    if (this._handlers) {
      for (const [type, fn] of Object.entries(this._handlers)) {
        this.ed.removeEventListener(type, fn);
      }
      this._handlers = null;
    }
    this._clearMarker();
    if (this.ed && this.ed.parentNode) this.ed.remove();
    this.ed = null;
    this._drag = null;
  }
}
