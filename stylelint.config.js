/** @type {import('stylelint').Config} */
module.exports = {
  extends: ['stylelint-config-standard'],
  ignoreFiles: [
    // Tailwind compiled output — not hand-authored, contains all manner of values
    'web/static/css/tailwind.css',
    // §6 fail-sample demo page — intentionally contains hardcoded values as
    // counter-examples; per-block disable comments would add ~30 noise lines.
    'web/static/css/pages/design-system.css',
  ],
  rules: {
    'color-no-hex': true,
    'declaration-property-value-disallowed-list': {
      '/^transition/': ['/\\b0?\\.\\d+s\\b/'],
      '/^(-webkit-)?(backdrop-)?filter$/': ['/blur\\(\\s*\\d+px/'],
      'box-shadow': ['/\\brgba\\(\\s*\\d/'],
      'border-radius': ['/^\\d+px/'],
      'object-position': ['/100%\\s+20%/'],
      // feature/76：禁手動把 view-transition-name 設為 root（root 是隱式預設，手動覆寫會
      // 與主題切換的 ::view-transition-*(root) 機制混亂）。命名一律走 sidebar/main-content/none。
      'view-transition-name': ['root'],
    },
    'selector-disallowed-list': ['/:is\\([^)]*manual-input/'],
    // Standard config rules relaxed for OpenAver's existing CSS conventions
    'no-descending-specificity': null,
    'alpha-value-notation': null,
    'color-function-notation': null,
    'hue-degree-notation': null,
    'media-feature-range-notation': null,
    'selector-class-pattern': null,
    'keyframes-name-pattern': null,
    'custom-property-pattern': null,
    'declaration-block-no-redundant-longhand-properties': null,
    'shorthand-property-no-redundant-values': null,
    'no-duplicate-selectors': null,
    'font-family-name-quotes': null,
    'font-family-no-missing-generic-family-keyword': null,
    'value-keyword-case': null,
    'property-no-vendor-prefix': null,
    'value-no-vendor-prefix': null,
    'at-rule-no-unknown': [true, { ignoreAtRules: ['tailwind', 'apply', 'layer', 'screen', 'variants', 'responsive', 'theme', 'plugin', 'config', 'source', 'utility', 'custom-variant', 'reference', 'view-transition'] }],
    'no-empty-source': null,
    'no-invalid-position-at-import-rule': null,
    'rule-empty-line-before': null,
    'comment-empty-line-before': null,
    'declaration-empty-line-before': null,
    'comment-whitespace-inside': null,
    'length-zero-no-unit': null,
    'number-max-precision': null,
    'declaration-block-single-line-max-declarations': null,
    'media-query-no-invalid': null,
    'function-no-unknown': null,
    'import-notation': null,
    'selector-pseudo-class-no-unknown': null,
    'selector-id-pattern': null,
    'selector-attribute-quotes': null,
    'lightness-notation': null,
    'at-rule-empty-line-before': null,
    'custom-property-empty-line-before': null,
  },
};
