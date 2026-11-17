import { pickTierName as tierNameOf, pickTierRank as tierRankOf } from '@/shared/pick-tier.js';

export function statePickTier() {
    return {
        pickTierName(rating) {
            return tierNameOf(rating);
        },
        pickStarAria(rating) {
            var rank = tierRankOf(rating);
            if (rank === 0) return window.t('showcase.pick.add_aria');
            if (rank === 1) return window.t('showcase.pick.remove_aria');
            if (rank === 3) return window.t('showcase.pick.next_aria', { tier: window.t('showcase.pick.tier.gold'), next: window.t('showcase.pick.tier.silver') });
            return window.t('showcase.pick.next_aria', { tier: window.t('showcase.pick.tier.silver'), next: window.t('showcase.pick.tier.bronze') });
        },
    };
}
