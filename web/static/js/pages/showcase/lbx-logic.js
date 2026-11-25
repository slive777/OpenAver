/**
 * lbx-logic.js — 影片燈箱規格帶純函式（199a-T2）
 *
 * formatRuntime：實際片長（分鐘）→ h:mm。
 * bandParts：規格帶項目（等級 · 編碼 · 實際片長 · 大小）；缺的項目直接省略。
 * 只用相對 import（FE-GUARD-11）；本檔零 Alpine、零 window。
 */

import { sameWork, sameNumber } from './work-versions.js';

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
 * 'right'＝卡片左緣貼錨點右側＋gap、上緣先對齊錨點上緣（寫真卡用；放不下往上挪但不低於封面下緣＋4，極矮才縮照片回 shrink）。
 * align：'left'（預設）左緣對齊錨點；'right' 右緣對齊錨點（⋯ 選單）。
 */
export function placePop({ anchorRect, coverBottom, vw, vh, popSize, mode, align = 'left', interactive = false, margin = 8, gap = 6, shrinkMax = 0 }) {
    const floor = coverBottom + 4;
    const bottomLimit = vh - margin;
    if (mode === 'right') {
        const cap = Number(shrinkMax);
        const limit = !Number.isFinite(cap) || cap < 0 ? 0 : cap;
        let top = Math.max(anchorRect.top, floor);
        const over = top + popSize.h - bottomLimit;
        if (over > 0) top = Math.max(floor, top - over);
        const left = Math.min(Math.max(anchorRect.right + gap, margin), Math.max(margin, vw - popSize.w - margin));
        const shrink = Math.min(limit, Math.max(0, top + popSize.h - bottomLimit));
        const maxHeight = top + popSize.h - shrink > bottomLimit ? Math.max(0, bottomLimit - top) : undefined;
        return { left, top, maxHeight, shrink };
    }
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
 * menuItems：⋯ 選單項目（199a-T4，CD-199a-11；200a-T3 加 focal）。
 * 順序固定 samples → translate → focal → advedit → rescrape → delete。
 * 沒有對應檔（hasPath 假）只剩 rescrape；有劇照不出 samples；翻譯條件不成立不出 translate；
 * canFocal 假（沿用版本／沒封面）不出 focal。
 */
export function menuItems(video, { sampleCount, trVisible, hasPath, canFocal }) {
    const items = [];
    if (hasPath && sampleCount === 0) items.push({ id: 'samples' });
    if (hasPath && trVisible) items.push({ id: 'translate' });
    if (hasPath && canFocal) items.push({ id: 'focal' });
    if (hasPath) items.push({ id: 'advedit' });
    items.push({ id: 'rescrape' });
    if (hasPath) items.push({ id: 'delete' });
    return items;
}

/** popPlacement：各 kind 的位置模式與水平對齊（199a-T4）。 */
export function popPlacement(kind) {
    if (kind === 'title' || kind === 'otitle') return { mode: 'inplace', align: 'left' };
    if (kind === 'actorCard') return { mode: 'right', align: 'left' };
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
 * fitActresses：第 3 列女優露出數（199a-T5，CD-199a-9）。預設不設上限、至少 min 位（不足人數時取人數）；
 * 放不下就逐位減少，有被收起的人時要多留「另有 N 位」那顆的寬度。輸入都是量到的寬度（px），純函式。
 */
export function fitActresses({ chipWidths, moreChipWidth, available, gap, max = Infinity, min = 1 }) {
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

/** sourceDurationPillShown：文字區「來源 xxx 分」膠囊是否顯示（207a-T1，CD-207a-9）。實際片長可信（≥1 分鐘且與來源差 ≤30%）時藏起避免重複；其餘照舊顯示。 */
export function sourceDurationPillShown(video) {
    if (!video) return false;
    if (!(Number(video.source_duration) > 0)) return false;
    if (formatRuntime(video.media_duration_min) === '') return true;
    return Math.abs(Number(video.media_duration_min) - Number(video.source_duration)) / Number(video.source_duration) > 0.3;
}

/**
 * fitSig：量測簽章（199a-T5，CD-199a-9）。簽章變 ⇒ 重量測；分隔字元避免欄位內容互相拼出相同字串。
 * favKey（199b-T1）：頭像表的鍵集合（頭像會讓 chip 變寬，頭像表一變就要重量）；空字串＝與舊版逐字相同。
 */
export function fitSig(video, adding, favKey = '') {
    if (!video) return '';
    const parts = [video.path || '', video.actresses || '', typeof video.tags_display === 'string' ? video.tags_display : (video.tags || ''), (video.user_tags || []).join('\u0001'), adding ? '1' : '0'];
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
 * initial＝片上名字的第一個字（Array.from 處理代理對），height／cup 缺值為 ''。index 為空或沒有影片 ⇒ {}。純函式。
 */
export function actorFavsOf(video, index) {
    const out = {};
    if (!video || !index || typeof index.lookup !== 'function') return out;
    for (const name of parseActresses(video)) {
        if (Object.prototype.hasOwnProperty.call(out, name)) continue;
        const a = index.lookup(name);
        if (!a) continue;
        out[name] = { name: a.name, photo_url: a.photo_url || '', initial: Array.from(name)[0] || '', height: a.height || '', cup: a.cup || '' };
    }
    return out;
}

export function actorSubSegments({ ageAtRelease, height, cup, t }) {
    const segs = [];
    if (ageAtRelease != null) segs.push({ id: 'age', text: ageAtRelease + t('showcase.unit.age_suffix') });
    if (height) segs.push({ id: 'height', text: height });
    if (cup) segs.push({ id: 'cup', text: cup + t('search.unit.cup') });
    return segs;
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

/** parseWorkTags：影片的作品標籤（逗號分隔、去空白、去空字串）。 */
export function parseWorkTags(video) {
    return String(video?.tags || '').split(',').map((s) => s.trim()).filter(Boolean);
}

// ---- 199b-T5：女優燈箱資料區最下面的縮圖排（批次標籤、下一批、發行日排序）----

/** batchLabel：目前這批「第幾到第幾／共幾」。回物件不回字串（顯示文字由 i18n 組）；to 要 clamp 到 total（最後一批不湊滿）。 */
export function batchLabel(start, size, total) {
    return { from: start + 1, to: Math.min(start + size, total), total };
}

/** nextBatchStart：下一批的起點；超過尾端繞回 0。 */
export function nextBatchStart(start, size, total) {
    return start + size < total ? start + size : 0;
}

/**
 * sortWorksByRelease：作品（預設版本物件）依發行日新→舊排，回新陣列、不改輸入。
 * 以 release_date 字串比較（YYYY-MM-DD 字串序＝時間序），空／缺值排最後；同值維持輸入順序（穩定）。
 */
export function sortWorksByRelease(works) {
    const key = (w) => (w && w.release_date) || '';
    return (works || []).slice().sort((a, b) => {
        const ka = key(a);
        const kb = key(b);
        if (ka === kb) return 0;
        if (!ka) return 1;
        if (!kb) return -1;
        return ka < kb ? 1 : -1;
    });
}

// 200a-T5：影片燈箱 ✓ 存檔提示。poster 缺欄位／null／非物件／未知 status 一律當 none。
export function focalSaveToast(poster) {
    const status = poster && poster.status;
    if (status === 'updated') return { key: 'showcase.lightbox.focal_saved_poster_updated', type: 'success' };
    if (status === 'failed') return { key: 'showcase.lightbox.focal_saved_poster_failed', type: 'error' };
    return { key: 'showcase.lightbox.focal_saved', type: 'success' };
}

export function formatHms(ms) {
    if (typeof ms !== 'number' || !Number.isFinite(ms) || ms < 1000) return '';
    const seconds = Math.floor(ms / 1000);
    return `${Math.floor(seconds / 3600)}:${String(Math.floor(seconds / 60) % 60).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
}
export function fileInfoParts(media, { formatSize, formatHms }) {
    if (!media || media.status !== 'ok') return [];
    const parts = [];
    const dimensions = media.width && media.height ? `${media.width}×${media.height}` : '';
    const tier = media.tier && dimensions ? `${media.tier}（${dimensions}）` : media.tier || dimensions;
    if (tier) parts.push({ id: 'tier', text: tier });
    if (media.codec) parts.push({ id: 'codec', text: media.codec });
    const duration = formatHms(media.duration_ms);
    if (duration) parts.push({ id: 'duration', text: duration });
    if (media.size) parts.push({ id: 'size', text: formatSize(media.size) });
    return parts;
}
export function mediaInfoText(media, opts) {
    if (media?.status === 'failed') return opts.t('showcase.adv_edit.files.media_failed');
    const parts = fileInfoParts(media, opts);
    return parts.length ? parts.map(p => p.text).join(' · ') : opts.t('showcase.adv_edit.files.media_none');
}
export function advEditOutputTarget(folders, nfoName) {
    if (!folders?.output) return '';
    const base = folders.output.replace(/\/+$/, '');
    return base + '/' + (nfoName ? encodeURIComponent(nfoName) : '');
}
function advEditPosterView(poster, imgFail) {
    if (!poster.visible) return 'hidden';
    if (poster.exists === true && !imgFail.poster) return 'img';
    if (poster.exists === null) return 'generic';
    if (poster.exists === false && poster.can_regen) return 'empty';
    return 'broken';
}
export function advEditFilesView(info, { borrowed = false, imgFail = {} } = {}) {
    const cover = info?.cover || {}, poster = info?.poster || {}, thumb = info?.thumb || {}, folders = info?.folders || {};
    const banner = info?.state === 'missing' ? (info.readonly ? 'missing_readonly' : 'missing') : info?.state === 'unreachable' ? 'unreachable' : '';
    return {
        banner,
        cover: cover.exists && !imgFail.cover ? 'img' : 'broken',
        poster: advEditPosterView(poster, imgFail),
        thumb: thumb.exists && !imgFail.thumb ? 'img' : thumb.mode === 'cache' && !thumb.exists && cover.exists ? 'pending' : 'broken',
        thumbChip: thumb.stale ? 'stale' : thumb.mode === 'cover' ? 'direct' : '',
        canRegenThumb: thumb.mode === 'cache' && !!cover.exists,
        canRegen: !!poster.can_regen && !borrowed,
        canReread: info?.state === 'ok',
        folders: info?.readonly ? { open: '', source: folders.source || '', output: advEditOutputTarget(folders, info.nfo?.name) } : { open: folders.source || '', source: '', output: '' },
    };
}
export function advEditActionNotice(kind, data, t) {
    if (kind === 'regen') {
        if (data?.success === true && data.poster?.status === 'updated') return { text: t('showcase.adv_edit.files.poster_updated'), type: 'success', reload: true };
        if (data?.success === true && data.poster?.status === 'skipped') return { text: t('showcase.adv_edit.files.poster_skipped'), type: 'info', reload: false };
        if (data?.success === false && data.error === 'generic_cover_name') return { text: t('showcase.adv_edit.files.poster_generic_cover'), type: 'warning', reload: false };
        if (data?.success === false && data.error === 'no_cover') return { text: t('showcase.adv_edit.files.poster_no_cover'), type: 'warning', reload: false };
        if (data?.success === false && data.error === 'readonly_output_not_current') return { text: t('showcase.adv_edit.files.poster_readonly_output'), type: 'warning', reload: false };
        if (data?.success === false && data.error === 'unreachable') return { text: t('showcase.adv_edit.files.unreachable'), type: 'warning', reload: false };
        return { text: t('showcase.adv_edit.files.poster_failed'), type: 'error', reload: false };
    }
    if (data?.success === true) {
        const status = data.status;
        if (status === 'ok') return { text: t('showcase.adv_edit.files.reread_done'), type: 'success', reload: true };
        if (status === 'failed') return { text: t('showcase.adv_edit.files.media_failed'), type: 'warning', reload: true };
        if (status === 'unreadable') return { text: t('showcase.adv_edit.files.reread_unreadable'), type: 'warning', reload: false };
        if (status === 'stale') return { text: t('showcase.adv_edit.files.reread_stale'), type: 'warning', reload: false };
        if (status === 'changed') return { text: data.readonly ? t('showcase.adv_edit.files.reread_changed_readonly') : t('showcase.adv_edit.files.reread_changed'), type: 'warning', reload: false };
        if (status === 'timeout') return { text: t('showcase.adv_edit.files.reread_timeout'), type: 'info', reload: false };
        if (status === 'unavailable') return { text: t('showcase.adv_edit.files.reread_unavailable'), type: 'warning', reload: false };
        if (status === 'skipped') return { text: t('showcase.adv_edit.files.reread_skipped'), type: 'info', reload: false };
    }
    if (data?.success === false && data.error === 'unreachable') return { text: t('showcase.adv_edit.files.unreachable'), type: 'warning', reload: false };
    return { text: t('showcase.adv_edit.files.reread_error'), type: 'error', reload: false };
}

export function advEditPathStem(p) {
    if (typeof p !== 'string' || !p) return '';
    const name = p.slice(Math.max(p.lastIndexOf('/'), p.lastIndexOf('\\')) + 1);
    const dot = name.lastIndexOf('.');
    return dot > 0 ? name.slice(0, dot) : name;
}
export function advEditRepathError(code, t) {
    if (code === 'confirm_required') return { text: '', confirm: true };
    const messages = {
        readonly: () => t('showcase.adv_edit.path.err_readonly'),
        unchanged: () => t('showcase.adv_edit.path.err_unchanged'),
        not_video: () => t('showcase.adv_edit.path.err_not_video'),
        not_found: () => t('showcase.adv_edit.path.err_not_found'),
        out_of_library: () => t('showcase.adv_edit.path.err_out_of_library'),
        already_in_library: () => t('showcase.adv_edit.path.err_already_in_library'),
        not_scannable: () => t('showcase.adv_edit.path.err_not_scannable'),
    };
    return { text: Object.hasOwn(messages, code) ? messages[code]() : t('showcase.adv_edit.path.err_generic'), confirm: false };
}
export function advEditUpdateNotice(data, t) {
    if (data?.success === true) {
        const pending = ['unreadable', 'stale', 'timeout'].includes(data.media_status);
        return { text: pending ? t('showcase.adv_edit.update.done_media_pending') : t('showcase.adv_edit.update.done'), type: pending ? 'warning' : 'success', reload: true, sync: false };
    }
    const messages = {
        unreachable: () => t('showcase.adv_edit.update.err_unreachable'),
        not_found: () => t('showcase.adv_edit.update.err_not_found'),
        no_nfo: () => t('showcase.adv_edit.update.err_no_nfo'),
        nfo_ambiguous: () => t('showcase.adv_edit.update.err_nfo_ambiguous'),
        nfo_unreadable: () => t('showcase.adv_edit.update.err_nfo_unreadable'),
    };
    const code = data?.success === false ? data.error : null;
    const known = Object.hasOwn(messages, code);
    return { text: known ? messages[code]() : t('showcase.adv_edit.update.err_generic'), type: known ? 'warning' : 'error', reload: false, sync: code === 'unreachable' || code === 'not_found' };
}

export function advEditThumbNotice(data, t) {
    if (data?.success === true) return { text: data.cover_changed ? t('showcase.adv_edit.files.thumb_regen_done_cover') : t('showcase.adv_edit.files.thumb_regen_done'), type: 'success', reload: true };
    if (data?.success === false && data.error === 'no_cover') return { text: t('showcase.adv_edit.files.thumb_no_cover'), type: 'warning', reload: false };
    if (data?.success === false && data.error === 'unreachable') return { text: t('showcase.adv_edit.files.unreachable'), type: 'warning', reload: false };
    return { text: t('showcase.adv_edit.files.thumb_failed'), type: 'error', reload: false };
}
export function ghostOnClose({ placed, immediate, prefersReducedMotion }) {
    return !!placed && !immediate && !prefersReducedMotion;
}

export function coverSwapPlan({ hadCover, toPhoto, prefersReducedMotion, sameSrc, bothNoImage }) {
    if (!hadCover || prefersReducedMotion) return 'none';
    if (toPhoto) return 'out';
    return sameSrc || bothNoImage ? 'none' : 'swap';
}

// 只在適合的時機播放，避免縮圖排重複閃動。
export function stripRevealPlan({ trigger, lightboxOpen, lightboxAnimating }) {
    if (!lightboxOpen) return { play: false, photo: false, films: false, next: false };
    if (trigger === 'switch') return { play: true, photo: true, films: true, next: true };
    if (trigger === 'next') return { play: true, photo: false, films: true, next: false };
    if (trigger === 'appear' && !lightboxAnimating) return { play: true, photo: true, films: true, next: true };
    return { play: false, photo: false, films: false, next: false };
}
export function isSameWork(nv, ov) {
    if (!nv) return true;
    if (!ov) return false;
    if (nv.path && ov.path) return sameWork(ov, nv) || sameWork(nv, ov);
    return sameNumber(nv.number, ov.number);
}
