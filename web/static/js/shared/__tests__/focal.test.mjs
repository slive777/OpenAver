// focal.test.mjs — parseFocal / focalObjectPosition 純函式守衛（98b-T1）。
// 零新依賴：Node 內建 node:test + node:assert/strict。跑：npm test（glob 涵蓋本檔）。
//
// 守 parseFocal 與 Python core/focal/detector.py::parse_focal 同粒度契約
// （falsy→null；恰 2 段；空段/非數/非有限→null；閉區間 [0,1]²；否則 null）。
// 守 focalObjectPosition 的 crop_mode gate + parse gate + deadzone gate + .toFixed(2) 格式。
// 含 2 mutation 案（越界 clamp、deadzone 判斷）：放寬/拔掉必 RED。

import { test } from 'node:test';
import assert from 'node:assert/strict';

const { FOCAL_X_DEADZONE, parseFocal, focalObjectPosition } = await import('../focal.js');

// ── parseFocal（鏡射 parse_focal 同粒度） ─────────────────────────────────

test('parseFocal〔happy〕"0.6231,0.4177" → {x,y}', () => {
  assert.deepEqual(parseFocal('0.6231,0.4177'), { x: 0.6231, y: 0.4177 });
});

test('parseFocal〔falsy〕"" / null / undefined → null', () => {
  assert.equal(parseFocal(''), null);
  assert.equal(parseFocal(null), null);
  assert.equal(parseFocal(undefined), null);
});

test('parseFocal〔x 越界〕"1.2,0.5" → null（mutation 目標：放寬 clamp 必 RED）', () => {
  assert.equal(parseFocal('1.2,0.5'), null);
});

test('parseFocal〔y 越界〕"0.5,1.5" → null', () => {
  assert.equal(parseFocal('0.5,1.5'), null);
});

test('parseFocal〔負值越界〕"-0.1,0.5" → null', () => {
  assert.equal(parseFocal('-0.1,0.5'), null);
});

test('parseFocal〔非數〕"a,b" → null', () => {
  assert.equal(parseFocal('a,b'), null);
});

test('parseFocal〔空段〕"0.5," → null（JS Number("")===0 陷阱須擋）', () => {
  assert.equal(parseFocal('0.5,'), null);
  assert.equal(parseFocal(',0.5'), null);
  assert.equal(parseFocal('0.5, '), null);  // 純空白段
});

test('parseFocal〔缺軸 1 段〕"0.5" → null', () => {
  assert.equal(parseFocal('0.5'), null);
});

test('parseFocal〔多軸 3 段〕"0.1,0.2,0.3" → null', () => {
  assert.equal(parseFocal('0.1,0.2,0.3'), null);
});

test('parseFocal〔非有限〕"Infinity,0.5" / "NaN,0.5" → null', () => {
  assert.equal(parseFocal('Infinity,0.5'), null);
  assert.equal(parseFocal('NaN,0.5'), null);
});

test('parseFocal〔邊界值合法〕"0.0,1.0" → {x:0,y:1}（閉區間含邊界）', () => {
  assert.deepEqual(parseFocal('0.0,1.0'), { x: 0, y: 1 });
});

// ── focalObjectPosition（crop_mode gate + parse + deadzone + 格式） ────────

test('focalObjectPosition〔default〕crop_mode=default + 任意 focal → null', () => {
  assert.equal(focalObjectPosition({ crop_mode: 'default', auto_focal: '0.3820,0.5000' }), null);
});

test('focalObjectPosition〔auto 無座標〕auto + auto_focal="" → null（退 baseline，零回歸關鍵案）', () => {
  assert.equal(focalObjectPosition({ crop_mode: 'auto', auto_focal: '' }), null);
});

test('focalObjectPosition〔auto + x<deadzone〕"0.3820,0.5000" → "38.20% center"（只 X、Y=center、.toFixed(2)）', () => {
  assert.equal(
    focalObjectPosition({ crop_mode: 'auto', auto_focal: '0.3820,0.5000' }),
    '38.20% center',
  );
});

test('focalObjectPosition〔deadzone〕auto + x=0.70 ≥ deadzone → null（mutation 目標：拔掉判斷必 RED）', () => {
  assert.equal(focalObjectPosition({ crop_mode: 'auto', auto_focal: '0.7000,0.5000' }), null);
});

test('focalObjectPosition〔parse 失敗〕auto + auto_focal="garbage" → null（退 baseline）', () => {
  assert.equal(focalObjectPosition({ crop_mode: 'auto', auto_focal: 'garbage' }), null);
});

test('focalObjectPosition〔null-guard〕null/undefined video → null 不拋（T3 imperative 呼叫端可能回 undefined）', () => {
  assert.equal(focalObjectPosition(null), null);
  assert.equal(focalObjectPosition(undefined), null);
});

test('FOCAL_X_DEADZONE 為 named 常數 0.62（暫定值）', () => {
  assert.equal(FOCAL_X_DEADZONE, 0.62);
});
