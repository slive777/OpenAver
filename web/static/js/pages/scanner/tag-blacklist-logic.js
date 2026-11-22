const ERROR_KEYS = {
    empty: 'scanner.tag_blacklist.error.empty',
    invalid: 'scanner.tag_blacklist.error.invalid',
    cover_badge: 'scanner.tag_blacklist.error.cover_badge',
    duplicate: 'scanner.tag_blacklist.error.duplicate',
};

export function errorKeyFor(code) {
    return Object.hasOwn(ERROR_KEYS, code) ? ERROR_KEYS[code] : 'scanner.tag_blacklist.error.generic';
}

export function suggestionChips(suggestions, items) {
    const keys = new Set((Array.isArray(items) ? items : []).map(item => item.key));
    return (Array.isArray(suggestions) ? suggestions : []).map(name => ({
        name,
        added: keys.has(String(name).trim().toLowerCase()),
    }));
}
