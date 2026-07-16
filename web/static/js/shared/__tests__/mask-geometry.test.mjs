// mask-geometry.test.mjs — G1 亮窗幾何 object-form 回歸鎖（100b-T2a）
// + CD-7 門檻純函式回歸鎖（100c-T1）。
// 零新依賴：Node 內建 node:test + node:assert/strict（純函式，無 DOM stub 需求）。
// 跑：npm test（glob 涵蓋本檔，package.json:13）。
//
// 100c-T3a：CD-2 軸向/凍結判定（computeMaskAxis）與 computeMaskWinGeometry 的 y 軸分支
// 已整段移除（T2 落地後 icon 只在橫向可拖幅度 ≥20% 的照片顯示，Y 軸/凍結分支結構上不可達，
// spec-100c §3.3 廢止）。本檔只保留 x 軸 G1/G5 案 + CD-7 門檻案，見 TASK-100c-T3a.md。
//
// 守的兩件事：
//   (a) G1：computeMaskWinGeometry 回傳**型別為 object 非 string**——99a-T5 事故本體
//       （`:style` 綁字串 → setAttribute('style') 整串覆寫 → 抹掉 x-show 的 display:none →
//       x-show 快取短路不自我修復 → 948 條全綠、功能完全不可用）。
//   (b) CD-7：computeMaskDragRoom 門檻判定——四類分支、真實邊界值的「在／不在門檻內」
//       歸屬、尺度無關、非有限值 fail-closed（不可回 NaN）。詳見下方「CD-7 門檻」一節。
//
// state-lightbox.js 為何不直接測：該檔用 `@/showcase/...` importmap alias（只有瀏覽器的
// base.html importmap 認得），plain Node 無法 import；故 G1/CD-7 的承重幾何抽至
// shared/mask-geometry.js（只用相對路徑 import），本檔直接驗純函式。

import { test } from 'node:test';
import assert from 'node:assert/strict';

const { computeMaskWinGeometry, computeMaskDragRoom, MASK_MIN_DRAG_ROOM } = await import('../mask-geometry.js');

const R_ACTRESS = 0.75;   // --actress-crop-ratio（女優 3/4 置中窗，CD-3）

// ── G1：computeMaskWinGeometry 恆回傳 object（99a-T5 回歸鎖）────────────────

test('🔴 G1〔x 軸 writer〕computeMaskWinGeometry 回傳 object 非 string（99a-T5：字串會抹掉 x-show 的 display:none）', () => {
  const s = computeMaskWinGeometry(1000, 600, R_ACTRESS, 0.5);
  assert.equal(typeof s, 'object', 'mutation：改回 CSS 字串模板 → 必 RED');
  assert.notEqual(s, null);
  assert.equal(typeof s.width, 'string');
  assert.equal(typeof s.height, 'string');
  assert.equal(typeof s.transform, 'string');
  assert.ok(s.transform.startsWith('translateX('), 'x 軸走 translateX');
});

test('computeMaskWinGeometry〔x 軸幾何〕1000×600, r=0.75, focalX=0.5 → 窗寬 450px、置中（left=275）', () => {
  const s = computeMaskWinGeometry(1000, 600, R_ACTRESS, 0.5);
  assert.equal(s.width, '450px', 'winW = min(1000, 600*0.75) = 450');
  assert.equal(s.height, '600px', 'x 軸窗高 = 整個 render 高');
  assert.equal(s.transform, 'translateX(275px)', 'left = 0.5*1000 - 450/2 = 275（3/4 置中基準）');
});

// ── G5：|| 吞掉合法 numeric 0（焦點貼邊是合法值）────────────────────────────

test('🔴 G5〔focalX=0 是合法值〕臉貼最左 → 窗鉗到 left=0，不可被當 falsy 退回右裁基準', () => {
  // G5（gotchas-frontend :236-264）：`focal.x || 0.5` 會把合法的 0 變成 0.5。
  // 本函式用 `!== null && !== undefined` 判斷（非 `||`），0 必須原樣通過。
  const s = computeMaskWinGeometry(1000, 600, R_ACTRESS, 0);
  // left = 0*1000 - 450/2 = -225 → clamp 進 [0, 550] → 0
  assert.equal(s.transform, 'translateX(0px)', 'focalX=0 → 窗貼左緣（clamp 下界）');
  // 對照：若 0 被吞掉走 fallback，left = W - winW = 550
  assert.notEqual(s.transform, 'translateX(550px)', '🔴 不可退回右裁基準（那是 focalX 為 null 時才有的行為）');
});

test('computeMaskWinGeometry〔focalX=null〕無焦點 → 右裁基準 left=W-winW（99a 既有語意，零回歸）', () => {
  const s = computeMaskWinGeometry(1000, 600, R_ACTRESS, null);
  assert.equal(s.transform, 'translateX(550px)', 'left = 1000-450 = 550（右裁基準 D2）');
});

// ── B-4：clampMaskWinLeft 數學軸無關（傳 (left,W,winW) 正確）─────────────────

test('B-4〔clamp 軸無關〕x 軸 focalX=1（臉貼最右）→ left 鉗進 [0, W-winW] 上界（既有行為對照）', () => {
  const s = computeMaskWinGeometry(1000, 600, R_ACTRESS, 1);
  assert.equal(s.transform, 'translateX(550px)', 'left 鉗進 W-winW=550');
});

// ── CD-7 門檻：computeMaskDragRoom ───────────────────────────────────────────

test('computeMaskDragRoom〔a < r 窄圖〕明里つむぎ a=0.7087 vs r=0.75 → 0（X 軸零溢出）', () => {
  assert.equal(computeMaskDragRoom(0.7087, R_ACTRESS), 0);
});

test('computeMaskDragRoom〔a === r 精準相等〕a=0.75 vs r=0.75 → 恆 0（不落入除法路徑算出殘值）', () => {
  assert.equal(computeMaskDragRoom(0.75, R_ACTRESS), 0, 'mutation：把 <= 改成 < → a===r 時會落入 1-r/a=0 的除法路徑，數值仍為 0 但分支覆蓋消失');
});

test('computeMaskDragRoom〔a > r 寬圖〕a=1.0 vs r=0.75 → 1 - r/a = 0.25（數值斷言，容浮點誤差）', () => {
  const result = computeMaskDragRoom(1.0, R_ACTRESS);
  assert.ok(Math.abs(result - 0.25) < 1e-6, `預期 ≈0.25，實得 ${result}`);
});

test('🔴 computeMaskDragRoom〔非有限值 fail-closed〕a=NaN/Infinity、r=NaN/0/-1 → 皆回傳 0，明確排除 NaN', () => {
  // DoD 1：不可只斷言 `=== 0`——0 和 NaN 在寬鬆比較下容易混淆，需顯式 assert.ok(!Number.isNaN(result))。
  for (const [a, r, label] of [
    [NaN, R_ACTRESS, 'a=NaN'],
    [Infinity, R_ACTRESS, 'a=Infinity'],
    [-Infinity, R_ACTRESS, 'a=-Infinity'],
    [1.0, NaN, 'r=NaN'],
    [1.0, 0, 'r=0'],
    [1.0, -1, 'r=-1'],
  ]) {
    const result = computeMaskDragRoom(a, r);
    assert.ok(!Number.isNaN(result), `${label}：result 不可為 NaN，實得 ${result}`);
    assert.equal(result, 0, `${label}：fail-closed 必回 0`);
  }
});

test('computeMaskDragRoom〔邊界真實值 + 門檻歸屬〕明里つむぎ a=0.7087 → 0（窄圖零溢出，遠低於門檻）', () => {
  const result = computeMaskDragRoom(0.7087, R_ACTRESS);
  assert.ok(Math.abs(result - 0) < 1e-6);
  assert.ok(result < MASK_MIN_DRAG_ROOM, '窄圖零溢出，不在門檻內');
});

test('computeMaskDragRoom〔邊界真實值 + 門檻歸屬〕gfriends a=0.8261 → ≈0.0921，斷言 < MASK_MIN_DRAG_ROOM（不在門檻內）', () => {
  const result = computeMaskDragRoom(0.8261, R_ACTRESS);
  assert.ok(Math.abs(result - 0.0921) < 1e-4, `預期 ≈0.0921，實得 ${result}`);
  // 🔴 門檻歸屬必須直接 import MASK_MIN_DRAG_ROOM 比較，不可硬編 0.20 字面
  // （否則 DoD 4 的 mutation：0.20→0.05 測不出——這條斷言在 mutation 下會單獨翻面 RED）。
  assert.ok(result < MASK_MIN_DRAG_ROOM, 'gfriends 不在門檻內（0.0921 < 0.20）');
});

test('computeMaskDragRoom〔邊界真實值 + 門檻歸屬〕方形 a=1.0 → 0.25，斷言 >= MASK_MIN_DRAG_ROOM（在門檻內）', () => {
  const result = computeMaskDragRoom(1.0, R_ACTRESS);
  assert.ok(Math.abs(result - 0.25) < 1e-6);
  assert.ok(result >= MASK_MIN_DRAG_ROOM, '方形在門檻內（0.25 >= 0.20）');
});

test('computeMaskDragRoom〔邊界真實值 + 門檻歸屬〕二葉エマ a=1.4986 → ≈0.4995，斷言 >= MASK_MIN_DRAG_ROOM（在門檻內）', () => {
  const result = computeMaskDragRoom(1.4986, R_ACTRESS);
  assert.ok(Math.abs(result - 0.4995) < 1e-4, `預期 ≈0.4995，實得 ${result}`);
  assert.ok(result >= MASK_MIN_DRAG_ROOM, '二葉エマ在門檻內（0.4995 >= 0.20）');
});

test('computeMaskDragRoom〔尺度無關〕同一 a 由不同 (W,H) 絕對值算出 → 回傳值相同（CD-7 承重）', () => {
  const aFromSmall = 1000 / 600;   // ≈1.6667
  const aFromLarge = 2000 / 1200;  // 同比值，不同絕對像素
  assert.equal(aFromSmall, aFromLarge, '兩組 (W,H) 算出相同比值（前提）');

  const resultSmall = computeMaskDragRoom(aFromSmall, R_ACTRESS);
  const resultLarge = computeMaskDragRoom(aFromLarge, R_ACTRESS);
  assert.equal(resultSmall, resultLarge, '🔴 同一 a 不同絕對 W/H 來源 → drag room 必須相同（尺度無關，簽名吃 a 的結構保證）');
});
