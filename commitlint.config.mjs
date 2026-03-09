export default {
  extends: ['@commitlint/config-conventional'],
  rules: {
    // Match the types documented in CONTRIBUTING.md plus standard types
    // from @commitlint/config-conventional that are useful in practice.
    // ci: CI/CD changes, perf: performance, build: build system, revert: undo
    'type-enum': [2, 'always', [
      'feat', 'fix', 'docs', 'refactor', 'test', 'chore',
      'ci', 'perf', 'build', 'revert'
    ]],
    // Subject line max 72 chars (matches CONTRIBUTING.md)
    'header-max-length': [2, 'always', 72],
    // No period at end (matches CONTRIBUTING.md)
    'subject-full-stop': [2, 'never', '.'],
    // Use config-conventional default: reject sentence-case, start-case,
    // pascal-case, and upper-case subjects. This enforces lowercase-first
    // subjects while allowing uppercase mid-subject (filenames, acronyms,
    // env vars). Inheriting the default so we don't override here.
  },
};
