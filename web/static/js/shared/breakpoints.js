/**
 * breakpoints.js — 共用響應式斷點常數（shared ESM）
 *
 * POSTER_CROP_MAX_W：posterCrop / lightbox-fit ghost-fly 路徑門檻。
 * MUST 對齊 showcase.css + search.css 的 poster-grid `@media (max-width: 899px)` 斷點
 * 與燈箱封面貼合 `@media (max-width: 899px)` 斷點（US-10 / CD-10）。
 * 由 tests/unit/test_frontend_lint.py::TestPosterCropThresholdAlignment 鎖死（改此值須同步 CSS）。
 */
export const POSTER_CROP_MAX_W = 899;
