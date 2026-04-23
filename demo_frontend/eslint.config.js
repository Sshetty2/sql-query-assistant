import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

// Defense-in-depth rule: every Object.keys / Object.entries / Object.values
// call gets flagged. The rule is intentionally noisy — at every call site
// the developer has to decide "yes, the argument is guaranteed non-null"
// and either restructure or add an explicit
//   // eslint-disable-next-line no-restricted-syntax -- guarded above
// comment with the rationale. The original `Object.keys(data[0])` crash
// (FRONTEND_HARDENING.md) would have tripped this rule before shipping.
//
// We cover all four iteration helpers; Object.fromEntries is excluded
// because it usually receives a literal array, not a backend value.
const noUnguardedObjectIteration = {
  selector:
    "CallExpression[callee.object.name='Object'][callee.property.name=/^(keys|entries|values)$/]",
  message:
    "Object.keys/entries/values throws on null/undefined and silently iterates strings as char arrays. " +
    "Guard with `x != null && typeof x === 'object'` first, OR use a safe helper like safeStringArray. " +
    "If the argument is provably non-null at this site, opt out with " +
    "`// eslint-disable-next-line no-restricted-syntax -- <reason>`.",
}

// Bonus rule: array indexing without explicit length/null check is the
// other half of the original bug. `data[0]` returns undefined for an
// empty array, and `Object.keys(undefined)` throws. We can't catch every
// `[0]` because some are on local-known arrays — but we can flag the
// pattern of indexing the first element of a maybe-array prop directly.
// This selector catches `data[0]` / `result[0]` / `rows[0]` etc. on any
// identifier whose name suggests a backend collection.
const noUnguardedFirstElement = {
  selector:
    "MemberExpression[object.type='Identifier'][object.name=/^(data|result|rows|items|records|list)$/][property.type='Literal'][property.value=0][computed=true]",
  message:
    "Indexing the first element of `data/result/rows/items/records/list` " +
    "without a length+null check can yield undefined, then crash on property access. " +
    "Use `arr.find((x): x is T => x != null)` or guard `arr?.length && arr[0] != null` first.",
}

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    rules: {
      'no-restricted-syntax': [
        'warn',
        noUnguardedObjectIteration,
        noUnguardedFirstElement,
      ],
    },
  },
  // The runtime schema validator and the ErrorBoundary itself need to call
  // Object.keys/entries on backend data — that's literally their job.
  // Exempt them so the rule doesn't fight legitimate uses.
  {
    files: ['src/api/schemas.ts', 'src/components/ErrorBoundary.tsx'],
    rules: {
      'no-restricted-syntax': 'off',
    },
  },
])
