export function buildAiAliasPrompt(locale, origin) {
    const key = ['zh-TW', 'zh-CN', 'ja', 'en', 'ko'].includes(locale) ? locale : 'zh-TW';
    return window.t('scanner.tag_alias.ai_prompt.body', { lang: window.t('scanner.tag_alias.ai_prompt.lang.' + key), url: origin + '/api/capabilities' });
}
