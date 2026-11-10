/**
 * resolution-tier.js — 解析度等級表的前端鏡像（TASK-198a-T4／CD-198a-10）
 *
 * 只放等級名陣列與 tierRank；門檻（寬高 → 等級）只在後端 core/media_probe.py。
 * 陣列必須維持單行字面：tests/unit/frontend_contracts/test_contract_resolution_tiers.py
 * 用 regex 讀它，與後端 RESOLUTION_TIERS 逐項相等。
 */

export const RESOLUTION_TIERS = ['SD', 'HD', 'FHD', '2K', '4K', '8K'];

/** 等級名 → 索引；null／缺鍵／未知字串 → -1（呼叫端必須先確認 >= 0 才比較）。 */
export function tierRank(label) {
    if (typeof label !== 'string') return -1;
    return RESOLUTION_TIERS.indexOf(label);
}
