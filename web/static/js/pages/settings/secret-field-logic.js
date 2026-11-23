/**
 * secret-field-logic.js — API Key two-state field state machine (no DOM, no Alpine, no window)
 *
 * CD-206-6: wire truth table (configured sends server mask as-is, replacing
 * with empty input keeps the key, clearing sends empty); CD-206-7: mask
 * function injected by the caller, never imported here.
 */

export function createSecretField(serverMask) {
    if (serverMask) return { state: 'configured', mask: serverMask, input: '' };
    return { state: 'unset', mask: '', input: '' };
}

export function startReplace(f) {
    if (f.state === 'configured' || f.state === 'clearing') {
        return { state: 'replacing', mask: f.mask, input: '' };
    }
    return { state: f.state, mask: f.mask, input: f.input };
}

export function requestClear(f) {
    if (f.state === 'configured' || f.state === 'replacing') {
        return { state: 'clearing', mask: f.mask, input: '' };
    }
    return { state: f.state, mask: f.mask, input: f.input };
}

export function wireValue(f) {
    const v = String(f.input ?? '').trim();
    if (f.state === 'configured') return f.mask;
    if (f.state === 'replacing') return v === '' ? f.mask : v;
    if (f.state === 'clearing') return '';
    return v;
}

export function previewText(f, maskFn) {
    const t = String(f.input ?? '').trim();
    if ((f.state === 'unset' || f.state === 'replacing') && t !== '') return maskFn(t);
    return '';
}

export function isDirty(f) {
    return wireValue(f) !== f.mask;
}

export function afterSave(f, maskFn) {
    const w = wireValue(f);
    if (w === '') return { state: 'unset', mask: '', input: '' };
    if (w === f.mask) return { state: 'configured', mask: f.mask, input: '' };
    return { state: 'configured', mask: maskFn(w), input: '' };
}
