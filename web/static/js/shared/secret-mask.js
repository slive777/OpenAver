/**
 * secret-mask.js — API key mask shared with the server (CD-206-7)
 *
 * Same rule as Python core.secret_fields.mask_secret: a short value (fewer
 * than 16 code points) collapses to four bullets, a longer value keeps the
 * first and last four code points so the user can recognise which key was
 * pasted. Length and slices count code points (Array.from), so astral
 * characters mask identically here and in Python. Pure function: no import,
 * no window / document.
 */

const MASK4 = '\u2022'.repeat(4);

export function maskSecret(value) {
    const chars = Array.from(String(value ?? ''));
    if (chars.length === 0) return '';
    if (chars.length < 16) return MASK4;
    return chars.slice(0, 4).join('') + MASK4 + chars.slice(-4).join('');
}
