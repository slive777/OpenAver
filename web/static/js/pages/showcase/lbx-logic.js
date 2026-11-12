/**
 * lbx-logic.js — 影片燈箱規格帶純函式（199a-T2）
 *
 * formatRuntime：實際片長（分鐘）→ h:mm。
 * bandParts：規格帶項目（等級 · 編碼 · 實際片長 · 大小）；缺的項目直接省略。
 * 只用相對 import（FE-GUARD-11）；本檔零 Alpine、零 window。
 */

export function formatRuntime(min) {
    const total = Math.round(Number(min));
    if (!Number.isFinite(total) || total < 1) return '';
    return Math.floor(total / 60) + ':' + String(total % 60).padStart(2, '0');
}

export function bandParts(video, { formatSize, formatRuntime }) {
    if (!video) return [];
    const parts = [];
    if (video.resolution_tier) parts.push({ id: 'tier', text: video.resolution_tier });
    if (video.media_codec) parts.push({ id: 'codec', text: video.media_codec });
    const runtime = formatRuntime(video.media_duration_min);
    if (runtime) parts.push({ id: 'runtime', text: runtime });
    if (video.size) parts.push({ id: 'size', text: formatSize(video.size) });
    return parts;
}

/**
 * placePop：浮層位置（199a-T3，CD-199a-4）。
 * mode 是「位置模式」：'below'＝錨點下緣＋gap；'inplace'＝錨點上緣−4（T4 的片名／原文才用）。
 * 恆不低於封面下緣＋4（浮層不蓋封面）；超出視窗底就上移；interactive（點開類）一律回 maxHeight（視窗底−top）讓內容長高時在浮層內捲，純閱讀類不內捲。
 * align：'left'（預設）左緣對齊錨點；'right' 右緣對齊錨點（⋯ 選單）。
 */
export function placePop({ anchorRect, coverBottom, vw, vh, popSize, mode, align = 'left', interactive = false, margin = 8, gap = 6 }) {
    const floor = coverBottom + 4;
    const bottomLimit = vh - margin;
    let top = mode === 'inplace' ? anchorRect.top - 4 : anchorRect.bottom + gap;
    top = Math.max(top, floor);
    if (top + popSize.h > bottomLimit) top = Math.max(floor, bottomLimit - popSize.h);
    // 可點類一律限高到視窗底（不只在當下內容超出時）：開啟後內容長高（如簡介翻譯完成）只會在浮層內捲，不會伸出視窗
    const maxHeight = interactive ? Math.max(0, bottomLimit - top) : undefined;
    const anchorX = align === 'right' ? anchorRect.right - popSize.w : anchorRect.left;
    const left = Math.min(Math.max(anchorX, margin), Math.max(margin, vw - popSize.w - margin));
    return { left, top, maxHeight };
}

/** isOutsidePop：pointerdown 的目標是否在浮層與其錨點之外（錨點內的點擊不算外面，免得「先收再重開」）。 */
export function isOutsidePop(target, panelEl, anchorSel) {
    if (!target || typeof target.closest !== 'function') return true;
    if (panelEl && panelEl.contains(target)) return false;
    return !target.closest(anchorSel);
}

/**
 * menuItems：⋯ 選單項目（199a-T4，CD-199a-11）。順序固定 samples → translate → rescrape → delete。
 * 沒有對應檔（hasPath 假）只剩 rescrape；有劇照不出 samples；翻譯條件不成立不出 translate。
 */
export function menuItems(video, { sampleCount, trVisible, hasPath }) {
    const items = [];
    if (hasPath && sampleCount === 0) items.push({ id: 'samples' });
    if (hasPath && trVisible) items.push({ id: 'translate' });
    items.push({ id: 'rescrape' });
    if (hasPath) items.push({ id: 'delete' });
    return items;
}

/** popPlacement：各 kind 的位置模式與水平對齊（199a-T4）。 */
export function popPlacement(kind) {
    if (kind === 'title' || kind === 'otitle') return { mode: 'inplace', align: 'left' };
    if (kind === 'actorCard') return { mode: 'below', align: 'left' };
    if (kind === 'menu') return { mode: 'below', align: 'right' };
    if (kind === 'info') return { mode: 'below', align: 'right' };
    return { mode: 'below', align: 'left' };
}

/** hasDistinctOtitle：有原文且與片名不同才畫第 2 列。 */
export function hasDistinctOtitle(video) {
    const o = String(video?.original_title || '').trim();
    return !!o && o !== String(video?.title || '').trim();
}

/**
 * fitActresses：第 3 列女優露出數（199a-T5，CD-199a-9）。最多 max 位、至少 min 位（不足人數時取人數）；
 * 放不下就逐位減少，有被收起的人時要多留「另有 N 位」那顆的寬度。輸入都是量到的寬度（px），純函式。
 */
export function fitActresses({ chipWidths, moreChipWidth, available, gap, max = 3, min = 1 }) {
    const n = chipWidths.length;
    let shown = Math.min(max, n);
    const floor = Math.min(min, n);
    for (; shown > floor; shown -= 1) {
        const used = chipWidths.slice(0, shown).reduce((a, w) => a + w, 0) + gap * (shown - 1);
        const more = shown < n ? moreChipWidth + gap : 0;
        if (used + more <= available) break;
    }
    return shown;
}

/**
 * fitChipRow：女優燈箱「別名＋資訊」單行 chips 的露出數（199b-T4，CD-199b-3）。
 * fitActresses 的 max＝全部數薄包裝；至少露 1 顆（min: 1），被收起的個數＝總數 − 露出數。
 */
export function fitChipRow({ chipWidths, moreChipWidth, available, gap }) {
    return fitActresses({ chipWidths, moreChipWidth, available, gap, max: chipWidths.length, min: 1 });
}

/** workInfoFields：作品資訊欄位（199a-T5，CD-199a-10）。空欄位不列；廠牌等於片商不重複列；來源片長 >0 才列。 */
export function workInfoFields(video, { releaseClickable = false } = {}) {
    if (!video) return [];
    const text = (v) => String(v ?? '').trim();
    const fields = [];
    if (text(video.number)) fields.push({ id: 'number', clickable: false });
    if (text(video.maker)) fields.push({ id: 'maker', clickable: true });
    if (text(video.label) && text(video.label) !== text(video.maker)) fields.push({ id: 'label', clickable: true });
    if (text(video.series)) fields.push({ id: 'series', clickable: true });
    if (text(video.director)) fields.push({ id: 'director', clickable: true });
    if (text(video.release_date)) fields.push({ id: 'release', clickable: !!releaseClickable });
    if (Number(video.source_duration) > 0) fields.push({ id: 'source_duration', clickable: false });
    return fields;
}

/**
 * fitSig：量測簽章（199a-T5，CD-199a-9）。簽章變 ⇒ 重量測；分隔字元避免欄位內容互相拼出相同字串。
 * favKey（199b-T1）：頭像表的鍵集合（頭像會讓 chip 變寬，頭像表一變就要重量）；空字串＝與舊版逐字相同。
 */
export function fitSig(video, adding, favKey = '') {
    if (!video) return '';
    const parts = [video.path || '', video.actresses || '', video.tags || '', (video.user_tags || []).join('\u0001'), adding ? '1' : '0'];
    if (favKey) parts.push(favKey);
    return parts.join('\u0000');
}

/** parseActresses：影片的女優名單（逗號分隔、去空白、去空字串）。 */
export function parseActresses(video) {
    return String(video?.actresses || '').split(',').map((s) => s.trim()).filter(Boolean);
}

/** orderFavoritesFirst：收藏者優先穩定分組（199b-T2，CD-199b-8）。isFav 為真的在前、其餘在後，兩群各自維持原順序；回傳新陣列。 */
export function orderFavoritesFirst(names, isFav) {
    const list = Array.isArray(names) ? names : [];
    return [...list.filter((n) => isFav(n)), ...list.filter((n) => !isFav(n))];
}

/**
 * actorFavsOf：影片女優頭像表（199b-T1，CD-199b-7）。key＝片上寫的名字（trim 過、同名只留一筆），
 * 只收 index.lookup(片上名字) 查得到的；name＝收藏名、photo_url＝當下的 a.photo_url（無照片為 ''）、
 * initial＝片上名字的第一個字（Array.from 處理代理對）。index 為空或沒有影片 ⇒ {}。純函式。
 */
export function actorFavsOf(video, index) {
    const out = {};
    if (!video || !index || typeof index.lookup !== 'function') return out;
    for (const name of parseActresses(video)) {
        if (Object.prototype.hasOwnProperty.call(out, name)) continue;
        const a = index.lookup(name);
        if (!a) continue;
        out[name] = { name: a.name, photo_url: a.photo_url || '', initial: Array.from(name)[0] || '' };
    }
    return out;
}

/**
 * 收藏女優小卡的內容（199b-T3，CD-199b-9）。純函式，t 由呼叫端注入（鏡射 bandParts 注入 formatSize）。
 * rows 依序 age／body／count，缺哪項整行不放進去。age 行看現在年齡（entity.age），沒生日就整行沒有；
 * ageAtRelease 只決定要不要附「拍這部時」。age／count 用 != null 判（count 的 0 是合法值），
 * height／cup／bwh 用 truthy 判——兩套缺值判定刻意不統一，鏡射 state-actress.js 的 _actressHoverInfo。
 */
export function actorCardLines(entity, { ageAtRelease, count, t }) {
    const rows = [];
    if (entity.age != null) {
        const parts = [];
        if (ageAtRelease != null) parts.push(t('showcase.lightbox.actor_card_age_release', { n: ageAtRelease }));
        parts.push(t('showcase.lightbox.actor_card_age_now', { n: entity.age }));
        rows.push({ id: 'age', text: parts.join(' · ') });
    }
    const body = [];
    if (entity.height) body.push(entity.height);
    if (entity.cup) body.push(entity.cup + t('search.unit.cup'));
    if (entity.bust && entity.waist && entity.hip) body.push(entity.bust + '-' + entity.waist + '-' + entity.hip);
    if (body.length) rows.push({ id: 'body', text: body.join(' · ') });
    if (count != null) rows.push({ id: 'count', text: t('showcase.lightbox.actor_card_count', { n: count }) });
    return { name: entity.name, photo: entity.photo_url || '', rows };
}

/**
 * fitTagRow：第 5 列標籤露出數（199a-T7，CD-199a-13）。使用者標籤先排（右區，上限＝列寬 × userMaxRatio，「＋」永遠先算進去），
 * 作品標籤用剩下的寬度；只要有任何標籤被收起（作品或使用者）就要為「+N」預留一顆寬度。輸入都是量到的寬度（px），純函式。
 */
export function fitTagRow({ userWidths, workWidths, plusWidth, moreChipWidth, rowWidth, gap, userMaxRatio = 0.5 }) {
    const budget = rowWidth * userMaxRatio;
    let userShown = 0;
    let right = plusWidth;
    for (; userShown < userWidths.length; userShown += 1) {
        const next = right + gap + userWidths[userShown];
        if (next > budget) break;
        right = next;
    }
    const userHidden = userWidths.length - userShown;
    const left = right > 0 ? rowWidth - right - gap : rowWidth;
    let workShown = workWidths.length;
    for (; workShown > 0; workShown -= 1) {
        const used = workWidths.slice(0, workShown).reduce((a, w) => a + w, 0) + gap * (workShown - 1);
        const more = workWidths.length - workShown + userHidden > 0 ? moreChipWidth + gap : 0;
        if (used + more <= left) break;
    }
    return { userShown, workShown };
}

/** parseWorkTags：影片的作品標籤（逗號分隔、去空白、去空字串）。 */
export function parseWorkTags(video) {
    return String(video?.tags || '').split(',').map((s) => s.trim()).filter(Boolean);
}
