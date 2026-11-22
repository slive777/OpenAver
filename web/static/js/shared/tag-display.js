export function workTagsOf(video) {
    if (!video) return [];
    const tags = typeof video.tags_display === 'string' ? video.tags_display : (video.tags || '');
    return tags.split(',').map((t) => t.trim()).filter(Boolean);
}
export function isTagHidden(tag, hidden) {
    return Array.isArray(hidden) && hidden.includes(String(tag).trim().toLowerCase());
}
export function visibleUserTags(video, hidden) {
    return (video?.user_tags || []).filter((t) => !isTagHidden(t, hidden));
}
export function lightboxWorkTags(video, hidden) {
    const mine = new Set(visibleUserTags(video, hidden).map((t) => String(t).trim()));
    return workTagsOf(video).filter((t) => !mine.has(t));
}
