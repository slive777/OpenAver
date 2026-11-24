/**
 * openai-endpoint.js — OpenAI Base URL normalization shared with the server.
 *
 * Same rule as Python core.openai_client.normalize_openai_base_url: trim,
 * strip trailing slashes, strip a trailing /chat/completions or /models
 * segment (case-insensitive, on a slash boundary) in a loop until stable.
 * Strip suffixes only after scheme://host, never from the hostname.
 * No import, no window / document. Pure functions.
 */

const ENDPOINT_SUFFIXES = ['/chat/completions', '/models'];

function stripOneSuffix(url) {
  const loweredTail = (s) => url.slice(url.length - s.length).toLowerCase();
  for (const suffix of ENDPOINT_SUFFIXES) {
    if (url.length >= suffix.length && loweredTail(suffix) === suffix) {
      return url.slice(0, url.length - suffix.length);
    }
  }
  return null;
}

export function normalizeOpenaiBaseUrl(raw) {
  let url = String(raw ?? '').trim();
  for (;;) {
    url = url.replace(/\/+$/, '');
    const prefix = url.match(/^[A-Za-z][A-Za-z0-9+.\-]*:\/\/[^/?#]*/)?.[0] ?? '';
    const stripped = stripOneSuffix(url.slice(prefix.length));
    if (stripped === null) return url;
    url = prefix + stripped;
  }
}

export function openaiEndpointPreview(raw) {
  const normalized = normalizeOpenaiBaseUrl(raw);
  if (normalized === '') return '';
  return `${normalized}/chat/completions`;
}
