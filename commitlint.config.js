module.exports = {
  extends: ['@commitlint/config-conventional'],
  rules: {
    // Match the types documented in CONTRIBUTING.md
    'type-enum': [2, 'always', [
      'feat', 'fix', 'docs', 'refactor', 'test', 'chore'
    ]],
    // Subject line max 72 chars (matches CONTRIBUTING.md)
    'header-max-length': [2, 'always', 72],
    // No period at end (matches CONTRIBUTING.md)
    'subject-full-stop': [2, 'never', '.'],
    // Lowercase subject (matches CONTRIBUTING.md)
    'subject-case': [2, 'always', 'lower-case'],
  },
};
