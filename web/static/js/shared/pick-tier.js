/**
 * pick-tier.js — 精選等級表的前端鏡像（TASK-201-T3／CD-201-4）
 *
 * 只放等級名陣列與 rank／name／next／matcher；編碼同後端 core/pick_tier.py。
 * 陣列必須維持單行字面：tests/unit/frontend_contracts/test_contract_pick_tiers.py
 * 用 regex 讀它，與後端 PICK_TIERS 逐項相等。
 */

export const PICK_TIERS = ['bronze', 'silver', 'gold'];

export const PICK_OPS = ['>=', '=', '<='];

export function pickTierRank(v) {
    return Math.min(3, Math.max(0, Math.trunc(Number(v) || 0)));
}

export function pickTierName(v) {
    var rank = pickTierRank(v);
    if (rank === 0) return null;
    return PICK_TIERS[rank - 1];
}

export function nextPickValue(v) {
    var rank = pickTierRank(v);
    return rank === 0 ? 3 : rank - 1;
}

export function matchesPickPill(video, pill) {
    var have = pickTierRank(video && video.user_rating);
    if (have === 0) return false;
    if (pill.value !== '1' && pill.value !== '2' && pill.value !== '3') return false;
    var op = pill.op === undefined ? '>=' : pill.op;
    if (op !== '>=' && op !== '=' && op !== '<=') return false;
    var need = Number(pill.value);
    if (op === '=') return have === need;
    return op === '<=' ? have <= need : have >= need;
}
