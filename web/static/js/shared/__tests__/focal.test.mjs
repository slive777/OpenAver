// focal.test.mjs — parseFocal / focalObjectPosition / focalCellObjectPosition 純函式守衛
// （98b-T1 + 99a-T2）。零新依賴：Node 內建 node:test + node:assert/strict。跑：npm test（glob 涵蓋本檔）。
//
// 守 parseFocal 與 Python core/focal/detector.py::parse_focal 同粒度契約
// （falsy→null；恰 2 段；空段/非數/非有限→null；閉區間 [0,1]²；否則 null）。
// 守 focalObjectPosition 的 crop_mode gate（auto/manual）+ parse gate + deadzone gate（auto only）
// + .toFixed(2) 格式。
// 守 focalCellObjectPosition（99a-T2 §1 aspect-aware 公式）的 crop_mode gate / parse gate /
// a≤r gate / deadzone gate（auto only）/ clamp / by-construction 與遮罩幾何一致性。
// 含 mutation 案（越界 clamp、deadzone 判斷、a≤r 邊界）：放寬/拔掉必 RED。

import { test } from 'node:test';
import assert from 'node:assert/strict';

const { FOCAL_X_DEADZONE, parseFocal, focalObjectPosition, focalCellObjectPosition, clampMaskWinLeft } =
  await import('../focal.js');

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

// ── focalObjectPosition〔manual 分支〕（99a-T2 §1.5 spec §7 缺口補完）────────

test('focalObjectPosition〔manual 繞 deadzone〕crop_mode=manual + x=0.70（≥deadzone）→ 仍算出 raw x%（不 null）', () => {
  assert.equal(
    focalObjectPosition({ crop_mode: 'manual', auto_focal: '0.7000,0.5000' }),
    '70.00% center',
  );
});

test('focalObjectPosition〔manual + x<deadzone〕同 auto 一樣正常算（manual 只是繞 deadzone，非另一套公式）', () => {
  assert.equal(
    focalObjectPosition({ crop_mode: 'manual', auto_focal: '0.3820,0.5000' }),
    '38.20% center',
  );
});

test('focalObjectPosition〔manual 對照 auto〕同一 x=0.70：manual 非 null、auto null（deadzone 只對 auto 生效，mutation 抓點）', () => {
  const manualResult = focalObjectPosition({ crop_mode: 'manual', auto_focal: '0.7000,0.5000' });
  const autoResult = focalObjectPosition({ crop_mode: 'auto', auto_focal: '0.7000,0.5000' });
  assert.notEqual(manualResult, null);
  assert.equal(autoResult, null);
});

test('focalObjectPosition〔manual parse 失敗〕crop_mode=manual + auto_focal="garbage" → null', () => {
  assert.equal(focalObjectPosition({ crop_mode: 'manual', auto_focal: 'garbage' }), null);
});

test('focalObjectPosition〔unknown crop_mode〕crop_mode="default" 或未知字串仍回 null（gate 只認 auto/manual）', () => {
  assert.equal(focalObjectPosition({ crop_mode: 'default', auto_focal: '0.3820,0.5000' }), null);
  assert.equal(focalObjectPosition({ crop_mode: 'weird', auto_focal: '0.3820,0.5000' }), null);
});

// ── focalCellObjectPosition（99a-T2 §1 aspect-aware 公式 + §4 邊界表）─────────
//
// 公式（card §1，a>r 且未被 gate 擋下）：
//   objPos = clamp((x − r/(2a)) / (1 − r/a), 0, 1)
// 以下 REF_* 是測試內鏡射同一公式的獨立計算，用來：
//   (1) 產生非硬編的 expected 值（非簡單複製實作字面）
//   (2) 驗證「回傳值 ≠ raw x%」（mutation 抓點：若實作退化回 raw x%，這條必 RED）

function refCellFormula(x, a, r) {
  const v = r / a;
  const raw = (x - v / 2) / (1 - v);
  const clamped = Math.max(0, Math.min(1, raw));
  return `${(clamped * 100).toFixed(2)}% center`;
}

// y 分支獨立參考公式（CD-6 100b-T3；與 x 分支對稱互換：v=a/r 非 v=r/a，見 focal.js docstring 推導）。
function refCellFormulaY(y, a, r) {
  const v = a / r;
  const raw = (y - v / 2) / (1 - v);
  const clamped = Math.max(0, Math.min(1, raw));
  return `center ${(clamped * 100).toFixed(2)}%`;
}

const A = 1.49; // 典型 poster 圖片 naturalWidth/naturalHeight（16:9-ish demo 值，非 --poster-crop-ratio）
const R = 0.71; // --poster-crop-ratio 單一真理值（theme.css:561）
const AY = 0.50; // 典型女優窄圖 naturalWidth/naturalHeight（< --actress-crop-ratio 0.75，y 分支 demo 值）
const RY = 0.75; // --actress-crop-ratio 單一真理值（theme.css:569）

test('focalCellObjectPosition〔中間臉 no-op〕x=0.5 對稱 → 50.00%（與 a/r 無關，公式本身自我驗算）', () => {
  assert.equal(
    focalCellObjectPosition({ crop_mode: 'auto', auto_focal: '0.5000,0.5000' }, A, R),
    '50.00% center',
  );
  // 換一組不同 a/r，中間臉仍應 50%（對稱性不依賴 a/r 取值）
  assert.equal(
    focalCellObjectPosition({ crop_mode: 'auto', auto_focal: '0.5000,0.5000' }, 2.0, 0.5),
    '50.00% center',
  );
});

test('focalCellObjectPosition〔偏側 x 算對〕x=0.30, a=1.49, r=0.71 → 依公式算出，非等於 raw 30.00%（mutation 抓點）', () => {
  const result = focalCellObjectPosition({ crop_mode: 'auto', auto_focal: '0.3000,0.5000' }, A, R);
  assert.notEqual(result, '30.00% center');
  assert.equal(result, refCellFormula(0.30, A, R));
});

test('focalCellObjectPosition〔manual 繞 deadzone〕x=0.70（≥0.62 deadzone）, crop_mode=manual → 非 null，套公式算出', () => {
  const result = focalCellObjectPosition({ crop_mode: 'manual', auto_focal: '0.7000,0.5000' }, A, R);
  assert.notEqual(result, null);
  assert.equal(result, refCellFormula(0.70, A, R));
});

test('focalCellObjectPosition〔auto 套 deadzone〕同一 x=0.70/a/r，crop_mode=auto → null（deadzone 只對 auto 生效）', () => {
  const result = focalCellObjectPosition({ crop_mode: 'auto', auto_focal: '0.7000,0.5000' }, A, R);
  assert.equal(result, null);
});

test('focalCellObjectPosition〔a<r〕a=0.60 < r=0.71，顯式傳 axisMode="auto" → 走 y 分支（CD-6 100b-T3：不再是 null，改為垂直溢出修正；y=0.30 非對稱值，防退化回原值。Fix C：軸向收回為顯式參數，此案顯式傳 "auto"）', () => {
  const result = focalCellObjectPosition({ crop_mode: 'auto', auto_focal: '0.3000,0.3000' }, 0.60, 0.71, 'auto');
  assert.notEqual(result, null);
  assert.notEqual(result, '30.00% center'); // 未退化成 x 分支/raw 字面值
  assert.equal(result, refCellFormulaY(0.30, 0.60, 0.71));
});

test('focalCellObjectPosition〔偏側 y 算對〕y=0.30, a=0.50, r=0.75（女優窄圖典型值），顯式傳 axisMode="auto" → 依 y 公式算出，非等於 raw 30.00%（mutation 抓點，仿 x 分支 :165-169）', () => {
  const result = focalCellObjectPosition({ crop_mode: 'auto', auto_focal: '0.5000,0.3000' }, AY, RY, 'auto');
  assert.notEqual(result, 'center 30.00%');
  assert.equal(result, refCellFormulaY(0.30, AY, RY));
});

test('focalCellObjectPosition〔y 分支 manual 繞 deadzone〕a<r 且 crop_mode=manual，顯式傳 axisMode="auto" → 非 null，套 y 公式算出（deadzone 只鎖 x 軸，對 y 分支無感）', () => {
  const result = focalCellObjectPosition({ crop_mode: 'manual', auto_focal: '0.9000,0.3000' }, AY, RY, 'auto');
  assert.notEqual(result, null);
  assert.equal(result, refCellFormulaY(0.30, AY, RY));
});

test('focalCellObjectPosition〔y 分支 clamp 下界〕y=0（極端上），顯式傳 axisMode="auto" → clamp 進 0 → "center 0.00%"', () => {
  assert.equal(
    focalCellObjectPosition({ crop_mode: 'manual', auto_focal: '0.5000,0.0000' }, AY, RY, 'auto'),
    'center 0.00%',
  );
});

test('focalCellObjectPosition〔y 分支 clamp 上界〕y=1（極端下），顯式傳 axisMode="auto" → clamp 進 1 → "center 100.00%"', () => {
  assert.equal(
    focalCellObjectPosition({ crop_mode: 'manual', auto_focal: '0.5000,1.0000' }, AY, RY, 'auto'),
    'center 100.00%',
  );
});

// ── Fix C（Codex 本地 review）：影片零回歸——axisMode 預設='x'，共用函式無法自行判斷呼叫者 ──
// 病灶回顧：100b-T3 曾讓 focalCellObjectPosition 依 a/r 大小關係自判軸向，使所有影片 grid /
// similar / mobile（呼叫端未變、皆 3-arg 呼叫）意外吃到 Y 軸，且從未對窄比例影片封面做過
// CDP 驗證。收回為顯式 axisMode 參數、預設 'x'，與 fd48295a~1（100b-T3 之前）逐字等價。

test('focalCellObjectPosition〔axisMode 預設=x〕a<r（窄圖）+ 合法 focal + crop_mode=manual，不傳第 4 引數 → null（影片窄圖不吃 Y 軸，零回歸核心案）', () => {
  const result = focalCellObjectPosition({ crop_mode: 'manual', auto_focal: '0.5000,0.3000' }, 0.60, 0.71);
  assert.equal(result, null);
});

test('focalCellObjectPosition〔axisMode="x" 顯式 vs "auto" 對照〕同一組 a<r 輸入：顯式 "x" → null；顯式 "auto" → 非 null（鎖住預設值真的是 "x"，防有人把預設改成 "auto" 而測試照樣綠）', () => {
  const video = { crop_mode: 'manual', auto_focal: '0.5000,0.3000' };
  const xResult = focalCellObjectPosition(video, 0.60, 0.71, 'x');
  const autoResult = focalCellObjectPosition(video, 0.60, 0.71, 'auto');
  assert.equal(xResult, null);
  assert.notEqual(autoResult, null);
  assert.equal(autoResult, refCellFormulaY(0.30, 0.60, 0.71));
});

test('focalCellObjectPosition〔寬圖零分歧〕a>r 時 axisMode="x" 與 "auto" 輸出完全相同（鎖住寬圖零分歧——兩軸模式在 a>r 分支必須是同一段程式碼路徑）', () => {
  const video = { crop_mode: 'auto', auto_focal: '0.3000,0.5000' };
  const xResult = focalCellObjectPosition(video, A, R, 'x');
  const autoResult = focalCellObjectPosition(video, A, R, 'auto');
  assert.equal(xResult, autoResult);
  assert.equal(xResult, refCellFormula(0.30, A, R));
});

// ── CD-7〔空操作證明〕女優型資料（manual 模式）在 x 分支與 y 分支都不會被 deadzone 攔下 ──
// 不改 focal.js 的 deadzone 邏輯（:122 維持原樣）——本節只證明現有結構已保證「女優打不到它」。

test('CD-7〔空操作證明 x 分支〕crop_mode=manual, x=0.90（深入 deadzone 範圍）, a>r → 非 null（deadzone 結構上打不到女優）', () => {
  assert.notEqual(
    focalCellObjectPosition({ crop_mode: 'manual', auto_focal: '0.9000,0.5000' }, 1.49, 0.71),
    null,
  );
});

test('CD-7〔空操作證明 y 分支〕crop_mode=manual, y=0.90, a<r，顯式傳 axisMode="auto" → 非 null（軸向擴充不會意外新增 y 向 deadzone；Fix C 後 y 分支僅在 axisMode="auto" 時可達，故顯式傳）', () => {
  assert.notEqual(
    focalCellObjectPosition({ crop_mode: 'manual', auto_focal: '0.5000,0.9000' }, 0.50, 0.75, 'auto'),
    null,
  );
});

test('focalCellObjectPosition〔a==r〕a=0.71 == r=0.71 → null（CD-6：精確相等時兩分支 v 恆為 1、(1-v) 除以零，函式須顯式擋下，不可讓其中一支意外算出 NaN%）', () => {
  assert.equal(
    focalCellObjectPosition({ crop_mode: 'auto', auto_focal: '0.3000,0.5000' }, 0.71, 0.71),
    null,
  );
});

test('focalCellObjectPosition〔crop_mode gate〕default/undefined/null → null（a>r、parse 皆合法）', () => {
  assert.equal(
    focalCellObjectPosition({ crop_mode: 'default', auto_focal: '0.3000,0.5000' }, A, R),
    null,
  );
  assert.equal(
    focalCellObjectPosition({ crop_mode: undefined, auto_focal: '0.3000,0.5000' }, A, R),
    null,
  );
  assert.equal(
    focalCellObjectPosition({ crop_mode: null, auto_focal: '0.3000,0.5000' }, A, R),
    null,
  );
});

test('focalCellObjectPosition〔null-guard〕video 為 null/undefined → null 不拋（imperative 呼叫端可能回 undefined）', () => {
  assert.equal(focalCellObjectPosition(null, A, R), null);
  assert.equal(focalCellObjectPosition(undefined, A, R), null);
});

test('focalCellObjectPosition〔parseFocal 失敗〕auto_focal="garbage" / "" → null', () => {
  assert.equal(
    focalCellObjectPosition({ crop_mode: 'auto', auto_focal: 'garbage' }, A, R),
    null,
  );
  assert.equal(
    focalCellObjectPosition({ crop_mode: 'auto', auto_focal: '' }, A, R),
    null,
  );
});

test('focalCellObjectPosition〔clamp 下界〕x=0（極端左）→ clamp 進 0 → "0.00% center"', () => {
  assert.equal(
    focalCellObjectPosition({ crop_mode: 'manual', auto_focal: '0.0000,0.5000' }, A, R),
    '0.00% center',
  );
});

test('focalCellObjectPosition〔clamp 上界〕x=1（極端右）→ clamp 進 1 → "100.00% center"', () => {
  assert.equal(
    focalCellObjectPosition({ crop_mode: 'manual', auto_focal: '1.0000,0.5000' }, A, R),
    '100.00% center',
  );
});

// ── by-construction：小格 objPos% 換算的可見窗中心 應與遮罩換算的可見窗中心一致 ──
// 鏡射 state-lightbox.js:867-892 的像素空間算法（正規化 W=1），驗證兩套機制對同一
// (x, a, r) 算出「所見即所得」（不做像素級 CDP 驗收，計算層一致性即可，見 card §1）。

function maskWindowCenterFraction(x, a, r) {
  const W = 1;
  const H = W / a;
  const winW = Math.min(W, H * r);
  let left = x * W - winW / 2;
  left = Math.max(0, Math.min(left, W - winW));
  return (left + winW / 2) / W;
}

function cellWindowCenterFraction(objPosStr, a, r) {
  const p = parseFloat(objPosStr) / 100;
  const v = r / a;
  return p * (1 - v) + v / 2;
}

test('mask/cell 一致性〔by-construction〕x=0.30, a=1.49, r=0.71（未觸邊界 clamp）→ 兩套換算的可見窗中心重合', () => {
  const x = 0.30;
  const cellResult = focalCellObjectPosition({ crop_mode: 'auto', auto_focal: '0.3000,0.5000' }, A, R);
  const maskCenter = maskWindowCenterFraction(x, A, R);
  const cellCenter = cellWindowCenterFraction(cellResult, A, R);
  assert.ok(Math.abs(maskCenter - x) < 1e-9, 'mask 換算本身應等於 x（未觸邊界）');
  assert.ok(
    Math.abs(cellCenter - maskCenter) < 0.002,
    `cell 換算窗中心 ${cellCenter} 應與 mask 換算窗中心 ${maskCenter} 一致（容許 .toFixed(2) 捨入誤差）`,
  );
});

test('mask/cell 一致性〔by-construction〕x=0.62（deadzone 邊界但 manual 繞過）, a=1.49, r=0.71 → 兩套換算窗中心重合', () => {
  const x = 0.62;
  const cellResult = focalCellObjectPosition({ crop_mode: 'manual', auto_focal: '0.6200,0.5000' }, A, R);
  const maskCenter = maskWindowCenterFraction(x, A, R);
  const cellCenter = cellWindowCenterFraction(cellResult, A, R);
  assert.ok(
    Math.abs(cellCenter - maskCenter) < 0.002,
    `cell 換算窗中心 ${cellCenter} 應與 mask 換算窗中心 ${maskCenter} 一致`,
  );
});

// ── clampMaskWinLeft（99a Gemini P2：拖曳死區）────────────────────────────
// 語意：把窗左緣鉗進 [0, W - winW]。render / dragStart / onMove 三處共用。

test('clampMaskWinLeft〔界內〕原值不動', () => {
  assert.equal(clampMaskWinLeft(300, 1000, 444), 300);
});

test('clampMaskWinLeft〔超右界〕鉗到 W - winW', () => {
  assert.equal(clampMaskWinLeft(700, 1000, 444), 556);
});

test('clampMaskWinLeft〔超左界〕鉗到 0', () => {
  assert.equal(clampMaskWinLeft(-172, 1000, 444), 0);
});

test('clampMaskWinLeft〔邊界〕0 與 W-winW 為閉區間、不被鉗掉', () => {
  assert.equal(clampMaskWinLeft(0, 1000, 444), 0);
  assert.equal(clampMaskWinLeft(556, 1000, 444), 556);
});

// 死區本體：raw x 貼右緣（0.95）算出的起手左緣落在界外 → 必須被鉗回視覺位置，
// 否則反向拖曳要先吃掉 (unclamped - clamped) 差值才會動（此案約封面寬 17%）。
test('clampMaskWinLeft〔死區回歸〕raw x=0.95 的起手左緣鉗回視覺右界（差值即原死區寬）', () => {
  const W = 1000;
  const winW = 444;
  const unclamped = 0.95 * W - winW / 2;          // 728 — 界外
  const clamped = clampMaskWinLeft(unclamped, W, winW);
  assert.equal(clamped, W - winW);                 // 556 ＝ 視覺上窗子實際停的位置
  assert.ok(unclamped - clamped > 0.17 * W);       // 未修版的死區寬 > 封面 17%
});

test('clampMaskWinLeft〔死區回歸〕raw x=0.05 的起手左緣鉗回左界', () => {
  const W = 1000;
  const winW = 444;
  const clamped = clampMaskWinLeft(0.05 * W - winW / 2, W, winW);   // -172 → 0
  assert.equal(clamped, 0);
});
