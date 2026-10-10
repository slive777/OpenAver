# OpenAver - Codex Review Guidelines

## Product context and severity calibration

OpenAver is a **single-user, LAN-only desktop application** for managing a personal
video library. The user is also the operator. There is no multi-tenancy, no account
system, and **no hostile authenticated LAN user in the default threat model**;
external access is delegated to the user's Tailscale / Cloudflare Zero Trust rather
than built in.

Almost all metadata here — covers, NFO contents, sample images, focal coordinates — is
**cheaply recoverable**: by re-scraping, by recomputing, or by re-entering one small
adjustment. Grade severity by **recovery cost**, not by whether data is technically
"regenerable", and not by whether a defect exists in the abstract.

- **P0** — irreversibly destroys something the user cannot get back: the **video files
  themselves** (rename / move / delete / content overwrite), or **user-authored metadata
  with no external source and no automatic reconstruction** — custom tags, aliases,
  primary names. (A settings toggle is user-authored but trivially reset; not P0.)
- **P1** — **silent × batch × unattributable**: wrong data written across many items, no
  notification, the screen looks normal, and afterwards the user cannot tell which items
  were touched. Recovery cost scales with library size. Also: **leaked secrets or
  credentials**.
- **P2** — user-visible and wrong, but **single-item, visible at the time, and fixed by
  re-scraping or re-running**. Or a real weakening of a security boundary that the stated
  threat model actually covers.
- **P3** — everything else: internal consistency, theoretical edge cases requiring input a
  real user cannot produce, **a guard's completeness against additional bypasses (false
  negatives)** — narrowly, see the two-mode rule under "Out of scope" — and cosmetics.

**Explicitly NOT P0/P1 on their own**: covers, NFO contents, sample images, focal
coordinates. Overwriting them for a single title the user is looking at is an
inconvenience, not a loss. **The same overwrite applied silently across a batch IS P1** —
severity comes from the silence and the scale, not from the file type.

**Conversely, never stop at the surface of a finding.** A predicate that reads like a
trivial boolean edge case may reach `shutil.move()` on the user's video file — that is
P0. **Trace to the final sink (which file / which DB row / which flow) before assigning
severity.**

An issue requiring an attacker capability outside the stated threat model is P3
regardless of how severe the consequence would be if triggered. Say so explicitly
rather than omitting it.

### Reporting volume

Report **all blockers (P0/P1)**, plus at most **three** non-blocking suggestions per
round, ordered by blast radius. If items fell below the cut, say how many and in one
line what category — do not expand them.

## Review guidelines

### Review stages and scope

- Plan review is doc-first. Verify source only for load-bearing assumptions that
  could invalidate architecture or task scope.
- Implementation review is diff-first. Inspect changed hunks, their direct
  callers/consumers, and relevant DoD; do not repeat full plan archaeology.
- Follow-up review is delta-only plus same-root-cause siblings.
- Review statically — do NOT run tests, lint, builds, or coverage. The implementing
  change runs targeted tests pre-commit; pre-merge and CI run the full suite plus
  lint. Trust the review packet's test summary; if edge-case coverage is in doubt,
  read the test file rather than executing it. (Empirically, running them caught 0
  unique issues across 24 reviews while consuming large amounts of context.)
- Expand to repository-wide audit only for exhaustive-coverage claims,
  shared/global infrastructure, concurrency/lifecycle, migrations, security,
  external-service contracts, or when the first contradiction is found.
- Stop expanding when each high-risk claim has direct evidence and no new
  sibling contradiction remains.

### Review focus areas

- Cross-component and cross-thread timing.
- Error/early-return state symmetry and cleanup.
- External-service behavior versus code assumptions.
- Shared/global CSS, lifecycle, serialization, and configuration contracts.
- Architecture drift across multiple entry points.

### Security

- API responses MUST NOT contain `str(e)` or Python exception details. Error messages to frontend must be fixed Chinese strings (e.g. `"操作失敗"`), with details logged server-side via `logger.error()` or `logger.exception()`.
- No SQL injection — all database queries must use parameterized statements.
- No unvalidated user input used directly in file system operations (`open()`, `Path()`, `os.path`).
- No hardcoded secrets, API keys, passwords, or tokens in source code.
- **SSRF is best-effort, NOT a default blocker.** Per the threat model stated at the top of this file, the default model does not include a hostile authenticated LAN user; residual browser-origin risks (DNS rebinding / malicious webpages) are handled as defense-in-depth, not merge blockers. Review missing SSRF hardening in **new** backend URL-fetching code as a suggestion/P3, not P0/P1, and do not block a PR solely on absent SSRF guards.
  - Existing mitigations (private-IP rejection, no-redirect-follow, image-host allowlist, LAN opt-in) should not be casually removed or weakened.
  - Still flag clear regressions in already-hardened endpoints, unauthenticated arbitrary-request proxy behavior, or code that contradicts a feature's own stated security contract.

### Path handling

- All `file:///` URI construction and parsing MUST go through `core/path_utils.py`.
- Forbidden patterns outside `path_utils.py`:
  - `path[8:]` or `path[len('file:///'):]` (manual URI strip)
  - `f"file:///{...}"` (manual URI construction)
  - `replace('/', '\\')` for path conversion
  - `startswith('file:///')` + manual handling
- These patterns are already enforced mechanically by
  `scripts/static_guard_lint.mjs` rules tagged
  `[lint-guard 162c-test_no_raw_uri_strip]` /
  `[lint-guard 162c-test_no_manual_uri_construct]` /
  `[lint-guard 162c-test_no_shadow_path_helpers]` /
  `[lint-guard 162c-test_path_to_display_js_no_optional_slash]`
  (scanning every `.py` under `core/ web/ windows/ tests/` with
  `core/path_utils.py` excluded, plus
  `web/static/js/components/path-utils.js` for the `/?` display regex).
  **Do not re-run that check by hand, and do not assign a
  severity by pattern match** — if a violation reaches review at all, grade it by the
  product impact of what the wrong path actually writes to.

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
  - **"Milestone/release" means the milestone sync on `main` (`🎯 milestone:` commit) or the release step (tagging `vX.Y.Z`) — never a feature-branch PR.** A feature PR that bumps `core/version.py` and adds a CHANGELOG entry is still a development PR; the version bump does **not** turn it into a release, and the 4-locale parity rule does **not** apply to it.
  - In a feature PR, these are expected and **not findings**: new keys present only in `zh_TW.json`; obsolete keys removed from all 4 locales without replacements in `zh_CN.json` / `ja.json` / `en.json`; users of those locales seeing the `zh_TW` fallback text until the milestone sync. (Locales are overlaid on `zh_TW`, so nothing breaks — the text is just untranslated.)

### General code quality

- No `console.log` left in production JavaScript (except intentional debug modes).
- Python `except` blocks should not silently swallow errors — at minimum `logger.error()`.
- Avoid introducing new inline `<script>` blocks in templates; prefer separate `.js` files.

### Out of scope (handled by automated tooling)

> **v0.11.11 (test-deflation)**: For ordinary product-code PRs, do NOT redo the
> mechanical checks that unchanged lint rules already cover, and trust the author's
> lint/test summary.
>
> **Guards and tests are reviewed in two separate modes. Do not conflate them.**
>
> 1. **Guard migration or deletion — reviewed strictly.** If a guard is replaced or removed
>    and the replacement catches strictly less than the original, that is a **silent loss of
>    coverage**, i.e. a regression. Check target set, scope, first-vs-all match, count/order,
>    positive/negative polarity, anchor-absent behaviour, and granularity equivalence with
>    the guard it replaces — still without running lint or tests. Grade by the product impact
>    of what is **no longer caught**.
>
> 2. **Guard absolute strength — always P3, never a merge blocker.** "This guard can be
>    bypassed by renaming a variable"; "this guard does not recognise `.format()`". A
>    bypassable guard is strictly better than no guard, and completeness against an
>    open-ended language is not achievable. Report it once as a suggestion and move on — do
>    **not** re-raise the same guard file across rounds. Empirically, three guards in this
>    repository were escalated this way and none was won by continued patching; two were
>    resolved by reverting and one by replacing the mechanism.
>
>    **"Absolute strength" means *only* additional false-negative bypasses.** It does **not**
>    cover, and the P3-never-block rule does **not** apply to:
>    - **loss of existing coverage** (that is mode 1 above — a regression),
>    - **false positives on valid code** (the guard blocks legitimate work),
>    - **crashes, hangs, or altered test execution** (one intermediate version of a guard in
>      this repository hung the entire pytest run — no traceback, no failure list, just a job
>      that never ended).
>
>    Those three are **defects in the change itself**, not strength findings. Report them as
>    such; they block regardless of P-level, because they break the development loop. When
>    the defect was introduced by this same change, **reverting is the expected resolution** —
>    do not iterate forward on it.
>
> When a guard is genuinely missing, adding a lint rule is the fix, not a pytest string
> test — but a missing guard does NOT by itself lower severity. An actual product defect
> it would have caught is graded by product impact regardless of whether automation exists.

The lint layer. CI `lint-frontend` runs three phases: `npm run lint` (eslint + stylelint +
the four `.mjs` guards below), then `npm test` (node structural/unit tests), then
`ruff check .`. Counts below are indicative only — the live config/script is the source
of truth:

- **`scripts/static_guard_lint.mjs`** — table-driven static guard engine (kinds:
  `required-string` / `forbidden-string` / `dup-id` / `structure-count` / `tag-scan` /
  `inline-style-token` / `order` / `file-absent` / `paired-string`), with scoped matching
  (anchor-missing = fail-closed RED, brace-balanced method-body windows, comment
  stripping). Covers HTML templates (which eslint cannot parse), JS string fingerprints,
  and Python hardcoded-literal bans. This is the default home for any "string X must (not)
  appear in file Y" guard — including the former pytest guards for inline handlers, inline
  `style=display:none`, native-dialog strings, and clipboard optional-chaining, all
  migrated here.
- **`scripts/css-guard.mjs`** — CSS-block rules (Fluent token families, poster-crop,
  z-index cross-file ordering, vt-anchor, selector scoping, whole-text property scans).
- **`scripts/i18n_lint.mjs`** — used-but-missing i18n keys (RED), 4-locale parity (warn),
  orphan keys (warn), forbidden words in translations (「推薦」「風味」, RED).
- **`scripts/lint-settings-ia.mjs`** — settings.html IA layering (DOM-ancestry lock).
- **ESLint** (`eslint.config.mjs`, flat config; `no-restricted-syntax` groups + `SEL_*`
  selector constants — `SEL_SHOW_MODAL`, `SEL_TRACKED_EVENTSOURCE`, `SEL_CLIP_BAN`,
  `SEL_NO_WINDOW_OPEN_PATH`, etc.): anything expressed in the live config is out of review
  scope — consult the config, not a duplicate list here. Scope caveats that ARE still
  review territory: `no-console` covers **search pages only** (`console.error`/`warn`
  allowed); `document.createElement` ban covers **state mixins only**.
- **Stylelint** (`web/static/css/**/*.css`, excluding `tailwind.css`/`design-system.css`):
  `color-no-hex`, bare duration/blur/radius/box-shadow literal bans, selector disallow list.
- **Ruff** (Python — `core/`, `web/`, `windows/` + root scripts; `tests/` excluded):
  `F`, `E722`, `B` (incl. `B904`/`B905`/`B023`), `T201`, `S110`/`S112`.

**Still enforced by pytest** (deliberate KEEPs — flag these in review if violated):
- **`tests/unit/frontend_contracts/`** — now only `test_contract_animation.py` (1 test): a
  code-shape guard that string-scan lint cannot faithfully express.
- **`tests/unit/test_frontend_lint.py`** — only 2 tests remain. Together with the 1 above,
  these are the three "162c 模糊留" tests (each carries an in-file reason line); the
  second-review verdict was undecided, so they were kept rather than moved or deleted.
- Front-end static string guards (formerly the classes in `test_frontend_lint.py`, incl.
  `TestPathContract`) now live in `scripts/static_guard_lint.mjs` (and `css-guard.mjs`).
  New front-end guards go there, not into a new pytest class.
- **`[lint-guard: pytest-justified]`-tagged tests** elsewhere keep their tag with the reason
  stated; the tag rule below still applies.

Only read a KEEP test when the changed hunk touches the contract's producer, consumer, or
the contract test itself — do not routinely sweep all KEEPs.

(Anything outside the lint layer's expressed rules — formatting, dead code not caught by
ruff `F`, logic — is still in code-review scope.)

### Test bloat policy

DO NOT request new pytest tests for anything the lint layer can express.
If a regression of this class arises, the fix is:
- a new rule row in `scripts/static_guard_lint.mjs` (the engine already exists — adding a
  rule is a table entry, not a new script), or `css-guard.mjs` / `i18n_lint.mjs` / eslint /
  stylelint for their domains — NOT a new TestNoXxx pytest class.
- New assertions in `tests/**` that check a **literal string against frontend
  HTML/JS/CSS text** — i.e. the shape `assert "<literal>" in (html|js|css_text)` or its
  `not in` negation, including incremental additions to a for-loop/list of such literals —
  must carry an inline `# [lint-guard: pytest-justified <reason> | migrate → <tool>]` tag;
  pre-merge SA-pre-6 flags untagged ones as BLOCKER. The canonical criterion lives in
  `feature/AI_COLLABORATION/pre-merge.md` 步驟 5.7 — read it before flagging.
  **Out of scope for this rule** (no lint tool can express these, so they belong in pytest
  and need no tag): assertions on the *return value* of Python code — scraper parse results
  (`assert video.title == "…"`, `assert "tag" in video.tags`), request URLs a client builds,
  JSON API response bodies, DB round-trips. (Asserting a literal against
  `TestClient(...).get(...).text` when that response **is** HTML/JS/CSS is still in scope.) The 8 existing scraper test files carry ~500 such
  assertions and none is tagged; that is correct, not debt.
- When migrating a guard to lint, port it at the **same scan granularity** as the original
  (whole-file / element-scoped / attribute-value / method-body window) and prefer
  fail-closed over fail-open — 7 scope-narrowing regressions of exactly this kind were
  caught by review during the v0.11.11 test-deflation.
- **No captured third-party site responses under `tests/`.** Flag any PR that adds a
  saved HTML/JSON page from an external site as a test fixture, or a `.gitignore`
  negation re-allowing `*.html` under `tests/` (default: `*.html` is ignored). Site
  structure is verified against the live site when a scraper is actually being fixed
  (canary NG → owner reproduces → compare with the live page); a stored copy goes stale
  silently and only adds friction. Behaviour of **our own** logic (exact-name matching,
  empty-result handling, the custom-source interpreter) is tested with a few lines of
  inline synthetic markup inside the test file. Severity P3, but flag it every time.
