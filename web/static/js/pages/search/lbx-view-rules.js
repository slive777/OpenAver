// Adapt search and wishlist items to the shared lightbox data shape.
const str = (value) => value == null ? '' : String(value);
const array = (value) => Array.isArray(value) ? value : [];

export function toLbxVideo(item, kind) {
    if (!item || typeof item !== 'object') return null;
    const isResult = kind === 'result';
    const tr = isResult ? str(item.translated_title) : '';
    const duration = Number(item.duration) || 0;
    return {
        number: str(item.number),
        title: tr || str(item.title),
        original_title: tr ? str(item.title) : '',
        actresses: array(isResult ? item.actors : item.actresses).join(','),
        tags: array(item.tags).join(','),
        release_date: str(isResult ? item.date : item.release_date),
        source_duration: duration,
        duration,
        maker: str(item.maker),
        label: str(item.label),
        series: str(item.series),
        director: str(item.director),
        sample_images: array(item.sample_images),
        preview_sample_images: array(item.preview_sample_images),
        summary: isResult ? (str(item.translated_summary) || str(item._summary)) : '',
    };
}

export function lbxItemKey(kind, item) {
    if (!item || typeof item !== 'object') return '';
    const num = str(item.number);
    if (kind === 'wishlist') return `w|${num}`;
    return `r|${num}|${str(item.source)}|${str(item.url)}`;
}
