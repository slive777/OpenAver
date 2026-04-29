# OpenAver - Codex Review Guidelines

## Review guidelines

### Security

- API responses MUST NOT contain `str(e)` or Python exception details. Error messages to frontend must be fixed Chinese strings (e.g. `"操作失敗"`), with details logged server-side via `logger.error()` or `logger.exception()`.
- No SQL injection — all database queries must use parameterized statements.
- No unvalidated user input used directly in file system operations (`open()`, `Path()`, `os.path`).
- No hardcoded secrets, API keys, passwords, or tokens in source code.

### Path handling

- All `file:///` URI construction and parsing MUST go through `core/path_utils.py`.
- Forbidden patterns outside `path_utils.py`:
  - `path[8:]` or `path[len('file:///'):]` (manual URI strip)
  - `f"file:///{...}"` (manual URI construction)
  - `replace('/', '\\')` for path conversion
  - `startswith('file:///')` + manual handling
- If you see any of these patterns, flag as P0.

### Alpine.js

- `document.querySelector('[x-data]')` without a scoped selector (e.g. `.search-container[x-data]`) is a bug — it selects the sidebar instead of the page component.
- Alpine methods in templates must be called with `()` — `:disabled="!canGoPrev"` is wrong, `:disabled="!canGoPrev()"` is correct.

### i18n

- Strategy: **source locale only + milestone sync**. During development PRs, only `locales/zh_TW.json` is required to be updated.
- Missing keys or entire subtrees in `zh_CN.json`, `ja.json`, or `en.json` during development **are not findings**.
- **Flag these**:
  - hardcoded Chinese UI text in HTML/JS that should use `t()` / `window.t()`
  - `t()` / `window.t()` referencing keys missing from `zh_TW.json`
  - HTML-containing translations rendered without `| safe`
- **Out of scope for i18n review**:
  - `showToast()`, `alert()`, `confirm()`
  - SSE messages
  - `console.*`
  - technical terms such as NFO, API Key, Jellyfin, Proxy
  - browser/platform built-in text
  - **`design-system` and `motion-lab` page demo content** — these are internal dev-reference pages (not in main nav, not user-facing), and demo labels often contain Fluent design tokens (`fluent-decel`, `Acrylic 30px`, `--surface-1` etc.) that should not be translated. Page chrome (nav / page title) still goes through i18n; only demo body text is exempt.
- At milestone/release, all 4 locales must have identical key sets.

### General code quality

- No `console.log` left in production JavaScript (except intentional debug modes).
- Python `except` blocks should not silently swallow errors — at minimum `logger.error()`.
- Avoid introducing new inline `<script>` blocks in templates; prefer separate `.js` files.
